-- SOURCE ONLY. Controlled audit-corruption fixture for DR25-D.
begin;
select life_runtime.enter_maintenance_v05b('DR25','danger-room:dr25','Caden');
select life_runtime.append_audit_event_v05b(
  'ROW_MUTATION','DR25','danger-room.fixture',null,null,null,'Caden',null,
  'DR25_FIXTURE','danger-room:dr25','V05B','APPROVED_RUNTIME_PATH','DR25',
  null,null,null,'{"fixture":true}'::jsonb
) as fixture_event_id;
set local session_replication_role=replica;
update life_runtime.audit_event_v05b
set audit_event_hash=repeat('0',64)
where audit_event_id=(select max(audit_event_id) from life_runtime.audit_event_v05b);
set local session_replication_role=origin;
select life_runtime.full_audit_verify_v05b() as verification_result;
rollback;
