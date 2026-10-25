"""Typed, defensive models for Facilioo consumption data."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from .const import TYPE_HEATING, TYPE_WARM_WATER, UNIT_KWH, UNIT_M3


class FaciliooDataError(ValueError):
    """Raised when a required API field is malformed."""


class MeterKind(StrEnum):
    """Consumption categories understood by the integration."""

    WARM_WATER = "warm_water"
    HEATING = "heating"
    UNKNOWN = "unknown"


def _int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise FaciliooDataError(f"Invalid {field}")
    try:
        return int(value)
    except (TypeError, ValueError) as err:
        raise FaciliooDataError(f"Invalid {field}") from err


def _decimal(value: Any, field: str, *, required: bool = False) -> Decimal | None:
    if value is None and not required:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as err:
        raise FaciliooDataError(f"Invalid {field}") from err
    if not parsed.is_finite():
        raise FaciliooDataError(f"Invalid {field}")
    return parsed


def _datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise FaciliooDataError(f"Invalid {field}")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as err:
        raise FaciliooDataError(f"Invalid {field}") from err
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FaciliooDataError(f"Invalid {field}: timezone is required")
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ConsumptionType:
    """Facilioo metadata describing a consumption meter type."""

    id: int
    meter_name: str | None
    utility_name: str

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> ConsumptionType:
        utility_raw = raw.get("utilityName")
        if not isinstance(utility_raw, str) or not utility_raw.strip():
            raise FaciliooDataError("Invalid consumption type utility name")
        meter_name_raw = raw.get("meterName")
        meter_name = None
        if meter_name_raw is not None:
            meter_name = str(meter_name_raw).strip() or None
        return cls(
            id=_int(raw.get("id"), "consumption type id"),
            meter_name=meter_name,
            utility_name=utility_raw.strip(),
        )

    @property
    def label(self) -> str:
        """Return all human-readable type metadata used for classification."""
        return " ".join(part for part in (self.meter_name, self.utility_name) if part)


@dataclass(frozen=True, slots=True)
class ConsumptionMeter:
    """A Facilioo consumption meter."""

    id: int
    type_id: int | None
    unit: str | None
    number: str | None
    label: str | None
    kind: MeterKind

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> ConsumptionMeter:
        meter_id = _int(raw.get("id"), "meter id")
        type_id_raw = raw.get("typeId")
        type_id = _int(type_id_raw, "meter type") if type_id_raw is not None else None
        unit_raw = raw.get("unitOfMeasure") or raw.get("unitOfMeasurement")
        unit = str(unit_raw).strip().upper().replace("³", "3") if unit_raw else None
        number = str(raw["number"]).strip() if raw.get("number") is not None else None
        label_parts = (
            raw.get("meterName"),
            raw.get("typeName"),
            raw.get("name"),
            raw.get("description"),
        )
        label = " ".join(str(part) for part in label_parts if part).strip() or None
        kind = classify_meter(type_id, unit, label)
        return cls(meter_id, type_id, unit, number, label, kind)


def classify_meter(
    type_id: int | None,
    unit: str | None,
    label: str | None,
    type_label: str | None = None,
) -> MeterKind:
    """Classify from ConsumptionType metadata with conservative fallbacks."""
    normalized_type = (type_label or "").casefold()
    normalized_meter = (label or "").casefold()
    warm_water_terms = ("warmwasser", "warm water", "hot water")
    heating_terms = ("heiz", "heating", "wärme", "heat")

    if type_label is not None:
        if unit == UNIT_M3 and any(term in normalized_type for term in warm_water_terms):
            return MeterKind.WARM_WATER
        if unit == UNIT_KWH and any(term in normalized_type for term in heating_terms):
            return MeterKind.HEATING
        return MeterKind.UNKNOWN

    # Known IDs from current Facilioo data remain a compatibility fallback when
    # ConsumptionType metadata is unavailable.
    if type_id == TYPE_WARM_WATER and unit == UNIT_M3:
        return MeterKind.WARM_WATER
    if type_id == TYPE_HEATING and unit == UNIT_KWH:
        return MeterKind.HEATING

    if unit == UNIT_M3 and any(term in normalized_meter for term in warm_water_terms):
        return MeterKind.WARM_WATER
    if unit == UNIT_KWH and any(term in normalized_meter for term in heating_terms):
        return MeterKind.HEATING
    return MeterKind.UNKNOWN


def resolve_meter_types(
    meters: tuple[ConsumptionMeter, ...],
    consumption_types: tuple[ConsumptionType, ...],
) -> tuple[ConsumptionMeter, ...]:
    """Resolve meter kinds and labels through Facilioo's ConsumptionType entities."""
    types_by_id = {consumption_type.id: consumption_type for consumption_type in consumption_types}
    resolved: list[ConsumptionMeter] = []
    for meter in meters:
        consumption_type = types_by_id.get(meter.type_id) if meter.type_id is not None else None
        if consumption_type is None:
            resolved.append(meter)
            continue
        resolved.append(
            replace(
                meter,
                label=meter.label or consumption_type.label,
                kind=classify_meter(
                    meter.type_id,
                    meter.unit,
                    meter.label,
                    consumption_type.label,
                ),
            )
        )
    return tuple(resolved)


