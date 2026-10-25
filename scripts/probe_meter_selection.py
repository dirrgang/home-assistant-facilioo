"""Manually invoked local read-only probe; never run against an account in tests.

Run with: .venv/bin/python -m scripts.probe_meter_selection --output /tmp/report.json
Credentials are entered only on a real terminal. No raw payload or ID is exported.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import getpass
import json
import os
import re
import sys
from collections import Counter
from contextlib import suppress
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import aiohttp

from custom_components.facilioo.models import (
    ConsumptionMeter,
    ConsumptionType,
    FaciliooDataError,
    MeterKind,
    resolve_meter_types,
)

BASE = "https://api.facilioo.de"
LOGIN = "/api/auth/login"
METERS = "/api/consumption-meters"
TYPES = "/api/consumption-types"
READINGS = "/api/consumption-readings/search"
ALLOWED = {("POST", LOGIN), ("GET", METERS), ("GET", TYPES), ("POST", READINGS)}
COMPARE_FIELDS = (
    "id",
    "consumptionMeterId",
    "readingDate",
    "currentValue",
    "currentValueInDifferentUnitOfMeasure",
    "costs",
    "isEstimated",
    "deleted",
    "lastModified",
)


class ProbeError(Exception):
    """Only fixed safe messages and numeric HTTP status may reach the terminal."""


def valid_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class ReadOnlyApi:
    def __init__(self, session: Any) -> None:
        self.session = session
        self.token: str | None = None
        self.requests = 0

    async def request(self, method: str, path: str, *, body=None, params=None) -> Any:
        if (method, path) not in ALLOWED:
            raise ProbeError("Nicht erlaubter Endpunkt oder HTTP-Vorgang.")
        if self.requests >= 100:
            raise ProbeError("Sicherheitsgrenze von 100 Anfragen erreicht.")
        self.requests += 1
        headers = {"api-version": "2.0", "Accept": "application/json"}
        if path != LOGIN:
            if not self.token:
                raise ProbeError("Keine vollstaendige Anmeldung vorhanden.")
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            async with self.session.request(
                method,
                BASE + path,
                json=body,
                params=params,
                headers=headers,
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    raise ProbeError(f"API-Anfrage abgebrochen: HTTP {response.status}.")
                raw = await response.read()
                if len(raw) > 2_000_000:
                    raise ProbeError("Antwort zu gross; Abbruch ohne Rohdaten-Ausgabe.")
                return json.loads(raw)
        except aiohttp.ClientError, TimeoutError:
            raise ProbeError("Verbindungsfehler; keine automatische Wiederholung.") from None
        except ValueError, UnicodeError:
            raise ProbeError("Antwort ist kein gueltiges JSON.") from None

    async def login(self, email: str, password: str) -> None:
        payload = await self.request(
            "POST",
            LOGIN,
            body={
                "email": email,
                "password": password,
                "skipMultiFactorAuthentication": False,
            },
        )
        if not isinstance(payload, dict):
            raise ProbeError("Unerwartete Anmeldeantwort.")
        token = payload.get("accessToken")
        try:
            # Scope routing only; authenticity comes from the HTTPS login endpoint.
            # No token is sent to a decoder or printed, and no MFA completion is attempted.
            encoded = token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            platform = claims.get("scope", "").casefold() == "platform"
        except AttributeError, IndexError, TypeError, ValueError:
            platform = False
        account = payload.get("account")
        if not platform or not isinstance(account, dict) or not valid_id(account.get("id")):
            raise ProbeError("Keine bestaetigte Platform-Anmeldung; MFA wird nicht umgangen.")
        self.token = token

    async def page(self, path: str, body=None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[int] = set()
        for number in range(1, 21):
            payload = await self.request(
                "POST" if path == READINGS else "GET",
                path,
                body=body,
                params={"PageSize": 100, "PageNumber": number},
            )
            if (
                not isinstance(payload, dict)
                or not isinstance(payload.get("items"), list)
                or payload.get("pageNumber") != number
                or not isinstance(payload.get("hasNextPage"), bool)
            ):
                raise ProbeError("Unerwartete Seitendaten; Vergleich abgebrochen.")
            for row in payload["items"]:
                if not isinstance(row, dict) or not valid_id(row.get("id")) or row["id"] in seen:
                    raise ProbeError(
                        "Ungueltige oder doppelte Datensatzkennung; Vergleich abgebrochen."
                    )
                seen.add(row["id"])
                rows.append(row)
            if not payload["hasNextPage"]:
                return rows
        raise ProbeError("Mehr als 20 Seiten; Vergleich ohne Teilergebnis abgebrochen.")


def shape(value: Any, present: bool = True) -> str:
    if not present:
        return "missing"
    if value is None:
        return "null"
    return {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }.get(type(value), "other")


def compare(expected: list[dict], actual: list[dict]) -> dict[str, Any]:
    def signatures(rows):
        # Raw values are compared only in memory, never included in the result.
        return Counter(
            json.dumps(
                {field: row[field] for field in COMPARE_FIELDS if field in row}, sort_keys=True
            )
            for row in rows
        )

    return {
        "status": (
            "no_data"
            if not expected and not actual
            else "equal"
            if signatures(expected) == signatures(actual)
            else "different"
        ),
        "expected_rows": len(expected),
        "returned_rows": len(actual),
    }


async def probe(api: ReadOnlyApi, month: str) -> dict[str, Any]:
    meters = await api.page(METERS)
    types = await api.page(TYPES)
    try:
        resolved = resolve_meter_types(
            tuple(ConsumptionMeter.from_api(row) for row in meters),
            tuple(ConsumptionType.from_api(row) for row in types),
        )
    except FaciliooDataError, TypeError, ValueError:
        raise ProbeError("Zaehler-Metadaten nicht klassifizierbar.") from None
    warm_ids = {meter.id for meter in resolved if meter.kind is MeterKind.WARM_WATER}
    warm = [row for row in meters if row["id"] in warm_ids]
    if not warm or len(warm) > 12:
        raise ProbeError("Benoetigt 1 bis 12 erkennbare Warmwasserzaehler.")
    units: dict[int, str] = {}
    properties: dict[int, str] = {}

    def alias(value, mapping, label):
        if not valid_id(value):
            return None
        if value not in mapping:
            mapping[value] = f"{label} {len(mapping) + 1}"
        return mapping[value]

    descriptions = []
    for index, row in enumerate(warm, 1):
        descriptions.append(
            {
                "meter": f"Zaehler {index}",
                "unit": alias(row.get("meteredUnitId"), units, "Einheit"),
                "property": alias(row.get("meteredPropertyId"), properties, "Objekt"),
                "metadata_shapes": {
                    key: shape(row.get(key), key in row)
                    for key in (
                        "meteredUnitId",
                        "meteredPropertyId",
                        "unitOfMeasure",
                        "number",
                        "location",
                    )
                },
            }
        )
    body = {"dates": [month], "orderBy": ["readingDate asc"]}
    baseline = await api.page(READINGS, body)
    if any(not valid_id(row.get("consumptionMeterId")) for row in baseline):
        raise ProbeError("Lesungszuordnung fehlt; Vergleich abgebrochen.")
    comparisons = []
    for index, meter in enumerate(warm, 1):
        actual = await api.page(READINGS, {**body, "consumptionMeterId": meter["id"]})
        expected = [row for row in baseline if row["consumptionMeterId"] == meter["id"]]
        comparisons.append(
            {"filter": "meter", "target": f"Zaehler {index}", **compare(expected, actual)}
        )
    for unit_id, label in units.items():
        # Compare all meter kinds for that currently assigned unit, not only warm water.
        ids = {row["id"] for row in meters if row.get("meteredUnitId") == unit_id}
        actual = await api.page(READINGS, {**body, "unitId": unit_id})
        expected = [row for row in baseline if row["consumptionMeterId"] in ids]
        comparisons.append({"filter": "unit", "target": label, **compare(expected, actual)})
    return {
        "schema_version": 1,
        "month": month,
        "warm_water_meters": descriptions,
        "comparisons": comparisons,
        "request_count": api.requests,
        "limitations": [
            "One current snapshot; concurrent API edits can cause differences.",
            "No proof of historical unit membership, replacements or physical non-overlap.",
        ],
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    # New private file only; never overwrite a file or persist a credential/payload dump.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")


async def run(month: str) -> dict[str, Any]:
    email = getpass.getpass("Facilioo E-Mail (unsichtbare Eingabe): ")
    password = getpass.getpass("Passwort (unsichtbare Eingabe): ")
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30), trust_env=False
    ) as session:
        api = ReadOnlyApi(session)
        try:
            await api.login(email, password)
            del email, password
            return await probe(api, month)
        finally:
            api.token = None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        parser.exit(
            2, "Nur in einem interaktiven Terminal ausfuehren; keine Zugangsdaten per Pipe.\n"
        )
    print("Lokaler Facilioo-Test: Login und ausschliesslich lesende Verbrauchsabfragen.")
    print(
        "Keine Rohdaten, echten Kennungen oder Verbrauchswerte im Bericht; keine Veroeffentlichung."
    )
    default = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    try:
        month = input(f"Monat mit bekannten Lesungen [{default}]: ").strip() or default
        if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month):
            raise ProbeError("Monat muss YYYY-MM sein.")
        if args.output.exists():
            raise ProbeError(
                "Berichtsdatei existiert bereits; bitte einen neuen Dateinamen verwenden."
            )
        report = asyncio.run(run(month))
        write_report(args.output, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"Bereinigter Bericht gespeichert: {args.output}")
    except ProbeError as error:
        print(str(error))
    except KeyboardInterrupt, EOFError:
        print("Abgebrochen; keine weitere Anfrage.")
    except Exception:
        # Never print exception details/tracebacks, which can include private response data.
        print("Test abgebrochen; unerwarteter lokaler Fehler, keine Rohdaten ausgegeben.")
    with suppress(KeyboardInterrupt, EOFError):
        input("Eingabetaste zum Schliessen ...")


if __name__ == "__main__":
    main()
