# Local manual meter-selection probe

This developer utility supports the evidence gates in [selection design](unit-meter-selection-design.md)
and [#65](https://github.com/dirrgang/home-assistant-facilioo/issues/65).
It does not enable selection in Home Assistant. Run it manually only for your own
consenting account. Automated tests use invented responses without a network fallback.

```sh
.venv/bin/python -m scripts.probe_meter_selection --output /tmp/facilioo-meter-summary.json
```

Use a real interactive terminal. Enter a month with known readings, then email and
password at the hidden prompts. Credentials are not command arguments or environment
variables. No secret input is echoed. The script refuses non-terminal input and
stops if a full Platform login cannot be recognized. MFA is not completed or bypassed.

The only allowed operations are POST login (`skipMultiFactorAuthentication: false`),
GET meters/types, and POST ordinary reading search. All target the fixed official
HTTPS API v2.0 origin; redirects are rejected. Login creates the normal API session;
there are no meter/reading writes, refresh/logout calls, HA access or configuration
changes. Credential/access-token state and raw responses remain in process memory,
not files. TLS defaults are retained and environment proxies are disabled.

The script reads one month of account readings and compares each recognized warm-water
meter's filtered query, plus each represented unit's query, with the matching rows
from that baseline. Unit expectations include every listed meter kind assigned to
that unit, not just warm water. Meter classification follows the existing integration.
A run is limited to 12 warm-water meters, 20 pages per stream, 100 total requests,
30-second request timeouts and no automatic retry. Unexpected/incomplete pagination
or duplicate IDs abort instead of yielding a misleading partial comparison.

Only a new mode-0600 summary file is written, outside the repository. It contains
session-local aliases, grouping-field types/presence, record counts and equal/different/
no_data results. No mapping back to real IDs, credentials, names, addresses, meter
numbers, exact readings, costs or raw payloads is saved. The terminal prints the
same reduced report; errors omit exception details/server bodies. Existing output
files are never overwritten. Close the terminal when done to end the local process.

The summary is minimized structural evidence, not guaranteed anonymous: month/counts
and group patterns may still be personal. Inspect it locally before choosing to
share it. Nothing is published or sent to GitHub by this utility.

`equal` establishes agreement for that one observed snapshot and month. `no_data`
does not verify filter behavior. `different` is an investigation signal, not a proven
bug: account changes between requests, incomplete meter visibility or different unit
semantics can all matter. Current grouping is not proof of historical membership,
replacement continuity or physical independence of main/submeters. A person familiar
with the installation must still identify whether these are multiple independent
meters in one dwelling, different dwellings, or replacement/overlapping meters.


If the month search is unexpectedly empty despite known readings, run a bounded
comparison without the `dates` filter:

```sh
.venv/bin/python -m scripts.probe_meter_selection --all-history \
  --output /tmp/facilioo-meter-history-summary.json
```

This reads up to the same page/request limits for available history and compares
meter/unit filters without `dates`. The report additionally contains total meter
counts by recognized kind and counts by the original reading timestamp's calendar
month. Those labels are not derived local billing months and may differ at month
boundaries; no values or exact timestamps are exported. An empty month-filtered
response alone is not proof that the account has no readings. A successful unfiltered
comparison would still not establish historical unit-membership semantics.
