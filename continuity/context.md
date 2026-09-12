# Life Continuity Context

## Purpose and authority

This file is the detailed narrative half of Life's continuity bundle. It exists so a fresh AI thread can reconstruct the engineering situation without relying on ChatGPT memory, prior-chat summaries, or Vince repeating the project.

This file has **zero Life runtime control authority**. Exact current state is represented in `continuity/current.json`; typed decision history is in `continuity/decisions.jsonl`; typed operational history is in `continuity/events.jsonl`; live external facts must be re-read from authorized systems.

## Core objective

Life is being built from first principles as a durable personal AI system. It must retrieve the right context, distinguish context from control, preserve exact state where exactness is required, recover across AI threads, and execute effects only through machine-verifiable control.

A governing design phrase is:

**Structure what must be exact. Vectorize what only needs to be discoverable by meaning.**

Semantic/vector search may retrieve candidate information. It does not establish truth, currentness, identity, authorization, routing, completion, release, mutation permission, or effect execution.

## Clean-slate rule

Existing work has no architectural privilege because it exists, was approved, was implemented, was proposed, was planned, or was previously recommended. Every candidate must be compared against Life requirements and current alternatives. Decisions use KEEP / REPLACE / MODIFY / COMBINE / REMOVE.

An earlier implementation phase got ahead of architecture. Useful concepts may survive, but there is no wholesale migration rule.

## First runtime event

Life runtime architecture begins with: **a user invokes Life**.

The canonical entry tool is `life.invoke`. Its v1 source architecture is selected and versioned, but the Project Instructions require the tool to be treated as READY only when current authorized-system reads show a deployed Life MCP endpoint and the exact tool `life.invoke`. That condition is not satisfied, so canonical invocation remains `NOT_RUN`.

The selected sequence is:

1. An MCP caller invokes `life.invoke`.
2. The remote MCP endpoint authenticates the caller at an OAuth 2.1 resource-server boundary.
3. Life validates the closed tool input and records an exact canonical invocation entry.
4. The recorded text provenance is `MCP_TOOL_ARGUMENT`; it is not claimed to be a machine-verified copy of the original ChatGPT user message.
5. Later context processing may derive embeddings or other retrieval representations keyed back to the exact invocation record.
6. Semantic retrieval may discover candidates, but candidate information must resolve to authoritative exact records before it becomes current fact.
7. Runtime control decisions use exact machine-verifiable evidence and deterministic evaluation.
8. Effects proceed only through later applicable control mechanisms.

## Canonical invocation v1 selection

Decision `D-0015` selects a combined architecture:

- **Vercel Functions**: remote Streamable HTTP MCP transport and OAuth resource-server boundary;
- **Supabase Auth**: OAuth 2.1 authorization server and identity provider;
- **Supabase Postgres** in project `jnenguxodtgwbskhdsxt`: exact append-only invocation ledger;
- **GitHub `Vinanonymous/Build`**: source, tests, CI, engineering history, and source coordination only;
- embeddings/vector retrieval: outside canonical invocation v1.

The Vercel host class is selected, but no exact Life Vercel project is authorized. Vercel deployment remains `NOT_RUN` until Vince authorizes an exact target.

The versioned source contract is:

- `architecture/canonical-invocation-v1.md`;
- `contracts/life.invoke.contract.json`;
- `contracts/life.invoke.input.schema.json`;
- `contracts/life.invoke.output.schema.json`;
- `tests/test_life_invoke_contract.py`.

PR #7 merged those files to `main` at `5d69173f8a3a46a0d8c161ca089e7295ea08fcbf`. PR validation run `34672110208` and post-merge main run `34672133627` both succeeded.

### Host reevaluation

**Vercel Functions — COMBINE.** Current Vercel MCP guidance exposes the server as an OAuth resource server, supports protected-resource metadata and application-supplied token verification, and follows current MCP transport/authentication patterns. This is the selected transport layer.

**Supabase Edge Functions — REPLACE as the v1 MCP front door.** Supabase stays selected for Auth and Postgres, but current Supabase MCP Edge guidance still disables the Edge-layer JWT check in its MCP deployment path and states authenticated MCP support at that layer is forthcoming. The v1 transport therefore does not duplicate that work.

