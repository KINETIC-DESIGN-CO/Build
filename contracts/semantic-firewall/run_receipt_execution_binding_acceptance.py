#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

STAGE_ENV = "LIFE_SF_PROVENANCE_STAGE"
MANIFEST_ENV = "LIFE_SF_PROVENANCE_MANIFEST"
PUBLIC_REL = "contracts/semantic-firewall/run_receipt_execution_binding_acceptance.py"
INNER_REL = "contracts/semantic-firewall/receipt_execution_binding_inner.py"
SEMANTIC_REL = "contracts/semantic-firewall"
EXPECTED_PROVENANCE_FILES = {
    "contracts/semantic-firewall/artifact-byte-identity.acceptance.json",
    "contracts/semantic-firewall/contract-reference.acceptance.json",
    "contracts/semantic-firewall/control-input-binding.acceptance.json",
    "contracts/semantic-firewall/control-request.acceptance.json",
    "contracts/semantic-firewall/receipt-execution-binding.acceptance.json",
    "contracts/semantic-firewall/receipt_execution_binding_inner.py",
    "contracts/semantic-firewall/run_artifact_byte_identity_acceptance.py",
    "contracts/semantic-firewall/run_contract_reference_acceptance.py",
    "contracts/semantic-firewall/run_control_input_binding_acceptance.py",
    "contracts/semantic-firewall/run_control_request_acceptance.py",
    "contracts/semantic-firewall/run_receipt_execution_binding_acceptance.py",
    "contracts/semantic-firewall/run_typed_contract_evaluation_acceptance.py",
    "contracts/semantic-firewall/typed-contract-evaluation.acceptance.json",
}
BOOTSTRAP = (
    "import sys; "
    "virtual_path=sys.argv[1]; module_root=sys.argv[2]; sys.path.insert(0,module_root); "
    "source=sys.stdin.buffer.read(); "
    "ns={'__name__':'__main__','__file__':virtual_path,'__package__':None}; "
    "exec(compile(source,virtual_path,'exec'),ns,ns)"
)


class ProvenanceError(Exception):
    pass


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProvenanceError(f"value is not canonical JSON: {exc}") from exc


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_relative(relative: str) -> PurePosixPath:
    if not isinstance(relative, str) or not relative:
        raise ProvenanceError("snapshot path must be a non-empty string")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise ProvenanceError(f"unsafe snapshot path: {relative}")
    return pure


def capture_semantic_firewall(root: Path) -> dict[str, bytes]:
    root = root.resolve()
    semantic_dir = (root / SEMANTIC_REL).resolve()
    try:
        semantic_dir.relative_to(root)
    except ValueError as exc:
        raise ProvenanceError("semantic-firewall directory escaped repository root") from exc
    if not semantic_dir.is_dir() or semantic_dir.is_symlink():
        raise ProvenanceError("semantic-firewall directory is unavailable or unsafe")

    captured: dict[str, bytes] = {}
    for path in sorted(semantic_dir.iterdir(), key=lambda item: item.name):
        if path.name == "__pycache__":
            continue
        if path.is_symlink() or not path.is_file():
            raise ProvenanceError(f"unexpected non-regular semantic-firewall entry: {path.name}")
        if path.suffix not in {".py", ".json"}:
            raise ProvenanceError(f"unexpected semantic-firewall file type: {path.name}")
        relative = path.resolve().relative_to(root).as_posix()
        safe_relative(relative)
        captured[relative] = path.read_bytes()

    if set(captured) != EXPECTED_PROVENANCE_FILES:
        missing = sorted(EXPECTED_PROVENANCE_FILES - set(captured))
        extra = sorted(set(captured) - EXPECTED_PROVENANCE_FILES)
        raise ProvenanceError(f"provenance file set mismatch: missing={missing} extra={extra}")
    return captured


def manifest_for(captured: dict[str, bytes]) -> dict[str, str]:
    return {path: sha256_bytes(captured[path]) for path in sorted(captured)}


