begin;

create function life_runtime.work_audit_trigger_v05b()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request_text text := pg_catalog.nullif(pg_catalog.current_setting('life_runtime.request_id', true),'');
  v_request uuid;
  v_operation text := pg_catalog.nullif(pg_catalog.current_setting('life_runtime.operation_kind', true),'');
  v_actor text := pg_catalog.nullif(pg_catalog.current_setting('life_runtime.claimed_actor', true),'');
  v_source text := pg_catalog.nullif(pg_catalog.current_setting('life_runtime.source_ref', true),'');
  v_contract text := pg_catalog.coalesce(pg_catalog.nullif(pg_catalog.current_setting('life_runtime.contract_generation', true),''),'V05B');
  v_path text := 'OUT_OF_PATH';
  v_old_hash text;
  v_new_hash text;
  v_event bigint;
  v_pk uuid;
begin
  if v_request_text is not null then
    begin
      v_request := v_request_text::uuid;
    exception when others then
      v_request := null;
    end;
  end if;

  if v_request is not null
     and v_operation is not null
     and exists (
       select 1 from life_runtime.operation_receipt_v05b o
       where o.request_id=v_request and o.operation_kind=v_operation
     ) then
    v_path := 'APPROVED_RUNTIME_PATH';
  end if;

  if tg_op <> 'INSERT' then
    v_old_hash := life_runtime.json_hash_v05b(pg_catalog.to_jsonb(old));
    v_pk := old.work_id;
  end if;
  if tg_op <> 'DELETE' then
    v_new_hash := life_runtime.json_hash_v05b(pg_catalog.to_jsonb(new));
    v_pk := new.work_id;
  end if;

  v_event := life_runtime.append_audit_event_v05b(
    'ROW_MUTATION',
    pg_catalog.coalesce(v_operation,tg_op),
    'life_runtime.work_v05b',
    pg_catalog.jsonb_build_object('work_id',v_pk),
    v_old_hash,
    v_new_hash,
    v_actor,
    v_request,
    v_operation,
    v_source,
    v_contract,
    v_path,
    null,
    null,
    null,
    null,
    pg_catalog.jsonb_build_object('trigger_op',tg_op)
  );

  if v_path='OUT_OF_PATH' and v_event is not null then
    perform life_runtime.open_blocking_flag_v05b(
      v_event,'OUT_OF_PATH',null,array['life_runtime.work_v05b',tg_op]
    );
  end if;

  return case when tg_op='DELETE' then old else new end;
end
$$;

create trigger work_v05b_audit_trg
after insert or update or delete on life_runtime.work_v05b
for each row execute function life_runtime.work_audit_trigger_v05b();

create function life_runtime.immutable_evidence_guard_v05b()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  raise exception using
    errcode='55000',
    message='V05B_IMMUTABLE_EVIDENCE';
end
$$;

create trigger transference_event_v05b_immutable_trg
before update or delete on life_runtime.transference_event_v05b
for each row execute function life_runtime.immutable_evidence_guard_v05b();

create trigger operation_receipt_v05b_immutable_trg
before update or delete on life_runtime.operation_receipt_v05b
for each row execute function life_runtime.immutable_evidence_guard_v05b();

create trigger audit_event_v05b_immutable_trg
before update or delete on life_runtime.audit_event_v05b
for each row execute function life_runtime.immutable_evidence_guard_v05b();

create trigger audit_clear_receipt_v05b_immutable_trg
before update or delete on life_runtime.audit_clear_receipt_v05b
for each row execute function life_runtime.immutable_evidence_guard_v05b();

create trigger audit_verification_receipt_v05b_immutable_trg
before update or delete on life_runtime.audit_verification_receipt_v05b
for each row execute function life_runtime.immutable_evidence_guard_v05b();

create trigger maintenance_receipt_v05b_immutable_trg
before update or delete on life_runtime.maintenance_receipt_v05b
for each row execute function life_runtime.immutable_evidence_guard_v05b();

create trigger owner_ingress_audit_v05b_immutable_trg
before update or delete on life_runtime.owner_ingress_audit_v05b
for each row execute function life_runtime.immutable_evidence_guard_v05b();

revoke all on function life_runtime.work_audit_trigger_v05b() from public, anon, authenticated, service_role;
revoke all on function life_runtime.immutable_evidence_guard_v05b() from public, anon, authenticated, service_role;

commit;
