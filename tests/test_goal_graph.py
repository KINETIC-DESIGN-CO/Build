import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/validate_goal_graph.py"
spec = importlib.util.spec_from_file_location("validate_goal_graph", MODULE_PATH)
goal_graph = importlib.util.module_from_spec(spec)
spec.loader.exec_module(goal_graph)


class GoalGraphValidationTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / "governance/goal-policy.json").read_text(encoding="utf-8"))
        self.registry = json.loads((ROOT / "governance/goal-registry.json").read_text(encoding="utf-8"))
        self.policy_schema = json.loads((ROOT / "governance/schema/goal-policy.schema.json").read_text(encoding="utf-8"))
        self.registry_schema = json.loads((ROOT / "governance/schema/goal-registry.schema.json").read_text(encoding="utf-8"))

    def validate(self, registry=None, policy=None):
        goal_graph.validate_policy(policy or self.policy, self.policy_schema)
        goal_graph.validate_registry(registry or self.registry, self.registry_schema)

    def test_canonical_goal_graph_validates(self):
        self.validate()

    def test_non_root_must_return_to_parent(self):
        registry = copy.deepcopy(self.registry)
        root = registry["goals"][0]
        child_id = "11111111-1111-4111-8111-111111111111"
        root["child_goal_ids"] = [child_id]
        registry["goals"].append({
            "goal_id": child_id,
            "root_goal_id": root["goal_id"],
            "parent_goal_id": root["goal_id"],
            "return_to_goal_id": None,
            "goal_relation": "PREREQUISITE",
            "goal_state": "ACTIVE",
            "title": "Child prerequisite",
            "completion_condition_ids": ["CHILD_COMPLETE"],
            "satisfied_condition_ids": [],
            "child_goal_ids": [],
            "execution_attempts": [],
            "source_refs": ["TEST"],
            "runtime_control_authority": "NONE",
        })
        registry["active_goal_id"] = child_id
        registry["active_path"] = [root["goal_id"], child_id]
        with self.assertRaises(goal_graph.GoalGraphError):
            self.validate(registry=registry)

    def test_active_path_must_follow_parent_chain(self):
        registry = copy.deepcopy(self.registry)
        root = registry["goals"][0]
        child_id = "22222222-2222-4222-8222-222222222222"
        root["child_goal_ids"] = [child_id]
        registry["goals"].append({
            "goal_id": child_id,
            "root_goal_id": root["goal_id"],
            "parent_goal_id": root["goal_id"],
            "return_to_goal_id": root["goal_id"],
            "goal_relation": "PREREQUISITE",
            "goal_state": "ACTIVE",
            "title": "Child prerequisite",
            "completion_condition_ids": ["CHILD_COMPLETE"],
            "satisfied_condition_ids": [],
            "child_goal_ids": [],
            "execution_attempts": [],
            "source_refs": ["TEST"],
            "runtime_control_authority": "NONE",
        })
        registry["active_goal_id"] = child_id
        registry["active_path"] = [child_id, root["goal_id"]]
        with self.assertRaises(goal_graph.GoalGraphError):
            self.validate(registry=registry)

    def test_complete_goal_requires_all_completion_conditions(self):
        registry = copy.deepcopy(self.registry)
        registry["goals"][0]["goal_state"] = "COMPLETE"
        registry["authorized_root_transition_id"] = "RT-0001"
        with self.assertRaises(goal_graph.GoalGraphError):
            self.validate(registry=registry)

    def test_execution_work_id_maps_to_exactly_one_goal(self):
        registry = copy.deepcopy(self.registry)
        root = registry["goals"][0]
        second_root_id = "33333333-3333-4333-8333-333333333333"
        registry["goals"].append({
            "goal_id": second_root_id,
            "root_goal_id": second_root_id,
            "parent_goal_id": None,
            "return_to_goal_id": None,
            "goal_relation": "ROOT",
            "goal_state": "ACTIVE",
            "title": "Second root",
            "completion_condition_ids": ["SECOND_ROOT_COMPLETE"],
            "satisfied_condition_ids": [],
            "child_goal_ids": [],
            "execution_attempts": copy.deepcopy(root["execution_attempts"]),
            "source_refs": ["TEST"],
            "runtime_control_authority": "NONE",
        })
        with self.assertRaises(goal_graph.GoalGraphError):
            self.validate(registry=registry)

    def test_policy_parent_first_rule_cannot_drift(self):
        policy = copy.deepcopy(self.policy)
        policy["child_terminal_rule"] = "SELECT_UNRELATED_ROOT"
        with self.assertRaises(goal_graph.GoalGraphError):
            self.validate(policy=policy)


if __name__ == "__main__":
    unittest.main()
