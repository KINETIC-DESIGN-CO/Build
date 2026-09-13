#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_PATH = ROOT / "scripts" / "select_work.py"
FENCE_PATH = ROOT / "scripts" / "evaluate_work_fence.py"

legacy_spec = importlib.util.spec_from_file_location("select_work_v4", LEGACY_PATH)
legacy = importlib.util.module_from_spec(legacy_spec)
assert legacy_spec.loader is not None
legacy_spec.loader.exec_module(legacy)

fence_spec = importlib.util.spec_from_file_location("evaluate_work_fence", FENCE_PATH)
fence = importlib.util.module_from_spec(fence_spec)
assert fence_spec.loader is not None
fence_spec.loader.exec_module(fence)


class SelectorV5Error(RuntimeError):
    pass


def fail(message: str) -> None:
    raise SelectorV5Error(message)


def validate_lock(key: str, lock: object):
    if lock is None:
        return None
    try:
        return fence.validate_lock_snapshot(lock, key)
    except fence.FenceError as exc:
        fail(f"dispatch lock invalid for {key}: {exc}")


def active(key: str, lock: dict | None, now: datetime) -> bool:
    if lock is None or lock["state"] != "ACTIVE":
        return False
    if key.startswith("component:"):
        return now < fence.effective_component_expiry(lock)
    return now < fence.parse_utc(lock["expires_at"])


def dispatch(snapshot: dict, current: dict, admissions: dict, by_id: dict):
    if not isinstance(snapshot, dict) or set(snapshot) != {"observed_at", "resources"}:
        fail("dispatch snapshot keys mismatch")
    now = fence.parse_utc(snapshot["observed_at"])
    resources = snapshot["resources"]
    required = legacy.dispatch_keys(current, admissions)
    if not isinstance(resources, dict) or set(resources) != set(required):
        fail(f"dispatch snapshot resource coverage mismatch: required={required}")
    locks = {key: validate_lock(key, resources[key]) for key in required}
    status, blockers, action_id = legacy.current_fields(current)
    current_key = f"component:{current['current_component']}"
    foreground = status in {"ACTIVE", "BLOCKED"} and not active(current_key, locks[current_key], now)
    if foreground:
        if status == "BLOCKED" and blockers:
            rank, selected = 1, "CLEAR_CURRENT_BLOCKERS"
        elif action_id is not None:
            rank, selected = 2, "CURRENT_NEXT_ACTION"
        else:
            rank, selected = None, None
        return {
            "decision": "SELECT" if rank is not None else "NO_ELIGIBLE_WORK",
            "worker_lane": "FOREGROUND",
            "lane_basis": "CURRENT_COMPONENT_AVAILABLE",
            "effective_rank": rank,
            "selected_work": selected,
            "current_component_id": current["current_component"],
            "current_next_action_id": action_id,
            "open_blocker_ids": blockers,
            "work_item_id": None,
            "source_issue_number": None,
            "claim_next_resource_key": current_key if rank is not None else None,
            "race_rule": legacy.FRESH["race_rule"],
            "component_stale_after_seconds": fence.EXPECTED_POLICY["component_stale_after_seconds"],
        }
    for item in legacy.ready_items(admissions, by_id):
        key = f"component:{item['component_id']}"
        if not active(key, locks[key], now):
            return {
                "decision": "SELECT",
                "worker_lane": "PARALLEL_ASSIGNED",
                "lane_basis": "CURRENT_COMPONENT_OWNED_OR_CURRENT_COMPLETE",
                "effective_rank": 3,
                "selected_work": "PARALLEL_ADMITTED_WORK",
                "current_component_id": current["current_component"],
                "current_next_action_id": action_id,
                "open_blocker_ids": blockers,
                "work_item_id": item["work_item_id"],
                "source_issue_number": item["source_issue_number"],
                "claim_next_resource_key": key,
                "race_rule": legacy.FRESH["race_rule"],
                "component_stale_after_seconds": fence.EXPECTED_POLICY["component_stale_after_seconds"],
            }
    return {
        "decision": "NO_ELIGIBLE_WORK",
        "worker_lane": "PARALLEL_ASSIGNED",
        "lane_basis": "CURRENT_COMPONENT_OWNED_OR_CURRENT_COMPLETE",
        "effective_rank": None,
        "selected_work": None,
        "current_component_id": current["current_component"],
        "current_next_action_id": action_id,
        "open_blocker_ids": blockers,
        "work_item_id": None,
        "source_issue_number": None,
        "claim_next_resource_key": None,
        "race_rule": legacy.FRESH["race_rule"],
        "component_stale_after_seconds": fence.EXPECTED_POLICY["component_stale_after_seconds"],
    }


