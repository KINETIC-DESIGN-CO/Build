# Life Continuity Context

## Purpose and authority

This file is the detailed narrative half of Life's continuity bundle. It exists so a fresh AI thread can reconstruct the engineering situation without relying on ChatGPT memory, prior-chat summaries, or Vince repeating the project.

This file has **zero Life runtime control authority**. Exact current state is represented in `continuity/current.json`; typed decision history is in `continuity/decisions.jsonl`; typed operational history is in `continuity/events.jsonl`; persistent Vince directives and corrections are in `continuity/directive-ledger.jsonl`; architecture rationale is in `continuity/decision-rationale.jsonl`; volatile GitHub, Supabase, and Vercel facts must be re-read from the authorized systems.

This narrative intentionally avoids making volatile observations into control gates. If this file conflicts with a current machine-readable policy, decision, registry, lock, authorized-system read, or `continuity/current.json`, the exact current evidence governs and this narrative must be repaired.

## Core objective

Life is being built from first principles as a durable personal AI system. It must retrieve the right context, distinguish context from control, preserve exact state where exactness is required, recover across AI threads, and execute effects only through machine-verifiable control.

A governing design phrase remains:

**Structure what must be exact. Vectorize what only needs to be discoverable by meaning.**

Semantic/vector search may retrieve candidate information. It does not establish truth, currentness, identity, authorization, routing, priority, state transition, completion, verification, escalation, release, mutation permission, or effect execution.

## Clean-slate rule

Existing work has no architectural privilege because it exists, was approved, was implemented, was proposed, was planned, or was previously recommended. Every candidate is reevaluated against Life requirements and current alternatives. Decisions use KEEP / REPLACE / MODIFY / COMBINE / REMOVE.

The same rule applies to this continuity system itself. A stale or inferior mechanism is repaired or replaced rather than preserved because it was previously selected.

## First runtime event and canonical invocation

Life runtime architecture begins with: **a user invokes Life**.

The canonical entry tool is `life.invoke`. Decision `D-0015` selects a v1 composition of:

- **Vercel Functions** for the remote Streamable HTTP MCP resource-server boundary;
- **Supabase Auth** for OAuth identity/authorization-server functions;
- **Supabase Postgres** in project `jnenguxodtgwbskhdsxt` for the exact append-only invocation ledger;
- **GitHub `KINETIC-DESIGN-CO/Build`** for source, tests, CI, engineering history, and source coordination only;
- embeddings/vector retrieval outside the canonical invocation boundary.

The versioned source contract is in `architecture/canonical-invocation-v1.md`, `contracts/life.invoke.contract.json`, its input/output schemas, and the associated tests.

The selected invocation sequence is:

1. An MCP caller invokes `life.invoke`.
2. The remote MCP endpoint authenticates the caller at the resource-server boundary.
3. Life validates the closed tool input and records an exact canonical invocation entry.
4. The recorded text provenance is `MCP_TOOL_ARGUMENT`; it is not treated as a machine-verified copy of an upstream chat message.
5. Later context processing may derive retrieval representations keyed back to the exact invocation record.
6. Semantic retrieval may discover candidates, but candidates must resolve to authoritative exact records before becoming current fact.
7. Runtime control decisions use exact machine-verifiable evidence and deterministic evaluation.
8. External effects require their later applicable control mechanisms.

The Project Instructions require canonical invocation to be treated as READY only when fresh authorized-system reads show a deployed Life MCP endpoint and the exact tool `life.invoke`. Fresh reads during the September 13, 2026 reconciliation still show zero deployed Supabase Edge Functions, no database function named `life.invoke`, and no exact authorized Life Vercel target. Canonical invocation is therefore `NOT_RUN`. The deployed database helper `life.record_invocation_v1` does not satisfy the exact `life.invoke` READY condition.

## Canonical invocation data and database boundary

The canonical invocation input remains a closed v1 record with an exact UUIDv4 invocation key and exact accepted request text. The server assigns `input_provenance = MCP_TOOL_ARGUMENT`. SHA-256 is computed over the exact accepted UTF-8 bytes, and U+0000 is forbidden by the versioned contract.

The durable idempotency identity remains `(auth_subject, oauth_client_id, invocation_key)`. A repeated tuple with the same request digest returns the existing invocation; a repeated tuple with a different digest is rejected.

