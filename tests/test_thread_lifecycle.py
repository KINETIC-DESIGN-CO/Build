import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/evaluate_thread_lifecycle.py"
spec = importlib.util.spec_from_file_location("evaluate_thread_lifecycle", MODULE_PATH)
lifecycle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lifecycle)

GOAL_REGISTRY = ROOT / "governance/goal-registry.json"
ADMISSIONS = ROOT / "governance/work-admissions.json"

class ThreadLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.registry_text = GOAL_REGISTRY.read_text()
        self.admissions_text = ADMISSIONS.read_text()
        self.registry = json.loads(self.registry_text)
        self.admissions = json.loads(self.admissions_text)

    def tearDown(self):
        GOAL_REGISTRY.write_text(self.registry_text)
        ADMISSIONS.write_text(self.admissions_text)

    def keys(self):
        return lifecycle.required_keys(json.loads(GOAL_REGISTRY.read_text()), json.loads(ADMISSIONS.read_text()))

    def lock(self, key, work_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", expires="2026-09-14T00:00:00Z", state="ACTIVE"):
        return {
            "schema_version":1,
            "resource_key":key,
            "generation":1,
            "state":state,
            "work_id":work_id,
            "worker":{"kind":"chatgpt","session_id":"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"},
            "implementation_branch":f"work/{work_id}",
            "lease_id":"cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            "base_sha":"0" * 40,
            "acquired_at":"2026-09-13T18:00:00Z",
            "heartbeat_at":"2026-09-13T18:00:00Z",
            "expires_at":expires,
            "runtime_control_authority":"NONE"
        }

    def snapshot(self, overrides=None, interruption="NONE"):
        resources = {key:None for key in self.keys()}
        resources.update(overrides or {})
        return {"observed_at":"2026-09-13T19:00:00Z","interrupted_operation_state":interruption,"resources":resources}

    def ensure_dispatchable_candidate(self):
        admissions = json.loads(ADMISSIONS.read_text())
        states = {item["work_item_id"]: item["state"] for item in admissions["items"]}
        if any(
            item["state"] == "ADMITTED"
            and all(states.get(dependency) == "COMPLETE" for dependency in item["depends_on"])
            for item in admissions["items"]
        ):
            return
        synthetic_number = 900101
        existing_ids = {item["work_item_id"] for item in admissions["items"]}
        while f"github-issue-{synthetic_number}" in existing_ids:
            synthetic_number += 1
        admissions["items"].append({
            "work_item_id": f"github-issue-{synthetic_number}",
            "source_issue_number": synthetic_number,
            "component_id": f"issue_{synthetic_number}",
            "dispatch_tier": 1000,
            "state": "ADMITTED",
            "depends_on": [],
        })
        ADMISSIONS.write_text(json.dumps(admissions, indent=2) + "\n")

    def make_terminal_root(self):
        registry = json.loads(GOAL_REGISTRY.read_text())
        root = registry["goals"][0]
        root["goal_state"] = "COMPLETE"
        root["terminal_cleanup_state"] = "VERIFIED"
        root["satisfied_condition_ids"] = copy.deepcopy(root["completion_condition_ids"])
        for attempt in root["execution_attempts"]:
            if attempt["attempt_state"] == "ACTIVE":
                attempt["attempt_state"] = "TERMINAL_SUCCESS"
        GOAL_REGISTRY.write_text(json.dumps(registry, indent=2) + "\n")
        return root

    def test_policy_validates(self):
        lifecycle.validate_policy(lifecycle.load(lifecycle.POLICY_PATH), lifecycle.load(lifecycle.POLICY_SCHEMA_PATH))

    def test_active_root_continues_instead_of_selecting_backlog(self):
        result = lifecycle.evaluate(self.snapshot(), "3edfca10-ac11-4a79-bd31-72bd84165594")
        self.assertEqual(result["boundary_state"], "CONTINUE_ACTIVE_GOAL")
        self.assertEqual(result["downstream_work_selection_effect"], "ZERO")
        self.assertEqual(result["recommendation"], "CONTINUE_ORIGINAL_GOAL")

    def test_unresolved_operation_resumes_before_goal_or_backlog(self):
        result = lifecycle.evaluate(self.snapshot(interruption="UNKNOWN"))
        self.assertEqual(result["boundary_state"], "RESUME_INTERRUPTED_OPERATION")
        self.assertEqual(result["downstream_work_selection_effect"], "ZERO")

    def test_terminal_child_returns_to_nonterminal_parent(self):
        registry = json.loads(GOAL_REGISTRY.read_text())
        root = registry["goals"][0]
        child_id = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
        root["child_goal_ids"].append(child_id)
        root["revision"] += 1
        root["control_signal"]["issued_for_revision"] = root["revision"]
        for attempt in root["execution_attempts"]:
            if attempt["attempt_state"] == "ACTIVE":
                attempt["planned_goal_revision"] = root["revision"]
        registry["goals"].append({
            "goal_id":child_id,"root_goal_id":root["goal_id"],"parent_goal_id":root["goal_id"],"return_to_goal_id":root["goal_id"],
            "component_id":"child_goal","goal_relation":"VERIFICATION","goal_state":"COMPLETE","terminal_cleanup_state":"VERIFIED","title":"Verification child","description":"Verify terminal child return to the nonterminal parent goal.",
            "revision":1,"control_signal":{"state":"NONE","signal_id":None,"target_work_id":None,"issued_for_revision":1,"source_ref":None},
            "completion_condition_ids":["CHILD_DONE"],"satisfied_condition_ids":["CHILD_DONE"],"child_goal_ids":[],
            "execution_attempts":[{"work_id":"eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee","attempt_state":"TERMINAL_SUCCESS","planned_goal_revision":1}],
            "source_refs":["TEST"],"runtime_control_authority":"NONE"
        })
        registry["active_goal_id"] = child_id
        registry["active_path"] = [root["goal_id"], child_id]
        GOAL_REGISTRY.write_text(json.dumps(registry, indent=2) + "\n")
        result = lifecycle.evaluate(self.snapshot(), "3edfca10-ac11-4a79-bd31-72bd84165594")
        self.assertEqual(result["boundary_state"], "RETURN_TO_PARENT_GOAL")
        self.assertEqual(result["effective_goal_id"], root["goal_id"])
        self.assertEqual(result["downstream_work_selection_effect"], "ZERO")

    def test_other_worker_owning_active_root_delegates_to_work_selection(self):
        key = "component:goal_lifecycle_identity"
        result = lifecycle.evaluate(self.snapshot({key:self.lock(key)}), "3edfca10-ac11-4a79-bd31-72bd84165594")
        self.assertEqual(result["boundary_state"], "DELEGATE_TO_WORK_SELECTION")
        self.assertEqual(result["downstream_work_selection_effect"], "DELEGATE")

    def test_requester_owning_root_continues_original_goal(self):
        key = "component:goal_lifecycle_identity"
        result = lifecycle.evaluate(self.snapshot({key:self.lock(key, work_id="3edfca10-ac11-4a79-bd31-72bd84165594")}), "3edfca10-ac11-4a79-bd31-72bd84165594")
        self.assertEqual(result["boundary_state"], "CONTINUE_ACTIVE_GOAL")
        self.assertEqual(result["downstream_work_selection_effect"], "ZERO")

    def test_terminal_root_with_live_claim_requires_cleanup(self):
        root = self.make_terminal_root()
        key = f"component:{root['component_id']}"
        result = lifecycle.evaluate(self.snapshot({key:self.lock(key, work_id="3edfca10-ac11-4a79-bd31-72bd84165594")}), "3edfca10-ac11-4a79-bd31-72bd84165594")
        self.assertEqual(result["boundary_state"], "TERMINAL_CLEANUP_REQUIRED")
        self.assertEqual(result["candidate"], None)
        self.assertEqual(result["downstream_work_selection_effect"], "ZERO")

    def test_terminal_root_discovers_candidate_but_defaults_to_close(self):
        self.ensure_dispatchable_candidate()
        self.make_terminal_root()
        result = lifecycle.evaluate(self.snapshot())
        self.assertEqual(result["boundary_state"], "TERMINAL_HANDOFF")
        self.assertEqual(result["terminal_handoff_state"], "SAFE_TO_CLOSE_WITH_CANDIDATE")
        self.assertIsNotNone(result["candidate"])
        self.assertEqual(result["recommendation"], "CLOSE_THREAD")
        self.assertEqual(result["options"], ["CLOSE_THREAD","CONTINUE_WITH_CANDIDATE"])
        self.assertEqual(result["downstream_work_selection_effect"], "ZERO")

    def test_terminal_root_candidate_discovery_does_not_create_claim(self):
        self.make_terminal_root()
        snapshot = self.snapshot()
        before = copy.deepcopy(snapshot)
        lifecycle.evaluate(snapshot)
        self.assertEqual(snapshot, before)

    def test_terminal_root_without_candidate_has_close_only(self):
        self.make_terminal_root()
        admissions = json.loads(ADMISSIONS.read_text())
        for item in admissions["items"]:
            if item["state"] == "ADMITTED":
                item["state"] = "REMOVED"
        ADMISSIONS.write_text(json.dumps(admissions, indent=2) + "\n")
        result = lifecycle.evaluate(self.snapshot())
        self.assertEqual(result["terminal_handoff_state"], "SAFE_TO_CLOSE_NO_CANDIDATE")
        self.assertEqual(result["options"], ["CLOSE_THREAD"])

    def test_missing_resource_evidence_fails_closed(self):
        snap = self.snapshot()
        del snap["resources"][next(iter(snap["resources"]))]
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.evaluate(snap)

if __name__ == "__main__":
    unittest.main()
