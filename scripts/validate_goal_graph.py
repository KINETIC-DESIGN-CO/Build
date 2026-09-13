#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance/goal-policy.json"
REGISTRY_PATH = ROOT / "governance/goal-registry.json"
POLICY_SCHEMA_PATH = ROOT / "governance/schema/goal-policy.schema.json"
REGISTRY_SCHEMA_PATH = ROOT / "governance/schema/goal-registry.schema.json"

UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
CONDITION_ID = re.compile(r"^[A-Z][A-Z0-9_]*$")
ROOT_TRANSITION_ID = re.compile(r"^RT-[0-9]{4}$")

GOAL_RELATIONS = [
    "ROOT",
    "PREREQUISITE",
    "BLOCKER_REPAIR",
    "CONTINUITY_CAPTURE",
    "VERIFICATION",
    "TERMINAL_CLEANUP",
    "DEFECT_REPAIR",
    "ISSUE_CONSOLIDATION",
    "IMPLEMENTATION_CHILD",
]
GOAL_STATES = [
    "ACTIVE",
    "BLOCKED_RESOURCE",
    "BLOCKED_AUTHORIZATION",
    "BLOCKED_COST",
    "BLOCKED_PLATFORM",
    "VERIFYING",
    "COMPLETE",
    "REMOVED",
]
TERMINAL_STATES = ["COMPLETE", "REMOVED"]
ATTEMPT_STATES = ["ACTIVE", "TERMINAL_SUCCESS", "TERMINAL_FAILURE", "SUPERSEDED"]

POLICY_EXACT = {
    "schema_version": 1,
    "policy_id": "life-engineering-goal-policy-v1",
    "runtime_control_authority": "NONE",
    "engineering_goal_authority": "DETERMINISTIC_EVALUATION_ONLY",
    "goal_relations": GOAL_RELATIONS,
    "goal_states": GOAL_STATES,
    "terminal_goal_states": TERMINAL_STATES,
    "active_path_rule": "ACTIVE_PATH_EQUALS_ROOT_TO_ACTIVE_GOAL_PARENT_CHAIN",
    "child_terminal_rule": "WHEN_ACTIVE_GOAL_STATE_IN:COMPLETE,REMOVED_AND_PARENT_GOAL_STATE_NOT_IN:COMPLETE,REMOVED_SELECT_PARENT_BEFORE_UNRELATED_ROOT",
    "root_switch_rule": "UNRELATED_ROOT_SELECTION_ALLOWED_IFF_ACTIVE_ROOT_GOAL_STATE_IN:COMPLETE,REMOVED_OR_EXACT_AUTHORIZED_ROOT_TRANSITION_ID_PRESENT",
    "blocker_rule": "BLOCKER_PREREQUISITE_VERIFICATION_CONTINUITY_REPAIR_TERMINAL_CLEANUP_DEFECT_REPAIR_AND_ISSUE_CONSOLIDATION_USE_TYPED_CHILD_GOALS_AND_DO_NOT_REPLACE_ROOT_GOAL_ID",
    "execution_identity_rule": "WORK_ID_LEASE_ID_AND_GENERATION_ARE_EXECUTION_IDENTITY_AND_DO_NOT_DEFINE_GOAL_ID",
    "parallel_rule": "PARALLEL_WORK_HAS_ZERO_EFFECT_ON_ANOTHER_FOREGROUND_ACTIVE_ROOT_GOAL_ID",
    "issue_authority_rule": "GITHUB_ISSUE_CONTENT_AND_RELATIONSHIPS_HAVE_ZERO_GOAL_SELECTION_AUTHORITY",
    "checkpoint_rule": "CHECKPOINT_GOAL_PATH_IS_HISTORICAL_EVIDENCE_AND_REQUIRES_FRESH_LIVE_HYDRATION_BEFORE_SELECTION",
    "missing_evidence_rule": "MISSING_INVALID_STALE_OR_UNVERIFIED_GOAL_CONTROL_EVIDENCE_CANNOT_CREATE_COMPLETE_OR_ROOT_SWITCH",
}

REGISTRY_ROOT_KEYS = {
    "schema_version",
    "registry_id",
    "runtime_control_authority",
    "engineering_goal_authority",
    "active_root_goal_id",
    "active_goal_id",
    "active_path",
    "authorized_root_transition_id",
    "goals",
}
GOAL_KEYS = {
    "goal_id",
    "root_goal_id",
    "parent_goal_id",
    "return_to_goal_id",
    "goal_relation",
    "goal_state",
    "title",
    "completion_condition_ids",
    "satisfied_condition_ids",
    "child_goal_ids",
    "execution_attempts",
    "source_refs",
    "runtime_control_authority",
}
ATTEMPT_KEYS = {"work_id", "attempt_state"}


class GoalGraphError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise GoalGraphError(message)


