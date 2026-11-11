"""Data coordinator for Facilioo."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FaciliooApiClient, FaciliooAuthenticationError, FaciliooError
from .const import (
    DOMAIN,
    RECONCILIATION_INTERVAL,
    SYNC_OVERLAP,
    SYNC_STORE_VERSION,
    UPDATE_INTERVAL,
)
from .models import (
    ConsumptionData,
    ConsumptionReading,
    FaciliooDataError,
    MeterKind,
    aggregate_monthly,
    billing_month,
)

_LOGGER = logging.getLogger(__name__)


def _serialize_reading(reading: ConsumptionReading) -> dict[str, Any]:
    """Serialize the minimal reading state required for incremental syncs."""
    return {
        "id": reading.id,
        "meter_id": reading.meter_id,
        "reading_date": reading.reading_date.isoformat(),
        "value": str(reading.value) if reading.value is not None else None,
        "value_in_different_unit": (
            str(reading.value_in_different_unit)
            if reading.value_in_different_unit is not None
            else None
        ),
        "costs": str(reading.costs) if reading.costs is not None else None,
        "is_estimated": reading.is_estimated,
        "deleted": reading.deleted,
        "last_modified": reading.last_modified.isoformat() if reading.last_modified else None,
    }


def _deserialize_reading(raw: Mapping[str, Any]) -> ConsumptionReading:
    """Restore a cached reading through the normal defensive API parser."""
    payload: dict[str, Any] = {
        "id": raw.get("id"),
        "consumptionMeterId": raw.get("meter_id"),
        "readingDate": raw.get("reading_date"),
        "currentValue": raw.get("value"),
        "currentValueInDifferentUnitOfMeasure": raw.get("value_in_different_unit"),
        "costs": raw.get("costs"),
        "isEstimated": raw.get("is_estimated", False),
        "deleted": raw.get("deleted", False),
    }
    if raw.get("last_modified") is not None:
        payload["lastModified"] = raw["last_modified"]
    return ConsumptionReading.from_api(payload)


def _parse_watermark(value: Any) -> datetime | None:
    """Parse a stored UTC watermark, treating malformed state as uninitialized."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


class FaciliooCoordinator(DataUpdateCoordinator[ConsumptionData]):
    """Fetch and process account consumption with persisted incremental readings."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: FaciliooApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self.client = client
        self._store: Store[dict[str, Any]] = Store(
            hass,
            SYNC_STORE_VERSION,
            f"{DOMAIN}.{entry.entry_id}.consumption",
        )

    async def _async_load_sync_state(
        self,
    ) -> tuple[dict[int, ConsumptionReading], datetime | None, datetime | None]:
        saved = await self._store.async_load()
        if not isinstance(saved, dict):
            return {}, None, None

        raw_readings = saved.get("readings")
        if not isinstance(raw_readings, list):
            return {}, None, None

        readings: dict[int, ConsumptionReading] = {}
        cache_valid = True
        for raw in raw_readings:
            if not isinstance(raw, Mapping):
                cache_valid = False
                continue
            try:
                reading = _deserialize_reading(raw)
            except FaciliooDataError as err:
                _LOGGER.warning("Ignoring invalid Facilioo sync cache and rebuilding: %s", err)
                cache_valid = False
                continue
            readings[reading.id] = reading

        watermark = _parse_watermark(saved.get("last_sync"))
        last_full_sync = _parse_watermark(saved.get("last_full_sync"))
        if not cache_valid or watermark is None:
            return {}, None, None
        return readings, watermark, last_full_sync

    async def _async_save_sync_state(
        self,
        readings: Mapping[int, ConsumptionReading],
        watermark: datetime,
        last_full_sync: datetime,
    ) -> None:
        await self._store.async_save(
            {
                "last_sync": watermark.astimezone(UTC).isoformat(),
                "last_full_sync": last_full_sync.astimezone(UTC).isoformat(),
                "readings": [
                    _serialize_reading(reading)
                    for reading in sorted(readings.values(), key=lambda item: item.id)
                ],
            }
        )

    def _reconciliation_tombstones(
        self,
        previous: Mapping[int, ConsumptionReading],
        current: Mapping[int, ConsumptionReading],
        sync_started: datetime,
    ) -> tuple[ConsumptionReading, ...]:
        """Represent hard deletions long enough for statistics to revise affected months."""
        current_keys = {
            (reading.meter_id, billing_month(reading.reading_date, self.hass.config.time_zone))
            for reading in current.values()
        }
        tombstones: list[ConsumptionReading] = []
        for reading_id, reading in previous.items():
            if reading_id in current or reading.deleted:
                continue
            key = (
                reading.meter_id,
                billing_month(reading.reading_date, self.hass.config.time_zone),
            )
            if key in current_keys:
                continue
            tombstones.append(replace(reading, deleted=True, last_modified=sync_started))
        return tuple(tombstones)

    async def _async_update_data(self) -> ConsumptionData:
        sync_started = datetime.now(UTC)
        cached, last_sync, last_full_sync = await self._async_load_sync_state()
        try:
            if (
                last_sync is not None
                and last_full_sync is not None
                and sync_started - last_full_sync < RECONCILIATION_INTERVAL
            ):
                changed_since = last_sync - SYNC_OVERLAP
                meters, changed_readings = await self.client.async_fetch_changes(changed_since)
                for reading in changed_readings:
                    cached[reading.id] = reading
                readings = tuple(cached.values())
                next_full_sync = last_full_sync
                sync_mode = "incremental"
            else:
                meters, fetched_readings = await self.client.async_fetch_all()
                fresh = {reading.id: reading for reading in fetched_readings}
                tombstones = self._reconciliation_tombstones(cached, fresh, sync_started)
                cached = fresh
                readings = tuple(fresh.values()) + tombstones
                changed_readings = fetched_readings
                next_full_sync = sync_started
                sync_mode = "reconciliation" if last_sync is not None else "full"
        except FaciliooAuthenticationError as err:
            raise ConfigEntryAuthFailed("Facilioo authentication failed") from err
        except FaciliooError as err:
            raise UpdateFailed(str(err)) from err

        monthly = aggregate_monthly(meters, readings, self.hass.config.time_zone)
        await self._async_save_sync_state(cached, sync_started, next_full_sync)

        known_meters = sum(meter.kind is not MeterKind.UNKNOWN for meter in meters)
        _LOGGER.debug(
            "Facilioo %s sync completed: %d meters (%d supported), %d returned readings, "
            "%d cached readings",
            sync_mode,
            len(meters),
            known_meters,
            len(changed_readings),
            len(cached),
        )
        return ConsumptionData(
            meters=meters,
            readings=tuple(readings),
            monthly=monthly,
            updated_at=datetime.now(UTC),
        )
