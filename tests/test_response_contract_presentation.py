from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ResponseContractPresentationTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((ROOT / "continuity/response-contract.json").read_text())
        self.orientation = self.contract["architecture_thread_orientation"]

    def test_goal_description_is_bounded_blockquote_and_content_isolated(self):
        self.assertEqual(
            self.orientation["start_description_rule"],
            "IMMEDIATELY_AFTER_FIRST_HEADING_RENDER_ACTIVE_ROOT_GOAL_DESCRIPTION_FROM_GOAL_REGISTRY_AS_ITS_OWN_BOUNDED_MARKDOWN_BLOCKQUOTE_WITH_SENTENCE_COUNT_IN:1,2",
        )
        self.assertIn("OWN_SEPARATELY_BOUNDED_MARKDOWN_BLOCKQUOTE", self.orientation["child_rule"])
        self.assertIn("CONTAINS_ONLY_GOAL_DESCRIPTION", self.orientation["description_boundary_rule"])
        self.assertIn("TERMINATES_BEFORE_OPENING_VINCE_ACTION", self.orientation["description_boundary_rule"])
        self.assertNotIn("WITHOUT_MARKDOWN_BLOCKQUOTE", self.orientation["start_description_rule"])

    def test_required_regions_are_closed_and_compositional(self):
        self.assertEqual(
            self.orientation["required_response_regions"],
            [
                "PARENT_GOAL_HEADING",
                "STANDALONE_GOAL_DESCRIPTION",
                "OPENING_VINCE_ACTION",
                "OPENING_TRACKED_WORK_CHECKLIST",
                "RESPONSE_BODY",
                "COMPACT_PARENT_GOAL_NAME",
                "ENDING_ACTION_CARD",
                "RESPONSE_COUNTER",
            ],
        )
        self.assertIn(
            "PRESERVE_ALL_UNSUPERSEDED_REQUIRED_RESPONSE_REGIONS",
            self.orientation["composition_rule"],
        )
        self.assertIn(
            "ZERO_IMPLIED_DELETION_EFFECT",
            self.orientation["composition_rule"],
        )

    def test_opening_vince_action_is_unquoted_exact_state(self):
        self.assertEqual(
            self.orientation["opening_action_states"],
            [
                "CONTINUE_THIS_THREAD",
                "CLOSE_THIS_THREAD",
                "WAIT_AND_RETURN",
                "ACTION_REQUIRED",
                "YOUR_ACTION_UNKNOWN",
            ],
        )
        rule = self.orientation["opening_action_rule"]
        self.assertIn("IMMEDIATELY_AFTER_OPENING_ORIENTATION", rule)
        self.assertIn("UNQUOTED", rule)
        self.assertIn("🏁_YOUR_ACTION", rule)
        self.assertIn("MUST_NOT_APPEAR_INSIDE_ANY_GOAL_BLOCKQUOTE", rule)

    def test_tracked_work_requires_opening_two_column_table(self):
        self.assertEqual(
            self.orientation["tracked_work_layout_rule"],
            "OPENING_TRACKED_WORK_CHECKLIST_RENDERS_AS_TWO_COLUMN_MARKDOWN_TABLE_WITH_STATUS_EMOJI_ONLY_IN_COLUMN_ONE_AND_COMPLETE_ITEM_TEXT_IN_COLUMN_TWO",
        )
        self.assertIn("EMOJI_PREFIXED_ORDINARY_PARAGRAPHS", self.orientation["tracked_work_prohibited_forms"])
        self.assertIn("HANGING_INDENT_PARAGRAPHS", self.orientation["tracked_work_prohibited_forms"])

    def test_status_vocabulary_is_closed_and_complete(self):
        self.assertEqual(
            set(self.orientation["tracked_work_statuses"]),
            {"✅", "☑️", "⛔️", "💡", "🛠️", "🧪", "⏸️", "📥", "🔁", "❓"},
        )

    def test_action_card_is_typed_and_your_action_is_last(self):
        self.assertEqual(
            self.orientation["action_card_row_order"],
            ["SYSTEM_OWNER", "EXECUTION_STATE", "SYSTEM_NEXT_STEP", "SUGGESTION", "YOUR_ACTION"],
        )
        self.assertEqual(self.orientation["action_card_row_order"][-1], "YOUR_ACTION")
        self.assertEqual(
            self.orientation["your_action_states"],
            [
                "CONTINUE_THIS_THREAD",
                "CLOSE_THIS_THREAD_OTHER_WORK_OWNS_REMAINDER",
                "CLOSE_THIS_THREAD_NO_REMAINING_WORK",
                "YOUR_ACTION_UNKNOWN",
            ],
        )
        self.assertIn("NO_ACTION_REQUIRED_ALONE_IS_INSUFFICIENT", self.orientation["your_action_rule"])

    def test_next_step_is_actor_first_without_background_execution_inference(self):
        self.assertEqual(
            self.orientation["system_owner_states"],
            [
                "THIS_THREAD_OWNS_NEXT_WORK",
                "OTHER_WORKER_OWNS_NEXT_WORK",
                "VINCE_ACTION_REQUIRED",
                "NO_FURTHER_SYSTEM_WORK",
                "OWNERSHIP_UNKNOWN",
            ],
        )
        self.assertIn("ACTOR_FIRST", self.orientation["system_next_step_rule"])
        self.assertIn(
            "SOURCE_OWNERSHIP_ALONE_CANNOT_ASSERT_CONTINUOUS_BACKGROUND_EXECUTION",
            self.orientation["execution_state_rule"],
        )
        self.assertIn("THIS_THREAD_OWNS_SELECTED_EXECUTABLE_WORK", self.contract["current_job_rule"])

    def test_pre_close_review_and_suggestion_are_exact(self):
        self.assertEqual(
            self.orientation["pre_close_review_categories"],
            [
                "UNRESOLVED_TRACKED_OBLIGATION",
                "RECURRING_FRICTION_OR_CORRECTION",
                "DUPLICATE_OR_SUPERSEDED_MECHANISM",
                "MISSING_VERIFICATION_OR_FALSIFICATION",
                "RESEARCH_DESIGN_CHANGE",
                "NATIVE_PLATFORM_SIMPLIFICATION",
                "PRESENTATION_OR_INTERACTION_IMPROVEMENT",
            ],
        )
        self.assertIn("BEFORE_ANY_CLOSE_THIS_THREAD_DISPOSITION", self.orientation["pre_close_review_rule"])
        self.assertIn("EXACTLY_ONE_SUGGESTION_ROW_IMMEDIATELY_BEFORE_YOUR_ACTION", self.orientation["suggestion_rule"])
        self.assertIn("ZERO_RUNTIME_CONTROL", self.orientation["suggestion_rule"])

    def test_unknown_or_chat_only_obligation_blocks_clean_terminal_handoff(self):
        rule = self.orientation["no_loose_ends_rule"]
        self.assertIn("UNKNOWN_OR_CHAT_ONLY_ACCOUNTABILITY_FORBIDS_CLEAN_TERMINAL_HANDOFF", rule)
        self.assertIn("DURABLE_OWNER_OR_REFERENCE", rule)

    def test_ending_stays_compact(self):
        self.assertEqual(
            self.orientation["end_rule"],
            "IMMEDIATELY_BEFORE_ENDING_ACTION_CARD_RENDER_ACTIVE_ROOT_GOAL_TITLE_ONLY_WITHOUT_DESCRIPTION_OR_REPEATED_TRACKED_WORK_TABLE_UNLESS_USER_EXPLICITLY_REQUESTS_FINAL_AUDIT",
        )


if __name__ == "__main__":
    unittest.main()
