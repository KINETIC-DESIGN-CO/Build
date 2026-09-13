from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_lock_history.py"
spec = importlib.util.spec_from_file_location("validate_lock_history", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

PROTOCOL = {
    "protocol_id": "life-source-coordination-v2",
    "lease_duration_seconds": 14400,
    "renew_when_remaining_seconds_lte": 1800,
    "lock_history_enforcement_start_utc": "2026-09-12T22:56:23Z",
}
WORK_A = "00000000-0000-4000-8000-000000000001"
WORK_B = "00000000-0000-4000-8000-000000000002"
LEASE_A = "00000000-0000-4000-8000-000000000003"
LEASE_B = "00000000-0000-4000-8000-000000000004"
SESSION_A = "00000000-0000-4000-8000-000000000005"
SESSION_B = "00000000-0000-4000-8000-000000000006"


def z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lock(
    *,
    state="ACTIVE",
    generation=1,
    work_id=WORK_A,
    lease_id=LEASE_A,
    session_id=SESSION_A,
    acquired=datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc),
    heartbeat=None,
    expires=None,
    base_sha="1" * 40,
):
    heartbeat = heartbeat or acquired
    expires = expires or (heartbeat + timedelta(seconds=PROTOCOL["lease_duration_seconds"]))
    return {
        "schema_version": 1,
        "resource_key": "repo-file:a",
        "generation": generation,
        "state": state,
        "work_id": work_id,
        "worker": {"kind": "chatgpt", "session_id": session_id},
        "implementation_branch": f"work/{work_id}",
        "lease_id": lease_id,
        "base_sha": base_sha,
        "acquired_at": z(acquired),
        "heartbeat_at": z(heartbeat),
        "expires_at": z(expires),
        "runtime_control_authority": "NONE",
    }


def entry(lock_value: dict, committed_at: datetime, sha_char: str) -> dict:
    return {
        "commit_sha": sha_char * 40,
        "committed_at": committed_at,
        "lock": lock_value,
    }


