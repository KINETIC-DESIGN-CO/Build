from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ResponseContractPresentationTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((ROOT / "continuity/response-contract.json").read_text())
        self.orientation = self.contract["architecture_thread_orientation"]

    def test_goal_quote_is_definition_only_and_bounded(self):
        self.assertEqual(
            self.orientation["quote_boundary_rule"],
            "GOAL_DESCRIPTION_QUOTE_CONTAINS_ONLY_GOAL_DESCRIPTION_AND_ENDS_BEFORE_USER_ACTION_TRACKED_WORK_BODY_OR_NEXT_STEP",
        )

    def test_user_action_has_closed_outcomes(self):
        self.assertEqual(
            self.orientation["user_action_states"],
            ["CONTINUE_THIS_THREAD", "CLOSE_THIS_THREAD", "WAIT_AND_RETURN", "ACTION_REQUIRED"],
        )
        self.assertIn("OUTSIDE_ANY_GOAL_QUOTE", self.orientation["user_action_rule"])

    def test_tracked_work_requires_two_column_table(self):
        self.assertEqual(
            self.orientation["tracked_work_layout_rule"],
            "TRACKED_WORK_RENDERS_AS_TWO_COLUMN_MARKDOWN_TABLE_WITH_STATUS_EMOJI_ONLY_IN_COLUMN_ONE_AND_COMPLETE_ITEM_TEXT_IN_COLUMN_TWO",
        )
        self.assertIn("EMOJI_PREFIXED_ORDINARY_PARAGRAPHS", self.orientation["tracked_work_prohibited_forms"])
        self.assertIn("HANGING_INDENT_PARAGRAPHS", self.orientation["tracked_work_prohibited_forms"])

    def test_status_vocabulary_is_closed_and_complete(self):
        self.assertEqual(
            set(self.orientation["tracked_work_statuses"]),
            {"✅", "☑️", "⛔️", "💡", "🛠️", "🧪", "⏸️", "📥", "🔁", "❓"},
        )

    def test_unknown_or_chat_only_obligation_blocks_clean_terminal_handoff(self):
        rule = self.orientation["no_loose_ends_rule"]
        self.assertIn("UNKNOWN_OR_CHAT_ONLY_ACCOUNTABILITY_FORBIDS_CLEAN_TERMINAL_HANDOFF", rule)
        self.assertIn("DURABLE_OWNER_OR_REFERENCE", rule)

    def test_ending_stays_compact(self):
        self.assertEqual(
            self.orientation["end_rule"],
            "IMMEDIATELY_BEFORE_NEXT_STEP_RENDER_ACTIVE_ROOT_GOAL_TITLE_ONLY_WITHOUT_DESCRIPTION_OR_REPEATED_TRACKED_WORK_TABLE_UNLESS_USER_EXPLICITLY_REQUESTS_FINAL_AUDIT",
        )


if __name__ == "__main__":
    unittest.main()
