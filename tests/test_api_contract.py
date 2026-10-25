"""Offline request-contract regression tests based on the documented Facilioo API v2."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from custom_components.facilioo.api import FaciliooApiClient
from custom_components.facilioo.const import (
    ACCOUNT_MYSELF_ENDPOINT,
    API_VERSION,
    BASE_URL,
    CONSUMPTION_TYPES_ENDPOINT,
    EXTENDED_READINGS_ENDPOINT,
    LOGIN_ENDPOINT,
    METERS_ENDPOINT,
    PAGE_SIZE,
    READINGS_ENDPOINT,
    READINGS_SEARCH_ENDPOINT,
)


def _contract() -> dict[str, Any]:
    """Read the reviewed public endpoint-contract fixture without network access."""
    path = Path(__file__).parent / "fixtures" / "facilioo_api_v2_contract.json"
    return json.loads(path.read_text(encoding="utf-8"))


class _Response:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.status = 200
        self.headers: dict[str, str] = {}

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def json(self, *, content_type: str | None = None) -> Any:
        return self.payload


class _Session:
    def __init__(self, payloads: list[Any]) -> None:
        self.responses = [_Response(payload) for payload in payloads]
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def request(self, method: str, url: str, **kwargs: Any) -> _Response:
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected request in mocked API contract test")
        return self.responses.pop(0)


def _empty_page() -> dict[str, Any]:
    return {
        "items": [],
        "pageNumber": 1,
        "totalPages": 1,
        "totalCount": 0,
        "hasPreviousPage": False,
        "hasNextPage": False,
    }


def test_documented_endpoint_constants_match_reviewed_contract() -> None:
    contract = _contract()
    endpoints = contract["endpoints"]
    expected = {
        "login": LOGIN_ENDPOINT,
        "myself": ACCOUNT_MYSELF_ENDPOINT,
        "meters": METERS_ENDPOINT,
        "consumption_types": CONSUMPTION_TYPES_ENDPOINT,
        "readings": READINGS_ENDPOINT,
        "extended_readings": EXTENDED_READINGS_ENDPOINT,
        "search_readings": READINGS_SEARCH_ENDPOINT,
    }
    assert API_VERSION == contract["api_version"] == "2.0"
    assert contract["base_url"] == BASE_URL
    assert set(endpoints) == set(expected)
    for name, path in expected.items():
        assert endpoints[name]["path"] == path
        assert endpoints[name]["reference"].startswith("https://developers.facilioo.de/reference/")


@pytest.mark.asyncio
async def test_login_matches_documented_request_contract_and_never_skips_mfa() -> None:
    contract = _contract()
    session = _Session([{"accessToken": "synthetic-token", "account": {"id": 123}}])
    client = FaciliooApiClient(session, "example@example.invalid", "synthetic-password")
    assert await client.async_login() == 123

    method, url, options = session.calls[0]
    assert method == contract["endpoints"]["login"]["method"] == "POST"
    assert url == BASE_URL + contract["endpoints"]["login"]["path"]
    assert set(options["json"]) == set(contract["endpoints"]["login"]["required_body"])
    assert options["json"]["skipMultiFactorAuthentication"] is False
    assert options["headers"]["api-version"] == API_VERSION
    assert options["headers"]["Content-Type"] == "application/json"
    assert "Authorization" not in options["headers"]


@pytest.mark.asyncio
async def test_account_identity_fallback_matches_documented_get_endpoint() -> None:
    contract = _contract()
    session = _Session([{"accessToken": "synthetic-token"}, {"id": 123}])
    client = FaciliooApiClient(session, "example@example.invalid", "synthetic-password")
    assert await client.async_login() == 123

    method, url, options = session.calls[1]
    assert method == contract["endpoints"]["myself"]["method"] == "GET"
    assert url == BASE_URL + contract["endpoints"]["myself"]["path"]
    assert options["headers"]["Authorization"] == "Bearer synthetic-token"
    assert options["headers"]["api-version"] == API_VERSION


@pytest.mark.parametrize(
    ("endpoint_name", "client_method"),
    [
        ("meters", "async_get_meters"),
        ("consumption_types", "async_get_consumption_types"),
        ("readings", "async_get_readings"),
        ("extended_readings", "async_get_extended_readings"),
    ],
)
@pytest.mark.asyncio
async def test_paginated_get_requests_follow_documented_contract(
    endpoint_name: str, client_method: str
) -> None:
    contract = _contract()
    session = _Session([_empty_page()])
    client = FaciliooApiClient(session, "example@example.invalid", "synthetic-password")
    client._token = "synthetic-token"

    assert await getattr(client, client_method)() == ()
    method, url, options = session.calls[0]
    assert method == contract["endpoints"][endpoint_name]["method"] == "GET"
    assert url == BASE_URL + contract["endpoints"][endpoint_name]["path"]
    assert options["params"] == {
        "PageNumber": contract["pagination"]["first_page"],
        "PageSize": contract["pagination"]["max_page_size"],
    }
    assert PAGE_SIZE == 100
    assert options["headers"]["api-version"] == API_VERSION
    assert options["headers"]["Authorization"] == "Bearer synthetic-token"


@pytest.mark.asyncio
async def test_search_request_uses_documented_body_fields_and_utc_timestamp() -> None:
    contract = _contract()
    session = _Session([_empty_page()])
    client = FaciliooApiClient(session, "example@example.invalid", "synthetic-password")
    client._token = "synthetic-token"

    local_time = datetime(2026, 8, 16, 18, tzinfo=timezone(timedelta(hours=2)))
    await client.async_search_readings(changed_since=local_time, dates=["2026-08"])
    method, url, options = session.calls[0]

    assert method == contract["endpoints"]["search_readings"]["method"] == "POST"
    assert url == BASE_URL + contract["endpoints"]["search_readings"]["path"]
    assert set(options["json"]) <= set(
        contract["endpoints"]["search_readings"]["documented_body_fields"]
    )
    assert options["json"] == {
        "orderBy": ["readingDate asc"],
        "changedSince": "2026-08-16T16:00:00Z",
        "dates": ["2026-08"],
    }
    assert options["params"] == {"PageNumber": 1, "PageSize": 100}
    assert options["headers"]["api-version"] == API_VERSION
    assert options["headers"]["Content-Type"] == "application/json"
    assert options["headers"]["Authorization"] == "Bearer synthetic-token"


@pytest.mark.asyncio
async def test_has_next_page_contract_fetches_each_page_once() -> None:
    session = _Session(
        [
            {
                "items": [{"id": 1}],
                "pageNumber": 1,
                "totalPages": 2,
                "totalCount": 2,
                "hasPreviousPage": False,
                "hasNextPage": True,
            },
            {
                "items": [{"id": 2}],
                "pageNumber": 2,
                "totalPages": 2,
                "totalCount": 2,
                "hasPreviousPage": True,
                "hasNextPage": False,
            },
        ]
    )
    client = FaciliooApiClient(session, "example@example.invalid", "synthetic-password")
    client._token = "synthetic-token"

    result = await client._paginate(METERS_ENDPOINT, page_size=100)
    assert [item["id"] for item in result] == [1, 2]
    assert [options["params"]["PageNumber"] for _, _, options in session.calls] == [1, 2]


# The snapshot projects only properties consumed by this client. Unread required
# properties are preserved as x-source-required for review, not fabricated in fixtures.
def _schemas() -> dict[str, Any]:
    path = Path(__file__).parent / "fixtures" / "facilioo_openapi_v2.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _responses() -> dict[str, Any]:
    path = Path(__file__).parent / "fixtures" / "facilioo_v2_responses.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _json_schema(value: Any) -> Any:
    """Adapt OpenAPI 3.0 nullable/int32 semantics for the JSON Schema validator."""
    if isinstance(value, list):
        return [_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: _json_schema(item) for key, item in value.items() if key != "nullable"}
    if result.get("format") == "int32":
        result.update(minimum=-(2**31), maximum=2**31 - 1)
    if value.get("nullable"):
        return {"anyOf": [result, {"type": "null"}]}
    return result


def _validate(
    payload: Any, schema: dict[str, Any], *, document: dict[str, Any] | None = None
) -> None:
    from jsonschema import Draft202012Validator, FormatChecker

    document = _json_schema(_schemas() if document is None else document)
    document.update(_json_schema(schema))
    Draft202012Validator(document, format_checker=FormatChecker()).validate(payload)


def _validate_dto(payload: Any, name: str) -> None:
    _validate(payload, {"$ref": f"#/components/schemas/{name}"})


class _ContractSession(_Session):
    """Validate all requests and responses against the pinned schema, offline."""

    async def request(self, method: str, url: str, **kwargs: Any) -> _Response:
        operation = _schemas()["paths"][url.removeprefix(BASE_URL)][method.lower()]
        params = kwargs.get("params") or {}
        query = {item["name"]: item for item in operation["parameters"] if item["in"] == "query"}
        assert set(params) <= set(query)
        for name, value in params.items():
            _validate(value, query[name]["schema"])
        if "requestBody" in operation:
            _validate(
                kwargs["json"], operation["requestBody"]["content"]["application/json"]["schema"]
            )
        if url.endswith(LOGIN_ENDPOINT):
            assert kwargs["json"]["skipMultiFactorAuthentication"] is False
            assert "Authorization" not in kwargs["headers"]
        else:
            assert kwargs["headers"]["Authorization"] == "Bearer synthetic-token-not-a-jwt"
        assert kwargs["headers"]["api-version"] == "2.0"
        response = await super().request(method, url, **kwargs)
        schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        _validate(response.payload, schema)
        return response


def _page(items: list[dict[str, Any]], number: int = 1, total_pages: int = 1) -> dict[str, Any]:
    return {
        "items": items,
        "pageNumber": number,
        "pageSize": 100,
        "totalCount": total_pages * len(items),
        "totalPages": total_pages,
        "hasNextPage": number < total_pages,
        "hasPreviousPage": number > 1,
    }


@pytest.mark.parametrize(
    ("endpoint", "fixture"),
    [
        ("async_get_meters", "meter"),
        ("async_get_consumption_types", "type"),
        ("async_get_readings", "reading"),
        ("async_get_extended_readings", "reading"),
        ("async_search_readings", "reading"),
    ],
)
async def test_schema_valid_responses_reach_parsers_without_skipped_records(
    endpoint: str, fixture: str
) -> None:
    data = _responses()
    session = _ContractSession([data["login"], _page([data[fixture]])])
    client = FaciliooApiClient(session, "example@example.invalid", "synthetic-password")
    assert await client.async_login() == 123
    parsed = await getattr(client, endpoint)()
    assert len(parsed) == 1
    assert parsed[0].id == data[fixture]["id"]
    assert not session.responses


async def test_schema_valid_search_paging_preserves_filters_and_reading_values() -> None:
    from datetime import UTC
    from decimal import Decimal

    from custom_components.facilioo.models import ConsumptionReading

    data = _responses()
    second = {**data["reading"], "id": 11}
    session = _ContractSession(
        [data["login"], _page([data["reading"]], 1, 2), _page([second], 2, 2)]
    )
    client = FaciliooApiClient(session, "example@example.invalid", "synthetic-password")
    await client.async_login()
    readings = await client.async_search_readings(
        changed_since=datetime(2026, 2, 1, 1, tzinfo=timezone(timedelta(hours=1))),
        dates=["2026-01"],
    )
    assert readings == (
        ConsumptionReading.from_api(data["reading"]),
        ConsumptionReading.from_api(second),
    )
    reading = readings[0]
    assert reading.value == Decimal("0.75")
    assert reading.value_in_different_unit == Decimal("36.5")
    assert reading.costs == Decimal("7.25")
    assert reading.reading_date == datetime(2026, 1, 31, 23, tzinfo=UTC)
    assert reading.last_modified == datetime(2026, 2, 2, 10, 30, tzinfo=UTC)
    assert reading.is_estimated is True
    assert reading.deleted is False
    for page, (_, _, options) in enumerate(session.calls[1:], start=1):
        assert options["params"] == {"PageNumber": page, "PageSize": 100}
        assert options["json"] == {
            "orderBy": ["readingDate asc"],
            "changedSince": "2026-02-01T00:00:00Z",
            "dates": ["2026-01"],
        }


@pytest.mark.parametrize("name", ["ConsumptionReadingRead", "ConsumptionReadingExtended"])
@pytest.mark.parametrize(
    "field",
    [
        "currentValue",
        "currentValueInDifferentUnitOfMeasure",
        "costs",
        "isEstimated",
        "deleted",
        "lastModified",
    ],
)
@pytest.mark.parametrize("absent", [False, True])
def test_nullable_and_omitted_reading_fields_match_schema_and_parser(
    name: str, field: str, absent: bool
) -> None:
    from custom_components.facilioo.models import ConsumptionReading

    payload = _responses()["reading"]
    if absent:
        del payload[field]
    else:
        payload[field] = None
    _validate_dto(payload, name)
    parsed = ConsumptionReading.from_api(payload)
    attributes = {
        "currentValue": "value",
        "currentValueInDifferentUnitOfMeasure": "value_in_different_unit",
        "costs": "costs",
        "isEstimated": "is_estimated",
        "deleted": "deleted",
        "lastModified": "last_modified",
    }
    expected = False if field in {"isEstimated", "deleted"} else None
    assert getattr(parsed, attributes[field]) is expected


@pytest.mark.parametrize("name", ["ConsumptionReadingRead", "ConsumptionReadingExtended"])
def test_schema_datetime_deletion_marker_is_recognized(name: str) -> None:
    from custom_components.facilioo.models import ConsumptionReading

    payload = {**_responses()["reading"], "deleted": "2026-03-01T12:00:00Z"}
    _validate_dto(payload, name)
    assert ConsumptionReading.from_api(payload).deleted is True


@pytest.mark.parametrize("field", ["unitOfMeasure", "number"])
@pytest.mark.parametrize("absent", [False, True])
def test_nullable_meter_fields_match_schema_and_parser(field: str, absent: bool) -> None:
    from custom_components.facilioo.models import ConsumptionMeter, MeterKind

    payload = _responses()["meter"]
    if absent:
        del payload[field]
    else:
        payload[field] = None
    _validate_dto(payload, "ConsumptionMeterRead")
    parsed = ConsumptionMeter.from_api(payload)
    if field == "unitOfMeasure":
        assert parsed.unit is None
        assert parsed.kind is MeterKind.UNKNOWN
    else:
        assert parsed.number is None


@pytest.mark.parametrize("absent", [False, True])
def test_nullable_type_name_matches_schema_and_parser(absent: bool) -> None:
    from custom_components.facilioo.models import ConsumptionType

    payload = _responses()["type"]
    if absent:
        del payload["meterName"]
    else:
        payload["meterName"] = None
    _validate_dto(payload, "ConsumptionTypeRead")
    parsed = ConsumptionType.from_api(payload)
    assert parsed.meter_name is None
    assert parsed.utility_name == "Warmwasser"


@pytest.mark.parametrize(
    ("name", "fixture"),
    [
        ("ConsumptionMeterRead", "meter"),
        ("ConsumptionTypeRead", "type"),
        ("ConsumptionReadingRead", "reading"),
        ("ConsumptionReadingExtended", "reading"),
        ("LoginCommandResponse", "login"),
        ("AccountRead", "account"),
    ],
)
def test_response_contract_enforces_required_types_nullability_and_formats(
    name: str, fixture: str
) -> None:
    from jsonschema import ValidationError

    payload = _responses()[fixture]
    schema = _schemas()["components"]["schemas"][name]
    _validate_dto(payload, name)
    for field in schema["required"]:
        without = {key: value for key, value in payload.items() if key != field}
        with pytest.raises(ValidationError):
            _validate_dto(without, name)
    for field, constraints in schema["properties"].items():
        # Arrays are invalid for every selected response field (including account).
        with pytest.raises(ValidationError):
            _validate_dto({**payload, field: []}, name)
        if not constraints.get("nullable"):
            with pytest.raises(ValidationError):
                _validate_dto({**payload, field: None}, name)
        if constraints.get("format") == "date-time":
            for invalid in ["2026-01-01", "2026-01-01T00:00:00", "invalid"]:
                with pytest.raises(ValidationError):
                    _validate_dto({**payload, field: invalid}, name)
        if constraints.get("format") == "int32":
            for invalid in [True, "123", 2**31, -(2**31) - 1]:
                with pytest.raises(ValidationError):
                    _validate_dto({**payload, field: invalid}, name)


def test_account_response_schema_and_defensive_identity_fallback() -> None:
    data = _responses()
    _validate_dto(data["account"], "AccountRead")
    assert FaciliooApiClient._extract_account_id(data["account"]) == 123
    assert FaciliooApiClient._extract_account_id(data["login"]) == 123
    for invalid in [True, "123", 0, -1, None]:
        assert FaciliooApiClient._extract_account_id({"id": invalid}) is None


def test_extractor_reproduces_snapshot_and_rejects_missing_consumed_fields() -> None:
    from scripts.extract_api_contract import extract

    snapshot = _schemas()
    # Build a small source-shaped input from the projection to test the extractor
    # offline. Reproduction from the exact full upstream bytes is a documented
    # optional command; CI never needs that multi-megabyte file or network access.
    source = {**_schemas(), "info": {"version": "v2.0"}}
    for schema in source["components"]["schemas"].values():
        if "x-source-required" in schema:
            schema["required"] = schema["x-source-required"]
            schema["additionalProperties"] = schema["x-source-additionalProperties"]
    raw = json.dumps(source).encode()
    result = extract(raw, "2026-10-24")
    assert result["paths"] == snapshot["paths"]
    assert result["components"] == snapshot["components"]
    del source["components"]["schemas"]["ConsumptionReadingRead"]["properties"]["costs"]
    with pytest.raises(KeyError):
        extract(json.dumps(source).encode(), "2026-10-24")


# Research #64 uses a separate projection, leaving the #58 runtime contract pinned.
def _readings_review() -> dict[str, Any]:
    return json.loads(
        (Path(__file__).parent / "fixtures/facilioo_readings_review.json").read_text()
    )


def test_ordinary_and_extended_reading_contract_differences() -> None:
    from scripts.extract_api_contract import extract

    contract = _readings_review()
    schemas = contract["components"]["schemas"]
    ordinary = schemas["ConsumptionReadingRead"]
    extended = schemas["ConsumptionReadingExtended"]
    extra = {"valuePercentageDifferenceToLastYear", "costPercentageDifferenceToLastYear"}
    assert set(extended["properties"]) - set(ordinary["properties"]) == extra
    assert ordinary == {
        **extended,
        "properties": {k: v for k, v in extended["properties"].items() if k not in extra},
    }
    for field in extra:
        assert extended["properties"][field] == {
            "type": "number",
            "format": "double",
            "nullable": True,
        }
    paths = contract["paths"]
    ordinary_search = paths["/api/consumption-readings/search"]["post"]
    extended_search = paths["/api/consumption-readings-extended/search"]["post"]
    assert ordinary_search["requestBody"] == extended_search["requestBody"]
    assert ordinary_search["parameters"] == extended_search["parameters"]
    assert ordinary_search["security"] == extended_search["security"] == [{"Bearer": []}]
    assert [
        p["name"]
        for p in paths["/api/consumption-readings-extended"]["get"]["parameters"]
        if p["in"] == "query"
    ] == ["PageSize", "PageNumber"]
    assert "SortByAttributeName" in [
        p["name"] for p in paths["/api/consumption-readings"]["get"]["parameters"]
    ]
    # Reproduction mechanics are offline; full-byte provenance is checked separately.
    source = {**contract, "info": {"version": "v2.0"}}
    result = extract(json.dumps(source).encode(), "2026-10-25", readings_review=True)
    assert result["paths"] == paths
    assert result["components"] == contract["components"]


class _ReadingsReviewSession(_Session):
    async def request(self, method: str, url: str, **kwargs: Any) -> _Response:
        contract = _readings_review()
        operation = contract["paths"][url.removeprefix(BASE_URL)][method.lower()]
        params = kwargs["params"]
        query = {p["name"]: p for p in operation["parameters"] if p["in"] == "query"}
        assert set(params) <= set(query)
        for name, value in params.items():
            _validate(value, query[name]["schema"], document=contract)
        if "requestBody" in operation:
            _validate(
                kwargs["json"],
                operation["requestBody"]["content"]["application/json"]["schema"],
                document=contract,
            )
        assert kwargs["headers"]["Authorization"] == "Bearer synthetic-token"
        response = await super().request(method, url, **kwargs)
        _validate(
            response.payload,
            operation["responses"]["200"]["content"]["application/json"]["schema"],
            document=contract,
        )
        return response


@pytest.mark.parametrize("partial", [False, True])
async def test_four_reading_routes_produce_identical_monthly_and_cumulative_history(
    partial: bool,
) -> None:
    from decimal import Decimal

    from custom_components.facilioo.models import ConsumptionMeter, aggregate_monthly
    from custom_components.facilioo.statistics import build_statistics

    january = {
        **_responses()["reading"],
        "readerAccountId": 456,
        "wasChecked": False,
        "wasDelivered": False,
        "averageReferenceValue": 0.8,
        "averageReferenceValueInDifferentUnitOfMeasure": 40.0,
    }
    february = {
        **january,
        "id": 11,
        "readingDate": "2026-02-28T23:00:00Z",
        "currentValue": 0.25,
        "costs": 2.75,
        "currentValueInDifferentUnitOfMeasure": None if partial else 13.5,
    }
    meter = ConsumptionMeter.from_api(_responses()["meter"])
    snapshots = []
    for path, operation in _readings_review()["paths"].items():
        method = next(iter(operation)).upper()
        rows = [dict(january), dict(february)]
        if "-extended" in path:
            for row in rows:
                row.update(
                    valuePercentageDifferenceToLastYear=-12.5,
                    costPercentageDifferenceToLastYear=None,
                )
        session = _ReadingsReviewSession([_page([rows[0]], 1, 2), _page([rows[1]], 2, 2)])
        client = FaciliooApiClient(session, "example@example.invalid", "synthetic-password")
        client._token = "synthetic-token"
        if path == READINGS_ENDPOINT:
            readings = await client.async_get_readings()
        elif path == EXTENDED_READINGS_ENDPOINT:
            readings = await client.async_get_extended_readings()
        elif path == READINGS_SEARCH_ENDPOINT:
            readings = await client.async_search_readings(
                dates=["2026"], changed_since=datetime(2026, 1, 1, tzinfo=UTC)
            )
        else:
            # Research-only invocation of existing pagination/parser primitives.
            # There is no proposed new runtime method or change of sync endpoint.
            raw = await client._paginate(
                path,
                page_size=100,
                method="POST",
                json_body={
                    "orderBy": ["readingDate asc"],
                    "dates": ["2026"],
                    "changedSince": "2026-01-01T00:00:00Z",
                },
            )
            from custom_components.facilioo.models import ConsumptionReading

            readings = client._parse_items(raw, ConsumptionReading.from_api, "reading")
        assert len(readings) == 2
        assert not session.responses
        assert [call[2]["params"]["PageNumber"] for call in session.calls] == [1, 2]
        if method == "POST":
            assert session.calls[0][2]["json"] == session.calls[1][2]["json"]
        monthly = aggregate_monthly((meter,), readings, "Europe/Berlin")[meter.kind]
        assert [item.value for item in monthly] == [Decimal("0.75"), Decimal("0.25")]
        consumption, _ = build_statistics(monthly, {}, "Europe/Berlin")
        costs, _ = build_statistics(monthly, {}, "Europe/Berlin", costs=True)
        alternative, _ = build_statistics(monthly, {}, "Europe/Berlin", different_unit=True)
        assert [point["sum"] for point in consumption] == [0, 0.75, 1.0]
        assert [point["sum"] for point in costs] == [0, 7.25, 10.0]
        assert [point["sum"] for point in alternative] == ([] if partial else [0, 36.5, 50.0])
        snapshots.append((readings, monthly, consumption, costs, alternative))
    assert all(snapshot == snapshots[0] for snapshot in snapshots[1:])
