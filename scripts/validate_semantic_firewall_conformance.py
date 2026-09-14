#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SF = ROOT / "contracts" / "semantic-firewall-v1"
PROFILE_PATH = SF / "conformance-profile.json"
REGISTRY_PATH = SF / "rule-registry.json"
SPEC_PATH = SF / "spec.json"
BOOTSTRAP_PATH = ROOT / "continuity" / "bootstrap.json"
COMPATIBILITY_PATH = ROOT / "reliability" / "compatibility-map.json"
PROBLEM_INTAKE_PATH = ROOT / "governance" / "problem-intake-policy.json"
ISSUE_CONSOLIDATION_PATH = ROOT / "governance" / "issue-consolidation-policy.json"


def load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def discover(profile: dict) -> set[str]:
    found: set[str] = set()
    discovery = profile.get("governed_surface_discovery", {})
    for pattern in discovery.get("glob_patterns", []):
        for path in ROOT.glob(pattern):
            if path.is_file():
                found.add(rel(path))
    found.difference_update(discovery.get("excluded_paths", []))
    return found


def validate() -> list[str]:
    errors: list[str] = []
    for path in (PROFILE_PATH, REGISTRY_PATH, SPEC_PATH, BOOTSTRAP_PATH):
        if not path.is_file():
            errors.append(f"SFC001_MISSING: {rel(path)}")
    if errors:
        return errors

    profile = load(PROFILE_PATH)
    registry = load(REGISTRY_PATH)
    spec = load(SPEC_PATH)
    bootstrap = load(BOOTSTRAP_PATH)

    if profile.get("runtime_control_authority") != "NONE" or profile.get("profile_authority") != "SOURCE_VALIDATION_ONLY":
        errors.append("SFC002_AUTHORITY: conformance profile must be source-validation only with runtime authority NONE")
    if registry.get("runtime_control_authority") != "NONE" or registry.get("registry_authority") != "SOURCE_VALIDATION_ONLY":
        errors.append("SFC002_AUTHORITY: rule registry must be source-validation only with runtime authority NONE")

    decision_kinds = profile.get("control_decision_kinds", [])
    if decision_kinds != spec.get("control_decision_kinds"):
        errors.append("SFC003_KINDS: conformance decision kinds must exactly match Semantic Firewall v1")
    fail_closed = set(profile.get("fail_closed_states", []))
    if fail_closed != {"UNKNOWN", "UNVERIFIED", "NOT_RUN", "MISSING", "STALE"}:
        errors.append("SFC004_FAIL_CLOSED: fail-closed states must exactly cover UNKNOWN/UNVERIFIED/NOT_RUN/MISSING/STALE")

    surfaces = registry.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        errors.append("SFC005_REGISTRY: surfaces must be a nonempty list")
        return errors
    paths = [entry.get("path") for entry in surfaces if isinstance(entry, dict)]
    if len(paths) != len(surfaces) or len(paths) != len(set(paths)):
        errors.append("SFC005_REGISTRY: every registered surface path must be present and unique")

    discovered = discover(profile)
    registered = set(paths)
    if discovered != registered:
        missing = sorted(discovered - registered)
        extra = sorted(registered - discovered)
        errors.append(f"SFC006_DISCOVERY: governed/registered mismatch missing={missing} extra={extra}")

    required_fields = set(profile.get("required_registry_entry_fields", []))
    authority_classes = set(profile.get("authority_classes", []))
    enforcement_states = set(profile.get("enforcement_states", []))
    unsafe_sources = set(profile.get("unsafe_direct_pass_source_classes", []))
    allowed_kinds = set(decision_kinds)
    expected_evidence_states = set(profile.get("evidence_states", []))

    for entry in surfaces:
        if not isinstance(entry, dict):
            errors.append("SFC007_ENTRY: registry entry must be an object")
            continue
        path = entry.get("path", "<missing>")
        if set(entry) != required_fields:
            errors.append(f"SFC007_ENTRY: {path} fields mismatch")
            continue
        if entry["canonical_owner"] != path:
            errors.append(f"SFC008_OWNER: {path} must own its registered rule surface directly")
        if not (ROOT / path).is_file() or not (ROOT / entry["canonical_owner"]).is_file():
            errors.append(f"SFC008_OWNER: {path} or its canonical owner is missing")
        if entry["authority_class"] not in authority_classes:
            errors.append(f"SFC009_AUTHORITY_CLASS: {path}")
        kinds = entry["affected_control_decision_kinds"]
        if len(kinds) != len(set(kinds)) or not set(kinds).issubset(allowed_kinds):
            errors.append(f"SFC010_KINDS: {path} has invalid affected control kinds")
        if set(entry["evidence_states"]) != expected_evidence_states:
            errors.append(f"SFC011_EVIDENCE: {path} evidence states drift from profile")
        if set(entry["fail_closed_states"]) != fail_closed:
            errors.append(f"SFC011_EVIDENCE: {path} fail-closed states drift from profile")
        if kinds and unsafe_sources.intersection(entry["permitted_evidence_source_classes"]):
            errors.append(f"SFC012_UNSAFE_SOURCE: {path} permits a direct-pass unsafe source class")
        if entry["enforcement_state"] not in enforcement_states:
            errors.append(f"SFC013_ENFORCEMENT: {path} has invalid enforcement state")
        if entry["enforcement_state"] != "SOURCE_ONLY" and not entry["deterministic_consumer_paths"]:
            errors.append(f"SFC013_ENFORCEMENT: {path} claims enforcement without a deterministic consumer")
        for consumer in entry["deterministic_consumer_paths"]:
            if not (ROOT / consumer).is_file():
                errors.append(f"SFC014_LINK: {path} missing consumer {consumer}")
        for test_ref in entry["test_refs"]:
            if not (ROOT / test_ref).is_file():
                errors.append(f"SFC014_LINK: {path} missing test {test_ref}")
        if entry["authority_class"] != "RUNTIME_CONTROL" and entry["output_authority"] != "NONE":
            errors.append(f"SFC015_OUTPUT_AUTHORITY: {path} non-runtime surface output authority must be NONE")
        if entry["enforcement_state"] == "RUNTIME_ACTIVE":
            errors.append(f"SFC016_RUNTIME: {path} cannot become runtime active from this build-time profile")
        if entry["state_change_effect_mode"] == "RELIABILITY_GATED" and not entry["authoritative_readback_requirements"]:
            errors.append(f"SFC017_READBACK: {path} reliability-gated effects require authoritative readback/postconditions")
        if any(field in {"work_id", "lease_id", "generation"} for field in entry["identity_fields"]) and not entry["fencing_requirements"]:
            errors.append(f"SFC018_FENCING: {path} stale-work-capable identity requires fencing requirements")

    if spec.get("conformance_profile_path") != rel(PROFILE_PATH) or spec.get("rule_registry_path") != rel(REGISTRY_PATH):
        errors.append("SFC019_SPEC_LINK: Semantic Firewall spec must bind the conformance profile and rule registry")
    if spec.get("conformance_enforcement_state") != "CI_ENFORCED_BOOTSTRAP_REQUIRED":
        errors.append("SFC019_SPEC_LINK: source conformance must be CI-enforced and bootstrap-required")

    required_bootstrap = {
        rel(PROFILE_PATH),
        rel(REGISTRY_PATH),
        "scripts/validate_semantic_firewall_conformance.py",
        "tests/test_semantic_firewall_conformance.py",
    }
    if not required_bootstrap.issubset(set(bootstrap.get("required_files", []))):
        errors.append("SFC020_BOOTSTRAP: conformance profile/registry/validator/tests must be required files")
    read_order = bootstrap.get("required_read_order", [])
    for required in (rel(PROFILE_PATH), rel(REGISTRY_PATH)):
        if required not in read_order:
            errors.append(f"SFC020_BOOTSTRAP: {required} must be in required read order")
    if "python scripts/validate_semantic_firewall.py" not in bootstrap.get("validation_command", ""):
        errors.append("SFC020_BOOTSTRAP: existing Semantic Firewall validator must remain in validation command")

    if PROBLEM_INTAKE_PATH.is_file():
        problem = load(PROBLEM_INTAKE_PATH)
        if problem.get("activation_state") != "SOURCE_ONLY_NOT_YET_CONSUMED_BY_WORK_SELECTION":
            errors.append("SFC021_SOURCE_ONLY: problem intake activation state is not explicit source-only")
    if ISSUE_CONSOLIDATION_PATH.is_file():
        consolidation = load(ISSUE_CONSOLIDATION_PATH)
        state = consolidation.get("integration", {}).get("selector_activation_state")
        if state != "SOURCE_ONLY_NOT_YET_CONSUMED_BY_WORK_SELECTION":
            errors.append("SFC021_SOURCE_ONLY: issue consolidation selector activation is not explicit source-only")

    if COMPATIBILITY_PATH.is_file():
        compatibility = load(COMPATIBILITY_PATH)
        sf_link = compatibility.get("semantic_firewall", {})
        if sf_link.get("current_contract_path") != "contracts/semantic-firewall-v1":
            errors.append("SFC022_CROSS_POLICY: Reliability must reference the Build-native Semantic Firewall v1 path")
        goal = compatibility.get("goal_identity", {})
        if goal.get("current_owner_path") != "governance/goal-registry.json" or goal.get("state") != "ACTIVE":
            errors.append("SFC022_CROSS_POLICY: Reliability goal identity link must reference the active canonical goal registry")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("SEMANTIC_FIREWALL_CONFORMANCE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
