#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_continuity as vc

CONT = ROOT / "continuity"
ERRORS: list[str] = []

LEGACY_CHECKPOINT_BLOBS = {
    "continuity/checkpoints/CP-000001-31ed3239.json": "273b968b34d7b78a510fa57e992c633bae73415d",
    "continuity/checkpoints/CP-000001-4e72b93a.json": "0f1767efa5ae64f263604f26f6fd1a7b31e1b176",
    "continuity/checkpoints/CP-000001-5ef4a72c.json": "57b128f2204066a541bb79fa0940c2a6db2835cb",
    "continuity/checkpoints/CP-000001-a31f7d2c.json": "26f27a0678e61f7b73a6a9b41adb856a7980878c",
    "continuity/checkpoints/CP-000001-b7e2a91c.json": "f94fe1f225a2bd52f8d650ff14332c8d649720d9",
    "continuity/checkpoints/CP-000001-d60e89a5.json": "45d03be1c7b3b5593d837832e3e54701c8cdf2bc",
    "continuity/checkpoints/CP-000002-4b8c7d31.json": "625cff5e2bb9902a94ee29175186dc1d0d2549d4",
    "continuity/checkpoints/CP-000002-7ac41e9b.json": "86a84aae8241df48971ee52509d523d182aa9401",
    "continuity/checkpoints/CP-000002-7e1c4a90.json": "18d96e6c8e999e3d7817b5ee87d16c4dc81dd8a9",
    "continuity/checkpoints/CP-000002-7f3a2c91.json": "6ea17fe8f0c1529a071b44da677b05850ba7d953",
    "continuity/checkpoints/CP-000002-a2622ab0.json": "621dd8c05c44496b7f2e080cabad3e6100afdb43",
    "continuity/checkpoints/CP-000002-a61d9b73.json": "ecb5b212c83973f01c1a23fc72df05757520a513",
    "continuity/checkpoints/CP-000002-fd37f38c.json": "0dc2c034394adeebf91f631cc6e9571f7eb7acd7",
    "continuity/checkpoints/CP-000003-91c64a2e.json": "611672de8a21606ad4afcfd314792206a17de25f",
    "continuity/checkpoints/CP-000003-92bfa7c4.json": "af9a878ab6f2b4441bb4185a94d8b6d9ca3b9f5c",
    "continuity/checkpoints/CP-000003-9f32a6c1.json": "985316afa14ef5093cc908f761e650836310b3c1",
    "continuity/checkpoints/CP-000003-f47c0e62.json": "43c2480029c1aa162374a9dd34a193dbbf80c90a",
    "continuity/checkpoints/CP-000004-38c1639d.json": "338d16811d3b54802788c10e1a80726065fb443c",
    "continuity/checkpoints/CP-000004-9a2d60d0.json": "534a47b2111bf94706f0e09356e09b06d79bac5a",
    "continuity/checkpoints/CP-000004-b28f91c4.json": "7d273fab1191b4593bacd12e28ff9176c1eca22e",
    "continuity/checkpoints/CP-000006-4c95292a.json": "e8c4b25f5cc9ddacdabe789abcc02790d5fcb136",
    "continuity/checkpoints/CP-000008-41b7c2e9.json": "7e73de8ddb2413e46a009e4c26787cea61ca4e45",
    "continuity/checkpoints/CP-000009-75f2a392.json": "a7f702e3d6ee3363d801117a7119f1bed9f898c8",
    "continuity/checkpoints/CP-000010-f63c26bb.json": "dd4e225bc8eaa60701ff769495ba09ada4d47e12",
    "continuity/checkpoints/CP-000011-05d67e48.json": "7cd46f2a00d976c350e2484b16187f1588fd4b0c",
    "continuity/checkpoints/CP-000011-5d12caaa.json": "58254fcecb6fb62178eedeff786d7b5f283ff4b4",
    "continuity/checkpoints/CP-000012-19e5c808.json": "f60de757572c5bdbd2adbbdcd9dc217c1cd6e47d2",
    "continuity/checkpoints/CP-000012-ef5f7857.json": "3cc113f8d74eeb05ccb88dda24afb532f1cfac74",
    "continuity/checkpoints/CP-000013-c2f3ad18.json": "86120ee5d5a91df8182377de1101611c61da5829",
    "continuity/checkpoints/CP-000013-daf49e42.json": "2c160e77b818f7eccb591952b21dd5e4c2434daf",
    "continuity/checkpoints/CP-000014-6f3b4334.json": "62c889970eac2812757f75d518e0f688bc05a169",
}
LEGACY_CHECKPOINT_ALLOWED_MISMATCH_CODES = frozenset({
    "C011_SCHEMA_INSTANCE",
    "C010_FORMAT",
    "CP010_GOAL",
    "CP007_READBACK",
})


