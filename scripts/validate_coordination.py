#!/usr/bin/env python3
from __future__ import annotations

import hashlib
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

UUID4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
COMPONENT_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
WORKER_KINDS = {"chatgpt", "claude", "grok", "codex", "human", "other_ai"}


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


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        fail(f"timestamp must be RFC3339 UTC ending Z: {value!r}")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        fail(f"invalid RFC3339 timestamp: {value!r}")


def expected_lock_branch(resource_key: str) -> str:
    return "lock/" + hashlib.sha256(resource_key.encode("utf-8")).hexdigest()


def validate_worker(worker: object) -> None:
    if not isinstance(worker, dict) or set(worker) != {"kind", "session_id"}:
        fail("worker must contain exactly kind and session_id")
    if worker["kind"] not in WORKER_KINDS:
        fail(f"unsupported worker kind: {worker['kind']!r}")
    if not UUID4_RE.fullmatch(str(worker["session_id"])):
        fail("worker.session_id must be lowercase UUIDv4")


def validate_acquisition_attempt_order(resource_keys: list[str]) -> None:
    if not isinstance(resource_keys, list) or not resource_keys:
        fail("acquisition attempt resource keys must be nonempty array")
    if any(not isinstance(key, str) or not key for key in resource_keys):
        fail("acquisition attempt resource keys must be nonempty strings")
    if len(resource_keys) != len(set(resource_keys)) or resource_keys != sorted(resource_keys):
        fail("each acquisition attempt must use unique RESOURCE_KEY_ASCENDING_UTF8 order")


def blocking_resource_keys(
    requested_resource_keys: list[str],
    live_locks: list[dict],
    requesting_work_id: str,
    now: datetime,
) -> list[str]:
    if not UUID4_RE.fullmatch(str(requesting_work_id)):
        fail("requesting_work_id must be lowercase UUIDv4")
    if not isinstance(requested_resource_keys, list) or len(requested_resource_keys) != len(set(requested_resource_keys)):
        fail("requested_resource_keys must be a unique array")
    if any(not isinstance(key, str) or not key for key in requested_resource_keys):
        fail("requested_resource_keys must contain nonempty strings")
    requested = set(requested_resource_keys)
    blockers: set[str] = set()
    for lock in live_locks:
        if not isinstance(lock, dict):
            fail("live lock evidence must be object")
        required = {"resource_key", "work_id", "state", "expires_at"}
        if not required <= set(lock):
            fail("live lock evidence missing resource_key/work_id/state/expires_at")
        key = lock["resource_key"]
        if key not in requested or lock["work_id"] == requesting_work_id:
            continue
        if lock["state"] == "ACTIVE" and now < parse_utc(lock["expires_at"]):
            blockers.add(key)
    return sorted(blockers)


def classify_operation_resource_sets(
    operation_resource_sets: dict[str, list[str]],
    live_locks: list[dict],
    requesting_work_id: str,
    now: datetime,
) -> dict[str, dict[str, object]]:
    if not isinstance(operation_resource_sets, dict) or not operation_resource_sets:
        fail("operation_resource_sets must be nonempty object")
    result = {}
    for operation_id in sorted(operation_resource_sets):
        if not isinstance(operation_id, str) or not operation_id:
            fail("operation id must be nonempty string")
        blockers = blocking_resource_keys(
            operation_resource_sets[operation_id], live_locks, requesting_work_id, now
        )
        result[operation_id] = {
            "intersection_state": "INTERSECTION_NONEMPTY" if blockers else "INTERSECTION_EMPTY",
            "blocking_resource_keys": blockers,
        }
    return result


