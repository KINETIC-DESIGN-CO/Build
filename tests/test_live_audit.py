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
            "finding_state": "NONE",
            "verified_repair_evidence_class": None,
            "resource_state": "AVAILABLE",
            "authorization_state": "AUTHORIZED",
            "cost_state": "NO_NEW_COMMITMENT",
            "platform_state": "AVAILABLE",
            "touches_verification_trust_root": False,
            "verification_trust_state": "NOT_APPLICABLE",
        }
        value.update(overrides)
        return value

    def test_policy_validates(self):
        live_audit.validate_policy(live_audit.load(live_audit.POLICY_PATH))

    def test_verified_failure_repairs_immediately(self):
        result = live_audit.evaluate(self.evidence(
            finding_state="VERIFIED_REPAIR",
            verified_repair_evidence_class="REQUIRED_CHECK_FAILURE",
        ))
        self.assertEqual(result["disposition"], "IMMEDIATE_REPAIR")
        self.assertTrue(result["repair_now"])

    def test_candidate_cannot_preempt(self):
        result = live_audit.evaluate(self.evidence(finding_state="CANDIDATE"))
        self.assertEqual(result["disposition"], "CANDIDATE_ONLY")
        self.assertEqual(result["candidate_preemption_effect"], "ZERO")

    def test_research_design_change_replans_before_mutation(self):
        result = live_audit.evaluate(self.evidence(finding_state="RESEARCH_DESIGN_CHANGE"))
        self.assertEqual(result["disposition"], "IMMEDIATE_REPLAN")
        self.assertTrue(result["replan_now"])

    def test_exact_resource_collision_is_the_only_resource_deferral(self):
        result = live_audit.evaluate(self.evidence(
            finding_state="VERIFIED_REPAIR",
            verified_repair_evidence_class="SCHEMA_OR_INVARIANT_VIOLATION",
            resource_state="BLOCKED",
        ))
        self.assertEqual(result["disposition"], "BLOCKED_RESOURCE")
        self.assertTrue(result["deferred_only_by_exact_blocker"])

    def test_trust_root_repair_requires_independent_verification(self):
        result = live_audit.evaluate(self.evidence(
            finding_state="VERIFIED_REPAIR",
            verified_repair_evidence_class="VERSIONED_FALSIFICATION_FAILURE",
            touches_verification_trust_root=True,
            verification_trust_state="BLOCKED",
        ))
        self.assertEqual(result["disposition"], "BLOCKED_VERIFICATION_TRUST")

    def test_verified_repair_requires_exact_evidence_class(self):
        with self.assertRaises(live_audit.LiveAuditError):
            live_audit.evaluate(self.evidence(finding_state="VERIFIED_REPAIR"))

    def test_passive_terminal_states_are_forbidden(self):
        policy = live_audit.load(live_audit.POLICY_PATH)
        for state in ("DOCUMENTED", "DEFERRED", "QUEUED_ONLY"):
            self.assertIn(state, policy["passive_terminal_states_forbidden"])

    def test_live_audit_is_pre_selector_gate(self):
        policy = live_audit.load(live_audit.POLICY_PATH)
        rule = policy["selection_binding_rule"]
        self.assertIn("LIVE_AUDIT_RUNS_BEFORE_NORMAL_WORK_SELECTION", rule)
        self.assertIn("IMMEDIATE_REPAIR_OR_IMMEDIATE_REPLAN_MUST_RESOLVE_BEFORE_NORMAL_SELECTOR_EXECUTION", rule)
        self.assertIn("CANDIDATE_ONLY_OR_NO_CHANGE_FALLS_THROUGH_TO_NORMAL_WORK_SELECTION", rule)


if __name__ == "__main__":
    unittest.main()
