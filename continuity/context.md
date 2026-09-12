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

Current Life architecture work ultimately starts from the first runtime event: **a user invokes Life**.

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

Fresh authorized Supabase reads on `2026-09-12T03:02:33Z` showed the project `ACTIVE_HEALTHY`, zero public tables, zero deployed Edge Functions, no `life.invoke` database function, no installed `vector` extension, and only the default main environment. Canonical invocation therefore remains `NOT_RUN`.

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

The repository is public so GitHub Free repository rulesets can enforce source-plane protections while standard GitHub-hosted Actions remain free for public repositories.

### Supabase

Authorized project: `jnenguxodtgwbskhdsxt`
Project name: `Life`
Region: `us-west-2`

Supabase remains a runtime/data candidate because Postgres, Auth, vector support, and Edge Functions may fit Life. Clean-slate reevaluation keeps the permanent invocation host open until comparison selects it.

Current Supabase Free pricing states that Branching is not included. Because the authorized project therefore has no free isolated preview environment, direct production mutations are serialized by the source-coordination protocol through one exact global resource claim until a different verified mechanism replaces that constraint.

### Vercel

No exact Life Vercel infrastructure target is authorized. Vercel Hobby may be researched and compared, but Life Vercel state is `NOT_RUN` until Vince authorizes an exact target.

## GitHub source protection

Vince created repository ruleset `Protect-main`, ruleset ID `22998982`, through the GitHub UI. Direct GitHub read-back verified:

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

GitHub reports `main` as protected. This ruleset has zero Life runtime control authority. Its purpose is source-plane enforcement.

The former blocker `B-0002` is resolved. A new blocker `B-0003` exists because the ruleset still uses loose required status checks. GitHub's current ruleset documentation distinguishes loose from strict checks: strict checks require the topic branch to be up to date with the base branch before merging, while loose checks can permit a branch whose checks passed before another collaborator changed the base. Multi-agent coordination is not complete until `strict_required_status_checks_policy=true` is read back for ruleset `22998982`.

## Multi-agent source coordination

Vince asked whether multiple threads or AIs can work on Life concurrently without overwriting or interfering with each other, then authorized installation of the permanent coordination mechanism before `life.invoke` work resumes.

Fresh comparison rejected branches/worktrees alone as sufficient. They isolate live file writes, but they do not prevent two independently passing branches from becoming semantically incompatible after one merges, and they do not isolate the single Supabase production environment. Current OpenAI Codex material uses worktrees for parallel agents; current GitHub documentation recommends strict latest-base status checks for compatibility with the newest base; recent multi-agent SWE research likewise emphasizes centralized delegation, isolated workspaces, branch-and-merge, and executable verification. Reddit reports show the same practical distinction: worktrees prevent direct clobbering, while merge compatibility and shared services still need coordination.

Decision `D-0012` therefore combines the following source-plane mechanisms:

1. Every mutable work item receives a UUIDv4 `work_id` and one branch named exactly `work/<work_id>`.
2. A local coding agent uses one Git worktree for that branch. A remote agent writes only to that branch.
3. Every mutable resource has an exact resource key. Required forms include `component:<component_id>`, `repo-file:<exact_repo_path>`, `integration:main`, and the current global Supabase production key `external:supabase:jnenguxodtgwbskhdsxt`.
4. The lock branch for a resource is deterministic: `lock/` plus the lowercase SHA-256 hex digest of the UTF-8 resource key.
5. `coordination/lock.json` on that branch is the machine-verifiable lease record. The lease has an exact worker identity, work ID, lease ID, generation, base SHA, timestamps, state, and implementation branch.
6. Lease duration is exactly 14,400 seconds. Renewal occurs when remaining time is at or below 1,800 seconds. Expiry occurs when current UTC is greater than or equal to `expires_at`. Takeover after expiry increments `generation` by exactly one.
7. Resources for one work item are acquired in ascending UTF-8 resource-key order. If an acquisition fails, that attempt releases already-acquired claims in reverse order.
8. Every repository path changed by a PR, except its unique work-record file, requires an exact `repo-file:` claim.
9. Every work item requires a component claim.
10. Every PR to `main` requires the exact `integration:main` claim.
11. Every Supabase production mutation requires the exact global Supabase claim because Free Branching is unavailable.
12. The existing required Actions job remains named `validate`; it now also validates the coordination protocol, exact changed-path coverage, current-base ancestry, work record, and live lock-branch claims.
13. GitHub Issues, PR text, comments, reviews, and narrative coordination records remain visibility surfaces with zero source-control or Life runtime authority.