def validate_protocol(protocol: dict) -> None:
    required = {
        "schema_version", "protocol_id", "runtime_control_authority", "source_coordination_authority",
        "canonical_repository", "default_branch", "work_branch_prefix", "lock_branch_prefix",
        "lock_branch_derivation", "lease_duration_seconds", "renew_when_remaining_seconds_lte",
        "expiration_rule", "lock_history_enforcement_start_utc", "resource_acquisition_order",
        "worker_kinds", "required_claims", "parallel_work", "mutation_rules", "integration_rules",
        "coordination_surfaces"
    }
    if set(protocol) != required:
        fail(f"protocol keys mismatch: missing={sorted(required-set(protocol))} extra={sorted(set(protocol)-required)}")
    exact = {
        "schema_version": 1,
        "protocol_id": "life-source-coordination-v3",
        "runtime_control_authority": "NONE",
        "source_coordination_authority": "GITHUB_MACHINE_STATE",
        "canonical_repository": "KINETIC-DESIGN-CO/Build",
        "default_branch": "main",
        "work_branch_prefix": "work/",
        "lock_branch_prefix": "lock/",
        "lock_branch_derivation": "lock/ + sha256(resource_key UTF-8 lowercase hex)",
        "lease_duration_seconds": 14400,
        "renew_when_remaining_seconds_lte": 1800,
        "expiration_rule": "EXPIRED_WHEN_UTC_NOW_GTE_EXPIRES_AT",
        "lock_history_enforcement_start_utc": "2026-09-12T22:56:23Z",
        "resource_acquisition_order": "PER_ACQUISITION_ATTEMPT_RESOURCE_KEY_ASCENDING_UTF8",
    }
    for key, value in exact.items():
        if protocol.get(key) != value:
            fail(f"protocol.{key} mismatch")
    if set(protocol["worker_kinds"]) != WORKER_KINDS or len(protocol["worker_kinds"]) != len(WORKER_KINDS):
        fail("protocol.worker_kinds mismatch")
    if protocol["required_claims"] != {
        "component": "component:<component_id>",
        "supabase_production": "external:supabase:jnenguxodtgwbskhdsxt",
    }:
        fail("protocol.required_claims mismatch")
    if protocol["parallel_work"] != {
        "blocking_claim_state": "ACTIVE",
        "unexpired_rule": "UTC_NOW_LT_EXPIRES_AT",
        "blocking_owner_rule": "CLAIM_WORK_ID_NE_REQUESTING_WORK_ID",
        "blocking_set_rule": "REQUESTED_RESOURCE_KEYS_INTERSECTION_OTHER_ACTIVE_UNEXPIRED_RESOURCE_KEYS",
        "empty_intersection_result": "INTERSECTION_EMPTY",
        "nonempty_intersection_result": "INTERSECTION_NONEMPTY",
        "main_integration_mode": "GITHUB_REQUIRED_MERGE_QUEUE",
        "continuity_fields_with_zero_claim_effect": ["current_component", "current_work", "next_action"],
        "repository_path_ownership_mode": "GIT_BRANCH_AND_MERGE_QUEUE_NOT_EXCLUSIVE_LEASE",
        "partial_execution_rule": "EVALUATE_EACH_OPERATION_USING_ITS_EXACT_REQUIRED_RESOURCE_SET_AND_LEAVE_INTERSECTING_OPERATIONS_UNEXECUTED",
        "work_record_base_rule": "BASE_SHA_IS_ACQUISITION_PROVENANCE_AND_MUST_BE_ANCESTOR_OF_PR_HEAD",
    }:
        fail("protocol.parallel_work mismatch")
    required_rules = {
        "ALL_RESOURCE_CLAIMS_IN_ONE_ACQUISITION_ATTEMPT_ARE_ACQUIRED_IN_RESOURCE_KEY_ASCENDING_UTF8_ORDER",
        "EXISTING_ACTIVE_CLAIMS_DO_NOT_PARTICIPATE_IN_LATER_ACQUISITION_ATTEMPT_ORDERING",
        "ACTIVE_UNEXPIRED_CLAIM_INTERSECTION_IS_THE_CROSS_WORK_ITEM_RESOURCE_BLOCKER",
        "CURRENT_COMPONENT_CURRENT_WORK_AND_NEXT_ACTION_HAVE_ZERO_SOURCE_CLAIM_EFFECT",
        "PULL_REQUEST_CREATION_AND_MAIN_INTEGRATION_DO_NOT_REQUIRE_INTEGRATION_MAIN_CLAIM",
        "PARTIAL_REQUEST_EXECUTION_EVALUATES_EACH_OPERATION_EXACT_RESOURCE_SET_AND_DOES_NOT_DROP_INTERSECTING_OPERATIONS",
        "REPOSITORY_PATHS_ARE_RECORDED_EXACTLY_IN_THE_WORK_RECORD_BUT_DO_NOT_REQUIRE_EXCLUSIVE_REPO_FILE_CLAIMS",
        "SOURCE_FILE_CONCURRENCY_IS_RESOLVED_BY_ISOLATED_WORK_BRANCHES_GIT_CONFLICT_DETECTION_REQUIRED_VALIDATE_AND_MERGE_GROUP_VALIDATION",
        "EVERY_DECLARED_EXTERNAL_TARGET_REQUIRES_ITS_EXACT_EXTERNAL_RESOURCE_CLAIM",
        "LOCK_TRANSITION_ENFORCEMENT_APPLIES_FROM_PROTOCOL_LOCK_HISTORY_ENFORCEMENT_START_UTC",
        "LOCK_HISTORY_VALIDATION_MUST_PROVE_LEGAL_DURATION_RENEWAL_RELEASE_REACQUISITION_AND_TAKEOVER_TRANSITIONS",
        "MAIN_INTEGRATION_REQUIRES_GITHUB_MERGE_QUEUE",
        "MERGE_GROUP_VALIDATE_IS_LATEST_BASE_INTEGRATION_GATE",
    }
    rules = protocol["mutation_rules"]
    if any(rules.count(rule) != 1 for rule in required_rules):
        fail("protocol merge-queue/parallel mutation rules mismatch")
    forbidden = {
        "EVERY_PR_TO_MAIN_REQUIRES_AN_ACTIVE_INTEGRATION_MAIN_CLAIM",
        "INTEGRATION_MAIN_CLAIM_CONFLICT_BLOCKS_PR_CREATION_AND_MAIN_INTEGRATION_NOT_WORK_BRANCH_IMPLEMENTATION",
        "EVERY_CHANGED_REPOSITORY_PATH_EXCEPT_THE_WORK_RECORD_REQUIRES_AN_EXACT_REPO_FILE_CLAIM",
    }
    if any(rule in rules for rule in forbidden):
        fail("obsolete integration/file-lease mutation rule remains")
    expected_integration = [
        "REQUIRED_VALIDATE_CHECK_MUST_PASS_ON_PR_HEAD",
        "MAIN_RULESET_MUST_REQUIRE_MERGE_QUEUE",
        "MERGE_GROUP_VALIDATE_MUST_PASS_BEFORE_MAIN_INTEGRATION",
        "PR_HEAD_NEED_NOT_CONTAIN_CURRENT_MAIN_AS_ANCESTOR_FOR_PULL_REQUEST_VALIDATION",
        "WORK_RECORD_BASE_SHA_MUST_BE_ANCESTOR_OF_PR_HEAD",
    ]
    if protocol["integration_rules"] != expected_integration:
        fail("protocol.integration_rules mismatch")


