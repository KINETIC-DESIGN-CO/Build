#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EVALUATOR_ID = "life-selected-operation-execution-v1"
RUNTIME_CONTROL_AUTHORITY = "NONE"

ROUTE_CLASSES = [
    "CURRENT_CONNECTED_ACTION_SURFACE",
    "DYNAMIC_TOOL_DISCOVERY",
    "INSTALLED_PLUGIN_DIRECTORY",
    "AUTHORIZED_PROVIDER_NATIVE_OR_REPOSITORY_AUTOMATION",
]

REQUIRED_FIELDS = {
    "selected_operation_state",
    "target_state",
    "authorization_state",
    "machine_route_state",
    "attempted_route_classes",
    "available_route_class",
    "app_permission_state",
    "safety_state",
    "resource_state",
    "cost_state",
    "effect_reconciliation_state",
}

ENUMS = {
    "selected_operation_state": {"NONE", "SELECTED"},
    "target_state": {"EXACT", "UNRESOLVED"},
    "authorization_state": {"AUTHORIZED", "NOT_AUTHORIZED"},
    "machine_route_state": {
        "NOT_RUN",
        "ACTION_AVAILABLE",
        "NO_MACHINE_ROUTE_VERIFIED",
    },
    "app_permission_state": {"AUTHORIZED", "NOT_AUTHORIZED", "NOT_APPLICABLE"},
    "safety_state": {"PASS", "BLOCKED"},
    "resource_state": {"AVAILABLE", "BLOCKED"},
    "cost_state": {
        "NO_NEW_COMMITMENT",
        "AUTHORIZED_COMMITMENT",
        "UNAUTHORIZED_COMMITMENT",
    },
    "effect_reconciliation_state": {"CLEAR", "REQUIRED"},
}

DISPOSITIONS = [
    "NO_SELECTED_OPERATION",
    "EFFECT_RECONCILIATION_REQUIRED",
    "TARGET_OR_OPERATION_UNRESOLVED",
    "DISCOVER_MACHINE_ROUTE",
    "BLOCKED_AUTHORIZATION",
    "BLOCKED_APP_PERMISSION",
    "BLOCKED_SAFETY",
    "BLOCKED_RESOURCE",
    "BLOCKED_COST",
    "USER_ACTION_REQUIRED_NO_MACHINE_ROUTE",
    "EXECUTE_NOW",
]


class ExecutionDispositionError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ExecutionDispositionError(message)


def validate_contract() -> None:
    if len(ROUTE_CLASSES) != len(set(ROUTE_CLASSES)):
        fail("route classes must be unique")
    if len(DISPOSITIONS) != len(set(DISPOSITIONS)):
        fail("dispositions must be unique")
    if "REDUNDANT_CONFIRMATION" in DISPOSITIONS or "ASK_FOR_CONFIRMATION" in DISPOSITIONS:
        fail("redundant confirmation disposition is forbidden")


def validate_evidence(evidence: object) -> dict:
    if not isinstance(evidence, dict) or set(evidence) != REQUIRED_FIELDS:
        fail("evidence keys mismatch")

    for field, allowed in ENUMS.items():
        if evidence[field] not in allowed:
            fail(f"{field} invalid")

    attempted = evidence["attempted_route_classes"]
    if not isinstance(attempted, list) or any(item not in ROUTE_CLASSES for item in attempted):
        fail("attempted_route_classes invalid")
    if len(attempted) != len(set(attempted)):
        fail("attempted_route_classes must be unique")

    available = evidence["available_route_class"]
    if available is not None and available not in ROUTE_CLASSES:
        fail("available_route_class invalid")

    route_state = evidence["machine_route_state"]
    if route_state == "ACTION_AVAILABLE":
        if available is None or available not in attempted:
            fail("ACTION_AVAILABLE requires an attempted available_route_class")
    elif available is not None:
        fail("available_route_class requires ACTION_AVAILABLE")

    if route_state == "NO_MACHINE_ROUTE_VERIFIED" and set(attempted) != set(ROUTE_CLASSES):
        fail("NO_MACHINE_ROUTE_VERIFIED requires every route class attempted")

    return evidence


def evaluate(evidence: object) -> dict:
    validate_contract()
    value = validate_evidence(evidence)
    attempted = set(value["attempted_route_classes"])
    all_routes_attempted = attempted == set(ROUTE_CLASSES)

    if value["selected_operation_state"] == "NONE":
        disposition = "NO_SELECTED_OPERATION"
    elif value["effect_reconciliation_state"] == "REQUIRED":
        disposition = "EFFECT_RECONCILIATION_REQUIRED"
    elif value["target_state"] == "UNRESOLVED":
        disposition = "TARGET_OR_OPERATION_UNRESOLVED"
    elif value["machine_route_state"] == "NOT_RUN":
        disposition = "DISCOVER_MACHINE_ROUTE"
    elif value["authorization_state"] == "NOT_AUTHORIZED":
        disposition = "BLOCKED_AUTHORIZATION"
    elif value["safety_state"] == "BLOCKED":
        disposition = "BLOCKED_SAFETY"
    elif value["resource_state"] == "BLOCKED":
        disposition = "BLOCKED_RESOURCE"
    elif value["cost_state"] == "UNAUTHORIZED_COMMITMENT":
        disposition = "BLOCKED_COST"
    elif value["machine_route_state"] == "ACTION_AVAILABLE" and value["app_permission_state"] == "NOT_AUTHORIZED":
        disposition = "BLOCKED_APP_PERMISSION" if all_routes_attempted else "DISCOVER_MACHINE_ROUTE"
    elif value["machine_route_state"] == "NO_MACHINE_ROUTE_VERIFIED":
        disposition = "USER_ACTION_REQUIRED_NO_MACHINE_ROUTE"
    elif value["machine_route_state"] == "ACTION_AVAILABLE":
        disposition = "EXECUTE_NOW"
    else:
        fail("unhandled execution evidence")

    return {
        "evaluator_id": EVALUATOR_ID,
        "disposition": disposition,
        "execute_now": disposition == "EXECUTE_NOW",
        "manual_handoff_allowed": disposition == "USER_ACTION_REQUIRED_NO_MACHINE_ROUTE",
        "remaining_route_classes": [
            route for route in ROUTE_CLASSES if route not in attempted
        ] if disposition == "DISCOVER_MACHINE_ROUTE" else [],
        "runtime_control_authority": RUNTIME_CONTROL_AUTHORITY,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-contract", action="store_true")
    mode.add_argument("--evaluate")
    args = parser.parse_args()
    try:
        validate_contract()
        if args.evaluate:
            evidence = json.loads(Path(args.evaluate).read_text(encoding="utf-8"))
            print(json.dumps(evaluate(evidence), indent=2))
        else:
            print("SELECTED_OPERATION_EXECUTION_VALID")
        return 0
    except (ExecutionDispositionError, OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
