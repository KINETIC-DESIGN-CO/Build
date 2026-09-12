#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONT = ROOT / "continuity"
GOV = ROOT / "governance"
ERRORS: list[str] = []

DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
SUPPORTED_SCHEMA_KEYWORDS = {
    "$schema",
    "$id",
    "title",
    "type",
    "additionalProperties",
    "required",
    "properties",
    "const",
    "enum",
    "minimum",
    "minLength",
    "minItems",
    "maxItems",
    "uniqueItems",
    "items",
    "pattern",
    "format",
    "minProperties",
}
SUPPORTED_JSON_TYPES = {"object", "array", "string", "integer", "null"}


def fail(code: str, msg: str) -> None:
    ERRORS.append(f"{code}: {msg}")


def no_dupe_object(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate JSON key: {k}")
        out[k] = v
    return out


def load_json(path: Path):
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as e:
        fail("C001_JSON", f"{path.relative_to(ROOT)} unreadable: {e}")
        return None
    try:
        return json.loads(raw, object_pairs_hook=no_dupe_object)
    except Exception as e:
        fail("C001_JSON", f"{path.relative_to(ROOT)} invalid JSON: {e}")
        return None


def load_jsonl(path: Path):
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as e:
        fail("C001_JSON", f"{path.relative_to(ROOT)} unreadable: {e}")
        return []
    rows = []
    for i, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            fail("C010_FORMAT", f"{path.relative_to(ROOT)} has blank line {i}")
            continue
        try:
            rows.append(json.loads(line, object_pairs_hook=no_dupe_object))
        except Exception as e:
            fail("C001_JSON", f"{path.relative_to(ROOT)} line {i} invalid JSON: {e}")
    return rows


def exact_keys(obj, required, allowed, label):
    if not isinstance(obj, dict):
        fail("C002_SCHEMA", f"{label} must be object")
        return
    missing = set(required) - set(obj)
    extra = set(obj) - set(allowed)
    if missing:
        fail("C002_SCHEMA", f"{label} missing keys: {sorted(missing)}")
    if extra:
        fail("C002_SCHEMA", f"{label} unknown keys: {sorted(extra)}")


def is_rfc3339_utc(v):
    if not isinstance(v, str) or not v.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(v[:-1] + "+00:00")
        return True
    except ValueError:
        return False


def is_json_schema_datetime(v):
    if not isinstance(v, str):
        return False
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})", v):
        return False
    try:
        datetime.fromisoformat(v[:-1] + "+00:00" if v.endswith("Z") else v)
        return True
    except ValueError:
        return False


