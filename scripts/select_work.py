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
ADMISSIONS_PATH = ROOT / "governance" / "work-admissions.json"
ADMISSIONS_SCHEMA_PATH = ROOT / "governance" / "schema" / "work-admissions.schema.json"
EVENTS_PATH = ROOT / "continuity" / "events.jsonl"

REQUIRED_POLICY_KEYS = {
    "schema_version", "policy_id", "runtime_control_authority",
    "engineering_work_selection_authority", "continuity_barrier_resource_key",
    "worker_lanes", "rank_semantics", "priority_order", "preemption_rule",
    "same_or_lower_priority_rule", "novelty_rule", "continuity_sync",
    "interruption", "foreground_blocker_rule", "parallel_admission",
    "parallel_rule", "evidence_contract",
}

PRIORITY_ORDER = [
    {"rank": 0, "condition_id": "CONTINUITY_SYNC_BLOCKS_OPERATION", "selected_work": "CONTINUITY_SYNC"},
    {"rank": 1, "condition_id": "INTERRUPTED_OPERATION_UNRESOLVED", "selected_work": "RESUME_INTERRUPTED_OPERATION"},
    {"rank": 2, "condition_id": "FOREGROUND_CURRENT_WORK_BLOCKED", "selected_work": "CLEAR_CURRENT_BLOCKERS"},
    {"rank": 3, "condition_id": "FOREGROUND_CURRENT_NEXT_ACTION_PRESENT", "selected_work": "CURRENT_NEXT_ACTION"},
    {"rank": 4, "condition_id": "PARALLEL_ADMITTED_REQUEST_RESOURCE_INTERSECTION_EMPTY", "selected_work": "PARALLEL_ADMITTED_WORK"},
]

SYNC_REQUIRED_IF_ANY = [
    "PENDING_CONTINUITY_EVENT_IDS_NONEMPTY",
    "CANONICAL_LIVE_MISMATCH_IDS_NONEMPTY",
    "CONTINUITY_SYNC_CLAIM_STATE_ACTIVE_UNEXPIRED",
    "CONTINUITY_SYNC_CLAIM_STATE_ACTIVE_EXPIRED",
]

SYNC_RULES = {
    "prearm_rule": "BEFORE_AN_ASSISTANT_INITIATED_OPERATION_THAT_CAN_EMIT_A_BOOTSTRAP_CONTINUITY_UPDATE_EVENT_THE_WORK_ITEM_MUST_HOLD_ACTIVE_UNEXPIRED_CONTINUITY_SYNC",
    "fresh_mismatch_rule": "WHEN_A_CURRENT_AUTHORIZED_SYSTEM_READ_FIRST_PROVES_A_TRACKED_CANONICAL_VALUE_DIFFERS_FROM_LIVE_STATE_AND_THE_DELTA_IS_NOT_CONTINUITY_SYNC_EXEMPT_ACQUIRE_CONTINUITY_SYNC_BEFORE_ANY OTHER_MUTABLE_OPERATION",
    "foreground_gate": "WHEN_CONTINUITY_SYNC_REQUIRED_FOREGROUND_SELECTS_CONTINUITY_SYNC",
    "parallel_gate": "WHEN_CONTINUITY_SYNC_REQUIRED_PARALLEL_ADMITTED_WORK_MAY_CONTINUE_ONLY_IF_CONTINUITY_RESOURCE_INTERSECTION_IS_INTERSECTION_EMPTY",
    "mutation_gate": "FOREGROUND_MUTATION_BLOCKED_IFF_CONTINUITY_SYNC_REQUIRED;PARALLEL_MUTATION_ALLOWED_IFF_CANONICAL_ADMISSION_AND_CONTINUITY_GATE_STATE_IN:SYNC_INACTIVE,INTERSECTION_EMPTY",
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
    "resume_rule": "WHEN_CONTINUITY_SYNC_DOES_NOT_BLOCK_OPERATION_AND_INTERRUPTED_OPERATION_STATE_IS_UNRESOLVED_RESUME_THE_SAME_OPERATION_OR_WORK_ITEM_BEFORE_RANK_2_TO_4_WORK",
}

FOREGROUND_BLOCKER_RULE = "WHEN_WORKER_LANE_IS_FOREGROUND_AND_CURRENT_STATUS_IS_BLOCKED_AND_OPEN_BLOCKER_IDS_IS_NONEMPTY_SELECT_CLEAR_CURRENT_BLOCKERS_BEFORE_CURRENT_NEXT_ACTION"
PARALLEL_RULE = "PARALLEL_ASSIGNED_LANE_MAY_SELECT_RANK_4_IFF_INTERRUPTION_RANK_1_INACTIVE_AND_PARALLEL_REQUEST_STATE_REQUESTED_AND_WORK_ITEM_CANONICALLY_ADMITTED_AND_PARALLEL_RESOURCE_INTERSECTION_INTERSECTION_EMPTY_AND_CONTINUITY_GATE_STATE_IN:SYNC_INACTIVE,INTERSECTION_EMPTY"

