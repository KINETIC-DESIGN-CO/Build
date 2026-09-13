#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import run_artifact_byte_identity_acceptance as artifact_identity
import run_contract_reference_acceptance as contract_reference

ACCEPTANCE_PATH = Path(__file__).with_name("receipt-execution-binding.acceptance.json")
RECEIPT_NAMESPACE = uuid.UUID("7a43874b-c0d6-5b91-8a75-739718838c9a")
PROVENANCE_STAGE_ENV = "LIFE_SF_PROVENANCE_STAGE"
PROVENANCE_STAGE_VALUE = "1"
EXPECTED_KINDS = {"VALIDATION", "TEST"}
EXPECTED_OUTCOMES = {"CONSUMABLE": True, "UNCONSUMABLE": False}
STRICT_JSON_REJECTION_CASES = (
    ("duplicate_json_key_rejected", b'{"value":1,"value":2}'),
    ("nonfinite_nan_rejected", b'{"value":NaN}'),
    ("nonfinite_positive_infinity_rejected", b'{"value":Infinity}'),
    ("nonfinite_negative_infinity_rejected", b'{"value":-Infinity}'),
)
REQUIRED_CASE_IDS = {
    "baseline_consumable",
    "contract_hash_self_consistent_forgery_rejected",
    "validator_hash_self_consistent_forgery_rejected",
    "evaluator_hash_self_consistent_forgery_rejected",
    "test_suite_hash_self_consistent_forgery_rejected",
    "validator_id_self_consistent_forgery_rejected",
    "evaluator_id_self_consistent_forgery_rejected",
    "validation_receipt_id_self_consistent_forgery_rejected",
    "test_receipt_id_self_consistent_forgery_rejected",
    "validation_stdout_hash_forgery_rejected",
    "validation_stderr_hash_forgery_rejected",
    "test_stdout_hash_forgery_rejected",
    "test_stderr_hash_forgery_rejected",
    "validation_exit_code_forgery_rejected",
    "test_exit_code_forgery_rejected",
    "validation_boolean_exit_code_rejected",
    "test_boolean_exit_code_rejected",
    "validation_execution_result_forgery_rejected",
    "test_execution_result_forgery_rejected",
    "validation_runtime_version_forgery_rejected",
    "test_runtime_version_forgery_rejected",
    "validation_runtime_implementation_forgery_rejected",
    "test_runtime_implementation_forgery_rejected",
    "validation_artifact_path_substitution_rejected",
    "test_artifact_path_substitution_rejected",
    "validation_evidence_hash_forgery_rejected",
    "test_evidence_hash_forgery_rejected",
    "validation_envelope_receipt_copy_mismatch_rejected",
    "test_envelope_receipt_copy_mismatch_rejected",
    "authorization_to_effect_execution_replay_rejected",
    "authorization_to_mutation_replay_rejected",
    "missing_validation_envelope_rejected",
    "missing_test_envelope_rejected",
    "extra_envelope_role_rejected",
    "extra_top_level_field_rejected",
}


class ReceiptBindingError(Exception):
    pass


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ReceiptBindingError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def reject_nonfinite_constant(value: str) -> None:
    raise ReceiptBindingError(f"non-finite JSON number is not permitted: {value}")


def decode_json(raw: bytes, source_name: str) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ReceiptBindingError(f"invalid JSON in {source_name}: {exc}") from exc


def load_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    document = decode_json(raw, path.name)
    if not isinstance(document, dict):
        raise ReceiptBindingError(f"{path.name} must contain a JSON object")
    return document, hashlib.sha256(raw).hexdigest()


def exact_keys(value: dict[str, Any], expected: set[str]) -> bool:
    return set(value) == expected


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReceiptBindingError(f"value is not canonical JSON: {exc}") from exc


def canonical_equal(left: Any, right: Any) -> bool:
    try:
        return canonical_bytes(left) == canonical_bytes(right)
    except ReceiptBindingError:
        return False


def different_sha256(value: str) -> str:
    if not artifact_identity.valid_sha256(value):
        raise ReceiptBindingError("cannot forge a non-SHA-256 value")
    replacement = ("1" if value[0] == "0" else "0") + value[1:]
    if replacement == value or not artifact_identity.valid_sha256(replacement):
        raise ReceiptBindingError("could not derive a different valid SHA-256")
    return replacement


