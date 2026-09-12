#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "ci-dependency-policy.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
USES_RE = re.compile(r"^(\s*)(?:-\s*)?uses:\s*([^\s#]+)(?:\s+#.*)?$")
STEP_RE = re.compile(r"^(\s*)-\s+")
VERSION_RE = re.compile(r"^\s*version:\s*([^\s#]+)(?:\s+#.*)?$")


class PolicyError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise PolicyError(message)


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
        "workflow_paths",
        "actions",
        "supabase_cli",
        "rules",
    }
    if set(policy) != required:
        fail("policy keys mismatch")
    if policy["schema_version"] != 1:
        fail("schema_version must equal 1")
    if policy["policy_id"] != "life-ci-dependency-pins-v1":
        fail("policy_id mismatch")
    if policy["runtime_control_authority"] != "NONE":
        fail("runtime_control_authority must be NONE")
    paths = policy["workflow_paths"]
    if not isinstance(paths, list) or not paths or len(paths) != len(set(paths)):
        fail("workflow_paths must be nonempty unique array")
    if not all(isinstance(path, str) and path.startswith(".github/workflows/") for path in paths):
        fail("workflow_paths must contain workflow paths")
    actions = policy["actions"]
    if not isinstance(actions, list) or not actions:
        fail("actions must be nonempty array")
    repositories = []
    for action in actions:
        if not isinstance(action, dict) or set(action) != {
            "repository", "commit_sha", "release", "required_occurrences"
        }:
            fail("action entry keys mismatch")
        repo = action["repository"]
        if (
            not isinstance(repo, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo)
        ):
            fail("action repository invalid")
        if not SHA_RE.fullmatch(str(action["commit_sha"])):
            fail(f"{repo} commit_sha must be lowercase 40-hex")
        if not isinstance(action["release"], str) or not action["release"]:
            fail(f"{repo} release must be nonempty string")
        if action["required_occurrences"] != 1:
            fail(f"{repo} required_occurrences must equal 1")
        repositories.append(repo)
    if len(repositories) != len(set(repositories)):
        fail("action repositories must be unique")
    cli = policy["supabase_cli"]
    if not isinstance(cli, dict) or set(cli) != {"version"}:
        fail("supabase_cli keys mismatch")
    if not SEMVER_RE.fullmatch(str(cli["version"])):
        fail("supabase_cli.version must be exact numeric semver")
    rules = policy["rules"]
    expected_rules = {
        "THIRD_PARTY_ACTION_REFS_MUST_EQUAL_POLICY_COMMIT_SHA",
        "UNLISTED_THIRD_PARTY_ACTIONS_FAIL_CLOSED",
        "SUPABASE_CLI_VERSION_MUST_EQUAL_POLICY_EXACT_VERSION",
        "LOCAL_ACTIONS_MAY_USE_RELATIVE_PATHS",
    }
    if not isinstance(rules, list) or set(rules) != expected_rules or len(rules) != len(expected_rules):
        fail("rules mismatch")


def parse_uses(lines: list[str]) -> list[tuple[int, int, str]]:
    uses = []
    for index, line in enumerate(lines):
        match = USES_RE.match(line)
        if match:
            uses.append((index, len(match.group(1)), match.group(2)))
    return uses


def step_end(lines: list[str], start_index: int, indent: int) -> int:
    for index in range(start_index + 1, len(lines)):
        match = STEP_RE.match(lines[index])
        if match and len(match.group(1)) <= indent:
            return index
    return len(lines)


def validate_workflow_text(text: str, policy: dict, label: str = "<workflow>") -> None:
    validate_policy(policy)
    lines = text.splitlines()
    allowed = {item["repository"]: item for item in policy["actions"]}
    counts = {repo: 0 for repo in allowed}
    setup_cli_versions = []

    for index, indent, spec in parse_uses(lines):
        if spec.startswith("./"):
            continue
        if "@" not in spec:
            fail(f"{label}:{index + 1}: third-party uses reference missing @ref")
        repository, ref = spec.rsplit("@", 1)
        entry = allowed.get(repository)
        if entry is None:
            fail(f"{label}:{index + 1}: unlisted third-party action {repository}")
        if ref != entry["commit_sha"]:
            fail(
                f"{label}:{index + 1}: {repository} must use {entry['commit_sha']} "
                f"({entry['release']})"
            )
        counts[repository] += 1

        if repository == "supabase/setup-cli":
            end = step_end(lines, index, indent)
            versions = []
            for step_line in lines[index + 1:end]:
                match = VERSION_RE.match(step_line)
                if match:
                    versions.append(match.group(1).strip("\"'"))
            if len(versions) != 1:
                fail(f"{label}:{index + 1}: supabase/setup-cli must set exactly one version")
            setup_cli_versions.append(versions[0])

    for repository, entry in allowed.items():
        if counts[repository] != entry["required_occurrences"]:
            fail(
                f"{label}: {repository} occurrence count {counts[repository]} "
                f"!= {entry['required_occurrences']}"
            )

    if setup_cli_versions != [policy["supabase_cli"]["version"]]:
        fail(
            f"{label}: supabase CLI version must equal "
            f"{policy['supabase_cli']['version']}"
        )


def validate_repository(policy: dict) -> None:
    for rel in policy["workflow_paths"]:
        path = ROOT / rel
        if not path.is_file():
            fail(f"missing workflow: {rel}")
        validate_workflow_text(path.read_text(encoding="utf-8"), policy, rel)


def main() -> int:
    try:
        policy = load_policy()
        validate_repository(policy)
    except PolicyError as exc:
        print(f"CI_DEPENDENCY_POLICY_INVALID: {exc}", file=sys.stderr)
        return 1
    print("CI_DEPENDENCY_POLICY_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
