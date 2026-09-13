# Semantic Firewall v1 — Build-native control boundary

## Status

Source-only implementation. Runtime control authority is `NONE`.

This package adapts the byte-verified legacy `contracts/semantic-firewall/` corpus into the current Build architecture without modifying the imported legacy bytes. Passing source tests, CI, review, or Merge Queue does not activate Life runtime control.

## Role

The Semantic Firewall sits between context/intention formation and any Life control decision for the closed decision-kind set:

`AUTHORIZATION`, `ROUTING`, `PRIORITY`, `STATE_TRANSITION`, `COMPLETION`, `VERIFICATION`, `ESCALATION`, `RELEASE`, `MUTATION`, `EFFECT_EXECUTION`.

It accepts only closed typed requests bound to exact contract, subject, action, scope, operation digest, and input-snapshot digest. It does not infer PASS from prose, labels, reviews, model confidence, apparent completeness, or semantic similarity.

## Evidence states

Required evidence may be `KNOWN`, `UNKNOWN`, `UNVERIFIED`, or `NOT_RUN`.

- Missing, `UNKNOWN`, `UNVERIFIED`, `NOT_RUN`, or stale required evidence produces `NOT_RUN`.
- Identity, source-type, type, future-time, or digest mismatch produces `FAIL`.
- `PASS` occurs only when every required input is exact, fresh where bounded, type-correct, source-allowed, and digest-bound.

`FAIL` takes precedence over `NOT_RUN` when both are observed in one evaluation so detected tampering or contradiction cannot be hidden by a simultaneous missing-input condition.

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

Those JSON fields and a self-hash do **not** establish trusted issuance by themselves. Any PASS produced by the source evaluator, including source-level effect-eligibility evaluation, has zero Life runtime control authority until the future trusted control service verifies authoritative receipt persistence/readback and the non-bypassable effect router consumes that authoritative evidence.

The trusted persistence/issuance mechanism is not implemented by this source slice and cannot be substituted by changing source fields in prose or model output.

## Reliability integration

Semantic Firewall v1 does not create a second retry/recovery plane. It combines with `reliability/*`.

Before a protected effect, the effect request must bind an exact `reliability_operation_contract_id` and a durable write-ahead `prepared_attempt_ref`. After execution, Semantic Firewall verification can return PASS only when the supplied reliability evidence says:

- source class is `AUTHORITATIVE_READBACK`;
- the exact operation digest matches;
- `effect_state = EFFECT_VERIFIED`;
- `required_postconditions_state = PASS`.

Retry, compensation, quarantine, and parent restoration remain owned by `reliability/recovery-policy.json`.

## Bootstrap and CI enforcement

`contracts/semantic-firewall-v1/spec.json` is bootstrap-required reading so future Life workers receive the source-level fail-closed semantics before making architecture or implementation decisions. The schemas, evaluator, validator, and falsification tests are bootstrap-required files and the repository `validate` workflow runs the Semantic Firewall validator. This is engineering/source enforcement only; it does not create Life runtime control authority.

## Relationship to canonical invocation

`life.invoke` remains the append-only invocation boundary. `RECORDED` means only that an authenticated, validated MCP tool argument was durably recorded. It never implies Semantic Firewall authorization or effect eligibility.

## Legacy dispositions

- Closed ten decision kinds: **KEEP**.
- Exact control request/input binding: **KEEP / COMBINE**.
- Legacy falsification corpus: **KEEP** as immutable reference evidence.
- Rebuilding the imported source from memory: **REMOVE**.
- Treating Structured Outputs/model schema adherence as authorization: **REMOVE_AS_REPLACEMENT**.
- Build-native reliability write-ahead/readback/postcondition layer: **COMBINE**.
- Wholesale restoration of the legacy runtime architecture: **REMOVE**.

## Activation boundary

This source slice is not runtime activation. Runtime activation remains blocked until a versioned trusted receipt persistence/issuance mechanism, exact non-bypassable effect routing, live deployment wiring, and authoritative live readback are separately implemented, protected, and verified.