def different_uuid(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ReceiptBindingError("cannot forge an invalid UUID") from exc
    return str(uuid.UUID(int=parsed.int ^ 1))


def different_identifier(value: str) -> str:
    candidate = value + ".forged"
    if candidate == value or not artifact_identity.valid_identifier(candidate):
        raise ReceiptBindingError("could not derive a different valid artifact identifier")
    return candidate


def load_request_schema() -> tuple[dict[str, Any], set[str]]:
    control = contract_reference.control_request
    document, _ = control.load_contract(control.CONTRACT_PATH)
    request_schema, _ = control.validate_contract_document(document)
    decision_ref = request_schema["properties"]["decision_kind"]["$ref"]
    decision_schema = control.resolve_ref(request_schema, decision_ref)
    return request_schema, set(decision_schema["enum"])


def load_canonical_artifacts() -> dict[str, dict[str, str]]:
    document, _ = artifact_identity.load_json(artifact_identity.ACCEPTANCE_PATH)
    return artifact_identity.validate_fixture(document["fixture"])


def validate_fixture(fixture: Any, decision_kinds: set[str]) -> dict[str, Any]:
    if not isinstance(fixture, dict) or not exact_keys(
        fixture, {"contract_id", "decision_kind", "artifacts"}
    ):
        raise ReceiptBindingError(
            "fixture must contain exactly contract_id, decision_kind, and artifacts"
        )
    if not contract_reference.valid_uuid(fixture["contract_id"]):
        raise ReceiptBindingError("fixture contract_id must be a lowercase UUID-shaped value")
    if not isinstance(fixture["decision_kind"], str) or fixture["decision_kind"] not in decision_kinds:
        raise ReceiptBindingError("fixture decision_kind must be in the control-request decision enum")

    canonical = load_canonical_artifacts()
    artifacts = fixture["artifacts"]
    if not isinstance(artifacts, dict) or set(artifacts) != set(canonical):
        raise ReceiptBindingError(
            "fixture artifact roles must exactly match the artifact-byte identity boundary"
        )

    normalized: dict[str, dict[str, str]] = {}
    for role in sorted(canonical):
        spec = artifacts[role]
        if not isinstance(spec, dict) or not exact_keys(spec, {"id", "path"}):
            raise ReceiptBindingError(f"{role}: artifact must contain exactly id and path")
        if spec != canonical[role]:
            raise ReceiptBindingError(
                f"{role}: artifact identity/path differs from the artifact-byte identity boundary"
            )
        if artifact_identity.resolve_repo_file(spec["path"]) is None:
            raise ReceiptBindingError(f"{role}: artifact path does not resolve to a repository file")
        normalized[role] = {"id": spec["id"], "path": spec["path"]}

    return {
        "contract_id": fixture["contract_id"],
        "decision_kind": fixture["decision_kind"],
        "artifacts": normalized,
    }


def observe_artifact_bytes(
    fixture: dict[str, Any],
) -> tuple[dict[str, dict[str, str]], dict[str, bytes]]:
    observed: dict[str, dict[str, str]] = {}
    raw_by_role: dict[str, bytes] = {}
    for role, spec in fixture["artifacts"].items():
        path = artifact_identity.resolve_repo_file(spec["path"])
        if path is None:
            raise ReceiptBindingError(f"{role}: artifact became unavailable")
        raw = path.read_bytes()
        raw_by_role[role] = raw
        observed[role] = {
            "id": spec["id"],
            "path": spec["path"],
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    return observed, raw_by_role


def snapshot_filename(spec: dict[str, str]) -> str:
    return Path(spec["path"]).name


@contextmanager
def artifact_snapshot(
    fixture: dict[str, Any],
) -> Iterator[tuple[dict[str, dict[str, str]], dict[str, bytes], Path]]:
    observed, raw_by_role = observe_artifact_bytes(fixture)
    with tempfile.TemporaryDirectory(prefix="life-sf-receipt-") as tmp:
        root = Path(tmp)
        for role, raw in raw_by_role.items():
            target = root / snapshot_filename(observed[role])
            target.write_bytes(raw)
            os.chmod(target, 0o400)
        verify_snapshot(root, observed)
        os.chmod(root, 0o500)
        try:
            yield observed, raw_by_role, root
            verify_snapshot(root, observed)
        finally:
            os.chmod(root, 0o700)


def verify_snapshot(root: Path, observed: dict[str, dict[str, str]]) -> None:
    for role, spec in observed.items():
        path = root / snapshot_filename(spec)
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ReceiptBindingError(f"{role}: snapshot became unreadable: {exc}") from exc
        if hashlib.sha256(raw).hexdigest() != spec["sha256"]:
            raise ReceiptBindingError(f"{role}: snapshot bytes changed after observation")


BOOTSTRAP = (
    "import sys; "
    "virtual_path=sys.argv[1]; root=sys.argv[2]; sys.path.insert(0, root); "
    "source=sys.stdin.buffer.read(); "
    "ns={'__name__':'__main__','__file__':virtual_path,'__package__':None}; "
    "exec(compile(source, virtual_path, 'exec'), ns, ns)"
)


def run_source_bytes(source: bytes, virtual_path: Path, root: Path, timeout: int = 30) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            [sys.executable, "-I", "-B", "-c", BOOTSTRAP, str(virtual_path), str(root)],
            input=source,
            cwd=root,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReceiptBindingError(f"snapshot execution failed: {exc}") from exc


def parse_last_record(stdout: bytes, role: str) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ReceiptBindingError(f"{role}: execution produced no stdout receipt")
    record = decode_json(lines[-1], f"{role} stdout receipt")
    if not isinstance(record, dict):
        raise ReceiptBindingError(f"{role}: final stdout record must be a JSON object")
    numeric = {"cases_failed", "cases_total"}
    if role == "EVALUATOR":
        numeric |= {"strict_json_cases_failed", "strict_json_cases_total"}
    for field in numeric:
        if field in record and type(record[field]) is not int:
            raise ReceiptBindingError(f"{role}: {field} must be an exact integer")
    return record


def observe_execution(
    role: str,
    observed: dict[str, dict[str, str]],
    raw_by_role: dict[str, bytes],
    snapshot_root: Path,
) -> dict[str, Any]:
    if role not in {"VALIDATOR", "EVALUATOR"}:
        raise ReceiptBindingError(f"unsupported executable role: {role}")
    virtual_path = snapshot_root / snapshot_filename(observed[role])
    completed = run_source_bytes(raw_by_role[role], virtual_path, snapshot_root)
    verify_snapshot(snapshot_root, observed)
    final_record = parse_last_record(completed.stdout, role)

    if completed.returncode != 0:
        raise ReceiptBindingError(f"{role}: exact snapshot program exited {completed.returncode}")
    if final_record.get("result") != "PASS":
        raise ReceiptBindingError(f"{role}: exact snapshot program did not emit result PASS")

    if role == "VALIDATOR":
        required = {"artifact_sha256", "cases_failed", "cases_total", "contract_id", "result"}
        if not exact_keys(final_record, required):
            raise ReceiptBindingError("VALIDATOR: final receipt shape changed")
        if final_record["contract_id"] != "semantic_firewall.control_request":
            raise ReceiptBindingError("VALIDATOR: unexpected contract_id")
        if final_record["artifact_sha256"] != observed["CONTRACT"]["sha256"]:
            raise ReceiptBindingError("VALIDATOR: output is not bound to snapshot CONTRACT bytes")
        if final_record["cases_failed"] != 0 or final_record["cases_total"] <= 0:
            raise ReceiptBindingError("VALIDATOR: acceptance cases did not pass")
    else:
        required = {
            "cases_failed",
            "cases_total",
            "contract_id",
            "control_request_artifact_sha256",
            "eligibility_artifact_sha256",
            "result",
            "runner_sha256",
            "strict_json_cases_failed",
            "strict_json_cases_total",
        }
        if not exact_keys(final_record, required):
            raise ReceiptBindingError("EVALUATOR: final receipt shape changed")
        if final_record["contract_id"] != "semantic_firewall.contract_reference_eligibility":
            raise ReceiptBindingError("EVALUATOR: unexpected contract_id")
        if final_record["control_request_artifact_sha256"] != observed["CONTRACT"]["sha256"]:
            raise ReceiptBindingError("EVALUATOR: output is not bound to snapshot CONTRACT bytes")
        if final_record["runner_sha256"] != observed["EVALUATOR"]["sha256"]:
            raise ReceiptBindingError("EVALUATOR: output is not bound to snapshot EVALUATOR bytes")
        if final_record["eligibility_artifact_sha256"] != observed["TEST_SUITE"]["sha256"]:
            raise ReceiptBindingError("EVALUATOR: output is not bound to snapshot TEST_SUITE bytes")
        if final_record["cases_failed"] != 0 or final_record["strict_json_cases_failed"] != 0:
            raise ReceiptBindingError("EVALUATOR: acceptance cases did not pass")
        if final_record["cases_total"] <= 0 or final_record["strict_json_cases_total"] <= 0:
            raise ReceiptBindingError("EVALUATOR: acceptance case counts must be positive")

    return {
        "program_role": role,
        "exit_code": completed.returncode,
        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
        "result": final_record["result"],
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
    }


def envelope_payload(
    kind: str,
    contract_id: str,
    decision_kind: str,
    artifacts: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    return {
        "kind": kind,
        "contract_id": contract_id,
        "decision_kind": decision_kind,
        "artifacts": artifacts,
        "execution": execution,
    }


def derive_receipt_identity(kind: str, evidence_sha256: str) -> str:
    return str(uuid.uuid5(RECEIPT_NAMESPACE, f"{kind}:{evidence_sha256}"))


def make_envelope(
    kind: str,
    contract_id: str,
    decision_kind: str,
    artifacts: dict[str, dict[str, str]],
    execution: dict[str, Any],
) -> dict[str, Any]:
    if kind == "VALIDATION":
        selected = {role: copy.deepcopy(artifacts[role]) for role in ("CONTRACT", "VALIDATOR")}
    elif kind == "TEST":
        selected = {
            role: copy.deepcopy(artifacts[role])
            for role in ("CONTRACT", "EVALUATOR", "TEST_SUITE")
        }
    else:
        raise ReceiptBindingError(f"unsupported receipt kind: {kind}")

    payload = envelope_payload(kind, contract_id, decision_kind, selected, execution)
    evidence_sha256 = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    receipt_id = derive_receipt_identity(kind, evidence_sha256)

    if kind == "VALIDATION":
        receipt = {
            "receipt_id": receipt_id,
            "contract_id": contract_id,
            "content_sha256": artifacts["CONTRACT"]["sha256"],
            "validator": {
                "id": artifacts["VALIDATOR"]["id"],
                "sha256": artifacts["VALIDATOR"]["sha256"],
            },
            "result": execution["result"],
        }
    else:
        receipt = {
            "receipt_id": receipt_id,
            "contract_id": contract_id,
            "content_sha256": artifacts["CONTRACT"]["sha256"],
            "evaluator": {
                "id": artifacts["EVALUATOR"]["id"],
                "sha256": artifacts["EVALUATOR"]["sha256"],
            },
            "suite_sha256": artifacts["TEST_SUITE"]["sha256"],
            "result": execution["result"],
        }

    return {
        "kind": kind,
        "decision_kind": decision_kind,
        "receipt": receipt,
        "artifacts": selected,
        "execution": copy.deepcopy(execution),
        "evidence_sha256": evidence_sha256,
    }


def issue_envelopes(fixture: dict[str, Any]) -> dict[str, Any]:
    with artifact_snapshot(fixture) as (observed, raw_by_role, root):
        validation_execution = observe_execution("VALIDATOR", observed, raw_by_role, root)
        test_execution = observe_execution("EVALUATOR", observed, raw_by_role, root)
        return {
            "VALIDATION": make_envelope(
                "VALIDATION",
                fixture["contract_id"],
                fixture["decision_kind"],
                observed,
                validation_execution,
            ),
            "TEST": make_envelope(
                "TEST",
                fixture["contract_id"],
                fixture["decision_kind"],
                observed,
                test_execution,
            ),
        }


def build_eligibility(fixture: dict[str, Any], envelopes: dict[str, Any]) -> dict[str, Any]:
    validation = copy.deepcopy(envelopes["VALIDATION"]["receipt"])
    test = copy.deepcopy(envelopes["TEST"]["receipt"])
    artifacts = {**envelopes["VALIDATION"]["artifacts"], **envelopes["TEST"]["artifacts"]}
    return {
        "request": {
            "decision_kind": fixture["decision_kind"],
            "contract_id": fixture["contract_id"],
        },
        "contract": {
            "contract_id": fixture["contract_id"],
            "decision_kind": fixture["decision_kind"],
            "enabled": True,
            "content_sha256": artifacts["CONTRACT"]["sha256"],
            "validator": {
                "id": artifacts["VALIDATOR"]["id"],
                "sha256": artifacts["VALIDATOR"]["sha256"],
            },
            "evaluator": {
                "id": artifacts["EVALUATOR"]["id"],
                "sha256": artifacts["EVALUATOR"]["sha256"],
            },
            "validation_receipt_id": validation["receipt_id"],
            "test_receipt_id": test["receipt_id"],
            "test_suite_sha256": artifacts["TEST_SUITE"]["sha256"],
        },
        "validation_receipt": validation,
        "test_receipt": test,
    }


def issue_candidate(fixture: dict[str, Any]) -> dict[str, Any]:
    envelopes = issue_envelopes(fixture)
    return {"eligibility": build_eligibility(fixture, envelopes), "receipt_envelopes": envelopes}


def structural_eligible(candidate: Any, request_schema: dict[str, Any], decision_kinds: set[str]) -> bool:
    if not isinstance(candidate, dict) or not isinstance(candidate.get("eligibility"), dict):
        return False
    try:
        return contract_reference.eligible(candidate["eligibility"], request_schema, decision_kinds)
    except (KeyError, TypeError):
        return False


def consumable(
    candidate: Any,
    fixture: dict[str, Any],
    request_schema: dict[str, Any],
    decision_kinds: set[str],
) -> bool:
    if not isinstance(candidate, dict) or not exact_keys(candidate, {"eligibility", "receipt_envelopes"}):
        return False
    if not structural_eligible(candidate, request_schema, decision_kinds):
        return False
    eligibility = candidate["eligibility"]
    envelopes = candidate["receipt_envelopes"]
    if not isinstance(envelopes, dict) or set(envelopes) != EXPECTED_KINDS:
        return False
    for kind in EXPECTED_KINDS:
        envelope = envelopes.get(kind)
        if not isinstance(envelope, dict) or not exact_keys(
            envelope,
            {"kind", "decision_kind", "receipt", "artifacts", "execution", "evidence_sha256"},
        ):
            return False
        if envelope["kind"] != kind:
            return False
        if envelope["decision_kind"] != eligibility["request"].get("decision_kind"):
            return False
        if envelope["decision_kind"] != eligibility["contract"].get("decision_kind"):
            return False
        execution = envelope.get("execution")
        if not isinstance(execution, dict) or type(execution.get("exit_code")) is not int:
            return False

    if not canonical_equal(
        envelopes["VALIDATION"].get("receipt"), eligibility.get("validation_receipt")
    ):
        return False
    if not canonical_equal(envelopes["TEST"].get("receipt"), eligibility.get("test_receipt")):
        return False

    try:
        fresh = issue_envelopes(fixture)
    except ReceiptBindingError:
        return False
    return canonical_equal(envelopes, fresh)


def receipt_key(kind: str) -> tuple[str, str]:
    if kind == "VALIDATION":
        return "validation_receipt", "validation_receipt_id"
    if kind == "TEST":
        return "test_receipt", "test_receipt_id"
    raise ReceiptBindingError(f"unsupported receipt kind: {kind}")


def rederive_envelope(candidate: dict[str, Any], kind: str) -> None:
    envelope = candidate["receipt_envelopes"][kind]
    eligibility = candidate["eligibility"]
    receipt_field, pointer_field = receipt_key(kind)
    payload = envelope_payload(
        kind,
        eligibility["contract"]["contract_id"],
        envelope["decision_kind"],
        envelope["artifacts"],
        envelope["execution"],
    )
    evidence_sha256 = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    receipt_id = derive_receipt_identity(kind, evidence_sha256)
    envelope["evidence_sha256"] = evidence_sha256
    envelope["receipt"]["receipt_id"] = receipt_id
    eligibility[receipt_field]["receipt_id"] = receipt_id
    eligibility["contract"][pointer_field] = receipt_id


def sync_role_hash(candidate: dict[str, Any], role: str, new_hash: str) -> None:
    eligibility = candidate["eligibility"]
    envelopes = candidate["receipt_envelopes"]
    if role == "CONTRACT":
        eligibility["contract"]["content_sha256"] = new_hash
        eligibility["validation_receipt"]["content_sha256"] = new_hash
        eligibility["test_receipt"]["content_sha256"] = new_hash
        for kind in EXPECTED_KINDS:
            envelopes[kind]["artifacts"]["CONTRACT"]["sha256"] = new_hash
            envelopes[kind]["receipt"]["content_sha256"] = new_hash
            rederive_envelope(candidate, kind)
    elif role == "VALIDATOR":
        eligibility["contract"]["validator"]["sha256"] = new_hash
        eligibility["validation_receipt"]["validator"]["sha256"] = new_hash
        envelopes["VALIDATION"]["artifacts"]["VALIDATOR"]["sha256"] = new_hash
        envelopes["VALIDATION"]["receipt"]["validator"]["sha256"] = new_hash
        rederive_envelope(candidate, "VALIDATION")
    elif role == "EVALUATOR":
        eligibility["contract"]["evaluator"]["sha256"] = new_hash
        eligibility["test_receipt"]["evaluator"]["sha256"] = new_hash
        envelopes["TEST"]["artifacts"]["EVALUATOR"]["sha256"] = new_hash
        envelopes["TEST"]["receipt"]["evaluator"]["sha256"] = new_hash
        rederive_envelope(candidate, "TEST")
    elif role == "TEST_SUITE":
        eligibility["contract"]["test_suite_sha256"] = new_hash
        eligibility["test_receipt"]["suite_sha256"] = new_hash
        envelopes["TEST"]["artifacts"]["TEST_SUITE"]["sha256"] = new_hash
        envelopes["TEST"]["receipt"]["suite_sha256"] = new_hash
        rederive_envelope(candidate, "TEST")
    else:
        raise ReceiptBindingError(f"unsupported artifact role: {role}")


def sync_role_id(candidate: dict[str, Any], role: str, new_id: str) -> None:
    eligibility = candidate["eligibility"]
    envelopes = candidate["receipt_envelopes"]
    if role == "VALIDATOR":
        eligibility["contract"]["validator"]["id"] = new_id
        eligibility["validation_receipt"]["validator"]["id"] = new_id
        envelopes["VALIDATION"]["artifacts"]["VALIDATOR"]["id"] = new_id
        envelopes["VALIDATION"]["receipt"]["validator"]["id"] = new_id
        rederive_envelope(candidate, "VALIDATION")
    elif role == "EVALUATOR":
        eligibility["contract"]["evaluator"]["id"] = new_id
        eligibility["test_receipt"]["evaluator"]["id"] = new_id
        envelopes["TEST"]["artifacts"]["EVALUATOR"]["id"] = new_id
        envelopes["TEST"]["receipt"]["evaluator"]["id"] = new_id
        rederive_envelope(candidate, "TEST")
    else:
        raise ReceiptBindingError("artifact-id forgery is only defined for VALIDATOR or EVALUATOR")


def apply_mutation(candidate: dict[str, Any], mutation: Any, decision_kinds: set[str]) -> None:
    if not isinstance(mutation, dict) or not isinstance(mutation.get("op"), str):
        raise ReceiptBindingError("mutation must be an object with an op string")
    op = mutation["op"]
    eligibility = candidate["eligibility"]
    envelopes = candidate["receipt_envelopes"]

    if op == "FORGE_DECISION_KIND":
        if set(mutation) != {"op", "value"} or mutation["value"] not in decision_kinds:
            raise ReceiptBindingError("FORGE_DECISION_KIND requires one allowed decision kind")
        if mutation["value"] == eligibility["request"]["decision_kind"]:
            raise ReceiptBindingError("FORGE_DECISION_KIND must change the decision kind")
        eligibility["request"]["decision_kind"] = mutation["value"]
        eligibility["contract"]["decision_kind"] = mutation["value"]
        return

    if op == "FORGE_ARTIFACT_HASH":
        if set(mutation) != {"op", "role"} or mutation["role"] not in artifact_identity.EXPECTED_ROLES:
            raise ReceiptBindingError("FORGE_ARTIFACT_HASH requires one supported role")
        role = mutation["role"]
        if role == "CONTRACT":
            current = eligibility["contract"]["content_sha256"]
        elif role == "VALIDATOR":
            current = eligibility["contract"]["validator"]["sha256"]
        elif role == "EVALUATOR":
            current = eligibility["contract"]["evaluator"]["sha256"]
        else:
            current = eligibility["contract"]["test_suite_sha256"]
        sync_role_hash(candidate, role, different_sha256(current))
        return

    if op == "FORGE_ARTIFACT_ID":
        if set(mutation) != {"op", "role"} or mutation["role"] not in {"VALIDATOR", "EVALUATOR"}:
            raise ReceiptBindingError("FORGE_ARTIFACT_ID requires VALIDATOR or EVALUATOR")
        role = mutation["role"]
        sync_role_id(
            candidate,
            role,
            different_identifier(eligibility["contract"][role.lower()]["id"]),
        )
        return

    if op == "FORGE_RECEIPT_ID":
        if set(mutation) != {"op", "kind"} or mutation["kind"] not in EXPECTED_KINDS:
            raise ReceiptBindingError("FORGE_RECEIPT_ID requires one supported kind")
        kind = mutation["kind"]
        receipt_field, pointer_field = receipt_key(kind)
        new_id = different_uuid(eligibility[receipt_field]["receipt_id"])
        eligibility[receipt_field]["receipt_id"] = new_id
        eligibility["contract"][pointer_field] = new_id
        envelopes[kind]["receipt"]["receipt_id"] = new_id
        return

    if op == "FORGE_EXECUTION_HASH":
        if (
            set(mutation) != {"op", "kind", "field"}
            or mutation["kind"] not in EXPECTED_KINDS
            or mutation["field"] not in {"stdout_sha256", "stderr_sha256"}
        ):
            raise ReceiptBindingError("FORGE_EXECUTION_HASH requires kind and stdout/stderr field")
        kind = mutation["kind"]
        field = mutation["field"]
        envelopes[kind]["execution"][field] = different_sha256(envelopes[kind]["execution"][field])
        rederive_envelope(candidate, kind)
        return

    if op == "FORGE_EXECUTION_EXIT_CODE":
        if set(mutation) != {"op", "kind"} or mutation["kind"] not in EXPECTED_KINDS:
            raise ReceiptBindingError("FORGE_EXECUTION_EXIT_CODE requires one supported kind")
        kind = mutation["kind"]
        current = envelopes[kind]["execution"]["exit_code"]
        envelopes[kind]["execution"]["exit_code"] = 1 if current == 0 else 0
        rederive_envelope(candidate, kind)
        return

    if op == "FORGE_EXECUTION_EXIT_CODE_BOOLEAN":
        if set(mutation) != {"op", "kind"} or mutation["kind"] not in EXPECTED_KINDS:
            raise ReceiptBindingError("FORGE_EXECUTION_EXIT_CODE_BOOLEAN requires one supported kind")
        envelopes[mutation["kind"]]["execution"]["exit_code"] = False
        return

    if op == "FORGE_EXECUTION_RESULT":
        if set(mutation) != {"op", "kind"} or mutation["kind"] not in EXPECTED_KINDS:
            raise ReceiptBindingError("FORGE_EXECUTION_RESULT requires one supported kind")
        kind = mutation["kind"]
        current = envelopes[kind]["execution"]["result"]
        envelopes[kind]["execution"]["result"] = "FAIL" if current == "PASS" else "PASS"
        rederive_envelope(candidate, kind)
        return

    if op in {"FORGE_EXECUTION_RUNTIME", "FORGE_EXECUTION_IMPLEMENTATION"}:
        if set(mutation) != {"op", "kind"} or mutation["kind"] not in EXPECTED_KINDS:
            raise ReceiptBindingError(f"{op} requires one supported kind")
        kind = mutation["kind"]
        field = "python_version" if op == "FORGE_EXECUTION_RUNTIME" else "python_implementation"
        current = envelopes[kind]["execution"][field]
        replacement = "0.0.0" if field == "python_version" and current != "0.0.0" else "forged"
        if replacement == current:
            replacement += ".x"
        envelopes[kind]["execution"][field] = replacement
        rederive_envelope(candidate, kind)
        return

    if op == "FORGE_ARTIFACT_PATH":
        if set(mutation) != {"op", "kind", "role"} or mutation["kind"] not in EXPECTED_KINDS:
            raise ReceiptBindingError("FORGE_ARTIFACT_PATH requires kind and role")
        kind = mutation["kind"]
        role = mutation["role"]
        if role not in envelopes[kind]["artifacts"]:
            raise ReceiptBindingError("FORGE_ARTIFACT_PATH role is not present in that envelope")
        alternatives = sorted(set(envelopes[kind]["artifacts"]) - {role})
        if not alternatives:
            raise ReceiptBindingError("FORGE_ARTIFACT_PATH has no substitution target")
        substitute = envelopes[kind]["artifacts"][alternatives[0]]
        envelopes[kind]["artifacts"][role]["path"] = substitute["path"]
        sync_role_hash(candidate, role, substitute["sha256"])
        rederive_envelope(candidate, kind)
        return

    if op == "FORGE_EVIDENCE_HASH":
        if set(mutation) != {"op", "kind"} or mutation["kind"] not in EXPECTED_KINDS:
            raise ReceiptBindingError("FORGE_EVIDENCE_HASH requires one supported kind")
        kind = mutation["kind"]
        forged = different_sha256(envelopes[kind]["evidence_sha256"])
        envelopes[kind]["evidence_sha256"] = forged
        new_id = derive_receipt_identity(kind, forged)
        receipt_field, pointer_field = receipt_key(kind)
        envelopes[kind]["receipt"]["receipt_id"] = new_id
        eligibility[receipt_field]["receipt_id"] = new_id
        eligibility["contract"][pointer_field] = new_id
        return

    if op == "FORGE_ENVELOPE_RECEIPT_COPY":
        if set(mutation) != {"op", "kind"} or mutation["kind"] not in EXPECTED_KINDS:
            raise ReceiptBindingError("FORGE_ENVELOPE_RECEIPT_COPY requires one supported kind")
        kind = mutation["kind"]
        envelopes[kind]["receipt"]["receipt_id"] = different_uuid(
            envelopes[kind]["receipt"]["receipt_id"]
        )
        return

    if op == "REMOVE_ENVELOPE":
        if set(mutation) != {"op", "kind"} or mutation["kind"] not in EXPECTED_KINDS:
            raise ReceiptBindingError("REMOVE_ENVELOPE requires one supported kind")
        del envelopes[mutation["kind"]]
        return

    if op == "ADD_EXTRA_ENVELOPE":
        if set(mutation) != {"op"}:
            raise ReceiptBindingError("ADD_EXTRA_ENVELOPE takes no additional fields")
        envelopes["OTHER"] = copy.deepcopy(envelopes["VALIDATION"])
        return

    if op == "ADD_EXTRA_TOP_LEVEL_FIELD":
        if set(mutation) != {"op"}:
            raise ReceiptBindingError("ADD_EXTRA_TOP_LEVEL_FIELD takes no additional fields")
        candidate["note"] = "forged"
        return

    raise ReceiptBindingError(f"unsupported mutation op: {op}")


def validate_acceptance_document(
    document: dict[str, Any], decision_kinds: set[str]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not exact_keys(document, {"contract_id", "purpose", "fixture", "acceptance_cases"}):
        raise ReceiptBindingError("acceptance document has unsupported or missing top-level keys")
    if document["contract_id"] != "semantic_firewall.receipt_execution_binding":
        raise ReceiptBindingError("unexpected contract_id")
    if not isinstance(document["purpose"], str) or not document["purpose"].strip():
        raise ReceiptBindingError("purpose must be a non-empty string")

    fixture = validate_fixture(document["fixture"], decision_kinds)
    cases = document["acceptance_cases"]
    if not isinstance(cases, list) or not cases:
        raise ReceiptBindingError("acceptance_cases must be a non-empty array")
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or not exact_keys(
            case, {"case_id", "mutations", "expected", "require_structural_eligible"}
        ):
            raise ReceiptBindingError(f"acceptance case {index} has invalid shape")
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ReceiptBindingError(f"acceptance case {index} has invalid/duplicate case_id")
        seen.add(case_id)
        if not isinstance(case["mutations"], list):
            raise ReceiptBindingError(f"{case_id}: mutations must be an array")
        if case["expected"] not in EXPECTED_OUTCOMES:
            raise ReceiptBindingError(f"{case_id}: unsupported expected outcome")
        if not isinstance(case["require_structural_eligible"], bool):
            raise ReceiptBindingError(f"{case_id}: require_structural_eligible must be boolean")
    missing = REQUIRED_CASE_IDS - seen
    extra = seen - REQUIRED_CASE_IDS
    if missing or extra:
        raise ReceiptBindingError(f"acceptance case set mismatch: missing={sorted(missing)} extra={sorted(extra)}")
    return fixture, cases


def implementation_manifest() -> dict[str, str]:
    modules = [
        Path(__file__),
        Path(artifact_identity.__file__),
        Path(contract_reference.__file__),
        Path(contract_reference.control_request.__file__),
    ]
    root = artifact_identity.REPO_ROOT.resolve()
    manifest: dict[str, str] = {}
    for path in modules:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise ReceiptBindingError(f"implementation module is outside repository: {resolved}") from exc
        safe = artifact_identity.resolve_repo_file(relative)
        if safe is None:
            raise ReceiptBindingError(f"implementation module does not resolve safely: {relative}")
        manifest[relative] = hashlib.sha256(safe.read_bytes()).hexdigest()
    return dict(sorted(manifest.items()))


def run_strict_json_acceptance() -> int:
    failures = 0
    for case_id, raw in STRICT_JSON_REJECTION_CASES:
        try:
            decode_json(raw, case_id)
        except ReceiptBindingError:
            print(f"PASS {case_id} expected=REJECT actual=REJECT")
        else:
            failures += 1
            print(f"FAIL {case_id} expected=REJECT actual=ACCEPT")
    return failures


def run_snapshot_isolation_acceptance() -> tuple[int, int]:
    failures = 0
    cases = 0
    with tempfile.TemporaryDirectory(prefix="life-sf-race-src-") as src_tmp:
        src = Path(src_tmp)

        cases += 1
        source_path = src / "program.py"
        source_a = b'print("A")\n'
        source_path.write_bytes(source_a)
        observed = source_path.read_bytes()
        with tempfile.TemporaryDirectory(prefix="life-sf-race-snap-") as snap_tmp:
            snap = Path(snap_tmp)
            virtual = snap / "program.py"
            virtual.write_bytes(observed)
            os.chmod(virtual, 0o400)
            source_path.write_bytes(b'print("B")\n')
            completed = run_source_bytes(observed, virtual, snap)
            ok = completed.returncode == 0 and completed.stdout == b"A\n"
        print(f"{'PASS' if ok else 'FAIL'} snapshot_executable_replacement_isolated")
        failures += 0 if ok else 1

        cases += 1
        main_path = src / "main.py"
        dep_path = src / "dep.py"
        main_bytes = b'import dep\nprint(dep.VALUE)\n'
        dep_a = b'VALUE = "A"\n'
        main_path.write_bytes(main_bytes)
        dep_path.write_bytes(dep_a)
        observed_main = main_path.read_bytes()
        observed_dep = dep_path.read_bytes()
        with tempfile.TemporaryDirectory(prefix="life-sf-race-dep-") as snap_tmp:
            snap = Path(snap_tmp)
            virtual_main = snap / "main.py"
            virtual_dep = snap / "dep.py"
            virtual_main.write_bytes(observed_main)
            virtual_dep.write_bytes(observed_dep)
            os.chmod(virtual_main, 0o400)
            os.chmod(virtual_dep, 0o400)
            dep_path.write_bytes(b'VALUE = "B"\n')
            completed = run_source_bytes(observed_main, virtual_main, snap)
            ok = completed.returncode == 0 and completed.stdout == b"A\n"
        print(f"{'PASS' if ok else 'FAIL'} snapshot_dependency_replacement_isolated")
        failures += 0 if ok else 1
    return cases, failures


def main() -> int:
    if os.environ.get(PROVENANCE_STAGE_ENV) != PROVENANCE_STAGE_VALUE:
        print(
            "CONTRACT_ERROR: receipt execution binding inner runner requires provenance wrapper",
            file=sys.stderr,
        )
        return 2
    try:
        start_manifest = implementation_manifest()
        parser_failures = run_strict_json_acceptance()
        snapshot_total, snapshot_failures = run_snapshot_isolation_acceptance()
        request_schema, decision_kinds = load_request_schema()
        document, acceptance_sha256 = load_json(ACCEPTANCE_PATH)
        fixture, cases = validate_acceptance_document(document, decision_kinds)
        baseline = issue_candidate(fixture)
        if not structural_eligible(baseline, request_schema, decision_kinds):
            raise ReceiptBindingError("issued baseline must satisfy structural eligibility")
        if not consumable(baseline, fixture, request_schema, decision_kinds):
            raise ReceiptBindingError("issued baseline must be CONSUMABLE")
    except (
        OSError,
        KeyError,
        TypeError,
        artifact_identity.ArtifactIdentityError,
        contract_reference.EligibilityError,
        contract_reference.control_request.ContractError,
        ReceiptBindingError,
    ) as exc:
        print(f"CONTRACT_ERROR: {exc}", file=sys.stderr)
        return 2

    failures = parser_failures + snapshot_failures
    structural_guard_failures = 0
    for case in cases:
        candidate = copy.deepcopy(baseline)
        try:
            for mutation in case["mutations"]:
                apply_mutation(candidate, mutation, decision_kinds)
            actual_structural = structural_eligible(candidate, request_schema, decision_kinds)
            actual_consumable = consumable(candidate, fixture, request_schema, decision_kinds)
        except (KeyError, TypeError, ReceiptBindingError) as exc:
            print(f"CONTRACT_ERROR: {case['case_id']}: {exc}", file=sys.stderr)
            return 2

        expected_consumable = EXPECTED_OUTCOMES[case["expected"]]
        guard_ok = (not case["require_structural_eligible"]) or actual_structural
        status = "PASS" if actual_consumable == expected_consumable and guard_ok else "FAIL"
        if not guard_ok:
            structural_guard_failures += 1
        if status == "FAIL":
            failures += 1
        actual = "CONSUMABLE" if actual_consumable else "UNCONSUMABLE"
        structural = "ELIGIBLE" if actual_structural else "INELIGIBLE"
        print(
            f"{status} {case['case_id']} expected={case['expected']} actual={actual} "
            f"structural={structural} require_structural_eligible={str(case['require_structural_eligible']).lower()}"
        )

    try:
        end_manifest = implementation_manifest()
        if not canonical_equal(start_manifest, end_manifest):
            raise ReceiptBindingError("implementation files changed during acceptance execution")
    except ReceiptBindingError as exc:
        print(f"CONTRACT_ERROR: {exc}", file=sys.stderr)
        return 2

    result = "PASS" if failures == 0 else "FAIL"
    runner_rel = Path(__file__).resolve().relative_to(artifact_identity.REPO_ROOT.resolve()).as_posix()
    manifest_sha256 = hashlib.sha256(canonical_bytes(start_manifest)).hexdigest()
    baseline_envelope_sha256 = hashlib.sha256(canonical_bytes(baseline["receipt_envelopes"])).hexdigest()
    print(
        json.dumps(
            {
                "contract_id": document["contract_id"],
                "acceptance_artifact_sha256": acceptance_sha256,
                "runner_sha256": start_manifest[runner_rel],
                "implementation_manifest": start_manifest,
                "implementation_manifest_sha256": manifest_sha256,
                "baseline_receipt_envelopes_sha256": baseline_envelope_sha256,
                "validation_receipt_id": baseline["eligibility"]["validation_receipt"]["receipt_id"],
                "test_receipt_id": baseline["eligibility"]["test_receipt"]["receipt_id"],
                "strict_json_cases_total": len(STRICT_JSON_REJECTION_CASES),
                "strict_json_cases_failed": parser_failures,
                "snapshot_cases_total": snapshot_total,
                "snapshot_cases_failed": snapshot_failures,
                "cases_total": len(cases),
                "cases_failed": failures - parser_failures - snapshot_failures,
                "structural_guard_failures": structural_guard_failures,
                "result": result,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
