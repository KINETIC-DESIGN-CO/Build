#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "work-fence-policy.json"
SCHEMA_PATH = ROOT / "governance" / "schema" / "work-fence-policy.schema.json"
REGISTRY_PATH = ROOT / "governance" / "goal-registry.json"
WORK_RECORD_RE = re.compile(r"^coordination/work/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.json$")
UUID4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
V1_LOCK_KEYS = {
    "schema_version", "resource_key", "generation", "state", "work_id", "worker",
    "implementation_branch", "lease_id", "base_sha", "acquired_at", "heartbeat_at",
    "expires_at", "runtime_control_authority",
}
V2_LOCK_KEYS = V1_LOCK_KEYS | {"lease_contract", "lease_event_type"}
V2_WORK_KEYS = {
    "schema_version", "work_id", "title", "worker", "implementation_branch", "base_sha",
    "component_id", "repo_paths", "external_targets", "claims", "goal_id",
    "planned_goal_revision", "pending_external_effect_state", "runtime_control_authority",
}
EXPECTED_POLICY = {
    "schema_version": 1,
    "policy_id": "life-work-fence-v1",
    "runtime_control_authority": "NONE",
    "engineering_fence_authority": "DETERMINISTIC_EVALUATION_ONLY",
    "canonical_evaluator": "scripts/evaluate_work_fence.py",
    "canonical_selector_entrypoint": "scripts/select_work.py",
    "component_stale_after_seconds": 1800,
    "legacy_v1_component_effective_expiry_rule": "AFTER_V4_MAIN_INTEGRATION_EFFECTIVE_EXPIRY_IS_MIN_STORED_EXPIRES_AT_AND_HEARTBEAT_PLUS_COMPONENT_STALE_AFTER_SECONDS",
    "goal_revision_fence_rule": "WHEN_GOAL_ID_IS_NON_NULL_PLANNED_GOAL_REVISION_MUST_EQUAL_CANONICAL_GOAL_REVISION",
    "goal_revision_mismatch_result": "REPLAN_REQUIRED",
    "generation_fence_rule": "WORK_RECORD_CLAIM_GENERATION_MUST_EQUAL_LIVE_CLAIM_GENERATION_AND_LIVE_CLAIM_WORK_ID_MUST_EQUAL_WORK_RECORD_WORK_ID",
    "generation_mismatch_result": "STALE_GENERATION",
    "control_signal_states": ["NONE", "YIELD_OR_REPLAN_REQUESTED", "REASSIGNMENT_REQUESTED"],
    "control_signal_rule": "NON_NONE_SIGNAL_APPLIES_ONLY_WHEN_TARGET_WORK_ID_EQUALS_EVALUATED_WORK_ID",
    "external_effect_states": ["NONE", "PENDING", "NO_RESULT", "TIMEOUT", "UNKNOWN", "SUCCESS", "FAILURE"],
    "external_effect_unresolved_states": ["PENDING", "NO_RESULT", "TIMEOUT", "UNKNOWN"],
    "external_effect_unresolved_result": "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED",
    "evaluation_precedence": [
        "EXTERNAL_EFFECT_UNRESOLVED", "GOAL_REVISION_MISMATCH", "CONTROL_SIGNAL_ACTIVE",
        "CLAIM_GENERATION_MISMATCH", "CLAIM_OWNER_MISMATCH", "COMPONENT_LEASE_EXPIRED", "PASS",
    ],
    "protected_boundaries": [
        "SOURCE_WORKSPACE_MUTATION", "CONNECTED_APP_MUTATION", "CLAIM_RENEWAL",
        "WORK_SELECTION_DISPATCH", "PULL_REQUEST_VALIDATION", "MERGE_GROUP_VALIDATION",
    ],
    "thread_wakeup_dependency": "FORBIDDEN",
    "takeover_rule": "COMPONENT_OWNERSHIP_TRANSFER_REQUIRES_PREDECESSOR_RELEASED_OR_EFFECTIVELY_EXPIRED_AND_GENERATION_PLUS_ONE_WITH_NEW_LEASE_ID;WORK_ID_MAY_REMAIN_SAME_FOR_DURABLE_WORK_RECOVERY",
    "renewal_event_types": ["PROTECTED_MUTATION_COMMITTED", "REQUIRED_CHECKPOINT_WRITTEN"],
    "background_heartbeat_requirement": "NONE",
    "scheduled_sweep_authority": "ADVISORY_ONLY",
}


