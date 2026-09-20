begin;

create function life_runtime.ddl_command_end_audit_v05b()
returns event_trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  r record;
  v_m life_runtime.maintenance_state_v05b%rowtype;
  v_path text;
  v_event bigint;
begin
  select * into v_m from life_runtime.maintenance_state_v05b where singleton_id=1;
  for r in select * from pg_catalog.pg_event_trigger_ddl_commands()
  loop
    if r.schema_name='life_runtime' then
      v_path := case when v_m.state='ON' and v_m.change_id is not null
                     then 'APPROVED_RUNTIME_PATH' else 'OUT_OF_PATH' end;
      v_event := life_runtime.append_audit_event_v05b(
        'DDL_CHANGE',
        r.command_tag,
        r.object_identity,
        null,null,null,
        v_m.claimed_actor,
        null,
        'DDL_EVENT_TRIGGER',
        v_m.source_ref,
        'V05B',
        v_path,
        v_m.change_id,
        r.command_tag,
        r.object_type,
        r.object_identity,
        pg_catalog.jsonb_build_object('schema_name',r.schema_name)
      );
      if v_path='OUT_OF_PATH' and v_event is not null then
        perform life_runtime.open_blocking_flag_v05b(
          v_event,'DDL_PROTECTED_OBJECT_CHANGE',v_m.change_id,
          array[r.command_tag,r.object_identity]
        );
      end if;
    end if;
  end loop;
end
$$;

create function life_runtime.sql_drop_audit_v05b()
returns event_trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  r record;
  v_m life_runtime.maintenance_state_v05b%rowtype;
  v_path text;
  v_event bigint;
begin
  select * into v_m from life_runtime.maintenance_state_v05b where singleton_id=1;
  for r in select * from pg_catalog.pg_event_trigger_dropped_objects()
  loop
    if r.schema_name='life_runtime' then
      v_path := case when v_m.state='ON' and v_m.change_id is not null
                     then 'APPROVED_RUNTIME_PATH' else 'OUT_OF_PATH' end;
      v_event := life_runtime.append_audit_event_v05b(
        'DDL_CHANGE',
        tg_tag,
        r.object_identity,
        null,null,null,
        v_m.claimed_actor,
        null,
        'DDL_EVENT_TRIGGER',
        v_m.source_ref,
        'V05B',
        v_path,
        v_m.change_id,
        tg_tag,
        r.object_type,
        r.object_identity,
        pg_catalog.jsonb_build_object('schema_name',r.schema_name,'original',r.original)
      );
      if v_path='OUT_OF_PATH' and v_event is not null then
        perform life_runtime.open_blocking_flag_v05b(
          v_event,'DDL_PROTECTED_OBJECT_CHANGE',v_m.change_id,
          array[tg_tag,r.object_identity]
        );
      end if;
    end if;
  end loop;
end
$$;

revoke all on function life_runtime.ddl_command_end_audit_v05b() from public, anon, authenticated, service_role;
revoke all on function life_runtime.sql_drop_audit_v05b() from public, anon, authenticated, service_role;

create event trigger life_runtime_v05b_ddl_command_end
on ddl_command_end
execute function life_runtime.ddl_command_end_audit_v05b();

create event trigger life_runtime_v05b_sql_drop
on sql_drop
execute function life_runtime.sql_drop_audit_v05b();

commit;
