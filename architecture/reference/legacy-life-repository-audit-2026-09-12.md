# Legacy `Vinanonymous/life` Repository Audit and Salvage Map

**Audit date:** 2026-09-12  
**Artifact purpose:** durable engineering reference for rebuilding useful legacy mechanisms in `Vinanonymous/Build`  
**Life runtime control authority:** **NONE**

## Authority and source-of-truth boundary

This document preserves a comprehensive audit of the predecessor repository so later Life work does not depend on a chat transcript, model memory, or a shortened continuity summary.

It is a **reference and mining map only**. It does not authorize, select, complete, release, mutate, or execute any Life runtime decision. A mechanism receives no preference merely because it existed in the legacy repository or appears in this audit.

The original source remains the authoritative evidence for what the legacy implementation actually contains. Before implementing a salvaged mechanism, re-read the exact original source bytes and compare them against current `Vinanonymous/Build`, current platform capabilities, current Life requirements, and current alternatives.

### Original repository pointer

- Repository: `Vinanonymous/life`
- Repository URL: https://github.com/Vinanonymous/life
- Audited legacy `main`: `c46179c730a5e7b94214433a59bdd3c85d18b31f`
- Legacy open control-input binding branch: `feature/control-input-binding` at `6cc602f2ac18599aa67c0352ce81fbd404dcb40f`
- Legacy open parallel-audit branch: `feature/parallel-audit-coordination-protocol` at `277021436d0fca774112b0ba40d776f0d06b17cd`
- Legacy open invocation branch: `feature/life-invocation-v1-final6` at `7b7f493d224f516a9b1b1bad1345bd0859f1f826`

These references are intentionally retained even if the legacy repository is no longer canonical. If later engineering needs exact implementation detail, revisit the repository rather than treating this document as a byte-for-byte substitute.

## Audit scope

The sweep covered the complete executable surface on legacy `main`, including:

- `.github/workflows/database-ci.yml`
- `contracts/semantic-firewall/control-request.acceptance.json`
- `contracts/semantic-firewall/run_control_request_acceptance.py`
- `contracts/semantic-firewall/contract-reference.acceptance.json`
- `contracts/semantic-firewall/run_contract_reference_acceptance.py`
- `contracts/semantic-firewall/artifact-byte-identity.acceptance.json`
- `contracts/semantic-firewall/run_artifact_byte_identity_acceptance.py`
- `contracts/semantic-firewall/receipt-execution-binding.acceptance.json`
- `contracts/semantic-firewall/run_receipt_execution_binding_acceptance.py`
- `contracts/semantic-firewall/receipt_execution_binding_inner.py`
- `contracts/semantic-firewall/typed-contract-evaluation.acceptance.json`
- `contracts/semantic-firewall/run_typed_contract_evaluation_acceptance.py`
- `coordination/github-audit-predicate.acceptance.json`
- `coordination/run_github_audit_predicate_acceptance.py`
- `supabase/config.toml`
- `supabase/tests/database/00_harness.test.sql`
- legacy README coordination/review protocol

The sweep also covered code that never reached legacy `main` but remained on the three significant open branches listed above: control-input binding, parallel-audit coordination, and the final Supabase Edge `life.invoke` implementation.

## High-level conclusion

The predecessor repository should **not** be migrated wholesale.

Its durable value is concentrated in five categories:

1. **Typed control requests and closed decision vocabularies.**
2. **Exact evidence/input binding and freshness checks.**
3. **Artifact-byte and execution-provenance binding.**
4. **Adversarial falsification tests for forgery, replay, substitution, and malformed data.**
5. **Deterministic engineering-evidence classification that prevents an AI from overlooking already-existing machine-observable evidence.**

The legacy hosting, broad service-role access, GitHub-Issue coordination model, inline embedding path, and prose-oriented orchestration should not be restored.

---

# 1. Semantic Firewall salvage

## 1.1 Closed control-decision universe — KEEP

Legacy control requests used a closed set of ten decision kinds:

- `AUTHORIZATION`
- `ROUTING`
- `PRIORITY`
- `STATE_TRANSITION`
- `COMPLETION`
- `VERIFICATION`
- `ESCALATION`
- `RELEASE`
- `MUTATION`
- `EFFECT_EXECUTION`

This matches the current Life control-authority model and should remain the permanent closed control vocabulary unless a later versioned architecture explicitly changes it.

