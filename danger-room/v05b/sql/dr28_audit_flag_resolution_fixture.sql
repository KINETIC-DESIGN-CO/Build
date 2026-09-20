-- SOURCE ONLY. Audit-hold clearing fixture for DR28-D.
begin;
set local session_replication_role=replica;
insert into life_runtime.work_v05b(
  work_id,root_goal_id,root_goal_revision_at_transfer,branch_depth,branch_kind,
  work_state,source_generation,contract_generation
) values (
  '72800000-0000-4000-8000-000000000001','DR28',1,0,'ROOT','ACTIVE','DR','V05B'
);
set local session_replication_role=origin;
update life_runtime.work_v05b
set next_action_ref='DR28-OUT-OF-PATH'
where work_id='72800000-0000-4000-8000-000000000001';
select life_runtime.enter_maintenance_v05b('DR28','danger-room:dr28','Caden');
select life_runtime.clear_audit_flag_v05b(
  (select flag_id from life_runtime.audit_flag_v05b where state='OPEN' order by opened_at desc limit 1),
  'UNEXPLAINED','DR28',array['danger-room:dr28'],'Connor','slack:dr28-review','Caden'
) as escalated_result;
select flag_id,state from life_runtime.audit_flag_v05b order by opened_at desc limit 1;
rollback;
