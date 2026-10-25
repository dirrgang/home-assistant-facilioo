"""Synthetic-only tests; the manual probe never contacts a resident account here."""

import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from scripts.probe_meter_selection import (
    BASE,
    LOGIN,
    METERS,
    READINGS,
    TYPES,
    ProbeError,
    ReadOnlyApi,
    compare,
    probe,
    write_report,
)


class Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def read(self):
        return json.dumps(self.payload).encode()


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


def _login(scope="platform"):
    claims = base64.urlsafe_b64encode(json.dumps({"scope": scope}).encode()).decode().rstrip("=")
    return {"accessToken": f"synthetic.{claims}.not-a-real-signature", "account": {"id": 987654}}


def _page(items, number=1, more=False):
    return {"items": items, "pageNumber": number, "hasNextPage": more}


async def test_only_allowed_routes_no_redirects_and_no_mfa_bypass():
    session = Session([Response(_login()), Response(_page([]))])
    api = ReadOnlyApi(session)
    await api.login("synthetic@example.invalid", "synthetic-password")
    await api.page(METERS)
    with pytest.raises(ProbeError):
        await api.request("DELETE", METERS)
    with pytest.raises(ProbeError):
        await api.request("POST", "/api/auth/logout")
    assert len(session.calls) == 2
    assert session.calls[0][1] == BASE + LOGIN
    assert session.calls[0][2]["json"]["skipMultiFactorAuthentication"] is False
    assert "Authorization" not in session.calls[0][2]["headers"]
    assert session.calls[1][2]["headers"]["Authorization"].startswith("Bearer synthetic.")
    assert all(call[2]["allow_redirects"] is False for call in session.calls)


@pytest.mark.parametrize(
    "payload",
    [
        _login("multiFactorChallenge"),
        {"accessToken": "synthetic"},
        {"accessToken": "synthetic", "nonce": "synthetic"},
    ],
)
async def test_unsupported_login_stops_without_any_followup(payload):
    session = Session([Response(payload)])
    api = ReadOnlyApi(session)
    with pytest.raises(ProbeError):
        await api.login("synthetic@example.invalid", "synthetic-password")
    assert api.token is None
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        Response({"secret": "not-for-output"}, status=403),
        Response({"secret": "not-for-output"}, status=302),
    ],
)
async def test_error_messages_do_not_include_body_or_credentials(response):
    api = ReadOnlyApi(Session([response]))
    with pytest.raises(ProbeError) as error:
        await api.login("synthetic@example.invalid", "synthetic-password")
    assert "not-for-output" not in str(error.value)
    assert "synthetic-password" not in str(error.value)
    assert "example.invalid" not in str(error.value)


async def test_repeated_ids_and_incomplete_pages_abort():
    api = ReadOnlyApi(
        Session([Response(_page([{"id": 1}], more=True)), Response(_page([{"id": 1}], number=2))])
    )
    api.token = "synthetic"
    with pytest.raises(ProbeError):
        await api.page(METERS)
    api = ReadOnlyApi(Session([Response({"items": []})]))
    api.token = "synthetic"
    with pytest.raises(ProbeError):
        await api.page(METERS)


async def test_report_contains_only_aliases_shapes_counts_and_comparisons(tmp_path):
    # Include a heating meter in the same unit: a unit query must compare all kinds.
    meters = [
        {
            "id": 77101,
            "typeId": 5,
            "unitOfMeasure": "M3",
            "meteredUnitId": 88201,
            "number": "private-meter-number",
            "location": "private-location",
        },
        {"id": 77102, "typeId": 5, "unitOfMeasure": "M3", "meteredUnitId": None},
        {"id": 77103, "typeId": 4, "unitOfMeasure": "KWH", "meteredUnitId": 88201},
    ]
    rows = [
        {
            "id": 99000 + i,
            "consumptionMeterId": meter["id"],
            "currentValue": 123.456789,
            "readingDate": "2026-09-30T22:00:00Z",
            "privateUnexpected": "private-extra",
        }
        for i, meter in enumerate(meters)
    ]
    api = ReadOnlyApi(Session([]))
    api.page = AsyncMock(side_effect=[meters, [], rows, [rows[0]], [rows[1]], [rows[0], rows[2]]])
    report = await probe(api, "2026-09")
    assert [item["status"] for item in report["comparisons"]] == ["equal"] * 3
    assert report["comparisons"][-1]["expected_rows"] == 2
    assert report["warm_water_meters"][0]["unit"] == "Einheit 1"
    assert report["warm_water_meters"][1]["unit"] is None
    assert report["warm_water_meters"][1]["metadata_shapes"]["meteredUnitId"] == "null"
    assert report["warm_water_meters"][0]["metadata_shapes"]["meteredPropertyId"] == "missing"
    calls = api.page.await_args_list
    assert calls[0].args == (METERS,)
    assert calls[1].args == (TYPES,)
    assert calls[-1].args[0] == READINGS
    assert calls[-1].args[1]["unitId"] == 88201
    path = tmp_path / "summary.json"
    write_report(path, report)
    output = path.read_text()
    for private in (
        "77101",
        "77102",
        "77103",
        "88201",
        "99000",
        "123.456789",
        "private-meter-number",
        "private-location",
        "private-extra",
    ):
        assert private not in output
    assert Path(path).stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_report(path, report)


def test_no_data_does_not_claim_filter_verification_and_values_are_compared_in_memory():
    assert compare([], [])["status"] == "no_data"
    assert compare([{"id": 1, "currentValue": 4}], [{"id": 1, "currentValue": 5}]) == {
        "status": "different",
        "expected_rows": 1,
        "returned_rows": 1,
    }
