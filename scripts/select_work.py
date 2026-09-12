#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "work-selection-policy.json"
SCHEMA_PATH = ROOT / "governance" / "schema" / "work-selection-policy.schema.json"

REQUIRED_POLICY_KEYS = {
    "schema_version", "policy_id", "runtime_control_authority",
    "engineering_work_selection_authority", "continuity_barrier_resource_key",
    "worker_lanes", "priority_order", "preemption_rule",
    "same_or_lower_priority_rule", "novelty_rule", "continuity_sync",
    "interruption", "foreground_blocker_rule", "parallel_rule", "evidence_contract",
}

PRIORITY_ORDER = [
    {"rank": 0, "condition_id": "CONTINUITY_SYNC_REQUIRED", "selected_work": "CONTINUITY_SYNC"},
    {"rank": 1, "condition_id": "INTERRUPTED_OPERATION_UNRESOLVED", "selected_work": "RESUME_INTERRUPTED_OPERATION"},
    {"rank": 2, "condition_id": "FOREGROUND_CURRENT_WORK_BLOCKED", "selected_work": "CLEAR_CURRENT_BLOCKERS"},
    {"rank": 3, "condition_id": "FOREGROUND_CURRENT_NEXT_ACTION_PRESENT", "selected_work": "CURRENT_NEXT_ACTION"},
    {"rank": 4, "condition_id": "PARALLEL_ASSIGNED_REQUEST_RESOURCE_INTERSECTION_EMPTY", "selected_work": "PARALLEL_ASSIGNED_WORK"},
]

SYNC_REQUIRED_IF_ANY = [
    "PENDING_CONTINUITY_EVENT_IDS_NONEMPTY",
    "CANONICAL_LIVE_MISMATCH_IDS_NONEMPTY",
    "CONTINUITY_SYNC_CLAIM_STATE_ACTIVE_UNEXPIRED",
    "CONTINUITY_SYNC_CLAIM_STATE_ACTIVE_EXPIRED",
]

SYNC_RULES = {
    "prearm_rule": "BEFORE_AN_ASSISTANT_INITIATED_OPERATION_THAT_CAN_EMIT_A_BOOTSTRAP_CONTINUITY_UPDATE_EVENT_THE_WORK_ITEM_MUST_HOLD_ACTIVE_UNEXPIRED_CONTINUITY_SYNC",
    "fresh_mismatch_rule": "WHEN_A_CURRENT_AUTHORIZED_SYSTEM_READ_FIRST_PROVES_A_TRACKED_CANONICAL_VALUE_DIFFERS_FROM_LIVE_STATE_AND_THE_DELTA_IS_NOT_CONTINUITY_SYNC_EXEMPT_ACQUIRE_CONTINUITY_SYNC_BEFORE_ANY_OTHER_MUTABLE_OPERATION",
    "mutation_gate": "WHEN_CONTINUITY_SYNC_REQUIRED_NO_RANK_1_TO_4_MUTABLE_WORK_MAY_START_OR_RESUME",
    "continuity_sync_exempt_source": "continuity/bootstrap.json:continuity_sync_rule",
}

SYNC_COMPLETION_REQUIRES = [
    "CONTINUITY_SYNC_PR_MERGED_TO_MAIN",
    "MERGED_MAIN_READBACK_VERIFIED",
    "POST_MERGE_VALIDATE_SUCCESS",
    "CONTINUITY_SYNC_CLAIMS_RELEASED_AND_READ_BACK",
]

INTERRUPTION = {
    "unresolved_states": ["PENDING", "NO_RESULT", "TIMEOUT", "UNKNOWN"],
    "terminal_states": ["NONE", "SUCCESS", "FAILURE"],
    "resume_cue_effect": "ZERO_PRIORITY_EFFECT",
    "resume_rule": "WHEN_RANK_0_IS_INACTIVE_AND_INTERRUPTED_OPERATION_STATE_IS_UNRESOLVED_RESUME_THE_SAME_OPERATION_OR_WORK_ITEM_BEFORE_RANK_2_TO_4_WORK",
}

