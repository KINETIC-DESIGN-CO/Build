-- SOURCE ONLY. Run concurrently with dr35_deadlock_race_session_a.sql after a shared fixture is prepared.
begin;
set local lock_timeout='5s';
select pg_catalog.pg_sleep(0.25);
update life_runtime.work_v05b
set next_action_ref='DR35-OUT-OF-PATH'
where work_id='73500000-0000-4000-8000-000000000001';
commit;
select status,open_flag_count from life_runtime.audit_status_v05b where singleton_id=1;
