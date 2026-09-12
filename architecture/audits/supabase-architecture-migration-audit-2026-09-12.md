# Supabase Architecture → Life/Build migration audit

Audit date: 2026-09-12
Source Supabase project: `Architecture` (`bxnncaanwczgglrhtymh`)
Destination Supabase project: `Life` (`jnenguxodtgwbskhdsxt`)
Destination repository: `Vinanonymous/Build`
Audit work: `e5d15f24-6814-4b63-9352-95af6752fefb`
Runtime control authority of this artifact: `NONE`

## Executive conclusion

Do **not** migrate the Architecture project as a database, schema, migration chain, or gateway implementation.

Migrate the **surviving requirements, protected properties, failure lessons, and a small number of control mechanisms**, then rebuild them from clean source-controlled contracts in Build and only add the minimum stateful runtime pieces to the Life Supabase project when a live Life surface needs them.

The old project is simultaneously valuable and overgrown. It contains strong ideas—deterministic authority, scoped claims, idempotency, mutation pre/postconditions, provenance, failure recurrence prevention, evidence-state discipline, external-review separation, and cross-worker conflict prevention—but those ideas became distributed across 65 Architecture tables, 2 views, 175 custom functions across Architecture-related schemas, 140 migrations, 3 Edge Functions, thousands of reasoning-dependency rows, and several overlapping ledgers. Replaying that implementation would import both its best concepts and the failure modes it was already documenting.

The correct migration unit is therefore the **property/control contract**, not the legacy object.

## Verified source inventory

Direct reads of the Architecture project established:

- Project is `ACTIVE_HEALTHY`, Postgres 17.6, region `us-west-1`.
- 140 applied migrations.
- `architecture`: 65 tables and 2 views.
- `architecture_advisory`: 1 table.
- Custom functions: 152 in `architecture`, 21 in `architecture_gateway`, 1 in `architecture_ingress`, 1 in `architecture_advisory` = 175 total across those four schemas.
- 3 ACTIVE Edge Functions: `architecture-gateway` v12, `architecture-signed-worker-gateway` v7, `architecture-review-ingress` v1.
- Database size approximately 25.4 MB; Architecture/Architecture Advisory table relations approximately 11.0 MB.
- No Supabase Storage buckets.
- No tables in the `supabase_realtime` publication.
- `pg_cron` is not installed; no cron job relation exists.
- No development branches.
- Installed extensions observed: `pg_stat_statements`, `pgcrypto`, `plpgsql`, `supabase_vault`, `uuid-ossp`.
- Security Advisor: 20 RLS-enabled tables with no policies, 5 mutable-search-path warnings, and public review RPC exposure warnings.
- Performance Advisor: 59 unindexed foreign keys and 3 unused indexes.
- Architecture and Life are the two `ACTIVE_HEALTHY` projects in the same Supabase organization; the other observed legacy Life projects are inactive. Current Supabase Free officially allows 2 active projects, so Architecture presently occupies one of the two active slots.

## Current Life/Build comparison

Direct reads of the current Life project established that the clean successor is still intentionally small:

- Custom Life tables: `life.invocations`, `life.oauth_callers_v1`.
- Life functions: `life.record_invocation_v1(...)` and immutable-ledger trigger `life.reject_invocation_mutation_v1()`.
- Applied migrations: `20260912042500 life_invocation_v1`, `20260912052949 life_invocation_v1_alignment`.
- Edge Functions: 0.
- Security Advisor lints: 0.
- Performance Advisor lints: 0.
- Canonical `life.invoke`: NOT_RUN because no exact authorized Vercel target/deployed Life MCP endpoint/tool is live-verified yet.

The Build repository already owns continuity, deterministic source coordination, work selection, watchdog definitions, canonical-invocation contracts, Supabase migrations/tests, and strict main-branch protection. That means several Architecture ideas have already been reimplemented in a smaller and cleaner form.

## Architecture-wide finding: duplicate control representations

Architecture has multiple audit/control trails that overlap in purpose:

- `events`: 942 rows
- `operation_log`: 674
- `mutation_receipts`: 158
- `provenance_spine`: 66
- `provider_change_receipts`: 74
- `reasoning_impact_events`: 464
- `reasoning_snapshots`: 197
- `reasoning_rebases`: 175
- `reasoning_snapshot_dependencies`: 6,995

This is the clearest structural reason not to copy the old control plane. One of Architecture's own protected properties says one authoritative representation should exist per control fact; the final implementation nevertheless accumulated several adjacent representations that require reconciliation.

The reasoning subsystem is the strongest example: 42 WORK rows produced 197 snapshots, 175 rebases, 464 impact events, and 6,995 snapshot dependencies. The underlying property—workers must not act from stale dependencies—is valuable. The legacy graph is not.

## Work and failure state is evidence, not successor authority

The Architecture project was not settled when superseded:

