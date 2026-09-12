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
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        fail(f"invalid RFC3339 timestamp: {value!r}")
    return parsed


def expected_lock_branch(resource_key: str) -> str:
    digest = hashlib.sha256(resource_key.encode("utf-8")).hexdigest()
    return f"lock/{digest}"


def validate_worker(worker: object) -> None:
    if not isinstance(worker, dict) or set(worker) != {"kind", "session_id"}:
        fail("worker must contain exactly kind and session_id")
    if worker["kind"] not in WORKER_KINDS:
        fail(f"unsupported worker kind: {worker['kind']!r}")
    if not UUID4_RE.fullmatch(str(worker["session_id"])):
        fail("worker.session_id must be lowercase UUIDv4")


def validate_protocol(protocol: dict) -> None:
    required = {
        "schema_version", "protocol_id", "runtime_control_authority", "source_coordination_authority",
        "canonical_repository", "default_branch", "work_branch_prefix", "lock_branch_prefix",
        "lock_branch_derivation", "lease_duration_seconds", "renew_when_remaining_seconds_lte",
        "expiration_rule", "resource_acquisition_order", "worker_kinds", "required_claims",
        "mutation_rules", "integration_rules", "coordination_surfaces"
    }
    if set(protocol) != required:
        fail(f"protocol keys mismatch: missing={sorted(required-set(protocol))} extra={sorted(set(protocol)-required)}")
    exact = {
        "schema_version": 1,
        "protocol_id": "life-source-coordination-v1",
        "runtime_control_authority": "NONE",
        "source_coordination_authority": "GITHUB_MACHINE_STATE",
        "canonical_repository": "Vinanonymous/Build",
        "default_branch": "main",
        "work_branch_prefix": "work/",
        "lock_branch_prefix": "lock/",
        "lock_branch_derivation": "lock/ + sha256(resource_key UTF-8 lowercase hex)",
        "lease_duration_seconds": 14400,
        "renew_when_remaining_seconds_lte": 1800,
        "expiration_rule": "EXPIRED_WHEN_UTC_NOW_GTE_EXPIRES_AT",
        "resource_acquisition_order": "RESOURCE_KEY_ASCENDING_UTF8"
    }
    for key, value in exact.items():
        if protocol.get(key) != value:
            fail(f"protocol.{key} mismatch")
    if set(protocol["worker_kinds"]) != WORKER_KINDS or len(protocol["worker_kinds"]) != len(WORKER_KINDS):
        fail("protocol.worker_kinds mismatch")
    required_claims = protocol["required_claims"]
    if required_claims != {
        "component": "component:<component_id>",
        "repository_file": "repo-file:<exact_repo_path>",
        "main_integration": "integration:main",
        "supabase_production": "external:supabase:jnenguxodtgwbskhdsxt"
    }:
        fail("protocol.required_claims mismatch")


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


def validate_work_record(record: dict, changed_files: list[str], head_branch: str, current_main: str) -> None:
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
    if not SHA_RE.fullmatch(str(record["base_sha"])) or record["base_sha"] != current_main:
        fail("work record base_sha must equal current origin/main")
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
    mandatory = {f"component:{record['component_id']}", "integration:main"}
    mandatory |= {f"repo-file:{path}" for path in repo_paths}
    mandatory |= set(external)
    if any(str(t).startswith("external:supabase:") for t in external):
        mandatory.add("external:supabase:jnenguxodtgwbskhdsxt")
    missing = mandatory - set(keys)
    if missing:
        fail(f"work record missing mandatory claims: {sorted(missing)}")
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


def validate_live_lock(lock: dict, claim: dict, record: dict, now: datetime) -> None:
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
        "base_sha": record["base_sha"]
    }
    for key, value in exact_pairs.items():
        if lock[key] != value:
            fail(f"live lock {claim['resource_key']} mismatch at {key}")
    acquired = parse_utc(lock["acquired_at"])
    heartbeat = parse_utc(lock["heartbeat_at"])
    expires = parse_utc(lock["expires_at"])
    if not (acquired <= heartbeat < expires):
        fail(f"live lock timestamp ordering invalid: {claim['resource_key']}")
    if now >= expires:
        fail(f"live lock expired: {claim['resource_key']}")


def validate_pull_request(protocol: dict) -> None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        fail("GITHUB_EVENT_PATH missing for pull_request validation")
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
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

    git("fetch", "--quiet", "origin", "main")
    current_main = git("rev-parse", "origin/main")
    if subprocess.run(["git", "merge-base", "--is-ancestor", current_main, head_sha], cwd=ROOT).returncode != 0:
        fail("PR head does not contain current main as an ancestor; update/rebase before integration")

    changed = [p for p in git("diff", "--name-only", f"{base_sha}...{head_sha}").splitlines() if p]
    work_paths = [p for p in changed if re.fullmatch(r"coordination/work/[0-9a-f-]{36}\.json", p)]
    if len(work_paths) != 1:
        fail("every post-bootstrap PR must change exactly one coordination/work/<work_id>.json")
    record = load_json(ROOT / work_paths[0])
    validate_work_record(record, changed, head_branch, current_main)
    if work_paths[0] != f"coordination/work/{record['work_id']}.json":
        fail("work record path/work_id mismatch")
    now = datetime.now(timezone.utc)
    for claim in record["claims"]:
        validate_live_lock(load_live_lock(claim), claim, record, now)


def main() -> int:
    try:
        for path in (PROTOCOL_PATH, LOCK_SCHEMA_PATH, WORK_SCHEMA_PATH):
            if not path.is_file():
                fail(f"required coordination file missing: {path.relative_to(ROOT)}")
            canonical_json(path)
        protocol = load_json(PROTOCOL_PATH)
        validate_protocol(protocol)
        validate_schema_headers()
        if os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
            validate_pull_request(protocol)
    except ValidationError as exc:
        print(f"COORDINATION_INVALID: {exc}", file=sys.stderr)
        return 1
    print("COORDINATION_VALID")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
