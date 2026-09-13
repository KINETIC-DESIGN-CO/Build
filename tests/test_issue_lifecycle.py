import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMISSIONS_PATH = ROOT / "governance/work-admissions.json"


class IssueLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.original_admissions = ADMISSIONS_PATH.read_text(encoding="utf-8")

    def tearDown(self):
        ADMISSIONS_PATH.write_text(self.original_admissions, encoding="utf-8")

    def run_tool(self, *args):
        return subprocess.run(
            ["python", "scripts/validate_issue_lifecycle.py", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def evaluate(self, issues):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "issues.json"
            path.write_text(json.dumps({"issues": issues}) + "\n", encoding="utf-8")
            proc = self.run_tool("--evaluate-snapshot", str(path))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return {row["work_item_id"]: row for row in json.loads(proc.stdout)["results"]}

    def test_policy_validates(self):
        proc = self.run_tool("--validate-policy")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "ISSUE_LIFECYCLE_POLICY_VALID")

    def test_terminal_operations_are_derived_from_canonical_admissions(self):
        proc = self.run_tool("--terminal-operations")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.splitlines(), ["2\tcompleted", "12\tcompleted"])

    def test_complete_admission_with_open_issue_is_not_terminal(self):
        rows = self.evaluate({"2": {"state": "open", "state_reason": None}})
        self.assertEqual(rows["github-issue-2"]["lifecycle_state"], "CLOSE_REQUIRED")
        self.assertFalse(rows["github-issue-2"]["selected_work_terminal"])

    def test_complete_admission_requires_closed_completed_readback(self):
        rows = self.evaluate({"2": {"state": "closed", "state_reason": "completed"}})
        self.assertEqual(rows["github-issue-2"]["lifecycle_state"], "VERIFIED_TERMINAL")
        self.assertTrue(rows["github-issue-2"]["selected_work_terminal"])

    def test_wrong_close_reason_is_not_terminal(self):
        rows = self.evaluate({"2": {"state": "closed", "state_reason": "not_planned"}})
        self.assertEqual(rows["github-issue-2"]["lifecycle_state"], "REASON_RECONCILIATION_REQUIRED")
        self.assertFalse(rows["github-issue-2"]["selected_work_terminal"])

    def test_missing_authoritative_readback_is_not_terminal(self):
        rows = self.evaluate({})
        self.assertEqual(rows["github-issue-2"]["lifecycle_state"], "READBACK_NOT_RUN")
        self.assertFalse(rows["github-issue-2"]["selected_work_terminal"])

    def test_admitted_item_is_nonterminal_even_if_issue_is_closed(self):
        rows = self.evaluate({"15": {"state": "closed", "state_reason": "completed"}})
        self.assertEqual(rows["github-issue-15"]["lifecycle_state"], "ADMISSION_NONTERMINAL")
        self.assertFalse(rows["github-issue-15"]["selected_work_terminal"])

    def test_removed_admission_requires_not_planned_reason(self):
        admissions = json.loads(self.original_admissions)
        for item in admissions["items"]:
            if item["work_item_id"] == "github-issue-30":
                item["state"] = "REMOVED"
        ADMISSIONS_PATH.write_text(json.dumps(admissions, indent=2) + "\n", encoding="utf-8")
        rows = self.evaluate({"30": {"state": "closed", "state_reason": "not_planned"}})
        self.assertEqual(rows["github-issue-30"]["lifecycle_state"], "VERIFIED_TERMINAL")
        self.assertTrue(rows["github-issue-30"]["selected_work_terminal"])

    def test_unknown_snapshot_properties_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "issues.json"
            path.write_text(json.dumps({"issues": {}, "extra": True}) + "\n", encoding="utf-8")
            proc = self.run_tool("--evaluate-snapshot", str(path))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("snapshot must be object with exact issues object", proc.stderr)


if __name__ == "__main__":
    unittest.main()
