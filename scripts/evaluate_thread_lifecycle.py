#!/usr/bin/env python3
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance/thread-lifecycle-policy.json"
POLICY_SCHEMA_PATH = ROOT / "governance/schema/thread-lifecycle-policy.schema.json"
GOAL_POLICY_PATH = ROOT / "governance/goal-policy.json"
GOAL_REGISTRY_PATH = ROOT / "governance/goal-registry.json"
ADMISSIONS_PATH = ROOT / "governance/work-admissions.json"
SELECTOR = ROOT / "scripts/select_work.py"

UNRESOLVED_INTERRUPTION = {"PENDING","NO_RESULT","TIMEOUT","UNKNOWN"}
TERMINAL_GOALS = {"COMPLETE","REMOVED"}
LOCK_KEYS = {"schema_version","resource_key","generation","state","work_id","worker","implementation_branch","lease_id","base_sha","acquired_at","heartbeat_at","expires_at","runtime_control_authority"}

class LifecycleError(RuntimeError):
    pass

def fail(message):
    raise LifecycleError(message)

def no_dupe(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            fail(f"duplicate JSON key: {key}")
        out[key] = value
    return out

def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_dupe)
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")

def parse_utc(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        fail(f"timestamp must be RFC3339 UTC ending Z: {value!r}")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        fail(f"invalid timestamp: {value!r}")

def lock_branch(resource_key):
    return "lock/" + hashlib.sha256(resource_key.encode()).hexdigest()

def validate_lock(key, lock):
    if lock is None:
        return None
    if not isinstance(lock, dict) or set(lock) != LOCK_KEYS:
        fail(f"lock shape mismatch for {key}")
    if lock["schema_version"] != 1 or lock["runtime_control_authority"] != "NONE" or lock["resource_key"] != key or lock["state"] not in {"ACTIVE","RELEASED"}:
        fail(f"lock invariant mismatch for {key}")
    if not isinstance(lock["generation"], int) or isinstance(lock["generation"], bool) or lock["generation"] < 1:
        fail(f"lock generation invalid for {key}")
    for field in ("acquired_at","heartbeat_at","expires_at"):
        parse_utc(lock[field])
    return lock

def active(lock, now):
    return lock is not None and lock["state"] == "ACTIVE" and now < parse_utc(lock["expires_at"])

def validate_policy(policy, schema):
    expected = {
        "schema_version":1,
        "policy_id":"life-thread-lifecycle-v1",
        "runtime_control_authority":"NONE",
        "engineering_selection_precondition_authority":"DETERMINISTIC_EVALUATION_ONLY",
        "canonical_entrypoint":"scripts/evaluate_thread_lifecycle.py",
        "goal_policy_path":"governance/goal-policy.json",
        "goal_registry_path":"governance/goal-registry.json",
        "downstream_work_selection_policy_path":"governance/work-selection-policy.json",
        "downstream_selector_path":"scripts/select_work.py",
        "boundary_states":["RESUME_INTERRUPTED_OPERATION","CONTINUE_ACTIVE_GOAL","RETURN_TO_PARENT_GOAL","DELEGATE_TO_WORK_SELECTION","TERMINAL_CLEANUP_REQUIRED","TERMINAL_HANDOFF"],
        "interruption_rule":"UNRESOLVED_INTERRUPTED_OPERATION_RETURNS_RESUME_INTERRUPTED_OPERATION_BEFORE_GOAL_EVALUATION",
        "parent_return_rule":"TERMINAL_ACTIVE_CHILD_WITH_NONTERMINAL_PARENT_RETURNS_PARENT_AS_EFFECTIVE_GOAL",
        "active_goal_rule":"NONTERMINAL_EFFECTIVE_GOAL_COMPONENT_AVAILABLE_OR_OWNED_BY_REQUESTER_RETURNS_CONTINUE_ACTIVE_GOAL",
        "parallel_delegation_rule":"NONTERMINAL_EFFECTIVE_GOAL_COMPONENT_ACTIVE_UNEXPIRED_FOR_OTHER_WORK_ID_RETURNS_DELEGATE_TO_WORK_SELECTION",
        "downstream_authority_rule":"DOWNSTREAM_WORK_SELECTION_RESULT_HAS_ZERO_EXECUTION_EFFECT_UNLESS_BOUNDARY_STATE_IS_DELEGATE_TO_WORK_SELECTION",
        "terminal_cleanup_rule":"TERMINAL_ROOT_WITH_ACTIVE_UNEXPIRED_ROOT_COMPONENT_CLAIM_RETURNS_TERMINAL_CLEANUP_REQUIRED",
        "terminal_handoff_rule":"TERMINAL_ROOT_WITH_NO_ACTIVE_UNEXPIRED_ROOT_COMPONENT_CLAIM_RETURNS_TERMINAL_HANDOFF",
        "terminal_handoff_states":["SAFE_TO_CLOSE_NO_CANDIDATE","SAFE_TO_CLOSE_WITH_CANDIDATE"],
        "candidate_discovery_rule":"TERMINAL_HANDOFF_DISCOVERS_FIRST_DISPATCHABLE_UNCLAIMED_ADMITTED_ITEM_BY_EXISTING_TIE_BREAK_WITHOUT_ACQUIRING_A_CLAIM",
        "candidate_effect":"ADVISORY_ONLY_ZERO_CLAIM_ACQUISITION_ZERO_EXECUTION",
        "automatic_execution_rule":"FORBID_AUTOMATIC_EXECUTION_AFTER_TERMINAL_ROOT",
        "continue_rule":"CONTINUE_CANDIDATE_ONLY_AFTER_EXACT_VINCE_CONTINUE_DIRECTIVE_OR_VERSIONED_AUTHORIZED_ROOT_TRANSITION",
        "default_recommendation":"CLOSE_THREAD",
        "options_rule":"SAFE_TO_CLOSE_NO_CANDIDATE_OPTIONS_EQUALS:CLOSE_THREAD;SAFE_TO_CLOSE_WITH_CANDIDATE_OPTIONS_EQUALS:CLOSE_THREAD,CONTINUE_WITH_CANDIDATE",
        "missing_evidence_rule":"MISSING_INVALID_STALE_OR_UNVERIFIED_BOUNDARY_EVIDENCE_CANNOT_RETURN_TERMINAL_HANDOFF_OR_DELEGATE_TO_WORK_SELECTION"
    }
    if policy != expected:
        fail("thread lifecycle policy exact contract mismatch")
    if not isinstance(schema, dict) or schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema" or schema.get("additionalProperties") is not False:
        fail("thread lifecycle schema root mismatch")
    if set(schema.get("required", [])) != set(expected) or set(schema.get("properties", {})) != set(expected):
        fail("thread lifecycle schema keys mismatch")
    for key, value in expected.items():
        if schema["properties"].get(key, {}).get("const") != value:
            fail(f"thread lifecycle schema const mismatch: {key}")

def validate_goal_graph():
    sys.path.insert(0, str(ROOT / "scripts"))
    import validate_goal_graph as goal_graph
    return goal_graph.validate_all(ROOT)

def load_admissions():
    admissions = load(ADMISSIONS_PATH)
    items = admissions.get("items")
    if not isinstance(items, list):
        fail("work admissions items missing")
    by_id = {item["work_item_id"]: item for item in items}
    if len(by_id) != len(items):
        fail("duplicate work admission id")
    return admissions, by_id

def dispatchable(item, by_id):
    return item["state"] == "ADMITTED" and all(by_id.get(dep, {}).get("state") == "COMPLETE" for dep in item["depends_on"])

def ready_items(admissions, by_id):
    return sorted(
        (item for item in admissions["items"] if dispatchable(item, by_id)),
        key=lambda item:(item["dispatch_tier"], item["source_issue_number"], item["work_item_id"]),
    )

def required_keys(registry, admissions):
    keys = {f"component:{goal['component_id']}" for goal in registry["goals"]}
    keys.update(f"component:{item['component_id']}" for item in admissions["items"] if item["state"] == "ADMITTED")
    return sorted(keys)

def candidate(admissions, by_id, locks, now):
    for item in ready_items(admissions, by_id):
        key = f"component:{item['component_id']}"
        if not active(locks[key], now):
            return {
                "work_item_id":item["work_item_id"],
                "source_issue_number":item["source_issue_number"],
                "component_resource_key":key,
                "dispatch_tier":item["dispatch_tier"],
            }
    return None

def evaluate(snapshot, requester_work_id=None):
    policy = load(POLICY_PATH)
    validate_policy(policy, load(POLICY_SCHEMA_PATH))
    validate_goal_graph()
    registry = load(GOAL_REGISTRY_PATH)
    admissions, by_id = load_admissions()
    if not isinstance(snapshot, dict) or set(snapshot) != {"observed_at","interrupted_operation_state","resources"}:
        fail("lifecycle snapshot keys mismatch")
    now = parse_utc(snapshot["observed_at"])
    if snapshot["interrupted_operation_state"] not in {"NONE","PENDING","NO_RESULT","TIMEOUT","UNKNOWN","SUCCESS","FAILURE"}:
        fail("interrupted_operation_state invalid")
    required = required_keys(registry, admissions)
    resources = snapshot["resources"]
    if not isinstance(resources, dict) or set(resources) != set(required):
        fail(f"lifecycle resource coverage mismatch: required={required}")
    locks = {key:validate_lock(key, resources[key]) for key in required}
    if snapshot["interrupted_operation_state"] in UNRESOLVED_INTERRUPTION:
        return {
            "boundary_state":"RESUME_INTERRUPTED_OPERATION",
            "effective_goal_id":registry["active_goal_id"],
            "downstream_work_selection_effect":"ZERO",
            "terminal_handoff_state":None,
            "candidate":None,
            "recommendation":"CONTINUE_ORIGINAL_OPERATION",
            "options":["CONTINUE_ORIGINAL_OPERATION"],
        }
    goals = {goal["goal_id"]:goal for goal in registry["goals"]}
    active_goal = goals[registry["active_goal_id"]]
    root = goals[registry["active_root_goal_id"]]
    effective_goal = active_goal
    returned_parent = False
    if active_goal["goal_state"] in TERMINAL_GOALS and active_goal["parent_goal_id"] is not None:
        parent = goals[active_goal["parent_goal_id"]]
        if parent["goal_state"] not in TERMINAL_GOALS:
            effective_goal = parent
            returned_parent = True
    if root["goal_state"] in TERMINAL_GOALS:
        if effective_goal["goal_id"] != root["goal_id"]:
            fail("terminal root cannot have non-root effective goal")
        root_key = f"component:{root['component_id']}"
        root_lock = locks[root_key]
        if active(root_lock, now):
            return {
                "boundary_state":"TERMINAL_CLEANUP_REQUIRED",
                "effective_goal_id":root["goal_id"],
                "downstream_work_selection_effect":"ZERO",
                "terminal_handoff_state":None,
                "candidate":None,
                "recommendation":"CONTINUE_TERMINAL_CLEANUP",
                "options":["CONTINUE_TERMINAL_CLEANUP"],
            }
        next_candidate = candidate(admissions, by_id, locks, now)
        handoff = "SAFE_TO_CLOSE_WITH_CANDIDATE" if next_candidate else "SAFE_TO_CLOSE_NO_CANDIDATE"
        options = ["CLOSE_THREAD"] + (["CONTINUE_WITH_CANDIDATE"] if next_candidate else [])
        return {
            "boundary_state":"TERMINAL_HANDOFF",
            "effective_goal_id":root["goal_id"],
            "downstream_work_selection_effect":"ZERO",
            "terminal_handoff_state":handoff,
            "candidate":next_candidate,
            "recommendation":"CLOSE_THREAD",
            "options":options,
        }
    key = f"component:{effective_goal['component_id']}"
    lock = locks[key]
    owned_by_other = active(lock, now) and (requester_work_id is None or lock["work_id"] != requester_work_id)
    if owned_by_other:
        return {
            "boundary_state":"DELEGATE_TO_WORK_SELECTION",
            "effective_goal_id":effective_goal["goal_id"],
            "downstream_work_selection_effect":"DELEGATE",
            "terminal_handoff_state":None,
            "candidate":None,
            "recommendation":"RUN_DOWNSTREAM_WORK_SELECTION",
            "options":["RUN_DOWNSTREAM_WORK_SELECTION"],
        }
    return {
        "boundary_state":"RETURN_TO_PARENT_GOAL" if returned_parent else "CONTINUE_ACTIVE_GOAL",
        "effective_goal_id":effective_goal["goal_id"],
        "downstream_work_selection_effect":"ZERO",
        "terminal_handoff_state":None,
        "candidate":None,
        "recommendation":"CONTINUE_ORIGINAL_GOAL",
        "options":["CONTINUE_ORIGINAL_GOAL"],
    }

def git(*args, check=True):
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if check and proc.returncode:
        fail(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc

def live_lock(key):
    branch = lock_branch(key)
    ref = f"refs/remotes/origin/{branch}"
    proc = git("fetch","--quiet","origin",f"refs/heads/{branch}:{ref}",check=False)
    if proc.returncode:
        low = proc.stderr.lower()
        if "couldn't find remote ref" in low or "remote ref does not exist" in low:
            return None
        fail(f"live lock fetch failed for {key}: {proc.stderr.strip()}")
    try:
        return validate_lock(key, json.loads(git("show", f"{ref}:coordination/lock.json").stdout, object_pairs_hook=no_dupe))
    except Exception as exc:
        fail(f"invalid live lock JSON for {key}: {exc}")

def live_snapshot():
    registry = load(GOAL_REGISTRY_PATH)
    admissions, _ = load_admissions()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    return {
        "observed_at":now,
        "interrupted_operation_state":"NONE",
        "resources":{key:live_lock(key) for key in required_keys(registry, admissions)},
    }

def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-policy", action="store_true")
    mode.add_argument("--evaluate-snapshot")
    mode.add_argument("--dispatch-live", action="store_true")
    parser.add_argument("--requester-work-id")
    args = parser.parse_args()
    try:
        validate_policy(load(POLICY_PATH), load(POLICY_SCHEMA_PATH))
        validate_goal_graph()
        if args.evaluate_snapshot:
            print(json.dumps(evaluate(load(Path(args.evaluate_snapshot)), args.requester_work_id), indent=2))
        elif args.dispatch_live:
            print(json.dumps(evaluate(live_snapshot(), args.requester_work_id), indent=2))
        else:
            print("VALID")
        return 0
    except (LifecycleError,OSError,json.JSONDecodeError) as exc:
        print(f"THREAD_LIFECYCLE_INVALID: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
