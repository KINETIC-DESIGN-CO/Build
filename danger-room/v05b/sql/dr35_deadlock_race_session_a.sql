-- SOURCE ONLY. Run concurrently with dr35_deadlock_race_session_b.sql after a shared fixture is prepared.
begin;
set local lock_timeout='5s';
select pg_catalog.pg_advisory_xact_lock(35001);
select pg_catalog.pg_sleep(1);
select life_runtime.apply_transference_v05b(
  '73500000-0000-4000-8000-000000000011',
  '73500000-0000-4000-8000-000000000001',
  0,
  '{"resulting_work_state":"ACTIVE","reactivation_condition_kind":"NONE","evidence_refs":[],"open_finding_refs":[]}'::jsonb,
  'Caden','danger-room:dr35-a','V05B'
);
commit;
