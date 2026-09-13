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
FENCE_POLICY_PATH = ROOT / "governance" / "work-fence-policy.json"
OBSERVATIONS_PATH = ROOT / "continuity" / "user-observations.jsonl"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
RESOURCE_RE = re.compile(r"^[a-z]+:[A-Za-z0-9_.:/-]+$")

CONTROL_DECISION_KINDS = {
    "AUTHORIZATION", "ROUTING", "PRIORITY", "STATE_TRANSITION", "COMPLETION",
    "VERIFICATION", "ESCALATION", "RELEASE", "MUTATION", "EFFECT_EXECUTION",
}
OPERATION_STATES = {"NONE", "PENDING", "NO_RESULT", "TIMEOUT", "UNKNOWN", "SUCCESS", "FAILURE"}
UNRESOLVED_EFFECT_STATES = {"PENDING", "NO_RESULT", "TIMEOUT", "UNKNOWN"}
WORK_RELATION_STATES = {"SAME_WORK_ACTIVE", "SAME_WORK_CLAIMS_INACTIVE", "DIFFERENT_WORK_STATE", "UNKNOWN", "NOT_RUN"}
COMPLETION_CLASSES = {"NO_INTERRUPTED_OPERATION", "VERIFIED_SUCCESS", "VERIFIED_FAILURE", "UNKNOWN", "NOT_RUN"}
RESUME_ACTIONS = {
    "RESUME_SAME_WORK_CONTINUE",
    "RESUME_SAME_WORK_VERIFY_LAST_OPERATION",
    "RECONCILE_EXTERNAL_EFFECT_BEFORE_RESUME",
    "CHECKPOINT_AND_REPLAN",
    "REACQUIRE_REQUIRED_CLAIMS_BEFORE_MUTATION",
    "RECONCILE_DIFFERENT_WORK_BEFORE_PROCEED",
    "STOP_UNKNOWN",
    "STOP_NOT_RUN",
}
FENCE_STATES = {
    "EXTERNAL_EFFECT_UNRESOLVED", "GOAL_REVISION_MISMATCH", "CONTROL_SIGNAL_ACTIVE",
    "OWNERSHIP_IDENTITY_MISMATCH", "CLAIM_INACTIVE_OR_EXPIRED",
    "INTERRUPTED_OPERATION_UNRESOLVED", "CONTINUE", "UNKNOWN", "NOT_RUN",
}
WORK_KEYS = {
    "work_id", "implementation_branch", "worker_session_id", "goal_id",
    "planned_goal_revision", "pending_external_effect_state", "claims",
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


def validate_uuid(value: object, label: str) -> str:
    if not isinstance(value, str) or UUID_RE.fullmatch(value) is None:
        fail(f"{label} must be lowercase UUIDv4")
    return value


def validate_policy(policy: object, fence_policy: dict | None = None) -> None:
    if not isinstance(policy, dict):
        fail("policy must be object")
    required = {
        "schema_version", "policy_id", "runtime_control_authority", "source_issue_number",
        "user_observation_ref", "work_selection_policy_path", "work_fence_policy_path",
        "goal_registry_path", "coordination_protocol_path", "resume_cues", "live_read_states",
        "interrupted_operation_states", "ownership_identity_fields", "work_relation_states",
        "operation_completion_classes", "fence_precedence", "resume_actions", "procedure_steps",
        "rules", "control_decision_kinds", "control_authority_effect",
    }
    if set(policy) != required:
        fail("policy keys mismatch")
    exact = {
        "schema_version": 2,
        "policy_id": "life-resume-reconciliation-v2",
        "runtime_control_authority": "NONE",
        "source_issue_number": 18,
        "user_observation_ref": "UO-0002",
        "work_selection_policy_path": "governance/work-selection-policy.json",
        "work_fence_policy_path": "governance/work-fence-policy.json",
        "goal_registry_path": "governance/goal-registry.json",
        "coordination_protocol_path": "coordination/protocol.json",
        "resume_cues": ["CONTINUE"],
        "live_read_states": ["VERIFIED", "NOT_RUN"],
        "interrupted_operation_states": ["NONE", "PENDING", "NO_RESULT", "TIMEOUT", "UNKNOWN", "SUCCESS", "FAILURE"],
        "ownership_identity_fields": ["resource_key", "work_id", "lease_id", "generation"],
        "work_relation_states": ["SAME_WORK_ACTIVE", "SAME_WORK_CLAIMS_INACTIVE", "DIFFERENT_WORK_STATE", "UNKNOWN", "NOT_RUN"],
        "operation_completion_classes": ["NO_INTERRUPTED_OPERATION", "VERIFIED_SUCCESS", "VERIFIED_FAILURE", "UNKNOWN", "NOT_RUN"],
        "fence_precedence": [
            "EXTERNAL_EFFECT_UNRESOLVED", "GOAL_REVISION_MISMATCH", "CONTROL_SIGNAL_ACTIVE",
            "OWNERSHIP_IDENTITY_MISMATCH", "CLAIM_INACTIVE_OR_EXPIRED",
            "INTERRUPTED_OPERATION_UNRESOLVED", "CONTINUE",
        ],
        "resume_actions": [
            "RESUME_SAME_WORK_CONTINUE", "RESUME_SAME_WORK_VERIFY_LAST_OPERATION",
            "RECONCILE_EXTERNAL_EFFECT_BEFORE_RESUME", "CHECKPOINT_AND_REPLAN",
            "REACQUIRE_REQUIRED_CLAIMS_BEFORE_MUTATION", "RECONCILE_DIFFERENT_WORK_BEFORE_PROCEED",
            "STOP_UNKNOWN", "STOP_NOT_RUN",
        ],
        "control_decision_kinds": [
            "AUTHORIZATION", "ROUTING", "PRIORITY", "STATE_TRANSITION", "COMPLETION",
            "VERIFICATION", "ESCALATION", "RELEASE", "MUTATION", "EFFECT_EXECUTION",
        ],
        "control_authority_effect": "ZERO",
    }
    for key, expected in exact.items():
        if policy.get(key) != expected:
            fail(f"policy.{key} mismatch")
    if not isinstance(policy["procedure_steps"], list) or len(policy["procedure_steps"]) != 9 or len(set(policy["procedure_steps"])) != 9:
        fail("policy.procedure_steps must contain exactly nine unique steps")
    if not isinstance(policy["rules"], list) or len(policy["rules"]) < 15 or len(policy["rules"]) != len(set(policy["rules"])):
        fail("policy.rules invalid")
    if set(policy["control_decision_kinds"]) != CONTROL_DECISION_KINDS:
        fail("policy.control_decision_kinds mismatch")
    fence_policy = fence_policy or load_json(FENCE_POLICY_PATH)
    if fence_policy.get("canonical_selector_entrypoint") != "scripts/select_work.py":
        fail("work fence canonical selector mismatch")
    if set(fence_policy.get("external_effect_unresolved_states", [])) != UNRESOLVED_EFFECT_STATES:
        fail("resume/fence unresolved external effect states mismatch")
    if fence_policy.get("goal_revision_mismatch_result") != "REPLAN_REQUIRED":
        fail("resume/fence revision result mismatch")
    if set(fence_policy.get("control_signal_states", [])) != {"NONE", "YIELD_OR_REPLAN_REQUESTED", "REASSIGNMENT_REQUESTED"}:
        fail("resume/fence control signal states mismatch")


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
    if not isinstance(value, dict) or set(value) != WORK_KEYS:
        fail(("live" if live else "thread") + " work keys mismatch")
    validate_uuid(value["work_id"], ("live" if live else "thread") + " work_id")
    if value["implementation_branch"] != f"work/{value['work_id']}":
        fail(("live" if live else "thread") + " implementation_branch mismatch")
    validate_uuid(value["worker_session_id"], ("live" if live else "thread") + " worker_session_id")
    goal_id = value["goal_id"]
    revision = value["planned_goal_revision"]
    if goal_id is None:
        if revision is not None:
            fail("planned_goal_revision must be null when goal_id is null")
    else:
        validate_uuid(goal_id, ("live" if live else "thread") + " goal_id")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            fail("planned_goal_revision must be integer >= 1")
    if value["pending_external_effect_state"] not in OPERATION_STATES:
        fail("pending_external_effect_state invalid")
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


def validate_canonical_goal(value: object) -> dict | None:
    if value is None:
        return None
    required = {"goal_id", "revision", "control_signal"}
    if not isinstance(value, dict) or set(value) != required:
        fail("canonical_goal keys mismatch")
    validate_uuid(value["goal_id"], "canonical goal_id")
    if not isinstance(value["revision"], int) or isinstance(value["revision"], bool) or value["revision"] < 1:
        fail("canonical goal revision invalid")
    signal = value["control_signal"]
    if not isinstance(signal, dict) or set(signal) != {"state", "target_work_id"}:
        fail("canonical goal control_signal keys mismatch")
    if signal["state"] not in {"NONE", "YIELD_OR_REPLAN_REQUESTED", "REASSIGNMENT_REQUESTED"}:
        fail("canonical goal control signal state invalid")
    if signal["state"] == "NONE":
        if signal["target_work_id"] is not None:
            fail("NONE control signal requires null target_work_id")
    else:
        validate_uuid(signal["target_work_id"], "canonical control signal target_work_id")
    return value


def validate_evidence(evidence: object) -> dict:
    required = {
        "schema_version", "resume_cue", "observed_at", "live_read_state",
        "interrupted_operation_state", "thread_work", "live_work", "canonical_goal",
    }
    if not isinstance(evidence, dict) or set(evidence) != required:
        fail("evidence keys mismatch")
    if evidence["schema_version"] != 2:
        fail("evidence schema_version mismatch")
    if evidence["resume_cue"] not in {"CONTINUE", "OTHER", "ABSENT"}:
        fail("resume_cue invalid")
    parse_utc(evidence["observed_at"])
    if evidence["live_read_state"] not in {"VERIFIED", "NOT_RUN"}:
        fail("live_read_state invalid")
    if evidence["interrupted_operation_state"] not in OPERATION_STATES:
        fail("interrupted_operation_state invalid")
    thread_work = validate_work(evidence["thread_work"], live=False)
    live_work = validate_work(evidence["live_work"], live=True)
    canonical_goal = validate_canonical_goal(evidence["canonical_goal"])
    if evidence["live_read_state"] == "NOT_RUN":
        if live_work is not None or canonical_goal is not None:
            fail("NOT_RUN live_read_state requires null live_work and canonical_goal")
    if evidence["live_read_state"] == "VERIFIED" and thread_work is not None and thread_work["goal_id"] is not None:
        if canonical_goal is None or canonical_goal["goal_id"] != thread_work["goal_id"]:
            fail("verified goal-bound resume requires matching canonical_goal")
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
    if thread_work["goal_id"] != live_work["goal_id"] or thread_work["planned_goal_revision"] != live_work["planned_goal_revision"]:
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


def fence_state(evidence: dict) -> str:
    if evidence["live_read_state"] == "NOT_RUN":
        return "NOT_RUN"
    thread_work = evidence["thread_work"]
    live_work = evidence["live_work"]
    if thread_work is None or live_work is None:
        return "UNKNOWN"
    if thread_work["pending_external_effect_state"] in UNRESOLVED_EFFECT_STATES or live_work["pending_external_effect_state"] in UNRESOLVED_EFFECT_STATES:
        return "EXTERNAL_EFFECT_UNRESOLVED"
    goal_id = thread_work["goal_id"]
    if goal_id is not None:
        canonical = evidence["canonical_goal"]
        if canonical is None or canonical["goal_id"] != goal_id:
            return "UNKNOWN"
        if thread_work["planned_goal_revision"] != canonical["revision"]:
            return "GOAL_REVISION_MISMATCH"
        signal = canonical["control_signal"]
        if signal["state"] != "NONE" and signal["target_work_id"] == thread_work["work_id"]:
            return "CONTROL_SIGNAL_ACTIVE"
    relation = work_relation(evidence)
    if relation == "NOT_RUN":
        return "NOT_RUN"
    if relation == "UNKNOWN":
        return "UNKNOWN"
    if relation == "DIFFERENT_WORK_STATE":
        return "OWNERSHIP_IDENTITY_MISMATCH"
    if relation == "SAME_WORK_CLAIMS_INACTIVE":
        return "CLAIM_INACTIVE_OR_EXPIRED"
    if operation_completion(evidence) == "UNKNOWN":
        return "INTERRUPTED_OPERATION_UNRESOLVED"
    return "CONTINUE"


def evaluate(evidence: object, policy: dict) -> dict:
    validate_policy(policy)
    evidence = validate_evidence(evidence)
    relation = work_relation(evidence)
    completion = operation_completion(evidence)
    state = fence_state(evidence)
    action_by_state = {
        "NOT_RUN": "STOP_NOT_RUN",
        "UNKNOWN": "STOP_UNKNOWN",
        "EXTERNAL_EFFECT_UNRESOLVED": "RECONCILE_EXTERNAL_EFFECT_BEFORE_RESUME",
        "GOAL_REVISION_MISMATCH": "CHECKPOINT_AND_REPLAN",
        "CONTROL_SIGNAL_ACTIVE": "CHECKPOINT_AND_REPLAN",
        "OWNERSHIP_IDENTITY_MISMATCH": "RECONCILE_DIFFERENT_WORK_BEFORE_PROCEED",
        "CLAIM_INACTIVE_OR_EXPIRED": "REACQUIRE_REQUIRED_CLAIMS_BEFORE_MUTATION",
        "INTERRUPTED_OPERATION_UNRESOLVED": "RESUME_SAME_WORK_VERIFY_LAST_OPERATION",
        "CONTINUE": "RESUME_SAME_WORK_CONTINUE",
    }
    action = action_by_state[state]
    classification = "NOT_RUN" if state == "NOT_RUN" else "UNKNOWN" if state == "UNKNOWN" else "VERIFIED"
    if relation not in WORK_RELATION_STATES or completion not in COMPLETION_CLASSES or state not in FENCE_STATES or action not in RESUME_ACTIONS:
        fail("derived resume state invalid")
    return {
        "work_relation_state": relation,
        "operation_completion_class": completion,
        "fence_state": state,
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
            evidence = json.loads(Path(args.evaluate).read_text(encoding="utf-8"), object_pairs_hook=no_dupe)
            print(json.dumps(evaluate(evidence, policy), indent=2))
        else:
            print("RESUME_RECONCILIATION_VALID")
        return 0
    except (ResumeError, OSError, json.JSONDecodeError) as exc:
        print(f"RESUME_RECONCILIATION_INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
