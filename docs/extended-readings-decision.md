# Extended consumption readings: endpoint decision

Reviewed **2026-10-25** for [#64](https://github.com/dirrgang/home-assistant-facilioo/issues/64),
within [#62](https://github.com/dirrgang/home-assistant-facilioo/issues/62).

## Decision

**Retain ordinary readings search for full, incremental and reconciliation imports.**
There is no documented extra consumption, cost or alternative-unit field needed
by today's entities or historical statistics. Do not add a supplemental request or
replace the endpoint merely because an extended route exists. This concludes the
investigation without a runtime implementation follow-up.

The extended DTO's two extra percentages could support future year-over-year
presentation. Their reference periods, calculation/zero-baseline rules and
multi-meter aggregation need evidence under [#68](https://github.com/dirrgang/home-assistant-facilioo/issues/68).
Do not sum percentages or mistake reference averages for the resident's prior-year
consumption. No new compatibility, backend-data-availability or release claim follows
from this contract comparison.

## Sources and reproducibility

The [official OpenAPI v2 document](https://api.facilioo.de/swagger/v2.0/swagger.json)
was retrieved without authentication. Source bytes: **4,354,131**; SHA-256:
`121bb1bf36ad99b3c2febc9ebe1437ce73853c82d478015b43c81aa6af1d4408`.
It identifies API v2.0 / OpenAPI 3.0.1, with no immutable revision date.
The official [extended GET reference](https://developers.facilioo.de/reference/get_api-consumption-readings-extended)
and [pagination guide](https://developers.facilioo.de/reference/pagination) were also read.
The bounded [review projection](../tests/fixtures/facilioo_readings_review.json)
contains the four read operations, complete reading DTOs, shared search request and
page wrappers. It excludes upstream examples/descriptions; authorization descriptions
were compared in the original source and are summarized below. Existing #58 runtime
contract expectations remain unchanged.

```sh
curl --fail --location --show-error --max-time 60 \
  https://api.facilioo.de/swagger/v2.0/swagger.json \
  --output /tmp/facilioo-extended-openapi.json
mise exec -- python scripts/extract_api_contract.py /tmp/facilioo-extended-openapi.json \
  --retrieved-on 2026-10-25 --readings-review \
  --output tests/fixtures/facilioo_readings_review.json --check
mise run check
```

Normal tests are offline; updating source provenance or accepting contract drift is
an explicit review step. No resident login, meter request or full real response was
used for this work. Schema equivalence does not establish equal actual responses
for a particular account; that requires separate consented, local verification.

## Contract comparison

All four routes return paginated readings, require a bearer token, and document
Platform scope plus ManageConsumptionMeter (29). Both families list User (7), Admin
and Property Management Company. Ordinary routes also list Pool Manager, Contractor,
Insurance Broker and Insurer; extended routes do not. Listed roles are not a guarantee
of data availability or access for any resident or white-label portal. The integration
must preserve safe authorization-error handling rather than assume extended access.

| Route | Filtering and sorting | Result |
| --- | --- | --- |
| GET `/api/consumption-readings` | Query `PageSize`, `PageNumber`, `SortByAttributeName`, `AscendingOrder`; no documented `changedSince` | `ConsumptionReadingRead` page |
| POST `/api/consumption-readings/search` | Pagination in query; `ConsumptionReadingSearchRequest` JSON | `ConsumptionReadingRead` page |
| GET `/api/consumption-readings-extended` | Query `PageSize`, `PageNumber`; no documented sorting/filter arguments | `ConsumptionReadingExtended` page |
| POST `/api/consumption-readings-extended/search` | Same query pagination and exact same search request schema as ordinary search | `ConsumptionReadingExtended` page |

Search supports `orderBy`, `changedSince`, `dates`, `ids`, `searchTerm`, `unitId`,
`consumptionMeterId`, and creation/modification bounds. `changedSince` includes
entities created or modified on/after the timestamp. `dates` matches explicitly
listed months/years, not a continuous range. The current client uses UTC timestamps,
an overlap, and `orderBy: ["readingDate asc"]`; it does not expose extended search.
The documented sort schema is an array of strings, not a guarantee of snapshot
isolation or tie ordering during concurrent backend changes.

Pagination is 1-based, up to 100 items per page; search POST pagination also belongs
in the query. Fewer items than requested do not imply completion. Both wrappers
share page metadata (`items`, `pageNumber`, `totalPages`, `totalCount`, previous/next
flags); only the item DTO reference differs. Existing client pagination handles
these wrappers and fails on unexpected/unbounded shapes.

Both DTOs have identical required fields and identical constraints for every shared
property. In particular both provide optional nullable `currentValue`, `costs`,
`currentValueInDifferentUnitOfMeasure`, `averageReferenceValue`, and
`averageReferenceValueInDifferentUnitOfMeasure`. Required identity/date fields and
optional `lastModified`, `deleted` and `isEstimated` also agree. Only extended adds
nullable doubles `valuePercentageDifferenceToLastYear` and
`costPercentageDifferenceToLastYear`.

Neither reference averages nor the extra percentages are currently parsed. The
specification does not establish reference population, interval meaning or percentage
weighting. Costs and warm-water energy are already parsed from ordinary readings;
missing ordinary values are not evidence that extended contains replacements.
There is no confirmed data-loss defect or documented need to merge both routes.

## Network and failure tradeoff

- Retaining ordinary search uses one paginated reading stream per sync alongside
  existing login/meter/type requests. It preserves current cache and correction
  semantics without adding a failure dependency.
- Replacing it with extended search would have the same number of reading requests
  for an equal number of rows/pages, but larger records. Actual latency, population
  and resident permissions have not been measured. A replacement has no demonstrated
  user-visible benefit for the current scope.
- A supplemental query adds its own pages (roughly doubles reading requests for
  equal full streams), payload and rate-limit exposure. A future optional comparison
  feature must isolate its failures, so unavailable extended data cannot discard a
  successful ordinary consumption import. Avoid automatic dual-route fallback and
  merging on guessed relationships. Stable IDs, revision behavior and permissions
  would need explicit tests/evidence before any such design.

## Synthetic demonstration and regression boundaries

The added tests in [test_api_contract.py](../tests/test_api_contract.py) drive the
real parser and pagination across all four routes using strictly queued mock
responses validated against the complete reading DTOs. Extended search is invoked
through existing private pagination/parsing primitives for research only; it is not
a new runtime API. Shared synthetic rows produce:

| Series | January | February | Cumulative boundaries including baseline |
| --- | --- | --- | --- |
| Warm water (m3) | 0.75 | 0.25 | 0, 0.75, 1.00 |
| Costs | 7.25 | 2.75 | 0, 7.25, 10.00 |
| Alternative energy (kWh) | 36.5 | 13.5 | 0, 36.5, 50.0 |

The extended examples add a negative percentage and a null percentage without
changing monthly values or Recorder statistics. A second case clears February's
alternative value: both families retain m3/cost history and suppress the incomplete
initial energy history. No fixed conversion is introduced. This proves processing
equivalence for equal shared data, not backend equivalence for live accounts.

Regression requirements for any future route change remain:

| Case | Observable expected behavior / existing coverage |
| --- | --- |
| Multiple/capped/empty pages | Visit each page once, preserve body/filters, no duplicate totals. API pagination tests and the new four-route two-page comparison cover this. |
| Absent/null consumption or cost | Null consumption must supersede a previous revision; missing cost must not erase an already imported cost unless its month is explicitly removed. Model, coordinator and statistics tests cover these distinct layers. |
| Revisions/estimates | Newer meter/month revision wins; corrections shift later sums, repeat imports are idempotent. Existing model/statistics tests cover this. |
| Deletion marker / hard deletion | Tombstone removes the affected month; periodic complete reconciliation detects disappearance and keeps fabricated tombstones out of the persisted API cache. Existing coordinator/statistics tests cover both paths. |
| Incomplete alternative values | Suppress partial initial energy history, preserve volume/costs; never invent missing kWh or conversions. Existing model/statistics tests and the new cross-route partial case cover this. |
| Permission/transport/rate-limit failure | Keep errors distinct, retain last successful data and do not change endpoints silently. Existing API/coordinator error tests remain required. |
| Future extra fields | Nullable reference/percentage values require semantic evidence and a separate aggregation design under #68 before presentation; no speculative entity/percentage implementation is tested here. |

Independent runtime verification, if offered later, should compare local route
results for the same account/scope/date range without publishing credentials,
identifiers or payloads. It can reveal a backend difference, which would justify a
focused follow-up; its availability does not block this bounded contract decision.
