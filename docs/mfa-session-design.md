# Resident MFA and session renewal investigation

Reviewed **2026-10-25** for [#63](https://github.com/dirrgang/home-assistant-facilioo/issues/63),
within [#62](https://github.com/dirrgang/home-assistant-facilioo/issues/62).

## Decision and evidence boundary

**Defer runtime MFA support until the bootstrap and session uncertainties below are
resolved.** The documented protocol supports a concrete design, but does not prove
a complete resident-account flow. This research decision completes the investigation;
it does not enable MFA, announce a release, or verify another white-label portal.
Keep `skipMultiFactorAuthentication: false` and the current unsupported-MFA message.
No resident account was contacted.

Sources are the official [authentication guide](https://developers.facilioo.de/reference/authentication)
and [OpenAPI v2 document](https://api.facilioo.de/swagger/v2.0/swagger.json).
The source had 4,354,131 bytes and SHA-256
`b97e8a210bd2604fe455d8b30ae38cee09236e1302a473d44632a14fd551c98a`.
The specification gives API version v2.0, not an immutable release date.
The guide was readable; the documentation index was inaccessible through the web
reader and individual endpoint markdown requests returned HTTP 403. Endpoint/model
findings below therefore use the retrieved OpenAPI descriptions and schemas.

The [bounded snapshot](../tests/fixtures/facilioo_mfa_openapi_v2.json) preserves six
operations and their small DTOs. `LoginCommandResponse` omits the optional `party`;
`AccountRead` retains only `id`. Original required fields and additional-property
policy are recorded for those projections. Examples validate the projection, not
the complete account DTO. The previous consumption-contract snapshot is unchanged.

## Documented contract

All operations use POST and API version 2.0. A missing operation-level security
requirement below is what the specification declares, not proof of all runtime
access rules. No global security requirement is declared in the reviewed source.

| Operation | JSON request | Success response / authorization |
| --- | --- | --- |
| `/api/auth/login` | `email`, `password`, required deprecated `skipMultiFactorAuthentication` boolean | `LoginCommandResponse`: required `accessToken`, `refreshToken: AuthSession`, `account`; optional nullable `party`. No declared bearer requirement. |
| `/api/auth/challenge/get` | `CreateChalllengeRequest` (upstream spelling): `email`, `password` | `MultiFactorChallenge`: required `nonce`, `accessToken`, `maskedProvider`, integer `providerTypeId`. No declared bearer requirement. |
| `/api/auth/challenge/resend` | `nonce` | `Void`; bearer required, description requires **Multi Factor Challenge (1)** scope. Described as resending email. |
| `/api/auth/challenge/complete` | `nonce`, `token` (submitted code, distinct from bearer) | `LoginCommandResponse`; bearer required, description requires **Multi Factor Challenge (1)** scope. |
| `/api/auth/refresh` | `refreshToken` string | `TokenPair`: `accessToken`, `refreshToken: AuthSession`; no declared bearer requirement. |
| `/api/auth/logout` | `refreshToken` string; optional nullable `logoutEverywhere`, default false | `Void`; removes refresh token; no declared bearer requirement. |

`AuthSession` requires `accountId` (int32), `token` (string), `issuedAt` and `expiresAt`
(date-times), `hasExpired`, `hasBeenRedeemed`, and `isPasswordChangeRequired` (booleans).
Refresh/logout submit **`refreshToken.token`**, not the whole session object.
The guide calls refresh tokens JWTs, but neither primitive schemas nor examples
establish token validity. Example strings in tests are deliberately not usable JWTs.

The guide distinguishes normal `platform` scope from narrower MFA/password-change
scopes. The challenge response's `accessToken` must therefore stay isolated from
the Platform token. Presence of an `accessToken` string alone cannot establish a
completed login. The numeric endpoint scope label does not establish the exact JWT
claim encoding of a challenge token. Do not infer it from the label or send a token
to an online decoder. Local claim parsing alone would not verify a token signature.

## Current integration and proposed states

The current [client](../custom_components/facilioo/api.py) logs in at every full or
incremental fetch, keeps only an in-memory access token/account ID, and clears these
on 401/unload. Its MFA detection handles missing-token challenge markers and
400/409 marker responses (regressions in #49). It does not parse token scope or
retain `AuthSession`. The [config flow](../custom_components/facilioo/config_flow.py)
validates credentials and meters in one step; reauthentication replaces credentials
and reloads. There are no challenge, refresh, or logout client methods.
This is a design gap for future MFA, not a newly reproduced production defect.

The following state machine is a **proposal**, including local UI policy rather
than undocumented assertions about backend errors:

| State / event | Proposed transition and handling |
| --- | --- |
| Credentials submitted | Ordinary login with skip=false. A verified full session proceeds to account/meter validation. A confirmed MFA-required result offers challenge creation with the supplied credentials. Exact detection/bootstrap remains an evidence gate. |
| Challenge created | Keep nonce, challenge bearer and provider information only in the active flow. Show code input and an explicit resend action for a verified supported provider; reject unknown providers safely. No consumption calls with challenge bearer. |
| Code submitted | Send nonce + code in `token`, challenge bearer in Authorization. On verified full session, validate account identity and supported readings, then commit the entry/session. |
| Invalid code | Keep input step only for a reliably identified retryable error; show a generic translated error without echoing code, bearer or server payload. No automated guessing. |
| Expired challenge / unauthorized | Discard challenge state and restart credentials/challenge; do not interpret every 401 as a wrong code. Exact error mappings require evidence. |
| Resend | Explicit user action; respect rate limits. Request carries current nonce and challenge bearer. Whether nonce/code validity changes is undocumented: do not assume replacement or unlimited reuse. |
| Cancel / flow timeout / HA restart before completion | Drop credentials, code, nonce and challenge bearer held by the flow. Start a new interactive flow; no persisted pending challenge. Local timeout policy must be chosen separately from server TTL. |
| Restart after completion | Load the persisted refresh session; renew as needed without another code. Expired/revoked session leads to reauthentication. |
| Access expiry / API 401 | Serialize refresh per entry; refresh once, persist the rotated session before another consumer can use it, then retry a safe read once. No infinite login/refresh loop. |
| Reauthentication | Repeat the interactive flow, require the same account ID, atomically replace credentials/session and reload. Cancellation does not replace the existing entry or its histories. |

## Session lifecycle and storage proposal

The guide explicitly says a refresh token is **one-time usable** and that every
successful refresh yields a new pair whose refresh token must be stored for the
next request. Access expiry is represented by JWT `exp`; expired access yields 401.
The schema provides refresh expiry/status fields, but specifies no fixed lifetime,
rotation grace window, concurrent-redemption behavior, or detailed revocation rules.
Password changes, logout-everywhere and scope upgrades must not be guessed to have
specific invalidation effects. `isPasswordChangeRequired` needs explicit handling;
no password-change flow is in scope here.

Durable refresh support is a prerequisite to useful unattended MFA: re-running the
current daily password login could demand a new interactive challenge every day
and after restart. Persist the minimum refresh session needed for rotation/expiry
in HA-managed config-entry data; document that it is a secret protected by the HA
configuration/backups, not encrypted storage promised by this integration. Keep
access tokens and pending challenge data in memory. Redact every new secret field
from diagnostics/errors/logs. Do not store submitted codes or provider identifiers
in diagnostics. Preserving passwords versus migrating existing entries to
refresh-only sessions needs an explicit follow-up storage/migration decision.

Use a per-entry lock to prevent simultaneous use of a one-time refresh token.
Do not retry an old token blindly after a refresh timeout: the server might already
have redeemed it. If the rotated response cannot be saved, stop using the session
and require reauthentication rather than reporting durable success. A crash between
server rotation and local persistence remains a recovery case, not a transaction
that can be made atomic across both systems.

Routine unload should discard in-memory tokens without logging out the durable
session needed after restart. Explicit removal/session revocation should attempt
logout of that entry's refresh token with `logoutEverywhere: false`, then remove
local secrets even if the service is unreachable. The API does not guarantee that
logout invalidates an already issued access token immediately. Global logout
would affect other sessions and must not be an implicit cleanup action.

## Synthetic checks and reproduction

[Offline examples](../tests/test_mfa_contract.py) use an exhausted-on-extra-call
`AsyncMock` for challenge creation, resend, completion, refresh rotation and logout.
They validate each request/response against the pinned projection, require the
challenge bearer where declared, and pass the new refresh string to logout.
`providerTypeId: 123` is an arbitrary schema-valid value, not a provider mapping.
Invented expiry dates are examples, not a lifetime claim. No login-to-challenge
exchange or error payload is fabricated as upstream evidence. The tests prove
schema consistency of examples, not an implemented state machine or real MFA.

Reproduce from public bytes without credentials:

```sh
curl --fail --location --show-error --max-time 60 \
  https://api.facilioo.de/swagger/v2.0/swagger.json \
  --output /tmp/facilioo-mfa-openapi.json
mise exec -- python -m scripts.extract_mfa_contract /tmp/facilioo-mfa-openapi.json \
  --retrieved-on 2026-10-25 \
  --output tests/fixtures/facilioo_mfa_openapi_v2.json --check
mise run check
```

CI remains offline. A changed hash/contract requires deliberate review; it is not
a reason to silently regenerate expectations.

## Evidence gates and conditional follow-up

Before implementation, obtain first-party clarification or minimal independently
consented, sanitized evidence for:

- Login-to-challenge bootstrap: actual MFA signal, intended use/order of `login`
  and `challenge/get`, and whether an MFA response can itself contain a token.
- Challenge JWT scope encoding, provider ID mapping and supported resident
  providers, code format, challenge TTL, invalid/expired code behavior, resend
  invalidation and retry/rate-limit rules. The specification gives 401 for
  complete/resend but no distinguishing error DTO or other error guarantees.
- Resident refresh issuance after challenge completion, rotation/expiry/revocation
  behavior, password-change-required handling and logout behavior in that flow.

These are evidence dependencies; no owner action or productive account access is
required for this delivered research. White-label confirmation stays in #50.
Ask only for minimized synthetic shapes and status categories; never public raw
responses, resident identifiers, masked real contact details, credentials or tokens.

Once gates are resolved, a bounded implementation could cover the session client,
HA user/reauth code steps, storage migration, translations and documentation in
roughly **5-8 development days**, excluding evidence collection and real-environment
verification. This is a design estimate, not a release commitment. Do not open a
speculative implementation issue before those gates justify it. A follow-up must
require fully mocked tests for all transitions above, strict token separation,
rotation concurrency and lost-response/persistence recovery, identity-preserving
reauthentication, secret-free diagnostics, no automatic global logout, and
`mise run check`. Independent real-account verification and release delivery must
be recorded separately from those mocked implementation checks.
