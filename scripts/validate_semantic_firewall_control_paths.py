#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SF = ROOT / "contracts" / "semantic-firewall-v1"
REGISTRY_PATH = SF / "control-path-registry.json"
SCHEMA_PATH = SF / "control-path-registry.schema.json"
SPEC_PATH = SF / "spec.json"
PROFILE_PATH = SF / "conformance-profile.json"
RULE_REGISTRY_PATH = SF / "rule-registry.json"
PREDICATE_REGISTRY_PATH = SF / "predicate-registry.json"
WORK_FENCE_PATH = ROOT / "governance" / "work-fence-policy.json"
ADMISSIONS_PATH = ROOT / "governance" / "work-admissions.json"

REQUIRED_CLASSES = [
    "GITHUB_ISSUE",
    "GITHUB_PULL_REQUEST",
    "ADMITTED_WORK_ITEM",
    "WORK_RECORD_INSTANCE",
    "RULE_SURFACE",
    "CLAIM_TRANSITION",
    "CONNECTED_APP_MUTATION",
    "RUNTIME_EFFECT",
    "CI_TRUST_ROOT",
]
EXPECTED_COMPLETION_STATES = {
    "RUNTIME_EFFECT": "RUNTIME_ACTIVE",
    "CI_TRUST_ROOT": "CI_ENFORCED_INDEPENDENT",
}
EXPECTED_RUNTIME_DEPS = {
    "TRUSTED_EVIDENCE_ADAPTER_IMPLEMENTED",
    "PERSISTED_TRUSTED_PASS_RECEIPT",
    "NON_BYPASS_EFFECT_ROUTING",
    "AUTHORITATIVE_POST_EFFECT_READBACK",
    "EXACT_LIFE_INVOKE_DEPLOYED_AND_VERIFIED",
}
EXPECTED_CI_TRUST_DEPS = {
    "BASE_OR_EXTERNAL_VERIFIER_NOT_CANDIDATE_CONTROLLED",
    "PROTECT_MAIN_REQUIRES_INDEPENDENT_GUARDIAN_CHECK",
    "MERGE_GROUP_GUARDIAN_EXECUTION",
}
REQUIRED_CLASS_FIELDS = {
    "class_id",
    "source_class",
    "direct_control_effect",
    "canonical_bridge_paths",
    "instance_globs",
    "schema_path",
    "deterministic_consumer_paths",
    "fence_paths",
    "authoritative_readback_requirements",
    "decision_kinds",
    "protected_boundaries",
    "enforcement_state",
}
OPTIONAL_CLASS_FIELDS = {"activation_dependencies"}


def load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _require_existing(path_text: str, owner: str, errors: list[str]) -> None:
    path = ROOT / path_text
    if not path.is_file():
        errors.append(f"SFCP006_LINK: {owner} missing path {path_text}")