### Why it matters

A model must not be allowed to create a new pseudo-control type by prose. Every control-bearing decision must resolve to an exact enumerated kind.

**Disposition: KEEP.**

## 1.2 Minimal typed control request — MODIFY

The legacy request was intentionally tiny: an exact `decision_kind` and a UUID contract identifier. It rejected free-text predicates, inline model-authored policy text, unknown decision kinds, malformed identifiers, and extra fields.

This is a strong boundary because it prevents the model from smuggling a new gate into the request itself.

### Missing permanent binding

The request did not yet bind the control decision to the exact:

- subject,
- action,
- scope/effect target.

A valid receipt for one target must not be replayable against a different target that happens to use the same contract.

**Disposition: MODIFY.** Preserve the closed request shape but add exact machine-verifiable subject/action/scope binding.

## 1.3 Strict JSON decoding — KEEP + CONSOLIDATE

The legacy runners repeatedly defended against malformed or ambiguous JSON, including:

- duplicate object keys,
- NaN/Infinity and other non-finite numbers,
- unknown fields,
- wrong primitive types,
- string values masquerading as booleans,
- integer/boolean confusion,
- malformed identifiers,
- missing required fields.

The permanent Build implementation should keep these rejection properties but consolidate them into a common canonical decoder/schema-validation layer instead of duplicating small schema interpreters across many runners.

**Disposition: KEEP + CONSOLIDATE.**

## 1.4 Contract-reference eligibility — KEEP + MODIFY

The legacy contract-reference layer required exact identity for:

- control request,
- control contract,
- decision kind,
- enabled/disabled state,
- contract content hash,
- validator identity/hash,
- evaluator identity/hash,
- validation receipt identity,
- test receipt identity/hash/suite,
- PASS state.

A caller could not merely name a contract and receive authority.

### Permanent improvement

Combine this with exact subject/action/scope and exact trusted input-snapshot binding.

**Disposition: KEEP + MODIFY.**

## 1.5 Artifact byte identity — KEEP

The legacy artifact binder associated each expected role such as `CONTRACT`, `VALIDATOR`, `EVALUATOR`, and `TEST_SUITE` with an exact repository-relative path and independently recomputed SHA-256.

It explicitly rejected:

- wrong hashes,
- wrong paths,
- wrong IDs,
- missing or extra roles,
- absolute paths,
- `..` traversal,
- unsafe `.` components,
- symlinks,
- directories substituted for files,
- missing files.

This is stronger than trusting a filename or Git label.

**Disposition: KEEP.**

## 1.6 Execution provenance / immutable snapshot — KEEP + GENERALIZE

The receipt-execution wrapper is one of the strongest pieces of the old repository.

It:

1. enumerated the complete expected Semantic Firewall source set;
2. rejected unexpected/missing/symlinked members;
3. captured exact source bytes;
4. computed a SHA-256 manifest;
5. copied those bytes into a private snapshot;
6. made the snapshot read-only;
7. launched the evaluator using the captured bytes rather than whatever happened to be on disk afterward;
8. rechecked the manifest before and after evaluation.

The acceptance corpus included a source-replacement race: observe implementation A, replace the working-tree file with implementation B, and prove the receipt was still produced from captured A.

**Disposition: KEEP + GENERALIZE.** Use the pattern for deterministic evaluator/CI provenance where exact executed bytes matter.

## 1.7 Receipt falsification and replay defenses — KEEP

The inner receipt tests tried to forge or alter:

- artifact hashes,
- artifact IDs,
- receipt IDs,
- stdout hashes,
- stderr hashes,
- exit codes,
- runtime metadata,
- artifact paths,
- evidence hashes,
- envelope copies,
- missing/extra envelope entries,
- decision kinds.

It also tested cross-decision replay such as reusing evidence associated with `AUTHORIZATION` as `MUTATION` or `EFFECT_EXECUTION` evidence.

A particularly valuable property is rejection of a **self-consistent forgery**: changing a claimed hash and every dependent claimed field still cannot pass when the authoritative evaluator regenerates evidence from trusted source bytes.

**Disposition: KEEP.** This corpus should be ported as permanent falsification tests.

## 1.8 Receipt identity is not authentication — MODIFY

The legacy implementation derived deterministic receipt identifiers from hashes. That is useful for content identity and replay detection, but it is not proof that a trusted authority issued the receipt.

