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
GOAL_ID = "77777777-7777-4777-8777-777777777777"
RESOURCE = "component:issue_18"
_DEFAULT = object()


def thread_claim(*, work_id=WORK_ID, lease_id=LEASE_ID, generation=1, resource=RESOURCE):
    return {"resource_key": resource, "work_id": work_id, "lease_id": lease_id, "generation": generation}


def live_claim(
    *,
    work_id=WORK_ID,
    lease_id=LEASE_ID,
    generation=1,
    resource=RESOURCE,
    state="ACTIVE",
    schema_version=2,
    heartbeat_at="2026-09-13T19:45:00Z",
    expires_at="2026-09-13T20:15:00Z",
):
    return {
        "schema_version": schema_version,
        "resource_key": resource,
        "state": state,
        "work_id": work_id,
        "lease_id": lease_id,
        "generation": generation,
        "heartbeat_at": heartbeat_at,
        "expires_at": expires_at,
    }


def work(*, live=False, work_id=WORK_ID, session=THREAD_SESSION, claims=None, goal_id=GOAL_ID, revision=3, effect="NONE"):
    if claims is None:
        claims = [live_claim(work_id=work_id) if live else thread_claim(work_id=work_id)]
    return {
        "work_id": work_id,
        "implementation_branch": f"work/{work_id}",
        "worker_session_id": session,
        "goal_id": goal_id,
        "planned_goal_revision": revision if goal_id is not None else None,
        "pending_external_effect_state": effect,
        "claims": claims,
    }


def canonical_goal(*, revision=3, state="NONE", target=None):
    return {
        "goal_id": GOAL_ID,
        "revision": revision,
        "control_signal": {"state": state, "target_work_id": target},
    }


def evidence(*, cue="CONTINUE", live_read="VERIFIED", operation="SUCCESS", thread=_DEFAULT, live=_DEFAULT, goal=_DEFAULT, observed_at="2026-09-13T20:00:00Z"):
    if thread is _DEFAULT:
        thread = work()
    if live is _DEFAULT:
        live = work(live=True, session=LIVE_SESSION) if live_read == "VERIFIED" else None
    if goal is _DEFAULT:
        goal = canonical_goal() if live_read == "VERIFIED" else None
    return {
        "schema_version": 2,
        "resume_cue": cue,
        "observed_at": observed_at,
        "live_read_state": live_read,
        "interrupted_operation_state": operation,
        "thread_work": thread,
        "live_work": live,
        "canonical_goal": goal,
    }