- WORK: 5 ACTIVE, 3 BLOCKED, 19 OPEN, 3 WAITING, 12 COMPLETE.
- Failure families: 21 OPEN, 2 MITIGATED, 17 CLOSED.
- Evolution candidates: 17 PROPOSED, 5 REQUIRED_REPAIR, 2 IMPLEMENTED.
- Execution claims: 12 ACTIVE, 30 EXPIRED, 62 RELEASED.
- Resource claims: 1 ACTIVE, 82 EXPIRED, 178 RELEASED.

Do not import these statuses into Life as current tasks or authority. Re-evaluate each underlying requirement/failure against current Life. Preserve only evidence and surviving protected properties.

## Highest-value failure lessons to preserve

The open/mitigated failure ledger contains concrete lessons that should survive even though the old machinery should not:

1. **Clean-slate contamination** — successor designs should not inherit old mechanisms without a requirement trace. This is already represented by current Build decisions and should remain.
2. **Capability-discovery false negatives** — a filtered tool query cannot prove provider-wide absence. Current research/tool-discovery rules already address this; preserve as evidence/falsification test.
3. **Exact artifact preservation** — hashes/lengths do not prove an artifact is durably retrievable. Preserve in source/evidence policy.
4. **Failure-writer idempotency ordering** — replay resolution must occur before mutable obligation-state validation where replay is supposed to be accepted. Preserve as an idempotency test pattern.
5. **Deterministic-language regression** — retired vague gate terms were copied back into protocols. Current semantic-firewall/project rules supersede the old implementation; preserve the regression as a test case.
6. **DDL prevalidation gaps** — large first-pass migrations caused invalid SQL. Preserve: smaller source-versioned migrations plus local/CI database tests before remote apply.
7. **Failure-ledger FK ordering** — bidirectional references created two-phase write hazards. Do not reproduce the schema; design acyclic insert paths.
8. **Mutation payload preflight omissions** — schema/signature/enums must be validated before execution. Preserve in mutation contract.
9. **Unnecessary multi-chat serialization** — unrelated work was blocked by stale/global gates. Current exact-resource source coordination is the successor pattern; runtime controls must remain scope-local.
10. **False-green semantic validators** — substring checking can report PASS while meaning is wrong. Preserve as a prohibition against token-presence validators claiming semantic correctness.
11. **Global deterministic-language gate serialized unrelated workers** — never put a global currentness gate in the mutation path when the protected fact is claim/resource scoped.
12. **Provider manifest settlement gap** — absence of receipts is not evidence that no pending provider change exists. Preserve exact declared-intent → receipt → readback linkage.
13. **Self-authored reasoning invalidation** — a worker's own verified mutation should not automatically invalidate every subsequent step. This is one reason to avoid the old reasoning-snapshot graph and use exact version/dependency tokens instead.
14. **Repair-loop nontermination** — repeated local patches need a finite escalation/reassessment state. Preserve as a bounded repair policy.
15. **Change-manifest sequencing failure** — the old scoped mutation primitive enforced many controls but did not mechanically require the declared manifest/pre-change gate before mutation. Preserve the property; rebuild the enforcement path rather than copying the function chain.

## Edge Functions: disposition

### `architecture-gateway` — REPLACE

What it did: GitHub-OIDC-authenticated mutation gateway with typed operations, request hashing, claim/generation checks, and database dispatch.

Why not migrate as-is:

- hard-coded to retired private repository `Vinanonymous/life-architecture-gateway`, repository ID 1358924601, actor ID 154024038, pinned workflow identity/audience;
- `verify_jwt=false` and custom OIDC handling;
- depends on the legacy Architecture function surface and service-level credentials;
- current clean-slate Life decision selected Vercel Functions as the MCP OAuth resource server and Supabase Auth/Postgres behind it.

Keep: closed operation schemas, exact request hash/idempotency key, resource/generation checks, server-side authorization, finite operation allowlists.

Destination: `governance/authorization-policy.json`, `governance/mutation-policy.json`, MCP/Vercel source when the authorized Life Vercel target exists, and GitHub-versioned Supabase functions only for database-local invariants.

### `architecture-signed-worker-gateway` — DEFER / POSSIBLE LATER COMBINE

What it did: P-256 worker public-key enrollment and signed-operation verification bound to claim/generation.

Keep only the property: an external worker must have a mechanically bound principal/capability before it can execute an effect.

Do not install now. Current ChatGPT/GitHub coordination does not need a parallel cryptographic principal system. Reconsider only when a real non-parent worker needs direct runtime mutation authority and the platform cannot provide a stronger native session/principal binding.

Destination if later justified: authenticated MCP/Vercel authorization layer + minimal Life credential/public-key registry + exact replay/idempotency tests.

### `architecture-review-ingress` — MODIFY, LATER

