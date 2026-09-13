# Life Reliability & Recovery Architecture v1

Status: SOURCE_ONLY architecture and implementation contract. Runtime control authority: NONE.

This document is the durable synthesis of the historical Life incident/failure corpus and the current Build architecture. It specifies the target reliability subsystem and how it combines with existing Life mechanisms. It does not itself authorize runtime actions, mutations, completion, release, retries, compensation, or effect execution.

## 1. Purpose

Life needs one subsystem that can answer, from durable evidence:

1. What obligation or operation was in progress?
2. What was attempted?
3. What was observed by the caller?
4. What external effect actually occurred, if that can be established?
5. Which invariant or postcondition is unsatisfied, failed, or unknown?
6. What recovery action is permitted by exact policy?
7. What evidence proves the recovery result?
8. What parent/root goal must resume afterward?
9. What reusable lesson or recurrence-prevention obligation remains?

The subsystem is not a generic error logger. It is an obligation/effect/evidence/recovery architecture.

## 2. Corpus-derived design requirements

The historical corpus repeatedly demonstrated these distinct failure mechanisms. The architecture MUST keep them separate rather than collapsing them into one `FAILURE` state:

- recognition without execution;
- execution without persistence;
- persistence without activation;
- source retrieval without governing influence;
- correct result produced through the wrong mechanism;
- implementation success without full-artifact invariant preservation;
- tool success/error response that does not establish the real external effect;
- timeout/no-result with an ambiguous external effect;
- occurrence repair without recurrence prevention;
- verifier failure or a verifier testing the wrong property;
- diagnosis revision after Vince correction or later evidence;
- successful child work without parent/root restoration;
- stale current-state representation;
- source-role or identity mismatch despite correct content;
- scope/precedence errors where a broad rule executes before a narrower applicable boundary;
- summary loss where final conclusions survive but the evidence and reasoning history needed to reevaluate them do not;
- a rule surviving in specification while failing in live execution;
- migration preserving a mechanism incompletely;
- conflicting evidence that cannot be truthfully collapsed into one winner.

These observations imply six hard architectural rules:

1. History is append-only evidence; diagnoses are revisions, not rewrites.
2. Caller result state and effect state are separate dimensions.
3. Output correctness and mechanism-execution correctness are separate dimensions.
4. Occurrence repair and recurrence prevention are separate obligations.
5. Every recovery detour remains bound to a stable parent/root obligation.
6. Derived summaries/indexes never upgrade themselves into primary evidence or control authority.

## 3. Placement: GitHub + Supabase + runtime

### GitHub — versioned definition/source plane

GitHub owns:

- subsystem contracts and schemas;
- invariant catalog;
- operation/effect contracts;
- postcondition contracts;
- deterministic recovery policy;
- projection logic;
- validators;
- database migrations and pgTAP tests;
- sanitized regression fixtures derived from real incidents;
- engineering repair records;
- implementation history and protected CI.

The public repository MUST NOT contain private full-fidelity conversation transcripts, personal screenshots, private Drive documents, or sensitive incident evidence.

### Supabase — private exact evidence/state plane

The non-public `life` Postgres schema owns:

- exact occurrence identities;
- append-only reliability events;
- evidence metadata and private object references;
- operation attempts;
- effect-state observations;
- postcondition observations;
- diagnosis revisions;
- repair obligations;
- deterministic recovery decisions and their input evidence;
- discrepancy/conflict records;
- current projections derived from append-only records.

Large/private evidence bytes belong in private Supabase Storage only when Life deliberately imports them. Existing Drive artifacts may remain external source-of-record objects with exact Drive IDs and provenance rather than being duplicated automatically.

### Runtime — deterministic evaluator/executor

The deployed Life runtime eventually:

- writes pre-effect attempt records;
- dispatches effects only after the applicable control gate passes;
- performs authoritative readback;
- writes postcondition/effect observations;
- invokes deterministic recovery evaluation;
- schedules/executes only the exact disposition returned by policy;
- returns work selection to the parent/root graph after recovery.

