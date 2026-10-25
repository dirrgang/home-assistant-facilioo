"""Tests for HTTP behavior and pagination."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import aiohttp
import pytest

from custom_components.facilioo.api import (
    FaciliooApiClient,
    FaciliooAuthenticationError,
    FaciliooAuthorizationError,
    FaciliooConnectionError,
    FaciliooMfaRequiredError,
    FaciliooRateLimitError,
    FaciliooResponseError,
)
from custom_components.facilioo.models import MeterKind


class FakeResponse:
    def __init__(self, payload=None, status=200, headers=None, text=""):
        self.payload = payload
        self.status = status
        self.headers = headers or {}
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def json(self, content_type=None):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload

    async def text(self):
        return self._text


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_successful_login_returns_account_id_without_credentials_in_headers():
    session = FakeSession([FakeResponse({"accessToken": "secret-token", "account": {"id": 12345}})])
    client = FaciliooApiClient(session, "resident@example.test", "secret-password")

    account_id = await client.async_login()

    assert account_id == 12345
    assert client.account_id == 12345
    _, _, kwargs = session.calls[0]
    assert "Authorization" not in kwargs["headers"]
    assert kwargs["json"]["skipMultiFactorAuthentication"] is False


@pytest.mark.asyncio
async def test_login_falls_back_to_myself_endpoint_for_account_id():
    session = FakeSession(
        [
            FakeResponse({"accessToken": "secret-token"}),
            FakeResponse({"id": 54321}),
        ]
    )
    client = FaciliooApiClient(session, "resident@example.test", "secret-password")

    account_id = await client.async_login()

    assert account_id == 54321
    method, url, kwargs = session.calls[1]
    assert method == "GET"
    assert url.endswith("/api/accounts/myself")
    assert kwargs["headers"]["Authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_login_rejects_missing_account_id():
    session = FakeSession(
        [
            FakeResponse({"accessToken": "secret-token"}),
            FakeResponse({}),
        ]
    )
    client = FaciliooApiClient(session, "resident@example.test", "secret-password")

    with pytest.raises(FaciliooResponseError):
        await client.async_login()

    assert client.account_id is None


@pytest.mark.asyncio
async def test_wrong_credentials_are_safe():
    client = FaciliooApiClient(
        FakeSession([FakeResponse(status=401)]), "resident@example.test", "secret-password"
    )
    with pytest.raises(FaciliooAuthenticationError) as error:
        await client.async_login()
    assert "secret-password" not in str(error.value)
    assert "resident@example.test" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 400, 409])
async def test_mfa_login_stops_without_bypass_or_followup_requests(status, mfa_payload, caplog):
    # These invented payloads exercise current heuristics, not documented challenge DTOs.
    mfa_payload["detail"] = "resident@example.test secret-password synthetic-challenge"
    session = FakeSession([FakeResponse(mfa_payload, status=status, text=json.dumps(mfa_payload))])
    client = FaciliooApiClient(session, "resident@example.test", "secret-password")

    with pytest.raises(FaciliooMfaRequiredError) as error:
        await client.async_login()

    assert client.account_id is None
    assert client._token is None
    assert len(session.calls) == 1
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url.endswith("/api/auth/login")
    assert kwargs["json"]["skipMultiFactorAuthentication"] is False
    assert "Authorization" not in kwargs["headers"]
    for private_value in ("resident@example.test", "secret-password", "synthetic-challenge"):
        assert private_value not in str(error.value)
        assert private_value not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "exception"),
    [
        (FakeResponse(status=400, text="Invalid credentials"), FaciliooAuthenticationError),
        (FakeResponse(status=409, text="Login rejected"), FaciliooAuthenticationError),
        (FakeResponse(status=401), FaciliooAuthenticationError),
        (FakeResponse(status=403), FaciliooAuthorizationError),
        (TimeoutError(), FaciliooConnectionError),
        (FakeResponse({}), FaciliooResponseError),
    ],
)
async def test_non_mfa_login_failures_remain_distinct(response, exception):
    session = FakeSession([response])
    client = FaciliooApiClient(session, "resident@example.test", "secret-password")

    with pytest.raises(exception) as error:
        await client.async_login()

    # MFA subclasses AuthenticationError; assert the exact type to catch misclassification.
    assert type(error.value) is exception
    assert len(session.calls) == 1
    assert session.calls[0][2]["json"]["skipMultiFactorAuthentication"] is False


@pytest.mark.asyncio
async def test_401_clears_authentication_state():
    client = FaciliooApiClient(FakeSession([FakeResponse(status=401)]), "x", "y")
    client._token = "token"
    client._account_id = 12345

    with pytest.raises(FaciliooAuthenticationError):
        await client.async_get_meters()

    assert client._token is None
    assert client.account_id is None


@pytest.mark.asyncio
async def test_403_is_authorization_error_and_preserves_authentication_state():
    client = FaciliooApiClient(FakeSession([FakeResponse(status=403)]), "x", "y")
    client._token = "token"
    client._account_id = 12345

    with pytest.raises(FaciliooAuthorizationError):
        await client.async_get_meters()

    assert client._token == "token"
    assert client.account_id == 12345


@pytest.mark.asyncio
async def test_server_timeout_rate_limit_and_invalid_json():
    for response, exception in (
        (FakeResponse(status=503), FaciliooConnectionError),
        (TimeoutError(), FaciliooConnectionError),
        (FakeResponse(status=429, headers={"Retry-After": "42"}), FaciliooRateLimitError),
        (
            FakeResponse(json.JSONDecodeError("bad", "x", 0)),
            FaciliooResponseError,
        ),
    ):
        client = FaciliooApiClient(FakeSession([response]), "x", "y")
        with pytest.raises(exception) as error:
            await client.async_login()
        if isinstance(error.value, FaciliooRateLimitError):
            assert error.value.retry_after == 42


@pytest.mark.asyncio
async def test_pagination_requests_every_page(meter_payload):
    first = dict(meter_payload)
    first["items"] = first["items"][:2]
    first["totalCount"] = 3
    second = {"items": meter_payload["items"][2:], "totalCount": 3}
    session = FakeSession(
        [
            FakeResponse({"accessToken": "token", "account": {"id": 12345}}),
            FakeResponse(first),
            FakeResponse(second),
        ]
    )
    client = FaciliooApiClient(session, "x", "y")
    await client.async_login()
    meters = await client._paginate("/api/consumption-meters", page_size=2)
    assert len(meters) == 3
    assert session.calls[2][2]["params"]["PageNumber"] == 2


@pytest.mark.asyncio
async def test_pagination_uses_received_count_when_server_caps_page_size():
    first = {"items": [{"id": item} for item in range(100)], "totalCount": 150}
    second = {"items": [{"id": item} for item in range(100, 150)], "totalCount": 150}
    session = FakeSession([FakeResponse(first), FakeResponse(second)])
    client = FaciliooApiClient(session, "x", "y")
    client._token = "token"

    items = await client._paginate("/api/consumption-readings", page_size=1000)

    assert len(items) == 150
    assert session.calls[1][2]["params"]["PageNumber"] == 2


@pytest.mark.asyncio
async def test_consumption_types_resolve_unknown_meter_ids():
    session = FakeSession(
        [
            FakeResponse(
                {
                    "items": [
                        {"id": 1, "typeId": 700, "unitOfMeasure": "M3"},
                        {"id": 2, "typeId": 701, "unitOfMeasure": "KWH"},
                    ],
                    "totalCount": 2,
                }
            ),
            FakeResponse(
                {
                    "items": [
                        {
                            "id": 700,
                            "meterName": "Warmwasserzähler",
                            "utilityName": "Warmwasser",
                        },
                        {
                            "id": 701,
                            "meterName": "Wärmemengenzähler",
                            "utilityName": "Heizung",
                        },
                    ],
                    "totalCount": 2,
                }
            ),
        ]
    )
    client = FaciliooApiClient(session, "x", "y")
    client._token = "token"

    meters = await client.async_get_resolved_meters()

    assert [meter.kind for meter in meters] == [MeterKind.WARM_WATER, MeterKind.HEATING]
    assert meters[0].label == "Warmwasserzähler Warmwasser"
    assert session.calls[1][1].endswith("/api/consumption-types")


@pytest.mark.asyncio
async def test_search_readings_posts_changed_since_and_paginates():
    first = {
        "items": [
            {
                "id": 10,
                "consumptionMeterId": 1,
                "currentValue": 0.5,
                "readingDate": "2026-01-31T23:00:00Z",
            }
        ],
        "totalCount": 2,
    }
    second = {
        "items": [
            {
                "id": 11,
                "consumptionMeterId": 1,
                "currentValue": 0.6,
                "readingDate": "2026-02-28T23:00:00Z",
            }
        ],
        "totalCount": 2,
    }
    session = FakeSession([FakeResponse(first), FakeResponse(second)])
    client = FaciliooApiClient(session, "x", "y")
    client._token = "token"

    readings = await client.async_search_readings(
        changed_since=datetime(2026, 8, 16, 18, 0, tzinfo=UTC)
    )

    assert len(readings) == 2
    for method, url, kwargs in session.calls:
        assert method == "POST"
        assert url.endswith("/api/consumption-readings/search")
        assert kwargs["json"] == {
            "orderBy": ["readingDate asc"],
            "changedSince": "2026-08-16T18:00:00Z",
        }
    assert session.calls[1][2]["params"]["PageNumber"] == 2


@pytest.mark.asyncio
async def test_search_readings_supports_dates_filter():
    session = FakeSession([FakeResponse({"items": [], "totalCount": 0})])
    client = FaciliooApiClient(session, "x", "y")
    client._token = "token"

    await client.async_search_readings(dates=["2026-1", "2026-2"])

    assert session.calls[0][2]["json"] == {
        "orderBy": ["readingDate asc"],
        "dates": ["2026-1", "2026-2"],
    }


@pytest.mark.asyncio
async def test_reading_endpoints_request_supported_page_size():
    session = FakeSession(
        [
            FakeResponse({"items": [], "totalCount": 0}),
            FakeResponse({"items": [], "totalCount": 0}),
            FakeResponse({"items": [], "totalCount": 0}),
        ]
    )
    client = FaciliooApiClient(session, "x", "y")
    client._token = "token"

    await client.async_get_readings()
    await client.async_get_extended_readings()
    await client.async_search_readings()

    assert [call[2]["params"]["PageSize"] for call in session.calls] == [100, 100, 100]


@pytest.mark.asyncio
async def test_aiohttp_error_is_connection_error():
    client = FaciliooApiClient(FakeSession([aiohttp.ClientError()]), "x", "y")
    with pytest.raises(FaciliooConnectionError):
        await client.async_login()
