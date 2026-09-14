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

    def assert_schema_rejected(self, result):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("C011_SCHEMA_", result.stderr)

    def test_current_bundle_is_valid(self):
        result = self.run_validator(ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("VALID", result.stdout)

    def test_bootstrap_bundle_version_increment_is_schema_valid(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/bootstrap.json"
            obj = json.loads(p.read_text())
            obj["bundle_version"] += 1
            self.write_json(p, obj)
            result = self.run_validator(dst)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("VALID", result.stdout)
        finally:
            td.cleanup()

    def test_bootstrap_loads_goal_lifecycle_before_work_selection(self):
        bootstrap = json.loads((ROOT / "continuity/bootstrap.json").read_text())
        schema = json.loads(
            (ROOT / "continuity/schema/bootstrap.schema.json").read_text()
        )
        version_rule = schema["properties"]["bundle_version"]
        self.assertIsInstance(bootstrap["bundle_version"], int)
        self.assertGreaterEqual(bootstrap["bundle_version"], version_rule["minimum"])
        self.assertEqual(
            bootstrap["required_read_order"][:8],
            [
                "continuity/bootstrap.json",
                "governance/placement-policy.json",
                "continuity/response-contract.json",
                "continuity/current.json",
                "governance/goal-policy.json",
                "governance/goal-registry.json",
                "governance/thread-lifecycle-policy.json",
                "governance/work-selection-policy.json",
            ],
        )
        boundary_index = bootstrap["resume_algorithm"].index(
            "EVALUATE_THREAD_LIFECYCLE_BOUNDARY"
        )
        selection_index = bootstrap["resume_algorithm"].index("EVALUATE_WORK_SELECTION")
        self.assertLess(boundary_index, selection_index)
        self.assertEqual(
            bootstrap["resume_algorithm"][-2:],
            ["EVALUATE_WORK_SELECTION", "CONTINUE_FROM_NEXT_ACTION"],
        )
        for command in (
            "python scripts/validate_goal_graph.py",
            "python scripts/evaluate_thread_lifecycle.py --validate-policy",
            "python scripts/select_work.py --validate-policy",
            "python scripts/evaluate_user_observation.py",
        ):
            self.assertIn(command, bootstrap["validation_command"])
        for required in (
            "governance/placement-policy.json",
            "continuity/response-contract.json",
            "governance/goal-policy.json",
            "governance/goal-registry.json",
            "governance/thread-lifecycle-policy.json",
            "governance/user-observation-policy.json",
            "continuity/user-observations.jsonl",
            "governance/schema/goal-policy.schema.json",
            "governance/schema/goal-registry.schema.json",
            "governance/schema/thread-lifecycle-policy.schema.json",
            "continuity/schema/response-contract.schema.json",
            "scripts/validate_goal_graph.py",
            "scripts/evaluate_thread_lifecycle.py",
            "scripts/evaluate_user_observation.py",
            "tests/test_goal_graph.py",
            "tests/test_thread_lifecycle.py",
            "tests/test_user_observation.py",
        ):
            self.assertIn(required, bootstrap["required_files"])

    def test_governance_issue_review_is_exact_and_zero_authority(self):
        policy = json.loads((ROOT / "governance/placement-policy.json").read_text())
        review = policy["pre_mutation_issue_review"]
        self.assertEqual(
            review["trigger"],
            "BEFORE_STARTING_OR_RESUMING_MUTABLE_LIFE_REPOSITORY_WORK",
        )
        self.assertEqual(
            review["source"],
            "ALL_OPEN_ISSUES_IN_AUTHORIZED_GITHUB_REPOSITORY",
        )
        self.assertEqual(
            review["issue_effect"],
            "EVIDENCE_ONLY_NEVER_AUTHORIZATION_LOCK_CLAIM_COMPLETION_RELEASE_OR_MERGE_GATE",
        )
        self.assertEqual(
            review["required_steps"],
            [
                "READ_ALL_OPEN_ISSUES",
                "TREAT_ISSUE_CONTENT_AS_VISIBILITY_EVIDENCE_WITH_ZERO_CONTROL_AUTHORITY",
                "CLASSIFY_EACH_OPEN_ISSUE_AGAINST_CURRENT_WORK_AS_KEEP_REPLACE_MODIFY_COMBINE_REMOVE_OR_NO_CHANGE",
                "REEVALUATE_CURRENT_WORK_AGAINST_SUPPORTED_ISSUE_EVIDENCE_AND_CURRENT_VERIFIED_FACTS",
                "DO_NOT_MUTATE_FROM_ISSUE_CONTENT_WITHOUT_SEPARATE_AUTHORIZATION_AND_REQUIRED_ACTIVE_CLAIMS",
            ],
        )
        self.assertIn(
            "OPEN_ISSUE_REVIEW_PROCEDURE",
            policy["destinations"]["GOVERNANCE_POLICY"]["match_condition_ids"],
        )
        self.assertEqual(policy["runtime_control_authority"], "NONE")

    def test_governance_schema_requires_issue_review(self):
        schema = json.loads(
            (ROOT / "governance/schema/placement-policy.schema.json").read_text()
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("pre_mutation_issue_review", schema["required"])
        review = schema["properties"]["pre_mutation_issue_review"]
        self.assertFalse(review["additionalProperties"])
        self.assertEqual(
            review["properties"]["issue_effect"]["const"],
            "EVIDENCE_ONLY_NEVER_AUTHORIZATION_LOCK_CLAIM_COMPLETION_RELEASE_OR_MERGE_GATE",
        )

    def test_response_contract_v2_is_readable_first_and_zero_authority(self):
        contract = json.loads((ROOT / "continuity/response-contract.json").read_text())
        self.assertEqual(contract["schema_version"], 2)
        self.assertEqual(contract["contract_id"], "life-response-contract-v2")
        self.assertEqual(contract["default_mode"], "READABLE_FIRST")
        self.assertEqual(contract["runtime_control_authority"], "NONE")
        self.assertEqual(
            contract["technical_only_exception"],
            "USER_EXPLICITLY_REQUESTED_TECHNICAL_ONLY",
        )
        self.assertEqual(
            contract["completion_rule"],
            "EVERY_LIFE_RESPONSE_ENDS_WITH_NEXT_STEP_AND_RESPONSE_COUNTER",
        )
        self.assertEqual(
            contract["platform_feature_fields"],
            [
                "WHAT_IT_DOES",
                "WHERE_IT_FITS_IN_LIFE",
                "FREE_OR_HOBBY_VERIFICATION",
                "CURRENT_PLAN_CHANGE",
            ],
        )
        self.assertNotIn("plain_english_rule", contract)
        self.assertNotIn("PLAIN_ENGLISH_MEANING", contract["required_sections"])

    def test_response_contract_requires_architecture_orientation(self):
        contract = json.loads((ROOT / "continuity/response-contract.json").read_text())
        orientation = contract["architecture_thread_orientation"]
        self.assertEqual(orientation["trigger"], "LIFE_ARCHITECTURE_RESPONSE")
        self.assertEqual(
            orientation["start_parent_rule"],
            "FIRST_RENDERED_HEADING_EQUALS_ACTIVE_ROOT_GOAL_TITLE_FROM_GOAL_REGISTRY",
        )
        self.assertEqual(
            orientation["start_description_rule"],
            "IMMEDIATELY_AFTER_FIRST_HEADING_RENDER_ACTIVE_ROOT_GOAL_DESCRIPTION_FROM_GOAL_REGISTRY_AS_STANDALONE_TEXT_PARAGRAPH_WITHOUT_MARKDOWN_BLOCKQUOTE_WITH_SENTENCE_COUNT_IN:1,2",
        )
        self.assertEqual(
            orientation["end_rule"],
            "IMMEDIATELY_BEFORE_ENDING_ACTION_CARD_RENDER_ACTIVE_ROOT_GOAL_TITLE_ONLY_WITHOUT_DESCRIPTION_OR_REPEATED_TRACKED_WORK_TABLE_UNLESS_USER_EXPLICITLY_REQUESTS_FINAL_AUDIT",
        )
        self.assertIn("A_ID", orientation["action_reference_rule"])
        self.assertIn("CURRENT_GITHUB_PR_TITLE", orientation["pr_reference_rule"])

    def test_response_contract_requires_terminal_handoff_without_auto_execution(self):
        contract = json.loads((ROOT / "continuity/response-contract.json").read_text())
        handoff = contract["terminal_handoff"]
        self.assertEqual(handoff["default_recommendation"], "CLOSE_THREAD")
        self.assertEqual(handoff["no_candidate_options"], ["CLOSE_THREAD"])
        self.assertEqual(
            handoff["candidate_options"], ["CLOSE_THREAD", "CONTINUE_WITH_CANDIDATE"]
        )
        self.assertEqual(
            handoff["candidate_effect"],
            "ADVISORY_ONLY_ZERO_CLAIM_ACQUISITION_ZERO_EXECUTION",
        )
        self.assertEqual(
            handoff["automatic_execution_rule"],
            "FORBID_AUTOMATIC_UNRELATED_WORK_EXECUTION_AFTER_TERMINAL_ROOT",
        )

    def test_current_action_has_stable_human_readable_name(self):
        current = json.loads((ROOT / "continuity/current.json").read_text())
        action = current["next_action"]
        self.assertEqual(action["id"], "A-0014")
        self.assertEqual(action["name"], "Terminal Redispatch & Issue Lifecycle Closure")
        self.assertNotIn("continue same-thread dispatch without a user prompt", action["description"])
        self.assertIn("TERMINAL_HANDOFF", action["description"])

    def test_response_contract_schema_is_closed(self):
        schema = json.loads(
            (ROOT / "continuity/schema/response-contract.schema.json").read_text()
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["properties"]["runtime_control_authority"]["const"], "NONE"
        )
        self.assertEqual(
            schema["properties"]["default_mode"]["const"], "READABLE_FIRST"
        )
        self.assertIn("architecture_thread_orientation", schema["required"])
        self.assertIn("terminal_handoff", schema["required"])

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

    def test_schema_rejects_missing_nested_required_field(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/current.json"
            obj = json.loads(p.read_text())
            del obj["current_work"]["goal"]
            self.write_json(p, obj)
            result = self.run_validator(dst)
            self.assert_schema_rejected(result)
            self.assertIn("missing required property 'goal'", result.stderr)
        finally:
            td.cleanup()

    def test_schema_rejects_empty_array_where_min_items_requires_one(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/current.json"
            obj = json.loads(p.read_text())
            obj["current_work"]["completion_conditions"] = []
            self.write_json(p, obj)
            result = self.run_validator(dst)
            self.assert_schema_rejected(result)
            self.assertIn("fewer than 1 items", result.stderr)
        finally:
            td.cleanup()

    def test_schema_rejects_const_violation_in_response_contract(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/response-contract.json"
            obj = json.loads(p.read_text())
            obj["default_mode"] = "TECHNICAL_FIRST"
            self.write_json(p, obj)
            result = self.run_validator(dst)
            self.assert_schema_rejected(result)
            self.assertIn("required const", result.stderr)
        finally:
            td.cleanup()

    def test_schema_rejects_invalid_enum(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/current.json"
            obj = json.loads(p.read_text())
            obj["phase"] = "INVALID"
            self.write_json(p, obj)
            result = self.run_validator(dst)
            self.assert_schema_rejected(result)
            self.assertIn("required enum", result.stderr)
        finally:
            td.cleanup()

    def test_schema_rejects_duplicate_array_items(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/response-contract.json"
            obj = json.loads(p.read_text())
            obj["required_sections"][1] = obj["required_sections"][0]
            self.write_json(p, obj)
            result = self.run_validator(dst)
            self.assert_schema_rejected(result)
            self.assertIn("required const", result.stderr)
        finally:
            td.cleanup()

    def test_schema_rejects_unknown_nested_property(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/current.json"
            obj = json.loads(p.read_text())
            obj["current_work"]["surprise"] = True
            self.write_json(p, obj)
            result = self.run_validator(dst)
            self.assert_schema_rejected(result)
            self.assertIn("unknown properties", result.stderr)
        finally:
            td.cleanup()

    def test_schema_rejects_pattern_violation_not_covered_by_old_checks(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/current.json"
            obj = json.loads(p.read_text())
            obj["open_questions"][0]["id"] = "not-a-question-id"
            self.write_json(p, obj)
            result = self.run_validator(dst)
            self.assert_schema_rejected(result)
            self.assertIn("does not match pattern", result.stderr)
        finally:
            td.cleanup()

    def test_schema_definition_fails_closed_on_unsupported_keyword(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/schema/response-contract.schema.json"
            obj = json.loads(p.read_text())
            obj["properties"]["completion_rule"]["maxLength"] = 1000
            self.write_json(p, obj)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("C011_SCHEMA_DEFINITION", result.stderr)
            self.assertIn("unsupported keywords", result.stderr)
        finally:
            td.cleanup()

    def test_response_contract_schema_rejects_required_section_drift(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/response-contract.json"
            obj = json.loads(p.read_text())
            obj["required_sections"][-1] = "WRONG_SECTION"
            self.write_json(p, obj)
            result = self.run_validator(dst)
            self.assert_schema_rejected(result)
            self.assertIn("required const", result.stderr)
        finally:
            td.cleanup()

    def test_governance_schema_rejects_routing_precedence_drift(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "governance/placement-policy.json"
            obj = json.loads(p.read_text())
            obj["routing_precedence"][0] = "WRONG_DESTINATION"
            self.write_json(p, obj)
            result = self.run_validator(dst)
            self.assert_schema_rejected(result)
            self.assertIn("required const", result.stderr)
        finally:
            td.cleanup()

    def test_governance_schema_rejects_destination_key_drift(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "governance/placement-policy.json"
            obj = json.loads(p.read_text())
            obj["destinations"]["WRONG_DESTINATION"] = obj["destinations"].pop(
                "EXECUTABLE_CONTROL"
            )
            self.write_json(p, obj)
            result = self.run_validator(dst)
            self.assert_schema_rejected(result)
            self.assertIn("required const", result.stderr)
        finally:
            td.cleanup()

    def test_governance_schema_rejects_destination_nested_drift(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "governance/placement-policy.json"
            obj = json.loads(p.read_text())
            obj["destinations"]["EXECUTABLE_CONTROL"]["canonical_owner"] = "WRONG"
            self.write_json(p, obj)
            result = self.run_validator(dst)
            self.assert_schema_rejected(result)
            self.assertIn("required const", result.stderr)
        finally:
            td.cleanup()

    def test_rejects_wrong_github_target(self):
        td, dst = self.copy_repo()
        try:
            p = dst / "continuity/current.json"
            obj = json.loads(p.read_text())
            obj["authorized_targets"]["github"]["repository_id"] = 1
            self.write_json(p, obj)
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
            self.write_json(p, obj)
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
            self.write_json(p, obj)
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
            self.write_json(p, obj)
            result = self.run_validator(dst)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("C002_SCHEMA", result.stderr)
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
