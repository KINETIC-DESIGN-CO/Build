import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "supabase" / "v05b" / "package-manifest.json"

class V05BPackageTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_non_live_authority(self):
        self.assertEqual(self.manifest["authority"], "SOURCE_ONLY_NON_LIVE")
        self.assertEqual(self.manifest["runtime_control_authority"], "NONE")
        self.assertEqual(self.manifest["active_runtime_caller_set"], [])
        self.assertEqual(self.manifest["danger_room_execution_state"], "NOT_RUN")
        self.assertEqual(self.manifest["remote_supabase_mutation_state"], "NOT_RUN")
        self.assertEqual(self.manifest["production_cutover_state"], "NOT_RUN")

    def test_exact_declared_file_set(self):
        files = self.manifest["declared_files"]
        self.assertEqual(files, sorted(set(files)))
        self.assertEqual(len(files), 35)
        self.assertTrue(all((ROOT / p).is_file() for p in files))

    def test_migration_sequence(self):
        self.assertEqual(
            self.manifest["migration_ids"],
            [f"202609200930{i:02d}" for i in range(1, 11)],
        )

    def test_replica_blind_spot_not_silently_retired(self):
        self.assertEqual(
            self.manifest["replica_mode_blind_spot_state"],
            "CURRENT_KNOWN_DETECT_BLIND_SPOT",
        )

if __name__ == "__main__":
    unittest.main()
