from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate_resume_reconciliation.py"
spec = importlib.util.spec_from_file_location("evaluate_resume_reconciliation", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

POLICY = json.loads((ROOT / "governance" / "resume-reconciliation-policy.json").read_text())
WORK_ID = "11111111-1111-4111-8111-111111111111"
OTHER_WORK_ID = "22222222-2222-4222-8222-222222222222"
LEASE_ID = "33333333-3333-4333-8333-333333333333"
OTHER_LEASE_ID = "44444444-4444-4444-8444-444444444444"
THREAD_SESSION = "55555555-5555-4555-8555-555555555555"
LIVE_SESSION = "66666666-6666-4666-8666-666666666666"
RESOURCE = "component:issue_18"


def thread_claim(*, work_id=WORK_ID, lease_id=LEASE_ID, generation=1, resource=RESOURCE):
    return {
        "resource_key": resource,
        "work_id": work_id,
        "lease_id": lease_id,
        "generation": generation,
    }


def live_claim(
    *,
    work_id=WORK_ID,
    lease_id=LEASE_ID,
    generation=1,
    resource=RESOURCE,
    state="ACTIVE",
    expires_at="2026-09-13T23:00:00Z",
):
    return {
        "resource_key": resource,
        "state": state,
        "work_id": work_id,
        "lease_id": lease_id,
        "generation": generation,
        "expires_at": expires_at,
    }


def work(*, live=False, work_id=WORK_ID, session=THREAD_SESSION, claims=None):
    if claims is None:
        claims = [live_claim(work_id=work_id) if live else thread_claim(work_id=work_id)]
    return {
        "work_id": work_id,
        "implementation_branch": f"work/{work_id}",
        "worker_session_id": session,
        "claims": claims,
    }


def evidence(
    *,
    cue="CONTINUE",
    live_read="VERIFIED",
    operation="TIMEOUT",
    thread=None,
    live=None,
    observed_at="2026-09-13T20:00:00Z",
):
    if thread is None:
        thread = work()
    if live is None and live_read == "VERIFIED":
        live = work(live=True, session=LIVE_SESSION)
    return {
        "schema_version": 1,
        "resume_cue": cue,
        "observed_at": observed_at,
        "live_read_state": live_read,
        "interrupted_operation_state": operation,
        "thread_work": thread,
        "live_work": live,
    }


class ResumeReconciliationTests(unittest.TestCase):
    def test_policy_is_exact_zero_authority_and_seven_step(self):
        mod.validate_policy(POLICY)
        self.assertEqual(POLICY["policy_id"], "life-resume-reconciliation-v1")
        self.assertEqual(POLICY["runtime_control_authority"], "NONE")
        self.assertEqual(POLICY["control_authority_effect"], "ZERO")
        self.assertEqual(len(POLICY["procedure_steps"]), 7)
        self.assertEqual(POLICY["user_observation_ref"], "UO-0002")

    def test_observation_reference_is_user_authorized_not_runtime_authority(self):
        mod.validate_observation_reference(POLICY)
        rows = [json.loads(line) for line in (ROOT / "continuity/user-observations.jsonl").read_text().splitlines()]
        row = next(item for item in rows if item["id"] == "UO-0002")
        self.assertEqual(row["authorization_state"], "AUTHORIZED_FOR_LIFE_REQUIREMENT")
        self.assertEqual(row["external_verification_state"], "NOT_RUN")
        self.assertEqual(row["runtime_control_authority"], "NONE")

    def test_matching_same_work_active_claim_resumes_same_work_but_verifies_unknown_operation(self):
        result = mod.evaluate(evidence(operation="TIMEOUT"), POLICY)
        self.assertEqual(result["work_relation_state"], "SAME_WORK_ACTIVE")
        self.assertEqual(result["operation_completion_class"], "UNKNOWN")
        self.assertEqual(result["resume_action"], "RESUME_SAME_WORK_VERIFY_LAST_OPERATION")

    def test_matching_same_work_after_visible_success_continues_post_operation(self):
        result = mod.evaluate(evidence(operation="SUCCESS"), POLICY)
        self.assertEqual(result["work_relation_state"], "SAME_WORK_ACTIVE")
        self.assertEqual(result["operation_completion_class"], "VERIFIED_SUCCESS")
        self.assertEqual(result["resume_action"], "RESUME_SAME_WORK_CONTINUE")

    def test_different_live_work_id_is_detected_even_with_same_session_label(self):
        different = work(
            live=True,
            work_id=OTHER_WORK_ID,
            session=THREAD_SESSION,
            claims=[live_claim(work_id=OTHER_WORK_ID)],
        )
        result = mod.evaluate(evidence(live=different), POLICY)
        self.assertEqual(result["work_relation_state"], "DIFFERENT_WORK_STATE")
        self.assertEqual(result["resume_action"], "RECONCILE_DIFFERENT_WORK_BEFORE_PROCEED")
        self.assertEqual(result["worker_session_id_effect"], "ZERO_OWNERSHIP_EFFECT")

    def test_changed_lease_id_is_different_live_state(self):
        changed = work(live=True, claims=[live_claim(lease_id=OTHER_LEASE_ID)])
        result = mod.evaluate(evidence(live=changed), POLICY)
        self.assertEqual(result["work_relation_state"], "DIFFERENT_WORK_STATE")

    def test_changed_generation_is_different_live_state(self):
        changed = work(live=True, claims=[live_claim(generation=2)])
        result = mod.evaluate(evidence(live=changed), POLICY)
        self.assertEqual(result["work_relation_state"], "DIFFERENT_WORK_STATE")

    def test_missing_live_work_after_verified_read_is_unknown_not_guessed(self):
        result = mod.evaluate(evidence(live=None, thread=work(), live_read="VERIFIED"), POLICY)
        self.assertEqual(result["work_relation_state"], "UNKNOWN")
        self.assertEqual(result["resume_action"], "STOP_UNKNOWN")
        self.assertEqual(result["classification"], "UNKNOWN")

    def test_not_run_live_read_stops_as_not_run(self):
        result = mod.evaluate(evidence(live_read="NOT_RUN", live=None), POLICY)
        self.assertEqual(result["work_relation_state"], "NOT_RUN")
        self.assertEqual(result["operation_completion_class"], "NOT_RUN")
        self.assertEqual(result["resume_action"], "STOP_NOT_RUN")
        self.assertEqual(result["classification"], "NOT_RUN")

    def test_claim_resource_set_mismatch_is_unknown(self):
        changed = work(live=True, claims=[])
        result = mod.evaluate(evidence(live=changed), POLICY)
        self.assertEqual(result["work_relation_state"], "UNKNOWN")
        self.assertEqual(result["resume_action"], "STOP_UNKNOWN")

    def test_released_matching_claim_requires_reacquisition_before_mutation(self):
        changed = work(live=True, claims=[live_claim(state="RELEASED")])
        result = mod.evaluate(evidence(live=changed, operation="SUCCESS"), POLICY)
        self.assertEqual(result["work_relation_state"], "SAME_WORK_CLAIMS_INACTIVE")
        self.assertEqual(result["resume_action"], "REACQUIRE_REQUIRED_CLAIMS_BEFORE_MUTATION")

    def test_expired_matching_claim_requires_reacquisition_before_mutation(self):
        changed = work(live=True, claims=[live_claim(expires_at="2026-09-13T19:59:59Z")])
        result = mod.evaluate(evidence(live=changed, observed_at="2026-09-13T20:00:00Z"), POLICY)
        self.assertEqual(result["work_relation_state"], "SAME_WORK_CLAIMS_INACTIVE")
        self.assertEqual(result["resume_action"], "REACQUIRE_REQUIRED_CLAIMS_BEFORE_MUTATION")

    def test_resume_cue_has_zero_effect_on_same_machine_evidence(self):
        continued = mod.evaluate(evidence(cue="CONTINUE"), POLICY)
        other = mod.evaluate(evidence(cue="OTHER"), POLICY)
        self.assertEqual(continued, other)
        self.assertEqual(continued["resume_cue_effect"], "ZERO_CONTROL_EFFECT")

    def test_worker_session_id_difference_has_zero_ownership_effect(self):
        same_session = mod.evaluate(evidence(live=work(live=True, session=THREAD_SESSION)), POLICY)
        different_session = mod.evaluate(evidence(live=work(live=True, session=LIVE_SESSION)), POLICY)
        self.assertEqual(same_session["work_relation_state"], "SAME_WORK_ACTIVE")
        self.assertEqual(different_session["work_relation_state"], "SAME_WORK_ACTIVE")

    def test_resume_evidence_cannot_satisfy_any_runtime_control_kind_by_itself(self):
        for kind in sorted(mod.CONTROL_DECISION_KINDS):
            self.assertFalse(mod.may_satisfy_runtime_control(kind, POLICY))

    def test_bootstrap_persists_policy_evaluator_tests_and_required_read(self):
        bootstrap = json.loads((ROOT / "continuity/bootstrap.json").read_text())
        for path in (
            "governance/resume-reconciliation-policy.json",
            "scripts/evaluate_resume_reconciliation.py",
            "tests/test_resume_reconciliation.py",
        ):
            self.assertIn(path, bootstrap["required_files"])
        self.assertIn("governance/resume-reconciliation-policy.json", bootstrap["required_read_order"])
        self.assertIn("python scripts/evaluate_resume_reconciliation.py", bootstrap["validation_command"])

    def test_invalid_live_claim_shape_fails_closed(self):
        bad_claim = live_claim()
        del bad_claim["generation"]
        bad = work(live=True, claims=[bad_claim])
        with self.assertRaises(mod.ResumeError):
            mod.evaluate(evidence(live=bad), POLICY)

    def test_not_run_cannot_include_claimed_live_work(self):
        with self.assertRaises(mod.ResumeError):
            mod.evaluate(evidence(live_read="NOT_RUN", live=work(live=True)), POLICY)


if __name__ == "__main__":
    unittest.main()
