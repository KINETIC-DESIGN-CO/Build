import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProblemIntakePolicyTests(unittest.TestCase):
    def policy(self):
        return json.loads((ROOT / "governance/problem-intake-policy.json").read_text())

    def test_source_only_zero_authority(self):
        policy = self.policy()
        self.assertEqual(policy["runtime_control_authority"], "NONE")
        self.assertEqual(policy["assistant_procedure_authority"], "SOURCE_ONLY_NOT_YET_CONSUMED_BY_WORK_SELECTION")
        self.assertEqual(policy["activation_state"], "SOURCE_ONLY_NOT_YET_CONSUMED_BY_WORK_SELECTION")
        self.assertEqual(policy["downstream_integration"]["work_selection_effect"], "ZERO_UNTIL_VERSIONED_PARENT_SELECTOR_INTEGRATION_CONSUMES_THIS_POLICY")
        self.assertEqual(policy["downstream_integration"]["selector_binding_state"], "NOT_ACTIVE")
        self.assertNotIn("bootstrap_effect", policy["problem_evaluation"])

    def test_intake_is_zero_authority_create_only(self):
        intake = self.policy()["intake"]
        self.assertEqual(intake["provider"], "GITHUB_ISSUE")
        self.assertEqual(intake["repository"], "KINETIC-DESIGN-CO/Build")
        self.assertEqual(intake["title_prefix"], "[LIFE-INTAKE] ")
        self.assertEqual(intake["intake_authority"], "ZERO")
        self.assertIn("OPERATION_IS_CREATE_GITHUB_ISSUE", intake["create_exemption_conditions"])
        self.assertIn("OPERATION_DOES_NOT_EDIT_DELETE_CLOSE_LABEL_ASSIGN_MILESTONE_OR_COMMENT_ON_ANY_EXISTING_OBJECT", intake["create_exemption_conditions"])
        self.assertIn("IF_EXACTLY_ONE_EXISTS_REUSE_IT", intake["dedupe_rule"])
        self.assertIn("IF_MORE_THAN_ONE_EXIST_CLASSIFY_SCHEMA_OR_INVARIANT_VIOLATION", intake["dedupe_rule"])

    def test_verified_defect_evidence_is_closed(self):
        evaluation = self.policy()["problem_evaluation"]
        self.assertEqual(evaluation["verified_defect_evidence_classes"], ["REQUIRED_CHECK_FAILURE","SCHEMA_OR_INVARIANT_VIOLATION","AUTHORITATIVE_LIVE_MISMATCH","VERSIONED_FALSIFICATION_FAILURE","VERIFIED_PLATFORM_INCOMPATIBILITY"])
        for forbidden in ("ACKNOWLEDGED", "DOCUMENTED", "DEFERRED", "WONTFIX", "LOW_PRIORITY"):
            self.assertNotIn(forbidden, evaluation["states"])
        self.assertIn("REPAIR_REQUIRED", evaluation["states"])
        self.assertIn("REMOVE_REQUIRED", evaluation["states"])
        self.assertIn("MAP_TO_CURRENT_CANONICAL_REQUIREMENT_AND_REPAIR_MECHANISMS", evaluation["required_steps"])

    def test_downstream_bindings_use_current_main_mechanisms(self):
        downstream = self.policy()["downstream_integration"]
        self.assertEqual(downstream["issue_consolidation_registry_path"], "governance/issue-consolidation-registry.json")
        self.assertEqual(downstream["root_cause_repair_policy_path"], "governance/root-cause-repair-policy.json")
        self.assertEqual(downstream["canonical_parent_goal_id"], "2910e7b9-87d8-4a82-b0ff-330b47037bf6")
        self.assertEqual(downstream["parent_goal_binding_state"], "PENDING_PARENT_GOAL_MAIN_INTEGRATION")
        self.assertIn("DETERMINISTIC_ISSUE_CONSOLIDATION", downstream["consolidation_rule"])
        self.assertIn("ROOT_CAUSE_REPAIR_POLICY", downstream["repair_handoff_rule"])

    def test_continuity_has_zero_global_claim_effect(self):
        continuity = self.policy()["continuity_integration"]
        self.assertEqual(continuity["mode"], "WORK_BRANCH_CAPTURE_PLUS_PROTECTED_MERGE")
        self.assertIsNone(continuity["global_claim_resource_key"])
        self.assertEqual(continuity["global_claim_effect"], "NONE")
        self.assertEqual(continuity["legacy_claim_rule"], "LEGACY_CONTINUITY_SYNC_LOCKS_HAVE_ZERO_WORK_SELECTION_LANE_OR_PREEMPTION_EFFECT")

    def test_schema_is_closed_and_matches_source_only_shape(self):
        schema = json.loads((ROOT / "governance/schema/problem-intake-policy.schema.json").read_text())
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["activation_state"]["const"], "SOURCE_ONLY_NOT_YET_CONSUMED_BY_WORK_SELECTION")
        self.assertFalse(schema["properties"]["intake"]["additionalProperties"])
        self.assertFalse(schema["properties"]["problem_evaluation"]["additionalProperties"])
        self.assertFalse(schema["properties"]["downstream_integration"]["additionalProperties"])
        self.assertFalse(schema["properties"]["continuity_integration"]["additionalProperties"])

    def test_current_main_mechanisms_exist(self):
        self.assertTrue((ROOT / "governance/issue-consolidation-registry.json").is_file())
        self.assertTrue((ROOT / "governance/root-cause-repair-policy.json").is_file())

    def test_response_contract_discloses_persistence_and_current_job(self):
        contract = json.loads((ROOT / "continuity/response-contract.json").read_text())
        self.assertIn("PERSISTENCE_STATUS", contract["required_sections"])
        self.assertEqual(
            contract["persistence_status_values"],
            ["THREAD_ONLY", "DURABLE_INTAKE_RECORDED", "QUEUED", "IMPLEMENTING", "LIVE", "BLOCKED"],
        )
        self.assertEqual(
            contract["current_job_rule"],
            "SYSTEM_NEXT_STEP_STATES_THE_EXACT_WORK_THE_VERIFIED_OWNER_IS_ASSIGNED_TO_EXECUTE;WHEN_THIS_THREAD_OWNS_SELECTED_EXECUTABLE_WORK_RENDER_CONTINUE_THIS_THREAD_AND_STATE_THAT_THIS_THREAD_WILL_CONTINUE_IT;WHEN_THREAD_LIFECYCLE_BOUNDARY_IS_TERMINAL_HANDOFF_RENDER_TERMINAL_HANDOFF_OPTIONS_AND_DO_NOT_EXECUTE_AN_UNRELATED_CANDIDATE_WITHOUT_EXACT_CONTINUE_EVIDENCE",
        )
        self.assertIn("ARTIFACT_OR_WORK_ID", contract["persistence_disclosure_rule"])


if __name__ == "__main__":
    unittest.main()
