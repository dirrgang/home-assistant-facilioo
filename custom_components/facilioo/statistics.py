"""Official Recorder external-statistics backfill for monthly data."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.recorder import get_instance
from homeassistant.helpers.storage import Store
from homeassistant.util.unit_conversion import EnergyConverter, VolumeConverter

from .const import (
    DOMAIN,
    STATISTIC_HEATING,
    STATISTIC_HEATING_COSTS,
    STATISTIC_WARM_WATER,
    STATISTIC_WARM_WATER_COSTS,
    STATISTIC_WARM_WATER_ENERGY,
    STORE_VERSION,
)
from .models import (
    ConsumptionData,
    MeterKind,
    MonthlyConsumption,
    latest_readings_by_meter_month,
)

_LOGGER = logging.getLogger(__name__)
_INVALID_STATISTIC_KEY = re.compile(r"[^a-z0-9]+")
_STATISTICS_LAYOUT_VERSION = 2
_CLEAR_STATISTICS_TIMEOUT = 30


def statistic_id(
    entry_id: str,
    kind: MeterKind,
    *,
    costs: bool = False,
    different_unit: bool = False,
) -> str:
    """Return an account-specific stable external statistic ID."""
    if costs and different_unit:
        raise ValueError("A statistic cannot represent costs and consumption together")
    if different_unit:
        if kind is not MeterKind.WARM_WATER:
            raise ValueError("Alternative-unit history is only defined for warm water")
        suffix = STATISTIC_WARM_WATER_ENERGY
    elif costs:
        suffix = (
            STATISTIC_WARM_WATER_COSTS if kind is MeterKind.WARM_WATER else STATISTIC_HEATING_COSTS
        )
    else:
        suffix = STATISTIC_WARM_WATER if kind is MeterKind.WARM_WATER else STATISTIC_HEATING
    # Config entry IDs are opaque. Newer Home Assistant versions may use uppercase
    # ULIDs, while Recorder only accepts lowercase statistic ID slugs.
    entry_key = _INVALID_STATISTIC_KEY.sub("_", entry_id.casefold()).strip("_") or "entry"
    return f"{DOMAIN}:{entry_key}_{suffix}"


def statistic_name(kind: MeterKind, *, costs: bool = False, different_unit: bool = False) -> str:
    """Return a name describing the external series' actual UI role."""
    if different_unit:
        if kind is not MeterKind.WARM_WATER or costs:
            raise ValueError("Invalid alternative-unit statistic")
        return "Facilioo warm water energy history (Energy Dashboard gas source)"
    if kind is MeterKind.WARM_WATER:
        value = "cost history" if costs else "consumption history"
        role = "source cost" if costs else "water source"
        return f"Facilioo warm water {value} (Energy Dashboard {role})"
    value = "cost history" if costs else "consumption history"
    role = "gas cost" if costs else "gas source"
    return f"Facilioo heating {value} (Energy Dashboard {role})"


def _next_month(month: date) -> date:
    return date(month.year + (month.month == 12), month.month % 12 + 1, 1)


def _month_range(first: date, last: date) -> Iterator[date]:
    month = first
    while month <= last:
        yield month
        month = _next_month(month)


def _boundary(month: date, time_zone: str) -> datetime:
    """Return local month boundary as an aware, top-of-hour UTC timestamp."""
    return datetime(month.year, month.month, 1, tzinfo=ZoneInfo(time_zone)).astimezone(UTC)


def build_statistics(
    current: tuple[MonthlyConsumption, ...],
    previous: dict[str, str],
    time_zone: str,
    observed_months: set[date] | None = None,
    *,
    costs: bool = False,
    different_unit: bool = False,
) -> tuple[list[StatisticData], dict[str, str]]:
    """Build an exact cumulative series without erasing transiently omitted data."""
    if costs and different_unit:
        raise ValueError("A series cannot contain costs and consumption together")
    current_values: dict[str, Decimal] = {}
    for item in current:
        value = (
            item.costs if costs else item.value_in_different_unit if different_unit else item.value
        )
        if value is not None:
            current_values[item.month.isoformat()] = value
    if (
        different_unit
        and not previous
        and any(item.value_in_different_unit is None for item in current)
    ):
        return [], {}
    if (costs or different_unit) and not current_values and not previous:
        return [], {}
    observed = {item.month for item in current} if observed_months is None else observed_months
    values: dict[str, Decimal | str] = dict(previous)
    for month in observed:
        values[month.isoformat()] = current_values.get(month.isoformat(), Decimal(0))
    values.update(current_values)
    months = {date.fromisoformat(key) for key in previous} | {
        date.fromisoformat(key) for key in values
    }
    if not months:
        return [], {}
    first, last = min(months), max(months)
    cumulative = Decimal(0)
    statistics: list[StatisticData] = [
        {"start": _boundary(first, time_zone), "state": 0.0, "sum": 0.0}
    ]
    stored: dict[str, str] = {}
    for month in _month_range(first, last):
        value = Decimal(values.get(month.isoformat(), Decimal(0)))
        cumulative += value
        stored[month.isoformat()] = str(value)
        statistics.append(
            {
                "start": _boundary(_next_month(month), time_zone),
                "state": float(cumulative),
                "sum": float(cumulative),
            }
        )
    return statistics, stored


