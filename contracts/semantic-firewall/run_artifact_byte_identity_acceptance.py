#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

ACCEPTANCE_PATH = Path(__file__).with_name("artifact-byte-identity.acceptance.json")
REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_ROLES = {"CONTRACT", "VALIDATOR", "EVALUATOR", "TEST_SUITE"}
EXPECTED_OUTCOMES = {"BOUND": True, "UNBOUND": False}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
STRICT_JSON_REJECTION_CASES = (
    ("duplicate_json_key_rejected", b'{"value":1,"value":2}'),
    ("nonfinite_nan_rejected", b'{"value":NaN}'),
    ("nonfinite_positive_infinity_rejected", b'{"value":Infinity}'),
    ("nonfinite_negative_infinity_rejected", b'{"value":-Infinity}'),
)
REQUIRED_CASE_IDS = {
    "baseline_bound",
    "contract_well_formed_wrong_hash_rejected",
    "validator_well_formed_wrong_hash_rejected",
    "evaluator_well_formed_wrong_hash_rejected",
    "test_suite_well_formed_wrong_hash_rejected",
    "artifact_identity_change_rejected",
    "artifact_path_change_rejected",
    "missing_artifact_file_rejected",
    "parent_traversal_rejected",
    "absolute_path_rejected",
    "directory_path_rejected",
    "missing_role_rejected",
    "extra_role_rejected",
    "extra_artifact_field_rejected",
    "malformed_hash_rejected",
    "hash_wrong_type_rejected",
    "id_wrong_type_rejected",
    "path_wrong_type_rejected",
}


class ArtifactIdentityError(Exception):
    pass


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactIdentityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_nonfinite_constant(value: str) -> None:
    raise ArtifactIdentityError(f"non-finite JSON number is not permitted: {value}")


def decode_json(raw: bytes, source_name: str) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ArtifactIdentityError(f"invalid JSON in {source_name}: {exc}") from exc


def load_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    document = decode_json(raw, path.name)
    if not isinstance(document, dict):
        raise ArtifactIdentityError(f"{path.name} must contain a JSON object")
    return document, digest


def exact_keys(value: dict[str, Any], expected: set[str]) -> bool:
    return set(value) == expected


def valid_identifier(value: Any) -> bool:
    return isinstance(value, str) and IDENTIFIER_PATTERN.fullmatch(value) is not None


def valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def resolve_repo_file(relative_path: Any) -> Path | None:
    if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
        return None
    pure = PurePosixPath(relative_path)
    if pure.is_absolute() or str(pure) != relative_path or any(part in {".", ".."} for part in pure.parts):
        return None

    current = REPO_ROOT
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            return None

    try:
        resolved_root = REPO_ROOT.resolve(strict=True)
        resolved = current.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (FileNotFoundError, RuntimeError, ValueError, OSError):
        return None

    return resolved if resolved.is_file() else None


def validate_fixture(fixture: Any) -> dict[str, dict[str, str]]:
    if not isinstance(fixture, dict) or not exact_keys(fixture, {"artifacts"}):
        raise ArtifactIdentityError("fixture must contain exactly artifacts")
    artifacts = fixture["artifacts"]
    if not isinstance(artifacts, dict) or set(artifacts) != EXPECTED_ROLES:
        raise ArtifactIdentityError(f"fixture artifacts must contain exactly {sorted(EXPECTED_ROLES)}")

    normalized: dict[str, dict[str, str]] = {}
    for role in sorted(EXPECTED_ROLES):
        spec = artifacts[role]
        if not isinstance(spec, dict) or not exact_keys(spec, {"id", "path"}):
            raise ArtifactIdentityError(f"{role}: fixture artifact must contain exactly id and path")
        if not valid_identifier(spec["id"]):
            raise ArtifactIdentityError(f"{role}: invalid artifact id")
        path = resolve_repo_file(spec["path"])
        if path is None:
            raise ArtifactIdentityError(f"{role}: fixture path does not resolve to a regular repository file")
        normalized[role] = {"id": spec["id"], "path": spec["path"]}
    return normalized


