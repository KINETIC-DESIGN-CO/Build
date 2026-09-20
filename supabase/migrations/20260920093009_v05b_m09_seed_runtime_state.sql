begin;

insert into life_runtime.maintenance_state_v05b(
  singleton_id,state,maintenance_epoch
) values (1,'OFF',0);

insert into life_runtime.audit_status_v05b(
  singleton_id,status,audit_head_event_id,audit_head_hash,open_flag_count,
  last_full_verified_event_id,last_full_verified_hash,last_full_verification_at,status_epoch
)
select 1,'PASS',null,g,0,null,g,null,0
from (select life_runtime.audit_genesis_hash_v05b() as g) s;

with objects(object_kind,object_identity) as (
  values
    ('ROW_TRIGGER','life_runtime.work_v05b.work_v05b_audit_trg'),
    ('ROW_TRIGGER','life_runtime.transference_event_v05b.transference_event_v05b_immutable_trg'),
    ('ROW_TRIGGER','life_runtime.operation_receipt_v05b.operation_receipt_v05b_immutable_trg'),
    ('ROW_TRIGGER','life_runtime.audit_event_v05b.audit_event_v05b_immutable_trg'),
    ('ROW_TRIGGER','life_runtime.audit_clear_receipt_v05b.audit_clear_receipt_v05b_immutable_trg'),
    ('ROW_TRIGGER','life_runtime.audit_verification_receipt_v05b.audit_verification_receipt_v05b_immutable_trg'),
    ('ROW_TRIGGER','life_runtime.maintenance_receipt_v05b.maintenance_receipt_v05b_immutable_trg'),
    ('ROW_TRIGGER','life_runtime.owner_ingress_audit_v05b.owner_ingress_audit_v05b_immutable_trg'),
    ('EVENT_TRIGGER','life_runtime_v05b_ddl_command_end'),
    ('EVENT_TRIGGER','life_runtime_v05b_sql_drop'),
    ('INDEX','life_runtime.work_v05b_one_active_root_per_goal_uq')
)
insert into life_runtime.runtime_catalog_manifest_v05b(
  object_kind,object_identity,expected_definition_hash,expected_enabled_state,
  contract_generation,active
)
select
  o.object_kind,o.object_identity,s.definition_hash,s.enabled_state,'V05B',true
from objects o
cross join lateral life_runtime.catalog_snapshot_v05b(o.object_kind,o.object_identity) s
where s.object_valid;

commit;
