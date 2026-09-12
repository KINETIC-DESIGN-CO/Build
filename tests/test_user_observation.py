from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_user_observation.py"
spec = importlib.util.spec_from_file_location("evaluate_user_observation", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

POLICY = json.loads(
    (Path(__file__).resolve().parents[1] / "governance" / "user-observation-policy.json").read_text()
)


def record(
    rid="UO-0001",
    *,
    statement="Vince personally observed the behavior.",
    authorization="AUTHORIZED_FOR_LIFE_REQUIREMENT",
    external="NOT_RUN",
    evidence=None,
    supersedes=None,
):
    return {
        "id": rid,
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
    def test_authorized_observation_becomes_user_requirement_without_external_verification(self):
        states = mod.evaluate_records([record()], POLICY)
        self.assertEqual(states["UO-0001"], "ACTIVE_USER_REQUIREMENT")

    def test_not_run_is_not_relabelled_external_verified(self):
        row = record()
        mod.validate_record(row, POLICY)
        self.assertEqual(row["external_verification_state"], "NOT_RUN")

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
            evidence=["DIRECT_PLATFORM_READ:example"],
        )
        states = mod.evaluate_records([row], POLICY)
        self.assertEqual(states["UO-0001"], "DIRECT_EVIDENCE_CONFLICT")

    def test_verified_contradiction_requires_external_evidence(self):
        row = record(external="VERIFIED_CONTRADICTION")
        with self.assertRaises(mod.ObservationError):
            mod.validate_record(row, POLICY)

    def test_user_observation_cannot_satisfy_runtime_control(self):
        row = record()
        for kind in sorted(mod.CONTROL_DECISION_KINDS):
            self.assertFalse(mod.may_satisfy_runtime_control(row, kind, POLICY))

    def test_supersedes_must_reference_prior_record(self):
        row = record("UO-0002", supersedes=["UO-0001"])
        with self.assertRaises(mod.ObservationError):
            mod.evaluate_records([row], POLICY)

    def test_policy_runtime_authority_drift_is_rejected(self):
        bad = json.loads(json.dumps(POLICY))
        bad["runtime_control_authority"] = "PASS"
        with self.assertRaises(mod.ObservationError):
            mod.validate_policy(bad)


if __name__ == "__main__":
    unittest.main()
