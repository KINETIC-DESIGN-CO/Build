# Canonical invocation v1

## Status and authority

This document selects the source architecture for Life's first runtime event: a caller invokes `life.invoke`.

This file and the contract files beside it have zero Life runtime control authority. They define versioned Build requirements and test targets. Runtime authorization, mutation, and effect execution remain subject to deployed machine-verifiable controls.

Selected composition:

- remote MCP transport/resource server: **Vercel Functions**;
- OAuth 2.1 authorization server and identity provider: **Supabase Auth** in project `jnenguxodtgwbskhdsxt`;
- canonical invocation ledger: **Supabase Postgres** in project `jnenguxodtgwbskhdsxt`;
- Build/source plane: **GitHub** repository `KINETIC-DESIGN-CO/Build`;
- embeddings/vector retrieval: **outside canonical invocation v1**.

The Vercel host class is selected, but no exact Life Vercel project is authorized. Deployment to Vercel is therefore `NOT_RUN`.

Current authorized Supabase reads show zero public tables, zero deployed Edge Functions, no `life.invoke` database function, and no installed `vector` extension. Canonical invocation is therefore `NOT_RUN`.

## Host comparison

### Vercel Functions — SELECT / COMBINE

Use Vercel Functions as the remote Streamable HTTP MCP resource server.

Current Vercel MCP guidance explicitly models the MCP server as an OAuth resource server. `mcp-handler` provides protected-resource discovery and `withMcpAuth`; token verification against the selected identity provider remains application code. The guidance is current to MCP 2026-07-28 and forbids forwarding a caller bearer token to an upstream service.

This separates transport from identity and data storage without adding a second database.

Current Vercel Hobby terms are for personal/non-commercial use. This architecture selects the host class for Life's current personal objective; a different use class requires reevaluation before deployment, and no paid Vercel plan may be selected without Vince's authorization.

### Supabase Edge Functions — REPLACE as the v1 MCP front door

Keep Supabase for Auth and Postgres, but do not select Edge Functions as the v1 remote MCP transport.

The current Supabase "Deploy MCP servers" guide uses `--no-verify-jwt` and states that authenticated MCP support at the Edge Function layer is coming. Building the permanent front door there now would require custom transport-auth work that the selected Vercel path already exposes directly.

### Cloudflare Workers — REMOVE from v1

Do not add Cloudflare to Life v1. It would create a third infrastructure platform and its current Free Worker CPU limit is 10 ms per request. Life v1 does not need that additional platform to obtain current MCP/OAuth support.

### GitHub — KEEP as source plane only

GitHub remains source, CI, coordination, and engineering evidence. It is not a Life runtime host or runtime control authority.

## OAuth and caller boundary

The MCP endpoint is an OAuth 2.1 resource server. It does not issue access tokens.

The authorization server is Supabase Auth with issuer:

`https://jnenguxodtgwbskhdsxt.supabase.co/auth/v1`

The implementation must:

1. publish RFC 9728 protected-resource metadata for the exact MCP resource URL;
2. require bearer authentication for `life.invoke`;
3. validate the JWT signature through the Supabase JWKS endpoint;
4. require exact issuer equality;
5. require exact audience equality to the deployed MCP resource URL;
6. require `sub`, `exp`, and `client_id`;
7. validate `nbf` when present;
8. reject tokens that fail any check;
9. never store the raw access token;
10. never forward the caller access token to Postgres or another upstream service.

Supabase OAuth 2.1 currently supports Authorization Code with PKCE, refresh tokens, dynamic client registration for MCP-compatible clients, and JWKS validation. Custom OAuth scopes are not currently supported, so Life v1 does not use a custom scope string as its authorization gate.

Tool-call permission requires an exact active machine record keyed by authenticated subject and OAuth client ID. The table and migration for that record are part of the implementation phase; prose, consent text, tool annotations, and model judgment cannot satisfy that gate.

The current authorized-system connector does not expose the live Supabase OAuth-server enablement or JWT-signing-key configuration. Those settings are `NOT_RUN` until a later deployment step can verify them directly. V1 deployment requires OAuth Server enabled and asymmetric JWT signing verified before the endpoint can become READY.

