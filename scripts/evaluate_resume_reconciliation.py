#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "resume-reconciliation-policy.json"
OBSERVATIONS_PATH = ROOT / "continuity" / "user-observations.jsonl"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
RESOURCE_RE = re.compile(r"^[a-z]+:[A-Za-z0-9_.:/-]+$")

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
OPERATION_STATES = {"NONE", "PENDING", "NO_RESULT", "TIMEOUT", "UNKNOWN", "SUCCESS", "FAILURE"}
WORK_RELATION_STATES = {"SAME_WORK_ACTIVE", "SAME_WORK_CLAIMS_INACTIVE", "DIFFERENT_WORK_STATE", "UNKNOWN", "NOT_RUN"}
COMPLETION_CLASSES = {"NO_INTERRUPTED_OPERATION", "VERIFIED_SUCCESS", "VERIFIED_FAILURE", "UNKNOWN", "NOT_RUN"}
RESUME_ACTIONS = {
    "RESUME_SAME_WORK_CONTINUE",
    "RESUME_SAME_WORK_VERIFY_LAST_OPERATION",
    "REACQUIRE_REQUIRED_CLAIMS_BEFORE_MUTATION",
    "RECONCILE_DIFFERENT_WORK_BEFORE_PROCEED",
    "STOP_UNKNOWN",
    "STOP_NOT_RUN",
}


class ResumeError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ResumeError(message)


