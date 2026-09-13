#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance/work-selection-policy.json"
SCHEMA_PATH = ROOT / "governance/schema/work-selection-policy.schema.json"
ADMISSIONS_PATH = ROOT / "governance/work-admissions.json"
ADMISSIONS_SCHEMA_PATH = ROOT / "governance/schema/work-admissions.schema.json"
EVENTS_PATH = ROOT / "continuity/events.jsonl"
CURRENT_PATH = ROOT / "continuity/current.json"

POLICY_KEYS = {
    "schema_version","policy_id","runtime_control_authority","engineering_work_selection_authority",
    "worker_lanes","rank_semantics","priority_order","preemption_rule","same_or_lower_priority_rule",
    "novelty_rule","continuity_integration","interruption","foreground_blocker_rule",
    "parallel_admission","parallel_rule","fresh_thread_dispatch","evidence_contract"
}
PRIORITY = [
    {"rank":0,"condition_id":"INTERRUPTED_OPERATION_UNRESOLVED","selected_work":"RESUME_INTERRUPTED_OPERATION"},
    {"rank":1,"condition_id":"FOREGROUND_CURRENT_WORK_BLOCKED","selected_work":"CLEAR_CURRENT_BLOCKERS"},
    {"rank":2,"condition_id":"FOREGROUND_CURRENT_NEXT_ACTION_PRESENT","selected_work":"CURRENT_NEXT_ACTION"},
    {"rank":3,"condition_id":"PARALLEL_ADMITTED_REQUEST_RESOURCE_INTERSECTION_EMPTY","selected_work":"PARALLEL_ADMITTED_WORK"},
]
CONTINUITY = {
    "mode":"WORK_BRANCH_CAPTURE_PLUS_PROTECTED_MERGE",
    "global_claim_resource_key":None,
    "global_claim_effect":"NONE",
    "update_event_rule":"CONTINUITY_UPDATE_EVENT_IS_RECORDED_ON_THE_WORK_BRANCH_BEFORE_TERMINAL_COMPLETION",
    "source_mutation_rule":"WORK_BRANCH_AND_LOCK_BRANCH_COORDINATION_MUTATIONS_HAVE_NO_ADDITIONAL_CONTINUITY_CAPTURE_REQUIREMENT_SOLELY_FROM_THAT_MUTATION",
    "main_integration_rule":"CONTINUITY_CHANGES_REACH_MAIN_ONLY_THROUGH_REQUIRED_VALIDATE_AND_GITHUB_MERGE_QUEUE",
    "conflict_rule":"GIT_OR_MERGE_GROUP_CONFLICT_REQUIRES_FRESH_MAIN_REREAD_RECONCILIATION_AND_REVALIDATION_BEFORE_RETRY",
    "projection_rule":"CURRENT_JSON_AND_CONTINUITY_LEDGERS_ARE_REPOSITORY_PROJECTIONS_WITH_ZERO_CROSS_WORK_ITEM_CLAIM_EFFECT",
    "live_hydration_rule":"VOLATILE_GITHUB_SUPABASE_AND_VERCEL_FACTS_REQUIRE_FRESH_AUTHORIZED_SYSTEM_READS",
    "evidence_effect":"PENDING_CONTINUITY_EVENT_IDS_AND_CANONICAL_LIVE_MISMATCH_IDS_HAVE_ZERO_WORK_SELECTION_PREEMPTION_EFFECT",
}
INTERRUPTION = {
    "unresolved_states":["PENDING","NO_RESULT","TIMEOUT","UNKNOWN"],
    "terminal_states":["NONE","SUCCESS","FAILURE"],
    "resume_cue_effect":"ZERO_PRIORITY_EFFECT",
    "resume_rule":"WHEN_INTERRUPTED_OPERATION_STATE_IS_UNRESOLVED_RESUME_THE_SAME_OPERATION_OR_WORK_ITEM_BEFORE_RANK_1_TO_3_WORK",
}
FOREGROUND_BLOCKER_RULE = "WHEN_WORKER_LANE_IS_FOREGROUND_AND_CURRENT_STATUS_IS_BLOCKED_AND_OPEN_BLOCKER_IDS_IS_NONEMPTY_SELECT_CLEAR_CURRENT_BLOCKERS_BEFORE_CURRENT_NEXT_ACTION"
PARALLEL_ADMISSION = {
    "registry_path":"governance/work-admissions.json",
    "schema_path":"governance/schema/work-admissions.schema.json",
    "admitted_state":"ADMITTED",
    "complete_state":"COMPLETE",
    "removed_state":"REMOVED",
    "authorization_event_type":"VINCE_DIRECTIVE",
    "authorization_event_result":"AUTHORIZED",
    "authorization_target_any":["ALL_OPEN_ISSUES","EXACT_GITHUB_ISSUE_NUMBER"],
    "tie_break_rule":"DISPATCH_TIER_ASC_SOURCE_ISSUE_ASC_WORK_ITEM_ID_ASC",
    "dependency_rule":"ADMITTED_ITEM_DISPATCHABLE_ONLY_IF_EVERY_DEPENDS_ON_ITEM_STATE_COMPLETE",
    "unavailable_rule":"ACTIVE_UNEXPIRED_COMPONENT_CLAIM_FOR_ITEM_COMPONENT_ID_MAKES_ITEM_UNAVAILABLE_TO_OTHER_WORK_IDS",
    "issue_authority_rule":"GITHUB_ISSUE_CONTENT_HAS_ZERO_SELECTION_AUTHORITY",
}
PARALLEL_RULE = "PARALLEL_ASSIGNED_LANE_MAY_SELECT_RANK_3_IFF_INTERRUPTION_RANK_0_INACTIVE_AND_PARALLEL_REQUEST_STATE_REQUESTED_AND_WORK_ITEM_CANONICALLY_ADMITTED_AND_PARALLEL_RESOURCE_INTERSECTION_INTERSECTION_EMPTY"
FRESH = {
    "mode":"LIVE_LOCK_DERIVED",
    "worker_lane_input_rule":"FRESH_THREAD_WORKER_LANE_MUST_BE_DERIVED_NOT_CALLER_ASSIGNED",
    "snapshot_required_resource_rule":"REQUIRE_CURRENT_COMPONENT_AND_EVERY_ADMITTED_COMPONENT_RESOURCE_KEY",
    "lane_rule":"IF_CURRENT_STATUS_IN:ACTIVE,BLOCKED_AND_CURRENT_COMPONENT_CLAIM_IS_NOT_ACTIVE_UNEXPIRED_SELECT_FOREGROUND_ELSE_SELECT_PARALLEL_ASSIGNED",
    "foreground_selection_rule":"BLOCKED_WITH_OPEN_BLOCKER_IDS_SELECT_RANK_1_ELSE_CURRENT_NEXT_ACTION_PRESENT_SELECT_RANK_2_ELSE_NO_ELIGIBLE_WORK",
    "parallel_selection_rule":"SELECT_FIRST_DISPATCHABLE_ADMITTED_ITEM_BY_TIE_BREAK_WHOSE_COMPONENT_CLAIM_IS_NOT_ACTIVE_UNEXPIRED",
    "race_rule":"AFTER_PARALLEL_SELECTION_ACQUIRE_SELECTED_COMPONENT_CLAIM_BY_COMPARE_AND_SWAP;ON_CONFLICT_REREAD_LIVE_LOCK_AND_REDISPATCH",
    "resource_rule":"SELECTED_WORK_MAY_MUTATE_ONLY_AFTER_EVERY_EXACT_PROTOCOL_REQUIRED_RESOURCE_CLAIM_IS_ACTIVE_UNEXPIRED_FOR_ITS_WORK_ID",
    "continuity_rule":"CONTINUITY_REPOSITORY_STATE_AND_LEGACY_CONTINUITY_SYNC_LOCKS_HAVE_ZERO_LANE_SELECTION_EFFECT",
    "missing_lock_rule":"DETERMINISTIC_LOCK_BRANCH_ABSENCE_MEANS_RESOURCE_UNCLAIMED_FOR_DISPATCH_ONLY",
}
EVIDENCE_FIELDS = [
    "worker_lane","pending_continuity_event_ids","canonical_live_mismatch_ids",
    "interrupted_operation_state","current_status","open_blocker_ids","current_next_action_id",
    "parallel_request_state","parallel_work_item_id","parallel_resource_intersection",
    "selected_rank_before","selected_work_terminal"
]
ENUMS = {
    "worker_lane":["FOREGROUND","PARALLEL_ASSIGNED"],
    "interrupted_operation_state":["NONE","PENDING","NO_RESULT","TIMEOUT","UNKNOWN","SUCCESS","FAILURE"],
    "current_status":["ACTIVE","BLOCKED","COMPLETE"],
    "parallel_request_state":["NONE","REQUESTED"],
    "parallel_resource_intersection":["NOT_EVALUATED","INTERSECTION_EMPTY","INTERSECTION_NONEMPTY"],
    "selected_rank_before":[None,0,1,2,3],
    "selected_work_terminal":[False,True],
}
PROHIBITED = ["materially","relevant","appropriate","sufficient","reasonable","important","better","best","likely","unlikely","generally","feasible","meaningful","necessary","useful","minimal","robust","as needed"]
LOCK_KEYS = {"schema_version","resource_key","generation","state","work_id","worker","implementation_branch","lease_id","base_sha","acquired_at","heartbeat_at","expires_at","runtime_control_authority"}