def validate_schema_headers() -> None:
    for path in (LOCK_SCHEMA_PATH, WORK_SCHEMA_PATH):
        obj = load_json(path)
        if obj.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            fail(f"{path.relative_to(ROOT)} must use JSON Schema draft 2020-12")
        if obj.get("additionalProperties") is not False:
            fail(f"{path.relative_to(ROOT)} must forbid root additionalProperties")


def validate_claim_shape(claim: object) -> None:
    if not isinstance(claim, dict) or set(claim) != {"resource_key", "lock_branch", "lease_id", "generation"}:
        fail("each work-record claim must contain exactly resource_key, lock_branch, lease_id, generation")
    if not isinstance(claim["resource_key"], str) or not claim["resource_key"]:
        fail("claim.resource_key must be nonempty string")
    if claim["lock_branch"] != expected_lock_branch(claim["resource_key"]):
        fail(f"claim lock branch mismatch for {claim['resource_key']}")
    if not UUID4_RE.fullmatch(str(claim["lease_id"])):
        fail("claim.lease_id must be lowercase UUIDv4")
    if not isinstance(claim["generation"], int) or claim["generation"] < 1:
        fail("claim.generation must be integer >= 1")


def required_claim_keys(record: dict) -> set[str]:
    mandatory = {f"component:{record['component_id']}"}
    external = set(record["external_targets"])
    mandatory |= external
    if any(str(target).startswith("external:supabase:") for target in external):
        mandatory.add("external:supabase:jnenguxodtgwbskhdsxt")
    return mandatory