## Exact input boundary

`life.invoke` accepts the object defined by `contracts/life.invoke.input.schema.json`.

The canonical text is the exact decoded `request_text` MCP tool argument. It is **not** claimed to be a machine-verified copy of the user's original ChatGPT message.

The server assigns provenance:

`MCP_TOOL_ARGUMENT`

The caller cannot override provenance.

The implementation performs no trim, Unicode normalization, case folding, or newline normalization. It requires strict UTF-8 encoding after JSON decoding and computes SHA-256 over those exact UTF-8 bytes. A decoded string that cannot be encoded as strict UTF-8 is rejected as `REQUEST_TEXT_INVALID_UNICODE`.

`request_text` rules:

- JSON Schema character length: 1 through 65,536;
- UTF-8 byte length: 1 through 262,144;
- U+0000 is forbidden;
- any U+0000 occurrence returns `REQUEST_TEXT_U0000_FORBIDDEN`.

The U+0000 rule is explicit because PostgreSQL text cannot store the zero character.

## Idempotency

The caller supplies a lowercase UUIDv4 `invocation_key`.

The durable uniqueness key is:

`(auth_subject, oauth_client_id, invocation_key)`

If that key already exists with the same `request_sha256`, return the existing invocation with `replayed=true`.

If that key already exists with a different `request_sha256`, return:

`INVOCATION_KEY_REUSE_MISMATCH`

This is the only basis for the tool's `idempotentHint=true` annotation. MCP annotations are hints, not enforcement.

## Canonical invocation ledger

The selected store is a non-public Supabase Postgres schema named `life`.

The v1 ledger table is `life.invocations`. The implementation migration must define at least:

- `invocation_id uuid` — server-generated primary key;
- `schema_version smallint` — exactly `1`;
- `invocation_key uuid` — caller idempotency key;
- `recorded_at timestamptz` — database-generated UTC timestamp;
- `auth_subject text` — exact validated JWT `sub`;
- `auth_issuer text` — exact validated issuer;
- `oauth_client_id text` — exact validated client ID;
- `audience text` — exact validated MCP audience;
- `tool_name text` — exactly `life.invoke`;
- `input_provenance text` — exactly `MCP_TOOL_ARGUMENT`;
- `request_text text` — exact decoded tool argument after the v1 validation rules;
- `request_sha256 text` — lowercase SHA-256 hex of exact UTF-8 bytes;
- `request_utf8_bytes integer`;
- `mcp_protocol_version text` — actual request protocol version;
- `runtime_build_sha text` — exact deployed source commit SHA.

The table is append-only from the runtime path. No embedding, vector, bearer token, model confidence, semantic-readiness label, or effect-authorization state belongs in this record.

A separate exact caller-allowlist table controls whether `(auth_subject, oauth_client_id)` may invoke the tool. Its state set must be an exact enumeration, not free-form prose.

## Database write boundary

The Vercel runtime uses one dedicated Postgres login role through Supavisor transaction-mode pooling.

The runtime role receives no direct table INSERT, UPDATE, or DELETE privilege.

Its only invocation-ledger write capability is EXECUTE on:

`life.record_invocation_v1`

That function must be `SECURITY DEFINER`, use an empty fixed `search_path`, schema-qualify referenced objects, enforce the idempotency rule, and enforce every server-side ledger invariant. EXECUTE is revoked from `PUBLIC` and granted only to the dedicated runtime role.

The runtime role must not use the `postgres` role or a broad Supabase service-role credential.

## Success semantics

A successful call returns the object defined by `contracts/life.invoke.output.schema.json`.

`state = "RECORDED"` means only:

- caller authentication passed;
- caller allowlist state passed;
- the v1 input invariants passed;
- the exact MCP tool argument was durably recorded.

`RECORDED` does not mean:

- an external effect is authorized;
- context retrieval is complete;
- retrieved information is true or current;
- a later control transition may pass;
- the model's interpretation is verified.

