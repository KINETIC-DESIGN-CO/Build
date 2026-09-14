from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_research_policy.py"

spec = importlib.util.spec_from_file_location("validate_research_policy", SCRIPT)
research = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(research)


class ResearchPolicyTests(unittest.TestCase):
    def test_canonical_policy_validates(self):
        self.assertEqual([], research.validate())

    def test_zoom_out_lanes_are_complete(self):
        policy = json.loads(research.POLICY_PATH.read_text())
        self.assertEqual(policy["required_lane_ids"], research.REQUIRED_LANES)
        self.assertIn("DISCONFIRMATION_SEARCH", policy["required_lane_ids"])
        self.assertIn("FAILURE_OR_PRACTITIONER_EVIDENCE", policy["required_lane_ids"])

    def test_single_supporting_source_cannot_close_research(self):
        policy = json.loads(research.POLICY_PATH.read_text())
        self.assertIn("NARROW_CORROBORATION_FALSE_CLOSURE", policy["narrow_corroboration_rule"])
        self.assertIn("EVERY_REQUIRED_LANE_HAS_ATTEMPT_STATE_ATTEMPTED", policy["closure_rule"])

    def test_not_run_is_visible_and_not_support(self):
        policy = json.loads(research.POLICY_PATH.read_text())
        self.assertIn("NOT_RUN", policy["lane_result_states"])
        self.assertIn("ZERO_SUPPORTING_EVIDENCE_EFFECT", policy["closure_rule"])

    def test_broader_context_forces_replan_when_design_changes(self):
        policy = json.loads(research.POLICY_PATH.read_text())
        self.assertIn("RESEARCH_DESIGN_CHANGE", policy["design_change_rule"])
        self.assertIn("BEFORE_THE_NEXT_PROTECTED_MUTATION", policy["design_change_rule"])

    def test_removing_disconfirmation_lane_fails_validation(self):
        td = tempfile.TemporaryDirectory()
        try:
            dst = Path(td.name) / "repo"
            shutil.copytree(ROOT, dst)
            path = dst / "governance" / "policies" / "research-policy.json"
            policy = json.loads(path.read_text())
            policy["required_lane_ids"].remove("DISCONFIRMATION_SEARCH")
            path.write_text(json.dumps(policy, indent=2) + "\n")
            script = dst / "scripts" / "validate_research_policy.py"
            spec2 = importlib.util.spec_from_file_location("validate_research_policy_mutated", script)
            mutated = importlib.util.module_from_spec(spec2)
            assert spec2.loader is not None
            spec2.loader.exec_module(mutated)
            self.assertTrue(any("RESEARCH004_LANES" in error for error in mutated.validate()))
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
