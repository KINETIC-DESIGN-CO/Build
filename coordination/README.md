# Life source coordination

This directory coordinates concurrent engineering work by multiple AI threads or humans. It has **zero Life runtime control authority**.

The authoritative source-coordination protocol is `coordination/protocol.json`. Deterministic engineering work selection is defined by `governance/work-selection-policy.json`. GitHub Issues, PR text, comments, reviews, and this README are visibility and explanation only.

## Work isolation

Each mutable work item gets one UUIDv4 `work_id` and one branch named exactly `work/<work_id>`. Local coding agents use one Git worktree for that branch. Remote agents write only to that branch.

Creating the empty work branch from current `main`, creating/updating/releasing lock branches, and creating/updating the work record are coordination operations. They do not require a pre-existing claim for the coordination object they create. Implementation mutations require the exact protocol claims for the component or shared external resources affected by that operation.

`worker.session_id` is an audit label only. It may repeat across separate work items and does not identify the owner of a claim. Claim ownership is determined by the exact `resource_key`, `work_id`, `lease_id`, and `generation` recorded in live GitHub machine state.

## Resource claims

A work item must hold an ACTIVE, unexpired claim for each protocol-defined shared resource it mutates.

Required keys include:

- `component:<component_id>` for the component being changed;
- `external:supabase:jnenguxodtgwbskhdsxt` before any write to the authorized Supabase production project;
- any other exact external target declared by the work item when that target requires a claim under the protocol.

Ordinary repository paths are **not** exclusive lease resources. Every changed repository path is still recorded exactly in the work record, but file concurrency is handled by isolated work branches, Git conflict detection, the required `validate` check, and Merge Queue `merge_group` validation.

`integration:main` is not an integration gate. Pull-request creation and main integration do not require that claim. Main integration is delegated to GitHub's required Merge Queue and its `merge_group` validation.

A resource's lock branch is deterministic:

`lock/` + lowercase SHA-256 hex digest of the UTF-8 resource key.

The branch contains `coordination/lock.json`, validated by `coordination/schema/lock.schema.json`. GitHub's file-SHA update semantics provide optimistic compare-and-swap behavior: competing claim updates based on the same prior lock version cannot both succeed.

### First lock publication

For a resource with no existing lock branch, the first visible lock ref must already point to a commit containing a valid ACTIVE generation-1 `coordination/lock.json`. Do **not** create the lock branch at `main` or another base commit and then add the lock file in a later mutation.

The exact first-acquisition sequence is:

1. Build the generation-1 lock JSON in memory without publishing a lock ref.
2. Create a Git tree that contains `coordination/lock.json` on top of the exact acquisition base.
3. Create a commit whose parent is that acquisition base and whose tree contains the lock file.
4. Create the deterministic `lock/<64hex>` ref directly at that prebuilt commit.
5. Read back the ref and `coordination/lock.json` before treating the claim as acquired.

Until step 4, no lock ref exists. This prevents another validator from observing a post-enforcement lock branch with no lock snapshot while acquisition is between API calls. A persistent empty lock branch remains invalid and `scripts/validate_lock_history.py` continues to reject it.

If a lock update fails because the live file changed, the worker must read the live lock again before any retry or new acquisition attempt for that resource. A stale compare-and-swap result is never retried from the stale snapshot.

Claims last exactly 14,400 seconds from the current heartbeat. Renew a claim only when 1,800 seconds or less remain. Renewal preserves the ownership cycle and immutable lease fields, advances `heartbeat_at`, and sets `expires_at` exactly 14,400 seconds after the new heartbeat.

A takeover is eligible only when the predecessor ACTIVE lease has expired. Takeover increments `generation` by exactly one and must use a new `lease_id`. The durable `work_id` may remain the same when the same nonterminal work item resumes under a new lease, or differ when a different work item takes over. Release changes only `state` to `RELEASED` and preserves the prior owner fields for audit. A later acquisition from RELEASED also increments `generation` by exactly one and must use a new `lease_id`; it preserves `work_id` when reacquiring the same durable work item and uses a different `work_id` only for a different work item.

