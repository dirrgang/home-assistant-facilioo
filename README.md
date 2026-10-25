# Home Assistant Facilioo

[**Deutsch: Kurzüberblick**](#auf-deutsch) · [Installation](#installation) · [Energy Dashboard](#energy-dashboard-and-historical-statistics)

Bring **monthly heating energy (kWh), warm-water consumption (m³), and available cost data**
from your [Facilioo](https://www.facilioo.de/) resident account into Home Assistant.
The integration exposes current billing-month and cumulative sensors and imports historical
consumption and costs for the **Home Assistant Energy Dashboard**.

![Example Home Assistant Energy Dashboard showing Facilioo monthly consumption data](https://github.com/user-attachments/assets/7b8a05e1-ea2c-48ed-adfe-54795e8bbeeb)

**What to expect**

- **Energy and water:** Heating energy in kWh and warm water in m³; optional warm-water energy in
  kWh only when Facilioo supplies complete alternative-unit readings.
- **Costs and history:** Monthly costs when available, plus historical Recorder statistics for
  Energy Dashboard consumption and cost views.
- **Monthly, not live:** Facilioo provides billing/backend readings at monthly resolution, not
  real-time meter telemetry.
- **Compatibility:** Home Assistant **2026.4.0+**, a **resident account** with supported meters,
  and the regular Facilioo API. The integration is based on behavior observed with the
  **MÜNCH Immo App**; other white-label tenants are not verified. **MFA is not supported.**

This unofficial, community-maintained project is independent of and not endorsed by Facilioo or
MÜNCH. See [Installation](#installation) and [Setup](#setup) to check whether it fits your account.

## Auf Deutsch

**Facilioo für Home Assistant** importiert monatliche Heizenergie (kWh), Warmwasserverbrauch
(m³) und – falls vorhanden – Kosten aus einem Facilioo-Bewohnerkonto. Die Daten lassen sich
einschließlich historischer Werte im Energie-Dashboard verwenden; es handelt sich **nicht um
Live-Zählerdaten**. Voraussetzung ist Home Assistant **ab 2026.4.0**. Die Kompatibilität mit
anderen White-Label-Apps ist nicht bestätigt, und Anmeldungen mit MFA werden derzeit nicht
unterstützt. Die verbindlichen technischen Details sowie die
[Installationsanleitung](#installation) und [Einrichtung](#setup) stehen unten auf Englisch.

## Publicly documented Facilioo portals

Some property managers publicly identify Facilioo as their customer portal or app.
See [known Facilioo providers and portals](docs/known-facilioo-providers.md) for
source-backed examples and evidence dates. **Being listed does not mean the
property manager's accounts work with this integration**: authentication, API
access, and available consumption meters have not been verified for those portals.

## Installation

You need **Home Assistant 2026.4.0 or newer** and a **Facilioo resident account** that can
access at least one supported warm-water or heating meter. Accounts that require multi-factor
authentication (MFA) cannot currently be configured. The integration uses the regular Facilioo
backend; compatibility with other white-label providers is not guaranteed.

### HACS (recommended)

If you already have HACS installed, open this integration in your Home Assistant instance:

[![Open Facilioo in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dirrgang&repository=home-assistant-facilioo&category=integration)

This link opens the repository in HACS and can offer to add it as a **custom repository**.
Facilioo does **not** need to be in the default HACS catalog. You still need to download the
integration in HACS and restart Home Assistant.

**Fallback: add the custom repository manually**

1. Open **HACS** in Home Assistant and select **⋮ → Custom repositories**.
2. Enter `https://github.com/dirrgang/home-assistant-facilioo` and choose **Integration**
   as the repository category.
3. Add the repository, open **Facilioo** in HACS, and download the integration.
4. Restart Home Assistant, then follow [Setup](#setup).

### Manual installation

If you do not use HACS, copy `custom_components/facilioo` into the `custom_components`
directory of your Home Assistant configuration, preserving the directory name, and restart
Home Assistant. Then follow [Setup](#setup).

## Setup

Go to:

**Settings → Devices & services → Add integration → Facilioo**

Enter the email address and password of the resident account. Setup performs a login and checks
that at least one supported meter is visible. Credentials are stored only in the Home Assistant
config entry. Access tokens exist only in memory, are never entities or diagnostics, and are
discarded on unload.

If Facilioo requires multi-factor authentication, setup stops with an explicit error. The
integration never asks the backend to skip MFA and currently cannot complete Facilioo's MFA
challenge because no resident-account challenge flow has been verified.

## Features

- Warm-water consumption in m³
- Warm-water energy equivalent in kWh when supplied by Facilioo readings
- Heating energy in kWh
- Latest monthly costs in Home Assistant's configured currency
- Cumulative total sensors with `state_class: total`
- Historical consumption and cost backfill through Home Assistant's supported Recorder
  statistics API
- Incremental daily synchronization using Facilioo's `changedSince` filter
- Periodic full reconciliation to detect records that were removed from the API without a deletion
  tombstone
- Rewrites historical points when Facilioo corrects, clears, or deletes a reading
- Estimated-reading status on latest-month sensors
- German and English UI translations
- Config flow, reauthentication, diagnostics, and HACS-compatible layout
- No telemetry and no third-party data transfer

Facilioo provides billing/backend data with monthly resolution. This is not a live meter and the
integration deliberately does not poll every few minutes.

## Entities

Consumption and billing-month entities are created only when the corresponding source meter
exists. The import timestamp is available for the integration as a whole:

| Entity name | Meaning | Default |
| --- | --- | --- |
| Last successful data import | Time the latest import finished successfully | Enabled (diagnostic) |
| Warm water / heating — latest available billing month | Newest usable billing month, as YYYY-MM | Enabled (diagnostic) |
| Warm water — cumulative total | Sum of all valid monthly warm-water readings | Enabled |
| Warm water energy — cumulative total | Sum of Facilioo's monthly warm-water energy values | Enabled when complete |
| Heating energy — cumulative total | Sum of all valid monthly heating readings | Enabled |
| Warm water — latest billing month | Newest monthly value | Enabled |
| Heating energy — latest billing month | Newest monthly value | Enabled |
| Warm-water/heating cost — latest billing month | Newest monthly cost | Enabled |
| Warm-water/heating cost — cumulative total | Sum of available costs | Disabled |

Supported meters visible to the account are combined by consumption kind. Unit or meter
selection is not currently available; see the [selection design](docs/unit-meter-selection-design.md)
for the proposed boundaries and historical-data considerations.

No cold-water entity is invented. Unknown meter types and units are ignored without preventing
supported meters from working.

## Energy Dashboard and historical statistics

The **Warm water total** sensor is a valid Home Assistant water sensor (`device_class: water`,
`state_class: total`, `m³`) and can be selected under:

**Settings → Dashboards → Energy → Water consumption**

For correct pre-installation history, select only the external statistic named **Facilioo warm
water consumption history (Energy Dashboard water source)** when it is offered by the statistic
picker. Do not add both that statistic and the **Warm water total** entity as separate water
sources, because they represent the same data and would be counted twice. Heating history is
published as **Facilioo heating consumption history (Energy Dashboard gas source)**. Add it as a
**Gas consumption** source and choose **Facilioo heating cost history (Energy Dashboard gas cost)**
as its cost statistic. Home Assistant explicitly accepts energy-class statistics in kWh for a gas
source, so the integration keeps the technically correct `energy` device class and does not pretend
that the Facilioo value is a physical gas-volume reading.

If Facilioo's readings provide `currentValueInDifferentUnitOfMeasure` for every imported
warm-water month, the integration also publishes **Facilioo warm water energy history (Energy
Dashboard gas source)** in kWh. It can be added as a second gas source for domestic hot-water energy,
with the warm-water cost history selected as its cost statistic. This value comes directly from
Facilioo; the integration does not invent a fixed m³-to-kWh conversion. The original m³ water source
remains available but should not also be added if the kWh gas-source representation is the desired
dashboard model.

The external history is a Recorder statistic, not a second Home Assistant entity. Home Assistant
shows entity statistics and external statistics in the same picker even though they have different
technical origins. The normal total entity provides a current state for automations and cards; the
external statistic is necessary for authoritative pre-installation backfill and corrections. Home
Assistant does not offer a supported way to inject that backfill into the native entity statistic
without letting the sensor compiler continue it from a conflicting baseline.

When Facilioo supplies monthly costs, the integration also publishes separate cumulative cost
statistics in Home Assistant's configured currency. Warm-water costs are labelled **Energy
Dashboard source cost** so they can accompany either the m³ water source or the kWh gas-source
representation. Heating costs are labelled **Energy Dashboard gas cost**. Missing cost fields do not
erase a previously imported amount; a newer reading explicitly marked as deleted removes its month
from both cumulative histories.

### Why the backfill is an external statistic

Home Assistant 2026 uses two related Recorder paths: native sensors compile five-minute and
hourly statistics from state changes, while `async_add_external_statistics` imports authoritative
hourly statistics and safely updates a point with the same `(statistic_id, start)` key. The public
API does not provide a supported way for a custom integration to initialize the native sensor's
short-term sum baseline to an already accumulated historical total.

Importing old values under the native entity ID would therefore let the sensor compiler later
continue from a different zero point. This implementation does not rely on that unstable
combination. It exposes normal total entities for current Home Assistant state and a separate,
official external statistic for exact backfill. The total entities include a small
`historical_statistic_id` attribute to make this relationship inspectable. Consumption totals
also expose `historical_cost_statistic_id`, which points to the matching cost history.

Each historical series contains:

1. a zero baseline at the beginning of the first billing month;
2. one cumulative point at each following local month boundary;
3. aware UTC timestamps aligned to an exact hour, as Recorder requires.

For example, monthly values `0.172`, `0.766`, and `0.500 m³` produce sums `0`, `0.172`, `0.938`,
and `1.438`. A repeated sync submits the same keys and values, so Recorder updates rather than
duplicates them. If an old month changes or is deleted, the complete cumulative sequence is
recomputed and the affected boundaries are overwritten. No SQL, database-specific code, or
`.storage` manipulation is used.

Version 0.1.5 performs a one-time rebuild of only this config entry's external Facilioo series.
This removes incorrectly placed experimental month-end points written by version 0.1.3 and then
immediately imports the authoritative monthly sequence again. Other Recorder statistics and the
native sensor history are not modified.

## Synchronization behavior

The first refresh imports the complete reading history. Subsequent daily refreshes use
`changedSince` with a short overlap and merge returned revisions by stable reading ID, so repeated
results are idempotent. The synchronization watermark advances only after the response has been
parsed, aggregated, and persisted successfully.

Facilioo's API may omit hard-deleted entities instead of returning a deletion marker. To avoid
keeping such records indefinitely, the integration performs a full reconciliation every seven days.
Missing records are removed from the persisted cache, and an in-memory deletion marker is emitted
for the affected billing month during that refresh so historical Recorder statistics are corrected
without persisting a fabricated API record.

`currentValue` is nullable in the Facilioo API. A newer revision with a null value is retained as
the authoritative revision and clears the previous consumption for that meter/month instead of
leaving a stale cached value behind.

### Import freshness and billing coverage

**Last successful data import** is a timestamp diagnostic sensor. It advances only after
readings have been fetched, processed and saved to the integration's consumption cache.
A successful refresh with no new billing month still advances it. It describes the import,
not the completion of the separately scheduled Recorder statistics write or a new publication
by Facilioo. It does not certify that every upstream record was usable.

**Warm water / Heating energy — latest available billing month** are diagnostic sensors whose
states are `YYYY-MM`, independently for each supported kind. They show the newest month with
usable, non-deleted, nonnegative consumption. They are month labels, not live readings or
invented timestamps on the first day of a month. Empty, cleared or unusable history yields
**unknown**, never a zero consumption or a fabricated month.

The diagnostics remain readable during a failed refresh, preserving their last successful
values. Their `last_refresh_success` attribute distinguishes those values from the result of
the latest attempt. Existing consumption entities retain Home Assistant's normal unavailable
behavior on update failure. No startup success is fabricated: if initial setup cannot refresh,
normal setup/reauthentication handling applies. These values are not restored as a successful
import from an earlier Home Assistant run.

Billing-month entities expose privacy-minimal coverage attributes from the last successful
snapshot; diagnostics include the same summary:

| Attribute | Meaning |
| --- | --- |
| `meter_count` | Currently recognized meters of that kind |
| `meters_with_history` | Meters with at least one usable consumption month |
| `meters_in_latest_month` | Meters contributing usable readings to the displayed latest month |
| `oldest_meter_billing_month` | Oldest of each meter's latest usable months; unknown when none has history |
| `is_estimated` | At least one contributing reading in the latest month is marked estimated; unknown with no usable month |

For example, if one of three warm-water meters reaches February, another only January and
one has no usable readings, the month is `2026-02`, coverage is `1` of `3`, and the oldest
meter month is `2026-01`. The existing latest-month consumption can therefore be a partial
sum; freshness does not change that aggregation or claim completeness. `is_estimated: false`
means no contributing reading was marked estimated; it does not independently verify its
quality. Missing/null estimation flags retain the existing parser behavior.

These counts do not identify which meter is missing and do not prove that an unreported
month is due. Internal gaps, inactive/replaced meters, access changes and publication delays
cannot reliably be distinguished from the current source semantics. **No completeness flag,
missing-month zero, fixed publication deadline or stale-data alarm is invented.** Reliable
expected-month/gap detection needs separately established publication and meter-activity
semantics. Daily polling is unchanged; no extra API calls are made for these diagnostics.

## Time zones

`readingDate` must include an offset. Facilioo examples such as `2025-11-30T23:00:00Z` represent
the local German boundary at midnight. The integration converts the instant to Home Assistant's
configured time zone and looks one microsecond back from the interval end to identify the month
that ended. This also handles daylight-saving boundaries without fixed UTC-offset assumptions.

## Limitations

- Values are monthly, not real-time.
- Only data authorized for the configured Facilioo account can be imported.
- The currently verified meter metadata is type 5/M3 for warm water and type 4/KWH for heating;
  descriptive API labels are also used as a defensive fallback.
- There is no cold-water sensor unless a future, verified API source can be classified safely.
- White-label compatibility depends on the app using the regular Facilioo API and login.
- MFA challenges are detected but not yet supported.
- The API is external and may change. Unexpected records are skipped or surfaced as safe errors;
  the coordinator retains the last successful values when a refresh fails.
- The currency is taken from Home Assistant because the observed reading response provides costs
  but no reliable per-reading currency field.
- The warm-water kWh entity/statistic is available only when every imported warm-water month has
  Facilioo's alternative-unit value. A partial energy history is intentionally not published.

## Privacy and security

Communication is limited to **Home Assistant ↔ `https://api.facilioo.de`**. There is no telemetry,
analytics, or forwarding of consumption data. Logs never intentionally include credentials,
tokens, full API payloads, or account email addresses. Diagnostics contain only counts, recognized
meter categories, billing-month coverage, update time, and API status.

See [SECURITY.md](SECURITY.md) before reporting a security issue. Never attach real credentials,
tokens, unredacted diagnostics, or personal meter identifiers to a public issue.

## Development

Python 3.14.2 or newer is required for development. With [uv](https://docs.astral.sh/uv/):

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The Home Assistant test harness targets Linux. On Windows, run the commands in WSL or another
Linux environment; a native Windows run cannot import Home Assistant's Unix-only runtime modules.

All HTTP tests use mocks. No productive Facilioo or Home Assistant system is contacted.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## License

MIT — see [LICENSE](LICENSE).
