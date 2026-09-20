#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "supabase" / "v05b" / "package-manifest.json"
WORK_ID = "d46cf24f-397f-4b11-a5db-59b9cf4fd639"
WORK_RECORD = ROOT / "coordination" / "work" / f"{WORK_ID}.json"

def fail(msg: str) -> None:
    raise SystemExit(msg)

def main() -> None:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if m["package_id"] != "TRANSFERENCE_RUNTIME_CONTRACT_V0.5B-D4":
        fail("package id mismatch")
    if m["authority"] != "SOURCE_ONLY_NON_LIVE" or m["runtime_control_authority"] != "NONE":
        fail("authority mismatch")
    if m["active_runtime_caller_set"] != []:
        fail("ACTIVE_RUNTIME_CALLER_SET must remain empty")
    if m["danger_room_execution_state"] != "NOT_RUN":
        fail("Danger Room source package cannot claim execution")
    if m["remote_supabase_mutation_state"] != "NOT_RUN":
        fail("source package cannot claim remote Supabase mutation")
    if m["production_cutover_state"] != "NOT_RUN":
        fail("source package cannot claim cutover")
    files = m["declared_files"]
    if files != sorted(set(files)) or len(files) != 35:
        fail("declared file set must be 35 unique sorted paths")
    missing = [p for p in files if not (ROOT / p).is_file()]
    if missing:
        fail("missing declared files: " + ",".join(missing))
    expected_migrations = [f"202609200930{i:02d}" for i in range(1, 11)]
    if m["migration_ids"] != expected_migrations:
        fail("migration id sequence mismatch")
    migration_files = sorted((ROOT / "supabase" / "migrations").glob("202609200930*_v05b_*.sql"))
    if len(migration_files) != 10:
        fail("expected exactly 10 V0.5B migrations")
    joined = "\n".join(p.read_text(encoding="utf-8") for p in migration_files)
    for token in (
        "work_v05b_one_active_root_per_goal_uq",
        "resolve_escalated_flag_v05b",
        "full_audit_verify_v05b",
        "runtime_catalog_guard_v05b",
        "life_runtime_v05b_ddl_command_end",
        "life_runtime_v05b_sql_drop",
        "V05B_ACTIVE_RUNTIME_CALLER_SET_NOT_EMPTY",
    ):
        if token not in joined:
            fail(f"required migration token missing: {token}")
    m07 = (ROOT / "supabase/migrations/20260920093007_v05b_m07_row_and_evidence_triggers.sql").read_text(encoding="utf-8")
    if re.search(r"alter\s+table\s+life_runtime\.\w+\s+enable\s+always\s+trigger", m07, re.I):
        fail("M07 must not claim DR33 ENABLE ALWAYS proof before Danger Room")
    if "CURRENT_KNOWN_DETECT_BLIND_SPOT" not in MANIFEST.read_text(encoding="utf-8"):
        fail("replica-mode blind spot must remain explicit")
    rollback = (ROOT / "supabase/rollback/v05b_rollback.sql").read_text(encoding="utf-8")
    if "drop schema if exists life_runtime cascade" not in rollback.lower():
        fail("rollback source missing life_runtime removal")
    record = json.loads(WORK_RECORD.read_text(encoding="utf-8"))
    expected_repo_paths = sorted(p for p in files if p != f"coordination/work/{WORK_ID}.json")
    if record["repo_paths"] != expected_repo_paths:
        fail("work record repo_paths mismatch manifest")
    if record["component_id"] != "transference_runtime_v05b":
        fail("work record component mismatch")
    print("V0.5B package validation PASS")

if __name__ == "__main__":
    main()
