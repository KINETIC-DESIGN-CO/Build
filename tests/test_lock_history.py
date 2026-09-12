from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_lock_history.py"
spec = importlib.util.spec_from_file_location("validate_lock_history", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

DURATION = 14400
RENEW = 1800
WORK_A = "00000000-0000-4000-8000-000000000001"
WORK_B = "00000000-0000-4000-8000-000000000002"
LEASE_A = "10000000-0000-4000-8000-000000000001"
LEASE_B = "10000000-0000-4000-8000-000000000002"
SESSION = "20000000-0000-4000-8000-000000000001"
BASE = "a" * 40


def snap(*, generation=1, state="ACTIVE", work_id=WORK_A, lease_id=LEASE_A,
         acquired="2026-09-12T08:00:00Z", heartbeat="2026-09-12T08:00:00Z",
         expires="2026-09-12T12:00:00Z"):
    return {
        "schema_version": 1,
        "resource_key": "repo-file:example.txt",
        "generation": generation,
        "state": state,
        "work_id": work_id,
        "worker": {"kind": "chatgpt", "session_id": SESSION},
        "implementation_branch": f"work/{work_id}",
        "lease_id": lease_id,
        "base_sha": BASE,
        "acquired_at": acquired,
        "heartbeat_at": heartbeat,
        "expires_at": expires,
        "runtime_control_authority": "NONE",
    }


class LockHistoryTests(unittest.TestCase):
    def test_initial_release_reacquire_is_valid(self):
        initial = snap()
        released = {**initial, "state": "RELEASED"}
        reacquired = snap(
            generation=2, work_id=WORK_B, lease_id=LEASE_B,
            acquired="2026-09-12T12:10:00Z", heartbeat="2026-09-12T12:10:00Z",
            expires="2026-09-12T16:10:00Z",
        )
        mod.validate_history([initial, released, reacquired], DURATION, RENEW)

    def test_renewal_inside_window_is_valid(self):
        initial = snap()
        renewed = snap(
            acquired="2026-09-12T08:00:00Z",
            heartbeat="2026-09-12T11:30:00Z",
            expires="2026-09-12T15:30:00Z",
        )
        mod.validate_history([initial, renewed], DURATION, RENEW)

    def test_takeover_at_exact_expiry_is_valid(self):
        initial = snap()
        takeover = snap(
            generation=2, work_id=WORK_B, lease_id=LEASE_B,
            acquired="2026-09-12T12:00:00Z", heartbeat="2026-09-12T12:00:00Z",
            expires="2026-09-12T16:00:00Z",
        )
        mod.validate_history([initial, takeover], DURATION, RENEW)

    def test_invalid_lease_duration_fails(self):
        bad = snap(expires="2026-09-12T11:59:59Z")
        with self.assertRaises(mod.LockHistoryError):
            mod.validate_history([bad], DURATION, RENEW)

    def test_skipped_generation_fails(self):
        initial = snap()
        released = {**initial, "state": "RELEASED"}
        bad = snap(
            generation=3, work_id=WORK_B, lease_id=LEASE_B,
            acquired="2026-09-12T12:10:00Z", heartbeat="2026-09-12T12:10:00Z",
            expires="2026-09-12T16:10:00Z",
        )
        with self.assertRaises(mod.LockHistoryError):
            mod.validate_history([initial, released, bad], DURATION, RENEW)

    def test_reused_lease_id_on_reacquire_fails(self):
        initial = snap()
        released = {**initial, "state": "RELEASED"}
        bad = snap(
            generation=2, work_id=WORK_B, lease_id=LEASE_A,
            acquired="2026-09-12T12:10:00Z", heartbeat="2026-09-12T12:10:00Z",
            expires="2026-09-12T16:10:00Z",
        )
        with self.assertRaises(mod.LockHistoryError):
            mod.validate_history([initial, released, bad], DURATION, RENEW)

    def test_premature_takeover_fails(self):
        initial = snap()
        bad = snap(
            generation=2, work_id=WORK_B, lease_id=LEASE_B,
            acquired="2026-09-12T11:59:59Z", heartbeat="2026-09-12T11:59:59Z",
            expires="2026-09-12T15:59:59Z",
        )
        with self.assertRaises(mod.LockHistoryError):
            mod.validate_history([initial, bad], DURATION, RENEW)

    def test_active_owner_replacement_without_generation_fails(self):
        initial = snap()
        bad = snap(
            generation=1, work_id=WORK_B, lease_id=LEASE_B,
            acquired="2026-09-12T08:00:00Z",
            heartbeat="2026-09-12T11:30:00Z",
            expires="2026-09-12T15:30:00Z",
        )
        with self.assertRaises(mod.LockHistoryError):
            mod.validate_history([initial, bad], DURATION, RENEW)

    def test_renewal_too_early_fails(self):
        initial = snap()
        bad = snap(
            acquired="2026-09-12T08:00:00Z",
            heartbeat="2026-09-12T10:00:00Z",
            expires="2026-09-12T14:00:00Z",
        )
        with self.assertRaises(mod.LockHistoryError):
            mod.validate_history([initial, bad], DURATION, RENEW)

    def test_release_may_change_only_state(self):
        initial = snap()
        bad = {**initial, "state": "RELEASED", "expires_at": "2026-09-12T12:00:01Z"}
        with self.assertRaises(mod.LockHistoryError):
            mod.validate_history([initial, bad], DURATION, RENEW)

    def test_released_to_released_fails(self):
        initial = snap()
        released = {**initial, "state": "RELEASED"}
        with self.assertRaises(mod.LockHistoryError):
            mod.validate_history([initial, released, dict(released)], DURATION, RENEW)


if __name__ == "__main__":
    unittest.main()
