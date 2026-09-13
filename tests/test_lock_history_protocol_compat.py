from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_lock_history.py"
spec = importlib.util.spec_from_file_location("validate_lock_history_protocol_compat", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def protocol(protocol_id: str, *, lease_duration_seconds: int = 14400) -> dict:
    return {
        "protocol_id": protocol_id,
        "lease_duration_seconds": lease_duration_seconds,
        "renew_when_remaining_seconds_lte": 1800,
        "lock_history_enforcement_start_utc": "2026-09-12T22:56:23Z",
    }


class LockHistoryProtocolCompatibilityTests(unittest.TestCase):
    def load(self, value: dict) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "protocol.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with mock.patch.object(mod, "PROTOCOL_PATH", path):
                return mod.load_protocol()

    def test_v2_protocol_remains_supported(self):
        self.assertEqual(self.load(protocol("life-source-coordination-v2"))["protocol_id"], "life-source-coordination-v2")

    def test_v3_protocol_is_supported_without_weakening_lease_contract(self):
        self.assertEqual(self.load(protocol("life-source-coordination-v3"))["protocol_id"], "life-source-coordination-v3")

    def test_unknown_protocol_version_fails_closed(self):
        with self.assertRaises(mod.ValidationError):
            self.load(protocol("life-source-coordination-v4"))

    def test_supported_protocol_with_wrong_lease_duration_still_fails(self):
        with self.assertRaises(mod.ValidationError):
            self.load(protocol("life-source-coordination-v3", lease_duration_seconds=14399))


if __name__ == "__main__":
    unittest.main()
