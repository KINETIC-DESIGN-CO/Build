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
