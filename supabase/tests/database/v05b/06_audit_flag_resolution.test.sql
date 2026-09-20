begin;
create extension if not exists pgtap with schema extensions;
set local search_path=extensions,pg_catalog,public;
select plan(4);
set local session_replication_role=replica;
insert into life_runtime.work_v05b(work_id,root_goal_id,root_goal_revision_at_transfer,branch_depth,branch_kind,work_state,source_generation,contract_generation)
values('50000000-0000-4000-8000-000000000001','G-F',1,0,'ROOT','ACTIVE','S','V05B');
set local session_replication_role=origin;
update life_runtime.work_v05b set next_action_ref='OUT' where work_id='50000000-0000-4000-8000-000000000001';
select is((select status from life_runtime.audit_status_v05b where singleton_id=1),'FLAGGED','out-of-path write flags audit');
select is((select state from life_runtime.audit_flag_v05b order by opened_at desc limit 1),'OPEN','blocking flag opens');
select is(life_runtime.enter_maintenance_v05b('CHG-F','test:flag','Caden')->>'code','APPLIED','maintenance enters for clear');
select is(
 life_runtime.clear_audit_flag_v05b(
  (select flag_id from life_runtime.audit_flag_v05b order by opened_at desc limit 1),
  'ACCIDENTAL','CHG-F',array['test'],'Connor','slack:test-pass','Caden'
 )->>'new_flag_state','CLEARED','eligible claimed review clears OPEN flag'
);
select * from finish();
rollback;