@dataclass(frozen=True, slots=True)
class ConsumptionReading:
    """One monthly Facilioo consumption reading."""

    id: int
    meter_id: int
    reading_date: datetime
    value: Decimal | None
    value_in_different_unit: Decimal | None
    costs: Decimal | None
    is_estimated: bool
    deleted: bool
    last_modified: datetime | None

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> ConsumptionReading:
        modified_raw = raw.get("lastModified")
        deleted_raw = raw.get("deleted")
        return cls(
            id=_int(raw.get("id"), "reading id"),
            meter_id=_int(raw.get("consumptionMeterId"), "consumption meter id"),
            reading_date=_datetime(raw.get("readingDate"), "reading date"),
            value=_decimal(raw.get("currentValue"), "current value"),
            value_in_different_unit=_decimal(
                raw.get("currentValueInDifferentUnitOfMeasure"),
                "current value in different unit of measure",
            ),
            costs=_decimal(raw.get("costs"), "costs"),
            is_estimated=bool(raw.get("isEstimated", False)),
            deleted=deleted_raw is not None and deleted_raw is not False,
            last_modified=_datetime(modified_raw, "last modified") if modified_raw else None,
        )

    @property
    def revision_key(self) -> tuple[datetime, int]:
        return (self.last_modified or self.reading_date, self.id)


@dataclass(frozen=True, slots=True)
class MonthlyConsumption:
    """Aggregated readings for a kind and billing month."""

    month: date
    value: Decimal
    costs: Decimal | None
    is_estimated: bool
    value_in_different_unit: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ConsumptionData:
    """Processed coordinator data."""

    meters: tuple[ConsumptionMeter, ...]
    readings: tuple[ConsumptionReading, ...]
    monthly: Mapping[MeterKind, tuple[MonthlyConsumption, ...]]
    updated_at: datetime

    def values(self, kind: MeterKind) -> tuple[MonthlyConsumption, ...]:
        return self.monthly.get(kind, ())

    def total(self, kind: MeterKind) -> Decimal:
        return sum((item.value for item in self.values(kind)), Decimal(0))

    def total_costs(self, kind: MeterKind) -> Decimal | None:
        costs = [item.costs for item in self.values(kind) if item.costs is not None]
        return sum(costs, Decimal(0)) if costs else None

    def total_in_different_unit(self, kind: MeterKind) -> Decimal | None:
        """Return a complete alternative-unit total, never a partial total."""
        values = self.values(kind)
        different_values = [
            item.value_in_different_unit
            for item in values
            if item.value_in_different_unit is not None
        ]
        if not values or len(different_values) != len(values):
            return None
        return sum(different_values, Decimal(0))

    def latest(self, kind: MeterKind) -> MonthlyConsumption | None:
        values = self.values(kind)
        return values[-1] if values else None


