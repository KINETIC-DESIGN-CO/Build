#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance/issue-lifecycle-policy.json"
SCHEMA_PATH = ROOT / "governance/schema/issue-lifecycle-policy.schema.json"
ADMISSIONS_PATH = ROOT / "governance/work-admissions.json"

ROOT_KEYS = {
    "schema_version",
    "policy_id",
    "runtime_control_authority",
    "scope",
    "authorized_repository",
    "registry_path",
    "workflow_path",
    "issue_state_source",
    "native_close_mode",
    "terminal_admission_states",
    "nonterminal_admission_state",
    "reconciliation_trigger",
    "reconciliation_rules",
    "terminal_binding",
    "redispatch_binding",
    "native_link_rule",
    "failure_rule",
    "states",
}
RULES = [
    "FOR_EACH_REGISTRY_ITEM_WITH_STATE_COMPLETE_OR_REMOVED_READ_GITHUB_ISSUE_STATE",
    "IF_ISSUE_IS_OPEN_CLOSE_WITH_REASON_MAPPED_FROM_ADMISSION_STATE",
    "IF_ISSUE_IS_CLOSED_WITH_DIFFERENT_REASON_SET_REASON_MAPPED_FROM_ADMISSION_STATE",
    "READ_GITHUB_ISSUE_STATE_AFTER_ANY_RECONCILIATION_OPERATION",
    "FAIL_RECONCILIATION_UNLESS_STATE_IS_CLOSED_AND_REASON_MATCHES_ADMISSION_STATE",
]
STATES = [
    "ADMISSION_NONTERMINAL",
    "CLOSE_REQUIRED",
    "REASON_RECONCILIATION_REQUIRED",
    "READBACK_NOT_RUN",
    "VERIFIED_TERMINAL",
]
EXACT = {
    "schema_version": 1,
    "policy_id": "life-github-issue-lifecycle-v1",
    "runtime_control_authority": "NONE",
    "scope": "GITHUB_ENGINEERING_VISIBILITY_ONLY",
    "authorized_repository": "KINETIC-DESIGN-CO/Build",
    "registry_path": "governance/work-admissions.json",
    "workflow_path": ".github/workflows/issue-lifecycle.yml",
    "issue_state_source": "AUTHORITATIVE_GITHUB_ISSUE_READBACK",
    "native_close_mode": "COMBINE_LINKED_PR_AUTO_CLOSE_WITH_REPOSITORY_RECONCILIATION",
    "terminal_admission_states": {"COMPLETE": "completed", "REMOVED": "not_planned"},
    "nonterminal_admission_state": "ADMITTED",
    "reconciliation_trigger": "EVERY_PUSH_TO_MAIN_AND_EXPLICIT_WORKFLOW_DISPATCH",
    "reconciliation_rules": RULES,
    "terminal_binding": "ADMITTED_ISSUE_SELECTED_WORK_TERMINAL_TRUE_ONLY_IF_ADMISSION_STATE_IS_COMPLETE_OR_REMOVED_AND_GITHUB_ISSUE_CLOSED_STATE_READBACK_IS_VERIFIED_WITH_MAPPED_REASON",
    "redispatch_binding": "TERMINAL_REDISPATCH_MAY_RUN_ONLY_AFTER_TERMINAL_BINDING_IS_TRUE_FOR_THE_COMPLETED_ADMITTED_ISSUE",
    "native_link_rule": "A_DEFAULT_BRANCH_PULL_REQUEST_MAY_USE_A_GITHUB_SUPPORTED_CLOSING_LINK_BUT_NATIVE_CLOSE_DOES_NOT_REPLACE_AUTHORITATIVE_READBACK",
    "failure_rule": "OPEN_OR_UNREADABLE_OR_WRONG_REASON_GITHUB_ISSUE_FOR_TERMINAL_ADMISSION_RETURNS_NONTERMINAL_CLEANUP_STATE",
    "states": STATES,
}


class LifecycleError(RuntimeError):
    pass


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise LifecycleError(f"invalid JSON {path.relative_to(ROOT)}: {exc}") from exc


