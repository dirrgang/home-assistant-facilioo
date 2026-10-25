# Facilioo API v2 contract verification

**Review/retrieval date:** 2026-10-24
**Tracking:** [Issue #58](https://github.com/dirrgang/home-assistant-facilioo/issues/58)

The tests compare the client with a reproducible projection of the official
[production OpenAPI document](https://api.facilioo.de/swagger/v2.0/swagger.json).
This completes the bounded specification comparison for the fields the integration
reads. It does not establish live service behavior or white-label compatibility.
No resident account or authenticated production request is involved.

## Provenance and reproduction

The source identifies itself as **OpenAPI 3.0.1**, `info.version: v2.0` (API version,
not OpenAPI language version). It publishes no build/revision date; the retrieval
date and SHA-256 identify the reviewed source precisely. The full source is about
4.15 MiB and is intentionally kept outside the repository.

The generated [schema projection](../tests/fixtures/facilioo_openapi_v2.json)
records the source URL, retrieval date, byte count and SHA-256. The independent
[request reference fixture](../tests/fixtures/facilioo_api_v2_contract.json)
records endpoint-page evidence, including pagination rules given in prose.

Reproduce the projection with Python and curl in a development environment:

```sh
curl --fail --location --show-error --max-time 60 \
  https://api.facilioo.de/swagger/v2.0/swagger.json \
  --output /tmp/facilioo-openapi-v2.json
mise exec -- python scripts/extract_api_contract.py /tmp/facilioo-openapi-v2.json \
  --retrieved-on 2026-10-24 \
  --output tests/fixtures/facilioo_openapi_v2.json --check
```

`--check` compares both content and provenance without writing files. It passes
only for the pinned source; upstream can change the document without changing its
API version. To review a newer source, omit `--check`, use its actual retrieval
date, inspect the diff, and run the checks below. Do not update expectations
silently to accept incompatible changes.

The extractor retains the seven client-used operations, their query parameters,
JSON request bodies, success response schema references and security declarations.
It copies types, formats, nullability, required fields and other constraints;
examples and descriptions are excluded. For response DTOs it projects the fields
actually consumed by the client. `x-source-required` preserves the **entire original
required list**, and `x-source-additionalProperties` preserves the original object
policy, while validation requires only selected fields and allows unread properties.
Thus the synthetic payloads validate the client projection, not full upstream DTOs.
Unconsumed login refresh/session/party fields and account profile fields are excluded;
no large transitive schema graph or generated SDK is needed. Small request and
pagination schemas are retained in full.

## Reviewed response fields

| DTO | Consumed fields and verified constraints |
| --- | --- |
| `ConsumptionMeterRead` | Required `id`/`typeId`: int32. Optional nullable `unitOfMeasure`/`number`: strings. |
| `ConsumptionTypeRead` | Required `id`: int32; `utilityName`: string. Optional nullable `meterName`: string. |
| `ConsumptionReadingRead` and `ConsumptionReadingExtended` | Required `id`/`consumptionMeterId`: int32; `readingDate`: date-time. Optional nullable `currentValue`, `currentValueInDifferentUnitOfMeasure`, `costs`: double; `isEstimated`: boolean; `deleted`/`lastModified`: date-time. |
| `LoginCommandResponse` | Required `accessToken`: string; required `account`: `AccountRead` via `allOf`. |
| `AccountRead` | Required `id`: int32, including the `/accounts/myself` fallback. |

There are **no enum restrictions on these consumed properties**. Units are nullable
strings, not an upstream enumeration of KWH/M3. IDs are integers, not an enum of
known meter types. Tests retain the integration's conservative unknown-type behavior.
Date-time validation checks RFC 3339 offsets; int32 bounds are enforced by adapting
the OpenAPI format for the test validator. OpenAPI `nullable` is adapted to JSON
Schema's null union, including composition where present.

The full reading and extended-reading DTOs agree on all consumed properties.
The extended percentage-difference properties are not read. Explicit nullable values,
omitted optional fields, fractional consumption/costs, estimated flags, offset dates,
modification timestamps and timestamp deletion markers are exercised through the
existing parsers. No confirmed behaviorally relevant incompatibility was found,
so this work does not require a runtime change or a separate bug issue.

## Request checks and deliberate defensive behavior

All seven endpoints are linked to their official reference pages in the request
fixture. Schema-validated mock sessions cover login and every consumption endpoint,
including search pagination with a stable body on each page. Tests assert 1-based
`PageNumber`, `PageSize: 100`, `orderBy: ["readingDate asc"]`, monthly `dates`, UTC
`changedSince`, the version header and bearer handling. The [pagination guide](https://developers.facilioo.de/reference/pagination)
gives the 1-based/max-100 constraints; the OpenAPI integer query schemas do not encode
these bounds. `dates` formats are likewise described in prose, not a schema pattern.

The login request requires `email`, `password` and the deprecated
`skipMultiFactorAuthentication` boolean. The tests require **false** even though the
upstream boolean schema also permits true. MFA challenge coverage remains in
[#49](https://github.com/dirrgang/home-assistant-facilioo/issues/49).

The client intentionally tolerates some shapes beyond the official contract:
missing login account with `/accounts/myself` fallback, bare lists/alternate page
wrappers, numeric coercion, and meter label/unit aliases (`meterName`, `typeName`,
`name`, `description`, `unitOfMeasurement`). These aliases are not properties of the
published meter DTO and are not presented as verified upstream shapes. Existing
fallback tests remain separate from schema-valid response tests.

Conversely, the client rejects empty tokens/utility labels, nonpositive account IDs
and nonfinite numeric values for safe processing. The published primitive schemas
do not express all these application constraints. Unsupported units/types remain
unclassified. Error response DTO bodies are not parsed; existing status/error tests
remain authoritative. These boundaries do not establish additional account access
or MFA support; white-label verification stays in [#50](https://github.com/dirrgang/home-assistant-facilioo/issues/50).

## Offline validation and maintenance

```sh
mise run check
```

The normal test suite uses only the committed projection and explicitly synthetic
[response fixtures](../tests/fixtures/facilioo_v2_responses.json). JSON Schema and
RFC 3339 validation are development dependencies only. Mock sessions have no network
fallback and fail on unexpected calls; tokens are literal non-JWT test strings.
Tests also ensure required/type/nullability/format violations fail schema validation,
and that extraction fails when a selected upstream property disappears.

Automatic CI downloads would make unrelated changes depend on API availability,
DNS, upstream edits and rate limits. Therefore source refresh is an explicit reviewed
development step, while CI stays deterministic and offline. Passing CI checks the
pinned contract and client, not future upstream drift or real-account compatibility.

The separate [MFA and session investigation](mfa-session-design.md) reviews the
challenge/refresh contract and records the evidence gates for future MFA support.

The [extended-readings endpoint decision](extended-readings-decision.md) compares
all four reading routes and retains ordinary search for the current sync scope.

The [unit and meter selection design](unit-meter-selection-design.md) records the
current aggregation boundary and a conditional migration-safe selection proposal.
