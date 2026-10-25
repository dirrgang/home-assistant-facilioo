"""Tests for privacy-safe diagnostics."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from custom_components.facilioo.diagnostics import async_get_config_entry_diagnostics
from custom_components.facilioo.models import (
    ConsumptionData,
    ConsumptionReading,
    MeterKind,
    MonthlyConsumption,
)


async def test_diagnostics_include_counts_but_no_identifiers():
    updated_at = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
    data = ConsumptionData(
        meters=(
            SimpleNamespace(id=1234, kind=MeterKind.WARM_WATER),
            SimpleNamespace(id=5678, kind=MeterKind.HEATING),
        ),
        readings=tuple(
            ConsumptionReading.from_api(
                {
                    "id": reading_id,
                    "consumptionMeterId": meter_id,
                    "readingDate": "2025-12-31T23:00:00Z",
                    "currentValue": value,
                }
            )
            for reading_id, meter_id, value in ((9876, 1234, 0.7), (9877, 5678, 80))
        ),
        monthly={
            MeterKind.WARM_WATER: (
                MonthlyConsumption(
                    date(2025, 12, 1),
                    Decimal("0.7"),
                    Decimal("4.2"),
                    False,
                    Decimal("40.1"),
                ),
            ),
            MeterKind.HEATING: (MonthlyConsumption(date(2025, 12, 1), Decimal("80"), None, False),),
        },
        updated_at=updated_at,
    )
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(
            coordinator=SimpleNamespace(data=data, last_update_success=True)
        )
    )

    diagnostics = await async_get_config_entry_diagnostics(
        SimpleNamespace(config=SimpleNamespace(time_zone="Europe/Berlin")), entry
    )

    assert diagnostics == {
        "api_status": "ok",
        "last_successful_update": "2026-01-02T03:04:00+00:00",
        "billing_coverage": {
            kind: {
                "latest_billing_month": "2025-12",
                "oldest_meter_billing_month": "2025-12",
                "meter_count": 1,
                "meters_with_history": 1,
                "meters_in_latest_month": 1,
                "is_estimated": False,
            }
            for kind in ("warm_water", "heating")
        },
        "meter_types": {"warm_water": 1, "heating": 1},
        "meter_count": 2,
        "reading_count": 2,
        "months": {"warm_water": 1, "heating": 1},
        "billing_months": {"warm_water": ["2025-12"], "heating": ["2025-12"]},
        "warm_water_energy_billing_months": ["2025-12"],
    }
    serialized = repr(diagnostics)
    assert "1234" not in serialized
    assert "5678" not in serialized
    assert "9876" not in serialized