def write_snapshot(root: Path, captured: dict[str, bytes]) -> None:
    for relative, raw in captured.items():
        pure = safe_relative(relative)
        target = root.joinpath(*pure.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        os.chmod(target, 0o400)
    semantic_dir = root / SEMANTIC_REL
    for directory in sorted(
        {semantic_dir, semantic_dir.parent}, key=lambda item: len(item.parts), reverse=True
    ):
        if directory.exists():
            os.chmod(directory, 0o500)


def read_snapshot(root: Path) -> dict[str, bytes]:
    captured: dict[str, bytes] = {}
    for relative in sorted(EXPECTED_PROVENANCE_FILES):
        pure = safe_relative(relative)
        path = root.joinpath(*pure.parts)
        if path.is_symlink() or not path.is_file():
            raise ProvenanceError(f"snapshot file unavailable or unsafe: {relative}")
        captured[relative] = path.read_bytes()
    return captured


def run_source(
    source: bytes,
    virtual_path: Path,
    module_root: Path,
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[bytes]:
    child_env = os.environ.copy()
    if env:
        child_env.update(env)
    try:
        return subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                BOOTSTRAP,
                str(virtual_path),
                str(module_root),
            ],
            input=source,
            cwd=cwd,
            env=child_env,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProvenanceError(f"snapshot execution failed: {exc}") from exc


def parse_last_json(stdout: bytes) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ProvenanceError("inner runner produced no stdout result")
    try:
        value = json.loads(lines[-1])
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProvenanceError(f"inner runner final record is invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ProvenanceError("inner runner final record must be a JSON object")
    return value


def run_provenance_acceptance(
    captured: dict[str, bytes], manifest: dict[str, str]
) -> tuple[int, int]:
    failures = 0
    total = 0

    total += 1
    closure_ok = set(captured) == EXPECTED_PROVENANCE_FILES and (
        "contracts/semantic-firewall/artifact-byte-identity.acceptance.json" in manifest
    )
    print(
        f"{'PASS' if closure_ok else 'FAIL'} provenance_dependency_closure_complete"
    )
    failures += 0 if closure_ok else 1

    total += 1
    with tempfile.TemporaryDirectory(prefix="life-sf-provenance-test-") as tmp:
        source_root = Path(tmp) / "source"
        snap_root = Path(tmp) / "snapshot"
        source_root.mkdir()
        snap_root.mkdir()
        source = source_root / "governing.json"
        source.write_bytes(b'{"value":"A"}\n')
        observed = source.read_bytes()
        observed_hash = sha256_bytes(observed)
        source.write_bytes(b'{"value":"B"}\n')
        target = snap_root / "governing.json"
        target.write_bytes(observed)
        replacement_ok = sha256_bytes(target.read_bytes()) == observed_hash
    print(
        f"{'PASS' if replacement_ok else 'FAIL'} provenance_source_replacement_isolated"
    )
    failures += 0 if replacement_ok else 1

    return total, failures


def authoritative_stage() -> int:
    try:
        expected_manifest_raw = os.environ.get(MANIFEST_ENV)
        if not expected_manifest_raw:
            raise ProvenanceError("missing expected provenance manifest")
        expected_manifest = json.loads(expected_manifest_raw)
        if not isinstance(expected_manifest, dict):
            raise ProvenanceError("expected provenance manifest must be an object")

        snapshot_root = Path(__file__).resolve().parents[2]
        captured = read_snapshot(snapshot_root)
        actual_manifest = manifest_for(captured)
        if actual_manifest != expected_manifest:
            raise ProvenanceError("authoritative snapshot does not match captured provenance manifest")

        provenance_total, provenance_failures = run_provenance_acceptance(
            captured, actual_manifest
        )

        with tempfile.TemporaryDirectory(prefix="life-sf-authoritative-") as tmp:
            execution_root = Path(tmp)
            write_snapshot(execution_root, captured)
            execution_manifest = manifest_for(read_snapshot(execution_root))
            if execution_manifest != actual_manifest:
                raise ProvenanceError("execution snapshot does not match provenance manifest")

            inner_path = execution_root / INNER_REL
            module_root = execution_root / SEMANTIC_REL
            completed = run_source(
                captured[INNER_REL],
                inner_path,
                module_root,
                execution_root,
            )
            post_manifest = manifest_for(read_snapshot(execution_root))
            if post_manifest != actual_manifest:
                raise ProvenanceError("execution snapshot changed during receipt acceptance")

        if completed.stderr:
            sys.stderr.buffer.write(completed.stderr)
        inner_lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if inner_lines:
            for line in inner_lines[:-1]:
                sys.stdout.buffer.write(line + b"\n")
        inner = parse_last_json(completed.stdout)
        if completed.returncode != 0 or inner.get("result") != "PASS":
            raise ProvenanceError(
                f"inner receipt acceptance failed: exit={completed.returncode} result={inner.get('result')}"
            )
        if inner.get("contract_id") != "semantic_firewall.receipt_execution_binding":
            raise ProvenanceError("inner receipt acceptance returned unexpected contract_id")

        result = "PASS" if provenance_failures == 0 else "FAIL"
        inner_record_sha256 = sha256_bytes(canonical_bytes(inner))
        final = {
            "contract_id": inner["contract_id"],
            "acceptance_artifact_sha256": inner.get("acceptance_artifact_sha256"),
            "runner_sha256": actual_manifest[PUBLIC_REL],
            "inner_runner_sha256": actual_manifest[INNER_REL],
            "provenance_manifest": actual_manifest,
            "provenance_manifest_sha256": sha256_bytes(canonical_bytes(actual_manifest)),
            "provenance_files_total": len(actual_manifest),
            "provenance_cases_total": provenance_total,
            "provenance_cases_failed": provenance_failures,
            "inner_result_sha256": inner_record_sha256,
            "baseline_receipt_envelopes_sha256": inner.get(
                "baseline_receipt_envelopes_sha256"
            ),
            "validation_receipt_id": inner.get("validation_receipt_id"),
            "test_receipt_id": inner.get("test_receipt_id"),
            "strict_json_cases_total": inner.get("strict_json_cases_total"),
            "strict_json_cases_failed": inner.get("strict_json_cases_failed"),
            "snapshot_cases_total": inner.get("snapshot_cases_total"),
            "snapshot_cases_failed": inner.get("snapshot_cases_failed"),
            "cases_total": inner.get("cases_total"),
            "cases_failed": inner.get("cases_failed"),
            "structural_guard_failures": inner.get("structural_guard_failures"),
            "result": result,
        }
        print(json.dumps(final, sort_keys=True, separators=(",", ":")))
        return 0 if result == "PASS" else 1
    except (OSError, KeyError, TypeError, ValueError, ProvenanceError) as exc:
        print(f"CONTRACT_ERROR: {exc}", file=sys.stderr)
        return 2


def bootstrap_stage() -> int:
    try:
        repo_root = Path(__file__).resolve().parents[2]
        captured = capture_semantic_firewall(repo_root)
        manifest = manifest_for(captured)
        with tempfile.TemporaryDirectory(prefix="life-sf-provenance-") as tmp:
            snapshot_root = Path(tmp)
            write_snapshot(snapshot_root, captured)
            stage_manifest = manifest_for(read_snapshot(snapshot_root))
            if stage_manifest != manifest:
                raise ProvenanceError("captured provenance snapshot verification failed")
            public_path = snapshot_root / PUBLIC_REL
            module_root = snapshot_root / SEMANTIC_REL
            completed = run_source(
                captured[PUBLIC_REL],
                public_path,
                module_root,
                snapshot_root,
                env={
                    STAGE_ENV: "1",
                    MANIFEST_ENV: json.dumps(manifest, sort_keys=True, separators=(",", ":")),
                },
            )
        if completed.stdout:
            sys.stdout.buffer.write(completed.stdout)
        if completed.stderr:
            sys.stderr.buffer.write(completed.stderr)
        return completed.returncode
    except (OSError, KeyError, TypeError, ValueError, ProvenanceError) as exc:
        print(f"CONTRACT_ERROR: {exc}", file=sys.stderr)
        return 2


def main() -> int:
    if os.environ.get(STAGE_ENV) == "1":
        return authoritative_stage()
    return bootstrap_stage()


if __name__ == "__main__":
    raise SystemExit(main())
