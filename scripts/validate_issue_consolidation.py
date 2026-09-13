#!/usr/bin/env python3
"""Deterministic validation for Life Issue consolidation source state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "issue-consolidation-policy.json"
REGISTRY_PATH = ROOT / "governance" / "issue-consolidation-registry.json"

TERMINAL_RELATIONSHIPS = (
    "DUPLICATE",
    "COMBINE_REQUIRED",
    "DEPENDENCY",
    "INDEPENDENT",
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def unordered_pair(left: str, right: str) -> tuple[str, str]:
    if left == right:
        raise ValueError("pair members must differ")
    return tuple(sorted((left, right)))


def index_registry(registry: dict[str, Any]):
    canonical = {}
    for item in registry["canonical_requirements"]:
        key = item["canonical_requirement_id"]
        if key in canonical:
            raise ValueError(f"duplicate canonical_requirement_id: {key}")
        canonical[key] = item

    sources = {}
    issue_fragments = set()
    for item in registry["source_requirements"]:
        ref = item["source_requirement_ref"]
        if ref in sources:
            raise ValueError(f"duplicate source_requirement_ref: {ref}")
        issue_fragment = (item["source_issue_number"], item["source_fragment_id"])
        if issue_fragment in issue_fragments:
            raise ValueError(f"duplicate source issue fragment: {issue_fragment}")
        issue_fragments.add(issue_fragment)
        sources[ref] = item

    dependency_edges = set()
    dependency_ids = set()
    for item in registry["dependencies"]:
        dep_id = item["dependency_id"]
        if dep_id in dependency_ids:
            raise ValueError(f"duplicate dependency_id: {dep_id}")
        dependency_ids.add(dep_id)
        edge = (item["requirement_id"], item["depends_on_requirement_id"])
        if edge in dependency_edges:
            raise ValueError(f"duplicate dependency edge: {edge}")
        dependency_edges.add(edge)

    independence_pairs = set()
    assertion_ids = set()
    for item in registry["independence_assertions"]:
        assertion_id = item["assertion_id"]
        if assertion_id in assertion_ids:
            raise ValueError(f"duplicate assertion_id: {assertion_id}")
        assertion_ids.add(assertion_id)
        pair = unordered_pair(item["left_requirement_id"], item["right_requirement_id"])
        if pair in independence_pairs:
            raise ValueError(f"duplicate independence assertion: {pair}")
        independence_pairs.add(pair)

    return canonical, sources, dependency_edges, independence_pairs


def derive_relationship(
    left_ref: str,
    right_ref: str,
    canonical: dict[str, Any],
    sources: dict[str, Any],
    dependency_edges: set[tuple[str, str]],
    independence_pairs: set[tuple[str, str]],
) -> str:
    left_source = sources[left_ref]
    right_source = sources[right_ref]
    left_id = left_source["canonical_requirement_id"]
    right_id = right_source["canonical_requirement_id"]
    left_canonical = canonical[left_id]
    right_canonical = canonical[right_id]

    if left_id == right_id:
        return "DUPLICATE"

    left_work = left_canonical["canonical_work_identity_id"]
    right_work = right_canonical["canonical_work_identity_id"]
    if left_work == right_work:
        return "COMBINE_REQUIRED"

    if (left_id, right_id) in dependency_edges or (right_id, left_id) in dependency_edges:
        return "DEPENDENCY"

    if unordered_pair(left_id, right_id) in independence_pairs:
        return "INDEPENDENT"

    return "UNRESOLVED"


def validate_dependency_graph(
    canonical: dict[str, Any],
    dependency_edges: set[tuple[str, str]],
) -> None:
    graph: dict[str, set[str]] = {key: set() for key in canonical}
    for requirement_id, depends_on_id in dependency_edges:
        if requirement_id not in canonical or depends_on_id not in canonical:
            raise ValueError(f"dependency references unknown requirement: {(requirement_id, depends_on_id)}")
        if requirement_id == depends_on_id:
            raise ValueError(f"self dependency forbidden: {requirement_id}")
        if (
            canonical[requirement_id]["canonical_work_identity_id"]
            == canonical[depends_on_id]["canonical_work_identity_id"]
        ):
            raise ValueError(
                "dependency within one canonical work identity is forbidden; "
                "decompose it in the parent goal mechanism"
            )
        graph[requirement_id].add(depends_on_id)

    temporary: set[str] = set()
    permanent: set[str] = set()

    def visit(node: str) -> None:
        if node in permanent:
            return
        if node in temporary:
            raise ValueError(f"dependency cycle detected at {node}")
        temporary.add(node)
        for dependency in graph[node]:
            visit(dependency)
        temporary.remove(node)
        permanent.add(node)

    for node in graph:
        visit(node)


def validate(policy: dict[str, Any], registry: dict[str, Any]) -> None:
    if policy["terminal_relationships"] != list(TERMINAL_RELATIONSHIPS):
        raise ValueError("terminal relationship enumeration drift")
    if policy["unit_of_consolidation"] != "ATOMIC_REQUIREMENT_NOT_RAW_ISSUE":
        raise ValueError("raw Issue cannot become the consolidation unit")
    if policy["candidate_discovery"]["authority"] != "ZERO":
        raise ValueError("candidate discovery must have zero authority")
    if registry["runtime_control_authority"] != "NONE":
        raise ValueError("registry cannot gain runtime control authority")

    canonical, sources, dependency_edges, independence_pairs = index_registry(registry)

    source_refs_by_canonical: dict[str, set[str]] = {key: set() for key in canonical}
    source_conditions_by_canonical: dict[str, set[str]] = {key: set() for key in canonical}
    for ref, source in sources.items():
        canonical_id = source["canonical_requirement_id"]
        if canonical_id not in canonical:
            raise ValueError(f"{ref} maps to unknown canonical requirement: {canonical_id}")
        source_refs_by_canonical[canonical_id].add(ref)
        source_conditions_by_canonical[canonical_id].update(source["acceptance_condition_ids"])

    for canonical_id, item in canonical.items():
        declared_refs = set(item["source_requirement_refs"])
        if declared_refs != source_refs_by_canonical[canonical_id]:
            raise ValueError(
                f"{canonical_id}: source refs mismatch declared={sorted(declared_refs)} "
                f"actual={sorted(source_refs_by_canonical[canonical_id])}"
            )
        declared_conditions = set(item["acceptance_condition_ids"])
        if declared_conditions != source_conditions_by_canonical[canonical_id]:
            raise ValueError(
                f"{canonical_id}: canonical acceptance conditions must equal the union "
                "of every source requirement's acceptance conditions"
            )

    validate_dependency_graph(canonical, dependency_edges)

    for left_id, right_id in independence_pairs:
        if left_id not in canonical or right_id not in canonical:
            raise ValueError(f"independence assertion references unknown requirement: {(left_id, right_id)}")
        if canonical[left_id]["canonical_work_identity_id"] == canonical[right_id]["canonical_work_identity_id"]:
            raise ValueError("independence assertion cannot split one canonical work identity")
        if (left_id, right_id) in dependency_edges or (right_id, left_id) in dependency_edges:
            raise ValueError("independence assertion cannot contradict an exact dependency edge")

    candidate_pairs: set[tuple[str, str]] = set()
    for pair in registry["candidate_pairs"]:
        left_ref = pair["left_source_requirement_ref"]
        right_ref = pair["right_source_requirement_ref"]
        if left_ref not in sources or right_ref not in sources:
            raise ValueError(f"candidate pair references unknown source requirement: {(left_ref, right_ref)}")
        pair_key = unordered_pair(left_ref, right_ref)
        if pair_key in candidate_pairs:
            raise ValueError(f"duplicate candidate pair: {pair_key}")
        candidate_pairs.add(pair_key)

        derived = derive_relationship(left_ref, right_ref, canonical, sources, dependency_edges, independence_pairs)
        expected_state = "UNRESOLVED" if derived == "UNRESOLVED" else "CLASSIFIED"
        expected_relationship = None if derived == "UNRESOLVED" else derived
        if pair["classification_state"] != expected_state:
            raise ValueError(
                f"{pair_key}: classification_state {pair['classification_state']} "
                f"does not match deterministic {expected_state}"
            )
        if pair["expected_relationship"] != expected_relationship:
            raise ValueError(
                f"{pair_key}: expected_relationship {pair['expected_relationship']} "
                f"does not match deterministic {expected_relationship}"
            )

    excluded = set()
    for item in registry["excluded_issues"]:
        issue = item["source_issue_number"]
        if issue in excluded:
            raise ValueError(f"duplicate excluded issue: {issue}")
        excluded.add(issue)
    source_issues = {item["source_issue_number"] for item in sources.values()}
    collision = excluded & source_issues
    if collision:
        raise ValueError(f"excluded Issue also supplies active source requirement: {sorted(collision)}")


def main() -> int:
    policy = load_json(POLICY_PATH)
    registry = load_json(REGISTRY_PATH)
    validate(policy, registry)
    print("ISSUE_CONSOLIDATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
