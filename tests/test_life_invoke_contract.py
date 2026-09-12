from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "life.invoke.contract.json"
INPUT_SCHEMA = ROOT / "contracts" / "life.invoke.input.schema.json"
OUTPUT_SCHEMA = ROOT / "contracts" / "life.invoke.output.schema.json"
ARCHITECTURE = ROOT / "architecture" / "canonical-invocation-v1.md"

UUID4_PATTERN = "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_canonical_json(test: unittest.TestCase, path: Path) -> None:
    obj = load_json(path)
    expected = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    test.assertEqual(path.read_text(encoding="utf-8"), expected)


def reference_request_facts(request_text: str) -> tuple[int, str]:
    if not isinstance(request_text, str):
        raise ValueError("INVALID_INPUT")
    if len(request_text) < 1 or len(request_text) > 65536:
        raise ValueError("INVALID_INPUT")
    if "\x00" in request_text:
        raise ValueError("REQUEST_TEXT_U0000_FORBIDDEN")
    try:
        raw = request_text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError("REQUEST_TEXT_INVALID_UNICODE") from exc
    if not 1 <= len(raw) <= 262144:
        raise ValueError("REQUEST_TEXT_UTF8_BYTES_OUT_OF_RANGE")
    return len(raw), hashlib.sha256(raw).hexdigest()


