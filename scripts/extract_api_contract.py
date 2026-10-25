"""Extract only client-used operations and DTO fields from public OpenAPI v2 JSON.

No network access, example values, credentials, or response bodies are involved.
The output is an OpenAPI projection, not a complete upstream specification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

SOURCE_URL = "https://api.facilioo.de/swagger/v2.0/swagger.json"
OPERATIONS = {
    "/api/auth/login": "post",
    "/api/accounts/myself": "get",
    "/api/consumption-meters": "get",
    "/api/consumption-types": "get",
    "/api/consumption-readings": "get",
    "/api/consumption-readings/search": "post",
    "/api/consumption-readings-extended": "get",
}
# None retains every property of the small request and pagination schemas.
# Response selections cover only fields read by the client, including optional ones.
FIELDS = {
    "LoginRequest": None,
    "LoginCommandResponse": ("accessToken", "account"),
    "AccountRead": ("id",),
    "ConsumptionMeterRead": ("id", "typeId", "unitOfMeasure", "number"),
    "ConsumptionTypeRead": ("id", "meterName", "utilityName"),
    "ConsumptionReadingRead": (
        "id",
        "consumptionMeterId",
        "readingDate",
        "currentValue",
        "currentValueInDifferentUnitOfMeasure",
        "costs",
        "isEstimated",
        "deleted",
        "lastModified",
    ),
    "ConsumptionReadingExtended": (
        "id",
        "consumptionMeterId",
        "readingDate",
        "currentValue",
        "currentValueInDifferentUnitOfMeasure",
        "costs",
        "isEstimated",
        "deleted",
        "lastModified",
    ),
    "ConsumptionReadingSearchRequest": None,
    "PaginatedListOfConsumptionMeterRead": None,
    "PaginatedListOfConsumptionTypeRead": None,
    "PaginatedListOfConsumptionReadingRead": None,
    "PaginatedListOfConsumptionReadingExtended": None,
}


# Separate bounded research profile; the runtime client profile remains unchanged.
READINGS_REVIEW_OPERATIONS = {
    "/api/consumption-readings": "get",
    "/api/consumption-readings/search": "post",
    "/api/consumption-readings-extended": "get",
    "/api/consumption-readings-extended/search": "post",
}
READINGS_REVIEW_FIELDS = dict.fromkeys(
    (
        "ConsumptionReadingRead",
        "ConsumptionReadingExtended",
        "ConsumptionReadingSearchRequest",
        "PaginatedListOfConsumptionReadingRead",
        "PaginatedListOfConsumptionReadingExtended",
    )
)


def _without_annotations(value: Any) -> Any:
    """Retain constraints, but never copy upstream example/default response data."""
    if isinstance(value, dict):
        return {
            key: _without_annotations(item)
            for key, item in value.items()
            if key not in {"description", "example", "examples", "externalDocs", "title"}
        }
    if isinstance(value, list):
        return [_without_annotations(item) for item in value]
    return value


def extract(raw: bytes, retrieved_on: str, *, readings_review: bool = False) -> dict[str, Any]:
    """Produce a deterministic, source-hashed contract projection; fail on missing fields."""
    date.fromisoformat(retrieved_on)
    source = json.loads(raw)
    if source["openapi"] != "3.0.1" or source["info"]["version"] != "v2.0":
        raise ValueError("Review the changed upstream specification version before extraction")
    schemas = {}
    selected_fields = READINGS_REVIEW_FIELDS if readings_review else FIELDS
    for name, fields in selected_fields.items():
        original = source["components"]["schemas"][name]
        selected = original["properties"] if fields is None else fields
        schema = _without_annotations(original)
        schema["properties"] = {
            field: _without_annotations(original["properties"][field]) for field in selected
        }
        if fields is not None:
            schema["x-source-required"] = original.get("required", [])
            schema["x-source-additionalProperties"] = original.get("additionalProperties", True)
            schema["additionalProperties"] = True  # Unparsed upstream fields are out of scope.
            schema["required"] = [key for key in original.get("required", []) if key in fields]
        schemas[name] = schema
    paths = {}
    operations = READINGS_REVIEW_OPERATIONS if readings_review else OPERATIONS
    for path, method in operations.items():
        operation = source["paths"][path][method]
        retained = {
            "parameters": _without_annotations(operation.get("parameters", [])),
            "responses": {"200": _without_annotations(operation["responses"]["200"])},
            "security": operation.get("security", []),
        }
        if "requestBody" in operation:
            retained["requestBody"] = _without_annotations(operation["requestBody"])
        paths[path] = {method: retained}
    return {
        "provenance": {
            "url": SOURCE_URL,
            "retrieved_on": retrieved_on,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "upstream_info_version": source["info"]["version"],
            "scope": (
                "Ordinary/extended readings research: full reading DTOs and four read operations"
                if readings_review
                else "Client-used response fields, request schemas and pagination; not full DTOs"
            ),
        },
        "openapi": source["openapi"],
        "paths": paths,
        "components": {"schemas": schemas},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--retrieved-on", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--check", action="store_true", help="Compare without overwriting the snapshot"
    )
    parser.add_argument(
        "--readings-review", action="store_true", help="Compare all four reading routes"
    )
    args = parser.parse_args()
    result = extract(
        args.source.read_bytes(), args.retrieved_on, readings_review=args.readings_review
    )
    if args.check:
        if result != json.loads(args.output.read_text(encoding="utf-8")):
            parser.exit(
                1, "Contract or provenance differs; review upstream changes before updating.\n"
            )
    else:
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