def no_duplicate_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            fail(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_keys)
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def require_unique_strings(value, name, pattern=None, min_items=0):
    if not isinstance(value, list) or len(value) < min_items:
        fail(f"{name} must be an array with at least {min_items} items")
    if any(not isinstance(item, str) or not item for item in value):
        fail(f"{name} must contain nonempty strings")
    if len(value) != len(set(value)):
        fail(f"{name} must contain unique values")
    if pattern is not None and any(pattern.fullmatch(item) is None for item in value):
        fail(f"{name} contains invalid identifier")
    return value


def validate_schema_header(schema, expected_id: str, expected_root_keys: set[str], name: str):
    if not isinstance(schema, dict):
        fail(f"{name} schema must be object")
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        fail(f"{name} schema draft mismatch")
    if schema.get("$id") != expected_id:
        fail(f"{name} schema id mismatch")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        fail(f"{name} schema root must be closed object")
    if set(schema.get("required", [])) != expected_root_keys:
        fail(f"{name} schema required keys mismatch")
    if set(schema.get("properties", {})) != expected_root_keys:
        fail(f"{name} schema properties mismatch")


def validate_policy(policy, schema):
    if not isinstance(policy, dict) or policy != POLICY_EXACT:
        fail("goal policy exact contract mismatch")
    validate_schema_header(
        schema,
        "https://github.com/KINETIC-DESIGN-CO/Build/blob/main/governance/schema/goal-policy.schema.json",
        set(POLICY_EXACT),
        "goal-policy",
    )
    props = schema["properties"]
    for key, value in POLICY_EXACT.items():
        if props.get(key, {}).get("const") != value:
            fail(f"goal-policy schema const mismatch: {key}")


