#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import validate_continuity as vc

ROOT = Path(__file__).resolve().parents[1]
SF = ROOT / "contracts" / "semantic-firewall-v1"
ERRORS: list[str] = []

SCHEMA_FILES = [
    "control-contract.schema.json",
    "control-receipt.schema.json",
    "control-request.schema.json",
    "effect-request.schema.json",
    "input-snapshot.schema.json",
    "reliability-verification.schema.json",
]

EXPECTED_DECISION_STATES = ["PASS", "FAIL", "NOT_RUN"]
EXPECTED_EVIDENCE_STATES = ["KNOWN", "UNKNOWN", "UNVERIFIED", "NOT_RUN"]


def fail(code: str, message: str) -> None:
    ERRORS.append(f"{code}: {message}")


def load_json(path: Path):
    vc.ERRORS.clear()
    value = vc.load_json(path)
    if vc.ERRORS:
        ERRORS.extend(f"SF001_JSON: {entry}" for entry in vc.ERRORS)
    return value


def validate_authority_none(value, path="$"):
    if isinstance(value, dict):
        if "runtime_control_authority" in value and value["runtime_control_authority"] != "NONE":
            fail("SF002_AUTHORITY", f"{path}.runtime_control_authority must be NONE")
        for key, child in value.items():
            validate_authority_none(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_authority_none(child, f"{path}[{index}]")


def load_evaluator():
    path = ROOT / "scripts" / "evaluate_semantic_firewall.py"
    spec = importlib.util.spec_from_file_location("life_semantic_firewall_eval", path)
    if spec is None or spec.loader is None:
        fail("SF003_EVALUATOR", "cannot load evaluator module")
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    spec = load_json(SF / "spec.json")
    placement = load_json(ROOT / "governance" / "placement-policy.json")
    reliability = load_json(ROOT / "reliability" / "spec.json")
    compatibility = load_json(ROOT / "reliability" / "compatibility-map.json")
    provenance = load_json(ROOT / "architecture" / "reference" / "semantic-firewall-import-provenance.json")

    for schema_name in SCHEMA_FILES:
        schema_path = SF / schema_name
        schema = load_json(schema_path)
        if schema is not None:
            vc.ERRORS.clear()
            vc.validate_schema_definition(schema, str(schema_path.relative_to(ROOT)))
            if vc.ERRORS:
                ERRORS.extend(f"SF004_SCHEMA: {entry}" for entry in vc.ERRORS)

    if any(value is None for value in (spec, placement, reliability, compatibility, provenance)):
        for error in ERRORS:
            print(error, file=sys.stderr)
        return 1

    validate_authority_none(spec)
    validate_authority_none(reliability)
    validate_authority_none(compatibility)
    validate_authority_none(provenance)

    if spec.get("subsystem_id") != "life-semantic-firewall-v1":
        fail("SF005_SPEC", "unexpected subsystem_id")
    if spec.get("activation_state") != "SOURCE_ONLY_NOT_RUNTIME_AUTHORITY":
        fail("SF005_SPEC", "source slice must remain SOURCE_ONLY_NOT_RUNTIME_AUTHORITY")
    if spec.get("decision_states") != EXPECTED_DECISION_STATES:
        fail("SF005_SPEC", "decision states must be PASS/FAIL/NOT_RUN")
    if spec.get("evidence_states") != EXPECTED_EVIDENCE_STATES:
        fail("SF005_SPEC", "evidence states must preserve KNOWN/UNKNOWN/UNVERIFIED/NOT_RUN")

    expected_kinds = placement.get("control_decision_kinds")
    if spec.get("control_decision_kinds") != expected_kinds:
        fail("SF006_KINDS", "Semantic Firewall decision kinds must exactly match placement-policy control kinds")

    required_invariants = {
        "SOURCE_EVALUATOR_CONTROL_AND_EFFECT_ELIGIBILITY_RESULTS_HAVE_ZERO_RUNTIME_CONTROL_AUTHORITY",
        "TRUSTED_RECEIPT_FIELDS_AND_SELF_HASH_ALONE_DO_NOT_ESTABLISH_TRUSTED_ISSUANCE_WITHOUT_AUTHORITATIVE_PERSISTENCE_READBACK",
    }
    if not required_invariants.issubset(set(spec.get("invariants", []))):
        fail("SF006_KINDS", "source-only trust-boundary invariants are missing")

    for rel in spec.get("schema_paths", []):
        if not (ROOT / rel).is_file():
            fail("SF007_SOURCE_LINK", f"schema path missing: {rel}")
    for field in ("evaluator_path", "validator_path", "test_path"):
        rel = spec.get(field)
        if not isinstance(rel, str) or not (ROOT / rel).is_file():
            fail("SF007_SOURCE_LINK", f"{field} missing: {rel}")

    legacy_path = ROOT / spec.get("imported_legacy_path", "")
    if not legacy_path.is_dir():
        fail("SF008_LEGACY", "byte-verified legacy Semantic Firewall directory is missing")
    if provenance.get("selected_source_commit") != "6cc602f2ac18599aa67c0352ce81fbd404dcb40f":
        fail("SF008_LEGACY", "legacy provenance must bind the selected control-input-binding source commit")
    phase_b_deps = set(provenance.get("phase_b_dependencies", []))
    if phase_b_deps != {
        "CR-SEMANTIC-FIREWALL-SOURCE-INTAKE:VERIFIED_COMPLETE",
        "CR-SCHEMA-ENFORCEMENT:VERIFIED_COMPLETE",
    }:
        fail("SF008_LEGACY", "Phase B dependency set must preserve verified source intake and schema enforcement")

    binding = spec.get("reliability_binding", {})
    expected_reliability = {
        "compatibility_path": "reliability/compatibility-map.json",
        "operation_catalog_path": "reliability/operation-catalog.json",
        "postconditions_path": "reliability/postconditions.json",
        "recovery_policy_path": "reliability/recovery-policy.json",
    }
    for key, expected in expected_reliability.items():
        if binding.get(key) != expected or not (ROOT / expected).is_file():
            fail("SF009_RELIABILITY", f"{key} must bind {expected}")

    sf_compat = compatibility.get("semantic_firewall", {})
    if sf_compat.get("state") not in {"SOURCE_IMPORTED_ACTIVATION_PENDING", "ACTIVE"}:
        fail("SF009_RELIABILITY", "unsupported Reliability Semantic Firewall link state")
    if sf_compat.get("state") == "ACTIVE":
        fail("SF009_RELIABILITY", "source-only Semantic Firewall v1 cannot make Reliability declare runtime activation")
    if "RELIABILITY" not in sf_compat.get("rule", ""):
        fail("SF009_RELIABILITY", "Reliability compatibility rule must remain explicit")

    evaluator = load_evaluator()
    if evaluator is not None:
        if list(evaluator.DECISION_KINDS) != spec.get("control_decision_kinds"):
            fail("SF010_EVALUATOR", "evaluator decision kinds drift from source contract")
        for name in (
            "evaluate_control",
            "make_receipt_candidate",
            "evaluate_effect_eligibility",
            "evaluate_post_effect",
            "recompute_receipt_sha",
        ):
            if not callable(getattr(evaluator, name, None)):
                fail("SF010_EVALUATOR", f"evaluator missing callable {name}")

    if ERRORS:
        for error in ERRORS:
            print(error, file=sys.stderr)
        return 1
    print("SEMANTIC_FIREWALL_V1_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
