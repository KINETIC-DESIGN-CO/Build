from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_ci_dependencies.py"
spec = importlib.util.spec_from_file_location("validate_ci_dependencies", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

POLICY = {
    "schema_version": 1,
    "policy_id": "life-ci-dependency-pins-v1",
    "runtime_control_authority": "NONE",
    "workflow_paths": [".github/workflows/continuity.yml"],
    "actions": [
        {
            "repository": "actions/checkout",
            "commit_sha": "3d3c42e5aac5ba805825da76410c181273ba90b1",
            "release": "v7.0.1",
            "required_occurrences": 1,
        },
        {
            "repository": "actions/setup-python",
            "commit_sha": "5fda3b95a4ea91299a34e894583c3862153e4b97",
            "release": "v7.0.0",
            "required_occurrences": 1,
        },
        {
            "repository": "supabase/setup-cli",
            "commit_sha": "46f7f98c7f948ad727d22c1e67fab04c223a0520",
            "release": "v3.0.0",
            "required_occurrences": 1,
        },
    ],
    "supabase_cli": {"version": "2.117.0"},
    "rules": [
        "THIRD_PARTY_ACTION_REFS_MUST_EQUAL_POLICY_COMMIT_SHA",
        "UNLISTED_THIRD_PARTY_ACTIONS_FAIL_CLOSED",
        "SUPABASE_CLI_VERSION_MUST_EQUAL_POLICY_EXACT_VERSION",
        "LOCAL_ACTIONS_MAY_USE_RELATIVE_PATHS",
    ],
}

GOOD = """name: test
jobs:
  validate:
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: \"3.12\"
      - uses: ./local-action
      - name: Supabase
        uses: supabase/setup-cli@46f7f98c7f948ad727d22c1e67fab04c223a0520 # v3.0.0
        with:
          version: 2.117.0
"""


class CiDependencyPolicyTests(unittest.TestCase):
    def test_exact_pins_are_valid(self):
        mod.validate_workflow_text(GOOD, POLICY)

    def test_mutable_tag_is_rejected(self):
        bad = GOOD.replace(
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            "actions/checkout@v7",
        )
        with self.assertRaises(mod.PolicyError):
            mod.validate_workflow_text(bad, POLICY)

    def test_branch_ref_is_rejected(self):
        bad = GOOD.replace(
            "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
            "actions/setup-python@main",
        )
        with self.assertRaises(mod.PolicyError):
            mod.validate_workflow_text(bad, POLICY)

    def test_unlisted_third_party_action_fails_closed(self):
        bad = GOOD.replace(
            "      - uses: ./local-action\n",
            "      - uses: example/unknown@0123456789012345678901234567890123456789\n",
        )
        with self.assertRaises(mod.PolicyError):
            mod.validate_workflow_text(bad, POLICY)

    def test_latest_supabase_cli_is_rejected(self):
        bad = GOOD.replace("version: 2.117.0", "version: latest")
        with self.assertRaises(mod.PolicyError):
            mod.validate_workflow_text(bad, POLICY)

    def test_wrong_fixed_supabase_cli_is_rejected(self):
        bad = GOOD.replace("version: 2.117.0", "version: 2.116.0")
        with self.assertRaises(mod.PolicyError):
            mod.validate_workflow_text(bad, POLICY)

    def test_duplicate_required_action_is_rejected(self):
        bad = GOOD.replace(
            "      - uses: ./local-action\n",
            "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n",
        )
        with self.assertRaises(mod.PolicyError):
            mod.validate_workflow_text(bad, POLICY)

    def test_policy_rejects_non_sha_action_pin(self):
        bad = json.loads(json.dumps(POLICY))
        bad["actions"][0]["commit_sha"] = "v7"
        with self.assertRaises(mod.PolicyError):
            mod.validate_policy(bad)

    def test_policy_rejects_floating_cli_version(self):
        bad = json.loads(json.dumps(POLICY))
        bad["supabase_cli"]["version"] = "latest"
        with self.assertRaises(mod.PolicyError):
            mod.validate_policy(bad)


if __name__ == "__main__":
    unittest.main()
