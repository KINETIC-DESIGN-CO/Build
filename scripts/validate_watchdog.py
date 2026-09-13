#!/usr/bin/env python3
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "watchdog" / "spec.json"
REGISTRY_PATH = ROOT / "watchdog" / "finding-registry.json"
SPEC_SCHEMA_PATH = ROOT / "watchdog" / "schema" / "spec.schema.json"
REGISTRY_SCHEMA_PATH = ROOT / "watchdog" / "schema" / "finding-registry.schema.json"

REQUIRED_PATHS = [SPEC_PATH, REGISTRY_PATH, SPEC_SCHEMA_PATH, REGISTRY_SCHEMA_PATH]
ALLOWED_OPS = {"EQ","NE","IN","NOT_IN","REGEX","LT","LTE","GT","GTE","SET_EQ","SUBSET","DIFF_EMPTY","HASH_EQ","EXISTS","AND","OR"}
SEVERITIES = {"CRITICAL","HIGH","MEDIUM","LOW"}
NOTIFICATION_EVENTS = {
    "NEW_VERIFIED_OPEN","VERSIONED_SEVERITY_CHANGE","VERIFIED_RESOLVED",
    "CONTROL_PLANE_UNVERIFIED_AFTER_RETRY","BOOTSTRAP_FAIL","SELF_AUDIT_DRIFT"
}
EXPECTED_SOURCE_CONTRACT_PATHS = {
    "continuity/bootstrap.json",
    "continuity/response-contract.json",
    "coordination/protocol.json",
    "governance/placement-policy.json",
}
EXPECTED_EXECUTOR_PROMPT = (
    "Run one Build Repository Watchdog cycle using embedded executor contract "
    "build-watchdog-executor-v2 and schedule contract build-watchdog-hourly-denver-v1. "
    "Read current main in KINETIC-DESIGN-CO/Build and load watchdog/spec.json and "
    "watchdog/finding-registry.json; do not use cached copies. Execute only the behaviors "
    "permitted by those current versioned sources. Perform the self-audit defined there "
    "before finding classification. Never alter this task prompt, schedule, authority, or "
    "mutation boundary from inside a run. If the embedded executor or schedule contract ID "
    "differs from current source, disable Issue mutations, perform only the permitted "
    "read-only control-plane audit, notify Vince of the exact drift, and do not repair the "
    "task. Do not repair Life. Mutate GitHub Issues only when current main source explicitly "
    "enables the exact operation and every registered precondition passes; otherwise remain "
    "read-only. Treat prose and model judgment as zero authority. Treat a null canonical "
    "Vercel target as EXPECTED_NOT_RUN."
)


class ValidationError(Exception):
    pass


