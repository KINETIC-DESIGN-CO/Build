import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Issue15SchemaFalsificationTests(unittest.TestCase):
    def run_validator(self, root):
        return subprocess.run(
            ["python", "scripts/validate_continuity.py"],
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

    def assert_schema_rejected(self, result, message_fragment):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("C011_SCHEMA_INSTANCE", result.stderr)
        self.assertIn(message_fragment, result.stderr)

    def test_schema_rejects_empty_string_where_min_length_requires_one(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "continuity/current.json"
            obj = json.loads(path.read_text())
            obj["current_work"]["goal"] = ""
            self.write_json(path, obj)
            result = self.run_validator(dst)
            self.assert_schema_rejected(result, "shorter than minLength 1")
        finally:
            td.cleanup()

    def test_schema_rejects_duplicate_array_items_via_unique_items(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "continuity/current.json"
            obj = json.loads(path.read_text())
            first = obj["current_work"]["completion_conditions"][0]
            obj["current_work"]["completion_conditions"] = [first, first]
            self.write_json(path, obj)
            result = self.run_validator(dst)
            self.assert_schema_rejected(result, "items must be unique")
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
