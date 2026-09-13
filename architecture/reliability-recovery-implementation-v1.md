# Life Reliability & Recovery v1 — Implementation Plan

Status: SOURCE_ONLY plan. Runtime control authority: NONE.

Companion architecture: `architecture/reliability-recovery-v1.md`.

This plan turns the selected Reliability & Recovery architecture into a staged implementation without creating a parallel lifecycle beside existing Life defect repair, learning, goal identity, work selection, checkpoints, Semantic Firewall, or source coordination.

## 1. Build strategy

Build in vertical slices. Every slice must preserve these rules:

- version database/control changes in GitHub before remote application;
- use exact schemas and closed enums for gates;
- preserve append-only evidence/history;
- keep private evidence out of the public repository;
- separate result state from effect state;
- separate occurrence repair from recurrence prevention;
- bind recovery to a stable parent/root goal;
- require authoritative readback before verified completion;
- use current GitHub Merge Queue and required `validate` integration;
- do not add paid infrastructure without Vince authorization;
- do not require Supabase Queues, Cron, vectors, Vercel Queues, or an observability vendor for v1.

The implementation must converge with existing Issue #49/#55/#59/#61 work rather than create another dispatcher, goal system, lesson system, or repair registry.

## 2. Target source tree

Proposed source layout after implementation:

- `architecture/reliability-recovery-v1.md`
- `architecture/reliability-recovery-implementation-v1.md`
- `reliability/spec.json`
- `reliability/invariants.json`
- `reliability/operation-catalog.json`
- `reliability/postconditions.json`
- `reliability/recovery-policy.json`
- `reliability/schema/*.schema.json`
- `reliability/tools/validate_reliability.py`
- `reliability/tools/project_reliability.py`
- `reliability/tests/test_reliability_contracts.py`
- `reliability/tests/test_recovery_policy.py`
- `reliability/tests/test_projection_replay.py`
- `reliability/regressions/` for sanitized non-private fixtures
- `supabase/migrations/<generated>_life_reliability_v1.sql`
- `supabase/tests/database/life_reliability_v1_test.sql`

Exact filenames for migrations are created by the current Supabase migration tool/CLI at implementation time; this plan deliberately does not invent a migration timestamp.

## 3. Phase 0 — Source contract and consolidation

Goal: make one authoritative source contract before database or runtime work.

### Work

1. Create `reliability/spec.json` with subsystem identity, authority boundary, exact event types, exact verification dimensions, exact obligation classes, result/effect state enums, and the closed recovery dispositions.
2. Create Draft 2020-12 schemas for every source artifact.
3. Add all new schemas to the Issue #15 full-schema-enforcement path rather than adding another partial validator.
4. Cross-link, do not duplicate:
   - root-cause repair policy;
   - problem/lesson intake;
   - goal/root identity;
   - work selection;
   - checkpoint policy;
   - Semantic Firewall contracts after migration.
5. Define stable IDs for invariants, postconditions and operation contracts.
6. Add a compatibility map for current Life interruption states and root-cause repair states.

### Falsification

Tests must reject:

- unknown enum values;
- missing parent/root identity where the contract requires one;
- an operation contract with no effect-readback rule for a state-changing effect unless it explicitly declares `READBACK_UNAVAILABLE` and the corresponding fail-closed disposition;
- retry policy with no numeric budget;
- compensation policy with no named contract;
- verification objects that attempt to project one dimension's PASS onto another;
- evidence records granting runtime authority through prose fields.

### Exit

Phase 0 is `SOURCE_ONLY + TESTED` only after PR validation, merge-group validation, merge, and post-merge `main` validation. No Supabase state changes.

## 4. Phase 1 — Private Postgres evidence ledger

Goal: establish durable exact occurrence/evidence history before attaching it to effects.

### Tables

#### `life.reliability_occurrences`

Stable identity/scope only:

- `occurrence_id uuid primary key`;
- `schema_version smallint`;
- `opened_at timestamptz` database-generated;
- nullable `invocation_id`;
- nullable `root_goal_id`;
- nullable `parent_goal_id`;
- nullable `work_id`;
- `origin_class` closed enum/domain;
- `subject_kind` closed enum/domain;
- `subject_id text`;
- no mutable canonical status field.