def load_json(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ValidationError(f"missing:{path.relative_to(ROOT)}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid-json:{path.relative_to(ROOT)}:{exc}") from exc


def expect(condition, message):
    if not condition:
        raise ValidationError(message)


def validate_predicate(node, allowed_ops):
    expect(isinstance(node, dict), "predicate:not-object")
    expect("op" in node, "predicate:missing-op")
    op = node["op"]
    expect(op in allowed_ops, f"predicate:unsupported-op:{op}")
    if op in {"AND", "OR"}:
        expect(set(node) == {"op", "args"}, f"predicate:{op}:keys")
        expect(isinstance(node["args"], list) and len(node["args"]) >= 2, f"predicate:{op}:args")
        for child in node["args"]:
            validate_predicate(child, allowed_ops)
        return
    expect(set(node) <= {"op", "left", "right"}, f"predicate:{op}:keys")
    expect("left" in node, f"predicate:{op}:missing-left")
    if op != "EXISTS":
        expect("right" in node, f"predicate:{op}:missing-right")


def validate_spec(spec):
    expect(spec.get("schema_version") == 1, "spec:schema-version")
    expect(spec.get("watchdog_id") == "build-repository-watchdog-v1", "spec:watchdog-id")
    expect(spec.get("runtime_control_authority") == "NONE", "spec:runtime-authority")
    expect(spec.get("source_control_authority") == "NONE", "spec:source-authority")
    repo = spec.get("authorized_repository", {})
    expect(repo == {"repository_id": 1366835183, "full_name": "KINETIC-DESIGN-CO/Build", "default_branch": "main"}, "spec:repository")
    ext = spec.get("authorized_external_targets", {})
    expect(ext.get("supabase_project_id") == "jnenguxodtgwbskhdsxt", "spec:supabase-target")
    expect(ext.get("vercel_target_source") == "continuity/current.json.authorized_targets.vercel", "spec:vercel-source")
    expect(ext.get("vercel_null_state") == "EXPECTED_NOT_RUN", "spec:vercel-null")
    schedule = spec.get("schedule", {})
    expect(schedule.get("timezone") == "America/Denver", "spec:timezone")
    expect(schedule.get("cadence") == "HOURLY", "spec:cadence")
    expect(schedule.get("deep_audit_local_hours") == [2, 14], "spec:deep-hours")
    expect(schedule.get("daily_summary_local_hour") == 14, "spec:summary-hour")
    expect(schedule.get("schedule_contract_id") == "build-watchdog-hourly-denver-v1", "spec:schedule-contract")
    expect(spec.get("audit_layers") == ["CONTROL_PLANE", "DEEP", "SELF_AUDIT"], "spec:audit-layers")
    expect(set(spec.get("detector_states", [])) == {"PASS", "FAIL", "UNVERIFIED", "UNKNOWN", "NOT_RUN", "EXPECTED_NOT_RUN"}, "spec:detector-states")
    expect(set(spec.get("finding_lifecycle_states", [])) == {"VERIFIED_OPEN", "FIX_APPEARS_PRESENT_VERIFICATION_PENDING", "VERIFIED_RESOLVED"}, "spec:lifecycle")
    expect(set(spec.get("deep_audit_states", [])) == {"COMPLETE_PASS", "COMPLETE_FINDINGS", "PARTIAL"}, "spec:deep-states")
    expect(set(spec.get("severity_states", [])) == SEVERITIES, "spec:severity-states")
    expect(set(spec.get("allowed_predicate_ops", [])) == ALLOWED_OPS, "spec:predicate-ops")
    rf = spec.get("read_failure", {})
    expect(rf == {"retry_count": 1, "after_retry_failure": "UNVERIFIED", "absence_is_fail_only_after_successful_authoritative_read": True}, "spec:read-failure")
    issue = spec.get("issue_mutation", {})
    expect(issue.get("mode") == "DISABLED", "spec:issue-mode")
    expect(issue.get("close_policy_default") == "REVIEW_REQUIRED", "spec:close-policy")
    expect(issue.get("auto_close_allowed") is False, "spec:auto-close")
    sa = spec.get("self_audit", {})
    expect(sa.get("lightweight_frequency") == "EVERY_RUN", "spec:self-lightweight")
    expect(sa.get("capability_reevaluation_frequency") == "DEEP_AUDIT_ONLY", "spec:self-capability-frequency")
    expect(sa.get("executor_contract_id") == "build-watchdog-executor-v2", "spec:executor-contract")
    expect(sa.get("schedule_contract_id") == schedule.get("schedule_contract_id"), "spec:self-schedule-contract")
    expect(sa.get("executor_prompt_template") == EXPECTED_EXECUTOR_PROMPT, "spec:executor-prompt")
    expect(sa.get("executor_contract_change_rule") == "BUMP_EXECUTOR_CONTRACT_ID_IF_AND_ONLY_IF_EXECUTOR_PROMPT_TEMPLATE_CHANGES", "spec:executor-change-rule")
    expect(sa.get("schedule_contract_change_rule") == "BUMP_SCHEDULE_CONTRACT_ID_IF_ANY_OF_TIMEZONE_CADENCE_DEEP_AUDIT_LOCAL_HOURS_DAILY_SUMMARY_LOCAL_HOUR_CHANGES", "spec:schedule-change-rule")
    expect(sa.get("source_change_executor_rule") == "DO_NOT_BUMP_EXECUTOR_CONTRACT_ID_WHEN_EXECUTOR_PROMPT_TEMPLATE_IS_BYTE_IDENTICAL", "spec:source-executor-rule")
    expect(sa.get("instruction_adjustment_mode") == "VERSIONED_SOURCE_ONLY", "spec:self-adjustment")
    expect(sa.get("task_prompt_mutation") == "FORBIDDEN", "spec:self-task-mutation")
    expect(sa.get("authority_expansion") == "FORBIDDEN", "spec:self-authority-expansion")
    paths = sa.get("source_contract_paths")
    expect(isinstance(paths, list), "spec:source-contract-paths")
    expect(set(paths) == EXPECTED_SOURCE_CONTRACT_PATHS and len(paths) == len(set(paths)), "spec:source-contract-path-set")
    expect(sa.get("source_contract_validation_mode") == "CURRENT_TREE_STRUCTURAL_COMPATIBILITY", "spec:source-contract-validation-mode")
    expect(sa.get("source_contract_change_effect") == "RUN_CURRENT_TREE_STRUCTURAL_COMPATIBILITY_VALIDATION", "spec:source-change-effect")
    expect("source_contract_fingerprints" not in sa, "spec:manual-source-fingerprints-forbidden")
    expect(sa.get("architecture_compatibility_rule") == "ALL_REGISTERED_ASSUMPTIONS_PASS", "spec:self-compat-rule")
    expect(sa.get("source_change_rule") == "REVALIDATE_ALL_REGISTERED_ASSUMPTIONS", "spec:self-source-rule")
    assumption_ids = [x.get("id") for x in sa.get("capability_assumptions", [])]
    expect(len(assumption_ids) == len(set(assumption_ids)) and assumption_ids, "spec:self-assumption-ids")
    boundary = spec.get("mutation_boundary", {})
    for key in ["source_files", "branches", "pull_requests_as_implementation", "merge", "rulesets", "coordination_claims", "continuity", "supabase", "vercel", "runtime", "project_instructions"]:
        expect(boundary.get(key) == "FORBIDDEN", f"spec:boundary:{key}")
    expect(boundary.get("issue_operations") == "ONLY_IF_ISSUE_MUTATION_MODE_ENABLED", "spec:boundary:issues")


def source_contract_documents_from_tree():
    return {rel_path: load_json(ROOT / rel_path) for rel_path in EXPECTED_SOURCE_CONTRACT_PATHS}


def validate_source_contract_documents(documents):
    expect(isinstance(documents, dict) and set(documents) == EXPECTED_SOURCE_CONTRACT_PATHS, "source-contract:document-set")
    bootstrap = documents["continuity/bootstrap.json"]
    expect(bootstrap.get("schema_version") == 1, "source-contract:bootstrap-schema")
    expect(bootstrap.get("project_id") == "life", "source-contract:bootstrap-project")
    expect(bootstrap.get("runtime_control_authority") == "NONE", "source-contract:bootstrap-authority")
    expect(bootstrap.get("canonical_repository") == {"repository_id": 1366835183, "full_name": "KINETIC-DESIGN-CO/Build", "default_branch": "main"}, "source-contract:bootstrap-repository")
    required_files = bootstrap.get("required_files")
    required_read_order = bootstrap.get("required_read_order")
    expect(isinstance(required_files, list) and required_files and len(required_files) == len(set(required_files)), "source-contract:bootstrap-required-files")
    expect(isinstance(required_read_order, list) and required_read_order and len(required_read_order) == len(set(required_read_order)), "source-contract:bootstrap-read-order")
    expect(set(required_read_order) <= set(required_files), "source-contract:bootstrap-read-order-subset")

    response = documents["continuity/response-contract.json"]
    expect(response.get("schema_version") == 1, "source-contract:response-schema")
    expect(response.get("contract_id") == "life-response-contract-v1", "source-contract:response-id")
    expect(response.get("runtime_control_authority") == "NONE", "source-contract:response-authority")

    protocol = documents["coordination/protocol.json"]
    expect(protocol.get("schema_version") == 1, "source-contract:coordination-schema")
    expect(protocol.get("protocol_id") == "life-source-coordination-v3", "source-contract:coordination-id")
    expect(protocol.get("runtime_control_authority") == "NONE", "source-contract:coordination-runtime-authority")
    expect(protocol.get("source_coordination_authority") == "GITHUB_MACHINE_STATE", "source-contract:coordination-authority")
    expect(protocol.get("canonical_repository") == "KINETIC-DESIGN-CO/Build", "source-contract:coordination-repository")
    expect(protocol.get("default_branch") == "main", "source-contract:coordination-default-branch")

    placement = documents["governance/placement-policy.json"]
    expect(placement.get("schema_version") == 1, "source-contract:placement-schema")
    expect(placement.get("policy_id") == "life-governance-placement-v1", "source-contract:placement-id")
    expect(placement.get("runtime_control_authority") == "NONE", "source-contract:placement-authority")
    expect(placement.get("canonical_owner_rule") == "ONE_REQUIREMENT_ONE_CANONICAL_OWNER_OTHER_SURFACES_REFERENCE_ONLY", "source-contract:placement-owner-rule")
    return True


def validate_source_contracts(spec):
    expect(spec["self_audit"]["source_contract_validation_mode"] == "CURRENT_TREE_STRUCTURAL_COMPATIBILITY", "source-contract:mode")
    return validate_source_contract_documents(source_contract_documents_from_tree())


def validate_registry(registry, spec):
    expect(registry.get("schema_version") == 1, "registry:schema-version")
    expect(registry.get("registry_id") == "build-watchdog-findings-v1", "registry:id")
    expect(registry.get("runtime_control_authority") == "NONE", "registry:runtime-authority")
    expect(registry.get("dedupe_key_fields") == ["finding_type_id", "subject_key"], "registry:dedupe")
    findings = registry.get("findings")
    expect(isinstance(findings, list) and findings, "registry:findings")
    ids = []
    detectors = []
    for finding in findings:
        fid = finding.get("finding_type_id")
        did = finding.get("detector_id")
        expect(isinstance(fid, str) and re.fullmatch(r"[A-Z0-9_]+", fid), "registry:finding-id")
        expect(isinstance(did, str) and re.fullmatch(r"[A-Z0-9_]+", did), "registry:detector-id")
        ids.append(fid)
        detectors.append(did)
        expect(finding.get("severity") in SEVERITIES, f"registry:severity:{fid}")
        expect(isinstance(finding.get("subject_key_rule"), str) and finding["subject_key_rule"], f"registry:subject:{fid}")
        validate_predicate(finding.get("fail_predicate"), ALLOWED_OPS)
        validate_predicate(finding.get("resolution_predicate"), ALLOWED_OPS)
        expect(isinstance(finding.get("deep_on_fail"), bool), f"registry:deep:{fid}")
        events = finding.get("notification_events")
        expect(isinstance(events, list) and events and set(events) <= NOTIFICATION_EVENTS, f"registry:notifications:{fid}")
        expect(finding.get("issue_write_policy") == "DISABLED_UNTIL_GLOBAL_ISSUE_MUTATION_ENABLED", f"registry:issue-policy:{fid}")
        expect(finding.get("close_policy") == "REVIEW_REQUIRED", f"registry:close-policy:{fid}")
    expect(len(ids) == len(set(ids)), "registry:duplicate-finding-id")
    expect(len(detectors) == len(set(detectors)), "registry:duplicate-detector-id")
    required_findings = {"WATCHDOG_EXECUTOR_STALE", "WATCHDOG_SCHEDULE_STALE", "WATCHDOG_SOURCE_INVALID", "WATCHDOG_CAPABILITY_DRIFT", "WATCHDOG_OBSERVABILITY_LOSS", "SCHEMA_VALIDATION_COVERAGE_GAP", "LEASE_DURATION_ENFORCEMENT_GAP", "LOCK_TRANSITION_ENFORCEMENT_GAP", "MERGE_TIME_INTEGRATION_FRESHNESS_GAP"}
    expect(required_findings <= set(ids), "registry:required-findings")


def validate_schema_envelopes():
    for path, title in [(SPEC_SCHEMA_PATH, "Build Repository Watchdog Specification"), (REGISTRY_SCHEMA_PATH, "Build Repository Watchdog Finding Registry")]:
        schema = load_json(path)
        expect(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", f"schema:dialect:{path.name}")
        expect(schema.get("title") == title, f"schema:title:{path.name}")
        expect(schema.get("type") == "object", f"schema:type:{path.name}")
        expect(schema.get("additionalProperties") is False, f"schema:closed:{path.name}")


def validate():
    for path in REQUIRED_PATHS:
        expect(path.exists(), f"missing:{path.relative_to(ROOT)}")
    spec = load_json(SPEC_PATH)
    registry = load_json(REGISTRY_PATH)
    validate_spec(spec)
    validate_source_contracts(spec)
    validate_registry(registry, spec)
    validate_schema_envelopes()
    return True


if __name__ == "__main__":
    try:
        validate()
    except ValidationError as exc:
        print(f"INVALID:{exc}")
        raise SystemExit(1)
    print("VALID")
