"""Tests for setup, duplicates, errors and reauthentication."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.facilioo.api import (
    FaciliooAuthenticationError,
    FaciliooAuthorizationError,
    FaciliooConnectionError,
    FaciliooMfaRequiredError,
)
from custom_components.facilioo.config_flow import legacy_account_unique_id
from custom_components.facilioo.const import CONF_EMAIL, CONF_PASSWORD, DOMAIN

ACCOUNT_ID = 12345


@pytest.fixture(autouse=True)
def mock_setup_entry():
    """Keep config-flow tests isolated from component and dependency setup."""
    with (
        patch(
            "homeassistant.config_entries.async_process_deps_reqs",
            new=AsyncMock(),
        ),
        patch("homeassistant.setup.async_process_deps_reqs", new=AsyncMock()),
        patch("custom_components.facilioo.async_setup_entry", return_value=True) as setup,
    ):
        yield setup


async def test_successful_setup(hass, enable_custom_integrations, mock_setup_entry):
    with patch(
        "custom_components.facilioo.config_flow._validate",
        new=AsyncMock(return_value=ACCOUNT_ID),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={CONF_EMAIL: "resident@example.test", CONF_PASSWORD: "password"},
        )
    await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["data"][CONF_EMAIL] == "resident@example.test"
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].unique_id == str(ACCOUNT_ID)
    mock_setup_entry.assert_awaited_once()


async def test_duplicate_account_uses_account_id_not_email(hass, enable_custom_integrations):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(ACCOUNT_ID),
        data={CONF_EMAIL: "old@example.test", CONF_PASSWORD: "old"},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.facilioo.config_flow._validate",
        new=AsyncMock(return_value=ACCOUNT_ID),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={CONF_EMAIL: "new@example.test", CONF_PASSWORD: "new"},
        )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_errors_are_presented(hass, enable_custom_integrations):
    from custom_components.facilioo.api import FaciliooConnectionError

    with patch(
        "custom_components.facilioo.config_flow._validate",
        new=AsyncMock(side_effect=FaciliooConnectionError("offline")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={CONF_EMAIL: "resident@example.test", CONF_PASSWORD: "password"},
        )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.parametrize("source", [SOURCE_USER, SOURCE_REAUTH])
@pytest.mark.parametrize(
    ("exception", "error_key"),
    [
        (FaciliooMfaRequiredError, "mfa_required"),
        (FaciliooAuthenticationError, "invalid_auth"),
        (FaciliooAuthorizationError, "not_authorized"),
        (FaciliooConnectionError, "cannot_connect"),
    ],
)
async def test_login_failures_show_safe_specific_errors(
    hass, enable_custom_integrations, mock_setup_entry, source, exception, error_key, caplog
):
    credentials = {CONF_EMAIL: "resident@example.test", CONF_PASSWORD: "secret-password"}
    context = {"source": source}
    if source == SOURCE_REAUTH:
        entry = MockConfigEntry(domain=DOMAIN, unique_id=str(ACCOUNT_ID), data=credentials)
        entry.add_to_hass(hass)
        context["entry_id"] = entry.entry_id

    with patch("custom_components.facilioo.config_flow.FaciliooApiClient", autospec=True) as client:
        client.return_value.async_login.side_effect = exception(
            "resident@example.test secret-password synthetic-challenge"
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context=context, data=credentials
        )
        if source == SOURCE_REAUTH:
            result = await hass.config_entries.flow.async_configure(result["flow_id"], credentials)

    assert result["type"] == "form"
    assert result["step_id"] == ("user" if source == SOURCE_USER else "reauth_confirm")
    assert result["errors"] == {"base": error_key}
    client.return_value.async_get_resolved_meters.assert_not_awaited()
    mock_setup_entry.assert_not_awaited()
    for private_value in (*credentials.values(), "synthetic-challenge"):
        assert private_value not in str(result["errors"])
        assert private_value not in str(result.get("description_placeholders", {}))
        assert private_value not in caplog.text
    if source == SOURCE_USER:
        assert not hass.config_entries.async_entries(DOMAIN)
    else:
        assert entry.data == credentials


async def test_authorization_error_is_not_presented_as_invalid_credentials(
    hass, enable_custom_integrations
):
    from custom_components.facilioo.api import FaciliooAuthorizationError

    with patch(
        "custom_components.facilioo.config_flow._validate",
        new=AsyncMock(side_effect=FaciliooAuthorizationError("forbidden")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={CONF_EMAIL: "resident@example.test", CONF_PASSWORD: "password"},
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "not_authorized"}


async def test_reauthentication_updates_credentials_for_same_account(
    hass, enable_custom_integrations
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(ACCOUNT_ID),
        data={CONF_EMAIL: "resident@example.test", CONF_PASSWORD: "old"},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.facilioo.config_flow._validate",
        new=AsyncMock(return_value=ACCOUNT_ID),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_EMAIL: "changed@example.test", CONF_PASSWORD: "new"},
        )
    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_EMAIL] == "changed@example.test"
    assert entry.data[CONF_PASSWORD] == "new"
    assert entry.unique_id == str(ACCOUNT_ID)


async def test_reauthentication_rejects_different_account(hass, enable_custom_integrations):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(ACCOUNT_ID),
        data={CONF_EMAIL: "resident@example.test", CONF_PASSWORD: "old"},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.facilioo.config_flow._validate",
        new=AsyncMock(return_value=99999),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_EMAIL: "other@example.test", CONF_PASSWORD: "new"},
        )
    assert result["type"] == "abort"
    assert result["reason"] == "unique_id_mismatch"


async def test_reauthentication_migrates_legacy_email_unique_id(hass, enable_custom_integrations):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=legacy_account_unique_id("resident@example.test"),
        data={CONF_EMAIL: "resident@example.test", CONF_PASSWORD: "old"},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.facilioo.config_flow._validate",
        new=AsyncMock(return_value=ACCOUNT_ID),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_EMAIL: "resident@example.test", CONF_PASSWORD: "new"},
        )
    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert entry.unique_id == str(ACCOUNT_ID)
