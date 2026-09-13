from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

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
    def protocol(self):
        return json.loads(
            (Path(__file__).resolve().parents[1] / "coordination" / "protocol.json").read_text()
        )

    def test_lock_branch_derivation_is_deterministic(self):
        self.assertEqual(
            mod.expected_lock_branch("integration:main"),
            "lock/138c728d71ab409c9ab9f7805063b24bebef209ef2f0ffe6db6a1db4263307a9",
        )

    def test_uuid4_rejects_non_v4(self):
        self.assertIsNone(mod.UUID4_RE.fullmatch("00000000-0000-3000-8000-000000000000"))
        self.assertIsNotNone(mod.UUID4_RE.fullmatch("00000000-0000-4000-8000-000000000000"))

    def test_protocol_current_file_validates(self):
        mod.validate_protocol(self.protocol())

    def test_protocol_uses_current_repository_identity(self):
        self.assertEqual(self.protocol()["canonical_repository"], "KINETIC-DESIGN-CO/Build")

    def test_protocol_replaces_integration_claim_with_merge_queue(self):
        protocol = self.protocol()
        self.assertNotIn("main_integration", protocol["required_claims"])
        self.assertEqual(protocol["parallel_work"]["main_integration_mode"], "GITHUB_REQUIRED_MERGE_QUEUE")
        self.assertIn("MAIN_RULESET_MUST_REQUIRE_MERGE_QUEUE", protocol["integration_rules"])
        self.assertIn("MERGE_GROUP_VALIDATE_MUST_PASS_BEFORE_MAIN_INTEGRATION", protocol["integration_rules"])
        self.assertNotIn(
            "EVERY_PR_TO_MAIN_REQUIRES_AN_ACTIVE_INTEGRATION_MAIN_CLAIM",
            protocol["mutation_rules"],
        )

    def test_protocol_declares_recursion_safe_continuity_sync(self):
        rule = "CONTINUITY_SYNC_PR_MAY_MERGE_MAIN_WITHOUT_SECOND_SYNC_ONLY_WHEN_CHANGED_PATHS_ARE_NONEMPTY_SUBSET_OF_BOOTSTRAP_CONTINUITY_SYNC_PATHS"
        self.assertEqual(self.protocol()["mutation_rules"].count(rule), 1)

    def test_protocol_declares_lock_history_enforcement(self):
        rule = "LOCK_HISTORY_VALIDATION_MUST_PROVE_LEGAL_DURATION_RENEWAL_RELEASE_REACQUISITION_AND_TAKEOVER_TRANSITIONS"
        self.assertEqual(self.protocol()["mutation_rules"].count(rule), 1)

    def test_protocol_requires_fresh_reread_after_lock_conflict(self):
        rule = "LOCK_COMPARE_AND_SWAP_CONFLICT_REQUIRES_FRESH_LIVE_LOCK_REREAD_BEFORE_ANY_RETRY_OR_NEW_ACQUISITION_ATTEMPT_FOR_THAT_RESOURCE"
        self.assertEqual(self.protocol()["mutation_rules"].count(rule), 1)

    def test_protocol_defines_claim_owner_without_session_id(self):
        rules = self.protocol()["mutation_rules"]
        self.assertEqual(
            rules.count("CLAIM_OWNERSHIP_IS_RESOURCE_KEY_WORK_ID_LEASE_ID_GENERATION_NOT_WORKER_SESSION_ID"),
            1,
        )
        self.assertEqual(
            rules.count("WORKER_SESSION_ID_IS_AUDIT_LABEL_ONLY_AND_MAY_REPEAT_ACROSS_WORK_ITEMS"),
            1,
        )

    def test_worker_requires_exact_keys(self):
        with self.assertRaises(mod.ValidationError):
            mod.validate_worker({
                "kind": "chatgpt",
                "session_id": "00000000-0000-4000-8000-000000000000",
                "extra": 1,
            })

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

    def test_legacy_integration_lock_has_no_effect_when_operation_does_not_request_it(self):
        blockers = mod.blocking_resource_keys(
            ["component:build_repository_watchdog", "repo-file:watchdog/spec.json"],
            [live_lock("integration:main")],
            WORK_A,
            NOW,
        )
        self.assertEqual(blockers, [])

    def test_supabase_production_claim_serializes_exact_target(self):
        key = "external:supabase:jnenguxodtgwbskhdsxt"
        self.assertEqual(mod.blocking_resource_keys([key], [live_lock(key)], WORK_A, NOW), [key])

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

    def test_partial_request_keeps_blocked_operation_separate(self):
        result = mod.classify_operation_resource_sets(
            {"free_operation": ["repo-file:a"], "blocked_operation": ["repo-file:b"]},
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
        with self.assertRaises(mod.ValidationError):
            mod.validate_acquisition_attempt_order([
                "repo-file:watchdog/spec.json",
                "component:build_repository_watchdog",
            ])

    def test_merge_group_requires_main_and_matching_sha(self):
        sha = "a" * 40
        mod.validate_merge_group_event(
            {"merge_group": {"head_sha": sha, "base_ref": "refs/heads/main"}},
            sha,
        )

    def test_merge_group_rejects_wrong_base(self):
        sha = "a" * 40
        with self.assertRaises(mod.ValidationError):
            mod.validate_merge_group_event(
                {"merge_group": {"head_sha": sha, "base_ref": "refs/heads/release"}},
                sha,
            )

    def test_merge_group_rejects_sha_mismatch(self):
        with self.assertRaises(mod.ValidationError):
            mod.validate_merge_group_event(
                {"merge_group": {"head_sha": "a" * 40, "base_ref": "refs/heads/main"}},
                "b" * 40,
            )

    def test_live_lock_allows_independent_acquisition_base(self):
        record = {
            "work_id": WORK_A,
            "worker": {"kind": "chatgpt", "session_id": "00000000-0000-4000-8000-000000000003"},
            "implementation_branch": f"work/{WORK_A}",
            "base_sha": "1" * 40,
        }
        claim = {
            "resource_key": "continuity:sync",
            "lock_branch": mod.expected_lock_branch("continuity:sync"),
            "lease_id": "00000000-0000-4000-8000-000000000004",
            "generation": 2,
        }
        lock = {
            "schema_version": 1,
            "resource_key": "continuity:sync",
            "generation": 2,
            "state": "ACTIVE",
            "work_id": WORK_A,
            "worker": record["worker"],
            "implementation_branch": record["implementation_branch"],
            "lease_id": claim["lease_id"],
            "base_sha": "2" * 40,
            "acquired_at": "2026-09-12T07:00:00Z",
            "heartbeat_at": "2026-09-12T07:00:00Z",
            "expires_at": "2026-09-12T11:00:00Z",
            "runtime_control_authority": "NONE",
        }
        mod.validate_live_lock(lock, claim, record, NOW, self.protocol())

    def test_live_lock_rejects_malformed_acquisition_base(self):
        record = {
            "work_id": WORK_A,
            "worker": {"kind": "chatgpt", "session_id": "00000000-0000-4000-8000-000000000003"},
            "implementation_branch": f"work/{WORK_A}",
            "base_sha": "1" * 40,
        }
        claim = {
            "resource_key": "continuity:sync",
            "lock_branch": mod.expected_lock_branch("continuity:sync"),
            "lease_id": "00000000-0000-4000-8000-000000000004",
            "generation": 2,
        }
        lock = {
            "schema_version": 1,
            "resource_key": "continuity:sync",
            "generation": 2,
            "state": "ACTIVE",
            "work_id": WORK_A,
            "worker": record["worker"],
            "implementation_branch": record["implementation_branch"],
            "lease_id": claim["lease_id"],
            "base_sha": "not-a-sha",
            "acquired_at": "2026-09-12T07:00:00Z",
            "heartbeat_at": "2026-09-12T07:00:00Z",
            "expires_at": "2026-09-12T11:00:00Z",
            "runtime_control_authority": "NONE",
        }
        with self.assertRaises(mod.ValidationError):
            mod.validate_live_lock(lock, claim, record, NOW, self.protocol())

    def test_work_record_base_is_provenance_not_current_main(self):
        record = {
            "schema_version": 1,
            "work_id": WORK_A,
            "title": "test",
            "worker": {"kind": "chatgpt", "session_id": "00000000-0000-4000-8000-000000000003"},
            "implementation_branch": f"work/{WORK_A}",
            "base_sha": "1" * 40,
            "component_id": "test_component",
            "repo_paths": ["a.txt"],
            "external_targets": [],
            "claims": [
                {
                    "resource_key": "component:test_component",
                    "lock_branch": mod.expected_lock_branch("component:test_component"),
                    "lease_id": "00000000-0000-4000-8000-000000000004",
                    "generation": 1,
                },
                {
                    "resource_key": "repo-file:a.txt",
                    "lock_branch": mod.expected_lock_branch("repo-file:a.txt"),
                    "lease_id": "00000000-0000-4000-8000-000000000005",
                    "generation": 1,
                },
            ],
            "runtime_control_authority": "NONE",
        }
        completed = type("P", (), {"returncode": 0})()
        with patch.object(mod.subprocess, "run", return_value=completed):
            mod.validate_work_record(record, ["a.txt", f"coordination/work/{WORK_A}.json"], f"work/{WORK_A}", "2" * 40)

    def test_work_record_rejects_obsolete_integration_claim(self):
        record = {
            "schema_version": 1,
            "work_id": WORK_A,
            "title": "test",
            "worker": {"kind": "chatgpt", "session_id": "00000000-0000-4000-8000-000000000003"},
            "implementation_branch": f"work/{WORK_A}",
            "base_sha": "1" * 40,
            "component_id": "test_component",
            "repo_paths": ["a.txt"],
            "external_targets": [],
            "claims": [
                {
                    "resource_key": "component:test_component",
                    "lock_branch": mod.expected_lock_branch("component:test_component"),
                    "lease_id": "00000000-0000-4000-8000-000000000004",
                    "generation": 1,
                },
                {
                    "resource_key": "integration:main",
                    "lock_branch": mod.expected_lock_branch("integration:main"),
                    "lease_id": "00000000-0000-4000-8000-000000000006",
                    "generation": 1,
                },
                {
                    "resource_key": "repo-file:a.txt",
                    "lock_branch": mod.expected_lock_branch("repo-file:a.txt"),
                    "lease_id": "00000000-0000-4000-8000-000000000005",
                    "generation": 1,
                },
            ],
            "runtime_control_authority": "NONE",
        }
        completed = type("P", (), {"returncode": 0})()
        with patch.object(mod.subprocess, "run", return_value=completed):
            with self.assertRaises(mod.ValidationError):
                mod.validate_work_record(record, ["a.txt", f"coordination/work/{WORK_A}.json"], f"work/{WORK_A}", "2" * 40)


if __name__ == "__main__":
    unittest.main()
