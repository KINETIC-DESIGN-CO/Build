from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_relevant_lock_history.py"
spec = importlib.util.spec_from_file_location("validate_relevant_lock_history", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class RelevantLockHistoryTests(unittest.TestCase):
    def test_relevant_lock_branches_uses_only_changed_work_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rel = "coordination/work/00000000-0000-4000-8000-000000000001.json"
            path = root / rel
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"claims": [{"lock_branch": "lock/" + "a" * 64}]}), encoding="utf-8")
            with mock.patch.object(mod, "ROOT", root):
                branches = mod.relevant_lock_branches([rel, "governance/example.json"])
        self.assertEqual(branches, ["lock/" + "a" * 64])

    def test_unrelated_empty_branch_is_not_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rel = "coordination/work/00000000-0000-4000-8000-000000000001.json"
            path = root / rel
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"claims": [{"lock_branch": "lock/" + "a" * 64}]}), encoding="utf-8")
            with mock.patch.object(mod, "ROOT", root):
                branches = mod.relevant_lock_branches([rel])
        self.assertNotIn("lock/" + "b" * 64, branches)

    def test_relevant_empty_branch_still_fails_closed(self):
        protocol = {"lock_history_enforcement_start_utc": "2026-09-12T22:56:23Z"}
        with mock.patch.object(mod.lock_history, "history_entries_for_branch", return_value=[]), mock.patch.object(
            mod.lock_history, "run_git", return_value="2026-09-12T22:57:00+00:00"
        ):
            with self.assertRaises(mod.lock_history.ValidationError):
                mod.validate_branch("lock/" + "a" * 64, protocol)

    def test_global_validator_still_rejects_post_epoch_empty_branch(self):
        protocol = {"lock_history_enforcement_start_utc": "2026-09-12T22:56:23Z"}
        with self.assertRaises(mod.lock_history.ValidationError):
            mod.lock_history.validate_empty_branch_tip(
                datetime(2026, 9, 12, 22, 57, tzinfo=timezone.utc), protocol
            )

    def test_pull_request_diff_uses_event_base_and_head(self):
        event = {"pull_request": {"base": {"sha": "1" * 40}, "head": {"sha": "2" * 40}}}
        with mock.patch.object(
            mod,
            "git",
            return_value="coordination/work/00000000-0000-4000-8000-000000000001.json\nx.txt",
        ) as git_call:
            paths = mod.changed_paths_for_event("pull_request", event, "")
        self.assertEqual(paths, ["coordination/work/00000000-0000-4000-8000-000000000001.json", "x.txt"])
        git_call.assert_called_once_with("diff", "--name-only", f"{'1' * 40}...{'2' * 40}")


if __name__ == "__main__":
    unittest.main()
