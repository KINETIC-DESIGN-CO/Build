#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "user-observation-policy.json"
ID_RE = re.compile(r"^UO-[0-9]{4}$")

CONTROL_DECISION_KINDS = {
    "AUTHORIZATION",
    "ROUTING",
    "PRIORITY",
    "STATE_TRANSITION",
    "COMPLETION",
    "VERIFICATION",
    "ESCALATION",
    "RELEASE",
    "MUTATION",
    "EFFECT_EXECUTION",
}


class ObservationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ObservationError(message)


def load_policy(path: Path = POLICY_PATH) -> dict:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid policy JSON: {exc}")
    validate_policy(policy)
    return policy


def validate_policy(policy: object) -> None:
    if not isinstance(policy, dict):
        fail("policy must be object")
    required = {
        "schema_version",
        "policy_id",
        "runtime_control_authority",
        "record_type",
        "authorization_states",
        "external_verification_states",
        "effective_states",
        "evaluation_precedence",
        "rules",
        "control_authority_effect",
    }
    if set(policy) != required:
        fail("policy keys mismatch")
    if policy["schema_version"] != 1:
        fail("schema_version must equal 1")
    if policy["policy_id"] != "life-user-observation-provenance-v1":
        fail("policy_id mismatch")
    if policy["runtime_control_authority"] != "NONE":
        fail("runtime_control_authority must be NONE")
    if policy["record_type"] != "VINCE_PERSONAL_OBSERVATION":
        fail("record_type mismatch")
    if policy["authorization_states"] != [
        "NOT_AUTHORIZED",
        "AUTHORIZED_FOR_LIFE_REQUIREMENT",
    ]:
        fail("authorization_states mismatch")
    if policy["external_verification_states"] != [
        "NOT_RUN",
        "UNVERIFIED",
        "VERIFIED_MATCH",
        "VERIFIED_CONTRADICTION",
    ]:
        fail("external_verification_states mismatch")
    if policy["effective_states"] != [
        "RECORDED_ONLY",
        "ACTIVE_USER_REQUIREMENT",
        "DIRECT_EVIDENCE_CONFLICT",
        "SUPERSEDED",
    ]:
        fail("effective_states mismatch")
    if policy["evaluation_precedence"] != [
        "SUPERSEDED_IF_REFERENCED_BY_LATER_RECORD",
        "DIRECT_EVIDENCE_CONFLICT_IF_VERIFIED_CONTRADICTION",
        "ACTIVE_USER_REQUIREMENT_IF_AUTHORIZED",
        "RECORDED_ONLY_OTHERWISE",
    ]:
        fail("evaluation_precedence mismatch")
    expected_rules = [
        "VINCE_OBSERVATION_IS_NOT_EXTERNAL_VERIFICATION",
        "AUTHORIZATION_MAY_CREATE_USER_REQUIREMENT_WITHOUT_FABRICATED_EXTERNAL_TEST",
        "LATER_VINCE_CORRECTION_APPENDS_NEW_RECORD_AND_SUPERSEDES_PRIOR_RECORD",
        "DIRECT_VERIFIED_CONTRADICTION_MUST_SURFACE_AS_CONFLICT",
        "DIRECT_VERIFIED_CONTRADICTION_DOES_NOT_SILENTLY_REWRITE_USER_OBSERVATION",
        "USER_OBSERVATION_HAS_ZERO_RUNTIME_CONTROL_AUTHORITY",
        "EXTERNAL_BEHAVIOR_WITHOUT_OBSERVABLE_INTERFACE_MUST_NOT_BE_RELABELED_MACHINE_TESTED",
    ]
    if policy["rules"] != expected_rules:
        fail("rules mismatch")
    if policy["control_authority_effect"] != "ZERO":
        fail("control_authority_effect must equal ZERO")


def is_rfc3339_utc(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
        return True
    except ValueError:
        return False


def validate_record(record: object, policy: dict) -> None:
    validate_policy(policy)
    if not isinstance(record, dict):
        fail("record must be object")
    required = {
        "id",
        "record_type",
        "observed_by",
        "observed_at",
        "statement",
        "authorization_state",
        "external_verification_state",
        "external_evidence_refs",
        "supersedes",
        "runtime_control_authority",
    }
    if set(record) != required:
        fail("record keys mismatch")
    if not ID_RE.fullmatch(str(record["id"])):
        fail("record id invalid")
    if record["record_type"] != policy["record_type"]:
        fail("record_type mismatch")
    if record["observed_by"] != "VINCE":
        fail("observed_by must equal VINCE")
    if not is_rfc3339_utc(record["observed_at"]):
        fail("observed_at must be RFC3339 UTC")
    if not isinstance(record["statement"], str) or not record["statement"]:
        fail("statement must be nonempty")
    if record["authorization_state"] not in policy["authorization_states"]:
        fail("authorization_state invalid")
    if record["external_verification_state"] not in policy["external_verification_states"]:
        fail("external_verification_state invalid")
    refs = record["external_evidence_refs"]
    if not isinstance(refs, list) or not all(isinstance(ref, str) and ref for ref in refs):
        fail("external_evidence_refs must be string array")
    if len(refs) != len(set(refs)):
        fail("external_evidence_refs must be unique")
    if record["external_verification_state"] in {
        "VERIFIED_MATCH",
        "VERIFIED_CONTRADICTION",
    } and not refs:
        fail("verified external state requires evidence refs")
    supersedes = record["supersedes"]
    if not isinstance(supersedes, list) or not all(ID_RE.fullmatch(str(ref)) for ref in supersedes):
        fail("supersedes must be observation-id array")
    if len(supersedes) != len(set(supersedes)):
        fail("supersedes must be unique")
    if record["id"] in supersedes:
        fail("record cannot supersede itself")
    if record["runtime_control_authority"] != "NONE":
        fail("record runtime_control_authority must be NONE")


def evaluate_records(records: list[dict], policy: dict) -> dict[str, str]:
    validate_policy(policy)
    seen: dict[str, dict] = {}
    superseded: set[str] = set()
    for record in records:
        validate_record(record, policy)
        rid = record["id"]
        if rid in seen:
            fail(f"duplicate record id {rid}")
        for prior_id in record["supersedes"]:
            if prior_id not in seen:
                fail(f"{rid} supersedes missing or later record {prior_id}")
            superseded.add(prior_id)
        seen[rid] = record

    result: dict[str, str] = {}
    for rid, record in seen.items():
        if rid in superseded:
            state = "SUPERSEDED"
        elif record["external_verification_state"] == "VERIFIED_CONTRADICTION":
            state = "DIRECT_EVIDENCE_CONFLICT"
        elif record["authorization_state"] == "AUTHORIZED_FOR_LIFE_REQUIREMENT":
            state = "ACTIVE_USER_REQUIREMENT"
        else:
            state = "RECORDED_ONLY"
        if state not in policy["effective_states"]:
            fail(f"derived state {state} is not permitted")
        result[rid] = state
    return result


def may_satisfy_runtime_control(record: dict, decision_kind: str, policy: dict) -> bool:
    validate_record(record, policy)
    if decision_kind not in CONTROL_DECISION_KINDS:
        fail("decision_kind invalid")
    return False


def main() -> int:
    try:
        load_policy()
    except ObservationError as exc:
        print(f"USER_OBSERVATION_POLICY_INVALID: {exc}", file=sys.stderr)
        return 1
    print("USER_OBSERVATION_POLICY_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