What it did: one-tool MCP ingress `submit_review_result`, explicitly advisory/non-authoritative. It used the Supabase anon key and called public RPC `archreview_submit_v1` with a one-time submission token.

Keep: external reviewers are evidence providers, not control authority; submission should be append-only and one-time/idempotent.

Replace: anon-key/public-RPC exposure. The Security Advisor currently warns that `archreview_submit_v1` is executable by `anon` and `authenticated`.

Destination: `governance/review-policy.json` now; authenticated MCP/Vercel reviewer route and append-only `life.review_submissions` only when an actual reviewer integration is activated.

## Security findings

### RLS pattern — DO NOT COPY

20 Architecture tables have RLS enabled but no policies. This can be intentionally fail-closed for API roles, but it is not a reusable per-user authorization design. The project mainly relied on privileged/security-definer functions and gateways.

Current Supabase guidance says exposed tables should use RLS and grants/policies together. Life should decide access per actual surface; do not mechanically reproduce `RLS enabled + zero policies` as architecture.

### Function privilege surface — NARROW IN SUCCESSOR

Many nonmutating Architecture functions retain `PUBLIC EXECUTE`, while `public.archreview_submit_v1` is executable by `anon` and `authenticated`. The old review RPC may be token-gated internally, but public execution is still a larger exposed surface than Life currently needs.

Successor rule: revoke default/public execution unless a function is deliberately exposed; expose through the canonical MCP/API route where possible; use database permissions as defense in depth.

### Mutable `search_path` warnings — FIX BY CONSTRUCTION

Security Advisor currently flags:

- `architecture.delegation_decision_core_v1`
- `architecture.execution_protocol_status_v1`
- `architecture.cross_worker_activation_gate_v1`
- `architecture.delegation_dispatch_value_v1`
- `architecture_advisory.block_immutable_message_v1`

Life's current `record_invocation_v1` already uses an empty `search_path`. Preserve that pattern for any SECURITY DEFINER successor function.

## Performance findings

Architecture has 59 unindexed foreign keys and 3 unused indexes according to the current Supabase Performance Advisor. This is consistent with rapid schema accretion. Do not port FK/index topology. Every successor migration must be designed from its live query/write paths and pass current performance/security advisors after deployment.

## Requirement-by-requirement disposition

The 45 legacy requirements reduce to the following current dispositions:

| Legacy requirement | Disposition | Destination / treatment |
|---|---|---|
| REQ-ARCH-001 low-maintenance parallel Life | KEEP/MODIFY | `governance/requirements.json`; current coordination + future runtime |
| 002 single canonical mutable control authority | KEEP | governance protected property |
| 003 prevent incompatible same-resource mutations; permit unrelated parallel work | KEEP | already in `coordination/protocol.json`; future runtime must mirror exact-resource scope |
| 004 unfinished obligations durable with dependencies | KEEP/MODIFY | current continuity/work records; later runtime only for runtime jobs |
| 005 retry/idempotency/stale-generation handling | KEEP | mutation policy + invocation/runtime tests |
| 006 completion requires observable postcondition | KEEP | mutation policy/readback tests |
| 007 failure learning + machine-checkable prevention | KEEP/MODIFY | new failure-learning source policy; minimal runtime ledger later |
| 008 Vince final owner decision maker, not transport | KEEP | governance/authorization policy |
| 009 rich provenance; summaries do not replace evidence | KEEP | provenance/evidence policy |
| 010 current production safety controls binding until replaced | REMOVE as legacy wording / KEEP property | current Build decisions and explicit migration controls |
| 011 preserve properties, not existing mechanisms | KEEP | already current clean-slate decision; retain |
| 012 one authoritative representation per control fact | KEEP | placement/governance; apply aggressively to new design |
| 013 parent/integrator handoff topology | MODIFY | current source coordination/Work capabilities; no generic DB topology graph by default |
| 014 every Life response ends Next step | ALREADY MIGRATED | `continuity/response-contract.json` |
| 015 Architecture Supabase is canonical control plane | REMOVE | superseded by Build/Life split |
| 016 inspect old production without inheriting RC7 | ARCHIVE | historical source-separation evidence only |
| 017 restore parent objective after detour | KEEP/MODIFY | continuity/work selection policy |
| 018 assigned work cannot silently change objective | KEEP | work record / completion contract |
| 019 deterministic continuity reconstruction | ALREADY MIGRATED | `continuity/*` |
| 020 preserve positive verified learning | KEEP | evidence/provenance policy; avoid failure-only memory |
| 021 Project Instructions exact <=8000 candidate check | KEEP current rule | Project Instructions + durable exact candidate artifact when edited |
| 022 dependency freshness after authoritative changes | KEEP/MODIFY | exact dependency/version hashes, not old global graph |
| 023 AI instruction sets cross-review | MODIFY | review policy only for current installed collaborators; no stale collaborator registry |
| 024 generalized dependency coherence | COMBINE with 022 | same dependency policy |
| 025 deterministic POST_CHANGE gate | KEEP/MODIFY | mutation policy + readback/tests; scoped to changed resources |
| 026 deterministic Council escalation | MODIFY | finite review/escalation states; only real independent evidence lanes |
| 027 restated post-change gate | COMBINE with 025 | remove duplicate requirement |
| 028 operational control manual + deterministic gate language | MODIFY | typed JSON schemas/enums and validators; avoid giant meta-manual |
| 029 mutation → control lifecycle audit | KEEP/MODIFY | mutation/control-lifecycle policy; only where controls actually change |
| 030 evolution engine proposes but cannot authorize | KEEP/MODIFY | suggestion/evolution source policy; zero runtime authority |
| 031 owner idea intake finite states | KEEP/MODIFY | optional ideas/evolution registry; no always-on DB subsystem required |
| 032 deterministic PRE_CHANGE gate | KEEP | mutation policy + exact manifest/preconditions |
| 033 machine-readable SELF_MODEL | MODIFY | derive from canonical source manifests; avoid parallel mutable meta table |
| 034 declared change manifest before mutation | KEEP | mutation policy/receipt binding |
| 035 unresolved external fact → research proposal | MODIFY | current mandatory fresh research rules + durable research artifact only when needed |
| 036 compact immutable provenance + full-context archive/readback | KEEP/MODIFY | provenance policy; domain-specific ledgers, not one giant generic graph |
| 037 principles + lineage/property survival on replacement | KEEP | requirements/lineage policy |
| 038 provider capability horizon with rechecks | MODIFY | fresh provider research + source-backed capability record when it changes design |
| 039 per-worker reasoning snapshot/rebase | REPLACE | exact dependency versions/base generation in work record; no 6,995-row reasoning graph |
| 040 must-precede prerequisites/regression lookback | KEEP/MODIFY | dependency graph/work-selection tests |
| 041 Delegation Detection | MODIFY | remove vague gates (`materially better`, `comparably suitable`); finite typed dispatch conditions if needed |
| 042 Live Ledger progress updates | REPLACE | current user-update cadence + durable work state; no separate runtime ledger purely for conversational updates |
| 043 Twenty-Minute Turnover | REMOVE | obsolete provider/time-bound mechanism; current platform behavior governs |
| 044 bare `continue` recovery | COMBINE | continuity bootstrap/current next_action + work-selection policy |
| 045 automatic Suggestion Sweep | MODIFY | non-authoritative optional suggestion/evolution mechanism; do not force noisy global scan |

