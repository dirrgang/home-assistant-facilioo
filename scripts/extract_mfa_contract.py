"""Extract the bounded MFA/session research contract from public OpenAPI bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from scripts.extract_api_contract import SOURCE_URL, _without_annotations

PATHS = (
    "/api/auth/login",
    "/api/auth/challenge/get",
    "/api/auth/challenge/complete",
    "/api/auth/challenge/resend",
    "/api/auth/refresh",
    "/api/auth/logout",
)
SCHEMAS = (
    "LoginRequest",
    "CreateChalllengeRequest",  # Upstream spelling.
    "MultiFactorChallenge",
    "CompleteChallengeRequest",
    "ResendChallengeRequest",
    "RefreshTokenRequest",
    "LogoutRequest",
    "AuthSession",
    "TokenPair",
    "Void",
)


def extract(raw: bytes, retrieved_on: str) -> dict[str, Any]:
    """Preserve complete small DTOs and project login to session/account identity."""
    date.fromisoformat(retrieved_on)
    source = json.loads(raw)
    if source["openapi"] != "3.0.1" or source["info"]["version"] != "v2.0":
        raise ValueError("Review changed upstream version before extraction")
    upstream = source["components"]["schemas"]
    schemas = {name: _without_annotations(upstream[name]) for name in SCHEMAS}
    for name, fields in {
        "LoginCommandResponse": ("accessToken", "refreshToken", "account"),
        "AccountRead": ("id",),
    }.items():
        original = upstream[name]
        schemas[name] = {
            "type": original["type"],
            "properties": {
                key: _without_annotations(original["properties"][key]) for key in fields
            },
            "required": [key for key in original["required"] if key in fields],
            "additionalProperties": True,
            "x-source-required": original["required"],
            "x-source-additionalProperties": original.get("additionalProperties", True),
        }
    return {
        "provenance": {
            "url": SOURCE_URL,
            "retrieved_on": retrieved_on,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "scope": "MFA/session research; login/account projections; no runtime implementation",
        },
        "openapi": source["openapi"],
        "paths": {
            path: {"post": _without_annotations(source["paths"][path]["post"])} for path in PATHS
        },
        "components": {"schemas": schemas},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--retrieved-on", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = extract(args.source.read_bytes(), args.retrieved_on)
    if args.check:
        if result != json.loads(args.output.read_text(encoding="utf-8")):
            parser.exit(1, "Contract or provenance differs; review before updating.\n")
    else:
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