## Context/control boundary

Canonical invocation creates exact provenance and a durable entry record. It does not collapse context retrieval and runtime control into one pipeline.

Later context processing may create embeddings or semantic indexes keyed back to `invocation_id`. Those derived records are separate from `life.invocations` and have zero runtime control authority.

Authorization, routing, priority, state transition, completion, verification, escalation, release, mutation, and effect execution remain exact control decisions evaluated by later machine-verifiable mechanisms.

## Legacy invocation dispositions

The machine-readable dispositions are in `contracts/life.invoke.contract.json`.

Summary:

- stable `life.invoke` tool — KEEP;
- authenticated invocation — KEEP;
- canonical invocation ledger — KEEP;
- exact invocation boundary separate from embeddings — KEEP;
- vectors have zero control authority — KEEP;
- migrations/tests/CI — KEEP;
- Supabase Auth/OAuth/JWT — COMBINE with Vercel resource-server transport;
- Supabase Edge Function as MCP front door — REPLACE;
- `gte-small` 384-dimensional embedding inside canonical invocation — REMOVE from v1 and defer to context architecture;
- legacy manual Bearer parser — REMOVE;
- claim that `request_text` is a machine-verified raw ChatGPT user message — MODIFY to exact MCP-tool-argument provenance;
- any assumption that PostgreSQL text accepts U+0000 — REMOVE;
- Project Instructions routing directly to database tables — REPLACE with the stable `life.invoke` tool boundary.

## Implement-now sequence

1. Version and merge this architecture, the machine-readable contract, JSON Schemas, and contract tests.
2. Version a Supabase migration and tests for the `life` schema, invocation ledger, caller allowlist, runtime role/grants, immutable-write rules, and `life.record_invocation_v1`.
3. Version the Vercel MCP server source and tests without deploying it.
4. Apply the already-versioned Supabase migration to project `jnenguxodtgwbskhdsxt` only while the required Supabase production claim is active; read back every created object.
5. Obtain Vince authorization for one exact Vercel project target before any Vercel creation or deployment.
6. Configure and directly verify Supabase OAuth Server, asymmetric JWT signing, exact MCP audience binding, and caller allowlist state.
7. Deploy the versioned MCP server to the authorized Vercel target.
8. Verify the live protected-resource metadata, OAuth flow, JWT checks, exact `life.invoke` tool schema, idempotency, database record, and failure cases.
9. Verify that the current ChatGPT account/workspace can invoke a write-capable custom MCP tool. Current public OpenAI documentation makes write-capable custom MCP availability plan/workspace dependent, so this gate remains unverified until account-specific evidence exists.
10. Only after current authorized-system reads show the deployed endpoint and exact `life.invoke` tool does canonical invocation become READY.

Building a temporary Supabase Edge MCP front door before the selected Vercel source would create transport/authentication code that would later be removed or rebuilt. V1 source therefore targets the selected composition immediately while remote deployment waits for exact-target authorization.

## Current external evidence

These sources were checked on 2026-09-12. They are research evidence, not runtime authority, and must be rechecked before deployment:

- Vercel MCP OAuth resource-server guide: https://vercel.com/i/mcp-server-oauth-authorization
- Vercel pricing: https://vercel.com/pricing
- Cloudflare Workers limits: https://developers.cloudflare.com/workers/platform/limits/
- Supabase OAuth 2.1 Server: https://supabase.com/docs/guides/auth/oauth-server
- Supabase MCP Authentication: https://supabase.com/docs/guides/auth/oauth-server/mcp-authentication
- Supabase OAuth Flows: https://supabase.com/docs/guides/auth/oauth-server/oauth-flows
- Supabase MCP Edge deployment guide: https://supabase.com/docs/guides/ai-tools/byo-mcp
- Supabase connection pooling: https://supabase.com/docs/guides/database/connecting-to-postgres/pooling-and-limits
- MCP 2026-07-28 release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- OpenAI ChatGPT developer mode and MCP apps: https://help.openai.com/en/articles/12584461
