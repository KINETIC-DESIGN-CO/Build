#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "coordination" / "protocol.json"
LOCK_SCHEMA_PATH = ROOT / "coordination" / "schema" / "lock.schema.json"
WORK_SCHEMA_PATH = ROOT / "coordination" / "schema" / "work-record.schema.json"
FENCE_PATH = ROOT / "scripts" / "evaluate_work_fence.py"
UUID4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
COMPONENT_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
WORKER_KINDS = {"chatgpt", "claude", "grok", "codex", "human", "other_ai"}
V1_WORK_KEYS = {"schema_version", "work_id", "title", "worker", "implementation_branch", "base_sha", "component_id", "repo_paths", "external_targets", "claims", "runtime_control_authority"}
V2_WORK_KEYS = V1_WORK_KEYS | {"goal_id", "planned_goal_revision", "pending_external_effect_state"}

fence_spec = importlib.util.spec_from_file_location("evaluate_work_fence", FENCE_PATH)
fence = importlib.util.module_from_spec(fence_spec)
assert fence_spec.loader is not None
fence_spec.loader.exec_module(fence)


class ValidationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ValidationError(message)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def canonical_json(path: Path) -> None:
    obj = load_json(path)
    expected = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    if path.read_text(encoding="utf-8") != expected:
        fail(f"{path.relative_to(ROOT)} must be canonical indent=2 JSON with LF and final newline")


