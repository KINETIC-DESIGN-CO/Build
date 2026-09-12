import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "work-selection-policy.json"
ADMISSIONS_PATH = ROOT / "governance" / "work-admissions.json"


class WorkSelectionTests(unittest.TestCase):
    def run_selector(self, evidence=None, policy_override=None, admissions_override=None, extra_args=None):
        original_policy = POLICY_PATH.read_text(encoding="utf-8")
        original_admissions = ADMISSIONS_PATH.read_text(encoding="utf-8")
        try:
            if policy_override is not None:
                POLICY_PATH.write_text(json.dumps(policy_override, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            if admissions_override is not None:
                ADMISSIONS_PATH.write_text(json.dumps(admissions_override, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            cmd = ["python", "scripts/select_work.py"]
            if evidence is None and extra_args is None:
                cmd.append("--validate-policy")
            elif evidence is not None:
                with tempfile.TemporaryDirectory() as td:
                    evidence_path = Path(td) / "evidence.json"
                    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
                    cmd += ["--evaluate", str(evidence_path)]
                    if extra_args:
                        cmd += extra_args
                    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
            else:
                cmd += extra_args or []
            return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        finally:
            POLICY_PATH.write_text(original_policy, encoding="utf-8")
            ADMISSIONS_PATH.write_text(original_admissions, encoding="utf-8")

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
            "current_next_action_id": "A-0011",
            "parallel_request_state": "NONE",
            "parallel_work_item_id": None,
            "parallel_resource_intersection": "NOT_EVALUATED",
            "selected_rank_before": None,
            "selected_work_terminal": True,
        }

    def parallel_evidence(self, work_item_id="github-issue-12"):
        evidence = self.base_evidence()
        evidence.update({
            "worker_lane": "PARALLEL_ASSIGNED",
            "parallel_request_state": "REQUESTED",
            "parallel_work_item_id": work_item_id,
            "parallel_resource_intersection": "INTERSECTION_EMPTY",
        })
        return evidence

    def result(self, evidence):
        proc = self.run_selector(evidence=evidence)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def select_parallel(self, *unavailable):
        args = ["--select-parallel"]
        for item in unavailable:
            args += ["--unavailable-work-item", item]
        proc = self.run_selector(extra_args=args)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_policy_and_admissions_validate(self):
        proc = self.run_selector()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("VALID", proc.stdout)

    def test_rank_semantics_make_zero_highest_precedence(self):
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(policy["rank_semantics"], "LOWER_NUMERIC_RANK_HAS_HIGHER_PRECEDENCE")
        self.assertEqual(policy["priority_order"][0]["rank"], 0)

    def test_foreground_continuity_required_selects_rank_zero(self):
        evidence = self.base_evidence()
        evidence["pending_continuity_event_ids"] = ["E-PENDING-1"]
        result = self.result(evidence)
        self.assertEqual(result["effective_rank"], 0)
        self.assertEqual(result["selected_work"], "CONTINUITY_SYNC")

    def test_parallel_disjoint_work_can_run_during_continuity_sync(self):
        evidence = self.parallel_evidence()
        evidence["pending_continuity_event_ids"] = ["E-PENDING-1"]
        evidence["continuity_resource_intersection"] = "INTERSECTION_EMPTY"
        result = self.result(evidence)
        self.assertEqual(result["effective_rank"], 4)
        self.assertEqual(result["selected_work"], "PARALLEL_ADMITTED_WORK")

    def test_parallel_intersecting_continuity_work_is_rank_zero_blocked(self):
        evidence = self.parallel_evidence()
        evidence["pending_continuity_event_ids"] = ["E-PENDING-1"]
        evidence["continuity_resource_intersection"] = "INTERSECTION_NONEMPTY"
        result = self.result(evidence)
        self.assertEqual(result["effective_rank"], 0)
        self.assertEqual(result["selected_work"], "CONTINUITY_SYNC")

    def test_parallel_sync_intersection_must_be_evaluated(self):
        evidence = self.parallel_evidence()
        evidence["pending_continuity_event_ids"] = ["E-PENDING-1"]
        proc = self.run_selector(evidence=evidence)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("requires continuity intersection evaluation", proc.stderr)

    def test_unresolved_interruption_outranks_disjoint_parallel_work(self):
        evidence = self.parallel_evidence()
        evidence["interrupted_operation_state"] = "NO_RESULT"
        result = self.result(evidence)
        self.assertEqual(result["effective_rank"], 1)
        self.assertEqual(result["selected_work"], "RESUME_INTERRUPTED_OPERATION")

    def test_parallel_other_resource_intersection_blocks_rank_four(self):
        evidence = self.parallel_evidence()
        evidence["parallel_resource_intersection"] = "INTERSECTION_NONEMPTY"
        result = self.result(evidence)
        self.assertIsNone(result["effective_rank"])
        self.assertEqual(result["decision"], "NO_ELIGIBLE_WORK")

    def test_parallel_request_requires_canonical_admitted_work_item(self):
        evidence = self.parallel_evidence("github-issue-999")
        proc = self.run_selector(evidence=evidence)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("must exist in admissions", proc.stderr)

    def test_dependency_blocks_issue_18_until_issue_21_complete(self):
        selected = self.select_parallel(
            "github-issue-12", "github-issue-15", "github-issue-16",
            "github-issue-17", "github-issue-21", "github-issue-30",
        )
        self.assertEqual(selected["decision"], "NO_ELIGIBLE_WORK")

    def test_selector_picks_lowest_dispatch_tier_then_issue_number(self):
        selected = self.select_parallel()
        self.assertEqual(selected["work_item_id"], "github-issue-12")
        self.assertEqual(selected["component_resource_key"], "component:issue_12")
        selected = self.select_parallel("github-issue-12")
        self.assertEqual(selected["work_item_id"], "github-issue-15")

    def test_dependency_unlocks_when_predecessor_complete(self):
        admissions = json.loads(ADMISSIONS_PATH.read_text(encoding="utf-8"))
        for item in admissions["items"]:
            if item["work_item_id"] == "github-issue-21":
                item["state"] = "COMPLETE"
        proc = self.run_selector(
            admissions_override=admissions,
            extra_args=[
                "--select-parallel",
                "--unavailable-work-item", "github-issue-12",
                "--unavailable-work-item", "github-issue-15",
                "--unavailable-work-item", "github-issue-16",
                "--unavailable-work-item", "github-issue-17",
            ],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["work_item_id"], "github-issue-18")

    def test_admissions_authorization_ref_must_resolve_to_vince_directive(self):
        admissions = json.loads(ADMISSIONS_PATH.read_text(encoding="utf-8"))
        admissions["authorization_ref"] = "E-9999"
        proc = self.run_selector(admissions_override=admissions)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("authorization_ref must resolve", proc.stderr)

    def test_lower_priority_candidate_cannot_preempt_nonterminal_selection(self):
        evidence = self.base_evidence()
        evidence["selected_rank_before"] = 1
        evidence["selected_work_terminal"] = False
        result = self.result(evidence)
        self.assertEqual(result["candidate_rank"], 3)
        self.assertEqual(result["decision"], "KEEP_SELECTED")
        self.assertEqual(result["effective_rank"], 1)

    def test_expired_continuity_barrier_blocks_foreground(self):
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

    def test_dependency_cycle_is_rejected(self):
        admissions = json.loads(ADMISSIONS_PATH.read_text(encoding="utf-8"))
        for item in admissions["items"]:
            if item["work_item_id"] == "github-issue-12":
                item["depends_on"] = ["github-issue-15"]
            if item["work_item_id"] == "github-issue-15":
                item["depends_on"] = ["github-issue-12"]
        proc = self.run_selector(admissions_override=admissions)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("dependency cycle", proc.stderr)


if __name__ == "__main__":
    unittest.main()
