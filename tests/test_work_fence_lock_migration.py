from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_lock_history.py"
spec = importlib.util.spec_from_file_location("validate_lock_history", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

WORK = "00000000-0000-4000-8000-000000000001"
LEASE_A = "00000000-0000-4000-8000-000000000002"
LEASE_B = "00000000-0000-4000-8000-000000000003"
SESSION = "00000000-0000-4000-8000-000000000004"
NOW = datetime(2026, 9, 13, 22, 0, tzinfo=timezone.utc)


def z(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def protocol():
    return {
        "protocol_id": "life-source-coordination-v4",
        "lease_duration_seconds": 14400,
        "renew_when_remaining_seconds_lte": 1800,
        "legacy_lease_duration_seconds": 14400,
        "component_lease_duration_seconds": 1800,
        "lock_history_enforcement_start_utc": "2026-09-12T22:56:23Z",
    }


def v1(*, generation=1, lease_id=LEASE_A, heartbeat=None, state="ACTIVE"):
    heartbeat = heartbeat or (NOW - timedelta(minutes=40))
    acquired = heartbeat
    return {
        "schema_version": 1,
        "resource_key": "component:test_component",
        "generation": generation,
        "state": state,
        "work_id": WORK,
        "worker": {"kind": "chatgpt", "session_id": SESSION},
        "implementation_branch": f"work/{WORK}",
        "lease_id": lease_id,
        "base_sha": "1" * 40,
        "acquired_at": z(acquired),
        "heartbeat_at": z(heartbeat),
        "expires_at": z(heartbeat + timedelta(hours=4)),
        "runtime_control_authority": "NONE",
    }


def v2_takeover(*, generation=2, lease_id=LEASE_B, acquired=NOW):
    return {
        "schema_version": 2,
        "resource_key": "component:test_component",
        "generation": generation,
        "state": "ACTIVE",
        "work_id": WORK,
        "worker": {"kind": "chatgpt", "session_id": SESSION},
        "implementation_branch": f"work/{WORK}",
        "lease_id": lease_id,
        "base_sha": "1" * 40,
        "acquired_at": z(acquired),
        "heartbeat_at": z(acquired),
        "expires_at": z(acquired + timedelta(seconds=1800)),
        "lease_contract": "COMPONENT_1800",
        "lease_event_type": "TAKEOVER",
        "runtime_control_authority": "NONE",
    }


class WorkFenceLockMigrationTests(unittest.TestCase):
    def test_legacy_v1_effective_expiry_uses_last_heartbeat(self):
        lock = v1(heartbeat=NOW - timedelta(minutes=10))
        self.assertEqual(mod.effective_expiry(lock, protocol()), NOW + timedelta(minutes=20))

    def test_same_work_takeover_is_valid_with_new_lease_and_generation(self):
        previous = v1(heartbeat=NOW - timedelta(minutes=40))
        current = v2_takeover()
        mod.validate_snapshot(previous, protocol())
        mod.validate_snapshot(current, protocol())
        mod.validate_transition_semantics(previous, current, protocol())

    def test_takeover_reusing_lease_is_rejected(self):
        previous = v1(heartbeat=NOW - timedelta(minutes=40))
        current = v2_takeover(lease_id=LEASE_A)
        with self.assertRaises(mod.ValidationError):
            mod.validate_transition_semantics(previous, current, protocol())

    def test_post_cutover_active_v1_snapshot_is_rejected(self):
        lock = v1(heartbeat=NOW)
        with self.assertRaises(mod.ValidationError):
            mod.validate_versioned_snapshot(lock, NOW, protocol(), NOW - timedelta(seconds=1))

    def test_pre_cutover_active_v1_snapshot_remains_valid_history(self):
        lock = v1(heartbeat=NOW - timedelta(minutes=10))
        mod.validate_versioned_snapshot(lock, NOW - timedelta(minutes=1), protocol(), NOW)


if __name__ == "__main__":
    unittest.main()
