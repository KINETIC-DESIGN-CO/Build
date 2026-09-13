from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReliabilityGoalLinkTests(unittest.TestCase):
    def test_reliability_uses_active_canonical_goal_owner(self):
        spec = json.loads((ROOT / "reliability/spec.json").read_text())
        compatibility = json.loads((ROOT / "reliability/compatibility-map.json").read_text())
        links = spec["cross_links"]
        self.assertEqual(links["goal_root_identity_owner_path"], "governance/goal-registry.json")
        self.assertEqual(links["goal_root_identity_link_state"], "ACTIVE")
        self.assertTrue((ROOT / links["goal_root_identity_owner_path"]).is_file())
        goal = compatibility["goal_identity"]
        self.assertEqual(goal["relationship"], "COMBINE_ACTIVE_CANONICAL_GOAL_OWNER")
        self.assertEqual(goal["current_owner_path"], links["goal_root_identity_owner_path"])
        self.assertEqual(goal["state"], links["goal_root_identity_link_state"])
        self.assertEqual(
            goal["rule"],
            "RELIABILITY_PRESERVES_ROOT_AND_PARENT_IDENTITIES_FROM_THE_CANONICAL_GOAL_OWNER_AND_DOES_NOT_INFER_SEMANTIC_IDENTITY_FROM_WORK_ID",
        )


if __name__ == "__main__":
    unittest.main()
