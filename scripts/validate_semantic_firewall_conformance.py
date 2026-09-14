#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SF = ROOT / "contracts" / "semantic-firewall-v1"
PROFILE_PATH = SF / "conformance-profile.json"
REGISTRY_PATH = SF / "rule-registry.json"
PREDICATE_REGISTRY_PATH = SF / "predicate-registry.json"
PREDICATE_SCHEMA_PATH = SF / "predicate-registry.schema.json"
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


def _shape_matches(value, value_type: str) -> bool:
    if value_type == "STRING":
        return isinstance(value, str)
    if value_type == "INTEGER":
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "BOOLEAN":
        return isinstance(value, bool)
    if value_type == "STRING_SET":
        return isinstance(value, list) and all(isinstance(item, str) for item in value) and len(value) == len(set(value))
    if value_type == "SHA256":
        return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    if value_type == "OBJECT":
        return isinstance(value, dict)
    return False


def _direct_parameter_field(node: ast.AST, params: set[str]) -> bool:
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id in params:
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
        return isinstance(node.func.value, ast.Name) and node.func.value.id in params
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"bool", "str", "int", "float"}:
        return len(node.args) == 1 and _direct_parameter_field(node.args[0], params)
    return False


def _find_direct_control_passthrough(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return []
    findings: list[str] = []
    for fn in [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        params = {arg.arg for arg in fn.args.args}
        if not fn.name.startswith(("should_", "can_", "is_", "evaluate")):
            continue
        aliases: set[str] = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if _direct_parameter_field(node.value, params):
                    aliases.add(node.targets[0].id)
        for node in ast.walk(fn):
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            if _direct_parameter_field(node.value, params) or (isinstance(node.value, ast.Name) and node.value.id in aliases):
                findings.append(f"{fn.name}:{getattr(node, 'lineno', 0)}")
    return findings


def _validate_predicate_registry(profile: dict, registry: dict, predicates: dict, errors: list[str]) -> None:
    if predicates.get("runtime_control_authority") != "NONE" or predicates.get("registry_authority") != "SOURCE_VALIDATION_ONLY":
        errors.append("SFC023_PREDICATE: predicate registry must be source-validation only with runtime authority NONE")
        return
    unsafe = set(predicates.get("unsafe_input_source_classes", []))
    if not set(profile.get("unsafe_direct_pass_source_classes", [])).issubset(unsafe):
        errors.append("SFC023_PREDICATE: predicate unsafe source classes must include every direct-pass unsafe source class")

    runtime_rows = predicates.get("runtime_predicates", [])
    ids = [row.get("predicate_id") for row in runtime_rows if isinstance(row, dict)]
    if len(ids) != len(runtime_rows) or len(ids) != len(set(ids)):
        errors.append("SFC023_PREDICATE: runtime predicate IDs must be present and unique")
        return
    by_id = {row["predicate_id"]: row for row in runtime_rows}
    allowed_kinds = set(profile.get("control_decision_kinds", []))
    derivation_graph: dict[str, set[str]] = {pid: set() for pid in by_id}

    for predicate_id, row in by_id.items():
        kinds = row.get("decision_kinds", [])
        if not kinds or len(kinds) != len(set(kinds)) or not set(kinds).issubset(allowed_kinds):
            errors.append(f"SFC023_PREDICATE: {predicate_id} has invalid decision kinds")
        inputs = row.get("required_inputs", [])
        names = [item.get("name") for item in inputs if isinstance(item, dict)]
        if not inputs or len(names) != len(inputs) or len(names) != len(set(names)):
            errors.append(f"SFC023_PREDICATE: {predicate_id} required input names must be present and unique")
            continue
        for item in inputs:
            name = item.get("name", "<missing>")
            sources = set(item.get("source_classes", []))
            if not sources or unsafe.intersection(sources):
                errors.append(f"SFC023_PREDICATE: {predicate_id}.{name} has unsafe or empty provenance source classes")
            semantic = item.get("semantic_type")
            if semantic == "CLOSED_ENUM" and not item.get("allowed_values"):
                errors.append(f"SFC023_PREDICATE: {predicate_id}.{name} closed enum requires allowed_values")
            if semantic == "INTEGER_WITH_UNIT" and not item.get("unit"):
                errors.append(f"SFC023_PREDICATE: {predicate_id}.{name} integer threshold input requires an exact unit")
            if semantic == "DETERMINISTIC_DERIVATION":
                ref = item.get("derivation_predicate_id")
                if ref not in by_id or ref == predicate_id:
                    errors.append(f"SFC023_PREDICATE: {predicate_id}.{name} deterministic derivation reference is missing or self-referential")
                else:
                    derivation_graph[predicate_id].add(ref)

        kind = row.get("definition_kind")
        if kind == "EXPRESSION":
            expression = row.get("expression")
            if not isinstance(expression, dict) or row.get("evaluator_ref") is not None:
                errors.append(f"SFC023_PREDICATE: {predicate_id} EXPRESSION definition shape invalid")
                continue
            left = expression.get("left_input")
            input_map = {item["name"]: item for item in inputs if isinstance(item, dict) and "name" in item}
            if left not in input_map:
                errors.append(f"SFC023_PREDICATE: {predicate_id} expression left_input is not a required input")
                continue
            try:
                right = json.loads(expression.get("right_value_json"))
            except Exception:
                errors.append(f"SFC023_PREDICATE: {predicate_id} expression right_value_json is invalid")
                continue
            if not _shape_matches(right, expression.get("right_value_type")):
                errors.append(f"SFC023_PREDICATE: {predicate_id} expression right value does not match its type")
            operator = expression.get("operator")
            left_type = input_map[left].get("value_type")
            if operator == "INTEGER_GTE" and left_type != "INTEGER":
                errors.append(f"SFC023_PREDICATE: {predicate_id} INTEGER_GTE requires INTEGER input")
            if operator == "TIMESTAMP_GTE" and input_map[left].get("semantic_type") != "TIMESTAMP_RFC3339":
                errors.append(f"SFC023_PREDICATE: {predicate_id} TIMESTAMP_GTE requires TIMESTAMP_RFC3339 input")
            if operator == "SET_CONTAINS_ALL" and left_type != "STRING_SET":
                errors.append(f"SFC023_PREDICATE: {predicate_id} SET_CONTAINS_ALL requires STRING_SET input")
        elif kind == "EVALUATOR_REF":
            if row.get("expression") is not None or not row.get("evaluator_ref"):
                errors.append(f"SFC023_PREDICATE: {predicate_id} EVALUATOR_REF definition shape invalid")
            config = row.get("evaluator_config_json")
            if config is not None:
                try:
                    json.loads(config)
                except Exception:
                    errors.append(f"SFC023_PREDICATE: {predicate_id} evaluator_config_json is invalid")
        else:
            errors.append(f"SFC023_PREDICATE: {predicate_id} definition_kind invalid")

    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(pid: str) -> None:
        if pid in visited:
            return
        if pid in visiting:
            errors.append(f"SFC023_PREDICATE: deterministic derivation cycle includes {pid}")
            return
        visiting.add(pid)
        for dep in derivation_graph.get(pid, set()):
            visit(dep)
        visiting.remove(pid)
        visited.add(pid)
    for pid in derivation_graph:
        visit(pid)

    surfaces = registry.get("surfaces", [])
    by_path = {entry.get("path"): entry for entry in surfaces if isinstance(entry, dict)}
    expected_paths = {path for path, entry in by_path.items() if entry.get("affected_control_decision_kinds")}
    bindings = predicates.get("surface_predicate_bindings", [])
    binding_paths = [row.get("path") for row in bindings if isinstance(row, dict)]
    if len(binding_paths) != len(bindings) or len(binding_paths) != len(set(binding_paths)):
        errors.append("SFC023_PREDICATE: surface predicate binding paths must be present and unique")
        return
    if set(binding_paths) != expected_paths:
        errors.append(f"SFC023_PREDICATE: predicate closure bindings mismatch missing={sorted(expected_paths-set(binding_paths))} extra={sorted(set(binding_paths)-expected_paths)}")
    for binding in bindings:
        path = binding.get("path")
        entry = by_path.get(path)
        if entry is None:
            continue
        if set(binding.get("affected_control_decision_kinds", [])) != set(entry.get("affected_control_decision_kinds", [])):
            errors.append(f"SFC023_PREDICATE: {path} binding decision kinds drift from rule registry")
        if binding.get("undefined_predicate_result") != "PREDICATE_DEFINITION_MISSING":
            errors.append(f"SFC023_PREDICATE: {path} undefined predicate result must fail closed as PREDICATE_DEFINITION_MISSING")
        sources = set(binding.get("permitted_input_source_classes", []))
        if not sources.issubset(set(entry.get("permitted_evidence_source_classes", []))) or unsafe.intersection(sources):
            errors.append(f"SFC023_PREDICATE: {path} predicate provenance sources are unsafe or exceed the registered surface")
        mode = binding.get("closure_mode")
        evaluator_paths = binding.get("evaluator_paths", [])
        if mode == "SOURCE_ONLY_INACTIVE":
            if entry.get("enforcement_state") != "SOURCE_ONLY":
                errors.append(f"SFC023_PREDICATE: {path} may be SOURCE_ONLY_INACTIVE only when the rule surface is SOURCE_ONLY")
        elif mode == "CANONICAL_EVALUATOR_REF":
            if not evaluator_paths:
                errors.append(f"SFC023_PREDICATE: {path} canonical evaluator closure requires evaluator paths")
            for evaluator_path in evaluator_paths:
                if evaluator_path not in entry.get("deterministic_consumer_paths", []) or not (ROOT / evaluator_path).is_file():
                    errors.append(f"SFC023_PREDICATE: {path} evaluator {evaluator_path} is not its registered deterministic consumer")
                    continue
                if evaluator_path.endswith(".py"):
                    for finding in _find_direct_control_passthrough(ROOT / evaluator_path):
                        errors.append(f"SFC024_PASSTHROUGH: {path} {evaluator_path}:{finding} returns caller field truth directly without an exact predicate")
        else:
            errors.append(f"SFC023_PREDICATE: {path} closure_mode invalid")


def validate() -> list[str]:
    errors: list[str] = []
    for path in (PROFILE_PATH, REGISTRY_PATH, PREDICATE_REGISTRY_PATH, PREDICATE_SCHEMA_PATH, SPEC_PATH, BOOTSTRAP_PATH):
        if not path.is_file():
            errors.append(f"SFC001_MISSING: {rel(path)}")
    if errors:
        return errors

    profile = load(PROFILE_PATH)
    registry = load(REGISTRY_PATH)
    predicates = load(PREDICATE_REGISTRY_PATH)
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
    if spec.get("predicate_registry_path") != rel(PREDICATE_REGISTRY_PATH):
        errors.append("SFC019_SPEC_LINK: Semantic Firewall spec must bind the canonical predicate registry")
    if spec.get("conformance_enforcement_state") != "CI_ENFORCED_BOOTSTRAP_REQUIRED":
        errors.append("SFC019_SPEC_LINK: source conformance must be CI-enforced and bootstrap-required")

    required_bootstrap = {
        rel(PROFILE_PATH), rel(REGISTRY_PATH), rel(PREDICATE_REGISTRY_PATH), rel(PREDICATE_SCHEMA_PATH),
        "scripts/validate_semantic_firewall_conformance.py", "tests/test_semantic_firewall_conformance.py",
    }
    if not required_bootstrap.issubset(set(bootstrap.get("required_files", []))):
        errors.append("SFC020_BOOTSTRAP: conformance profile/registries/predicate schema/validator/tests must be required files")
    read_order = bootstrap.get("required_read_order", [])
    for required in (rel(PROFILE_PATH), rel(REGISTRY_PATH), rel(PREDICATE_REGISTRY_PATH)):
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

    _validate_predicate_registry(profile, registry, predicates, errors)
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
