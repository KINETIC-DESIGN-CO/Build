#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import run_control_request_acceptance as control_request

ACCEPTANCE_PATH = Path(__file__).with_name("control-input-binding.acceptance.json")
EXPECTED_OUTCOMES = {"INPUTS_BOUND": True, "INPUTS_UNBOUND": False}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
INPUT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
TOKEN_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
VALUE_TYPES = {"STRING", "INTEGER", "BOOLEAN", "STRING_SET"}
INPUT_STATES = {"KNOWN", "UNKNOWN"}


class BindingError(Exception):
    pass


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BindingError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_nonfinite_constant(value: str) -> None:
    raise BindingError(f"non-finite JSON number is not permitted: {value}")


def load_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        document = json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BindingError(f"invalid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise BindingError("acceptance document must be a JSON object")
    return document, digest


def exact_keys(value: dict[str, Any], expected: set[str]) -> bool:
    return set(value) == expected


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def valid_uuid(value: Any) -> bool:
    return isinstance(value, str) and UUID_PATTERN.fullmatch(value) is not None


def valid_input_name(value: Any) -> bool:
    return isinstance(value, str) and INPUT_NAME_PATTERN.fullmatch(value) is not None


def valid_token(value: Any) -> bool:
    return isinstance(value, str) and TOKEN_PATTERN.fullmatch(value) is not None


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return parsed


def valid_typed_value(value_type: str, value: Any) -> bool:
    if value_type == "STRING":
        return isinstance(value, str)
    if value_type == "INTEGER":
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "BOOLEAN":
        return isinstance(value, bool)
    if value_type == "STRING_SET":
        return (
            isinstance(value, list)
            and all(isinstance(item, str) for item in value)
            and len(value) == len(set(value))
            and value == sorted(value)
        )
    return False


def valid_required_input_spec(value: Any) -> bool:
    if not isinstance(value, dict) or not exact_keys(
        value,
        {"name", "value_type", "accepted_source_types", "max_age_seconds"},
    ):
        return False
    if not valid_input_name(value["name"]):
        return False
    if value["value_type"] not in VALUE_TYPES:
        return False
    source_types = value["accepted_source_types"]
    if (
        not isinstance(source_types, list)
        or not source_types
        or not all(valid_token(item) for item in source_types)
        or len(source_types) != len(set(source_types))
        or source_types != sorted(source_types)
    ):
        return False
    max_age = value["max_age_seconds"]
    return max_age is None or (isinstance(max_age, int) and not isinstance(max_age, bool) and max_age >= 0)


def valid_contract(value: Any, decision_kinds: set[str]) -> bool:
    if not isinstance(value, dict) or not exact_keys(
        value,
        {"contract_id", "decision_kind", "required_inputs"},
    ):
        return False
    if not valid_uuid(value["contract_id"]):
        return False
    if value["decision_kind"] not in decision_kinds:
        return False
    required_inputs = value["required_inputs"]
    if not isinstance(required_inputs, list) or not required_inputs:
        return False
    if not all(valid_required_input_spec(item) for item in required_inputs):
        return False
    names = [item["name"] for item in required_inputs]
    return len(names) == len(set(names)) and names == sorted(names)


def valid_input_observation(value: Any) -> bool:
    if not isinstance(value, dict) or not exact_keys(
        value,
        {
            "name",
            "state",
            "source_type",
            "source_ref",
            "source_version",
            "observed_at",
            "value_type",
            "value",
            "value_sha256",
        },
    ):
        return False
    if not valid_input_name(value["name"]):
        return False
    if value["state"] not in INPUT_STATES:
        return False
    if not valid_token(value["source_type"]):
        return False
    if not isinstance(value["source_ref"], str) or not value["source_ref"]:
        return False
    if not isinstance(value["source_version"], str) or not value["source_version"]:
        return False
    if parse_timestamp(value["observed_at"]) is None:
        return False
    if value["value_type"] not in VALUE_TYPES:
        return False
    if not valid_sha256(value["value_sha256"]):
        return False
    if value["state"] == "UNKNOWN":
        return value["value"] is None and value["value_sha256"] == sha256_json(None)
    return valid_typed_value(value["value_type"], value["value"]) and value["value_sha256"] == sha256_json(value["value"])


def valid_snapshot(value: Any) -> bool:
    if not isinstance(value, dict) or not exact_keys(value, {"snapshot_id", "inputs"}):
        return False
    if not valid_uuid(value["snapshot_id"]):
        return False
    inputs = value["inputs"]
    if not isinstance(inputs, list) or not inputs:
        return False
    if not all(valid_input_observation(item) for item in inputs):
        return False
    names = [item["name"] for item in inputs]
    return len(names) == len(set(names)) and names == sorted(names)


def valid_evaluation(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and exact_keys(value, {"evaluated_at", "contract_sha256", "input_snapshot_sha256"})
        and parse_timestamp(value["evaluated_at"]) is not None
        and valid_sha256(value["contract_sha256"])
        and valid_sha256(value["input_snapshot_sha256"])
    )


def inputs_bound(value: dict[str, Any], request_schema: dict[str, Any], decision_kinds: set[str]) -> bool:
    if not exact_keys(value, {"control_request", "contract", "input_snapshot", "evaluation"}):
        return False

    request = value["control_request"]
    contract = value["contract"]
    snapshot = value["input_snapshot"]
    evaluation = value["evaluation"]

    if not control_request.instance_is_valid(request, request_schema, request_schema):
        return False
    if not valid_contract(contract, decision_kinds):
        return False
    if not valid_snapshot(snapshot):
        return False
    if not valid_evaluation(evaluation):
        return False

    if request["contract_id"] != contract["contract_id"]:
        return False
    if request["decision_kind"] != contract["decision_kind"]:
        return False
    if evaluation["contract_sha256"] != sha256_json(contract):
        return False
    if evaluation["input_snapshot_sha256"] != sha256_json(snapshot):
        return False

    specs = {item["name"]: item for item in contract["required_inputs"]}
    observations = {item["name"]: item for item in snapshot["inputs"]}
    if set(specs) != set(observations):
        return False

    evaluated_at = parse_timestamp(evaluation["evaluated_at"])
    if evaluated_at is None:
        return False

    for name, spec in specs.items():
        observation = observations[name]
        if observation["state"] != "KNOWN":
            return False
        if observation["value_type"] != spec["value_type"]:
            return False
        if observation["source_type"] not in spec["accepted_source_types"]:
            return False
        observed_at = parse_timestamp(observation["observed_at"])
        if observed_at is None or observed_at > evaluated_at:
            return False
        max_age = spec["max_age_seconds"]
        if max_age is not None:
            age_seconds = int((evaluated_at - observed_at).total_seconds())
            if age_seconds > max_age:
                return False

    return True


def rebind(value: dict[str, Any]) -> None:
    for observation in value["input_snapshot"]["inputs"]:
        observation["value_sha256"] = sha256_json(observation["value"])
    value["evaluation"]["contract_sha256"] = sha256_json(value["contract"])
    value["evaluation"]["input_snapshot_sha256"] = sha256_json(value["input_snapshot"])


def find_named(items: list[dict[str, Any]], name: str, location: str) -> dict[str, Any]:
    matches = [item for item in items if item.get("name") == name]
    if len(matches) != 1:
        raise BindingError(f"{location}: expected exactly one item named {name!r}")
    return matches[0]


def apply_mutation(value: dict[str, Any], mutation: dict[str, Any]) -> None:
    if not isinstance(mutation, dict) or "op" not in mutation:
        raise BindingError("mutation must be an object with op")
    op = mutation["op"]

    if op == "SET_DECISION_KIND":
        if not exact_keys(mutation, {"op", "value"}):
            raise BindingError("SET_DECISION_KIND requires exactly op,value")
        value["control_request"]["decision_kind"] = copy.deepcopy(mutation["value"])
        value["contract"]["decision_kind"] = copy.deepcopy(mutation["value"])
        return

    if op == "ADD_INPUT":
        if not exact_keys(mutation, {"op", "input"}):
            raise BindingError("ADD_INPUT requires exactly op,input")
        value["input_snapshot"]["inputs"].append(copy.deepcopy(mutation["input"]))
        value["input_snapshot"]["inputs"].sort(key=lambda item: str(item.get("name", "")))
        return

    if op == "REMOVE_INPUT":
        if not exact_keys(mutation, {"op", "name"}) or not isinstance(mutation["name"], str):
            raise BindingError("REMOVE_INPUT requires exactly op,name")
        before = len(value["input_snapshot"]["inputs"])
        value["input_snapshot"]["inputs"] = [
            item for item in value["input_snapshot"]["inputs"] if item.get("name") != mutation["name"]
        ]
        if len(value["input_snapshot"]["inputs"]) != before - 1:
            raise BindingError(f"REMOVE_INPUT did not remove exactly one input: {mutation['name']}")
        return

    if op == "SET_INPUT_FIELD":
        if not exact_keys(mutation, {"op", "name", "field", "value"}):
            raise BindingError("SET_INPUT_FIELD requires exactly op,name,field,value")
        target = find_named(value["input_snapshot"]["inputs"], mutation["name"], "input_snapshot.inputs")
        if mutation["field"] not in target:
            raise BindingError(f"unknown input field: {mutation['field']}")
        target[mutation["field"]] = copy.deepcopy(mutation["value"])
        return

    if op == "SET_REQUIRED_INPUT_FIELD":
        if not exact_keys(mutation, {"op", "name", "field", "value"}):
            raise BindingError("SET_REQUIRED_INPUT_FIELD requires exactly op,name,field,value")
        target = find_named(value["contract"]["required_inputs"], mutation["name"], "contract.required_inputs")
        if mutation["field"] not in target:
            raise BindingError(f"unknown required-input field: {mutation['field']}")
        target[mutation["field"]] = copy.deepcopy(mutation["value"])
        return

    if op == "SET_REQUEST_FIELD":
        if not exact_keys(mutation, {"op", "field", "value"}):
            raise BindingError("SET_REQUEST_FIELD requires exactly op,field,value")
        if mutation["field"] not in value["control_request"]:
            raise BindingError(f"unknown control_request field: {mutation['field']}")
        value["control_request"][mutation["field"]] = copy.deepcopy(mutation["value"])
        return

    if op == "SET_EVALUATION_FIELD":
        if not exact_keys(mutation, {"op", "field", "value"}):
            raise BindingError("SET_EVALUATION_FIELD requires exactly op,field,value")
        if mutation["field"] not in value["evaluation"]:
            raise BindingError(f"unknown evaluation field: {mutation['field']}")
        value["evaluation"][mutation["field"]] = copy.deepcopy(mutation["value"])
        return

    raise BindingError(f"unsupported mutation op: {op!r}")


def validate_acceptance_document(document: dict[str, Any], request_schema: dict[str, Any], decision_kinds: set[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not exact_keys(document, {"contract_id", "purpose", "fixture", "acceptance_cases"}):
        raise BindingError("acceptance document has unsupported or missing top-level keys")
    if document["contract_id"] != "semantic_firewall.control_input_binding":
        raise BindingError("unexpected contract_id")
    if not isinstance(document["purpose"], str) or not document["purpose"].strip():
        raise BindingError("purpose must be a non-empty string")
    fixture = document["fixture"]
    if not isinstance(fixture, dict) or not inputs_bound(fixture, request_schema, decision_kinds):
        raise BindingError("fixture must itself be INPUTS_BOUND")

    cases = document["acceptance_cases"]
    if not isinstance(cases, list) or not cases:
        raise BindingError("acceptance_cases must be a non-empty array")
    seen: set[str] = set()
    bound_kinds: set[str] = set()
    has_unbound = False
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or not exact_keys(case, {"case_id", "mutations", "rebind", "expected"}):
            raise BindingError(f"acceptance case {index} has invalid shape")
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not case_id:
            raise BindingError(f"acceptance case {index} has invalid case_id")
        if case_id in seen:
            raise BindingError(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        if not isinstance(case["mutations"], list):
            raise BindingError(f"{case_id}: mutations must be an array")
        if not isinstance(case["rebind"], bool):
            raise BindingError(f"{case_id}: rebind must be boolean")
        if case["expected"] not in EXPECTED_OUTCOMES:
            raise BindingError(f"{case_id}: unsupported expected outcome {case['expected']!r}")

        candidate = copy.deepcopy(fixture)
        for mutation in case["mutations"]:
            apply_mutation(candidate, mutation)
        if case["rebind"]:
            rebind(candidate)
        if case["expected"] == "INPUTS_BOUND":
            kind = candidate.get("control_request", {}).get("decision_kind")
            if isinstance(kind, str) and kind in decision_kinds:
                bound_kinds.add(kind)
        else:
            has_unbound = True

    missing = decision_kinds - bound_kinds
    if missing:
        raise BindingError(f"missing INPUTS_BOUND coverage for decision kinds: {sorted(missing)}")
    if not has_unbound:
        raise BindingError("at least one INPUTS_UNBOUND acceptance case is required")
    return fixture, cases


def main() -> int:
    try:
        control_document, control_sha256 = control_request.load_contract(control_request.CONTRACT_PATH)
        request_schema, _ = control_request.validate_contract_document(control_document)
        decision_ref = request_schema["properties"]["decision_kind"]["$ref"]
        decision_schema = control_request.resolve_ref(request_schema, decision_ref)
        decision_kinds = set(decision_schema["enum"])
        document, acceptance_sha256 = load_json(ACCEPTANCE_PATH)
        fixture, cases = validate_acceptance_document(document, request_schema, decision_kinds)
    except (OSError, KeyError, TypeError, control_request.ContractError, BindingError) as exc:
        print(f"CONTRACT_ERROR: {exc}", file=sys.stderr)
        return 2

    failures = 0
    for case in cases:
        candidate = copy.deepcopy(fixture)
        try:
            for mutation in case["mutations"]:
                apply_mutation(candidate, mutation)
            if case["rebind"]:
                rebind(candidate)
            actual_bound = inputs_bound(candidate, request_schema, decision_kinds)
        except (KeyError, TypeError, BindingError) as exc:
            print(f"CONTRACT_ERROR: {case['case_id']}: {exc}", file=sys.stderr)
            return 2
        expected_bound = EXPECTED_OUTCOMES[case["expected"]]
        status = "PASS" if actual_bound == expected_bound else "FAIL"
        if status == "FAIL":
            failures += 1
        actual = "INPUTS_BOUND" if actual_bound else "INPUTS_UNBOUND"
        print(f"{status} {case['case_id']} expected={case['expected']} actual={actual}")

    result = "PASS" if failures == 0 else "FAIL"
    print(json.dumps({
        "contract_id": document["contract_id"],
        "control_request_artifact_sha256": control_sha256,
        "acceptance_artifact_sha256": acceptance_sha256,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cases_total": len(cases),
        "cases_failed": failures,
        "result": result,
    }, sort_keys=True, separators=(",", ":")))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
