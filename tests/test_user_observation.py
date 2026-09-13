from __future__ import annotations

import importlib.util
import json
import tempfile
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
    record_id="UO-9001",
    *,
    statement="Vince personally observed the behavior.",
    source_class="VINCE_PERSONAL_TEST",
    source_refs=None,
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
        "source_class": source_class,
        "source_refs": ["TEST:VINCE_OBSERVATION"] if source_refs is None else source_refs,
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

    def test_canonical_ledger_preserves_both_motivating_user_observations(self):
        rows = mod.load_ledger(ROOT / POLICY["ledger_path"], POLICY)
        states = mod.evaluate_records(rows, POLICY)
        by_id = {row["id"]: row for row in rows}
        self.assertEqual(set(by_id), {"UO-0001", "UO-0002"})
        self.assertEqual(states["UO-0001"], "ACTIVE_USER_REQUIREMENT")
        self.assertEqual(states["UO-0002"], "ACTIVE_USER_REQUIREMENT")
        self.assertEqual(by_id["UO-0001"]["external_verification_state"], "NOT_RUN")
        self.assertEqual(by_id["UO-0001"]["external_evidence_refs"], [])
        self.assertIn("continuity/events.jsonl:E-0023", by_id["UO-0001"]["source_refs"])
        self.assertEqual(by_id["UO-0002"]["external_verification_state"], "NOT_RUN")
        self.assertEqual(by_id["UO-0002"]["external_evidence_refs"], [])
        self.assertIn("GITHUB_ISSUE:18", by_id["UO-0002"]["source_refs"])

    def test_authorized_observation_becomes_user_requirement_without_external_verification(self):
        states = mod.evaluate_records([record()], POLICY)
        self.assertEqual(states["UO-9001"], "ACTIVE_USER_REQUIREMENT")

    def test_source_refs_are_required_provenance(self):
        row = record(source_refs=[])
        with self.assertRaises(mod.ObservationError):
            mod.validate_record(row, POLICY)

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
        self.assertEqual(states["UO-9001"], "ACTIVE_USER_REQUIREMENT")

    def test_unauthorized_observation_is_recorded_only(self):
        states = mod.evaluate_records(
            [record(authorization="NOT_AUTHORIZED")],
            POLICY,
        )
        self.assertEqual(states["UO-9001"], "RECORDED_ONLY")

    def test_later_correction_supersedes_without_rewriting_prior_provenance(self):
        first = record(
            statement="Original observation.",
            source_refs=["VINCE:ORIGINAL"],
        )
        second = record(
            "UO-9002",
            statement="Corrected observation.",
            source_refs=["VINCE:CORRECTION"],
            supersedes=["UO-9001"],
        )
        states = mod.evaluate_records([first, second], POLICY)
        self.assertEqual(first["statement"], "Original observation.")
        self.assertEqual(first["source_refs"], ["VINCE:ORIGINAL"])
        self.assertEqual(states["UO-9001"], "SUPERSEDED")
        self.assertEqual(states["UO-9002"], "ACTIVE_USER_REQUIREMENT")

    def test_direct_verified_contradiction_surfaces_conflict_without_rewrite(self):
        row = record(
            statement="User-observed behavior remains historical provenance.",
            source_refs=["VINCE:OBSERVATION"],
            external="VERIFIED_CONTRADICTION",
            evidence=["DIRECT_PLATFORM_READ:contradiction"],
        )
        states = mod.evaluate_records([row], POLICY)
        self.assertEqual(states["UO-9001"], "DIRECT_EVIDENCE_CONFLICT")
        self.assertEqual(row["statement"], "User-observed behavior remains historical provenance.")
        self.assertEqual(row["source_refs"], ["VINCE:OBSERVATION"])

    def test_verified_contradiction_requires_external_evidence(self):
        row = record(external="VERIFIED_CONTRADICTION")
        with self.assertRaises(mod.ObservationError):
            mod.validate_record(row, POLICY)

    def test_user_observation_cannot_satisfy_any_runtime_control_kind(self):
        row = record()
        for kind in sorted(mod.CONTROL_DECISION_KINDS):
            self.assertFalse(mod.may_satisfy_runtime_control(row, kind, POLICY))

    def test_supersedes_must_reference_prior_record(self):
        row = record("UO-9002", supersedes=["UO-9001"])
        with self.assertRaises(mod.ObservationError):
            mod.evaluate_records([row], POLICY)

    def test_issue18_continue_observation_is_not_machine_proof_of_chatgpt_internals(self):
        rows = mod.load_ledger(ROOT / POLICY["ledger_path"], POLICY)
        row = next(item for item in rows if item["id"] == "UO-0002")
        self.assertEqual(row["source_class"], "VINCE_PERSONAL_TEST")
        self.assertEqual(row["external_verification_state"], "NOT_RUN")
        self.assertEqual(row["external_evidence_refs"], [])
        self.assertIn("GITHUB_ISSUE:18", row["source_refs"])

    def test_8000_character_example_remains_user_observation_not_external_fact(self):
        rows = mod.load_ledger(ROOT / POLICY["ledger_path"], POLICY)
        row = next(item for item in rows if item["id"] == "UO-0001")
        self.assertEqual(row["source_class"], "VINCE_PERSONAL_TEST")
        self.assertEqual(row["external_verification_state"], "NOT_RUN")
        self.assertEqual(row["external_evidence_refs"], [])

    def test_tests_are_scoped_to_life_owned_evaluation_not_external_behavior(self):
        self.assertIn(
            "TEST_SCOPE_IS_LIFE_OWNED_RECORD_VALIDATION_AND_STATE_DERIVATION_ONLY",
            POLICY["rules"],
        )

    def test_ledger_rejects_noncanonical_or_blank_lines(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ledger.jsonl"
            row = record()
            path.write_text(json.dumps(row, indent=2) + "\n")
            with self.assertRaises(mod.ObservationError):
                mod.load_ledger(path, POLICY)


if __name__ == "__main__":
    unittest.main()
