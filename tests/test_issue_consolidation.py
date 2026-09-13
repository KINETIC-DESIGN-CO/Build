import copy
import json
import unittest
from pathlib import Path

from scripts.validate_issue_consolidation import derive_relationship, index_registry, validate

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "issue-consolidation-policy.json"
REGISTRY_PATH = ROOT / "governance" / "issue-consolidation-registry.json"


def load_fixture():
    with POLICY_PATH.open("r", encoding="utf-8") as handle:
        policy = json.load(handle)
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        registry = json.load(handle)
    return policy, registry


class IssueConsolidationTests(unittest.TestCase):
    def test_repository_fixture_is_valid(self):
        policy, registry = load_fixture()
        validate(policy, registry)

    def test_same_canonical_requirement_is_duplicate(self):
        policy, registry = load_fixture()
        duplicate = copy.deepcopy(registry["source_requirements"][0])
        duplicate["source_requirement_ref"] = "ISSUE-999:DEFAULT"
        duplicate["source_issue_number"] = 999
        registry["source_requirements"].append(duplicate)

        canonical_id = duplicate["canonical_requirement_id"]
        for item in registry["canonical_requirements"]:
            if item["canonical_requirement_id"] == canonical_id:
                item["source_requirement_refs"].append("ISSUE-999:DEFAULT")
                break
        registry["candidate_pairs"].append(
            {
                "left_source_requirement_ref": "ISSUE-49:DEFAULT",
                "right_source_requirement_ref": "ISSUE-999:DEFAULT",
                "classification_state": "CLASSIFIED",
                "expected_relationship": "DUPLICATE",
            }
        )
        validate(policy, registry)

    def test_duplicate_unique_acceptance_condition_cannot_be_dropped(self):
        policy, registry = load_fixture()
        duplicate = copy.deepcopy(registry["source_requirements"][0])
        duplicate["source_requirement_ref"] = "ISSUE-999:DEFAULT"
        duplicate["source_issue_number"] = 999
        duplicate["acceptance_condition_ids"] = ["UNIQUE_DUPLICATE_ACCEPTANCE_CONDITION"]
        registry["source_requirements"].append(duplicate)
        canonical_id = duplicate["canonical_requirement_id"]
        for item in registry["canonical_requirements"]:
            if item["canonical_requirement_id"] == canonical_id:
                item["source_requirement_refs"].append("ISSUE-999:DEFAULT")
                break
        with self.assertRaisesRegex(ValueError, "acceptance conditions"):
            validate(policy, registry)

    def test_semantic_candidate_cannot_default_to_independent(self):
        policy, registry = load_fixture()
        registry["candidate_pairs"].append(
            {
                "left_source_requirement_ref": "ISSUE-18:DEFAULT",
                "right_source_requirement_ref": "ISSUE-15:DEFAULT",
                "classification_state": "CLASSIFIED",
                "expected_relationship": "INDEPENDENT",
            }
        )
        with self.assertRaisesRegex(ValueError, "deterministic"):
            validate(policy, registry)

    def test_combine_required_uses_one_work_identity(self):
        policy, registry = load_fixture()
        validate(policy, registry)
        canonical, sources, deps, independent = index_registry(registry)
        relationship = derive_relationship(
            "ISSUE-49:DEFAULT",
            "ISSUE-61:DEFAULT",
            canonical,
            sources,
            deps,
            independent,
        )
        self.assertEqual(relationship, "COMBINE_REQUIRED")
        self.assertEqual(
            canonical[sources["ISSUE-49:DEFAULT"]["canonical_requirement_id"]]["canonical_work_identity_id"],
            canonical[sources["ISSUE-61:DEFAULT"]["canonical_requirement_id"]]["canonical_work_identity_id"],
        )

    def test_dependency_is_distinct_from_combination(self):
        policy, registry = load_fixture()
        validate(policy, registry)
        canonical, sources, deps, independent = index_registry(registry)
        relationship = derive_relationship(
            "ISSUE-18:DEFAULT",
            "ISSUE-21:DEFAULT",
            canonical,
            sources,
            deps,
            independent,
        )
        self.assertEqual(relationship, "DEPENDENCY")
        self.assertNotEqual(
            canonical[sources["ISSUE-18:DEFAULT"]["canonical_requirement_id"]]["canonical_work_identity_id"],
            canonical[sources["ISSUE-21:DEFAULT"]["canonical_requirement_id"]]["canonical_work_identity_id"],
        )

    def test_one_issue_can_split_into_requirement_level_relationships(self):
        policy, registry = load_fixture()
        validate(policy, registry)
        canonical, sources, deps, independent = index_registry(registry)
        source_intake_vs_schema = derive_relationship(
            "ISSUE-57:PHASE_A_SOURCE_INTAKE",
            "ISSUE-15:DEFAULT",
            canonical,
            sources,
            deps,
            independent,
        )
        activation_vs_schema = derive_relationship(
            "ISSUE-57:PHASE_B_ACTIVATION",
            "ISSUE-15:DEFAULT",
            canonical,
            sources,
            deps,
            independent,
        )
        self.assertEqual(source_intake_vs_schema, "INDEPENDENT")
        self.assertEqual(activation_vs_schema, "DEPENDENCY")

    def test_dependency_cycle_is_rejected(self):
        policy, registry = load_fixture()
        registry["dependencies"].append(
            {
                "requirement_id": "CR-VINCE-OBSERVATION-PROVENANCE",
                "depends_on_requirement_id": "CR-RESUME-RECONCILIATION",
                "dependency_id": "DEP-9999",
            }
        )
        with self.assertRaisesRegex(ValueError, "cycle"):
            validate(policy, registry)

    def test_excluded_issue_cannot_supply_active_requirement(self):
        policy, registry = load_fixture()
        registry["excluded_issues"].append(
            {
                "source_issue_number": 49,
                "eligibility_state": "EXCLUDED_INVALID_INTAKE",
                "reason_id": "TEST_INVALID_INTAKE",
            }
        )
        with self.assertRaisesRegex(ValueError, "excluded Issue"):
            validate(policy, registry)


if __name__ == "__main__":
    unittest.main()
