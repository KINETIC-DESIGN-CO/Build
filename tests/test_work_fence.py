from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate_work_fence.py"
spec = importlib.util.spec_from_file_location("evaluate_work_fence", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

WORK_A = "00000000-0000-4000-8000-000000000001"
WORK_B = "00000000-0000-4000-8000-000000000002"
LEASE_A = "00000000-0000-4000-8000-000000000003"
GOAL_A = "00000000-0000-4000-8000-000000000004"
SESSION_A = "00000000-0000-4000-8000-000000000005"
NOW = datetime(2026, 9, 13, 21, 0, tzinfo=timezone.utc)


def z(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def registry(revision=3, signal_state="NONE", signal_target=None):
    return {
        "goals": [
            {
                "goal_id": GOAL_A,
                "revision": revision,
                "control_signal": {
                    "state": signal_state,
                    "signal_id": None if signal_state == "NONE" else "GS-0001",
                    "target_work_id": signal_target,
                    "issued_for_revision": revision,
                },
            }
        ]
    }


def record(revision=3, effect="NONE"):
    return {
        "schema_version": 2,
        "work_id": WORK_A,
        "goal_id": GOAL_A,
        "planned_goal_revision": revision,
        "pending_external_effect_state": effect,
    }


def claim(generation=2):
    return {
        "resource_key": "component:test_component",
        "lock_branch": mod.expected_lock_branch("component:test_component"),
        "lease_id": LEASE_A,
        "generation": generation,
    }


def lock_v1(*, generation=2, work_id=WORK_A, acquired=None, expires=None):
    acquired = acquired or (NOW - timedelta(minutes=10))
    expires = expires or (acquired + timedelta(hours=4))
    return {
        "schema_version": 1,
        "resource_key": "component:test_component",
        "generation": generation,
        "state": "ACTIVE",
        "work_id": work_id,
        "worker": {"kind": "chatgpt", "session_id": SESSION_A},
        "implementation_branch": f"work/{work_id}",
        "lease_id": LEASE_A,
        "base_sha": "1" * 40,
        "acquired_at": z(acquired),
        "heartbeat_at": z(acquired),
        "expires_at": z(expires),
        "runtime_control_authority": "NONE",
    }


def lock_v2(*, generation=2, work_id=WORK_A, heartbeat=None, event="ACQUIRE"):
    heartbeat = heartbeat or (NOW - timedelta(minutes=10))
    return {
        "schema_version": 2,
        "resource_key": "component:test_component",
        "generation": generation,
        "state": "ACTIVE",
        "work_id": work_id,
        "worker": {"kind": "chatgpt", "session_id": SESSION_A},
        "implementation_branch": f"work/{work_id}",
        "lease_id": LEASE_A,
        "base_sha": "1" * 40,
        "acquired_at": z(heartbeat),
        "heartbeat_at": z(heartbeat),
        "expires_at": z(heartbeat + timedelta(seconds=1800)),
        "lease_contract": "COMPONENT_1800",
        "lease_event_type": event,
        "runtime_control_authority": "NONE",
    }


class WorkFenceTests(unittest.TestCase):
    def test_canonical_policy_validates(self):
        self.assertEqual(mod.validate_policy()["component_stale_after_seconds"], 1800)

    def test_legacy_v1_component_uses_1800_hard_bound_not_four_hour_storage_expiry(self):
        old = NOW - timedelta(minutes=40)
        value = lock_v1(acquired=old, expires=old + timedelta(hours=4))
        self.assertEqual(mod.effective_component_expiry(value), old + timedelta(seconds=1800))

    def test_v2_component_uses_stored_1800_expiry(self):
        value = lock_v2()
        self.assertEqual(mod.effective_component_expiry(value), mod.parse_utc(value["expires_at"]))

    def test_revision_mismatch_returns_replan_required_before_generation_checks(self):
        result = mod.evaluate_record_claim(record(revision=2), claim(generation=999), lock_v2(generation=2), registry(revision=3), NOW)
        self.assertEqual(result, {"result": "REPLAN_REQUIRED", "reason": "GOAL_REVISION_MISMATCH"})

    def test_unresolved_external_effect_outranks_revision_mismatch(self):
        result = mod.evaluate_record_claim(record(revision=2, effect="TIMEOUT"), claim(), lock_v2(), registry(revision=3), NOW)
        self.assertEqual(result, {"result": "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED", "reason": "EXTERNAL_EFFECT_UNRESOLVED"})

    def test_yield_signal_targets_only_named_work(self):
        result = mod.evaluate_record_claim(record(), claim(), lock_v2(), registry(signal_state="YIELD_OR_REPLAN_REQUESTED", signal_target=WORK_A), NOW)
        self.assertEqual(result, {"result": "REPLAN_REQUIRED", "reason": "CONTROL_SIGNAL_ACTIVE"})

    def test_reassignment_signal_fences_named_work(self):
        result = mod.evaluate_record_claim(record(), claim(), lock_v2(), registry(signal_state="REASSIGNMENT_REQUESTED", signal_target=WORK_A), NOW)
        self.assertEqual(result, {"result": "REASSIGNMENT_REQUIRED", "reason": "CONTROL_SIGNAL_ACTIVE"})

    def test_signal_for_other_work_does_not_block_current_attempt(self):
        result = mod.evaluate_record_claim(record(), claim(), lock_v2(), registry(signal_state="YIELD_OR_REPLAN_REQUESTED", signal_target=WORK_B), NOW)
        self.assertEqual(result, {"result": "PASS", "reason": "PASS"})

    def test_generation_mismatch_fails_closed(self):
        result = mod.evaluate_record_claim(record(), claim(generation=1), lock_v2(generation=2), registry(), NOW)
        self.assertEqual(result, {"result": "STALE_GENERATION", "reason": "CLAIM_GENERATION_MISMATCH"})

    def test_owner_mismatch_fails_even_when_generation_matches(self):
        result = mod.evaluate_record_claim(record(), claim(), lock_v2(work_id=WORK_B), registry(), NOW)
        self.assertEqual(result, {"result": "STALE_OWNER", "reason": "CLAIM_OWNER_MISMATCH"})

    def test_expired_legacy_component_fails_at_1800_seconds(self):
        old = NOW - timedelta(seconds=1800)
        result = mod.evaluate_record_claim(record(), claim(), lock_v1(acquired=old), registry(), NOW)
        self.assertEqual(result, {"result": "COMPONENT_LEASE_EXPIRED", "reason": "COMPONENT_LEASE_EXPIRED"})

    def test_v2_duration_other_than_1800_is_rejected(self):
        value = lock_v2()
        value["expires_at"] = z(mod.parse_utc(value["heartbeat_at"]) + timedelta(seconds=1801))
        with self.assertRaises(mod.FenceError):
            mod.validate_lock_snapshot(value)


if __name__ == "__main__":
    unittest.main()