Similarly, the old inner runner required an environment marker such as `LIFE_SF_PROVENANCE_STAGE` before execution. The repository correctly treated that as a narrow fail-closed invocation marker rather than cryptographic caller authentication.

### Permanent improvement

Authoritative production receipts need a trusted issuer/storage boundary. A model or arbitrary process that can construct a structurally valid JSON object must not be able to mint an authoritative PASS.

**Disposition: MODIFY.** Keep deterministic content identity, but establish authority from trusted service execution and protected receipt persistence/consumption.

---

# 2. Control-input binding from legacy PR #19

The most valuable unfinished legacy branch is `feature/control-input-binding` at `6cc602f2ac18599aa67c0352ce81fbd404dcb40f`.

It should be re-read directly before permanent Semantic Firewall implementation.

## 2.1 Exact typed input snapshot — KEEP + STRENGTHEN

PR #19 modeled contract inputs with fields including:

- exact input name,
- finite state (`KNOWN` / `UNKNOWN`),
- `source_type`,
- `source_ref`,
- `source_version`,
- `observed_at`,
- closed value type,
- typed value,
- value hash.

The evaluator required the supplied input-name set to equal the contract-required set exactly. No missing inputs and no extra semantic inputs were accepted.

It also bound:

- the control contract hash,
- each input value hash,
- the complete input-snapshot hash.

A changed contract or changed evidence snapshot therefore requires reevaluation.

**Disposition: KEEP + STRENGTHEN.**

## 2.2 `KNOWN` / `UNKNOWN` fail-closed state — KEEP

Unknown evidence did not become PASS through prose or model inference.

**Disposition: KEEP.**

## 2.3 Numeric evidence freshness — KEEP

The legacy design used exact numeric `max_age_seconds` values rather than qualitative gates such as “recent enough.” It rejected future observations and stale observations outside the contract's exact age threshold.

This directly fits Life's requirement-precision rules.

**Disposition: KEEP.**

## 2.4 Closed typed values — KEEP + EXPAND ONLY BY VERSION

The branch used closed value categories such as string, integer, boolean, and string-set values. It rejected type coercion.

Future value types should be introduced only through versioned contracts with deterministic canonicalization rules.

**Disposition: KEEP.**

## 2.5 Critical weakness: provenance claims were still self-described — STRENGTHEN

PR #19 could prove that an input structurally declared `source_type`, `source_ref`, and `source_version` correctly.

It could **not** prove that the data actually came from the system named by those fields.

For example, a structurally valid `CURRENT_TOOL_OBSERVATION` was still a typed claim about provenance unless a trusted mechanism created it.

### Permanent Build requirement

Introduce **trusted evidence adapters**. The adapter performs the GitHub/Supabase/Vercel/Life-state read and emits the typed observation. The planner/model may request evidence but cannot manufacture authoritative observations.

The evaluator consumes only observations whose issuer/adapter identity is itself machine-verifiable.

**Disposition: KEEP the input model; STRENGTHEN provenance issuance.**

---

# 3. Typed contract evaluator

Legacy `typed-contract-evaluation` deliberately supported only a fixture-oriented `COMPLETION` contract with an `ALL_TRUE` operator and exact named boolean inputs.

It distinguished `COMPLETE`, `INCOMPLETE`, and `REJECT`, declared `TEST_FIXTURE_ONLY` as its source, and declared no side effects.

The important part is not the hard-coded operator. The important part is the fail-closed pattern:

- exact decision kind,
- exact contract version,
- exact operator,
- exact input names,
- exact types,
- unsupported source rejected,
- extra fields rejected,
- side effects forbidden during evaluation.

**Disposition: MODIFY.** Generalize through a reviewed closed operator library and versioned contract schemas. Do not turn an LLM expression evaluator into the permanent control engine.

---

# 4. Missing legacy control-plane pieces that still need building

Legacy Issue #16 identified major gaps that were never completed. The audit confirms these are still useful requirements to consider for current Q-0002.

## 4.1 Mandatory control-path invocation — BUILD

A perfect evaluator is irrelevant if application code can bypass it.

For every one of the ten control decision kinds, the permanent architecture must make the Semantic Firewall/dispatcher the only executable route into a controlled effect.

Direct planner-to-effect calls must be structurally unavailable, not merely discouraged by instructions.

## 4.2 Exact subject/action/scope binding — BUILD