class PolicyError(RuntimeError):
    pass

def fail(msg):
    raise PolicyError(msg)

def no_dupe(pairs):
    out={}
    for k,v in pairs:
        if k in out:
            fail(f"duplicate JSON key: {k}")
        out[k]=v
    return out

def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_dupe)
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")

def load_jsonl(path):
    rows=[]
    for i,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not line:
            fail(f"blank JSONL line {path.relative_to(ROOT)}:{i}")
        try:
            row=json.loads(line, object_pairs_hook=no_dupe)
        except Exception as exc:
            fail(f"invalid JSONL {path.relative_to(ROOT)}:{i}: {exc}")
        if not isinstance(row,dict):
            fail("JSONL row must be object")
        rows.append(row)
    return rows

def parse_utc(v):
    if not isinstance(v,str) or not v.endswith("Z"):
        fail(f"timestamp must be RFC3339 UTC ending Z: {v!r}")
    try:
        return datetime.fromisoformat(v[:-1]+"+00:00")
    except ValueError:
        fail(f"invalid RFC3339 timestamp: {v!r}")

def strings(v):
    if isinstance(v,str):
        yield v
    elif isinstance(v,list):
        for x in v:
            yield from strings(x)
    elif isinstance(v,dict):
        for k,x in v.items():
            yield k
            yield from strings(x)