No prose, model confidence, semantic similarity score, Issue label, review, approval sentence, or diagnosis text can satisfy a Life runtime control decision.

## 4. Canonical identities

Every object uses a stable server-generated UUID unless a current Life identity already exists.

Required identities:

- `invocation_id` — canonical Life invocation when available;
- `goal_id` / `root_goal_id` — stable semantic goal identity;
- `work_id` — engineering/runtime execution attempt identity where applicable;
- `occurrence_id` — one observed reliability occurrence;
- `operation_id` — one logical state-changing or externally observable operation;
- `attempt_id` — one dispatch attempt for an operation;
- `evidence_id` — one preserved evidence object or evidence reference;
- `proposition_id` — one exact claim extracted/represented for evidence reconciliation;
- `diagnosis_revision_id` — one immutable diagnosis revision;
- `obligation_id` — one repair/verification/restoration obligation;
- `recovery_decision_id` — one deterministic recovery evaluation result;
- `invariant_id` — stable versioned invariant identity;
- `postcondition_id` — stable versioned postcondition identity;
- `operation_contract_id` — stable versioned effect contract identity.

Semantic goal identity MUST NOT be inferred from execution attempt identity. A lease takeover, retry, new worker, new thread, or replacement branch can change execution identity without silently creating a new root goal.

## 5. Evidence model

### Evidence objects

Each evidence object records at least:

- `evidence_id`;
- `source_class`;
- `source_system`;
- external/source object ID when available;
- source URI when applicable;
- capture/observed timestamp;
- MIME/type;
- byte length when available;
- cryptographic digest when bytes are available;
- privacy class;
- immutable/volatile classification;
- whether live re-verification is required;
- storage/reference locator;
- derivation parent IDs when derived;
- `runtime_control_authority = NONE` unless a separately defined trusted control-evidence issuer creates a typed machine-verifiable control record.

Initial source classes:

- `IMMUTABLE_REPOSITORY`;
- `LIVE_GITHUB`;
- `LIVE_SUPABASE`;
- `LIVE_VERCEL`;
- `VINCE_DIRECTIVE`;
- `VINCE_OBSERVATION`;
- `TOOL_REQUEST`;
- `TOOL_RESULT`;
- `UI_TRACE`;
- `RESEARCH_SOURCE`;
- `EXTERNAL_DOCUMENT`;
- `MODEL_RESPONSE`;
- `DERIVED_SUMMARY`;
- `INFERRED`.

### Evidence roles

The same source document can support different propositions with different roles. Therefore role is stored on a link/proposition record, not only on the file.

Initial roles:

- `USER_TRIGGER`;
- `FAILED_RESPONSE`;
- `TOOL_INPUT`;
- `TOOL_RESULT`;
- `USER_CORRECTION`;
- `DIRECT_OBSERVATION`;
- `AUTHORITATIVE_READBACK`;
- `DIAGNOSIS_SUPPORT`;
- `DIAGNOSIS_REFUTATION`;
- `REPAIR_ATTEMPT`;
- `POSTCONDITION_PROOF`;
- `REGRESSION_PROOF`;
- `PARENT_CONTEXT`;
- `MECHANISM_TRACE`;
- `TIMING_TRACE`;
- `SOURCE_ROLE_PROOF`;
- `CONFLICTING_EVIDENCE`.

### Evidence conflicts

Contradictory evidence is preserved in a typed discrepancy object. A discrepancy records the conflicting proposition/evidence IDs and a state from:

- `OPEN`;
- `RESOLVED_BY_NEW_EVIDENCE`;
- `RESOLVED_BY_VINCE_CORRECTION`;
- `RESOLVED_BY_AUTHORITATIVE_READBACK`;
- `UNRESOLVED`.

No record is deleted merely because another source supersedes its interpretation.

## 6. Occurrence and event ledger