**Cloudflare Workers — REMOVE from v1.** Adding another infrastructure platform is not selected for the first invocation path.

**GitHub — KEEP as source plane only.** GitHub has zero Life runtime control authority.

## Exact `life.invoke` tool input

The input schema is closed and contains exactly:

- `schema_version`: exactly `1`;
- `invocation_key`: lowercase UUIDv4;
- `request_text`: JSON string with character length 1 through 65,536.

After JSON decoding, the runtime performs no trim, Unicode normalization, case folding, or newline normalization. It encodes `request_text` as strict UTF-8 and accepts byte length 1 through 262,144 inclusive.

U+0000 is explicitly forbidden and returns `REQUEST_TEXT_U0000_FORBIDDEN`. An input that cannot be encoded as strict UTF-8 returns `REQUEST_TEXT_INVALID_UNICODE`. SHA-256 is computed over the exact accepted UTF-8 bytes.

The server assigns `input_provenance = MCP_TOOL_ARGUMENT`. A caller cannot override provenance. The contract explicitly forbids treating `request_text` as a machine-verified copy of an upstream chat message.

## Idempotency

The durable idempotency key is the tuple:

`(auth_subject, oauth_client_id, invocation_key)`

If the tuple already exists with the same request SHA-256, return the existing invocation and `replayed=true`. If the tuple exists with a different request SHA-256, return `INVOCATION_KEY_REUSE_MISMATCH`.

The MCP `idempotentHint=true` annotation is a hint only. Enforcement comes from the exact database uniqueness/idempotency mechanism.

## OAuth and caller boundary

The selected authorization server is Supabase Auth with issuer:

`https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1`

The implementation contract requires:

1. RFC 9728 protected-resource metadata for the exact deployed MCP resource URL;
2. bearer authentication for `life.invoke`;
3. JWT signature verification through Supabase JWKS;
4. exact issuer equality;
5. exact audience equality to the deployed MCP resource URL;
6. required `sub`, `exp`, and `client_id` claims;
7. `nbf` validation when present;
8. rejection when any check fails;
9. no raw access-token storage;
10. no caller-token passthrough to Postgres or any upstream service.

Supabase OAuth currently supports Authorization Code with PKCE, refresh tokens, dynamic client registration for MCP-compatible clients, and JWKS validation. Custom OAuth scopes are not used as the Life v1 authorization gate because current Supabase OAuth does not support custom scopes.

Tool-call permission also requires an exact active machine record keyed by `(auth_subject, oauth_client_id)`. Prose, consent text, tool annotations, labels, model judgment, comments, and reviews cannot satisfy that gate.

The connected Supabase tool does not expose direct reads of the live OAuth-server enablement or JWT-signing-key configuration. Those settings remain `NOT_RUN` until a later deployment step can verify them directly. Deployment requires OAuth Server enabled and asymmetric signing verified.

## Canonical invocation ledger

The selected database location is a non-public Supabase Postgres schema `life`.

The v1 ledger table is `life.invocations`. The selected architecture requires at least:

- server-generated `invocation_id` UUID primary key;
- `schema_version = 1`;
- caller `invocation_key` UUID;
- database-generated `recorded_at` timestamp;
- validated `auth_subject`, `auth_issuer`, `oauth_client_id`, and `audience`;
- `tool_name = 'life.invoke'`;
- `input_provenance = 'MCP_TOOL_ARGUMENT'`;
- exact `request_text`;
- lowercase text request SHA-256;
- exact UTF-8 byte length;
- MCP protocol version;
- exact runtime build commit SHA.

No embedding, vector, bearer token, model confidence, semantic-readiness label, or effect-authorization state belongs in the canonical invocation row.

A separate exact caller-allowlist table controls whether `(auth_subject, oauth_client_id)` may invoke the tool. Its state is an exact enumeration.

## Database write boundary

