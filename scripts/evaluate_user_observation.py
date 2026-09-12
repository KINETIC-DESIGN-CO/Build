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


def reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            fail(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_policy(path: Path = POLICY_PATH) -> dict:
    try:
        policy = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except ObservationError:
        raise
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
        "external_evidence_ref_requirements",
        "effective_states",
        "evaluation_precedence",
        "control_decision_kinds",
        "rules",
        "motivating_examples",
        "control_authority_effect",
    }
    if set(policy) != required:
        fail("policy keys mismatch")
    exact = {
        "schema_version": 1,
        "policy_id": "life-user-observation-provenance-v1",
        "runtime_control_authority": "NONE",
        "record_type": "VINCE_PERSONAL_OBSERVATION",
        "authorization_states": [
            "NOT_AUTHORIZED",
            "AUTHORIZED_FOR_LIFE_REQUIREMENT",
        ],
        "external_verification_states": [
            "NOT_RUN",
            "UNVERIFIED",
            "VERIFIED_MATCH",
            "VERIFIED_CONTRADICTION",
        ],
        "external_evidence_ref_requirements": {
            "NOT_RUN": "ZERO",
            "UNVERIFIED": "ONE_OR_MORE",
            "VERIFIED_MATCH": "ONE_OR_MORE",
            "VERIFIED_CONTRADICTION": "ONE_OR_MORE",
        },
        "effective_states": [
            "RECORDED_ONLY",
            "ACTIVE_USER_REQUIREMENT",
            "DIRECT_EVIDENCE_CONFLICT",
            "SUPERSEDED",
        ],
        "evaluation_precedence": [
            "SUPERSEDED_IF_REFERENCED_BY_LATER_RECORD",
            "DIRECT_EVIDENCE_CONFLICT_IF_VERIFIED_CONTRADICTION",
            "ACTIVE_USER_REQUIREMENT_IF_AUTHORIZED",
            "RECORDED_ONLY_OTHERWISE",
        ],
        "control_decision_kinds": [
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
        ],
        "rules": [
            "VINCE_OBSERVATION_IS_NOT_EXTERNAL_VERIFICATION",
            "AUTHORIZATION_MAY_CREATE_USER_REQUIREMENT_WITHOUT_EXTERNAL_PLATFORM_TEST",
            "NOT_RUN_REQUIRES_ZERO_EXTERNAL_EVIDENCE_REFS",
            "UNVERIFIED_REQUIRES_ONE_OR_MORE_EXTERNAL_VERIFICATION_ATTEMPT_REFS",
            "VERIFIED_MATCH_REQUIRES_ONE_OR_MORE_DIRECT_EXTERNAL_EVIDENCE_REFS",
            "VERIFIED_CONTRADICTION_REQUIRES_ONE_OR_MORE_DIRECT_EXTERNAL_EVIDENCE_REFS",
            "LATER_VINCE_CORRECTION_APPENDS_NEW_RECORD_AND_EXPLICITLY_SUPERSEDES_PRIOR_RECORD",
            "DIRECT_VERIFIED_CONTRADICTION_DERIVES_DIRECT_EVIDENCE_CONFLICT",
            "DIRECT_VERIFIED_CONTRADICTION_DOES_NOT_REWRITE_PRIOR_OBSERVATION",
            "USER_OBSERVATION_CONTROL_EFFECT_IS_ZERO_FOR_EVERY_CONTROL_DECISION_KIND",
            "TEST_SCOPE_IS_LIFE_OWNED_RECORD_VALIDATION_AND_STATE_DERIVATION_ONLY",
        ],
        "motivating_examples": [
            "ISSUE_18_INTERRUPTED_RESPONSE_CONTINUE_OBSERVATION",
            "PROJECT_INSTRUCTIONS_8000_CHARACTER_LIMIT_OBSERVATION",
        ],
        "control_authority_effect": "ZERO",
    }
    for key, expected in exact.items():
        if policy.get(key) != expected:
            fail(f"policy.{key} mismatch")
    if set(policy["control_decision_kinds"]) != CONTROL_DECISION_KINDS:
        fail("policy.control_decision_kinds mismatch")


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
    external_state = record["external_verification_state"]
    if external_state not in policy["external_verification_states"]:
        fail("external_verification_state invalid")
    refs = record["external_evidence_refs"]
    if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref for ref in refs):
        fail("external_evidence_refs must be an array of nonempty strings")
    if len(refs) != len(set(refs)):
        fail("external_evidence_refs must be unique")
    ref_requirement = policy["external_evidence_ref_requirements"][external_state]
    if ref_requirement == "ZERO" and refs:
        fail(f"{external_state} requires zero external evidence refs")
    if ref_requirement == "ONE_OR_MORE" and not refs:
        fail(f"{external_state} requires one or more external evidence refs")
    supersedes = record["supersedes"]
    if not isinstance(supersedes, list) or any(
        ID_RE.fullmatch(str(ref)) is None for ref in supersedes
    ):
        fail("supersedes must be an observation-id array")
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
        record_id = record["id"]
        if record_id in seen:
            fail(f"duplicate record id {record_id}")
        for prior_id in record["supersedes"]:
            if prior_id not in seen:
                fail(f"{record_id} supersedes missing or later record {prior_id}")
            superseded.add(prior_id)
        seen[record_id] = record

    result: dict[str, str] = {}
    for record_id, record in seen.items():
        if record_id in superseded:
            state = "SUPERSEDED"
        elif record["external_verification_state"] == "VERIFIED_CONTRADICTION":
            state = "DIRECT_EVIDENCE_CONFLICT"
        elif record["authorization_state"] == "AUTHORIZED_FOR_LIFE_REQUIREMENT":
            state = "ACTIVE_USER_REQUIREMENT"
        else:
            state = "RECORDED_ONLY"
        if state not in policy["effective_states"]:
            fail(f"derived state {state} is not permitted")
        result[record_id] = state
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