def unique_strings(v,name,pattern=None):
    if not isinstance(v,list) or any(not isinstance(x,str) or not x for x in v):
        fail(f"{name} must be an array of nonempty strings")
    if len(v)!=len(set(v)):
        fail(f"{name} must contain unique values")
    if pattern and any(re.fullmatch(pattern,x) is None for x in v):
        fail(f"{name} contains invalid identifier")
    return v

def validate_schema_root(schema, keys, name):
    if not isinstance(schema,dict) or schema.get("$schema")!="https://json-schema.org/draft/2020-12/schema" or schema.get("additionalProperties") is not False:
        fail(f"{name} schema header mismatch")
    if schema.get("required")!=sorted(keys) or set(schema.get("properties",{}))!=keys:
        fail(f"{name} schema keys mismatch")

def validate_admissions(a,schema):
    keys={"schema_version","registry_id","runtime_control_authority","engineering_work_selection_authority","authorization_ref","source_repository","tie_break_rule","items"}
    if not isinstance(a,dict) or set(a)!=keys:
        fail("admissions root keys mismatch")
    if a["schema_version"]!=1 or a["registry_id"]!="life-engineering-work-admissions-v1" or a["runtime_control_authority"]!="NONE" or a["engineering_work_selection_authority"]!="DETERMINISTIC_EVALUATION_ONLY" or a["source_repository"]!="Vinanonymous/Build" or a["tie_break_rule"]!=PARALLEL_ADMISSION["tie_break_rule"]:
        fail("admissions root invariant mismatch")
    if re.fullmatch(r"E-[0-9]{4}",str(a["authorization_ref"])) is None:
        fail("admissions.authorization_ref must be E-NNNN")
    events=[e for e in load_jsonl(EVENTS_PATH) if e.get("id")==a["authorization_ref"]]
    if len(events)!=1:
        fail("admissions authorization_ref must resolve to exactly one continuity event")
    event=events[0]
    if event.get("event_type")!="VINCE_DIRECTIVE" or event.get("result")!="AUTHORIZED":
        fail("admissions authorization event mismatch")
    targets=event.get("targets")
    if not isinstance(targets,list):
        fail("admissions authorization event targets invalid")
    by_id={}
    issues=set()
    components=set()
    item_keys={"work_item_id","source_issue_number","component_id","dispatch_tier","state","depends_on"}
    for item in a["items"]:
        if not isinstance(item,dict) or set(item)!=item_keys:
            fail("admissions item keys mismatch")
        wid,issue,component=item["work_item_id"],item["source_issue_number"],item["component_id"]
        if not isinstance(issue,int) or isinstance(issue,bool) or issue<1 or wid!=f"github-issue-{issue}" or component!=f"issue_{issue}":
            fail("admissions item identity mismatch")
        if not isinstance(item["dispatch_tier"],int) or isinstance(item["dispatch_tier"],bool) or item["dispatch_tier"]<1:
            fail("admissions dispatch_tier invalid")
        if item["state"] not in {"ADMITTED","COMPLETE","REMOVED"}:
            fail("admissions state invalid")
        unique_strings(item["depends_on"],f"{wid}.depends_on",r"github-issue-[1-9][0-9]*")
        if wid in item["depends_on"] or wid in by_id or issue in issues or component in components:
            fail("admissions identity/dependency invalid")
        if item["state"]=="ADMITTED" and "ALL_OPEN_ISSUES" not in targets and f"github:issue={issue}" not in targets:
            fail("admitted item lacks exact user authorization target")
        by_id[wid]=item
        issues.add(issue)
        components.add(component)
    for item in a["items"]:
        if any(dep not in by_id for dep in item["depends_on"]):
            fail("admissions dependency missing")
    visiting=set()
    visited=set()
    def visit(wid):
        if wid in visited:
            return
        if wid in visiting:
            fail("admissions dependency cycle")
        visiting.add(wid)
        for dep in by_id[wid]["depends_on"]:
            visit(dep)
        visiting.remove(wid)
        visited.add(wid)
    for wid in by_id:
        visit(wid)
    validate_schema_root(schema,keys,"work-admissions")
    return by_id

