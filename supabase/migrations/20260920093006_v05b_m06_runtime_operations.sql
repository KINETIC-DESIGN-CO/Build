begin;

create function life_runtime.get_work_state_v05b(p_work_id uuid)
returns jsonb
language sql
stable
set search_path = ''
as $$
  select pg_catalog.jsonb_build_object(
    'work', pg_catalog.to_jsonb(w),
    'audit', (
      select pg_catalog.to_jsonb(a)
      from life_runtime.audit_status_v05b a
      where a.singleton_id = 1
    ),
    'maintenance', (
      select pg_catalog.to_jsonb(m)
      from life_runtime.maintenance_state_v05b m
      where m.singleton_id = 1
    )
  )
  from life_runtime.work_v05b w
  where w.work_id = p_work_id
$$;

create function life_runtime.perform_transition_v05b(
  p_operation_kind text,
  p_request_id uuid,
  p_work_id uuid,
  p_expected_revision bigint,
  p_target_state text,
  p_next_actor text,
  p_next_action_ref text,
  p_reactivation_kind text,
  p_reactivation_ref jsonb,
  p_source_ref text,
  p_claimed_actor text,
  p_contract_generation text,
  p_evidence_refs text[],
  p_open_finding_refs text[]
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request jsonb;
  v_hash text;
  v_existing life_runtime.operation_receipt_v05b%rowtype;
  v_maintenance life_runtime.maintenance_state_v05b%rowtype;
  v_audit life_runtime.audit_status_v05b%rowtype;
  v_work life_runtime.work_v05b%rowtype;
  v_transfer uuid;
  v_transfer_hash text;
  v_result jsonb;
  v_event bigint;
begin
  v_request := pg_catalog.jsonb_build_object(
    'operation_kind', p_operation_kind,
    'request_id', p_request_id,
    'work_id', p_work_id,
    'expected_revision', p_expected_revision,
    'target_state', p_target_state,
    'next_actor', p_next_actor,
    'next_action_ref', p_next_action_ref,
    'reactivation_kind', p_reactivation_kind,
    'reactivation_ref', p_reactivation_ref,
    'source_ref', p_source_ref,
    'claimed_actor', p_claimed_actor,
    'contract_generation', p_contract_generation,
    'evidence_refs', pg_catalog.coalesce(p_evidence_refs,array[]::text[]),
    'open_finding_refs', pg_catalog.coalesce(p_open_finding_refs,array[]::text[])
  );
  v_hash := life_runtime.json_hash_v05b(v_request);

  select * into v_existing
  from life_runtime.operation_receipt_v05b
  where request_id = p_request_id;

  if found then
    if v_existing.canonical_request_hash = v_hash then
      return v_existing.exact_result_payload || pg_catalog.jsonb_build_object('replayed', true);
    end if;
    return pg_catalog.jsonb_build_object(
      'code','REJECT_MUTATED_RETRY','replayed',false,'request_id',p_request_id
    );
  end if;

  select * into v_maintenance
  from life_runtime.maintenance_state_v05b
  where singleton_id = 1
  for update;

  if not found then
    return pg_catalog.jsonb_build_object('code','RUNTIME_UNAVAILABLE','replayed',false);
  end if;

  select * into v_work
  from life_runtime.work_v05b
  where work_id = p_work_id
  for update;

  if not found then
    return pg_catalog.jsonb_build_object('code','VALIDATION_REJECTED','replayed',false);
  end if;

  select * into v_audit
  from life_runtime.audit_status_v05b
  where singleton_id = 1
  for update;

  if not found then
    return pg_catalog.jsonb_build_object('code','RUNTIME_UNAVAILABLE','replayed',false);
  end if;

  if v_maintenance.state = 'ON' then
    v_result := pg_catalog.jsonb_build_object('code','MAINTENANCE_BLOCKED','replayed',false);
    insert into life_runtime.operation_receipt_v05b(
      request_id,operation_kind,work_id,expected_revision,canonical_request,
      canonical_request_hash,claimed_actor,source_ref,contract_generation,
      exact_result_code,exact_result_payload,expected_audit_event_count
    ) values (
      p_request_id,p_operation_kind,p_work_id,p_expected_revision,v_request,
      v_hash,p_claimed_actor,p_source_ref,p_contract_generation,
      'MAINTENANCE_BLOCKED',v_result,0
    );
    return v_result;
  end if;

  if v_audit.status <> 'PASS' then
    v_result := pg_catalog.jsonb_build_object('code','AUDIT_HOLD','replayed',false);
    insert into life_runtime.operation_receipt_v05b(
      request_id,operation_kind,work_id,expected_revision,canonical_request,
      canonical_request_hash,claimed_actor,source_ref,contract_generation,
      exact_result_code,exact_result_payload,expected_audit_event_count
    ) values (
      p_request_id,p_operation_kind,p_work_id,p_expected_revision,v_request,
      v_hash,p_claimed_actor,p_source_ref,p_contract_generation,
      'AUDIT_HOLD',v_result,0
    );
    return v_result;
  end if;

  if not life_runtime.runtime_catalog_guard_v05b() then
    v_event := life_runtime.append_audit_event_v05b(
      'DDL_CHANGE','CATALOG_GUARD','life_runtime.runtime_catalog_manifest_v05b',
      null,null,null,p_claimed_actor,null,'RUNTIME_CATALOG_GUARD',p_source_ref,
      p_contract_generation,'OUT_OF_PATH',null,null,'CATALOG','catalog_guard',
      pg_catalog.jsonb_build_object('result','MISMATCH')
    );
    if v_event is not null then
      perform life_runtime.open_blocking_flag_v05b(
        v_event,'CATALOG_MISMATCH',null,array['runtime_catalog_guard_v05b']
      );
    end if;
    v_result := pg_catalog.jsonb_build_object('code','AUDIT_HOLD','reason','CATALOG_MISMATCH','replayed',false);
    insert into life_runtime.operation_receipt_v05b(
      request_id,operation_kind,work_id,expected_revision,canonical_request,
      canonical_request_hash,claimed_actor,source_ref,contract_generation,
      exact_result_code,exact_result_payload,expected_audit_event_count
    ) values (
      p_request_id,p_operation_kind,p_work_id,p_expected_revision,v_request,
      v_hash,p_claimed_actor,p_source_ref,p_contract_generation,
      'AUDIT_HOLD',v_result,0
    );
    return v_result;
  end if;

  if v_work.revision <> p_expected_revision then
    v_result := pg_catalog.jsonb_build_object(
      'code','STALE_REVISION','current_revision',v_work.revision,'replayed',false
    );
    insert into life_runtime.operation_receipt_v05b(
      request_id,operation_kind,work_id,expected_revision,canonical_request,
      canonical_request_hash,claimed_actor,source_ref,contract_generation,
      exact_result_code,exact_result_payload,committed_work_revision,
      expected_audit_event_count
    ) values (
      p_request_id,p_operation_kind,p_work_id,p_expected_revision,v_request,
      v_hash,p_claimed_actor,p_source_ref,p_contract_generation,
      'STALE_REVISION',v_result,v_work.revision,0
    );
    return v_result;
  end if;

  if p_operation_kind = 'DEFER_WORK' then
    if v_work.work_state <> 'ACTIVE'
       or p_target_state <> 'DEFERRED'
       or p_reactivation_kind = 'NONE'
       or p_reactivation_ref is null then
      v_result := pg_catalog.jsonb_build_object('code','VALIDATION_REJECTED','replayed',false);
      insert into life_runtime.operation_receipt_v05b(
        request_id,operation_kind,work_id,expected_revision,canonical_request,
        canonical_request_hash,claimed_actor,source_ref,contract_generation,
        exact_result_code,exact_result_payload,expected_audit_event_count
      ) values (
        p_request_id,p_operation_kind,p_work_id,p_expected_revision,v_request,
        v_hash,p_claimed_actor,p_source_ref,p_contract_generation,
        'VALIDATION_REJECTED',v_result,0
      );
      return v_result;
    end if;
  elsif p_operation_kind = 'REACTIVATE_WORK' then
    if v_work.work_state <> 'DEFERRED'
       or not life_runtime.evaluate_reactivation_v05b(
         v_work.reactivation_condition_kind,v_work.reactivation_condition_ref
       ) then
      v_result := pg_catalog.jsonb_build_object('code','REACTIVATION_CONDITION_FALSE','replayed',false);
      insert into life_runtime.operation_receipt_v05b(
        request_id,operation_kind,work_id,expected_revision,canonical_request,
        canonical_request_hash,claimed_actor,source_ref,contract_generation,
        exact_result_code,exact_result_payload,expected_audit_event_count
      ) values (
        p_request_id,p_operation_kind,p_work_id,p_expected_revision,v_request,
        v_hash,p_claimed_actor,p_source_ref,p_contract_generation,
        'REACTIVATION_CONDITION_FALSE',v_result,0
      );
      return v_result;
    end if;
  elsif p_operation_kind = 'CLOSE_WORK' then
    if p_target_state not in ('COMPLETED','CANCELLED','SUPERSEDED') then
      v_result := pg_catalog.jsonb_build_object('code','VALIDATION_REJECTED','replayed',false);
      insert into life_runtime.operation_receipt_v05b(
        request_id,operation_kind,work_id,expected_revision,canonical_request,
        canonical_request_hash,claimed_actor,source_ref,contract_generation,
        exact_result_code,exact_result_payload,expected_audit_event_count
      ) values (
        p_request_id,p_operation_kind,p_work_id,p_expected_revision,v_request,
        v_hash,p_claimed_actor,p_source_ref,p_contract_generation,
        'VALIDATION_REJECTED',v_result,0
      );
      return v_result;
    end if;
  end if;

  if p_target_state not in ('ACTIVE','DEFERRED','COMPLETED','CANCELLED','SUPERSEDED') then
    v_result := pg_catalog.jsonb_build_object('code','VALIDATION_REJECTED','replayed',false);
    insert into life_runtime.operation_receipt_v05b(
      request_id,operation_kind,work_id,expected_revision,canonical_request,
      canonical_request_hash,claimed_actor,source_ref,contract_generation,
      exact_result_code,exact_result_payload,expected_audit_event_count
    ) values (
      p_request_id,p_operation_kind,p_work_id,p_expected_revision,v_request,
      v_hash,p_claimed_actor,p_source_ref,p_contract_generation,
      'VALIDATION_REJECTED',v_result,0
    );
    return v_result;
  end if;

  v_transfer := pg_catalog.gen_random_uuid();
  v_transfer_hash := life_runtime.json_hash_v05b(
    pg_catalog.jsonb_build_object(
      'work_id',p_work_id,
      'expected_revision',p_expected_revision,
      'resulting_revision',v_work.revision + 1,
      'root_goal_id',v_work.root_goal_id,
      'root_goal_revision_at_transfer',v_work.root_goal_revision_at_transfer,
      'parent_work_id',v_work.parent_work_id,
      'return_work_id',v_work.return_work_id,
      'branch_depth',v_work.branch_depth,
      'branch_kind',v_work.branch_kind,
      'resulting_work_state',p_target_state,
      'evidence_refs',pg_catalog.coalesce(p_evidence_refs,array[]::text[]),
      'open_finding_refs',pg_catalog.coalesce(p_open_finding_refs,array[]::text[]),
      'next_actor',p_next_actor,
      'next_action_ref',p_next_action_ref,
      'reactivation_condition_kind',
        case when p_operation_kind='REACTIVATE_WORK' then 'NONE' else p_reactivation_kind end,
      'reactivation_condition_ref',
        case when p_operation_kind='REACTIVATE_WORK' then null else p_reactivation_ref end,
      'source_generation',v_work.source_generation,
      'contract_generation',p_contract_generation
    )
  );

  v_result := pg_catalog.jsonb_build_object(
    'code','APPLIED',
    'work_id',p_work_id,
    'committed_revision',v_work.revision + 1,
    'transfer_id',v_transfer,
    'replayed',false
  );

  insert into life_runtime.operation_receipt_v05b(
    request_id,operation_kind,work_id,expected_revision,canonical_request,
    canonical_request_hash,claimed_actor,source_ref,contract_generation,
    exact_result_code,exact_result_payload,committed_work_revision,transfer_id,
    expected_audit_event_count
  ) values (
    p_request_id,p_operation_kind,p_work_id,p_expected_revision,v_request,
    v_hash,p_claimed_actor,p_source_ref,p_contract_generation,
    'APPLIED',v_result,v_work.revision + 1,v_transfer,1
  );

  perform pg_catalog.set_config('life_runtime.request_id',p_request_id::text,true);
  perform pg_catalog.set_config('life_runtime.operation_kind',p_operation_kind,true);
  perform pg_catalog.set_config('life_runtime.claimed_actor',p_claimed_actor,true);
  perform pg_catalog.set_config('life_runtime.source_ref',p_source_ref,true);
  perform pg_catalog.set_config('life_runtime.contract_generation',p_contract_generation,true);

  insert into life_runtime.transference_event_v05b(
    transfer_id,request_id,transfer_state_id,work_id,expected_revision,
    resulting_revision,predecessor_transfer_id,root_goal_id,
    root_goal_revision_at_transfer,parent_work_id,return_work_id,branch_depth,
    branch_kind,resulting_work_state,evidence_refs,open_finding_refs,next_actor,
    next_action_ref,reactivation_condition_kind,reactivation_condition_ref,
    source_generation,contract_generation
  ) values (
    v_transfer,p_request_id,v_transfer_hash,p_work_id,p_expected_revision,
    v_work.revision + 1,v_work.last_transfer_id,v_work.root_goal_id,
    v_work.root_goal_revision_at_transfer,v_work.parent_work_id,v_work.return_work_id,
    v_work.branch_depth,v_work.branch_kind,p_target_state,
    pg_catalog.coalesce(p_evidence_refs,array[]::text[]),
    pg_catalog.coalesce(p_open_finding_refs,array[]::text[]),
    p_next_actor,p_next_action_ref,
    case when p_operation_kind='REACTIVATE_WORK' then 'NONE' else p_reactivation_kind end,
    case when p_operation_kind='REACTIVATE_WORK' then null else p_reactivation_ref end,
    v_work.source_generation,p_contract_generation
  );

  update life_runtime.work_v05b
  set revision = revision + 1,
      work_state = p_target_state,
      last_transfer_id = v_transfer,
      next_actor = p_next_actor,
      next_action_ref = p_next_action_ref,
      reactivation_condition_kind =
        case when p_operation_kind='REACTIVATE_WORK' then 'NONE' else p_reactivation_kind end,
      reactivation_condition_ref =
        case when p_operation_kind='REACTIVATE_WORK' then null else p_reactivation_ref end,
      terminal_source_ref =
        case when p_target_state in ('COMPLETED','CANCELLED','SUPERSEDED') then p_source_ref else terminal_source_ref end,
      contract_generation = p_contract_generation,
      updated_at = pg_catalog.clock_timestamp()
  where work_id = p_work_id;

  return v_result;
end
$$;

create function life_runtime.apply_transference_v05b(
  p_request_id uuid,
  p_work_id uuid,
  p_expected_revision bigint,
  p_transfer jsonb,
  p_claimed_actor text,
  p_source_ref text,
  p_contract_generation text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
  return life_runtime.perform_transition_v05b(
    'APPLY_TRANSFERENCE',p_request_id,p_work_id,p_expected_revision,
    p_transfer ->> 'resulting_work_state',
    p_transfer ->> 'next_actor',
    p_transfer ->> 'next_action_ref',
    pg_catalog.coalesce(p_transfer ->> 'reactivation_condition_kind','NONE'),
    p_transfer -> 'reactivation_condition_ref',
    p_source_ref,p_claimed_actor,p_contract_generation,
    coalesce(array(select pg_catalog.jsonb_array_elements_text(coalesce(p_transfer->'evidence_refs','[]'::jsonb))),array[]::text[]),
    coalesce(array(select pg_catalog.jsonb_array_elements_text(coalesce(p_transfer->'open_finding_refs','[]'::jsonb))),array[]::text[])
  );
end
$$;

create function life_runtime.defer_work_v05b(
  p_request_id uuid,
  p_work_id uuid,
  p_expected_revision bigint,
  p_condition_kind text,
  p_condition_ref jsonb,
  p_next_actor text,
  p_next_action_ref text,
  p_claimed_actor text,
  p_source_ref text,
  p_contract_generation text
)
returns jsonb
language sql
security definer
set search_path = ''
as $$
  select life_runtime.perform_transition_v05b(
    'DEFER_WORK',p_request_id,p_work_id,p_expected_revision,'DEFERRED',
    p_next_actor,p_next_action_ref,p_condition_kind,p_condition_ref,
    p_source_ref,p_claimed_actor,p_contract_generation,array[]::text[],array[]::text[]
  )
$$;

create function life_runtime.reactivate_work_v05b(
  p_request_id uuid,
  p_work_id uuid,
  p_expected_revision bigint,
  p_next_actor text,
  p_next_action_ref text,
  p_claimed_actor text,
  p_source_ref text,
  p_contract_generation text
)
returns jsonb
language sql
security definer
set search_path = ''
as $$
  select life_runtime.perform_transition_v05b(
    'REACTIVATE_WORK',p_request_id,p_work_id,p_expected_revision,'ACTIVE',
    p_next_actor,p_next_action_ref,'NONE',null,
    p_source_ref,p_claimed_actor,p_contract_generation,array[]::text[],array[]::text[]
  )
$$;

create function life_runtime.close_work_v05b(
  p_request_id uuid,
  p_work_id uuid,
  p_expected_revision bigint,
  p_terminal_state text,
  p_claimed_actor text,
  p_source_ref text,
  p_contract_generation text
)
returns jsonb
language sql
security definer
set search_path = ''
as $$
  select life_runtime.perform_transition_v05b(
    'CLOSE_WORK',p_request_id,p_work_id,p_expected_revision,p_terminal_state,
    null,null,'NONE',null,p_source_ref,p_claimed_actor,p_contract_generation,
    array[]::text[],array[]::text[]
  )
$$;

create function life_runtime.apply_owner_decision_v05b(
  p_request_id uuid,
  p_work_id uuid,
  p_expected_revision bigint,
  p_source_type text,
  p_source_ref text,
  p_canonical_action jsonb,
  p_claimed_actor text,
  p_contract_generation text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request jsonb;
  v_hash text;
  v_work life_runtime.work_v05b%rowtype;
  v_m life_runtime.maintenance_state_v05b%rowtype;
  v_a life_runtime.audit_status_v05b%rowtype;
  v_result jsonb;
begin
  v_request := pg_catalog.jsonb_build_object(
    'operation_kind','APPLY_OWNER_DECISION','request_id',p_request_id,
    'work_id',p_work_id,'expected_revision',p_expected_revision,
    'source_type',p_source_type,'source_ref',p_source_ref,
    'canonical_action',p_canonical_action,'claimed_actor',p_claimed_actor,
    'contract_generation',p_contract_generation
  );
  v_hash := life_runtime.json_hash_v05b(v_request);

  if exists (select 1 from life_runtime.operation_receipt_v05b where request_id=p_request_id) then
    return (
      select case
        when canonical_request_hash=v_hash
        then exact_result_payload || pg_catalog.jsonb_build_object('replayed',true)
        else pg_catalog.jsonb_build_object('code','REJECT_MUTATED_RETRY','replayed',false)
      end
      from life_runtime.operation_receipt_v05b where request_id=p_request_id
    );
  end if;

  select * into v_m from life_runtime.maintenance_state_v05b where singleton_id=1 for update;
  select * into v_work from life_runtime.work_v05b where work_id=p_work_id for update;
  if not found then
    return pg_catalog.jsonb_build_object('code','VALIDATION_REJECTED','replayed',false);
  end if;
  select * into v_a from life_runtime.audit_status_v05b where singleton_id=1 for update;

  if v_m.state='ON' then
    v_result := pg_catalog.jsonb_build_object('code','MAINTENANCE_BLOCKED','replayed',false);
  elsif v_a.status<>'PASS' or not life_runtime.runtime_catalog_guard_v05b() then
    v_result := pg_catalog.jsonb_build_object('code','AUDIT_HOLD','replayed',false);
  elsif v_work.revision<>p_expected_revision then
    v_result := pg_catalog.jsonb_build_object('code','STALE_REVISION','current_revision',v_work.revision,'replayed',false);
  else
    v_result := pg_catalog.jsonb_build_object('code','APPLIED','replayed',false);
  end if;

  insert into life_runtime.operation_receipt_v05b(
    request_id,operation_kind,work_id,expected_revision,canonical_request,
    canonical_request_hash,claimed_actor,source_ref,contract_generation,
    exact_result_code,exact_result_payload,committed_work_revision,
    expected_audit_event_count
  ) values (
    p_request_id,'APPLY_OWNER_DECISION',p_work_id,p_expected_revision,v_request,
    v_hash,p_claimed_actor,p_source_ref,p_contract_generation,
    v_result->>'code',v_result,v_work.revision,0
  );

  if v_result->>'code'='APPLIED' then
    insert into life_runtime.owner_ingress_audit_v05b(
      claimed_owner,source_type,source_ref,canonical_action,
      canonical_action_hash,consuming_request_id
    ) values (
      'Vince',p_source_type,p_source_ref,p_canonical_action,
      life_runtime.json_hash_v05b(p_canonical_action),p_request_id
    );
  end if;

  return v_result;
end
$$;

create function life_runtime.kick_return_v05b(
  p_request_id uuid,
  p_work_id uuid,
  p_expected_revision bigint,
  p_claimed_actor text,
  p_source_ref text,
  p_contract_generation text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_m life_runtime.maintenance_state_v05b%rowtype;
  v_a life_runtime.audit_status_v05b%rowtype;
  v_origin life_runtime.work_v05b%rowtype;
  v_candidate life_runtime.work_v05b%rowtype;
  v_candidate_id uuid;
  v_request jsonb;
  v_hash text;
  v_result jsonb;
  v_index_ok boolean;
  v_count integer;
begin
  v_request := pg_catalog.jsonb_build_object(
    'operation_kind','KICK_RETURN','request_id',p_request_id,'work_id',p_work_id,
    'expected_revision',p_expected_revision,'claimed_actor',p_claimed_actor,
    'source_ref',p_source_ref,'contract_generation',p_contract_generation
  );
  v_hash := life_runtime.json_hash_v05b(v_request);

  if exists (select 1 from life_runtime.operation_receipt_v05b where request_id=p_request_id) then
    return (
      select case
        when canonical_request_hash=v_hash
        then exact_result_payload || pg_catalog.jsonb_build_object('replayed',true)
        else pg_catalog.jsonb_build_object('code','REJECT_MUTATED_RETRY','replayed',false)
      end
      from life_runtime.operation_receipt_v05b where request_id=p_request_id
    );
  end if;

  select * into v_m from life_runtime.maintenance_state_v05b where singleton_id=1 for update;
  select * into v_origin from life_runtime.work_v05b where work_id=p_work_id for update;
  if not found then
    return pg_catalog.jsonb_build_object('code','VALIDATION_REJECTED','replayed',false);
  end if;

  v_candidate_id := v_origin.return_work_id;
  while v_candidate_id is not null loop
    select * into v_candidate
    from life_runtime.work_v05b
    where work_id=v_candidate_id
    for update;
    if not found then
      return pg_catalog.jsonb_build_object('code','VALIDATION_REJECTED','reason','CORRUPT_ANCESTRY','replayed',false);
    end if;
    if v_candidate.work_state='ACTIVE'
       or (v_candidate.work_state='DEFERRED'
           and life_runtime.evaluate_reactivation_v05b(
             v_candidate.reactivation_condition_kind,v_candidate.reactivation_condition_ref
           )) then
      exit;
    end if;
    v_candidate_id := v_candidate.return_work_id;
  end loop;

  if v_candidate_id is null then
    select exists (
      select 1
      from pg_catalog.pg_index i
      join pg_catalog.pg_class idx on idx.oid=i.indexrelid
      join pg_catalog.pg_namespace n on n.oid=idx.relnamespace
      where n.nspname='life_runtime'
        and idx.relname='work_v05b_one_active_root_per_goal_uq'
        and i.indisunique and i.indisvalid and i.indisready
        and pg_catalog.pg_get_indexdef(i.indexrelid) like '%(root_goal_id)%'
        and pg_catalog.pg_get_expr(i.indpred,i.indrelid)
          = '((branch_kind = ''ROOT''::text) AND (work_state = ''ACTIVE''::text))'
    ) into v_index_ok;

    if v_index_ok then
      select pg_catalog.count(*)::integer into v_count
      from life_runtime.work_v05b
      where root_goal_id=v_origin.root_goal_id
        and branch_kind='ROOT'
        and work_state='ACTIVE';

      if v_count=1 then
        select * into v_candidate
        from life_runtime.work_v05b
        where root_goal_id=v_origin.root_goal_id
          and branch_kind='ROOT'
          and work_state='ACTIVE'
        for update;
        v_candidate_id := v_candidate.work_id;
      end if;
    else
      v_count := -1;
    end if;
  end if;

  select * into v_a from life_runtime.audit_status_v05b where singleton_id=1 for update;

  if v_m.state='ON' then
    v_result := pg_catalog.jsonb_build_object('code','MAINTENANCE_BLOCKED','replayed',false);
  elsif v_a.status<>'PASS' then
    v_result := pg_catalog.jsonb_build_object('code','AUDIT_HOLD','replayed',false);
  elsif not life_runtime.runtime_catalog_guard_v05b() or v_count=-1 then
    v_result := pg_catalog.jsonb_build_object('code','AUDIT_HOLD','reason','CATALOG_MISMATCH','replayed',false);
  elsif v_origin.revision<>p_expected_revision then
    v_result := pg_catalog.jsonb_build_object('code','STALE_REVISION','current_revision',v_origin.revision,'replayed',false);
  elsif v_candidate_id is null then
    v_result := pg_catalog.jsonb_build_object('code','BLOCKED_NO_RESUMABLE_RETURN','replayed',false);
  else
    v_result := pg_catalog.jsonb_build_object(
      'code','APPLIED','candidate_work_id',v_candidate_id,
      'candidate_revision',v_candidate.revision + 1,'replayed',false
    );
  end if;

  insert into life_runtime.operation_receipt_v05b(
    request_id,operation_kind,work_id,expected_revision,canonical_request,
    canonical_request_hash,claimed_actor,source_ref,contract_generation,
    exact_result_code,exact_result_payload,committed_work_revision,
    expected_audit_event_count
  ) values (
    p_request_id,'KICK_RETURN',p_work_id,p_expected_revision,v_request,v_hash,
    p_claimed_actor,p_source_ref,p_contract_generation,
    case when v_result->>'code'='AUDIT_HOLD' then 'AUDIT_HOLD' else v_result->>'code' end,
    v_result,
    case when v_result->>'code'='APPLIED' then v_candidate.revision+1 else v_origin.revision end,
    case when v_result->>'code'='APPLIED' then 1 else 0 end
  );

  if v_result->>'code'='APPLIED' then
    perform pg_catalog.set_config('life_runtime.request_id',p_request_id::text,true);
    perform pg_catalog.set_config('life_runtime.operation_kind','KICK_RETURN',true);
    perform pg_catalog.set_config('life_runtime.claimed_actor',p_claimed_actor,true);
    perform pg_catalog.set_config('life_runtime.source_ref',p_source_ref,true);
    perform pg_catalog.set_config('life_runtime.contract_generation',p_contract_generation,true);

    update life_runtime.work_v05b
    set revision=revision+1,
        work_state='ACTIVE',
        reactivation_condition_kind='NONE',
        reactivation_condition_ref=null,
        updated_at=pg_catalog.clock_timestamp()
    where work_id=v_candidate_id;
  end if;

  return v_result;
end
$$;

create function life_runtime.enter_maintenance_v05b(
  p_change_id text,
  p_source_ref text,
  p_claimed_actor text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_m life_runtime.maintenance_state_v05b%rowtype;
  v_a life_runtime.audit_status_v05b%rowtype;
  v_before bigint;
  v_after bigint;
begin
  select * into v_m from life_runtime.maintenance_state_v05b where singleton_id=1 for update;
  select * into v_a from life_runtime.audit_status_v05b where singleton_id=1 for update;
  if v_m.state='ON' then
    return pg_catalog.jsonb_build_object('code','APPLIED','maintenance_epoch',v_m.maintenance_epoch,'already_on',true);
  end if;
  v_before:=v_m.maintenance_epoch;
  v_after:=v_before+1;
  update life_runtime.maintenance_state_v05b
  set state='ON',change_id=p_change_id,source_ref=p_source_ref,
      claimed_actor=p_claimed_actor,entered_at=pg_catalog.clock_timestamp(),
      maintenance_epoch=v_after
  where singleton_id=1;
  insert into life_runtime.maintenance_receipt_v05b(
    change_id,action,source_ref,claimed_actor,maintenance_epoch_before,
    maintenance_epoch_after,audit_head_event_id_before,audit_head_event_id_after
  ) values (
    p_change_id,'ENTER',p_source_ref,p_claimed_actor,v_before,v_after,
    v_a.audit_head_event_id,v_a.audit_head_event_id
  );
  return pg_catalog.jsonb_build_object('code','APPLIED','maintenance_epoch',v_after);
end
$$;

create function life_runtime.full_audit_verify_v05b()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_m life_runtime.maintenance_state_v05b%rowtype;
  v_a life_runtime.audit_status_v05b%rowtype;
  v_prev text;
  v_from_id bigint;
  v_events integer:=0;
  v_receipts integer:=0;
  v_blocking integer:=0;
  v_mismatch text[]:=array[]::text[];
  v_calc text;
  v_payload jsonb;
  r life_runtime.audit_event_v05b%rowtype;
  v_result text;
  v_epoch bigint;
  v_bad integer;
begin
  select * into v_m from life_runtime.maintenance_state_v05b where singleton_id=1 for update;
  select * into v_a from life_runtime.audit_status_v05b where singleton_id=1 for update;

  if not found or v_m.state<>'ON' then
    return pg_catalog.jsonb_build_object('result','UNVERIFIED','reason','MAINTENANCE_REQUIRED');
  end if;

  v_prev:=v_a.last_full_verified_hash;
  v_from_id:=v_a.last_full_verified_event_id;

  for r in
    select * from life_runtime.audit_event_v05b
    where audit_event_id > coalesce(v_from_id,0)
      and (v_a.audit_head_event_id is null or audit_event_id <= v_a.audit_head_event_id)
    order by audit_event_id
  loop
    v_events:=v_events+1;
    v_payload:=pg_catalog.jsonb_build_object(
      'event_kind',r.event_kind,'transaction_id',r.transaction_id,
      'operation_kind',r.operation_kind,'object_identity',r.object_identity,
      'primary_key',r.primary_key,'old_state_hash',r.old_state_hash,
      'new_state_hash',r.new_state_hash,'database_principal',r.database_principal,
      'claimed_life_actor',r.claimed_life_actor,'request_id',r.request_id,
      'runtime_function_context',r.runtime_function_context,'source_ref',r.source_ref,
      'contract_generation',r.contract_generation,'path_class',r.path_class,
      'maintenance_change_id',r.maintenance_change_id,'command_tag',r.command_tag,
      'ddl_object_type',r.ddl_object_type,'ddl_object_identity',r.ddl_object_identity,
      'event_payload',r.event_payload,'occurred_at',r.occurred_at,
      'previous_audit_hash',r.previous_audit_hash
    );
    v_calc:=life_runtime.json_hash_v05b(v_payload);
    if r.previous_audit_hash is distinct from v_prev
       or r.audit_event_hash is distinct from v_calc then
      v_mismatch:=pg_catalog.array_append(v_mismatch,'AUDIT_HASH:'||r.audit_event_id::text);
    end if;
    if r.path_class='APPROVED_RUNTIME_PATH' then
      if r.request_id is null
         or not exists (
           select 1 from life_runtime.operation_receipt_v05b o
           where o.request_id=r.request_id
         ) then
        v_mismatch:=pg_catalog.array_append(v_mismatch,'RECEIPT_MISSING:'||r.audit_event_id::text);
      else
        v_receipts:=v_receipts+1;
      end if;
    end if;
    v_prev:=r.audit_event_hash;
  end loop;

  select pg_catalog.count(*)::integer into v_bad
  from life_runtime.work_v05b w
  where
    (w.branch_kind='ROOT' and not (w.branch_depth=0 and w.parent_work_id is null and w.return_work_id is null))
    or
    (w.branch_kind='SPLINTER' and not (
      w.branch_depth>0 and w.parent_work_id is not null and w.return_work_id=w.parent_work_id
      and exists (select 1 from life_runtime.work_v05b p where p.work_id=w.parent_work_id)
    ))
    or
    (w.parent_work_id is not null and not exists (
      select 1 from life_runtime.work_v05b p where p.work_id=w.parent_work_id
    ))
    or
    (w.return_work_id is not null and not exists (
      select 1 from life_runtime.work_v05b p where p.work_id=w.return_work_id
    ));
  if v_bad>0 then
    v_mismatch:=pg_catalog.array_append(v_mismatch,'WORK_ANCESTRY:'||v_bad::text);
  end if;

  select pg_catalog.count(*)::integer into v_bad
  from life_runtime.operation_receipt_v05b o
  where not exists (select 1 from life_runtime.work_v05b w where w.work_id=o.work_id);
  if v_bad>0 then
    v_mismatch:=pg_catalog.array_append(v_mismatch,'OP_WORK_REF:'||v_bad::text);
  end if;

  select pg_catalog.count(*)::integer into v_bad
  from life_runtime.transference_event_v05b t
  where not exists (select 1 from life_runtime.operation_receipt_v05b o where o.request_id=t.request_id)
     or not exists (select 1 from life_runtime.work_v05b w where w.work_id=t.work_id);
  if v_bad>0 then
    v_mismatch:=pg_catalog.array_append(v_mismatch,'TRANSFER_REF:'||v_bad::text);
  end if;

  select pg_catalog.count(*)::integer into v_bad
  from life_runtime.operation_receipt_v05b o
  where o.exact_result_code='APPLIED'
    and o.expected_audit_event_count>0
    and (
      select pg_catalog.count(*)
      from life_runtime.audit_event_v05b e
      where e.request_id=o.request_id
    ) <> o.expected_audit_event_count;
  if v_bad>0 then
    v_mismatch:=pg_catalog.array_append(v_mismatch,'RECEIPT_EVENT_COUNT:'||v_bad::text);
  end if;

  select pg_catalog.count(*)::integer into v_blocking
  from life_runtime.audit_flag_v05b
  where state in ('OPEN','ESCALATED');

  if pg_catalog.array_length(v_mismatch,1) is not null or v_blocking>0 then
    v_result:='FLAGGED';
  else
    v_result:='PASS';
  end if;

  update life_runtime.audit_status_v05b
  set status=v_result,
      open_flag_count=v_blocking,
      last_full_verified_event_id=case when v_result='PASS' then v_a.audit_head_event_id else last_full_verified_event_id end,
      last_full_verified_hash=case when v_result='PASS' then v_a.audit_head_hash else last_full_verified_hash end,
      last_full_verification_at=case when v_result='PASS' then pg_catalog.clock_timestamp() else last_full_verification_at end,
      status_epoch=status_epoch+1
  where singleton_id=1
  returning status_epoch into v_epoch;

  insert into life_runtime.audit_verification_receipt_v05b(
    from_event_id,from_hash,fixed_target_head_event_id,fixed_target_head_hash,
    result,events_checked,receipts_checked,flags_open_or_escalated,
    mismatch_refs,resulting_status_epoch
  ) values (
    v_from_id,v_a.last_full_verified_hash,v_a.audit_head_event_id,v_a.audit_head_hash,
    v_result,v_events,v_receipts,v_blocking,v_mismatch,v_epoch
  );

  return pg_catalog.jsonb_build_object(
    'result',v_result,'events_checked',v_events,'receipts_checked',v_receipts,
    'flags_open_or_escalated',v_blocking,'mismatch_refs',v_mismatch
  );
end
$$;

create function life_runtime.exit_maintenance_v05b(
  p_change_id text,
  p_source_ref text,
  p_claimed_actor text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_m life_runtime.maintenance_state_v05b%rowtype;
  v_a life_runtime.audit_status_v05b%rowtype;
  v_verify jsonb;
begin
  select * into v_m from life_runtime.maintenance_state_v05b where singleton_id=1 for update;
  if v_m.state<>'ON' or v_m.change_id is distinct from p_change_id then
    return pg_catalog.jsonb_build_object('code','VALIDATION_REJECTED');
  end if;

  v_verify:=life_runtime.full_audit_verify_v05b();
  if v_verify->>'result'<>'PASS' then
    return pg_catalog.jsonb_build_object('code','AUDIT_HOLD','verification',v_verify);
  end if;

  select * into v_a from life_runtime.audit_status_v05b where singleton_id=1 for update;
  insert into life_runtime.maintenance_receipt_v05b(
    change_id,action,source_ref,claimed_actor,maintenance_epoch_before,
    maintenance_epoch_after,audit_head_event_id_before,audit_head_event_id_after
  ) values (
    p_change_id,'EXIT',p_source_ref,p_claimed_actor,v_m.maintenance_epoch,
    v_m.maintenance_epoch,v_a.audit_head_event_id,v_a.audit_head_event_id
  );

  update life_runtime.maintenance_state_v05b
  set state='OFF',change_id=null,source_ref=null,claimed_actor=null,entered_at=null
  where singleton_id=1;

  return pg_catalog.jsonb_build_object('code','APPLIED','maintenance_epoch',v_m.maintenance_epoch);
end
$$;

create function life_runtime.clear_audit_flag_v05b(
  p_flag_id uuid,
  p_disposition text,
  p_change_id text,
  p_evidence_refs text[],
  p_reviewer_name text,
  p_reviewer_source_ref text,
  p_claimed_clearing_actor text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_m life_runtime.maintenance_state_v05b%rowtype;
  v_f life_runtime.audit_flag_v05b%rowtype;
  v_a life_runtime.audit_status_v05b%rowtype;
  v_new text;
  v_request uuid:=pg_catalog.gen_random_uuid();
  v_count integer;
begin
  select * into v_m from life_runtime.maintenance_state_v05b where singleton_id=1 for update;
  if v_m.state<>'ON' then
    return pg_catalog.jsonb_build_object('code','MAINTENANCE_BLOCKED');
  end if;
  select * into v_f from life_runtime.audit_flag_v05b where flag_id=p_flag_id for update;
  if not found or v_f.state<>'OPEN' then
    return pg_catalog.jsonb_build_object('code','VALIDATION_REJECTED');
  end if;
  select * into v_a from life_runtime.audit_status_v05b where singleton_id=1 for update;

  if p_disposition not in ('ACCIDENTAL','AUTHORIZED_MAINTENANCE','UNEXPLAINED')
     or p_reviewer_name not in ('Connor','Claude')
     or p_reviewer_source_ref is null then
    return pg_catalog.jsonb_build_object('code','VALIDATION_REJECTED');
  end if;

  if p_disposition='UNEXPLAINED' then
    v_new:='ESCALATED';
    update life_runtime.audit_flag_v05b
    set state='ESCALATED',escalated_at=pg_catalog.clock_timestamp()
    where flag_id=p_flag_id;
  else
    if p_disposition='AUTHORIZED_MAINTENANCE'
       and (p_change_id is null or p_change_id is distinct from v_m.change_id) then
      return pg_catalog.jsonb_build_object('code','VALIDATION_REJECTED');
    end if;
    v_new:='CLEARED';
    update life_runtime.audit_flag_v05b
    set state='CLEARED',cleared_at=pg_catalog.clock_timestamp()
    where flag_id=p_flag_id;
  end if;

  insert into life_runtime.audit_clear_receipt_v05b(
    flag_id,disposition,change_id,evidence_refs,reviewer_name,reviewer_source_ref,
    clearing_database_principal,claimed_clearing_actor,owner_ingress_id,
    old_flag_state,new_flag_state,audit_head_event_id,audit_head_hash,
    clearing_operation_request_id
  ) values (
    p_flag_id,p_disposition,p_change_id,pg_catalog.coalesce(p_evidence_refs,array[]::text[]),
    p_reviewer_name,p_reviewer_source_ref,current_user,p_claimed_clearing_actor,null,
    'OPEN',v_new,v_a.audit_head_event_id,v_a.audit_head_hash,v_request
  );

  select pg_catalog.count(*)::integer into v_count
  from life_runtime.audit_flag_v05b where state in ('OPEN','ESCALATED');
  update life_runtime.audit_status_v05b
  set status='FLAGGED',open_flag_count=v_count,status_epoch=status_epoch+1
  where singleton_id=1;

  return pg_catalog.jsonb_build_object('code','APPLIED','new_flag_state',v_new);
end
$$;

create function life_runtime.resolve_escalated_flag_v05b(
  p_flag_id uuid,
  p_owner_ingress_id uuid,
  p_disposition text,
  p_claimed_clearing_actor text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_m life_runtime.maintenance_state_v05b%rowtype;
  v_f life_runtime.audit_flag_v05b%rowtype;
  v_a life_runtime.audit_status_v05b%rowtype;
  v_owner life_runtime.owner_ingress_audit_v05b%rowtype;
  v_request uuid:=pg_catalog.gen_random_uuid();
  v_count integer;
begin
  select * into v_m from life_runtime.maintenance_state_v05b where singleton_id=1 for update;
  if v_m.state<>'ON' then
    return pg_catalog.jsonb_build_object('code','MAINTENANCE_BLOCKED');
  end if;
  select * into v_f from life_runtime.audit_flag_v05b where flag_id=p_flag_id for update;
  if not found or v_f.state<>'ESCALATED' or p_disposition<>'OWNER_CLEAR' then
    return pg_catalog.jsonb_build_object('code','VALIDATION_REJECTED');
  end if;
  select * into v_a from life_runtime.audit_status_v05b where singleton_id=1 for update;
  select * into v_owner
  from life_runtime.owner_ingress_audit_v05b
  where owner_ingress_id=p_owner_ingress_id
  for share;

  if not found
     or v_owner.claimed_owner<>'Vince'
     or v_owner.canonical_action->>'operation'<>'RESOLVE_ESCALATED_FLAG'
     or v_owner.canonical_action->>'flag_id'<>p_flag_id::text
     or v_owner.canonical_action->>'disposition'<>'OWNER_CLEAR' then
    return pg_catalog.jsonb_build_object('code','OWNER_SOURCE_MISMATCH');
  end if;

  update life_runtime.audit_flag_v05b
  set state='CLEARED',cleared_at=pg_catalog.clock_timestamp()
  where flag_id=p_flag_id;

  insert into life_runtime.audit_clear_receipt_v05b(
    flag_id,disposition,change_id,evidence_refs,reviewer_name,reviewer_source_ref,
    clearing_database_principal,claimed_clearing_actor,owner_ingress_id,
    old_flag_state,new_flag_state,audit_head_event_id,audit_head_hash,
    clearing_operation_request_id
  ) values (
    p_flag_id,'OWNER_RESOLVED',null,array[]::text[],null,null,current_user,
    p_claimed_clearing_actor,p_owner_ingress_id,'ESCALATED','CLEARED',
    v_a.audit_head_event_id,v_a.audit_head_hash,v_request
  );

  select pg_catalog.count(*)::integer into v_count
  from life_runtime.audit_flag_v05b where state in ('OPEN','ESCALATED');
  update life_runtime.audit_status_v05b
  set status='FLAGGED',open_flag_count=v_count,status_epoch=status_epoch+1
  where singleton_id=1;

  return pg_catalog.jsonb_build_object('code','APPLIED','new_flag_state','CLEARED');
end
$$;

revoke all on all functions in schema life_runtime from public, anon, authenticated, service_role;

commit;
