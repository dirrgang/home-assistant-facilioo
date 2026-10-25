"""Shared anonymized test data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def meter_payload() -> dict[str, Any]:
    return json.loads((FIXTURES / "meters.json").read_text(encoding="utf-8"))


@pytest.fixture
def reading_payload() -> dict[str, Any]:
    return json.loads((FIXTURES / "readings.json").read_text(encoding="utf-8"))


@pytest.fixture(params=json.loads((FIXTURES / "mfa_responses.json").read_text(encoding="utf-8")))
def mfa_payload(request) -> dict[str, Any]:
    """Synthetic signals for the existing defensive MFA detection, not a verified flow."""
    return dict(request.param)