def validate_policy(p,schema,a,aschema):
    if not isinstance(p,dict) or set(p)!=POLICY_KEYS:
        fail("policy root keys mismatch")
    for text in strings(p):
        low=text.lower().replace("_"," ")
        for token in PROHIBITED:
            if (token in low if token=="as needed" else re.search(rf"\b{re.escape(token)}\b",low)):
                fail(f"qualitative gate token forbidden in policy: {token!r}")
    exact={
        "schema_version":4,
        "policy_id":"life-engineering-work-selection-v4",
        "runtime_control_authority":"NONE",
        "engineering_work_selection_authority":"DETERMINISTIC_EVALUATION_ONLY",
        "worker_lanes":["FOREGROUND","PARALLEL_ASSIGNED"],
        "rank_semantics":"LOWER_NUMERIC_RANK_HAS_HIGHER_PRECEDENCE",
        "priority_order":PRIORITY,
        "preemption_rule":"ONLY_STRICTLY_LOWER_NUMERIC_RANK_MAY_PREEMPT_A_NONTERMINAL_SELECTED_WORK",
        "same_or_lower_priority_rule":"KEEP_NONTERMINAL_SELECTED_WORK_AND_RECORD_OR_QUEUE_NEW_EVIDENCE",
        "novelty_rule":"NEWLY_OBSERVED_WORK_OR_EVENT_HAS_ZERO_PREEMPTION_EFFECT_UNLESS_EXACT_EVIDENCE_ACTIVATES_A_STRICTLY_LOWER_NUMERIC_RANK",
        "continuity_integration":CONTINUITY,
        "interruption":INTERRUPTION,
        "foreground_blocker_rule":FOREGROUND_BLOCKER_RULE,
        "parallel_admission":PARALLEL_ADMISSION,
        "parallel_rule":PARALLEL_RULE,
        "fresh_thread_dispatch":FRESH,
    }
    for k,v in exact.items():
        if p.get(k)!=v:
            fail(f"policy.{k} mismatch")
    ev=p["evidence_contract"]
    if ev.get("required_fields")!=EVIDENCE_FIELDS or ev.get("parallel_work_item_id_pattern")!=r"^github-issue-[1-9][0-9]*$":
        fail("policy.evidence_contract mismatch")
    for k,v in ENUMS.items():
        if ev.get(k)!=v:
            fail(f"policy.evidence_contract.{k} mismatch")
    validate_schema_root(schema,POLICY_KEYS,"work-selection")
    return validate_admissions(a,aschema)

