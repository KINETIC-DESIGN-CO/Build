#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "root-cause-repair-policy.json"
POLICY_SCHEMA_PATH = ROOT / "governance" / "schema" / "root-cause-repair-policy.schema.json"
REGISTRY_PATH = ROOT / "governance" / "root-cause-repairs.json"
REGISTRY_SCHEMA_PATH = ROOT / "governance" / "schema" / "root-cause-repairs.schema.json"

POLICY_KEYS = {
    "schema_version",
    "policy_id",
    "runtime_control_authority",
    "scope",
    "problem_intake_relationship",
    "trigger",
    "states",
    "required_trace_fields",
    "history_trace_rule",
    "patch_only_rule",
    "test_isolation_rule",
    "derived_state_rule",
    "dependency_rule",
    "detector_change_rule",
    "completion_requires",
    "forbidden_terminal_shortcuts",
    "durability_rule",
    "terminal_rule",
}
REPAIR_KEYS = {
    "repair_id",
    "root_goal_ref",
    "state",
    "failure_refs",
    "violated_invariant_ids",
    "origin_commit_refs",
    "history_evidence_refs",
    "root_cause_classes",
    "affected_surfaces",
    "dependent_validator_surfaces",
    "selected_dispositions",
    "recurrence_test_ids",
    "verification_state",
}
STATES = [
    "FAILURE_OBSERVED",
    "INVARIANT_IDENTIFIED",
    "ORIGIN_TRACED",
    "DEPENDENCIES_ENUMERATED",
    "ROOT_MECHANISM_SELECTED",
    "RECURRENCE_FALSIFICATION_DEFINED",
    "REPAIRING",
    "VERIFYING",
    "VERIFIED_FIXED",
    "BLOCKED",
]
TRACE_FIELDS = [
    "repair_id",
    "root_goal_ref",
    "failure_refs",
    "violated_invariant_ids",
    "origin_commit_refs",
    "root_cause_classes",
    "affected_surfaces",
    "dependent_validator_surfaces",
    "selected_dispositions",
    "recurrence_test_ids",
    "verification_state",
]
COMPLETION = [
    "ROOT_CAUSE_RECORD_SCHEMA_VALID",
    "EVERY_FAILURE_HAS_EXACT_VIOLATED_INVARIANT_ID",
    "EVERY_FAILURE_HAS_ORIGIN_COMMIT_OR_BLOCKED_UNKNOWN_ORIGIN",
    "EVERY_AFFECTED_SURFACE_IS_ENUMERATED",
    "EVERY_DEPENDENT_VALIDATOR_SURFACE_IS_ENUMERATED",
    "EVERY_SELECTED_DISPOSITION_IS_KEEP_REPLACE_MODIFY_COMBINE_OR_REMOVE",
    "RECURRENCE_FALSIFICATION_PASSES",
    "ORIGINAL_FAILURE_DETECTOR_RERUN_PASSES",
    "FULL_REQUIRED_REPOSITORY_VALIDATION_PASSES",
    "PROTECTED_INTEGRATION_AND_REQUIRED_LIVE_READBACK_PASS",
]
SHORTCUTS = [
    "PATCH_EXPECTED_LITERAL_ONLY",
    "REFRESH_DERIVED_HASH_ONLY",
    "DISABLE_OR_WEAKEN_DETECTOR_WITHOUT_INDEPENDENT_FALSIFICATION",
    "MARK_FIXED_FROM_PROSE_REVIEW_OR_MODEL_JUDGMENT",
    "SKIP_DEPENDENT_VALIDATOR_ENUMERATION",
]


class RootCauseError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise RootCauseError(message)


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def nonempty_unique_strings(value, name: str):
    if not isinstance(value, list) or not value:
        fail(f"{name} must be a nonempty array")
    if any(not isinstance(item, str) or not item for item in value):
        fail(f"{name} must contain nonempty strings")
    if len(value) != len(set(value)):
        fail(f"{name} must contain unique values")
    return value


def validate_schema_envelope(schema, required_keys, title):
    if not isinstance(schema, dict):
        fail(f"{title} schema must be object")
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        fail(f"{title} schema draft mismatch")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        fail(f"{title} schema root closure mismatch")
    if set(schema.get("required", [])) != required_keys:
        fail(f"{title} schema required keys mismatch")
    if set(schema.get("properties", {})) != required_keys:
        fail(f"{title} schema properties mismatch")


