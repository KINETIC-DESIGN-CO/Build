begin;

create extension if not exists pgtap with schema extensions;
set local search_path = extensions, pg_catalog, public;

select plan(31);

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
  pg_catalog.to_regprocedure('life.record_invocation_v1(text,text,uuid,text)') is not null,
  'record_invocation_v1 exists with exact signature'
);

select ok(
  (
    select p.prosecdef
    from pg_catalog.pg_proc as p
    where p.oid = pg_catalog.to_regprocedure('life.record_invocation_v1(text,text,uuid,text)')
  ),
  'record_invocation_v1 is security definer'
);

select ok(
  (
    select p.proconfig = array['search_path=""']::text[]
    from pg_catalog.pg_proc as p
    where p.oid = pg_catalog.to_regprocedure('life.record_invocation_v1(text,text,uuid,text)')
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
    'life.record_invocation_v1(text,text,uuid,text)',
    'EXECUTE'
  ),
  'runtime role can execute only the invocation entry function'
);

select ok(
  not pg_catalog.has_table_privilege('life_runtime_v1', 'life.invocations', 'SELECT'),
  'runtime role cannot select invocation rows directly'
);

select ok(
  not pg_catalog.has_table_privilege('life_runtime_v1', 'life.invocations', 'INSERT'),
  'runtime role cannot insert invocation rows directly'
);

select ok(
  not pg_catalog.has_table_privilege('life_runtime_v1', 'life.invocations', 'UPDATE'),
  'runtime role cannot update invocation rows directly'
);

select ok(
  not pg_catalog.has_table_privilege('life_runtime_v1', 'life.invocations', 'DELETE'),
  'runtime role cannot delete invocation rows directly'
);

select ok(
  not pg_catalog.has_function_privilege(
    'anon',
    'life.record_invocation_v1(text,text,uuid,text)',
    'EXECUTE'
  ),
  'anon cannot execute record_invocation_v1'
);

select ok(
  not pg_catalog.has_function_privilege(
    'service_role',
    'life.record_invocation_v1(text,text,uuid,text)',
    'EXECUTE'
  ),
  'service_role cannot execute record_invocation_v1'
);

insert into life.oauth_callers_v1 (auth_subject, oauth_client_id, state)
values ('subject-1', 'client-1', 'DISABLED');

select throws_ok(
  $$select * from life.record_invocation_v1(
      'subject-1',
      'client-1',
      '11111111-1111-4111-8111-111111111111'::uuid,
      'hello'
    )$$,
  '42501',
  'CALLER_NOT_ALLOWED',
  'disabled caller cannot record an invocation'
);

update life.oauth_callers_v1
set state = 'ACTIVE'
where auth_subject = 'subject-1'
  and oauth_client_id = 'client-1';

select results_eq(
  $$select schema_version, replayed, state, input_provenance, request_utf8_bytes
    from life.record_invocation_v1(
      'subject-1',
      'client-1',
      '11111111-1111-4111-8111-111111111111'::uuid,
      'hello'
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
    select pg_catalog.encode(request_sha256, 'hex')
    from life.invocations
    where invocation_key = '11111111-1111-4111-8111-111111111111'::uuid
  ),
  pg_catalog.encode(
    pg_catalog.sha256(pg_catalog.convert_to('hello', 'UTF8')),
    'hex'
  ),
  'ledger hash is SHA-256 of exact UTF-8 request bytes'
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

select results_eq(
  $$select replayed, state
    from life.record_invocation_v1(
      'subject-1',
      'client-1',
      '11111111-1111-4111-8111-111111111111'::uuid,
      'hello'
    )$$,
  $$values (true, 'RECORDED'::text)$$,
  'same idempotency key and same request replays existing invocation'
);

select is(
  (select pg_catalog.count(*)::bigint from life.invocations),
  1::bigint,
  'idempotent replay does not add a second ledger row'
);

select throws_ok(
  $$select * from life.record_invocation_v1(
      'subject-1',
      'client-1',
      '11111111-1111-4111-8111-111111111111'::uuid,
      'different'
    )$$,
  '23505',
  'INVOCATION_KEY_REUSE_MISMATCH',
  'same key with different request is rejected'
);

select throws_ok(
  $$select * from life.record_invocation_v1(
      'subject-1',
      'client-1',
      '22222222-2222-4222-8222-222222222222'::uuid,
      ''
    )$$,
  '22023',
  'REQUEST_TEXT_UTF8_BYTES_OUT_OF_RANGE',
  'empty request text is rejected'
);

select throws_ok(
  $$select * from life.record_invocation_v1(
      'subject-1',
      'client-1',
      '33333333-3333-4333-8333-333333333333'::uuid,
      repeat('a', 262145)
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
      'client-1',
      '44444444-4444-4444-8444-444444444444'::uuid,
      'after-disable'
    )$$,
  '42501',
  'CALLER_NOT_ALLOWED',
  'caller must still be ACTIVE for a new invocation'
);

select * from finish();
rollback;