A PASS must authorize exactly the object/action/scope evaluated. It cannot be replayed against a different object or broader effect.

## 4.3 Trusted live-state/input provenance — BUILD

Inputs need machine-verifiable acquisition from trusted evidence adapters rather than caller-supplied provenance labels.

## 4.4 Postcondition-bound COMPLETION / VERIFICATION — BUILD

A pre-execution authorization receipt is not evidence that the effect happened correctly. Completion and verification require post-effect evidence bound to the exact effect instance and expected postconditions.

## 4.5 Authoritative receipt issuance/storage/consumption — BUILD

The permanent system needs a trusted receipt boundary rather than an environment-variable provenance marker.

---

# 5. Recommended permanent control flow

The strongest architecture derived from the legacy work and current Build direction is:

1. **Model/planner proposal** — zero control authority.
2. **Typed control request** — exact decision kind, contract, subject, action, and scope.
3. **Contract resolver** — resolves one enabled exact contract version and exact evaluator identity.
4. **Trusted evidence adapters** — perform current external/internal reads and issue typed observations.
5. **Bound evidence snapshot** — exact finite input set, source identity/version, timestamps, values, and hashes.
6. **Deterministic evaluator** — closed operators only; no open-ended LLM judgment.
7. **Evaluation receipt** — binds request, subject/action/scope, contract, evidence snapshot, evaluator build, result, and execution identity.
8. **Mandatory dispatcher** — independently verifies receipt eligibility/consumability.
9. **Exact effect adapter** — executes only the effect bound to that receipt.
10. **Post-effect evidence** — used by later COMPLETION / VERIFICATION contracts.

No retrieval score, model confidence, review comment, prose approval, or issue label becomes control authority anywhere in this chain.

---

# 6. Engineering-evidence salvage

The legacy GitHub audit code belongs in Build/watchdog engineering assurance, not in the deployed Life runtime control plane.

## 6.1 Complete GitHub audit evidence surface — KEEP FOR ENGINEERING

The old evaluator used a closed evidence surface:

- PR review submissions,
- top-level PR conversation comments,
- inline review comments.

It retrieved the complete surface before classification rather than semantically searching only for comments that “look like” audit output.

That prevents an AI from incorrectly declaring an audit absent because its own retrieval missed the exact record.

## 6.2 Finite audit states — KEEP FOR ENGINEERING

The legacy evaluator used finite states such as:

- `SATISFIED`
- `MISSING`
- `STALE`
- `SUPERSEDED`
- `CHANGES_REQUIRED`
- `INVALID`

This is stronger than asking a model to decide whether “the review seems current.”

## 6.3 Malformed target audit attempts fail conservatively — KEEP

A malformed record that genuinely claims the target audit run should not be silently ignored just because another valid-looking record exists.

## 6.4 Parallel audit branch PR #24 — MODIFY + COMBINE

`feature/parallel-audit-coordination-protocol` at `277021436d0fca774112b0ba40d776f0d06b17cd` establishes useful engineering rules:

- one exact completion-bearing audit run is selected by predicate, not by a prose purpose label;
- a second-opinion ACCEPT cannot substitute for the selected completion audit;
- a blocking finding from any independent audit must be dispositioned;
- completion-bearing auditor verification is tied to the accepted head SHA;
- verification on the wrong head does not satisfy the gate.

These are useful quality-assurance invariants.

They must remain **engineering evidence only**. An AI review cannot become runtime `AUTHORIZATION`, `MUTATION`, `RELEASE`, or `EFFECT_EXECUTION` authority.

---

# 7. Legacy GitHub coordination system

The predecessor README implemented temporary coordination with GitHub Issues, workstream revisions, finite predicates, conflict surfaces, expiring claims, handoff/block/complete states, and a planned retirement gate into later WORK infrastructure.

Current `Vinanonymous/Build` now has a stronger source-coordination mechanism using exact work branches, deterministic lock branches, exact resource keys, generations, lease IDs, current-base validation, and protected-main integration.

Therefore:

- old Issue-based claim authority — **REMOVE**;
- four-hour expiring lease concept — **KEEP CONCEPT, current Build implementation wins**;
- exact conflict surfaces — **KEEP concept through current resource keys**;
- retirement-to-WORK idea — **reconsider later only for deployed Life work orchestration, not Git engineering claims**.

