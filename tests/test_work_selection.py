import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "work-selection-policy.json"


class WorkSelectionTests(unittest.TestCase):
    def run_selector(self, evidence=None, policy_override=None):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            if policy_override is not None:
                original = POLICY_PATH.read_text(encoding="utf-8")
                try:
                    POLICY_PATH.write_text(json.dumps(policy_override, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                    return self.run_selector(evidence=evidence)
                finally:
                    POLICY_PATH.write_text(original, encoding="utf-8")
            if evidence is None:
                return subprocess.run(["python", "scripts/select_work.py", "--validate-policy"], cwd=ROOT, text=True, capture_output=True)
            evidence_path = td_path / "evidence.json"
            evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
            return subprocess.run(["python", "scripts/select_work.py", "--evaluate", str(evidence_path)], cwd=ROOT, text=True, capture_output=True)

    def base_evidence(self):
        return {
            "worker_lane": "FOREGROUND",
            "pending_continuity_event_ids": [],
            "canonical_live_mismatch_ids": [],
            "continuity_sync_claim_state": "NONE",
            "interrupted_operation_state": "NONE",
            "current_status": "ACTIVE",
            "open_blocker_ids": [],
            "current_next_action_id": "A-0010",
            "parallel_request_state": "NONE",
            "parallel_resource_intersection": "NOT_EVALUATED",
            "selected_rank_before": None,
            "selected_work_terminal": True,
        }

    def result(self, evidence):
        proc = self.run_selector(evidence=evidence)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_policy_validates(self):
        proc = self.run_selector()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("VALID", proc.stdout)

    def test_continuity_required_outranks_next_action(self):
        evidence = self.base_evidence()
        evidence["pending_continuity_event_ids"] = ["E-PENDING-1"]
        result = self.result(evidence)
        self.assertEqual(result["effective_rank"], 0)
        self.assertEqual(result["selected_work"], "CONTINUITY_SYNC")

    def test_nonterminal_continuity_selection_cannot_be_displaced_by_next_action(self):
        evidence = self.base_evidence()
        evidence["selected_rank_before"] = 0
        evidence["selected_work_terminal"] = False
        result = self.result(evidence)
        self.assertEqual(result["candidate_rank"], 3)
        self.assertEqual(result["decision"], "KEEP_SELECTED")
        self.assertEqual(result["effective_rank"], 0)

    def test_continuity_preempts_unresolved_interruption(self):
        evidence = self.base_evidence()
        evidence["canonical_live_mismatch_ids"] = ["WATCHDOG_FIRST_RUN_STATUS"]
        evidence["interrupted_operation_state"] = "NO_RESULT"
        evidence["selected_rank_before"] = 1
        evidence["selected_work_terminal"] = False
        result = self.result(evidence)
        self.assertEqual(result["decision"], "PREEMPT")
        self.assertEqual(result["effective_rank"], 0)

    def test_interrupted_operation_outranks_next_action(self):
        evidence = self.base_evidence()
        evidence["interrupted_operation_state"] = "NO_RESULT"
        result = self.result(evidence)
        self.assertEqual(result["effective_rank"], 1)
        self.assertEqual(result["selected_work"], "RESUME_INTERRUPTED_OPERATION")

    def test_open_blocker_outranks_next_action(self):
        evidence = self.base_evidence()
        evidence["current_status"] = "BLOCKED"
        evidence["open_blocker_ids"] = ["B-0042"]
        result = self.result(evidence)
        self.assertEqual(result["effective_rank"], 2)
        self.assertEqual(result["selected_work"], "CLEAR_CURRENT_BLOCKERS")

    def test_foreground_next_action_only_after_higher_ranks_clear(self):
        result = self.result(self.base_evidence())
        self.assertEqual(result["effective_rank"], 3)
        self.assertEqual(result["selected_work"], "CURRENT_NEXT_ACTION")

    def test_parallel_assigned_disjoint_work_gets_rank_4(self):
        evidence = self.base_evidence()
        evidence.update({"worker_lane": "PARALLEL_ASSIGNED", "current_next_action_id": "A-0010", "parallel_request_state": "REQUESTED", "parallel_resource_intersection": "INTERSECTION_EMPTY"})
        result = self.result(evidence)
        self.assertEqual(result["effective_rank"], 4)
        self.assertEqual(result["selected_work"], "PARALLEL_ASSIGNED_WORK")

    def test_parallel_intersection_blocks_rank_4(self):
        evidence = self.base_evidence()
        evidence.update({"worker_lane": "PARALLEL_ASSIGNED", "parallel_request_state": "REQUESTED", "parallel_resource_intersection": "INTERSECTION_NONEMPTY"})
        result = self.result(evidence)
        self.assertIsNone(result["effective_rank"])
        self.assertEqual(result["decision"], "NO_ELIGIBLE_WORK")

    def test_lower_priority_candidate_cannot_preempt_nonterminal_selection(self):
        evidence = self.base_evidence()
        evidence["selected_rank_before"] = 1
        evidence["selected_work_terminal"] = False
        result = self.result(evidence)
        self.assertEqual(result["candidate_rank"], 3)
        self.assertEqual(result["decision"], "KEEP_SELECTED")
        self.assertEqual(result["effective_rank"], 1)

    def test_expired_continuity_barrier_still_requires_sync(self):
        evidence = self.base_evidence()
        evidence["continuity_sync_claim_state"] = "ACTIVE_EXPIRED"
        result = self.result(evidence)
        self.assertEqual(result["effective_rank"], 0)

    def test_qualitative_gate_token_is_rejected(self):
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        policy["novelty_rule"] = "USE_RELEVANT_NEW_WORK"
        proc = self.run_selector(policy_override=policy)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("qualitative gate token forbidden", proc.stderr)


if __name__ == "__main__":
    unittest.main()