FOREGROUND_BLOCKER_RULE = "WHEN_WORKER_LANE_IS_FOREGROUND_AND_CURRENT_STATUS_IS_BLOCKED_AND_OPEN_BLOCKER_IDS_IS_NONEMPTY_SELECT_CLEAR_CURRENT_BLOCKERS_BEFORE_CURRENT_NEXT_ACTION"
PARALLEL_RULE = "PARALLEL_ASSIGNED_LANE_MAY_SELECT_RANK_4_ONLY_WHEN_RANK_0_AND_RANK_1_ARE_INACTIVE_AND_PARALLEL_REQUEST_STATE_IS_REQUESTED_AND_RESOURCE_INTERSECTION_IS_INTERSECTION_EMPTY"

REQUIRED_EVIDENCE_FIELDS = [
    "worker_lane", "pending_continuity_event_ids", "canonical_live_mismatch_ids",
    "continuity_sync_claim_state", "interrupted_operation_state", "current_status",
    "open_blocker_ids", "current_next_action_id", "parallel_request_state",
    "parallel_resource_intersection", "selected_rank_before", "selected_work_terminal",
]

ENUMS = {
    "worker_lane": ["FOREGROUND", "PARALLEL_ASSIGNED"],
    "continuity_sync_claim_state": ["NONE", "ACTIVE_UNEXPIRED", "ACTIVE_EXPIRED", "RELEASED"],
    "interrupted_operation_state": ["NONE", "PENDING", "NO_RESULT", "TIMEOUT", "UNKNOWN", "SUCCESS", "FAILURE"],
    "current_status": ["ACTIVE", "BLOCKED", "COMPLETE"],
    "parallel_request_state": ["NONE", "REQUESTED"],
    "parallel_resource_intersection": ["NOT_EVALUATED", "INTERSECTION_EMPTY", "INTERSECTION_NONEMPTY"],
    "selected_rank_before": [None, 0, 1, 2, 3, 4],
    "selected_work_terminal": [False, True],
}

PROHIBITED_QUALITATIVE_GATES = [
    "materially", "relevant", "appropriate", "sufficient", "reasonable", "important",
    "better", "best", "likely", "unlikely", "generally", "feasible", "meaningful",
    "necessary", "useful", "minimal", "robust", "as needed",
]


class PolicyError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise PolicyError(message)


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from all_strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from all_strings(item)


def validate_no_qualitative_gates(policy: dict) -> None:
    for text in all_strings(policy):
        lowered = text.lower().replace("_", " ")
        for token in PROHIBITED_QUALITATIVE_GATES:
            matched = token in lowered if token == "as needed" else re.search(rf"\b{re.escape(token)}\b", lowered) is not None
            if matched:
                fail(f"qualitative gate token forbidden in policy: {token!r}")