## Decision disposition

| Legacy decision | Disposition |
|---|---|
| DEC-0001 Architecture project canonical successor | REMOVE; superseded by Build/Life clean successor |
| DEC-0002 many chats, one Supabase control plane | COMBINE; GitHub now owns source coordination, Supabase later owns only runtime state that requires transactions |
| DEC-0003 no second JOB authority; WORK owns collaboration | KEEP property; current source work records already avoid a duplicate source authority |
| DEC-0004 replace Drive lease with server-enforced claims/CAS/idempotency/postconditions | KEEP property; source side already rebuilt in GitHub; runtime side later |
| DEC-0005 Drive is not queue/bus/completion authority | KEEP |
| DEC-0006 do not inherit RC7 | ARCHIVE; covered by current clean-slate decisions |
| DEC-0007 parent orchestrates topology/handoffs | MODIFY to current agent/plugin capabilities and exact work-selection control |
| DEC-0008 every response includes next step | ALREADY MIGRATED |
| DEC-WORKER-PRINCIPAL-BOUNDARY | KEEP/MODIFY; ordinary workers constrained, reviewers advisory, admin access break-glass only |

## Principle disposition

`PRINC-ARCH-EPISTEMIC-INTEGRITY-0001` should survive, but not as a one-row mutable database principle registry. Its core rule—keep observed/retrieved/reported/inferred/unknown/inaccessible/speculation distinct and never let model confidence promote evidence—is already reflected in current Build state classifications.

Destination: add a source-controlled `governance/evidence-policy.json` and keep user-facing state names aligned with `continuity/response-contract.json`.

## Table-by-table migration map

`KEEP` below means keep the protected property, not copy the table. `LATER` means only create a Life runtime table after a live runtime need exists.

