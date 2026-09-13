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

ACCEPTANCE_PATH = Path(__file__).with_name("typed-contract-evaluation.acceptance.json")
UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
MUTATION_PATH_PATTERN = re.compile(r"/(?:[A-Za-z_][A-Za-z0-9_]*)(?:/[A-Za-z_][A-Za-z0-9_]*)*")
EXPECTED_OUTCOMES = {"COMPLETE", "INCOMPLETE", "REJECT"}
STRICT_JSON_REJECTION_CASES = (
    ("duplicate_json_key_rejected", b'{"value":true,"value":false}'),
    ("nonfinite_nan_rejected", b'{"value":NaN}'),
    ("nonfinite_positive_infinity_rejected", b'{"value":Infinity}'),
    ("nonfinite_negative_infinity_rejected", b'{"value":-Infinity}'),
)


class EvaluationError(Exception):
    pass


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_nonfinite_constant(value: str) -> None:
    raise EvaluationError(f"non-finite JSON number is not permitted: {value}")


def decode_json(raw: bytes, source_name: str) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise EvaluationError(f"invalid JSON in {source_name}: {exc}") from exc


def load_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    document = decode_json(raw, path.name)
    if not isinstance(document, dict):
        raise EvaluationError(f"{path.name} must contain a JSON object")
    return document, digest


def exact_keys(value: dict[str, Any], expected: set[str]) -> bool:
    return set(value) == expected


def valid_uuid(value: Any) -> bool:
    return isinstance(value, str) and UUID_PATTERN.fullmatch(value) is not None


def valid_identifier(value: Any) -> bool:
    return isinstance(value, str) and IDENTIFIER_PATTERN.fullmatch(value) is not None


