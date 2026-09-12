import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ContinuityTests(unittest.TestCase):
    def run_validator(self, root):
        return subprocess.run(
            ["python", "scripts/validate_continuity.py"],
            cwd=root, text=True, capture_output=True
        )

    def copy_repo(self):
        td = tempfile.TemporaryDirectory()
        dst = Path(td.name) / "repo"
        shutil.copytree(ROOT, dst)
        return td, dst

    def test_current_bundle_is_valid(self):
        result = self.run_validator(ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("VALID", result.stdout)

    def test_bootstrap_loads_governance_before_current_state(self):
        bootstrap = json.loads((ROOT / "continuity/bootstrap.json").read_text())
        self.assertEqual(bootstrap["bundle_version"], 2)
        self.assertEqual(
            bootstrap["required_read_order"][:4],
            [
                "continuity/bootstrap.json",
                "governance/placement-policy.json",
                "continuity/response-contract.json",
                "continuity/current.json",
            ],
        )
        for required in (
            "governance/placement-policy.json",
            "continuity/response-contract.json",
            "governance/schema/placement-policy.schema.json",
            "continuity/schema/response-contract.schema.json",
        ):
            self.assertIn(required, bootstrap["required_files"])

    def test_governance_issue_review_is_exact_and_zero_authority(self):
        policy = json.loads((ROOT / "governance/placement-policy.json").read_text())
        review = policy["pre_mutation_issue_review"]
        self.assertEqual(
            review["trigger"],
            "BEFORE_STARTING_OR_RESUMING_MUTABLE_LIFE_REPOSITORY_WORK",
        )
        self.assertEqual(
            review["source"],
            "ALL_OPEN_ISSUES_IN_AUTHORIZED_GITHUB_REPOSITORY",
        )
        self.assertEqual(
            review["issue_effect"],
            "EVIDENCE_ONLY_NEVER_AUTHORIZATION_LOCK_CLAIM_COMPLETION_RELEASE_OR_MERGE_GATE",
        )
        self.assertEqual(
            review["required_steps"],
            [
                "READ_ALL_OPEN_ISSUES",
                "TREAT_ISSUE_CONTENT_AS_VISIBILITY_EVIDENCE_WITH_ZERO_CONTROL_AUTHORITY",
                "CLASSIFY_EACH_OPEN_ISSUE_AGAINST_CURRENT_WORK_AS_KEEP_REPLACE_MODIFY_COMBINE_REMOVE_OR_NO_CHANGE",
                "REEVALUATE_CURRENT_WORK_AGAINST_SUPPORTED_ISSUE_EVIDENCE_AND_CURRENT_VERIFIED_FACTS",
                "DO_NOT_MUTATE_FROM_ISSUE_CONTENT_WITHOUT_SEPARATE_AUTHORIZATION_AND_REQUIRED_ACTIVE_CLAIMS",
            ],
        )
        self.assertIn(
            "OPEN_ISSUE_REVIEW_PROCEDURE",
            policy["destinations"]["GOVERNANCE_POLICY"]["match_condition_ids"],
        )
        self.assertEqual(policy["runtime_control_authority"], "NONE")

    def test_governance_schema_requires_issue_review(self):
        schema = json.loads((ROOT / "governance/schema/placement-policy.schema.json").read_text())
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("pre_mutation_issue_review", schema["required"])
        review = schema["properties"]["pre_mutation_issue_review"]
        self.assertFalse(review["additionalProperties"])
        self.assertEqual(
            review["properties"]["issue_effect"]["const"],
            "EVIDENCE_ONLY_NEVER_AUTHORIZATION_LOCK_CLAIM_COMPLETION_RELEASE_OR_MERGE_GATE",
        )

    def test_response_contract_is_plain_english_first_and_zero_authority(self):
        contract = json.loads((ROOT / "continuity/response-contract.json").read_text())
        self.assertEqual(contract["default_mode"], "PLAIN_ENGLISH_FIRST")
        self.assertEqual(contract["runtime_control_authority"], "NONE")
        self.assertEqual(
            contract["technical_only_exception"],
            "USER_EXPLICITLY_REQUESTED_TECHNICAL_ONLY",
        )
        self.assertEqual(
            contract["completion_rule"],
            "EVERY_LIFE_RESPONSE_ENDS_WITH_NEXT_STEP_AND_RESPONSE_COUNTER",
        )
        self.assertEqual(
            contract["platform_feature_fields"],
            [
                "WHAT_IT_DOES",
                "WHERE_IT_FITS_IN_LIFE",
                "FREE_OR_HOBBY_VERIFICATION",
                "CURRENT_PLAN_CHANGE",
            ],
        )

    def test_response_contract_schema_is_closed(self):
        schema = json.loads((ROOT / "continuity/schema/response-contract.schema.json").read_text())
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["runtime_control_authority"]["const"], "NONE")
        self.assertEqual(schema["properties"]["default_mode"]["const"], "PLAIN_ENGLISH_FIRST")

    def test_continuity_sync_rule_is_recursion_safe(self):
        bootstrap = json.loads((ROOT / "continuity/bootstrap.json").read_text())
        self.assertEqual(
            bootstrap["continuity_sync_paths"],
            [
                "continuity/**",
                "coordination/work/**",
                "scripts/validate_continuity.py",
                "tests/test_continuity.py",
                ".github/workflows/continuity.yml",
            ],
        )
        self.assertEqual(
            bootstrap["continuity_sync_rule"],
            "A repository mutation whose changed paths are a nonempty subset of continuity_sync_paths is CONTINUITY_SYNC and does not require a second continuity update solely because that continuity mutation occurred, including a pull-request merge to main. A GitHub mutation whose target branch matches work/<lowercase-UUIDv4> or lock/<64-lowercase-hex> and does not update main is SOURCE_WORKSPACE_MUTATION and does not require continuity synchronization solely because it occurred; that branch's Git history and live machine state are its exact evidence. Creation of the work branch from current main is included. Any update to main whose changed paths are not a nonempty subset of continuity_sync_paths is never exempt. Git history remains the exact byte-history for every exempt mutation.",
        )

    def test_rejects_wrong_github_target(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/current.json"
            obj = json.loads(p.read_text())
            obj["authorized_targets"]["github"]["repository_id"] = 1
            p.write_text(json.dumps(obj, indent=2) + "\n")
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("C003_TARGET", result.stderr)
        finally:
            td.cleanup()

    def test_rejects_runtime_authority(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/current.json"
            obj = json.loads(p.read_text())
            obj["runtime_control_authority"] = "PASS"
            p.write_text(json.dumps(obj, indent=2) + "\n")
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("C004_AUTHORITY", result.stderr)
        finally:
            td.cleanup()

    def test_rejects_duplicate_decision_id(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/decisions.jsonl"
            lines = p.read_text().splitlines()
            p.write_text("\n".join(lines + [lines[0]]) + "\n")
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("C005_ID_DUPLICATE", result.stderr)
        finally:
            td.cleanup()

    def test_rejects_open_question_with_resolution(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/current.json"
            obj = json.loads(p.read_text())
            obj["open_questions"][0]["state"] = "OPEN"
            obj["open_questions"][0]["resolution_decision_id"] = "D-0001"
            p.write_text(json.dumps(obj, indent=2) + "\n")
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("C007_QUESTION_STATE", result.stderr)
        finally:
            td.cleanup()

    def test_rejects_unknown_root_field(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/current.json"
            obj = json.loads(p.read_text())
            obj["surprise"] = True
            p.write_text(json.dumps(obj, indent=2) + "\n")
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("C002_SCHEMA", result.stderr)
        finally:
            td.cleanup()

if __name__ == "__main__":
    unittest.main()