| Architecture table | Disposition | Successor destination |
|---|---|---|
| activation_validation_sessions | REMOVE | CI/runtime verification evidence, not persistent generic table |
| change_cycles | COMBINE | mutation manifest/receipt lifecycle |
| change_manifests | KEEP/MODIFY | `governance/mutation-policy.json`; minimal `life.mutation_manifests` later if runtime effects need it |
| control_artifacts | REPLACE | GitHub canonical files + hashes; no duplicate artifact registry by default |
| control_dependencies | MODIFY | exact source dependency declarations/version hashes |
| control_lifecycle_dispositions | MODIFY | source control-lifecycle policy; runtime only if live controls mutate dynamically |
| control_lineage | KEEP/MODIFY | source lineage/provenance; minimal append-only runtime lineage later if needed |
| control_principle_links | REMOVE as table | encode direct requirement/protected-property IDs in source artifacts |
| control_term_usages | REMOVE as table | typed schemas/static validators |
| cross_worker_impacts | MODIFY/LATER | exact resource/dependency impact records only for shared runtime mutation |
| cross_worker_validation_runs | REMOVE | CI/test evidence |
| decisions | COMBINE | `continuity/decisions.jsonl` for adopted Build decisions |
| events | SPLIT | engineering events → `continuity/events.jsonl`; runtime events → domain ledgers only |
| evidence_refs | MODIFY | source evidence references/provenance fields; no standalone table unless reuse proves necessary |
| evolution_candidates | KEEP/MODIFY | source `evolution/` candidate registry later; zero authority |
| execution_claims | SPLIT | GitHub source claims already exist; runtime claims only when external effects require them |
| execution_handoff_validation_runs | REMOVE | tests/CI |
| execution_handoffs | MODIFY | source work record/continuity; runtime handoff only if a real task engine exists |
| external_review_ingress_validation_runs | REMOVE | tests/CI |
| external_review_submission_grants | LATER | authenticated one-time reviewer grants only if external review is activated |
| external_review_submissions | LATER | append-only `life.review_submissions` if activated |
| failure_capture_obligations | COMBINE | failure-learning policy + unresolved finding/work item |
| failure_context_contract_state | REMOVE | derive from policy/versioned schema |
| failure_families | KEEP/MODIFY | source failure registry; migrate selected historical lessons, not old status authority |
| failure_occurrences | KEEP/MODIFY | append-only runtime/source occurrences only when current failure family exists |
| failure_preventions | KEEP | prevention definition + falsification test evidence |
| full_context_records | MODIFY | durable source artifacts for comprehensive audits/failures; avoid generic DB blob table |
| global_governance_surfaces | REPLACE | placement-policy canonical-owner map |
| governed_mutation_input_preflight_validation_runs | REMOVE | tests/CI + mutation receipt outcome |
| language_audit_findings | COMBINE | watchdog/finding registry + semantic-firewall tests |
| meta | REMOVE | no generic mutable meta authority |
| meta_assumptions | REMOVE as table | explicit evidence/assumption fields in owning artifact |
| mutation_receipts | KEEP/MODIFY | minimal append-only runtime `life.mutation_receipts` later; engineering mutations remain Git/GitHub evidence |
| narratives | REMOVE as authority | documentation/audit artifacts only |
| operation_control_bindings | MODIFY | authorization/mutation policy bindings in source |
| operation_log | REPLACE | invocation/mutation domain ledgers; avoid generic duplicate operation log |
| operational_controls | REMOVE empty legacy table | source policies and executable validators |
| operational_definitions | MODIFY | exact enums/schemas local to owning policy; no generic terminology DB unless repeated need proves it |
| principles | COMBINE | requirements/evidence policy source artifacts |
| provenance_spine | KEEP/MODIFY | compact source/runtime provenance fields; avoid overlap with events/operation logs |
| provider_change_receipts | MODIFY | provider-capability/research evidence artifact, only on actual provider-dependent changes |
| reasoning_enforcement_validation_runs | REMOVE | tests/CI |
| reasoning_impact_events | REPLACE | exact dependency version changes scoped to affected work |
| reasoning_rebases | REPLACE | update work base/dependency generations directly |
| reasoning_snapshot_dependencies | REMOVE | replace massive graph with exact dependencies declared by work/control owner |
| reasoning_snapshot_enforcement | REMOVE | derive/enforce from work/dependency contract |
| reasoning_snapshots | REPLACE | work record base SHA/generations/evidence refs |
| requirements | KEEP/MODIFY | new `governance/requirements.json` deduplicated current protected properties |
| research_proposals | MODIFY | durable research artifact only when unresolved fact changes a gate/design |
| resource_claims | SPLIT | current GitHub lock branches for source; Life runtime claims later only for runtime resources |
| results | COMBINE | PR/CI/readback evidence for engineering; typed runtime outcomes for runtime |
| system_meta_state | REMOVE | derive from canonical source/live state |
| turn_red_team_reviews | MODIFY | review policy/evidence; independent review only when it adds a defined evidence class |
| work | REPLACE for source | `coordination/work/*.json`; runtime work table only if Life later needs durable asynchronous job execution |
| work_checkpoints | COMBINE | continuity/work records; durable audit artifact for large analyses |
| work_context_dependencies | MODIFY | exact dependencies in work records/control artifacts |
| work_dependencies | KEEP/MODIFY | source dependency graph/work-selection policy |
| work_resource_scopes | ALREADY MIGRATED concept | exact GitHub resource claims |
| worker_capability_validation_runs | REMOVE | tests/CI |
| worker_execution_capabilities | DEFER | only if direct non-parent worker mutation authority exists |
| worker_execution_capability_packs | DEFER/REMOVE | avoid preset capability bundles until exact live need |
| worker_gateway_operation_receipts | REPLACE | canonical runtime mutation receipt if/when gateway exists |
| worker_signed_operation_receipts | REMOVE now | only if signed-worker design later adopted |
| worker_signing_key_offers | REMOVE now | same |
| worker_signing_keys | REMOVE now | same |

