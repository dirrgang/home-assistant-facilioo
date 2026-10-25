"""Offline schema examples for research #63, not an implemented MFA client."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from scripts.extract_mfa_contract import PATHS, extract


def _contract() -> dict[str, Any]:
    return json.loads((Path(__file__).parent / "fixtures/facilioo_mfa_openapi_v2.json").read_text())


def _json_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: _json_schema(item) for key, item in value.items() if key != "nullable"}
    if result.get("format") == "int32":
        result.update(minimum=-(2**31), maximum=2**31 - 1)
    return {"anyOf": [result, {"type": "null"}]} if value.get("nullable") else result


def _validate(payload: Any, schema: dict[str, Any]) -> None:
    document = _json_schema(_contract())
    document.update(_json_schema(schema))
    Draft202012Validator(document, format_checker=FormatChecker()).validate(payload)


def _session(token: str) -> dict[str, Any]:
    return {
        "accountId": 123,
        "token": token,
        "issuedAt": "2026-10-25T00:00:00Z",
        "expiresAt": "2026-11-25T00:00:00Z",
        "hasExpired": False,
        "hasBeenRedeemed": False,
        "isPasswordChangeRequired": False,
    }


async def test_synthetic_challenge_session_transcript_is_schema_valid() -> None:
    """Validate a proposed exchange using a mock with no network fallback.

    Strings are deliberately not JWTs. Scope labels describe the proposal and
    cannot prove actual token claims or resident-account access.
    """
    credentials = {"email": "example@example.invalid", "password": "synthetic-password"}
    challenge = {
        "nonce": "synthetic-nonce",
        "accessToken": "synthetic-challenge-token",
        "maskedProvider": "synthetic-masked-provider",
        "providerTypeId": 123,  # Arbitrary schema-valid int, NOT a known provider mapping.
    }
    login = {
        "accessToken": "synthetic-platform-token",
        "refreshToken": _session("synthetic-refresh-one"),
        "account": {"id": 123},  # Explicit AccountRead projection.
    }
    rotated = {
        "accessToken": "synthetic-platform-token-two",
        "refreshToken": _session("synthetic-refresh-two"),
    }
    exchanges = [
        ("/api/auth/challenge/get", credentials, None, challenge),
        ("/api/auth/challenge/resend", {"nonce": challenge["nonce"]}, challenge["accessToken"], {}),
        (
            "/api/auth/challenge/complete",
            {"nonce": challenge["nonce"], "token": "synthetic-code"},
            challenge["accessToken"],
            login,
        ),
        ("/api/auth/refresh", {"refreshToken": login["refreshToken"]["token"]}, None, rotated),
        (
            "/api/auth/logout",
            {"refreshToken": rotated["refreshToken"]["token"], "logoutEverywhere": False},
            None,
            {},
        ),
    ]
    request = AsyncMock(side_effect=[response for _, _, _, response in exchanges])
    for path, body, bearer, _ in exchanges:
        operation = _contract()["paths"][path]["post"]
        _validate(body, operation["requestBody"]["content"]["application/json"]["schema"])
        headers = {"api-version": "2.0"}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        assert bool(bearer) == bool(operation.get("security"))
        response = await request("POST", path, json=body, headers=headers)
        _validate(response, operation["responses"]["200"]["content"]["application/json"]["schema"])
    assert request.await_count == len(exchanges)
    # Exhaustion fails instead of falling back to HTTP.
    with pytest.raises(StopAsyncIteration):
        await request("POST", "/unexpected")


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("CompleteChallengeRequest", {"nonce": "synthetic"}),
        ("ResendChallengeRequest", {"nonce": None}),
        ("RefreshTokenRequest", {"refreshToken": _session("synthetic")}),
        ("MultiFactorChallenge", {"accessToken": "synthetic"}),
        ("AuthSession", {**_session("synthetic"), "expiresAt": "unknown"}),
        ("CreateChalllengeRequest", {"email": "example@example.invalid"}),
    ],
)
def test_examples_reject_missing_fields_and_wrong_token_shapes(name: str, body: Any) -> None:
    with pytest.raises(ValidationError):
        _validate(body, {"$ref": f"#/components/schemas/{name}"})


def test_mfa_projection_extractor_preserves_reviewed_contract() -> None:
    snapshot = _contract()
    source = {**_contract(), "info": {"version": "v2.0"}}
    for schema in source["components"]["schemas"].values():
        if "x-source-required" in schema:
            schema["required"] = schema["x-source-required"]
            schema["additionalProperties"] = schema["x-source-additionalProperties"]
    result = extract(json.dumps(source).encode(), "2026-10-25")
    assert result["paths"] == snapshot["paths"]
    assert result["components"] == snapshot["components"]
    assert set(result["paths"]) == set(PATHS)
    del source["components"]["schemas"]["AuthSession"]["properties"]["token"]
    # Small DTOs are copied in full; a changed contract must produce a reviewable diff.
    assert (
        extract(json.dumps(source).encode(), "2026-10-25")["components"] != snapshot["components"]
    )