class FaciliooStatisticsManager:
    """Import and revise historical hourly statistics without direct DB access."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}.statistics"
        )

    async def _async_clear_owned_statistics(self) -> bool:
        """Clear this config entry's external series before a layout migration."""
        done = asyncio.Event()

        def on_done() -> None:
            self.hass.loop.call_soon_threadsafe(done.set)

        statistic_ids = [
            statistic_id(self.entry.entry_id, kind, costs=costs)
            for kind in (MeterKind.WARM_WATER, MeterKind.HEATING)
            for costs in (False, True)
        ]
        statistic_ids.append(
            statistic_id(self.entry.entry_id, MeterKind.WARM_WATER, different_unit=True)
        )
        get_instance(self.hass).async_clear_statistics(statistic_ids, on_done=on_done)
        try:
            async with asyncio.timeout(_CLEAR_STATISTICS_TIMEOUT):
                await done.wait()
        except TimeoutError:
            _LOGGER.error("Timed out migrating Facilioo historical statistics")
            return False
        return True

    async def async_sync(self, data: ConsumptionData) -> None:
        saved = await self.store.async_load() or {"months": {}}
        saved_months = saved.get("months", {}) if isinstance(saved, dict) else {}
        saved_layout = saved.get("layout_version") if isinstance(saved, dict) else None
        if saved_months and saved_layout != _STATISTICS_LAYOUT_VERSION:
            if not await self._async_clear_owned_statistics():
                return
            _LOGGER.info("Rebuilding Facilioo historical statistics after layout migration")
        next_months: dict[str, dict[str, str]] = {}
        meter_kinds = {meter.id: meter.kind for meter in data.meters}
        observed_by_kind: dict[MeterKind, set[date]] = {}
        observed_costs_by_kind: dict[MeterKind, set[date]] = {}
        observed_different_unit_by_kind: dict[MeterKind, set[date]] = {}
        latest_readings = latest_readings_by_meter_month(
            data.meters, data.readings, self.hass.config.time_zone
        )
        for (meter_id, month), reading in latest_readings.items():
            kind = meter_kinds[meter_id]
            observed_by_kind.setdefault(kind, set()).add(month)
            if reading.costs is not None or reading.deleted:
                observed_costs_by_kind.setdefault(kind, set()).add(month)
            if reading.value_in_different_unit is not None or reading.deleted:
                observed_different_unit_by_kind.setdefault(kind, set()).add(month)
        for kind, unit, unit_class, name, is_costs, is_different_unit, store_key in (
            (
                MeterKind.WARM_WATER,
                UnitOfVolume.CUBIC_METERS,
                VolumeConverter.UNIT_CLASS,
                statistic_name(MeterKind.WARM_WATER),
                False,
                False,
                MeterKind.WARM_WATER.value,
            ),
            (
                MeterKind.HEATING,
                UnitOfEnergy.KILO_WATT_HOUR,
                EnergyConverter.UNIT_CLASS,
                statistic_name(MeterKind.HEATING),
                False,
                False,
                MeterKind.HEATING.value,
            ),
            (
                MeterKind.WARM_WATER,
                UnitOfEnergy.KILO_WATT_HOUR,
                EnergyConverter.UNIT_CLASS,
                statistic_name(MeterKind.WARM_WATER, different_unit=True),
                False,
                True,
                "warm_water_energy",
            ),
            (
                MeterKind.WARM_WATER,
                self.hass.config.currency,
                None,
                statistic_name(MeterKind.WARM_WATER, costs=True),
                True,
                False,
                f"{MeterKind.WARM_WATER.value}_costs",
            ),
            (
                MeterKind.HEATING,
                self.hass.config.currency,
                None,
                statistic_name(MeterKind.HEATING, costs=True),
                True,
                False,
                f"{MeterKind.HEATING.value}_costs",
            ),
        ):
            previous = saved_months.get(store_key, {})
            if not isinstance(previous, dict):
                previous = {}
            stats, stored = build_statistics(
                data.values(kind),
                previous,
                self.hass.config.time_zone,
                (
                    observed_costs_by_kind.get(kind, set())
                    if is_costs
                    else observed_different_unit_by_kind.get(kind, set())
                    if is_different_unit
                    else observed_by_kind.get(kind, set())
                ),
                costs=is_costs,
                different_unit=is_different_unit,
            )
            if not stats:
                next_months[store_key] = stored
                continue
            metadata: StatisticMetaData = {
                "mean_type": StatisticMeanType.NONE,
                "has_sum": True,
                "name": name,
                "source": DOMAIN,
                "statistic_id": statistic_id(
                    self.entry.entry_id,
                    kind,
                    costs=is_costs,
                    different_unit=is_different_unit,
                ),
                "unit_class": unit_class,
                "unit_of_measurement": unit,
            }
            try:
                async_add_external_statistics(self.hass, metadata, stats)
            except HomeAssistantError as err:
                # Historical import is additive functionality. Recorder rejecting a
                # batch must not prevent the regular Facilioo entities from loading.
                _LOGGER.error("Unable to import Facilioo %s history: %s", store_key, err)
                next_months[store_key] = previous
            else:
                next_months[store_key] = stored
        await self.store.async_save(
            {"layout_version": _STATISTICS_LAYOUT_VERSION, "months": next_months}
        )
        _LOGGER.debug("Facilioo historical statistics synchronized")