### Views

- `work_ready_v1` / `work_runnable_v1`: **COMBINE/REPLACE** with current deterministic `governance/work-selection-policy.json` + `scripts/select_work.py`. A database view should not become a second source-work authority. If Life later has runtime jobs, implement a separate runtime readiness query with exact typed prerequisites.

### `architecture_advisory.messages`

Do not migrate as control state. If future external reviewers need messages, use the actual connected transport plus a typed append-only review submission/evidence record. Advisory prose remains zero authority.

## Function/trigger migration policy

Do not port 175 functions one by one. They fall into six families:

1. **Scoped mutation/CAS/idempotency/postconditions** → KEEP properties; rebuild a minimal current mutation API.
2. **Work/claim/handoff/runnable/delegation** → source side already replaced by GitHub coordination/work-selection; runtime subset later only if needed.
3. **Reasoning snapshot/rebase/impact graph** → REPLACE with compact exact dependency generations/hashes.
4. **Pre/post-change, deterministic-language, control-freshness validators** → COMBINE into source schemas/tests and a small mutation policy; eliminate duplicate validators and overloaded generations.
5. **Failure/provenance/evolution/provider tracking** → KEEP selected domain records with one canonical owner each; avoid parallel generic ledgers.
6. **Worker gateway/signed worker/external review ingress** → DEFER until live principal/reviewer need; use current MCP/OAuth architecture rather than old GitHub-OIDC Edge gateways.

Trigger lessons to retain: append-only history when immutability is a true invariant; cycle prevention for dependency graphs; postcondition enforcement at the database boundary when the database owns the invariant. Do not copy the legacy trigger topology. The reasoning-enforcement area currently contains duplicate trigger variants, another reason to rebuild rather than transplant.

## Data that should be preserved from Architecture

Preserve **evidence**, not active authority:

- the 45 requirement texts with this audit's disposition mapping;
- the 9 legacy decisions with supersession mapping;
- the epistemic-integrity principle;
- the failure families/occurrences/preventions, especially open/high-recurrence root-cause lessons;
- evolution candidates as historical design candidates, explicitly non-governing;
- final schema/function/trigger/Edge Function inventory and current security/performance advisor findings;
- enough source identifiers to re-read Architecture while it remains available.

Do **not** import old WORK/claim/generation/status rows into Life as current obligations. Do not import old collaborator instruction artifacts as active rules. Do not replay old migration history.

Before Architecture is eventually paused/decommissioned, create a source-controlled evidence snapshot/export sufficient to reconstruct the facts above. Do not delete the project until the successor artifacts and any selected evidence exports have been independently read back.

## Proposed successor files and exact role

These are candidate destinations, not yet adopted control authority merely because this audit proposes them:

- `governance/requirements.json` — deduplicated Life protected properties and exact requirement IDs.
- `governance/evidence-policy.json` — evidence states, provenance requirements, inference/unknown handling.
- `governance/mutation-policy.json` — declared intent, preconditions, authority, idempotency, effect, postcondition/readback, rollback classification.
- `governance/authorization-policy.json` — principal/capability boundaries, admin break-glass boundary, per-effect authorization.
- `governance/provenance-policy.json` — canonical provenance fields and owner per domain; prevents duplicate ledgers.
- `governance/failure-learning-policy.json` — family/occurrence/prevention/recurrence states and falsification evidence.
- `governance/review-policy.json` — advisory review evidence classes and finite escalation states; zero authority from prose.
- `governance/control-lifecycle-policy.json` — replace/retire controls only after protected-property mapping and successor evidence.
- `governance/provider-capability-policy.json` — provider-dependent claims require current source verification; retain only design-affecting capability evidence.

Each file must have a schema plus executable validation/falsification tests before it is allowed to participate in a gate.

## Runtime objects to consider later, not now

Only after the canonical Life MCP endpoint is deployed and an actual runtime effect path requires them:

- `life.mutation_receipts` (append-only, request/invocation bound)
- `life.runtime_resource_claims` (only for conflicting runtime effects, not source code)
- `life.failure_occurrences` / `life.failure_preventions` (only if runtime failure-learning needs structured querying)
- `life.review_submissions` / one-time grants (only if external independent review is activated)
- `life.control_lineage` (only for dynamically mutable runtime controls)

