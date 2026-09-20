-- SOURCE ONLY. Active-root uniqueness fixture for DR36-D.
begin;
set local session_replication_role=replica;
insert into life_runtime.work_v05b(
  work_id,root_goal_id,root_goal_revision_at_transfer,branch_depth,branch_kind,
  work_state,source_generation,contract_generation
) values (
  '73600000-0000-4000-8000-000000000001','DR36',1,0,'ROOT','ACTIVE','DR','V05B'
);
do $$
begin
  begin
    insert into life_runtime.work_v05b(
      work_id,root_goal_id,root_goal_revision_at_transfer,branch_depth,branch_kind,
      work_state,source_generation,contract_generation
    ) values (
      '73600000-0000-4000-8000-000000000002','DR36',2,0,'ROOT','ACTIVE','DR','V05B'
    );
    raise exception 'DR36_UNIQUENESS_DID_NOT_FIRE';
  exception
    when unique_violation then null;
  end;
end
$$;
rollback;
