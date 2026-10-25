# Publicly documented Facilioo property-management portals

**Last source review:** 2026-10-23

This is a **non-exhaustive, source-backed list** of property managers that have
publicly identified Facilioo as a customer portal, branded app, or service
provider. It helps residents recognize a possible Facilioo-backed portal and
helps contributors prioritize further compatibility investigations.

**This is not a general compatibility guarantee.** Only the specifically
described MÜNCH Immo App resident-account configuration has been tested by
the integration maintainer. A public reference to Facilioo does **not**
establish that another resident account can authenticate against the regular
Facilioo API, exposes heating or hot-water meter readings, or is compatible
with `home-assistant-facilioo`. White-label implementations can differ,
and multi-factor authentication is currently unsupported.

The integration's known working environment is described in the
[README](../README.md#installation): the regular Facilioo API as observed
through the MÜNCH Immo App. MÜNCH is the only entry below with
maintainer-tested integration compatibility; every other provider remains
unverified.

## Evidence categories

- **Customer portal/app:** The property manager's own website identifies a
  Facilioo customer-facing portal or app.
- **Service disclosure:** The manager's privacy notice names Facilioo as a
  service provider for customer data or portal access. This is not
  necessarily evidence of a particular app, login method, or meter API.
- **Historical reference:** An older published account of Facilioo adoption;
  continued use is **not confirmed**.

## Integration compatibility statuses

The **Compatibility status** column concerns this integration's technical
compatibility with a particular **resident-account portal**, *not* the quality
of the evidence that the property manager uses Facilioo. It must not be
inferred from branding, app listings, privacy policies, or the presence of
a Facilioo-powered portal.

- **Unverified:** No specific resident-account backend or end-to-end
  integration compatibility has been verified. This is the default for
  entries without account-specific evidence, including historical references.
- **Backend confirmed:** The property manager or platform provider has
  specifically confirmed relevant resident API, authentication, and/or
  consumption-data behavior for a defined portal. This does **not** establish
  that the Home Assistant integration works there.
- **Community tested:** A user has supplied a credible, anonymized
  end-to-end integration report, identifying the integration version, account
  type, authentication outcome, and available meter categories. This is
  **not** a blanket compatibility or maintenance guarantee.
- **Maintainer supported:** The integration maintainers have validated a
  specific portal/account variant and explicitly documented its supported
  scope and limitations.
- **Limited / incompatible:** A concrete compatibility limitation or
  failure has been reproduced and documented for a defined portal/account
  variant; identify what works and what does not.

These are **evidence labels, not automatic stages**. Multiple labels may
apply (for example, *Backend confirmed; Community tested*), and a label
must be reviewed or removed if backend behavior changes. Each status other
than *Unverified* must be accompanied by a link to an appropriately
anonymized public report or other verifiable source.

## Publicly documented portals and services

| Property manager | Publicly described portal / relationship | Evidence | Compatibility status | Source | Checked |
| --- | --- | --- | --- | --- | --- |
| Clevesta GmbH | Facilioo customer/owner portal; privacy notice also mentions a separate Impower portal | Customer portal + service disclosure | Unverified | [Privacy notice](https://clevesta.de/legal/datenschutz) | 2026-10-23 |
| Cornely & Roth GmbH | Facilioo customer portal/app; another service portal is also offered | Customer portal/app | Unverified | [Customer login](https://www.cornely-roth.de/kundenlogin) | 2026-10-23 |
| GfH – Gesellschaft für Hausverwaltung mbH (Saarbrücken-Dudweiler) | “Zuhause – effizient verwaltet” customer app and Facilioo portal | Customer portal/app | Unverified | [Customer portal](https://gfhdudweiler.de/kundenportal/) | 2026-10-23 |
| Haustakt GmbH | Facilioo customer portal available by web browser or app | Customer portal/app | Unverified | [Customer portal](https://www.haustakt.com/kundenportal) | 2026-10-23 |
| Immo-Agentur MGL GmbH | Facilioo property portal for selected customers | Customer portal | Unverified | [Property management](https://www.immo-mgl.de/verwaltung) | 2026-10-23 |
| Kassenbrock Hausverwaltung | “Kassenbrock HV App powered by facilioo” and customer portal | Branded customer app | Unverified | [App information](https://www.kassenbrock.de/unsere-app/) | 2026-10-23 |
| KREMER Hausverwaltungen GmbH | Facilioo online portal/app used for customer-data administration | Service disclosure | Unverified | [Customer privacy notice](https://www.kremerhv.de/datenschutzhinweise) | 2026-10-23 |
| MoVida | “MoVida Mieterportal” provided through a Facilioo platform | Customer portal + service disclosure | Unverified | [Privacy notice](https://movidaliving.de/datenschutzerklaerung/) | 2026-10-23 |
| MÜNCH Wohnungsverwaltung GmbH (MÜNCH Immobiliengruppe) | “MÜNCH Immo-App”; Facilioo-backed property portal; one maintainer-tested resident-account configuration | Customer portal/app + maintainer test | [Maintainer supported](#maintainer-tested-scope-muench-immo-app) | [Current MÜNCH portal](https://xn--mnch-0ra.de/mein-muench/) · [MÜNCH brochure (2021, p. 16)](https://s9d56e8dc6a45f17f.jimcontent.com/download/version/1629279571/module/16217164024/name/WEG-Broschuere_2021.pdf) | 2026-10-23 |
| RS Hausverwaltung | Facilioo customer portal; the website also describes a planned transition to Facilioo Neo | Customer portal/app | Unverified | [Customer portal](https://www.rshv.de/kundenportal/) | 2026-10-23 |
| Strauß & Bock Immobilien | Facilioo customer portal for owners, tenants, and contractors | Customer portal/app | Unverified | [Customer login](https://strauss-bock.de/kundenlogin/) | 2026-10-23 |
| Wolf-Immobilien-Management GmbH | Facilioo app for tenants and owners | Customer app | Unverified | [Management services](https://www.w-i-m-immobilien.de/verwaltung) | 2026-10-23 |

### Maintainer-tested scope: MÜNCH Immo App

The maintainer developed and has operated this integration with a
**resident account using the regular Facilioo API through the MÜNCH Immo
App**, including available monthly heating-energy and warm-water
consumption data. This is the **Maintainer supported** scope for the
specific tested configuration, as reflected in the
[README's compatibility and setup guidance](../README.md#installation).

MÜNCH's [current portal page](https://xn--mnch-0ra.de/mein-muench/)
identifies the MÜNCH Immo-App. Its [2021 company brochure (page 16)](https://s9d56e8dc6a45f17f.jimcontent.com/download/version/1629279571/module/16217164024/name/WEG-Broschuere_2021.pdf)
explicitly identifies Facilioo as the underlying property portal.
The brochure is **historical evidence of the platform relationship**;
the actual integration use is based on maintainer testing, **not**
provider-side technical certification or endorsement.

This status does **not** guarantee compatibility with every MÜNCH
resident account, property, authentication method, or meter setup.
In particular, the integration does not support MFA challenges.
No private account details or real consumption readings are published.

## Historical reference — current use unconfirmed

| Property manager | What the source establishes | Evidence | Compatibility status | Source | Checked |
| --- | --- | --- | --- | --- | --- |
| Promeda Hausverwaltung GmbH | Company history records introduction of Facilioo as a cloud/customer portal in **2020**; continued use in 2026 is not established by this source | Historical reference | Unverified | [Company history](https://www.promeda.de/ueber-uns/) | 2026-10-23 |

A provider can change software or operate several different portals at the
same time. Information from a privacy policy or provider website may remain
online after a transition. Entries should be revised or moved to the
historical section when evidence changes.

## Contributing evidence or compatibility reports

Follow the [verification protocol](compatibility-verification.md) for account-specific
checks, minimized synthetic evidence and the distinction between API and end-to-end
results. Existing status definitions here remain authoritative.

To add or update a provider, open a documentation pull request with a
**first-party source URL**, the exact product or relationship it describes,
the source's publication date if available, and the **date you reviewed it**.
Keep reports of actual integration compatibility separate from publicly
documented product use. For a status change, link the supporting evidence
and state its scope. A provider's public Facilioo reference alone is not
grounds for **Backend confirmed**, **Community tested**, or **Maintainer
supported**. An integration compatibility report should identify the tested
release, type of resident account, authentication path, and available meter
types, **without personal or account-specific details**.

Do **not** include credentials, access tokens, residents' names or addresses,
meter IDs, screenshots of private portals, unredacted diagnostics, or real
API responses in public issues or pull requests. See
[SECURITY.md](../SECURITY.md) and [CONTRIBUTING.md](../CONTRIBUTING.md).
