# Life Continuity Context

## Purpose of this file

This file is the detailed narrative half of Life's continuity bundle. It exists so a fresh AI thread can reconstruct the engineering situation without relying on ChatGPT memory, prior-chat summaries, or Vince repeating the project. It is intentionally detailed.

This file has **zero Life runtime control authority**. It explains state and rationale. Exact current state is represented in `continuity/current.json`; typed decision history is in `continuity/decisions.jsonl`; typed operational history is in `continuity/events.jsonl`; live facts must be re-read from authorized systems.

## Core objective

Life is being built from first principles as a durable personal AI system. The engineering objective is not merely to make an assistant that remembers things. Life must be able to retrieve the right context, distinguish context from control, preserve exact state where exactness is required, recover across AI threads, and eventually execute allowed effects without letting prose or model judgment become authority.

A governing design phrase is:

**Structure what must be exact. Vectorize what only needs to be discoverable by meaning.**

Semantic/vector search may retrieve candidate information. It does not establish truth, currentness, identity, authorization, routing, completion, release, mutation permission, or effect execution.

## Clean-slate rule

Existing work has no architectural privilege because it already exists, was approved, was implemented, or was previously recommended. Every mechanism must survive current comparison against Life requirements and alternatives. Decisions use the vocabulary KEEP / REPLACE / MODIFY / COMBINE / REMOVE.

This matters because an earlier implementation phase got ahead of architecture. Useful code and concepts may survive, but there is no wholesale migration rule.

## The first-event focus

Current Life architecture work starts from the first runtime event: **a user invokes Life**.

The working conceptual sequence is:

1. A user makes a Life request.
2. The canonical Life entry tool is intended to be `life.invoke`.
3. Life establishes an authenticated/canonical invocation boundary and records exact request facts that belong at that boundary.
4. Derived semantic representation may be created for retrieval.
5. Later context retrieval can use semantic search to find candidates.
6. Candidate information must be resolved back to authoritative exact records before it can be treated as current fact.
7. Runtime control decisions must use exact machine-verifiable evidence and deterministic evaluation.
8. AI reasoning and allowed effects operate only after the applicable control path permits them.

The current Project Instructions require `life.invoke` only when fresh authorized-system reads show a deployed Life MCP endpoint and exact tool `life.invoke`. If that condition is not verified, invocation is `NOT_RUN` and no runtime output may be fabricated.

As of the last observation recorded in `current.json`, the authorized Supabase project had zero deployed Edge Functions, so canonical invocation is not yet deployed.

## Context pipeline versus control pipeline

These are separate.

**Context pipeline:** What information should be considered?

Possible mechanisms include exact relational lookup, semantic/vector candidate discovery, retrieved documents, user-provided material, and connected-system reads.

**Control pipeline:** What is allowed to happen?

Authorization, routing, priority, state transition, completion, verification, escalation, release, mutation, and effect execution require exact machine-verifiable evidence and deterministic evaluation. Free-form prose, AI judgment, labels, approvals, comments, reviews, and coordination notes have zero runtime control authority.

No retrieval score or model confidence may be promoted into a PASS control state.

## Current platform roles

### GitHub

Authorized Build/Engineering repository: `Vinanonymous/Build`
Stable repository ID: `1366835183`
Visibility: public
Default branch: `main`

GitHub is the source/build plane: source code, migrations, tests, CI, schemas, history, and engineering evidence. GitHub is not the deployed Life runtime control plane.

The repository was intentionally created public because GitHub Free can enforce repository rulesets on public repositories and standard GitHub-hosted Actions are free for public repositories. The previous private repository did not provide the same Free-plan enforcement.

At continuity-bootstrap start, the new repository was empty, had zero rulesets, and had no observed pull requests.

### Supabase

Authorized project: `jnenguxodtgwbskhdsxt`
Project name: `Life`
Region: `us-west-2`
Current organization plan at last verification: Free

Supabase remains the leading runtime/data candidate because its current platform offers Postgres, Auth, vector capabilities, and Edge Functions that may fit Life. However, clean-slate reevaluation means the exact permanent MCP/runtime host is still an open question.

At continuity-bootstrap start, direct reads showed zero public tables and zero deployed Edge Functions.

### Vercel

No exact Life Vercel infrastructure target is currently authorized. Vercel Hobby may be researched and compared, but Life state on Vercel is `NOT_RUN` until Vince authorizes an exact target.

Vercel remains a possible runtime-host alternative, especially for MCP/gateway hosting, but it is not selected.

## Legacy invocation work

Before the clean-slate correction, a legacy private repository contained an invocation implementation commonly referred to as PR #25. It explored several concepts that may still be valuable:

- a stable `life.invoke` tool;
- authenticated invocation;
- a canonical invocation ledger;
- separation between raw invocation facts and vector embeddings;
- 384-dimensional `gte-small` embeddings;
- vectors explicitly carrying no control authority;
- database tests and CI;
- Supabase Auth/OAuth/JWT and an Edge Function entry point.

That implementation must **not** be copied wholesale into `Vinanonymous/Build`. It was created under earlier assumptions, and later review also found implementation defects including a PostgreSQL zero-byte edge case in a text field and case-sensitive parsing of the Bearer authentication scheme.

