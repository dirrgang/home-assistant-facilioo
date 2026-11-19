"""Tests for exact idempotent historical series construction."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.energy.validate import (
    GAS_USAGE_DEVICE_CLASSES,
    GAS_USAGE_UNITS,
)
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfEnergy
from homeassistant.util import dt as dt_util

import custom_components.facilioo.statistics as statistics_module
from custom_components.facilioo.models import (
    ConsumptionData,
    MeterKind,
    MonthlyConsumption,
)
from custom_components.facilioo.statistics import (
    FaciliooStatisticsManager,
    build_statistics,
    statistic_id,
    statistic_name,
)

BERLIN = ZoneInfo("Europe/Berlin")


def month(value: str, when: date, estimated: bool = False) -> MonthlyConsumption:
    return MonthlyConsumption(when, Decimal(value), None, estimated)


def cost_month(value: str, costs: str | None, when: date) -> MonthlyConsumption:
    return MonthlyConsumption(
        when,
        Decimal(value),
        Decimal(costs) if costs is not None else None,
        False,
    )


def test_historical_backfill_has_baseline_and_cumulative_boundaries():
    stats, stored = build_statistics(
        (
            month("0.172", date(2025, 11, 1)),
            month("0.766", date(2025, 12, 1)),
            month("0.500", date(2026, 1, 1)),
        ),
        {},
        BERLIN,
    )
    assert [point["sum"] for point in stats] == [0.0, 0.172, 0.938, 1.438]
    assert stats[0]["start"].minute == 0
    assert stored["2025-11-01"] == "0.172"


def test_repeat_is_identical_and_correction_shifts_following_points():
    original = {
        "2025-11-01": "0.172",
        "2025-12-01": "0.766",
        "2026-01-01": "0.500",
    }
    current = (
        month("0.180", date(2025, 11, 1)),
        month("0.766", date(2025, 12, 1)),
        month("0.500", date(2026, 1, 1)),
    )
    corrected, saved = build_statistics(current, original, BERLIN)
    repeated, repeated_saved = build_statistics(current, saved, BERLIN)
    assert [point["sum"] for point in corrected] == [0.0, 0.18, 0.946, 1.446]
    assert corrected == repeated
    assert saved == repeated_saved


def test_deleted_month_becomes_zero_increment_not_stale_data():
    old = {"2025-11-01": "0.2", "2025-12-01": "0.7"}
    stats, saved = build_statistics(
        (month("0.7", date(2025, 12, 1)),),
        old,
        BERLIN,
        {date(2025, 11, 1), date(2025, 12, 1)},
    )
    assert [point["sum"] for point in stats] == [0.0, 0.0, 0.7]
    assert saved["2025-11-01"] == "0"


def test_temporarily_omitted_month_retains_last_known_value():
    old = {"2025-11-01": "0.2", "2025-12-01": "0.7"}
    stats, saved = build_statistics(
        (month("0.7", date(2025, 12, 1)),),
        old,
        BERLIN,
        {date(2025, 12, 1)},
    )
    assert [point["sum"] for point in stats] == [0.0, 0.2, 0.9]
    assert saved["2025-11-01"] == "0.2"


def test_monthly_costs_have_independent_cumulative_series():
    stats, saved = build_statistics(
        (
            cost_month("0.172", "3.40", date(2025, 11, 1)),
            cost_month("0.766", "15.94", date(2025, 12, 1)),
        ),
        {},
        BERLIN,
        costs=True,
    )

    assert [point["sum"] for point in stats] == [0.0, 3.4, 19.34]
    assert saved == {"2025-11-01": "3.40", "2025-12-01": "15.94"}


def test_missing_latest_cost_does_not_erase_stored_month():
    stats, saved = build_statistics(
        (cost_month("0.172", None, date(2025, 11, 1)),),
        {"2025-11-01": "3.40"},
        BERLIN,
        set(),
        costs=True,
    )

    assert [point["sum"] for point in stats] == [0.0, 3.4]
    assert saved == {"2025-11-01": "3.40"}


def test_deleted_cost_month_becomes_zero_increment():
    stats, saved = build_statistics(
        (),
        {"2025-11-01": "3.40", "2025-12-01": "15.94"},
        BERLIN,
        {date(2025, 11, 1)},
        costs=True,
    )

    assert [point["sum"] for point in stats] == [0.0, 0.0, 15.94]
    assert saved["2025-11-01"] == "0"


def test_statistic_id_is_external_and_account_specific():
    assert statistic_id("abc123", MeterKind.WARM_WATER) == (
        "facilioo:abc123_warm_water_consumption"
    )


def test_statistic_id_normalizes_uppercase_config_entry_ulid():
    assert statistic_id("01K2N-ABC__DEF", MeterKind.HEATING) == (
        "facilioo:01k2n_abc_def_heating_energy_consumption"
    )


def test_cost_statistic_id_is_normalized_and_account_specific():
    assert statistic_id("01K2N-ABC", MeterKind.WARM_WATER, costs=True) == (
        "facilioo:01k2n_abc_warm_water_costs"
    )


def test_external_statistic_names_are_unambiguous_energy_history():
    assert statistic_name(MeterKind.WARM_WATER) == (
        "Facilioo warm water consumption history (Energy Dashboard water source)"
    )
    assert statistic_name(MeterKind.WARM_WATER, costs=True) == (
        "Facilioo warm water cost history (Energy Dashboard source cost)"
    )
    assert statistic_name(MeterKind.HEATING, costs=True) == (
        "Facilioo heating cost history (Energy Dashboard gas cost)"
    )
    assert statistic_name(MeterKind.HEATING) == (
        "Facilioo heating consumption history (Energy Dashboard gas source)"
    )
    assert statistic_name(MeterKind.WARM_WATER, different_unit=True) == (
        "Facilioo warm water energy history (Energy Dashboard gas source)"
    )


def test_heating_energy_is_valid_for_home_assistant_gas_source():
    assert SensorDeviceClass.ENERGY in GAS_USAGE_DEVICE_CLASSES
    assert UnitOfEnergy.KILO_WATT_HOUR in GAS_USAGE_UNITS[SensorDeviceClass.ENERGY]


def test_warm_water_energy_has_independent_cumulative_series():
    current = (
        MonthlyConsumption(date(2025, 11, 1), Decimal("0.172"), None, False, Decimal("10.0018")),
        MonthlyConsumption(date(2025, 12, 1), Decimal("0.766"), None, False, Decimal("44.5529")),
    )

    stats, saved = build_statistics(current, {}, BERLIN, different_unit=True)

    assert [point["sum"] for point in stats] == [0.0, 10.0018, 54.5547]
    assert saved == {"2025-11-01": "10.0018", "2025-12-01": "44.5529"}
    assert statistic_id("01K2NABC", MeterKind.WARM_WATER, different_unit=True) == (
        "facilioo:01k2nabc_warm_water_energy_consumption"
    )


def test_incomplete_initial_warm_water_energy_series_is_not_published():
    current = (
        MonthlyConsumption(date(2025, 11, 1), Decimal("0.172"), None, False, Decimal("10.0018")),
        MonthlyConsumption(date(2025, 12, 1), Decimal("0.766"), None, False),
    )

    assert build_statistics(current, {}, BERLIN, different_unit=True) == ([], {})


@pytest.mark.asyncio
async def test_layout_migration_clears_only_owned_series_once(monkeypatch):
    class MemoryStore:
        saved = {"months": {"warm_water": {"2025-11-01": "0.172"}}}

        async def async_load(self):
            return self.saved

        async def async_save(self, data):
            self.saved = data

    cleared = []

    class FakeRecorder:
        def async_clear_statistics(self, statistic_ids, *, on_done):
            cleared.append(statistic_ids)
            on_done()

    monkeypatch.setattr(statistics_module, "get_instance", lambda hass: FakeRecorder())
    monkeypatch.setattr(
        statistics_module, "async_add_external_statistics", lambda hass, metadata, stats: None
    )
    # No ``config.time_zone``: the manager must use Home Assistant's loaded zone
    # instead of constructing ``ZoneInfo`` (blocking file I/O) on the event loop.
    monkeypatch.setattr(dt_util, "get_default_time_zone", lambda: BERLIN)
    manager = object.__new__(FaciliooStatisticsManager)
    manager.hass = SimpleNamespace(
        loop=asyncio.get_running_loop(),
        config=SimpleNamespace(currency="EUR"),
    )
    manager.entry = SimpleNamespace(entry_id="01K2NABC")
    manager.store = MemoryStore()
    data = ConsumptionData((), (), {}, datetime.now(UTC))

    await manager.async_sync(data)
    await manager.async_sync(data)

    assert cleared == [
        [
            statistic_id("01K2NABC", MeterKind.WARM_WATER),
            statistic_id("01K2NABC", MeterKind.WARM_WATER, costs=True),
            statistic_id("01K2NABC", MeterKind.HEATING),
            statistic_id("01K2NABC", MeterKind.HEATING, costs=True),
            statistic_id("01K2NABC", MeterKind.WARM_WATER, different_unit=True),
        ]
    ]
    assert manager.store.saved["layout_version"] == 2