def validate_policy(policy: dict, schema: dict) -> None:
    if not isinstance(policy, dict) or set(policy) != REQUIRED_POLICY_KEYS:
        fail("policy root keys mismatch")
    validate_no_qualitative_gates(policy)
    if policy["schema_version"] != 1:
        fail("policy.schema_version must equal 1")
    if policy["policy_id"] != "life-engineering-work-selection-v1":
        fail("policy.policy_id mismatch")
    if policy["runtime_control_authority"] != "NONE":
        fail("policy.runtime_control_authority must be NONE")
    if policy["engineering_work_selection_authority"] != "DETERMINISTIC_EVALUATION_ONLY":
        fail("policy.engineering_work_selection_authority mismatch")
    if policy["continuity_barrier_resource_key"] != "continuity:sync":
        fail("policy.continuity_barrier_resource_key mismatch")
    if policy["worker_lanes"] != ["FOREGROUND", "PARALLEL_ASSIGNED"]:
        fail("policy.worker_lanes mismatch")
    if policy["priority_order"] != PRIORITY_ORDER:
        fail("policy.priority_order mismatch")
    if policy["preemption_rule"] != "ONLY_STRICTLY_LOWER_NUMERIC_RANK_MAY_PREEMPT_A_NONTERMINAL_SELECTED_WORK":
        fail("policy.preemption_rule mismatch")
    if policy["same_or_lower_priority_rule"] != "KEEP_NONTERMINAL_SELECTED_WORK_AND_RECORD_OR_QUEUE_NEW_EVIDENCE":
        fail("policy.same_or_lower_priority_rule mismatch")
    if policy["novelty_rule"] != "NEWLY_OBSERVED_WORK_OR_EVENT_HAS_ZERO_PREEMPTION_EFFECT_UNLESS_EXACT_EVIDENCE_ACTIVATES_A_STRICTLY_LOWER_NUMERIC_RANK":
        fail("policy.novelty_rule mismatch")

    sync = policy["continuity_sync"]
    if not isinstance(sync, dict) or set(sync) != {
        "sync_required_if_any", "prearm_rule", "fresh_mismatch_rule", "mutation_gate",
        "completion_requires", "continuity_sync_exempt_source",
    }:
        fail("policy.continuity_sync keys mismatch")
    if sync["sync_required_if_any"] != SYNC_REQUIRED_IF_ANY:
        fail("policy.continuity_sync.sync_required_if_any mismatch")
    for key, expected in SYNC_RULES.items():
        if sync[key] != expected:
            fail(f"policy.continuity_sync.{key} mismatch")
    if sync["completion_requires"] != SYNC_COMPLETION_REQUIRES:
        fail("policy.continuity_sync.completion_requires mismatch")

    if policy["interruption"] != INTERRUPTION:
        fail("policy.interruption mismatch")
    if policy["foreground_blocker_rule"] != FOREGROUND_BLOCKER_RULE:
        fail("policy.foreground_blocker_rule mismatch")
    if policy["parallel_rule"] != PARALLEL_RULE:
        fail("policy.parallel_rule mismatch")

    evidence = policy["evidence_contract"]
    expected_evidence_keys = {"required_fields", *ENUMS.keys()}
    if not isinstance(evidence, dict) or set(evidence) != expected_evidence_keys:
        fail("policy.evidence_contract keys mismatch")
    if evidence["required_fields"] != REQUIRED_EVIDENCE_FIELDS:
        fail("policy.evidence_contract.required_fields mismatch")
    for key, values in ENUMS.items():
        if evidence[key] != values:
            fail(f"policy.evidence_contract.{key} mismatch")

    if not isinstance(schema, dict):
        fail("work-selection schema must be object")
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        fail("work-selection schema must use Draft 2020-12")
    if schema.get("additionalProperties") is not False:
        fail("work-selection schema must forbid root additionalProperties")
    if schema.get("required") != sorted(REQUIRED_POLICY_KEYS):
        fail("work-selection schema required list mismatch")
    if set(schema.get("properties", {})) != REQUIRED_POLICY_KEYS:
        fail("work-selection schema properties mismatch")


def unique_string_list(value, field: str, pattern: str | None = None) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        fail(f"{field} must be an array of nonempty strings")
    if len(value) != len(set(value)):
        fail(f"{field} must contain unique values")
    if pattern:
        rx = re.compile(pattern)
        if any(rx.fullmatch(item) is None for item in value):
            fail(f"{field} contains invalid identifier")
    return value