def exact_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def valid_contract_content(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if not exact_keys(
        value,
        {
            "contract_id",
            "contract_version",
            "decision_kind",
            "source_requirement",
            "side_effects",
            "predicate",
        },
    ):
        return False
    if not valid_uuid(value["contract_id"]):
        return False
    if not exact_int(value["contract_version"]) or value["contract_version"] < 1:
        return False
    if value["decision_kind"] != "COMPLETION":
        return False
    if value["source_requirement"] != "TEST_FIXTURE_ONLY":
        return False
    if value["side_effects"] != "NONE":
        return False

    predicate = value["predicate"]
    if not isinstance(predicate, dict) or not exact_keys(predicate, {"op", "input_ids"}):
        return False
    if predicate["op"] != "ALL_TRUE":
        return False
    input_ids = predicate["input_ids"]
    if not isinstance(input_ids, list) or not input_ids:
        return False
    if any(not valid_identifier(item) for item in input_ids):
        return False
    if len(set(input_ids)) != len(input_ids):
        return False
    return True


def evaluate(value: dict[str, Any], request_schema: dict[str, Any]) -> str:
    if not exact_keys(value, {"request", "contract_content", "inputs"}):
        return "REJECT"

    request = value["request"]
    contract = value["contract_content"]
    inputs = value["inputs"]

    if not control_request.instance_is_valid(request, request_schema, request_schema):
        return "REJECT"
    if not valid_contract_content(contract):
        return "REJECT"
    if request["contract_id"] != contract["contract_id"]:
        return "REJECT"
    if request["decision_kind"] != contract["decision_kind"]:
        return "REJECT"
    if not isinstance(inputs, dict):
        return "REJECT"

    input_ids = contract["predicate"]["input_ids"]
    if set(inputs) != set(input_ids):
        return "REJECT"
    if any(type(inputs[input_id]) is not bool for input_id in input_ids):
        return "REJECT"

    return "COMPLETE" if all(inputs[input_id] is True for input_id in input_ids) else "INCOMPLETE"


def resolve_parent(root: dict[str, Any], path: str) -> tuple[dict[str, Any], str]:
    if not isinstance(path, str) or MUTATION_PATH_PATTERN.fullmatch(path) is None:
        raise EvaluationError(f"unsupported mutation path: {path!r}")
    parts = path.split("/")[1:]
    parent: dict[str, Any] = root
    for segment in parts[:-1]:
        if segment not in parent or not isinstance(parent[segment], dict):
            raise EvaluationError(f"mutation path does not resolve to an object: {path}")
        parent = parent[segment]
    return parent, parts[-1]


def apply_mutation(value: dict[str, Any], mutation: dict[str, Any]) -> None:
    if not isinstance(mutation, dict):
        raise EvaluationError("mutation must be an object")
    op = mutation.get("op")
    if op in {"ADD", "REPLACE"}:
        if not exact_keys(mutation, {"op", "path", "value"}):
            raise EvaluationError(f"{op} mutation must contain exactly op, path, and value")
    elif op == "REMOVE":
        if not exact_keys(mutation, {"op", "path"}):
            raise EvaluationError("REMOVE mutation must contain exactly op and path")
    else:
        raise EvaluationError(f"unsupported mutation op: {op!r}")

    parent, target = resolve_parent(value, mutation["path"])
    if op == "ADD":
        if target in parent:
            raise EvaluationError(f"ADD target already exists: {mutation['path']}")
        parent[target] = copy.deepcopy(mutation["value"])
    elif op == "REPLACE":
        if target not in parent:
            raise EvaluationError(f"REPLACE target does not exist: {mutation['path']}")
        parent[target] = copy.deepcopy(mutation["value"])
    else:
        if target not in parent:
            raise EvaluationError(f"REMOVE target does not exist: {mutation['path']}")
        del parent[target]


def validate_acceptance_document(
    document: dict[str, Any], request_schema: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not exact_keys(document, {"contract_id", "purpose", "fixture", "acceptance_cases"}):
        raise EvaluationError("acceptance document has unsupported or missing top-level keys")
    if document["contract_id"] != "semantic_firewall.typed_contract_evaluation":
        raise EvaluationError("unexpected contract_id")
    if not isinstance(document["purpose"], str) or not document["purpose"].strip():
        raise EvaluationError("purpose must be a non-empty string")

    fixture = document["fixture"]
    if not isinstance(fixture, dict) or evaluate(fixture, request_schema) != "COMPLETE":
        raise EvaluationError("fixture must itself evaluate to COMPLETE")

    cases = document["acceptance_cases"]
    if not isinstance(cases, list) or not cases:
        raise EvaluationError("acceptance_cases must be a non-empty array")

    seen: set[str] = set()
    coverage: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or not exact_keys(case, {"case_id", "mutations", "expected"}):
            raise EvaluationError(f"acceptance case {index} has invalid shape")
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not valid_identifier(case_id):
            raise EvaluationError(f"acceptance case {index} has invalid case_id")
        if case_id in seen:
            raise EvaluationError(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        if case["expected"] not in EXPECTED_OUTCOMES:
            raise EvaluationError(f"{case_id}: unsupported expected outcome {case['expected']!r}")
        coverage.add(case["expected"])
        if not isinstance(case["mutations"], list):
            raise EvaluationError(f"{case_id}: mutations must be an array")

    missing = EXPECTED_OUTCOMES - coverage
    if missing:
        raise EvaluationError(f"missing acceptance outcome coverage: {sorted(missing)}")
    return fixture, cases


def run_strict_json_acceptance() -> int:
    failures = 0
    for case_id, raw in STRICT_JSON_REJECTION_CASES:
        try:
            decode_json(raw, case_id)
        except EvaluationError:
            print(f"PASS {case_id} expected=REJECT actual=REJECT")
        else:
            failures += 1
            print(f"FAIL {case_id} expected=REJECT actual=ACCEPT")
    return failures


def main() -> int:
    try:
        control_document, control_sha256 = load_json(control_request.CONTRACT_PATH)
        request_schema, _ = control_request.validate_contract_document(control_document)
        parser_failures = run_strict_json_acceptance()
        document, acceptance_sha256 = load_json(ACCEPTANCE_PATH)
        fixture, cases = validate_acceptance_document(document, request_schema)
    except (OSError, KeyError, TypeError, control_request.ContractError, EvaluationError) as exc:
        print(f"CONTRACT_ERROR: {exc}", file=sys.stderr)
        return 2

    failures = parser_failures
    for case in cases:
        candidate = copy.deepcopy(fixture)
        try:
            for mutation in case["mutations"]:
                apply_mutation(candidate, mutation)
            actual = evaluate(candidate, request_schema)
        except (KeyError, TypeError, EvaluationError) as exc:
            print(f"CONTRACT_ERROR: {case['case_id']}: {exc}", file=sys.stderr)
            return 2

        status = "PASS" if actual == case["expected"] else "FAIL"
        if status == "FAIL":
            failures += 1
        print(f"{status} {case['case_id']} expected={case['expected']} actual={actual}")

    result = "PASS" if failures == 0 else "FAIL"
    runner_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(
        json.dumps(
            {
                "contract_id": document["contract_id"],
                "control_request_artifact_sha256": control_sha256,
                "evaluation_artifact_sha256": acceptance_sha256,
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
