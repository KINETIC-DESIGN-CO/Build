from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "coordination" / "protocol.json"
LOCK_HISTORY_SCRIPT = ROOT / "scripts" / "validate_lock_history.py"

spec = importlib.util.spec_from_file_location("validate_lock_history", LOCK_HISTORY_SCRIPT)
lock_history = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(lock_history)


class InitialLockPublicationTests(unittest.TestCase):
    def protocol(self) -> dict:
        return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))

    def test_protocol_requires_prebuilt_generation_one_lock_commit(self):
        rules = self.protocol()["mutation_rules"]
        self.assertEqual(
            rules.count(
                "INITIAL_GENERATION_ONE_LOCK_PUBLICATION_PREBUILDS_COMMIT_WITH_COORDINATION_LOCK_JSON_BEFORE_LOCK_REF_CREATION"
            ),
            1,
        )
        self.assertEqual(
            rules.count(
                "FIRST_VISIBLE_LOCK_REF_TARGET_MUST_ALREADY_CONTAIN_VALID_ACTIVE_GENERATION_ONE_COORDINATION_LOCK_JSON"
            ),
            1,
        )

    def test_protocol_forbids_visible_empty_post_epoch_lock_ref(self):
        rules = self.protocol()["mutation_rules"]
        self.assertEqual(
            rules.count(
                "EMPTY_LOCK_BRANCH_REF_PUBLICATION_IS_FORBIDDEN_AT_OR_AFTER_LOCK_HISTORY_ENFORCEMENT_START_UTC"
            ),
            1,
        )

    def test_post_epoch_empty_lock_branch_detector_remains_fail_closed(self):
        protocol = self.protocol()
        with self.assertRaises(lock_history.ValidationError):
            lock_history.validate_empty_branch_tip(
                datetime(2026, 9, 13, 9, 13, 6, tzinfo=timezone.utc),
                protocol,
            )


if __name__ == "__main__":
    unittest.main()
