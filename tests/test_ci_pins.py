import unittest

from scripts.validate_ci_pins import validate_workflow_text


CHECKOUT_SHA = "11d5960a326750d5838078e36cf38b85af677262"
SETUP_PYTHON_SHA = "a26af69be951a213d495a4c3e4e4022e16d87065"
SUPABASE_SETUP_SHA = "46f7f98c7f948ad727d22c1e67fab04c223a0520"


class CiPinValidationTests(unittest.TestCase):
    def errors(self, text: str) -> list[str]:
        return validate_workflow_text(text, "test.yml")

    def test_accepts_full_commit_shas_and_stable_supabase_cli_version(self):
        workflow = f"""
name: validate
jobs:
  validate:
    steps:
      - name: Checkout
        uses: actions/checkout@{CHECKOUT_SHA} # v4.4.0
      - name: Python
        uses: actions/setup-python@{SETUP_PYTHON_SHA} # v5.6.0
      - name: Supabase
        uses: supabase/setup-cli@{SUPABASE_SETUP_SHA} # v3.0.0
        with:
          version: 2.117.0
"""
        self.assertEqual([], self.errors(workflow))

    def test_rejects_moving_action_tag(self):
        errors = self.errors("jobs:\n  x:\n    steps:\n      - uses: actions/checkout@v4\n")
        self.assertTrue(any("full 40-hex commit SHA" in error for error in errors))

    def test_rejects_branch_action_ref(self):
        errors = self.errors("jobs:\n  x:\n    steps:\n      - uses: owner/action@main\n")
        self.assertTrue(any("full 40-hex commit SHA" in error for error in errors))

    def test_rejects_future_third_party_action_tag(self):
        errors = self.errors("jobs:\n  x:\n    steps:\n      - uses: vendor/new-action@v1\n")
        self.assertEqual(1, len(errors))
        self.assertIn("full 40-hex commit SHA", errors[0])

    def test_allows_local_action(self):
        errors = self.errors("jobs:\n  x:\n    steps:\n      - uses: ./.github/actions/local-check\n")
        self.assertEqual([], errors)

    def test_rejects_latest_supabase_cli(self):
        workflow = f"""
jobs:
  x:
    steps:
      - name: Supabase
        uses: supabase/setup-cli@{SUPABASE_SETUP_SHA}
        with:
          version: latest
"""
        errors = self.errors(workflow)
        self.assertEqual(1, len(errors))
        self.assertIn("exact stable X.Y.Z", errors[0])

    def test_rejects_prerelease_supabase_cli(self):
        workflow = f"""
jobs:
  x:
    steps:
      - uses: supabase/setup-cli@{SUPABASE_SETUP_SHA}
        with:
          version: 2.118.0-beta.2
"""
        errors = self.errors(workflow)
        self.assertEqual(1, len(errors))
        self.assertIn("exact stable X.Y.Z", errors[0])

    def test_requires_supabase_cli_version(self):
        workflow = f"""
jobs:
  x:
    steps:
      - uses: supabase/setup-cli@{SUPABASE_SETUP_SHA}
      - run: supabase db start
"""
        errors = self.errors(workflow)
        self.assertEqual(1, len(errors))
        self.assertIn("exactly one with.version", errors[0])

    def test_direct_uses_step_does_not_consume_next_steps_version(self):
        workflow = f"""
jobs:
  x:
    steps:
      - uses: supabase/setup-cli@{SUPABASE_SETUP_SHA}
      - name: Unrelated
        run: echo ok
        env:
          version: 2.117.0
"""
        errors = self.errors(workflow)
        self.assertEqual(1, len(errors))
        self.assertIn("exactly one with.version", errors[0])

    def test_accepts_quoted_pinned_reference(self):
        workflow = f'''jobs:\n  x:\n    steps:\n      - uses: "actions/checkout@{CHECKOUT_SHA}" # reviewed\n'''
        self.assertEqual([], self.errors(workflow))


if __name__ == "__main__":
    unittest.main()
