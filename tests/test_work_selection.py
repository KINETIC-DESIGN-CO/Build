import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance/work-selection-policy.json"
ADMISSIONS_PATH = ROOT / "governance/work-admissions.json"
CURRENT_PATH = ROOT / "continuity/current.json"


class WorkSelectionTests(unittest.TestCase):
    def setUp(self):
        self.original_policy = POLICY_PATH.read_text(encoding="utf-8")
        self.original_admissions = ADMISSIONS_PATH.read_text(encoding="utf-8")
        self.original_current = CURRENT_PATH.read_text(encoding="utf-8")
        current = json.loads(self.original_current)
        current["current_status"] = "ACTIVE"
        CURRENT_PATH.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")

    def tearDown(self):
        POLICY_PATH.write_text(self.original_policy, encoding="utf-8")
        ADMISSIONS_PATH.write_text(self.original_admissions, encoding="utf-8")
        CURRENT_PATH.write_text(self.original_current, encoding="utf-8")

    def run_selector(self, args):
        return subprocess.run(["python", "scripts/select_work.py", *args], cwd=ROOT, text=True, capture_output=True)

    def base_evidence(self):
        return {
            "worker_lane": "FOREGROUND",
            "pending_continuity_event_ids": [],
            "canonical_live_mismatch_ids": [],
            "continuity_sync_claim_state": "NONE",
            "continuity_resource_intersection": "NOT_EVALUATED",
            "interrupted_operation_state": "NONE",
            "current_status": "ACTIVE",
            "open_blocker_ids": [],
            "current_next_action_id": "A-0012",
            "parallel_request_state": "NONE",
            "parallel_work_item_id": None,
            "parallel_resource_intersection": "NOT_EVALUATED",
            "selected_rank_before": None,
            "selected_work_terminal": True,
        }

    def parallel_evidence(self, item="github-issue-12"):
        value = self.base_evidence()
        value.update({
            "worker_lane": "PARALLEL_ASSIGNED",
            "parallel_request_state": "REQUESTED",
            "parallel_work_item_id": item,
            "parallel_resource_intersection": "INTERSECTION_EMPTY",
        })
        return value

    def evaluate(self, evidence):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "evidence.json"
            path.write_text(json.dumps(evidence) + "\n", encoding="utf-8")
            proc = self.run_selector(["--evaluate", str(path)])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def required_dispatch_keys(self):
        current = json.loads(CURRENT_PATH.read_text())
        admissions = json.loads(ADMISSIONS_PATH.read_text())
        keys = {"continuity:sync", f"component:{current['current_component']}"}
        keys.update(f"component:{item['component_id']}" for item in admissions["items"] if item["state"] == "ADMITTED")
        return sorted(keys)

    def lock(self, key, expires="2026-09-12T18:00:00Z", state="ACTIVE"):
        return {
            "schema_version": 1,
            "resource_key": key,
            "generation": 1,
            "state": state,
            "work_id": "11111111-1111-4111-8111-111111111111",
            "worker": {"kind": "chatgpt", "session_id": "22222222-2222-4222-8222-222222222222"},
            "implementation_branch": "work/11111111-1111-4111-8111-111111111111",
            "lease_id": "33333333-3333-4333-8333-333333333333",
            "base_sha": "0" * 40,
            "acquired_at": "2026-09-12T13:00:00Z",
            "heartbeat_at": "2026-09-12T13:00:00Z",
            "expires_at": expires,
            "runtime_control_authority": "NONE",
        }

    def snapshot(self, overrides=None, observed_at="2026-09-12T14:00:00Z"):
        resources = {key: None for key in self.required_dispatch_keys()}
        resources.update(overrides or {})
        return {"observed_at": observed_at, "resources": resources}

    def dispatch(self, snapshot):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "snapshot.json"
            path.write_text(json.dumps(snapshot) + "\n", encoding="utf-8")
            proc = self.run_selector(["--dispatch-snapshot", str(path)])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_policy_validates_as_v4(self):
        proc = self.run_selector(["--validate-policy"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        policy = json.loads(POLICY_PATH.read_text())
        self.assertEqual(policy["schema_version"], 4)
        self.assertEqual(policy["policy_id"], "life-engineering-work-selection-v4")
        self.assertEqual(policy["fresh_thread_dispatch"]["mode"], "LIVE_LOCK_DERIVED")
        self.assertEqual(policy["fresh_thread_dispatch"]["worker_lane_input_rule"], "FRESH_THREAD_WORKER_LANE_MUST_BE_DERIVED_NOT_CALLER_ASSIGNED")

    def test_terminal_redispatch_is_exact_same_thread_loop(self):
        policy = json.loads(POLICY_PATH.read_text())
        terminal = policy["terminal_redispatch"]
        self.assertEqual(
            terminal["trigger"],
            "SELECTED_WORK_TERMINAL_AND_REQUIRED_COMPLETION_CLEANUP_VERIFIED",
        )
        self.assertEqual(
            terminal["same_thread_action"],
            "RERUN_LIVE_FRESH_THREAD_DISPATCH_WITHOUT_USER_PROMPT",
        )
        self.assertEqual(
            terminal["issue_review_rule"],
            "RUN_PLACEMENT_POLICY_OPEN_ISSUE_REVIEW_BEFORE_EACH_NEW_MUTABLE_WORK_ITEM",
        )
        self.assertEqual(
            terminal["repeat_rule"],
            "AFTER_EACH_TERMINAL_WORK_ITEM_REPEAT_TERMINAL_REDISPATCH",
        )
        self.assertEqual(
            terminal["stop_states"],
            [
                "NO_ELIGIBLE_WORK",
                "REQUIRED_LIVE_READ_NOT_RUN",
                "UNSUPPORTED_OR_UNAUTHORIZED_OPERATION",
            ],
        )

    def test_legacy_rank_zero_foreground_continuity_still_works(self):
        evidence = self.base_evidence()
        evidence["pending_continuity_event_ids"] = ["E-PENDING-1"]
        result = self.evaluate(evidence)
        self.assertEqual(result["effective_rank"], 0)
        self.assertEqual(result["selected_work"], "CONTINUITY_SYNC")

    def test_legacy_disjoint_parallel_rank_four_still_works(self):
        evidence = self.parallel_evidence()
        evidence["pending_continuity_event_ids"] = ["E-PENDING-1"]
        evidence["continuity_resource_intersection"] = "INTERSECTION_EMPTY"
        result = self.evaluate(evidence)
        self.assertEqual(result["effective_rank"], 4)
        self.assertEqual(result["selected_work"], "PARALLEL_ADMITTED_WORK")

    def test_fresh_thread_foreground_is_derived_when_component_is_free(self):
        result = self.dispatch(self.snapshot())
        self.assertEqual(result["worker_lane"], "FOREGROUND")
        self.assertEqual(result["effective_rank"], 3)
        self.assertEqual(result["selected_work"], "CURRENT_NEXT_ACTION")
        self.assertEqual(result["claim_next_resource_key"], "component:multi_thread_coordination_hardening")

    def test_completed_current_work_routes_fresh_thread_to_parallel(self):
        current = json.loads(CURRENT_PATH.read_text())
        current["current_status"] = "COMPLETE"
        CURRENT_PATH.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        result = self.dispatch(self.snapshot())
        self.assertEqual(result["worker_lane"], "PARALLEL_ASSIGNED")
        self.assertEqual(result["work_item_id"], "github-issue-12")
        self.assertEqual(result["claim_next_resource_key"], "component:issue_12")

    def test_terminal_redispatch_skips_busy_issue_and_selects_next_admitted_issue(self):
        current = json.loads(CURRENT_PATH.read_text())
        current["current_status"] = "COMPLETE"
        CURRENT_PATH.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        issue12 = "component:issue_12"
        result = self.dispatch(self.snapshot({issue12: self.lock(issue12)}))
        self.assertEqual(result["worker_lane"], "PARALLEL_ASSIGNED")
        self.assertEqual(result["work_item_id"], "github-issue-15")
        self.assertEqual(result["claim_next_resource_key"], "component:issue_15")

    def test_fresh_thread_becomes_parallel_when_foreground_component_is_owned(self):
        key = "component:multi_thread_coordination_hardening"
        result = self.dispatch(self.snapshot({key: self.lock(key)}))
        self.assertEqual(result["worker_lane"], "PARALLEL_ASSIGNED")
        self.assertEqual(result["work_item_id"], "github-issue-12")
        self.assertEqual(result["claim_next_resource_key"], "component:issue_12")

    def test_active_continuity_claim_also_routes_fresh_thread_to_parallel(self):
        key = "continuity:sync"
        result = self.dispatch(self.snapshot({key: self.lock(key)}))
        self.assertEqual(result["worker_lane"], "PARALLEL_ASSIGNED")
        self.assertEqual(result["work_item_id"], "github-issue-12")

    def test_parallel_auto_selection_skips_owned_component(self):
        current_key = "component:multi_thread_coordination_hardening"
        issue12 = "component:issue_12"
        result = self.dispatch(self.snapshot({current_key: self.lock(current_key), issue12: self.lock(issue12)}))
        self.assertEqual(result["work_item_id"], "github-issue-15")
        self.assertEqual(result["claim_next_resource_key"], "component:issue_15")

    def test_expired_component_claim_is_available(self):
        current_key = "component:multi_thread_coordination_hardening"
        issue12 = "component:issue_12"
        result = self.dispatch(self.snapshot({current_key: self.lock(current_key), issue12: self.lock(issue12, expires="2026-09-12T13:59:59Z")}))
        self.assertEqual(result["work_item_id"], "github-issue-12")

    def test_dependency_blocks_issue_18_when_issue_21_not_complete(self):
        current_key = "component:multi_thread_coordination_hardening"
        overrides = {current_key: self.lock(current_key)}
        for n in (12, 15, 16, 17, 21, 30):
            key = f"component:issue_{n}"
            overrides[key] = self.lock(key)
        result = self.dispatch(self.snapshot(overrides))
        self.assertEqual(result["decision"], "NO_ELIGIBLE_WORK")
        self.assertIsNone(result["work_item_id"])

    def test_dependency_unlocks_issue_18_after_issue_21_complete(self):
        admissions = json.loads(ADMISSIONS_PATH.read_text())
        for item in admissions["items"]:
            if item["work_item_id"] == "github-issue-21":
                item["state"] = "COMPLETE"
        ADMISSIONS_PATH.write_text(json.dumps(admissions, indent=2) + "\n")
        current_key = "component:multi_thread_coordination_hardening"
        overrides = {current_key: self.lock(current_key)}
        for n in (12, 15, 16, 17):
            key = f"component:issue_{n}"
            overrides[key] = self.lock(key)
        result = self.dispatch(self.snapshot(overrides))
        self.assertEqual(result["work_item_id"], "github-issue-18")

    def test_snapshot_must_cover_every_required_component_resource(self):
        snap = self.snapshot()
        del snap["resources"]["component:issue_12"]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "snapshot.json"
            path.write_text(json.dumps(snap) + "\n")
            proc = self.run_selector(["--dispatch-snapshot", str(path)])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("resource coverage mismatch", proc.stderr)

    def test_malformed_live_lock_fails_closed(self):
        key = "component:multi_thread_coordination_hardening"
        bad = self.lock(key)
        del bad["lease_id"]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "snapshot.json"
            path.write_text(json.dumps(self.snapshot({key: bad})) + "\n")
            proc = self.run_selector(["--dispatch-snapshot", str(path)])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("lock shape mismatch", proc.stderr)

    def test_parallel_race_rule_requires_cas_and_redispatch(self):
        policy = json.loads(POLICY_PATH.read_text())
        self.assertEqual(policy["fresh_thread_dispatch"]["race_rule"], "AFTER_PARALLEL_SELECTION_ACQUIRE_SELECTED_COMPONENT_CLAIM_BY_COMPARE_AND_SWAP;ON_CONFLICT_REREAD_LIVE_LOCK_AND_REDISPATCH")

    def test_terminal_race_rule_requires_cas_reread_and_redispatch_without_prompt(self):
        policy = json.loads(POLICY_PATH.read_text())
        self.assertEqual(
            policy["terminal_redispatch"]["race_rule"],
            "ON_CLAIM_COMPARE_AND_SWAP_CONFLICT_REREAD_LIVE_LOCK_AND_REDISPATCH_WITHOUT_USER_PROMPT",
        )

    def test_manual_selector_tie_break_remains_deterministic(self):
        proc = self.run_selector(["--select-parallel"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["work_item_id"], "github-issue-12")
        proc = self.run_selector(["--select-parallel", "--unavailable-work-item", "github-issue-12"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["work_item_id"], "github-issue-15")

    def test_nonterminal_higher_precedence_selection_is_not_replaced(self):
        evidence = self.base_evidence()
        evidence["selected_rank_before"] = 1
        evidence["selected_work_terminal"] = False
        result = self.evaluate(evidence)
        self.assertEqual(result["decision"], "KEEP_SELECTED")
        self.assertEqual(result["effective_rank"], 1)

    def test_qualitative_gate_token_is_rejected(self):
        policy = json.loads(POLICY_PATH.read_text())
        policy["novelty_rule"] = "USE_RELEVANT_NEW_WORK"
        POLICY_PATH.write_text(json.dumps(policy, indent=2) + "\n")
        proc = self.run_selector(["--validate-policy"])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("qualitative gate token forbidden", proc.stderr)


if __name__ == "__main__":
    unittest.main()
