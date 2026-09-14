from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from scripts import evaluate_semantic_firewall as sf
from scripts import evaluate_semantic_firewall_trusted_evidence as trusted

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-13T20:00:00Z"
FRESH = "2026-09-13T19:59:00Z"
ISSUED = "2026-09-13T19:59:30Z"
EXPIRES = "2026-09-13T20:05:00Z"
PREDICATE_ID = "SF-PRED-EFFECT-AUTHORIZATION-STATE-AUTHORIZED-V1"
RECEIPT_ID = "55555555-5555-4555-8555-555555555555"


def canonical_registry() -> dict:
    return json.loads((ROOT / "contracts" / "semantic-firewall-v1" / "predicate-registry.json").read_text())


def value_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class SemanticFirewallTrustedEvidenceTests(unittest.TestCase):
    def contract(self) -> dict:
        return {
            "schema_version": 1,
            "contract_id": "11111111-1111-4111-8111-111111111111",
            "decision_kind": "EFFECT_EXECUTION",
            "subject_type": "WORK_ITEM",
            "subject_id": "work-57",
            "action": "EXECUTE_EFFECT",
            "scope_type": "COMPONENT",
            "scope_id": "issue_57",
            "predicate_id": PREDICATE_ID,
            "required_inputs": [
                {
                    "name": "authorization_state",
                    "value_type": "STRING",
                    "accepted_source_types": ["LIVE_GITHUB"],
                    "max_age_seconds": 300,
                }
            ],
        }

    def snapshot_and_receipt(self, *, expires_at=EXPIRES) -> tuple[dict, dict]:
        encoded = value_json("AUTHORIZED")
        value_digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        row = {
            "name": "authorization_state",
            "state": "KNOWN",
            "source_type": "LIVE_GITHUB",
            "source_ref": "github:lock:component:issue_57",
            "source_version": "generation:5",
            "observed_at": FRESH,
            "value_type": "STRING",
            "value_json": encoded,
            "value_json_sha256": value_digest,
        }
        receipt = {
            "schema_version": 1,
            "evidence_receipt_id": RECEIPT_ID,
            "issuer_type": "TRUSTED_EVIDENCE_ADAPTER",
            "persistence_state": "PERSISTED_TRUSTED",
            "input_name": row["name"],
            "source_type": row["source_type"],
            "source_ref": row["source_ref"],
            "source_version": row["source_version"],
            "observed_at": row["observed_at"],
            "value_type": row["value_type"],
            "value_json_sha256": row["value_json_sha256"],
            "issued_at": ISSUED,
            "expires_at": expires_at,
        }
        receipt["evidence_receipt_sha256"] = trusted.recompute_evidence_receipt_sha(receipt)
        row["evidence_receipt_id"] = receipt["evidence_receipt_id"]
        row["evidence_receipt_sha256"] = receipt["evidence_receipt_sha256"]
        snapshot = {
            "schema_version": 1,
            "snapshot_id": "22222222-2222-4222-8222-222222222222",
            "captured_at": NOW,
            "inputs": [row],
        }
        return snapshot, receipt

    def request(self, contract: dict, snapshot: dict) -> dict:
        registry = canonical_registry()
        predicate = next(row for row in registry["runtime_predicates"] if row["predicate_id"] == PREDICATE_ID)
        return {
            "schema_version": 1,
            "request_id": "33333333-3333-4333-8333-333333333333",
            "decision_kind": contract["decision_kind"],
            "contract_id": contract["contract_id"],
            "contract_sha256": sf.sha256_json(contract),
            "predicate_id": PREDICATE_ID,
            "predicate_definition_sha256": sf.predicate_definition_sha256(predicate),
            "subject_type": contract["subject_type"],
            "subject_id": contract["subject_id"],
            "action": contract["action"],
            "scope_type": contract["scope_type"],
            "scope_id": contract["scope_id"],
            "operation_sha256": "a" * 64,
            "input_snapshot_id": snapshot["snapshot_id"],
            "input_snapshot_sha256": sf.sha256_json(snapshot),
            "requested_at": NOW,
        }

    def validate_bindings(self, snapshot: dict, receipts):
        return trusted.validate_trusted_evidence_bindings(
            snapshot,
            receipts,
            evaluated_at=NOW,
        )

    def evaluate(self, snapshot: dict, receipts):
        contract = self.contract()
        return trusted.evaluate_trusted_control(
            contract,
            self.request(contract, snapshot),
            snapshot,
            trusted_evidence_receipts=receipts,
            evaluated_at=NOW,
        )

    def test_missing_binding_candidates_fails_closed_as_not_run(self):
        snapshot, _ = self.snapshot_and_receipt()
        result = self.evaluate(snapshot, None)
        self.assertEqual("NOT_RUN", result["decision"])
        self.assertIn("TRUSTED_EVIDENCE_BINDING_CANDIDATES_NOT_BOUND", result["reason_codes"])

    def test_missing_candidate_receipt_fails_closed_as_not_run(self):
        snapshot, _ = self.snapshot_and_receipt()
        result = self.evaluate(snapshot, {})
        self.assertEqual("NOT_RUN", result["decision"])
        self.assertIn("TRUSTED_EVIDENCE_RECEIPT_NOT_FOUND", result["reason_codes"])

    def test_source_binding_candidate_can_pass_structural_validation(self):
        snapshot, receipt = self.snapshot_and_receipt()
        result = self.validate_bindings(snapshot, {RECEIPT_ID: receipt})
        self.assertEqual("PASS", result["decision"])
        self.assertIn("ALL_KNOWN_INPUTS_MATCH_EVIDENCE_RECEIPT_BINDING_CANDIDATES", result["reason_codes"])
        self.assertEqual("NONE", result["runtime_control_authority"])

    def test_source_only_receipt_cannot_create_trusted_control_pass(self):
        snapshot, receipt = self.snapshot_and_receipt()
        result = self.evaluate(snapshot, {RECEIPT_ID: receipt})
        self.assertEqual("NOT_RUN", result["decision"])
        self.assertIn("TRUSTED_EVIDENCE_ADAPTER_NOT_IMPLEMENTED", result["reason_codes"])
        self.assertIn("AUTHORITATIVE_PERSISTENCE_READBACK_NOT_IMPLEMENTED", result["reason_codes"])
        self.assertEqual("NONE", result["runtime_control_authority"])

    def test_self_hash_cannot_establish_trusted_issuer_label(self):
        snapshot, receipt = self.snapshot_and_receipt()
        receipt["issuer_type"] = "SOURCE_EVIDENCE_ADAPTER"
        receipt["evidence_receipt_sha256"] = trusted.recompute_evidence_receipt_sha(receipt)
        snapshot["inputs"][0]["evidence_receipt_sha256"] = receipt["evidence_receipt_sha256"]
        result = self.validate_bindings(snapshot, {RECEIPT_ID: receipt})
        self.assertEqual("FAIL", result["decision"])
        self.assertIn("TRUSTED_EVIDENCE_ISSUER_LABEL_MISMATCH", result["reason_codes"])

    def test_receipt_must_bind_exact_source_identity(self):
        snapshot, receipt = self.snapshot_and_receipt()
        receipt["source_ref"] = "github:other-resource"
        receipt["evidence_receipt_sha256"] = trusted.recompute_evidence_receipt_sha(receipt)
        snapshot["inputs"][0]["evidence_receipt_sha256"] = receipt["evidence_receipt_sha256"]
        result = self.validate_bindings(snapshot, {RECEIPT_ID: receipt})
        self.assertEqual("FAIL", result["decision"])
        self.assertIn("TRUSTED_EVIDENCE_SOURCE_REF_MISMATCH", result["reason_codes"])

    def test_expired_binding_candidate_cannot_pass(self):
        snapshot, receipt = self.snapshot_and_receipt(expires_at="2026-09-13T19:59:45Z")
        result = self.validate_bindings(snapshot, {RECEIPT_ID: receipt})
        self.assertEqual("NOT_RUN", result["decision"])
        self.assertIn("TRUSTED_EVIDENCE_RECEIPT_EXPIRED", result["reason_codes"])

    def test_receipt_digest_mismatch_fails(self):
        snapshot, receipt = self.snapshot_and_receipt()
        snapshot["inputs"][0]["evidence_receipt_sha256"] = "0" * 64
        result = self.validate_bindings(snapshot, {RECEIPT_ID: receipt})
        self.assertEqual("FAIL", result["decision"])
        self.assertIn("TRUSTED_EVIDENCE_RECEIPT_DIGEST_MISMATCH", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
