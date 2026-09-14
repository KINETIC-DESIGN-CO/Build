from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate_live_audit.py"

spec = importlib.util.spec_from_file_location("evaluate_live_audit", SCRIPT)
live_audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(live_audit)


class LiveAuditTests(unittest.TestCase):
    def evidence(self, **overrides):
        value = {
            "trigger_id": "BEFORE_PROTECTED_BOUNDARY",
            "dimension_states": {name: "PASS" for name in live_audit.DIMENSIONS},
            "finding_state": "NONE",
            "verified_repair_evidence_class": None,
            "root_goal_id": "2910e7b9-87d8-4a82-b0ff-330b47037bf6",
            "detector_or_invariant_id": "DETECTOR-1",
            "subject_id": "subject-1",
            "component_id": "goal_lifecycle_identity",
            "resource_state": "AVAILABLE",
            "authorization_state": "AUTHORIZED",
            "cost_state": "NO_NEW_COMMITMENT",
            "platform_state": "AVAILABLE",
        }
        value.update(overrides)
        return value

    def test_policy_validates_and_uses_exact_triggers(self):
        policy = live_audit.load(live_audit.POLICY_PATH)
        live_audit.validate_policy(policy)
        self.assertEqual(policy["trigger_ids"], live_audit.TRIGGERS)
        self.assertIn("BEFORE_FINAL_REQUIRED_CLAIM_RELEASE", policy["trigger_ids"])
        self.assertIn("TRACKED_PR_HEAD_OR_STATE_CHANGED", policy["trigger_ids"])

    def test_no_change_continues_selected_work(self):
        result = live_audit.evaluate(self.evidence())
        self.assertEqual(result["audit_result_state"], "NO_COURSE_CHANGE_EVIDENCE")
        self.assertEqual(result["execution_disposition"], "CONTINUE_SELECTED_WORK")

    def test_verified_failure_becomes_immediate_defect_repair_child(self):
        result = live_audit.evaluate(self.evidence(
            finding_state="VERIFIED_REPAIR",
            verified_repair_evidence_class="REQUIRED_CHECK_FAILURE",
        ))
        self.assertEqual(result["repair_lifecycle_transition"], "REPAIR_REQUIRED")
        self.assertEqual(result["execution_disposition"], "EXECUTE_VERIFIED_REPAIR_CHILD")
        self.assertEqual(result["goal_relation"], "DEFECT_REPAIR")
        self.assertTrue(result["repair_identity"].startswith("repair-"))

    def test_repair_identity_is_stable_for_same_exact_inputs(self):
        evidence = self.evidence(
            finding_state="VERIFIED_REPAIR",
            verified_repair_evidence_class="SCHEMA_OR_INVARIANT_VIOLATION",
        )
        self.assertEqual(live_audit.evaluate(evidence)["repair_identity"], live_audit.evaluate(evidence)["repair_identity"])

    def test_candidate_cannot_preempt_or_mutate(self):
        result = live_audit.evaluate(self.evidence(finding_state="CANDIDATE"))
        self.assertEqual(result["audit_result_state"], "DEFECT_CANDIDATE")
        self.assertEqual(result["execution_disposition"], "RECORD_DEFECT_CANDIDATE")
        self.assertEqual(result["candidate_control_effect"], "ZERO")

    def test_research_design_change_replans_before_mutation(self):
        result = live_audit.evaluate(self.evidence(finding_state="RESEARCH_DESIGN_CHANGE"))
        self.assertEqual(result["audit_result_state"], "REPLAN_CANDIDATE")
        self.assertEqual(result["execution_disposition"], "REPLAN_BEFORE_PROTECTED_MUTATION")

    def test_research_horizon_issue_expands_research(self):
        dimensions = {name: "PASS" for name in live_audit.DIMENSIONS}
        dimensions["RESEARCH_EVIDENCE_HORIZON"] = "ISSUE"
        result = live_audit.evaluate(self.evidence(dimension_states=dimensions))
        self.assertEqual(result["audit_result_state"], "RESEARCH_EXPANSION_REQUIRED")
        self.assertEqual(result["execution_disposition"], "EXPAND_RESEARCH")

    def test_not_run_dimension_fails_closed(self):
        dimensions = {name: "PASS" for name in live_audit.DIMENSIONS}
        dimensions["OWNERSHIP_AND_FENCE"] = "NOT_RUN"
        result = live_audit.evaluate(self.evidence(dimension_states=dimensions))
        self.assertEqual(result["audit_result_state"], "NOT_RUN")
        self.assertEqual(result["execution_disposition"], "NOT_RUN")

    def test_unresolved_external_effect_precedes_repair(self):
        result = live_audit.evaluate(self.evidence(finding_state="UNRESOLVED_EXTERNAL_EFFECT"))
        self.assertEqual(result["audit_result_state"], "EFFECT_RECONCILIATION_REQUIRED")
        self.assertEqual(result["execution_disposition"], "RECONCILE_EFFECT_BEFORE_CONTINUE")

    def test_exact_resource_collision_blocks_only_repair_execution(self):
        result = live_audit.evaluate(self.evidence(
            finding_state="VERIFIED_REPAIR",
            verified_repair_evidence_class="SCHEMA_OR_INVARIANT_VIOLATION",
            resource_state="BLOCKED",
        ))
        self.assertEqual(result["audit_result_state"], "BLOCKED_RESOURCE")
        self.assertEqual(result["execution_disposition"], "BLOCKED_RESOURCE")
        self.assertEqual(result["repair_lifecycle_transition"], "REPAIR_REQUIRED")

    def test_verification_gap_forces_retest(self):
        result = live_audit.evaluate(self.evidence(finding_state="VERIFICATION_GAP"))
        self.assertEqual(result["audit_result_state"], "VERIFICATION_REQUIRED")
        self.assertEqual(result["execution_disposition"], "VERIFY_BEFORE_CONTINUE")

    def test_verified_repair_requires_exact_evidence_class(self):
        with self.assertRaises(live_audit.LiveAuditError):
            live_audit.evaluate(self.evidence(finding_state="VERIFIED_REPAIR"))

    def test_passive_queue_is_not_a_handled_terminal_state(self):
        policy = live_audit.load(live_audit.POLICY_PATH)
        self.assertIn("QUEUED_ONLY", policy["passive_terminal_states_forbidden"])
        self.assertIn("QUEUED_ONLY_IS_NOT_A_HANDLED_VERIFIED_REPAIR_STATE", policy["queue_rule"])


if __name__ == "__main__":
    unittest.main()
