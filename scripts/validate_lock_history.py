#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "coordination" / "protocol.json"

UUID4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
LOCK_BRANCH_RE = re.compile(r"^refs/heads/(lock/[0-9a-f]{64})$")
LOCK_KEYS = {
    "schema_version", "resource_key", "generation", "state", "work_id", "worker",
    "implementation_branch", "lease_id", "base_sha", "acquired_at", "heartbeat_at",
    "expires_at", "runtime_control_authority",
}
SUPPORTED_PROTOCOL_IDS = {
    "life-source-coordination-v2",
    "life-source-coordination-v3",
}


class ValidationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ValidationError(message)


def run_git(*args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if check and proc.returncode != 0:
        fail(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        fail(f"timestamp must be RFC3339 UTC ending Z: {value!r}")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        fail(f"invalid timestamp: {value!r}")


def parse_git_time(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        fail("git commit timestamp missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail(f"invalid git commit timestamp: {value!r}")
    if parsed.tzinfo is None:
        fail("git commit timestamp must be timezone-aware")
    return parsed


def validate_worker(worker: object) -> None:
    if not isinstance(worker, dict) or set(worker) != {"kind", "session_id"}:
        fail("worker must contain exactly kind and session_id")
    if not UUID4_RE.fullmatch(str(worker["session_id"])):
        fail("worker.session_id must be lowercase UUIDv4")
    if worker["kind"] not in {"chatgpt", "claude", "grok", "codex", "human", "other_ai"}:
        fail("worker.kind invalid")


def validate_legacy_snapshot(lock: dict) -> None:
    if not isinstance(lock, dict) or set(lock) != LOCK_KEYS:
        fail("legacy lock snapshot keys mismatch")
    if lock["schema_version"] != 1 or lock["runtime_control_authority"] != "NONE":
        fail("legacy lock snapshot schema/authority mismatch")
    if lock["state"] not in {"ACTIVE", "RELEASED"}:
        fail("legacy lock state invalid")
    if not isinstance(lock["resource_key"], str) or not lock["resource_key"]:
        fail("legacy resource_key must be nonempty")
    if not isinstance(lock["generation"], int) or lock["generation"] < 1:
        fail("legacy generation must be integer >= 1")
    if not isinstance(lock["work_id"], str) or not lock["work_id"]:
        fail("legacy work_id must be nonempty string")
    if not isinstance(lock["lease_id"], str) or not lock["lease_id"]:
        fail("legacy lease_id must be nonempty string")
    worker = lock["worker"]
    if not isinstance(worker, dict) or set(worker) != {"kind", "session_id"}:
        fail("legacy worker must contain exactly kind and session_id")
    if not isinstance(worker["kind"], str) or not worker["kind"]:
        fail("legacy worker.kind must be nonempty string")
    if not isinstance(worker["session_id"], str) or not worker["session_id"]:
        fail("legacy worker.session_id must be nonempty string")
    if not isinstance(lock["implementation_branch"], str) or not lock["implementation_branch"]:
        fail("legacy implementation_branch must be nonempty string")
    if not SHA_RE.fullmatch(str(lock["base_sha"])):
        fail("legacy base_sha invalid")
    acquired = parse_utc(lock["acquired_at"])
    heartbeat = parse_utc(lock["heartbeat_at"])
    expires = parse_utc(lock["expires_at"])
    if not (acquired <= heartbeat < expires):
        fail("legacy lock timestamp ordering invalid")


def validate_snapshot_shape(lock: dict) -> None:
    if not isinstance(lock, dict) or set(lock) != LOCK_KEYS:
        fail("lock snapshot keys mismatch")
    if lock["schema_version"] != 1 or lock["runtime_control_authority"] != "NONE":
        fail("lock snapshot schema/authority mismatch")
    if lock["state"] not in {"ACTIVE", "RELEASED"}:
        fail("lock state invalid")
    if not isinstance(lock["resource_key"], str) or not lock["resource_key"]:
        fail("resource_key must be nonempty")
    if not isinstance(lock["generation"], int) or lock["generation"] < 1:
        fail("generation must be integer >= 1")
    if not UUID4_RE.fullmatch(str(lock["work_id"])) or not UUID4_RE.fullmatch(str(lock["lease_id"])):
        fail("work_id/lease_id must be lowercase UUIDv4")
    validate_worker(lock["worker"])
    if lock["implementation_branch"] != f"work/{lock['work_id']}":
        fail("implementation_branch must match work_id")
    if not SHA_RE.fullmatch(str(lock["base_sha"])):
        fail("base_sha invalid")
    acquired = parse_utc(lock["acquired_at"])
    heartbeat = parse_utc(lock["heartbeat_at"])
    expires = parse_utc(lock["expires_at"])
    if not (acquired <= heartbeat < expires):
        fail("lock timestamp ordering invalid")


def validate_snapshot(lock: dict, protocol: dict) -> None:
    validate_snapshot_shape(lock)
    heartbeat = parse_utc(lock["heartbeat_at"])
    expires = parse_utc(lock["expires_at"])
    if int((expires - heartbeat).total_seconds()) != protocol["lease_duration_seconds"]:
        fail("lock lease duration must equal protocol.lease_duration_seconds")


def immutable_release_fields(lock: dict) -> tuple:
    return (
        lock["resource_key"], lock["generation"], lock["work_id"], lock["worker"],
        lock["implementation_branch"], lock["lease_id"], lock["base_sha"], lock["acquired_at"],
        lock["heartbeat_at"], lock["expires_at"], lock["runtime_control_authority"],
    )


def validate_transition_semantics(previous: dict, current: dict, protocol: dict) -> None:
    if previous["resource_key"] != current["resource_key"]:
        fail("resource_key cannot change within lock history")

    prev_state = previous["state"]
    curr_state = current["state"]
    prev_heartbeat = parse_utc(previous["heartbeat_at"])
    prev_expires = parse_utc(previous["expires_at"])
    curr_acquired = parse_utc(current["acquired_at"])
    curr_heartbeat = parse_utc(current["heartbeat_at"])

    if prev_state == "ACTIVE" and curr_state == "RELEASED":
        if immutable_release_fields(previous) != immutable_release_fields(current):
            fail("release must preserve prior owner and timestamps")
        return

    if prev_state == "RELEASED" and curr_state == "ACTIVE":
        if current["generation"] != previous["generation"] + 1:
            fail("released reacquisition must increment generation by exactly one")
        if current["lease_id"] == previous["lease_id"]:
            fail("released reacquisition must use a new lease_id")
        if curr_acquired != curr_heartbeat:
            fail("released reacquisition must start with acquired_at == heartbeat_at")
        if curr_acquired < prev_heartbeat:
            fail("released reacquisition cannot predate predecessor heartbeat")
        return

    if prev_state == "ACTIVE" and curr_state == "ACTIVE":
        same_owner = (
            current["work_id"] == previous["work_id"]
            and current["lease_id"] == previous["lease_id"]
            and current["generation"] == previous["generation"]
        )
        if same_owner:
            fixed_fields = ("worker", "implementation_branch", "base_sha", "acquired_at")
            if any(current[field] != previous[field] for field in fixed_fields):
                fail("renewal changed immutable ownership field")
            if curr_heartbeat <= prev_heartbeat:
                fail("renewal heartbeat must advance")
            remaining = int((prev_expires - curr_heartbeat).total_seconds())
            if remaining < 0:
                fail("renewal cannot occur after predecessor expiry")
            if remaining > protocol["renew_when_remaining_seconds_lte"]:
                fail("renewal occurred before configured renewal window")
            return

        if curr_acquired < prev_expires:
            fail("takeover cannot occur before predecessor expiry")
        if current["generation"] != previous["generation"] + 1:
            fail("takeover must increment generation by exactly one")
        if current["lease_id"] == previous["lease_id"]:
            fail("takeover must use a new lease_id")
        if curr_acquired != curr_heartbeat:
            fail("takeover must start with acquired_at == heartbeat_at")
        return

    fail(f"illegal lock transition {prev_state}->{curr_state}")


def validate_transition(previous: dict, current: dict, protocol: dict) -> None:
    validate_snapshot(previous, protocol)
    validate_snapshot(current, protocol)
    validate_transition_semantics(previous, current, protocol)


def validate_history(history: list[dict], protocol: dict) -> None:
    if not history:
        fail("lock history must contain at least one snapshot")
    first = history[0]
    validate_snapshot(first, protocol)
    if first["state"] != "ACTIVE" or first["generation"] != 1:
        fail("initial lock snapshot must be ACTIVE generation 1")
    if first["acquired_at"] != first["heartbeat_at"]:
        fail("initial lock snapshot must have acquired_at == heartbeat_at")
    for index, (previous, current) in enumerate(zip(history, history[1:]), start=1):
        try:
            validate_transition(previous, current, protocol)
        except ValidationError as exc:
            fail(f"transition[{index - 1}->{index}] generation {previous['generation']}->{current['generation']} {previous['state']}->{current['state']}: {exc}")


def validate_empty_branch_tip(committed_at: datetime, protocol: dict) -> None:
    if not isinstance(committed_at, datetime) or committed_at.tzinfo is None:
        fail("empty lock branch tip timestamp must be timezone-aware datetime")
    cutoff = parse_utc(protocol["lock_history_enforcement_start_utc"])
    if committed_at >= cutoff:
        fail("empty lock branch exists at or after lock transition enforcement epoch")


def validate_versioned_history(entries: list[dict], protocol: dict) -> None:
    if not entries:
        fail("lock history must contain at least one snapshot")
    cutoff = parse_utc(protocol["lock_history_enforcement_start_utc"])
    resource_key = None
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {"commit_sha", "committed_at", "lock"}:
            fail("history entry keys mismatch")
        if not SHA_RE.fullmatch(str(entry["commit_sha"])):
            fail("history entry commit_sha invalid")
        committed_at = entry["committed_at"]
        if not isinstance(committed_at, datetime) or committed_at.tzinfo is None:
            fail("history entry committed_at must be timezone-aware datetime")
        lock = entry["lock"]

        if committed_at < cutoff:
            validate_legacy_snapshot(lock)
        else:
            validate_snapshot(lock, protocol)

        if resource_key is None:
            resource_key = lock["resource_key"]
        elif lock["resource_key"] != resource_key:
            fail("resource_key cannot change within lock history")

        if committed_at < cutoff:
            continue

        if index == 0:
            if lock["state"] != "ACTIVE" or lock["generation"] != 1:
                fail("enforced initial lock snapshot must be ACTIVE generation 1")
            if lock["acquired_at"] != lock["heartbeat_at"]:
                fail("enforced initial lock snapshot must have acquired_at == heartbeat_at")
            continue

        previous_entry = entries[index - 1]
        previous = previous_entry["lock"]
        if previous_entry["committed_at"] < cutoff:
            validate_legacy_snapshot(previous)
        else:
            validate_snapshot(previous, protocol)
        try:
            validate_transition_semantics(previous, lock, protocol)
        except ValidationError as exc:
            fail(
                f"transition[{index - 1}->{index}] generation {previous['generation']}->{lock['generation']} "
                f"{previous['state']}->{lock['state']}: {exc}"
            )


def load_protocol() -> dict:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if protocol.get("protocol_id") not in SUPPORTED_PROTOCOL_IDS:
        fail("lock-history validator requires a supported source-coordination protocol")
    if protocol.get("lease_duration_seconds") != 14400:
        fail("unexpected lease_duration_seconds")
    if protocol.get("renew_when_remaining_seconds_lte") != 1800:
        fail("unexpected renew_when_remaining_seconds_lte")
    if protocol.get("lock_history_enforcement_start_utc") != "2026-09-12T22:56:23Z":
        fail("unexpected lock_history_enforcement_start_utc")
    parse_utc(protocol["lock_history_enforcement_start_utc"])
    return protocol


def remote_lock_branches() -> list[str]:
    output = run_git("ls-remote", "--heads", "origin", "refs/heads/lock/*")
    branches = []
    for line in output.splitlines():
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            fail("malformed git ls-remote output")
        match = LOCK_BRANCH_RE.fullmatch(parts[1])
        if not match:
            fail(f"unexpected lock ref: {parts[1]}")
        branches.append(match.group(1))
    return sorted(branches)


def history_entries_for_branch(branch: str) -> list[dict]:
    remote_ref = f"refs/remotes/origin/{branch}"
    run_git("fetch", "--quiet", "origin", f"refs/heads/{branch}:{remote_ref}")
    commits = [
        line for line in run_git(
            "log", "--reverse", "--format=%H", remote_ref, "--", "coordination/lock.json"
        ).splitlines() if line
    ]
    entries = []
    for commit in commits:
        raw = run_git("show", f"{commit}:coordination/lock.json")
        try:
            lock = json.loads(raw)
        except Exception as exc:
            fail(f"{branch} commit {commit} has invalid lock JSON: {exc}")
        committed_at = parse_git_time(run_git("show", "-s", "--format=%cI", commit))
        entries.append({"commit_sha": commit, "committed_at": committed_at, "lock": lock})
    return entries


def main() -> int:
    try:
        protocol = load_protocol()
        for branch in remote_lock_branches():
            try:
                entries = history_entries_for_branch(branch)
                if not entries:
                    remote_ref = f"refs/remotes/origin/{branch}"
                    tip_time = parse_git_time(run_git("show", "-s", "--format=%cI", remote_ref))
                    validate_empty_branch_tip(tip_time, protocol)
                    continue
                validate_versioned_history(entries, protocol)
            except ValidationError as exc:
                fail(f"{branch}: {exc}")
    except ValidationError as exc:
        print(f"LOCK_HISTORY_INVALID: {exc}", file=sys.stderr)
        return 1
    print("LOCK_HISTORY_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