def validate_registry(registry, schema):
    if not isinstance(registry, dict) or set(registry) != REGISTRY_ROOT_KEYS:
        fail("goal registry root keys mismatch")
    if registry.get("schema_version") != 1:
        fail("goal registry schema_version mismatch")
    if registry.get("registry_id") != "life-engineering-goal-registry-v1":
        fail("goal registry id mismatch")
    if registry.get("runtime_control_authority") != "NONE":
        fail("goal registry runtime authority mismatch")
    if registry.get("engineering_goal_authority") != "DETERMINISTIC_EVALUATION_ONLY":
        fail("goal registry engineering authority mismatch")

    active_root = registry.get("active_root_goal_id")
    active_goal = registry.get("active_goal_id")
    if not isinstance(active_root, str) or UUID4.fullmatch(active_root) is None:
        fail("active_root_goal_id invalid")
    if not isinstance(active_goal, str) or UUID4.fullmatch(active_goal) is None:
        fail("active_goal_id invalid")

    transition_id = registry.get("authorized_root_transition_id")
    if transition_id is not None and (not isinstance(transition_id, str) or ROOT_TRANSITION_ID.fullmatch(transition_id) is None):
        fail("authorized_root_transition_id invalid")

    active_path = require_unique_strings(registry.get("active_path"), "active_path", UUID4, min_items=1)
    if active_path[0] != active_root or active_path[-1] != active_goal:
        fail("active_path endpoints mismatch")

    goals = registry.get("goals")
    if not isinstance(goals, list) or not goals:
        fail("goals must be nonempty array")

    by_id = {}
    attempt_owner = {}
    for goal in goals:
        if not isinstance(goal, dict) or set(goal) != GOAL_KEYS:
            fail("goal keys mismatch")
        goal_id = goal.get("goal_id")
        if not isinstance(goal_id, str) or UUID4.fullmatch(goal_id) is None or goal_id in by_id:
            fail("goal_id invalid or duplicate")
        if not isinstance(goal.get("root_goal_id"), str) or UUID4.fullmatch(goal["root_goal_id"]) is None:
            fail("root_goal_id invalid")
        parent_id = goal.get("parent_goal_id")
        return_id = goal.get("return_to_goal_id")
        for field_name, value in (("parent_goal_id", parent_id), ("return_to_goal_id", return_id)):
            if value is not None and (not isinstance(value, str) or UUID4.fullmatch(value) is None):
                fail(f"{field_name} invalid")
        if goal.get("goal_relation") not in GOAL_RELATIONS:
            fail("goal_relation invalid")
        if goal.get("goal_state") not in GOAL_STATES:
            fail("goal_state invalid")
        if not isinstance(goal.get("title"), str) or not 1 <= len(goal["title"]) <= 200:
            fail("goal title invalid")
        completion = require_unique_strings(
            goal.get("completion_condition_ids"), f"{goal_id}.completion_condition_ids", CONDITION_ID, min_items=1
        )
        satisfied = require_unique_strings(
            goal.get("satisfied_condition_ids"), f"{goal_id}.satisfied_condition_ids", CONDITION_ID
        )
        if not set(satisfied).issubset(completion):
            fail("satisfied_condition_ids must be subset of completion_condition_ids")
        if goal["goal_state"] == "COMPLETE" and set(satisfied) != set(completion):
            fail("COMPLETE goal requires every completion condition satisfied")
        children = require_unique_strings(goal.get("child_goal_ids"), f"{goal_id}.child_goal_ids", UUID4)
        if goal_id in children:
            fail("goal cannot be its own child")
        attempts = goal.get("execution_attempts")
        if not isinstance(attempts, list):
            fail("execution_attempts must be array")
        seen_attempts = set()
        for attempt in attempts:
            if not isinstance(attempt, dict) or set(attempt) != ATTEMPT_KEYS:
                fail("execution attempt keys mismatch")
            work_id = attempt.get("work_id")
            if not isinstance(work_id, str) or UUID4.fullmatch(work_id) is None:
                fail("execution attempt work_id invalid")
            if attempt.get("attempt_state") not in ATTEMPT_STATES:
                fail("execution attempt state invalid")
            if work_id in seen_attempts or work_id in attempt_owner:
                fail("execution work_id must map to exactly one goal")
            seen_attempts.add(work_id)
            attempt_owner[work_id] = goal_id
        require_unique_strings(goal.get("source_refs"), f"{goal_id}.source_refs", min_items=1)
        if goal.get("runtime_control_authority") != "NONE":
            fail("goal runtime authority mismatch")
        by_id[goal_id] = goal

    if active_root not in by_id or active_goal not in by_id:
        fail("active goal identifiers must resolve")
    if by_id[active_root]["goal_relation"] != "ROOT" or by_id[active_root]["parent_goal_id"] is not None:
        fail("active root must be ROOT with null parent")
    if by_id[active_root]["root_goal_id"] != active_root:
        fail("active root root_goal_id must equal goal_id")
    if by_id[active_root]["return_to_goal_id"] is not None:
        fail("active root return_to_goal_id must be null")
    if by_id[active_root]["goal_state"] in TERMINAL_STATES and transition_id is None:
        fail("terminal active root requires exact authorized root transition id")
    if by_id[active_goal]["goal_state"] in TERMINAL_STATES:
        fail("active_goal_id cannot reference terminal goal")

    roots = {goal_id for goal_id, goal in by_id.items() if goal["goal_relation"] == "ROOT"}
    for goal_id, goal in by_id.items():
        parent_id = goal["parent_goal_id"]
        if goal["goal_relation"] == "ROOT":
            if parent_id is not None or goal["root_goal_id"] != goal_id or goal["return_to_goal_id"] is not None:
                fail("ROOT goal identity invariant mismatch")
            continue
        if parent_id is None or parent_id not in by_id:
            fail("non-root goal must resolve parent")
        parent = by_id[parent_id]
        if goal["root_goal_id"] not in roots or parent["root_goal_id"] != goal["root_goal_id"]:
            fail("goal root ancestry mismatch")
        if goal["return_to_goal_id"] != parent_id:
            fail("non-root return_to_goal_id must equal parent_goal_id")
        if goal_id not in parent["child_goal_ids"]:
            fail("parent child_goal_ids missing child")

    for parent_id, parent in by_id.items():
        for child_id in parent["child_goal_ids"]:
            if child_id not in by_id:
                fail("child_goal_ids contains unknown goal")
            if by_id[child_id]["parent_goal_id"] != parent_id:
                fail("child parent pointer mismatch")

    for index, goal_id in enumerate(active_path):
        if goal_id not in by_id:
            fail("active_path contains unknown goal")
        goal = by_id[goal_id]
        if goal["root_goal_id"] != active_root:
            fail("active_path goal root mismatch")
        if index == 0:
            if goal_id != active_root:
                fail("active_path must start at active root")
        elif goal["parent_goal_id"] != active_path[index - 1]:
            fail("active_path is not parent chain")

    validate_schema_header(
        schema,
        "https://github.com/KINETIC-DESIGN-CO/Build/blob/main/governance/schema/goal-registry.schema.json",
        REGISTRY_ROOT_KEYS,
        "goal-registry",
    )


def validate_all(root: Path = ROOT):
    policy = load_json(root / "governance/goal-policy.json")
    registry = load_json(root / "governance/goal-registry.json")
    policy_schema = load_json(root / "governance/schema/goal-policy.schema.json")
    registry_schema = load_json(root / "governance/schema/goal-registry.schema.json")
    validate_policy(policy, policy_schema)
    validate_registry(registry, registry_schema)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true")
    parser.parse_args()
    try:
        validate_all()
    except GoalGraphError as exc:
        print(f"GOAL_GRAPH_INVALID: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print("GOAL_GRAPH_VALID")


if __name__ == "__main__":
    import sys
    main()
