from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_coordination.py"
spec = importlib.util.spec_from_file_location("validate_coordination_claim_scope", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

WORK_ID = "00000000-0000-4000-8000-000000000101"
SESSION_ID = "00000000-0000-4000-8000-000000000102"
LEASE_ID = "00000000-0000-4000-8000-000000000103"


def claim(resource_key: str, lease_id: str = LEASE_ID) -> dict:
    return {
        "resource_key": resource_key,
        "lock_branch": mod.expected_lock_branch(resource_key),
        "lease_id": lease_id,
        "generation": 1,
    }


def base_record() -> dict:
    return {
        "schema_version": 1,
        "work_id": WORK_ID,
        "title": "claim scope test",
        "worker": {"kind": "chatgpt", "session_id": SESSION_ID},
        "implementation_branch": f"work/{WORK_ID}",
        "base_sha": "1" * 40,
        "component_id": "claim_scope_test",
        "repo_paths": ["src/a.py", "src/b.py"],
        "external_targets": [],
        "claims": [claim("component:claim_scope_test")],
        "runtime_control_authority": "NONE",
    }


class ClaimScopeTests(unittest.TestCase):
    def test_changed_repository_paths_do_not_require_file_leases(self):
        record = base_record()
        completed = type("P", (), {"returncode": 0})()
        changed = ["src/a.py", "src/b.py", f"coordination/work/{WORK_ID}.json"]
        with patch.object(mod.subprocess, "run", return_value=completed):
            mod.validate_work_record(record, changed, f"work/{WORK_ID}", "2" * 40)

    def test_component_claim_remains_required(self):
        record = base_record()
        record["claims"] = []
        completed = type("P", (), {"returncode": 0})()
        changed = ["src/a.py", "src/b.py", f"coordination/work/{WORK_ID}.json"]
        with patch.object(mod.subprocess, "run", return_value=completed):
            with self.assertRaises(mod.ValidationError):
                mod.validate_work_record(record, changed, f"work/{WORK_ID}", "2" * 40)

    def test_declared_external_target_requires_exact_claim(self):
        record = base_record()
        record["external_targets"] = ["external:example:shared"]
        completed = type("P", (), {"returncode": 0})()
        changed = ["src/a.py", "src/b.py", f"coordination/work/{WORK_ID}.json"]
        with patch.object(mod.subprocess, "run", return_value=completed):
            with self.assertRaises(mod.ValidationError):
                mod.validate_work_record(record, changed, f"work/{WORK_ID}", "2" * 40)

        record["claims"].append(
            claim("external:example:shared", "00000000-0000-4000-8000-000000000104")
        )
        record["claims"] = sorted(record["claims"], key=lambda item: item["resource_key"])
        with patch.object(mod.subprocess, "run", return_value=completed):
            mod.validate_work_record(record, changed, f"work/{WORK_ID}", "2" * 40)

    def test_legacy_repo_file_claim_remains_accepted_but_optional(self):
        record = base_record()
        record["claims"].append(
            claim("repo-file:src/a.py", "00000000-0000-4000-8000-000000000105")
        )
        record["claims"] = sorted(record["claims"], key=lambda item: item["resource_key"])
        completed = type("P", (), {"returncode": 0})()
        changed = ["src/a.py", "src/b.py", f"coordination/work/{WORK_ID}.json"]
        with patch.object(mod.subprocess, "run", return_value=completed):
            mod.validate_work_record(record, changed, f"work/{WORK_ID}", "2" * 40)


if __name__ == "__main__":
    unittest.main()