Do not reintroduce GitHub comments/Issues as machine source-control authority.

---

# 8. CI and reproducibility salvage

Legacy CI did one thing better than current Build CI: it pinned external dependencies.

It pinned:

- `actions/checkout` to a full commit SHA;
- `supabase/setup-cli` to a full commit SHA;
- Supabase CLI to exact version `2.117.0`.

Current Build Issue #12 already records the need to restore immutable CI dependency resolution, including `actions/setup-python` and a policy test that rejects mutable tags or `latest` tool versions.

**Disposition: KEEP and restore through Issue #12.** Do not blindly copy old SHAs; select current reviewed versions and pin them immutably.

Legacy pgTAP usage and clean local database reconstruction remain useful and should continue.

Current Build Issue #15 is also a prerequisite before treating new control schemas as strongly enforced: full Draft 2020-12 schema validation must actually execute in CI rather than relying only on selected hand-written field checks.

---

# 9. Legacy `life.invoke` branch PR #25

The legacy invocation branch is useful primarily for failure cases and invariants, not for its hosting architecture.

Branch/head to revisit:

`feature/life-invocation-v1-final6` — `7b7f493d224f516a9b1b1bad1345bd0859f1f826`

## 9.1 Good invariants to keep

The old implementation correctly distinguished:

- the exact `life.invoke` tool argument from the upstream ChatGPT UI message;
- canonical invocation evidence from derived embeddings;
- recording from authorization;
- canonical source-event durability from optional downstream derivation success.

It explicitly gave embeddings zero control authority.

The current Build architecture already preserves these principles and improves the database boundary.

## 9.2 Host architecture — REPLACE

The legacy branch used a Supabase Edge Function as the MCP front door.

Current Life decision D-0015 selects Vercel Functions as the remote Streamable HTTP MCP/OAuth resource-server boundary, Supabase Auth as authorization server, and Supabase Postgres as the exact ledger.

Do not transplant the old Edge Function host.

## 9.3 Broad service-role database access — REPLACE

The legacy Edge runtime used broader Supabase service credentials and direct client operations than the current architecture should allow.

Current Build's dedicated `life_runtime_v1` role plus a narrowly granted `SECURITY DEFINER` recording function is the preferred boundary.

## 9.4 Protected-resource metadata/OAuth challenge tests — PORT

The old CI tested:

- health boundary,
- protected-resource metadata,
- advertised authorization server,
- unauthenticated MCP call returning 401,
- `WWW-Authenticate` metadata linkage.

Port the equivalent acceptance tests to the Vercel implementation rather than copying the hosting code.

## 9.5 Public origin vs internal service origin — PORT REGRESSION

The legacy implementation initially risked advertising an internal Supabase URL rather than the public resource origin. The later branch introduced a separate public origin.

Permanent test: all advertised OAuth/MCP resource metadata must use the externally reachable canonical resource URL, never an internal service URL.

## 9.6 U+0000 handling — PORT REGRESSION

The old branch fixed U+0000 handling for the main request text but retained an unresolved review finding for optional `client_thread_ref` flowing into PostgreSQL text.

Permanent rule: every text value that can reach PostgreSQL must have an explicit exact Unicode/NUL contract. Do not validate only the primary message field.

## 9.7 Bearer scheme parsing — PORT REGRESSION / REMOVE MANUAL PARSER

The final legacy branch still had an unresolved review finding because its Bearer scheme recognition was case-sensitive.

Permanent rule: use a vetted standards-correct authorization implementation. Do not revive the hand-written parser. Add protocol-level regression coverage.

## 9.8 Canonical event survives derived embedding failure — KEEP

The old function caught embedding failure so it did not destroy the already-valid canonical invocation.

Permanent invariant: failure of any derived representation, semantic indexing step, enrichment, or context projection must not erase, rewrite, or falsify the canonical source event.

## 9.9 Inline embedding generation — REMOVE FROM INVOCATION V1

The legacy branch generated `gte-small` 384-dimensional embeddings during canonical invocation.

Current design deliberately separates canonical invocation from later context/retrieval processing.

**Disposition: REMOVE from canonical invocation v1.** A later retrieval pipeline may derive embeddings keyed to the exact invocation ID.

## 9.10 OAuth hosted desired-state manifest — COMBINE

The legacy branch kept a versioned desired-state representation for hosted Auth settings.

