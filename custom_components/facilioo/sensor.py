"""Sensor entities for Facilioo consumption."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FaciliooRuntimeData
from .const import DOMAIN, NAME
from .coordinator import FaciliooCoordinator
from .models import ConsumptionData, MeterKind, billing_coverage
from .statistics import statistic_id


@dataclass(frozen=True, kw_only=True)
class FaciliooSensorDescription(SensorEntityDescription):
    """Description with value and attribute callbacks."""

    value_fn: Callable[[ConsumptionData], Decimal | datetime | str | None]
    attrs_fn: Callable[[ConsumptionData], dict[str, Any]] | None = None
    kind: MeterKind | None
    retain_on_failure: bool = False


def _latest_value(kind: MeterKind) -> Callable[[ConsumptionData], Decimal | None]:
    return lambda data: data.latest(kind).value if data.latest(kind) else None


def _latest_cost(kind: MeterKind) -> Callable[[ConsumptionData], Decimal | None]:
    return lambda data: data.latest(kind).costs if data.latest(kind) else None


def _latest_attrs(kind: MeterKind) -> Callable[[ConsumptionData], dict[str, Any]]:
    def attributes(data: ConsumptionData) -> dict[str, Any]:
        latest = data.latest(kind)
        return (
            {"billing_month": latest.month.isoformat()[:7], "is_estimated": latest.is_estimated}
            if latest
            else {}
        )

    return attributes


BASE_DESCRIPTIONS = (
    FaciliooSensorDescription(
        key="last_successful_import",
        translation_key="last_successful_import",
        kind=None,
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        retain_on_failure=True,
        value_fn=lambda data: data.updated_at,
    ),
    *(
        FaciliooSensorDescription(
            key=f"{kind.value}_billing_month",
            translation_key=f"{kind.value}_billing_month",
            kind=kind,
            entity_category=EntityCategory.DIAGNOSTIC,
            retain_on_failure=True,
            value_fn=lambda data, selected=kind: (
                latest.month.isoformat()[:7] if (latest := data.latest(selected)) else None
            ),
        )
        for kind in (MeterKind.WARM_WATER, MeterKind.HEATING)
    ),
    FaciliooSensorDescription(
        key="warm_water_total",
        translation_key="warm_water_total",
        kind=MeterKind.WARM_WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=3,
        value_fn=lambda data: data.total(MeterKind.WARM_WATER),
    ),
    FaciliooSensorDescription(
        key="heating_energy_total",
        translation_key="heating_energy_total",
        kind=MeterKind.HEATING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=3,
        value_fn=lambda data: data.total(MeterKind.HEATING),
    ),
    FaciliooSensorDescription(
        key="warm_water_energy_total",
        translation_key="warm_water_energy_total",
        kind=MeterKind.WARM_WATER,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=3,
        value_fn=lambda data: data.total_in_different_unit(MeterKind.WARM_WATER),
    ),
    FaciliooSensorDescription(
        key="warm_water_last_month",
        translation_key="warm_water_last_month",
        kind=MeterKind.WARM_WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.WATER,
        suggested_display_precision=3,
        value_fn=_latest_value(MeterKind.WARM_WATER),
        attrs_fn=_latest_attrs(MeterKind.WARM_WATER),
    ),
    FaciliooSensorDescription(
        key="heating_energy_last_month",
        translation_key="heating_energy_last_month",
        kind=MeterKind.HEATING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=3,
        value_fn=_latest_value(MeterKind.HEATING),
        attrs_fn=_latest_attrs(MeterKind.HEATING),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create entities only for meter kinds actually exposed by the account."""
    runtime: FaciliooRuntimeData = entry.runtime_data
    kinds = {meter.kind for meter in runtime.coordinator.data.meters}
    descriptions = list(BASE_DESCRIPTIONS)
    currency = hass.config.currency
    for kind, prefix in (
        (MeterKind.WARM_WATER, "warm_water"),
        (MeterKind.HEATING, "heating"),
    ):
        descriptions.extend(
            (
                FaciliooSensorDescription(
                    key=f"{prefix}_cost_last_month",
                    translation_key=f"{prefix}_cost_last_month",
                    kind=kind,
                    native_unit_of_measurement=currency,
                    device_class=SensorDeviceClass.MONETARY,
                    suggested_display_precision=2,
                    value_fn=_latest_cost(kind),
                    attrs_fn=_latest_attrs(kind),
                ),
                FaciliooSensorDescription(
                    key=f"{prefix}_cost_total",
                    translation_key=f"{prefix}_cost_total",
                    kind=kind,
                    native_unit_of_measurement=currency,
                    device_class=SensorDeviceClass.MONETARY,
                    state_class=SensorStateClass.TOTAL,
                    suggested_display_precision=2,
                    entity_registry_enabled_default=False,
                    value_fn=lambda data, selected=kind: data.total_costs(selected),
                ),
            )
        )
    async_add_entities(
        FaciliooSensor(runtime.coordinator, entry, description)
        for description in descriptions
        if (description.kind is None or description.kind in kinds)
        and (
            description.key != "warm_water_energy_total"
            or description.value_fn(runtime.coordinator.data) is not None
        )
    )


class FaciliooSensor(CoordinatorEntity[FaciliooCoordinator], SensorEntity):
    """A memory-only view of coordinator data."""

    _attr_has_entity_name = True
    entity_description: FaciliooSensorDescription

    def __init__(
        self,
        coordinator: FaciliooCoordinator,
        entry: ConfigEntry,
        description: FaciliooSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Facilioo Consumption",
            manufacturer=NAME,
            model="Consumption account",
        )
        self._attr_extra_state_attributes = {}
        if description.key in ("warm_water_total", "heating_energy_total"):
            self._attr_extra_state_attributes = {
                "historical_statistic_id": statistic_id(entry.entry_id, description.kind),
                "historical_cost_statistic_id": statistic_id(
                    entry.entry_id, description.kind, costs=True
                ),
            }
        elif description.key == "warm_water_energy_total":
            self._attr_extra_state_attributes = {
                "historical_statistic_id": statistic_id(
                    entry.entry_id, description.kind, different_unit=True
                ),
                "historical_cost_statistic_id": statistic_id(
                    entry.entry_id, description.kind, costs=True
                ),
            }
        elif description.key.endswith("_cost_total"):
            self._attr_extra_state_attributes = {
                "historical_statistic_id": statistic_id(
                    entry.entry_id, description.kind, costs=True
                )
            }

    @property
    def available(self) -> bool:
        """Keep last-success information readable during a failed refresh."""
        if self.entity_description.retain_on_failure:
            return self.coordinator.data is not None
        return super().available

    @property
    def native_value(self) -> Decimal | datetime | str | None:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attributes = dict(self._attr_extra_state_attributes or {})
        if self.entity_description.retain_on_failure:
            attributes["last_refresh_success"] = self.coordinator.last_update_success
            if self.entity_description.kind is not None:
                attributes.update(
                    billing_coverage(
                        self.coordinator.data,
                        self.entity_description.kind,
                        self.coordinator.hass.config.time_zone,
                    )
                )
        if self.entity_description.attrs_fn:
            attributes.update(self.entity_description.attrs_fn(self.coordinator.data))
        return attributes or None
