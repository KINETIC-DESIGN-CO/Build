#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "live-audit-policy.json"

REQUIRED_FIELDS = {
    "finding_state",
    "verified_repair_evidence_class",
    "resource_state",
    "authorization_state",
    "cost_state",
    "platform_state",
    "touches_verification_trust_root",
    "verification_trust_state",
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
    if policy.get("schema_version") != 1:
        fail("live audit schema_version must be 1")
    if policy.get("policy_id") != "life-live-audit-repair-first-v1":
        fail("live audit policy_id mismatch")
    if policy.get("runtime_control_authority") != "NONE":
        fail("live audit runtime control authority must be NONE")
    if policy.get("assistant_procedure_authority") != "BOOTSTRAP_REQUIRED_GOVERNANCE":
        fail("live audit assistant procedure authority mismatch")
    expected_loop = ["AUDIT", "CLASSIFY", "FIX_OR_REPLAN", "VERIFY", "RESUME_PARENT_GOAL"]
    if policy.get("loop") != expected_loop:
        fail("live audit loop mismatch")
    required_triggers = {
        "RUN_START",
        "BEFORE_SELECTED_WORK_START",
        "BEFORE_PROTECTED_MUTATION",
        "AFTER_RESEARCH_RESULT",
        "AFTER_TOOL_OR_CONNECTED_SYSTEM_RESULT",
        "AFTER_REQUIRED_CHECK_RESULT",
        "AFTER_LIVE_STATE_CHANGE",
        "AFTER_MUTATION_READBACK",
        "BEFORE_COMPLETION",
        "BEFORE_RELEASE",
    }
    if set(policy.get("trigger_ids", [])) != required_triggers:
        fail("live audit trigger set mismatch")
    expected_evidence = {
        "REQUIRED_CHECK_FAILURE",
        "SCHEMA_OR_INVARIANT_VIOLATION",
        "AUTHORITATIVE_LIVE_MISMATCH",
        "VERSIONED_FALSIFICATION_FAILURE",
        "VERIFIED_PLATFORM_INCOMPATIBILITY",
    }
    if set(policy.get("verified_repair_evidence_classes", [])) != expected_evidence:
        fail("verified repair evidence class set mismatch")
    expected_dispositions = {
        "NO_CHANGE",
        "CANDIDATE_ONLY",
        "IMMEDIATE_REPAIR",
        "IMMEDIATE_REPLAN",
        "BLOCKED_RESOURCE",
        "BLOCKED_AUTHORIZATION",
        "BLOCKED_COST",
        "BLOCKED_PLATFORM",
        "BLOCKED_VERIFICATION_TRUST",
    }
    if set(policy.get("dispositions", [])) != expected_dispositions:
        fail("live audit disposition set mismatch")
    forbidden = set(policy.get("passive_terminal_states_forbidden", []))
    if not {"DOCUMENTED", "DEFERRED", "QUEUED_ONLY"}.issubset(forbidden):
        fail("passive terminal states must remain forbidden")


def validate_evidence(evidence: object, policy: dict) -> dict:
    if not isinstance(evidence, dict) or set(evidence) != REQUIRED_FIELDS:
        fail("live audit evidence keys mismatch")
    if evidence["finding_state"] not in policy["finding_states"]:
        fail("finding_state invalid")
    repair_class = evidence["verified_repair_evidence_class"]
    if repair_class is not None and repair_class not in policy["verified_repair_evidence_classes"]:
        fail("verified_repair_evidence_class invalid")
    if evidence["finding_state"] == "VERIFIED_REPAIR" and repair_class is None:
        fail("VERIFIED_REPAIR requires a verified repair evidence class")
    if evidence["finding_state"] != "VERIFIED_REPAIR" and repair_class is not None:
        fail("verified repair evidence class is allowed only for VERIFIED_REPAIR")
    for field, allowed in policy["blocker_states"].items():
        if evidence[field] not in allowed:
            fail(f"{field} invalid")
    if not isinstance(evidence["touches_verification_trust_root"], bool):
        fail("touches_verification_trust_root must be boolean")
    if not evidence["touches_verification_trust_root"] and evidence["verification_trust_state"] == "BLOCKED":
        fail("verification trust may be BLOCKED only when the repair touches the verification trust root")
    return evidence


def evaluate(evidence: object) -> dict:
    policy = load(POLICY_PATH)
    validate_policy(policy)
    value = validate_evidence(evidence, policy)

    finding = value["finding_state"]
    if finding == "NONE":
        disposition = "NO_CHANGE"
    elif finding == "CANDIDATE":
        disposition = "CANDIDATE_ONLY"
    elif finding == "RESEARCH_DESIGN_CHANGE":
        disposition = "IMMEDIATE_REPLAN"
    else:
        if value["authorization_state"] == "BLOCKED":
            disposition = "BLOCKED_AUTHORIZATION"
        elif value["resource_state"] == "BLOCKED":
            disposition = "BLOCKED_RESOURCE"
        elif value["cost_state"] == "BLOCKED":
            disposition = "BLOCKED_COST"
        elif value["platform_state"] == "BLOCKED":
            disposition = "BLOCKED_PLATFORM"
        elif value["touches_verification_trust_root"] and value["verification_trust_state"] != "PASS":
            disposition = "BLOCKED_VERIFICATION_TRUST"
        else:
            disposition = "IMMEDIATE_REPAIR"

    return {
        "policy_id": policy["policy_id"],
        "disposition": disposition,
        "repair_now": disposition == "IMMEDIATE_REPAIR",
        "replan_now": disposition == "IMMEDIATE_REPLAN",
        "deferred_only_by_exact_blocker": disposition.startswith("BLOCKED_"),
        "candidate_preemption_effect": "ZERO" if disposition == "CANDIDATE_ONLY" else "NOT_APPLICABLE",
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
