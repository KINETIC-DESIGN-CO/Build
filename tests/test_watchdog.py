import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate_watchdog.py"
spec = importlib.util.spec_from_file_location("validate_watchdog", MODULE_PATH)
vw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vw)

BASE_SPEC = json.loads((ROOT / "watchdog" / "spec.json").read_text())
BASE_REGISTRY = json.loads((ROOT / "watchdog" / "finding-registry.json").read_text())

class WatchdogValidationTests(unittest.TestCase):
    def test_canonical_package_validates(self):
        self.assertTrue(vw.validate())

    def test_self_audit_cannot_mutate_task_prompt(self):
        broken = copy.deepcopy(BASE_SPEC)
        broken["self_audit"]["task_prompt_mutation"] = "ALLOWED"
        with self.assertRaises(vw.ValidationError):
            vw.validate_spec(broken)

    def test_self_audit_cannot_expand_authority(self):
        broken = copy.deepcopy(BASE_SPEC)
        broken["self_audit"]["authority_expansion"] = "ALLOWED"
        with self.assertRaises(vw.ValidationError):
            vw.validate_spec(broken)

    def test_issue_mutation_initially_disabled(self):
        broken = copy.deepcopy(BASE_SPEC)
        broken["issue_mutation"]["mode"] = "ENABLED"
        with self.assertRaises(vw.ValidationError):
            vw.validate_spec(broken)

    def test_hourly_and_deep_schedule_are_exact(self):
        broken = copy.deepcopy(BASE_SPEC)
        broken["schedule"]["deep_audit_local_hours"] = [2]
        with self.assertRaises(vw.ValidationError):
            vw.validate_spec(broken)

    def test_executor_contract_is_exact(self):
        broken = copy.deepcopy(BASE_SPEC)
        broken["self_audit"]["executor_contract_id"] = "other"
        with self.assertRaises(vw.ValidationError):
            vw.validate_spec(broken)

    def test_unregistered_predicate_operator_fails(self):
        broken = copy.deepcopy(BASE_REGISTRY)
        broken["findings"][0]["fail_predicate"]["op"] = "MODEL_JUDGMENT"
        with self.assertRaises(vw.ValidationError):
            vw.validate_registry(broken, BASE_SPEC)

    def test_duplicate_finding_id_fails(self):
        broken = copy.deepcopy(BASE_REGISTRY)
        broken["findings"][1]["finding_type_id"] = broken["findings"][0]["finding_type_id"]
        with self.assertRaises(vw.ValidationError):
            vw.validate_registry(broken, BASE_SPEC)

    def test_required_findings_are_mandatory(self):
        broken = copy.deepcopy(BASE_REGISTRY)
        broken["findings"] = [f for f in broken["findings"] if f["finding_type_id"] != "MERGE_TIME_INTEGRATION_FRESHNESS_GAP"]
        with self.assertRaises(vw.ValidationError):
            vw.validate_registry(broken, BASE_SPEC)

    def test_external_mutation_boundaries_fail_closed(self):
        for key in ["supabase","vercel","runtime","continuity","coordination_claims","project_instructions"]:
            with self.subTest(key=key):
                broken = copy.deepcopy(BASE_SPEC)
                broken["mutation_boundary"][key] = "ALLOWED"
                with self.assertRaises(vw.ValidationError):
                    vw.validate_spec(broken)

if __name__ == "__main__":
    unittest.main()