class FenceError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise FenceError(message)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        fail(f"timestamp must be RFC3339 UTC ending Z: {value!r}")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        fail(f"invalid timestamp: {value!r}")


def git(*args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if check and proc.returncode != 0:
        fail(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def expected_lock_branch(resource_key: str) -> str:
    return "lock/" + hashlib.sha256(resource_key.encode("utf-8")).hexdigest()


def validate_policy(policy: dict | None = None, schema: dict | None = None) -> dict:
    policy = policy or load_json(POLICY_PATH)
    schema = schema or load_json(SCHEMA_PATH)
    if policy != EXPECTED_POLICY:
        fail("work-fence policy drift")
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema" or schema.get("additionalProperties") is not False:
        fail("work-fence schema header mismatch")
    if set(schema.get("required", [])) != set(EXPECTED_POLICY) or set(schema.get("properties", {})) != set(EXPECTED_POLICY):
        fail("work-fence schema keys mismatch")
    return policy


def validate_lock_snapshot(lock: dict, resource_key: str | None = None) -> dict:
    if not isinstance(lock, dict):
        fail("live claim must be object")
    version = lock.get("schema_version")
    expected = V1_LOCK_KEYS if version == 1 else V2_LOCK_KEYS if version == 2 else None
    if expected is None or set(lock) != expected:
        fail("live claim schema/keys mismatch")
    if lock.get("runtime_control_authority") != "NONE" or lock.get("state") not in {"ACTIVE", "RELEASED"}:
        fail("live claim authority/state invalid")
    if resource_key is not None and lock.get("resource_key") != resource_key:
        fail("live claim resource_key mismatch")
    if not isinstance(lock.get("generation"), int) or isinstance(lock.get("generation"), bool) or lock["generation"] < 1:
        fail("live claim generation invalid")
    if not UUID4_RE.fullmatch(str(lock.get("work_id", ""))) or not UUID4_RE.fullmatch(str(lock.get("lease_id", ""))):
        fail("live claim work_id/lease_id invalid")
    acquired, heartbeat, expires = map(parse_utc, (lock.get("acquired_at"), lock.get("heartbeat_at"), lock.get("expires_at")))
    if not (acquired <= heartbeat < expires):
        fail("live claim timestamp ordering invalid")
    if version == 2:
        if not str(lock.get("resource_key", "")).startswith("component:"):
            fail("schema v2 lock is reserved for component resources")
        if lock.get("lease_contract") != "COMPONENT_1800":
            fail("schema v2 component lease_contract mismatch")
        if lock.get("lease_event_type") not in {"ACQUIRE", "TAKEOVER", "REACQUIRE", "RENEW_PROTECTED_MUTATION", "RENEW_REQUIRED_CHECKPOINT"}:
            fail("schema v2 component lease_event_type invalid")
        if int((expires - heartbeat).total_seconds()) != EXPECTED_POLICY["component_stale_after_seconds"]:
            fail("schema v2 component duration must equal component_stale_after_seconds")
    return lock


def effective_component_expiry(lock: dict, policy: dict | None = None) -> datetime:
    policy = policy or EXPECTED_POLICY
    validate_lock_snapshot(lock)
    stored = parse_utc(lock["expires_at"])
    if not str(lock["resource_key"]).startswith("component:"):
        return stored
    heartbeat = parse_utc(lock["heartbeat_at"])
    if lock["schema_version"] == 2:
        if int((stored - heartbeat).total_seconds()) != policy["component_stale_after_seconds"]:
            fail("schema v2 component duration must equal component_stale_after_seconds")
        return stored
    return min(stored, heartbeat + timedelta(seconds=policy["component_stale_after_seconds"]))


def goal_by_id(registry: dict, goal_id: str) -> dict:
    goals = registry.get("goals") if isinstance(registry, dict) else None
    if not isinstance(goals, list):
        fail("goal registry goals missing")
    matches = [goal for goal in goals if isinstance(goal, dict) and goal.get("goal_id") == goal_id]
    if len(matches) != 1:
        fail("goal_id must resolve to exactly one canonical goal")
    return matches[0]


def evaluate_record_claim(record: dict, claim: dict, live_lock: dict, registry: dict, observed_at: datetime, policy: dict | None = None) -> dict:
    policy = policy or EXPECTED_POLICY
    effect_state = record.get("pending_external_effect_state")
    if effect_state in set(policy["external_effect_unresolved_states"]):
        return {"result": policy["external_effect_unresolved_result"], "reason": "EXTERNAL_EFFECT_UNRESOLVED"}
    if effect_state not in policy["external_effect_states"]:
        fail("pending_external_effect_state invalid")
    goal_id, planned_revision = record.get("goal_id"), record.get("planned_goal_revision")
    if goal_id is not None:
        if not isinstance(goal_id, str) or UUID4_RE.fullmatch(goal_id) is None:
            fail("work record goal_id invalid")
        goal = goal_by_id(registry, goal_id)
        canonical_revision = goal.get("revision")
        if not isinstance(canonical_revision, int) or isinstance(canonical_revision, bool) or canonical_revision < 1:
            fail("canonical goal revision invalid")
        if planned_revision != canonical_revision:
            return {"result": policy["goal_revision_mismatch_result"], "reason": "GOAL_REVISION_MISMATCH"}
        signal = goal.get("control_signal")
        if not isinstance(signal, dict) or signal.get("state") not in policy["control_signal_states"]:
            fail("canonical goal control signal invalid")
        if signal["state"] != "NONE" and signal.get("target_work_id") == record.get("work_id"):
            return {"result": "REASSIGNMENT_REQUIRED" if signal["state"] == "REASSIGNMENT_REQUESTED" else "REPLAN_REQUIRED", "reason": "CONTROL_SIGNAL_ACTIVE"}
    elif planned_revision is not None:
        fail("planned_goal_revision must be null when goal_id is null")
    resource_key = claim.get("resource_key")
    if not isinstance(resource_key, str) or not resource_key.startswith("component:"):
        fail("evaluate_record_claim requires a component claim")
    validate_lock_snapshot(live_lock, resource_key)
    if claim.get("generation") != live_lock.get("generation"):
        return {"result": policy["generation_mismatch_result"], "reason": "CLAIM_GENERATION_MISMATCH"}
    if live_lock.get("work_id") != record.get("work_id") or live_lock.get("lease_id") != claim.get("lease_id"):
        return {"result": "STALE_OWNER", "reason": "CLAIM_OWNER_MISMATCH"}
    if live_lock.get("state") != "ACTIVE":
        return {"result": "CLAIM_NOT_ACTIVE", "reason": "CLAIM_OWNER_MISMATCH"}
    if observed_at >= effective_component_expiry(live_lock, policy):
        return {"result": "COMPONENT_LEASE_EXPIRED", "reason": "COMPONENT_LEASE_EXPIRED"}
    return {"result": "PASS", "reason": "PASS"}


def load_live_lock(claim: dict) -> dict:
    branch = claim.get("lock_branch")
    if branch != expected_lock_branch(str(claim.get("resource_key", ""))):
        fail("claim lock_branch mismatch")
    remote_ref = f"refs/remotes/origin/{branch}"
    proc = subprocess.run(["git", "fetch", "--quiet", "origin", f"refs/heads/{branch}:{remote_ref}"], cwd=ROOT, text=True, capture_output=True)
    if proc.returncode:
        fail(f"missing live lock branch {branch}")
    try:
        return validate_lock_snapshot(json.loads(git("show", f"{remote_ref}:coordination/lock.json")), claim["resource_key"])
    except json.JSONDecodeError as exc:
        fail(f"invalid live lock JSON on {branch}: {exc}")


def protocol_id_at(commit_sha: str) -> str:
    try:
        value = json.loads(git("show", f"{commit_sha}:coordination/protocol.json")).get("protocol_id")
    except Exception as exc:
        fail(f"cannot read base coordination protocol: {exc}")
    if not isinstance(value, str):
        fail("base coordination protocol_id missing")
    return value


def event_diff(event_name: str, event: dict, github_sha: str) -> tuple[str, str, list[str]]:
    if event_name == "pull_request":
        pr = event.get("pull_request") or {}
        base_sha, head_sha = str((pr.get("base") or {}).get("sha") or ""), str((pr.get("head") or {}).get("sha") or "")
        if not SHA_RE.fullmatch(base_sha) or not SHA_RE.fullmatch(head_sha):
            fail("pull_request base/head SHA invalid")
        return base_sha, head_sha, sorted(p for p in git("diff", "--name-only", f"{base_sha}...{head_sha}").splitlines() if p)
    if event_name == "merge_group":
        group = event.get("merge_group") or {}
        head_sha = str(group.get("head_sha") or "")
        if not SHA_RE.fullmatch(head_sha) or (github_sha and head_sha != github_sha):
            fail("merge_group head SHA invalid")
        base_sha = git("rev-parse", f"{head_sha}^1")
        return base_sha, head_sha, sorted(p for p in git("diff", "--name-only", f"{base_sha}..{head_sha}").splitlines() if p)
    fail("work-fence event validation supports pull_request and merge_group only")


def validate_current_event() -> str:
    policy = validate_policy()
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    if event_name not in {"pull_request", "merge_group"}:
        return "WORK_FENCE_EVENT_NOT_APPLICABLE"
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not event_path:
        fail("GITHUB_EVENT_PATH missing")
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    base_sha, _head_sha, changed = event_diff(event_name, event, os.environ.get("GITHUB_SHA", ""))
    if protocol_id_at(base_sha) != "life-source-coordination-v4":
        return "WORK_FENCE_MIGRATION_COMPATIBILITY_PASS"
    work_paths = [path for path in changed if WORK_RECORD_RE.fullmatch(path)]
    if len(work_paths) != 1:
        fail("post-v4 protected event must change exactly one work record")
    record = load_json(ROOT / work_paths[0])
    if set(record) != V2_WORK_KEYS or record.get("schema_version") != 2:
        fail("post-v4 protected event requires schema v2 work record")
    if record.get("runtime_control_authority") != "NONE" or record.get("pending_external_effect_state") not in policy["external_effect_states"]:
        fail("post-v4 work record fence fields invalid")
    registry = load_json(REGISTRY_PATH)
    observed_at = datetime.now(timezone.utc)
    component_claims = [claim for claim in record.get("claims", []) if isinstance(claim, dict) and str(claim.get("resource_key", "")).startswith("component:")]
    if not component_claims:
        fail("post-v4 work record requires at least one component claim")
    for claim in component_claims:
        result = evaluate_record_claim(record, claim, load_live_lock(claim), registry, observed_at, policy)
        if result["result"] != "PASS":
            fail(f"{claim['resource_key']} fence result {result['result']} ({result['reason']})")
    return "WORK_FENCE_PASS"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-policy", action="store_true")
    parser.add_argument("--validate-current-event", action="store_true")
    parser.add_argument("--evidence")
    args = parser.parse_args()
    try:
        if args.validate_policy:
            validate_policy(); print("WORK_FENCE_POLICY_VALID")
        elif args.validate_current_event:
            print(validate_current_event())
        elif args.evidence:
            evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
            if not isinstance(evidence, dict) or set(evidence) != {"record", "claim", "live_lock", "registry", "observed_at"}:
                fail("evidence keys mismatch")
            print(json.dumps(evaluate_record_claim(evidence["record"], evidence["claim"], evidence["live_lock"], evidence["registry"], parse_utc(evidence["observed_at"]), validate_policy()), indent=2))
        else:
            validate_policy(); print("WORK_FENCE_POLICY_VALID")
        return 0
    except (FenceError, OSError, json.JSONDecodeError) as exc:
        print(f"WORK_FENCE_INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
