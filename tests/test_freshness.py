"""Communication success and usable billing data have separate freshness."""

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_component import EntityComponent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.facilioo.api import (
    FaciliooApiClient,
    FaciliooAuthenticationError,
    FaciliooConnectionError,
    FaciliooResponseError,
)
from custom_components.facilioo.const import DOMAIN
from custom_components.facilioo.coordinator import FaciliooCoordinator
from custom_components.facilioo.diagnostics import async_get_config_entry_diagnostics
from custom_components.facilioo.models import ConsumptionMeter, ConsumptionReading
from custom_components.facilioo.sensor import BASE_DESCRIPTIONS, FaciliooSensor, async_setup_entry


def _reading(meter_id=1, month=1, value=0.5, **extra):
    return ConsumptionReading.from_api(
        {
            "id": meter_id * 10 + month,
            "consumptionMeterId": meter_id,
            "readingDate": {1: "2026-01-31T23:00:00Z", 2: "2026-02-28T23:00:00Z"}[month],
            "currentValue": value,
            **extra,
        }
    )


def _meter(meter_id=1, heating=False):
    return ConsumptionMeter.from_api(
        {
            "id": meter_id,
            "typeId": 4 if heating else 5,
            "unitOfMeasure": "KWH" if heating else "M3",
        }
    )


def _sensor(coordinator, key):
    return FaciliooSensor(
        coordinator,
        SimpleNamespace(entry_id="freshness"),
        next(item for item in BASE_DESCRIPTIONS if item.key == key),
    )


async def _coordinator(hass, meters, readings):
    await hass.config.async_set_time_zone("Europe/Berlin")
    client = AsyncMock(spec=FaciliooApiClient)
    client.async_fetch_all.return_value = (meters, readings)
    coordinator = FaciliooCoordinator(hass, MockConfigEntry(domain=DOMAIN, data={}), client)
    await coordinator.async_refresh()
    return coordinator


async def test_success_without_new_month_and_then_new_month(hass, freezer):
    freezer.move_to("2026-03-01T12:00:00Z")
    coordinator = await _coordinator(hass, (_meter(),), (_reading(),))
    imported = _sensor(coordinator, "last_successful_import")
    billing = _sensor(coordinator, "warm_water_billing_month")
    assert imported.native_value == datetime(2026, 3, 1, 12, tzinfo=UTC)
    imported.entity_id = "sensor.facilioo_last_successful_import"
    billing.entity_id = "sensor.facilioo_warm_water_billing_month"
    component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
    await component.async_add_entities([imported, billing])
    assert hass.states.get(imported.entity_id).state == "2026-03-01T12:00:00+00:00"
    assert hass.states.get(billing.entity_id).state == "2026-01"
    assert billing.native_value == "2026-01"
    assert imported.entity_description.device_class is SensorDeviceClass.TIMESTAMP
    assert imported.entity_description.entity_category is EntityCategory.DIAGNOSTIC
    assert imported.entity_description.state_class is None
    assert billing.entity_description.device_class is None  # A month, not an invented day.
    coordinator.client.async_fetch_changes.return_value = ((_meter(),), ())

    freezer.move_to("2026-03-02T12:00:00Z")
    await coordinator.async_refresh()
    assert imported.native_value == datetime(2026, 3, 2, 12, tzinfo=UTC)
    assert hass.states.get(imported.entity_id).state == "2026-03-02T12:00:00+00:00"
    assert billing.native_value == "2026-01"

    coordinator.client.async_fetch_changes.return_value = ((_meter(),), (_reading(month=2),))
    freezer.move_to("2026-03-03T12:00:00Z")
    await coordinator.async_refresh()
    assert imported.native_value == datetime(2026, 3, 3, 12, tzinfo=UTC)
    assert billing.native_value == "2026-02"
    assert hass.states.get(billing.entity_id).state == "2026-02"
    assert billing.extra_state_attributes["last_refresh_success"] is True
    assert coordinator.client.async_fetch_all.await_count == 1
    assert coordinator.client.async_fetch_changes.await_count == 2


