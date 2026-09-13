#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

CORE_PATH = Path(__file__).with_name("validate_lock_history_core.py")
_spec = importlib.util.spec_from_file_location("validate_lock_history_core", CORE_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError("unable to load lock-history core")
_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core)

for _name in dir(_core):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_core, _name)

QUARANTINE_PATH = ROOT / "coordination" / "orphan-lock-branches.json"
QUARANTINE_REGISTRY_KEYS = {
    "schema_version",
    "registry_id",
    "runtime_control_authority",
    "entries",
}
QUARANTINE_ENTRY_KEYS = {
    "branch",
    "exact_tip_sha",
    "disposition",
    "observed_at",
    "evidence_refs",
}
QUARANTINE_BRANCH_RE = re.compile(r"^lock/[0-9a-f]{64}$")
QUARANTINE_DISPOSITION = "ABANDONED_EMPTY_CLAIM_BRANCH"


def load_protocol() -> dict:
    _core.PROTOCOL_PATH = PROTOCOL_PATH
    return _core.load_protocol()


def validate_quarantine_registry(value: object) -> dict[str, dict]:
    if not isinstance(value, dict) or set(value) != QUARANTINE_REGISTRY_KEYS:
        fail("orphan-lock quarantine registry keys mismatch")
    if value["schema_version"] != 1:
        fail("orphan-lock quarantine schema_version must equal 1")
    if value["registry_id"] != "life-orphan-lock-branch-quarantine-v1":
        fail("orphan-lock quarantine registry_id mismatch")
    if value["runtime_control_authority"] != "NONE":
        fail("orphan-lock quarantine runtime_control_authority must equal NONE")
    entries = value["entries"]
    if not isinstance(entries, list):
        fail("orphan-lock quarantine entries must be an array")

    by_branch: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != QUARANTINE_ENTRY_KEYS:
            fail("orphan-lock quarantine entry keys mismatch")
        branch = entry["branch"]
        if not isinstance(branch, str) or not QUARANTINE_BRANCH_RE.fullmatch(branch):
            fail("orphan-lock quarantine branch invalid")
        if branch in by_branch:
            fail("orphan-lock quarantine branch duplicated")
        if not SHA_RE.fullmatch(str(entry["exact_tip_sha"])):
            fail("orphan-lock quarantine exact_tip_sha invalid")
        if entry["disposition"] != QUARANTINE_DISPOSITION:
            fail("orphan-lock quarantine disposition invalid")
        parse_utc(entry["observed_at"])
        evidence_refs = entry["evidence_refs"]
        if (
            not isinstance(evidence_refs, list)
            or not evidence_refs
            or len(set(evidence_refs)) != len(evidence_refs)
            or any(not isinstance(ref, str) or not ref for ref in evidence_refs)
        ):
            fail("orphan-lock quarantine evidence_refs must be a nonempty unique string array")
        by_branch[branch] = entry
    return by_branch


def load_quarantine_registry() -> dict[str, dict]:
    try:
        value = json.loads(QUARANTINE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"cannot read orphan-lock quarantine registry: {exc}")
    return validate_quarantine_registry(value)


def validate_empty_branch_or_quarantine(
    branch: str,
    tip_sha: str,
    committed_at: datetime,
    protocol: dict,
    quarantine: dict[str, dict],
) -> None:
    try:
        validate_empty_branch_tip(committed_at, protocol)
        return
    except ValidationError as original:
        entry = quarantine.get(branch)
        if entry is None:
            raise original
        if entry["exact_tip_sha"] != tip_sha:
            fail(
                f"quarantined empty lock branch tip mismatch: expected {entry['exact_tip_sha']} got {tip_sha}"
            )


def main() -> int:
    try:
        protocol = load_protocol()
        quarantine = load_quarantine_registry()
        branches = remote_lock_branches()
        missing = sorted(set(quarantine) - set(branches))
        if missing:
            fail(f"orphan-lock quarantine references missing branch: {missing[0]}")

        for branch in branches:
            try:
                entries = history_entries_for_branch(branch)
                if entries:
                    if branch in quarantine:
                        fail("quarantined orphan lock branch now contains lock history")
                    validate_versioned_history(entries, protocol)
                    continue

                remote_ref = f"refs/remotes/origin/{branch}"
                tip_time = parse_git_time(run_git("show", "-s", "--format=%cI", remote_ref))
                tip_sha = run_git("rev-parse", remote_ref)
                validate_empty_branch_or_quarantine(branch, tip_sha, tip_time, protocol, quarantine)
            except ValidationError as exc:
                fail(f"{branch}: {exc}")
    except ValidationError as exc:
        print(f"LOCK_HISTORY_INVALID: {exc}", file=sys.stderr)
        return 1
    print("LOCK_HISTORY_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