#### `life.reliability_events`

Append-only chronology:

- `event_id uuid primary key`;
- `occurrence_id` FK;
- `event_type` closed enum/domain;
- `recorded_at` database-generated;
- `actor_class` closed enum;
- `payload jsonb` validated by event-type function/contract;
- `source_build_sha text` where runtime source is known;
- immutable after insert.

#### `life.reliability_evidence`

- `evidence_id uuid primary key`;
- `source_class`;
- `source_system`;
- external object identity fields;
- observed/captured timestamp;
- MIME type;
- byte length;
- SHA-256 when bytes are available;
- privacy class;
- volatility class;
- live-verification-required boolean derived from source class;
- storage kind + locator;
- nullable derivation parent.

#### `life.reliability_evidence_links`

Many-to-many role assignment:

- occurrence/event/proposition target;
- evidence ID;
- exact evidence role;
- optional byte/line/range locator;
- unique composite constraint preventing duplicate links.

#### `life.reliability_propositions`

Exact claim-level representation:

- proposition ID;
- occurrence ID;
- normalized typed subject/predicate/object or closed proposition kind + typed payload;
- provenance state;
- currentness/valid-time scope where applicable.

#### `life.reliability_discrepancies`

- discrepancy ID;
- involved proposition/evidence IDs;
- typed discrepancy kind;
- exact state;
- resolution event ID when resolved;
- no destructive overwrite of either side.

#### `life.diagnosis_revisions`

Append-only diagnosis history with predecessor, support/refutation evidence, proposer class and certainty state.

### Database protections

- private `life` schema only;
- no `anon`/`authenticated` table access;
- runtime role receives no direct UPDATE/DELETE on ledger history;
- narrowly scoped `SECURITY DEFINER` functions only when required, empty fixed `search_path`, schema-qualified objects, `PUBLIC` EXECUTE revoked;
- append-only triggers/permissions for immutable history;
- check constraints for enums and identifier formats;
- foreign keys for lineage;
- no bearer token or secret storage.

### Tests

pgTAP must prove:

- append-only rows reject update/delete through runtime role;
- invalid enum/state rejected;
- dangling evidence/occurrence refs rejected;
- same source object may support multiple proposition roles;
- discrepancy preserves both sides;
- a diagnosis revision cannot mutate its predecessor;
- runtime role cannot bypass intended write functions;
- `PUBLIC`, `anon`, and `authenticated` do not gain accidental access.

### Application

1. Acquire `external:supabase:jnenguxodtgwbskhdsxt`.
2. Confirm migration source/tests are already on protected-integrated GitHub `main`.
3. Apply one forward migration; never rewrite already-applied history.
4. Run security/performance advisors.
5. Read back tables, constraints, functions, privileges and test-relevant invariants.
6. Release claim only after checkpoint/readback requirements pass.

No paid Supabase development branch is used; current connected cost evidence shows branches are metered.

## 5. Phase 2 — Deterministic projections

Goal: current state is derived, not manually authored.

Create security-invoker/private views or exact SQL functions for:

- unresolved occurrences;
- open obligations;
- unknown effects;
- verification gaps by dimension;
- discrepancies;
- parent restoration pending;
- recurrence by invariant;
- repair effectiveness.

Replay/property tests must prove that the same ordered event set produces the same projection and that adding a later diagnosis revision never changes historical event bytes.

Do not make projections the new history source. Rebuildability from append-only evidence is mandatory.

## 6. Phase 3 — Obligation layer and integration with existing repair/lesson/goal systems

Goal: one lifecycle, not several overlapping queues.

### Integrate Issue #49 / root-cause repair

A verified engineering defect produces or resolves to exactly one `RECURRENCE_PREVENTION`/`OCCURRENCE_REPAIR` obligation identity and one existing canonical repair work identity. `governance/root-cause-repairs.json` references reliability IDs; it does not copy private evidence.

### Integrate Issue #55 durable lessons

Reusable learning maps to `LESSON_PROMOTION`. Its durable outcome still uses the existing typed lesson mechanism. The reliability ledger preserves the observation/evidence lineage; lesson intake owns promotion into future work.

