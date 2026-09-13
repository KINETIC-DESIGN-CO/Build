#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from typing import Any

DECISION_KINDS = (
    "AUTHORIZATION","ROUTING","PRIORITY","STATE_TRANSITION","COMPLETION",
    "VERIFICATION","ESCALATION","RELEASE","MUTATION","EFFECT_EXECUTION",
)
INCOMPLETE_STATES = {"UNKNOWN","UNVERIFIED","NOT_RUN"}

def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()

def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value).astimezone(timezone.utc)

def _type_matches(value: Any, value_type: str) -> bool:
    if value_type == "STRING": return isinstance(value, str)
    if value_type == "INTEGER": return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "BOOLEAN": return isinstance(value, bool)
    if value_type == "STRING_SET":
        return isinstance(value, list) and all(isinstance(v, str) for v in value) and len(value) == len(set(value))
    if value_type == "SHA256":
        return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    if value_type == "OBJECT": return isinstance(value, dict)
    return False

def _result(decision: str, reasons: list[str]) -> dict:
    return {"decision": decision, "reason_codes": sorted(set(reasons))}

def evaluate_control(contract: dict, request: dict, snapshot: dict, *, evaluated_at: str) -> dict:
    fail, not_run = [], []
    exact = (
        ("decision_kind","DECISION_KIND_MISMATCH"),("contract_id","CONTRACT_ID_MISMATCH"),
        ("subject_type","SUBJECT_TYPE_MISMATCH"),("subject_id","SUBJECT_ID_MISMATCH"),
        ("action","ACTION_MISMATCH"),("scope_type","SCOPE_TYPE_MISMATCH"),("scope_id","SCOPE_ID_MISMATCH"),
    )
    for field, code in exact:
        if request.get(field) != contract.get(field): fail.append(code)
    if request.get("contract_sha256") != sha256_json(contract): fail.append("CONTRACT_HASH_MISMATCH")
    if request.get("input_snapshot_id") != snapshot.get("snapshot_id"): fail.append("SNAPSHOT_ID_MISMATCH")
    if request.get("input_snapshot_sha256") != sha256_json(snapshot): fail.append("SNAPSHOT_HASH_MISMATCH")

    required = {r["name"]: r for r in contract.get("required_inputs", [])}
    provided_list = snapshot.get("inputs", [])
    provided = {r.get("name"): r for r in provided_list if isinstance(r, dict) and isinstance(r.get("name"), str)}
    if len(provided) != len(provided_list): fail.append("DUPLICATE_OR_INVALID_INPUT_NAME")
    missing = sorted(set(required) - set(provided))
    extra = sorted(set(provided) - set(required))
    if missing: not_run.append("REQUIRED_INPUT_MISSING")
    if extra: fail.append("UNDECLARED_INPUT_PRESENT")

    now = _parse_time(evaluated_at)
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
        try:
            value = json.loads(inp.get("value_json", ""))
        except Exception:
            fail.append("INPUT_VALUE_JSON_INVALID")
            continue
        if not _type_matches(value, req.get("value_type")):
            fail.append("INPUT_VALUE_SHAPE_MISMATCH")
        if inp.get("value_json_sha256") != hashlib.sha256(inp.get("value_json", "").encode()).hexdigest():
            fail.append("INPUT_VALUE_HASH_MISMATCH")
        try:
            observed = _parse_time(inp.get("observed_at"))
        except Exception:
            fail.append("INPUT_OBSERVED_AT_INVALID")
            continue
        if observed > now:
            fail.append("INPUT_OBSERVED_IN_FUTURE")
        max_age = req.get("max_age_seconds")
        if isinstance(max_age, int) and (now-observed).total_seconds() > max_age:
            not_run.append("INPUT_STALE")
    if fail: return _result("FAIL", fail)
    if not_run: return _result("NOT_RUN", not_run)
    return _result("PASS", ["ALL_REQUIRED_EVIDENCE_BOUND"])