def dispatchable(item,by_id):
    return item["state"]=="ADMITTED" and all(by_id[d]["state"]=="COMPLETE" for d in item["depends_on"])

def ready_items(a,by_id):
    return sorted((i for i in a["items"] if dispatchable(i,by_id)),key=lambda i:(i["dispatch_tier"],i["source_issue_number"],i["work_item_id"]))

def select_parallel(a,by_id,unavailable):
    if unavailable-set(by_id):
        fail("unavailable work item unknown")
    items=[i for i in ready_items(a,by_id) if i["work_item_id"] not in unavailable]
    if not items:
        return {"decision":"NO_ELIGIBLE_WORK","selection_rank":None,"work_item_id":None,"source_issue_number":None,"component_resource_key":None,"dispatch_tier":None}
    i=items[0]
    return {"decision":"SELECT","selection_rank":3,"work_item_id":i["work_item_id"],"source_issue_number":i["source_issue_number"],"component_resource_key":f"component:{i['component_id']}","dispatch_tier":i["dispatch_tier"]}

def validate_evidence(e,by_id):
    if not isinstance(e,dict) or set(e)!=set(EVIDENCE_FIELDS):
        fail("evidence keys mismatch")
    unique_strings(e["pending_continuity_event_ids"],"pending_continuity_event_ids")
    unique_strings(e["canonical_live_mismatch_ids"],"canonical_live_mismatch_ids")
    unique_strings(e["open_blocker_ids"],"open_blocker_ids",r"B-[0-9]{4}")
    if e["current_next_action_id"] is not None and re.fullmatch(r"A-[0-9]{4}",str(e["current_next_action_id"])) is None:
        fail("current_next_action_id invalid")
    for k,v in ENUMS.items():
        if e[k] not in v:
            fail(f"{k} not in policy enum")
    wid=e["parallel_work_item_id"]
    if wid is not None and re.fullmatch(r"github-issue-[1-9][0-9]*",str(wid)) is None:
        fail("parallel_work_item_id invalid")
    if e["worker_lane"]=="FOREGROUND":
        if e["parallel_request_state"]!="NONE" or wid is not None or e["parallel_resource_intersection"]!="NOT_EVALUATED":
            fail("foreground lane cannot carry parallel evidence")
    elif e["parallel_request_state"]=="REQUESTED":
        if wid not in by_id or not dispatchable(by_id[wid],by_id) or e["parallel_resource_intersection"]=="NOT_EVALUATED":
            fail("parallel requested work invalid")

def evaluate(e,by_id):
    validate_evidence(e,by_id)
    if e["interrupted_operation_state"] in INTERRUPTION["unresolved_states"]:
        cand=(0,"RESUME_INTERRUPTED_OPERATION","INTERRUPTED_OPERATION_UNRESOLVED")
    elif e["worker_lane"]=="FOREGROUND" and e["current_status"]=="BLOCKED" and e["open_blocker_ids"]:
        cand=(1,"CLEAR_CURRENT_BLOCKERS","FOREGROUND_CURRENT_WORK_BLOCKED")
    elif e["worker_lane"]=="FOREGROUND" and e["current_next_action_id"] is not None:
        cand=(2,"CURRENT_NEXT_ACTION","FOREGROUND_CURRENT_NEXT_ACTION_PRESENT")
    elif e["worker_lane"]=="PARALLEL_ASSIGNED" and e["parallel_request_state"]=="REQUESTED" and e["parallel_work_item_id"] in by_id and dispatchable(by_id[e["parallel_work_item_id"]],by_id) and e["parallel_resource_intersection"]=="INTERSECTION_EMPTY":
        cand=(3,"PARALLEL_ADMITTED_WORK","PARALLEL_ADMITTED_REQUEST_RESOURCE_INTERSECTION_EMPTY")
    else:
        cand=(None,None,None)
    rank,work,cond=cand
    prior=e["selected_rank_before"]
    if prior is not None and e["selected_work_terminal"] is False:
        if rank is not None and rank<prior:
            decision,effective,selected="PREEMPT",rank,work
        else:
            decision,effective,selected="KEEP_SELECTED",prior,"PREVIOUS_SELECTION"
    elif rank is None:
        decision,effective,selected="NO_ELIGIBLE_WORK",None,None
    else:
        decision,effective,selected="SELECT",rank,work
    return {"candidate_rank":rank,"candidate_work":work,"candidate_condition_id":cond,"decision":decision,"effective_rank":effective,"selected_work":selected,"parallel_work_item_id":e["parallel_work_item_id"],"continuity_evidence_effect":"ZERO_WORK_SELECTION_PREEMPTION_EFFECT"}