### Integrate Issue #59 parent/root goals

Every created repair/reconciliation obligation carries stable root/parent identity. Recovery completion emits eligibility to return; the goal/work selector owns actual routing.

### Integrate Issue #61 dedupe/combine

Before a new repair/lesson work identity is independently admitted, exact canonical identity/consolidation runs. Semantic similarity can nominate candidate overlaps only.

### Integrate #18/#21

Vince-personally-verified observations retain their own provenance class and can establish user-authorized design requirements while remaining distinct from independently verified external facts. Resume cues cannot create effect, ownership, or completion evidence by themselves.

## 7. Phase 4 — Operation catalog and write-ahead effect journal

Goal: make ambiguous external effects recoverable.

Implement one operation class first before generalizing. Choose a low-risk Life-owned mutation whose authoritative readback is deterministic.

Each `operation_contract` declares:

- target identity schema;
- required control decision/evidence IDs;
- state-changing flag;
- idempotency key derivation;
- dispatch adapter ID;
- response/result mapping;
- readback adapter ID;
- postcondition IDs;
- retry budget;
- retry predicates;
- compensation contract or null;
- terminal failure disposition.

`effect_operations` stores logical operation identity.
`effect_attempts` stores every dispatch attempt.

The runtime transaction order is:

`CONTROL_PASS -> PREPARED_DURABLY -> DISPATCH -> RESULT_RECORDED -> READBACK -> EFFECT_STATE -> POSTCONDITIONS -> RECOVERY_EVALUATION`.

Protected effects cannot jump from control PASS straight to dispatch if the write-ahead journal failed.

## 8. Phase 5 — Effect readback and postconditions

Goal: establish what happened, separately from what the caller returned.

Implement adapters that return one effect state only:

- `NO_EFFECT_VERIFIED`;
- `EFFECT_VERIFIED`;
- `PARTIAL_EFFECT_VERIFIED`;
- `EFFECT_UNKNOWN`.

Store each readback as evidence, including authoritative target object identity, observed time and exact fields checked.

Postconditions are independently evaluated by ID. An API 200/success result never marks postconditions PASS.

Tests include:

- success response + missing target state;
- timeout + target state present;
- failure response + target state present;
- partial mutation;
- delayed visibility returning UNKNOWN before later VERIFIED observation;
- wrong-target success.

## 9. Phase 6 — Recovery kernel

Goal: turn exact observations into exact next action.

Implement deterministic pure-function evaluation over:

- operation contract version;
- result state;
- effect state;
- postcondition states;
- attempt count;
- idempotency evidence;
- compensation availability;
- exact blocker/control states.

Output exactly one disposition or an exact invalid-policy failure.

Falsification matrix must cover every `(result_state, effect_state)` combination relevant to state-changing operations. Required safety cases:

- timeout + unknown effect cannot blind-retry;
- no result + effect verified accepts effect only when postconditions pass;
- partial effect cannot retry as though no effect occurred;
- retry limit cannot be exceeded;
- retry without idempotency when duplicates are possible is rejected;
- compensation without a versioned contract is rejected;
- changing the detector/policy to make a test green requires independent falsification.

## 10. Phase 7 — Work selection and parent restoration

Goal: recovery becomes automatic without hijacking the semantic root goal.

Integrate exact open obligations into deterministic work selection:

- unresolved interrupted operation/effect reconciliation keeps current precedence;
- verified repair obligations outrank ordinary feature work according to the canonical repair policy;
- exact resource intersection controls parallel dispatch;
- a recovery child remains a child of the stable root;
- `PARENT_RESTORATION_ELIGIBLE` does not itself authorize routing; it supplies typed evidence to the goal/work selector;
- unrelated backlog is ineligible until parent/root terminal or an exact authorized root transition occurs.

Tests cover interruption, resource blocking, takeover/retry, nested repair, verification child, terminal cleanup and redispatch.

## 11. Phase 8 — Historical corpus reference import

Goal: make old incidents queryable without destroying their provenance or leaking them into public source.

### First import mode: references only

Index:

