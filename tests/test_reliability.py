import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReliabilityTests(unittest.TestCase):
    def run_validator(self, root):
        return subprocess.run(
            ["python", "scripts/validate_reliability.py"],
            cwd=root,
            text=True,
            capture_output=True,
        )

    def copy_repo(self):
        td = tempfile.TemporaryDirectory()
        dst = Path(td.name) / "repo"
        shutil.copytree(ROOT, dst)
        return td, dst

    def write_json(self, path, obj):
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")

    def assert_rejected(self, result, code):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(code, result.stderr)

    def test_current_reliability_contract_is_valid(self):
        result = self.run_validator(ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RELIABILITY_VALID", result.stdout)

    def test_zero_retry_budget_cannot_hide_retryable_states(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "reliability/operation-catalog.json"
            obj = json.loads(path.read_text())
            op = next(row for row in obj["operation_contracts"] if row["operation_contract_id"] == "ROP-0002")
            op["retryable_attempt_result_states"] = ["TIMEOUT"]
            self.write_json(path, obj)
            self.assert_rejected(self.run_validator(dst), "R006_OPERATION")
        finally:
            td.cleanup()

    def test_operation_cannot_reference_missing_postcondition(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "reliability/operation-catalog.json"
            obj = json.loads(path.read_text())
            obj["operation_contracts"][0]["postcondition_ids"] = ["RPOST-9999"]
            self.write_json(path, obj)
            self.assert_rejected(self.run_validator(dst), "R006_OPERATION")
        finally:
            td.cleanup()

    def test_timeout_with_unknown_effect_requires_verification_before_retry(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "reliability/recovery-policy.json"
            obj = json.loads(path.read_text())
            rule = next(row for row in obj["rules"] if row["rule_id"] == "RREC-0003")
            rule["disposition"] = "RETRY"
            self.write_json(path, obj)
            self.assert_rejected(self.run_validator(dst), "R008_FALSIFICATION")
        finally:
            td.cleanup()

    def test_transport_success_cannot_override_failed_postcondition(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "reliability/recovery-policy.json"
            obj = json.loads(path.read_text())
            rule = next(row for row in obj["rules"] if row["rule_id"] == "RREC-0008")
            rule["disposition"] = "ACCEPT_EFFECT"
            self.write_json(path, obj)
            self.assert_rejected(self.run_validator(dst), "R008_FALSIFICATION")
        finally:
            td.cleanup()

    def test_unreadable_non_idempotent_unknown_effect_cannot_retry(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "reliability/recovery-policy.json"
            obj = json.loads(path.read_text())
            rule = next(row for row in obj["rules"] if row["rule_id"] == "RREC-0004")
            rule["disposition"] = "RETRY"
            self.write_json(path, obj)
            self.assert_rejected(self.run_validator(dst), "R008_FALSIFICATION")
        finally:
            td.cleanup()

    def test_fallback_must_fail_closed_to_abort(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "reliability/recovery-policy.json"
            obj = json.loads(path.read_text())
            rule = next(row for row in obj["rules"] if row["rule_id"] == "RREC-9999")
            rule["disposition"] = "RETRY"
            self.write_json(path, obj)
            self.assert_rejected(self.run_validator(dst), "R007_RECOVERY")
        finally:
            td.cleanup()

    def test_parent_restoration_cannot_be_replaced_by_accept_effect(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "reliability/recovery-policy.json"
            obj = json.loads(path.read_text())
            rule = next(row for row in obj["rules"] if row["rule_id"] == "RREC-0001")
            rule["disposition"] = "ACCEPT_EFFECT"
            self.write_json(path, obj)
            self.assert_rejected(self.run_validator(dst), "R008_FALSIFICATION")
        finally:
            td.cleanup()

    def test_semantic_firewall_link_cannot_regress_to_pre_import_state(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "reliability/spec.json"
            obj = json.loads(path.read_text())
            obj["cross_links"]["semantic_firewall_contract_path"] = None
            obj["cross_links"]["semantic_firewall_link_state"] = "PENDING_MIGRATION"
            self.write_json(path, obj)
            self.assert_rejected(self.run_validator(dst), "R001_SCHEMA")
        finally:
            td.cleanup()

    def test_goal_identity_active_owner_must_be_canonical_registry(self):
        td, dst = self.copy_repo()
        try:
            spec_path = dst / "reliability/spec.json"
            spec = json.loads(spec_path.read_text())
            spec["cross_links"]["goal_root_identity_owner_path"] = "governance/work-selection-policy.json"
            self.write_json(spec_path, spec)
            self.assert_rejected(self.run_validator(dst), "R004_SOURCE_LINK")
        finally:
            td.cleanup()

    def test_goal_identity_state_must_match_across_artifacts(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "reliability/compatibility-map.json"
            obj = json.loads(path.read_text())
            obj["goal_identity"]["relationship"] = "COMBINE_PENDING_GOAL_OWNER_IMPLEMENTATION"
            obj["goal_identity"]["current_owner_path"] = None
            obj["goal_identity"]["state"] = "PENDING_IMPLEMENTATION"
            self.write_json(path, obj)
            self.assert_rejected(self.run_validator(dst), "R009_COMPATIBILITY")
        finally:
            td.cleanup()

    def test_active_goal_identity_cannot_use_pending_relationship(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "reliability/compatibility-map.json"
            obj = json.loads(path.read_text())
            obj["goal_identity"]["relationship"] = "COMBINE_PENDING_GOAL_OWNER_IMPLEMENTATION"
            self.write_json(path, obj)
            self.assert_rejected(self.run_validator(dst), "R009_COMPATIBILITY")
        finally:
            td.cleanup()

    def test_duplicate_invariant_identity_is_rejected(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "reliability/invariants.json"
            obj = json.loads(path.read_text())
            obj["invariants"][1]["invariant_id"] = obj["invariants"][0]["invariant_id"]
            self.write_json(path, obj)
            self.assert_rejected(self.run_validator(dst), "R002_DUPLICATE_ID")
        finally:
            td.cleanup()

    def test_unreadable_state_change_must_have_zero_retry_budget(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "reliability/operation-catalog.json"
            obj = json.loads(path.read_text())
            op = next(row for row in obj["operation_contracts"] if row["operation_contract_id"] == "ROP-0004")
            op["retry_budget"] = 1
            op["retryable_attempt_result_states"] = ["TIMEOUT"]
            self.write_json(path, obj)
            self.assert_rejected(self.run_validator(dst), "R006_OPERATION")
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
