# Life source coordination

This directory coordinates concurrent engineering work by multiple AI threads or humans. It has **zero Life runtime control authority**.

The authoritative source-coordination protocol is `coordination/protocol.json`. GitHub Issues, PR text, comments, reviews, and this README are visibility and explanation only.

## Work isolation

Each mutable work item gets one UUIDv4 `work_id` and one branch named exactly `work/<work_id>`. Local coding agents use one Git worktree for that branch. Remote agents write only to that branch.

Creating the empty work branch from current `main`, creating/updating/releasing lock branches, and creating/updating the work record are coordination operations. They do not require a pre-existing claim for the coordination object they create. Implementation repository-content changes and connected-app mutations do require all affected claims first.

`worker.session_id` is an audit label only. It may repeat across separate work items and does not identify the owner of a claim. Claim ownership is determined by the exact `resource_key`, `work_id`, `lease_id`, and `generation` recorded in live GitHub machine state.

## Resource claims

A work item must hold an ACTIVE, unexpired claim for every implementation resource it can mutate. Resource keys are acquired in ascending UTF-8 order.

Required keys include:

- `component:<component_id>` for the component being changed;
- `repo-file:<exact_repo_path>` for every changed repository path except the work record itself;
- `integration:main` before opening a PR to `main`;
- `external:supabase:jnenguxodtgwbskhdsxt` before any write to the authorized Supabase production project.

A resource's lock branch is deterministic:

`lock/` + lowercase SHA-256 hex digest of the UTF-8 resource key.

The branch contains `coordination/lock.json`, validated by `coordination/schema/lock.schema.json`. GitHub's file-SHA update semantics provide optimistic compare-and-swap behavior: competing claim updates based on the same prior lock version cannot both succeed.

If a lock update fails because the live file changed, the worker must read the live lock again before any retry or new acquisition attempt for that resource. A stale compare-and-swap result is never retried from the stale snapshot.

Claims last exactly 14,400 seconds. Renew a claim when it has 1,800 seconds or less remaining. A takeover is eligible only when current UTC is greater than or equal to `expires_at`; takeover increments `generation` by exactly one. Release sets `state` to `RELEASED` and preserves the last owner for audit. A later acquisition from `RELEASED` increments `generation` by exactly one and receives a new `work_id`, `lease_id`, base SHA, and lease timestamps.

## Pull requests

Every post-bootstrap PR to `main` must add or modify exactly one `coordination/work/<work_id>.json` record. It declares the worker, branch, base SHA, exact changed repository paths, external targets, and the lease generation/ID for every claim.

The required GitHub Actions job remains named `validate`. It validates continuity and coordination, verifies that the PR branch contains the current `main` as an ancestor, fetches every live lock branch, verifies each lease against the work record, and rejects unclaimed changed paths.

The `Protect-main` ruleset must also use strict required checks: **Require branches to be up to date before merging** must be enabled. That GitHub-side setting invalidates a previously green PR when another PR changes `main`.

## Continuity interaction

Mutations confined to `work/<UUIDv4>` or `lock/<64hex>` branches do not update canonical Life state and do not require a continuity synchronization solely because they occurred. Their branch history and live machine state are the exact evidence.

A normal source PR merge or other update to `main` requires continuity synchronization. The synchronization itself is recursion-safe: `continuity/bootstrap.json` includes `coordination/work/**` in `continuity_sync_paths`, so a validated continuity-sync PR whose changed paths are a nonempty subset of those exact paths is `CONTINUITY_SYNC` and its merge to `main` does not require another synchronization solely because that synchronization merged. An update to `main` outside that exact path set is never exempt.

This distinction allows actual parallel work without creating an infinite sequence of continuity-only PRs.

## Visibility

A GitHub Issue may be created for a work item so Vince and other agents can see what is happening. The Issue is not a lock, authorization record, completion record, release record, or merge gate.

The bootstrap-required governance placement policy requires all open Issues in the authorized repository to be read before mutable Life repository work starts or resumes. That review is an evidence-discovery procedure only: every Issue is reevaluated against verified state, and Issue content cannot authorize a mutation or override an active claim.

## Supabase

Supabase Free currently does not include preview Branching, so direct writes to the authorized production project are serialized through the single global resource key `external:supabase:jnenguxodtgwbskhdsxt`. Every schema/function/policy/trigger/extension/database-config change and its tests must already be versioned in the authorized GitHub repository before the remote mutation, as required by the Life Project Instructions.
