from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_goal_graph.py"
spec = importlib.util.spec_from_file_location("validate_goal_graph_revision", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class GoalRevisionTests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads((ROOT / "governance/goal-registry.json").read_text())

    def test_canonical_registry_is_v2_revision_fenced(self):
        root = self.registry["goals"][0]
        self.assertEqual(self.registry["schema_version"], 2)
        self.assertEqual(root["revision"], 1)
        self.assertEqual(root["control_signal"]["state"], "NONE")
        active = [a for a in root["execution_attempts"] if a["attempt_state"] == "ACTIVE"]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["planned_goal_revision"], root["revision"])

    def test_v1_to_v2_migration_requires_revision_one(self):
        previous = copy.deepcopy(self.registry)
        previous["schema_version"] = 1
        previous["registry_id"] = "life-engineering-goal-registry-v1"
        for goal in previous["goals"]:
            goal.pop("revision")
            goal.pop("control_signal")
            for attempt in goal["execution_attempts"]:
                attempt.pop("planned_goal_revision")
        mod.validate_revision_transition(previous, self.registry)
        bad = copy.deepcopy(self.registry)
        bad["goals"][0]["revision"] = 2
        with self.assertRaises(mod.GoalError):
            mod.validate_revision_transition(previous, bad)

    def test_requirement_change_requires_revision_plus_one(self):
        previous = copy.deepcopy(self.registry)
        current = copy.deepcopy(previous)
        current["goals"][0]["completion_condition_ids"].append("NEW_EXACT_REQUIREMENT")
        with self.assertRaises(mod.GoalError):
            mod.validate_revision_transition(previous, current)
        current["goals"][0]["revision"] += 1
        current["goals"][0]["control_signal"]["issued_for_revision"] += 1
        mod.validate_revision_transition(previous, current)

    def test_execution_progress_does_not_increment_requirement_revision(self):
        previous = copy.deepcopy(self.registry)
        current = copy.deepcopy(previous)
        current["goals"][0]["satisfied_condition_ids"].append("FINAL_ARCHITECTURE_THREAD_PRESENTATION_VERSIONED_AND_FALSIFIED")
        mod.validate_revision_transition(previous, current)

    def test_active_signal_requires_matching_active_vince_source(self):
        goal = copy.deepcopy(self.registry["goals"][0])
        goal["control_signal"] = {
            "state": "YIELD_OR_REPLAN_REQUESTED",
            "signal_id": "GS-0001",
            "target_work_id": "3edfca10-ac11-4a79-bd31-72bd84165594",
            "issued_for_revision": goal["revision"],
            "source_ref": "VINCE_DIRECTIVE:VD-0029",
        }
        directives = {
            "VD-0029": {
                "id": "VD-0029",
                "input_class": "VINCE_DIRECTIVE",
                "lifecycle": "ACTIVE",
            }
        }
        mod.validate_signal(goal, directives)
        goal["control_signal"]["source_ref"] = "VINCE_DIRECTIVE:VD-9999"
        with self.assertRaises(mod.GoalError):
            mod.validate_signal(goal, directives)


if __name__ == "__main__":
    unittest.main()