def no_dupe(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            fail(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_dupe)
    except ResumeError:
        raise
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def is_utc(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
        return True
    except ValueError:
        return False


def parse_utc(value: str) -> datetime:
    if not is_utc(value):
        fail(f"invalid RFC3339 UTC timestamp: {value!r}")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def validate_policy(policy: object) -> None:
    if not isinstance(policy, dict):
        fail("policy must be object")
    required = {
        "schema_version",
        "policy_id",
        "runtime_control_authority",
        "source_issue_number",
        "user_observation_ref",
        "work_selection_policy_path",
        "coordination_protocol_path",
        "resume_cues",
        "live_read_states",
        "interrupted_operation_states",
        "ownership_identity_fields",
        "work_relation_states",
        "operation_completion_classes",
        "resume_actions",
        "procedure_steps",
        "rules",
        "control_decision_kinds",
        "control_authority_effect",
    }
    if set(policy) != required:
        fail("policy keys mismatch")
    exact = {
        "schema_version": 1,
        "policy_id": "life-resume-reconciliation-v1",
        "runtime_control_authority": "NONE",
        "source_issue_number": 18,
        "user_observation_ref": "UO-0002",
        "work_selection_policy_path": "governance/work-selection-policy.json",
        "coordination_protocol_path": "coordination/protocol.json",
        "resume_cues": ["CONTINUE"],
        "live_read_states": ["VERIFIED", "NOT_RUN"],
        "interrupted_operation_states": ["NONE", "PENDING", "NO_RESULT", "TIMEOUT", "UNKNOWN", "SUCCESS", "FAILURE"],
        "ownership_identity_fields": ["resource_key", "work_id", "lease_id", "generation"],
        "work_relation_states": ["SAME_WORK_ACTIVE", "SAME_WORK_CLAIMS_INACTIVE", "DIFFERENT_WORK_STATE", "UNKNOWN", "NOT_RUN"],
        "operation_completion_classes": ["NO_INTERRUPTED_OPERATION", "VERIFIED_SUCCESS", "VERIFIED_FAILURE", "UNKNOWN", "NOT_RUN"],
        "resume_actions": [
            "RESUME_SAME_WORK_CONTINUE",
            "RESUME_SAME_WORK_VERIFY_LAST_OPERATION",
            "REACQUIRE_REQUIRED_CLAIMS_BEFORE_MUTATION",
            "RECONCILE_DIFFERENT_WORK_BEFORE_PROCEED",
            "STOP_UNKNOWN",
            "STOP_NOT_RUN",
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
        "control_authority_effect": "ZERO",
    }
    for key, expected in exact.items():
        if policy.get(key) != expected:
            fail(f"policy.{key} mismatch")
    if not isinstance(policy["procedure_steps"], list) or len(policy["procedure_steps"]) != 7 or len(set(policy["procedure_steps"])) != 7:
        fail("policy.procedure_steps must contain exactly seven unique steps")
    if not isinstance(policy["rules"], list) or len(policy["rules"]) < 10 or len(policy["rules"]) != len(set(policy["rules"])):
        fail("policy.rules invalid")
    if set(policy["control_decision_kinds"]) != CONTROL_DECISION_KINDS:
        fail("policy.control_decision_kinds mismatch")


def validate_observation_reference(policy: dict, path: Path = OBSERVATIONS_PATH) -> None:
    rows = []
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as exc:
        fail(f"observation ledger unreadable: {exc}")
    for line_number, line in enumerate(raw.splitlines(), 1):
        if not line:
            fail(f"observation ledger blank line {line_number}")
        try:
            row = json.loads(line, object_pairs_hook=no_dupe)
        except ResumeError:
            raise
        except Exception as exc:
            fail(f"observation ledger invalid JSON line {line_number}: {exc}")
        rows.append(row)
    matches = [row for row in rows if row.get("id") == policy["user_observation_ref"]]
    if len(matches) != 1:
        fail("policy user_observation_ref must resolve exactly once")
    row = matches[0]
    if row.get("record_type") != "VINCE_PERSONAL_OBSERVATION" or row.get("observed_by") != "VINCE":
        fail("resume observation provenance mismatch")
    if row.get("authorization_state") != "AUTHORIZED_FOR_LIFE_REQUIREMENT":
        fail("resume observation must be user-authorized")
    if row.get("runtime_control_authority") != "NONE":
        fail("resume observation runtime authority must be NONE")


def validate_uuid(value: object, label: str) -> str:
    if not isinstance(value, str) or UUID_RE.fullmatch(value) is None:
        fail(f"{label} must be lowercase UUIDv4")
    return value


def validate_thread_claim(claim: object) -> dict:
    required = {"resource_key", "work_id", "lease_id", "generation"}
    if not isinstance(claim, dict) or set(claim) != required:
        fail("thread claim keys mismatch")
    if not isinstance(claim["resource_key"], str) or RESOURCE_RE.fullmatch(claim["resource_key"]) is None:
        fail("thread claim resource_key invalid")
    validate_uuid(claim["work_id"], "thread claim work_id")
    validate_uuid(claim["lease_id"], "thread claim lease_id")
    if not isinstance(claim["generation"], int) or isinstance(claim["generation"], bool) or claim["generation"] < 1:
        fail("thread claim generation invalid")
    return claim


def validate_live_claim(claim: object) -> dict:
    required = {"resource_key", "state", "work_id", "lease_id", "generation", "expires_at"}
    if not isinstance(claim, dict) or set(claim) != required:
        fail("live claim keys mismatch")
    if not isinstance(claim["resource_key"], str) or RESOURCE_RE.fullmatch(claim["resource_key"]) is None:
        fail("live claim resource_key invalid")
    if claim["state"] not in {"ACTIVE", "RELEASED"}:
        fail("live claim state invalid")
    validate_uuid(claim["work_id"], "live claim work_id")
    validate_uuid(claim["lease_id"], "live claim lease_id")
    if not isinstance(claim["generation"], int) or isinstance(claim["generation"], bool) or claim["generation"] < 1:
        fail("live claim generation invalid")
    parse_utc(claim["expires_at"])
    return claim


def validate_work(value: object, *, live: bool) -> dict | None:
    if value is None:
        return None
    required = {"work_id", "implementation_branch", "worker_session_id", "claims"}
    if not isinstance(value, dict) or set(value) != required:
        fail(("live" if live else "thread") + " work keys mismatch")
    validate_uuid(value["work_id"], ("live" if live else "thread") + " work_id")
    expected_branch = f"work/{value['work_id']}"
    if value["implementation_branch"] != expected_branch:
        fail(("live" if live else "thread") + " implementation_branch mismatch")
    validate_uuid(value["worker_session_id"], ("live" if live else "thread") + " worker_session_id")
    if not isinstance(value["claims"], list):
        fail(("live" if live else "thread") + " claims must be array")
    validator = validate_live_claim if live else validate_thread_claim
    claims = [validator(claim) for claim in value["claims"]]
    resource_keys = [claim["resource_key"] for claim in claims]
    if len(resource_keys) != len(set(resource_keys)):
        fail(("live" if live else "thread") + " claim resource keys must be unique")
    if any(claim["work_id"] != value["work_id"] for claim in claims):
        fail(("live" if live else "thread") + " claim work_id must match work record")
    return value


def validate_evidence(evidence: object) -> dict:
    required = {
        "schema_version",
        "resume_cue",
        "observed_at",
        "live_read_state",
        "interrupted_operation_state",
        "thread_work",
        "live_work",
    }
    if not isinstance(evidence, dict) or set(evidence) != required:
        fail("evidence keys mismatch")
    if evidence["schema_version"] != 1:
        fail("evidence schema_version mismatch")
    if evidence["resume_cue"] not in {"CONTINUE", "OTHER", "ABSENT"}:
        fail("resume_cue invalid")
    parse_utc(evidence["observed_at"])
    if evidence["live_read_state"] not in {"VERIFIED", "NOT_RUN"}:
        fail("live_read_state invalid")
    if evidence["interrupted_operation_state"] not in OPERATION_STATES:
        fail("interrupted_operation_state invalid")
    validate_work(evidence["thread_work"], live=False)
    validate_work(evidence["live_work"], live=True)
    if evidence["live_read_state"] == "NOT_RUN" and evidence["live_work"] is not None:
        fail("NOT_RUN live_read_state requires null live_work")
    return evidence


def operation_completion(evidence: dict) -> str:
    if evidence["live_read_state"] == "NOT_RUN":
        return "NOT_RUN"
    state = evidence["interrupted_operation_state"]
    if state == "NONE":
        return "NO_INTERRUPTED_OPERATION"
    if state == "SUCCESS":
        return "VERIFIED_SUCCESS"
    if state == "FAILURE":
        return "VERIFIED_FAILURE"
    return "UNKNOWN"


def claim_identity(claim: dict) -> tuple:
    return claim["resource_key"], claim["work_id"], claim["lease_id"], claim["generation"]


def work_relation(evidence: dict) -> str:
    if evidence["live_read_state"] == "NOT_RUN":
        return "NOT_RUN"
    thread_work = evidence["thread_work"]
    live_work = evidence["live_work"]
    if thread_work is None or live_work is None:
        return "UNKNOWN"
    if thread_work["work_id"] != live_work["work_id"] or thread_work["implementation_branch"] != live_work["implementation_branch"]:
        return "DIFFERENT_WORK_STATE"
    thread_by_resource = {claim["resource_key"]: claim for claim in thread_work["claims"]}
    live_by_resource = {claim["resource_key"]: claim for claim in live_work["claims"]}
    if set(thread_by_resource) != set(live_by_resource):
        return "UNKNOWN"
    observed_at = parse_utc(evidence["observed_at"])
    inactive = False
    for resource_key in sorted(thread_by_resource):
        thread_claim = thread_by_resource[resource_key]
        live_claim = live_by_resource[resource_key]
        if claim_identity(thread_claim) != claim_identity(live_claim):
            return "DIFFERENT_WORK_STATE"
        if live_claim["state"] != "ACTIVE" or observed_at >= parse_utc(live_claim["expires_at"]):
            inactive = True
    return "SAME_WORK_CLAIMS_INACTIVE" if inactive else "SAME_WORK_ACTIVE"


def evaluate(evidence: object, policy: dict) -> dict:
    validate_policy(policy)
    evidence = validate_evidence(evidence)
    relation = work_relation(evidence)
    completion = operation_completion(evidence)
    if relation == "NOT_RUN":
        action = "STOP_NOT_RUN"
        classification = "NOT_RUN"
    elif relation == "UNKNOWN":
        action = "STOP_UNKNOWN"
        classification = "UNKNOWN"
    elif relation == "DIFFERENT_WORK_STATE":
        action = "RECONCILE_DIFFERENT_WORK_BEFORE_PROCEED"
        classification = "VERIFIED"
    elif relation == "SAME_WORK_CLAIMS_INACTIVE":
        action = "REACQUIRE_REQUIRED_CLAIMS_BEFORE_MUTATION"
        classification = "VERIFIED"
    elif completion == "UNKNOWN":
        action = "RESUME_SAME_WORK_VERIFY_LAST_OPERATION"
        classification = "VERIFIED"
    else:
        action = "RESUME_SAME_WORK_CONTINUE"
        classification = "VERIFIED"
    if relation not in WORK_RELATION_STATES or completion not in COMPLETION_CLASSES or action not in RESUME_ACTIONS:
        fail("derived resume state invalid")
    return {
        "work_relation_state": relation,
        "operation_completion_class": completion,
        "resume_action": action,
        "classification": classification,
        "resume_cue_effect": "ZERO_CONTROL_EFFECT",
        "worker_session_id_effect": "ZERO_OWNERSHIP_EFFECT",
        "ownership_identity_fields": policy["ownership_identity_fields"],
        "runtime_control_authority": "NONE",
    }


def may_satisfy_runtime_control(decision_kind: str, policy: dict) -> bool:
    validate_policy(policy)
    if decision_kind not in CONTROL_DECISION_KINDS:
        fail("decision_kind invalid")
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluate")
    args = parser.parse_args()
    try:
        policy = load_json(POLICY_PATH)
        validate_policy(policy)
        validate_observation_reference(policy)
        if args.evaluate:
            evidence = load_json(Path(args.evaluate))
            print(json.dumps(evaluate(evidence, policy), sort_keys=True))
        else:
            print("RESUME_RECONCILIATION_POLICY_VALID")
        return 0
    except ResumeError as exc:
        print(f"RESUME_RECONCILIATION_POLICY_INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
