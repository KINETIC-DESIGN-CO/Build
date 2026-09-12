from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate_user_observation.py"
spec = importlib.util.spec_from_file_location("evaluate_user_observation", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

POLICY = json.loads((ROOT / "governance" / "user-observation-policy.json").read_text())


def record(
    record_id="UO-0001",
    *,
    statement="Vince personally observed the behavior.",
    authorization="AUTHORIZED_FOR_LIFE_REQUIREMENT",
    external="NOT_RUN",
    evidence=None,
    supersedes=None,
):
    return {
        "id": record_id,
        "record_type": "VINCE_PERSONAL_OBSERVATION",
        "observed_by": "VINCE",
        "observed_at": "2026-09-12T20:00:00Z",
        "statement": statement,
        "authorization_state": authorization,
        "external_verification_state": external,
        "external_evidence_refs": [] if evidence is None else evidence,
        "supersedes": [] if supersedes is None else supersedes,
        "runtime_control_authority": "NONE",
    }


class UserObservationTests(unittest.TestCase):
    def test_policy_is_exact_and_has_zero_runtime_control_authority(self):
        mod.validate_policy(POLICY)
        self.assertEqual(POLICY["policy_id"], "life-user-observation-provenance-v1")
        self.assertEqual(POLICY["runtime_control_authority"], "NONE")
        self.assertEqual(POLICY["control_authority_effect"], "ZERO")
        self.assertEqual(set(POLICY["control_decision_kinds"]), mod.CONTROL_DECISION_KINDS)

    def test_authorized_observation_becomes_user_requirement_without_external_verification(self):
        states = mod.evaluate_records([record()], POLICY)
        self.assertEqual(states["UO-0001"], "ACTIVE_USER_REQUIREMENT")

    def test_not_run_requires_zero_external_evidence_refs(self):
        row = record(evidence=["EXTERNAL:claim"])
        with self.assertRaises(mod.ObservationError):
            mod.validate_record(row, POLICY)

    def test_unverified_requires_verification_attempt_reference(self):
        with self.assertRaises(mod.ObservationError):
            mod.validate_record(record(external="UNVERIFIED"), POLICY)
        row = record(external="UNVERIFIED", evidence=["OPENAI_SEARCH:2026-09-12"])
        mod.validate_record(row, POLICY)

    def test_verified_match_requires_direct_external_evidence_reference(self):
        with self.assertRaises(mod.ObservationError):
            mod.validate_record(record(external="VERIFIED_MATCH"), POLICY)
        row = record(
            external="VERIFIED_MATCH",
            evidence=["DIRECT_PLATFORM_READ:example"],
        )
        states = mod.evaluate_records([row], POLICY)
        self.assertEqual(states["UO-0001"], "ACTIVE_USER_REQUIREMENT")

    def test_unauthorized_observation_is_recorded_only(self):
        states = mod.evaluate_records(
            [record(authorization="NOT_AUTHORIZED")],
            POLICY,
        )
        self.assertEqual(states["UO-0001"], "RECORDED_ONLY")

    def test_later_correction_supersedes_without_rewriting_prior_statement(self):
        first = record(statement="Original observation.")
        second = record(
            "UO-0002",
            statement="Corrected observation.",
            supersedes=["UO-0001"],
        )
        states = mod.evaluate_records([first, second], POLICY)
        self.assertEqual(first["statement"], "Original observation.")
        self.assertEqual(states["UO-0001"], "SUPERSEDED")
        self.assertEqual(states["UO-0002"], "ACTIVE_USER_REQUIREMENT")

    def test_direct_verified_contradiction_surfaces_conflict(self):
        row = record(
            external="VERIFIED_CONTRADICTION",
            evidence=["DIRECT_PLATFORM_READ:contradiction"],
        )
        states = mod.evaluate_records([row], POLICY)
        self.assertEqual(states["UO-0001"], "DIRECT_EVIDENCE_CONFLICT")
        self.assertEqual(row["statement"], "Vince personally observed the behavior.")

    def test_verified_contradiction_requires_external_evidence(self):
        row = record(external="VERIFIED_CONTRADICTION")
        with self.assertRaises(mod.ObservationError):
            mod.validate_record(row, POLICY)

    def test_user_observation_cannot_satisfy_any_runtime_control_kind(self):
        row = record()
        for kind in sorted(mod.CONTROL_DECISION_KINDS):
            self.assertFalse(mod.may_satisfy_runtime_control(row, kind, POLICY))

    def test_supersedes_must_reference_prior_record(self):
        row = record("UO-0002", supersedes=["UO-0001"])
        with self.assertRaises(mod.ObservationError):
            mod.evaluate_records([row], POLICY)

    def test_issue18_continue_observation_uses_user_authorized_provenance_only(self):
        row = record(
            statement=(
                "Vince personally observed that after an interrupted or timed-out ChatGPT "
                "response, a continue cue is intended to resume and reconcile the same Life work."
            ),
        )
        states = mod.evaluate_records([row], POLICY)
        self.assertEqual(row["external_verification_state"], "NOT_RUN")
        self.assertEqual(row["external_evidence_refs"], [])
        self.assertEqual(states["UO-0001"], "ACTIVE_USER_REQUIREMENT")

    def test_8000_character_project_instructions_example_remains_user_observation(self):
        row = record(
            statement="Vince personally observed an 8,000-character Project Instructions limit.",
        )
        states = mod.evaluate_records([row], POLICY)
        self.assertEqual(row["external_verification_state"], "NOT_RUN")
        self.assertEqual(row["external_evidence_refs"], [])
        self.assertEqual(states["UO-0001"], "ACTIVE_USER_REQUIREMENT")

    def test_tests_are_scoped_to_life_owned_evaluation_not_external_behavior(self):
        self.assertIn(
            "TEST_SCOPE_IS_LIFE_OWNED_RECORD_VALIDATION_AND_STATE_DERIVATION_ONLY",
            POLICY["rules"],
        )


if __name__ == "__main__":
    unittest.main()