def validate_policy(policy, schema):
    if not isinstance(policy, dict) or set(policy) != POLICY_KEYS:
        fail("root-cause policy keys mismatch")
    exact = {
        "schema_version": 1,
        "policy_id": "life-engineering-root-cause-repair-v1",
        "runtime_control_authority": "NONE",
        "scope": "ENGINEERING_REPAIR_PROCEDURE_AFTER_WORK_SELECTION",
        "trigger": "A_DETERMINISTIC_FAILURE_OR_VERIFIED_DEFECT_IS_SELECTED_FOR_REPAIR",
        "states": STATES,
        "required_trace_fields": TRACE_FIELDS,
        "completion_requires": COMPLETION,
        "forbidden_terminal_shortcuts": SHORTCUTS,
        "terminal_rule": "VERIFIED_FIXED_IS_ALLOWED_ONLY_WHEN_EVERY_COMPLETION_REQUIRES_ENTRY_IS_MACHINE_VERIFIED",
    }
    for key, value in exact.items():
        if policy.get(key) != value:
            fail(f"root-cause policy field mismatch: {key}")
    for key in [
        "problem_intake_relationship",
        "history_trace_rule",
        "patch_only_rule",
        "test_isolation_rule",
        "derived_state_rule",
        "dependency_rule",
        "detector_change_rule",
        "durability_rule",
    ]:
        if not isinstance(policy.get(key), str) or not policy[key]:
            fail(f"root-cause policy {key} missing")
    if "ONLY_EDITS_A_FAILING_EXPECTATION_DETECTOR_OR_STORED_DERIVED_VALUE" not in policy["patch_only_rule"]:
        fail("patch-only prevention missing")
    if "CONTROLLED_TEST_FIXTURES_OR_AN_INDEPENDENT_DERIVATION" not in policy["test_isolation_rule"]:
        fail("test isolation invariant missing")
    if "RUNTIME_PROJECTION_DETERMINISTIC_GENERATION_OR_EXECUTABLE_CURRENT_SOURCE_COMPATIBILITY_VALIDATION" not in policy["derived_state_rule"]:
        fail("derived-state repair invariant missing")
    validate_schema_envelope(schema, POLICY_KEYS, "root-cause policy")


def validate_registry(registry, schema):
    root_keys = {"schema_version", "registry_id", "runtime_control_authority", "repairs"}
    if not isinstance(registry, dict) or set(registry) != root_keys:
        fail("root-cause registry keys mismatch")
    if registry.get("schema_version") != 1 or registry.get("registry_id") != "life-engineering-root-cause-repairs-v1":
        fail("root-cause registry identity mismatch")
    if registry.get("runtime_control_authority") != "NONE":
        fail("root-cause registry runtime authority mismatch")
    repairs = registry.get("repairs")
    if not isinstance(repairs, list) or not repairs:
        fail("root-cause registry must contain repairs")
    seen = set()
    for repair in repairs:
        if not isinstance(repair, dict) or set(repair) != REPAIR_KEYS:
            fail("root-cause repair keys mismatch")
        repair_id = repair["repair_id"]
        if re.fullmatch(r"RCA-[0-9]{4}", str(repair_id)) is None or repair_id in seen:
            fail("root-cause repair id invalid or duplicate")
        seen.add(repair_id)
        if repair["state"] not in STATES:
            fail(f"{repair_id} state invalid")
        for key in [
            "failure_refs",
            "violated_invariant_ids",
            "origin_commit_refs",
            "history_evidence_refs",
            "root_cause_classes",
            "affected_surfaces",
            "dependent_validator_surfaces",
            "selected_dispositions",
            "recurrence_test_ids",
        ]:
            nonempty_unique_strings(repair[key], f"{repair_id}.{key}")
        if any(re.fullmatch(r"[0-9a-f]{40}|UNKNOWN", ref) is None for ref in repair["origin_commit_refs"]):
            fail(f"{repair_id} origin commit ref invalid")
        if any(re.fullmatch(r"[0-9a-f]{40}", ref) is None for ref in repair["history_evidence_refs"]):
            fail(f"{repair_id} history commit ref invalid")
        if "UNKNOWN" in repair["origin_commit_refs"] and repair["state"] != "BLOCKED":
            fail(f"{repair_id} unknown origin must be BLOCKED")
        allowed_prefixes = ("KEEP_", "REPLACE_", "MODIFY_", "COMBINE_", "REMOVE_")
        if any(not disposition.startswith(allowed_prefixes) for disposition in repair["selected_dispositions"]):
            fail(f"{repair_id} disposition invalid")
        if repair["state"] == "VERIFIED_FIXED" and repair["verification_state"] != "VERIFIED_REQUIRED_CI_PROTECTED_INTEGRATION_AND_LIVE_READBACK":
            fail(f"{repair_id} cannot be VERIFIED_FIXED without final verification state")
        if not isinstance(repair["root_goal_ref"], str) or not repair["root_goal_ref"]:
            fail(f"{repair_id} root goal ref missing")
        if not isinstance(repair["verification_state"], str) or not repair["verification_state"]:
            fail(f"{repair_id} verification state missing")
    validate_schema_envelope(schema, root_keys, "root-cause registry")


def validate():
    policy = load(POLICY_PATH)
    policy_schema = load(POLICY_SCHEMA_PATH)
    registry = load(REGISTRY_PATH)
    registry_schema = load(REGISTRY_SCHEMA_PATH)
    validate_policy(policy, policy_schema)
    validate_registry(registry, registry_schema)
    return True


if __name__ == "__main__":
    try:
        validate()
    except RootCauseError as exc:
        print(f"ROOT_CAUSE_REPAIR_INVALID: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print("ROOT_CAUSE_REPAIR_VALID")