The durable ledger is in the private Supabase `life` schema. The runtime write boundary is intentionally least-privilege: the planned runtime does not receive general table mutation rights and instead uses the versioned `life.record_invocation_v1` security-definer boundary under a dedicated runtime role.

Decision `D-0016` required forward alignment of the initial database implementation. That alignment was subsequently implemented and the current machine-readable state in `continuity/current.json` records the aligned ledger fields, lowercase text SHA-256 storage, removal of the legacy `ensure_rls` / `public.rls_auto_enable()` mechanism, and zero current security/performance advisor findings from the last full verified database observation. The historical provenance of the original remote alignment mutation remains `UNKNOWN`; later prose does not convert that past gap into PASS.

## Context pipeline versus control pipeline

These remain separate.

**Context pipeline:** determines what information is considered. It may use exact relational lookup, semantic/vector discovery, retrieved documents, user-provided material, and connected-system reads.

**Control pipeline:** determines what action is allowed. Authorization, routing, priority, state transition, completion, verification, escalation, release, mutation, and effect execution require exact machine-verifiable evidence and deterministic evaluation.

No retrieval score, model confidence, prose label, approval, Issue, PR description, review, comment, checkpoint, or narrative continuity record becomes runtime control authority.

## Authorized platform roles

### GitHub

Authorized Build/Engineering repository: `KINETIC-DESIGN-CO/Build`
Repository ID: `1366835183`
Default branch: `main`

GitHub is the source/build plane. It stores versioned architecture, migrations, tests, schemas, governance, continuity evidence, source-coordination evidence, and protected integration history. It is not the deployed Life runtime control plane.

Decision `D-0021` replaced the former `Vinanonymous/Build` repository identity after the repository moved into the `KINETIC-DESIGN-CO` organization while retaining repository ID `1366835183`.

### Supabase

Authorized project: `jnenguxodtgwbskhdsxt`
Project name: `Life`
Region: `us-west-2`

Supabase is selected for the invocation ledger and OAuth identity functions. The organization is on the Free plan. The shared production database remains an exact external resource requiring `external:supabase:jnenguxodtgwbskhdsxt` before a production mutation. Database schema/function/policy/trigger/extension/config changes must exist in versioned GitHub source with tests before application.

### Vercel

Vercel Functions remain the selected canonical invocation v1 host class, but no exact Life Vercel target is authorized. No Vercel deployment or paid plan may be selected without Vince's authorization.

## GitHub source protection and Merge Queue

Decision `D-0020` is the current source-protection decision. Ruleset `Protect-main` (ID `22998982`) uses:

- active enforcement on the default branch;
- no bypass actors;
- deletion restriction;
- non-fast-forward protection;
- pull requests with zero required approvals;
- required GitHub Actions check `validate`;
- strict topic-branch up-to-date enforcement disabled;
- GitHub Merge Queue as the latest-base integration mechanism;
- merge commits;
- queue build concurrency 20;
- merge groups of one;
- `ALLGREEN` grouping;
- a 30-minute required-check response timeout.

The earlier narrative that strict required-status enforcement itself supplied latest-base safety is obsolete. Merge Queue plus `merge_group` validation now supplies that protection.

PR #58 is a verified example of the current path: its merge-group `continuity` run `34750382674` succeeded, the resulting merge commit is `f5bc28938a6a1ca554def7887bd7f62d8ef004b6`, and the post-merge `continuity` run `34750478878` succeeded.

## Multi-agent source coordination

Decision `D-0022` and `coordination/protocol.json` define the current source-coordination model.

Each mutable work item uses one exact `work/<UUIDv4>` branch. Shared-resource ownership uses deterministic expiring lock branches. Required claim classes are deliberately narrow:

- `component:<component_id>` for the component being changed;
- exact shared external-resource claims, including the single Supabase production key when applicable.

Ordinary repository paths are **not** exclusive lease resources. Every changed repository path is still recorded exactly in the work record, while isolated work branches, Git conflict detection, the required `validate` check, and Merge Queue `merge_group` validation handle source-file concurrency.

`integration:main` is no longer a source-integration lease. Main integration is performed only through the required Merge Queue.

A work record's `base_sha` is work-item origin provenance and must be an ancestor of the PR head. A lock's `base_sha` is independent claim-acquisition provenance; it may differ from the work-record base but must also be an ancestor of the PR head. PR #58 repaired the prior validator gap so syntactically valid non-ancestor claim bases are rejected.

