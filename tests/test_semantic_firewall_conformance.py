from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SemanticFirewallConformanceTests(unittest.TestCase):
    def copy_repo(self):
        td = tempfile.TemporaryDirectory()
        dst = Path(td.name) / "repo"
        shutil.copytree(ROOT, dst)
        return td, dst

    def run_validator(self, root: Path):
        return subprocess.run(["python", "scripts/validate_semantic_firewall_conformance.py"], cwd=root, text=True, capture_output=True)

    def write_json(self, path: Path, value):
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")

    def test_canonical_rule_registry_conforms(self):
        result = self.run_validator(ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SEMANTIC_FIREWALL_CONFORMANCE_VALID", result.stdout)

    def test_new_policy_surface_cannot_bypass_registry(self):
        td, dst = self.copy_repo()
        try:
            (dst / "governance" / "future-policy.json").write_text('{"runtime_control_authority":"NONE"}\n')
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFC006_DISCOVERY", result.stderr)
        finally:
            td.cleanup()

    def test_enforced_surface_cannot_drop_deterministic_consumer(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "contracts" / "semantic-firewall-v1" / "rule-registry.json"
            registry = json.loads(path.read_text())
            target = next(s for s in registry["surfaces"] if s["path"] == "governance/work-selection-policy.json")
            target["deterministic_consumer_paths"] = []
            self.write_json(path, registry)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFC013_ENFORCEMENT", result.stderr)
        finally:
            td.cleanup()

    def test_source_only_surface_may_explicitly_lack_consumer(self):
        registry = json.loads((ROOT / "contracts/semantic-firewall-v1" / "rule-registry.json").read_text())
        target = next(s for s in registry["surfaces"] if s["path"] == "governance/problem-intake-policy.json")
        self.assertEqual("SOURCE_ONLY", target["enforcement_state"])
        self.assertEqual([], target["deterministic_consumer_paths"])

    def test_unsafe_source_cannot_directly_feed_control_gate(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "contracts" / "semantic-firewall-v1" / "rule-registry.json"
            registry = json.loads(path.read_text())
            target = next(s for s in registry["surfaces"] if s["path"] == "governance/work-selection-policy.json")
            target["permitted_evidence_source_classes"].append("MODEL_RESPONSE")
            self.write_json(path, registry)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFC012_UNSAFE_SOURCE", result.stderr)
        finally:
            td.cleanup()

    def test_control_surface_cannot_omit_predicate_closure_binding(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "contracts" / "semantic-firewall-v1" / "predicate-registry.json"
            registry = json.loads(path.read_text())
            registry["surface_predicate_bindings"] = [row for row in registry["surface_predicate_bindings"] if row["path"] != "governance/work-selection-policy.json"]
            self.write_json(path, registry)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFC023_PREDICATE", result.stderr)
            self.assertIn("work-selection-policy.json", result.stderr)
        finally:
            td.cleanup()

    def test_executable_wrapper_does_not_make_undefined_qualitative_field_deterministic(self):
        td, dst = self.copy_repo()
        try:
            wrapper = dst / "scripts" / "undefined_qualitative_wrapper.py"
            wrapper.write_text('def should_release(record):\n    return record["change_is_material"]\n')
            rules_path = dst / "contracts" / "semantic-firewall-v1" / "rule-registry.json"
            rules = json.loads(rules_path.read_text())
            surface = next(s for s in rules["surfaces"] if s["path"] == "governance/work-selection-policy.json")
            surface["deterministic_consumer_paths"] = ["scripts/undefined_qualitative_wrapper.py"]
            self.write_json(rules_path, rules)
            predicates_path = dst / "contracts" / "semantic-firewall-v1" / "predicate-registry.json"
            predicates = json.loads(predicates_path.read_text())
            binding = next(b for b in predicates["surface_predicate_bindings"] if b["path"] == "governance/work-selection-policy.json")
            binding["evaluator_paths"] = ["scripts/undefined_qualitative_wrapper.py"]
            self.write_json(predicates_path, predicates)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFC024_PASSTHROUGH", result.stderr)
            self.assertIn("should_release", result.stderr)
        finally:
            td.cleanup()

    def test_typed_predicate_input_cannot_launder_model_provenance(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "contracts" / "semantic-firewall-v1" / "predicate-registry.json"
            registry = json.loads(path.read_text())
            registry["runtime_predicates"][0]["required_inputs"][0]["source_classes"] = ["MODEL_RESPONSE"]
            self.write_json(path, registry)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFC023_PREDICATE", result.stderr)
            self.assertIn("unsafe or empty provenance", result.stderr)
        finally:
            td.cleanup()

    def test_exact_typed_predicate_definitions_cover_threshold_time_set_hash_id_and_evaluator_ref(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "contracts" / "semantic-firewall-v1" / "predicate-registry.json"
            registry = json.loads(path.read_text())
            safe = ["IMMUTABLE_REPOSITORY"]
            registry["runtime_predicates"].extend([
                {"predicate_id":"SF-PRED-COUNT-GTE-V1","definition_kind":"EXPRESSION","decision_kinds":["PRIORITY"],"required_inputs":[{"name":"count","value_type":"INTEGER","semantic_type":"INTEGER_WITH_UNIT","source_classes":safe,"unit":"ITEMS","allowed_values":None,"derivation_predicate_id":None}],"expression":{"operator":"INTEGER_GTE","left_input":"count","right_value_type":"INTEGER","right_value_json":"3","unit":"ITEMS"},"evaluator_ref":None,"evaluator_config_json":None,"runtime_control_authority":"NONE"},
                {"predicate_id":"SF-PRED-TIME-GTE-V1","definition_kind":"EXPRESSION","decision_kinds":["STATE_TRANSITION"],"required_inputs":[{"name":"observed_at","value_type":"STRING","semantic_type":"TIMESTAMP_RFC3339","source_classes":safe,"unit":None,"allowed_values":None,"derivation_predicate_id":None}],"expression":{"operator":"TIMESTAMP_GTE","left_input":"observed_at","right_value_type":"STRING","right_value_json":"\"2026-09-14T00:00:00Z\"","unit":None},"evaluator_ref":None,"evaluator_config_json":None,"runtime_control_authority":"NONE"},
                {"predicate_id":"SF-PRED-SET-V1","definition_kind":"EXPRESSION","decision_kinds":["VERIFICATION"],"required_inputs":[{"name":"states","value_type":"STRING_SET","semantic_type":"STRING_SET","source_classes":safe,"unit":None,"allowed_values":None,"derivation_predicate_id":None}],"expression":{"operator":"SET_CONTAINS_ALL","left_input":"states","right_value_type":"STRING_SET","right_value_json":"[\"PASS\",\"READBACK\"]","unit":None},"evaluator_ref":None,"evaluator_config_json":None,"runtime_control_authority":"NONE"},
                {"predicate_id":"SF-PRED-HASH-V1","definition_kind":"EXPRESSION","decision_kinds":["VERIFICATION"],"required_inputs":[{"name":"digest","value_type":"SHA256","semantic_type":"SHA256","source_classes":safe,"unit":None,"allowed_values":None,"derivation_predicate_id":None}],"expression":{"operator":"EQ","left_input":"digest","right_value_type":"SHA256","right_value_json":"\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"","unit":None},"evaluator_ref":None,"evaluator_config_json":None,"runtime_control_authority":"NONE"},
                {"predicate_id":"SF-PRED-ID-V1","definition_kind":"EXPRESSION","decision_kinds":["AUTHORIZATION"],"required_inputs":[{"name":"owner_id","value_type":"STRING","semantic_type":"EXACT_ID","source_classes":safe,"unit":None,"allowed_values":None,"derivation_predicate_id":None}],"expression":{"operator":"EQ","left_input":"owner_id","right_value_type":"STRING","right_value_json":"\"owner-1\"","unit":None},"evaluator_ref":None,"evaluator_config_json":None,"runtime_control_authority":"NONE"},
                {"predicate_id":"SF-PRED-EVALUATOR-REF-V1","definition_kind":"EVALUATOR_REF","decision_kinds":["ROUTING"],"required_inputs":[{"name":"state","value_type":"STRING","semantic_type":"CLOSED_ENUM","source_classes":safe,"unit":None,"allowed_values":["A","B"],"derivation_predicate_id":None}],"expression":None,"evaluator_ref":"CANONICAL_ROUTE_EVALUATOR_V1","evaluator_config_json":"{\"states\":[\"A\",\"B\"]}","runtime_control_authority":"NONE"}
            ])
            self.write_json(path, registry)
            result = self.run_validator(dst)
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            td.cleanup()

    def test_cross_policy_semantic_firewall_path_must_be_current(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "reliability" / "compatibility-map.json"
            compatibility = json.loads(path.read_text())
            compatibility["semantic_firewall"]["current_contract_path"] = "contracts/semantic-firewall"
            self.write_json(path, compatibility)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFC022_CROSS_POLICY", result.stderr)
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
