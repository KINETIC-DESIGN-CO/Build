begin;
create extension if not exists pgtap with schema extensions;
set local search_path=extensions,pg_catalog,public;
select plan(4);
set local session_replication_role=replica;
insert into life_runtime.work_v05b(work_id,root_goal_id,root_goal_revision_at_transfer,branch_depth,branch_kind,work_state,source_generation,contract_generation)
values('10000000-0000-4000-8000-000000000001','G-1',1,0,'ROOT','ACTIVE','S','V05B');
select throws_ok(
  $$insert into life_runtime.work_v05b(work_id,root_goal_id,root_goal_revision_at_transfer,branch_depth,branch_kind,work_state,source_generation,contract_generation)
    values('10000000-0000-4000-8000-000000000002','G-1',2,0,'ROOT','ACTIVE','S','V05B')$$,
  '23505',null,'second ACTIVE ROOT for same root_goal_id is rejected'
);
select throws_ok(
  $$insert into life_runtime.work_v05b(work_id,root_goal_id,root_goal_revision_at_transfer,branch_depth,branch_kind,work_state,source_generation,contract_generation,parent_work_id)
    values('10000000-0000-4000-8000-000000000003','G-2',1,0,'ROOT','ACTIVE','S','V05B','10000000-0000-4000-8000-000000000001')$$,
  '23514',null,'ROOT ancestry shape is enforced'
);
select throws_ok(
  $$insert into life_runtime.work_v05b(work_id,root_goal_id,root_goal_revision_at_transfer,branch_depth,branch_kind,work_state,source_generation,contract_generation)
    values('10000000-0000-4000-8000-000000000004','G-3',1,0,'ROOT','DEFERRED','S','V05B')$$,
  '23514',null,'DEFERRED requires an exact reactivation condition'
);
select is((select work_state from life_runtime.work_v05b where work_id='10000000-0000-4000-8000-000000000001'),'ACTIVE','valid ROOT fixture remains ACTIVE');
select * from finish();
rollback;