- Drive file/folder ID;
- title;
- MIME type;
- original created/modified timestamps when available;
- corpus/folder classification;
- incident/failure IDs already present in source records;
- relation to later summary/audit records;
- privacy class;
- source-of-record locator.

Do not copy bytes yet.

### Optional later byte preservation

Only if Vince selects it:

- download original bytes from authorized source;
- compute SHA-256 over original bytes;
- store in a private Storage bucket with a content-addressed path;
- preserve original Drive identity/URI and digest;
- never delete or silently replace the original Drive source merely because a copy exists.

### Import tests

- original and derived summary are different objects;
- a derived summary cannot become primary evidence solely from import;
- conflicts survive import;
- Vince corrections are linked without erasing earlier assistant interpretations;
- missing bytes remain `EXTERNAL_REFERENCE`, not falsely `ARCHIVED`.

## 12. Phase 9 — Automatic occurrence intake

Goal: recognized failures enter the system without requiring a conversational promise.

Initial machine triggers:

- required CI/check failure;
- schema/invariant validator failure;
- authoritative live mismatch;
- versioned falsification failure;
- protected attempt `FAILURE/NO_RESULT/TIMEOUT/UNKNOWN`;
- required postcondition `FAIL/UNKNOWN`;
- Semantic Firewall rejection.

Candidate-only triggers:

- Vince correction;
- Vince observation;
- model self-report;
- Issue/review/comment;
- research finding.

Candidate-only sources can persist evidence and nominate a problem/lesson, but cannot mint a runtime verification/control PASS.

Deduplication uses stable operation/invariant/goal identifiers before admitting new work.

## 13. Phase 10 — Optional asynchronous enrichment

Only after core v1 is live and measured.

Candidate Supabase Queues uses:

- evidence enrichment;
- historical import batching;
- sanitized regression candidate generation;
- analytics aggregation;
- noncritical reclassification proposals.

Critical pre-effect journaling, control evaluation and authoritative readback remain synchronous/fail-closed; they do not move behind a queue.

Supabase Cron may later run exact housekeeping/projection verification jobs. It is not a reasoning engine.

`pgmq` and `pg_cron` are currently not installed, so adding either requires a versioned migration/test + production claim + readback.

## 14. Phase 11 — Observability and dashboards

Core telemetry is derived from the reliability ledger itself:

- open occurrence count by exact state;
- unknown-effect count;
- time from occurrence open to occurrence repair;
- time to recurrence prevention;
- retry counts by operation contract;
- duplicate-effect prevention events;
- verifier failures;
- diagnosis-revision count;
- parent restoration latency;
- recurrence by invariant;
- unresolved discrepancies.

PostHog/Datadog/other observability products may receive derived telemetry later. They never become the only canonical evidence store.

## 15. Cutover rules

There must be no long-lived dual authority.

1. Existing checkpoint/root-cause/problem-intake artifacts continue to operate until their reliability integration is tested and protected-integrated.
2. New reliability tables start as evidence-only/source of richer provenance.
3. Work selection consumes reliability obligations only after selector integration tests pass.
4. Effect execution consumes the write-ahead journal only after the first operation adapter's end-to-end test passes.
5. Old duplicated failure fields are deprecated only after deterministic equivalence/replacement is proven.
6. Historical files remain history; do not rewrite old migrations/incident records.
7. GitHub Issues remain human-visible projections, never runtime authority.

## 16. Migration/duplication cost of delaying pieces

### Build now

These should be designed/source-versioned together because splitting them creates later schema churn:

- occurrence/event/evidence identity;
- result/effect separation;
- verification dimensions;
- obligation identity;
- diagnosis revisions;
- parent/root references;
- operation/postcondition contract IDs.

### Can wait

- queues;
- cron;
- vector/semantic clustering;
- external observability vendor;
- private Storage copy of historical Drive bytes;
- advanced automated incident clustering;
- Vercel Queues/Workflow integration.

If these later features are added, they consume the canonical ledger rather than requiring a new reliability data model.

## 17. Security model

