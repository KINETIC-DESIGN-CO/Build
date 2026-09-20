begin;

drop event trigger if exists life_runtime_v05b_sql_drop;
drop event trigger if exists life_runtime_v05b_ddl_command_end;
drop schema if exists life_runtime cascade;

do $$
begin
  if pg_catalog.to_regnamespace('life') is null
     or pg_catalog.to_regclass('life.oauth_callers_v1') is null
     or pg_catalog.to_regclass('life.invocations') is null
     or pg_catalog.to_regprocedure('life.record_invocation_v1(text,text,text,text,uuid,text,text,text)') is null then
    raise exception using errcode='55000',message='V05B_ROLLBACK_LEGACY_LIFE_REGRESSION';
  end if;
end
$$;

commit;