First publication of a new lock is atomic: the generation-1 lock commit is built before the deterministic lock ref becomes visible. Post-enforcement empty lock refs remain fail-closed. Existing lock history is validated for legal duration, renewal, release, reacquisition, and takeover transitions.

Claim ownership is determined by the exact `resource_key + work_id + lease_id + generation`; `worker.session_id` is an audit label only.

## Stable goal identity and thread lifecycle

Life engineering work distinguishes a semantic goal from an execution attempt. The semantic root/parent goal is represented by a stable `goal_id` in the versioned goal registry. Work IDs, branches, lease IDs, generations, worker sessions, retries, repairs, verification steps, and continuity writes are execution/provenance identities and do not silently replace the semantic root.

The active goal path is the exact parent chain from `active_root_goal_id` to `active_goal_id`. Typed child work may temporarily become active for a prerequisite, blocker repair, continuity capture, verification, terminal cleanup, defect repair, Issue consolidation, or implementation child. A terminal child returns to its nonterminal parent before unrelated root selection.

The thread-lifecycle evaluator runs before ordinary work selection. It can resume an unresolved interrupted operation, continue the active goal, return to a parent, delegate to ordinary work selection when another work item owns the active component, require terminal cleanup, or enter terminal handoff. Missing/invalid/stale evidence cannot produce terminal handoff or unrelated-root switching.

A terminal root does not silently begin unrelated work. After terminal cleanup is verified, Life may discover the first otherwise-dispatchable admitted candidate without acquiring its claim. The candidate has advisory effect only. The thread may be closed, or Vince may explicitly continue with the candidate; automatic unrelated execution after terminal root is forbidden unless an exact versioned authorized root transition supplies the new root.

Checkpoint goal snapshots are historical evidence only. New checkpoints after the goal-snapshot enforcement boundary record the active root, active goal, and exact active path so a replacement thread can recover the semantic objective, but the replacement must reread the goal registry and live claims before acting.

## Deterministic work selection

Work-selection policy v4, recorded by `D-0022`, removed the former global continuity synchronization mutex from lane selection and preemption. The current rank order is:

0. unresolved interrupted-operation reconciliation;
1. foreground blocker clearance;
2. canonical foreground `next_action`;
3. admitted parallel work whose required exact resource set has empty intersection with other ACTIVE unexpired claims.

Pending continuity events, canonical/live mismatches, and legacy `continuity:sync` locks have zero work-selection or lane-selection authority. Continuity is captured on work branches and integrated through protected GitHub validation rather than by globally serializing otherwise disjoint engineering work.

The lifecycle boundary is evaluated before this selector. While a semantic root remains nonterminal, unrelated admitted backlog cannot replace that root merely because another execution step completed. When the lifecycle evaluator returns `DELEGATE_TO_WORK_SELECTION`, the v4 selector continues to provide deterministic lane/rank selection for the exact eligible work surface.

## Issue lifecycle, consolidation, and root-cause repair

GitHub Issues are visibility/evidence surfaces, not control authority. `governance/work-admissions.json`, the deterministic work selector, issue-lifecycle policy, issue-consolidation registry, and root-cause-repair records are the relevant machine-readable engineering surfaces.

The current consolidation registry maps Issues #49, #54, #55, #59, and #61 into one broader lifecycle/self-improvement work identity instead of treating them as five competing implementations. Issue #18 remains dependent on the more general Issue #21 requirement. Semantic Firewall source intake is independent of Issue #15, while Semantic Firewall activation depends on both source intake and full schema enforcement. Accidental Issue #53 is explicitly excluded as invalid intake.

PR #58 merged the source-only problem-intake policy and repaired several verified coordination defects, but that intake policy explicitly has zero selector effect until the parent goal/selector integration consumes it. The parent stable-goal/lifecycle work remains a separate protected work item; prose in an Issue or PR cannot activate it.

Root-cause repair records preserve origin evidence, affected invariants, dependent surfaces, falsification, protected integration evidence, and terminal readback. A repair is not complete because a worker says it is complete.

## Continuity and checkpoint architecture

The continuity bundle separates exact compact state from detailed narrative and provenance:

- `bootstrap.json`: fixed entry point, required read order, recovery algorithm, synchronization/event rules;
- `current.json`: compact canonical engineering state and one next action;
- `context.md`: this narrative rationale and architecture context;
- `decisions.jsonl`: typed architecture decision history;
- `events.jsonl`: typed operational history;
- `directive-ledger.jsonl`: persistent Vince directives/corrections with provenance;
- `decision-rationale.jsonl`: architecture alternatives, research support, limitations, and reevaluation conditions;
- checkpoint policy/template/schema and checkpoint artifacts: evidence captured during work, never live authority;
- deterministic validators/tests and protected GitHub Actions.