def validate() -> list[str]:
    errors: list[str] = []
    for path in (
        REGISTRY_PATH,
        SCHEMA_PATH,
        SPEC_PATH,
        PROFILE_PATH,
        RULE_REGISTRY_PATH,
        PREDICATE_REGISTRY_PATH,
        WORK_FENCE_PATH,
        ADMISSIONS_PATH,
    ):
        if not path.is_file():
            errors.append(f"SFCP001_MISSING: {rel(path)}")
    if errors:
        return errors

    registry = load(REGISTRY_PATH)
    spec = load(SPEC_PATH)
    profile = load(PROFILE_PATH)
    work_fence = load(WORK_FENCE_PATH)
    admissions = load(ADMISSIONS_PATH)

    if (
        registry.get("runtime_control_authority") != "NONE"
        or registry.get("registry_authority") != "SOURCE_VALIDATION_ONLY"
    ):
        errors.append(
            "SFCP002_AUTHORITY: control-path registry must be source-validation only with runtime authority NONE"
        )

    if registry.get("registry_id") != "life-semantic-firewall-control-path-registry-v1":
        errors.append("SFCP003_ID: unexpected control-path registry id")
    if registry.get("protected_boundary_source") != "governance/work-fence-policy.json:protected_boundaries":
        errors.append("SFCP003_ID: protected boundary source must be the canonical work-fence policy")
    if registry.get("semantic_firewall_work_item_id") != "github-issue-57":
        errors.append("SFCP003_ID: Semantic Firewall work item binding must remain github-issue-57")
    if spec.get("control_path_registry_path") != rel(REGISTRY_PATH):
        errors.append("SFCP003_ID: Semantic Firewall spec must bind the canonical control-path registry")

    required_classes = registry.get("required_object_classes", [])
    if required_classes != REQUIRED_CLASSES:
        errors.append("SFCP004_CLASSES: required object classes drift from the closed universal coverage set")

    rows = registry.get("object_classes", [])
    if not isinstance(rows, list):
        errors.append("SFCP004_CLASSES: object_classes must be a list")
        return errors
    ids = [row.get("class_id") for row in rows if isinstance(row, dict)]
    if len(ids) != len(rows) or len(ids) != len(set(ids)):
        errors.append("SFCP004_CLASSES: object class IDs must be present and unique")
        return errors
    if set(ids) != set(REQUIRED_CLASSES):
        errors.append(
            f"SFCP004_CLASSES: object class coverage mismatch missing={sorted(set(REQUIRED_CLASSES)-set(ids))} "
            f"extra={sorted(set(ids)-set(REQUIRED_CLASSES))}"
        )
    by_id = {row["class_id"]: row for row in rows if isinstance(row, dict) and "class_id" in row}

    allowed_kinds = set(spec.get("control_decision_kinds", []))
    profile_unsafe = set(profile.get("unsafe_direct_pass_source_classes", []))
    covered_kinds: set[str] = set()
    boundary_owners: dict[str, list[str]] = {}

    for class_id, row in by_id.items():
        fields = set(row)
        if not REQUIRED_CLASS_FIELDS.issubset(fields) or not fields.issubset(REQUIRED_CLASS_FIELDS | OPTIONAL_CLASS_FIELDS):
            errors.append(f"SFCP005_SHAPE: {class_id} fields mismatch")
            continue
        kinds = row.get("decision_kinds", [])
        if not kinds or len(kinds) != len(set(kinds)) or not set(kinds).issubset(allowed_kinds):
            errors.append(f"SFCP005_SHAPE: {class_id} has invalid decision kinds")
        covered_kinds.update(kinds)

        for path_text in row.get("canonical_bridge_paths", []):
            _require_existing(path_text, class_id, errors)
        for path_text in row.get("deterministic_consumer_paths", []):
            _require_existing(path_text, class_id, errors)
        for path_text in row.get("fence_paths", []):
            _require_existing(path_text, class_id, errors)
        schema_path = row.get("schema_path")
        if schema_path is not None:
            _require_existing(schema_path, class_id, errors)

        for pattern in row.get("instance_globs", []):
            matches = [path for path in ROOT.glob(pattern) if path.is_file()]
            if not matches:
                errors.append(f"SFCP006_LINK: {class_id} instance glob has no current instance: {pattern}")

        for boundary in row.get("protected_boundaries", []):
            boundary_owners.setdefault(boundary, []).append(class_id)

        if row.get("source_class") in profile_unsafe and row.get("direct_control_effect") != "FORBIDDEN":
            errors.append(
                f"SFCP008_UNSAFE_DYNAMIC_SOURCE: {class_id} unsafe source must have direct control effect FORBIDDEN"
            )

        state = row.get("enforcement_state")
        if state in {"CI_ENFORCED", "BOOTSTRAP_REQUIRED", "CI_ENFORCED_INDEPENDENT", "RUNTIME_ACTIVE"}:
            if not row.get("deterministic_consumer_paths"):
                errors.append(f"SFCP009_ENFORCEMENT: {class_id} active enforcement requires deterministic consumers")
        elif state != "SOURCE_ONLY_INACTIVE":
            errors.append(f"SFCP009_ENFORCEMENT: {class_id} has invalid enforcement state")

    if covered_kinds != allowed_kinds:
        errors.append(
            f"SFCP007_COVERAGE: decision-kind coverage mismatch missing={sorted(allowed_kinds-covered_kinds)} "
            f"extra={sorted(covered_kinds-allowed_kinds)}"
        )

    expected_boundaries = set(work_fence.get("protected_boundaries", []))
    actual_boundaries = set(boundary_owners)
    if actual_boundaries != expected_boundaries:
        errors.append(
            f"SFCP007_BOUNDARY: protected boundary coverage mismatch missing={sorted(expected_boundaries-actual_boundaries)} "
            f"extra={sorted(actual_boundaries-expected_boundaries)}"
        )
    duplicate_boundaries = sorted(boundary for boundary, owners in boundary_owners.items() if len(owners) != 1)
    if duplicate_boundaries:
        errors.append(
            f"SFCP007_BOUNDARY: every protected boundary must have exactly one canonical class owner duplicates={duplicate_boundaries}"
        )

    issue = by_id.get("GITHUB_ISSUE", {})
    if issue.get("source_class") != "GITHUB_ISSUE" or issue.get("direct_control_effect") != "FORBIDDEN":
        errors.append("SFCP008_UNSAFE_DYNAMIC_SOURCE: GitHub Issue prose cannot directly produce control")
    if "governance/work-admissions.json" not in issue.get("canonical_bridge_paths", []):
        errors.append("SFCP008_UNSAFE_DYNAMIC_SOURCE: GitHub Issue authority transition must pass through work admissions")

    pr = by_id.get("GITHUB_PULL_REQUEST", {})
    if pr.get("source_class") != "GITHUB_PR" or pr.get("direct_control_effect") != "FORBIDDEN":
        errors.append("SFCP008_UNSAFE_DYNAMIC_SOURCE: GitHub PR prose cannot directly produce control")
    if not {"PULL_REQUEST_VALIDATION", "MERGE_GROUP_VALIDATION"}.issubset(set(pr.get("protected_boundaries", []))):
        errors.append("SFCP008_UNSAFE_DYNAMIC_SOURCE: GitHub PR integration must bind PR and merge-group validation")

    work_item = by_id.get("ADMITTED_WORK_ITEM", {})
    if "governance/work-admissions.json" not in work_item.get("canonical_bridge_paths", []):
        errors.append("SFCP010_WORK_ITEM: admitted work must originate from canonical work admissions")
    if "WORK_SELECTION_DISPATCH" not in work_item.get("protected_boundaries", []):
        errors.append("SFCP010_WORK_ITEM: admitted work must pass the work-selection dispatch boundary")

    work_record = by_id.get("WORK_RECORD_INSTANCE", {})
    if work_record.get("instance_globs") != ["coordination/work/*.json"]:
        errors.append("SFCP010_WORK_ITEM: every work-record instance class must be covered by coordination/work/*.json")
    if work_record.get("schema_path") != "coordination/schema/work-record.schema.json":
        errors.append("SFCP010_WORK_ITEM: work-record instances must bind the canonical work-record schema")
    if "SOURCE_WORKSPACE_MUTATION" not in work_record.get("protected_boundaries", []):
        errors.append("SFCP010_WORK_ITEM: work records must bind the source-workspace mutation boundary")

    runtime = by_id.get("RUNTIME_EFFECT", {})
    if set(runtime.get("activation_dependencies", [])) != EXPECTED_RUNTIME_DEPS:
        errors.append("SFCP011_RUNTIME: runtime effect activation dependency set drifted")
    if spec.get("activation_state") == "SOURCE_ONLY_NOT_RUNTIME_AUTHORITY":
        if runtime.get("enforcement_state") != "SOURCE_ONLY_INACTIVE":
            errors.append("SFCP011_RUNTIME: runtime effect path cannot be active while Semantic Firewall is source-only")
    if spec.get("evidence_trust_boundary", {}).get("trusted_evidence_adapter_state") == "NOT_IMPLEMENTED":
        if runtime.get("enforcement_state") == "RUNTIME_ACTIVE":
            errors.append("SFCP011_RUNTIME: runtime effect path cannot be active before trusted evidence adapter implementation")

    ci_trust = by_id.get("CI_TRUST_ROOT", {})
    if set(ci_trust.get("activation_dependencies", [])) != EXPECTED_CI_TRUST_DEPS:
        errors.append("SFCP011_RUNTIME: independent CI trust-root activation dependency set drifted")
    if ci_trust.get("enforcement_state") == "CI_ENFORCED_INDEPENDENT":
        errors.append(
            "SFCP011_RUNTIME: source registry cannot self-assert independent CI trust; activation requires external/ruleset evidence"
        )

    gate = registry.get("completion_gate", {})
    if gate != {
        "complete_requires_all_required_object_classes": True,
        "complete_requires_exact_protected_boundary_coverage": True,
        "complete_requires_unsafe_dynamic_sources_direct_control_forbidden": True,
        "complete_requires_class_states": EXPECTED_COMPLETION_STATES,
    }:
        errors.append("SFCP012_COMPLETION: Semantic Firewall completion gate drifted")

    work_item_id = registry.get("semantic_firewall_work_item_id")
    matches = [
        item
        for item in admissions.get("items", [])
        if isinstance(item, dict) and item.get("work_item_id") == work_item_id
    ]
    if len(matches) != 1:
        errors.append("SFCP012_COMPLETION: Semantic Firewall work admission must exist exactly once")
    elif matches[0].get("state") == "COMPLETE":
        unmet = [
            f"{class_id}:{by_id.get(class_id, {}).get('enforcement_state')}!={required_state}"
            for class_id, required_state in EXPECTED_COMPLETION_STATES.items()
            if by_id.get(class_id, {}).get("enforcement_state") != required_state
        ]
        if unmet:
            errors.append(
                "SFCP012_COMPLETION: github-issue-57 cannot be COMPLETE before non-bypass runtime and independent CI "
                f"requirements are active unmet={unmet}"
            )

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("SEMANTIC_FIREWALL_CONTROL_PATHS_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