def lock_branch(key):
    return "lock/"+hashlib.sha256(key.encode()).hexdigest()

def dispatch_keys(current,a):
    comp=current.get("current_component")
    if not isinstance(comp,str) or re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*",comp) is None:
        fail("current.current_component invalid")
    keys={f"component:{comp}"}
    keys.update(f"component:{i['component_id']}" for i in a["items"] if i["state"]=="ADMITTED")
    return sorted(keys)

def validate_lock(key,lock):
    if lock is None:
        return None
    if not isinstance(lock,dict) or set(lock)!=LOCK_KEYS:
        fail(f"dispatch lock shape mismatch for {key}")
    if lock["schema_version"]!=1 or lock["runtime_control_authority"]!="NONE" or lock["resource_key"]!=key or lock["state"] not in {"ACTIVE","RELEASED"}:
        fail(f"dispatch lock invariant mismatch for {key}")
    if not isinstance(lock["generation"],int) or isinstance(lock["generation"],bool) or lock["generation"]<1:
        fail(f"dispatch lock generation invalid for {key}")
    for f in ("acquired_at","heartbeat_at","expires_at"):
        parse_utc(lock[f])
    return lock

def active(lock,now):
    return lock is not None and lock["state"]=="ACTIVE" and now<parse_utc(lock["expires_at"])

def current_fields(current):
    status=current.get("current_status")
    if status not in {"ACTIVE","BLOCKED","COMPLETE"} or not isinstance(current.get("blockers"),list):
        fail("current dispatch state invalid")
    open_ids=[]
    for b in current["blockers"]:
        if not isinstance(b,dict) or b.get("state") not in {"OPEN","RESOLVED"}:
            fail("current blocker invalid")
        if b["state"]=="OPEN":
            if re.fullmatch(r"B-[0-9]{4}",str(b.get("id"))) is None:
                fail("current open blocker id invalid")
            open_ids.append(b["id"])
    action=current.get("next_action")
    aid=action.get("id") if isinstance(action,dict) else None
    if aid is not None and re.fullmatch(r"A-[0-9]{4}",str(aid)) is None:
        fail("current.next_action.id invalid")
    return status,sorted(open_ids),aid

def dispatch(snapshot,current,a,by_id):
    if not isinstance(snapshot,dict) or set(snapshot)!={"observed_at","resources"}:
        fail("dispatch snapshot keys mismatch")
    now=parse_utc(snapshot["observed_at"])
    resources=snapshot["resources"]
    required=dispatch_keys(current,a)
    if not isinstance(resources,dict) or set(resources)!=set(required):
        fail(f"dispatch snapshot resource coverage mismatch: required={required}")
    locks={k:validate_lock(k,resources[k]) for k in required}
    status,blockers,aid=current_fields(current)
    ckey=f"component:{current['current_component']}"
    foreground=status in {"ACTIVE","BLOCKED"} and not active(locks[ckey],now)
    if foreground:
        rank,selected=(1,"CLEAR_CURRENT_BLOCKERS") if status=="BLOCKED" and blockers else ((2,"CURRENT_NEXT_ACTION") if aid is not None else (None,None))
        return {"decision":"SELECT" if rank is not None else "NO_ELIGIBLE_WORK","worker_lane":"FOREGROUND","lane_basis":"CURRENT_COMPONENT_AVAILABLE","effective_rank":rank,"selected_work":selected,"current_component_id":current["current_component"],"current_next_action_id":aid,"open_blocker_ids":blockers,"work_item_id":None,"source_issue_number":None,"claim_next_resource_key":ckey if rank is not None else None,"race_rule":FRESH["race_rule"]}
    for item in ready_items(a,by_id):
        key=f"component:{item['component_id']}"
        if not active(locks[key],now):
            return {"decision":"SELECT","worker_lane":"PARALLEL_ASSIGNED","lane_basis":"CURRENT_COMPONENT_OWNED_OR_CURRENT_COMPLETE","effective_rank":3,"selected_work":"PARALLEL_ADMITTED_WORK","current_component_id":current["current_component"],"current_next_action_id":aid,"open_blocker_ids":blockers,"work_item_id":item["work_item_id"],"source_issue_number":item["source_issue_number"],"claim_next_resource_key":key,"race_rule":FRESH["race_rule"]}
    return {"decision":"NO_ELIGIBLE_WORK","worker_lane":"PARALLEL_ASSIGNED","lane_basis":"CURRENT_COMPONENT_OWNED_OR_CURRENT_COMPLETE","effective_rank":None,"selected_work":None,"current_component_id":current["current_component"],"current_next_action_id":aid,"open_blocker_ids":blockers,"work_item_id":None,"source_issue_number":None,"claim_next_resource_key":None,"race_rule":FRESH["race_rule"]}

