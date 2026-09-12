begin;

create extension if not exists pgtap with schema extensions;
set local search_path = extensions, pg_catalog, public;

select plan(52);

select ok(
  pg_catalog.to_regnamespace('life') is not null,
  'life schema exists'
);

select ok(
  pg_catalog.to_regclass('life.oauth_callers_v1') is not null,
  'caller allowlist table exists'
);

select ok(
  pg_catalog.to_regclass('life.invocations') is not null,
  'invocation ledger table exists'
);

select ok(
  exists (select 1 from pg_catalog.pg_roles where rolname = 'life_runtime_v1'),
  'dedicated runtime role exists'
);

select ok(
  (select rolcanlogin from pg_catalog.pg_roles where rolname = 'life_runtime_v1'),
  'runtime role can log in'
);

select ok(
  not (select rolsuper from pg_catalog.pg_roles where rolname = 'life_runtime_v1'),
  'runtime role is not superuser'
);

select ok(
  pg_catalog.to_regprocedure(
    'life.record_invocation_v1(text,text,uuid,text)'
  ) is null,
  'legacy record_invocation_v1 signature is removed'
);

select ok(
  pg_catalog.to_regprocedure(
    'life.record_invocation_v1(text,text,text,text,uuid,text,text,text)'
  ) is not null,
  'record_invocation_v1 exists with aligned exact signature'
);

select ok(
  (
    select p.prosecdef
    from pg_catalog.pg_proc as p
    where p.oid = pg_catalog.to_regprocedure(
      'life.record_invocation_v1(text,text,text,text,uuid,text,text,text)'
    )
  ),
  'record_invocation_v1 is security definer'
);

select ok(
  (
    select p.proconfig = array['search_path=""']::text[]
    from pg_catalog.pg_proc as p
    where p.oid = pg_catalog.to_regprocedure(
      'life.record_invocation_v1(text,text,text,text,uuid,text,text,text)'
    )
  ),
  'record_invocation_v1 pins an empty search_path'
);

select ok(
  pg_catalog.has_schema_privilege('life_runtime_v1', 'life', 'USAGE'),
  'runtime role has life schema usage'
);

select ok(
  pg_catalog.has_function_privilege(
    'life_runtime_v1',
    'life.record_invocation_v1(text,text,text,text,uuid,text,text,text)',
    'EXECUTE'
  ),
  'runtime role can execute the aligned invocation entry function'
);

select ok(
  not pg_catalog.has_table_privilege(
    'life_runtime_v1', 'life.invocations', 'SELECT'
  ),
  'runtime role cannot select invocation rows directly'
);

select ok(
  not pg_catalog.has_table_privilege(
    'life_runtime_v1', 'life.invocations', 'INSERT'
  ),
  'runtime role cannot insert invocation rows directly'
);

select ok(
  not pg_catalog.has_table_privilege(
    'life_runtime_v1', 'life.invocations', 'UPDATE'
  ),
  'runtime role cannot update invocation rows directly'
);

select ok(
  not pg_catalog.has_table_privilege(
    'life_runtime_v1', 'life.invocations', 'DELETE'
  ),
  'runtime role cannot delete invocation rows directly'
);

select ok(
  not pg_catalog.has_function_privilege(
    'anon',
    'life.record_invocation_v1(text,text,text,text,uuid,text,text,text)',
    'EXECUTE'
  ),
  'anon cannot execute record_invocation_v1'
);

select ok(
  not pg_catalog.has_function_privilege(
    'service_role',
    'life.record_invocation_v1(text,text,text,text,uuid,text,text,text)',
    'EXECUTE'
  ),
  'service_role cannot execute record_invocation_v1'
);

select ok(
  not exists (
    select 1
    from pg_catalog.pg_event_trigger
    where evtname = 'ensure_rls'
  ),
  'legacy ensure_rls event trigger is absent'
);

select ok(
  pg_catalog.to_regprocedure('public.rls_auto_enable()') is null,
  'legacy public.rls_auto_enable function is absent'
);

select is(
  (
    select data_type::text
    from information_schema.columns
    where table_schema = 'life'
      and table_name = 'invocations'
      and column_name = 'schema_version'
  ),
  'smallint',
  'schema_version is smallint'
);

select ok(
  exists (
    select 1 from information_schema.columns
    where table_schema = 'life'
      and table_name = 'invocations'
      and column_name = 'auth_issuer'
  ),
  'auth_issuer column exists'
);

select ok(
  exists (
    select 1 from information_schema.columns
    where table_schema = 'life'
      and table_name = 'invocations'
      and column_name = 'audience'
  ),
  'audience column exists'
);

select ok(
  exists (
    select 1 from information_schema.columns
    where table_schema = 'life'
      and table_name = 'invocations'
      and column_name = 'tool_name'
  ),
  'tool_name column exists'
);

