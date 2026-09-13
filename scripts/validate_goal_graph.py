#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance/goal-policy.json"
REGISTRY_PATH = ROOT / "governance/goal-registry.json"
POLICY_SCHEMA_PATH = ROOT / "governance/schema/goal-policy.schema.json"
REGISTRY_SCHEMA_PATH = ROOT / "governance/schema/goal-registry.schema.json"
DIRECTIVE_PATH = ROOT / "continuity/directive-ledger.jsonl"

UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
CONDITION = re.compile(r"^[A-Z][A-Z0-9_]*$")
COMPONENT = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
RT = re.compile(r"^RT-[0-9]{4}$")
SIGNAL_ID = re.compile(r"^GS-[0-9]{4}$")
SIGNAL_SOURCE = re.compile(r"^(VINCE_DIRECTIVE|VINCE_CORRECTION|VINCE_AUTHORIZED_CHANGE):(VD-[0-9]{4})$")
REVISION_SENSITIVE_FIELDS = {
    "root_goal_id",
    "parent_goal_id",
    "return_to_goal_id",
    "component_id",
    "goal_relation",
    "title",
    "description",
    "completion_condition_ids",
    "child_goal_ids",
}


class GoalError(RuntimeError):
    pass


def fail(message):
    raise GoalError(message)


def load(path):
    def hook(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                fail(f"duplicate JSON key in {path}: {key}")
            out[key] = value
        return out
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=hook)
    except GoalError:
        raise
    except Exception as exc:
        fail(f"invalid JSON {path}: {exc}")


def load_jsonl(path):
    rows = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        fail(f"cannot read {path}: {exc}")
    for index, line in enumerate(lines, 1):
        if not line:
            fail(f"blank JSONL line {path}:{index}")
        try:
            row = json.loads(line)
        except Exception as exc:
            fail(f"invalid JSONL {path}:{index}: {exc}")
        if not isinstance(row, dict):
            fail(f"JSONL row must be object {path}:{index}")
        rows.append(row)
    return rows


