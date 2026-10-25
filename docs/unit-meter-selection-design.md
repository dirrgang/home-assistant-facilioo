# Unit and meter selection without rewriting existing history

Reviewed **2026-10-25** for [#65](https://github.com/dirrgang/home-assistant-facilioo/issues/65),
within [#62](https://github.com/dirrgang/home-assistant-facilioo/issues/62).

## Decision

**Retain the current account-wide aggregation in this delivery.** Do not introduce
an automatic unit filter or silently migrate existing statistics. The contract
supports a future explicit set of meters, but does not establish historical unit
membership, replacement lineage or non-overlapping meter topology. There is no
reproduced single-unit defect or independently confirmed multi-unit scenario here.
This closes the bounded design investigation, not an implementation or release.

If selection is justified by a concrete multi-unit use case, use **one selected,
immutable meter set per existing account config entry**, with unit grouping only as
a selection aid. Give each different set its own entity/statistic/cache identities.
This is a conditional implementation proposal, not a new supported configuration.
A dynamic unit scope which automatically follows assignments is deferred pending
relationship evidence. No new implementation issue is created merely to promise it.

## Contract and current implementation

First-party sources: [OpenAPI v2](https://api.facilioo.de/swagger/v2.0/swagger.json),
[meter list](https://developers.facilioo.de/reference/get_api-consumption-meters),
[meter search](https://developers.facilioo.de/reference/post_api-consumption-meters-search),
and [reading search](https://developers.facilioo.de/reference/post_api-consumption-readings-search).
The source was retrieved without authentication: **4,354,131 bytes**, SHA-256
`708808c8b33e8aec8df867e986ebb980ffbfcf7120e61c7e24bb5bc5461a7228`.
The API version is v2.0, not an immutable source revision. No resident account was
accessed and no raw resident response is included.

| Contract element | Evidence / limit |
| --- | --- |
| `ConsumptionMeterRead.id` | Required int32 identity. |
| `meteredUnitId`, `meteredPropertyId` | Optional nullable int32 fields. Missing/null is valid; neither is required for a usable consumption meter. |
| Meter search | Supports `ids`, `meteredUnitId`, `meteredPropertyId`, `consumptionMeterLevel` and other filters. Prose describes property-level vs unit-level meters; it does not give historical parent/child overlap or replacement relationships. |
| Reading search | Scalar nullable `unitId` and `consumptionMeterId`; `ids` refers to reading IDs, not a list of meter IDs. Supports `changedSince`, `dates` and `orderBy`. No documented multi-meter-ID array. |
| Reading DTO | References the meter via `consumptionMeterId`; it has no historical unit-membership interval. |
| Units | `/api/units/{id}` documents a scoped unit read with ReadUnit permission. Additional unit/property calls are not needed for the initial meter-set design. |

Published endpoints and roles do not prove access or complete data for a resident
or white-label account. The schema alone does not say what happens to historic
readings when a meter moves, a tenancy ends, a meter is replaced, or access is removed.
It does not say that a property meter is independent of its unit meters. Do not infer
these relationships from similar names, units, meter numbers or current assignments.

The [model](../custom_components/facilioo/models.py) currently ignores both grouping
IDs and sums supported meters by kind after selecting the latest revision per
meter/month. The [config flow](../custom_components/facilioo/config_flow.py) permits
one entry per stable account ID. [Entities](../custom_components/facilioo/sensor.py)
use `{entry_id}_{description.key}`; external
[statistics](../custom_components/facilioo/statistics.py) use the normalized entry ID
and consumption/cost/alternative-unit suffix. The coordinator cache and historical
month store are entry-specific. No options flow or scoped cache exists.

## Proposed behavior by case

The following is future behavior; current aggregation remains unchanged:

| Case | Proposed behavior |
| --- | --- |
| One unit | Keep account-wide default and existing identities. Do not automatically reinterpret it as that unit. |
| Multiple units | Offer supported meters grouped by current unit metadata. A unit heading selects an explicit snapshot of meter IDs, reviewed before activation; do not label this as verified historical consumption of that dwelling. |
| Multiple meters of one kind | Sum each selected meter once, with revisions resolved per meter/month. Use a set, so checking a unit group and an individual meter cannot duplicate it. |
| Missing metadata | Keep supported meters selectable in an unassigned group. Do not infer a unit from labels or drop them silently. |
| Property-level meters | Keep separate from unit groups. Do not auto-add property meters to each unit; warn that overlapping main/submeter relationships cannot be detected. Explicit selection cannot by itself guarantee physical non-overlap. |
| Unsupported kind/unit | Retain conservative classification; cannot be selected into a supported series by relabeling. |
| Replacement meter | No automatic identity match. Adding/replacing a meter changes the immutable set and therefore creates a new scope/history. Include both only after confirming the intervals do not represent duplicate measurements. Same-month overlap cannot be resolved from this schema. |
| Reassigned meter | Fixed set stays fixed; grouping labels may change. Its history is meter-based, not a retroactive dwelling claim. No automatic transfer of historical readings between units. |
| Missing selected meter / removed access | Treat the scope as incomplete and do not publish a reduced total or a synthetic zero. Preserve previous history/cache and expose unavailable/needs-attention until access returns or an explicit new set is chosen. A missing meter does not prove access revocation. |
| Permission/transport/partial-page failure | Abort that refresh before saving cache, advancing watermark or deleting history; no fallback to account-wide values. |

One active source set per entry avoids automatically exposing overlapping account,
unit and individual-meter totals together. The user must still remove old overlapping
Energy Dashboard sources when switching: historical external statistics remain
selectable, and the integration must not rewrite dashboard configuration or promise
to prevent manual double counting.

## Identity and migration rules

Keep the config-entry unique ID as the authenticated account ID, so selection does
not create a duplicate login entry. Keep the current device association. For new
explicit sets, canonicalize a versioned structure such as
`{"version":1,"mode":"meters","ids":[101,102]}` with sorted unique numeric IDs,
then use its **full SHA-256** as `scope_key`. Same set/order-independent -> same key;
changed membership -> different key. Labels and current unit grouping must not enter
the identity. The hash is a local stable identifier, not anonymization of sensitive IDs.

Proposed scoped entity unique ID:
`{entry_id}_scope_{scope_key}_{description.key}`.
Proposed statistic ID:
`facilioo:{normalized_entry_id}_scope_{scope_key}_{existing_series_suffix}`.
Use the same normalization as current statistic IDs and preserve kind, cost and
alternative-unit separation. Verify Recorder constraints before implementation.
Native entity statistics and external historical statistics must remain distinct.

Existing entries without a selection remain **legacy account mode**: preserve
all entity/statistic IDs and current all-visible-meter behavior. Do not guess that
a former account history equals a newly selected set even if today's meters match.
The current owned-series layout rebuild is not a scope-migration mechanism.

On first opt-in, backfill the new scoped history under new IDs from its own full
snapshot. Do not copy legacy aggregate values, native baselines or saved month sums.
Deactivate old live entities as unavailable without emitting zero; stop writes to
that inactive scope's external history, and retain its stored statistics. Do not
clear or rename legacy series. Explain switching dashboard sources before opt-in.
Canceling selection leaves the old active scope intact.

Changing an explicit set follows the same create/backfill/activate path. Returning
to an already known set may reuse its exact identity only after a complete successful
reconciliation of that set; historic corrections are valid within the same meter
set. Returning to legacy mode resumes the account-wide stream under its original
meaning, without blending in a selected set. Selection changes require an awaited
transition that drains previous imports/statistics writes before committing the new
active scope; on failure retain the old selection. Do not allow queued old-scope
work to write to a newly activated store.

## Cache, filters and reconciliation

Each explicit scope needs independent consumption and statistics stores, including
its scope definition, readings, watermark, last-full-sync time and layout version.
Never share legacy month sums or a watermark across different scopes. Scope checks
on loading must reject mismatched stored definitions, not reinterpret the cache.

An initial implementation should retain ordinary account-wide reading search and
filter **locally by selected meter IDs** before cache/aggregation. This uses the
existing single paginated stream and avoids one request stream per meter. Validate
complete meter discovery on each sync, including selected meters; missing selection
members trigger incomplete-scope handling before saving anything. No additional
rapid polling, unit enumeration or property/administrative client is needed.

`unitId` must not be used as a historical correctness shortcut. If network needs
later justify scalar `consumptionMeterId` queries, all selected-meter streams must
succeed before a shared watermark advances; deduplicate by reading ID and validate
returned meter IDs. That optimization needs its own request/permission/error tests.

Within an unchanged scope retain the current overlap, stable reading-ID revisions,
nullable consumption handling, cost retention rules and periodic full reconciliation.
Reconciliation compares **only the same scope's complete successful snapshots**.
Reading deletions while selected meters remain available may correct that scope's
history. A scope switch, incomplete page set, missing selected meter or permission
failure must never be converted into hard-deletion tombstones. Synthetic reconciliation
tombstones remain ephemeral, as in the current coordinator.

## Synthetic examples and limits

The examples in [test_models.py](../tests/test_models.py) use invented independent
warm-water meters. IDs below are synthetic, not resident identifiers. The final
property meter is assumed independent for arithmetic only; real independence is
not established by the grouping schema.

| Meter set / conceptual group | January m3 | February m3 | History sums, including baseline |
| --- | --- | --- | --- |
| 101 + 102 / unit A | 1.25 | 1.25 | 0, 1.25, 2.50 |
| 201 / unit B | 2 | 3 | 0, 2, 5 |
| 301 / missing unit | 4 | 5 | 0, 4, 9 |
| 401 / property-level | 8 | 9 | 0, 8, 17 |
| Current account-wide combination | 15.25 | 18.25 | 0, 15.25, 33.50 |

The tests exercise the real aggregation and statistics functions for hand-picked
meter sets, including independent cost histories. A newer January revision of 101
changes unit A from 1.25 to 1.75 without replacing meter 102. These are executable
examples of arithmetic and revision behavior, **not an implemented selector,
a migration test, or confirmation of real multi-unit compatibility**. Current model
parsing still ignores the supplied grouping metadata.

## Conditional implementation acceptance

Before opening an implementation follow-up, confirm a concrete multi-unit or
meter-exclusion need and gather minimal consented relationship evidence. The
available no-MFA test account may help only if it actually exposes relevant cases;
no production access or credential sharing is required to finish this design.
Unresolved automatic dwelling-history and replacement semantics stay explicit.

A justified follow-up must implement/test:

- Optional meter metadata parsing and explicit set selection with grouping as an
  aid, unknown/unassigned/property meters handled as above, no implicit selection.
- Stable scope identity, duplicate prevention, unchanged legacy identities,
  first opt-in, cancellation, restart and switch-back; same-account reauthentication.
- Scope-isolated full/incremental/reconciliation cache and statistics stores,
  atomic selection transitions, failed import/persistence recovery and in-flight
  writer isolation. Never mix old and new scope tombstones or month histories.
- Missing selected meter/access handling without zero, silent partial totals or
  automatic scope expansion; replacement creates a new set, with overlap explained.
- Fully mocked multiple-meter revisions, nulls, estimates, costs, partial energy,
  deletions, pagination failures and empty/partial snapshots. Test actual Recorder
  entity/statistic behavior during transitions, not only hash construction.
- German/English selection/transition/error wording, dashboard switching guidance,
  secret-free minimal diagnostics and `mise run check`.

Estimated implementation effort: **4-7 development days**, excluding representative
evidence collection and real-environment verification. Account/white-label
verification remains separate under #50. Existing implementation, release delivery
and this design decision must not be presented as interchangeable.
