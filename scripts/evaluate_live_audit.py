#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "live-audit-policy.json"

TRIGGERS = [
    "BEFORE_SELECTED_WORK_START",
    "BEFORE_PROTECTED_BOUNDARY",
    "AFTER_NEW_RESEARCH_BATCH",
    "AFTER_NEW_VERIFIED_EVIDENCE",
    "AFTER_REQUIRED_CHECK_TERMINAL",
    "AFTER_AUTHORITATIVE_READBACK_TERMINAL",
    "LIVE_MAIN_SHA_CHANGED",
    "TRACKED_PR_HEAD_OR_STATE_CHANGED",
    "GOAL_REVISION_OR_CONTROL_SIGNAL_CHANGED",
    "REQUIRED_CLAIM_STATE_GENERATION_OR_EXPIRY_CHANGED",
    "OPEN_BLOCKER_SET_CHANGED",
    "BEFORE_TERMINAL_COMPLETION",
    "BEFORE_FINAL_REQUIRED_CLAIM_RELEASE",
]
DIMENSIONS = [
    "GOAL_ALIGNMENT",
    "OWNERSHIP_AND_FENCE",
    "DEPENDENCY_AND_INVARIANT_COVERAGE",
    "REGRESSION_STATE",
    "RESEARCH_EVIDENCE_HORIZON",
    "NEW_SYSTEM_EVIDENCE",
    "DURABLE_LESSON_OR_DEFECT_ROUTING",
]
DIMENSION_STATES = ["PASS", "ISSUE", "NOT_RUN"]
FINDING_STATES = [
    "NONE",
    "CANDIDATE",
    "VERIFIED_REPAIR",
    "RESEARCH_DESIGN_CHANGE",
    "VERIFICATION_GAP",
    "UNRESOLVED_EXTERNAL_EFFECT",
]
VERIFIED_CLASSES = [
    "REQUIRED_CHECK_FAILURE",
    "SCHEMA_OR_INVARIANT_VIOLATION",
    "AUTHORITATIVE_LIVE_MISMATCH",
    "VERSIONED_FALSIFICATION_FAILURE",
    "VERIFIED_PLATFORM_INCOMPATIBILITY",
]
REQUIRED_FIELDS = {
    "trigger_id",
    "dimension_states",
    "finding_state",
    "verified_repair_evidence_class",
    "root_goal_id",
    "detector_or_invariant_id",
    "subject_id",
    "component_id",
    "resource_state",
    "authorization_state",
    "cost_state",
    "platform_state",
}


class LiveAuditError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise LiveAuditError(message)


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{path.name} must contain one JSON object")
    return value


def validate_policy(policy: dict) -> None:
    if policy.get("schema_version") != 1 or policy.get("policy_id") != "life-live-worker-audit-repair-first-v1":
        fail("live audit policy identity mismatch")
    if policy.get("runtime_control_authority") != "NONE":
        fail("live audit runtime control authority must be NONE")
    if policy.get("assistant_procedure_authority") != "BOOTSTRAP_REQUIRED_GOVERNANCE":
        fail("live audit assistant procedure authority mismatch")
    if policy.get("mode") != "IN_RUN_EVENT_BOUNDARY_DRIVEN":
        fail("live audit mode mismatch")
    if policy.get("loop") != ["AUDIT", "CLASSIFY", "FIX_OR_REPLAN", "VERIFY", "RESUME_PARENT_GOAL"]:
        fail("live audit loop mismatch")
    if policy.get("trigger_ids") != TRIGGERS:
        fail("live audit trigger set/order mismatch")
    if policy.get("audit_dimensions") != DIMENSIONS:
        fail("live audit dimension set/order mismatch")
    if policy.get("dimension_states") != DIMENSION_STATES:
        fail("live audit dimension states mismatch")
    if policy.get("finding_states") != FINDING_STATES:
        fail("live audit finding states mismatch")
    if policy.get("verified_repair_evidence_classes") != VERIFIED_CLASSES:
        fail("live audit verified repair evidence classes mismatch")
    if "QUEUED_ONLY_IS_NOT_A_HANDLED_VERIFIED_REPAIR_STATE" not in policy.get("queue_rule", ""):
        fail("live audit queue waiting-room prohibition missing")
    if "UNRESOLVED_EXTERNAL_EFFECT_RECONCILIATION_PRECEDES_REPAIR_EXECUTION" not in policy.get("selection_binding_rule", ""):
        fail("live audit unresolved external effect precedence missing")
    if "GOAL_RELATION_DEFECT_REPAIR" not in policy.get("parent_goal_rule", ""):
        fail("live audit defect repair child binding missing")
    if "SHA256" not in policy.get("repair_identity_rule", ""):
        fail("live audit deterministic repair identity rule missing")
    if "ZERO_AUTHORIZATION_ROUTING_PRIORITY_COMPLETION_VERIFICATION_RELEASE_MUTATION_OR_EFFECT_EXECUTION_AUTHORITY" not in policy.get("non_authority_rule", ""):
        fail("live audit evidence non-authority rule missing")


def nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or any(ord(ch) < 32 for ch in value):
        fail(f"{field} must be a nonempty control-character-free string")
    return value


