begin;

drop event trigger if exists ensure_rls;
drop function if exists public.rls_auto_enable();

revoke execute on function life.record_invocation_v1(text, text, uuid, text)
  from life_runtime_v1;
drop function life.record_invocation_v1(text, text, uuid, text);

alter table life.invocations
  drop constraint invocations_request_sha256_exact;

alter table life.invocations
  add column schema_version smallint not null default 1,
  add column auth_issuer text not null,
  add column audience text not null,
  add column tool_name text not null default 'life.invoke',
  add column mcp_protocol_version text not null,
  add column runtime_build_sha text not null;

alter table life.invocations
  alter column request_sha256 type text
  using pg_catalog.encode(request_sha256, 'hex');

alter table life.invocations
  add constraint invocations_schema_version_exact
    check (schema_version = 1),
  add constraint invocations_auth_issuer_exact
    check (auth_issuer = 'https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1'),
  add constraint invocations_audience_nonempty
    check (pg_catalog.octet_length(pg_catalog.convert_to(audience, 'UTF8')) > 0),
  add constraint invocations_tool_name_exact
    check (tool_name = 'life.invoke'),
  add constraint invocations_protocol_version_nonempty
    check (
      pg_catalog.octet_length(
        pg_catalog.convert_to(mcp_protocol_version, 'UTF8')
      ) > 0
    ),
  add constraint invocations_runtime_build_sha_nonempty
    check (
      pg_catalog.octet_length(
        pg_catalog.convert_to(runtime_build_sha, 'UTF8')
      ) > 0
    ),
  add constraint invocations_request_sha256_exact
    check (
      request_sha256 ~ '^[0-9a-f]{64}$'
      and request_sha256 = pg_catalog.encode(
        pg_catalog.sha256(pg_catalog.convert_to(request_text, 'UTF8')),
        'hex'
      )
    );

create function life.record_invocation_v1(
  p_auth_subject text,
  p_auth_issuer text,
  p_oauth_client_id text,
  p_audience text,
  p_invocation_key uuid,
  p_request_text text,
  p_mcp_protocol_version text,
  p_runtime_build_sha text
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
  v_request_sha256 text;
  v_row life.invocations%rowtype;
begin
  if p_auth_issuer is distinct from
       'https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1' then
    raise exception using
      errcode = '22023',
      message = 'INVALID_INPUT';
  end if;

  if p_audience is null
     or pg_catalog.octet_length(
          pg_catalog.convert_to(p_audience, 'UTF8')
        ) < 1
     or p_mcp_protocol_version is null
     or pg_catalog.octet_length(
          pg_catalog.convert_to(p_mcp_protocol_version, 'UTF8')
        ) < 1
     or p_runtime_build_sha is null
     or pg_catalog.octet_length(
          pg_catalog.convert_to(p_runtime_build_sha, 'UTF8')
        ) < 1 then
    raise exception using
      errcode = '22023',
      message = 'INVALID_INPUT';
  end if;

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

  v_request_sha256 := pg_catalog.encode(
    pg_catalog.sha256(pg_catalog.convert_to(p_request_text, 'UTF8')),
    'hex'
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
    schema_version,
    auth_subject,
    auth_issuer,
    oauth_client_id,
    audience,
    invocation_key,
    tool_name,
    request_text,
    request_sha256,
    request_utf8_bytes,
    input_provenance,
    mcp_protocol_version,
    runtime_build_sha
  )
  values (
    1,
    p_auth_subject,
    p_auth_issuer,
    p_oauth_client_id,
    p_audience,
    p_invocation_key,
    'life.invoke',
    p_request_text,
    v_request_sha256,
    v_request_utf8_bytes,
    'MCP_TOOL_ARGUMENT',
    p_mcp_protocol_version,
    p_runtime_build_sha
  )
  on conflict on constraint invocations_idempotency_uq do nothing
  returning i.* into v_row;

  if found then
    return query
    select
      1,
      v_row.invocation_id,
      v_row.invocation_key,
      v_row.recorded_at,
      v_row.request_sha256,
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
    v_row.request_sha256,
    v_row.request_utf8_bytes,
    v_row.input_provenance,
    'RECORDED'::text,
    true;
end
$$;

revoke all on all functions in schema life from public;
revoke all on all functions in schema life from anon;
revoke all on all functions in schema life from authenticated;
revoke all on all functions in schema life from service_role;
revoke all on all functions in schema life from life_runtime_v1;

grant usage on schema life to life_runtime_v1;
grant execute on function life.record_invocation_v1(
  text, text, text, text, uuid, text, text, text
) to life_runtime_v1;

commit;
