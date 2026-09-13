#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import run_control_request_acceptance as control_request

ACCEPTANCE_PATH = Path(__file__).with_name("contract-reference.acceptance.json")
UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
EXPECTED_OUTCOMES = {"ELIGIBLE": True, "INELIGIBLE": False}
STRICT_JSON_REJECTION_CASES = (
    ("nonfinite_nan_rejected", b'{"value":NaN}'),
    ("nonfinite_positive_infinity_rejected", b'{"value":Infinity}'),
    ("nonfinite_negative_infinity_rejected", b'{"value":-Infinity}'),
)


class EligibilityError(Exception):
    pass


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EligibilityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_nonfinite_constant(value: str) -> None:
    raise EligibilityError(f"non-finite JSON number is not permitted: {value}")


def decode_json(raw: bytes, source_name: str) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise EligibilityError(f"invalid JSON in {source_name}: {exc}") from exc


def load_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    document = decode_json(raw, path.name)
    if not isinstance(document, dict):
        raise EligibilityError(f"{path.name} must contain a JSON object")
    return document, digest


def run_strict_json_acceptance() -> int:
    failures = 0
    for case_id, raw in STRICT_JSON_REJECTION_CASES:
        try:
            decode_json(raw, case_id)
        except EligibilityError:
            print(f"PASS {case_id} expected=REJECT actual=REJECT")
        else:
            failures += 1
            print(f"FAIL {case_id} expected=REJECT actual=ACCEPT")
    return failures


def exact_keys(value: dict[str, Any], expected: set[str]) -> bool:
    return set(value) == expected


def valid_uuid(value: Any) -> bool:
    return isinstance(value, str) and UUID_PATTERN.fullmatch(value) is not None


def valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def valid_identifier(value: Any) -> bool:
    return isinstance(value, str) and IDENTIFIER_PATTERN.fullmatch(value) is not None


def valid_identity(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and exact_keys(value, {"id", "sha256"})
        and valid_identifier(value["id"])
        and valid_sha256(value["sha256"])
    )


def valid_contract(value: Any, decision_kinds: set[str]) -> bool:
    required = {
        "contract_id",
        "decision_kind",
        "enabled",
        "content_sha256",
        "validator",
        "evaluator",
        "validation_receipt_id",
        "test_receipt_id",
        "test_suite_sha256",
    }
    return (
        isinstance(value, dict)
        and exact_keys(value, required)
        and valid_uuid(value["contract_id"])
        and isinstance(value["decision_kind"], str)
        and value["decision_kind"] in decision_kinds
        and isinstance(value["enabled"], bool)
        and valid_sha256(value["content_sha256"])
        and valid_identity(value["validator"])
        and valid_identity(value["evaluator"])
        and valid_uuid(value["validation_receipt_id"])
        and valid_uuid(value["test_receipt_id"])
        and valid_sha256(value["test_suite_sha256"])
    )


def valid_validation_receipt(value: Any) -> bool:
    required = {"receipt_id", "contract_id", "content_sha256", "validator", "result"}
    return (
        isinstance(value, dict)
        and exact_keys(value, required)
        and valid_uuid(value["receipt_id"])
        and valid_uuid(value["contract_id"])
        and valid_sha256(value["content_sha256"])
        and valid_identity(value["validator"])
        and isinstance(value["result"], str)
        and value["result"] in {"PASS", "FAIL"}
    )


def valid_test_receipt(value: Any) -> bool:
    required = {"receipt_id", "contract_id", "content_sha256", "evaluator", "suite_sha256", "result"}
    return (
        isinstance(value, dict)
        and exact_keys(value, required)
        and valid_uuid(value["receipt_id"])
        and valid_uuid(value["contract_id"])
        and valid_sha256(value["content_sha256"])
        and valid_identity(value["evaluator"])
        and valid_sha256(value["suite_sha256"])
        and isinstance(value["result"], str)
        and value["result"] in {"PASS", "FAIL"}
    )


def eligible(
    value: dict[str, Any],
    request_schema: dict[str, Any],
    decision_kinds: set[str],
) -> bool:
    if not exact_keys(value, {"request", "contract", "validation_receipt", "test_receipt"}):
        return False

    request = value["request"]
    contract = value["contract"]
    validation = value["validation_receipt"]
    test = value["test_receipt"]

    if not control_request.instance_is_valid(request, request_schema, request_schema):
        return False
    if not valid_contract(contract, decision_kinds):
        return False
    if not valid_validation_receipt(validation):
        return False
    if not valid_test_receipt(test):
        return False

    return all(
        (
            contract["enabled"] is True,
            request["contract_id"] == contract["contract_id"],
            request["decision_kind"] == contract["decision_kind"],
            contract["validation_receipt_id"] == validation["receipt_id"],
            contract["contract_id"] == validation["contract_id"],
            contract["content_sha256"] == validation["content_sha256"],
            contract["validator"] == validation["validator"],
            validation["result"] == "PASS",
            contract["test_receipt_id"] == test["receipt_id"],
            contract["contract_id"] == test["contract_id"],
            contract["content_sha256"] == test["content_sha256"],
            contract["evaluator"] == test["evaluator"],
            contract["test_suite_sha256"] == test["suite_sha256"],
            test["result"] == "PASS",
        )
    )