`life.reliability_occurrences` stores immutable occurrence identity and stable scope fields only.

`life.reliability_events` is append-only and is the canonical chronological history.

Suggested event types:

- `OCCURRENCE_OPENED`;
- `EVIDENCE_ATTACHED`;
- `PROPOSITION_RECORDED`;
- `DISCREPANCY_OPENED`;
- `DISCREPANCY_RESOLVED`;
- `DIAGNOSIS_REVISION_RECORDED`;
- `OBLIGATION_CREATED`;
- `OPERATION_PREPARED`;
- `ATTEMPT_DISPATCHED`;
- `ATTEMPT_RESULT_RECORDED`;
- `EFFECT_OBSERVED`;
- `POSTCONDITION_OBSERVED`;
- `RECOVERY_EVALUATED`;
- `RECOVERY_DISPATCHED`;
- `RECOVERY_VERIFIED`;
- `RECURRENCE_TEST_LINKED`;
- `PARENT_RESTORATION_ELIGIBLE`;
- `PARENT_RESTORED`;
- `OCCURRENCE_RESOLVED`;
- `OCCURRENCE_REOPENED`.

Current-state views are deterministic projections over append-only rows; they are not independently authored truth.

## 7. Result state versus effect state

Caller/attempt result state uses the existing Life-compatible enumeration:

- `PENDING`;
- `SUCCESS`;
- `FAILURE`;
- `NO_RESULT`;
- `TIMEOUT`;
- `UNKNOWN`.

External effect state is evaluated independently:

- `NOT_EVALUATED`;
- `NO_EFFECT_VERIFIED`;
- `EFFECT_VERIFIED`;
- `PARTIAL_EFFECT_VERIFIED`;
- `EFFECT_UNKNOWN`.

A `SUCCESS` response MUST NOT automatically map to `EFFECT_VERIFIED`.
A `FAILURE`, `NO_RESULT`, or `TIMEOUT` MUST NOT automatically map to `NO_EFFECT_VERIFIED`.

The architecture therefore supports the critical case:

`attempt_result = TIMEOUT` + `effect_state = EFFECT_VERIFIED`.

## 8. Verification dimensions

Verification is dimension-specific. Required dimensions are represented separately:

- `OUTPUT_CORRECTNESS`;
- `MECHANISM_EXECUTION`;
- `SOURCE_ROUTE`;
- `EFFECT_STATE`;
- `POSTCONDITION_STATE`;
- `PROTECTED_INVARIANT_PRESERVATION`;
- `RECURRENCE_PREVENTION`;
- `SPECIFICATION_SURVIVAL`;
- `LIVE_ENFORCEMENT`;
- `PARENT_RESTORATION`.

Each observation records one of:

- `PASS`;
- `FAIL`;
- `UNKNOWN`;
- `NOT_RUN`.

A PASS in one dimension has zero automatic effect on any other dimension.

This prevents a correct final answer from proving the intended retrieval mechanism ran, a successful write from proving the whole artifact remains valid, or a repaired occurrence from proving recurrence prevention.

## 9. Operation contracts and write-ahead effect journal

Every state-changing operation exposed to autonomous execution receives a versioned `operation_contract_id` declaring:

- exact operation kind;
- exact target identity requirements;
- preconditions;
- required authorization/control evidence references;
- idempotency mechanism, if any;
- retry budget as an integer;
- retryable result/effect-state combinations;
- readback procedure;
- postcondition IDs;
- compensation contract ID or null;
- maximum attempt count;
- terminal/fail-closed states.

Before dispatch of a protected state-changing effect, Life MUST durably persist an `OPERATION_PREPARED`/attempt row with the operation ID, attempt ID, target, contract version, idempotency key when defined, parent obligation, and intended postconditions.

If that pre-effect record cannot be durably written, the protected effect is not dispatched.

## 10. Deterministic recovery kernel

Recovery is a deterministic evaluator. Model judgment can propose evidence or diagnosis but cannot select a control disposition.