def live_lock(key: str):
    branch = legacy.lock_branch(key)
    remote_ref = f"refs/remotes/origin/{branch}"
    proc = subprocess.run(
        ["git", "fetch", "--quiet", "origin", f"refs/heads/{branch}:{remote_ref}"],
        cwd=ROOT, text=True, capture_output=True,
    )
    if proc.returncode:
        low = proc.stderr.lower()
        if "couldn't find remote ref" in low or "remote ref does not exist" in low:
            return None
        fail(f"live lock fetch failed for {key}: {proc.stderr.strip()}")
    show = subprocess.run(
        ["git", "show", f"{remote_ref}:coordination/lock.json"],
        cwd=ROOT, text=True, capture_output=True,
    )
    if show.returncode:
        fail(f"live lock read failed for {key}: {show.stderr.strip()}")
    try:
        return validate_lock(key, json.loads(show.stdout))
    except json.JSONDecodeError as exc:
        fail(f"invalid live lock JSON for {key}: {exc}")


def live_snapshot(current: dict, admissions: dict):
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {"observed_at": now, "resources": {key: live_lock(key) for key in legacy.dispatch_keys(current, admissions)}}


def validate_all():
    policy = legacy.load(legacy.POLICY_PATH)
    schema = legacy.load(legacy.SCHEMA_PATH)
    admissions = legacy.load(legacy.ADMISSIONS_PATH)
    admissions_schema = legacy.load(legacy.ADMISSIONS_SCHEMA_PATH)
    by_id = legacy.validate_policy(policy, schema, admissions, admissions_schema)
    fence.validate_policy()
    return policy, admissions, by_id


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-policy", action="store_true")
    mode.add_argument("--evaluate")
    mode.add_argument("--select-parallel", action="store_true")
    mode.add_argument("--dispatch-snapshot")
    mode.add_argument("--dispatch-live", action="store_true")
    parser.add_argument("--unavailable-work-item", action="append", default=[])
    args = parser.parse_args()
    try:
        _policy, admissions, by_id = validate_all()
        if args.evaluate:
            if args.unavailable_work_item:
                fail("--unavailable-work-item is valid only with --select-parallel")
            evidence = json.loads(Path(args.evaluate).read_text(encoding="utf-8"))
            print(json.dumps(legacy.evaluate(evidence, by_id), indent=2))
        elif args.select_parallel:
            unavailable = set(legacy.unique_strings(args.unavailable_work_item, "unavailable_work_item", r"github-issue-[1-9][0-9]*"))
            print(json.dumps(legacy.select_parallel(admissions, by_id, unavailable), indent=2))
        elif args.dispatch_snapshot:
            if args.unavailable_work_item:
                fail("--unavailable-work-item is valid only with --select-parallel")
            snapshot = json.loads(Path(args.dispatch_snapshot).read_text(encoding="utf-8"))
            print(json.dumps(dispatch(snapshot, legacy.load(legacy.CURRENT_PATH), admissions, by_id), indent=2))
        elif args.dispatch_live:
            if args.unavailable_work_item:
                fail("--unavailable-work-item is valid only with --select-parallel")
            current = legacy.load(legacy.CURRENT_PATH)
            snapshot = live_snapshot(current, admissions)
            result = dispatch(snapshot, current, admissions, by_id)
            result["observed_at"] = snapshot["observed_at"]
            print(json.dumps(result, indent=2))
        else:
            if args.unavailable_work_item:
                fail("--unavailable-work-item requires --select-parallel")
            print("VALID")
        return 0
    except (SelectorV5Error, legacy.PolicyError, fence.FenceError, OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