def make_receipt_candidate(contract: dict, request: dict, snapshot: dict, result: dict, *, evaluated_at: str, expires_at: str) -> dict:
    receipt = {
        "schema_version":1,
        "receipt_id":str(__import__("uuid").uuid4()),
        "issuer_type":"SOURCE_EVALUATOR",
        "persistence_state":"CANDIDATE",
        "decision":result["decision"],
        "reason_codes":result["reason_codes"],
        "decision_kind":request["decision_kind"], "contract_id":request["contract_id"],
        "request_id":request["request_id"], "contract_sha256":request["contract_sha256"],
        "input_snapshot_sha256":request["input_snapshot_sha256"],
        "subject_type":request["subject_type"], "subject_id":request["subject_id"],
        "action":request["action"], "scope_type":request["scope_type"], "scope_id":request["scope_id"],
        "operation_sha256":request["operation_sha256"],
        "evaluated_at":evaluated_at, "expires_at":expires_at,
    }
    receipt["receipt_sha256"] = sha256_json(receipt)
    return receipt

def recompute_receipt_sha(receipt: dict) -> str:
    copy_receipt = dict(receipt); copy_receipt.pop("receipt_sha256", None)
    return sha256_json(copy_receipt)

def evaluate_effect_eligibility(receipt: dict, effect_request: dict, *, evaluated_at: str) -> dict:
    fail, not_run = [], []
    if receipt.get("receipt_sha256") != recompute_receipt_sha(receipt): fail.append("RECEIPT_HASH_MISMATCH")
    if receipt.get("decision") != "PASS": fail.append("RECEIPT_NOT_PASS")
    if receipt.get("decision_kind") != "EFFECT_EXECUTION": fail.append("RECEIPT_KIND_NOT_EFFECT_EXECUTION")
    if receipt.get("issuer_type") != "TRUSTED_CONTROL_SERVICE": fail.append("RECEIPT_ISSUER_NOT_TRUSTED")
    if receipt.get("persistence_state") != "PERSISTED_TRUSTED": fail.append("RECEIPT_NOT_PERSISTED_TRUSTED")
    mapping = (
        ("receipt_id","receipt_id","RECEIPT_ID_MISMATCH"),
        ("receipt_sha256","receipt_sha256","RECEIPT_DIGEST_MISMATCH"),
        ("subject_type","subject_type","SUBJECT_TYPE_MISMATCH"),("subject_id","subject_id","SUBJECT_ID_MISMATCH"),
        ("action","action","ACTION_MISMATCH"),("scope_type","scope_type","SCOPE_TYPE_MISMATCH"),
        ("scope_id","scope_id","SCOPE_ID_MISMATCH"),("operation_sha256","operation_sha256","OPERATION_HASH_MISMATCH"),
    )
    for rfield, efield, code in mapping:
        if receipt.get(rfield) != effect_request.get(efield): fail.append(code)
    if not effect_request.get("prepared_attempt_ref"): fail.append("WRITE_AHEAD_PREPARATION_MISSING")
    if not str(effect_request.get("reliability_operation_contract_id","")).startswith("ROP-"):
        fail.append("RELIABILITY_OPERATION_CONTRACT_INVALID")
    try:
        if _parse_time(receipt.get("expires_at")) <= _parse_time(evaluated_at): not_run.append("RECEIPT_EXPIRED")
    except Exception:
        fail.append("RECEIPT_EXPIRY_INVALID")
    if fail: return _result("FAIL", fail)
    if not_run: return _result("NOT_RUN", not_run)
    return _result("PASS", ["TRUSTED_EFFECT_RECEIPT_BOUND"])

def evaluate_post_effect(effect_request: dict, verification: dict) -> dict:
    fail, not_run = [], []
    if verification.get("effect_request_id") != effect_request.get("effect_request_id"): fail.append("EFFECT_REQUEST_ID_MISMATCH")
    if verification.get("operation_sha256") != effect_request.get("operation_sha256"): fail.append("OPERATION_HASH_MISMATCH")
    if verification.get("readback_source_class") != "AUTHORITATIVE_READBACK": fail.append("READBACK_NOT_AUTHORITATIVE")
    effect = verification.get("effect_state")
    posts = verification.get("required_postconditions_state")
    if effect in {"EFFECT_UNKNOWN","NOT_EVALUATED"}: not_run.append("EFFECT_STATE_INCOMPLETE")
    elif effect != "EFFECT_VERIFIED": fail.append("EFFECT_NOT_VERIFIED")
    if posts in {"UNKNOWN","NOT_RUN"}: not_run.append("POSTCONDITIONS_INCOMPLETE")
    elif posts != "PASS": fail.append("POSTCONDITIONS_NOT_PASS")
    if fail: return _result("FAIL", fail)
    if not_run: return _result("NOT_RUN", not_run)
    return _result("PASS", ["AUTHORITATIVE_EFFECT_AND_POSTCONDITIONS_VERIFIED"])
