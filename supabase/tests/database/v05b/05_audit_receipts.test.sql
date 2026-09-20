begin;
create extension if not exists pgtap with schema extensions;
set local search_path=extensions,pg_catalog,public;
select plan(4);
set local session_replication_role=replica;
insert into life_runtime.work_v05b(work_id,root_goal_id,root_goal_revision_at_transfer,branch_depth,branch_kind,work_state,source_generation,contract_generation)
values('40000000-0000-4000-8000-000000000001','G-A',1,0,'ROOT','ACTIVE','S','V05B');
set local session_replication_role=origin;
select is(
 life_runtime.apply_transference_v05b(
  '40000000-0000-4000-8000-000000000011','40000000-0000-4000-8000-000000000001',0,
  '{"resulting_work_state":"ACTIVE","reactivation_condition_kind":"NONE","evidence_refs":[],"open_finding_refs":[]}'::jsonb,
  'Caden','test:audit','V05B'
 )->>'code','APPLIED','approved mutation applies'
);
select is((select expected_audit_event_count from life_runtime.operation_receipt_v05b where request_id='40000000-0000-4000-8000-000000000011'),1,'receipt expects one audit event');
select is((select pg_catalog.count(*)::integer from life_runtime.audit_event_v05b where request_id='40000000-0000-4000-8000-000000000011'),1,'exactly one paired audit event exists');
select isnt((select audit_head_hash from life_runtime.audit_status_v05b where singleton_id=1),life_runtime.audit_genesis_hash_v05b(),'audit head advances from genesis');
select * from finish();
rollback;
