# Instructions for automated contributors

This repository provides a community-maintained Home Assistant custom integration for Facilioo. Read `README.md`, `docs/technical-reference.md`, `CONTRIBUTING.md`, and `SECURITY.md` before substantive work; inspect the relevant integration code, tests, existing issues, and open pull requests.

## Work tracking and handoffs

- **GitHub Issues are the authoritative operational backlog** for concrete bugs, investigations, feature requests, maintenance, acceptance criteria, dependencies, blockers, and task status. Search existing open and closed issues and PRs before creating a new issue; do not duplicate tracked work.
- Use a focused issue for substantial, actionable work. State the observed problem or evidence, intended outcome, scope boundaries, reproducible steps where applicable, and observable acceptance criteria. Distinguish an unverified hypothesis from a confirmed defect. Small self-contained fixes can be explained in their PR without ceremonial issues.
- Before implementing an issue, read its current discussion and linked PRs. Record material findings, limitations, changed scope, validation, and handoff information in the issue; use the PR description for delivered changes and review evidence. Keep implementation, release, and real-world compatibility verification distinct.
- Keep GitHub Issues and PRs as the live coordination surface. Do not introduce or maintain local worklogs, TODO inventories, or parallel task-status registers. Durable technical and user-facing documentation remains in the repository; commits record change-specific context, not a competing backlog.
- Link related issues and PRs. Close issues only when their stated acceptance criteria are met; unresolved verification must remain visible. If GitHub is temporarily unavailable, use a clearly temporary handoff and synchronize it when access returns.

## Official Facilioo API reference

The integration targets the official Facilioo REST API **v2.0**. For changes to
API endpoints, authentication, request parameters, pagination, or response
models, consult Facilioo's first-party documentation before editing code:

- [Developer documentation](https://developers.facilioo.de/)
- [AI-readable documentation index](https://developers.facilioo.de/llms.txt)
- [OpenAPI v2 specification](https://api.facilioo.de/swagger/v2.0/swagger.json)

Compare the relevant documented contract with the existing client, models,
and tests. Distinguish a **confirmed contract mismatch** from a hypothesis or
previously observed backend behavior; do not assume that published endpoints
or privileges are available to every resident account or white-label portal.
Preserve documented behavior unless evidence justifies changing it and add
fully mocked regression tests for material changes. If the upstream
documentation cannot be accessed or does not describe the behavior in
question, state that limitation explicitly instead of inventing a contract.

The published specification is external reference material, not permission
to send credentials, access tokens, or private resident data to documentation
sites or third-party test tools. For reproducible schema checks, follow
[issue #58](https://github.com/dirrgang/home-assistant-facilioo/issues/58).

## Integration and security boundaries

- Preserve the documented behavior and constraints: monthly billing-derived data is not live telemetry; unverified white-label compatibility must not be presented as established; unsupported MFA must not be bypassed.
- Never test against a productive resident account in automated tests. Fully mock HTTP and add focused regression tests for changed API, statistics, or configuration-flow behavior. Follow `CONTRIBUTING.md` and run `mise run check` when the environment supports it.
- Do not put credentials, tokens, resident names, addresses, meter identifiers, unredacted diagnostics, or complete real API responses in code, fixtures, issues, PRs, or logs. Follow `SECURITY.md` for private vulnerability reports rather than disclosing vulnerabilities in a public issue.
- A requested code or documentation change does not authorize access to real resident accounts or Home Assistant devices, production changes, deployment, or publication outside the requested scope.