The general idea is useful: deployment-relevant hosted configuration should have a source-controlled expected state and direct live readback where the connected platform exposes it.

Do not treat an expected-state file as proof the hosted configuration is actually live.

---

# 10. RLS finding: do not copy legacy RLS mechanically

Legacy PR #25 used RLS/forced-RLS around its invocation tables.

Current Build uses the private `life` schema and a narrower function/grant boundary. At the 2026-09-12 audit point, direct authorized reads showed no direct table privileges for `anon`, `authenticated`, or `service_role` on `life.oauth_callers_v1` or `life.invocations`; `life_runtime_v1` had EXECUTE on `life.record_invocation_v1` rather than direct table DML.

The generic Supabase table inspector still reports RLS-disabled warnings for these tables. That generic warning should be surfaced when encountered, but it should not replace inspection of the actual exposed schemas and grants.

Permanent database tests should prove the intended access boundary explicitly. If a later design exposes direct table access through the Data API, introduce and test the required RLS policies as part of that versioned change.

Do not copy `ENABLE RLS` / `FORCE ROW LEVEL SECURITY` solely because the predecessor used it.

---

# 11. Salvage disposition summary

| Legacy mechanism | Disposition | Build destination |
| --- | --- | --- |
| Ten closed control kinds | KEEP | Permanent control plane |
| Minimal typed control request | MODIFY | Add exact subject/action/scope |
| Reject prose predicates/model output | KEEP | Control request boundary |
| Contract-reference eligibility | KEEP + MODIFY | Contract resolver |
| Strict JSON parsing | KEEP + CONSOLIDATE | Shared canonical decoder/schema layer |
| Artifact-byte identity | KEEP | Evaluator/contract provenance |
| Traversal/symlink/path defenses | KEEP | Artifact loader |
| Immutable execution snapshot | KEEP + GENERALIZE | Evaluator/CI provenance |
| Pre/post manifest equality | KEEP | Evaluator execution boundary |
| Receipt envelopes | KEEP + REDESIGN | Trusted receipt service/storage |
| UUID/hash-derived receipt IDs | MODIFY | Identity only, not authority |
| Self-consistent forgery tests | KEEP | Permanent falsification corpus |
| Cross-decision replay tests | KEEP | Permanent falsification corpus |
| PR #19 input snapshots | KEEP + STRENGTHEN | Trusted evidence layer |
| `KNOWN` / `UNKNOWN` | KEEP | Evidence state |
| Exact input-set equality | KEEP | Contract evaluator |
| Numeric `max_age_seconds` | KEEP | Evidence freshness |
| Future-observation rejection | KEEP | Evidence validation |
| Typed values | KEEP + versioned expansion | Evidence schema |
| Trusted evidence issuance | BUILD | Evidence adapters |
| Fixture-only `ALL_TRUE` evaluator | MODIFY | Closed evaluator/operator library |
| Mandatory dispatcher/control path | BUILD | Runtime control plane |
| Postcondition-bound completion | BUILD | Post-effect verification |
| GitHub audit evidence parser | COMBINE | Watchdog/engineering assurance |
| Parallel-audit exact-head rules | MODIFY + COMBINE | Engineering assurance |
| Old Issue-based work claims | REMOVE | Current Build lock protocol wins |
| Immutable CI pins | KEEP / RESTORE | Issue #12 |
| Full schema enforcement prerequisite | IMPLEMENT | Issue #15 |
| pgTAP database testing | KEEP | Database CI |
| Supabase Edge MCP host | REPLACE | Vercel resource server |
| Supabase Auth OAuth | COMBINE | Current invocation architecture |
| MCP OAuth metadata/challenge tests | PORT | Vercel acceptance tests |
| Manual Bearer parser | REMOVE | Standards-compliant auth library |
| Broad service-role access | REPLACE | Dedicated runtime role/function |
| Exact invocation ledger | KEEP + current Build version | Supabase private schema |
| Invocation-time embedding | REMOVE | Later retrieval pipeline |
| Vectors have zero control authority | KEEP | Permanent architecture invariant |

---

# 12. Permanent falsification corpus to port

When the Build Semantic Firewall is implemented, preserve tests for at least:

