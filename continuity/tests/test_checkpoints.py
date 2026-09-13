import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class CheckpointTests(unittest.TestCase):
    def copy_repo(self):
        td = tempfile.TemporaryDirectory()
        dst = Path(td.name) / "repo"
        shutil.copytree(ROOT, dst)
        return td, dst

    def run_validator(self, root):
        return subprocess.run(
            ["python", "continuity/tools/validate_checkpoints.py"],
            cwd=root,
            text=True,
            capture_output=True,
        )

    def write_json(self, path, obj):
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")

    def read_jsonl(self, path):
        return [json.loads(line) for line in path.read_text().splitlines() if line]

    def write_jsonl(self, path, rows):
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows) + "\n"
        )

    def checkpoint_path(self, root):
        matches = sorted((root / "continuity/checkpoints").glob("CP-*.json"))
        self.assertTrue(matches)
        return matches[-1]

    def test_current_checkpoint_bundle_is_valid(self):
        result = self.run_validator(ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("VALID", result.stdout)

    def test_bootstrap_requires_checkpoint_and_provenance_surfaces(self):
        bootstrap = json.loads((ROOT / "continuity/bootstrap.json").read_text())
        for rel in (
            "continuity/checkpoint-policy.json",
            "continuity/checkpoint-template.json",
            "continuity/directive-ledger.jsonl",
            "continuity/decision-rationale.jsonl",
            "continuity/checkpoint.schema.json",
            "continuity/directive-record.schema.json",
            "continuity/decision-rationale.schema.json",
            "governance/work-admissions.json",
            "governance/schema/work-admissions.schema.json",
            "scripts/validate_lock_history.py",
            "tests/test_lock_history.py",
            "continuity/tools/validate_checkpoints.py",
            "continuity/tests/test_checkpoints.py",
        ):
            self.assertIn(rel, bootstrap["required_files"])
        for step in (
            "READ_LIVE_COORDINATION_FOR_CHECKPOINT_DISCOVERY",
            "READ_LATEST_WORK_CHECKPOINT",
            "READ_CHECKPOINT_PROVENANCE",
        ):
            self.assertIn(step, bootstrap["resume_algorithm"])
        self.assertIn("python scripts/validate_lock_history.py", bootstrap["validation_command"])
        self.assertIn("python continuity/tools/validate_checkpoints.py", bootstrap["validation_command"])
        self.assertIn("python continuity/tests/test_checkpoints.py", bootstrap["validation_command"])

    def test_policy_has_only_exact_checkpoint_triggers(self):
        policy = json.loads((ROOT / "continuity/checkpoint-policy.json").read_text())
        self.assertEqual(policy["trigger_mode"], "ANY_TRUE")
        self.assertEqual(policy["cadence"]["non_checkpoint_tool_result_limit"], 12)
        self.assertEqual(policy["cadence"]["elapsed_seconds_limit"], 1800)
        self.assertEqual(policy["cadence"]["elapsed_trigger_min_new_evidence_items"], 1)
        self.assertEqual(policy["checkpoint_authority"], "EVIDENCE_ONLY")
        template = json.loads((ROOT / "continuity/checkpoint-template.json").read_text())
        self.assertIn("MODEL_JUDGMENT_AS_TRIGGER", template["prohibited_interpretations"])

    def test_unknown_checkpoint_trigger_is_rejected(self):
        td, dst = self.copy_repo()
        try:
            path = self.checkpoint_path(dst)
            obj = json.loads(path.read_text())
            obj["trigger_ids"][0] = "WHEN_IT_SEEMS_IMPORTANT"
            self.write_json(path, obj)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("required enum", result.stderr)
        finally:
            td.cleanup()

    def test_directive_unknown_property_is_rejected(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "continuity/directive-ledger.jsonl"
            rows = self.read_jsonl(path)
            rows[0]["model_judgment"] = "looks important"
            self.write_jsonl(path, rows)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown properties", result.stderr)
        finally:
            td.cleanup()

    def test_duplicate_directive_id_is_rejected(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "continuity/directive-ledger.jsonl"
            rows = self.read_jsonl(path)
            rows.append(dict(rows[0]))
            self.write_jsonl(path, rows)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate directive id", result.stderr)
        finally:
            td.cleanup()

    def test_rationale_missing_directive_reference_is_rejected(self):
        td, dst = self.copy_repo()
        try:
            path = dst / "continuity/decision-rationale.jsonl"
            rows = self.read_jsonl(path)
            rows[0]["directive_ids"] = ["VD-9999"]
            self.write_jsonl(path, rows)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("references missing directive VD-9999", result.stderr)
        finally:
            td.cleanup()

    def test_failed_mutation_cannot_have_verified_readback(self):
        td, dst = self.copy_repo()
        try:
            path = self.checkpoint_path(dst)
            obj = json.loads(path.read_text())
            obj["operation_results"][0]["result"] = "FAILURE"
            obj["operation_results"][0]["readback_state"] = "VERIFIED"
            self.write_json(path, obj)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("VERIFIED readback requires SUCCESS result", result.stderr)
        finally:
            td.cleanup()

    def test_resume_candidate_has_zero_authority(self):
        td, dst = self.copy_repo()
        try:
            path = self.checkpoint_path(dst)
            obj = json.loads(path.read_text())
            obj["resume_candidate"]["authority"] = "MUTATION"
            self.write_json(path, obj)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("required const", result.stderr)
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