def check_format(path: Path, kind: str):
    try:
        raw = path.read_bytes()
    except Exception:
        return
    if b"\r\n" in raw or b"\r" in raw:
        fail("C010_FORMAT", f"{path.relative_to(ROOT)} must use LF line endings")
    if not raw.endswith(b"\n"):
        fail("C010_FORMAT", f"{path.relative_to(ROOT)} must end with newline")
    if kind == "json":
        obj = load_json(path)
        if obj is not None:
            expected = (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode()
            if raw != expected:
                fail("C010_FORMAT", f"{path.relative_to(ROOT)} is not canonical indent=2 JSON")
    elif kind == "jsonl":
        rows = load_jsonl(path)
        if rows:
            expected = (
                "\n".join(
                    json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows
                )
                + "\n"
            ).encode()
            if raw != expected:
                fail("C010_FORMAT", f"{path.relative_to(ROOT)} is not canonical compact JSONL")


def json_fingerprint(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def json_equal(left, right):
    return json_fingerprint(left) == json_fingerprint(right)


def type_matches(value, type_name):
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "null":
        return value is None
    return False


def validate_schema_definition(schema, label, schema_path="$"):
    if not isinstance(schema, dict):
        fail("C011_SCHEMA_DEFINITION", f"{label} {schema_path} must be a schema object")
        return

    unsupported = sorted(set(schema) - SUPPORTED_SCHEMA_KEYWORDS)
    if unsupported:
        fail(
            "C011_SCHEMA_DEFINITION",
            f"{label} {schema_path} uses unsupported keywords: {unsupported}",
        )

    if "$schema" in schema and schema["$schema"] != DRAFT_2020_12:
        fail(
            "C011_SCHEMA_DEFINITION",
            f"{label} {schema_path} must declare JSON Schema Draft 2020-12",
        )
    if "$id" in schema and not isinstance(schema["$id"], str):
        fail("C011_SCHEMA_DEFINITION", f"{label} {schema_path} $id must be string")
    if "title" in schema and not isinstance(schema["title"], str):
        fail("C011_SCHEMA_DEFINITION", f"{label} {schema_path} title must be string")

    declared_type = schema.get("type")
    if declared_type is not None:
        if isinstance(declared_type, str):
            types = [declared_type]
        elif (
            isinstance(declared_type, list)
            and declared_type
            and all(isinstance(item, str) for item in declared_type)
            and len(declared_type) == len(set(declared_type))
        ):
            types = declared_type
        else:
            fail(
                "C011_SCHEMA_DEFINITION",
                f"{label} {schema_path} type must be a string or nonempty unique string array",
            )
            types = []
        unknown_types = sorted(set(types) - SUPPORTED_JSON_TYPES)
        if unknown_types:
            fail(
                "C011_SCHEMA_DEFINITION",
                f"{label} {schema_path} uses unsupported JSON types: {unknown_types}",
            )

    if "additionalProperties" in schema and not isinstance(
        schema["additionalProperties"], bool
    ):
        fail(
            "C011_SCHEMA_DEFINITION",
            f"{label} {schema_path} supports only boolean additionalProperties",
        )
    if "required" in schema and (
        not isinstance(schema["required"], list)
        or not all(isinstance(item, str) for item in schema["required"])
        or len(schema["required"]) != len(set(schema["required"]))
    ):
        fail(
            "C011_SCHEMA_DEFINITION",
            f"{label} {schema_path} required must be a unique string array",
        )
    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, dict):
            fail(
                "C011_SCHEMA_DEFINITION",
                f"{label} {schema_path} properties must be object",
            )
        else:
            for name, subschema in properties.items():
                validate_schema_definition(
                    subschema, label, f"{schema_path}.properties[{name!r}]"
                )
    if "items" in schema:
        validate_schema_definition(schema["items"], label, f"{schema_path}.items")

    if "minimum" in schema and (
        not isinstance(schema["minimum"], (int, float))
        or isinstance(schema["minimum"], bool)
    ):
        fail(
            "C011_SCHEMA_DEFINITION",
            f"{label} {schema_path} minimum must be numeric",
        )
    for keyword in ("minLength", "minItems", "maxItems", "minProperties"):
        if keyword in schema and (
            not isinstance(schema[keyword], int)
            or isinstance(schema[keyword], bool)
            or schema[keyword] < 0
        ):
            fail(
                "C011_SCHEMA_DEFINITION",
                f"{label} {schema_path} {keyword} must be integer >= 0",
            )
    if "uniqueItems" in schema and not isinstance(schema["uniqueItems"], bool):
        fail(
            "C011_SCHEMA_DEFINITION",
            f"{label} {schema_path} uniqueItems must be boolean",
        )
    if "pattern" in schema:
        if not isinstance(schema["pattern"], str):
            fail(
                "C011_SCHEMA_DEFINITION",
                f"{label} {schema_path} pattern must be string",
            )
        else:
            try:
                re.compile(schema["pattern"])
            except re.error as e:
                fail(
                    "C011_SCHEMA_DEFINITION",
                    f"{label} {schema_path} pattern is invalid regex: {e}",
                )
    if "format" in schema and schema["format"] != "date-time":
        fail(
            "C011_SCHEMA_DEFINITION",
            f"{label} {schema_path} unsupported format: {schema['format']!r}",
        )
    if "enum" in schema:
        enum_values = schema["enum"]
        if not isinstance(enum_values, list) or not enum_values:
            fail(
                "C011_SCHEMA_DEFINITION",
                f"{label} {schema_path} enum must be a nonempty array",
            )
        elif len([json_fingerprint(item) for item in enum_values]) != len(
            set(json_fingerprint(item) for item in enum_values)
        ):
            fail(
                "C011_SCHEMA_DEFINITION",
                f"{label} {schema_path} enum values must be unique",
            )


def validate_instance_against_schema(instance, schema, label, instance_path="$"):
    if not isinstance(schema, dict):
        return

    declared_type = schema.get("type")
    if declared_type is not None:
        types = [declared_type] if isinstance(declared_type, str) else declared_type
        if not isinstance(types, list) or not any(
            type_matches(instance, type_name)
            for type_name in types
            if isinstance(type_name, str)
        ):
            fail(
                "C011_SCHEMA_INSTANCE",
                f"{label} {instance_path} does not match type {declared_type!r}",
            )
            return

    if "const" in schema and not json_equal(instance, schema["const"]):
        fail(
            "C011_SCHEMA_INSTANCE",
            f"{label} {instance_path} does not equal required const",
        )
    if "enum" in schema and not any(json_equal(instance, item) for item in schema["enum"]):
        fail(
            "C011_SCHEMA_INSTANCE",
            f"{label} {instance_path} is not in required enum",
        )

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            fail(
                "C011_SCHEMA_INSTANCE",
                f"{label} {instance_path} is shorter than minLength {schema['minLength']}",
            )
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            fail(
                "C011_SCHEMA_INSTANCE",
                f"{label} {instance_path} does not match pattern {schema['pattern']!r}",
            )
        if schema.get("format") == "date-time" and not is_json_schema_datetime(instance):
            fail(
                "C011_SCHEMA_INSTANCE",
                f"{label} {instance_path} is not RFC3339 date-time",
            )

    if isinstance(instance, int) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            fail(
                "C011_SCHEMA_INSTANCE",
                f"{label} {instance_path} is below minimum {schema['minimum']}",
            )

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            fail(
                "C011_SCHEMA_INSTANCE",
                f"{label} {instance_path} has fewer than {schema['minItems']} items",
            )
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            fail(
                "C011_SCHEMA_INSTANCE",
                f"{label} {instance_path} has more than {schema['maxItems']} items",
            )
        if schema.get("uniqueItems") is True:
            fingerprints = [json_fingerprint(item) for item in instance]
            if len(fingerprints) != len(set(fingerprints)):
                fail(
                    "C011_SCHEMA_INSTANCE",
                    f"{label} {instance_path} items must be unique",
                )
        if "items" in schema:
            for index, item in enumerate(instance):
                validate_instance_against_schema(
                    item, schema["items"], label, f"{instance_path}[{index}]"
                )

    if isinstance(instance, dict):
        if "minProperties" in schema and len(instance) < schema["minProperties"]:
            fail(
                "C011_SCHEMA_INSTANCE",
                f"{label} {instance_path} has fewer than {schema['minProperties']} properties",
            )
        required = schema.get("required", [])
        if isinstance(required, list):
            for name in required:
                if name not in instance:
                    fail(
                        "C011_SCHEMA_INSTANCE",
                        f"{label} {instance_path} missing required property {name!r}",
                    )
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for name, subschema in properties.items():
                if name in instance:
                    validate_instance_against_schema(
                        instance[name],
                        subschema,
                        label,
                        f"{instance_path}.{name}",
                    )
            if schema.get("additionalProperties") is False:
                extras = sorted(set(instance) - set(properties))
                if extras:
                    fail(
                        "C011_SCHEMA_INSTANCE",
                        f"{label} {instance_path} has unknown properties: {extras}",
                    )


def validate_bootstrap(b):
    required = {
        "schema_version",
        "project_id",
        "runtime_control_authority",
        "bundle_version",
        "canonical_repository",
        "required_files",
        "required_read_order",
        "resume_algorithm",
        "continuity_update_event_types",
        "continuity_sync_paths",
        "continuity_sync_rule",
        "validation_command",
    }
    exact_keys(b, required, required, "bootstrap")
    if not isinstance(b, dict):
        return
    if b.get("schema_version") != 1 or b.get("project_id") != "life":
        fail("C002_SCHEMA", "bootstrap schema_version/project_id mismatch")
    if b.get("runtime_control_authority") != "NONE":
        fail("C004_AUTHORITY", "bootstrap runtime_control_authority must be NONE")
    repo = b.get("canonical_repository")
    if repo != {
        "repository_id": 1366835183,
        "full_name": "Vinanonymous/Build",
        "default_branch": "main",
    }:
        fail("C003_TARGET", "bootstrap canonical_repository mismatch")
    required_types = {
        "VINCE_DIRECTIVE",
        "ARCHITECTURE_DECISION",
        "GITHUB_MUTATION",
        "SUPABASE_MUTATION",
        "VERCEL_MUTATION",
        "PROJECT_INSTRUCTION_CHANGE",
        "VERIFICATION_TRANSITION",
        "BLOCKER_TRANSITION",
        "NEXT_ACTION_CHANGE",
        "COMPONENT_TRANSITION",
    }
    if set(b.get("continuity_update_event_types", [])) != required_types:
        fail(
            "C002_SCHEMA",
            "bootstrap continuity_update_event_types must equal the exact required set",
        )
    files = b.get("required_files", [])
    if len(files) != len(set(files)) or not files:
        fail("C002_SCHEMA", "required_files must be nonempty and unique")
    for rel in files:
        if not (ROOT / rel).is_file():
            fail("C002_SCHEMA", f"required file missing: {rel}")
    order = b.get("required_read_order", [])
    if len(order) != len(set(order)) or not order:
        fail("C002_SCHEMA", "required_read_order must be nonempty and unique")
    for rel in order:
        if rel not in files:
            fail("C002_SCHEMA", f"required_read_order path not in required_files: {rel}")


def validate_current(c, decision_by_id):
    required = {
        "schema_version",
        "manifest_revision",
        "project_id",
        "runtime_control_authority",
        "updated_at",
        "objective",
        "phase",
        "current_component",
        "current_status",
        "authorized_targets",
        "current_work",
        "active_decision_ids",
        "retired_decision_ids",
        "open_questions",
        "blockers",
        "last_observed",
        "next_action",
    }
    exact_keys(c, required, required, "current")
    if not isinstance(c, dict):
        return
    if c.get("schema_version") != 1 or c.get("project_id") != "life":
        fail("C002_SCHEMA", "current schema_version/project_id mismatch")
    if (
        not isinstance(c.get("manifest_revision"), int)
        or isinstance(c.get("manifest_revision"), bool)
        or c["manifest_revision"] < 1
    ):
        fail("C009_REVISION", "manifest_revision must be integer >= 1")
    if c.get("runtime_control_authority") != "NONE":
        fail("C004_AUTHORITY", "current runtime_control_authority must be NONE")
    if not is_rfc3339_utc(c.get("updated_at")):
        fail("C010_FORMAT", "current.updated_at must be RFC3339 UTC ending Z")
    if c.get("phase") not in {
        "RESEARCH",
        "DESIGN",
        "IMPLEMENTATION",
        "VERIFICATION",
        "DEPLOYMENT",
        "OPERATIONS",
    }:
        fail("C002_SCHEMA", "current.phase invalid")
    if c.get("current_status") not in {"ACTIVE", "BLOCKED", "COMPLETE"}:
        fail("C002_SCHEMA", "current.current_status invalid")
    if not re.fullmatch(
        r"[a-z0-9]+(?:_[a-z0-9]+)*", str(c.get("current_component", ""))
    ):
        fail("C002_SCHEMA", "current.current_component invalid")
    targets = c.get("authorized_targets", {})
    gh = targets.get("github", {}) if isinstance(targets, dict) else {}
    sb = targets.get("supabase", {}) if isinstance(targets, dict) else {}
    if gh != {
        "repository_id": 1366835183,
        "full_name": "Vinanonymous/Build",
        "visibility": "public",
        "default_branch": "main",
    }:
        fail("C003_TARGET", "current GitHub target mismatch")
    if sb != {
        "project_id": "jnenguxodtgwbskhdsxt",
        "name": "Life",
        "region": "us-west-2",
    }:
        fail("C003_TARGET", "current Supabase target mismatch")
    if isinstance(targets, dict) and targets.get("vercel") is not None:
        fail("C003_TARGET", "current Vercel target must be null until explicitly authorized")
    active = c.get("active_decision_ids", [])
    retired = c.get("retired_decision_ids", [])
    if (
        len(active) != len(set(active))
        or len(retired) != len(set(retired))
        or set(active) & set(retired)
    ):
        fail(
            "C005_ID_DUPLICATE",
            "active/retired decision ID lists overlap or contain duplicates",
        )
    for did in active:
        d = decision_by_id.get(did)
        if d is None or d.get("state") != "ACTIVE":
            fail("C006_REFERENCE", f"active decision {did} missing or not ACTIVE")
    for did in retired:
        d = decision_by_id.get(did)
        if d is None or d.get("state") != "RETIRED":
            fail("C006_REFERENCE", f"retired decision {did} missing or not RETIRED")
    qids = set()
    for q in c.get("open_questions", []):
        if not isinstance(q, dict):
            fail("C002_SCHEMA", "question must be object")
            continue
        exact_keys(
            q,
            {"id", "state", "question", "resolution_decision_id"},
            {"id", "state", "question", "resolution_decision_id"},
            f"question {q.get('id')}",
        )
        qid = q.get("id")
        if qid in qids:
            fail("C005_ID_DUPLICATE", f"duplicate question id {qid}")
        qids.add(qid)
        st = q.get("state")
        rid = q.get("resolution_decision_id")
        if st == "OPEN" and rid is not None:
            fail("C007_QUESTION_STATE", f"{qid} OPEN must have null resolution_decision_id")
        elif st == "RESOLVED":
            if rid is None or rid not in decision_by_id:
                fail(
                    "C007_QUESTION_STATE",
                    f"{qid} RESOLVED must reference existing decision",
                )
        elif st not in {"OPEN", "RESOLVED"}:
            fail("C002_SCHEMA", f"{qid} invalid state")
    bids = set()
    for blocker in c.get("blockers", []):
        if not isinstance(blocker, dict):
            fail("C002_SCHEMA", "blocker must be object")
            continue
        exact_keys(
            blocker,
            {"id", "state", "condition", "clears_when"},
            {"id", "state", "condition", "clears_when"},
            f"blocker {blocker.get('id')}",
        )
        bid = blocker.get("id")
        if bid in bids:
            fail("C005_ID_DUPLICATE", f"duplicate blocker id {bid}")
        bids.add(bid)
        if blocker.get("state") not in {"OPEN", "RESOLVED"}:
            fail("C002_SCHEMA", f"{bid} invalid blocker state")
    na = c.get("next_action", {})
    if isinstance(na, dict):
        exact_keys(
            na,
            {"id", "kind", "target", "description", "authorization_effect"},
            {"id", "kind", "target", "description", "authorization_effect"},
            "next_action",
        )
        if na.get("kind") not in {
            "RESEARCH",
            "READ",
            "DESIGN",
            "IMPLEMENT",
            "VERIFY",
            "MUTATE",
            "DEPLOY",
        }:
            fail("C002_SCHEMA", "next_action.kind invalid")
        if na.get("authorization_effect") != "NONE":
            fail("C004_AUTHORITY", "next_action.authorization_effect must be NONE")


def validate_decisions(rows):
    by_id = {}
    allowed_keys = {
        "id",
        "state",
        "disposition",
        "statement",
        "rationale",
        "evidence",
        "supersedes",
        "recorded_at",
        "runtime_control_authority",
    }
    for d in rows:
        if not isinstance(d, dict):
            fail("C002_SCHEMA", "decision row must be object")
            continue
        exact_keys(d, allowed_keys, allowed_keys, f"decision {d.get('id')}")
        did = d.get("id")
        if not isinstance(did, str) or not re.fullmatch(r"D-[0-9]{4}", did):
            fail("C002_SCHEMA", f"invalid decision id {did}")
            continue
        if did in by_id:
            fail("C005_ID_DUPLICATE", f"duplicate decision id {did}")
        by_id[did] = d
        if d.get("state") not in {"ACTIVE", "RETIRED"}:
            fail("C002_SCHEMA", f"{did} invalid state")
        if d.get("disposition") not in {
            "KEEP",
            "REPLACE",
            "MODIFY",
            "COMBINE",
            "REMOVE",
        }:
            fail("C002_SCHEMA", f"{did} invalid disposition")
        if d.get("runtime_control_authority") != "NONE":
            fail("C004_AUTHORITY", f"{did} authority must be NONE")
        if not is_rfc3339_utc(d.get("recorded_at")):
            fail("C010_FORMAT", f"{did} recorded_at invalid")
        if not isinstance(d.get("evidence"), list) or not d["evidence"]:
            fail("C002_SCHEMA", f"{did} evidence must be nonempty list")
        if not isinstance(d.get("supersedes"), list):
            fail("C002_SCHEMA", f"{did} supersedes must be list")
    for did, d in by_id.items():
        for ref in d.get("supersedes", []):
            if ref not in by_id:
                fail("C006_REFERENCE", f"{did} supersedes missing decision {ref}")
            if ref == did:
                fail("C006_REFERENCE", f"{did} cannot supersede itself")
    return by_id


def validate_events(rows, decision_by_id, allowed_trigger_types):
    seen = set()
    allowed_keys = {
        "id",
        "event_type",
        "occurred_at",
        "summary",
        "targets",
        "result",
        "verification_status",
        "related_decision_ids",
        "runtime_control_authority",
    }
    allowed_events = set(allowed_trigger_types) | {"CONTINUITY_SYNC"}
    for event in rows:
        if not isinstance(event, dict):
            fail("C002_SCHEMA", "event row must be object")
            continue
        exact_keys(event, allowed_keys, allowed_keys, f"event {event.get('id')}")
        eid = event.get("id")
        if not isinstance(eid, str) or not re.fullmatch(r"E-[0-9]{4}", eid):
            fail("C002_SCHEMA", f"invalid event id {eid}")
            continue
        if eid in seen:
            fail("C005_ID_DUPLICATE", f"duplicate event id {eid}")
        seen.add(eid)
        if event.get("event_type") not in allowed_events:
            fail("C002_SCHEMA", f"{eid} invalid event_type")
        if event.get("verification_status") not in {
            "VERIFIED",
            "UNVERIFIED",
            "UNKNOWN",
            "NOT_RUN",
        }:
            fail("C002_SCHEMA", f"{eid} invalid verification_status")
        if event.get("runtime_control_authority") != "NONE":
            fail("C004_AUTHORITY", f"{eid} authority must be NONE")
        if not is_rfc3339_utc(event.get("occurred_at")):
            fail("C010_FORMAT", f"{eid} occurred_at invalid")
        if not isinstance(event.get("targets"), list) or not event["targets"]:
            fail("C002_SCHEMA", f"{eid} targets must be nonempty list")
        for ref in event.get("related_decision_ids", []):
            if ref not in decision_by_id:
                fail("C006_REFERENCE", f"{eid} references missing decision {ref}")


def load_and_validate_schema(schema_path):
    schema = load_json(schema_path)
    if not isinstance(schema, dict):
        return None
    label = str(schema_path.relative_to(ROOT))
    if schema.get("$schema") != DRAFT_2020_12:
        fail(
            "C011_SCHEMA_DEFINITION",
            f"{label} must declare JSON Schema Draft 2020-12",
        )
    if schema.get("additionalProperties") is not False:
        fail(
            "C011_SCHEMA_DEFINITION",
            f"{label} root must set additionalProperties to false",
        )
    validate_schema_definition(schema, label)
    return schema


def validate_schema_governed_artifacts(b, c, drows, erows):
    if not isinstance(b, dict):
        return

    required_files = b.get("required_files", [])
    schema_paths = sorted(
        rel
        for rel in required_files
        if isinstance(rel, str)
        and (
            rel.startswith("continuity/schema/")
            or rel.startswith("governance/schema/")
        )
        and rel.endswith(".schema.json")
    )

    for rel in schema_paths:
        schema_path = ROOT / rel
        schema = load_and_validate_schema(schema_path)
        if schema is None:
            continue

        if rel == "continuity/schema/bootstrap.schema.json":
            if b is not None:
                validate_instance_against_schema(b, schema, "continuity/bootstrap.json")
            continue
        if rel == "continuity/schema/current.schema.json":
            if c is not None:
                validate_instance_against_schema(c, schema, "continuity/current.json")
            continue
        if rel == "continuity/schema/decision.schema.json":
            for index, row in enumerate(drows, 1):
                validate_instance_against_schema(
                    row, schema, f"continuity/decisions.jsonl line {index}"
                )
            continue
        if rel == "continuity/schema/event.schema.json":
            for index, row in enumerate(erows, 1):
                validate_instance_against_schema(
                    row, schema, f"continuity/events.jsonl line {index}"
                )
            continue

        if rel.startswith("continuity/schema/"):
            name = Path(rel).name.removesuffix(".schema.json")
            instance_rel = f"continuity/{name}.json"
        else:
            name = Path(rel).name.removesuffix(".schema.json")
            instance_rel = f"governance/{name}.json"

        if instance_rel not in required_files:
            fail(
                "C011_SCHEMA_BINDING",
                f"{rel} has no bootstrap-required instance {instance_rel}",
            )
            continue
        instance = load_json(ROOT / instance_rel)
        if instance is not None:
            validate_instance_against_schema(instance, schema, instance_rel)


def main():
    b = load_json(CONT / "bootstrap.json")
    c = load_json(CONT / "current.json")
    drows = load_jsonl(CONT / "decisions.jsonl")
    erows = load_jsonl(CONT / "events.jsonl")

    if b is not None:
        validate_bootstrap(b)
    decision_by_id = validate_decisions(drows)
    if c is not None:
        validate_current(c, decision_by_id)
    if b is not None:
        validate_events(
            erows,
            decision_by_id,
            b.get("continuity_update_event_types", []),
        )

    validate_schema_governed_artifacts(b, c, drows, erows)

    for p in CONT.glob("*.json"):
        check_format(p, "json")
    for p in CONT.glob("*.jsonl"):
        check_format(p, "jsonl")

    context = CONT / "context.md"
    if context.exists():
        if not context.read_bytes().endswith(b"\n"):
            fail("C010_FORMAT", "continuity/context.md must end with newline")
    else:
        fail("C002_SCHEMA", "continuity/context.md missing")

    if ERRORS:
        for error in ERRORS:
            print(error, file=sys.stderr)
        return 1
    print("Life continuity bundle: VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