@pytest.mark.parametrize(
    "error",
    [
        FaciliooConnectionError("offline"),
        FaciliooAuthenticationError("rejected"),
        FaciliooResponseError("invalid response"),
    ],
)
async def test_failure_preserves_success_timestamp_billing_and_persisted_cache(
    hass, freezer, error
):
    freezer.move_to("2026-03-01T12:00:00Z")
    coordinator = await _coordinator(hass, (_meter(),), (_reading(),))
    before = coordinator.data
    component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
    sensors = {
        key: _sensor(coordinator, key)
        for key in ("last_successful_import", "warm_water_billing_month", "warm_water_total")
    }
    for key, sensor in sensors.items():
        sensor.entity_id = f"sensor.facilioo_{key}"
    await component.async_add_entities(sensors.values())
    saved = await coordinator._store.async_load()
    coordinator.client.async_fetch_changes.side_effect = error
    freezer.move_to("2026-03-02T12:00:00Z")
    with patch("homeassistant.config_entries.ConfigEntry.async_start_reauth_if_available"):
        await coordinator.async_refresh()
    assert coordinator.data is before
    assert coordinator.last_update_success is False
    assert await coordinator._store.async_load() == saved
    for key, expected in (
        ("last_successful_import", before.updated_at),
        ("warm_water_billing_month", "2026-01"),
    ):
        sensor = sensors[key]
        assert sensor.available is True
        assert sensor.native_value == expected
        assert sensor.extra_state_attributes["last_refresh_success"] is False
        state = hass.states.get(sensor.entity_id)
        assert state.state not in ("unknown", "unavailable")
        assert state.attributes["last_refresh_success"] is False
    assert hass.states.get(sensors["warm_water_total"].entity_id).state == "unavailable"
    diagnostics = await async_get_config_entry_diagnostics(
        hass, SimpleNamespace(runtime_data=SimpleNamespace(coordinator=coordinator))
    )
    assert diagnostics["api_status"] == "error"
    assert diagnostics["last_successful_update"] == before.updated_at.isoformat()


async def test_persistence_failure_does_not_advance_import_timestamp(hass, freezer):
    freezer.move_to("2026-03-01T12:00:00Z")
    coordinator = await _coordinator(hass, (_meter(),), (_reading(),))
    before = coordinator.data
    coordinator.client.async_fetch_changes.return_value = ((_meter(),), (_reading(month=2),))
    freezer.move_to("2026-03-02T12:00:00Z")
    with patch.object(
        coordinator._store, "async_save", side_effect=OSError("synthetic write error")
    ):
        await coordinator.async_refresh()
    assert coordinator.data is before
    assert coordinator.last_update_success is False
    assert _sensor(coordinator, "last_successful_import").native_value == before.updated_at


async def test_partial_meter_coverage_and_different_kinds(hass):
    coordinator = await _coordinator(
        hass,
        (_meter(1), _meter(2), _meter(3), _meter(4, heating=True)),
        (
            _reading(),
            _reading(month=2, isEstimated=True),
            _reading(meter_id=2),
            _reading(meter_id=4, value=80),
        ),
    )
    water = _sensor(coordinator, "warm_water_billing_month")
    heating = _sensor(coordinator, "heating_billing_month")
    assert water.native_value == "2026-02"
    assert heating.native_value == "2026-01"
    assert water.extra_state_attributes == {
        "last_refresh_success": True,
        "latest_billing_month": "2026-02",
        "oldest_meter_billing_month": "2026-01",
        "meter_count": 3,
        "meters_with_history": 2,
        "meters_in_latest_month": 1,
        "is_estimated": True,
    }
    assert heating.extra_state_attributes["meters_in_latest_month"] == 1
    assert heating.extra_state_attributes["is_estimated"] is False
    assert "meter_id" not in repr(water.extra_state_attributes)


@pytest.mark.parametrize(
    "readings",
    [
        (),
        (_reading(value=None),),
        (_reading(value=-1),),
        (_reading(deleted="2026-03-01T00:00:00Z"),),
    ],
)
async def test_unusable_history_has_unknown_month_not_zero(hass, readings):
    coordinator = await _coordinator(hass, (_meter(),), readings)
    sensor = _sensor(coordinator, "warm_water_billing_month")
    assert sensor.available is True
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {
        "last_refresh_success": True,
        "latest_billing_month": None,
        "oldest_meter_billing_month": None,
        "meter_count": 1,
        "meters_with_history": 0,
        "meters_in_latest_month": 0,
        "is_estimated": None,
    }
    assert _sensor(coordinator, "last_successful_import").native_value is not None


async def test_setup_creates_freshness_entities_without_consumption_statistics(hass):
    coordinator = await _coordinator(hass, (_meter(),), ())
    entry = SimpleNamespace(
        entry_id="freshness", runtime_data=SimpleNamespace(coordinator=coordinator)
    )
    entities = []
    await async_setup_entry(hass, entry, entities.extend)
    by_key = {entity.entity_description.key: entity for entity in entities}
    assert "last_successful_import" in by_key
    assert "warm_water_billing_month" in by_key
    assert "heating_billing_month" not in by_key
    assert by_key["last_successful_import"].unique_id == "freshness_last_successful_import"
    assert by_key["warm_water_billing_month"].entity_description.state_class is None
    assert (
        "historical_statistic_id" not in by_key["warm_water_billing_month"].extra_state_attributes
    )
