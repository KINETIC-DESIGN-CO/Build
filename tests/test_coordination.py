from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_coordination.py"
spec = importlib.util.spec_from_file_location("validate_coordination", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class CoordinationTests(unittest.TestCase):
    def test_lock_branch_derivation_is_deterministic(self):
        self.assertEqual(
            mod.expected_lock_branch("integration:main"),
            "lock/138c728d71ab409c9ab9f7805063b24bebef209ef2f0ffe6db6a1db4263307a9",
        )

    def test_uuid4_rejects_non_v4(self):
        self.assertIsNone(mod.UUID4_RE.fullmatch("00000000-0000-3000-8000-000000000000"))
        self.assertIsNotNone(mod.UUID4_RE.fullmatch("00000000-0000-4000-8000-000000000000"))

    def test_protocol_current_file_validates(self):
        protocol = json.loads((Path(__file__).resolve().parents[1] / "coordination" / "protocol.json").read_text())
        mod.validate_protocol(protocol)

    def test_protocol_declares_recursion_safe_continuity_sync(self):
        protocol = json.loads((Path(__file__).resolve().parents[1] / "coordination" / "protocol.json").read_text())
        rule = "CONTINUITY_SYNC_PR_MAY_MERGE_MAIN_WITHOUT_SECOND_SYNC_ONLY_WHEN_CHANGED_PATHS_ARE_NONEMPTY_SUBSET_OF_BOOTSTRAP_CONTINUITY_SYNC_PATHS"
        self.assertEqual(protocol["mutation_rules"].count(rule), 1)

    def test_protocol_declares_released_reacquisition_generation(self):
        protocol = json.loads((Path(__file__).resolve().parents[1] / "coordination" / "protocol.json").read_text())
        rule = "LEASE_REACQUISITION_AFTER_RELEASE_INCREMENTS_GENERATION_BY_EXACTLY_ONE"
        self.assertEqual(protocol["mutation_rules"].count(rule), 1)

    def test_protocol_requires_fresh_reread_after_lock_conflict(self):
        protocol = json.loads((Path(__file__).resolve().parents[1] / "coordination" / "protocol.json").read_text())
        rule = "LOCK_COMPARE_AND_SWAP_CONFLICT_REQUIRES_FRESH_LIVE_LOCK_REREAD_BEFORE_ANY_RETRY_OR_NEW_ACQUISITION_ATTEMPT_FOR_THAT_RESOURCE"
        self.assertEqual(protocol["mutation_rules"].count(rule), 1)

    def test_protocol_defines_claim_owner_without_session_id(self):
        protocol = json.loads((Path(__file__).resolve().parents[1] / "coordination" / "protocol.json").read_text())
        ownership = "CLAIM_OWNERSHIP_IS_RESOURCE_KEY_WORK_ID_LEASE_ID_GENERATION_NOT_WORKER_SESSION_ID"
        audit_only = "WORKER_SESSION_ID_IS_AUDIT_LABEL_ONLY_AND_MAY_REPEAT_ACROSS_WORK_ITEMS"
        self.assertEqual(protocol["mutation_rules"].count(ownership), 1)
        self.assertEqual(protocol["mutation_rules"].count(audit_only), 1)

    def test_worker_requires_exact_keys(self):
        with self.assertRaises(mod.ValidationError):
            mod.validate_worker({"kind": "chatgpt", "session_id": "00000000-0000-4000-8000-000000000000", "extra": 1})


if __name__ == "__main__":
    unittest.main()