def apply_mutation(value: dict[str, Any], mutation: dict[str, Any]) -> None:
    if not exact_keys(mutation, {"op", "path", "value"}):
        raise EligibilityError("each mutation must contain exactly op, path, and value")
    if mutation["op"] not in {"ADD", "REPLACE"}:
        raise EligibilityError(f"unsupported mutation op: {mutation['op']!r}")
    path = mutation["path"]
    if not isinstance(path, str) or re.fullmatch(r"/(?:[A-Za-z_][A-Za-z0-9_]*)(?:/[A-Za-z_][A-Za-z0-9_]*)*", path) is None:
        raise EligibilityError(f"unsupported mutation path: {path!r}")

    parts = path.split("/")[1:]
    parent: dict[str, Any] = value
    for segment in parts[:-1]:
        if segment not in parent or not isinstance(parent[segment], dict):
            raise EligibilityError(f"mutation path does not resolve to an object: {path}")
        parent = parent[segment]

    target = parts[-1]
    if mutation["op"] == "ADD":
        if target in parent:
            raise EligibilityError(f"ADD target already exists: {path}")
    else:
        if target not in parent:
            raise EligibilityError(f"REPLACE target does not exist: {path}")
    parent[target] = copy.deepcopy(mutation["value"])


def validate_acceptance_document(
    document: dict[str, Any],
    request_schema: dict[str, Any],
    decision_kinds: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not exact_keys(document, {"contract_id", "purpose", "fixture", "acceptance_cases"}):
        raise EligibilityError("acceptance document has unsupported or missing top-level keys")
    if document["contract_id"] != "semantic_firewall.contract_reference_eligibility":
        raise EligibilityError("unexpected contract_id")
    if not isinstance(document["purpose"], str) or not document["purpose"].strip():
        raise EligibilityError("purpose must be a non-empty string")

    fixture = document["fixture"]
    if not isinstance(fixture, dict) or not eligible(fixture, request_schema, decision_kinds):
        raise EligibilityError("fixture must itself be ELIGIBLE")

    cases = document["acceptance_cases"]
    if not isinstance(cases, list) or not cases:
        raise EligibilityError("acceptance_cases must be a non-empty array")

    seen: set[str] = set()
    eligible_kind_coverage: set[str] = set()
    has_ineligible = False
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or not exact_keys(case, {"case_id", "mutations", "expected"}):
            raise EligibilityError(f"acceptance case {index} has invalid shape")
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not case_id:
            raise EligibilityError(f"acceptance case {index} has invalid case_id")
        if case_id in seen:
            raise EligibilityError(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        if not isinstance(case["expected"], str) or case["expected"] not in EXPECTED_OUTCOMES:
            raise EligibilityError(f"{case_id}: unsupported expected outcome {case['expected']!r}")
        if not isinstance(case["mutations"], list):
            raise EligibilityError(f"{case_id}: mutations must be an array")

        candidate = copy.deepcopy(fixture)
        for mutation in case["mutations"]:
            if not isinstance(mutation, dict):
                raise EligibilityError(f"{case_id}: mutation must be an object")
            apply_mutation(candidate, mutation)

        if case["expected"] == "ELIGIBLE":
            request = candidate.get("request")
            if isinstance(request, dict) and isinstance(request.get("decision_kind"), str) and request["decision_kind"] in decision_kinds:
                eligible_kind_coverage.add(request["decision_kind"])
        else:
            has_ineligible = True

    missing_coverage = decision_kinds - eligible_kind_coverage
    if missing_coverage:
        raise EligibilityError(f"missing ELIGIBLE coverage for decision kinds: {sorted(missing_coverage)}")
    if not has_ineligible:
        raise EligibilityError("at least one INELIGIBLE acceptance case is required")

    return fixture, cases


def main() -> int:
    try:
        control_document, control_sha256 = control_request.load_contract(control_request.CONTRACT_PATH)
        request_schema, _ = control_request.validate_contract_document(control_document)
        decision_ref = request_schema["properties"]["decision_kind"]["$ref"]
        decision_schema = control_request.resolve_ref(request_schema, decision_ref)
        decision_kinds = set(decision_schema["enum"])

        parser_failures = run_strict_json_acceptance()
        document, acceptance_sha256 = load_json(ACCEPTANCE_PATH)
        fixture, cases = validate_acceptance_document(document, request_schema, decision_kinds)
    except (OSError, KeyError, TypeError, control_request.ContractError, EligibilityError) as exc:
        print(f"CONTRACT_ERROR: {exc}", file=sys.stderr)
        return 2

    failures = parser_failures
    for case in cases:
        candidate = copy.deepcopy(fixture)
        try:
            for mutation in case["mutations"]:
                apply_mutation(candidate, mutation)
            actual_eligible = eligible(candidate, request_schema, decision_kinds)
        except (KeyError, TypeError, EligibilityError) as exc:
            print(f"CONTRACT_ERROR: {case['case_id']}: {exc}", file=sys.stderr)
            return 2

        expected_eligible = EXPECTED_OUTCOMES[case["expected"]]
        status = "PASS" if actual_eligible == expected_eligible else "FAIL"
        if status == "FAIL":
            failures += 1
        actual = "ELIGIBLE" if actual_eligible else "INELIGIBLE"
        print(f"{status} {case['case_id']} expected={case['expected']} actual={actual}")

    result = "PASS" if failures == 0 else "FAIL"
    runner_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(
        json.dumps(
            {
                "contract_id": document["contract_id"],
                "control_request_artifact_sha256": control_sha256,
                "eligibility_artifact_sha256": acceptance_sha256,
                "runner_sha256": runner_sha256,
                "strict_json_cases_total": len(STRICT_JSON_REJECTION_CASES),
                "strict_json_cases_failed": parser_failures,
                "cases_total": len(cases),
                "cases_failed": failures - parser_failures,
                "result": result,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