def fail(code: str, message: str) -> None:
    ERRORS.append(f"{code}: {message}")


def load_schema(rel: str):
    before = len(vc.ERRORS)
    schema = vc.load_and_validate_schema(ROOT / rel)
    if len(vc.ERRORS) > before:
        return None
    return schema



def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()


def is_legacy_checkpoint_compatible(path: Path, root: Path = ROOT) -> bool:
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return False
    expected = LEGACY_CHECKPOINT_BLOBS.get(rel)
    return expected is not None and git_blob_sha(path) == expected

def parse_datetime(value, label: str):
    if not isinstance(value, str):
        fail("CP010_GOAL", f"{label} must be RFC3339 date-time")
        return None
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        fail("CP010_GOAL", f"{label} must be RFC3339 date-time")
        return None


def validate_jsonl_records(path: Path, schema, label: str) -> list[dict]:
    rows = vc.load_jsonl(path)
    if schema is not None:
        for index, row in enumerate(rows, 1):
            vc.validate_instance_against_schema(row, schema, f"{label} line {index}")
    return rows


def main() -> int:
    vc.ERRORS.clear()

    policy = vc.load_json(CONT / "checkpoint-policy.json")
    template = vc.load_json(CONT / "checkpoint-template.json")
    goal_snapshot_enforcement = None
    if not isinstance(policy, dict) or not isinstance(template, dict):
        fail("CP001_LOAD", "checkpoint policy and template must be JSON objects")
    else:
        if policy.get("checkpoint_template_path") != "continuity/checkpoint-template.json":
            fail("CP002_POLICY", "checkpoint_template_path mismatch")
        if policy.get("checkpoint_schema_path") != "continuity/checkpoint.schema.json":
            fail("CP002_POLICY", "checkpoint_schema_path mismatch")
        if template.get("checkpoint_schema_path") != policy.get("checkpoint_schema_path"):
            fail("CP002_POLICY", "template checkpoint_schema_path must match policy")
        if template.get("policy_path") != "continuity/checkpoint-policy.json":
            fail("CP002_POLICY", "template policy_path mismatch")
        if policy.get("checkpoint_authority") != "EVIDENCE_ONLY" or template.get("checkpoint_authority") != "EVIDENCE_ONLY":
            fail("CP003_AUTHORITY", "checkpoint policy/template authority must be EVIDENCE_ONLY")
        if policy.get("runtime_control_authority") != "NONE" or template.get("runtime_control_authority") != "NONE":
            fail("CP003_AUTHORITY", "checkpoint policy/template runtime authority must be NONE")
        goal_snapshot_enforcement = parse_datetime(
            policy.get("goal_snapshot_enforcement_utc"),
            "checkpoint-policy.goal_snapshot_enforcement_utc",
        )
        if policy.get("goal_snapshot_rule") != "CHECKPOINT_CREATED_AT_UTC_GTE_GOAL_SNAPSHOT_ENFORCEMENT_UTC_MUST_INCLUDE_GOAL_SNAPSHOT_WITH_ROOT_ACTIVE_AND_EXACT_ACTIVE_PATH_AS_HISTORICAL_OBSERVATION_ONLY":
            fail("CP002_POLICY", "goal_snapshot_rule mismatch")

    policy_schema = load_schema("continuity/schema/checkpoint-policy.schema.json")
    template_schema = load_schema("continuity/schema/checkpoint-template.schema.json")
    checkpoint_schema = load_schema("continuity/checkpoint.schema.json")
    directive_schema = load_schema("continuity/directive-record.schema.json")
    rationale_schema = load_schema("continuity/decision-rationale.schema.json")

    if policy is not None and policy_schema is not None:
        vc.validate_instance_against_schema(policy, policy_schema, "continuity/checkpoint-policy.json")
    if template is not None and template_schema is not None:
        vc.validate_instance_against_schema(template, template_schema, "continuity/checkpoint-template.json")

    directives = validate_jsonl_records(CONT / "directive-ledger.jsonl", directive_schema, "continuity/directive-ledger.jsonl")
    directive_ids: set[str] = set()
    for row in directives:
        rid = row.get("id") if isinstance(row, dict) else None
        if rid in directive_ids:
            fail("CP004_DUPLICATE", f"duplicate directive id {rid}")
        if isinstance(rid, str):
            directive_ids.add(rid)
    for row in directives:
        if not isinstance(row, dict):
            continue
        for ref in row.get("supersedes", []):
            if ref == row.get("id") or ref not in directive_ids:
                fail("CP005_REFERENCE", f"directive {row.get('id')} invalid supersedes reference {ref}")

    rationales = validate_jsonl_records(CONT / "decision-rationale.jsonl", rationale_schema, "continuity/decision-rationale.jsonl")
    rationale_ids: set[str] = set()
    for row in rationales:
        rid = row.get("id") if isinstance(row, dict) else None
        if rid in rationale_ids:
            fail("CP004_DUPLICATE", f"duplicate rationale id {rid}")
        if isinstance(rid, str):
            rationale_ids.add(rid)
        if isinstance(row, dict):
            for ref in row.get("directive_ids", []):
                if ref not in directive_ids:
                    fail("CP005_REFERENCE", f"rationale {rid} references missing directive {ref}")

    placement = vc.load_json(ROOT / "governance/placement-policy.json")
    if isinstance(policy, dict) and isinstance(placement, dict):
        if policy.get("control_decision_kinds_forbidden_from_checkpoint_authority") != placement.get("control_decision_kinds"):
            fail("CP003_AUTHORITY", "checkpoint forbidden control kinds must exactly equal placement-policy control_decision_kinds")

    pattern = None
    if isinstance(policy, dict):
        try:
            pattern = re.compile(str(policy.get("checkpoint_filename_pattern", "")))
        except re.error as exc:
            fail("CP002_POLICY", f"checkpoint filename pattern invalid: {exc}")

    checkpoints: list[dict] = []
    for path in sorted((CONT / "checkpoints").glob("CP-*.json")):
        if pattern is not None and pattern.fullmatch(path.name) is None:
            fail("CP006_FILENAME", f"checkpoint filename rejected by policy: {path.name}")
        record = vc.load_json(path)
        if not isinstance(record, dict):
            continue
        checkpoints.append(record)
        legacy_compatible = is_legacy_checkpoint_compatible(path)
        if checkpoint_schema is not None and not legacy_compatible:
            vc.validate_instance_against_schema(record, checkpoint_schema, str(path.relative_to(ROOT)))
        if record.get("checkpoint_id") != path.stem:
            fail("CP006_FILENAME", f"{path.name} checkpoint_id must equal filename stem")
        for ref in record.get("directive_refs", []):
            if ref not in directive_ids:
                fail("CP005_REFERENCE", f"{path.name} references missing directive {ref}")
        for ref in record.get("decision_rationale_refs", []):
            if ref not in rationale_ids:
                fail("CP005_REFERENCE", f"{path.name} references missing rationale {ref}")
        if not legacy_compatible:
            for operation in record.get("operation_results", []):
                if isinstance(operation, dict) and operation.get("readback_state") == "VERIFIED" and operation.get("result") != "SUCCESS":
                    fail("CP007_READBACK", f"{path.name} VERIFIED readback requires SUCCESS result")

            created_at = parse_datetime(record.get("created_at"), f"{path.name}.created_at")
            if goal_snapshot_enforcement is not None and created_at is not None and created_at >= goal_snapshot_enforcement:
                snapshot = record.get("goal_snapshot")
                if not isinstance(snapshot, dict):
                    fail("CP010_GOAL", f"{path.name} requires goal_snapshot after enforcement")
                else:
                    active_path = snapshot.get("active_path")
                    root_goal = snapshot.get("active_root_goal_id")
                    active_goal = snapshot.get("active_goal_id")
                    if not isinstance(active_path, list) or not active_path:
                        fail("CP010_GOAL", f"{path.name} goal_snapshot.active_path must be nonempty")
                    else:
                        if active_path[0] != root_goal:
                            fail("CP010_GOAL", f"{path.name} goal_snapshot.active_path must start at active_root_goal_id")
                        if active_path[-1] != active_goal:
                            fail("CP010_GOAL", f"{path.name} goal_snapshot.active_path must end at active_goal_id")
                    if snapshot.get("authority") != "HISTORICAL_OBSERVATION_ONLY":
                        fail("CP010_GOAL", f"{path.name} goal_snapshot authority mismatch")

    if not checkpoints:
        fail("CP008_REQUIRED", "at least one CP-* checkpoint must exist")

    required_paths = [
        "continuity/checkpoint-policy.json",
        "continuity/checkpoint-template.json",
        "continuity/directive-ledger.jsonl",
        "continuity/decision-rationale.jsonl",
        "continuity/checkpoint.schema.json",
        "continuity/directive-record.schema.json",
        "continuity/decision-rationale.schema.json",
    ]
    bootstrap = vc.load_json(CONT / "bootstrap.json")
    if isinstance(bootstrap, dict):
        required_files = set(bootstrap.get("required_files", []))
        for rel in required_paths:
            if rel not in required_files:
                fail("CP009_BOOTSTRAP", f"bootstrap missing checkpoint dependency {rel}")
        for step in (
            "READ_LIVE_COORDINATION_FOR_CHECKPOINT_DISCOVERY",
            "READ_LATEST_WORK_CHECKPOINT",
            "READ_CHECKPOINT_PROVENANCE",
            "EVALUATE_THREAD_LIFECYCLE_BOUNDARY",
        ):
            if step not in bootstrap.get("resume_algorithm", []):
                fail("CP009_BOOTSTRAP", f"bootstrap resume_algorithm missing {step}")
        if "python continuity/tools/validate_checkpoints.py" not in str(bootstrap.get("validation_command", "")):
            fail("CP009_BOOTSTRAP", "bootstrap validation_command missing continuity/tools/validate_checkpoints.py")

    for path in (
        CONT / "checkpoint-policy.json",
        CONT / "checkpoint-template.json",
        CONT / "checkpoint.schema.json",
        CONT / "directive-record.schema.json",
        CONT / "decision-rationale.schema.json",
    ):
        vc.check_format(path, "json")
    vc.check_format(CONT / "directive-ledger.jsonl", "jsonl")
    vc.check_format(CONT / "decision-rationale.jsonl", "jsonl")
    for path in (CONT / "checkpoints").glob("CP-*.json"):
        if not is_legacy_checkpoint_compatible(path):
            vc.check_format(path, "json")

    all_errors = [*vc.ERRORS, *ERRORS]
    if all_errors:
        for error in all_errors:
            print(error, file=sys.stderr)
        return 1
    print("Life checkpoint provenance: VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
