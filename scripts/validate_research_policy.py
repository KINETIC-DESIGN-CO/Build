#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "research-policy.json"

REQUIRED_LANES = [
    "WHOLE_SOURCE_CONTEXT",
    "SAME_PUBLISHER_NEIGHBORHOOD",
    "INDEPENDENT_PARALLEL_EVIDENCE",
    "ALTERNATIVE_MECHANISM",
    "FAILURE_OR_PRACTITIONER_EVIDENCE",
    "DISCONFIRMATION_SEARCH",
    "LIFE_COMPARISON",
]
REQUIRED_CATEGORIES = [
    "LIFECYCLE_OR_STATE_MODEL",
    "FAILURE_MODES",
    "TAKEOVER_PREEMPTION_OR_CANCELLATION",
    "STALE_RESULT_VERSIONING_OR_FENCING",
    "RECOVERY_OR_IDEMPOTENCY",
    "LIMITS_QUOTAS_OR_COST",
    "OPERATIONAL_CAVEATS",
]
DISPOSITIONS = ["KEEP", "REPLACE", "MODIFY", "COMBINE", "REMOVE"]


def validate() -> list[str]:
    errors: list[str] = []
    try:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"RESEARCH001_LOAD: {exc}"]
    if policy.get("schema_version") != 1 or policy.get("policy_id") != "life-research-source-neighborhood-v1":
        errors.append("RESEARCH002_ID: policy identity mismatch")
    if policy.get("runtime_control_authority") != "NONE" or policy.get("research_authority") != "EVIDENCE_ONLY":
        errors.append("RESEARCH003_AUTHORITY: research must remain evidence only with runtime authority NONE")
    if policy.get("assistant_procedure_authority") != "BOOTSTRAP_REQUIRED_GOVERNANCE":
        errors.append("RESEARCH003_AUTHORITY: assistant procedure authority mismatch")
    if policy.get("required_lane_ids") != REQUIRED_LANES:
        errors.append("RESEARCH004_LANES: required lane set/order drifted")
    if policy.get("lane_attempt_states") != ["ATTEMPTED", "NOT_ATTEMPTED"]:
        errors.append("RESEARCH004_LANES: lane attempt states drifted")
    if policy.get("lane_result_states") != ["EVIDENCE_FOUND", "NOT_RUN", "NOT_APPLICABLE"]:
        errors.append("RESEARCH004_LANES: lane result states drifted")
    if policy.get("same_publisher_required_categories") != REQUIRED_CATEGORIES:
        errors.append("RESEARCH005_NEIGHBORHOOD: same-publisher category set/order drifted")
    if policy.get("comparison_dispositions") != DISPOSITIONS:
        errors.append("RESEARCH006_COMPARISON: comparison disposition set/order drifted")
    if "NARROW_CORROBORATION_FALSE_CLOSURE" not in policy.get("narrow_corroboration_rule", ""):
        errors.append("RESEARCH007_CLOSURE: narrow corroboration false-closure guard missing")
    if "EVERY_REQUIRED_LANE_HAS_ATTEMPT_STATE_ATTEMPTED" not in policy.get("closure_rule", ""):
        errors.append("RESEARCH007_CLOSURE: closure must require every lane attempted")
    if "RESULT_STATE_NOT_RUN_MUST_REMAIN_VISIBLE" not in policy.get("closure_rule", ""):
        errors.append("RESEARCH007_CLOSURE: NOT_RUN visibility rule missing")
    if "RESEARCH_DESIGN_CHANGE" not in policy.get("design_change_rule", ""):
        errors.append("RESEARCH008_REPLAN: broader evidence must feed live-audit replan")
    if "CANNOT_CREATE_AUTHORIZATION_ROUTING_PRIORITY_COMPLETION_VERIFICATION_RELEASE_MUTATION_OR_EFFECT_EXECUTION_PASS" not in policy.get("non_authority_rule", ""):
        errors.append("RESEARCH009_NONAUTHORITY: research non-authority rule drifted")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("RESEARCH_POLICY_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