Closed recovery dispositions:

- `ACCEPT_EFFECT`;
- `VERIFY_EFFECT`;
- `RETRY`;
- `COMPENSATE`;
- `QUARANTINE`;
- `ESCALATE`;
- `ABORT`;
- `RESUME_PARENT`.

Required rules:

1. `EFFECT_UNKNOWN` forbids `RETRY` for any operation that can create duplicate external effects unless its versioned contract proves retry idempotency for that exact operation.
2. `TIMEOUT`, `NO_RESULT`, or `UNKNOWN` after dispatch defaults to `VERIFY_EFFECT` when an authoritative readback contract exists.
3. `RETRY` is legal only when every exact contract predicate passes and retry count is below the integer budget.
4. No retry policy means retry budget zero.
5. `PARTIAL_EFFECT_VERIFIED` may select `COMPENSATE` only when an exact versioned compensation contract exists and its preconditions pass; otherwise select `QUARANTINE` or `ESCALATE` according to the operation contract.
6. `ACCEPT_EFFECT` requires required postconditions to pass, not merely a transport/API success code.
7. Every recovery decision stores the exact policy version and evidence IDs evaluated.

## 11. Obligation model

A reliability occurrence can create multiple independent obligations. Initial exact classes:

- `OCCURRENCE_REPAIR`;
- `RECURRENCE_PREVENTION`;
- `EVIDENCE_RECOVERY`;
- `EFFECT_RECONCILIATION`;
- `VERIFIER_REPAIR`;
- `SPECIFICATION_REPAIR`;
- `LIVE_ENFORCEMENT_REPAIR`;
- `PARENT_RESTORATION`;
- `LESSON_PROMOTION`.

Obligation state:

- `OPEN`;
- `BLOCKED_RESOURCE`;
- `BLOCKED_AUTHORIZATION`;
- `BLOCKED_COST`;
- `BLOCKED_PLATFORM`;
- `EXECUTING`;
- `VERIFYING`;
- `SATISFIED`;
- `REJECTED_NOT_APPLICABLE`.

A blocker preserves the obligation; clearing the exact blocker returns it to `OPEN`/selectable state through deterministic work selection.

## 12. Diagnosis revisions

Diagnosis is evidence, not control authority.

`life.diagnosis_revisions` is append-only. Each revision records:

- occurrence ID;
- predecessor revision ID or null;
- proposer class;
- diagnosis text/typed candidate class;
- supporting evidence IDs;
- refuting evidence IDs;
- certainty state;
- recorded timestamp;
- supersession reason when a later revision exists.

The system MUST be able to represent:

`diagnosis A -> Vince correction -> evidence refutes A -> diagnosis B -> later readback modifies B`.

Historical diagnosis A remains queryable.

## 13. Parent/root restoration

Every occurrence/repair obligation created during active work records `root_goal_id` and `parent_goal_id` when available.

Reliability work can preempt execution only under current deterministic selection rules. Completing the repair does not select unrelated backlog work. After the recovery postconditions pass, the subsystem emits `PARENT_RESTORATION_ELIGIBLE`. The work selector then reevaluates live state and returns to the nonterminal parent/root before unrelated work is eligible.

The reliability subsystem does not itself invent routing authority.

## 14. Existing Life mechanisms: disposition

### KEEP + COMBINE

- `governance/root-cause-repair-policy.json`: becomes the engineering recurrence/root-cause layer above reliability evidence.
- `continuity/checkpoint-policy.json`: checkpoints reference occurrence/operation/attempt/evidence IDs instead of duplicating full incident narratives.
- `governance/work-selection-policy.json`: interrupted/repair obligations hydrate from reliability state and keep deterministic precedence.
- source coordination v3, isolated work branches, component/shared-external claims, required validation, Merge Queue and merge-group validation.
- Semantic Firewall direction: typed semantic/control input before deterministic control evaluation.
- Issue #15 schema enforcement: reliability schemas join full Draft 2020-12 validation.
- Issue #18/#21 provenance and resume semantics.
- Issue #49 verified-defect repair lifecycle.
- Issue #55 durable reusable lessons.
- Issue #59 parent/root goal identity.
- Issue #61 deduplicate/combine/dependency consolidation.

