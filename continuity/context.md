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

Current Life architecture work starts from the first runtime event: **a user invokes Life**.

The working sequence is:

1. A user makes a Life request.
2. The canonical Life entry tool is intended to be `life.invoke`.
3. Life establishes an authenticated canonical invocation boundary and records exact request facts that belong at that boundary.
4. Derived semantic representation may be created for retrieval.
5. Later context retrieval may use semantic search to find candidates.
6. Candidate information must resolve back to authoritative exact records before it can be treated as current fact.
7. Runtime control decisions use exact machine-verifiable evidence and deterministic evaluation.
8. AI reasoning and allowed effects proceed only after the applicable control path permits them.

The Project Instructions require `life.invoke` only when fresh authorized-system reads show a deployed Life MCP endpoint and exact tool `life.invoke`. If that condition is not verified, canonical invocation is `NOT_RUN` and no runtime output may be fabricated.

Fresh authorized Supabase reads on `2026-09-12T02:50:04Z` showed zero public tables, zero deployed Edge Functions, no `life.invoke` database function, and no installed `vector` extension. Canonical invocation therefore remains `NOT_RUN`.

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

GitHub is the source/build plane: source code, migrations, tests, CI, schemas, history, and engineering evidence. GitHub is not the deployed Life runtime control plane.

The repository is public so GitHub Free repository rulesets can enforce source-plane protections while standard GitHub-hosted Actions remain free for public repositories.

### Supabase

Authorized project: `jnenguxodtgwbskhdsxt`
Project name: `Life`
Region: `us-west-2`

Supabase remains a runtime/data candidate because Postgres, Auth, vector support, and Edge Functions may fit Life. Clean-slate reevaluation keeps the permanent invocation host open until comparison selects it.

### Vercel

No exact Life Vercel infrastructure target is authorized. Vercel Hobby may be researched and compared, but Life Vercel state is `NOT_RUN` until Vince authorizes an exact target.

## GitHub source protection is complete

Vince created repository ruleset `Protect-main`, ruleset ID `22998982`, through the GitHub UI. Direct GitHub read-back verified all selected fields:

- target: default branch;
- enforcement: active;
- bypass actors: none;
- deletion: restricted;
- non-fast-forward pushes: blocked;
- pull request required;
- required approving review count: 0;
- required status check: `validate` from GitHub Actions;
- strict up-to-date status-check policy: disabled;
- extra approval for unattributed changes: disabled;
- merge, squash, and rebase merge methods remain allowed.

GitHub also reports `main` as protected. This ruleset has zero Life runtime control authority. Its purpose is source-plane enforcement: ordinary changes to `main` must pass through a PR and the repository validator/tests.

The former source-protection blocker `B-0002` is resolved. `github_source_protection` is complete.

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

That implementation must not be copied wholesale into `Vinanonymous/Build`. It was created under earlier assumptions, and later review found defects including a PostgreSQL zero-byte edge case in a text field and case-sensitive Bearer-scheme parsing.

Treat the legacy implementation as evidence and candidate parts. Rebuild only the parts that survive current comparison.

## Repository transition

The legacy private repository is not the authorized Build target. `Vinanonymous/Build` is the authorized GitHub repository. The public repository provides GitHub Free ruleset enforcement and a clean source history containing only mechanisms that survive reevaluation.

## Continuity architecture

The continuity bundle contains:

- `bootstrap.json`: fixed entry point, required files/read order, resume algorithm, synchronization triggers, and recursion exemption;
- `current.json`: compact exact current state, targets, component/status, blockers, observations, and one next action;
- `context.md`: this detailed narrative and rationale;
- `decisions.jsonl`: append-only typed decision history;
- `events.jsonl`: append-only operational history;
- JSON Schemas, a deterministic validator, tests, and GitHub Actions CI.

Historical observations never satisfy a later response's fresh-verification requirements.

## Continuity synchronization

Synchronization is required after each successful occurrence of:

- `VINCE_DIRECTIVE`
- `ARCHITECTURE_DECISION`
- `GITHUB_MUTATION`
- `SUPABASE_MUTATION`
- `VERCEL_MUTATION`
- `PROJECT_INSTRUCTION_CHANGE`
- `VERIFICATION_TRANSITION`
- `BLOCKER_TRANSITION`
- `NEXT_ACTION_CHANGE`
- `COMPONENT_TRANSITION`

A repository mutation whose changed paths are a nonempty subset of the exact `continuity_sync_paths` in `bootstrap.json` is `CONTINUITY_SYNC` and does not recursively require another synchronization solely because it occurred. Git history preserves its byte-level mutation.

## Project Instruction correction

Vince changed the final sentence of the `CONVERSATION CONTINUITY` Project Instruction block from:

`End with next step+response number.`

to:

`End with next step+response counter.`

No other text in that block changed. The replacement adds one character. Using the previously verified 7,998-character complete Project Instructions as the base, the complete Project Instructions now contain 7,999 characters including whitespace, remaining within the 8,000-character ceiling.

Future Life responses must use **response counter** terminology.

## Current research posture

Fresh research in the response that completed source protection rechecked Supabase Free, GitHub Free, and Vercel Hobby pricing/limits/billing/docs; current GitHub ruleset and Actions behavior; current Supabase Edge Function/MCP material; current Vercel Function/MCP material; Reddit reports on operational failures and workarounds; current OpenAI model/plugin/app/agent mechanisms; and current agent instruction-following/security research.

The research does not grandfather any runtime host. It reinforces the existing separation between probabilistic/model reasoning and deterministic execution control. Current agent research continues to show that instruction arbitration can fail under complex or conflicting instruction sets, which supports keeping security-critical control outside model judgment.

## Current unresolved questions

1. Which permanent runtime host should expose the canonical Life MCP endpoint after fresh comparison?
2. Which exact deterministic runtime control implementation should satisfy the ten enumerated control decision kinds?
3. Which concepts from the legacy invocation implementation should survive the clean-slate rebuild?

Do not resolve these from implementation history alone.

## Current active component

`canonical_invocation_architecture` is active in DESIGN.

The current work is to rederive and select the permanent `life.invoke` architecture, beginning with:

- runtime host;
- exact tool contract;
- authentication boundary;
- canonical invocation record;
- context/control boundary;
- implement-now sequence.

No runtime deployment should occur before those decisions are defined and versioned as required.

## Cost constraints

No paid plan, add-on, metered charge, purchase, or billing commitment may be made without Vince's authorization.

GitHub Free public-repository mechanisms remain the selected source-plane path. Supabase is currently Free. Vercel Hobby remains a candidate within current terms and limits; no Vercel target is authorized.

## Reading discipline for future threads

A future thread must:

1. read `continuity/bootstrap.json` and every path in `required_read_order`;
2. validate the bundle;
3. read the current request/thread;
4. run the required fresh research;
5. directly read the authorized systems;
6. verify referenced live objects;
7. mark stale, missing, mismatched, unsupported, failed, or unverified evidence under the Project Instructions;
8. apply later Vince corrections;
9. continue from `current.json.next_action`.

If live authorized-system state conflicts with continuity, live state determines the external fact and continuity must be synchronized.

## Last bundle-authoring timestamp

`2026-09-12T02:50:04Z`