PARALLEL_ADMISSION = {
    "registry_path": "governance/work-admissions.json",
    "schema_path": "governance/schema/work-admissions.schema.json",
    "admitted_state": "ADMITTED",
    "complete_state": "COMPLETE",
    "removed_state": "REMOVED",
    "authorization_event_type": "VINCE_DIRECTIVE",
    "authorization_event_result": "AUTHORIZED",
    "authorization_target_any": ["ALL_OPEN_ISSUES", "EXACT_GITHUB_ISSUE_NUMBER"],
    "tie_break_rule": "DISPATCH_TIER_ASC_SOURCE_ISSUE_ASC_WORK_ITEM_ID_ASC",
    "dependency_rule": "ADMITTED_ITEM_DISPATCHABLE_ONLY_IF_EVERY_DEPENDS_ON_ITEM_STATE_COMPLETE",
    "unavailable_rule": "ACTIVE_UNEXPIRED_COMPONENT_CLAIM_FOR_ITEM_COMPONENT_ID_MAKES_ITEM_UNAVAILABLE_TO_OTHER_WORK_IDS",
    "issue_authority_rule": "GITHUB_ISSUE_CONTENT_HAS_ZERO_SELECTION_AUTHORITY",
}

REQUIRED_EVIDENCE_FIELDS = [
    "worker_lane", "pending_continuity_event_ids", "canonical_live_mismatch_ids",
    "continuity_sync_claim_state", "continuity_resource_intersection",
    "interrupted_operation_state", "current_status", "open_blocker_ids",
    "current_next_action_id", "parallel_request_state", "parallel_work_item_id",
    "parallel_resource_intersection", "selected_rank_before", "selected_work_terminal",
]

