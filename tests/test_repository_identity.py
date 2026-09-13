from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "continuity" / "bootstrap.json"
ADMISSIONS = ROOT / "governance" / "work-admissions.json"
ADMISSIONS_SCHEMA = ROOT / "governance" / "schema" / "work-admissions.schema.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class RepositoryIdentityTests(unittest.TestCase):
    def test_admissions_identity_matches_bootstrap_canonical_repository(self):
        bootstrap = load(BOOTSTRAP)
        admissions = load(ADMISSIONS)
        schema = load(ADMISSIONS_SCHEMA)
        canonical = bootstrap["canonical_repository"]["full_name"]
        default_branch = bootstrap["canonical_repository"]["default_branch"]

        self.assertEqual(admissions["source_repository"], canonical)
        self.assertEqual(schema["properties"]["source_repository"]["const"], canonical)
        self.assertEqual(
            schema["$id"],
            f"https://github.com/{canonical}/blob/{default_branch}/governance/schema/work-admissions.schema.json",
        )


if __name__ == "__main__":
    unittest.main()
