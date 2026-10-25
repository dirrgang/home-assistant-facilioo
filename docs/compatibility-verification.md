# Verifying a resident portal without expanding compatibility by assumption

Protocol reviewed **2026-10-25**; evidence coordination stays in
[#50](https://github.com/dirrgang/home-assistant-facilioo/issues/50).
The [portal directory](known-facilioo-providers.md) remains the single maintained
provider/status list. This document defines the checks and decision rules, not a
second backlog or a certification of every Facilioo-branded app.

## Evidence matrix

"Observed" below means the scope already documented in the repository, not an
independent fresh test of every path. Passing mocked tests establishes client
behavior for their inputs; it cannot confirm a resident backend's actual access.

| Behavior | Currently documented observation | Fully mocked coverage | Independent second environment |
| --- | --- | --- | --- |
| Portal/backend | Maintainer operation with MÜNCH Immo App and the regular API, as scoped in the README | Fixed API origin/version and endpoint/request checks | No report establishing a second portal variant in #50 yet |
| Login | Resident email/password path; no supported MFA completion | Login, invalid credentials, challenge detection and config-flow errors | Needed for that variant's actual login method; branding/endpoint existence is insufficient |
| Meter/type metadata | Heating kWh and warm-water m3 in the documented baseline | Dynamic ConsumptionType labels, legacy IDs, unknown type/unit exclusion | Needed to establish that the variant supplies supported meters, not just a successful login |
| Readings | Monthly billing-derived consumption, optional costs/alternative values | Pagination, offsets, nulls, estimates, revisions, deletion markers | Needed to establish actual interval/unit meaning and available history for that variant |
| Incremental/reconciliation | Current documented sync design | changedSince request shape, persisted revisions, restart and hard-deletion reconciliation | Repeated local observation needed; a one-time response does not verify future corrections/deletions |
| Home Assistant delivery | Maintainer-operated baseline described in README | Entities, reauth/identity, diagnostic freshness and external-statistics construction | Separate end-to-end install/import/dashboard check needed; an API probe alone is insufficient |

Sources: [README](../README.md), [API contract review](api-contract-v2.md),
[model tests](../tests/test_models.py), [API tests](../tests/test_api.py),
[coordinator tests](../tests/test_coordinator.py), [statistics tests](../tests/test_statistics.py),
[config-flow tests](../tests/test_config_flow.py), and [freshness tests](../tests/test_freshness.py).
No independent variation is fabricated as a fixture merely to fill the final column.
Public references in the directory prove a product relationship only.

## Bounded verification sequence

1. **Define the exact variant and consent.** The tester controls their own local
   resident account and chooses what minimized evidence may be shared. Record the
   integration release, HA version, broad account type, test date and authentication
   method. Name a public portal/product only if the tester consents; never identify
   a dwelling, resident, account or private portal link. Existing documented baseline
   testing is not an independent second white-label environment.
2. **Establish backend and login locally.** Confirm the account is authorized to use
   the regular API; do not infer it from an app name. Stop on MFA, SSO-only/incompatible
   login, revoked access or rate limiting. Do not probe alternate hosts, copy app
   session cookies, request skipped MFA, or change account settings. The official
   [authentication guide](https://developers.facilioo.de/reference/authentication)
   distinguishes full Platform scope from narrower tokens and access by account type.
3. **Inspect minimum meter/reading relationships.** Check recognized kind/unit,
   type-label classification, nullable unit/property links, and whether the account
   exposes usable monthly readings. Compare meter/unit filters with a baseline only
   when their expected scope is known. A successful response with no data proves
   neither supported meters nor correct filters. The optional
   [local probe](local-meter-probe.md) performs bounded read comparisons and exports
   aliases/shapes/counts only. It requires 1-12 recognizable warm-water meters, strict
   page metadata and a recognizable full Platform login: probe rejection alone does
   not prove the integration is incompatible.
4. **Verify monthly meaning locally.** Compare an actually available billing month,
   its unit/estimated status, optional costs and alternative-unit completeness with
   the app. Keep original reading timestamps, UTC calendar month and HA local billing
   month distinct. Do not infer conversion, currency, cumulative/interval meaning or
   full history from a field's name. The [pagination guide](https://developers.facilioo.de/reference/pagination)
   describes 1-based pages, a maximum of 100 and search pagination in the query.
   Empty date-filter queries require investigation under #76, not a compatibility verdict.
5. **Separate end-to-end verification.** If the tester separately chooses to install
   or update HA, check setup, entity values, expected external history, repeat sync,
   restart and reauthentication. Do not count native entities and external histories
   twice. This protocol or a generic code change is not authorization to operate a
   productive HA device. Mark untested paths explicitly. Do not create artificial
   deletions, corrections or password/account changes to test them in production;
   use existing legitimate observations and offline regressions instead.
6. **Review minimized evidence before sharing.** The tester reviews the reduced
   report locally. Nothing is automatically uploaded. Share only the approved portion
   in #50; distinguish source contract, mock result, API observation and HA outcome.
   A private local snapshot remains private until sharing is explicitly authorized.

No new resident account requests are executed by CI or unit tests. Tests for the
manual probe have queued synthetic responses and no network fallback.

## Capture and synthetic-fixture rules

[SECURITY.md](../SECURITY.md) and [CONTRIBUTING.md](../CONTRIBUTING.md) are the policy
sources. Do not copy a full response and try to redact it afterward for publication.
Instead, construct a new minimal synthetic example retaining only the fields needed
to reproduce a specific variation:

- Retain field names, primitive types, missing-vs-null distinctions, unit/category
  semantics and essential relationships. Replace **every** ID with independent
  synthetic IDs, consistently across meter/type/reading relationships. Never hash
  real IDs as a substitute for removing them.
- Invent readings, costs, dates, revisions and deletion markers that reproduce the
  relevant boundary; do not preserve actual consumption patterns or timestamps.
  For date-boundary behavior use an invented equivalent offset/DST case. Type-label
  text is allowed only after confirming it is a generic category, not free text
  containing a person, address or meter identifier.
- Never include tokens/JWT claims, refresh sessions, headers, credentials, emails,
  meter numbers, external IDs, private URLs or free-text location/description fields.
  Use literal invalid token strings or generated synthetic claim examples as tests
  require, never production token material or online token decoders.
- The probe's aliases are session-local; no alias-to-real-ID mapping is saved. Even
  reduced dates/counts/group patterns can be personal. Prefer qualitative results
  in public reports and include structural detail only if necessary and approved.

A generic synthetic example could use type ID `700`, meter ID `101`, reading ID
`1001` and a supported category/unit, with the reading pointing to meter `101`.
These are invented identifiers, not an upstream type enumeration. Do not add such
a fixture as "second-portal evidence" unless a legitimate actual variation exists.
Derive a focused fully mocked regression from that variation and run `mise run check`.
Passing it verifies the client fix against the example, not general live compatibility.

## Decision and status rules

Use the existing directory labels; no automatic promotion follows a login or probe:

| Result | Decision |
| --- | --- |
| Marketing/privacy-policy evidence only | Remain **Unverified** for integration compatibility |
| Provider confirms a defined API behavior | May support **Backend confirmed**, with scope/source; not an HA test |
| Credible second-environment synthetic fixture plus approved end-to-end report | May support **Community tested** for the exact release/account/auth/meter scope; no blanket guarantee |
| Maintainer validates and explicitly commits to the defined scope | May support **Maintainer supported**, with evidence and limitations |
| Reproduced incompatible path | Record **Limited / incompatible** for that specific path; preserve what works |
| Empty data, unknown kind/unit or ambiguous transient error | Keep the result inconclusive until explained; do not invent support or a defect |

Before expanding README compatibility claims, require a minimized synthetic fixture
from the second explicitly consenting environment plus credible scoped verification.
Search open/closed issues and PRs before opening an implementation follow-up. Only
an actual reproduced incompatibility with a concrete outcome justifies one; MFA,
cold water, selection, reference values and date filters already have dedicated work.
New labels, guesses about numeric type IDs or endpoint substitution are not fixes.

No second-environment variation is established by this delivery. #50 therefore
remains the live evidence surface; the protocol and manual probe can be delivered
without claiming independent verification. Review or qualify compatibility status
when backend/authentication behavior changes. Release delivery is a separate fact
from implementation, mock checks and account verification.

## Minimal approved-report outline

- Public product/portal variant (optional and consented), broad resident account type.
- Test date, HA version and integration release; installed artifact vs source branch.
- Authentication outcome: non-MFA, MFA-required, unsupported/unknown; no secrets.
- Supported/unknown meter categories and units; history present/absent/untested.
- API-only or end-to-end scope; month/unit/filter interpretations and relevant limits.
- Independently observed variation, linked minimized synthetic regression if any.
- Paths explicitly not tested, conclusions supported, and exact sharing approval.

Use #50 for the actual evidence and handoff. Keep operational status out of local
notes or duplicate provider registers.
