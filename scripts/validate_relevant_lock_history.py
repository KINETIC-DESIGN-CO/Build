#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_VALIDATOR_PATH = ROOT / "scripts" / "validate_lock_history.py"
WORK_RECORD_RE = re.compile(r"^coordination/work/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.json$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

spec = importlib.util.spec_from_file_location("validate_lock_history", LOCK_VALIDATOR_PATH)
lock_history = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(lock_history)


class ValidationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ValidationError(message)


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        fail(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def changed_paths_for_event(event_name: str, event: dict, github_sha: str) -> list[str]:
    if event_name == "pull_request":
        pr = event.get("pull_request") or {}
        base_sha = str((pr.get("base") or {}).get("sha") or "")
        head_sha = str((pr.get("head") or {}).get("sha") or "")
        if not SHA_RE.fullmatch(base_sha) or not SHA_RE.fullmatch(head_sha):
            fail("pull_request base/head SHA missing or invalid")
        diff_spec = f"{base_sha}...{head_sha}"
    elif event_name == "merge_group":
        group = event.get("merge_group") or {}
        head_sha = str(group.get("head_sha") or "")
        if not SHA_RE.fullmatch(head_sha):
            fail("merge_group head_sha missing or invalid")
        if github_sha and head_sha != github_sha:
            fail("merge_group head_sha must equal GITHUB_SHA")
        parent_sha = git("rev-parse", f"{head_sha}^1")
        if not SHA_RE.fullmatch(parent_sha):
            fail("merge_group first parent SHA missing or invalid")
        diff_spec = f"{parent_sha}..{head_sha}"
    elif event_name == "push":
        head_sha = github_sha or str(event.get("after") or "")
        before_sha = str(event.get("before") or "")
        if not SHA_RE.fullmatch(head_sha):
            fail("push head SHA missing or invalid")
        if not SHA_RE.fullmatch(before_sha) or before_sha == "0" * 40:
            before_sha = git("rev-parse", f"{head_sha}^1")
        diff_spec = f"{before_sha}..{head_sha}"
    else:
        fail(f"unsupported required-CI event: {event_name!r}")
    return sorted(path for path in git("diff", "--name-only", diff_spec).splitlines() if path)


def relevant_lock_branches(changed_paths: list[str]) -> list[str]:
    work_paths = sorted(path for path in changed_paths if WORK_RECORD_RE.fullmatch(path))
    branches: set[str] = set()
    for rel in work_paths:
        path = ROOT / rel
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(f"invalid work record {rel}: {exc}")
        claims = record.get("claims")
        if not isinstance(claims, list) or not claims:
            fail(f"work record {rel} claims must be nonempty array")
        for claim in claims:
            if not isinstance(claim, dict):
                fail(f"work record {rel} claim must be object")
            branch = claim.get("lock_branch")
            if not isinstance(branch, str) or not lock_history.LOCK_BRANCH_RE.fullmatch(f"refs/heads/{branch}"):
                fail(f"work record {rel} has invalid lock_branch")
            branches.add(branch)
    return sorted(branches)


def validate_branch(branch: str, protocol: dict) -> None:
    entries = lock_history.history_entries_for_branch(branch)
    if not entries:
        remote_ref = f"refs/remotes/origin/{branch}"
        tip_time = lock_history.parse_git_time(
            lock_history.run_git("show", "-s", "--format=%cI", remote_ref)
        )
        lock_history.validate_empty_branch_tip(tip_time, protocol)
        return
    lock_history.validate_versioned_history(entries, protocol)


def main() -> int:
    try:
        protocol = lock_history.load_protocol()
        event_name = os.environ.get("GITHUB_EVENT_NAME", "")
        event_path = os.environ.get("GITHUB_EVENT_PATH", "")
        github_sha = os.environ.get("GITHUB_SHA", "")

        if event_name in {"pull_request", "merge_group", "push"}:
            if not event_path:
                fail("GITHUB_EVENT_PATH missing")
            try:
                event = json.loads(Path(event_path).read_text(encoding="utf-8"))
            except Exception as exc:
                fail(f"invalid GITHUB_EVENT_PATH JSON: {exc}")
            branches = relevant_lock_branches(changed_paths_for_event(event_name, event, github_sha))
        else:
            # Manual/local invocation remains a full namespace audit.
            branches = lock_history.remote_lock_branches()

        for branch in branches:
            try:
                validate_branch(branch, protocol)
            except lock_history.ValidationError as exc:
                fail(f"{branch}: {exc}")
    except (ValidationError, lock_history.ValidationError) as exc:
        print(f"RELEVANT_LOCK_HISTORY_INVALID: {exc}", file=sys.stderr)
        return 1

    print("RELEVANT_LOCK_HISTORY_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