The planned Vercel runtime uses a dedicated Postgres login path through Supavisor transaction-mode pooling. The runtime does not receive direct table INSERT, UPDATE, or DELETE privilege.

Its invocation-ledger write capability is restricted to EXECUTE on `life.record_invocation_v1`. The function must be `SECURITY DEFINER`, use an empty fixed `search_path`, schema-qualify referenced objects, enforce idempotency and ledger invariants, revoke EXECUTE from `PUBLIC`, and grant EXECUTE only to the dedicated runtime role.

The runtime must not use the `postgres` role or a broad Supabase service-role credential.

## Initial database source and verified mismatch

PR #9 merged the initial Supabase database foundation to `main` at `0934c5e1ff4a6632afb93d86263e284920f3f8d7`. Post-merge workflow run `34673627298` succeeded, including a clean local Postgres 17 migration application and pgTAP tests.

Fresh authorized Supabase reads then showed that migration `20260912042500` (`life_invocation_v1`) is already present remotely and created:

- `life.oauth_callers_v1`;
- `life.invocations`;
- `life.record_invocation_v1(text,text,uuid,text)`;
- dedicated login role `life_runtime_v1`.

Both Life tables currently contain zero rows and the project has zero deployed Edge Functions.

The current implementation is **MODIFY**, not complete relative to `D-0015`. Direct source and remote-schema reads verify that `life.invocations` omits `schema_version`, `auth_issuer`, `audience`, `tool_name`, `mcp_protocol_version`, and `runtime_build_sha`. It also stores `request_sha256` as `bytea`, while the selected architecture requires lowercase text SHA-256 in the canonical ledger.

Decision `D-0016` therefore requires a new forward migration. The already-applied migration is preserved as immutable history rather than edited after deployment. The retained pieces are the private `life` schema, exact caller allowlist, append-only guards, idempotency uniqueness, dedicated runtime role, and least-privilege `SECURITY DEFINER` boundary.

## Remote-mutation provenance gap

The earlier verified Supabase read at `2026-09-12T04:09:04Z` showed the invocation database objects absent. The current direct read shows migration `20260912042500` and its objects present.

The mutation therefore occurred, but the exact time, actor, and control provenance are **UNKNOWN**. No deterministic lock branch exists for the required global production resource `external:supabase:jnenguxodtgwbskhdsxt`, so there is no machine-verifiable evidence that the original remote mutation held the required claim. This past mutation cannot be converted to PASS through inference, prose, or later approval.

Future Supabase writes remain serialized through the exact global claim and must satisfy version-first GitHub requirements before remote application.

## Legacy Supabase RLS auto-enable mechanism

Fresh Supabase security advisors currently report two warnings for `public.rls_auto_enable()`: the `SECURITY DEFINER` function is executable by `anon` and `authenticated`. Direct read-back shows active event trigger `ensure_rls` invokes the function on `ddl_command_end` to auto-enable RLS for newly created `public` tables.

Authorized GitHub source contains no versioned definition for this mechanism. Clean-slate disposition is **REMOVE**. Future RLS behavior must be explicit in versioned migrations and tests rather than hidden in an unversioned database event trigger.

The removal must itself be versioned and tested in GitHub before any authorized Supabase mutation.

## Success boundary

A successful tool call returns the closed v1 output with:

- schema version 1;
- invocation ID;
- invocation key;
- recorded timestamp;
- request SHA-256;
- exact UTF-8 byte count;
- `input_provenance = MCP_TOOL_ARGUMENT`;
- `state = RECORDED`;
- replay flag.

`RECORDED` means only that authentication, caller allowlist, input validation, and durable recording passed. It does not authorize an external effect, establish context completeness, establish semantic maturity, or pass any later control decision.

## Legacy invocation dispositions

The clean-slate comparison in `contracts/life.invoke.contract.json` records:

- stable `life.invoke` tool — KEEP;
- authenticated invocation — KEEP;
- canonical invocation ledger — KEEP;
- exact invocation boundary separate from embeddings — KEEP;
- vectors have zero control authority — KEEP;
- migrations/tests/CI — KEEP;
- Supabase Auth/OAuth/JWT — COMBINE with Vercel transport;
- Supabase Edge Function as MCP front door — REPLACE;
- `gte-small` 384-dimensional embedding inside canonical invocation — REMOVE from v1;
- legacy manual Bearer parser — REMOVE;
- claim that request text is the machine-verified raw chat message — MODIFY to exact MCP-tool-argument provenance;
- assumption that PostgreSQL text accepts U+0000 — REMOVE;
- Project Instructions routing directly to database tables — REPLACE with the stable `life.invoke` boundary.

The earlier private-repository implementation remains evidence only and is not migrated wholesale.

## Context pipeline versus control pipeline

These remain separate.

**Context pipeline:** determines what information is considered. It may use exact relational lookup, semantic/vector discovery, retrieved documents, user-provided material, and connected-system reads.

**Control pipeline:** determines what action is allowed. Authorization, routing, priority, state transition, completion, verification, escalation, release, mutation, and effect execution require exact machine-verifiable evidence and deterministic evaluation.

No retrieval score, model confidence, prose label, approval, comment, review, or coordination record can become a PASS control state.

## Authorized platform roles

### GitHub

Authorized Build/Engineering repository: `Vinanonymous/Build`
Repository ID: `1366835183`
Visibility: public
Default branch: `main`

GitHub is the source/build plane: source, migrations, tests, CI, schemas, history, source-coordination evidence, and engineering evidence. It is not the deployed Life runtime control plane.

Fresh direct reads show `main` at `0934c5e1ff4a6632afb93d86263e284920f3f8d7`, zero open pull requests before this continuity work item, and post-merge workflow run `34673627298` successful.

### Supabase

Authorized project: `jnenguxodtgwbskhdsxt`
Project name: `Life`
Region: `us-west-2`

Supabase is selected for OAuth identity and Postgres data in canonical invocation v1. Fresh direct reads show the project `ACTIVE_HEALTHY`, zero public base tables, zero deployed Edge Functions, the initial Life invocation migration already present, two Life tables with zero rows, the dedicated runtime role, and `life.record_invocation_v1` deployed. The deployed database record is not yet aligned to every `D-0015` ledger requirement.

Supabase Free currently has no preview Branching for this project path, so every direct authorized-project write is serialized through the exact global claim `external:supabase:jnenguxodtgwbskhdsxt` until a different verified mechanism replaces that constraint.

### Vercel

Vercel Functions are selected as the canonical invocation v1 transport host class. No exact Life Vercel target is authorized. No Vercel mutation or deployment may occur until Vince authorizes the exact target. No paid Vercel plan may be selected without Vince's authorization.

## GitHub source protection

Ruleset `Protect-main`, ID `22998982`, is directly verified with:

- default-branch target;
- enforcement active;
- no bypass actors;
- deletion restricted;
- non-fast-forward pushes blocked;
- pull request required;
- zero required approvals;
- required GitHub Actions check `validate`;
- strict required status checks enabled;
- no extra approval for unattributed changes.

Decision `D-0013` supersedes the earlier loose-check description in `D-0011`. The ruleset has zero Life runtime control authority.

## Multi-agent source coordination

Source coordination is enforced by `coordination/protocol.json`, its schemas, validator, tests, and the required `validate` check.

Each mutable work item uses an exact `work/<UUIDv4>` branch and exact resource leases on deterministic `lock/<sha256(resource_key)>` branches. Required claims include a component claim, exact file claims, `integration:main` for PRs, and the global authorized-Supabase production claim before Supabase writes. Leases last exactly 14,400 seconds, resource acquisition is ascending UTF-8 order, failed acquisition releases in reverse order, expiry takeover increments generation by one, and reacquisition after `RELEASED` increments generation by one.

Every post-bootstrap PR includes one `coordination/work/<work_id>.json` record. CI validates exact changed-path coverage and live claims. `Protect-main` strict checks require current-base validation before merge.

PR #3 installed coordination. PR #4 fixed continuity-sync recursion by admitting `coordination/work/**` to the exact sync path set. PR #5 defined monotonic generation on clean reacquisition after release. Decisions `D-0012` and `D-0014` record this mechanism.

