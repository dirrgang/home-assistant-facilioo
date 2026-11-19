"""Static guards against blocking time zone lookups on the event loop."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

INTEGRATION = Path(__file__).parent.parent / "custom_components" / "facilioo"
SOURCES = sorted(INTEGRATION.glob("*.py"))


@pytest.mark.parametrize("source", SOURCES, ids=lambda path: path.name)
def test_integration_uses_home_assistants_loaded_time_zone(source: Path) -> None:
    """Forbid ``zoneinfo`` and ``config.time_zone``; use ``dt_util.get_default_time_zone()``.

    Building a zone from the configured name loads the zone file from disk on
    first use, which is blocking I/O on the event loop (HACS review of
    hacs/default#12519). Tests cannot catch it at runtime because the zone is
    already cached in the test process.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    violations = [
        f"{source.name}:{node.lineno}"
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Import)
            and any(alias.name.split(".")[0] == "zoneinfo" for alias in node.names)
        )
        or (isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "zoneinfo")
        or (
            isinstance(node, ast.Attribute)
            and node.attr == "time_zone"
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "config"
        )
    ]

    assert violations == []
