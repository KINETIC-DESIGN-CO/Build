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
        return subprocess.run(
            ["python", "scripts/validate_semantic_firewall_conformance.py"],
            cwd=root,
            text=True,
            capture_output=True,
        )

    def write_json(self, path: Path, value):
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")

    def test_canonical_rule_registry_conforms(self):
        result = self.run_validator(ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SEMANTIC_FIREWALL_CONFORMANCE_VALID", result.stdout)

    def test_new_policy_surface_cannot_bypass_registry(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "governance" / "future-policy.json"
            path.write_text('{"runtime_control_authority":"NONE"}\n')
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFC006_DISCOVERY", result.stderr)
            self.assertIn("governance/future-policy.json", result.stderr)
        finally:
            td.cleanup()

    def test_enforced_surface_cannot_drop_deterministic_consumer(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "contracts" / "semantic-firewall-v1" / "rule-registry.json"
            registry = json.loads(path.read_text())
            target = next(surface for surface in registry["surfaces"] if surface["path"] == "governance/work-selection-policy.json")
            target["deterministic_consumer_paths"] = []
            self.write_json(path, registry)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFC013_ENFORCEMENT", result.stderr)
        finally:
            td.cleanup()

    def test_source_only_surface_may_explicitly_lack_consumer(self):
        registry = json.loads((ROOT / "contracts" / "semantic-firewall-v1" / "rule-registry.json").read_text())
        target = next(surface for surface in registry["surfaces"] if surface["path"] == "governance/problem-intake-policy.json")
        self.assertEqual("SOURCE_ONLY", target["enforcement_state"])
        self.assertEqual([], target["deterministic_consumer_paths"])

    def test_unsafe_source_cannot_directly_feed_control_gate(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "contracts" / "semantic-firewall-v1" / "rule-registry.json"
            registry = json.loads(path.read_text())
            target = next(surface for surface in registry["surfaces"] if surface["path"] == "governance/work-selection-policy.json")
            target["permitted_evidence_source_classes"].append("MODEL_RESPONSE")
            self.write_json(path, registry)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SFC012_UNSAFE_SOURCE", result.stderr)
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
