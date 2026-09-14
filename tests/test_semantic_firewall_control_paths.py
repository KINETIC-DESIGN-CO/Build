from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SemanticFirewallControlPathTests(unittest.TestCase):
    def copy_repo(self):
        td = tempfile.TemporaryDirectory()
        dst = Path(td.name) / "repo"
        shutil.copytree(ROOT, dst)
        return td, dst

    def run_validator(self, root: Path):
        return subprocess.run(
            ["python", "scripts/validate_semantic_firewall_control_paths.py"],
            cwd=root,
            text=True,
            capture_output=True,
        )

    def write_json(self, path: Path, value):
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")

    def registry_path(self, root: Path) -> Path:
        return root / "contracts" / "semantic-firewall-v1" / "control-path-registry.json"

    def test_canonical_control_path_registry_conforms(self):
        result = self.run_validator(ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SEMANTIC_FIREWALL_CONTROL_PATHS_VALID", result.stdout)

    def test_control_path_schema_is_valid_draft_2020_12_source_schema(self):
        script_path = ROOT / "scripts" / "validate_continuity.py"
        spec = importlib.util.spec_from_file_location("life_validate_continuity_for_sfcp", script_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        schema_path = ROOT / "contracts" / "semantic-firewall-v1" / "control-path-registry.schema.json"
        schema = json.loads(schema_path.read_text())
        module.ERRORS.clear()
        module.validate_schema_definition(schema, "contracts/semantic-firewall-v1/control-path-registry.schema.json")
        self.assertEqual([], module.ERRORS)

    def test_issue_class_cannot_be_removed_from_universal_coverage(self):
        td, dst = self.copy_repo()
        try:
            path = self.registry_path(dst)
            registry = json.loads(path.read_text())
            registry["object_classes"] = [
                row for row in registry["object_classes"] if row["class_id"] != "GITHUB_ISSUE"
            ]
            self.write_json(path, registry)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFCP004_CLASSES", result.stderr)
        finally:
            td.cleanup()

    def test_issue_or_pr_prose_cannot_be_promoted_to_direct_control(self):
        for class_id in ("GITHUB_ISSUE", "GITHUB_PULL_REQUEST"):
            td, dst = self.copy_repo()
            try:
                path = self.registry_path(dst)
                registry = json.loads(path.read_text())
                row = next(item for item in registry["object_classes"] if item["class_id"] == class_id)
                row["direct_control_effect"] = "DETERMINISTIC_BRIDGE_ONLY"
                self.write_json(path, registry)
                result = self.run_validator(dst)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("SFCP008_UNSAFE_DYNAMIC_SOURCE", result.stderr)
            finally:
                td.cleanup()

    def test_new_protected_boundary_cannot_exist_without_control_path_owner(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "governance" / "work-fence-policy.json"
            policy = json.loads(path.read_text())
            policy["protected_boundaries"].append("FUTURE_PROTECTED_BOUNDARY")
            self.write_json(path, policy)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFCP007_BOUNDARY", result.stderr)
            self.assertIn("FUTURE_PROTECTED_BOUNDARY", result.stderr)
        finally:
            td.cleanup()

    def test_protected_boundary_cannot_have_multiple_canonical_class_owners(self):
        td, dst = self.copy_repo()
        try:
            path = self.registry_path(dst)
            registry = json.loads(path.read_text())
            issue = next(item for item in registry["object_classes"] if item["class_id"] == "GITHUB_ISSUE")
            issue["protected_boundaries"] = ["WORK_SELECTION_DISPATCH"]
            self.write_json(path, registry)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFCP007_BOUNDARY", result.stderr)
            self.assertIn("duplicates", result.stderr)
        finally:
            td.cleanup()

    def test_work_item_must_pass_admissions_and_dispatch_boundary(self):
        td, dst = self.copy_repo()
        try:
            path = self.registry_path(dst)
            registry = json.loads(path.read_text())
            row = next(item for item in registry["object_classes"] if item["class_id"] == "ADMITTED_WORK_ITEM")
            row["canonical_bridge_paths"] = ["governance/work-selection-policy.json"]
            self.write_json(path, registry)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFCP010_WORK_ITEM", result.stderr)
        finally:
            td.cleanup()

    def test_work_record_instance_class_cannot_drop_schema_or_mutation_boundary(self):
        td, dst = self.copy_repo()
        try:
            path = self.registry_path(dst)
            registry = json.loads(path.read_text())
            row = next(item for item in registry["object_classes"] if item["class_id"] == "WORK_RECORD_INSTANCE")
            row["schema_path"] = None
            row["protected_boundaries"] = []
            self.write_json(path, registry)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFCP010_WORK_ITEM", result.stderr)
        finally:
            td.cleanup()

    def test_runtime_effect_cannot_be_claimed_active_while_firewall_is_source_only(self):
        td, dst = self.copy_repo()
        try:
            path = self.registry_path(dst)
            registry = json.loads(path.read_text())
            row = next(item for item in registry["object_classes"] if item["class_id"] == "RUNTIME_EFFECT")
            row["enforcement_state"] = "RUNTIME_ACTIVE"
            self.write_json(path, registry)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFCP011_RUNTIME", result.stderr)
        finally:
            td.cleanup()

    def test_independent_ci_trust_cannot_be_self_asserted_by_source_registry(self):
        td, dst = self.copy_repo()
        try:
            path = self.registry_path(dst)
            registry = json.loads(path.read_text())
            row = next(item for item in registry["object_classes"] if item["class_id"] == "CI_TRUST_ROOT")
            row["enforcement_state"] = "CI_ENFORCED_INDEPENDENT"
            self.write_json(path, registry)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("source registry cannot self-assert independent CI trust", result.stderr)
        finally:
            td.cleanup()

    def test_issue_57_cannot_complete_while_runtime_or_independent_ci_paths_are_inactive(self):
        td, dst = self.copy_repo()
        try:
            admissions_path = dst / "governance" / "work-admissions.json"
            admissions = json.loads(admissions_path.read_text())
            item = next(row for row in admissions["items"] if row["work_item_id"] == "github-issue-57")
            item["state"] = "COMPLETE"
            self.write_json(admissions_path, admissions)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFCP012_COMPLETION", result.stderr)
            self.assertIn("cannot be COMPLETE", result.stderr)
        finally:
            td.cleanup()

    def test_completion_gate_cannot_be_weakened_in_registry(self):
        td, dst = self.copy_repo()
        try:
            path = self.registry_path(dst)
            registry = json.loads(path.read_text())
            registry["completion_gate"]["complete_requires_class_states"].pop("CI_TRUST_ROOT")
            self.write_json(path, registry)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFCP012_COMPLETION", result.stderr)
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