select ok(
  exists (
    select 1 from information_schema.columns
    where table_schema = 'life'
      and table_name = 'invocations'
      and column_name = 'mcp_protocol_version'
  ),
  'mcp_protocol_version column exists'
);

select ok(
  exists (
    select 1 from information_schema.columns
    where table_schema = 'life'
      and table_name = 'invocations'
      and column_name = 'runtime_build_sha'
  ),
  'runtime_build_sha column exists'
);

select is(
  (
    select data_type::text
    from information_schema.columns
    where table_schema = 'life'
      and table_name = 'invocations'
      and column_name = 'request_sha256'
  ),
  'text',
  'request_sha256 is stored as lowercase text hex'
);

insert into life.oauth_callers_v1 (auth_subject, oauth_client_id, state)
values ('subject-1', 'client-1', 'DISABLED');

select throws_ok(
  $$select * from life.record_invocation_v1(
      'subject-1',
      'https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1',
      'client-1',
      'https://example.invalid/life-mcp',
      '11111111-1111-4111-8111-111111111111'::uuid,
      'hello',
      '2026-07-28',
      '883c7aea6ff228baac9acc6515233919fa5e9225'
    )$$,
  '42501',
  'CALLER_NOT_ALLOWED',
  'disabled caller cannot record an invocation'
);

update life.oauth_callers_v1
set state = 'ACTIVE'
where auth_subject = 'subject-1'
  and oauth_client_id = 'client-1';

select throws_ok(
  $$select * from life.record_invocation_v1(
      'subject-1',
      'https://wrong.invalid/auth/v1',
      'client-1',
      'https://example.invalid/life-mcp',
      '11111111-1111-4111-8111-111111111111'::uuid,
      'hello',
      '2026-07-28',
      '883c7aea6ff228baac9acc6515233919fa5e9225'
    )$$,
  '22023',
  'INVALID_INPUT',
  'noncanonical issuer is rejected'
);

select throws_ok(
  $$select * from life.record_invocation_v1(
      'subject-1',
      'https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1',
      'client-1',
      '',
      '11111111-1111-4111-8111-111111111111'::uuid,
      'hello',
      '2026-07-28',
      '883c7aea6ff228baac9acc6515233919fa5e9225'
    )$$,
  '22023',
  'INVALID_INPUT',
  'empty audience is rejected'
);

select throws_ok(
  $$select * from life.record_invocation_v1(
      'subject-1',
      'https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1',
      'client-1',
      'https://example.invalid/life-mcp',
      '11111111-1111-4111-8111-111111111111'::uuid,
      'hello',
      '',
      '883c7aea6ff228baac9acc6515233919fa5e9225'
    )$$,
  '22023',
  'INVALID_INPUT',
  'empty MCP protocol version is rejected'
);

select throws_ok(
  $$select * from life.record_invocation_v1(
      'subject-1',
      'https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1',
      'client-1',
      'https://example.invalid/life-mcp',
      '11111111-1111-4111-8111-111111111111'::uuid,
      'hello',
      '2026-07-28',
      ''
    )$$,
  '22023',
  'INVALID_INPUT',
  'empty runtime build SHA is rejected'
);

select results_eq(
  $$select schema_version, replayed, state, input_provenance, request_utf8_bytes
    from life.record_invocation_v1(
      'subject-1',
      'https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1',
      'client-1',
      'https://example.invalid/life-mcp',
      '11111111-1111-4111-8111-111111111111'::uuid,
      'hello',
      '2026-07-28',
      '883c7aea6ff228baac9acc6515233919fa5e9225'
    )$$,
  $$values (1, false, 'RECORDED'::text, 'MCP_TOOL_ARGUMENT'::text, 5)$$,
  'first invocation records exact success semantics'
);

select is(
  (select pg_catalog.count(*)::bigint from life.invocations),
  1::bigint,
  'first invocation creates exactly one ledger row'
);

select is(
  (
    select schema_version
    from life.invocations
    where invocation_key = '11111111-1111-4111-8111-111111111111'::uuid
  ),
  1::smallint,
  'ledger stores schema version 1'
);

select is(
  (
    select auth_issuer
    from life.invocations
    where invocation_key = '11111111-1111-4111-8111-111111111111'::uuid
  ),
  'https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1',
  'ledger stores exact validated issuer'
);

select is(
  (
    select audience
    from life.invocations
    where invocation_key = '11111111-1111-4111-8111-111111111111'::uuid
  ),
  'https://example.invalid/life-mcp',
  'ledger stores exact validated audience'
);

select is(
  (
    select tool_name
    from life.invocations
    where invocation_key = '11111111-1111-4111-8111-111111111111'::uuid
  ),
  'life.invoke',
  'ledger stores exact tool name'
);

