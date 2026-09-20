begin;

create table life_runtime.operation_receipt_v05b (
  request_id uuid primary key,
  operation_kind text not null check (
    operation_kind in ('APPLY_TRANSFERENCE','DEFER_WORK','REACTIVATE_WORK','CLOSE_WORK','KICK_RETURN','APPLY_OWNER_DECISION')
  ),
  work_id uuid not null references life_runtime.work_v05b(work_id) on update restrict on delete restrict,
  expected_revision bigint not null check (expected_revision >= 0),
  canonical_request jsonb not null,
  canonical_request_hash text not null check (canonical_request_hash ~ '^[0-9a-f]{64}$'),
  claimed_actor text not null check (claimed_actor in ('Clea','Alexander','Connor','Caden','Claude','Kal')),
  source_ref text not null,
  contract_generation text not null,
  exact_result_code text not null check (
    exact_result_code in (
      'APPLIED','STALE_REVISION','VALIDATION_REJECTED','MAINTENANCE_BLOCKED',
      'AUDIT_HOLD','RUNTIME_UNAVAILABLE','REACTIVATION_CONDITION_FALSE',
      'BLOCKED_NO_RESUMABLE_RETURN','OWNER_DECISION_REQUIRED','OWNER_SOURCE_MISMATCH'
    )
  ),
  exact_result_payload jsonb not null,
  committed_work_revision bigint check (committed_work_revision is null or committed_work_revision >= 0),
  transfer_id uuid,
  expected_audit_event_count integer not null default 0 check (expected_audit_event_count >= 0),
  created_at timestamptz not null default pg_catalog.clock_timestamp()
);

create table life_runtime.transference_event_v05b (
  transfer_id uuid primary key default pg_catalog.gen_random_uuid(),
  request_id uuid not null unique
    references life_runtime.operation_receipt_v05b(request_id) on update restrict on delete restrict,
  transfer_state_id text not null check (transfer_state_id ~ '^[0-9a-f]{64}$'),
  work_id uuid not null references life_runtime.work_v05b(work_id) on update restrict on delete restrict,
  expected_revision bigint not null check (expected_revision >= 0),
  resulting_revision bigint not null check (resulting_revision >= 0),
  predecessor_transfer_id uuid references life_runtime.transference_event_v05b(transfer_id) on update restrict on delete restrict,
  root_goal_id text not null,
  root_goal_revision_at_transfer bigint not null check (root_goal_revision_at_transfer >= 0),
  parent_work_id uuid,
  return_work_id uuid,
  branch_depth integer not null check (branch_depth >= 0),
  branch_kind text not null check (branch_kind in ('ROOT','SPLINTER')),
  resulting_work_state text not null check (
    resulting_work_state in ('ACTIVE','DEFERRED','COMPLETED','CANCELLED','SUPERSEDED')
  ),
  evidence_refs text[] not null default array[]::text[],
  open_finding_refs text[] not null default array[]::text[],
  next_actor text check (
    next_actor is null or next_actor in ('Vince','Clea','Alexander','Connor','Caden','Claude','Kal')
  ),
  next_action_ref text,
  reactivation_condition_kind text not null check (
    reactivation_condition_kind in ('NONE','OWNER_DIRECTIVE','DEPENDENCY_STATE','EXACT_EVENT')
  ),
  reactivation_condition_ref jsonb,
  source_generation text not null,
  contract_generation text not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp()
);

create table life_runtime.maintenance_receipt_v05b (
  maintenance_receipt_id uuid primary key default pg_catalog.gen_random_uuid(),
  change_id text not null,
  action text not null check (action in ('ENTER','CHANGE','EXIT')),
  source_ref text not null,
  claimed_actor text not null check (
    claimed_actor in ('Vince','Clea','Alexander','Connor','Caden','Claude','Kal')
  ),
  maintenance_epoch_before bigint not null check (maintenance_epoch_before >= 0),
  maintenance_epoch_after bigint not null check (maintenance_epoch_after >= 0),
  audit_head_event_id_before bigint,
  audit_head_event_id_after bigint,
  created_at timestamptz not null default pg_catalog.clock_timestamp()
);

create table life_runtime.owner_ingress_audit_v05b (
  owner_ingress_id uuid primary key default pg_catalog.gen_random_uuid(),
  claimed_owner text not null default 'Vince' check (claimed_owner = 'Vince'),
  source_type text not null,
  source_ref text not null,
  canonical_action jsonb not null,
  canonical_action_hash text not null check (canonical_action_hash ~ '^[0-9a-f]{64}$'),
  consuming_request_id uuid not null unique
    references life_runtime.operation_receipt_v05b(request_id) on update restrict on delete restrict,
  recorded_at timestamptz not null default pg_catalog.clock_timestamp()
);

revoke all on all tables in schema life_runtime from public, anon, authenticated, service_role;

commit;
