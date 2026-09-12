from __future__ import annotations

import importlib.util
import json
import tempfile
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
            "lock/589445284f78e3b05558c8f57e9d4c85bf3204df6066ec0209640b9472368820",
        )

    def test_uuid4_rejects_non_v4(self):
        self.assertIsNone(mod.UUID4_RE.fullmatch("00000000-0000-3000-8000-000000000000"))
        self.assertIsNotNone(mod.UUID4_RE.fullmatch("00000000-0000-4000-8000-000000000000"))

    def test_protocol_current_file_validates(self):
        protocol = json.loads((Path(__file__).resolve().parents[1] / "coordination" / "protocol.json").read_text())
        mod.validate_protocol(protocol)

    def test_worker_requires_exact_keys(self):
        with self.assertRaises(mod.ValidationError):
            mod.validate_worker({"kind": "chatgpt", "session_id": "00000000-0000-4000-8000-000000000000", "extra": 1})


if __name__ == "__main__":
    unittest.main()
