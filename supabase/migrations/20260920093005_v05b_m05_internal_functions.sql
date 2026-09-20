begin;

create function life_runtime.audit_genesis_hash_v05b()
returns text
language sql
immutable
strict
set search_path = ''
as $$
  select pg_catalog.encode(
    pg_catalog.sha256(pg_catalog.convert_to('LIFE_TRANSFERENCE_AUDIT_GENESIS_V05B','UTF8')),
    'hex'
  )
$$;

create function life_runtime.json_hash_v05b(p_value jsonb)
returns text
language sql
immutable
strict
set search_path = ''
as $$
  select pg_catalog.encode(
    pg_catalog.sha256(pg_catalog.convert_to(p_value::text,'UTF8')),
    'hex'
  )
$$;

create function life_runtime.append_audit_event_v05b(
  p_event_kind text,
  p_operation_kind text,
  p_object_identity text,
  p_primary_key jsonb,
  p_old_state_hash text,
  p_new_state_hash text,
  p_claimed_actor text,
  p_request_id uuid,
  p_runtime_context text,
  p_source_ref text,
  p_contract_generation text,
  p_path_class text,
  p_maintenance_change_id text,
  p_command_tag text,
  p_ddl_object_type text,
  p_ddl_object_identity text,
  p_event_payload jsonb
)
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_prev text;
  v_id bigint;
  v_hash text;
  v_tx text := pg_catalog.txid_current()::text;
  v_when timestamptz := pg_catalog.clock_timestamp();
  v_payload jsonb;
begin
  select audit_head_hash
    into v_prev
  from life_runtime.audit_status_v05b
  where singleton_id = 1
  for update;

  if not found then
    return null;
  end if;

  v_payload := pg_catalog.jsonb_build_object(
    'event_kind', p_event_kind,
    'transaction_id', v_tx,
    'operation_kind', p_operation_kind,
    'object_identity', p_object_identity,
    'primary_key', p_primary_key,
    'old_state_hash', p_old_state_hash,
    'new_state_hash', p_new_state_hash,
    'database_principal', current_user,
    'claimed_life_actor', p_claimed_actor,
    'request_id', p_request_id,
    'runtime_function_context', p_runtime_context,
    'source_ref', p_source_ref,
    'contract_generation', p_contract_generation,
    'path_class', p_path_class,
    'maintenance_change_id', p_maintenance_change_id,
    'command_tag', p_command_tag,
    'ddl_object_type', p_ddl_object_type,
    'ddl_object_identity', p_ddl_object_identity,
    'event_payload', p_event_payload,
    'occurred_at', v_when,
    'previous_audit_hash', v_prev
  );

  v_hash := life_runtime.json_hash_v05b(v_payload);

  insert into life_runtime.audit_event_v05b (
    event_kind, transaction_id, operation_kind, object_identity, primary_key,
    old_state_hash, new_state_hash, database_principal, claimed_life_actor,
    request_id, runtime_function_context, source_ref, contract_generation,
    path_class, maintenance_change_id, command_tag, ddl_object_type,
    ddl_object_identity, event_payload, occurred_at, previous_audit_hash,
    audit_event_hash
  )
  values (
    p_event_kind, v_tx, p_operation_kind, p_object_identity, p_primary_key,
    p_old_state_hash, p_new_state_hash, current_user, p_claimed_actor,
    p_request_id, p_runtime_context, p_source_ref, p_contract_generation,
    p_path_class, p_maintenance_change_id, p_command_tag, p_ddl_object_type,
    p_ddl_object_identity, p_event_payload, v_when, v_prev, v_hash
  )
  returning audit_event_id into v_id;

  update life_runtime.audit_status_v05b
  set audit_head_event_id = v_id,
      audit_head_hash = v_hash
  where singleton_id = 1;

  return v_id;
end
$$;

