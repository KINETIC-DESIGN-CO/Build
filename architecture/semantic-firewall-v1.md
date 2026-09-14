# Semantic Firewall v1 — Build-native control boundary

## Status

Source-only implementation. Runtime control authority is `NONE`.

This package adapts the byte-verified legacy `contracts/semantic-firewall/` corpus into the current Build architecture without modifying the imported legacy bytes. Passing source tests, CI, review, or Merge Queue does not activate Life runtime control.

## Role

The Semantic Firewall sits between context/intention formation and any Life control decision for the closed decision-kind set:

`AUTHORIZATION`, `ROUTING`, `PRIORITY`, `STATE_TRANSITION`, `COMPLETION`, `VERIFICATION`, `ESCALATION`, `RELEASE`, `MUTATION`, `EFFECT_EXECUTION`.

It accepts only closed typed requests bound to exact contract, subject, action, scope, operation digest, and input-snapshot digest. It does not grant runtime control authority from prose, labels, reviews, model confidence, apparent completeness, semantic similarity, or a caller-authored source label.

## Evidence states

Required evidence may be `KNOWN`, `UNKNOWN`, `UNVERIFIED`, or `NOT_RUN`.

- Missing, `UNKNOWN`, `UNVERIFIED`, `NOT_RUN`, or stale required evidence produces `NOT_RUN`.
- Identity, source-type, type, future-time, or digest mismatch produces `FAIL`.
- Source-level `PASS` occurs only when every required input is exact, fresh where bounded, type-correct, source-label-compatible with the selected contract, and digest-bound.

`FAIL` takes precedence over `NOT_RUN` when both are observed in one evaluation so detected tampering or contradiction cannot be hidden by a simultaneous missing-input condition.

Every result emitted by the source evaluator carries `runtime_control_authority = NONE`. Source-level `PASS` proves only the deterministic checks implemented by this source evaluator. It is not an authorization, routing, completion, release, mutation, or effect-execution permission.

## Evidence provenance boundary

The legacy control-input-binding work proved a critical limitation: `source_type`, `source_ref`, and `source_version` are caller-supplied structural claims unless a trusted evidence adapter actually performs the authoritative read and issues the observation.

Semantic Firewall v1 therefore treats those fields only as source-level compatibility/binding labels. A contract listing an `accepted_source_type` does not make that source authoritative, and a self-consistent input snapshot does not prove that the named system issued it.

Runtime activation requires a separate versioned trusted-evidence-adapter contract and implementation that:

- performs the authoritative system read outside model/planner control;
- binds the observation to machine-verifiable adapter/issuer identity;
- prevents caller/model-authored `source_type`, `source_ref`, or `source_version` fields from manufacturing trusted provenance; and
- supplies only adapter-issued evidence to the authoritative control service.

Model responses, model judgment, prose, Issue text/labels/comments, PR text/reviews, model confidence, and semantic similarity remain zero-authority inputs. A control contract cannot elevate any of them into authoritative evidence merely by whitelisting a source-type token.

Trusted evidence adapters are **not implemented** by this source slice. Their absence is an activation blocker, not an invitation to infer provenance from source labels.

## Receipts

The source evaluator can emit only a `CANDIDATE` receipt from issuer type `SOURCE_EVALUATOR`. That receipt has zero effect authority.

An effect is eligible only when a separate trusted persistence/issuance mechanism supplies a receipt with:

- `decision = PASS`;
- `decision_kind = EFFECT_EXECUTION`;
- `issuer_type = TRUSTED_CONTROL_SERVICE`;
- `persistence_state = PERSISTED_TRUSTED`;
- a self-consistent receipt digest;
- exact subject/action/scope/operation binding;
- an unexpired evaluation window.

Those JSON fields and a self-hash do **not** establish trusted issuance by themselves. Any PASS produced by the source evaluator, including source-level effect-eligibility evaluation, has zero Life runtime control authority until the future trusted control service verifies trusted evidence-adapter issuance, authoritative receipt persistence/readback, and the non-bypassable effect router consumes that authoritative evidence.

The trusted evidence and receipt persistence/issuance mechanisms are not implemented by this source slice and cannot be substituted by changing source fields in prose or model output.

## Reliability integration

Semantic Firewall v1 does not create a second retry/recovery plane. It combines with `reliability/*`.

Before a protected effect, the effect request must bind an exact `reliability_operation_contract_id` and a durable write-ahead `prepared_attempt_ref`. After execution, Semantic Firewall verification can return source-level PASS only when the supplied reliability evidence says:

- source class is `AUTHORITATIVE_READBACK`;
- the exact operation digest matches;
- `effect_state = EFFECT_VERIFIED`;
- `required_postconditions_state = PASS`.

That source-level PASS still has `runtime_control_authority = NONE`; the future trusted control service must independently establish authoritative evidence issuance and consumption.

Retry, compensation, quarantine, and parent restoration remain owned by `reliability/recovery-policy.json`.

## Bootstrap and CI enforcement

`contracts/semantic-firewall-v1/spec.json` is bootstrap-required reading so future Life workers receive the source-level fail-closed semantics before making architecture or implementation decisions. The schemas, evaluator, validator, and falsification tests are bootstrap-required files and the repository `validate` workflow runs the Semantic Firewall validator. This is engineering/source enforcement only; it does not create Life runtime control authority.

## Relationship to canonical invocation

`life.invoke` remains the append-only invocation boundary. `RECORDED` means only that an authenticated, validated MCP tool argument was durably recorded. It never implies Semantic Firewall authorization or effect eligibility.

## Legacy dispositions

- Closed ten decision kinds: **KEEP**.
- Exact control request/input binding: **KEEP / COMBINE**.
- Caller-described provenance fields as proof of trustworthy evidence issuance: **REMOVE_AS_AUTHORITY**.
- Trusted evidence-adapter issuance requirement from the legacy audit: **KEEP / STRENGTHEN**.
- Legacy falsification corpus: **KEEP** as immutable reference evidence.
- Rebuilding the imported source from memory: **REMOVE**.
- Treating Structured Outputs/model schema adherence as authorization: **REMOVE_AS_REPLACEMENT**.
- Build-native reliability write-ahead/readback/postcondition layer: **COMBINE**.
- Wholesale restoration of the legacy runtime architecture: **REMOVE**.

## Activation boundary

This source slice is not runtime activation. Runtime activation remains blocked until all of the following are separately versioned, implemented, protected, and verified:

1. trusted evidence adapters and machine-verifiable evidence issuance/consumption;
2. trusted receipt persistence/issuance and authoritative receipt readback;
3. exact non-bypassable control/effect routing;
4. live deployment wiring; and
5. authoritative live runtime readback.
