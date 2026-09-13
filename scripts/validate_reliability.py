#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import validate_continuity as vc

ROOT = Path(__file__).resolve().parents[1]
REL = ROOT / "reliability"
ERRORS: list[str] = []

SOURCE_SCHEMA_PAIRS = {
    "spec": (REL / "spec.json", REL / "schema/spec.schema.json"),
    "invariants": (REL / "invariants.json", REL / "schema/invariants.schema.json"),
    "operation_catalog": (REL / "operation-catalog.json", REL / "schema/operation-catalog.schema.json"),
    "postconditions": (REL / "postconditions.json", REL / "schema/postconditions.schema.json"),
    "recovery_policy": (REL / "recovery-policy.json", REL / "schema/recovery-policy.schema.json"),
    "compatibility_map": (REL / "compatibility-map.json", REL / "schema/compatibility-map.schema.json"),
}

FAIL_CLOSED_DISPOSITIONS = {"QUARANTINE", "ESCALATE", "ABORT"}
CANONICAL_GOAL_OWNER_PATH = "governance/goal-registry.json"


def fail(code: str, message: str) -> None:
    ERRORS.append(f"{code}: {message}")


def unique_by(rows, key, label):
    values = [row.get(key) for row in rows if isinstance(row, dict)]
    if len(values) != len(set(values)):
        fail("R002_DUPLICATE_ID", f"{label} {key} values must be unique")
    return {row.get(key): row for row in rows if isinstance(row, dict) and row.get(key) is not None}


def load_contracts():
    vc.ERRORS.clear()
    loaded = {}
    for label, (source_path, schema_path) in SOURCE_SCHEMA_PAIRS.items():
        source = vc.load_json(source_path)
        schema = vc.load_json(schema_path)
        loaded[label] = source
        if schema is not None:
            vc.validate_schema_definition(schema, str(schema_path.relative_to(ROOT)))
        if source is not None and schema is not None:
            vc.validate_instance_against_schema(
                source,
                schema,
                str(source_path.relative_to(ROOT)),
            )
    if vc.ERRORS:
        ERRORS.extend(f"R001_SCHEMA: {entry}" for entry in vc.ERRORS)
    return loaded


def value_matches(actual, allowed):
    return "*" in allowed or actual in allowed


def evaluate_recovery(policy, context):
    for rule in sorted(policy["rules"], key=lambda row: row["priority"]):
        match = rule["match"]
        if all(value_matches(context[key], match[key]) for key in policy["input_domains"]):
            return rule["disposition"], rule["rule_id"]
    return None, None


