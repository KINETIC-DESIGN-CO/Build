#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "coordination" / "protocol.json"
LOCK_PATH = "coordination/lock.json"
UUID4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
WORK_BRANCH_RE = re.compile(r"^work/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
LOCK_KEYS = {
    "schema_version", "resource_key", "generation", "state", "work_id", "worker",
    "implementation_branch", "lease_id", "base_sha", "acquired_at", "heartbeat_at",
    "expires_at", "runtime_control_authority",
}
WORKER_KINDS = {"chatgpt", "claude", "grok", "codex", "human", "other_ai"}
REQUIRED_TRANSITION_RULES = {
    "ACTIVE_LEASE_WINDOW_EQUALS_LEASE_DURATION_SECONDS_FROM_HEARTBEAT_AT_TO_EXPIRES_AT",
    "INITIAL_ACQUISITION_REQUIRES_GENERATION_ONE_AND_ACQUIRED_AT_EQUALS_HEARTBEAT_AT",
    "LEASE_RENEWAL_REQUIRES_ACTIVE_PREDECESSOR_SAME_OWNER_IDENTITY_SAME_ACQUIRED_AT_STRICTLY_LATER_HEARTBEAT_AND_REMAINING_SECONDS_LTE_RENEW_THRESHOLD",
    "LEASE_TAKEOVER_REQUIRES_EXPIRED_ACTIVE_PREDECESSOR_GENERATION_PLUS_ONE_NEW_WORK_ID_NEW_LEASE_ID_AND_ACQUIRED_AT_EQUALS_HEARTBEAT_AT",
    "LEASE_REACQUISITION_REQUIRES_RELEASED_PREDECESSOR_GENERATION_PLUS_ONE_NEW_WORK_ID_NEW_LEASE_ID_AND_ACQUIRED_AT_EQUALS_HEARTBEAT_AT",
    "RELEASE_CHANGES_ONLY_STATE_FROM_ACTIVE_TO_RELEASED",
}


class LockHistoryError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise LockHistoryError(message)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON {path}: {exc}")


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        fail(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        fail(f"timestamp must be RFC3339 UTC ending Z: {value!r}")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        fail(f"invalid RFC3339 timestamp: {value!r}")


def validate_protocol_contract(protocol: dict) -> tuple[int, int]:
    duration = protocol.get("lease_duration_seconds")
    renew_threshold = protocol.get("renew_when_remaining_seconds_lte")
    if not isinstance(duration, int) or duration <= 0:
        fail("protocol.lease_duration_seconds must be a positive integer")
    if not isinstance(renew_threshold, int) or not (0 <= renew_threshold < duration):
        fail("protocol.renew_when_remaining_seconds_lte must be integer in [0, lease_duration_seconds)")
    rules = protocol.get("mutation_rules")
    if not isinstance(rules, list):
        fail("protocol.mutation_rules must be an array")
    missing = sorted(rule for rule in REQUIRED_TRANSITION_RULES if rules.count(rule) != 1)
    if missing:
        fail(f"protocol executable lease-transition rules mismatch: {missing}")
    return duration, renew_threshold


def validate_worker(worker: object) -> None:
    if not isinstance(worker, dict) or set(worker) != {"kind", "session_id"}:
        fail("worker must contain exactly kind and session_id")
    if worker["kind"] not in WORKER_KINDS:
        fail(f"unsupported worker kind: {worker['kind']!r}")
    if not UUID4_RE.fullmatch(str(worker["session_id"])):
        fail("worker.session_id must be lowercase UUIDv4")


def validate_snapshot(lock: dict, duration_seconds: int) -> None:
    if not isinstance(lock, dict) or set(lock) != LOCK_KEYS:
        fail("lock snapshot keys mismatch")
    if lock["schema_version"] != 1 or lock["runtime_control_authority"] != "NONE":
        fail("lock snapshot schema_version/authority mismatch")
    if not isinstance(lock["resource_key"], str) or not lock["resource_key"]:
        fail("resource_key must be nonempty string")
    if lock["state"] not in {"ACTIVE", "RELEASED"}:
        fail("lock state must be ACTIVE or RELEASED")
    if not isinstance(lock["generation"], int) or lock["generation"] < 1:
        fail("generation must be integer >= 1")
    if not UUID4_RE.fullmatch(str(lock["work_id"])):
        fail("work_id must be lowercase UUIDv4")
    validate_worker(lock["worker"])
    if lock["implementation_branch"] != f"work/{lock['work_id']}" or not WORK_BRANCH_RE.fullmatch(str(lock["implementation_branch"])):
        fail("implementation_branch must be work/<work_id>")
    if not UUID4_RE.fullmatch(str(lock["lease_id"])):
        fail("lease_id must be lowercase UUIDv4")
    if not SHA_RE.fullmatch(str(lock["base_sha"])):
        fail("base_sha must be lowercase 40-hex SHA")
    acquired = parse_utc(lock["acquired_at"])
    heartbeat = parse_utc(lock["heartbeat_at"])
    expires = parse_utc(lock["expires_at"])
    if not (acquired <= heartbeat < expires):
        fail("lock timestamp ordering must satisfy acquired_at <= heartbeat_at < expires_at")
    if int((expires - heartbeat).total_seconds()) != duration_seconds:
        fail("expires_at - heartbeat_at must equal protocol.lease_duration_seconds exactly")


def _preserved(prev: dict, curr: dict, fields: set[str], transition: str) -> None:
    changed = sorted(field for field in fields if prev[field] != curr[field])
    if changed:
        fail(f"{transition} changed preserved fields: {changed}")


def validate_transition(prev: dict, curr: dict, duration_seconds: int, renew_threshold_seconds: int) -> None:
    validate_snapshot(prev, duration_seconds)
    validate_snapshot(curr, duration_seconds)
    if curr["resource_key"] != prev["resource_key"]:
        fail("resource_key may never change within one lock branch")

    if prev["state"] == "ACTIVE" and curr["state"] == "RELEASED":
        _preserved(prev, curr, LOCK_KEYS - {"state"}, "release")
        return

    if prev["state"] == "RELEASED" and curr["state"] == "ACTIVE":
        if curr["generation"] != prev["generation"] + 1:
            fail("reacquisition must increment generation by exactly one")
        if curr["work_id"] == prev["work_id"]:
            fail("reacquisition must use a new work_id")
        if curr["lease_id"] == prev["lease_id"]:
            fail("reacquisition must use a new lease_id")
        if curr["acquired_at"] != curr["heartbeat_at"]:
            fail("reacquisition requires acquired_at == heartbeat_at")
        return

    if prev["state"] == "ACTIVE" and curr["state"] == "ACTIVE":
        if curr["generation"] == prev["generation"]:
            preserved = {
                "schema_version", "resource_key", "generation", "work_id", "worker",
                "implementation_branch", "lease_id", "base_sha", "acquired_at",
                "runtime_control_authority",
            }
            _preserved(prev, curr, preserved, "renewal")
            prev_heartbeat = parse_utc(prev["heartbeat_at"])
            prev_expires = parse_utc(prev["expires_at"])
            curr_heartbeat = parse_utc(curr["heartbeat_at"])
            if not (prev_heartbeat < curr_heartbeat < prev_expires):
                fail("renewal heartbeat must be strictly later and before predecessor expiry")
            remaining = int((prev_expires - curr_heartbeat).total_seconds())
            if remaining > renew_threshold_seconds:
                fail("renewal occurred before configured renewal window")
            if parse_utc(curr["expires_at"]) <= prev_expires:
                fail("renewal must strictly extend expires_at")
            return
        if curr["generation"] == prev["generation"] + 1:
            if parse_utc(curr["acquired_at"]) < parse_utc(prev["expires_at"]):
                fail("takeover requires predecessor lease to be expired")
            if curr["work_id"] == prev["work_id"]:
                fail("takeover must use a new work_id")
            if curr["lease_id"] == prev["lease_id"]:
                fail("takeover must use a new lease_id")
            if curr["acquired_at"] != curr["heartbeat_at"]:
                fail("takeover requires acquired_at == heartbeat_at")
            return
        fail("ACTIVE to ACTIVE transition must be renewal or generation+1 takeover")

    fail(f"illegal lock transition {prev['state']}->{curr['state']}")


def validate_history(history: list[dict], duration_seconds: int, renew_threshold_seconds: int) -> None:
    if not isinstance(history, list) or not history:
        fail("lock history must contain at least one snapshot")
    first = history[0]
    validate_snapshot(first, duration_seconds)
    if first["state"] != "ACTIVE" or first["generation"] != 1:
        fail("first lock snapshot must be ACTIVE generation 1")
    if first["acquired_at"] != first["heartbeat_at"]:
        fail("initial acquisition requires acquired_at == heartbeat_at")
    for prev, curr in zip(history, history[1:]):
        validate_transition(prev, curr, duration_seconds, renew_threshold_seconds)


def load_remote_history(lock_branch: str) -> list[dict]:
    if not re.fullmatch(r"lock/[0-9a-f]{64}", lock_branch):
        fail(f"invalid lock branch: {lock_branch!r}")
    remote_ref = f"refs/remotes/origin/{lock_branch}"
    proc = subprocess.run(
        ["git", "fetch", "--quiet", "origin", f"refs/heads/{lock_branch}:{remote_ref}"],
        cwd=ROOT, text=True, capture_output=True,
    )
    if proc.returncode != 0:
        fail(f"missing live lock branch {lock_branch}")
    commits = [c for c in git("rev-list", "--reverse", remote_ref, "--", LOCK_PATH).splitlines() if c]
    if not commits:
        fail(f"lock branch {lock_branch} has no {LOCK_PATH} history")
    history = []
    for commit in commits:
        raw = git("show", f"{commit}:{LOCK_PATH}")
        try:
            history.append(json.loads(raw))
        except Exception as exc:
            fail(f"invalid {LOCK_PATH} at {commit}: {exc}")
    return history


def validate_pull_request_claim_histories(protocol: dict) -> None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        fail("GITHUB_EVENT_PATH missing for pull_request lock-history validation")
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    pr = event.get("pull_request") or {}
    base_sha = str((pr.get("base") or {}).get("sha") or "")
    head_sha = str((pr.get("head") or {}).get("sha") or "")
    if not SHA_RE.fullmatch(base_sha) or not SHA_RE.fullmatch(head_sha):
        fail("pull_request base/head SHA missing or invalid")
    changed = [p for p in git("diff", "--name-only", f"{base_sha}...{head_sha}").splitlines() if p]
    work_paths = [p for p in changed if re.fullmatch(r"coordination/work/[0-9a-f-]{36}\.json", p)]
    if len(work_paths) != 1:
        fail("every post-bootstrap PR must change exactly one coordination/work/<work_id>.json")
    record = load_json(ROOT / work_paths[0])
    claims = record.get("claims")
    if not isinstance(claims, list) or not claims:
        fail("work record claims must be nonempty array")
    duration, renew_threshold = validate_protocol_contract(protocol)
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get("lock_branch"), str):
            fail("work record claim missing lock_branch")
        history = load_remote_history(claim["lock_branch"])
        validate_history(history, duration, renew_threshold)
        live = history[-1]
        if live["resource_key"] != claim.get("resource_key"):
            fail("live lock history resource_key does not match work-record claim")
        if live["generation"] != claim.get("generation") or live["lease_id"] != claim.get("lease_id"):
            fail("live lock history tail identity does not match work-record claim")


def main() -> int:
    try:
        protocol = load_json(PROTOCOL_PATH)
        validate_protocol_contract(protocol)
        if os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
            validate_pull_request_claim_histories(protocol)
    except LockHistoryError as exc:
        print(f"LOCK_HISTORY_INVALID: {exc}", file=sys.stderr)
        return 1
    print("LOCK_HISTORY_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
