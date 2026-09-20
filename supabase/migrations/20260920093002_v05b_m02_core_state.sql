begin;

create table life_runtime.maintenance_state_v05b (
  singleton_id smallint primary key default 1 check (singleton_id = 1),
  state text not null check (state in ('OFF','ON')),
  change_id text,
  source_ref text,
  claimed_actor text check (
    claimed_actor is null or claimed_actor in ('Vince','Clea','Alexander','Connor','Caden','Claude','Kal')
  ),
  entered_at timestamptz,
  maintenance_epoch bigint not null default 0 check (maintenance_epoch >= 0)
);

create table life_runtime.audit_status_v05b (
  singleton_id smallint primary key default 1 check (singleton_id = 1),
  status text not null check (status in ('PASS','FLAGGED','UNVERIFIED')),
  audit_head_event_id bigint,
  audit_head_hash text not null check (audit_head_hash ~ '^[0-9a-f]{64}$'),
  open_flag_count integer not null default 0 check (open_flag_count >= 0),
  last_full_verified_event_id bigint,
  last_full_verified_hash text not null check (last_full_verified_hash ~ '^[0-9a-f]{64}$'),
  last_full_verification_at timestamptz,
  status_epoch bigint not null default 0 check (status_epoch >= 0)
);

create table life_runtime.work_v05b (
  work_id uuid primary key,
  revision bigint not null default 0 check (revision >= 0),
  root_goal_id text not null check (pg_catalog.octet_length(pg_catalog.convert_to(root_goal_id,'UTF8')) > 0),
  root_goal_revision_at_transfer bigint not null check (root_goal_revision_at_transfer >= 0),
  parent_work_id uuid references life_runtime.work_v05b(work_id) on update restrict on delete restrict,
  return_work_id uuid references life_runtime.work_v05b(work_id) on update restrict on delete restrict,
  branch_depth integer not null check (branch_depth >= 0),
  branch_kind text not null check (branch_kind in ('ROOT','SPLINTER')),
  work_state text not null check (work_state in ('ACTIVE','DEFERRED','COMPLETED','CANCELLED','SUPERSEDED')),
  source_generation text not null check (pg_catalog.octet_length(pg_catalog.convert_to(source_generation,'UTF8')) > 0),
  contract_generation text not null check (pg_catalog.octet_length(pg_catalog.convert_to(contract_generation,'UTF8')) > 0),
  last_transfer_id uuid,
  next_actor text check (
    next_actor is null or next_actor in ('Vince','Clea','Alexander','Connor','Caden','Claude','Kal')
  ),
  next_action_ref text,
  reactivation_condition_kind text not null default 'NONE'
    check (reactivation_condition_kind in ('NONE','OWNER_DIRECTIVE','DEPENDENCY_STATE','EXACT_EVENT')),
  reactivation_condition_ref jsonb,
  terminal_source_ref text,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint work_v05b_root_shape_ck check (
    branch_kind <> 'ROOT'
    or (branch_depth = 0 and parent_work_id is null and return_work_id is null)
  ),
  constraint work_v05b_splinter_shape_ck check (
    branch_kind <> 'SPLINTER'
    or (branch_depth > 0 and parent_work_id is not null and return_work_id = parent_work_id)
  ),
  constraint work_v05b_deferred_condition_ck check (
    work_state <> 'DEFERRED'
    or (reactivation_condition_kind <> 'NONE' and reactivation_condition_ref is not null)
  ),
  constraint work_v05b_active_condition_ck check (
    work_state <> 'ACTIVE'
    or (reactivation_condition_kind = 'NONE' and reactivation_condition_ref is null)
  )
);

create unique index work_v05b_one_active_root_per_goal_uq
  on life_runtime.work_v05b(root_goal_id)
  where branch_kind = 'ROOT' and work_state = 'ACTIVE';

revoke all on all tables in schema life_runtime from public, anon, authenticated, service_role;

commit;