def validate_authority_none(value, path="$"):
    if isinstance(value, dict):
        if "runtime_control_authority" in value and value["runtime_control_authority"] != "NONE":
            fail("R003_AUTHORITY", f"{path}.runtime_control_authority must be NONE")
        for key, child in value.items():
            validate_authority_none(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_authority_none(child, f"{path}[{index}]")


def validate_source_links(spec):
    for key, rel in spec["source_artifacts"].items():
        expected = SOURCE_SCHEMA_PAIRS[key][0]
        actual = ROOT / rel
        if actual != expected:
            fail("R004_SOURCE_LINK", f"spec.source_artifacts.{key} must be {expected.relative_to(ROOT)}")
        if not actual.is_file():
            fail("R004_SOURCE_LINK", f"source artifact missing: {rel}")

    links = spec["cross_links"]
    for field in (
        "root_cause_repair_policy",
        "problem_intake_policy",
        "work_selection_policy",
        "checkpoint_policy",
        "issue_consolidation_policy",
        "user_observation_policy",
        "user_observation_ledger",
    ):
        rel = links[field]
        if not (ROOT / rel).is_file():
            fail("R004_SOURCE_LINK", f"cross-link missing: {rel}")

    if links["semantic_firewall_link_state"] == "SOURCE_IMPORTED_ACTIVATION_PENDING":
        rel = links["semantic_firewall_contract_path"]
        if rel != "contracts/semantic-firewall" or not (ROOT / rel).is_dir():
            fail("R004_SOURCE_LINK", "imported Semantic Firewall state requires contracts/semantic-firewall directory")
    if links["semantic_firewall_link_state"] == "ACTIVE":
        fail("R004_SOURCE_LINK", "Phase 0 cannot declare Build-native Semantic Firewall ACTIVE")

    goal_state = links["goal_root_identity_link_state"]
    goal_owner = links["goal_root_identity_owner_path"]
    if goal_state == "PENDING_IMPLEMENTATION" and goal_owner is not None:
        fail("R004_SOURCE_LINK", "pending goal identity must not claim an active owner path")
    if goal_state == "ACTIVE":
        if goal_owner != CANONICAL_GOAL_OWNER_PATH:
            fail("R004_SOURCE_LINK", f"active goal identity owner must be {CANONICAL_GOAL_OWNER_PATH}")
        elif not (ROOT / goal_owner).is_file():
            fail("R004_SOURCE_LINK", f"active goal identity owner missing: {goal_owner}")


def validate_postconditions(spec, catalog):
    by_id = unique_by(catalog["postconditions"], "postcondition_id", "postconditions")
    for post_id, post in by_id.items():
        if post["verification_dimension"] not in spec["verification_dimensions"]:
            fail("R005_POSTCONDITION", f"{post_id} uses unknown verification dimension")
        if post["required_evidence_role"] not in spec["evidence_roles"]:
            fail("R005_POSTCONDITION", f"{post_id} uses unknown evidence role")
    return by_id


def validate_operations(spec, catalog, post_by_id):
    by_id = unique_by(catalog["operation_contracts"], "operation_contract_id", "operation contracts")
    for op_id, op in by_id.items():
        missing = sorted(set(op["postcondition_ids"]) - set(post_by_id))
        if missing:
            fail("R006_OPERATION", f"{op_id} references missing postconditions {missing}")
        compensation = op["compensation_contract_id"]
        if compensation is not None and compensation not in by_id:
            fail("R006_OPERATION", f"{op_id} references missing compensation contract {compensation}")
        if compensation == op_id:
            fail("R006_OPERATION", f"{op_id} cannot compensate itself")
        if op["retry_budget"] == 0 and (op["retryable_attempt_result_states"] or op["retryable_effect_states"]):
            fail("R006_OPERATION", f"{op_id} retry budget 0 requires empty retryable state lists")
        if op["retry_budget"] > 0 and not op["retryable_attempt_result_states"]:
            fail("R006_OPERATION", f"{op_id} positive retry budget requires retryable attempt states")
        unknown_attempts = sorted(set(op["retryable_attempt_result_states"]) - set(spec["attempt_result_states"]))
        unknown_effects = sorted(set(op["retryable_effect_states"]) - set(spec["effect_states"]))
        if unknown_attempts or unknown_effects:
            fail("R006_OPERATION", f"{op_id} has retry states outside source contract")
        if op["effect_class"] == "STATE_CHANGING" and op["readback_mode"] == "READBACK_UNAVAILABLE":
            if op["retry_budget"] != 0 or op["fail_closed_disposition"] not in FAIL_CLOSED_DISPOSITIONS:
                fail("R006_OPERATION", f"{op_id} unreadable state change must have zero retries and fail closed")
        if op["idempotency_mode"] == "NONE" and "EFFECT_UNKNOWN" in op["retryable_effect_states"]:
            fail("R006_OPERATION", f"{op_id} non-idempotent operation cannot mark EFFECT_UNKNOWN retryable")
    return by_id


def validate_recovery(spec, policy):
    rule_by_id = unique_by(policy["rules"], "rule_id", "recovery rules")
    priorities = [rule["priority"] for rule in policy["rules"]]
    if priorities != sorted(priorities) or len(priorities) != len(set(priorities)):
        fail("R007_RECOVERY", "recovery rule priorities must be unique and ascending")

    domain_keys = set(policy["input_domains"])
    for rule_id, rule in rule_by_id.items():
        if set(rule["match"]) != domain_keys:
            fail("R007_RECOVERY", f"{rule_id} match keys must equal input domain keys")
        if rule["disposition"] not in spec["recovery_dispositions"]:
            fail("R007_RECOVERY", f"{rule_id} disposition is outside source contract")
        for key, values in rule["match"].items():
            if "*" in values and len(values) != 1:
                fail("R007_RECOVERY", f"{rule_id}.{key} cannot mix wildcard with concrete states")
            concrete = [value for value in values if value != "*"]
            unknown = sorted(set(concrete) - set(policy["input_domains"][key]))
            if unknown:
                fail("R007_RECOVERY", f"{rule_id}.{key} contains unknown states {unknown}")

    fallback = max(policy["rules"], key=lambda row: row["priority"])
    if fallback["rule_id"] != "RREC-9999" or fallback["disposition"] != "ABORT":
        fail("R007_RECOVERY", "highest-priority-number fallback must be RREC-9999 ABORT")
    if any(values != ["*"] for values in fallback["match"].values()):
        fail("R007_RECOVERY", "RREC-9999 must wildcard every input domain")

    expected_cases = [
        (
            "VERIFY_BEFORE_RETRY",
            {"attempt_result_state":"TIMEOUT","effect_state":"EFFECT_UNKNOWN","readback_mode":"AUTHORITATIVE_READBACK","idempotency_mode":"NONE","duplicate_effect_risk":"YES","retry_budget_state":"AVAILABLE","required_postconditions_state":"UNKNOWN","compensation_contract_state":"ABSENT","parent_restoration_state":"NOT_ELIGIBLE"},
            "VERIFY_EFFECT",
        ),
        (
            "UNREADABLE_NON_IDEMPOTENT_UNKNOWN_EFFECT",
            {"attempt_result_state":"TIMEOUT","effect_state":"EFFECT_UNKNOWN","readback_mode":"READBACK_UNAVAILABLE","idempotency_mode":"NONE","duplicate_effect_risk":"YES","retry_budget_state":"EXHAUSTED","required_postconditions_state":"UNKNOWN","compensation_contract_state":"ABSENT","parent_restoration_state":"NOT_ELIGIBLE"},
            "QUARANTINE",
        ),
        (
            "VERIFIED_NO_EFFECT_ALLOWS_BOUNDED_RETRY",
            {"attempt_result_state":"TIMEOUT","effect_state":"NO_EFFECT_VERIFIED","readback_mode":"AUTHORITATIVE_READBACK","idempotency_mode":"NONE","duplicate_effect_risk":"YES","retry_budget_state":"AVAILABLE","required_postconditions_state":"NOT_RUN","compensation_contract_state":"ABSENT","parent_restoration_state":"NOT_ELIGIBLE"},
            "RETRY",
        ),
        (
            "TRANSPORT_SUCCESS_DOES_NOT_OVERRIDE_FAILED_POSTCONDITION",
            {"attempt_result_state":"SUCCESS","effect_state":"EFFECT_VERIFIED","readback_mode":"AUTHORITATIVE_READBACK","idempotency_mode":"EXACT_KEY","duplicate_effect_risk":"YES","retry_budget_state":"AVAILABLE","required_postconditions_state":"FAIL","compensation_contract_state":"ABSENT","parent_restoration_state":"NOT_ELIGIBLE"},
            "QUARANTINE",
        ),
        (
            "PARENT_RESTORATION_PRECEDES_UNRELATED_WORK",
            {"attempt_result_state":"SUCCESS","effect_state":"EFFECT_VERIFIED","readback_mode":"AUTHORITATIVE_READBACK","idempotency_mode":"EXACT_KEY","duplicate_effect_risk":"YES","retry_budget_state":"AVAILABLE","required_postconditions_state":"PASS","compensation_contract_state":"ABSENT","parent_restoration_state":"ELIGIBLE"},
            "RESUME_PARENT",
        ),
        (
            "VERIFIED_EFFECT_WITHOUT_PARENT_IS_ACCEPTED",
            {"attempt_result_state":"SUCCESS","effect_state":"EFFECT_VERIFIED","readback_mode":"AUTHORITATIVE_READBACK","idempotency_mode":"EXACT_KEY","duplicate_effect_risk":"YES","retry_budget_state":"AVAILABLE","required_postconditions_state":"PASS","compensation_contract_state":"ABSENT","parent_restoration_state":"NOT_ELIGIBLE"},
            "ACCEPT_EFFECT",
        ),
    ]
    for label, context, expected in expected_cases:
        actual, rule_id = evaluate_recovery(policy, context)
        if actual != expected:
            fail("R008_FALSIFICATION", f"{label} expected {expected} but got {actual} via {rule_id}")


def validate_compatibility(spec, compatibility):
    mappings = compatibility["work_selection_interruption"]["mappings"]
    states = [row["source_state"] for row in mappings]
    if set(states) != set(spec["attempt_result_states"]) or len(states) != len(set(states)):
        fail("R009_COMPATIBILITY", "work-selection interruption mappings must cover each attempt state exactly once")
    user_obs = compatibility["user_observation"]
    if user_obs["reliability_source_class"] != "VINCE_PERSONAL_OBSERVATION_REF":
        fail("R009_COMPATIBILITY", "Vince observations must use canonical observation references")
    firewall = compatibility["semantic_firewall"]
    if firewall["state"] != spec["cross_links"]["semantic_firewall_link_state"]:
        fail("R009_COMPATIBILITY", "Semantic Firewall states must match across Reliability artifacts")
    if firewall["current_contract_path"] != spec["cross_links"]["semantic_firewall_contract_path"]:
        fail("R009_COMPATIBILITY", "Semantic Firewall paths must match across Reliability artifacts")

    goal = compatibility["goal_identity"]
    links = spec["cross_links"]
    if goal["state"] != links["goal_root_identity_link_state"]:
        fail("R009_COMPATIBILITY", "goal identity states must match across Reliability artifacts")
    if goal["current_owner_path"] != links["goal_root_identity_owner_path"]:
        fail("R009_COMPATIBILITY", "goal identity owner paths must match across Reliability artifacts")
    if goal["state"] == "PENDING_IMPLEMENTATION":
        if goal["relationship"] != "COMBINE_PENDING_GOAL_OWNER_IMPLEMENTATION" or goal["current_owner_path"] is not None:
            fail("R009_COMPATIBILITY", "pending goal identity must use the pending relationship with no owner path")
    elif goal["state"] == "ACTIVE":
        if goal["relationship"] != "COMBINE_CANONICAL_GOAL_OWNER":
            fail("R009_COMPATIBILITY", "active goal identity must combine with the canonical goal owner")
        if goal["current_owner_path"] != CANONICAL_GOAL_OWNER_PATH:
            fail("R009_COMPATIBILITY", f"active goal identity owner must be {CANONICAL_GOAL_OWNER_PATH}")
        elif not (ROOT / goal["current_owner_path"]).is_file():
            fail("R009_COMPATIBILITY", f"active goal identity owner missing: {goal['current_owner_path']}")


def validate_invariants(spec, catalog):
    by_id = unique_by(catalog["invariants"], "invariant_id", "invariants")
    required_ids = {f"RINV-{index:04d}" for index in range(1, 11)}
    if set(by_id) != required_ids:
        fail("R010_INVARIANT", "Phase 0 invariant catalog must contain exactly RINV-0001 through RINV-0010")
    for invariant_id, row in by_id.items():
        if row["verification_dimension"] not in spec["verification_dimensions"]:
            fail("R010_INVARIANT", f"{invariant_id} uses unknown verification dimension")


def main() -> int:
    contracts = load_contracts()
    if any(contracts.get(name) is None for name in SOURCE_SCHEMA_PAIRS):
        for error in ERRORS:
            print(error, file=sys.stderr)
        return 1

    spec = contracts["spec"]
    for value in contracts.values():
        validate_authority_none(value)
    validate_source_links(spec)
    post_by_id = validate_postconditions(spec, contracts["postconditions"])
    validate_operations(spec, contracts["operation_catalog"], post_by_id)
    validate_recovery(spec, contracts["recovery_policy"])
    validate_compatibility(spec, contracts["compatibility_map"])
    validate_invariants(spec, contracts["invariants"])

    if ERRORS:
        for error in ERRORS:
            print(error, file=sys.stderr)
        return 1
    print("RELIABILITY_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
