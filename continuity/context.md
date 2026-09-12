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

Current runtime architecture work starts from the first event: **a user invokes Life**.

The intended sequence is:

1. A user makes a Life request.
2. The canonical Life entry tool is intended to be `life.invoke`.
3. Life establishes an authenticated canonical invocation boundary and records exact request facts that belong at that boundary.
4. Derived semantic representation may be created for retrieval.
5. Later context retrieval may use semantic search to find candidates.
6. Candidate information must resolve back to authoritative exact records before it can be treated as current fact.
7. Runtime control decisions use exact machine-verifiable evidence and deterministic evaluation.
8. AI reasoning and allowed effects proceed only after the applicable control path permits them.

The Project Instructions require `life.invoke` only when fresh authorized-system reads show a deployed Life MCP endpoint and exact tool `life.invoke`. Fresh authorized Supabase reads in response 21 showed project `jnenguxodtgwbskhdsxt` ACTIVE_HEALTHY, zero public tables, zero deployed Edge Functions, no `life.invoke` database function, no installed `vector` extension, and only the default main environment. Canonical invocation therefore remains `NOT_RUN`.

## Context pipeline versus control pipeline

These are separate.

**Context pipeline:** determines what information is considered. Candidate mechanisms include exact relational lookup, semantic/vector discovery, retrieved documents, user-provided material, and connected-system reads.

**Control pipeline:** determines what action is allowed. Authorization, routing, priority, state transition, completion, verification, escalation, release, mutation, and effect execution require exact machine-verifiable evidence and deterministic evaluation. Prose, AI judgment, labels, approvals, comments, reviews, and coordination records have zero Life runtime control authority.

No retrieval score or model confidence may become a PASS control state.

## Authorized platform roles

### GitHub

Authorized Build/Engineering repository: `Vinanonymous/Build`
Stable repository ID: `1366835183`
Visibility: public
Default branch: `main`

GitHub is the source/build plane: source code, migrations, tests, CI, schemas, history, source-coordination evidence, and engineering evidence. GitHub is not the deployed Life runtime control plane.

### Supabase

Authorized project: `jnenguxodtgwbskhdsxt`
Project name: `Life`
Region: `us-west-2`

Supabase remains a runtime/data candidate. Current Supabase Free pricing states Branching is not included, so direct writes to the one authorized production project are serialized through the source-coordination protocol's exact global Supabase claim unless a later verified mechanism replaces that constraint.

### Vercel

No exact Life Vercel infrastructure target is authorized. Vercel Hobby may be researched and compared, but Life Vercel state is `NOT_RUN` until Vince authorizes an exact target.

## GitHub source protection

Repository ruleset `Protect-main`, ruleset ID `22998982`, is directly verified with:

- target: default branch;
- enforcement: active;
- bypass actors: none;
- deletion restricted;
- non-fast-forward pushes blocked;
- pull request required;
- required approving review count: 0;
- required status check: `validate` from GitHub Actions;
- **strict required status checks enabled**;
- extra approval for unattributed changes disabled;
- merge, squash, and rebase merge methods allowed.

The strict setting means a topic branch must be up to date with `main` before it can merge under the required `validate` check. Decision `D-0013` supersedes the earlier loose-check description in `D-0011`. The ruleset has zero Life runtime control authority; it is source-plane enforcement.

## Multi-agent source coordination is complete

Vince asked whether multiple threads or AIs could work on Life without overwriting or interfering with one another and authorized installation of the permanent source-coordination mechanism before `life.invoke` work resumed.

Decision `D-0012` selected a combined source-plane design because branches/worktrees alone isolate live file writes but do not prevent incompatible clean merges or shared-environment collisions. The installed mechanism now consists of:

1. one UUIDv4 `work_id` and exact `work/<work_id>` branch for each mutable work item;
2. one worktree per work branch for local coding agents; remote agents write only to their work branch;
3. exact resource keys including `component:<component_id>`, `repo-file:<exact_repo_path>`, `integration:main`, and `external:supabase:jnenguxodtgwbskhdsxt`;
4. deterministic lock branches: `lock/` plus the lowercase SHA-256 digest of the UTF-8 resource key;
5. machine-verifiable `coordination/lock.json` lease records with worker identity, work ID, lease ID, generation, base SHA, timestamps, state, and implementation branch;
6. exact 14,400-second leases and renewal when remaining time is at or below 1,800 seconds;
7. expiry takeover only when current UTC is greater than or equal to `expires_at`, with generation incremented by exactly one;
8. reacquisition after `RELEASED` with generation incremented by exactly one and new work/lease/base/timestamp identity;
9. ascending UTF-8 resource-key acquisition order and reverse-order release if an acquisition attempt fails;
10. exact file claims for every repository path changed by a PR except that work item's own work-record path;
11. a component claim for every work item;
12. an `integration:main` claim for every PR to `main`;
13. the one global Supabase production claim before every authorized-project mutation;
14. one `coordination/work/<work_id>.json` record on every post-bootstrap PR;
15. the required `validate` GitHub Actions job as the machine gate for continuity validation, coordination validation, exact changed-path coverage, current-main ancestry, work-record validation, and live lease validation;
16. strict latest-base enforcement from `Protect-main` so a PR cannot reuse a green result from an older base state.

GitHub Issues, PR text, comments, reviews, and narrative coordination records remain visibility surfaces with zero source-control authority and zero Life runtime authority.

The authoritative coordination files are:

- `coordination/protocol.json`;
- `coordination/schema/lock.schema.json`;
- `coordination/schema/work-record.schema.json`;
- `scripts/validate_coordination.py`;
- `tests/test_coordination.py`.

The coordination protocol and README are part of `continuity/bootstrap.json`'s mandatory future-thread read order.

## Coordination installation evidence

PR #3 installed the coordination bootstrap. After its validator correctly rejected noncanonical schema formatting, the schemas were canonicalized and the complete PR validation passed. PR #3 merged to `main` at `9535ba7efd1aceec752c4f88324620f66e3f8c51`; post-merge workflow run `34669982539` succeeded.

The first attempted coordinated continuity sync exposed a deterministic recursion defect: every post-bootstrap PR must include a work record, but `coordination/work/**` was not yet in `continuity_sync_paths`. PR #4 corrected this by including `coordination/work/**` in the exact sync path set and defining that a validated continuity-sync merge whose changed paths are a nonempty subset of `continuity_sync_paths` does not require another synchronization solely because that synchronization merged. PR #4 merged at `a2d3a0468760933c98171c0ef7b9c1808b1f3323`; workflow run `34670368190` succeeded.

The next work cycle exposed a second exact lifecycle ambiguity: the protocol defined expiry takeover generations but not clean reacquisition after `RELEASED`. PR #5 added the exact rule `LEASE_REACQUISITION_AFTER_RELEASE_INCREMENTS_GENERATION_BY_EXACTLY_ONE`, documented it, and tested it. PR #5 merged at `4478966f70941d258c818f97d4ba841ac58604a7`; workflow run `34670572503` succeeded.

Decision `D-0014` records both refinements. `B-0003` is resolved. `multi_agent_coordination` is complete.

## Continuity interaction with parallel work

Mutations confined to branches matching `work/<lowercase-UUIDv4>` or `lock/<64-lowercase-hex>` do not update canonical Life state and do not require continuity synchronization solely because they occurred. Their branch history and live machine state are their exact evidence.

A normal source PR merge or other update to `main` still requires synchronization under the enumerated continuity event rules. A continuity-sync PR is recursion-safe only when all of its changed paths are a nonempty subset of the exact `continuity_sync_paths` in `continuity/bootstrap.json`; that exact set now includes `coordination/work/**`. An update to `main` outside the sync path set is never exempt.

## Legacy invocation work

