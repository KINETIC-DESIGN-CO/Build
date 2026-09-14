from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVALUATOR_PATH = ROOT / "scripts" / "evaluate_semantic_firewall.py"
_spec = importlib.util.spec_from_file_location("life_semantic_firewall_eval_tests", EVALUATOR_PATH)
assert _spec is not None and _spec.loader is not None
sf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sf)

NOW = "2026-09-13T20:00:00Z"
FRESH = "2026-09-13T19:59:00Z"
STALE = "2026-09-13T19:00:00Z"
FUTURE = "2026-09-13T20:01:00Z"
PREDICATE_ID = "SF-PRED-EFFECT-AUTHORIZATION-STATE-AUTHORIZED-V1"


def value_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def value_hash(value_text: str) -> str:
    return hashlib.sha256(value_text.encode("utf-8")).hexdigest()


class SemanticFirewallV1Tests(unittest.TestCase):
    def contract(self):
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

    def snapshot(self, *, state="KNOWN", source_type="LIVE_GITHUB", observed_at=FRESH, value="AUTHORIZED", derivation_predicate_id=None):
        encoded = value_json(value)
        row = {
            "name": "authorization_state",
            "state": state,
            "source_type": source_type,
            "source_ref": "github:lock:component:issue_57",
            "source_version": "generation:1",
            "observed_at": observed_at,
            "value_type": "STRING",
            "value_json": encoded,
            "value_json_sha256": value_hash(encoded),
        }
        if derivation_predicate_id is not None:
            row["derivation_predicate_id"] = derivation_predicate_id
        return {
            "schema_version": 1,
            "snapshot_id": "22222222-2222-4222-8222-222222222222",
            "captured_at": NOW,
            "inputs": [row],
        }

    def request(self, contract, snapshot):
        return {
            "schema_version": 1,
            "request_id": "33333333-3333-4333-8333-333333333333",
            "decision_kind": contract["decision_kind"],
            "contract_id": contract["contract_id"],
            "contract_sha256": sf.sha256_json(contract),
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

    def effect_request(self, receipt):
        return {
            "schema_version": 1,
            "effect_request_id": "44444444-4444-4444-8444-444444444444",
            "receipt_id": receipt["receipt_id"],
            "receipt_sha256": receipt["receipt_sha256"],
            "subject_type": receipt["subject_type"],
            "subject_id": receipt["subject_id"],
            "action": receipt["action"],
            "scope_type": receipt["scope_type"],
            "scope_id": receipt["scope_id"],
            "operation_sha256": receipt["operation_sha256"],
            "reliability_operation_contract_id": "ROP-0001",
            "prepared_attempt_ref": "reliability:attempt:prepared:1",
            "requested_at": NOW,
        }

    def trusted_receipt(self):
        contract = self.contract()
        snapshot = self.snapshot()
        request = self.request(contract, snapshot)
        result = sf.evaluate_control(contract, request, snapshot, evaluated_at=NOW)
        self.assertEqual("PASS", result["decision"])
        receipt = sf.make_receipt_candidate(contract, request, snapshot, result, evaluated_at=NOW, expires_at="2026-09-13T20:10:00Z")
        receipt["issuer_type"] = "TRUSTED_CONTROL_SERVICE"
        receipt["persistence_state"] = "PERSISTED_TRUSTED"
        receipt["receipt_sha256"] = sf.recompute_receipt_sha(receipt)
        return receipt

    def test_exact_bound_evidence_and_canonical_predicate_pass(self):
        contract = self.contract()
        snapshot = self.snapshot()
        result = sf.evaluate_control(contract, self.request(contract, snapshot), snapshot, evaluated_at=NOW)
        self.assertEqual("PASS", result["decision"])
        self.assertEqual(["ALL_REQUIRED_EVIDENCE_BOUND", "PREDICATE_TRUE"], result["reason_codes"])
        self.assertEqual("NONE", result["runtime_control_authority"])

    def test_unknown_required_input_is_not_run(self):
        contract = self.contract(); snapshot = self.snapshot(state="UNKNOWN")
        result = sf.evaluate_control(contract, self.request(contract, snapshot), snapshot, evaluated_at=NOW)
        self.assertEqual("NOT_RUN", result["decision"]); self.assertIn("INPUT_UNKNOWN", result["reason_codes"])

    def test_stale_required_input_is_not_run(self):
        contract = self.contract(); snapshot = self.snapshot(observed_at=STALE)
        result = sf.evaluate_control(contract, self.request(contract, snapshot), snapshot, evaluated_at=NOW)
        self.assertEqual("NOT_RUN", result["decision"]); self.assertIn("INPUT_STALE", result["reason_codes"])

    def test_wrong_source_type_fails(self):
        contract = self.contract(); snapshot = self.snapshot(source_type="MODEL_RESPONSE")
        result = sf.evaluate_control(contract, self.request(contract, snapshot), snapshot, evaluated_at=NOW)
        self.assertEqual("FAIL", result["decision"]); self.assertIn("INPUT_SOURCE_TYPE_FORBIDDEN", result["reason_codes"])

    def test_contract_whitelist_cannot_launder_model_provenance(self):
        contract = self.contract()
        contract["required_inputs"][0]["accepted_source_types"] = ["MODEL_RESPONSE"]
        snapshot = self.snapshot(source_type="MODEL_RESPONSE")
        result = sf.evaluate_control(contract, self.request(contract, snapshot), snapshot, evaluated_at=NOW)
        self.assertEqual("FAIL", result["decision"])
        self.assertIn("PREDICATE_INPUT_SOURCE_FORBIDDEN", result["reason_codes"])

    def test_undefined_typed_predicate_fails_closed(self):
        contract = self.contract(); contract["predicate_id"] = "SF-PRED-UNDEFINED-MATERIALITY-V1"
        snapshot = self.snapshot()
        result = sf.evaluate_control(contract, self.request(contract, snapshot), snapshot, evaluated_at=NOW)
        self.assertEqual("NOT_RUN", result["decision"])
        self.assertEqual(["PREDICATE_DEFINITION_MISSING"], result["reason_codes"])

    def test_predicate_false_is_fail_not_pass(self):
        contract = self.contract(); snapshot = self.snapshot(value="DENIED")
        result = sf.evaluate_control(contract, self.request(contract, snapshot), snapshot, evaluated_at=NOW)
        self.assertEqual("FAIL", result["decision"])
        self.assertIn("PREDICATE_INPUT_OUTSIDE_CLOSED_DOMAIN", result["reason_codes"])

    def test_deterministic_derivation_requires_exact_predicate_provenance(self):
        derivation_id = "SF-PRED-DERIVE-MATERIALITY-V1"
        registry = {
            "unsafe_input_source_classes": ["MODEL_RESPONSE", "PROSE"],
            "runtime_predicates": [
                {
                    "predicate_id": derivation_id,
                    "definition_kind": "EXPRESSION",
                    "decision_kinds": ["EFFECT_EXECUTION"],
                    "required_inputs": [{"name":"authorization_state","value_type":"STRING","semantic_type":"CLOSED_ENUM","source_classes":["LIVE_GITHUB"],"unit":None,"allowed_values":["AUTHORIZED"],"derivation_predicate_id":None}],
                    "expression": {"operator":"EQ","left_input":"authorization_state","right_value_type":"STRING","right_value_json":"\"AUTHORIZED\"","unit":None},
                    "evaluator_ref": None,
                    "evaluator_config_json": None,
                },
                {
                    "predicate_id": PREDICATE_ID,
                    "definition_kind": "EXPRESSION",
                    "decision_kinds": ["EFFECT_EXECUTION"],
                    "required_inputs": [{"name":"authorization_state","value_type":"STRING","semantic_type":"DETERMINISTIC_DERIVATION","source_classes":["LIVE_GITHUB"],"unit":None,"allowed_values":None,"derivation_predicate_id":derivation_id}],
                    "expression": {"operator":"EQ","left_input":"authorization_state","right_value_type":"STRING","right_value_json":"\"AUTHORIZED\"","unit":None},
                    "evaluator_ref": None,
                    "evaluator_config_json": None,
                },
            ],
        }
        contract = self.contract()
        no_binding = self.snapshot()
        result = sf.evaluate_control(contract, self.request(contract, no_binding), no_binding, evaluated_at=NOW, predicate_registry=registry)
        self.assertEqual("FAIL", result["decision"]); self.assertIn("PREDICATE_DERIVATION_BINDING_MISSING", result["reason_codes"])
        bound = self.snapshot(derivation_predicate_id=derivation_id)
        result = sf.evaluate_control(contract, self.request(contract, bound), bound, evaluated_at=NOW, predicate_registry=registry)
        self.assertEqual("PASS", result["decision"])

    def test_future_observation_fails(self):
        contract = self.contract(); snapshot = self.snapshot(observed_at=FUTURE)
        result = sf.evaluate_control(contract, self.request(contract, snapshot), snapshot, evaluated_at=NOW)
        self.assertEqual("FAIL", result["decision"]); self.assertIn("INPUT_OBSERVED_IN_FUTURE", result["reason_codes"])

    def test_contract_hash_mismatch_fails(self):
        contract = self.contract(); snapshot = self.snapshot(); request = self.request(contract, snapshot); request["contract_sha256"] = "0" * 64
        result = sf.evaluate_control(contract, request, snapshot, evaluated_at=NOW)
        self.assertEqual("FAIL", result["decision"]); self.assertIn("CONTRACT_HASH_MISMATCH", result["reason_codes"])

    def test_source_candidate_receipt_has_zero_effect_eligibility(self):
        contract = self.contract(); snapshot = self.snapshot(); request = self.request(contract, snapshot)
        result = sf.evaluate_control(contract, request, snapshot, evaluated_at=NOW)
        receipt = sf.make_receipt_candidate(contract, request, snapshot, result, evaluated_at=NOW, expires_at="2026-09-13T20:10:00Z")
        eligibility = sf.evaluate_effect_eligibility(receipt, self.effect_request(receipt), evaluated_at=NOW)
        self.assertEqual("FAIL", eligibility["decision"])
        self.assertIn("RECEIPT_ISSUER_NOT_TRUSTED", eligibility["reason_codes"])
        self.assertIn("RECEIPT_NOT_PERSISTED_TRUSTED", eligibility["reason_codes"])

    def test_trusted_persisted_receipt_with_write_ahead_binding_passes(self):
        receipt = self.trusted_receipt()
        result = sf.evaluate_effect_eligibility(receipt, self.effect_request(receipt), evaluated_at=NOW)
        self.assertEqual("PASS", result["decision"]); self.assertEqual(["TRUSTED_EFFECT_RECEIPT_BOUND"], result["reason_codes"])

    def test_operation_digest_mismatch_fails_effect_eligibility(self):
        receipt = self.trusted_receipt(); effect = self.effect_request(receipt); effect["operation_sha256"] = "b" * 64
        result = sf.evaluate_effect_eligibility(receipt, effect, evaluated_at=NOW)
        self.assertEqual("FAIL", result["decision"]); self.assertIn("OPERATION_HASH_MISMATCH", result["reason_codes"])

    def test_expired_trusted_receipt_is_not_run(self):
        receipt = self.trusted_receipt(); receipt["evaluated_at"] = "2026-09-13T19:50:00Z"; receipt["expires_at"] = "2026-09-13T19:59:59Z"; receipt["receipt_sha256"] = sf.recompute_receipt_sha(receipt)
        result = sf.evaluate_effect_eligibility(receipt, self.effect_request(receipt), evaluated_at=NOW)
        self.assertEqual("NOT_RUN", result["decision"]); self.assertIn("RECEIPT_EXPIRED", result["reason_codes"])

    def test_post_effect_requires_authoritative_verified_effect_and_postconditions(self):
        receipt = self.trusted_receipt(); effect = self.effect_request(receipt)
        verification = {"schema_version":1,"verification_id":"55555555-5555-4555-8555-555555555555","effect_request_id":effect["effect_request_id"],"operation_sha256":effect["operation_sha256"],"effect_state":"EFFECT_VERIFIED","required_postconditions_state":"PASS","readback_source_class":"AUTHORITATIVE_READBACK","readback_ref":"github:readback:1","observed_at":NOW}
        result = sf.evaluate_post_effect(effect, verification, evaluated_at=NOW)
        self.assertEqual("PASS", result["decision"])

    def test_unknown_effect_fails_closed_as_not_run(self):
        receipt = self.trusted_receipt(); effect = self.effect_request(receipt)
        verification = {"schema_version":1,"verification_id":"55555555-5555-4555-8555-555555555555","effect_request_id":effect["effect_request_id"],"operation_sha256":effect["operation_sha256"],"effect_state":"EFFECT_UNKNOWN","required_postconditions_state":"UNKNOWN","readback_source_class":"AUTHORITATIVE_READBACK","readback_ref":"github:readback:unknown","observed_at":NOW}
        result = sf.evaluate_post_effect(effect, verification, evaluated_at=NOW)
        self.assertEqual("NOT_RUN", result["decision"]); self.assertIn("EFFECT_STATE_INCOMPLETE", result["reason_codes"]); self.assertIn("POSTCONDITIONS_INCOMPLETE", result["reason_codes"])

    def test_duplicate_required_input_name_fails(self):
        contract = self.contract(); contract["required_inputs"].append({"name":"authorization_state","value_type":"STRING","accepted_source_types":["LIVE_GITHUB"],"max_age_seconds":600})
        snapshot = self.snapshot(); result = sf.evaluate_control(contract, self.request(contract, snapshot), snapshot, evaluated_at=NOW)
        self.assertEqual("FAIL", result["decision"]); self.assertIn("DUPLICATE_OR_INVALID_REQUIRED_INPUT_NAME", result["reason_codes"])

    def test_future_request_time_fails(self):
        contract = self.contract(); snapshot = self.snapshot(); request = self.request(contract, snapshot); request["requested_at"] = FUTURE
        result = sf.evaluate_control(contract, request, snapshot, evaluated_at=NOW)
        self.assertEqual("FAIL", result["decision"]); self.assertIn("REQUESTED_AT_IN_FUTURE", result["reason_codes"])

    def test_missing_write_ahead_preparation_fails_effect_eligibility(self):
        receipt = self.trusted_receipt(); effect = self.effect_request(receipt); effect["prepared_attempt_ref"] = ""
        result = sf.evaluate_effect_eligibility(receipt, effect, evaluated_at=NOW)
        self.assertEqual("FAIL", result["decision"]); self.assertIn("WRITE_AHEAD_PREPARATION_MISSING", result["reason_codes"])

    def test_spec_blocks_runtime_activation_without_trusted_evidence_adapter(self):
        spec = json.loads((ROOT / "contracts/semantic-firewall-v1/spec.json").read_text())
        self.assertEqual("NOT_IMPLEMENTED", spec["evidence_trust_boundary"]["trusted_evidence_adapter_state"])
        self.assertEqual("SOURCE_ONLY_NOT_RUNTIME_AUTHORITY", spec["activation_state"])
        self.assertEqual("contracts/semantic-firewall-v1/predicate-registry.json", spec["predicate_registry_path"])


if __name__ == "__main__":
    unittest.main()