Every such database object must first exist as a GitHub migration plus database tests, per current Life rules.

## Implement-now vs implement-later

### Implement now

1. Preserve this audit and the Architecture source pointer.
2. Add the surviving protected-property/requirement registry in source.
3. Add evidence policy.
4. Add mutation policy (manifest → precondition/authorization → idempotent effect → readback/postcondition → receipt/rollback classification).
5. Add authorization/principal policy.
6. Add failure-learning/provenance policy using one canonical owner per fact.
7. Add falsification tests for the concrete Architecture failures listed above.

### Implement after canonical invocation is live

1. Bind `life.invoke` identity/invocation to any mutation receipt.
2. Add runtime claims only where two authorized invocations can conflict on the same runtime resource.
3. Add review ingress only if a real external reviewer is activated.
4. Add signed-worker principals only if native provider/session identity cannot mechanically bind the external worker.
5. Add structured failure/prevention runtime tables only if source-only failure learning cannot satisfy the active requirement.

Later implementation has a higher migration cost because runtime data may already exist; however installing speculative tables now recreates Architecture's overengineering. The current best trade is source contracts/tests now, stateful runtime tables only at the first proven runtime consumer.

## What should be explicitly removed/not migrated

- Architecture as canonical Life control plane.
- All 140 migrations as a migration chain.
- The 65-table schema wholesale.
- The 175-function surface wholesale.
- the GitHub-OIDC `architecture-gateway` implementation and retired repository identities.
- the current signed-worker gateway as default worker auth.
- anon/authenticated public execution of `archreview_submit_v1`.
- generic mutable `meta`/`system_meta_state` authority.
- old collaborator Project Instruction artifacts (Claude/Grok/Perplexity) as active truth.
- the reasoning snapshot/rebase/dependency graph as implemented.
- global currentness gates that serialize unrelated resources.
- substring/token-presence semantic validators.
- the 20-minute turnover rule and other historical provider-timing mechanisms.
- duplicate generic ledgers for events/operations/provenance/receipts.
- empty/dead tables simply because they exist.
- unindexed FK/index topology.
- RLS-with-no-policy as a default authorization pattern.

## Current platform fit (fresh 2026-09-12 check)

### Supabase Free

Official current Free plan: $0; 2 active projects; 500 MB database/project; 50,000 MAU; 5 GB egress + 5 GB cached egress; 1 GB Storage; 500,000 Edge Function invocations; 2 million Realtime messages; 200 peak Realtime connections. Branching is not included on Free. Architecture (~25.4 MB) and current Life are far below the DB quota; the meaningful constraint is the two-active-project cap. No migration recommendation here requires a paid Supabase feature.

Feature placement:

- Postgres tables/functions/triggers: use only for transactional runtime invariants; available on Free.
- RLS/grants: defense-in-depth for exposed database API surfaces; available on Free.
- Edge Functions: available on Free but **not selected as the canonical Life MCP host**; therefore the old gateways should not be retained merely because the feature is free.
- Branching: not on Free; do not make it a dependency.
- Storage/Realtime/pg_cron: Architecture currently does not use them, so there is nothing to migrate.

Official sources checked: https://supabase.com/pricing, https://supabase.com/docs, database/functions, secure-data/RLS, Edge Functions docs.

### GitHub Free/public repository

Current GitHub Free is $0, supports unlimited public/private repositories, and public-repository standard Actions are free. Rulesets are available on public repositories under GitHub Free; required PRs/status checks and force-push/deletion restrictions fit the current Build design. GitHub Free includes 2,000 private-repository Actions minutes and 500 MB Actions storage, but Build is public, so standard public CI minutes are not billed under the documented rule.

Feature placement: GitHub remains the canonical source/change-review/CI/source-coordination layer. This audit recommends more source policies/tests there, not a second database control plane.

Official sources checked: https://github.com/pricing and current docs for rulesets, Actions billing/usage, and included plan usage.

### Vercel Hobby

Current Hobby is $0 for personal/non-commercial use, includes automatic CI/CD, Fluid compute, 1M function invocations/month, 4 active CPU hours/month, 360 GB-hours provisioned memory/month; Hobby Functions currently default/max at 300 seconds. Hobby cannot buy overage; hitting caps pauses/limits service rather than authorizing paid spend. Current Vercel guidance for MCP uses OAuth 2.1 resource-server semantics and the 2026-07-28 MCP authorization model.

Feature placement: Vercel remains the selected future canonical MCP resource-server host. It replaces the Architecture Edge gateway role; it does not change the current plan until Vince authorizes an exact Vercel target/deployment.

Official sources checked: https://vercel.com/pricing and current Vercel MCP OAuth/Functions guidance.

### OpenAI/ChatGPT capability check