def validate_work_record(record: dict, changed_files: list[str], head_branch: str, head_sha: str) -> None:
    required = {"schema_version", "work_id", "title", "worker", "implementation_branch", "base_sha", "component_id", "repo_paths", "external_targets", "claims", "runtime_control_authority"}
    if set(record) != required:
        fail("work record keys mismatch")
    if record["schema_version"] != 1 or record["runtime_control_authority"] != "NONE":
        fail("work record schema_version/authority mismatch")
    work_id = str(record["work_id"])
    if not UUID4_RE.fullmatch(work_id):
        fail("work_id must be lowercase UUIDv4")
    validate_worker(record["worker"])
    expected_branch = f"work/{work_id}"
    if record["implementation_branch"] != expected_branch or head_branch != expected_branch:
        fail(f"implementation branch must be exactly {expected_branch}")
    if not SHA_RE.fullmatch(str(record["base_sha"])):
        fail("work record base_sha must be 40-lowercase-hex SHA")
    if subprocess.run(["git", "merge-base", "--is-ancestor", record["base_sha"], head_sha], cwd=ROOT).returncode != 0:
        fail("work record base_sha must be an ancestor of PR head")
    if not COMPONENT_RE.fullmatch(str(record["component_id"])):
        fail("component_id must be snake_case [a-z0-9_]")
    if not isinstance(record["title"], str) or not (1 <= len(record["title"]) <= 160):
        fail("title length must be 1..160")
    repo_paths = record["repo_paths"]
    if not isinstance(repo_paths, list) or not repo_paths or len(repo_paths) != len(set(repo_paths)) or repo_paths != sorted(repo_paths):
        fail("repo_paths must be nonempty, unique, sorted array")
    external = record["external_targets"]
    if not isinstance(external, list) or len(external) != len(set(external)) or external != sorted(external):
        fail("external_targets must be unique, sorted array")
    claims = record["claims"]
    if not isinstance(claims, list) or not claims:
        fail("claims must be nonempty array")
    for claim in claims:
        validate_claim_shape(claim)
    keys = [claim["resource_key"] for claim in claims]
    if len(keys) != len(set(keys)) or keys != sorted(keys):
        fail("claims must be unique and sorted by resource_key")
    missing = required_claim_keys(record) - set(keys)
    if missing:
        fail(f"work record missing mandatory claims: {sorted(missing)}")
    if "integration:main" in keys:
        fail("work record must not use obsolete integration:main claim")
    work_record_path = f"coordination/work/{work_id}.json"
    expected_changed = sorted(path for path in changed_files if path != work_record_path)
    if repo_paths != expected_changed:
        fail(f"repo_paths must exactly cover changed paths except work record; expected {expected_changed}")


def load_live_lock(claim: dict) -> dict:
    branch = claim["lock_branch"]
    remote_ref = f"refs/remotes/origin/{branch}"
    fetch = subprocess.run(
        ["git", "fetch", "--quiet", "origin", f"refs/heads/{branch}:{remote_ref}"],
        cwd=ROOT, text=True, capture_output=True
    )
    if fetch.returncode != 0:
        fail(f"missing live lock branch {branch}")
    raw = git("show", f"{remote_ref}:coordination/lock.json")
    try:
        return json.loads(raw)
    except Exception as exc:
        fail(f"invalid coordination/lock.json on {branch}: {exc}")