### MODIFY

- Root-cause repair records reference `occurrence_id`, `obligation_id`, `invariant_id`, and verification evidence instead of independently restating incidents.
- Checkpoints carry compact references plus required live-hydration fields, not private full-fidelity evidence.
- Watchdog detects exact versioned/live mismatches; it is not a generic LLM judge of every response.
- Continuity current state becomes projection/summary; volatile runtime reliability state remains in Supabase and requires current reads.

### REPLACE

- Generic mutable `failure_status` as canonical history -> append-only events + deterministic projections.
- Blind retry -> verify-before-retry/reconcile-before-retry.
- Summary-only incident records -> evidence graph + compact projections.
- GitHub Issue as incident database -> private reliability ledger; Issues remain visibility/projection only.

### REMOVE

- One monolithic failure taxonomy as a runtime gate.
- Model-selected retry/compensation without exact policy.
- Any rule that treats transport success as proof of postcondition success.
- Any rule that treats answer equality as proof that the intended mechanism executed.
- Any mechanism that overwrites a prior diagnosis or conflicting source to manufacture a clean history.
- Every-turn generic watchdog judgment as a mandatory detector.

## 15. Detection/intake

Occurrence creation may be triggered by exact machine signals:

- required CI/check failure;
- versioned schema/invariant rejection;
- authoritative live mismatch;
- versioned falsification failure;
- attempt result `FAILURE`, `NO_RESULT`, `TIMEOUT`, or `UNKNOWN`;
- postcondition `FAIL` or `UNKNOWN` after required evaluation;
- Semantic Firewall rejection;
- exact control/invariant violation.

A Vince correction, model self-report, Issue, review, or external research item may create an occurrence/lesson candidate and attach evidence. It does not become a VERIFIED runtime defect/control state without the exact applicable evidence contract.

## 16. Data model target

Initial Postgres objects in private `life` schema:

- `reliability_occurrences`;
- `reliability_events`;
- `reliability_evidence`;
- `reliability_evidence_links`;
- `reliability_propositions`;
- `reliability_discrepancies`;
- `diagnosis_revisions`;
- `repair_obligations`;
- `effect_operations`;
- `effect_attempts`;
- `effect_observations`;
- `postcondition_observations`;
- `recovery_decisions`;
- optional `historical_source_links` for corpus import provenance.

Initial deterministic read models/views:

- `unresolved_occurrences_v1`;
- `unknown_effects_v1`;
- `open_repair_obligations_v1`;
- `parent_restoration_pending_v1`;
- `postcondition_gaps_v1`;
- `recurrence_by_invariant_v1`;
- `verification_failures_v1`;
- `repair_effectiveness_v1`.

The first implementation MUST work without `pgmq`, `pg_cron`, or `vector`.

## 17. Privacy and retention

Because the authorized GitHub repository is public:

- private incident evidence is forbidden in repository source;
- sanitized regression fixtures MUST remove private names, conversations, screenshots, and unrelated personal content;
- Supabase tables remain in non-public `life` schema;
- private Storage buckets are used only when source bytes are intentionally imported;
- external Drive references can remain references with exact provenance instead of being copied;
- raw secrets, bearer tokens, OAuth access tokens, passwords, and private keys are never reliability evidence payloads;
- evidence metadata may store a redacted/hardened identifier or digest when the original object cannot be safely retained.

## 18. Platform fit as of 2026-09-13

### Supabase Free — KEEP as evidence/state plane

Verified current project: `jnenguxodtgwbskhdsxt`, Postgres 17.6, healthy, two `life` tables, zero Edge Functions, no `pgmq`, `pg_cron`, or `vector` extension installed.