Current OpenAI sources show Plugins as the primary workflow-capability directory for ChatGPT/Codex; plugins can package skills, connected apps, and templates. Connected apps remain separately authorized. GPT-5.6 family/current agent tooling also strengthens the case for keeping provider capabilities outside Life's control authority: model capability can change without changing deterministic authorization semantics.

Current Plugin Directory search confirmed installed Supabase/GitHub/Vercel capabilities are available in this environment. This does not grant those connectors Life runtime control authority.

## Current external/research comparison

Current MCP 2026-07-28 is stateless at the protocol core and hardens OAuth/resource-server authorization. Vercel's current guide emphasizes that the MCP server validates tokens rather than minting them and forbids bearer-token passthrough. This supports the current Build choice to replace the custom Architecture GitHub-OIDC gateway with the selected OAuth resource-server boundary.

Recent 2026 agent-security research independently supports deterministic mediation around model-selected tool actions rather than treating model judgment/tool exposure as authorization. This aligns with the strongest Architecture property: finite, machine-enforced authority at the effect boundary.

Recent Supabase community experience also repeatedly reports schema/migration sprawl, RLS drift, and difficulty auditing current functions/policies once many repair migrations accumulate. Community evidence is anecdotal, but it matches what is directly observable here: 140 migrations, 175 functions, security warnings, and many repair generations. Current community recommendations favor source-controlled migrations/declarative definitions, small focused functions, explicit RLS design, and database-side handling for race-sensitive state.

## KEEP / REPLACE / MODIFY / COMBINE / REMOVE summary

**KEEP:** deterministic authority; exact resource conflict prevention; idempotency; completion postconditions/readback; owner authority boundary; provenance/evidence-state discipline; failure recurrence prevention; declared intent/pre-change/post-change structure; immutable history where required; worker principal boundary; advisory review separation.

**REPLACE:** Architecture canonical control plane; old Edge gateways; reasoning snapshot graph; generic operation/event/meta ledgers; source WORK database; public review RPC exposure; historical turnover/provider mechanisms.

**MODIFY:** failure/evolution engine; review/Council mechanism; control lifecycle; provider capability horizon; external worker authorization; dependency freshness; full-context retention; deterministic language controls.

**COMBINE:** Architecture decisions/requirements with current Build continuity/governance; work/dependencies with GitHub source coordination; event/provenance concepts with domain-specific canonical ledgers; bare-continue/recovery with current bootstrap/work-selection.

**REMOVE:** stale collaborator artifacts, duplicate validators/triggers, empty tables without a current consumer, old project IDs/repo identities, obsolete production references, and old active/open statuses as successor authority.

## Migration order recommended by this audit

1. Preserve the audit/evidence snapshot.
2. Normalize surviving requirements/protected properties into one source registry.
3. Install evidence policy.
4. Install mutation + authorization policy and falsification tests before adding any new runtime mutation surface.
5. Install failure-learning/provenance/control-lifecycle policy with one canonical owner per fact.
6. Continue canonical `life.invoke` implementation on the already selected Vercel + Supabase Auth/Postgres architecture.
7. When first runtime side effect is introduced, add only the minimal transaction/receipt/claim objects needed by that effect.
8. Re-evaluate reviewer/signed-worker mechanisms at the first real external-worker need.
9. After all selected evidence is durably source-controlled and independently read back, pause/decommission Architecture to free the second Supabase active-project slot. Do not delete it before preservation is verified.

## Live Build issue discovered during this audit

A fresh direct read found a machine-state inconsistency unrelated to the old Architecture schema but relevant to safe integration: continuity event E-0087 reports the prior `integration:main` claim was released, while the canonical lock branch `lock/138c728d71ab409c9ab9f7805063b24bebef209ef2f0ffe6db6a1db4263307a9` currently reads `state: ACTIVE` for work `f579e3ce-2ffa-480a-9c1c-9f9d9b9544f7`, lease `e4a2aa10-e135-45e9-b845-5be14df2fcab`, expiring `2026-09-12T15:30:59Z`.

Per current coordination rules, machine lock state outranks prose/events for source coordination. Therefore this audit may be implemented on its claimed work branch, but a PR to main must not be created while that other ACTIVE integration claim remains authoritative. This is exactly the kind of stale-green/control-evidence mismatch the watchdog/coordination system is intended to surface.

## Final recommendation

Use Architecture as a **mine of requirements, failure evidence, and design constraints**, then retire its implementation topology. The successor should be materially smaller in mechanism count even while preserving more of the important behavior: GitHub for source truth/coordination/verification; Vercel for the authenticated MCP front door once authorized; Supabase Postgres for minimal transactional runtime truth; model/plugins for reasoning and access, never control authority.

The highest-risk mistake would be copying the old project because it is already elaborate. The second-highest-risk mistake would be discarding it completely. The right path is selective extraction: preserve the hard-earned invariants and failure lessons, rebuild only the mechanisms current Life actually needs, and force every new control fact to have one canonical owner.