create function life_runtime.open_blocking_flag_v05b(
  p_event_id bigint,
  p_flag_class text,
  p_change_id text,
  p_evidence_refs text[]
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_flag uuid;
  v_count integer;
begin
  insert into life_runtime.audit_flag_v05b(
    opening_audit_event_id, flag_class, state, change_id, evidence_refs
  )
  values (
    p_event_id, p_flag_class, 'OPEN', p_change_id,
    pg_catalog.coalesce(p_evidence_refs, array[]::text[])
  )
  returning flag_id into v_flag;

  select pg_catalog.count(*)::integer into v_count
  from life_runtime.audit_flag_v05b
  where state in ('OPEN','ESCALATED');

  update life_runtime.audit_status_v05b
  set status = 'FLAGGED',
      open_flag_count = v_count,
      status_epoch = status_epoch + 1
  where singleton_id = 1;

  return v_flag;
end
$$;

create function life_runtime.evaluate_reactivation_v05b(
  p_kind text,
  p_ref jsonb
)
returns boolean
language plpgsql
stable
set search_path = ''
as $$
declare
  v_uuid uuid;
  v_state text;
  v_revision bigint;
begin
  if p_kind = 'NONE' then
    return false;
  end if;

  if p_ref is null then
    return false;
  end if;

  if p_kind = 'OWNER_DIRECTIVE' then
    begin
      v_uuid := (p_ref ->> 'owner_ingress_id')::uuid;
    exception when others then
      return false;
    end;
    return exists (
      select 1
      from life_runtime.owner_ingress_audit_v05b
      where owner_ingress_id = v_uuid
        and claimed_owner = 'Vince'
    );
  elsif p_kind = 'DEPENDENCY_STATE' then
    begin
      v_uuid := (p_ref ->> 'work_id')::uuid;
      v_state := p_ref ->> 'required_state';
      v_revision := nullif(p_ref ->> 'required_revision','')::bigint;
    exception when others then
      return false;
    end;
    return exists (
      select 1
      from life_runtime.work_v05b
      where work_id = v_uuid
        and work_state = v_state
        and (v_revision is null or revision = v_revision)
    );
  elsif p_kind = 'EXACT_EVENT' then
    begin
      v_uuid := (p_ref ->> 'id')::uuid;
    exception when others then
      return false;
    end;
    if p_ref ->> 'kind' = 'OPERATION_RECEIPT' then
      return exists (select 1 from life_runtime.operation_receipt_v05b where request_id = v_uuid);
    elsif p_ref ->> 'kind' = 'TRANSFERENCE_EVENT' then
      return exists (select 1 from life_runtime.transference_event_v05b where transfer_id = v_uuid);
    else
      return false;
    end if;
  end if;

  return false;
end
$$;

create function life_runtime.catalog_snapshot_v05b(
  p_kind text,
  p_identity text
)
returns table(definition_hash text, enabled_state text, object_valid boolean)
language plpgsql
stable
set search_path = ''
as $$
declare
  v_schema text;
  v_table text;
  v_name text;
begin
  if p_kind = 'ROW_TRIGGER' then
    v_schema := pg_catalog.split_part(p_identity,'.',1);
    v_table := pg_catalog.split_part(p_identity,'.',2);
    v_name := pg_catalog.split_part(p_identity,'.',3);
    return query
      select
        life_runtime.json_hash_v05b(pg_catalog.to_jsonb(pg_catalog.pg_get_triggerdef(t.oid, true))),
        t.tgenabled::text,
        true
      from pg_catalog.pg_trigger t
      join pg_catalog.pg_class c on c.oid = t.tgrelid
      join pg_catalog.pg_namespace n on n.oid = c.relnamespace
      where n.nspname = v_schema
        and c.relname = v_table
        and t.tgname = v_name
        and not t.tgisinternal;
  elsif p_kind = 'EVENT_TRIGGER' then
    return query
      select
        life_runtime.json_hash_v05b(
          pg_catalog.jsonb_build_object(
            'name', e.evtname,
            'event', e.evtevent,
            'owner', pg_catalog.pg_get_userbyid(e.evtowner),
            'tags', e.evttags
          )
        ),
        e.evtenabled::text,
        true
      from pg_catalog.pg_event_trigger e
      where e.evtname = p_identity;
  elsif p_kind = 'INDEX' then
    v_schema := pg_catalog.split_part(p_identity,'.',1);
    v_name := pg_catalog.split_part(p_identity,'.',2);
    return query
      select
        life_runtime.json_hash_v05b(pg_catalog.to_jsonb(pg_catalog.pg_get_indexdef(i.indexrelid))),
        null::text,
        (i.indisvalid and i.indisready)
      from pg_catalog.pg_index i
      join pg_catalog.pg_class idx on idx.oid = i.indexrelid
      join pg_catalog.pg_namespace n on n.oid = idx.relnamespace
      where n.nspname = v_schema
        and idx.relname = v_name;
  end if;
end
$$;

create function life_runtime.runtime_catalog_guard_v05b()
returns boolean
language plpgsql
stable
set search_path = ''
as $$
declare
  r record;
  s record;
  v_expected integer;
  v_actual integer;
begin
  select pg_catalog.count(*)::integer into v_expected
  from life_runtime.runtime_catalog_manifest_v05b
  where active;

  if v_expected = 0 then
    return false;
  end if;

  for r in
    select object_kind, object_identity, expected_definition_hash, expected_enabled_state
    from life_runtime.runtime_catalog_manifest_v05b
    where active
    order by object_kind, object_identity
  loop
    select * into s
    from life_runtime.catalog_snapshot_v05b(r.object_kind, r.object_identity);

    if not found
       or s.object_valid is distinct from true
       or s.definition_hash is distinct from r.expected_definition_hash
       or s.enabled_state is distinct from r.expected_enabled_state then
      return false;
    end if;
  end loop;

  select (
    (select pg_catalog.count(*)
       from pg_catalog.pg_trigger t
       join pg_catalog.pg_class c on c.oid=t.tgrelid
       join pg_catalog.pg_namespace n on n.oid=c.relnamespace
      where n.nspname='life_runtime' and not t.tgisinternal)
    +
    (select pg_catalog.count(*)
       from pg_catalog.pg_event_trigger e
      where e.evtname in ('life_runtime_v05b_ddl_command_end','life_runtime_v05b_sql_drop'))
    +
    (select pg_catalog.count(*)
       from pg_catalog.pg_class i
       join pg_catalog.pg_namespace n on n.oid=i.relnamespace
      where n.nspname='life_runtime'
        and i.relkind='i'
        and i.relname='work_v05b_one_active_root_per_goal_uq')
  )::integer into v_actual;

  return v_actual = v_expected;
end
$$;

revoke all on all functions in schema life_runtime from public, anon, authenticated, service_role;

commit;
