#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DECISION_KINDS = (
    "AUTHORIZATION",
    "ROUTING",
    "PRIORITY",
    "STATE_TRANSITION",
    "COMPLETION",
    "VERIFICATION",
    "ESCALATION",
    "RELEASE",
    "MUTATION",
    "EFFECT_EXECUTION",
)
INCOMPLETE_STATES = {"UNKNOWN", "UNVERIFIED", "NOT_RUN"}
ROOT = Path(__file__).resolve().parents[1]
PREDICATE_REGISTRY_PATH = ROOT / "contracts" / "semantic-firewall-v1" / "predicate-registry.json"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value).astimezone(timezone.utc)


def _type_matches(value: Any, value_type: str) -> bool:
    if value_type == "STRING":
        return isinstance(value, str)
    if value_type == "INTEGER":
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "BOOLEAN":
        return isinstance(value, bool)
    if value_type == "STRING_SET":
        return isinstance(value, list) and all(isinstance(v, str) for v in value) and len(value) == len(set(value))
    if value_type == "SHA256":
        return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    if value_type == "OBJECT":
        return isinstance(value, dict)
    return False


def _result(decision: str, reasons: list[str]) -> dict:
    return {
        "decision": decision,
        "reason_codes": sorted(set(reasons)),
        "runtime_control_authority": "NONE",
    }


def _load_predicate_registry() -> dict:
    with PREDICATE_REGISTRY_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _predicate_index(registry: dict) -> dict[str, dict]:
    rows = registry.get("runtime_predicates", [])
    return {
        row["predicate_id"]: row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("predicate_id"), str)
    }


def _semantic_input_valid(definition: dict, value: Any, predicates: dict[str, dict], input_record: dict) -> tuple[bool, str | None]:
    semantic_type = definition.get("semantic_type")
    if semantic_type == "CLOSED_ENUM":
        allowed = definition.get("allowed_values")
        return (isinstance(allowed, list) and value in allowed, "PREDICATE_INPUT_OUTSIDE_CLOSED_DOMAIN")
    if semantic_type == "EXACT_ID":
        return (isinstance(value, str) and bool(value), "PREDICATE_INPUT_EXACT_ID_INVALID")
    if semantic_type == "INTEGER_WITH_UNIT":
        return (
            isinstance(value, int) and not isinstance(value, bool) and isinstance(definition.get("unit"), str),
            "PREDICATE_INPUT_UNIT_INVALID",
        )
    if semantic_type == "TIMESTAMP_RFC3339":
        try:
            _parse_time(value)
            return True, None
        except Exception:
            return False, "PREDICATE_INPUT_TIMESTAMP_INVALID"
    if semantic_type == "STRING_SET":
        return (_type_matches(value, "STRING_SET"), "PREDICATE_INPUT_SET_INVALID")
    if semantic_type == "SHA256":
        return (_type_matches(value, "SHA256"), "PREDICATE_INPUT_SHA256_INVALID")
    if semantic_type == "VERSION_STRING":
        return (isinstance(value, str) and bool(value), "PREDICATE_INPUT_VERSION_INVALID")
    if semantic_type == "DETERMINISTIC_DERIVATION":
        derivation = definition.get("derivation_predicate_id")
        observed_derivation = input_record.get("derivation_predicate_id")
        return (
            isinstance(derivation, str)
            and derivation in predicates
            and observed_derivation == derivation,
            "PREDICATE_DERIVATION_BINDING_MISSING",
        )
    return False, "PREDICATE_INPUT_SEMANTIC_TYPE_INVALID"


def _evaluate_expression(expression: dict, values: dict[str, Any]) -> bool:
    left_name = expression.get("left_input")
    if left_name not in values:
        raise ValueError("left input missing")
    left = values[left_name]
    right = json.loads(expression["right_value_json"])
    operator = expression.get("operator")
    if operator == "EQ":
        return left == right
    if operator == "INTEGER_GTE":
        return isinstance(left, int) and not isinstance(left, bool) and isinstance(right, int) and not isinstance(right, bool) and left >= right
    if operator == "TIMESTAMP_GTE":
        return _parse_time(left) >= _parse_time(right)
    if operator == "SET_CONTAINS_ALL":
        return isinstance(left, list) and isinstance(right, list) and set(right).issubset(set(left))
    raise ValueError("unsupported predicate operator")