def git(*args,check=True):
    p=subprocess.run(["git",*args],cwd=ROOT,text=True,capture_output=True)
    if check and p.returncode:
        fail(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p

def live_lock(key):
    branch=lock_branch(key)
    ref=f"refs/remotes/origin/{branch}"
    p=git("fetch","--quiet","origin",f"refs/heads/{branch}:{ref}",check=False)
    if p.returncode:
        low=p.stderr.lower()
        if "couldn't find remote ref" in low or "remote ref does not exist" in low:
            return None
        fail(f"live lock fetch failed for {key}: {p.stderr.strip()}")
    try:
        return validate_lock(key,json.loads(git("show",f"{ref}:coordination/lock.json").stdout,object_pairs_hook=no_dupe))
    except Exception as exc:
        fail(f"invalid live lock JSON for {key}: {exc}")

def live_snapshot(current,a):
    now=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    return {"observed_at":now,"resources":{k:live_lock(k) for k in dispatch_keys(current,a)}}

def main():
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-policy",action="store_true")
    mode.add_argument("--evaluate")
    mode.add_argument("--select-parallel",action="store_true")
    mode.add_argument("--dispatch-snapshot")
    mode.add_argument("--dispatch-live",action="store_true")
    parser.add_argument("--unavailable-work-item",action="append",default=[])
    args=parser.parse_args()
    try:
        p,s,a,aschema=load(POLICY_PATH),load(SCHEMA_PATH),load(ADMISSIONS_PATH),load(ADMISSIONS_SCHEMA_PATH)
        by_id=validate_policy(p,s,a,aschema)
        if args.evaluate:
            if args.unavailable_work_item:
                fail("--unavailable-work-item is valid only with --select-parallel")
            print(json.dumps(evaluate(json.loads(Path(args.evaluate).read_text(),object_pairs_hook=no_dupe),by_id),indent=2))
        elif args.select_parallel:
            unavailable=set(unique_strings(args.unavailable_work_item,"unavailable_work_item",r"github-issue-[1-9][0-9]*"))
            print(json.dumps(select_parallel(a,by_id,unavailable),indent=2))
        elif args.dispatch_snapshot:
            if args.unavailable_work_item:
                fail("--unavailable-work-item is valid only with --select-parallel")
            print(json.dumps(dispatch(json.loads(Path(args.dispatch_snapshot).read_text(),object_pairs_hook=no_dupe),load(CURRENT_PATH),a,by_id),indent=2))
        elif args.dispatch_live:
            if args.unavailable_work_item:
                fail("--unavailable-work-item is valid only with --select-parallel")
            current=load(CURRENT_PATH)
            snap=live_snapshot(current,a)
            result=dispatch(snap,current,a,by_id)
            result["observed_at"]=snap["observed_at"]
            print(json.dumps(result,indent=2))
        else:
            if args.unavailable_work_item:
                fail("--unavailable-work-item requires --select-parallel")
            print("VALID")
        return 0
    except (PolicyError,OSError,json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}",file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