def validate_policy():
    policy = load(POLICY_PATH)
    schema = load(SCHEMA_PATH)
    if not isinstance(policy, dict) or set(policy) != ROOT_KEYS:
        raise LifecycleError("issue lifecycle policy root keys mismatch")
    for key, value in EXACT.items():
        if policy.get(key) != value:
            raise LifecycleError(f"issue lifecycle policy field mismatch: {key}")
    if not isinstance(schema, dict):
        raise LifecycleError("issue lifecycle schema must be object")
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise LifecycleError("issue lifecycle schema draft mismatch")
    if schema.get("additionalProperties") is not False:
        raise LifecycleError("issue lifecycle schema must reject unknown root properties")
    if set(schema.get("required", [])) != ROOT_KEYS:
        raise LifecycleError("issue lifecycle schema required keys mismatch")
    if set(schema.get("properties", {})) != ROOT_KEYS:
        raise LifecycleError("issue lifecycle schema property keys mismatch")
    admissions = load(ADMISSIONS_PATH)
    items = admissions.get("items") if isinstance(admissions, dict) else None
    if not isinstance(items, list):
        raise LifecycleError("work admissions items missing")
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise LifecycleError("work admissions item must be object")
        issue = item.get("source_issue_number")
        work_item_id = item.get("work_item_id")
        state = item.get("state")
        if not isinstance(issue, int) or isinstance(issue, bool) or issue < 1:
            raise LifecycleError("work admissions issue number invalid")
        if work_item_id != f"github-issue-{issue}":
            raise LifecycleError("work admissions issue identity mismatch")
        if issue in seen:
            raise LifecycleError("duplicate source issue number")
        if state not in {"ADMITTED", "COMPLETE", "REMOVED"}:
            raise LifecycleError("work admissions state invalid")
        seen.add(issue)
    return policy, admissions


def terminal_operations(policy, admissions):
    mapping = policy["terminal_admission_states"]
    operations = []
    for item in admissions["items"]:
        state = item["state"]
        if state in mapping:
            operations.append(
                {
                    "work_item_id": item["work_item_id"],
                    "issue_number": item["source_issue_number"],
                    "admission_state": state,
                    "expected_state": "closed",
                    "expected_reason": mapping[state],
                }
            )
    operations.sort(key=lambda row: (row["issue_number"], row["work_item_id"]))
    return operations


def evaluate_snapshot(policy, admissions, snapshot):
    if not isinstance(snapshot, dict) or set(snapshot) != {"issues"} or not isinstance(snapshot["issues"], dict):
        raise LifecycleError("snapshot must be object with exact issues object")
    mapping = policy["terminal_admission_states"]
    results = []
    for item in sorted(admissions["items"], key=lambda row: (row["source_issue_number"], row["work_item_id"])):
        state = item["state"]
        issue_number = item["source_issue_number"]
        row = {
            "work_item_id": item["work_item_id"],
            "issue_number": issue_number,
            "admission_state": state,
            "selected_work_terminal": False,
        }
        if state == policy["nonterminal_admission_state"]:
            row["lifecycle_state"] = "ADMISSION_NONTERMINAL"
            results.append(row)
            continue
        expected_reason = mapping[state]
        observed = snapshot["issues"].get(str(issue_number))
        if observed is None:
            row["lifecycle_state"] = "READBACK_NOT_RUN"
            results.append(row)
            continue
        if not isinstance(observed, dict) or set(observed) != {"state", "state_reason"}:
            raise LifecycleError(f"issue {issue_number} snapshot shape mismatch")
        if observed["state"] != "closed":
            row["lifecycle_state"] = "CLOSE_REQUIRED"
            results.append(row)
            continue
        if observed["state_reason"] != expected_reason:
            row["lifecycle_state"] = "REASON_RECONCILIATION_REQUIRED"
            results.append(row)
            continue
        row["lifecycle_state"] = "VERIFIED_TERMINAL"
        row["selected_work_terminal"] = True
        results.append(row)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-policy", action="store_true")
    parser.add_argument("--terminal-operations", action="store_true")
    parser.add_argument("--evaluate-snapshot")
    args = parser.parse_args()
    try:
        policy, admissions = validate_policy()
        if args.terminal_operations:
            for row in terminal_operations(policy, admissions):
                print(f"{row['issue_number']}\t{row['expected_reason']}")
        elif args.evaluate_snapshot:
            snapshot = load(Path(args.evaluate_snapshot))
            print(json.dumps({"results": evaluate_snapshot(policy, admissions, snapshot)}, sort_keys=True))
        elif args.validate_policy:
            print("ISSUE_LIFECYCLE_POLICY_VALID")
        else:
            parser.error("one action is required")
    except LifecycleError as exc:
        print(f"ISSUE_LIFECYCLE_INVALID: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
