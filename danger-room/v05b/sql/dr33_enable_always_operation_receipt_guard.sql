-- SOURCE ONLY. Execute only under separately authorized Danger Room DDL.
begin;
select life_runtime.enter_maintenance_v05b('DR33-RECEIPT','danger-room:dr33-receipt','Caden');
set local session_replication_role=replica;
insert into life_runtime.work_v05b(
  work_id,root_goal_id,root_goal_revision_at_transfer,branch_depth,branch_kind,
  work_state,source_generation,contract_generation
) values (
  '73330000-0000-4000-8000-000000000002','DR33-RECEIPT',1,0,'ROOT','ACTIVE','DR','V05B'
);
insert into life_runtime.operation_receipt_v05b(
  request_id,operation_kind,work_id,expected_revision,canonical_request,
  canonical_request_hash,claimed_actor,source_ref,contract_generation,
  exact_result_code,exact_result_payload,expected_audit_event_count
) values (
  '73330000-0000-4000-8000-000000000012','DEFER_WORK',
  '73330000-0000-4000-8000-000000000002',0,'{}'::jsonb,
  repeat('a',64),'Caden','danger-room:dr33-receipt','V05B',
  'VALIDATION_REJECTED','{"code":"VALIDATION_REJECTED"}'::jsonb,0
);
set local session_replication_role=origin;
alter table life_runtime.operation_receipt_v05b
  enable always trigger operation_receipt_v05b_immutable_trg;
set local session_replication_role=replica;
do $$
begin
  begin
    update life_runtime.operation_receipt_v05b
    set exact_result_payload='{"corrupt":true}'::jsonb
    where request_id='73330000-0000-4000-8000-000000000012';
    raise exception 'DR33_GUARD_DID_NOT_FIRE';
  exception
    when sqlstate '55000' then null;
  end;
end
$$;
rollback;
select pg_catalog.current_setting('session_replication_role') as post_role;
