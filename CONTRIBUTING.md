# Contributing

Thank you for helping improve Home Assistant Facilioo.

1. Install [mise](https://mise.jdx.dev/) and run `mise run setup` from a Linux or WSL checkout.
2. Make focused changes with type annotations and asynchronous I/O.
3. Run `mise run check` before committing. Use `mise run fix` to apply Ruff fixes and formatting.
   `mise run hooks` runs the same Git hooks as CI on all files, including a guard against
   committing credentials, Home Assistant storage, diagnostics downloads or API captures.
4. Add tests for API/schema behavior and consumption/statistics semantics.
5. Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, ...).
   Releases are cut by merging the release-please PR, which bumps `pyproject.toml`,
   `manifest.json` and `uv.lock` together and writes `CHANGELOG.md`; do not bump versions by hand.

`mise run setup` provisions the repository-pinned Python, uv, and prek versions, synchronizes the
locked development environment, and installs the Git hook. Home Assistant's test harness targets
Linux; native Windows cannot import its Unix-only runtime modules.

Toolchain and runtime policy:

- **Python**: `mise.toml` and `.python-version` select the `3.14` line and resolve to its newest
  patch release, so security fixes arrive without a repository change. The floor `>=3.14.2` in
  `pyproject.toml` is inherited from Home Assistant's own `Requires-Python`; raise it together with
  the `homeassistant` dev dependency. `uv sync --locked` refuses an interpreter below the floor, so
  CI cannot silently run on an unsupported patch; the CI log records the resolved versions.
- **Dependencies**: `uv.lock` pins every Python package; Dependabot updates it weekly.
- **Tools**: `mise.toml` pins exact uv and prek versions, and CI pins the mise version. A
  `mise.lock` is deliberately not used: it would only add checksums for these tools, while the
  Python line intentionally floats to the newest patch.

Tests must fully mock HTTP. Never use a productive resident account in automated tests. Do not
post credentials, tokens, personal names, addresses, real meter IDs, or unredacted API responses
in commits, fixtures, issues, or pull requests.

The Facilioo API is external and may differ by account. When reporting a schema variation, provide
the smallest anonymized example that preserves field names and types.

For another resident portal, follow the [compatibility verification protocol](docs/compatibility-verification.md)
and its optional local probe. API observations, mocked regressions and end-to-end HA
verification are separate evidence; do not broaden compatibility claims from a login alone.