def _evaluate_registered_predicate(
    contract: dict,
    provided: dict[str, dict],
    parsed_values: dict[str, Any],
    *,
    predicate_registry: dict | None,
) -> dict:
    try:
        registry = predicate_registry if predicate_registry is not None else _load_predicate_registry()
    except (OSError, json.JSONDecodeError):
        return _result("NOT_RUN", ["PREDICATE_REGISTRY_NOT_RUN"])

    predicates = _predicate_index(registry)
    predicate_id = contract.get("predicate_id")
    predicate = predicates.get(predicate_id)
    if predicate is None:
        return _result("NOT_RUN", ["PREDICATE_DEFINITION_MISSING"])
    if contract.get("decision_kind") not in predicate.get("decision_kinds", []):
        return _result("FAIL", ["PREDICATE_DECISION_KIND_MISMATCH"])

    definitions = predicate.get("required_inputs", [])
    defined = {
        row.get("name"): row
        for row in definitions
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    contract_inputs = {
        row.get("name"): row
        for row in contract.get("required_inputs", [])
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    if len(defined) != len(definitions) or set(defined) != set(contract_inputs):
        return _result("FAIL", ["PREDICATE_INPUT_CONTRACT_MISMATCH"])

    unsafe_sources = set(registry.get("unsafe_input_source_classes", []))
    reasons: list[str] = []
    for name, definition in defined.items():
        req = contract_inputs[name]
        inp = provided[name]
        if req.get("value_type") != definition.get("value_type"):
            reasons.append("PREDICATE_INPUT_TYPE_MISMATCH")
        source_type = inp.get("source_type")
        if source_type in unsafe_sources or source_type not in definition.get("source_classes", []):
            reasons.append("PREDICATE_INPUT_SOURCE_FORBIDDEN")
        ok, code = _semantic_input_valid(definition, parsed_values[name], predicates, inp)
        if not ok and code:
            reasons.append(code)
    if reasons:
        return _result("FAIL", reasons)

    kind = predicate.get("definition_kind")
    if kind == "EXPRESSION":
        expression = predicate.get("expression")
        if not isinstance(expression, dict):
            return _result("NOT_RUN", ["PREDICATE_DEFINITION_MISSING"])
        try:
            predicate_pass = _evaluate_expression(expression, parsed_values)
        except Exception:
            return _result("FAIL", ["PREDICATE_DEFINITION_INVALID"])
        if predicate_pass:
            return _result("PASS", ["ALL_REQUIRED_EVIDENCE_BOUND", "PREDICATE_TRUE"])
        return _result("FAIL", ["PREDICATE_FALSE"])
    if kind == "EVALUATOR_REF":
        return _result("NOT_RUN", ["PREDICATE_EVALUATOR_NOT_RUNTIME_BOUND"])
    return _result("NOT_RUN", ["PREDICATE_DEFINITION_MISSING"])


def evaluate_control(
    contract: dict,
    request: dict,
    snapshot: dict,
    *,
    evaluated_at: str,
    predicate_registry: dict | None = None,
) -> dict:
    fail: list[str] = []
    not_run: list[str] = []
    exact = (
        ("decision_kind", "DECISION_KIND_MISMATCH"),
        ("contract_id", "CONTRACT_ID_MISMATCH"),
        ("subject_type", "SUBJECT_TYPE_MISMATCH"),
        ("subject_id", "SUBJECT_ID_MISMATCH"),
        ("action", "ACTION_MISMATCH"),
        ("scope_type", "SCOPE_TYPE_MISMATCH"),
        ("scope_id", "SCOPE_ID_MISMATCH"),
    )
    for field, code in exact:
        if request.get(field) != contract.get(field):
            fail.append(code)
    if request.get("contract_sha256") != sha256_json(contract):
        fail.append("CONTRACT_HASH_MISMATCH")
    if request.get("input_snapshot_id") != snapshot.get("snapshot_id"):
        fail.append("SNAPSHOT_ID_MISMATCH")
    if request.get("input_snapshot_sha256") != sha256_json(snapshot):
        fail.append("SNAPSHOT_HASH_MISMATCH")

    try:
        now = _parse_time(evaluated_at)
        requested_at = _parse_time(request.get("requested_at"))
        captured_at = _parse_time(snapshot.get("captured_at"))
        if requested_at > now:
            fail.append("REQUESTED_AT_IN_FUTURE")
        if captured_at > now:
            fail.append("SNAPSHOT_CAPTURED_IN_FUTURE")
        if captured_at > requested_at:
            fail.append("SNAPSHOT_CAPTURED_AFTER_REQUEST")
    except Exception:
        fail.append("CONTROL_TIME_INVALID")
        now = None

    required_list = contract.get("required_inputs", [])
    required = {
        row.get("name"): row
        for row in required_list
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    if len(required) != len(required_list):
        fail.append("DUPLICATE_OR_INVALID_REQUIRED_INPUT_NAME")

    provided_list = snapshot.get("inputs", [])
    provided = {
        row.get("name"): row
        for row in provided_list
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    if len(provided) != len(provided_list):
        fail.append("DUPLICATE_OR_INVALID_INPUT_NAME")

    missing = sorted(set(required) - set(provided))
    extra = sorted(set(provided) - set(required))
    if missing:
        not_run.append("REQUIRED_INPUT_MISSING")
    if extra:
        fail.append("UNDECLARED_INPUT_PRESENT")

    parsed_values: dict[str, Any] = {}
    for name in sorted(set(required) & set(provided)):
        req, inp = required[name], provided[name]
        state = inp.get("state")
        if state in INCOMPLETE_STATES:
            not_run.append(f"INPUT_{state}")
            continue
        if state != "KNOWN":
            fail.append("INPUT_STATE_INVALID")
            continue
        if inp.get("source_type") not in req.get("accepted_source_types", []):
            fail.append("INPUT_SOURCE_TYPE_FORBIDDEN")
        if inp.get("value_type") != req.get("value_type"):
            fail.append("INPUT_VALUE_TYPE_MISMATCH")
        value_text = inp.get("value_json")
        if not isinstance(value_text, str):
            fail.append("INPUT_VALUE_JSON_INVALID")
            continue
        try:
            value = json.loads(value_text)
        except Exception:
            fail.append("INPUT_VALUE_JSON_INVALID")
            continue
        if not _type_matches(value, req.get("value_type")):
            fail.append("INPUT_VALUE_SHAPE_MISMATCH")
        else:
            parsed_values[name] = value
        if inp.get("value_json_sha256") != hashlib.sha256(value_text.encode("utf-8")).hexdigest():
            fail.append("INPUT_VALUE_HASH_MISMATCH")
        try:
            observed = _parse_time(inp.get("observed_at"))
        except Exception:
            fail.append("INPUT_OBSERVED_AT_INVALID")
            continue
        if now is not None:
            if observed > now:
                fail.append("INPUT_OBSERVED_IN_FUTURE")
            max_age = req.get("max_age_seconds")
            if isinstance(max_age, int) and (now - observed).total_seconds() > max_age:
                not_run.append("INPUT_STALE")

    if fail:
        return _result("FAIL", fail)
    if not_run:
        return _result("NOT_RUN", not_run)
    if set(parsed_values) != set(required):
        return _result("NOT_RUN", ["PREDICATE_INPUT_NOT_AVAILABLE"])
    return _evaluate_registered_predicate(
        contract,
        provided,
        parsed_values,
        predicate_registry=predicate_registry,
    )


def make_receipt_candidate(
    contract: dict,
    request: dict,
    snapshot: dict,
    result: dict,
    *,
    evaluated_at: str,
    expires_at: str,
) -> dict:
    receipt = {
        "schema_version": 1,
        "receipt_id": str(uuid.uuid4()),
        "issuer_type": "SOURCE_EVALUATOR",
        "persistence_state": "CANDIDATE",
        "decision": result["decision"],
        "reason_codes": result["reason_codes"],
        "decision_kind": request["decision_kind"],
        "contract_id": request["contract_id"],
        "request_id": request["request_id"],
        "contract_sha256": request["contract_sha256"],
        "input_snapshot_sha256": request["input_snapshot_sha256"],
        "subject_type": request["subject_type"],
        "subject_id": request["subject_id"],
        "action": request["action"],
        "scope_type": request["scope_type"],
        "scope_id": request["scope_id"],
        "operation_sha256": request["operation_sha256"],
        "evaluated_at": evaluated_at,
        "expires_at": expires_at,
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    return receipt


def recompute_receipt_sha(receipt: dict) -> str:
    copy_receipt = dict(receipt)
    copy_receipt.pop("receipt_sha256", None)
    return sha256_json(copy_receipt)


def evaluate_effect_eligibility(receipt: dict, effect_request: dict, *, evaluated_at: str) -> dict:
    fail: list[str] = []
    not_run: list[str] = []
    if receipt.get("receipt_sha256") != recompute_receipt_sha(receipt):
        fail.append("RECEIPT_HASH_MISMATCH")
    if receipt.get("decision") != "PASS":
        fail.append("RECEIPT_NOT_PASS")
    if receipt.get("decision_kind") != "EFFECT_EXECUTION":
        fail.append("RECEIPT_KIND_NOT_EFFECT_EXECUTION")
    if receipt.get("issuer_type") != "TRUSTED_CONTROL_SERVICE":
        fail.append("RECEIPT_ISSUER_NOT_TRUSTED")
    if receipt.get("persistence_state") != "PERSISTED_TRUSTED":
        fail.append("RECEIPT_NOT_PERSISTED_TRUSTED")

    mapping = (
        ("receipt_id", "receipt_id", "RECEIPT_ID_MISMATCH"),
        ("receipt_sha256", "receipt_sha256", "RECEIPT_DIGEST_MISMATCH"),
        ("subject_type", "subject_type", "SUBJECT_TYPE_MISMATCH"),
        ("subject_id", "subject_id", "SUBJECT_ID_MISMATCH"),
        ("action", "action", "ACTION_MISMATCH"),
        ("scope_type", "scope_type", "SCOPE_TYPE_MISMATCH"),
        ("scope_id", "scope_id", "SCOPE_ID_MISMATCH"),
        ("operation_sha256", "operation_sha256", "OPERATION_HASH_MISMATCH"),
    )
    for receipt_field, effect_field, code in mapping:
        if receipt.get(receipt_field) != effect_request.get(effect_field):
            fail.append(code)

    if not effect_request.get("prepared_attempt_ref"):
        fail.append("WRITE_AHEAD_PREPARATION_MISSING")
    operation_contract_id = effect_request.get("reliability_operation_contract_id")
    if not isinstance(operation_contract_id, str) or not operation_contract_id.startswith("ROP-"):
        fail.append("RELIABILITY_OPERATION_CONTRACT_INVALID")

    try:
        now = _parse_time(evaluated_at)
        receipt_evaluated_at = _parse_time(receipt.get("evaluated_at"))
        receipt_expires_at = _parse_time(receipt.get("expires_at"))
        effect_requested_at = _parse_time(effect_request.get("requested_at"))
        if receipt_evaluated_at > now:
            fail.append("RECEIPT_EVALUATED_IN_FUTURE")
        if effect_requested_at > now:
            fail.append("EFFECT_REQUESTED_IN_FUTURE")
        if effect_requested_at < receipt_evaluated_at:
            fail.append("EFFECT_REQUEST_PRECEDES_RECEIPT")
        if receipt_expires_at <= receipt_evaluated_at:
            fail.append("RECEIPT_WINDOW_INVALID")
        elif receipt_expires_at <= now:
            not_run.append("RECEIPT_EXPIRED")
    except Exception:
        fail.append("EFFECT_TIME_INVALID")

    if fail:
        return _result("FAIL", fail)
    if not_run:
        return _result("NOT_RUN", not_run)
    return _result("PASS", ["TRUSTED_EFFECT_RECEIPT_BOUND"])


def evaluate_post_effect(effect_request: dict, verification: dict, *, evaluated_at: str) -> dict:
    fail: list[str] = []
    not_run: list[str] = []
    if verification.get("effect_request_id") != effect_request.get("effect_request_id"):
        fail.append("EFFECT_REQUEST_ID_MISMATCH")
    if verification.get("operation_sha256") != effect_request.get("operation_sha256"):
        fail.append("OPERATION_HASH_MISMATCH")
    if verification.get("readback_source_class") != "AUTHORITATIVE_READBACK":
        fail.append("READBACK_NOT_AUTHORITATIVE")

    try:
        now = _parse_time(evaluated_at)
        requested_at = _parse_time(effect_request.get("requested_at"))
        observed_at = _parse_time(verification.get("observed_at"))
        if observed_at > now:
            fail.append("READBACK_OBSERVED_IN_FUTURE")
        if observed_at < requested_at:
            fail.append("READBACK_PRECEDES_EFFECT_REQUEST")
    except Exception:
        fail.append("POST_EFFECT_TIME_INVALID")

    effect = verification.get("effect_state")
    posts = verification.get("required_postconditions_state")
    if effect in {"EFFECT_UNKNOWN", "NOT_EVALUATED"}:
        not_run.append("EFFECT_STATE_INCOMPLETE")
    elif effect != "EFFECT_VERIFIED":
        fail.append("EFFECT_NOT_VERIFIED")
    if posts in {"UNKNOWN", "NOT_RUN"}:
        not_run.append("POSTCONDITIONS_INCOMPLETE")
    elif posts != "PASS":
        fail.append("POSTCONDITIONS_NOT_PASS")

    if fail:
        return _result("FAIL", fail)
    if not_run:
        return _result("NOT_RUN", not_run)
    return _result("PASS", ["AUTHORITATIVE_EFFECT_AND_POSTCONDITIONS_VERIFIED"])
