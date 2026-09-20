import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENFORCEMENT = "2026-09-13T19:38:19Z"
ROOT_GOAL = "2910e7b9-87d8-4a82-b0ff-330b47037bf6"

VALIDATOR_PATH = ROOT / "continuity/tools/validate_checkpoints.py"
VALIDATOR_SPEC = importlib.util.spec_from_file_location("life_checkpoint_validator", VALIDATOR_PATH)
assert VALIDATOR_SPEC is not None and VALIDATOR_SPEC.loader is not None
checkpoint_validator = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(checkpoint_validator)


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

    def non_legacy_checkpoint_path(self, root):
        for path in sorted((root / "continuity/checkpoints").glob("CP-*.json")):
            rel = path.relative_to(root).as_posix()
            if rel not in checkpoint_validator.LEGACY_CHECKPOINT_BLOBS:
                return path
        self.fail("expected at least one non-legacy checkpoint")

    def test_legacy_checkpoint_baseline_identity_is_exactly_31_entries(self):
        baseline = checkpoint_validator.LEGACY_CHECKPOINT_BLOBS
        self.assertEqual(len(baseline), 31)
        self.assertEqual(len(set(baseline.items())), 31)
        self.assertEqual(
            checkpoint_validator.LEGACY_CHECKPOINT_ALLOWED_MISMATCH_CODES,
            frozenset({"C011_SCHEMA_INSTANCE", "C010_FORMAT", "CP010_GOAL", "CP007_READBACK"}),
        )
        for rel, expected_sha in baseline.items():
            path = ROOT / rel
            self.assertTrue(path.is_file(), rel)
            self.assertEqual(checkpoint_validator.git_blob_sha(path), expected_sha, rel)
            self.assertTrue(checkpoint_validator.is_legacy_checkpoint_compatible(path), rel)

    def test_one_byte_mutation_loses_legacy_compatibility(self):
        td, dst = self.copy_repo()
        try:
            rel = next(iter(checkpoint_validator.LEGACY_CHECKPOINT_BLOBS))
            path = dst / rel
            path.write_bytes(path.read_bytes() + b" ")
            self.assertFalse(checkpoint_validator.is_legacy_checkpoint_compatible(path, dst))
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
        finally:
            td.cleanup()

    def test_path_copy_loses_legacy_compatibility(self):
        td, dst = self.copy_repo()
        try:
            rel = next(iter(checkpoint_validator.LEGACY_CHECKPOINT_BLOBS))
            source = dst / rel
            copied = dst / "continuity/checkpoints/CP-999999-deadbeef.json"
            copied.write_bytes(source.read_bytes())
            self.assertFalse(checkpoint_validator.is_legacy_checkpoint_compatible(copied, dst))
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("checkpoint_id must equal filename stem", result.stderr)
        finally:
            td.cleanup()

    def test_new_checkpoint_receives_current_validation(self):
        td, dst = self.copy_repo()
        try:
            source = self.non_legacy_checkpoint_path(dst)
            obj = json.loads(source.read_text())
            path = dst / "continuity/checkpoints/CP-999999-deadbeef.json"
            obj["checkpoint_id"] = path.stem
            obj["model_judgment"] = "not allowed"
            self.write_json(path, obj)
            self.assertFalse(checkpoint_validator.is_legacy_checkpoint_compatible(path, dst))
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown properties", result.stderr)
        finally:
            td.cleanup()

    def test_non_allowlisted_historical_checkpoint_receives_current_validation(self):
        td, dst = self.copy_repo()
        try:
            path = self.non_legacy_checkpoint_path(dst)
            obj = json.loads(path.read_text())
            obj["model_judgment"] = "not allowed"
            self.write_json(path, obj)
            self.assertFalse(checkpoint_validator.is_legacy_checkpoint_compatible(path, dst))
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown properties", result.stderr)
        finally:
            td.cleanup()

    def test_current_checkpoint_bundle_is_valid(self):
        result = self.run_validator(ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("VALID", result.stdout)

    def test_bootstrap_requires_checkpoint_goal_and_provenance_surfaces(self):
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
            "governance/goal-policy.json",
            "governance/goal-registry.json",
            "scripts/validate_goal_graph.py",
            "tests/test_goal_graph.py",
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
            "EVALUATE_THREAD_LIFECYCLE_BOUNDARY",
        ):
            self.assertIn(step, bootstrap["resume_algorithm"])
        self.assertIn("python scripts/validate_goal_graph.py", bootstrap["validation_command"])
        self.assertIn("python continuity/tools/validate_checkpoints.py", bootstrap["validation_command"])
        self.assertIn("python continuity/tests/test_checkpoints.py", bootstrap["validation_command"])

    def test_policy_has_exact_goal_snapshot_boundary(self):
        policy = json.loads((ROOT / "continuity/checkpoint-policy.json").read_text())
        self.assertEqual(policy["trigger_mode"], "ANY_TRUE")
        self.assertEqual(policy["cadence"]["non_checkpoint_tool_result_limit"], 12)
        self.assertEqual(policy["cadence"]["elapsed_seconds_limit"], 1800)
        self.assertEqual(policy["cadence"]["elapsed_trigger_min_new_evidence_items"], 1)
        self.assertEqual(policy["checkpoint_authority"], "EVIDENCE_ONLY")
        self.assertEqual(policy["goal_snapshot_enforcement_utc"], ENFORCEMENT)
        template = json.loads((ROOT / "continuity/checkpoint-template.json").read_text())
        self.assertIn("goal_snapshot", template["field_order"])
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

    def test_checkpoint_after_enforcement_requires_goal_snapshot(self):
        td, dst = self.copy_repo()
        try:
            path = self.checkpoint_path(dst)
            obj = json.loads(path.read_text())
            obj["created_at"] = ENFORCEMENT
            obj.pop("goal_snapshot", None)
            self.write_json(path, obj)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires goal_snapshot after enforcement", result.stderr)
        finally:
            td.cleanup()

    def test_goal_snapshot_path_must_start_at_root_and_end_at_active(self):
        td, dst = self.copy_repo()
        try:
            path = self.checkpoint_path(dst)
            obj = json.loads(path.read_text())
            obj["created_at"] = ENFORCEMENT
            child = "5c4d26d4-f821-4db5-9f5c-dccce3eaa697"
            obj["goal_snapshot"] = {
                "active_root_goal_id": ROOT_GOAL,
                "active_goal_id": child,
                "active_path": [child],
                "observed_at": ENFORCEMENT,
                "authority": "HISTORICAL_OBSERVATION_ONLY",
            }
            self.write_json(path, obj)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must start at active_root_goal_id", result.stderr)
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
