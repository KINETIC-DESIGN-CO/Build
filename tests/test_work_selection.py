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
        return subprocess.run(
            ["python", "scripts/select_work.py", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def base_evidence(self):
        return {
            "worker_lane": "FOREGROUND",
            "pending_continuity_event_ids": [],
            "canonical_live_mismatch_ids": [],
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

    def admitted_items(self):
        admissions = json.loads(ADMISSIONS_PATH.read_text())
        return sorted(
            [item for item in admissions["items"] if item["state"] == "ADMITTED"],
            key=lambda item: (
                item["dispatch_tier"],
                item["source_issue_number"],
                item["work_item_id"],
            ),
        )

    def dispatchable_admitted_items(self):
        admissions = json.loads(ADMISSIONS_PATH.read_text())
        states = {item["work_item_id"]: item["state"] for item in admissions["items"]}
        return sorted(
            [
                item
                for item in admissions["items"]
                if item["state"] == "ADMITTED"
                and all(
                    states.get(dependency) == "COMPLETE"
                    for dependency in item["depends_on"]
                )
            ],
            key=lambda item: (
                item["dispatch_tier"],
                item["source_issue_number"],
                item["work_item_id"],
            ),
        )

    def make_issue_18_admitted(self):
        admissions = json.loads(ADMISSIONS_PATH.read_text())
        for item in admissions["items"]:
            if item["work_item_id"] == "github-issue-18":
                item["state"] = "ADMITTED"
                break
        ADMISSIONS_PATH.write_text(
            json.dumps(admissions, indent=2) + "\n", encoding="utf-8"
        )

    def make_issue_18_dispatchable(self):
        admissions = json.loads(ADMISSIONS_PATH.read_text())
        for item in admissions["items"]:
            if item["work_item_id"] == "github-issue-18":
                item["state"] = "ADMITTED"
                item["depends_on"] = []
                break
        ADMISSIONS_PATH.write_text(
            json.dumps(admissions, indent=2) + "\n", encoding="utf-8"
        )

    def make_issue_21_admitted(self):
        admissions = json.loads(ADMISSIONS_PATH.read_text())
        for item in admissions["items"]:
            if item["work_item_id"] == "github-issue-21":
                item["state"] = "ADMITTED"
                break
        ADMISSIONS_PATH.write_text(
            json.dumps(admissions, indent=2) + "\n", encoding="utf-8"
        )

    def admitted_item(self, index=0):
        return self.admitted_items()[index]

    def parallel_evidence(self, item=None):
        value = self.base_evidence()
        value.update(
            {
                "worker_lane": "PARALLEL_ASSIGNED",
                "parallel_request_state": "REQUESTED",
                "parallel_work_item_id": item
                or self.dispatchable_admitted_items()[0]["work_item_id"],
                "parallel_resource_intersection": "INTERSECTION_EMPTY",
            }
        )
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
        keys = {f"component:{current['current_component']}"}
        keys.update(
            f"component:{item['component_id']}"
            for item in admissions["items"]
            if item["state"] == "ADMITTED"
        )
        return sorted(keys)

    def lock(self, key, expires="2026-09-12T18:00:00Z", state="ACTIVE"):
        return {
            "schema_version": 1,
            "resource_key": key,
            "generation": 1,
            "state": state,
            "work_id": "11111111-1111-4111-8111-111111111111",
            "worker": {
                "kind": "chatgpt",
                "session_id": "22222222-2222-4222-8222-222222222222",
            },
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

    def test_policy_validates_as_v4_without_global_continuity_claim(self):
        proc = self.run_selector(["--validate-policy"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        policy = json.loads(POLICY_PATH.read_text())
        self.assertEqual(policy["schema_version"], 4)
        self.assertEqual(policy["policy_id"], "life-engineering-work-selection-v4")
        self.assertIsNone(policy["continuity_integration"]["global_claim_resource_key"])
        self.assertEqual(
            policy["continuity_integration"]["global_claim_effect"], "NONE"
        )

    def test_pending_continuity_event_does_not_preempt_foreground_work(self):
        evidence = self.base_evidence()
        evidence["pending_continuity_event_ids"] = ["E-PENDING-1"]
        result = self.evaluate(evidence)
        self.assertEqual(result["effective_rank"], 2)
        self.assertEqual(result["selected_work"], "CURRENT_NEXT_ACTION")
        self.assertEqual(
            result["continuity_evidence_effect"],
            "ZERO_WORK_SELECTION_PREEMPTION_EFFECT",
        )

    def test_canonical_live_mismatch_does_not_preempt_disjoint_parallel_work(self):
        self.make_issue_18_admitted()
        evidence = self.parallel_evidence()
        evidence["canonical_live_mismatch_ids"] = ["GITHUB_MAIN_HEAD_SHA"]
        result = self.evaluate(evidence)
        self.assertEqual(result["effective_rank"], 3)
        self.assertEqual(result["selected_work"], "PARALLEL_ADMITTED_WORK")

    def test_interrupted_operation_has_highest_rank(self):
        evidence = self.base_evidence()
        evidence["interrupted_operation_state"] = "UNKNOWN"
        result = self.evaluate(evidence)
        self.assertEqual(result["effective_rank"], 0)
        self.assertEqual(result["selected_work"], "RESUME_INTERRUPTED_OPERATION")

    def test_fresh_thread_foreground_is_derived_when_component_is_free(self):
        result = self.dispatch(self.snapshot())
        self.assertEqual(result["worker_lane"], "FOREGROUND")
        self.assertEqual(result["effective_rank"], 2)
        self.assertEqual(result["selected_work"], "CURRENT_NEXT_ACTION")
        self.assertEqual(
            result["claim_next_resource_key"],
            "component:multi_thread_coordination_hardening",
        )

    def test_dispatch_snapshot_does_not_require_continuity_sync_resource(self):
        self.assertNotIn("continuity:sync", self.required_dispatch_keys())
        result = self.dispatch(self.snapshot())
        self.assertEqual(result["worker_lane"], "FOREGROUND")

    def test_legacy_continuity_sync_resource_is_rejected_as_extra_snapshot_state(self):
        snap = self.snapshot()
        snap["resources"]["continuity:sync"] = self.lock("continuity:sync")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "snapshot.json"
            path.write_text(json.dumps(snap) + "\n")
            proc = self.run_selector(["--dispatch-snapshot", str(path)])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("resource coverage mismatch", proc.stderr)

    def test_completed_current_work_with_empty_admitted_queue_has_no_parallel_work(self):
        current = json.loads(CURRENT_PATH.read_text())
        current["current_status"] = "COMPLETE"
        CURRENT_PATH.write_text(
            json.dumps(current, indent=2) + "\n", encoding="utf-8"
        )
        self.assertEqual(self.dispatchable_admitted_items(), [])
        result = self.dispatch(self.snapshot())
        self.assertEqual(result["decision"], "NO_ELIGIBLE_WORK")
        self.assertEqual(result["worker_lane"], "PARALLEL_ASSIGNED")

    def test_completed_current_work_routes_fresh_thread_to_parallel(self):
        self.make_issue_18_admitted()
        current = json.loads(CURRENT_PATH.read_text())
        current["current_status"] = "COMPLETE"
        CURRENT_PATH.write_text(
            json.dumps(current, indent=2) + "\n", encoding="utf-8"
        )
        first = self.dispatchable_admitted_items()[0]
        result = self.dispatch(self.snapshot())
        self.assertEqual(result["worker_lane"], "PARALLEL_ASSIGNED")
        self.assertEqual(result["work_item_id"], first["work_item_id"])
        self.assertEqual(
            result["claim_next_resource_key"], f"component:{first['component_id']}"
        )

    def test_fresh_thread_becomes_parallel_when_foreground_component_is_owned(self):
        self.make_issue_18_admitted()
        key = "component:multi_thread_coordination_hardening"
        first = self.dispatchable_admitted_items()[0]
        result = self.dispatch(self.snapshot({key: self.lock(key)}))
        self.assertEqual(result["worker_lane"], "PARALLEL_ASSIGNED")
        self.assertEqual(result["work_item_id"], first["work_item_id"])

    def test_parallel_auto_selection_skips_owned_component(self):
        self.make_issue_21_admitted()
        self.make_issue_18_dispatchable()
        current_key = "component:multi_thread_coordination_hardening"
        first = self.dispatchable_admitted_items()[0]
        second = self.dispatchable_admitted_items()[1]
        first_key = f"component:{first['component_id']}"
        result = self.dispatch(
            self.snapshot(
                {current_key: self.lock(current_key), first_key: self.lock(first_key)}
            )
        )
        self.assertEqual(result["work_item_id"], second["work_item_id"])
        self.assertEqual(
            result["claim_next_resource_key"], f"component:{second['component_id']}"
        )

    def test_expired_component_claim_is_available(self):
        self.make_issue_18_admitted()
        current_key = "component:multi_thread_coordination_hardening"
        first = self.dispatchable_admitted_items()[0]
        first_key = f"component:{first['component_id']}"
        result = self.dispatch(
            self.snapshot(
                {
                    current_key: self.lock(current_key),
                    first_key: self.lock(first_key, expires="2026-09-12T13:59:59Z"),
                }
            )
        )
        self.assertEqual(result["work_item_id"], first["work_item_id"])

    def test_dependency_blocks_issue_18_when_issue_21_not_complete(self):
        self.make_issue_18_admitted()
        self.make_issue_21_admitted()
        current_key = "component:multi_thread_coordination_hardening"
        overrides = {current_key: self.lock(current_key)}
        for item in self.admitted_items():
            if item["work_item_id"] != "github-issue-18":
                key = f"component:{item['component_id']}"
                overrides[key] = self.lock(key)
        result = self.dispatch(self.snapshot(overrides))
        self.assertEqual(result["decision"], "NO_ELIGIBLE_WORK")

    def test_snapshot_must_cover_every_required_component_resource(self):
        self.make_issue_18_admitted()
        snap = self.snapshot()
        first = self.admitted_item()
        del snap["resources"][f"component:{first['component_id']}"]
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
        self.assertEqual(
            policy["fresh_thread_dispatch"]["race_rule"],
            "AFTER_PARALLEL_SELECTION_ACQUIRE_SELECTED_COMPONENT_CLAIM_BY_COMPARE_AND_SWAP;ON_CONFLICT_REREAD_LIVE_LOCK_AND_REDISPATCH",
        )

    def test_manual_selector_tie_break_remains_deterministic(self):
        self.make_issue_21_admitted()
        self.make_issue_18_dispatchable()
        first = self.dispatchable_admitted_items()[0]
        second = self.dispatchable_admitted_items()[1]
        proc = self.run_selector(["--select-parallel"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["work_item_id"], first["work_item_id"])
        self.assertEqual(json.loads(proc.stdout)["selection_rank"], 3)
        proc = self.run_selector(
            ["--select-parallel", "--unavailable-work-item", first["work_item_id"]]
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["work_item_id"], second["work_item_id"])

    def test_nonterminal_higher_precedence_selection_is_not_replaced(self):
        evidence = self.base_evidence()
        evidence["selected_rank_before"] = 0
        evidence["selected_work_terminal"] = False
        result = self.evaluate(evidence)
        self.assertEqual(result["decision"], "KEEP_SELECTED")
        self.assertEqual(result["effective_rank"], 0)

    def test_old_continuity_gate_fields_are_rejected(self):
        evidence = self.base_evidence()
        evidence["continuity_sync_claim_state"] = "ACTIVE_UNEXPIRED"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "evidence.json"
            path.write_text(json.dumps(evidence) + "\n")
            proc = self.run_selector(["--evaluate", str(path)])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("evidence keys mismatch", proc.stderr)

    def test_qualitative_gate_token_is_rejected(self):
        policy = json.loads(POLICY_PATH.read_text())
        policy["novelty_rule"] = "USE_RELEVANT_NEW_WORK"
        POLICY_PATH.write_text(json.dumps(policy, indent=2) + "\n")
        proc = self.run_selector(["--validate-policy"])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("qualitative gate token forbidden", proc.stderr)


if __name__ == "__main__":
    unittest.main()
