#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from scripts import evaluate_semantic_firewall as sf


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value).astimezone(timezone.utc)


def _result(decision: str, reasons: list[str]) -> dict:
    return {
        "decision": decision,
        "reason_codes": sorted(set(reasons)),
        "runtime_control_authority": "NONE",
    }


def recompute_evidence_receipt_sha(receipt: dict[str, Any]) -> str:
    copy_receipt = dict(receipt)
    copy_receipt.pop("evidence_receipt_sha256", None)
    return sf.sha256_json(copy_receipt)


def validate_trusted_evidence_bindings(
    snapshot: dict[str, Any],
    trusted_evidence_receipts: dict[str, dict[str, Any]] | None,
    *,
    evaluated_at: str,
) -> dict:
    fail: list[str] = []
    not_run: list[str] = []
    if trusted_evidence_receipts is None:
        return _result("NOT_RUN", ["TRUSTED_EVIDENCE_ADAPTER_NOT_BOUND"])
    if not isinstance(trusted_evidence_receipts, dict):
        return _result("FAIL", ["TRUSTED_EVIDENCE_STORE_INVALID"])

    try:
        now = _parse_time(evaluated_at)
    except Exception:
        return _result("FAIL", ["TRUSTED_EVIDENCE_TIME_INVALID"])

    used_receipt_ids: set[str] = set()
    for input_record in snapshot.get("inputs", []):
        if not isinstance(input_record, dict) or input_record.get("state") != "KNOWN":
            continue

        receipt_id = input_record.get("evidence_receipt_id")
        receipt_sha = input_record.get("evidence_receipt_sha256")
        if not isinstance(receipt_id, str) or not receipt_id:
            not_run.append("TRUSTED_EVIDENCE_RECEIPT_ID_MISSING")
            continue
        if not isinstance(receipt_sha, str) or len(receipt_sha) != 64:
            not_run.append("TRUSTED_EVIDENCE_RECEIPT_DIGEST_MISSING")
            continue
        if receipt_id in used_receipt_ids:
            fail.append("TRUSTED_EVIDENCE_RECEIPT_REUSED")
            continue
        used_receipt_ids.add(receipt_id)

        receipt = trusted_evidence_receipts.get(receipt_id)
        if not isinstance(receipt, dict):
            not_run.append("TRUSTED_EVIDENCE_RECEIPT_NOT_FOUND")
            continue
        if receipt.get("evidence_receipt_id") != receipt_id:
            fail.append("TRUSTED_EVIDENCE_RECEIPT_ID_MISMATCH")
        if receipt.get("evidence_receipt_sha256") != receipt_sha:
            fail.append("TRUSTED_EVIDENCE_RECEIPT_DIGEST_MISMATCH")
        if receipt.get("evidence_receipt_sha256") != recompute_evidence_receipt_sha(receipt):
            fail.append("TRUSTED_EVIDENCE_RECEIPT_HASH_MISMATCH")
        if receipt.get("issuer_type") != "TRUSTED_EVIDENCE_ADAPTER":
            fail.append("TRUSTED_EVIDENCE_ISSUER_NOT_TRUSTED")
        if receipt.get("persistence_state") != "PERSISTED_TRUSTED":
            fail.append("TRUSTED_EVIDENCE_NOT_PERSISTED_TRUSTED")

        mapping = (
            ("input_name", "name", "TRUSTED_EVIDENCE_INPUT_NAME_MISMATCH"),
            ("source_type", "source_type", "TRUSTED_EVIDENCE_SOURCE_TYPE_MISMATCH"),
            ("source_ref", "source_ref", "TRUSTED_EVIDENCE_SOURCE_REF_MISMATCH"),
            ("source_version", "source_version", "TRUSTED_EVIDENCE_SOURCE_VERSION_MISMATCH"),
            ("observed_at", "observed_at", "TRUSTED_EVIDENCE_OBSERVED_AT_MISMATCH"),
            ("value_type", "value_type", "TRUSTED_EVIDENCE_VALUE_TYPE_MISMATCH"),
            ("value_json_sha256", "value_json_sha256", "TRUSTED_EVIDENCE_VALUE_DIGEST_MISMATCH"),
        )
        for receipt_field, input_field, code in mapping:
            if receipt.get(receipt_field) != input_record.get(input_field):
                fail.append(code)

        try:
            observed_at = _parse_time(receipt.get("observed_at"))
            issued_at = _parse_time(receipt.get("issued_at"))
            expires_at = _parse_time(receipt.get("expires_at"))
            if observed_at > issued_at:
                fail.append("TRUSTED_EVIDENCE_ISSUED_BEFORE_OBSERVATION")
            if issued_at > now:
                fail.append("TRUSTED_EVIDENCE_ISSUED_IN_FUTURE")
            if expires_at <= issued_at:
                fail.append("TRUSTED_EVIDENCE_WINDOW_INVALID")
            elif expires_at <= now:
                not_run.append("TRUSTED_EVIDENCE_RECEIPT_EXPIRED")
        except Exception:
            fail.append("TRUSTED_EVIDENCE_TIME_INVALID")

    if fail:
        return _result("FAIL", fail)
    if not_run:
        return _result("NOT_RUN", not_run)
    return _result("PASS", ["ALL_KNOWN_INPUTS_BOUND_TO_PERSISTED_TRUSTED_EVIDENCE"])


def evaluate_trusted_control(
    contract: dict[str, Any],
    request: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    trusted_evidence_receipts: dict[str, dict[str, Any]] | None,
    evaluated_at: str,
    predicate_registry: dict[str, Any] | None = None,
) -> dict:
    base_result = sf.evaluate_control(
        contract,
        request,
        snapshot,
        evaluated_at=evaluated_at,
        predicate_registry=predicate_registry,
    )
    if base_result.get("decision") != "PASS":
        return base_result

    binding_result = validate_trusted_evidence_bindings(
        snapshot,
        trusted_evidence_receipts,
        evaluated_at=evaluated_at,
    )
    if binding_result.get("decision") != "PASS":
        return binding_result

    return _result(
        "PASS",
        list(base_result.get("reason_codes", [])) + list(binding_result.get("reason_codes", [])),
    )
