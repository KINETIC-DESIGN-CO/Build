#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "research-policy.json"

REQUIRED_LANES = [
    "WHOLE_SOURCE_CONTEXT",
    "SOURCE_SYSTEM_CONTEXT",
    "SAME_SOURCE_PARALLEL",
    "INDEPENDENT_PARALLEL_EVIDENCE",
    "COMPETING_MECHANISMS",
    "FAILURE_AND_COUNTEREXAMPLE_EVIDENCE",
    "DISCONFIRMATION_SEARCH",
    "LIFE_REEVALUATION",
]
LANE_STATES = ["EVIDENCE_FOUND", "NO_EVIDENCE_FOUND", "NOT_APPLICABLE", "NOT_RUN"]
REQUIRED_CATEGORIES = [
    "LIFECYCLE_OR_STATE_MODEL",
    "FAILURE_MODES",
    "RENEWAL_TAKEOVER_PREEMPTION_OR_CANCELLATION",
    "STALE_RESULT_VERSIONING_OR_FENCING",
    "RECOVERY_OR_IDEMPOTENCY",
    "LIMITS_QUOTAS_OR_COST",
    "OPERATIONAL_CAVEATS",
]
DISPOSITIONS = ["KEEP", "REPLACE", "MODIFY", "COMBINE", "REMOVE"]
RECORD_KEYS = {"lane_results", "selected_disposition", "affected_requirement_or_invariant_ids", "design_change_ids"}
LANE_KEYS = {"state", "evidence_refs", "attempted_search_refs", "source_family_ids", "alternative_ids"}


class ResearchError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ResearchError(message)


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{path.name} must contain one JSON object")
    return value


def strings(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        fail(f"{name} must be an array of nonempty strings")
    if len(value) != len(set(value)):
        fail(f"{name} must contain unique values")
    return value


def validate_policy(policy: dict) -> None:
    if policy.get("schema_version") != 1 or policy.get("policy_id") != "life-research-evidence-horizon-v1":
        fail("research policy identity mismatch")
    if policy.get("runtime_control_authority") != "NONE" or policy.get("research_authority") != "EVIDENCE_ONLY":
        fail("research must remain evidence only with runtime authority NONE")
    if policy.get("assistant_procedure_authority") != "BOOTSTRAP_REQUIRED_GOVERNANCE":
        fail("research assistant procedure authority mismatch")
    if policy.get("required_lane_ids") != REQUIRED_LANES:
        fail("research required lane set/order drifted")
    if policy.get("lane_result_states") != LANE_STATES:
        fail("research lane result state set/order drifted")
    if policy.get("source_system_required_categories") != REQUIRED_CATEGORIES:
        fail("research source-system category set/order drifted")
    if policy.get("comparison_dispositions") != DISPOSITIONS:
        fail("research comparison disposition set/order drifted")
    required_fragments = {
        "closure_rule": "EVERY_APPLICABLE_REQUIRED_LANE_STATE_NE_NOT_RUN",
        "narrow_corroboration_rule": "NARROW_CORROBORATION_FALSE_CLOSURE",
        "independent_parallel_rule": "AT_LEAST_TWO_DISTINCT_CURRENT_SOURCE_FAMILY_IDS",
        "competing_mechanism_rule": "AT_LEAST_ONE_CURRENT_ALTERNATIVE_ID",
        "failure_rule": "NO_EVIDENCE_FOUND_REQUIRES_AT_LEAST_ONE_ATTEMPTED_SEARCH_REF",
        "disconfirmation_rule": "NO_EVIDENCE_FOUND_REQUIRES_AT_LEAST_ONE_ATTEMPTED_SEARCH_REF",
        "life_reevaluation_rule": "ONE_SELECTED_DISPOSITION",
        "design_change_rule": "REPLAN_BEFORE_THE_NEXT_PROTECTED_MUTATION",
        "non_authority_rule": "CANNOT_CREATE_AUTHORIZATION_ROUTING_PRIORITY_COMPLETION_VERIFICATION_RELEASE_MUTATION_OR_EFFECT_EXECUTION_PASS",
    }
    for field, fragment in required_fragments.items():
        if fragment not in policy.get(field, ""):
            fail(f"research {field} missing required invariant {fragment}")


def validate_record(record: object, policy: dict) -> dict:
    if not isinstance(record, dict) or set(record) != RECORD_KEYS:
        fail("research record keys mismatch")
    lanes = record["lane_results"]
    if not isinstance(lanes, dict) or list(lanes) != REQUIRED_LANES:
        fail("research record lane set/order mismatch")
    for lane_id in REQUIRED_LANES:
        row = lanes[lane_id]
        if not isinstance(row, dict) or set(row) != LANE_KEYS:
            fail(f"{lane_id} lane keys mismatch")
        if row["state"] not in LANE_STATES:
            fail(f"{lane_id} state invalid")
        evidence_refs = strings(row["evidence_refs"], f"{lane_id}.evidence_refs")
        attempted = strings(row["attempted_search_refs"], f"{lane_id}.attempted_search_refs")
        source_families = strings(row["source_family_ids"], f"{lane_id}.source_family_ids")
        alternatives = strings(row["alternative_ids"], f"{lane_id}.alternative_ids")
        if row["state"] == "EVIDENCE_FOUND" and not evidence_refs:
            fail(f"{lane_id} EVIDENCE_FOUND requires evidence_refs")
        if row["state"] == "NO_EVIDENCE_FOUND" and not attempted:
            fail(f"{lane_id} NO_EVIDENCE_FOUND requires attempted_search_refs")
        if lane_id == "INDEPENDENT_PARALLEL_EVIDENCE" and row["state"] == "EVIDENCE_FOUND" and len(source_families) < 2:
            fail("INDEPENDENT_PARALLEL_EVIDENCE requires at least two distinct source families")
        if lane_id == "COMPETING_MECHANISMS" and row["state"] == "EVIDENCE_FOUND" and not alternatives:
            fail("COMPETING_MECHANISMS requires at least one current alternative")
    if lanes["LIFE_REEVALUATION"]["state"] != "EVIDENCE_FOUND":
        fail("LIFE_REEVALUATION must be EVIDENCE_FOUND before research closure")
    if record["selected_disposition"] not in DISPOSITIONS:
        fail("selected_disposition invalid")
    affected = strings(record["affected_requirement_or_invariant_ids"], "affected_requirement_or_invariant_ids")
    if not affected:
        fail("LIFE_REEVALUATION requires at least one affected requirement or invariant id")
    changes = strings(record["design_change_ids"], "design_change_ids")
    if any(row["state"] == "NOT_RUN" for row in lanes.values()):
        closure = "RESEARCH_NOT_COMPLETE"
    elif changes:
        closure = "REPLAN_REQUIRED"
    else:
        closure = "RESEARCH_COMPLETE"
    return {
        "policy_id": policy["policy_id"],
        "closure_state": closure,
        "selected_disposition": record["selected_disposition"],
        "design_change_ids": changes,
        "runtime_control_authority": "NONE",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluate-record")
    args = parser.parse_args()
    try:
        policy = load(POLICY_PATH)
        validate_policy(policy)
        if args.evaluate_record:
            record = json.loads(Path(args.evaluate_record).read_text(encoding="utf-8"))
            print(json.dumps(validate_record(record, policy), indent=2))
        else:
            print("RESEARCH_POLICY_VALID")
        return 0
    except (ResearchError, OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