def repair_identity(value: dict) -> str:
    fields = [
        value["root_goal_id"],
        value["verified_repair_evidence_class"],
        value["detector_or_invariant_id"],
        value["subject_id"],
        value["component_id"],
    ]
    digest = hashlib.sha256("\0".join(fields).encode("utf-8")).hexdigest()
    return f"repair-{digest}"


def validate_evidence(evidence: object, policy: dict) -> dict:
    if not isinstance(evidence, dict) or set(evidence) != REQUIRED_FIELDS:
        fail("live audit evidence keys mismatch")
    if evidence["trigger_id"] not in TRIGGERS:
        fail("trigger_id invalid")
    dimensions = evidence["dimension_states"]
    if not isinstance(dimensions, dict) or list(dimensions) != DIMENSIONS:
        fail("dimension_states keys/order mismatch")
    if any(dimensions[name] not in DIMENSION_STATES for name in DIMENSIONS):
        fail("dimension state invalid")
    finding = evidence["finding_state"]
    if finding not in FINDING_STATES:
        fail("finding_state invalid")
    repair_class = evidence["verified_repair_evidence_class"]
    if finding == "VERIFIED_REPAIR":
        if repair_class not in VERIFIED_CLASSES:
            fail("VERIFIED_REPAIR requires one exact verified repair evidence class")
    elif repair_class is not None:
        fail("verified_repair_evidence_class is allowed only for VERIFIED_REPAIR")
    for field in ("root_goal_id", "detector_or_invariant_id", "subject_id", "component_id"):
        nonempty(evidence[field], field)
    if re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", evidence["component_id"]) is None:
        fail("component_id must be snake_case")
    for field, allowed in policy["blocker_states"].items():
        if evidence[field] not in allowed:
            fail(f"{field} invalid")
    return evidence


def evaluate(evidence: object) -> dict:
    policy = load(POLICY_PATH)
    validate_policy(policy)
    value = validate_evidence(evidence, policy)
    dims = value["dimension_states"]
    finding = value["finding_state"]

    result_state = "NO_COURSE_CHANGE_EVIDENCE"
    disposition = "CONTINUE_SELECTED_WORK"
    lifecycle = "NONE"
    rid = None

    if any(state == "NOT_RUN" for state in dims.values()):
        result_state, disposition = "NOT_RUN", "NOT_RUN"
    elif finding == "UNRESOLVED_EXTERNAL_EFFECT":
        result_state, disposition = "EFFECT_RECONCILIATION_REQUIRED", "RECONCILE_EFFECT_BEFORE_CONTINUE"
    elif finding == "RESEARCH_DESIGN_CHANGE":
        result_state, disposition = "REPLAN_CANDIDATE", "REPLAN_BEFORE_PROTECTED_MUTATION"
    elif finding == "VERIFICATION_GAP":
        result_state, disposition = "VERIFICATION_REQUIRED", "VERIFY_BEFORE_CONTINUE"
    elif finding == "VERIFIED_REPAIR":
        lifecycle = "REPAIR_REQUIRED"
        rid = repair_identity(value)
        if value["authorization_state"] == "BLOCKED":
            result_state = disposition = "BLOCKED_AUTHORIZATION"
        elif value["resource_state"] == "BLOCKED":
            result_state = disposition = "BLOCKED_RESOURCE"
        elif value["cost_state"] == "BLOCKED":
            result_state = disposition = "BLOCKED_COST"
        elif value["platform_state"] == "BLOCKED":
            result_state = disposition = "BLOCKED_PLATFORM"
        else:
            result_state, disposition = "VERIFICATION_REQUIRED", "EXECUTE_VERIFIED_REPAIR_CHILD"
    elif finding == "CANDIDATE":
        result_state, disposition = "DEFECT_CANDIDATE", "RECORD_DEFECT_CANDIDATE"
    elif dims["RESEARCH_EVIDENCE_HORIZON"] == "ISSUE":
        result_state, disposition = "RESEARCH_EXPANSION_REQUIRED", "EXPAND_RESEARCH"
    elif any(state == "ISSUE" for state in dims.values()):
        result_state, disposition = "DEFECT_CANDIDATE", "RECORD_DEFECT_CANDIDATE"

    return {
        "policy_id": policy["policy_id"],
        "audit_result_state": result_state,
        "execution_disposition": disposition,
        "repair_lifecycle_transition": lifecycle,
        "repair_identity": rid,
        "goal_relation": "DEFECT_REPAIR" if lifecycle == "REPAIR_REQUIRED" else None,
        "candidate_control_effect": "ZERO" if finding == "CANDIDATE" else "NOT_APPLICABLE",
        "runtime_control_authority": "NONE",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--validate-policy", action="store_true")
    group.add_argument("--evaluate")
    args = parser.parse_args()
    try:
        policy = load(POLICY_PATH)
        validate_policy(policy)
        if args.evaluate:
            evidence = json.loads(Path(args.evaluate).read_text(encoding="utf-8"))
            print(json.dumps(evaluate(evidence), indent=2))
        else:
            print("LIVE_AUDIT_POLICY_VALID")
        return 0
    except (LiveAuditError, OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