def git(*args):
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        fail(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def unique_strings(value, label, pattern=None, min_items=0):
    if not isinstance(value, list) or len(value) < min_items:
        fail(f"{label} must be an array with at least {min_items} item(s)")
    if any(not isinstance(item, str) or not item for item in value):
        fail(f"{label} must contain nonempty strings")
    if len(value) != len(set(value)):
        fail(f"{label} must contain unique strings")
    if pattern and any(pattern.fullmatch(item) is None for item in value):
        fail(f"{label} contains an invalid identifier")
    return value


def validate_policy(policy, schema):
    required = {
        "schema_version", "policy_id", "runtime_control_authority", "engineering_goal_authority",
        "goal_relations", "goal_states", "terminal_goal_states", "terminal_cleanup_states",
        "attempt_states", "active_path_rule", "child_terminal_rule", "root_terminal_rule",
        "root_switch_rule", "execution_identity_rule", "parallel_rule", "issue_authority_rule",
        "checkpoint_rule", "missing_evidence_rule",
    }
    if not isinstance(policy, dict) or set(policy) != required:
        fail("goal-policy root keys mismatch")
    if policy["schema_version"] != 1 or policy["policy_id"] != "life-engineering-goal-policy-v1":
        fail("goal-policy identity mismatch")
    if policy["runtime_control_authority"] != "NONE" or policy["engineering_goal_authority"] != "DETERMINISTIC_EVALUATION_ONLY":
        fail("goal-policy authority mismatch")
    expected_relations = ["ROOT", "PREREQUISITE", "BLOCKER_REPAIR", "CONTINUITY_CAPTURE", "VERIFICATION", "TERMINAL_CLEANUP", "DEFECT_REPAIR", "ISSUE_CONSOLIDATION", "IMPLEMENTATION_CHILD"]
    expected_states = ["ACTIVE", "BLOCKED_RESOURCE", "BLOCKED_AUTHORIZATION", "BLOCKED_COST", "BLOCKED_PLATFORM", "VERIFYING", "COMPLETE", "REMOVED"]
    if policy["goal_relations"] != expected_relations or policy["goal_states"] != expected_states:
        fail("goal-policy closed enums mismatch")
    if policy["terminal_goal_states"] != ["COMPLETE", "REMOVED"] or policy["terminal_cleanup_states"] != ["PENDING", "VERIFIED"]:
        fail("goal-policy terminal enums mismatch")
    if policy["attempt_states"] != ["ACTIVE", "TERMINAL_SUCCESS", "TERMINAL_FAILURE", "SUPERSEDED"]:
        fail("goal-policy attempt states mismatch")
    exact_rules = {
        "active_path_rule": "ACTIVE_PATH_EQUALS_ROOT_TO_ACTIVE_GOAL_PARENT_CHAIN",
        "child_terminal_rule": "TERMINAL_CHILD_RETURNS_TO_PARENT_BEFORE_UNRELATED_ROOT_SELECTION",
        "root_terminal_rule": "ROOT_TERMINAL_REQUIRES_ALL_COMPLETION_CONDITIONS_TERMINAL_CLEANUP_VERIFIED_AND_ZERO_ACTIVE_ATTEMPTS",
        "root_switch_rule": "UNRELATED_ROOT_SELECTION_ALLOWED_ONLY_AFTER_TERMINAL_HANDOFF_AND_EXACT_VINCE_CONTINUE_DIRECTIVE_OR_VERSIONED_AUTHORIZED_ROOT_TRANSITION",
        "execution_identity_rule": "WORK_ID_LEASE_ID_GENERATION_AND_THREAD_ID_DO_NOT_DEFINE_GOAL_ID",
        "parallel_rule": "PARALLEL_WORK_HAS_ZERO_EFFECT_ON_ANOTHER_FOREGROUND_ACTIVE_ROOT_GOAL_ID",
        "issue_authority_rule": "GITHUB_ISSUE_CONTENT_AND_RELATIONSHIPS_HAVE_ZERO_GOAL_SELECTION_AUTHORITY",
        "checkpoint_rule": "CHECKPOINT_GOAL_STATE_IS_HISTORICAL_EVIDENCE_ONLY_AND_REQUIRES_FRESH_GOAL_REGISTRY_AND_LIVE_CLAIM_READS",
        "missing_evidence_rule": "MISSING_INVALID_STALE_OR_UNVERIFIED_GOAL_EVIDENCE_CANNOT_CREATE_TERMINAL_STATE_OR_ROOT_SWITCH",
    }
    for key, value in exact_rules.items():
        if policy.get(key) != value:
            fail(f"goal-policy rule mismatch: {key}")
    if not isinstance(schema, dict) or schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema" or schema.get("additionalProperties") is not False:
        fail("goal-policy schema root mismatch")
    if set(schema.get("required", [])) != required or set(schema.get("properties", {})) != required:
        fail("goal-policy schema keys mismatch")
    for key, value in policy.items():
        if schema["properties"].get(key, {}).get("const") != value:
            fail(f"goal-policy schema const mismatch: {key}")


def directive_map(rows):
    out = {}
    for row in rows:
        directive_id = row.get("id")
        if isinstance(directive_id, str) and re.fullmatch(r"VD-[0-9]{4}", directive_id):
            if directive_id in out:
                fail(f"duplicate directive id {directive_id}")
            out[directive_id] = row
    return out


def validate_signal(goal, directives):
    signal = goal.get("control_signal")
    if not isinstance(signal, dict) or set(signal) != {"state", "signal_id", "target_work_id", "issued_for_revision", "source_ref"}:
        fail("control_signal keys mismatch")
    state = signal["state"]
    if state not in {"NONE", "YIELD_OR_REPLAN_REQUESTED", "REASSIGNMENT_REQUESTED"}:
        fail("control_signal state invalid")
    if signal["issued_for_revision"] != goal["revision"]:
        fail("control_signal issued_for_revision must equal goal revision")
    if state == "NONE":
        if signal["signal_id"] is not None or signal["target_work_id"] is not None or signal["source_ref"] is not None:
            fail("NONE control_signal must have null signal_id/target_work_id/source_ref")
        return
    if not isinstance(signal["signal_id"], str) or SIGNAL_ID.fullmatch(signal["signal_id"]) is None:
        fail("active control_signal signal_id invalid")
    if not isinstance(signal["target_work_id"], str) or UUID4.fullmatch(signal["target_work_id"]) is None:
        fail("active control_signal target_work_id invalid")
    source = signal["source_ref"]
    match = SIGNAL_SOURCE.fullmatch(str(source))
    if match is None:
        fail("active control_signal source_ref must be typed Vince evidence")
    source_class, directive_id = match.groups()
    directive = directives.get(directive_id)
    if directive is None or directive.get("input_class") != source_class or directive.get("lifecycle") != "ACTIVE":
        fail("active control_signal source_ref does not resolve to matching ACTIVE directive")


def validate_registry(registry, schema, policy, directives):
    root_keys = {"schema_version", "registry_id", "runtime_control_authority", "engineering_goal_authority", "active_root_goal_id", "active_goal_id", "active_path", "authorized_root_transition_id", "goals"}
    if not isinstance(registry, dict) or set(registry) != root_keys:
        fail("goal-registry root keys mismatch")
    if registry["schema_version"] != 2 or registry["registry_id"] != "life-engineering-goal-registry-v2":
        fail("goal-registry identity mismatch")
    if registry["runtime_control_authority"] != "NONE" or registry["engineering_goal_authority"] != "DETERMINISTIC_EVALUATION_ONLY":
        fail("goal-registry authority mismatch")
    root_id, active_id = registry["active_root_goal_id"], registry["active_goal_id"]
    if not isinstance(root_id, str) or UUID4.fullmatch(root_id) is None or not isinstance(active_id, str) or UUID4.fullmatch(active_id) is None:
        fail("active goal identifiers invalid")
    transition = registry["authorized_root_transition_id"]
    if transition is not None and (not isinstance(transition, str) or RT.fullmatch(transition) is None):
        fail("authorized_root_transition_id invalid")
    active_path = unique_strings(registry["active_path"], "active_path", UUID4, 1)
    if active_path[0] != root_id or active_path[-1] != active_id:
        fail("active_path endpoints mismatch")
    goals = registry["goals"]
    if not isinstance(goals, list) or not goals:
        fail("goals must be a nonempty array")
    goal_keys = {"goal_id", "root_goal_id", "parent_goal_id", "return_to_goal_id", "component_id", "goal_relation", "goal_state", "terminal_cleanup_state", "title", "description", "revision", "control_signal", "completion_condition_ids", "satisfied_condition_ids", "child_goal_ids", "execution_attempts", "source_refs", "runtime_control_authority"}
    by_id = {}
    attempt_owner = {}
    for goal in goals:
        if not isinstance(goal, dict) or set(goal) != goal_keys:
            fail("goal keys mismatch")
        gid = goal["goal_id"]
        if not isinstance(gid, str) or UUID4.fullmatch(gid) is None or gid in by_id:
            fail("goal_id invalid or duplicate")
        if not isinstance(goal["root_goal_id"], str) or UUID4.fullmatch(goal["root_goal_id"]) is None:
            fail("root_goal_id invalid")
        for field in ("parent_goal_id", "return_to_goal_id"):
            value = goal[field]
            if value is not None and (not isinstance(value, str) or UUID4.fullmatch(value) is None):
                fail(f"{field} invalid")
        if not isinstance(goal["component_id"], str) or COMPONENT.fullmatch(goal["component_id"]) is None:
            fail("component_id invalid")
        if goal["goal_relation"] not in policy["goal_relations"] or goal["goal_state"] not in policy["goal_states"]:
            fail("goal relation/state invalid")
        if goal["terminal_cleanup_state"] not in policy["terminal_cleanup_states"]:
            fail("terminal_cleanup_state invalid")
        if not isinstance(goal["title"], str) or not goal["title"] or len(goal["title"]) > 200:
            fail("goal title invalid")
        if not isinstance(goal["description"], str) or not goal["description"] or len(goal["description"]) > 500:
            fail("goal description invalid")
        if not isinstance(goal["revision"], int) or isinstance(goal["revision"], bool) or goal["revision"] < 1:
            fail("goal revision invalid")
        validate_signal(goal, directives)
        completion = unique_strings(goal["completion_condition_ids"], f"{gid}.completion_condition_ids", CONDITION, 1)
        satisfied = unique_strings(goal["satisfied_condition_ids"], f"{gid}.satisfied_condition_ids", CONDITION)
        if not set(satisfied).issubset(completion):
            fail("satisfied_condition_ids must be subset of completion_condition_ids")
        children = unique_strings(goal["child_goal_ids"], f"{gid}.child_goal_ids", UUID4)
        if gid in children:
            fail("goal cannot be own child")
        attempts = goal["execution_attempts"]
        if not isinstance(attempts, list):
            fail("execution_attempts must be array")
        active_attempts = 0
        for attempt in attempts:
            if not isinstance(attempt, dict) or set(attempt) != {"work_id", "attempt_state", "planned_goal_revision"}:
                fail("execution attempt keys mismatch")
            wid, state, planned = attempt["work_id"], attempt["attempt_state"], attempt["planned_goal_revision"]
            if not isinstance(wid, str) or UUID4.fullmatch(wid) is None or state not in policy["attempt_states"]:
                fail("execution attempt invalid")
            if state == "ACTIVE":
                active_attempts += 1
                if not isinstance(planned, int) or isinstance(planned, bool) or planned < 1:
                    fail("ACTIVE attempt requires planned_goal_revision")
            elif planned is not None and (not isinstance(planned, int) or isinstance(planned, bool) or planned < 1):
                fail("planned_goal_revision invalid")
            if wid in attempt_owner:
                fail("execution work_id maps to multiple goals")
            attempt_owner[wid] = gid
        if active_attempts > 1:
            fail("goal cannot have more than one ACTIVE execution attempt")
        unique_strings(goal["source_refs"], f"{gid}.source_refs", min_items=1)
        if goal["runtime_control_authority"] != "NONE":
            fail("goal runtime authority mismatch")
        if goal["goal_state"] in policy["terminal_goal_states"]:
            if set(satisfied) != set(completion) or goal["terminal_cleanup_state"] != "VERIFIED" or active_attempts:
                fail("terminal goal completion/cleanup/attempt invariant mismatch")
        by_id[gid] = goal
    if root_id not in by_id or active_id not in by_id:
        fail("active goal ids must resolve")
    root = by_id[root_id]
    if root["goal_relation"] != "ROOT" or root["parent_goal_id"] is not None or root["return_to_goal_id"] is not None or root["root_goal_id"] != root_id:
        fail("active root identity mismatch")
    for gid, goal in by_id.items():
        if goal["goal_relation"] == "ROOT":
            if goal["root_goal_id"] != gid or goal["parent_goal_id"] is not None or goal["return_to_goal_id"] is not None:
                fail("ROOT goal invariant mismatch")
        else:
            parent = goal["parent_goal_id"]
            if parent is None or parent not in by_id or goal["return_to_goal_id"] != parent or goal["root_goal_id"] != by_id[parent]["root_goal_id"] or gid not in by_id[parent]["child_goal_ids"]:
                fail("non-root parent/return/root linkage mismatch")
    for gid, goal in by_id.items():
        for child in goal["child_goal_ids"]:
            if child not in by_id or by_id[child]["parent_goal_id"] != gid:
                fail("child pointer mismatch")
    for index, gid in enumerate(active_path):
        if gid not in by_id or by_id[gid]["root_goal_id"] != root_id or (index and by_id[gid]["parent_goal_id"] != active_path[index - 1]):
            fail("active_path is not exact parent chain")
    if root["goal_state"] in policy["terminal_goal_states"] and active_id != root_id:
        fail("terminal root must be active_goal_id for terminal handoff")
    if not isinstance(schema, dict) or schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema" or schema.get("additionalProperties") is not False:
        fail("goal-registry schema root mismatch")
    if set(schema.get("required", [])) != root_keys or set(schema.get("properties", {})) != root_keys:
        fail("goal-registry schema keys mismatch")
    return by_id


def validate_revision_transition(previous, current):
    if previous.get("schema_version") == 1 and current.get("schema_version") == 2:
        old_ids = {goal.get("goal_id") for goal in previous.get("goals", []) if isinstance(goal, dict)}
        new = {goal.get("goal_id"): goal for goal in current.get("goals", []) if isinstance(goal, dict)}
        if not old_ids.issubset(new):
            fail("v1->v2 migration cannot delete existing goals")
        for gid in old_ids:
            if new[gid].get("revision") != 1:
                fail("v1->v2 migrated goals must initialize at revision 1")
        return
    if previous.get("schema_version") != 2 or current.get("schema_version") != 2:
        fail("unsupported goal-registry revision transition")
    old = {goal["goal_id"]: goal for goal in previous.get("goals", [])}
    new = {goal["goal_id"]: goal for goal in current.get("goals", [])}
    if not set(old).issubset(new):
        fail("goal history is append/state-transition only; existing goal cannot disappear")
    for gid, goal in new.items():
        if gid not in old:
            if goal.get("revision") != 1:
                fail("new goal must start at revision 1")
            continue
        prior = old[gid]
        prior_revision = prior.get("revision")
        current_revision = goal.get("revision")
        if not isinstance(prior_revision, int) or not isinstance(current_revision, int):
            fail("goal revisions missing during transition")
        changed = any(prior.get(field) != goal.get(field) for field in REVISION_SENSITIVE_FIELDS)
        expected = prior_revision + 1 if changed else prior_revision
        if current_revision != expected:
            fail(f"goal {gid} revision must be {expected} for this transition")


def base_sha_for_event():
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    github_sha = os.environ.get("GITHUB_SHA", "")
    if event_name not in {"pull_request", "merge_group", "push"}:
        return None
    if not event_path:
        fail("GITHUB_EVENT_PATH missing")
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    if event_name == "pull_request":
        return str(((event.get("pull_request") or {}).get("base") or {}).get("sha") or "")
    if event_name == "merge_group":
        head = str((event.get("merge_group") or {}).get("head_sha") or github_sha)
        return git("rev-parse", f"{head}^1")
    before = str(event.get("before") or "")
    if re.fullmatch(r"[0-9a-f]{40}", before) and before != "0" * 40:
        return before
    head = github_sha or str(event.get("after") or "")
    return git("rev-parse", f"{head}^1")


def registry_at(sha):
    raw = git("show", f"{sha}:governance/goal-registry.json")
    try:
        return json.loads(raw)
    except Exception as exc:
        fail(f"invalid prior goal registry at {sha}: {exc}")


def validate_all(root=ROOT):
    policy = load(root / "governance/goal-policy.json")
    registry = load(root / "governance/goal-registry.json")
    directives = directive_map(load_jsonl(root / "continuity/directive-ledger.jsonl"))
    validate_policy(policy, load(root / "governance/schema/goal-policy.schema.json"))
    by_id = validate_registry(registry, load(root / "governance/schema/goal-registry.schema.json"), policy, directives)
    base_sha = base_sha_for_event()
    if base_sha:
        validate_revision_transition(registry_at(base_sha), registry)
    return by_id


def main():
    try:
        validate_all()
    except GoalError as exc:
        print(f"GOAL_GRAPH_INVALID: {exc}", file=sys.stderr)
        return 1
    print("GOAL_GRAPH_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
