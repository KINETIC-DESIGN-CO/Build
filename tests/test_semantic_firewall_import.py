from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIREWALL_DIR = REPO_ROOT / "contracts" / "semantic-firewall"
SOURCE_TREE_SHA = "ca4b5d72897f17dc2f9d929186f41d6c93ba2dbc"
EXPECTED_BLOBS = {
    "artifact-byte-identity.acceptance.json": "f5af029e83b3ae115934cbc3684c59390252dd85",
    "contract-reference.acceptance.json": "fe5bbb12f7365c5bf0405a0ee78397ab8b934654",
    "control-input-binding.acceptance.json": "8a74bfc60f2d62941e75ad33258069e3378865a1",
    "control-request.acceptance.json": "adfbf6a823120990fd5782db3ac51ae62146f05b",
    "receipt-execution-binding.acceptance.json": "e522a1f7ea72474204ad00ed384caadb6cc714d2",
    "receipt_execution_binding_inner.py": "771e97168051f0f19c3f384d72da8ed83d802aef",
    "run_artifact_byte_identity_acceptance.py": "b1f4bfe92601cd78e59a851e20cd344a53bb9704",
    "run_contract_reference_acceptance.py": "ad952e8aea4388a5782865735bf7630c136cffcd",
    "run_control_input_binding_acceptance.py": "44677fa47b344c3e6a018c4e4dc51daa5395de29",
    "run_control_request_acceptance.py": "c40a0aebcaecc7aac671638c436f262b870788f4",
    "run_receipt_execution_binding_acceptance.py": "37ecc081c99f7145317dc6445eb4abf0fd303b83",
    "run_typed_contract_evaluation_acceptance.py": "8d1b80205a0a3fd9fede9d767eb3a6b54010950a",
    "typed-contract-evaluation.acceptance.json": "fdef722d326e26582b731b804ce5ab9e4ab9d601",
}
RUNNERS = (
    "run_control_request_acceptance.py",
    "run_contract_reference_acceptance.py",
    "run_control_input_binding_acceptance.py",
    "run_typed_contract_evaluation_acceptance.py",
    "run_artifact_byte_identity_acceptance.py",
    "run_receipt_execution_binding_acceptance.py",
)


class SemanticFirewallImportTests(unittest.TestCase):
    def test_exact_legacy_tree_and_blob_identities(self) -> None:
        actual_files = {
            path.name
            for path in FIREWALL_DIR.iterdir()
            if path.is_file()
        }
        self.assertEqual(actual_files, set(EXPECTED_BLOBS))

        tree = subprocess.run(
            ["git", "rev-parse", "HEAD:contracts/semantic-firewall"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        self.assertEqual(tree, SOURCE_TREE_SHA)

        for name, expected_sha in EXPECTED_BLOBS.items():
            actual_sha = subprocess.run(
                ["git", "hash-object", str(FIREWALL_DIR / name)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            self.assertEqual(actual_sha, expected_sha, name)

    def test_all_legacy_acceptance_runners_pass(self) -> None:
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                completed = subprocess.run(
                    [sys.executable, str(FIREWALL_DIR / runner)],
                    cwd=REPO_ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=180,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    f"{runner}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
                )
                lines = [line for line in completed.stdout.splitlines() if line.strip()]
                self.assertTrue(lines, runner)
                result = json.loads(lines[-1])
                self.assertEqual(result.get("result"), "PASS", runner)

    def test_receipt_inner_runner_requires_provenance_wrapper(self) -> None:
        env = os.environ.copy()
        env.pop("LIFE_SF_PROVENANCE_STAGE", None)
        env.pop("LIFE_SF_PROVENANCE_MANIFEST", None)
        completed = subprocess.run(
            [sys.executable, str(FIREWALL_DIR / "receipt_execution_binding_inner.py")],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
            env=env,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(
            completed.stderr.strip(),
            "CONTRACT_ERROR: receipt execution binding inner runner requires provenance wrapper",
        )


if __name__ == "__main__":
    unittest.main()
