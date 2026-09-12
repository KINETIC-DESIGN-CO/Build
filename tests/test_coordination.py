from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_coordination.py"
spec = importlib.util.spec_from_file_location("validate_coordination", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

WORK_A = "00000000-0000-4000-8000-000000000001"
WORK_B = "00000000-0000-4000-8000-000000000002"
NOW = datetime(2026, 9, 12, 8, 30, tzinfo=timezone.utc)

def live_lock(resource_key, work_id=WORK_B, state="ACTIVE", expires_at="2026-09-12T12:30:00Z"):
    return {
        "resource_key": resource_key,
        "work_id": work_id,
        "state": state,
        "expires_at": expires_at,
    }

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

    def test_unrelated_active_worker_does_not_block(self):
        blockers = mod.blocking_resource_keys(
            ["repo-file:watchdog/spec.json"],
            [live_lock("repo-file:coordination/protocol.json")],
            WORK_A,
            NOW,
        )
        self.assertEqual(blockers, [])

    def test_exact_shared_file_claim_blocks_only_that_resource(self):
        blockers = mod.blocking_resource_keys(
            ["repo-file:watchdog/spec.json", "repo-file:coordination/protocol.json"],
            [live_lock("repo-file:coordination/protocol.json")],
            WORK_A,
            NOW,
        )
        self.assertEqual(blockers, ["repo-file:coordination/protocol.json"])

    def test_exact_shared_component_claim_blocks_component(self):
        blockers = mod.blocking_resource_keys(
            ["component:source_coordination_parallel_resource_gating"],
            [live_lock("component:source_coordination_parallel_resource_gating")],
            WORK_A,
            NOW,
        )
        self.assertEqual(blockers, ["component:source_coordination_parallel_resource_gating"])

    def test_integration_claim_does_not_block_work_branch_implementation(self):
        blockers = mod.blocking_resource_keys(
            ["component:build_repository_watchdog", "repo-file:watchdog/spec.json"],
            [live_lock("integration:main")],
            WORK_A,
            NOW,
        )
        self.assertEqual(blockers, [])

    def test_integration_claim_blocks_integration_operation(self):
        blockers = mod.blocking_resource_keys(
            ["integration:main"],
            [live_lock("integration:main")],
            WORK_A,
            NOW,
        )
        self.assertEqual(blockers, ["integration:main"])

    def test_supabase_production_claim_serializes_exact_target(self):
        key = "external:supabase:jnenguxodtgwbskhdsxt"
        blockers = mod.blocking_resource_keys([key], [live_lock(key)], WORK_A, NOW)
        self.assertEqual(blockers, [key])

    def test_expired_or_released_claim_does_not_block(self):
        locks = [
            live_lock("repo-file:a", expires_at="2026-09-12T08:29:59Z"),
            live_lock("repo-file:b", state="RELEASED"),
        ]
        self.assertEqual(
            mod.blocking_resource_keys(["repo-file:a", "repo-file:b"], locks, WORK_A, NOW),
            [],
        )

    def test_same_work_id_does_not_block_itself(self):
        lock = live_lock("repo-file:a", work_id=WORK_A)
        self.assertEqual(mod.blocking_resource_keys(["repo-file:a"], [lock], WORK_A, NOW), [])

    def test_current_json_progression_fields_have_zero_claim_effect(self):
        protocol = json.loads((Path(__file__).resolve().parents[1] / "coordination" / "protocol.json").read_text())
        self.assertEqual(
            protocol["parallel_work"]["continuity_fields_with_zero_claim_effect"],
            ["current_component", "current_work", "next_action"],
        )
        self.assertEqual(mod.blocking_resource_keys(["repo-file:a"], [], WORK_A, NOW), [])

    def test_partial_request_keeps_blocked_operation_separate(self):
        result = mod.classify_operation_resource_sets(
            {
                "free_operation": ["repo-file:a"],
                "blocked_operation": ["repo-file:b"],
            },
            [live_lock("repo-file:b")],
            WORK_A,
            NOW,
        )
        self.assertEqual(result["free_operation"]["intersection_state"], "INTERSECTION_EMPTY")
        self.assertEqual(result["blocked_operation"], {
            "intersection_state": "INTERSECTION_NONEMPTY",
            "blocking_resource_keys": ["repo-file:b"],
        })

    def test_acquisition_order_is_per_attempt(self):
        mod.validate_acquisition_attempt_order([
            "component:build_repository_watchdog",
            "repo-file:watchdog/spec.json",
        ])
        mod.validate_acquisition_attempt_order(["integration:main"])
        with self.assertRaises(mod.ValidationError):
            mod.validate_acquisition_attempt_order([
                "repo-file:watchdog/spec.json",
                "component:build_repository_watchdog",
            ])

if __name__ == "__main__":
    unittest.main()
