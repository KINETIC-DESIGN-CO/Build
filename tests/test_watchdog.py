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
BASE_SOURCE_DOCS = vw.source_contract_documents_from_tree()


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

    def test_executor_prompt_contract_is_exact(self):
        broken = copy.deepcopy(BASE_SPEC)
        broken["self_audit"]["executor_prompt_template"] += " changed"
        with self.assertRaises(vw.ValidationError):
            vw.validate_spec(broken)

    def test_source_contract_paths_are_exact_and_manual_hashes_are_forbidden(self):
        broken = copy.deepcopy(BASE_SPEC)
        broken["self_audit"]["source_contract_paths"] = broken["self_audit"]["source_contract_paths"][1:]
        with self.assertRaises(vw.ValidationError):
            vw.validate_spec(broken)
        copied_hash = copy.deepcopy(BASE_SPEC)
        copied_hash["self_audit"]["source_contract_fingerprints"] = []
        with self.assertRaises(vw.ValidationError):
            vw.validate_spec(copied_hash)

    def test_non_authority_bootstrap_growth_does_not_require_hash_refresh(self):
        docs = copy.deepcopy(BASE_SOURCE_DOCS)
        docs["continuity/bootstrap.json"]["required_files"].append("future/versioned-source.json")
        self.assertTrue(vw.validate_source_contract_documents(docs))

    def test_bootstrap_repository_identity_drift_fails(self):
        docs = copy.deepcopy(BASE_SOURCE_DOCS)
        docs["continuity/bootstrap.json"]["canonical_repository"]["full_name"] = "other/repo"
        with self.assertRaises(vw.ValidationError):
            vw.validate_source_contract_documents(docs)

    def test_control_authority_drift_fails_structurally(self):
        for path in ["continuity/bootstrap.json", "continuity/response-contract.json", "coordination/protocol.json", "governance/placement-policy.json"]:
            with self.subTest(path=path):
                docs = copy.deepcopy(BASE_SOURCE_DOCS)
                docs[path]["runtime_control_authority"] = "MODEL_JUDGMENT"
                with self.assertRaises(vw.ValidationError):
                    vw.validate_source_contract_documents(docs)

    def test_response_contract_epoch_drift_fails(self):
        docs = copy.deepcopy(BASE_SOURCE_DOCS)
        docs["continuity/response-contract.json"]["schema_version"] = 1
        docs["continuity/response-contract.json"]["contract_id"] = "life-response-contract-v1"
        with self.assertRaises(vw.ValidationError):
            vw.validate_source_contract_documents(docs)

    def test_coordination_protocol_epoch_drift_fails(self):
        docs = copy.deepcopy(BASE_SOURCE_DOCS)
        docs["coordination/protocol.json"]["protocol_id"] = "life-source-coordination-v4"
        with self.assertRaises(vw.ValidationError):
            vw.validate_source_contract_documents(docs)

    def test_bootstrap_read_order_must_be_discoverable_in_required_files(self):
        docs = copy.deepcopy(BASE_SOURCE_DOCS)
        docs["continuity/bootstrap.json"]["required_read_order"].append("missing/from-required-files.json")
        with self.assertRaises(vw.ValidationError):
            vw.validate_source_contract_documents(docs)

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
        for key in ["supabase", "vercel", "runtime", "continuity", "coordination_claims", "project_instructions"]:
            with self.subTest(key=key):
                broken = copy.deepcopy(BASE_SPEC)
                broken["mutation_boundary"][key] = "ALLOWED"
                with self.assertRaises(vw.ValidationError):
                    vw.validate_spec(broken)


if __name__ == "__main__":
    unittest.main()
