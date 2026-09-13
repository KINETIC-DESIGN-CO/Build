#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

CONTRACT_PATH = Path(__file__).with_name("control-request.acceptance.json")
EXPECTED_OUTCOMES = {
    "REQUEST_SCHEMA_VALID": True,
    "REQUEST_SCHEMA_INVALID": False,
}
SUPPORTED_SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"
SUPPORTED_SCHEMA_KEYWORDS = {
    "$schema",
    "$defs",
    "$ref",
    "type",
    "enum",
    "pattern",
    "required",
    "properties",
    "additionalProperties",
}
SUPPORTED_TYPES = {"object", "string"}


class ContractError(Exception):
    pass


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_contract(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        document = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ContractError(f"invalid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ContractError("contract document must be a JSON object")
    return document, digest


def ensure_exact_keys(value: dict[str, Any], allowed: set[str], location: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ContractError(f"unsupported keys at {location}: {sorted(unknown)}")


def validate_schema_definition(schema: Any, root: dict[str, Any], location: str) -> None:
    if not isinstance(schema, dict):
        raise ContractError(f"schema at {location} must be an object")

    ensure_exact_keys(schema, SUPPORTED_SCHEMA_KEYWORDS, location)

    if "$schema" in schema:
        if location != "$":
            raise ContractError("$schema is permitted only at the schema root")
        if schema["$schema"] != SUPPORTED_SCHEMA_URI:
            raise ContractError(f"unsupported $schema: {schema['$schema']!r}")

    if "$ref" in schema:
        ref = schema["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
            raise ContractError(f"only local #/$defs/ references are permitted at {location}")
        name = ref.removeprefix("#/$defs/")
        defs = root.get("$defs")
        if not isinstance(defs, dict) or name not in defs:
            raise ContractError(f"unresolved $ref at {location}: {ref}")

    if "type" in schema:
        schema_type = schema["type"]
        if schema_type not in SUPPORTED_TYPES:
            raise ContractError(f"unsupported schema type at {location}: {schema_type!r}")

    if "enum" in schema:
        enum_values = schema["enum"]
        if not isinstance(enum_values, list) or not enum_values:
            raise ContractError(f"enum at {location} must be a non-empty array")
        canonical = [json.dumps(v, sort_keys=True, separators=(",", ":")) for v in enum_values]
        if len(canonical) != len(set(canonical)):
            raise ContractError(f"enum at {location} contains duplicate values")

    if "pattern" in schema:
        pattern = schema["pattern"]
        if not isinstance(pattern, str):
            raise ContractError(f"pattern at {location} must be a string")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ContractError(f"invalid regex at {location}: {exc}") from exc

    if "required" in schema:
        required = schema["required"]
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise ContractError(f"required at {location} must be an array of strings")
        if len(required) != len(set(required)):
            raise ContractError(f"required at {location} contains duplicate names")

    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, dict):
            raise ContractError(f"properties at {location} must be an object")
        for name, child in properties.items():
            validate_schema_definition(child, root, f"{location}.properties.{name}")

    if "additionalProperties" in schema and not isinstance(schema["additionalProperties"], bool):
        raise ContractError(f"additionalProperties at {location} must be boolean")

    if "$defs" in schema:
        if location != "$":
            raise ContractError("$defs is permitted only at the schema root")
        defs = schema["$defs"]
        if not isinstance(defs, dict) or not defs:
            raise ContractError("$defs must be a non-empty object")
        for name, child in defs.items():
            validate_schema_definition(child, root, f"$.$defs.{name}")


def resolve_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    name = ref.removeprefix("#/$defs/")
    defs = root["$defs"]
    target = defs[name]
    if not isinstance(target, dict):
        raise ContractError(f"$ref target is not an object: {ref}")
    return target


def instance_is_valid(instance: Any, schema: dict[str, Any], root: dict[str, Any]) -> bool:
    if "$ref" in schema and not instance_is_valid(instance, resolve_ref(root, schema["$ref"]), root):
        return False

    schema_type = schema.get("type")
    if schema_type == "object" and not isinstance(instance, dict):
        return False
    if schema_type == "string" and not isinstance(instance, str):
        return False

    if "enum" in schema and instance not in schema["enum"]:
        return False

    if "pattern" in schema:
        if not isinstance(instance, str) or re.search(schema["pattern"], instance) is None:
            return False

    if isinstance(instance, dict):
        required = schema.get("required", [])
        if any(name not in instance for name in required):
            return False

        properties = schema.get("properties", {})
        for name, child_schema in properties.items():
            if name in instance and not instance_is_valid(instance[name], child_schema, root):
                return False

        if schema.get("additionalProperties") is False:
            if any(name not in properties for name in instance):
                return False

    return True


def validate_contract_document(document: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ensure_exact_keys(
        document,
        {"contract_id", "purpose", "control_request_schema", "acceptance_cases"},
        "contract document",
    )

    if document.get("contract_id") != "semantic_firewall.control_request":
        raise ContractError("unexpected contract_id")
    if not isinstance(document.get("purpose"), str) or not document["purpose"].strip():
        raise ContractError("purpose must be a non-empty string")

    schema = document.get("control_request_schema")
    if not isinstance(schema, dict):
        raise ContractError("control_request_schema must be an object")
    if schema.get("$schema") != SUPPORTED_SCHEMA_URI:
        raise ContractError(f"control_request_schema must declare {SUPPORTED_SCHEMA_URI}")
    validate_schema_definition(schema, schema, "$")

    cases = document.get("acceptance_cases")
    if not isinstance(cases, list) or not cases:
        raise ContractError("acceptance_cases must be a non-empty array")

    seen_case_ids: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ContractError(f"acceptance case {index} must be an object")
        ensure_exact_keys(case, {"case_id", "request", "expected"}, f"acceptance_cases[{index}]")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ContractError(f"acceptance case {index} has invalid case_id")
        if case_id in seen_case_ids:
            raise ContractError(f"duplicate case_id: {case_id}")
        seen_case_ids.add(case_id)
        if not isinstance(case.get("request"), dict):
            raise ContractError(f"{case_id}: request must be an object")
        if case.get("expected") not in EXPECTED_OUTCOMES:
            raise ContractError(f"{case_id}: unsupported expected outcome {case.get('expected')!r}")

    decision_ref = schema.get("properties", {}).get("decision_kind", {}).get("$ref")
    if not isinstance(decision_ref, str):
        raise ContractError("decision_kind must reference a closed enum")
    decision_schema = resolve_ref(schema, decision_ref)
    decision_kinds = decision_schema.get("enum")
    if not isinstance(decision_kinds, list) or not all(isinstance(item, str) for item in decision_kinds):
        raise ContractError("decision_kind reference must resolve to a string enum")

    for decision_kind in decision_kinds:
        valid_coverage = any(
            case["expected"] == "REQUEST_SCHEMA_VALID"
            and case["request"].get("decision_kind") == decision_kind
            for case in cases
        )
        invalid_coverage = any(
            case["expected"] == "REQUEST_SCHEMA_INVALID"
            and case["request"].get("decision_kind") == decision_kind
            for case in cases
        )
        if not valid_coverage or not invalid_coverage:
            raise ContractError(
                f"decision_kind {decision_kind} requires at least one valid and one invalid acceptance case"
            )

    return schema, cases


def main() -> int:
    try:
        document, artifact_sha256 = load_contract(CONTRACT_PATH)
        schema, cases = validate_contract_document(document)
    except (OSError, ContractError) as exc:
        print(f"CONTRACT_ERROR: {exc}", file=sys.stderr)
        return 2

    failures = 0
    for case in cases:
        actual_valid = instance_is_valid(case["request"], schema, schema)
        expected_valid = EXPECTED_OUTCOMES[case["expected"]]
        status = "PASS" if actual_valid == expected_valid else "FAIL"
        if status == "FAIL":
            failures += 1
        actual_name = "REQUEST_SCHEMA_VALID" if actual_valid else "REQUEST_SCHEMA_INVALID"
        print(
            f"{status} {case['case_id']} expected={case['expected']} actual={actual_name}"
        )

    result = "PASS" if failures == 0 else "FAIL"
    print(
        json.dumps(
            {
                "contract_id": document["contract_id"],
                "artifact_sha256": artifact_sha256,
                "cases_total": len(cases),
                "cases_failed": failures,
                "result": result,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