1. duplicate JSON keys;
2. NaN/Infinity/non-canonical numbers;
3. missing required fields;
4. unexpected fields;
5. wrong primitive types;
6. boolean/integer confusion;
7. malformed IDs;
8. unknown decision kinds;
9. inline free-text predicates;
10. model-authored predicate text;
11. disabled/wrong contract identity;
12. contract hash mismatch;
13. evaluator/validator/test-suite identity mismatch;
14. missing/extra artifact roles;
15. absolute/path-traversal/symlink/directory substitution;
16. source replacement after observation;
17. forged artifact hash;
18. forged artifact/receipt ID;
19. forged stdout/stderr hash;
20. forged exit code/result/runtime metadata;
21. missing/extra receipt envelopes;
22. cross-decision replay;
23. `UNKNOWN` evidence attempting PASS;
24. missing required input;
25. extra semantic input;
26. source-type mismatch;
27. stale observation;
28. future-dated observation;
29. value hash mismatch;
30. contract/input snapshot changed without rebinding;
31. subject/action/scope replay;
32. direct effect-adapter bypass attempt;
33. receipt issued by an untrusted issuer;
34. receipt for one effect consumed for another;
35. postcondition verification using evidence from the wrong effect instance.

The purpose is not to copy every legacy test implementation. The purpose is to retain the adversarial properties those tests discovered.

---

# 13. Implementation sequence for Build

This audit does not change `continuity/current.json.next_action`. When Q-0002/control-plane work becomes selected under the deterministic work-selection mechanism, the recommended dependency order is:

1. **Source trust first.** Complete immutable CI dependency pinning from Issue #12.
2. **Schema enforcement.** Complete actual Draft 2020-12 artifact validation from Issue #15.
3. **Semantic Firewall/control contracts.** Introduce the ten control kinds, exact target binding, contract resolver, and closed schemas.
4. **Trusted evidence adapters.** Rebuild PR #19's typed/fresh input snapshot around observations issued by trusted adapters.
5. **Artifact/evaluator provenance.** Port byte identity, immutable snapshot, manifest, and forgery tests.
6. **Authoritative receipts.** Establish trusted issuance/persistence/consumption; deterministic IDs alone are insufficient.
7. **Mandatory dispatcher.** Make bypass structurally impossible for controlled effect adapters.
8. **Post-effect completion/verification.** Bind evidence to the exact effect instance and postconditions.
9. **Engineering audit assurance.** Port GitHub exact-evidence-surface/stale/superseded logic into watchdog/repository assurance, physically separate from runtime authority.
10. **Vercel invocation acceptance.** When the selected Vercel endpoint is built, port the legacy OAuth metadata, external-origin, 401, text-safety, auth-standard, and canonical-event-survival regression cases.

Implement-now advantage: defining the permanent evidence/receipt/dispatcher boundary before many Life capabilities exist avoids later migration of every effect adapter into a new control path.

---

# 14. Things explicitly not to restore

Do not restore merely because they existed:

- legacy repository as canonical Build authority;
- GitHub Issues/comments as executable work/control authority;
- Supabase Edge Function as selected v1 MCP front door;
- broad Supabase `service_role` runtime access;
- manual Bearer parser;
- invocation-time embedding generation;
- vector similarity as any control gate;
- prose approvals as runtime evidence;
- fixture-only semantic maturity/readiness labels;
- environment-variable markers as production authentication;
- RLS configuration without re-evaluating current schema exposure/grants;
- old code wholesale without current clean-slate comparison.

---

# 15. How future workers should use this artifact

For any legacy-salvage question:

1. Read this artifact to locate the candidate mechanism and prior disposition.
2. Re-open `Vinanonymous/life` at the cited legacy commit/branch and inspect the exact source involved.
3. Re-read current `Vinanonymous/Build` equivalents and current open issues.
4. Re-run the required current platform/research checks.
5. Compare the candidate against every current Life requirement and alternative.
6. Reclassify it as `KEEP`, `REPLACE`, `MODIFY`, `COMBINE`, or `REMOVE`; the disposition in this document is not irrevocable.
7. If implementation is selected, create new Build-native source/tests rather than importing the predecessor tree wholesale.
8. Preserve useful adversarial tests even when the implementation mechanism is replaced.

## Staleness rule

This audit describes the legacy repository as observed on **2026-09-12** at the exact heads listed above. If `Vinanonymous/life` changes, or if current Build/platform architecture changes, the original source and current verified state take precedence over this document.

This document remains a durable map of what was found and why it was considered valuable; it is not a claim that every recommendation remains selected forever.