def validate_evidence(evidence: dict) -> None:
    if not isinstance(evidence, dict) or set(evidence) != set(REQUIRED_EVIDENCE_FIELDS):
        fail("evidence keys mismatch")
    unique_string_list(evidence["pending_continuity_event_ids"], "pending_continuity_event_ids")
    unique_string_list(evidence["canonical_live_mismatch_ids"], "canonical_live_mismatch_ids")
    unique_string_list(evidence["open_blocker_ids"], "open_blocker_ids", r"B-[0-9]{4}")
    action_id = evidence["current_next_action_id"]
    if action_id is not None and (not isinstance(action_id, str) or re.fullmatch(r"A-[0-9]{4}", action_id) is None):
        fail("current_next_action_id must be null or A-NNNN")
    for field, values in ENUMS.items():
        if evidence[field] not in values:
            fail(f"{field} not in policy enum")
    if evidence["worker_lane"] == "FOREGROUND" and evidence["parallel_request_state"] != "NONE":
        fail("foreground lane cannot carry parallel request state")
    if evidence["worker_lane"] == "FOREGROUND" and evidence["parallel_resource_intersection"] != "NOT_EVALUATED":
        fail("foreground lane cannot carry parallel intersection state")


def candidate_for(evidence: dict) -> tuple[int | None, str | None, str | None]:
    sync_required = (
        bool(evidence["pending_continuity_event_ids"])
        or bool(evidence["canonical_live_mismatch_ids"])
        or evidence["continuity_sync_claim_state"] in {"ACTIVE_UNEXPIRED", "ACTIVE_EXPIRED"}
    )
    if sync_required:
        return 0, "CONTINUITY_SYNC", "CONTINUITY_SYNC_REQUIRED"
    if evidence["interrupted_operation_state"] in set(INTERRUPTION["unresolved_states"]):
        return 1, "RESUME_INTERRUPTED_OPERATION", "INTERRUPTED_OPERATION_UNRESOLVED"
    if evidence["worker_lane"] == "FOREGROUND" and evidence["current_status"] == "BLOCKED" and bool(evidence["open_blocker_ids"]):
        return 2, "CLEAR_CURRENT_BLOCKERS", "FOREGROUND_CURRENT_WORK_BLOCKED"
    if evidence["worker_lane"] == "FOREGROUND" and evidence["current_next_action_id"] is not None:
        return 3, "CURRENT_NEXT_ACTION", "FOREGROUND_CURRENT_NEXT_ACTION_PRESENT"
    if evidence["worker_lane"] == "PARALLEL_ASSIGNED" and evidence["parallel_request_state"] == "REQUESTED" and evidence["parallel_resource_intersection"] == "INTERSECTION_EMPTY":
        return 4, "PARALLEL_ASSIGNED_WORK", "PARALLEL_ASSIGNED_REQUEST_RESOURCE_INTERSECTION_EMPTY"
    return None, None, None


def evaluate(evidence: dict) -> dict:
    validate_evidence(evidence)
    candidate_rank, candidate_work, condition_id = candidate_for(evidence)
    prior_rank = evidence["selected_rank_before"]
    prior_nonterminal = prior_rank is not None and evidence["selected_work_terminal"] is False

    if prior_nonterminal:
        if candidate_rank is not None and candidate_rank < prior_rank:
            decision = "PREEMPT"
            effective_rank = candidate_rank
            selected_work = candidate_work
        else:
            decision = "KEEP_SELECTED"
            effective_rank = prior_rank
            selected_work = "PREVIOUS_SELECTION"
    elif candidate_rank is None:
        decision = "NO_ELIGIBLE_WORK"
        effective_rank = None
        selected_work = None
    else:
        decision = "SELECT"
        effective_rank = candidate_rank
        selected_work = candidate_work

    return {
        "candidate_rank": candidate_rank,
        "candidate_work": candidate_work,
        "candidate_condition_id": condition_id,
        "decision": decision,
        "effective_rank": effective_rank,
        "selected_work": selected_work,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-policy", action="store_true")
    parser.add_argument("--evaluate", type=str)
    args = parser.parse_args()
    try:
        policy = load_json(POLICY_PATH)
        schema = load_json(SCHEMA_PATH)
        validate_policy(policy, schema)
        if args.evaluate is not None:
            evidence = json.loads(Path(args.evaluate).read_text(encoding="utf-8"))
            print(json.dumps(evaluate(evidence), indent=2))
        else:
            print("VALID")
        return 0
    except (PolicyError, OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
