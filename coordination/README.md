# Life source coordination

This directory coordinates concurrent engineering work by multiple AI threads or humans. It has **zero Life runtime control authority**.

The authoritative source-coordination protocol is `coordination/protocol.json`. GitHub Issues, PR text, comments, reviews, and this README are visibility and explanation only.

## Work isolation

Each mutable work item gets one UUIDv4 `work_id` and one branch named exactly `work/<work_id>`. Local coding agents use one Git worktree for that branch. Remote agents write only to that branch.

Creating the empty work branch from current `main`, creating/updating/releasing lock branches, and creating/updating the work record are coordination operations. They do not require a pre-existing claim for the coordination object they create. Implementation repository-content changes and connected-app mutations do require all affected claims first.

`worker.session_id` is an audit label only. It may repeat across separate work items and does not identify the owner of a claim. Claim ownership is determined by the exact `resource_key`, `work_id`, `lease_id`, and `generation` recorded in live GitHub machine state.

## Resource claims

A work item must hold an ACTIVE, unexpired claim for every implementation resource it can mutate.

Required keys include:

- `component:<component_id>` for the component being changed;
- `repo-file:<exact_repo_path>` for every changed repository path except the work record itself;
- `external:supabase:jnenguxodtgwbskhdsxt` before any write to the authorized Supabase production project.

`integration:main` is no longer an integration gate. Pull-request creation and main integration do not require that claim. Main integration is delegated to GitHub's required Merge Queue and its `merge_group` validation.

A resource's lock branch is deterministic:

`lock/` + lowercase SHA-256 hex digest of the UTF-8 resource key.

The branch contains `coordination/lock.json`, validated by `coordination/schema/lock.schema.json`. GitHub's file-SHA update semantics provide optimistic compare-and-swap behavior: competing claim updates based on the same prior lock version cannot both succeed.

If a lock update fails because the live file changed, the worker must read the live lock again before any retry or new acquisition attempt for that resource. A stale compare-and-swap result is never retried from the stale snapshot.

Claims last exactly 14,400 seconds from the current heartbeat. Renew a claim only when 1,800 seconds or less remain. Renewal preserves the ownership cycle and immutable lease fields, advances `heartbeat_at`, and sets `expires_at` exactly 14,400 seconds after the new heartbeat.

A takeover is eligible only when the predecessor ACTIVE lease has expired; takeover increments `generation` by exactly one and creates a new work ID/lease ownership cycle. Release changes only `state` to `RELEASED` and preserves the prior owner fields for audit. A later acquisition from RELEASED increments `generation` by exactly one and receives a new `work_id`, `lease_id`, base SHA, and lease timestamps.

Executable transition enforcement starts at the exact protocol field `lock_history_enforcement_start_utc = 2026-09-12T22:56:23Z`, the recorded D-0019 decision time. Earlier lock commits remain machine-readable legacy evidence and are not retroactively converted into compliant transitions. Every lock commit at or after the enforcement timestamp is validated against its immediate predecessor. This prevents legacy behavior—such as rewriting `base_sha` inside the same live lease—from being repeated after v2 activation without making historical defects impossible to migrate past. `scripts/validate_lock_history.py` performs that branch-history validation.

## Parallel work selection

Another active work item is not a global block.

For each proposed operation, determine the exact resource-key set required by that operation. Compare that set with the resource keys held by other work items whose live locks are both `ACTIVE` and unexpired. Only the exact intersection blocks that operation.

`continuity/current.json` fields `current_component`, `current_work`, and `next_action` describe canonical engineering progression. They are not resource claims and create no exclusive ownership.

If one requested operation intersects another work item's ACTIVE unexpired claims and another requested operation does not, evaluate them separately. The non-intersecting operation may proceed with its own exact required claims. The intersecting operation remains unexecuted; it is not silently dropped.

Resource acquisition ordering applies to each acquisition attempt, not to the entire lifetime history of a work item. Keys acquired in one attempt must be unique and sorted ascending by UTF-8 resource key.

## Pull requests and Merge Queue

Every post-bootstrap PR to `main` must add or modify exactly one `coordination/work/<work_id>.json` record. It declares the worker, branch, acquisition base SHA, exact changed repository paths, external targets, and the lease generation/ID for every claim.

The work record's `base_sha` is acquisition provenance. It must be an ancestor of the PR head, but the PR branch does not have to contain today's `main` merely to obtain a valid pull-request check.

The required GitHub Actions job remains named `validate`. On `pull_request`, it validates continuity and coordination, fetches every live lock branch, verifies each lease against the work record, and rejects unclaimed changed paths. It does not require `integration:main`.

On `merge_group`, the same workflow validates the queue-generated latest-base combined commit and runs the repository and database tests. `Protect-main` must require GitHub Merge Queue, so a PR reaches `main` only through a successful merge group rather than through the removed custom integration lease.

## Continuity interaction

Mutations confined to `work/<UUIDv4>` or `lock/<64hex>` branches do not update canonical Life state and do not require a continuity synchronization solely because they occurred. Their branch history and live machine state are the exact evidence.

A normal source PR merge or other update to `main` requires continuity synchronization. The synchronization itself is recursion-safe: `continuity/bootstrap.json` includes `coordination/work/**` in `continuity_sync_paths`, so a validated continuity-sync PR whose changed paths are a nonempty subset of those exact paths is `CONTINUITY_SYNC` and its merge to `main` does not require another synchronization solely because that synchronization merged. An update to `main` outside that exact path set is never exempt.

## Visibility

A GitHub Issue may be created for a work item so Vince and other agents can see what is happening. The Issue is not a lock, authorization record, completion record, release record, or merge gate.

The bootstrap-required governance placement policy requires all open Issues in the authorized repository to be read before mutable Life repository work starts or resumes. That review is an evidence-discovery procedure only: every Issue is reevaluated against verified state, and Issue content cannot authorize a mutation or override an active claim.

## Supabase

Supabase Free currently does not include preview Branching, so direct writes to the authorized production project are serialized through the single global resource key `external:supabase:jnenguxodtgwbskhdsxt`. Every schema/function/policy/trigger/extension/database-config change and its tests must already be versioned in the authorized GitHub repository before the remote mutation, as required by the Life Project Instructions.