def billing_month(reading_date: datetime, time_zone: str) -> date:
    """Map a period-end timestamp to its local billing month.

    Facilioo period ends can be exactly local midnight of the next month
    (for example 23:00 UTC in winter). Looking one microsecond back assigns
    the interval end to the month it closes without guessing a fixed offset.
    """
    local_end = reading_date.astimezone(ZoneInfo(time_zone))
    within_period = local_end - timedelta(microseconds=1)
    return date(within_period.year, within_period.month, 1)


def latest_readings_by_meter_month(
    meters: tuple[ConsumptionMeter, ...],
    readings: tuple[ConsumptionReading, ...],
    time_zone: str,
) -> dict[tuple[int, date], ConsumptionReading]:
    """Select the newest known revision for each supported meter and month."""
    meter_kinds = {meter.id: meter.kind for meter in meters}
    selected: dict[tuple[int, date], ConsumptionReading] = {}
    for reading in readings:
        if meter_kinds.get(reading.meter_id, MeterKind.UNKNOWN) is MeterKind.UNKNOWN:
            continue
        month = billing_month(reading.reading_date, time_zone)
        key = (reading.meter_id, month)
        if key not in selected or reading.revision_key > selected[key].revision_key:
            selected[key] = reading
    return selected


def aggregate_monthly(
    meters: tuple[ConsumptionMeter, ...],
    readings: tuple[ConsumptionReading, ...],
    time_zone: str,
) -> dict[MeterKind, tuple[MonthlyConsumption, ...]]:
    """Select the newest revision per meter/month and aggregate meter kinds."""
    meter_kinds = {meter.id: meter.kind for meter in meters}
    selected = latest_readings_by_meter_month(meters, readings, time_zone)

    aggregated: dict[tuple[MeterKind, date], list[ConsumptionReading]] = {}
    for (meter_id, month), reading in selected.items():
        if reading.deleted or reading.value is None or reading.value < 0:
            continue
        aggregated.setdefault((meter_kinds[meter_id], month), []).append(reading)

    result: dict[MeterKind, list[MonthlyConsumption]] = {}
    for (kind, month), values in aggregated.items():
        costs = [item.costs for item in values if item.costs is not None]
        different_values = [
            item.value_in_different_unit
            for item in values
            if item.value_in_different_unit is not None
        ]
        result.setdefault(kind, []).append(
            MonthlyConsumption(
                month=month,
                value=sum(
                    (item.value for item in values if item.value is not None),
                    Decimal(0),
                ),
                costs=sum(costs, Decimal(0)) if costs else None,
                is_estimated=any(item.is_estimated for item in values),
                value_in_different_unit=(
                    sum(different_values, Decimal(0))
                    if len(different_values) == len(values)
                    else None
                ),
            )
        )
    return {
        kind: tuple(sorted(items, key=lambda item: item.month)) for kind, items in result.items()
    }


def billing_coverage(data: ConsumptionData, kind: MeterKind, time_zone: str) -> dict[str, Any]:
    """Summarize valid billing coverage without IDs or a completeness guarantee."""
    meters = tuple(meter for meter in data.meters if meter.kind is kind)
    latest_by_meter: dict[int, date] = {}
    for (meter_id, month), reading in latest_readings_by_meter_month(
        meters, data.readings, time_zone
    ).items():
        if reading.deleted or reading.value is None or reading.value < 0:
            continue
        latest_by_meter[meter_id] = max(month, latest_by_meter.get(meter_id, month))
    latest = data.latest(kind)
    oldest = min(latest_by_meter.values(), default=None)
    return {
        "latest_billing_month": latest.month.isoformat()[:7] if latest else None,
        "oldest_meter_billing_month": oldest.isoformat()[:7] if oldest else None,
        "meter_count": len(meters),
        "meters_with_history": len(latest_by_meter),
        "meters_in_latest_month": (
            sum(month == latest.month for month in latest_by_meter.values()) if latest else 0
        ),
        "is_estimated": latest.is_estimated if latest else None,
    }