The authoritative protocol is `coordination/protocol.json`. Its schemas are `coordination/schema/lock.schema.json` and `coordination/schema/work-record.schema.json`. Enforcement code is `scripts/validate_coordination.py`; tests are `tests/test_coordination.py`. `continuity/bootstrap.json` now includes the coordination protocol and README in the mandatory future-thread read order so a new Life thread reconstructs both project state and the concurrency rules before mutating anything.

Issue #2 (`WORK: install multi-agent source coordination`) is visibility-only. It does not grant or reserve work.

The installation branch is `coordination/multi-agent-v1`. It is intentionally a bootstrap exception: the coordination validator permits this first PR because the PR base does not yet contain `coordination/protocol.json`. After that protocol exists on `main`, every later PR is required to satisfy the work-record and live-claim gate.

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
- JSON Schemas, deterministic validators, tests, and GitHub Actions CI.

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

Fresh research for multi-agent coordination rechecked all required Supabase Free, GitHub Free, and Vercel Hobby plan/pricing, quotas/limits, billing/usage, docs roots, and named mechanism documentation. It also rechecked Reddit multi-agent implementations and failures, current OpenAI Codex/plugin/app mechanisms, and recent research on asynchronous software-engineering agents and verifiable tool control.

The selected mechanism uses only current GitHub Free/public-repository facilities plus repository code and CI. It does not require a paid GitHub feature. Supabase is not used as the Build coordination store because Free Branching is unavailable and coupling source coordination to the single runtime/data candidate would create an unnecessary shared-environment dependency. Vercel is not used because no Life Vercel target is authorized and no Vercel feature is needed for this source-plane mechanism.

## Current unresolved questions

1. Which permanent runtime host should expose the canonical Life MCP endpoint after fresh comparison?
2. Which exact deterministic runtime control implementation should satisfy the ten enumerated control decision kinds?
3. Which concepts from the legacy invocation implementation should survive the clean-slate rebuild?

Do not resolve these from implementation history alone.

## Current active component

`multi_agent_coordination` is active in IMPLEMENTATION and is currently BLOCKED on one exact GitHub setting: `Protect-main` must change from loose to strict required status checks by enabling **Require branches to be up to date before merging** for the existing `validate` check.

`canonical_invocation_architecture` is paused, not abandoned. After coordination is merged, read back, validated, and `B-0003` is resolved, the canonical next action returns to the existing `A-0003` clean-slate `life.invoke` architecture work.

## Cost constraints

No paid plan, add-on, metered charge, purchase, or billing commitment may be made without Vince's authorization.

GitHub Free public-repository mechanisms remain the selected source-plane path. Supabase is currently Free. Vercel Hobby remains a candidate within current terms and limits; no Vercel target is authorized.

## Reading discipline for future threads

A future thread must:

1. read `continuity/bootstrap.json` and every path in `required_read_order`, now including the exact coordination protocol;
2. validate the bundle and coordination files;
3. read the current request/thread;
4. run the required fresh research;
5. directly read the authorized systems;
6. verify referenced live objects and live resource claims;
7. mark stale, missing, mismatched, unsupported, failed, or unverified evidence under the Project Instructions;
8. apply later Vince corrections;
9. continue from `current.json.next_action`.

If live authorized-system state conflicts with continuity, live state determines the external fact and continuity must be synchronized.

## Last bundle-authoring timestamp

`2026-09-12T03:02:33Z`