- private schema by default;
- no Data API exposure required for core ledger;
- least-privilege dedicated runtime function access;
- no broad `service_role` credential in public/client runtime;
- no secrets/tokens in evidence payloads;
- views are `security_invoker` or kept private/revoked;
- `SECURITY DEFINER` only for narrow required write boundaries with fixed empty search path and PUBLIC EXECUTE revoked;
- every database mutation runs Supabase security/performance advisors and direct privilege readback;
- user/private evidence never enters public CI fixtures.

## 18. Exact implementation acceptance suite

The overall project cannot be marked LIVE until automated tests prove at least:

1. append-only event history cannot be rewritten by runtime role;
2. diagnosis revision preserves earlier wrong diagnosis;
3. conflicting evidence persists until a typed resolution event;
4. correct output does not imply mechanism PASS;
5. success response does not imply effect PASS;
6. timeout with verified effect does not retry;
7. timeout with unknown non-idempotent effect cannot retry;
8. verified no-effect + allowed idempotent operation can retry within exact budget;
9. partial effect fails closed or uses exact compensation;
10. occurrence repair does not auto-satisfy recurrence prevention;
11. verifier repair requires independent falsification;
12. specification PASS does not auto-satisfy live-enforcement PASS;
13. blocked obligation survives thread/work interruption;
14. duplicate/combined problem identity cannot create competing repair work;
15. child repair returns to parent/root before unrelated backlog;
16. historical Drive references preserve source IDs and derived/source roles;
17. private evidence is absent from public repository fixtures;
18. Supabase runtime privilege boundary rejects direct history mutation;
19. protected GitHub validation and merge-group validation pass;
20. post-deployment authoritative Supabase/runtime readback passes.

## 19. Rollback and failure handling during build

Before runtime cutover, rollback is source/database-forward only:

- Git source can be reverted through a new protected PR;
- already-applied database migrations are not edited; use a forward corrective migration;
- if a reliability migration applies partially/ambiguously, treat it as an interrupted protected mutation, reread production state, record UNKNOWN where evidence is insufficient, and reconcile before another attempt;
- if runtime integration produces ambiguous side effects, disable the new adapter through its exact versioned control/config mechanism and preserve evidence; do not delete the ledger to make the state look clean.

## 20. Recommended implementation order

1. Finish/merge current lifecycle and parent-goal work that this architecture depends on; do not fork a competing lifecycle.
2. Integrate Issue #15 schema enforcement if still nonterminal.
3. Merge Reliability source contract/schemas/tests.
4. Merge Supabase migration + pgTAP tests in source.
5. Apply/read back private evidence ledger under production claim.
6. Build deterministic projections.
7. Link root-cause repair + lesson intake + goal graph to reliability IDs.
8. Implement one write-ahead operation adapter.
9. Implement effect readback/postcondition evaluator.
10. Implement recovery kernel + full falsification matrix.
11. Integrate work selection and parent restoration.
12. Import historical corpus in reference-only mode.
13. Enable automatic occurrence intake.
14. Evaluate Queues/Cron only after measurements show a need.
15. Evaluate external observability only as a derived consumer.

## 21. Current platform constraints that affect execution

As of 2026-09-13 direct authorized reads show:

- Supabase Life project is healthy on Postgres 17.6;
- only two current `life` tables exist;
- `record_invocation_v1` exists;
- zero Edge Functions are deployed;
- `pgmq`, `pg_cron`, and `vector` are not installed;
- no exact Life Vercel target is authorized;
- exact `life.invoke` is not verified live;
- GitHub `Protect-main` currently requires PR + `validate` + Merge Queue; the live ruleset reports `strict_required_status_checks_policy=false`, so older continuity statements claiming strict=true are stale and must not be used as current evidence.

This plan therefore creates no direct Supabase/Vercel mutation now. The first remote database work begins only after versioned migration/tests are on protected-integrated main and the exact Supabase production claim is held.

## 22. Persistence and ownership

This plan and its companion architecture are versioned source artifacts. They are durable engineering design, not thread memory.

Future workers must still reevaluate them under Life's clean-slate rule, fresh platform research, current corpus evidence and current live system state. Prior selection does not make any mechanism immune to KEEP/REPLACE/MODIFY/COMBINE/REMOVE reevaluation.