Current official Free limits include 500 MB database size, 1 GB file storage, 5 GB uncached egress + 5 GB cached egress, 50,000 MAU, and 500,000 Edge Function invocations. Free projects can pause after one week of inactivity. Development Branching is not included in Free; the connected cost surface reports a metered hourly branch cost, so production schema work stays serialized through the existing Supabase production claim unless Vince authorizes a paid branch later.

Supabase Queues (`pgmq`) and Cron (`pg_cron`) are platform-available candidates for later async enrichment/maintenance, but v1 does not depend on them.

### GitHub Free — KEEP as source/test/integration plane

The authorized repository is public. Standard GitHub-hosted Actions are free for public repositories. Current GitHub Free standard-runner concurrency is 20 jobs, and public repositories can use repository rulesets. Existing Life Merge Queue + required `validate` + `merge_group` validation remain the protected integration path.

### Vercel Hobby — COMBINE only as future runtime transport

The host class remains selected for canonical invocation, but no exact Life Vercel target is authorized. Hobby is capped rather than pay-as-you-go; current Functions default/max duration on Hobby is 300 seconds under Fluid compute. Vercel Queues provides at-least-once delivery, idempotency keys, visibility timeouts and automatic redelivery, while Workflow provides durable step execution/retries. They remain reevaluation candidates for orchestration, not canonical reliability evidence authority. No Vercel mutation is authorized by this architecture.

### OpenAI agents/plugins — executor/integration candidates, not authority

Current OpenAI Agents API provides managed long-running agent sessions/orchestration and context management; current ChatGPT Plugins/Apps expose connected systems. These can later act as executors/adapters. Life reliability state remains provider-independent and cannot depend on one vendor's opaque execution history as its only evidence source.

## 19. Research basis

Current external research reinforces the corpus findings:

- ESAA (arXiv:2602.23193): validated structured events + deterministic orchestration + append-only/projected state for agent traceability/replay.
- Microsoft AgentRx (2026): diagnosis from execution trajectories using invariants, critical-step localization and auditable evidence logs.
- Current production community reports repeatedly identify lost state, retries causing duplicate side effects, ambiguous timeout outcomes, and log archaeology as operational failures; these are treated as practitioner evidence, not authority.
- Current Vercel and Supabase queue/workflow documentation reinforces idempotency, durable state, redelivery and visibility-timeout concerns.

## 20. Non-goals for v1

v1 does not:

- classify every incident into a permanent universal taxonomy;
- use embeddings/semantic similarity as control evidence;
- copy the complete private Drive corpus into GitHub;
- infer hidden model chain-of-thought;
- require queues, cron, vectors, Datadog, PostHog, or another observability vendor;
- replace the Semantic Firewall;
- replace goal/work selection;
- replace source coordination;
- create a Vercel target;
- create a paid Supabase branch;
- grant runtime authority to this architecture document.

## 21. Completion boundary for the subsystem

The subsystem is LIVE only when all of these exact conditions pass:

1. GitHub contracts/schemas/migrations/tests are protected-integrated to `main`.
2. Required schema + semantic validators pass.
3. Supabase migration is applied under the global production claim and read back.
4. Append-only protections and privilege boundaries pass pgTAP/live verification.
5. Operation/effect journal is wired into the deployed Life effect path.
6. Deterministic recovery evaluator is wired into that path.
7. At least one controlled ambiguous-effect test proves verify-before-retry behavior.
8. At least one controlled partial-effect test proves fail-closed recovery.
9. A diagnosis-correction test proves history is preserved rather than overwritten.
10. A verifier-defect test proves verifier repair is independently falsified.
11. A child-repair test proves parent/root restoration before unrelated work.
12. Historical corpus reference import proves original source IDs/provenance survive without copying private evidence into public source.
13. Protected integration and post-deployment authoritative readback pass.

Until all applicable conditions pass, state must be reported as SOURCE_ONLY, TESTED, NOT_RUN, or an exact combination; never LIVE by prose.
