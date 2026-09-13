import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate_issue_lifecycle.py"
spec = importlib.util.spec_from_file_location("validate_issue_lifecycle", MODULE_PATH)
lifecycle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lifecycle)

POLICY = json.loads((ROOT / "governance" / "issue-lifecycle-policy.json").read_text())
ADMISSIONS_PATH = ROOT / "governance" / "work-admissions.json"


def item(issue_number, state):
    return {
        "work_item_id": f"github-issue-{issue_number}",
        "source_issue_number": issue_number,
        "component_id": f"issue_{issue_number}",
        "dispatch_tier": 1,
        "state": state,
        "depends_on": [],
    }


def admissions(*items):
    return {"items": list(items)}


class IssueLifecycleTests(unittest.TestCase):
    def run_tool(self, *args):
        return subprocess.run(
            ["python", "scripts/validate_issue_lifecycle.py", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def evaluate_fixture(self, registry, issues):
        rows = lifecycle.evaluate_snapshot(POLICY, registry, {"issues": issues})
        return {row["work_item_id"]: row for row in rows}

    def test_policy_validates_against_canonical_package(self):
        proc = self.run_tool("--validate-policy")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "ISSUE_LIFECYCLE_POLICY_VALID")

    def test_terminal_operations_are_controlled_fixture_projection(self):
        registry = admissions(item(701, "COMPLETE"), item(702, "REMOVED"), item(703, "ADMITTED"))
        operations = lifecycle.terminal_operations(POLICY, registry)
        self.assertEqual(
            [(row["issue_number"], row["expected_reason"]) for row in operations],
            [(701, "completed"), (702, "not_planned")],
        )

    def test_new_terminal_item_does_not_require_literal_expected_list_change(self):
        registry = admissions(item(701, "COMPLETE"), item(702, "REMOVED"))
        before = lifecycle.terminal_operations(POLICY, registry)
        registry["items"].append(item(704, "COMPLETE"))
        after = lifecycle.terminal_operations(POLICY, registry)
        self.assertEqual(len(after), len(before) + 1)
        self.assertEqual(after[-1]["issue_number"], 704)
        self.assertEqual(after[-1]["expected_reason"], "completed")

    def test_canonical_cli_projection_matches_independent_current_registry_derivation(self):
        canonical = json.loads(ADMISSIONS_PATH.read_text())
        mapping = POLICY["terminal_admission_states"]
        expected = sorted(
            (entry["source_issue_number"], mapping[entry["state"]])
            for entry in canonical["items"]
            if entry["state"] in mapping
        )
        proc = self.run_tool("--terminal-operations")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        observed = []
        for line in proc.stdout.splitlines():
            issue_number, reason = line.split("\t")
            observed.append((int(issue_number), reason))
        self.assertEqual(observed, expected)

    def test_complete_admission_with_open_issue_is_not_terminal(self):
        rows = self.evaluate_fixture(admissions(item(701, "COMPLETE")), {"701": {"state": "open", "state_reason": None}})
        self.assertEqual(rows["github-issue-701"]["lifecycle_state"], "CLOSE_REQUIRED")
        self.assertFalse(rows["github-issue-701"]["selected_work_terminal"])

    def test_complete_admission_requires_closed_completed_readback(self):
        rows = self.evaluate_fixture(admissions(item(701, "COMPLETE")), {"701": {"state": "closed", "state_reason": "completed"}})
        self.assertEqual(rows["github-issue-701"]["lifecycle_state"], "VERIFIED_TERMINAL")
        self.assertTrue(rows["github-issue-701"]["selected_work_terminal"])

    def test_wrong_close_reason_is_not_terminal(self):
        rows = self.evaluate_fixture(admissions(item(701, "COMPLETE")), {"701": {"state": "closed", "state_reason": "not_planned"}})
        self.assertEqual(rows["github-issue-701"]["lifecycle_state"], "REASON_RECONCILIATION_REQUIRED")
        self.assertFalse(rows["github-issue-701"]["selected_work_terminal"])

    def test_missing_authoritative_readback_is_not_terminal(self):
        rows = self.evaluate_fixture(admissions(item(701, "COMPLETE")), {})
        self.assertEqual(rows["github-issue-701"]["lifecycle_state"], "READBACK_NOT_RUN")
        self.assertFalse(rows["github-issue-701"]["selected_work_terminal"])

    def test_admitted_item_is_nonterminal_even_if_issue_is_closed(self):
        rows = self.evaluate_fixture(admissions(item(703, "ADMITTED")), {"703": {"state": "closed", "state_reason": "completed"}})
        self.assertEqual(rows["github-issue-703"]["lifecycle_state"], "ADMISSION_NONTERMINAL")
        self.assertFalse(rows["github-issue-703"]["selected_work_terminal"])

    def test_removed_admission_requires_not_planned_reason(self):
        rows = self.evaluate_fixture(admissions(item(702, "REMOVED")), {"702": {"state": "closed", "state_reason": "not_planned"}})
        self.assertEqual(rows["github-issue-702"]["lifecycle_state"], "VERIFIED_TERMINAL")
        self.assertTrue(rows["github-issue-702"]["selected_work_terminal"])

    def test_unknown_snapshot_properties_fail_closed(self):
        registry = admissions(item(701, "COMPLETE"))
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.evaluate_snapshot(POLICY, registry, {"issues": {}, "extra": True})


if __name__ == "__main__":
    unittest.main()
