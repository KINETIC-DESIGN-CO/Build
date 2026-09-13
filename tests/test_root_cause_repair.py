import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate_root_cause_repair.py"
spec = importlib.util.spec_from_file_location("validate_root_cause_repair", MODULE_PATH)
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

BASE_POLICY = json.loads((ROOT / "governance" / "root-cause-repair-policy.json").read_text())
BASE_REGISTRY = json.loads((ROOT / "governance" / "root-cause-repairs.json").read_text())
POLICY_SCHEMA = json.loads((ROOT / "governance" / "schema" / "root-cause-repair-policy.schema.json").read_text())
REGISTRY_SCHEMA = json.loads((ROOT / "governance" / "schema" / "root-cause-repairs.schema.json").read_text())


class RootCauseRepairTests(unittest.TestCase):
    def test_canonical_package_validates(self):
        self.assertTrue(rc.validate())

    def test_patch_only_shortcut_cannot_be_removed(self):
        broken = copy.deepcopy(BASE_POLICY)
        broken["forbidden_terminal_shortcuts"].remove("PATCH_EXPECTED_LITERAL_ONLY")
        with self.assertRaises(rc.RootCauseError):
            rc.validate_policy(broken, POLICY_SCHEMA)

    def test_mutable_state_fixture_rule_is_mandatory(self):
        broken = copy.deepcopy(BASE_POLICY)
        broken["test_isolation_rule"] = "ALLOW_CURRENT_PRODUCTION_SNAPSHOT_AS_EXPECTED_VALUE"
        with self.assertRaises(rc.RootCauseError):
            rc.validate_policy(broken, POLICY_SCHEMA)

    def test_manual_derived_copy_cannot_be_selected_repair(self):
        broken = copy.deepcopy(BASE_POLICY)
        broken["derived_state_rule"] = "REFRESH_STORED_HASH_AFTER_SOURCE_CHANGES"
        with self.assertRaises(rc.RootCauseError):
            rc.validate_policy(broken, POLICY_SCHEMA)

    def test_unknown_origin_requires_blocked_state(self):
        broken = copy.deepcopy(BASE_REGISTRY)
        broken["repairs"][0]["origin_commit_refs"] = ["UNKNOWN"]
        with self.assertRaises(rc.RootCauseError):
            rc.validate_registry(broken, REGISTRY_SCHEMA)

    def test_verified_fixed_requires_final_machine_verification(self):
        broken = copy.deepcopy(BASE_REGISTRY)
        broken["repairs"][0]["state"] = "VERIFIED_FIXED"
        broken["repairs"][0]["verification_state"] = "PENDING_REQUIRED_CI_AND_PROTECTED_INTEGRATION"
        with self.assertRaises(rc.RootCauseError):
            rc.validate_registry(broken, REGISTRY_SCHEMA)

    def test_dispositions_are_closed_to_architecture_actions(self):
        broken = copy.deepcopy(BASE_REGISTRY)
        broken["repairs"][0]["selected_dispositions"] = ["PATCH_THE_TEST"]
        with self.assertRaises(rc.RootCauseError):
            rc.validate_registry(broken, REGISTRY_SCHEMA)

    def test_failure_cannot_lose_origin_or_history_trace(self):
        for key in ("origin_commit_refs", "history_evidence_refs"):
            with self.subTest(key=key):
                broken = copy.deepcopy(BASE_REGISTRY)
                broken["repairs"][0][key] = []
                with self.assertRaises(rc.RootCauseError):
                    rc.validate_registry(broken, REGISTRY_SCHEMA)


if __name__ == "__main__":
    unittest.main()
