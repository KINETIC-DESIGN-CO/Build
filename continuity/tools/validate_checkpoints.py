#!/usr/bin/env python3
from __future__ import annotations

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


def fail(code: str, message: str) -> None:
    ERRORS.append(f"{code}: {message}")


def load_schema(rel: str):
    before = len(vc.ERRORS)
    schema = vc.load_and_validate_schema(ROOT / rel)
    if len(vc.ERRORS) > before:
        return None
    return schema


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
        if checkpoint_schema is not None:
            vc.validate_instance_against_schema(record, checkpoint_schema, str(path.relative_to(ROOT)))
        if record.get("checkpoint_id") != path.stem:
            fail("CP006_FILENAME", f"{path.name} checkpoint_id must equal filename stem")
        for ref in record.get("directive_refs", []):
            if ref not in directive_ids:
                fail("CP005_REFERENCE", f"{path.name} references missing directive {ref}")
        for ref in record.get("decision_rationale_refs", []):
            if ref not in rationale_ids:
                fail("CP005_REFERENCE", f"{path.name} references missing rationale {ref}")
        for operation in record.get("operation_results", []):
            if isinstance(operation, dict) and operation.get("readback_state") == "VERIFIED" and operation.get("result") != "SUCCESS":
                fail("CP007_READBACK", f"{path.name} VERIFIED readback requires SUCCESS result")

        created_at = parse_datetime(record.get("created_at"), f"{path.name}.created_at")
        if (
            goal_snapshot_enforcement is not None
            and created_at is not None
            and created_at >= goal_snapshot_enforcement
        ):
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
        ):
            if step not in bootstrap.get("resume_algorithm", []):
                fail("CP009_BOOTSTRAP", f"bootstrap resume_algorithm missing {step}")
        if "EVALUATE_ACTIVE_GOAL_PATH" not in bootstrap.get("resume_algorithm", []):
            fail("CP009_BOOTSTRAP", "bootstrap resume_algorithm missing EVALUATE_ACTIVE_GOAL_PATH")
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