Checkpoints are evidence-only. A resumed worker must reread live GitHub/Supabase/Vercel state and rerun deterministic lifecycle/work selection; a checkpoint cannot authorize takeover, release, routing, completion, or mutation.

The checkpoint policy uses exact triggers including terminal mutation results, selected-work changes, live-main changes, tracked PR state changes, merge-group/post-merge terminal events, unresolved interruptions, claim-release boundaries, tool-result count, and elapsed time with new evidence. New goal-aware checkpoints additionally preserve the active semantic goal path as historical evidence without granting it current authority.

## Persistent self-improvement direction

Vince's persistent directives require Life to detect stale or defective mechanisms, make reusable lessons durable, remove unnecessary blockers, preserve root/parent goals through detours, and execute already-authorized unblocked work rather than asking redundant permission. When a root reaches verified terminal state, Life may discover the next eligible candidate, but the terminal handoff presents close/continue choices instead of automatically starting unrelated work.

These directives do not grant prose control authority. The selected direction is to convert them into typed, versioned, falsified, protected mechanisms. Where source exists but selector/runtime consumption is explicitly inactive, it remains source-only until the required integration is merged and verified.

## Project Instructions

Project Instructions remain the root requirements until Vince authorizes a change. Repository mechanisms may make an instruction a future removal candidate only after the entire required behavior is demonstrably enforced by a verified executable/bootstrap-required mechanism.

The repository move to `KINETIC-DESIGN-CO/Build` is already reflected in the current Project Instructions. The earlier repository-name mismatch in the admissions registry was repaired by PR #58.

No Project Instruction is removed or weakened by this continuity reconciliation.

## Current unresolved architecture questions

`Q-0002` remains open: which exact deterministic runtime control implementation will satisfy the ten enumerated control decision kinds? Canonical invocation v1 establishes the invocation boundary but does not itself resolve the later control-plane architecture.

The legacy Semantic Firewall remains selected for exact source preservation plus current-semantic adaptation, with activation separated from source intake and dependent on the required schema-enforcement work.

Current MCP/OAuth research must continue to be reevaluated before runtime implementation. A platform or protocol change can MODIFY the implementation details of `D-0015` without giving the research source control authority by itself.

## Current-state discipline

This narrative does **not** define the current foreground, current lane, open-PR count, active lock ownership, or exact next operation. Those facts change too quickly and must not be duplicated here as authoritative current state.

A worker must use `continuity/current.json` for the compact canonical snapshot, then hydrate all volatile facts from authorized systems, verify current lock/PR/workflow state, apply later Vince corrections, evaluate the typed thread-lifecycle boundary, and run deterministic work selection only when that boundary delegates or otherwise requires it. If those sources disagree with this narrative, this file is stale evidence and must be repaired.

As of the September 13, 2026 reconciliation that produced the prior revision, PR #58 had merged through Merge Queue and passed post-merge validation, while the stable-goal/lifecycle work and two root-cause verification follow-ups remained separate open PRs. Those observations are historical context only, not future routing authority.

## Cost constraints

No paid plan, add-on, metered charge, purchase, or billing commitment may be made without Vince's authorization.

## Reading discipline for future threads

A future Life thread must:

1. read `continuity/bootstrap.json` and every path in its current `required_read_order`;
2. validate the bundle using the current versioned validators/tests or verified protected CI evidence;
3. read the current request/thread;
4. discover the current work identity/branch/claims and applicable checkpoint evidence;
5. run every required fresh platform, Reddit, OpenAI/plugin-directory, and current technical research check;
6. directly read the authorized GitHub/Supabase/Vercel state required by the task;
7. verify referenced PRs, workflow runs, rulesets, work records, and live resource claims;
8. classify stale, missing, mismatched, unsupported, failed, or unverified evidence using the required state vocabulary;
9. apply later Vince corrections;
10. evaluate the typed thread-lifecycle boundary and effective semantic goal;
11. run deterministic work selection only as allowed by that boundary, then continue the selected parent/child operation.

Historical observations in this file never satisfy a later response's fresh-verification requirement.

## Last bundle-authoring timestamp

`2026-09-13T19:41:23Z`