GitHub Issues, PR text, comments, reviews, and narrative coordination records remain visibility-only and have zero Life runtime control authority.

## Continuity architecture

The continuity bundle contains:

- `bootstrap.json`: fixed entry point, required files/read order, resume algorithm, synchronization triggers, and recursion exemption;
- `current.json`: compact exact current state, targets, component/status, blockers, observations, and one next action;
- `context.md`: this detailed narrative;
- `decisions.jsonl`: append-only typed decision history;
- `events.jsonl`: append-only operational history;
- schemas, deterministic validators, tests, and GitHub Actions CI.

A continuity-sync PR may merge without a second sync only when its changed paths are a nonempty subset of the exact `continuity_sync_paths`. Historical observations never satisfy a later response's fresh-verification requirements.

## Project Instructions

Vince changed the final continuity sentence from `End with next step+response number.` to `End with next step+response counter.` The complete Project Instructions remain at the previously verified **7,999 characters including whitespace**, within the 8,000-character ceiling.

The current instructions still match the verified authorized-system identities. No instruction has been shown to be fully replaced by a deployed Life executable mechanism, so no instruction removal is proposed.

The current verified state does expose one historical control-evidence gap: the already-present Supabase migration lacks machine-verifiable original global-claim provenance. The Project Instructions do not conflict with that state; they require the gap to remain UNKNOWN/NOT_RUN rather than being inferred into PASS.

## Current research posture

The current response freshly completed the required platform 5/5 checks for Supabase Free, GitHub Free, and Vercel Hobby; Reddit searches on current database/hosting/authentication mechanisms and failure reports; current OpenAI model/plugin/app/MCP capability checks and Plugin Directory search; and current MCP, agent-security, instruction-following, PostgreSQL-security, and reliability research.

Those external facts must be rechecked on every later Life response under the Project Instructions.

## Current unresolved question

`Q-0002` remains open: which exact deterministic runtime control implementation will satisfy the ten enumerated control decision kinds? Canonical invocation v1 deliberately does not resolve that later control-plane architecture.

`Q-0001` is resolved by `D-0015`: Vercel Functions + Supabase Auth/Postgres is the selected canonical invocation composition.

`Q-0003` is resolved by `D-0015`: the legacy invocation concepts have explicit KEEP / REPLACE / MODIFY / COMBINE / REMOVE dispositions in the merged contract.

## Current active component and next action

`canonical_invocation_architecture` is complete.

The merged initial database foundation is not accepted as complete against `D-0015`; it is dispositioned **MODIFY** by `D-0016`.

The active component is `canonical_invocation_database_alignment_source` in IMPLEMENTATION.

The next action is `A-0006`: create one new forward Supabase migration and pgTAP test update that adds the missing canonical ledger fields, aligns `request_sha256` storage and `life.record_invocation_v1` with the `D-0015` record contract, and removes the unversioned `ensure_rls` event trigger plus `public.rls_auto_enable()`. Validate and merge that source before any further authorized Supabase mutation.

After the source passes and merges, a separately claimed Supabase production mutation may apply only the already-versioned forward migration, followed by direct read-back and advisor verification. Vercel source and deployment follow later; no exact Vercel target is authorized yet.

## Cost constraints

No paid plan, add-on, metered charge, purchase, or billing commitment may be made without Vince's authorization.

## Reading discipline for future threads

A future Life thread must:

1. read `continuity/bootstrap.json` and every path in `required_read_order`, including the coordination protocol;
2. validate the continuity and coordination bundle;
3. read the current request/thread;
4. run every required fresh research check;
5. directly read the authorized systems;
6. verify referenced live objects and live resource claims;
7. mark stale, missing, mismatched, unsupported, failed, or unverified evidence under the Project Instructions;
8. apply later Vince corrections;
9. continue from `continuity/current.json.next_action`.

If live authorized-system state conflicts with continuity, live state determines the external fact and continuity must be synchronized.

## Last bundle-authoring timestamp

`2026-09-12T05:08:16Z`
