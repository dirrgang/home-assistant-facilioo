"""Diagnostics support with credentials and API identifiers excluded."""

from __future__ import annotations

from collections import Counter
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import FaciliooRuntimeData
from .models import MeterKind, billing_coverage


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return non-sensitive operational diagnostics."""
    runtime: FaciliooRuntimeData = entry.runtime_data
    data = runtime.coordinator.data
    meter_types = Counter(meter.kind.value for meter in data.meters)
    return {
        "api_status": "ok" if runtime.coordinator.last_update_success else "error",
        "last_successful_update": data.updated_at.isoformat(),
        "billing_coverage": {
            kind.value: billing_coverage(data, kind, hass.config.time_zone)
            for kind in (MeterKind.WARM_WATER, MeterKind.HEATING)
            if any(meter.kind is kind for meter in data.meters)
        },
        "meter_types": dict(meter_types),
        "meter_count": len(data.meters),
        "reading_count": len(data.readings),
        "months": {kind.value: len(values) for kind, values in data.monthly.items()},
        "billing_months": {
            kind.value: [value.month.isoformat()[:7] for value in values]
            for kind, values in data.monthly.items()
        },
        "warm_water_energy_billing_months": [
            value.month.isoformat()[:7]
            for value in data.values(MeterKind.WARM_WATER)
            if value.value_in_different_unit is not None
        ],
    }
