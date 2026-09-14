import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "evaluate_selected_operation_execution.py"

spec = importlib.util.spec_from_file_location("selected_operation_execution", SCRIPT)
execution = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(execution)


class SelectedOperationExecutionTests(unittest.TestCase):
    def base(self):
        return {
            "selected_operation_state": "SELECTED",
            "target_state": "EXACT",
            "authorization_state": "AUTHORIZED",
            "machine_route_state": "ACTION_AVAILABLE",
            "attempted_route_classes": ["CURRENT_CONNECTED_ACTION_SURFACE"],
            "available_route_class": "CURRENT_CONNECTED_ACTION_SURFACE",
            "app_permission_state": "AUTHORIZED",
            "safety_state": "PASS",
            "resource_state": "AVAILABLE",
            "cost_state": "NO_NEW_COMMITMENT",
            "effect_reconciliation_state": "CLEAR",
        }

    def test_authorized_available_action_executes_now(self):
        result = execution.evaluate(self.base())
        self.assertEqual(result["disposition"], "EXECUTE_NOW")
        self.assertTrue(result["execute_now"])
        self.assertFalse(result["manual_handoff_allowed"])

    def test_fallback_route_executes_now(self):
        value = self.base()
        value["attempted_route_classes"] = [
            "CURRENT_CONNECTED_ACTION_SURFACE",
            "DYNAMIC_TOOL_DISCOVERY",
            "INSTALLED_PLUGIN_DIRECTORY",
            "AUTHORIZED_PROVIDER_NATIVE_OR_REPOSITORY_AUTOMATION",
        ]
        value["available_route_class"] = "AUTHORIZED_PROVIDER_NATIVE_OR_REPOSITORY_AUTOMATION"
        result = execution.evaluate(value)
        self.assertEqual(result["disposition"], "EXECUTE_NOW")

    def test_not_run_requires_machine_route_discovery_not_human_handoff(self):
        value = self.base()
        value["machine_route_state"] = "NOT_RUN"
        value["attempted_route_classes"] = []
        value["available_route_class"] = None
        result = execution.evaluate(value)
        self.assertEqual(result["disposition"], "DISCOVER_MACHINE_ROUTE")
        self.assertFalse(result["manual_handoff_allowed"])
        self.assertEqual(result["remaining_route_classes"], execution.ROUTE_CLASSES)

    def test_blocked_connected_app_searches_remaining_routes_before_stopping(self):
        value = self.base()
        value["app_permission_state"] = "NOT_AUTHORIZED"
        result = execution.evaluate(value)
        self.assertEqual(result["disposition"], "DISCOVER_MACHINE_ROUTE")
        self.assertFalse(result["manual_handoff_allowed"])

    def test_no_machine_route_requires_all_route_classes_attempted(self):
        value = self.base()
        value["machine_route_state"] = "NO_MACHINE_ROUTE_VERIFIED"
        value["available_route_class"] = None
        with self.assertRaises(execution.ExecutionDispositionError):
            execution.evaluate(value)

    def test_human_action_allowed_only_after_every_machine_route_is_exhausted(self):
        value = self.base()
        value["machine_route_state"] = "NO_MACHINE_ROUTE_VERIFIED"
        value["available_route_class"] = None
        value["attempted_route_classes"] = list(execution.ROUTE_CLASSES)
        result = execution.evaluate(value)
        self.assertEqual(result["disposition"], "USER_ACTION_REQUIRED_NO_MACHINE_ROUTE")
        self.assertTrue(result["manual_handoff_allowed"])
        self.assertFalse(result["execute_now"])

    def test_authorization_safety_resource_cost_and_effect_states_fail_closed(self):
        cases = [
            ("authorization_state", "NOT_AUTHORIZED", "BLOCKED_AUTHORIZATION"),
            ("safety_state", "BLOCKED", "BLOCKED_SAFETY"),
            ("resource_state", "BLOCKED", "BLOCKED_RESOURCE"),
            ("cost_state", "UNAUTHORIZED_COMMITMENT", "BLOCKED_COST"),
            ("effect_reconciliation_state", "REQUIRED", "EFFECT_RECONCILIATION_REQUIRED"),
        ]
        for field, state, expected in cases:
            with self.subTest(field=field):
                value = self.base()
                value[field] = state
                result = execution.evaluate(value)
                self.assertEqual(result["disposition"], expected)
                self.assertFalse(result["execute_now"])
                self.assertFalse(result["manual_handoff_allowed"])

    def test_unresolved_target_fails_closed(self):
        value = self.base()
        value["target_state"] = "UNRESOLVED"
        result = execution.evaluate(value)
        self.assertEqual(result["disposition"], "TARGET_OR_OPERATION_UNRESOLVED")

    def test_contract_has_no_redundant_confirmation_state(self):
        execution.validate_contract()
        joined = " ".join(execution.DISPOSITIONS)
        self.assertNotIn("CONFIRM", joined)
        self.assertNotIn("APPROVAL_REQUEST", joined)

    def test_no_selected_operation_does_not_execute(self):
        value = self.base()
        value["selected_operation_state"] = "NONE"
        result = execution.evaluate(value)
        self.assertEqual(result["disposition"], "NO_SELECTED_OPERATION")
        self.assertFalse(result["execute_now"])


if __name__ == "__main__":
    unittest.main()
