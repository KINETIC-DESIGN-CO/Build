begin;
create extension if not exists pgtap with schema extensions;
set local search_path=extensions,pg_catalog,public;
select plan(3);
set local session_replication_role=replica;
insert into life_runtime.work_v05b(work_id,root_goal_id,root_goal_revision_at_transfer,branch_depth,branch_kind,work_state,source_generation,contract_generation)
values('30000000-0000-4000-8000-000000000001','G-M',1,0,'ROOT','ACTIVE','S','V05B');
set local session_replication_role=origin;
select is(life_runtime.enter_maintenance_v05b('CHG-1','test:maintenance','Caden')->>'code','APPLIED','maintenance enters');
select is(
 life_runtime.apply_transference_v05b(
   '30000000-0000-4000-8000-000000000011','30000000-0000-4000-8000-000000000001',0,
   '{"resulting_work_state":"ACTIVE","reactivation_condition_kind":"NONE","evidence_refs":[],"open_finding_refs":[]}'::jsonb,
   'Caden','test:maintenance','V05B'
 )->>'code','MAINTENANCE_BLOCKED','runtime mutation blocks during maintenance'
);
select is((select revision from life_runtime.work_v05b where work_id='30000000-0000-4000-8000-000000000001'),0::bigint,'blocked mutation leaves revision unchanged');
select * from finish();
rollback;