def validate_live_lock(
    lock: dict,
    claim: dict,
    record: dict,
    now: datetime,
    protocol: dict,
    head_sha: str,
) -> None:
    required = {"schema_version", "resource_key", "generation", "state", "work_id", "worker", "implementation_branch", "lease_id", "base_sha", "acquired_at", "heartbeat_at", "expires_at", "runtime_control_authority"}
    if set(lock) != required:
        fail(f"live lock keys mismatch for {claim['resource_key']}")
    if lock["schema_version"] != 1 or lock["runtime_control_authority"] != "NONE" or lock["state"] != "ACTIVE":
        fail(f"live lock is not ACTIVE schema v1 with NONE runtime authority: {claim['resource_key']}")
    validate_worker(lock["worker"])
    exact_pairs = {
        "resource_key": claim["resource_key"],
        "generation": claim["generation"],
        "work_id": record["work_id"],
        "worker": record["worker"],
        "implementation_branch": record["implementation_branch"],
        "lease_id": claim["lease_id"],
    }
    for key, value in exact_pairs.items():
        if lock[key] != value:
            fail(f"live lock {claim['resource_key']} mismatch at {key}")
    if not SHA_RE.fullmatch(str(lock["base_sha"])):
        fail(f"live lock base_sha invalid: {claim['resource_key']}")
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", lock["base_sha"], head_sha],
        cwd=ROOT,
    ).returncode != 0:
        fail(f"live lock base_sha must be an ancestor of PR head: {claim['resource_key']}")
    acquired = parse_utc(lock["acquired_at"])
    heartbeat = parse_utc(lock["heartbeat_at"])
    expires = parse_utc(lock["expires_at"])
    if not (acquired <= heartbeat < expires):
        fail(f"live lock timestamp ordering invalid: {claim['resource_key']}")
    duration = int((expires - heartbeat).total_seconds())
    if duration != protocol["lease_duration_seconds"]:
        fail(f"live lock duration mismatch: {claim['resource_key']}")
    if now >= expires:
        fail(f"live lock expired: {claim['resource_key']}")


def validate_pull_request_event(event: dict, protocol: dict) -> None:
    pr = event.get("pull_request") or {}
    base_sha = str((pr.get("base") or {}).get("sha") or "")
    head_sha = str((pr.get("head") or {}).get("sha") or "")
    head_branch = str((pr.get("head") or {}).get("ref") or "")
    if not SHA_RE.fullmatch(base_sha) or not SHA_RE.fullmatch(head_sha):
        fail("pull_request base/head SHA missing or invalid")
    base_has_protocol = subprocess.run(
        ["git", "cat-file", "-e", f"{base_sha}:coordination/protocol.json"],
        cwd=ROOT, capture_output=True
    ).returncode == 0
    if not base_has_protocol:
        if not PROTOCOL_PATH.is_file():
            fail("coordination bootstrap PR must add coordination/protocol.json")
        return
    changed = [p for p in git("diff", "--name-only", f"{base_sha}...{head_sha}").splitlines() if p]
    work_paths = [p for p in changed if re.fullmatch(r"coordination/work/[0-9a-f-]{36}\.json", p)]
    if len(work_paths) != 1:
        fail("every post-bootstrap PR must change exactly one coordination/work/<work_id>.json")
    record = load_json(ROOT / work_paths[0])
    validate_work_record(record, changed, head_branch, head_sha)
    if work_paths[0] != f"coordination/work/{record['work_id']}.json":
        fail("work record path/work_id mismatch")
    now = datetime.now(timezone.utc)
    for claim in record["claims"]:
        validate_live_lock(load_live_lock(claim), claim, record, now, protocol, head_sha)


def validate_merge_group_event(event: dict, github_sha: str) -> None:
    group = event.get("merge_group")
    if not isinstance(group, dict):
        fail("merge_group payload missing")
    head_sha = str(group.get("head_sha") or "")
    base_ref = str(group.get("base_ref") or "")
    if not SHA_RE.fullmatch(head_sha):
        fail("merge_group head_sha missing or invalid")
    if base_ref != "refs/heads/main":
        fail("merge_group base_ref must be refs/heads/main")
    if github_sha and head_sha != github_sha:
        fail("merge_group head_sha must equal GITHUB_SHA")


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
    except ValidationError as exc:
        print(f"COORDINATION_INVALID: {exc}", file=sys.stderr)
        return 1
    print("COORDINATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
