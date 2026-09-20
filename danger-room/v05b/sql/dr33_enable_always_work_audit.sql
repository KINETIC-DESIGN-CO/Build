-- SOURCE ONLY. Execute only under separately authorized Danger Room DDL.
begin;
select life_runtime.enter_maintenance_v05b('DR33-WORK','danger-room:dr33-work','Caden');
set local session_replication_role=replica;
insert into life_runtime.work_v05b(
  work_id,root_goal_id,root_goal_revision_at_transfer,branch_depth,branch_kind,
  work_state,source_generation,contract_generation
) values (
  '73330000-0000-4000-8000-000000000001','DR33-WORK',1,0,'ROOT','ACTIVE','DR','V05B'
);
set local session_replication_role=origin;
alter table life_runtime.work_v05b enable always trigger work_v05b_audit_trg;
set local session_replication_role=replica;
update life_runtime.work_v05b
set next_action_ref='DR33-REPLICA-WRITE'
where work_id='73330000-0000-4000-8000-000000000001';
select audit_event_id,path_class,object_identity
from life_runtime.audit_event_v05b
where primary_key->>'work_id'='73330000-0000-4000-8000-000000000001'
order by audit_event_id;
select status,open_flag_count from life_runtime.audit_status_v05b where singleton_id=1;
rollback;
select pg_catalog.current_setting('session_replication_role') as post_role;