class ResumeReconciliationTests(unittest.TestCase):
    def test_policy_v2_is_exact_zero_authority_and_fence_aligned(self):
        mod.validate_policy(POLICY)
        self.assertEqual(POLICY["policy_id"], "life-resume-reconciliation-v2")
        self.assertEqual(POLICY["runtime_control_authority"], "NONE")
        self.assertEqual(POLICY["control_authority_effect"], "ZERO")
        self.assertEqual(POLICY["work_fence_policy_path"], "governance/work-fence-policy.json")
        self.assertIn(mod.V4_LEGACY_COMPONENT_EXPIRY_RULE, POLICY["rules"])

    def test_observation_reference_remains_user_authorized_not_runtime_authority(self):
        mod.validate_observation_reference(POLICY)

    def test_matching_same_work_after_visible_success_continues(self):
        result = mod.evaluate(evidence(), POLICY)
        self.assertEqual(result["fence_state"], "CONTINUE")
        self.assertEqual(result["resume_action"], "RESUME_SAME_WORK_CONTINUE")

    def test_unresolved_interrupted_operation_requires_verification_before_retry(self):
        result = mod.evaluate(evidence(operation="TIMEOUT"), POLICY)
        self.assertEqual(result["fence_state"], "INTERRUPTED_OPERATION_UNRESOLVED")
        self.assertEqual(result["resume_action"], "RESUME_SAME_WORK_VERIFY_LAST_OPERATION")

    def test_unresolved_external_effect_outranks_revision_and_operation_state(self):
        result = mod.evaluate(
            evidence(
                operation="SUCCESS",
                thread=work(revision=2, effect="TIMEOUT"),
                live=work(live=True, session=LIVE_SESSION, revision=2, effect="TIMEOUT"),
                goal=canonical_goal(revision=3),
            ),
            POLICY,
        )
        self.assertEqual(result["fence_state"], "EXTERNAL_EFFECT_UNRESOLVED")
        self.assertEqual(result["resume_action"], "RECONCILE_EXTERNAL_EFFECT_BEFORE_RESUME")

    def test_goal_revision_mismatch_requires_checkpoint_and_replan(self):
        result = mod.evaluate(
            evidence(thread=work(revision=2), live=work(live=True, session=LIVE_SESSION, revision=2), goal=canonical_goal(revision=3)),
            POLICY,
        )
        self.assertEqual(result["fence_state"], "GOAL_REVISION_MISMATCH")
        self.assertEqual(result["resume_action"], "CHECKPOINT_AND_REPLAN")

    def test_targeted_control_signal_requires_checkpoint_and_replan(self):
        result = mod.evaluate(evidence(goal=canonical_goal(state="YIELD_OR_REPLAN_REQUESTED", target=WORK_ID)), POLICY)
        self.assertEqual(result["fence_state"], "CONTROL_SIGNAL_ACTIVE")
        self.assertEqual(result["resume_action"], "CHECKPOINT_AND_REPLAN")

    def test_signal_for_other_work_does_not_change_current_resume(self):
        result = mod.evaluate(evidence(goal=canonical_goal(state="YIELD_OR_REPLAN_REQUESTED", target=OTHER_WORK_ID)), POLICY)
        self.assertEqual(result["resume_action"], "RESUME_SAME_WORK_CONTINUE")

    def test_changed_generation_is_reconciled_as_different_live_state(self):
        changed = work(live=True, session=LIVE_SESSION, claims=[live_claim(generation=2)])
        result = mod.evaluate(evidence(live=changed), POLICY)
        self.assertEqual(result["work_relation_state"], "DIFFERENT_WORK_STATE")
        self.assertEqual(result["resume_action"], "RECONCILE_DIFFERENT_WORK_BEFORE_PROCEED")

    def test_changed_lease_id_is_reconciled_as_different_live_state(self):
        changed = work(live=True, session=LIVE_SESSION, claims=[live_claim(lease_id=OTHER_LEASE_ID)])
        result = mod.evaluate(evidence(live=changed), POLICY)
        self.assertEqual(result["resume_action"], "RECONCILE_DIFFERENT_WORK_BEFORE_PROCEED")

    def test_released_matching_claim_requires_reacquisition(self):
        changed = work(live=True, session=LIVE_SESSION, claims=[live_claim(state="RELEASED")])
        result = mod.evaluate(evidence(live=changed), POLICY)
        self.assertEqual(result["resume_action"], "REACQUIRE_REQUIRED_CLAIMS_BEFORE_MUTATION")

    def test_expired_matching_claim_requires_reacquisition(self):
        changed = work(
            live=True,
            session=LIVE_SESSION,
            claims=[live_claim(heartbeat_at="2026-09-13T19:30:00Z", expires_at="2026-09-13T20:00:00Z")],
        )
        result = mod.evaluate(evidence(live=changed), POLICY)
        self.assertEqual(result["resume_action"], "REACQUIRE_REQUIRED_CLAIMS_BEFORE_MUTATION")

    def test_legacy_v1_component_uses_effective_expiry_not_stored_four_hour_expiry(self):
        changed = work(
            live=True,
            session=LIVE_SESSION,
            claims=[
                live_claim(
                    schema_version=1,
                    heartbeat_at="2026-09-13T19:29:00Z",
                    expires_at="2026-09-13T23:29:00Z",
                )
            ],
        )
        result = mod.evaluate(evidence(live=changed), POLICY)
        self.assertEqual(result["work_relation_state"], "SAME_WORK_CLAIMS_INACTIVE")
        self.assertEqual(result["resume_action"], "REACQUIRE_REQUIRED_CLAIMS_BEFORE_MUTATION")

    def test_legacy_v1_external_claim_uses_stored_expiry(self):
        resource = "external:test:shared"
        thread = work(claims=[thread_claim(resource=resource)])
        live = work(
            live=True,
            session=LIVE_SESSION,
            claims=[
                live_claim(
                    resource=resource,
                    schema_version=1,
                    heartbeat_at="2026-09-13T19:00:00Z",
                    expires_at="2026-09-13T23:00:00Z",
                )
            ],
        )
        result = mod.evaluate(evidence(thread=thread, live=live), POLICY)
        self.assertEqual(result["work_relation_state"], "SAME_WORK_ACTIVE")
        self.assertEqual(result["resume_action"], "RESUME_SAME_WORK_CONTINUE")

    def test_v2_component_duration_must_match_fence_duration(self):
        changed = work(
            live=True,
            session=LIVE_SESSION,
            claims=[live_claim(heartbeat_at="2026-09-13T19:45:00Z", expires_at="2026-09-13T20:16:00Z")],
        )
        with self.assertRaises(mod.ResumeError):
            mod.evaluate(evidence(live=changed), POLICY)

    def test_not_run_stops_and_cannot_carry_claimed_live_state(self):
        result = mod.evaluate(evidence(live_read="NOT_RUN", live=None, goal=None), POLICY)
        self.assertEqual(result["resume_action"], "STOP_NOT_RUN")
        with self.assertRaises(mod.ResumeError):
            mod.evaluate(evidence(live_read="NOT_RUN", live=work(live=True), goal=None), POLICY)

    def test_missing_canonical_goal_for_goal_bound_verified_resume_fails_closed(self):
        with self.assertRaises(mod.ResumeError):
            mod.evaluate(evidence(goal=None), POLICY)

    def test_resume_cue_and_worker_session_labels_have_zero_control_or_ownership_effect(self):
        continued = mod.evaluate(evidence(cue="CONTINUE"), POLICY)
        other = mod.evaluate(evidence(cue="OTHER"), POLICY)
        self.assertEqual(continued, other)
        same_session = mod.evaluate(evidence(live=work(live=True, session=THREAD_SESSION)), POLICY)
        different_session = mod.evaluate(evidence(live=work(live=True, session=LIVE_SESSION)), POLICY)
        self.assertEqual(same_session["work_relation_state"], different_session["work_relation_state"])
        self.assertEqual(continued["resume_cue_effect"], "ZERO_CONTROL_EFFECT")
        self.assertEqual(continued["worker_session_id_effect"], "ZERO_OWNERSHIP_EFFECT")

    def test_resume_evidence_cannot_satisfy_any_runtime_control_kind_by_itself(self):
        for kind in sorted(mod.CONTROL_DECISION_KINDS):
            self.assertFalse(mod.may_satisfy_runtime_control(kind, POLICY))


if __name__ == "__main__":
    unittest.main()
