# Supabase Architecture migration audit — correction and structural addendum

Date: 2026-09-12
Parent audit: `architecture/audits/supabase-architecture-migration-audit-2026-09-12.md`
Work: `e5d15f24-6814-4b63-9352-95af6752fefb`
Runtime control authority: `NONE`

## Correction to parent audit

The parent audit section titled **“Live Build issue discovered during this audit”** contains one incorrect interpretation and is superseded by this section.

Continuity event `E-0087` records release of the prior `continuity:sync` claim. It does **not** state that `integration:main` was released. Therefore the earlier comparison between E-0087 and an ACTIVE `integration:main` lock was not evidence of a machine/prose inconsistency.

Fresh machine state subsequently showed `integration:main` generation 24 ACTIVE for work `b63563ed-49aa-48c2-a6f2-63493338a2cd`, “Persist legacy Life repository audit and salvage map,” lease `9ca298fc-25f0-4fb6-a334-304cfa346b15`, acquired at `2026-09-12T11:42:53Z` and expiring at `2026-09-12T15:42:53Z` unless renewed/released/replaced according to the coordination protocol.

Correct conclusion: this Architecture audit can be authored on its own claimed work branch in parallel, but it cannot create a PR to `main` while another ACTIVE unexpired `integration:main` claim is authoritative. This is ordinary expected source-coordination behavior, not a detected stale-green inconsistency.

## Additional database topology findings

A final direct structural pass across Architecture-related PostgreSQL code found:

- 42 non-internal custom triggers on `architecture` / `architecture_advisory` relations.
- 310 constraints across those schemas.
- 85 foreign keys.
- 120 indexes.
- 20 RLS-enabled tables and exactly 0 RLS policies.
- The current Performance Advisor independently reports 59 unindexed foreign keys and 3 unused indexes.

Function-family inspection across Architecture-related schemas plus `public` shows the control plane is concentrated in work/coordination machinery rather than domain data. Name-based grouping found 82 work/claim/handoff/resource/runnable functions, 22 reasoning/snapshot/rebase functions, 21 mutation/change/manifest/receipt functions, 14 review/escalation functions, 14 governance/validation functions, 7 failure/evolution functions, 5 worker-gateway functions, and 31 other functions. Across that inspected set, 125 functions are SECURITY DEFINER. Five functions have no per-function configuration; this is consistent with the current Security Advisor’s five mutable-`search_path` warnings.

Direct definition scanning found database functions that still encode Architecture-project-specific assumptions (`architecture.validate_control_plane_v1`, `architecture_gateway.gateway_probe_v1`) and multiple validation functions that explicitly reason about `service_role`. The Life project ID was not found hard-coded in these legacy function bodies. The legacy GitHub repository identity is instead hard-coded in the deployed Edge Function gateway code.

These findings strengthen—not change—the parent audit disposition: migrate protected properties and failure lessons, not the legacy function/trigger/constraint topology.

## Canonical use

For future work, read the parent audit **together with this addendum**. Where the two conflict, this addendum controls the factual correction above. All other parent-audit migration dispositions remain unchanged.
