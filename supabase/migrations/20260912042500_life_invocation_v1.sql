begin;

create schema if not exists life;

revoke all on schema life from public;
revoke all on schema life from anon;
revoke all on schema life from authenticated;
revoke all on schema life from service_role;

alter default privileges in schema life revoke all on tables from public;
alter default privileges in schema life revoke execute on functions from public;

do $$
begin
  if not exists (
    select 1
    from pg_catalog.pg_roles
    where rolname = 'life_runtime_v1'
  ) then
    create role life_runtime_v1
      login
      noinherit
      nosuperuser
      nocreatedb
      nocreaterole
      noreplication
      nobypassrls;
  end if;
end
$$;

create table life.oauth_callers_v1 (
  auth_subject text not null,
  oauth_client_id text not null,
  state text not null default 'DISABLED',
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint oauth_callers_v1_pk primary key (auth_subject, oauth_client_id),
  constraint oauth_callers_v1_subject_nonempty check (
    pg_catalog.octet_length(pg_catalog.convert_to(auth_subject, 'UTF8')) > 0
  ),
  constraint oauth_callers_v1_client_nonempty check (
    pg_catalog.octet_length(pg_catalog.convert_to(oauth_client_id, 'UTF8')) > 0
  ),
  constraint oauth_callers_v1_state_exact check (state in ('ACTIVE', 'DISABLED'))
);

create table life.invocations (
  invocation_id uuid primary key default pg_catalog.gen_random_uuid(),
  auth_subject text not null,
  oauth_client_id text not null,
  invocation_key uuid not null,
  request_text text not null,
  request_sha256 bytea not null,
  request_utf8_bytes integer not null,
  input_provenance text not null default 'MCP_TOOL_ARGUMENT',
  recorded_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint invocations_caller_fk
    foreign key (auth_subject, oauth_client_id)
    references life.oauth_callers_v1 (auth_subject, oauth_client_id)
    on update restrict
    on delete restrict,
  constraint invocations_idempotency_uq
    unique (auth_subject, oauth_client_id, invocation_key),
  constraint invocations_key_uuid_v4 check (
    invocation_key::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  constraint invocations_request_bytes_exact check (
    request_utf8_bytes = pg_catalog.octet_length(pg_catalog.convert_to(request_text, 'UTF8'))
    and request_utf8_bytes between 1 and 262144
  ),
  constraint invocations_request_sha256_exact check (
    pg_catalog.octet_length(request_sha256) = 32
    and request_sha256 = pg_catalog.sha256(pg_catalog.convert_to(request_text, 'UTF8'))
  ),
  constraint invocations_input_provenance_exact check (
    input_provenance = 'MCP_TOOL_ARGUMENT'
  )
);

create function life.reject_invocation_mutation_v1()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception using
    errcode = '55000',
    message = 'INVOCATION_LEDGER_APPEND_ONLY';
  return null;
end
$$;

create trigger invocations_reject_update_delete_v1
before update or delete on life.invocations
for each row
execute function life.reject_invocation_mutation_v1();

create trigger invocations_reject_truncate_v1
before truncate on life.invocations
for each statement
execute function life.reject_invocation_mutation_v1();

create function life.record_invocation_v1(
  p_auth_subject text,
  p_oauth_client_id text,
  p_invocation_key uuid,
  p_request_text text
)
returns table (
  schema_version integer,
  invocation_id uuid,
  invocation_key uuid,
  recorded_at timestamptz,
  request_sha256 text,
  request_utf8_bytes integer,
  input_provenance text,
  state text,
  replayed boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_caller_state text;
  v_request_utf8_bytes integer;
  v_request_sha256 bytea;
  v_row life.invocations%rowtype;
begin
  if p_invocation_key is null
     or p_invocation_key::text !~ '^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' then
    raise exception using
      errcode = '22023',
      message = 'INVALID_INPUT';
  end if;

  v_request_utf8_bytes := pg_catalog.octet_length(
    pg_catalog.convert_to(p_request_text, 'UTF8')
  );

  if v_request_utf8_bytes is null
     or v_request_utf8_bytes < 1
     or v_request_utf8_bytes > 262144 then
    raise exception using
      errcode = '22023',
      message = 'REQUEST_TEXT_UTF8_BYTES_OUT_OF_RANGE';
  end if;

  v_request_sha256 := pg_catalog.sha256(
    pg_catalog.convert_to(p_request_text, 'UTF8')
  );

  select c.state
    into v_caller_state
  from life.oauth_callers_v1 as c
  where c.auth_subject = p_auth_subject
    and c.oauth_client_id = p_oauth_client_id
  for share;

  if not found or v_caller_state <> 'ACTIVE' then
    raise exception using
      errcode = '42501',
      message = 'CALLER_NOT_ALLOWED';
  end if;

  insert into life.invocations as i (
    auth_subject,
    oauth_client_id,
    invocation_key,
    request_text,
    request_sha256,
    request_utf8_bytes,
    input_provenance
  )
  values (
    p_auth_subject,
    p_oauth_client_id,
    p_invocation_key,
    p_request_text,
    v_request_sha256,
    v_request_utf8_bytes,
    'MCP_TOOL_ARGUMENT'
  )
  on conflict (auth_subject, oauth_client_id, invocation_key) do nothing
  returning i.* into v_row;

  if found then
    return query
    select
      1,
      v_row.invocation_id,
      v_row.invocation_key,
      v_row.recorded_at,
      pg_catalog.encode(v_row.request_sha256, 'hex'),
      v_row.request_utf8_bytes,
      v_row.input_provenance,
      'RECORDED'::text,
      false;
    return;
  end if;

  select i.*
    into strict v_row
  from life.invocations as i
  where i.auth_subject = p_auth_subject
    and i.oauth_client_id = p_oauth_client_id
    and i.invocation_key = p_invocation_key;

  if v_row.request_sha256 is distinct from v_request_sha256 then
    raise exception using
      errcode = '23505',
      message = 'INVOCATION_KEY_REUSE_MISMATCH';
  end if;

  return query
  select
    1,
    v_row.invocation_id,
    v_row.invocation_key,
    v_row.recorded_at,
    pg_catalog.encode(v_row.request_sha256, 'hex'),
    v_row.request_utf8_bytes,
    v_row.input_provenance,
    'RECORDED'::text,
    true;
end
$$;

revoke all on all tables in schema life from public;
revoke all on all tables in schema life from anon;
revoke all on all tables in schema life from authenticated;
revoke all on all tables in schema life from service_role;
revoke all on all tables in schema life from life_runtime_v1;

revoke all on all functions in schema life from public;
revoke all on all functions in schema life from anon;
revoke all on all functions in schema life from authenticated;
revoke all on all functions in schema life from service_role;
revoke all on all functions in schema life from life_runtime_v1;

grant usage on schema life to life_runtime_v1;
grant execute on function life.record_invocation_v1(text, text, uuid, text)
  to life_runtime_v1;

commit;
