begin;

do $$
declare
  v_missing text[];
  v_count integer;
begin
  select pg_catalog.array_agg(name order by name) into v_missing
  from (
    select name
    from (
      values
        ('maintenance_state_v05b'),('audit_status_v05b'),('work_v05b'),
        ('operation_receipt_v05b'),('transference_event_v05b'),
        ('maintenance_receipt_v05b'),('owner_ingress_audit_v05b'),
        ('audit_event_v05b'),('audit_flag_v05b'),('audit_clear_receipt_v05b'),
        ('audit_verification_receipt_v05b'),('runtime_catalog_manifest_v05b')
    ) x(name)
    where pg_catalog.to_regclass('life_runtime.'||name) is null
  ) q;
  if v_missing is not null then
    raise exception using errcode='55000',message='V05B_MISSING_TABLES:'||pg_catalog.array_to_string(v_missing,',');
  end if;

  select pg_catalog.count(*)::integer into v_count
  from life_runtime.runtime_catalog_manifest_v05b where active;
  if v_count<>11 then
    raise exception using errcode='55000',message='V05B_CATALOG_CARDINALITY:'||v_count::text;
  end if;

  if not life_runtime.runtime_catalog_guard_v05b() then
    raise exception using errcode='55000',message='V05B_CATALOG_GUARD_FAILED';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_index i
    join pg_catalog.pg_class idx on idx.oid=i.indexrelid
    join pg_catalog.pg_namespace n on n.oid=idx.relnamespace
    where n.nspname='life_runtime'
      and idx.relname='work_v05b_one_active_root_per_goal_uq'
      and i.indisunique and i.indisvalid and i.indisready
      and pg_catalog.pg_get_indexdef(i.indexrelid) like '%(root_goal_id)%'
      and pg_catalog.pg_get_indexdef(i.indexrelid) not like '%root_goal_revision_at_transfer%'
      and pg_catalog.pg_get_expr(i.indpred,i.indrelid)
        = '((branch_kind = ''ROOT''::text) AND (work_state = ''ACTIVE''::text))'
  ) then
    raise exception using errcode='55000',message='V05B_ACTIVE_ROOT_INDEX_MISMATCH';
  end if;

  if exists (
    select 1
    from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid=p.pronamespace
    cross join lateral unnest(array['anon','authenticated','service_role','life_runtime_v1']) r(role_name)
    where n.nspname='life_runtime'
      and pg_catalog.to_regrole(r.role_name) is not null
      and pg_catalog.has_function_privilege(r.role_name,p.oid,'EXECUTE')
  ) then
    raise exception using errcode='55000',message='V05B_ACTIVE_RUNTIME_CALLER_SET_NOT_EMPTY';
  end if;
end
$$;

commit;