def git(*args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if check and proc.returncode != 0:
        fail(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def require_ancestor(base_sha: str, head_sha: str, label: str) -> None:
    proc = subprocess.run(["git", "merge-base", "--is-ancestor", base_sha, head_sha], cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        fail(f"{label} must be an ancestor of PR head")


def parse_utc(value: object) -> datetime:
    try:
        return fence.parse_utc(value)
    except fence.FenceError as exc:
        fail(str(exc))


def expected_lock_branch(resource_key: str) -> str:
    return "lock/" + hashlib.sha256(resource_key.encode("utf-8")).hexdigest()


def validate_worker(worker: object) -> None:
    if not isinstance(worker, dict) or set(worker) != {"kind", "session_id"}:
        fail("worker must contain exactly kind and session_id")
    if worker["kind"] not in WORKER_KINDS or not UUID4_RE.fullmatch(str(worker["session_id"])):
        fail("worker identity invalid")


def validate_acquisition_attempt_order(resource_keys: list[str]) -> None:
    if not isinstance(resource_keys, list) or not resource_keys or any(not isinstance(key, str) or not key for key in resource_keys):
        fail("acquisition attempt resource keys must be nonempty strings")
    if len(resource_keys) != len(set(resource_keys)) or resource_keys != sorted(resource_keys):
        fail("each acquisition attempt must use unique RESOURCE_KEY_ASCENDING_UTF8 order")


def blocking_resource_keys(requested_resource_keys: list[str], live_locks: list[dict], requesting_work_id: str, now: datetime) -> list[str]:
    if not UUID4_RE.fullmatch(str(requesting_work_id)):
        fail("requesting_work_id must be lowercase UUIDv4")
    if not isinstance(requested_resource_keys, list) or len(requested_resource_keys) != len(set(requested_resource_keys)):
        fail("requested_resource_keys must be unique array")
    requested = set(requested_resource_keys)
    blockers = set()
    for lock in live_locks:
        required = {"resource_key", "work_id", "state", "expires_at"}
        if not isinstance(lock, dict) or not required <= set(lock):
            fail("live lock evidence missing required blocking fields")
        if lock["resource_key"] in requested and lock["work_id"] != requesting_work_id and lock["state"] == "ACTIVE" and now < parse_utc(lock["expires_at"]):
            blockers.add(lock["resource_key"])
    return sorted(blockers)


def classify_operation_resource_sets(operation_resource_sets: dict[str, list[str]], live_locks: list[dict], requesting_work_id: str, now: datetime) -> dict[str, dict[str, object]]:
    if not isinstance(operation_resource_sets, dict) or not operation_resource_sets:
        fail("operation_resource_sets must be nonempty object")
    out = {}
    for operation_id in sorted(operation_resource_sets):
        blockers = blocking_resource_keys(operation_resource_sets[operation_id], live_locks, requesting_work_id, now)
        out[operation_id] = {"intersection_state": "INTERSECTION_NONEMPTY" if blockers else "INTERSECTION_EMPTY", "blocking_resource_keys": blockers}
    return out


def validate_protocol(protocol: dict) -> None:
    required = {
        "schema_version", "protocol_id", "runtime_control_authority", "source_coordination_authority",
        "canonical_repository", "default_branch", "work_branch_prefix", "lock_branch_prefix",
        "lock_branch_derivation", "lease_duration_seconds", "renew_when_remaining_seconds_lte",
        "legacy_lease_duration_seconds", "external_lease_duration_seconds", "component_lease_duration_seconds",
        "component_lock_schema_version", "component_v2_transition_rule", "component_legacy_effective_expiry_rule",
        "component_renewal_event_types", "expiration_rule", "lock_history_enforcement_start_utc",
        "resource_acquisition_order", "worker_kinds", "required_claims", "parallel_work", "mutation_rules",
        "integration_rules", "coordination_surfaces",
    }
    if not isinstance(protocol, dict) or set(protocol) != required:
        fail("protocol keys mismatch")
    exact = {
        "schema_version": 1,
        "protocol_id": "life-source-coordination-v4",
        "runtime_control_authority": "NONE",
        "source_coordination_authority": "GITHUB_MACHINE_STATE",
        "canonical_repository": "KINETIC-DESIGN-CO/Build",
        "default_branch": "main",
        "work_branch_prefix": "work/",
        "lock_branch_prefix": "lock/",
        "lock_branch_derivation": "lock/ + sha256(resource_key UTF-8 lowercase hex)",
        "lease_duration_seconds": 14400,
        "renew_when_remaining_seconds_lte": 1800,
        "legacy_lease_duration_seconds": 14400,
        "external_lease_duration_seconds": 14400,
        "component_lease_duration_seconds": 1800,
        "component_lock_schema_version": 2,
        "component_v2_transition_rule": "V1_COMPONENT_LOCK_REMAINS_VALID_TO_STORED_EXPIRES_AT;AFTER_V4_MAIN_INTEGRATION_ANY_COMPONENT_ACQUIRE_RENEW_TAKEOVER_OR_REACQUIRE_MUST_WRITE_SCHEMA_V2_COMPONENT_1800",
        "component_legacy_effective_expiry_rule": "USE_STORED_EXPIRES_AT_UNTIL_NEXT_SCHEMA_V2_TRANSITION",
        "component_renewal_event_types": ["PROTECTED_MUTATION_COMMITTED", "REQUIRED_CHECKPOINT_WRITTEN"],
        "expiration_rule": "COMPONENT_V1_AND_EXTERNAL_USE_STORED_EXPIRES_AT;COMPONENT_V2_USES_STORED_1800_SECOND_EXPIRES_AT",
        "lock_history_enforcement_start_utc": "2026-09-12T22:56:23Z",
        "resource_acquisition_order": "PER_ACQUISITION_ATTEMPT_RESOURCE_KEY_ASCENDING_UTF8",
    }
    for key, value in exact.items():
        if protocol.get(key) != value:
            fail(f"protocol.{key} mismatch")
    if set(protocol["worker_kinds"]) != WORKER_KINDS or len(protocol["worker_kinds"]) != len(WORKER_KINDS):
        fail("protocol.worker_kinds mismatch")
    if protocol["required_claims"] != {"component": "component:<component_id>", "supabase_production": "external:supabase:jnenguxodtgwbskhdsxt"}:
        fail("protocol.required_claims mismatch")
    rules = protocol["mutation_rules"]
    for rule in {
        "CONTINUITY_SYNC_PR_MAY_MERGE_MAIN_WITHOUT_SECOND_SYNC_ONLY_WHEN_CHANGED_PATHS_ARE_NONEMPTY_SUBSET_OF_BOOTSTRAP_CONTINUITY_SYNC_PATHS",
        "LOCK_HISTORY_VALIDATION_MUST_PROVE_LEGAL_DURATION_RENEWAL_RELEASE_REACQUISITION_AND_TAKEOVER_TRANSITIONS",
        "LOCK_COMPARE_AND_SWAP_CONFLICT_REQUIRES_FRESH_LIVE_LOCK_REREAD_BEFORE_ANY_RETRY_OR_NEW_ACQUISITION_ATTEMPT_FOR_THAT_RESOURCE",
        "CLAIM_OWNERSHIP_IS_RESOURCE_KEY_WORK_ID_LEASE_ID_GENERATION_NOT_WORKER_SESSION_ID",
        "WORKER_SESSION_ID_IS_AUDIT_LABEL_ONLY_AND_MAY_REPEAT_ACROSS_WORK_ITEMS",
        "LEGACY_V1_COMPONENT_RETAINS_STORED_EXPIRES_AT_AND_CANNOT_RENEW_AS_V1_AFTER_V4_MAIN_INTEGRATION",
        "AFTER_V4_MAIN_INTEGRATION_COMPONENT_RENEWAL_REQUIRES_SCHEMA_V2_AND_PROTECTED_MUTATION_COMMITTED_OR_REQUIRED_CHECKPOINT_WRITTEN_EVENT",
        "COMPONENT_SCHEMA_V2_EFFECTIVE_LEASE_DURATION_IS_1800_SECONDS",
        "AFTER_V4_MAIN_INTEGRATION_COMPONENT_ACQUIRE_RENEW_TAKEOVER_AND_REACQUIRE_REQUIRE_SCHEMA_V2_COMPONENT_1800_CONTRACT",
        "COMPONENT_GENERATION_IS_THE_STALE_WORKER_FENCING_TOKEN",
        "GOAL_REVISION_MISMATCH_RETURNS_REPLAN_REQUIRED_BEFORE_PROTECTED_BOUNDARY",
        "UNRESOLVED_EXTERNAL_EFFECT_PRECEDES_TAKEOVER_RETRY_OR_REPLAN",
        "MAIN_INTEGRATION_REQUIRES_GITHUB_MERGE_QUEUE",
        "MERGE_GROUP_VALIDATE_IS_LATEST_BASE_INTEGRATION_GATE",
    }:
        if rules.count(rule) != 1:
            fail(f"protocol mutation rule missing/duplicate: {rule}")
    if protocol["parallel_work"].get("main_integration_mode") != "GITHUB_REQUIRED_MERGE_QUEUE":
        fail("protocol parallel main integration mode mismatch")
    if protocol["parallel_work"].get("unexpired_rule") != "COMPONENT_V1_USES_STORED_EXPIRES_AT_COMPONENT_V2_USES_1800_SECOND_STORED_EXPIRES_AT_EXTERNAL_USES_STORED_EXPIRES_AT":
        fail("protocol parallel unexpired rule mismatch")
    for required_rule in {"MAIN_RULESET_MUST_REQUIRE_MERGE_QUEUE", "MERGE_GROUP_VALIDATE_MUST_PASS_BEFORE_MAIN_INTEGRATION", "LOCK_BASE_SHA_MUST_BE_ANCESTOR_OF_PR_HEAD", "POST_V4_MERGE_GROUP_MUST_PASS_WORK_FENCE_VALIDATION"}:
        if required_rule not in protocol["integration_rules"]:
            fail(f"protocol integration rule missing: {required_rule}")


def validate_schema_headers() -> None:
    for path in (LOCK_SCHEMA_PATH, WORK_SCHEMA_PATH):
        obj = load_json(path)
        if obj.get("$schema") != "https://json-schema.org/draft/2020-12/schema" or obj.get("additionalProperties") is not False:
            fail(f"{path.relative_to(ROOT)} schema header mismatch")


def validate_claim_shape(claim: object) -> None:
    if not isinstance(claim, dict) or set(claim) != {"resource_key", "lock_branch", "lease_id", "generation"}:
        fail("claim keys mismatch")
    if claim["lock_branch"] != expected_lock_branch(str(claim["resource_key"])):
        fail("claim lock branch mismatch")
    if not UUID4_RE.fullmatch(str(claim["lease_id"])) or not isinstance(claim["generation"], int) or isinstance(claim["generation"], bool) or claim["generation"] < 1:
        fail("claim identity/generation invalid")


def required_claim_keys(record: dict) -> set[str]:
    mandatory = {f"component:{record['component_id']}"} | set(record["external_targets"])
    if any(str(target).startswith("external:supabase:") for target in record["external_targets"]):
        mandatory.add("external:supabase:jnenguxodtgwbskhdsxt")
    return mandatory


def validate_work_record(record: dict, changed_files: list[str], head_branch: str, head_sha: str, require_v2: bool = False) -> None:
    expected = V2_WORK_KEYS if record.get("schema_version") == 2 else V1_WORK_KEYS if record.get("schema_version") == 1 else set()
    if not expected or set(record) != expected:
        fail("work record keys/schema mismatch")
    if require_v2 and record["schema_version"] != 2:
        fail("post-v4 work record must use schema v2")
    if record["runtime_control_authority"] != "NONE":
        fail("work record authority mismatch")
    work_id = str(record["work_id"])
    if not UUID4_RE.fullmatch(work_id):
        fail("work_id invalid")
    validate_worker(record["worker"])
    expected_branch = f"work/{work_id}"
    if record["implementation_branch"] != expected_branch or head_branch != expected_branch:
        fail(f"implementation branch must be exactly {expected_branch}")
    if not SHA_RE.fullmatch(str(record["base_sha"])):
        fail("work record base_sha invalid")
    require_ancestor(record["base_sha"], head_sha, "work record base_sha")
    if not COMPONENT_RE.fullmatch(str(record["component_id"])):
        fail("component_id invalid")
    if not isinstance(record["title"], str) or not (1 <= len(record["title"]) <= 160):
        fail("title length invalid")
    repo_paths = record["repo_paths"]
    if not isinstance(repo_paths, list) or not repo_paths or repo_paths != sorted(set(repo_paths)):
        fail("repo_paths must be nonempty unique sorted array")
    external = record["external_targets"]
    if not isinstance(external, list) or external != sorted(set(external)):
        fail("external_targets must be unique sorted array")
    claims = record["claims"]
    if not isinstance(claims, list) or not claims:
        fail("claims must be nonempty")
    for claim in claims:
        validate_claim_shape(claim)
    keys = [claim["resource_key"] for claim in claims]
    if keys != sorted(set(keys)):
        fail("claims must be unique sorted by resource_key")
    missing = required_claim_keys(record) - set(keys)
    if missing:
        fail(f"work record missing mandatory claims: {sorted(missing)}")
    if "integration:main" in keys:
        fail("obsolete integration:main claim forbidden")
    if record["schema_version"] == 2:
        goal_id, revision = record["goal_id"], record["planned_goal_revision"]
        if goal_id is None and revision is not None:
            fail("planned_goal_revision must be null when goal_id is null")
        if goal_id is not None and (not UUID4_RE.fullmatch(str(goal_id)) or not isinstance(revision, int) or isinstance(revision, bool) or revision < 1):
            fail("goal revision fence identity invalid")
        if record["pending_external_effect_state"] not in fence.EXPECTED_POLICY["external_effect_states"]:
            fail("pending_external_effect_state invalid")
    work_record_path = f"coordination/work/{work_id}.json"
    expected_changed = sorted(path for path in changed_files if path != work_record_path)
    if repo_paths != expected_changed:
        fail(f"repo_paths must exactly cover changed paths except work record; expected {expected_changed}")


def load_live_lock(claim: dict) -> dict:
    branch = claim["lock_branch"]
    remote_ref = f"refs/remotes/origin/{branch}"
    proc = subprocess.run(["git", "fetch", "--quiet", "origin", f"refs/heads/{branch}:{remote_ref}"], cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        fail(f"missing live lock branch {branch}")
    try:
        return json.loads(git("show", f"{remote_ref}:coordination/lock.json"))
    except Exception as exc:
        fail(f"invalid live lock JSON on {branch}: {exc}")


def effective_expiry(lock: dict, protocol: dict) -> datetime:
    if protocol.get("protocol_id") == "life-source-coordination-v4" and str(lock.get("resource_key", "")).startswith("component:"):
        try:
            return fence.effective_component_expiry(lock)
        except fence.FenceError as exc:
            fail(str(exc))
    return parse_utc(lock["expires_at"])


def validate_live_lock(lock: dict, claim: dict, record: dict, head_sha: str, now: datetime, protocol: dict) -> None:
    try:
        fence.validate_lock_snapshot(lock, claim["resource_key"])
    except fence.FenceError as exc:
        fail(str(exc))
    exact = {"resource_key": claim["resource_key"], "generation": claim["generation"], "work_id": record["work_id"], "worker": record["worker"], "implementation_branch": record["implementation_branch"], "lease_id": claim["lease_id"]}
    for key, value in exact.items():
        if lock[key] != value:
            fail(f"live lock {claim['resource_key']} mismatch at {key}")
    if not SHA_RE.fullmatch(str(lock["base_sha"])):
        fail("live lock base_sha invalid")
    require_ancestor(str(lock["base_sha"]), head_sha, f"live lock base_sha for {claim['resource_key']}")
    if protocol.get("protocol_id") in {"life-source-coordination-v2", "life-source-coordination-v3"}:
        if lock["schema_version"] != 1 or int((parse_utc(lock["expires_at"]) - parse_utc(lock["heartbeat_at"])).total_seconds()) != 14400:
            fail("legacy protocol requires schema v1 14400-second lock")
    elif str(lock["resource_key"]).startswith("component:") and lock["schema_version"] == 2:
        if int((parse_utc(lock["expires_at"]) - parse_utc(lock["heartbeat_at"])).total_seconds()) != 1800:
            fail("component v2 duration mismatch")
    elif lock["schema_version"] != 1:
        fail("noncomponent lock must remain schema v1")
    if now >= effective_expiry(lock, protocol):
        fail(f"live lock expired: {claim['resource_key']}")


def protocol_at(commit_sha: str) -> dict:
    try:
        return json.loads(git("show", f"{commit_sha}:coordination/protocol.json"))
    except Exception as exc:
        fail(f"cannot load base protocol: {exc}")


def validate_pull_request_event(event: dict, protocol: dict) -> None:
    pr = event.get("pull_request") or {}
    base_sha = str((pr.get("base") or {}).get("sha") or "")
    head_sha = str((pr.get("head") or {}).get("sha") or "")
    head_branch = str((pr.get("head") or {}).get("ref") or "")
    if not SHA_RE.fullmatch(base_sha) or not SHA_RE.fullmatch(head_sha):
        fail("pull_request base/head SHA invalid")
    changed = [path for path in git("diff", "--name-only", f"{base_sha}...{head_sha}").splitlines() if path]
    work_paths = [path for path in changed if re.fullmatch(r"coordination/work/[0-9a-f-]{36}\.json", path)]
    if len(work_paths) != 1:
        fail("every post-bootstrap PR must change exactly one work record")
    record = load_json(ROOT / work_paths[0])
    base_protocol = protocol_at(base_sha)
    require_v2 = base_protocol.get("protocol_id") == "life-source-coordination-v4"
    validate_work_record(record, changed, head_branch, head_sha, require_v2=require_v2)
    now = datetime.now(timezone.utc)
    claim_protocol = protocol if require_v2 else base_protocol
    for claim in record["claims"]:
        validate_live_lock(load_live_lock(claim), claim, record, head_sha, now, claim_protocol)


def validate_merge_group_event(event: dict, github_sha: str) -> None:
    group = event.get("merge_group")
    if not isinstance(group, dict):
        fail("merge_group payload missing")
    head_sha = str(group.get("head_sha") or "")
    if not SHA_RE.fullmatch(head_sha) or group.get("base_ref") != "refs/heads/main" or (github_sha and head_sha != github_sha):
        fail("merge_group identity mismatch")


def main() -> int:
    try:
        for path in (PROTOCOL_PATH, LOCK_SCHEMA_PATH, WORK_SCHEMA_PATH):
            if not path.is_file():
                fail(f"required coordination file missing: {path.relative_to(ROOT)}")
            canonical_json(path)
        protocol = load_json(PROTOCOL_PATH)
        validate_protocol(protocol)
        validate_schema_headers()
        event_name = os.environ.get("GITHUB_EVENT_NAME")
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if event_name in {"pull_request", "merge_group"}:
            if not event_path:
                fail("GITHUB_EVENT_PATH missing")
            event = json.loads(Path(event_path).read_text(encoding="utf-8"))
            if event_name == "pull_request":
                validate_pull_request_event(event, protocol)
            else:
                validate_merge_group_event(event, os.environ.get("GITHUB_SHA", ""))
    except (ValidationError, json.JSONDecodeError, fence.FenceError) as exc:
        print(f"COORDINATION_INVALID: {exc}", file=sys.stderr)
        return 1
    print("COORDINATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