The work record's `base_sha` is the work item's branch-origin provenance and must be an ancestor of the PR head. Each lock's `base_sha` is that claim acquisition's provenance. A later legal claim acquisition may therefore have a different `base_sha` from the work record, but its claim base must also be an ancestor of the PR head.

Executable transition enforcement starts at the exact protocol field `lock_history_enforcement_start_utc = 2026-09-12T22:56:23Z`, the recorded D-0019 decision time. Earlier lock commits remain machine-readable legacy evidence and are not retroactively converted into compliant transitions. Every lock commit at or after the enforcement timestamp is validated against its immediate predecessor. `scripts/validate_lock_history.py` performs that branch-history validation.

## Parallel work selection

Another active work item is not a global block.

For each proposed operation, determine the exact resource-key set required by that operation. Compare that set with the resource keys held by other work items whose live locks are both `ACTIVE` and unexpired. Only the exact intersection blocks that operation.

`continuity/current.json` fields `current_component`, `current_work`, and `next_action` describe canonical engineering progression. They are not resource claims and create no exclusive ownership.

If one requested operation intersects another work item's ACTIVE unexpired claims and another requested operation does not, evaluate them separately. The non-intersecting operation may proceed with its own exact required claims. The intersecting operation remains unexecuted; it is not silently dropped.

Resource acquisition ordering applies to each acquisition attempt, not to the entire lifetime history of a work item. Keys acquired in one attempt must be unique and sorted ascending by UTF-8 resource key.

Current work-selection v4 uses work-branch continuity capture and gives legacy `continuity:sync` locks zero lane-selection and preemption effect. A legacy continuity lock is historical coordination state, not a global engineering-work barrier.

## Pull requests and Merge Queue

Every post-bootstrap PR to `main` must add or modify exactly one `coordination/work/<work_id>.json` record. It declares the worker, branch, work-item origin SHA, exact changed repository paths, external targets, and the lease generation/ID for every declared claim.

The required GitHub Actions job remains named `validate`. On `pull_request`, it validates continuity and coordination, checks that the work record exactly covers the changed repository paths, fetches every declared live lock branch, and verifies each required lease against the work record. It does not require `integration:main` or exclusive repository-file leases.

On `merge_group`, the same workflow validates the queue-generated latest-base combined commit and runs the repository and database tests. `Protect-main` requires GitHub Merge Queue, so a PR reaches `main` only through a successful merge group rather than through the removed custom integration lease.

## Continuity interaction

Work-selection v4 treats repository continuity as work-branch capture plus protected integration. Continuity update events required for a work item are recorded on that work branch before terminal completion. Work-branch and lock-branch coordination mutations do not create an additional continuity-capture requirement solely because those mutations occurred.

Continuity changes reach `main` through the same required `validate` check and GitHub Merge Queue as the rest of the work item. If Git or a merge group reports a conflict, the worker must reread current `main`, reconcile, and revalidate before retrying. Repository continuity projections have zero cross-work-item claim effect, and volatile GitHub, Supabase, or Vercel facts still require fresh authorized-system reads.

## Visibility

A GitHub Issue may be created for a work item so Vince and other agents can see what is happening. The Issue is not a lock, authorization record, completion record, release record, or merge gate.

The bootstrap-required governance placement policy requires all open Issues in the authorized repository to be read before mutable Life repository work starts or resumes. That review is an evidence-discovery procedure only: every Issue is reevaluated against verified state, and Issue content cannot authorize a mutation or override an active claim.

## Supabase

Supabase Free currently does not include preview Branching, so direct writes to the authorized production project are serialized through the single global resource key `external:supabase:jnenguxodtgwbskhdsxt`. Every schema/function/policy/trigger/extension/database-config change and its tests must already be versioned in the authorized GitHub repository before the remote mutation, as required by the Life Project Instructions.