The correct posture is: treat the legacy implementation as evidence and a set of candidate parts. Re-evaluate each part. Rebuild only what still wins.

## Repository transition

The legacy private repository is no longer the authorized Build target. `Vinanonymous/Build` is the current authorized GitHub repository.

The reason for creating a new public repository rather than automatically publishing or migrating the old one was to obtain GitHub Free enforcement without inheriting potentially stale architecture, old repository history, or unreviewed private material. Only mechanisms that survive reevaluation should enter Build.

## Continuity problem being solved now

Vince explicitly required that a future thread be able to continue Life without him re-explaining what happened. He also required maximum useful context and minimum ambiguity.

A single handoff paragraph is not sufficient because it can omit:

- the actual objective;
- the exact active component;
- user corrections;
- retired interpretations;
- decisions and their rationale;
- known failed or rejected paths;
- exact authorized-system identities;
- current verification status;
- open architecture questions;
- blockers;
- exact next action.

ChatGPT Project memory remains supplemental context only. The canonical continuity design is repo-local and Git-backed.

## Continuity bundle architecture

The bundle has four content layers plus validation machinery.

### `bootstrap.json`

The fixed entry point. It lists required files, required read order, the resume algorithm, event types that trigger continuity synchronization, and the exact recursion exemption for continuity-only synchronization commits.

### `current.json`

The compact exact current picture. It contains authorized targets, active phase/component/status, current work goal, active/retired decision IDs, unresolved questions, blockers, historical last-observed system state, and one canonical next action.

Historical observations do not satisfy fresh-verification requirements in later responses.

### `context.md`

This file. It preserves detailed narrative context, rationale, nuance, negative knowledge, and the story needed to understand why the current state exists.

### `decisions.jsonl`

Append-only typed decision history. Decisions remain addressable even after retirement. New decisions supersede old IDs rather than erasing history.

### `events.jsonl`

Append-only operational history. It records Vince directives, architecture decisions, mutations, verification transitions, blockers, next-action changes, and component transitions.

## Exact continuity synchronization triggers

Continuity synchronization is required after every successful occurrence of one of these event classes:

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

There is no gate using “important”, “material”, “meaningful”, “as needed”, or a synonym.

A repository mutation whose changed paths are a nonempty subset of the exact continuity synchronization path set defined in `bootstrap.json` is `CONTINUITY_SYNC`. It does not require a second continuity update solely because the continuity synchronization itself mutated the repository. Git history preserves its exact byte-level mutation.

## What must happen after mutations

For a successful non-continuity GitHub mutation, continuity must record the target, operation, changed paths/objects, resulting commit or object identity when available, verification result, associated decision IDs, and effect on current state before the mutation sequence is considered complete.

For Supabase or Vercel mutations, continuity must record the authorized target, operation, exact changed object identities, source Git identity when applicable, and read-back verification result.

Continuity does not authorize those mutations. It records and reconstructs them.

## Vince corrections

A later Vince correction, replacement, narrowing, or resolution supersedes the earlier target content. Future threads must not resurrect the retired interpretation unless Vince does.

Corrections are continuity events even when no repository mutation has happened yet. This is necessary because conversation can change project state before code changes.

## Current unresolved questions

1. Which permanent runtime host should expose the canonical Life MCP endpoint after fresh comparison?
2. Which exact deterministic runtime control implementation should satisfy the ten enumerated control decision kinds?
3. Which concepts from the legacy invocation implementation should survive the clean-slate rebuild?

Do not silently resolve these from prior implementation history.

## Current immediate sequence

The continuity bundle has been bootstrapped and verified first so every later Life component can benefit from deterministic recovery.

The bundle is installed and read back. The next required step is to update the Life Project Instructions so every future Life response is forced to read and validate the continuity bundle before continuing. The complete Project Instructions must remain at or below 8,000 characters.

After the Project Instruction pointer is installed, configure the minimum machine-enforced protections for `Vinanonymous/Build`, including the rules/CI structure selected under fresh research.

After that, return to the first-event problem and rederive the permanent `life.invoke` architecture.

## Cost and platform constraints

No paid plan, metered add-on, purchase, or billing commitment may be made without Vince's authorization.

GitHub Free public-repository features should be preferred when they satisfy requirements without sacrificing architecture. Supabase is currently on the Free plan. Vercel Hobby may be considered only within its current terms and limits, and no Vercel target is authorized yet.

## Reading discipline for future threads

A future thread must not treat this file as verified current external fact. It must:

1. read the required continuity bundle;
2. validate the bundle;
3. run the Project Instructions' required fresh research;
4. directly read the authorized GitHub and Supabase systems;
5. verify live objects referenced by continuity;
6. mark stale, missing, mismatched, unsupported, failed, or unverified evidence according to Project Instructions;
7. apply later Vince corrections from the current thread;
8. continue from `current.json.next_action`.

If live state conflicts with continuity, live authorized-system reads determine the external state, and continuity must be synchronized before the affected work sequence is considered complete.

## Last bundle-authoring timestamp

`2026-09-12T02:11:13Z`