class LifeInvokeContractTests(unittest.TestCase):
    def test_contract_files_are_canonical_json(self):
        for path in (CONTRACT, INPUT_SCHEMA, OUTPUT_SCHEMA):
            assert_canonical_json(self, path)

    def test_input_schema_is_closed_and_exact(self):
        schema = load_json(INPUT_SCHEMA)
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["type"], "object")
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(
            schema["required"],
            ["schema_version", "invocation_key", "request_text"],
        )
        self.assertEqual(schema["properties"]["schema_version"], {"const": 1})
        self.assertEqual(schema["properties"]["invocation_key"]["pattern"], UUID4_PATTERN)
        self.assertEqual(
            schema["properties"]["request_text"],
            {"type": "string", "minLength": 1, "maxLength": 65536},
        )

    def test_output_schema_is_closed_and_recorded_only(self):
        schema = load_json(OUTPUT_SCHEMA)
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(schema["properties"]["input_provenance"], {"const": "MCP_TOOL_ARGUMENT"})
        self.assertEqual(schema["properties"]["state"], {"const": "RECORDED"})
        self.assertEqual(schema["properties"]["request_sha256"]["pattern"], "^[0-9a-f]{64}$")
        self.assertEqual(
            schema["properties"]["request_utf8_bytes"],
            {"type": "integer", "minimum": 1, "maximum": 262144},
        )

    def test_selected_host_identity_and_store_are_exact(self):
        contract = load_json(CONTRACT)
        self.assertEqual(contract["tool_name"], "life.invoke")
        self.assertEqual(contract["runtime_control_authority"], "NONE")
        self.assertEqual(contract["transport"]["selected_host"], "VERCEL_FUNCTIONS")
        self.assertEqual(contract["transport"]["deployment_target_status"], "NOT_AUTHORIZED")
        self.assertIsNone(contract["transport"]["deployment_target"])
        self.assertEqual(contract["identity"]["authorization_server"], "SUPABASE_AUTH")
        self.assertEqual(
            contract["identity"]["issuer"],
            "https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1",
        )
        self.assertEqual(contract["record"]["store"], "SUPABASE_POSTGRES")
        self.assertEqual(contract["record"]["schema"], "life")
        self.assertEqual(contract["record"]["table"], "invocations")

    def test_exact_tool_argument_provenance_and_no_normalization(self):
        contract = load_json(CONTRACT)
        item = contract["input"]
        self.assertEqual(item["input_provenance"], "MCP_TOOL_ARGUMENT")
        self.assertEqual(item["claim_of_raw_chat_message_equivalence"], "FORBIDDEN")
        self.assertEqual(item["unicode_normalization"], "NONE")
        self.assertEqual(item["trim"], "NONE")
        self.assertEqual(item["case_folding"], "NONE")
        self.assertEqual(item["newline_normalization"], "NONE")
        self.assertEqual(item["utf8_encoding"], "STRICT")
        self.assertIs(item["reject_u0000"], True)
        self.assertEqual(item["utf8_min_bytes"], 1)
        self.assertEqual(item["utf8_max_bytes"], 262144)

    def test_reference_request_facts_preserve_exact_utf8(self):
        text = "  A\r\né  "
        byte_count, digest = reference_request_facts(text)
        raw = text.encode("utf-8")
        self.assertEqual(byte_count, len(raw))
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

    def test_reference_request_facts_reject_u0000(self):
        with self.assertRaisesRegex(ValueError, "REQUEST_TEXT_U0000_FORBIDDEN"):
            reference_request_facts("a\x00b")

    def test_reference_request_facts_accept_exact_byte_ceiling(self):
        within = "😀" * 65536
        self.assertEqual(reference_request_facts(within)[0], 262144)

    def test_reference_request_facts_reject_invalid_unicode(self):
        with self.assertRaisesRegex(ValueError, "REQUEST_TEXT_INVALID_UNICODE"):
            reference_request_facts("\ud800")

    def test_idempotency_and_annotations_are_exact(self):
        contract = load_json(CONTRACT)
        self.assertEqual(
            contract["idempotency"]["key_fields"],
            ["auth_subject", "oauth_client_id", "invocation_key"],
        )
        self.assertEqual(
            contract["idempotency"]["same_key_same_request_sha256"],
            "RETURN_EXISTING_RECORD",
        )
        self.assertEqual(
            contract["idempotency"]["same_key_different_request_sha256"],
            "INVOCATION_KEY_REUSE_MISMATCH",
        )
        self.assertEqual(
            contract["tool_annotations"],
            {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
                "authority": "HINTS_ONLY",
            },
        )

    def test_ledger_excludes_vectors_tokens_and_control_state(self):
        contract = load_json(CONTRACT)
        record = contract["record"]
        self.assertIs(record["append_only"], True)
        self.assertIs(record["embeddings_in_record"], False)
        self.assertIs(record["bearer_token_in_record"], False)
        self.assertIs(record["derived_control_state_in_record"], False)
        db = contract["database_access"]
        self.assertEqual(db["direct_table_dml_for_runtime_role"], "FORBIDDEN")
        self.assertEqual(db["allowed_operation"], "EXECUTE_LIFE_RECORD_INVOCATION_V1_ONLY")
        self.assertEqual(db["security_definer_search_path"], "")

    def test_deployment_gates_include_client_and_live_tool_verification(self):
        gates = set(load_json(CONTRACT)["deployment_gates"])
        self.assertIn("EXACT_VERCEL_TARGET_AUTHORIZED", gates)
        self.assertIn("SUPABASE_ASYMMETRIC_JWT_SIGNING_VERIFIED", gates)
        self.assertIn("CALLER_ALLOWLIST_MACHINE_RECORD_ACTIVE", gates)
        self.assertIn("CHATGPT_WRITE_MCP_CAPABILITY_VERIFIED", gates)
        self.assertIn("LIVE_MCP_ENDPOINT_AND_EXACT_TOOL_LIFE_INVOKE_VERIFIED", gates)

    def test_legacy_dispositions_are_complete_and_unique(self):
        rows = load_json(CONTRACT)["legacy_dispositions"]
        concepts = [row["concept"] for row in rows]
        self.assertEqual(len(concepts), len(set(concepts)))
        expected = {
            "stable_life_invoke_tool": "KEEP",
            "authenticated_invocation": "KEEP",
            "canonical_invocation_ledger": "KEEP",
            "exact_invocation_boundary_separate_from_embeddings": "KEEP",
            "vectors_have_zero_control_authority": "KEEP",
            "database_migrations_tests_and_ci": "KEEP",
            "supabase_auth_oauth_jwt": "COMBINE",
            "supabase_edge_function_as_mcp_front_door": "REPLACE",
            "gte_small_384_embedding_in_canonical_invocation": "REMOVE",
            "legacy_manual_bearer_parser": "REMOVE",
            "request_text_is_machine_verified_raw_chat_message": "MODIFY",
            "postgres_text_accepts_u0000": "REMOVE",
            "project_instruction_routes_directly_to_database_tables": "REPLACE",
        }
        self.assertEqual({row["concept"]: row["disposition"] for row in rows}, expected)

    def test_architecture_declares_zero_runtime_authority_and_not_run_deployment(self):
        text = ARCHITECTURE.read_text(encoding="utf-8")
        self.assertIn("zero Life runtime control authority", text)
        self.assertIn("Deployment to Vercel is therefore `NOT_RUN`.", text)
        self.assertIn("`MCP_TOOL_ARGUMENT`", text)
        self.assertTrue(text.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