Before the clean-slate correction, a legacy private repository contained an invocation implementation commonly referred to as PR #25. Candidate concepts from that implementation include:

- a stable `life.invoke` tool;
- authenticated invocation;
- a canonical invocation ledger;
- separation between raw invocation facts and vector embeddings;
- 384-dimensional `gte-small` embeddings;
- vectors carrying no control authority;
- database tests and CI;
- Supabase Auth/OAuth/JWT;
- an Edge Function entry point.

That implementation must not be copied wholesale into `Vinanonymous/Build`. It was created under earlier assumptions, and later review found defects including a PostgreSQL zero-byte edge case in a text field and case-sensitive Bearer-scheme parsing. Treat it as evidence and candidate parts; rebuild only pieces that survive current comparison.

## Continuity architecture

The continuity bundle contains:

- `bootstrap.json`: fixed entry point, required files/read order, resume algorithm, synchronization triggers, and recursion exemption;
- `current.json`: compact exact current state, targets, component/status, blockers, observations, and one next action;
- `context.md`: this detailed narrative and rationale;
- `decisions.jsonl`: append-only typed decision history;
- `events.jsonl`: append-only operational history;
- JSON Schemas, deterministic validators, tests, and GitHub Actions CI.

Historical observations never satisfy a later response's fresh-verification requirements.

## Project Instruction correction

Vince changed the final sentence of the `CONVERSATION CONTINUITY` Project Instruction block from `End with next step+response number.` to `End with next step+response counter.` No other text in that block changed. The complete Project Instructions remain at the previously verified **7,999 characters including whitespace**, within the 8,000-character ceiling.

Future Life responses use **response counter** terminology.

## Current research posture

The response that completed source coordination freshly rechecked the required Supabase Free, GitHub Free, and Vercel Hobby pricing/plan, quotas/limits, billing/usage, docs roots, and named mechanism documentation; Reddit reports about multi-agent worktrees, merge conflicts, and shared databases; current OpenAI Codex, model, plugin/app, and agent mechanisms; and current research on asynchronous software-engineering agents and concurrency control.

The source mechanism uses GitHub Free/public-repository capabilities plus repository code and CI. Supabase is not the source-coordination store because Free Branching is unavailable and the authorized project is a shared runtime/data environment. Vercel is not used for source coordination because no Life Vercel target is authorized and no Vercel mechanism is required for this layer.

## Current unresolved runtime questions

1. Which permanent runtime host should expose the canonical Life MCP endpoint after fresh comparison?
2. Which exact deterministic runtime control implementation should satisfy the ten enumerated control decision kinds?
3. Which concepts from the legacy invocation implementation should survive the clean-slate rebuild?

Do not resolve these from implementation history alone.

## Current active component and next action

`multi_agent_coordination` is complete. `canonical_invocation_architecture` has resumed as the active component in DESIGN.

The canonical next action is `A-0003`: compare permanent `life.invoke` host and invocation-boundary candidates against Life requirements; select KEEP / REPLACE / MODIFY / COMBINE / REMOVE for legacy concepts; then define the exact tool contract, authentication boundary, invocation record, context/control boundary, and implement-now sequence before runtime deployment.

## Cost constraints

No paid plan, add-on, metered charge, purchase, or billing commitment may be made without Vince's authorization.

## Reading discipline for future threads

A future Life thread must:

1. read `continuity/bootstrap.json` and every path in `required_read_order`, including the exact coordination protocol;
2. validate the continuity and coordination bundle;
3. read the current request/thread;
4. run the required fresh research;
5. directly read the authorized systems;
6. verify referenced live objects and live resource claims;
7. mark stale, missing, mismatched, unsupported, failed, or unverified evidence under the Project Instructions;
8. apply later Vince corrections;
9. continue from `current.json.next_action`.

If live authorized-system state conflicts with continuity, live state determines the external fact and continuity must be synchronized.

## Last bundle-authoring timestamp

`2026-09-12T03:32:55Z`
