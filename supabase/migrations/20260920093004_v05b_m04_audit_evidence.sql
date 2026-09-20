begin;

create table life_runtime.audit_event_v05b (
  audit_event_id bigint generated always as identity primary key,
  event_kind text not null check (event_kind in ('ROW_MUTATION','DDL_CHANGE')),
  transaction_id text not null,
  operation_kind text not null,
  object_identity text not null,
  primary_key jsonb,
  old_state_hash text check (old_state_hash is null or old_state_hash ~ '^[0-9a-f]{64}$'),
  new_state_hash text check (new_state_hash is null or new_state_hash ~ '^[0-9a-f]{64}$'),
  database_principal text not null,
  claimed_life_actor text,
  request_id uuid references life_runtime.operation_receipt_v05b(request_id) on update restrict on delete restrict,
  runtime_function_context text,
  source_ref text,
  contract_generation text not null,
  path_class text not null check (
    path_class in ('APPROVED_RUNTIME_PATH','OUT_OF_PATH','AUDIT_TAMPER_ATTEMPT')
  ),
  maintenance_change_id text,
  command_tag text,
  ddl_object_type text,
  ddl_object_identity text,
  event_payload jsonb,
  occurred_at timestamptz not null default pg_catalog.clock_timestamp(),
  previous_audit_hash text not null check (previous_audit_hash ~ '^[0-9a-f]{64}$'),
  audit_event_hash text not null check (audit_event_hash ~ '^[0-9a-f]{64}$')
);

alter table life_runtime.audit_status_v05b
  add constraint audit_status_head_event_fk
  foreign key (audit_head_event_id)
  references life_runtime.audit_event_v05b(audit_event_id)
  deferrable initially deferred;

create table life_runtime.audit_flag_v05b (
  flag_id uuid primary key default pg_catalog.gen_random_uuid(),
  opening_audit_event_id bigint not null
    references life_runtime.audit_event_v05b(audit_event_id) on update restrict on delete restrict,
  flag_class text not null check (
    flag_class in (
      'OUT_OF_PATH','AUDIT_TAMPER_ATTEMPT','DDL_PROTECTED_OBJECT_CHANGE',
      'CATALOG_MISMATCH','RECEIPT_EVENT_MISMATCH','AUDIT_HASH_MISMATCH'
    )
  ),
  state text not null check (state in ('OPEN','ESCALATED','CLEARED')),
  change_id text,
  evidence_refs text[] not null default array[]::text[],
  opened_at timestamptz not null default pg_catalog.clock_timestamp(),
  escalated_at timestamptz,
  cleared_at timestamptz
);

create table life_runtime.audit_clear_receipt_v05b (
  clear_receipt_id uuid primary key default pg_catalog.gen_random_uuid(),
  flag_id uuid not null references life_runtime.audit_flag_v05b(flag_id) on update restrict on delete restrict,
  disposition text not null check (
    disposition in ('ACCIDENTAL','AUTHORIZED_MAINTENANCE','UNEXPLAINED','OWNER_RESOLVED')
  ),
  change_id text,
  evidence_refs text[] not null default array[]::text[],
  reviewer_name text check (reviewer_name is null or reviewer_name in ('Connor','Claude')),
  reviewer_source_ref text,
  clearing_database_principal text not null,
  claimed_clearing_actor text not null check (
    claimed_clearing_actor in ('Vince','Clea','Alexander','Connor','Caden','Claude','Kal')
  ),
  owner_ingress_id uuid references life_runtime.owner_ingress_audit_v05b(owner_ingress_id) on update restrict on delete restrict,
  old_flag_state text not null check (old_flag_state in ('OPEN','ESCALATED','CLEARED')),
  new_flag_state text not null check (new_flag_state in ('OPEN','ESCALATED','CLEARED')),
  audit_head_event_id bigint,
  audit_head_hash text not null check (audit_head_hash ~ '^[0-9a-f]{64}$'),
  clearing_operation_request_id uuid not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint audit_clear_review_shape_ck check (
    (disposition = 'OWNER_RESOLVED' and owner_ingress_id is not null and reviewer_name is null and reviewer_source_ref is null)
    or
    (disposition <> 'OWNER_RESOLVED' and reviewer_name is not null and reviewer_source_ref is not null)
  )
);

create table life_runtime.audit_verification_receipt_v05b (
  verification_receipt_id uuid primary key default pg_catalog.gen_random_uuid(),
  from_event_id bigint,
  from_hash text not null check (from_hash ~ '^[0-9a-f]{64}$'),
  fixed_target_head_event_id bigint,
  fixed_target_head_hash text not null check (fixed_target_head_hash ~ '^[0-9a-f]{64}$'),
  result text not null check (result in ('PASS','FLAGGED','UNVERIFIED')),
  events_checked integer not null check (events_checked >= 0),
  receipts_checked integer not null check (receipts_checked >= 0),
  flags_open_or_escalated integer not null check (flags_open_or_escalated >= 0),
  mismatch_refs text[] not null default array[]::text[],
  verified_at timestamptz not null default pg_catalog.clock_timestamp(),
  resulting_status_epoch bigint not null check (resulting_status_epoch >= 0)
);

create table life_runtime.runtime_catalog_manifest_v05b (
  catalog_entry_id uuid primary key default pg_catalog.gen_random_uuid(),
  object_kind text not null check (object_kind in ('ROW_TRIGGER','EVENT_TRIGGER','INDEX')),
  object_identity text not null unique,
  expected_definition_hash text not null check (expected_definition_hash ~ '^[0-9a-f]{64}$'),
  expected_enabled_state text,
  contract_generation text not null,
  active boolean not null default true,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint catalog_enabled_shape_ck check (
    (object_kind in ('ROW_TRIGGER','EVENT_TRIGGER') and expected_enabled_state is not null)
    or (object_kind = 'INDEX' and expected_enabled_state is null)
  )
);

revoke all on all tables in schema life_runtime from public, anon, authenticated, service_role;

commit;