class LockHistoryTests(unittest.TestCase):
    def test_initial_active_generation_one_valid(self):
        mod.validate_history([lock()], PROTOCOL)

    def test_invalid_duration_fails(self):
        value = lock()
        value["expires_at"] = z(datetime(2026, 9, 12, 11, 59, 59, tzinfo=timezone.utc))
        with self.assertRaises(mod.ValidationError):
            mod.validate_snapshot(value, PROTOCOL)

    def test_valid_release_changes_only_state(self):
        previous = lock()
        current = dict(previous)
        current["state"] = "RELEASED"
        mod.validate_transition(previous, current, PROTOCOL)

    def test_release_cannot_change_owner(self):
        previous = lock()
        current = dict(previous)
        current["state"] = "RELEASED"
        current["lease_id"] = LEASE_B
        with self.assertRaises(mod.ValidationError):
            mod.validate_transition(previous, current, PROTOCOL)

    def test_valid_reacquisition_after_release(self):
        previous = lock(state="RELEASED")
        acquired = datetime(2026, 9, 12, 9, 0, tzinfo=timezone.utc)
        current = lock(
            generation=2,
            work_id=WORK_B,
            lease_id=LEASE_B,
            session_id=SESSION_B,
            acquired=acquired,
            base_sha="2" * 40,
        )
        mod.validate_transition(previous, current, PROTOCOL)

    def test_reacquisition_skipped_generation_fails(self):
        previous = lock(state="RELEASED")
        current = lock(
            generation=3,
            work_id=WORK_B,
            lease_id=LEASE_B,
            session_id=SESSION_B,
            acquired=datetime(2026, 9, 12, 9, 0, tzinfo=timezone.utc),
        )
        with self.assertRaises(mod.ValidationError):
            mod.validate_transition(previous, current, PROTOCOL)

    def test_reacquisition_reused_lease_fails(self):
        previous = lock(state="RELEASED")
        current = lock(
            generation=2,
            work_id=WORK_B,
            lease_id=LEASE_A,
            session_id=SESSION_B,
            acquired=datetime(2026, 9, 12, 9, 0, tzinfo=timezone.utc),
        )
        with self.assertRaises(mod.ValidationError):
            mod.validate_transition(previous, current, PROTOCOL)

    def test_valid_renewal_inside_window(self):
        previous = lock()
        heartbeat = datetime(2026, 9, 12, 11, 30, tzinfo=timezone.utc)
        current = lock(
            acquired=datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc),
            heartbeat=heartbeat,
            expires=heartbeat + timedelta(seconds=14400),
        )
        mod.validate_transition(previous, current, PROTOCOL)

    def test_renewal_too_early_fails(self):
        previous = lock()
        heartbeat = datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc)
        current = lock(
            acquired=datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc),
            heartbeat=heartbeat,
            expires=heartbeat + timedelta(seconds=14400),
        )
        with self.assertRaises(mod.ValidationError):
            mod.validate_transition(previous, current, PROTOCOL)

    def test_malformed_renewal_changes_base_fails(self):
        previous = lock()
        heartbeat = datetime(2026, 9, 12, 11, 30, tzinfo=timezone.utc)
        current = lock(
            acquired=datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc),
            heartbeat=heartbeat,
            expires=heartbeat + timedelta(seconds=14400),
            base_sha="2" * 40,
        )
        with self.assertRaises(mod.ValidationError):
            mod.validate_transition(previous, current, PROTOCOL)

    def test_valid_takeover_after_expiry(self):
        previous = lock()
        acquired = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
        current = lock(
            generation=2,
            work_id=WORK_B,
            lease_id=LEASE_B,
            session_id=SESSION_B,
            acquired=acquired,
            base_sha="2" * 40,
        )
        mod.validate_transition(previous, current, PROTOCOL)

    def test_premature_takeover_fails(self):
        previous = lock()
        current = lock(
            generation=2,
            work_id=WORK_B,
            lease_id=LEASE_B,
            session_id=SESSION_B,
            acquired=datetime(2026, 9, 12, 11, 59, 59, tzinfo=timezone.utc),
        )
        with self.assertRaises(mod.ValidationError):
            mod.validate_transition(previous, current, PROTOCOL)

    def test_takeover_same_generation_fails(self):
        previous = lock()
        current = lock(
            generation=1,
            work_id=WORK_B,
            lease_id=LEASE_B,
            session_id=SESSION_B,
            acquired=datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc),
        )
        with self.assertRaises(mod.ValidationError):
            mod.validate_transition(previous, current, PROTOCOL)

    def test_released_to_released_fails(self):
        previous = lock(state="RELEASED")
        current = dict(previous)
        with self.assertRaises(mod.ValidationError):
            mod.validate_transition(previous, current, PROTOCOL)

    def test_pre_epoch_legacy_base_rewrite_is_retained_as_evidence(self):
        first = lock(base_sha="1" * 40)
        second = dict(first)
        second["base_sha"] = "2" * 40
        mod.validate_versioned_history(
            [
                entry(first, datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc), "a"),
                entry(second, datetime(2026, 9, 12, 9, 0, tzinfo=timezone.utc), "b"),
            ],
            PROTOCOL,
        )

    def test_post_epoch_same_lease_base_rewrite_is_rejected(self):
        first = lock(base_sha="1" * 40)
        second = dict(first)
        second["base_sha"] = "2" * 40
        with self.assertRaises(mod.ValidationError):
            mod.validate_versioned_history(
                [
                    entry(first, datetime(2026, 9, 12, 22, 55, tzinfo=timezone.utc), "a"),
                    entry(second, datetime(2026, 9, 12, 22, 57, tzinfo=timezone.utc), "b"),
                ],
                PROTOCOL,
            )

    def test_post_epoch_release_from_pre_epoch_baseline_is_enforced(self):
        first = lock()
        second = dict(first)
        second["state"] = "RELEASED"
        mod.validate_versioned_history(
            [
                entry(first, datetime(2026, 9, 12, 22, 55, tzinfo=timezone.utc), "a"),
                entry(second, datetime(2026, 9, 12, 22, 57, tzinfo=timezone.utc), "b"),
            ],
            PROTOCOL,
        )

    def test_pre_epoch_non_uuid_session_is_legacy_evidence(self):
        legacy = lock()
        legacy["worker"] = {"kind": "chatgpt", "session_id": "legacy-session"}
        mod.validate_versioned_history(
            [entry(legacy, datetime(2026, 9, 12, 22, 55, tzinfo=timezone.utc), "a")],
            PROTOCOL,
        )

    def test_post_epoch_non_uuid_session_is_rejected(self):
        invalid = lock()
        invalid["worker"] = {"kind": "chatgpt", "session_id": "legacy-session"}
        with self.assertRaises(mod.ValidationError):
            mod.validate_versioned_history(
                [entry(invalid, datetime(2026, 9, 12, 22, 57, tzinfo=timezone.utc), "a")],
                PROTOCOL,
            )

    def test_pre_epoch_empty_lock_branch_is_legacy_namespace(self):
        mod.validate_empty_branch_tip(
            datetime(2026, 9, 12, 22, 55, tzinfo=timezone.utc),
            PROTOCOL,
        )

    def test_post_epoch_empty_lock_branch_is_rejected(self):
        with self.assertRaises(mod.ValidationError):
            mod.validate_empty_branch_tip(
                datetime(2026, 9, 12, 22, 57, tzinfo=timezone.utc),
                PROTOCOL,
            )


if __name__ == "__main__":
    unittest.main()
