import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProblemIntakePolicyTests(unittest.TestCase):
    def test_policy_is_zero_authority_and_split_is_exact(self):
        policy = json.loads((ROOT / "governance/problem-intake-policy.json").read_text())
        self.assertEqual(policy["runtime_control_authority"], "NONE")
        self.assertEqual(policy["assistant_procedure_authority"], "ASSISTANT_PROCEDURE_ONLY")
        self.assertEqual(policy["current_continuity_split"]["canonical_projection_resource"], "continuity:sync")
        self.assertEqual(
            policy["current_continuity_split"]["intake_rule"],
            "DO_NOT_REQUIRE_CANONICAL_PROJECTION_RESOURCE_FOR_ZERO_AUTHORITY_INTAKE_ISSUE_CREATE_WHEN_ALL_CREATE_EXEMPTION_CONDITIONS_PASS",
        )

    def test_intake_exemption_is_create_only_and_closed(self):
        policy = json.loads((ROOT / "governance/problem-intake-policy.json").read_text())
        intake = policy["intake"]
        self.assertEqual(intake["provider"], "GITHUB_ISSUE")
        self.assertEqual(intake["repository"], "KINETIC-DESIGN-CO/Build")
        self.assertEqual(intake["title_prefix"], "[LIFE-INTAKE] ")
        self.assertEqual(intake["intake_authority"], "ZERO")
        self.assertEqual(intake["create_exemption_id"], "ZERO_AUTHORITY_INTAKE_ISSUE_CREATE")
        self.assertIn("OPERATION_IS_CREATE_GITHUB_ISSUE", intake["create_exemption_conditions"])
        self.assertIn(
            "OPERATION_DOES_NOT_EDIT_DELETE_CLOSE_LABEL_ASSIGN_MILESTONE_OR_COMMENT_ON_ANY_EXISTING_OBJECT",
            intake["create_exemption_conditions"],
        )
        self.assertEqual(
            intake["create_exemption_effect"],
            "CONTINUITY_SYNC_PREARM_NOT_REQUIRED_FOR_THIS_CREATE_ONLY_OPERATION",
        )

    def test_problem_evaluation_has_no_acknowledge_only_terminal_state(self):
        policy = json.loads((ROOT / "governance/problem-intake-policy.json").read_text())
        evaluation = policy["problem_evaluation"]
        for forbidden in ("ACKNOWLEDGED", "DOCUMENTED", "DEFERRED", "WONTFIX", "LOW_PRIORITY"):
            self.assertNotIn(forbidden, evaluation["states"])
        self.assertIn("REPAIR_REQUIRED", evaluation["states"])
        self.assertIn("REMOVE_REQUIRED", evaluation["states"])
        self.assertIn("BLOCKED_EVIDENCE", evaluation["states"])
        self.assertIn("READ_BACK_AND_VERIFY_RESULT", evaluation["required_steps"])

    def test_remove_requires_full_verified_invariant_coverage(self):
        policy = json.loads((ROOT / "governance/problem-intake-policy.json").read_text())
        self.assertEqual(
            policy["problem_evaluation"]["remove_rule"],
            "REMOVE_REQUIRED_IFF_EVERY_PROTECTED_INVARIANT_ID_OF_THE_BLOCKING_MECHANISM_IS_COVERED_BY_A_CURRENT_VERIFIED_SUCCESSOR_MECHANISM_ID",
        )

    def test_policy_schema_is_closed(self):
        schema = json.loads((ROOT / "governance/schema/problem-intake-policy.schema.json").read_text())
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["runtime_control_authority"]["const"], "NONE")
        self.assertFalse(schema["properties"]["intake"]["additionalProperties"])
        self.assertFalse(schema["properties"]["problem_evaluation"]["additionalProperties"])

    def test_bootstrap_requires_policy_and_evaluation_step(self):
        bootstrap = json.loads((ROOT / "continuity/bootstrap.json").read_text())
        self.assertIn("governance/problem-intake-policy.json", bootstrap["required_files"])
        self.assertIn("governance/schema/problem-intake-policy.schema.json", bootstrap["required_files"])
        self.assertIn("governance/problem-intake-policy.json", bootstrap["required_read_order"])
        self.assertIn("EVALUATE_PERSISTENT_INTAKE_AND_PROBLEMS", bootstrap["resume_algorithm"])
        self.assertIn("ZERO_AUTHORITY_INTAKE_ISSUE_CREATE", bootstrap["continuity_sync_rule"])

    def test_response_contract_discloses_persistence_and_current_job(self):
        contract = json.loads((ROOT / "continuity/response-contract.json").read_text())
        self.assertIn("PERSISTENCE_STATUS", contract["required_sections"])
        self.assertEqual(
            contract["persistence_status_values"],
            ["THREAD_ONLY", "DURABLE_INTAKE_RECORDED", "QUEUED", "IMPLEMENTING", "LIVE", "BLOCKED"],
        )
        self.assertEqual(
            contract["current_job_rule"],
            "NEXT_STEP_STATES_THE_EXACT_WORK_THIS_THREAD_OWNS_AND_WILL_EXECUTE;IF_THIS_THREAD_HAS_NO_WORK_TO_CONTINUE_OUTPUT_EXACTLY_THIS_THREAD_CAN_BE_CLOSED",
        )
        self.assertIn("ARTIFACT_OR_WORK_ID", contract["persistence_disclosure_rule"])


if __name__ == "__main__":
    unittest.main()