ENUMS = {
    "worker_lane": ["FOREGROUND", "PARALLEL_ASSIGNED"],
    "continuity_sync_claim_state": ["NONE", "ACTIVE_UNEXPIRED", "ACTIVE_EXPIRED", "RELEASED"],
    "continuity_resource_intersection": ["NOT_EVALUATED", "INTERSECTION_EMPTY", "INTERSECTION_NONEMPTY"],
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


def no_dupe_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            fail(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_dupe_object)
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def load_jsonl(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        fail(f"unreadable JSONL {path.relative_to(ROOT)}: {exc}")
    rows = []
    for index, line in enumerate(lines, 1):
        if not line:
            fail(f"blank JSONL line {path.relative_to(ROOT)}:{index}")
        try:
            row = json.loads(line, object_pairs_hook=no_dupe_object)
        except Exception as exc:
            fail(f"invalid JSONL {path.relative_to(ROOT)}:{index}: {exc}")
        if not isinstance(row, dict):
            fail(f"JSONL row must be object {path.relative_to(ROOT)}:{index}")
        rows.append(row)
    return rows


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


def validate_schema_root(schema: dict, required_keys: set[str], label: str) -> None:
    if not isinstance(schema, dict):
        fail(f"{label} schema must be object")
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        fail(f"{label} schema must use Draft 2020-12")
    if schema.get("additionalProperties") is not False:
        fail(f"{label} schema must forbid root additionalProperties")
    if schema.get("required") != sorted(required_keys):
        fail(f"{label} schema required list mismatch")
    if set(schema.get("properties", {})) != required_keys:
        fail(f"{label} schema properties mismatch")


def find_authorization_event(event_id: str) -> dict:
    matches = [row for row in load_jsonl(EVENTS_PATH) if row.get("id") == event_id]
    if len(matches) != 1:
        fail("admissions authorization_ref must resolve to exactly one continuity event")
    return matches[0]


def validate_admissions(admissions: dict, schema: dict) -> dict[str, dict]:
    required_root = {
        "schema_version", "registry_id", "runtime_control_authority",
        "engineering_work_selection_authority", "authorization_ref",
        "source_repository", "tie_break_rule", "items",
    }
    if not isinstance(admissions, dict) or set(admissions) != required_root:
        fail("admissions root keys mismatch")
    if admissions["schema_version"] != 1:
        fail("admissions.schema_version must equal 1")
    if admissions["registry_id"] != "life-engineering-work-admissions-v1":
        fail("admissions.registry_id mismatch")
    if admissions["runtime_control_authority"] != "NONE":
        fail("admissions.runtime_control_authority must be NONE")
    if admissions["engineering_work_selection_authority"] != "DETERMINISTIC_EVALUATION_ONLY":
        fail("admissions engineering authority mismatch")
    if admissions["source_repository"] != "Vinanonymous/Build":
        fail("admissions source_repository mismatch")
    if admissions["tie_break_rule"] != PARALLEL_ADMISSION["tie_break_rule"]:
        fail("admissions tie_break_rule mismatch")
    if not isinstance(admissions["authorization_ref"], str) or re.fullmatch(r"E-[0-9]{4}", admissions["authorization_ref"]) is None:
        fail("admissions.authorization_ref must be E-NNNN")

    event = find_authorization_event(admissions["authorization_ref"])
    if event.get("event_type") != PARALLEL_ADMISSION["authorization_event_type"]:
        fail("admissions authorization event type mismatch")
    if event.get("result") != PARALLEL_ADMISSION["authorization_event_result"]:
        fail("admissions authorization event result mismatch")
    targets = event.get("targets")
    if not isinstance(targets, list) or any(not isinstance(item, str) for item in targets):
        fail("admissions authorization event targets invalid")

    items = admissions["items"]
    if not isinstance(items, list) or not items:
        fail("admissions.items must be nonempty array")

    by_id: dict[str, dict] = {}
    seen_issues: set[int] = set()
    seen_components: set[str] = set()
    required_item = {
        "work_item_id", "source_issue_number", "component_id",
        "dispatch_tier", "state", "depends_on",
    }
    for item in items:
        if not isinstance(item, dict) or set(item) != required_item:
            fail("admissions item keys mismatch")
        work_item_id = item["work_item_id"]
        issue = item["source_issue_number"]
        component = item["component_id"]
        tier = item["dispatch_tier"]
        state = item["state"]
        deps = item["depends_on"]
        if not isinstance(work_item_id, str) or re.fullmatch(r"github-issue-[1-9][0-9]*", work_item_id) is None:
            fail("admissions work_item_id invalid")
        if not isinstance(issue, int) or isinstance(issue, bool) or issue < 1:
            fail("admissions source_issue_number invalid")
        if work_item_id != f"github-issue-{issue}":
            fail("admissions work_item_id/source_issue_number mismatch")
        if not isinstance(component, str) or component != f"issue_{issue}":
            fail("admissions component_id/source_issue_number mismatch")
        if not isinstance(tier, int) or isinstance(tier, bool) or tier < 1:
            fail("admissions dispatch_tier invalid")
        if state not in {"ADMITTED", "COMPLETE", "REMOVED"}:
            fail("admissions state invalid")
        unique_string_list(deps, f"{work_item_id}.depends_on", r"github-issue-[1-9][0-9]*")
        if work_item_id in deps:
            fail("admissions item cannot depend on itself")
        if work_item_id in by_id or issue in seen_issues or component in seen_components:
            fail("admissions item identity must be unique")
        by_id[work_item_id] = item
        seen_issues.add(issue)
        seen_components.add(component)
        if state == "ADMITTED" and "ALL_OPEN_ISSUES" not in targets and f"github:issue={issue}" not in targets:
            fail("admitted item lacks exact user authorization target")

    for item in items:
        for dep in item["depends_on"]:
            if dep not in by_id:
                fail(f"admissions dependency missing: {dep}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(item_id: str) -> None:
        if item_id in visited:
            return
        if item_id in visiting:
            fail("admissions dependency cycle")
        visiting.add(item_id)
        for dep in by_id[item_id]["depends_on"]:
            visit(dep)
        visiting.remove(item_id)
        visited.add(item_id)

    for item_id in by_id:
        visit(item_id)

    validate_schema_root(
        schema,
        {
            "schema_version", "registry_id", "runtime_control_authority",
            "engineering_work_selection_authority", "authorization_ref",
            "source_repository", "tie_break_rule", "items",
        },
        "work-admissions",
    )
    return by_id


def dispatchable(item: dict, by_id: dict[str, dict]) -> bool:
    return (
        item["state"] == "ADMITTED"
        and all(by_id[dep]["state"] == "COMPLETE" for dep in item["depends_on"])
    )


def select_parallel_work(admissions: dict, by_id: dict[str, dict], unavailable: set[str]) -> dict:
    unknown = unavailable - set(by_id)
    if unknown:
        fail(f"unavailable work item unknown: {sorted(unknown)}")
    candidates = [
        item for item in admissions["items"]
        if dispatchable(item, by_id) and item["work_item_id"] not in unavailable
    ]
    candidates.sort(key=lambda item: (item["dispatch_tier"], item["source_issue_number"], item["work_item_id"]))
    if not candidates:
        return {
            "decision": "NO_ELIGIBLE_WORK",
            "selection_rank": None,
            "work_item_id": None,
            "source_issue_number": None,
            "component_resource_key": None,
            "dispatch_tier": None,
        }
    item = candidates[0]
    return {
        "decision": "SELECT",
        "selection_rank": 4,
        "work_item_id": item["work_item_id"],
        "source_issue_number": item["source_issue_number"],
        "component_resource_key": f"component:{item['component_id']}",
        "dispatch_tier": item["dispatch_tier"],
    }


def validate_policy(policy: dict, schema: dict, admissions: dict, admissions_schema: dict) -> dict[str, dict]:
    if not isinstance(policy, dict) or set(policy) != REQUIRED_POLICY_KEYS:
        fail("policy root keys mismatch")
    validate_no_qualitative_gates(policy)
    if policy["schema_version"] != 2:
        fail("policy.schema_version must equal 2")
    if policy["policy_id"] != "life-engineering-work-selection-v2":
        fail("policy.policy_id mismatch")
    if policy["runtime_control_authority"] != "NONE":
        fail("policy.runtime_control_authority must be NONE")
    if policy["engineering_work_selection_authority"] != "DETERMINISTIC_EVALUATION_ONLY":
        fail("policy.engineering_work_selection_authority mismatch")
    if policy["continuity_barrier_resource_key"] != "continuity:sync":
        fail("policy.continuity_barrier_resource_key mismatch")
    if policy["worker_lanes"] != ["FOREGROUND", "PARALLEL_ASSIGNED"]:
        fail("policy.worker_lanes mismatch")
    if policy["rank_semantics"] != "LOWER_NUMERIC_RANK_HAS_HIGHER_PRECEDENCE":
        fail("policy.rank_semantics mismatch")
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
        "sync_required_if_any", "prearm_rule", "fresh_mismatch_rule",
        "foreground_gate", "parallel_gate", "mutation_gate",
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
    if policy["parallel_admission"] != PARALLEL_ADMISSION:
        fail("policy.parallel_admission mismatch")
    if policy["parallel_rule"] != PARALLEL_RULE:
        fail("policy.parallel_rule mismatch")

    evidence = policy["evidence_contract"]
    expected_evidence_keys = {"required_fields", *ENUMS.keys(), "parallel_work_item_id_pattern"}
    if not isinstance(evidence, dict) or set(evidence) != expected_evidence_keys:
        fail("policy.evidence_contract keys mismatch")
    if evidence["required_fields"] != REQUIRED_EVIDENCE_FIELDS:
        fail("policy.evidence_contract.required_fields mismatch")
    for key, values in ENUMS.items():
        if evidence[key] != values:
            fail(f"policy.evidence_contract.{key} mismatch")
    if evidence["parallel_work_item_id_pattern"] != r"^github-issue-[1-9][0-9]*$":
        fail("policy.evidence_contract.parallel_work_item_id_pattern mismatch")

    validate_schema_root(schema, REQUIRED_POLICY_KEYS, "work-selection")
    return validate_admissions(admissions, admissions_schema)


def sync_required(evidence: dict) -> bool:
    return (
        bool(evidence["pending_continuity_event_ids"])
        or bool(evidence["canonical_live_mismatch_ids"])
        or evidence["continuity_sync_claim_state"] in {"ACTIVE_UNEXPIRED", "ACTIVE_EXPIRED"}
    )


def validate_evidence(evidence: dict, by_id: dict[str, dict]) -> None:
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

    work_item_id = evidence["parallel_work_item_id"]
    if work_item_id is not None and (
        not isinstance(work_item_id, str)
        or re.fullmatch(r"github-issue-[1-9][0-9]*", work_item_id) is None
    ):
        fail("parallel_work_item_id invalid")

    if evidence["worker_lane"] == "FOREGROUND":
        if evidence["parallel_request_state"] != "NONE":
            fail("foreground lane cannot carry parallel request state")
        if work_item_id is not None:
            fail("foreground lane cannot carry parallel_work_item_id")
        if evidence["parallel_resource_intersection"] != "NOT_EVALUATED":
            fail("foreground lane cannot carry parallel resource intersection")
        if evidence["continuity_resource_intersection"] != "NOT_EVALUATED":
            fail("foreground lane cannot carry continuity resource intersection")
        return

    if evidence["parallel_request_state"] == "NONE":
        if work_item_id is not None:
            fail("parallel request NONE cannot carry parallel_work_item_id")
        if evidence["parallel_resource_intersection"] != "NOT_EVALUATED":
            fail("parallel request NONE cannot carry parallel resource intersection")
        if evidence["continuity_resource_intersection"] != "NOT_EVALUATED":
            fail("parallel request NONE cannot carry continuity resource intersection")
        return

    if work_item_id is None or work_item_id not in by_id:
        fail("parallel requested work item must exist in admissions")
    if not dispatchable(by_id[work_item_id], by_id):
        fail("parallel requested work item is not dispatchable")
    if evidence["parallel_resource_intersection"] == "NOT_EVALUATED":
        fail("parallel requested work requires resource intersection evaluation")
    if sync_required(evidence):
        if evidence["continuity_resource_intersection"] == "NOT_EVALUATED":
            fail("parallel requested work during continuity sync requires continuity intersection evaluation")
    elif evidence["continuity_resource_intersection"] != "NOT_EVALUATED":
        fail("continuity intersection must be NOT_EVALUATED when continuity sync is inactive")


def continuity_blocks_operation(evidence: dict) -> bool:
    if not sync_required(evidence):
        return False
    if evidence["worker_lane"] == "FOREGROUND":
        return True
    return evidence["continuity_resource_intersection"] != "INTERSECTION_EMPTY"


def candidate_for(evidence: dict, by_id: dict[str, dict]) -> tuple[int | None, str | None, str | None]:
    if continuity_blocks_operation(evidence):
        return 0, "CONTINUITY_SYNC", "CONTINUITY_SYNC_BLOCKS_OPERATION"
    if evidence["interrupted_operation_state"] in set(INTERRUPTION["unresolved_states"]):
        return 1, "RESUME_INTERRUPTED_OPERATION", "INTERRUPTED_OPERATION_UNRESOLVED"
    if evidence["worker_lane"] == "FOREGROUND" and evidence["current_status"] == "BLOCKED" and bool(evidence["open_blocker_ids"]):
        return 2, "CLEAR_CURRENT_BLOCKERS", "FOREGROUND_CURRENT_WORK_BLOCKED"
    if evidence["worker_lane"] == "FOREGROUND" and evidence["current_next_action_id"] is not None:
        return 3, "CURRENT_NEXT_ACTION", "FOREGROUND_CURRENT_NEXT_ACTION_PRESENT"
    if (
        evidence["worker_lane"] == "PARALLEL_ASSIGNED"
        and evidence["parallel_request_state"] == "REQUESTED"
        and evidence["parallel_work_item_id"] in by_id
        and dispatchable(by_id[evidence["parallel_work_item_id"]], by_id)
        and evidence["parallel_resource_intersection"] == "INTERSECTION_EMPTY"
    ):
        return 4, "PARALLEL_ADMITTED_WORK", "PARALLEL_ADMITTED_REQUEST_RESOURCE_INTERSECTION_EMPTY"
    return None, None, None


def evaluate(evidence: dict, by_id: dict[str, dict]) -> dict:
    validate_evidence(evidence, by_id)
    candidate_rank, candidate_work, condition_id = candidate_for(evidence, by_id)
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
        "parallel_work_item_id": evidence["parallel_work_item_id"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-policy", action="store_true")
    mode.add_argument("--evaluate", type=str)
    mode.add_argument("--select-parallel", action="store_true")
    parser.add_argument("--unavailable-work-item", action="append", default=[])
    args = parser.parse_args()
    try:
        policy = load_json(POLICY_PATH)
        schema = load_json(SCHEMA_PATH)
        admissions = load_json(ADMISSIONS_PATH)
        admissions_schema = load_json(ADMISSIONS_SCHEMA_PATH)
        by_id = validate_policy(policy, schema, admissions, admissions_schema)

        if args.evaluate is not None:
            if args.unavailable_work_item:
                fail("--unavailable-work-item is valid only with --select-parallel")
            evidence = json.loads(Path(args.evaluate).read_text(encoding="utf-8"), object_pairs_hook=no_dupe_object)
            print(json.dumps(evaluate(evidence, by_id), indent=2))
        elif args.select_parallel:
            unavailable = set(unique_string_list(
                args.unavailable_work_item,
                "unavailable_work_item",
                r"github-issue-[1-9][0-9]*",
            ))
            print(json.dumps(select_parallel_work(admissions, by_id, unavailable), indent=2))
        else:
            if args.unavailable_work_item:
                fail("--unavailable-work-item requires --select-parallel")
            print("VALID")
        return 0
    except (PolicyError, OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
