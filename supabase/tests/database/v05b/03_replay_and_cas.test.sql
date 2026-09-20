begin;
create extension if not exists pgtap with schema extensions;
set local search_path=extensions,pg_catalog,public;
select plan(4);
set local session_replication_role=replica;
insert into life_runtime.work_v05b(work_id,root_goal_id,root_goal_revision_at_transfer,branch_depth,branch_kind,work_state,source_generation,contract_generation)
values('20000000-0000-4000-8000-000000000001','G-R',1,0,'ROOT','ACTIVE','S','V05B');
set local session_replication_role=origin;
select is(
  life_runtime.apply_transference_v05b(
    '20000000-0000-4000-8000-000000000011','20000000-0000-4000-8000-000000000001',0,
    '{"resulting_work_state":"ACTIVE","next_actor":"Caden","next_action_ref":"A","reactivation_condition_kind":"NONE","evidence_refs":[],"open_finding_refs":[]}'::jsonb,
    'Caden','test:replay','V05B'
  )->>'code','APPLIED','first transition applies'
);
select is((select revision from life_runtime.work_v05b where work_id='20000000-0000-4000-8000-000000000001'),1::bigint,'revision advances exactly once');
select is(
  life_runtime.apply_transference_v05b(
    '20000000-0000-4000-8000-000000000011','20000000-0000-4000-8000-000000000001',0,
    '{"resulting_work_state":"ACTIVE","next_actor":"Caden","next_action_ref":"A","reactivation_condition_kind":"NONE","evidence_refs":[],"open_finding_refs":[]}'::jsonb,
    'Caden','test:replay','V05B'
  )->>'replayed','true','same request replays stored result'
);
select is(
  life_runtime.apply_transference_v05b(
    '20000000-0000-4000-8000-000000000011','20000000-0000-4000-8000-000000000001',0,
    '{"resulting_work_state":"ACTIVE","next_actor":"Claude","next_action_ref":"DIFFERENT","reactivation_condition_kind":"NONE","evidence_refs":[],"open_finding_refs":[]}'::jsonb,
    'Caden','test:replay','V05B'
  )->>'code','REJECT_MUTATED_RETRY','mutated retry is rejected'
);
select * from finish();
rollback;