select is(
  (
    select request_sha256
    from life.invocations
    where invocation_key = '11111111-1111-4111-8111-111111111111'::uuid
  ),
  pg_catalog.encode(
    pg_catalog.sha256(pg_catalog.convert_to('hello', 'UTF8')),
    'hex'
  ),
  'ledger hash is lowercase SHA-256 text of exact UTF-8 request bytes'
);

select is(
  (
    select request_utf8_bytes
    from life.invocations
    where invocation_key = '11111111-1111-4111-8111-111111111111'::uuid
  ),
  5,
  'ledger stores exact UTF-8 byte length'
);

select is(
  (
    select mcp_protocol_version
    from life.invocations
    where invocation_key = '11111111-1111-4111-8111-111111111111'::uuid
  ),
  '2026-07-28',
  'ledger stores actual MCP protocol version'
);

select is(
  (
    select runtime_build_sha
    from life.invocations
    where invocation_key = '11111111-1111-4111-8111-111111111111'::uuid
  ),
  '883c7aea6ff228baac9acc6515233919fa5e9225',
  'ledger stores exact runtime build commit SHA'
);

select results_eq(
  $$select replayed, state
    from life.record_invocation_v1(
      'subject-1',
      'https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1',
      'client-1',
      'https://example.invalid/life-mcp',
      '11111111-1111-4111-8111-111111111111'::uuid,
      'hello',
      '2026-07-28',
      'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    )$$,
  $$values (true, 'RECORDED'::text)$$,
  'same idempotency key and request replays the existing record'
);

select is(
  (select pg_catalog.count(*)::bigint from life.invocations),
  1::bigint,
  'idempotent replay does not add a second ledger row'
);

select is(
  (
    select runtime_build_sha
    from life.invocations
    where invocation_key = '11111111-1111-4111-8111-111111111111'::uuid
  ),
  '883c7aea6ff228baac9acc6515233919fa5e9225',
  'idempotent replay preserves the original canonical record'
);

select throws_ok(
  $$select * from life.record_invocation_v1(
      'subject-1',
      'https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1',
      'client-1',
      'https://example.invalid/life-mcp',
      '11111111-1111-4111-8111-111111111111'::uuid,
      'different',
      '2026-07-28',
      '883c7aea6ff228baac9acc6515233919fa5e9225'
    )$$,
  '23505',
  'INVOCATION_KEY_REUSE_MISMATCH',
  'same key with different request is rejected'
);

select throws_ok(
  $$select * from life.record_invocation_v1(
      'subject-1',
      'https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1',
      'client-1',
      'https://example.invalid/life-mcp',
      '22222222-2222-4222-8222-222222222222'::uuid,
      '',
      '2026-07-28',
      '883c7aea6ff228baac9acc6515233919fa5e9225'
    )$$,
  '22023',
  'REQUEST_TEXT_UTF8_BYTES_OUT_OF_RANGE',
  'empty request text is rejected'
);

select throws_ok(
  $$select * from life.record_invocation_v1(
      'subject-1',
      'https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1',
      'client-1',
      'https://example.invalid/life-mcp',
      '33333333-3333-4333-8333-333333333333'::uuid,
      repeat('a', 262145),
      '2026-07-28',
      '883c7aea6ff228baac9acc6515233919fa5e9225'
    )$$,
  '22023',
  'REQUEST_TEXT_UTF8_BYTES_OUT_OF_RANGE',
  'request text above 262144 UTF-8 bytes is rejected'
);

select throws_ok(
  $$update life.invocations set request_text = 'changed'$$,
  '55000',
  'INVOCATION_LEDGER_APPEND_ONLY',
  'invocation ledger rejects update'
);

select throws_ok(
  $$delete from life.invocations$$,
  '55000',
  'INVOCATION_LEDGER_APPEND_ONLY',
  'invocation ledger rejects delete'
);

select throws_ok(
  $$truncate table life.invocations$$,
  '55000',
  'INVOCATION_LEDGER_APPEND_ONLY',
  'invocation ledger rejects truncate'
);

update life.oauth_callers_v1
set state = 'DISABLED'
where auth_subject = 'subject-1'
  and oauth_client_id = 'client-1';

select throws_ok(
  $$select * from life.record_invocation_v1(
      'subject-1',
      'https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1',
      'client-1',
      'https://example.invalid/life-mcp',
      '44444444-4444-4444-8444-444444444444'::uuid,
      'after-disable',
      '2026-07-28',
      '883c7aea6ff228baac9acc6515233919fa5e9225'
    )$$,
  '42501',
  'CALLER_NOT_ALLOWED',
  'caller must still be ACTIVE for a new invocation'
);

select * from finish();
rollback;
