"""Config flow for Facilioo."""

from __future__ import annotations

import hashlib
from typing import Any

# Home Assistant annotates data_schema with probatio (its voluptuous fork) since 2026.9.
# The supported minimum (2026.4) still ships voluptuous, which HA accepts at runtime.
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    FaciliooApiClient,
    FaciliooAuthenticationError,
    FaciliooAuthorizationError,
    FaciliooConnectionError,
    FaciliooMfaRequiredError,
    FaciliooRateLimitError,
    FaciliooResponseError,
)
from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN
from .models import MeterKind


def legacy_account_unique_id(email: str) -> str:
    """Return the email-derived unique ID used by early integration versions."""
    normalized = email.strip().casefold().encode()
    return hashlib.sha256(normalized).hexdigest()


async def _validate(hass: HomeAssistant, data: dict[str, Any]) -> int:
    client = FaciliooApiClient(async_get_clientsession(hass), data[CONF_EMAIL], data[CONF_PASSWORD])
    account_id = await client.async_login()
    meters = await client.async_get_resolved_meters()
    supported_meter_ids = {meter.id for meter in meters if meter.kind is not MeterKind.UNKNOWN}
    if not supported_meter_ids:
        raise LookupError("no supported consumption meters")
    readings = await client.async_search_readings()
    if not any(reading.meter_id in supported_meter_ids for reading in readings):
        raise LookupError("no supported consumption meters")
    return account_id


class FaciliooConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup and credential replacement."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            account_id, error = await self._async_validate_input(user_input)
            if error is None and account_id is not None:
                await self.async_set_unique_id(str(account_id))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Facilioo", data=user_input)
            errors["base"] = error or "unknown_response"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(  # type: ignore[arg-type]  # see import note
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {
                CONF_EMAIL: user_input.get(CONF_EMAIL, entry.data[CONF_EMAIL]),
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            account_id, error = await self._async_validate_input(data)
            if error is None and account_id is not None:
                new_unique_id = str(account_id)
                await self.async_set_unique_id(new_unique_id)
                if entry.unique_id in (
                    None,
                    legacy_account_unique_id(entry.data[CONF_EMAIL]),
                ):
                    self._abort_if_unique_id_configured()
                    self.hass.config_entries.async_update_entry(entry, unique_id=new_unique_id)
                else:
                    self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = error or "unknown_response"
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(  # type: ignore[arg-type]  # see import note
                {
                    vol.Required(CONF_EMAIL, default=entry.data[CONF_EMAIL]): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def _async_validate_input(
        self, user_input: dict[str, Any]
    ) -> tuple[int | None, str | None]:
        try:
            account_id = await _validate(self.hass, user_input)
        except FaciliooMfaRequiredError:
            return None, "mfa_required"
        except FaciliooAuthenticationError:
            return None, "invalid_auth"
        except FaciliooAuthorizationError:
            return None, "not_authorized"
        except FaciliooRateLimitError:
            return None, "rate_limited"
        except FaciliooConnectionError:
            return None, "cannot_connect"
        except LookupError:
            return None, "no_consumption_data"
        except FaciliooResponseError:
            return None, "unknown_response"
        return account_id, None
