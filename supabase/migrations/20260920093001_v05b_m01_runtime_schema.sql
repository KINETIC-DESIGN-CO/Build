begin;

do $$
begin
  if not exists (select 1 from pg_catalog.pg_extension where extname = 'pgcrypto') then
    raise exception using errcode = '55000', message = 'V05B_PGCRYPTO_REQUIRED';
  end if;
end
$$;

create schema if not exists life_runtime;

revoke all on schema life_runtime from public;
revoke all on schema life_runtime from anon;
revoke all on schema life_runtime from authenticated;
revoke all on schema life_runtime from service_role;

alter default privileges in schema life_runtime revoke all on tables from public;
alter default privileges in schema life_runtime revoke execute on functions from public;
alter default privileges in schema life_runtime revoke usage on sequences from public;

comment on schema life_runtime is
  'V0.5B non-live Transference runtime candidate. Object existence grants no runtime authority.';

commit;
