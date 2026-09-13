from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_lock_history.py"
spec = importlib.util.spec_from_file_location("validate_lock_history_orphan_refs", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

PROTOCOL = {
    "protocol_id": "life-source-coordination-v3",
    "lease_duration_seconds": 14400,
    "renew_when_remaining_seconds_lte": 1800,
    "lock_history_enforcement_start_utc": "2026-09-12T22:56:23Z",
}
BRANCH = "lock/" + ("a" * 64)
POST_EPOCH = datetime(2026, 9, 12, 22, 57, tzinfo=timezone.utc)


class OrphanLockRefTests(unittest.TestCase):
    def test_unreferenced_empty_branch_has_zero_claim_effect(self):
        mod.validate_empty_branch_reference(BRANCH, POST_EPOCH, PROTOCOL, set())

    def test_referenced_post_epoch_empty_branch_fails_closed(self):
        with self.assertRaises(mod.ValidationError):
            mod.validate_empty_branch_reference(BRANCH, POST_EPOCH, PROTOCOL, {BRANCH})


if __name__ == "__main__":
    unittest.main()
