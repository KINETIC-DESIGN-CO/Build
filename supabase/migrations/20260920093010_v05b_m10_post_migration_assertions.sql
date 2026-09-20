begin;

do $$
declare
  v_diff text[];
  v_count integer;
begin
  with expected(name) as (
    values
      ('maintenance_state_v05b'),('audit_status_v05b'),('work_v05b'),
      ('operation_receipt_v05b'),('transference_event_v05b'),
      ('maintenance_receipt_v05b'),('owner_ingress_audit_v05b'),
      ('audit_event_v05b'),('audit_flag_v05b'),('audit_clear_receipt_v05b'),
      ('audit_verification_receipt_v05b'),('runtime_catalog_manifest_v05b')
  ),
  actual(name) as (
    select c.relname::text
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid=c.relnamespace
    where n.nspname='life_runtime' and c.relkind='r'
  ),
  diff(name) as (
    (select name from expected except select name from actual)
    union all
    (select name from actual except select name from expected)
  )
  select pg_catalog.array_agg(name order by name) into v_diff from diff;

  if v_diff is not null then
    raise exception using
      errcode='55000',
      message='V05B_TABLE_SET_MISMATCH:'||pg_catalog.array_to_string(v_diff,',');
  end if;

  with expected(name) as (
    values
      ('append_audit_event_v05b'),
      ('apply_owner_decision_v05b'),
      ('apply_transference_v05b'),
      ('audit_genesis_hash_v05b'),
      ('catalog_snapshot_v05b'),
      ('clear_audit_flag_v05b'),
      ('close_work_v05b'),
      ('ddl_command_end_audit_v05b'),
      ('defer_work_v05b'),
      ('enter_maintenance_v05b'),
      ('evaluate_reactivation_v05b'),
      ('exit_maintenance_v05b'),
      ('full_audit_verify_v05b'),
      ('get_work_state_v05b'),
      ('immutable_evidence_guard_v05b'),
      ('json_hash_v05b'),
      ('kick_return_v05b'),
      ('open_blocking_flag_v05b'),
      ('perform_transition_v05b'),
      ('reactivate_work_v05b'),
      ('resolve_escalated_flag_v05b'),
      ('runtime_catalog_guard_v05b'),
      ('sql_drop_audit_v05b'),
      ('work_audit_trigger_v05b')
  ),
  actual(name) as (
    select p.proname::text
    from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid=p.pronamespace
    where n.nspname='life_runtime'
  ),
  diff(name) as (
    (select name from expected except select name from actual)
    union all
    (select name from actual except select name from expected)
  )
  select pg_catalog.array_agg(name order by name) into v_diff from diff;

  if v_diff is not null then
    raise exception using
      errcode='55000',
      message='V05B_FUNCTION_SET_MISMATCH:'||pg_catalog.array_to_string(v_diff,',');
  end if;

  select pg_catalog.count(*)::integer into v_count
  from pg_catalog.pg_proc p
  join pg_catalog.pg_namespace n on n.oid=p.pronamespace
  where n.nspname='life_runtime';
  if v_count<>24 then
    raise exception using
      errcode='55000',
      message='V05B_FUNCTION_CARDINALITY:'||v_count::text;
  end if;

  with expected(name) as (
    values
      ('audit_clear_receipt_v05b_immutable_trg'),
      ('audit_event_v05b_immutable_trg'),
      ('audit_verification_receipt_v05b_immutable_trg'),
      ('maintenance_receipt_v05b_immutable_trg'),
      ('operation_receipt_v05b_immutable_trg'),
      ('owner_ingress_audit_v05b_immutable_trg'),
      ('transference_event_v05b_immutable_trg'),
      ('work_v05b_audit_trg')
  ),
  actual(name) as (
    select t.tgname::text
    from pg_catalog.pg_trigger t
    join pg_catalog.pg_class c on c.oid=t.tgrelid
    join pg_catalog.pg_namespace n on n.oid=c.relnamespace
    where n.nspname='life_runtime' and not t.tgisinternal
  ),
  diff(name) as (
    (select name from expected except select name from actual)
    union all
    (select name from actual except select name from expected)
  )
  select pg_catalog.array_agg(name order by name) into v_diff from diff;

  if v_diff is not null then
    raise exception using
      errcode='55000',
      message='V05B_ROW_TRIGGER_SET_MISMATCH:'||pg_catalog.array_to_string(v_diff,',');
  end if;

  with expected(name) as (
    values
      ('life_runtime_v05b_ddl_command_end'),
      ('life_runtime_v05b_sql_drop')
  ),
  actual(name) as (
    select e.evtname::text
    from pg_catalog.pg_event_trigger e
    where e.evtname like 'life_runtime_v05b_%'
  ),
  diff(name) as (
    (select name from expected except select name from actual)
    union all
    (select name from actual except select name from expected)
  )
  select pg_catalog.array_agg(name order by name) into v_diff from diff;

  if v_diff is not null then
    raise exception using
      errcode='55000',
      message='V05B_EVENT_TRIGGER_SET_MISMATCH:'||pg_catalog.array_to_string(v_diff,',');
  end if;

  select pg_catalog.count(*)::integer into v_count
  from life_runtime.runtime_catalog_manifest_v05b
  where active;
  if v_count<>11 then
    raise exception using
      errcode='55000',
      message='V05B_CATALOG_CARDINALITY:'||v_count::text;
  end if;

  if not life_runtime.runtime_catalog_guard_v05b() then
    raise exception using
      errcode='55000',
      message='V05B_CATALOG_GUARD_FAILED';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_index i
    join pg_catalog.pg_class idx on idx.oid=i.indexrelid
    join pg_catalog.pg_namespace n on n.oid=idx.relnamespace
    where n.nspname='life_runtime'
      and idx.relname='work_v05b_one_active_root_per_goal_uq'
      and i.indisunique
      and i.indisvalid
      and i.indisready
      and pg_catalog.pg_get_indexdef(i.indexrelid) like '%(root_goal_id)%'
      and pg_catalog.pg_get_indexdef(i.indexrelid) not like '%root_goal_revision_at_transfer%'
      and pg_catalog.pg_get_expr(i.indpred,i.indrelid)
        = '((branch_kind = ''ROOT''::text) AND (work_state = ''ACTIVE''::text))'
  ) then
    raise exception using
      errcode='55000',
      message='V05B_ACTIVE_ROOT_INDEX_MISMATCH';
  end if;

  if exists (
    select 1
    from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid=p.pronamespace
    cross join lateral pg_catalog.unnest(
      array['anon','authenticated','service_role','life_runtime_v1']
    ) r(role_name)
    where n.nspname='life_runtime'
      and pg_catalog.to_regrole(r.role_name) is not null
      and pg_catalog.has_function_privilege(r.role_name,p.oid,'EXECUTE')
  ) then
    raise exception using
      errcode='55000',
      message='V05B_ACTIVE_RUNTIME_CALLER_SET_NOT_EMPTY';
  end if;
end
$$;

commit;