def materialize_claim(fixture_artifacts: dict[str, dict[str, str]]) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for role, spec in fixture_artifacts.items():
        path = resolve_repo_file(spec["path"])
        if path is None:
            raise ArtifactIdentityError(f"{role}: fixture path became unavailable")
        artifacts[role] = {
            "id": spec["id"],
            "path": spec["path"],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return {"artifacts": artifacts}


def artifact_set_is_bound(candidate: Any, fixture_artifacts: dict[str, dict[str, str]]) -> bool:
    if not isinstance(candidate, dict) or not exact_keys(candidate, {"artifacts"}):
        return False
    artifacts = candidate["artifacts"]
    if not isinstance(artifacts, dict) or set(artifacts) != EXPECTED_ROLES:
        return False

    for role in EXPECTED_ROLES:
        value = artifacts[role]
        if not isinstance(value, dict) or not exact_keys(value, {"id", "path", "sha256"}):
            return False
        if not valid_identifier(value["id"]) or not valid_sha256(value["sha256"]):
            return False
        path = resolve_repo_file(value["path"])
        if path is None:
            return False
        if value["id"] != fixture_artifacts[role]["id"] or value["path"] != fixture_artifacts[role]["path"]:
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != value["sha256"]:
            return False
    return True


def apply_mutation(value: dict[str, Any], mutation: dict[str, Any]) -> None:
    if not isinstance(mutation, dict):
        raise ArtifactIdentityError("mutation must be an object")
    op = mutation.get("op")
    if op not in {"ADD", "REPLACE", "REMOVE", "REPLACE_WITH_DIFFERENT_VALID_SHA256"}:
        raise ArtifactIdentityError(f"unsupported mutation op: {op!r}")
    if op in {"REMOVE", "REPLACE_WITH_DIFFERENT_VALID_SHA256"}:
        if set(mutation) != {"op", "path"}:
            raise ArtifactIdentityError(f"{op} mutation must contain exactly op and path")
    elif set(mutation) != {"op", "path", "value"}:
        raise ArtifactIdentityError(f"{op} mutation must contain exactly op, path, and value")

    path = mutation.get("path")
    if not isinstance(path, str) or re.fullmatch(r"/(?:[A-Z_]+|[a-z][a-z0-9_]*)(?:/(?:[A-Z_]+|[a-z][a-z0-9_]*))*", path) is None:
        raise ArtifactIdentityError(f"unsupported mutation path: {path!r}")

    parts = path.split("/")[1:]
    parent: dict[str, Any] = value
    for segment in parts[:-1]:
        if segment not in parent or not isinstance(parent[segment], dict):
            raise ArtifactIdentityError(f"mutation path does not resolve to an object: {path}")
        parent = parent[segment]

    target = parts[-1]
    if op == "ADD":
        if target in parent:
            raise ArtifactIdentityError(f"ADD target already exists: {path}")
        parent[target] = copy.deepcopy(mutation["value"])
        return
    if target not in parent:
        raise ArtifactIdentityError(f"{op} target does not exist: {path}")
    if op == "REPLACE":
        parent[target] = copy.deepcopy(mutation["value"])
    elif op == "REMOVE":
        del parent[target]
    else:
        current = parent[target]
        if not valid_sha256(current):
            raise ArtifactIdentityError(f"{op} target is not a valid SHA-256: {path}")
        first = "1" if current[0] == "0" else "0"
        replacement = first + current[1:]
        if replacement == current or not valid_sha256(replacement):
            raise ArtifactIdentityError(f"could not derive a different valid SHA-256 for {path}")
        parent[target] = replacement


def validate_acceptance_document(document: dict[str, Any]) -> tuple[dict[str, dict[str, str]], list[dict[str, Any]]]:
    if not exact_keys(document, {"contract_id", "purpose", "fixture", "acceptance_cases"}):
        raise ArtifactIdentityError("acceptance document has unsupported or missing top-level keys")
    if document["contract_id"] != "semantic_firewall.artifact_byte_identity":
        raise ArtifactIdentityError("unexpected contract_id")
    if not isinstance(document["purpose"], str) or not document["purpose"].strip():
        raise ArtifactIdentityError("purpose must be a non-empty string")

    fixture_artifacts = validate_fixture(document["fixture"])
    baseline = materialize_claim(fixture_artifacts)
    if not artifact_set_is_bound(baseline, fixture_artifacts):
        raise ArtifactIdentityError("materialized fixture must itself be BOUND")

    cases = document["acceptance_cases"]
    if not isinstance(cases, list) or not cases:
        raise ArtifactIdentityError("acceptance_cases must be a non-empty array")

    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or not exact_keys(case, {"case_id", "mutations", "expected"}):
            raise ArtifactIdentityError(f"acceptance case {index} has invalid shape")
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not case_id:
            raise ArtifactIdentityError(f"acceptance case {index} has invalid case_id")
        if case_id in seen:
            raise ArtifactIdentityError(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        if not isinstance(case["expected"], str) or case["expected"] not in EXPECTED_OUTCOMES:
            raise ArtifactIdentityError(f"{case_id}: unsupported expected outcome {case['expected']!r}")
        if not isinstance(case["mutations"], list):
            raise ArtifactIdentityError(f"{case_id}: mutations must be an array")
        candidate = copy.deepcopy(baseline)
        for mutation in case["mutations"]:
            apply_mutation(candidate, mutation)

    missing = REQUIRED_CASE_IDS - seen
    if missing:
        raise ArtifactIdentityError(f"missing required acceptance cases: {sorted(missing)}")
    return fixture_artifacts, cases


def run_strict_json_acceptance() -> int:
    failures = 0
    for case_id, raw in STRICT_JSON_REJECTION_CASES:
        try:
            decode_json(raw, case_id)
        except ArtifactIdentityError:
            print(f"PASS {case_id} expected=REJECT actual=REJECT")
        else:
            failures += 1
            print(f"FAIL {case_id} expected=REJECT actual=ACCEPT")
    return failures


def main() -> int:
    try:
        parser_failures = run_strict_json_acceptance()
        document, acceptance_sha256 = load_json(ACCEPTANCE_PATH)
        fixture_artifacts, cases = validate_acceptance_document(document)
        baseline = materialize_claim(fixture_artifacts)
    except (OSError, KeyError, TypeError, ArtifactIdentityError) as exc:
        print(f"CONTRACT_ERROR: {exc}", file=sys.stderr)
        return 2

    failures = parser_failures
    for case in cases:
        candidate = copy.deepcopy(baseline)
        try:
            for mutation in case["mutations"]:
                apply_mutation(candidate, mutation)
            actual_bound = artifact_set_is_bound(candidate, fixture_artifacts)
        except (KeyError, TypeError, ArtifactIdentityError) as exc:
            print(f"CONTRACT_ERROR: {case['case_id']}: {exc}", file=sys.stderr)
            return 2

        expected_bound = EXPECTED_OUTCOMES[case["expected"]]
        status = "PASS" if actual_bound == expected_bound else "FAIL"
        if status == "FAIL":
            failures += 1
        actual = "BOUND" if actual_bound else "UNBOUND"
        print(f"{status} {case['case_id']} expected={case['expected']} actual={actual}")

    manifest_bytes = json.dumps(
        baseline,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    result = "PASS" if failures == 0 else "FAIL"
    runner_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(
        json.dumps(
            {
                "contract_id": document["contract_id"],
                "acceptance_artifact_sha256": acceptance_sha256,
                "runner_sha256": runner_sha256,
                "artifact_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "artifacts": baseline["artifacts"],
                "strict_json_cases_total": len(STRICT_JSON_REJECTION_CASES),
                "strict_json_cases_failed": parser_failures,
                "cases_total": len(cases),
                "cases_failed": failures - parser_failures,
                "result": result,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
