from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_research_policy.py"

spec = importlib.util.spec_from_file_location("validate_research_policy", SCRIPT)
research = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(research)


class ResearchPolicyTests(unittest.TestCase):
    def record(self):
        lanes = {}
        for lane_id in research.REQUIRED_LANES:
            lanes[lane_id] = {
                "state": "EVIDENCE_FOUND",
                "evidence_refs": [f"evidence:{lane_id}"],
                "attempted_search_refs": [],
                "source_family_ids": [],
                "alternative_ids": [],
            }
        lanes["INDEPENDENT_PARALLEL_EVIDENCE"]["source_family_ids"] = ["family-a", "family-b"]
        lanes["COMPETING_MECHANISMS"]["alternative_ids"] = ["alternative-a"]
        return {
            "lane_results": lanes,
            "selected_disposition": "COMBINE",
            "affected_requirement_or_invariant_ids": ["REQ-ZOOM-OUT"],
            "design_change_ids": [],
        }

    def policy(self):
        return research.load(research.POLICY_PATH)

    def test_canonical_policy_validates(self):
        research.validate_policy(self.policy())

    def test_zoom_out_lanes_match_durable_contract(self):
        self.assertEqual(research.REQUIRED_LANES, [
            "WHOLE_SOURCE_CONTEXT",
            "SOURCE_SYSTEM_CONTEXT",
            "SAME_SOURCE_PARALLEL",
            "INDEPENDENT_PARALLEL_EVIDENCE",
            "COMPETING_MECHANISMS",
            "FAILURE_AND_COUNTEREXAMPLE_EVIDENCE",
            "DISCONFIRMATION_SEARCH",
            "LIFE_REEVALUATION",
        ])
        self.assertEqual(research.LANE_STATES, ["EVIDENCE_FOUND", "NO_EVIDENCE_FOUND", "NOT_APPLICABLE", "NOT_RUN"])

    def test_complete_horizon_closes_research(self):
        result = research.validate_record(self.record(), self.policy())
        self.assertEqual(result["closure_state"], "RESEARCH_COMPLETE")

    def test_not_run_lane_blocks_research_closure(self):
        record = self.record()
        record["lane_results"]["SAME_SOURCE_PARALLEL"] = {
            "state": "NOT_RUN",
            "evidence_refs": [],
            "attempted_search_refs": [],
            "source_family_ids": [],
            "alternative_ids": [],
        }
        result = research.validate_record(record, self.policy())
        self.assertEqual(result["closure_state"], "RESEARCH_NOT_COMPLETE")

    def test_design_changing_whole_source_context_requires_replan(self):
        record = self.record()
        record["selected_disposition"] = "MODIFY"
        record["design_change_ids"] = ["WHOLE_SOURCE_REVEALS_FAILURE_MODE"]
        result = research.validate_record(record, self.policy())
        self.assertEqual(result["closure_state"], "REPLAN_REQUIRED")

    def test_parallel_evidence_requires_two_source_families(self):
        record = self.record()
        record["lane_results"]["INDEPENDENT_PARALLEL_EVIDENCE"]["source_family_ids"] = ["one-family"]
        with self.assertRaises(research.ResearchError):
            research.validate_record(record, self.policy())

    def test_competing_mechanism_requires_current_alternative(self):
        record = self.record()
        record["lane_results"]["COMPETING_MECHANISMS"]["alternative_ids"] = []
        with self.assertRaises(research.ResearchError):
            research.validate_record(record, self.policy())

    def test_no_evidence_found_requires_attempted_search_reference(self):
        record = self.record()
        record["lane_results"]["FAILURE_AND_COUNTEREXAMPLE_EVIDENCE"] = {
            "state": "NO_EVIDENCE_FOUND",
            "evidence_refs": [],
            "attempted_search_refs": [],
            "source_family_ids": [],
            "alternative_ids": [],
        }
        with self.assertRaises(research.ResearchError):
            research.validate_record(record, self.policy())

    def test_research_has_zero_control_authority(self):
        policy = self.policy()
        self.assertEqual(policy["runtime_control_authority"], "NONE")
        self.assertEqual(policy["research_authority"], "EVIDENCE_ONLY")
        self.assertIn("CANNOT_CREATE_AUTHORIZATION_ROUTING_PRIORITY_COMPLETION_VERIFICATION_RELEASE_MUTATION_OR_EFFECT_EXECUTION_PASS", policy["non_authority_rule"])


if __name__ == "__main__":
    unittest.main()
