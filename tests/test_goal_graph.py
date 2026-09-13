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

class GoalGraphTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / "governance/goal-policy.json").read_text())
        self.registry = json.loads((ROOT / "governance/goal-registry.json").read_text())
        self.policy_schema = json.loads((ROOT / "governance/schema/goal-policy.schema.json").read_text())
        self.registry_schema = json.loads((ROOT / "governance/schema/goal-registry.schema.json").read_text())

    def validate(self, registry=None, policy=None):
        goal_graph.validate_policy(policy or self.policy, self.policy_schema)
        return goal_graph.validate_registry(registry or self.registry, self.registry_schema, policy or self.policy)

    def test_canonical_goal_graph_validates(self):
        self.validate()

    def test_old_execution_attempt_is_superseded_and_new_attempt_is_active(self):
        root = self.registry["goals"][0]
        attempts = {item["work_id"]: item["attempt_state"] for item in root["execution_attempts"]}
        self.assertEqual(attempts["941b4a91-994e-45c4-a49b-7e9c6fc2254b"], "SUPERSEDED")
        self.assertEqual(attempts["3edfca10-ac11-4a79-bd31-72bd84165594"], "ACTIVE")

    def test_work_id_cannot_map_to_multiple_goals(self):
        registry = copy.deepcopy(self.registry)
        root = registry["goals"][0]
        second = copy.deepcopy(root)
        second["goal_id"] = "11111111-1111-4111-8111-111111111111"
        second["root_goal_id"] = second["goal_id"]
        second["title"] = "Second root"
        registry["goals"].append(second)
        with self.assertRaises(goal_graph.GoalError):
            self.validate(registry=registry)

    def test_terminal_goal_requires_all_completion_conditions(self):
        registry = copy.deepcopy(self.registry)
        root = registry["goals"][0]
        root["goal_state"] = "COMPLETE"
        root["terminal_cleanup_state"] = "VERIFIED"
        root["execution_attempts"][1]["attempt_state"] = "TERMINAL_SUCCESS"
        with self.assertRaises(goal_graph.GoalError):
            self.validate(registry=registry)

    def test_terminal_goal_rejects_active_attempt(self):
        registry = copy.deepcopy(self.registry)
        root = registry["goals"][0]
        root["goal_state"] = "COMPLETE"
        root["terminal_cleanup_state"] = "VERIFIED"
        root["satisfied_condition_ids"] = copy.deepcopy(root["completion_condition_ids"])
        with self.assertRaises(goal_graph.GoalError):
            self.validate(registry=registry)

    def test_non_root_must_return_to_parent(self):
        registry = copy.deepcopy(self.registry)
        root = registry["goals"][0]
        child_id = "22222222-2222-4222-8222-222222222222"
        root["child_goal_ids"].append(child_id)
        registry["goals"].append({
            "goal_id":child_id,
            "root_goal_id":root["goal_id"],
            "parent_goal_id":root["goal_id"],
            "return_to_goal_id":None,
            "component_id":"child_goal",
            "goal_relation":"PREREQUISITE",
            "goal_state":"ACTIVE",
            "terminal_cleanup_state":"PENDING",
            "title":"Child goal",
            "completion_condition_ids":["CHILD_COMPLETE"],
            "satisfied_condition_ids":[],
            "child_goal_ids":[],
            "execution_attempts":[],
            "source_refs":["TEST"],
            "runtime_control_authority":"NONE"
        })
        registry["active_goal_id"] = child_id
        registry["active_path"] = [root["goal_id"], child_id]
        with self.assertRaises(goal_graph.GoalError):
            self.validate(registry=registry)

    def test_active_path_must_follow_parent_chain(self):
        registry = copy.deepcopy(self.registry)
        registry["active_path"] = list(reversed(registry["active_path"])) + ["33333333-3333-4333-8333-333333333333"]
        with self.assertRaises(goal_graph.GoalError):
            self.validate(registry=registry)

    def test_parent_first_policy_cannot_drift(self):
        policy = copy.deepcopy(self.policy)
        policy["child_terminal_rule"] = "TERMINAL_CHILD_SELECTS_UNRELATED_WORK"
        with self.assertRaises(goal_graph.GoalError):
            self.validate(policy=policy)

if __name__ == "__main__":
    unittest.main()
