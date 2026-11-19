# Facilioo for Home Assistant

[![Release](https://img.shields.io/github/v/release/dirrgang/home-assistant-facilioo)](https://github.com/dirrgang/home-assistant-facilioo/releases/latest)
[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](#installation)
[![Home Assistant 2026.4+](https://img.shields.io/badge/Home%20Assistant-2026.4%2B-41BDF5?logo=homeassistant&logoColor=white)](#requirements)
[![Home Assistant validation](https://github.com/dirrgang/home-assistant-facilioo/actions/workflows/validate.yml/badge.svg?branch=master)](https://github.com/dirrgang/home-assistant-facilioo/actions/workflows/validate.yml)

**Your heating and hot-water consumption from your Facilioo resident account, in the Home
Assistant Energy Dashboard, including every month before you installed the integration.**

[**Deutsch**](#auf-deutsch) · [Requirements](#requirements) · [Installation](#installation) ·
[Energy Dashboard](#energy-dashboard) · [FAQ](#faq)

![Home Assistant Energy Dashboard showing monthly consumption imported from Facilioo](https://github.com/user-attachments/assets/7b8a05e1-ea2c-48ed-adfe-54795e8bbeeb)

Facilioo runs the resident portals and apps of a number of German property managers. Those
portals show your monthly heating and hot-water consumption. This integration brings the same
numbers into Home Assistant, so you can see them next to the rest of your energy data.

## Highlights

- **Heating and hot water:** heating energy in kWh and hot water in m³ for each billing month.
- **Costs:** monthly costs in your Home Assistant currency, if your property manager publishes
  them.
- **Your full history:** all past months are imported during setup, so the Energy Dashboard
  shows your history from the first day.
- **Automatic updates:** checks for new data once a day and applies corrections Facilioo makes
  to earlier months.
- **Private:** connects only to Facilioo and sends no telemetry or analytics.
- **German and English:** the setup dialog and sensor names are translated.

## Requirements

- **Home Assistant 2026.4.0** or newer.
- A **Facilioo resident account** (email address and password) that shows heating or hot-water
  consumption.
- **No multi-factor authentication (MFA)** on that account. Accounts with MFA can't be set up
  yet.

> [!NOTE]
> **Tested with the MÜNCH Immo App.** The integration was developed and tested with a resident
> account in the MÜNCH Immo App, which runs on Facilioo. Facilioo portals and apps from other
> property managers might work too, but none has been confirmed so far. See
> [which property managers publicly use Facilioo](https://github.com/dirrgang/home-assistant-facilioo/blob/master/docs/known-facilioo-providers.md),
> and if you try another portal, please
> [share your result](https://github.com/dirrgang/home-assistant-facilioo/blob/master/docs/compatibility-verification.md).

> [!IMPORTANT]
> **Monthly values, not live data.** Facilioo provides consumption per billing month, and a
> month appears only once Facilioo has published it. Don't expect current meter readings
> or hourly values.

## Installation

### With HACS (recommended)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dirrgang&repository=home-assistant-facilioo&category=integration)

Facilioo is available in the default HACS catalog, so you don't need to add a custom
repository.

1. Select the button above, or open **HACS** in Home Assistant and search for **Facilioo**.
2. Select **Download**.
3. Restart Home Assistant.

### Manual installation

Download the [latest release](https://github.com/dirrgang/home-assistant-facilioo/releases/latest),
copy the `custom_components/facilioo` folder into the `custom_components` folder of your Home
Assistant configuration, and restart Home Assistant.

## Setup

[![Open your Home Assistant instance and start setting up Facilioo.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=facilioo)

1. Go to **Settings → Devices & services → Add integration** and search for **Facilioo**.
2. Enter the email address and password you use for your resident portal or app.

Home Assistant signs in and checks that your account has at least one supported meter. A
**Facilioo Consumption** device with its sensors then appears, and your past months are
imported.

## Energy Dashboard

Go to **Settings → Dashboards → Energy** and add these entries:

| Section | Consumption | Cost |
| --- | --- | --- |
| **Water consumption** | Facilioo warm water consumption history (Energy Dashboard water source) | Facilioo warm water cost history (Energy Dashboard source cost) |
| **Gas consumption** | Facilioo heating consumption history (Energy Dashboard gas source) | Facilioo heating cost history (Energy Dashboard gas cost) |

> [!WARNING]
> Choose the entries ending in **"… history"**, not the sensors named **"… cumulative total"**.
> Both contain the same data, so adding both counts your consumption twice. Only the history
> entries include the months before you installed the integration.

**Why is heating under "Gas"?** The Energy Dashboard has no separate heating section. The gas
section accepts energy in kWh, so heating energy fits there. The value is still your heating
energy, not a gas meter reading.

**Hot water in kWh (optional).** If Facilioo provides an energy value for every month of hot
water, you also get **Facilioo warm water energy history (Energy Dashboard gas source)**. You
can add it as a second gas source with the warm-water cost history as its cost. Use it
*instead of* the m³ water source, not alongside it.

## Sensors

You only get sensors for meter types that your account has.

| Sensor | What it shows |
| --- | --- |
| Warm water — latest billing month | Hot-water use in the newest available month (m³) |
| Heating energy — latest billing month | Heating energy in the newest available month (kWh) |
| Warm water cost / Heating cost — latest billing month | Costs for the newest available month |
| Warm water / Heating energy — cumulative total | Running total of all months, for cards and automations |
| Warm water energy — cumulative total | Hot water as energy (kWh), if Facilioo provides it for every month |
| Warm water cost / Heating cost — cumulative total | Running cost totals (disabled by default) |
| Warm water / Heating energy — latest available billing month | Diagnostic: the month of the newest data, e.g. `2026-09` |
| Last successful data import | Diagnostic: when Home Assistant last fetched data successfully |

The latest-month sensors also show whether Facilioo marked the value as estimated. The
[technical reference](https://github.com/dirrgang/home-assistant-facilioo/blob/master/docs/technical-reference.md#entities-and-attributes)
explains every attribute.

## FAQ

<details>
<summary><b>Why don't I see today's consumption?</b></summary>

Facilioo provides billing data per month, not live meter readings. A month shows up once
Facilioo has published it, and the integration checks once a day. The **latest available
billing month** sensor shows which month the newest data is from.

</details>

<details>
<summary><b>Does it work with my property manager's portal or app?</b></summary>

It may, if the portal runs on Facilioo and you sign in with an email address and password. So
far, only the MÜNCH Immo App has been tested. The
[list of property managers](https://github.com/dirrgang/home-assistant-facilioo/blob/master/docs/known-facilioo-providers.md)
shows which ones publicly use Facilioo. Being on that list doesn't mean the integration works
there. If you try it, the
[compatibility guide](https://github.com/dirrgang/home-assistant-facilioo/blob/master/docs/compatibility-verification.md)
explains how to share your result without revealing personal data.

</details>

<details>
<summary><b>Setup says my account requires multi-factor authentication.</b></summary>

Accounts with MFA can't be set up yet. The integration doesn't try to bypass MFA, so setup
stops with this message.

</details>

<details>
<summary><b>Setup says no supported meter is available.</b></summary>

Your account needs access to at least one heating or hot-water meter. Cold water and other meter
types aren't supported yet. Check whether your resident portal or app shows consumption values
for your apartment.

</details>

<details>
<summary><b>What happens when I change my Facilioo password?</b></summary>

Home Assistant tells you under **Settings → Devices & services** that Facilioo needs to be
reauthenticated. Enter the new password there. Your sensors and history stay as they are.

</details>

<details>
<summary><b>Why are there both "cumulative total" sensors and "history" entries?</b></summary>

The sensors provide the current value for dashboards, cards and automations. The history
entries contain every month, including those from before installation, and they're corrected
when Facilioo changes an old value. Home Assistant can't write this kind of past data into a
normal sensor's history, so the integration provides it separately. The
[technical reference](https://github.com/dirrgang/home-assistant-facilioo/blob/master/docs/technical-reference.md#energy-dashboard-and-historical-statistics)
has the details.

</details>

## Privacy

- Home Assistant connects only to `https://api.facilioo.de`. There's no telemetry or
  analytics, and your consumption data isn't sent anywhere else.
- Your email address and password are stored in the integration's settings in Home Assistant.
  Login tokens are kept only in memory.
- Diagnostics downloads contain counts, meter categories and months only. They don't include
  your login details, names, addresses or meter numbers.

## Help and contributing

- **Something isn't working?** [Open an issue](https://github.com/dirrgang/home-assistant-facilioo/issues/new/choose).
  Never post passwords, addresses, meter numbers, complete logs or diagnostics. The issue
  template explains what's useful.
- **Security issue?** Report it privately as described in
  [SECURITY.md](https://github.com/dirrgang/home-assistant-facilioo/blob/master/SECURITY.md).
- **How does it work?** The
  [technical reference](https://github.com/dirrgang/home-assistant-facilioo/blob/master/docs/technical-reference.md)
  covers synchronization, historical statistics, time zones and every limitation.
- **Want to contribute?** See
  [CONTRIBUTING.md](https://github.com/dirrgang/home-assistant-facilioo/blob/master/CONTRIBUTING.md).

## Auf Deutsch

**Facilioo für Home Assistant** überträgt deinen monatlichen Verbrauch an Heizenergie und
Warmwasser aus deinem Facilioo-Bewohnerkonto ins Energie-Dashboard von Home Assistant. Wenn
deine Hausverwaltung Kosten bereitstellt, kommen diese mit. Bei der Einrichtung werden auch alle
vergangenen Monate importiert.

**Voraussetzungen:** Home Assistant ab 2026.4.0 und ein Facilioo-Bewohnerkonto mit E-Mail und
Passwort, ohne Mehrfaktor-Authentifizierung. Getestet ist die Integration mit der MÜNCH Immo
App. Facilioo-Portale anderer Hausverwaltungen können funktionieren, das ist aber noch nicht
bestätigt. Die Werte sind monatliche Abrechnungsdaten, keine Live-Zählerstände.

**So richtest du sie ein:**

1. Öffne die Integration über den HACS-Button oben, oder suche in HACS nach **Facilioo**. Sie
   ist im Standardkatalog von HACS enthalten. Lade sie herunter und starte Home Assistant neu.
2. Wähle **Einstellungen → Geräte & Dienste → Integration hinzufügen → Facilioo** und gib die
   Zugangsdaten deines Bewohnerportals ein.
3. Füge unter **Einstellungen → Dashboards → Energie** die Statistiken
   „Facilioo warm water consumption history …“ (Wasserverbrauch) und
   „Facilioo heating consumption history …“ (Gasverbrauch) hinzu. Füge die Sensoren
   „… kumulierter Gesamtstand“ nicht zusätzlich hinzu, sonst wird doppelt gezählt.

Alle weiteren Details findest du in den englischen Abschnitten oben.

---

This is an unofficial, community-maintained project. It is not affiliated with or endorsed by
Facilioo or MÜNCH. Licensed under the
[MIT License](https://github.com/dirrgang/home-assistant-facilioo/blob/master/LICENSE).
