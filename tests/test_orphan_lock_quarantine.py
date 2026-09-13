from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_lock_history.py"
spec = importlib.util.spec_from_file_location("validate_lock_history_quarantine", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

BRANCH = "lock/" + "3" * 64
TIP = "a" * 40
OTHER_TIP = "b" * 40
PROTOCOL = {
    "protocol_id": "life-source-coordination-v3",
    "lease_duration_seconds": 14400,
    "renew_when_remaining_seconds_lte": 1800,
    "lock_history_enforcement_start_utc": "2026-09-12T22:56:23Z",
}


def registry(*, branch=BRANCH, tip=TIP, disposition="ABANDONED_EMPTY_CLAIM_BRANCH"):
    return {
        "schema_version": 1,
        "registry_id": "life-orphan-lock-branch-quarantine-v1",
        "runtime_control_authority": "NONE",
        "entries": [
            {
                "branch": branch,
                "exact_tip_sha": tip,
                "disposition": disposition,
                "observed_at": "2026-09-13T09:02:02Z",
                "evidence_refs": ["TEST:EVIDENCE"],
            }
        ],
    }


class OrphanLockQuarantineTests(unittest.TestCase):
    def test_exact_quarantine_allows_post_epoch_empty_branch(self):
        quarantine = mod.validate_quarantine_registry(registry())
        mod.validate_empty_branch_or_quarantine(
            BRANCH,
            TIP,
            datetime(2026, 9, 13, 9, 2, 2, tzinfo=timezone.utc),
            PROTOCOL,
            quarantine,
        )

    def test_unlisted_post_epoch_empty_branch_still_fails(self):
        with self.assertRaises(mod.ValidationError):
            mod.validate_empty_branch_or_quarantine(
                BRANCH,
                TIP,
                datetime(2026, 9, 13, 9, 2, 2, tzinfo=timezone.utc),
                PROTOCOL,
                {},
            )

    def test_quarantine_tip_mismatch_fails(self):
        quarantine = mod.validate_quarantine_registry(registry())
        with self.assertRaises(mod.ValidationError):
            mod.validate_empty_branch_or_quarantine(
                BRANCH,
                OTHER_TIP,
                datetime(2026, 9, 13, 9, 2, 2, tzinfo=timezone.utc),
                PROTOCOL,
                quarantine,
            )

    def test_duplicate_quarantine_branch_fails(self):
        value = registry()
        value["entries"].append(dict(value["entries"][0]))
        with self.assertRaises(mod.ValidationError):
            mod.validate_quarantine_registry(value)

    def test_invalid_disposition_fails(self):
        with self.assertRaises(mod.ValidationError):
            mod.validate_quarantine_registry(registry(disposition="IGNORE"))

    def test_registry_file_loader_is_closed(self):
        value = registry()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orphan-lock-branches.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with mock.patch.object(mod, "QUARANTINE_PATH", path):
                loaded = mod.load_quarantine_registry()
        self.assertEqual(loaded[BRANCH]["exact_tip_sha"], TIP)


if __name__ == "__main__":
    unittest.main()
