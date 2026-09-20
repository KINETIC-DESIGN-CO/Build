begin;
create extension if not exists pgtap with schema extensions;
set local search_path=extensions,pg_catalog,public;
select plan(3);
set local session_replication_role=replica;
insert into life_runtime.work_v05b(work_id,root_goal_id,root_goal_revision_at_transfer,parent_work_id,return_work_id,branch_depth,branch_kind,work_state,source_generation,contract_generation)
values
('60000000-0000-4000-8000-000000000001','G-K',1,null,null,0,'ROOT','ACTIVE','S','V05B'),
('60000000-0000-4000-8000-000000000002','G-K',1,'60000000-0000-4000-8000-000000000001','60000000-0000-4000-8000-000000000001',1,'SPLINTER','COMPLETED','S','V05B');
set local session_replication_role=origin;
select is(
 life_runtime.kick_return_v05b(
  '60000000-0000-4000-8000-000000000011','60000000-0000-4000-8000-000000000002',0,
  'Caden','test:kick','V05B'
 )->>'code','APPLIED','KICK resumes stored ACTIVE return candidate'
);
select is((select revision from life_runtime.work_v05b where work_id='60000000-0000-4000-8000-000000000001'),1::bigint,'resumed candidate revision advances once');
select is((select pg_catalog.count(*)::integer from life_runtime.operation_receipt_v05b where request_id='60000000-0000-4000-8000-000000000011'),1,'KICK has one receipt');
select * from finish();
rollback;
