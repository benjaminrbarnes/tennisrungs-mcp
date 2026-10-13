# TennisRungs direct HTTP client, CLI and MCP

A small direct HTTP integration for TennisRungs. It does **not** control a browser,
extract browser cookies, impersonate a browser, solve security challenges, or use a
bearer token. Frontend write contracts are private and subject to change.

## Current validation

- Anonymous direct HTTP player history: live read-only smoke test succeeded.
- CLI/client parsing, transport, operation journal, guarded writes: offline tests.
- MCP stdio initialization, tool discovery and safe account-auth error: protocol tests.
- Authenticated HTTP login, dashboard reads and production writes: **not yet validated**.
- iParcs anonymous sign-in bootstrap: live verified; credential POST and account readback: synthetic tests only.
- No real account credential has been transferred or stored during development.
- Autonomous proposal withdrawal: disabled, because acceptance may race with POST.

This is a functioning implementation with explicit validation gaps, not a claim of
authenticated end-to-end production success. See [evidence and boundaries](docs/evidence.md).

## Install and reads

```sh
python3 -m venv .venv
.venv/bin/python -m pip install '.[test]'
.venv/bin/tennisrungs history <season-team-id>
.venv/bin/tennisrungs --keychain ladders
.venv/bin/tennisrungs --keychain matches
.venv/bin/tennisrungs --keychain own-proposals
.venv/bin/tennisrungs --keychain open-proposals
.venv/bin/tennisrungs --keychain rankings <ladder-id>
```

IDs are intentionally not hard-coded. Ladder ID, season team ID and challenge ID
are different identifiers. Club open proposals may include other seasons. Own
proposals may appear only in My Challenges. Counts/pagination uncertainty is exposed.

## Authentication: exact approval required before setup

The cookie-session mechanism is a candidate supported by normal form-login flow,
not a validated auth contract. No documented TennisRungs personal API token exists
in the evidence collected. The development executor cannot inspect authenticated
network headers or export browser sessions through its supported browser interface.
An anonymous account request returned HTTP 403; no bypass was attempted.

The normal public login form was separately verified over direct HTTP (200):
POST `/Account/Login`, `UserName`, `Password`, `remember`, no current hidden fields
or cookies issued before authentication. Successful credential submission and
the resulting session remain untested.

The proposed approved setup is a single normal interactive username/password login
to `https://app.tennisrungs.com/Account/Login`. The form destination, field names
and hidden inputs are verified dynamically before submission. The password is
prompted without echo and is not stored. Only the returned, verified same-site
session cookies would be stored in macOS Keychain, service
`tennisrungs-mcp.session.v1`, account `local-user`. The local client process reads
that entry when explicitly started with `--keychain`. Site access is account-wide:
cookie authentication cannot provide a real read-only scope. MCP tools still
default to reads, and the server has no login or credential-export tools.

Only after specific action-time approval:

```sh
.venv/bin/tennisrungs login --approve-session-storage
```

This command has **not** been run against the real account. If the normal login
returns 403, CAPTCHA, MFA or an unexpected form, it stops. It does not rotate user
agents, switch channels, read browser databases or retry credentials. Session
expiration/renewal/revocation is not documented: expired access requires another
explicit normal login. Delete the named Keychain entry through Keychain Access to
remove the local credential; that does not prove server-side session revocation.
Python/OS may retain transient secret bytes in memory; this is not a secure-erasure
guarantee. Keychain ACL behavior and the actual cookie lifecycle need validation.

The user should run the login command in macOS Terminal and enter the password
directly at the hidden prompt, never in chat, command arguments, environment
variables or a pipe. The CLI requires a terminal and refuses getpass's echoing
fallback. Password input goes directly to the local process without model context;
it is not shown in Terminal output or saved in shell history. Keychain storage
occurs only after direct HTTP dashboard verification succeeds.

## MCP stdio

```sh
.venv/bin/tennisrungs-mcp
# Authenticated reads, only after approved credential setup:
.venv/bin/tennisrungs-mcp --keychain
```

Configure your MCP client to launch that executable over stdio. No global client
configuration is installed by this repository. Default tools:

`list_current_ladders`, `list_own_matches`, `list_own_proposals`,
`list_open_proposals`, `get_rankings`, `get_player_history`.

`--enable-writes` registers separate `propose_match`, `accept_proposal`,
`report_score` and `withdraw_proposal` tools. Enabling a process is not authority to
perform a live action. Every call additionally requires `confirmed=true`, exact
human authorization and an operation key. MCP withdrawal always refuses autonomous
execution until the server's atomic race behavior is established.

## Writes and duplicate prevention

Live proposal creation notifies the whole ladder. Never post a synthetic match as
a production test. Use [the controlled test plan](docs/controlled-tests.md).

CLI write commands require `--enable-writes`, `--keychain`, `--confirm` and
`--operation-key`. `propose` and `score` take a non-secret JSON input file; fields
are the typed `ProposalInput` and `ScoreInput` definitions. `accept` takes explicit
challenge/ladder/season-team IDs. CLI `withdraw` is manual-only and additionally
requires `--human-confirmed-race-risk`; this flag does not make the server atomic.

The local SQLite journal defaults to
`~/Library/Application Support/tennisrungs-mcp/operations.sqlite3` and is created
only when writes are enabled. It stores intent hashes, action kinds, operation
keys, states, target IDs and timestamps, not credentials or full payloads. One
proposal per season team/start time is reserved before POST, regardless of edited
notes or a new operation key. Challenge actions share a per-target reservation.
Entries survive process restarts. This is local duplicate prevention, not server
idempotency; independent machines/clients can still race.

States: `ATTEMPTED`, `ACKNOWLEDGED`, `VERIFIED`, `REJECTED`, `UNKNOWN`.
An unknown or acknowledged result must be manually reconciled using account reads
before any new action. There is intentionally no reset-and-retry command. Deleting
the journal defeats the protection. Scores remain acknowledged because the public
history contract does not identify a stable challenge ID for conclusive read-back.

All requests are single-attempt with normal TLS checks. 401/403 and 429 stop. No
automatic write retries. Pagination/schema drift blocks writes. No rate quota is
known; use infrequent reads, serialize clients, and respect vendor limits.

## iParcs anonymous reads and boundary

The separate `iparcs_consumer.py` adapter implements verified anonymous consumer
facility search, resource detail and daily availability. It requires no Keychain
or browser login. CLI commands:

```sh
.venv/bin/tennisrungs iparcs search Bagley
.venv/bin/tennisrungs iparcs detail 7247
.venv/bin/tennisrungs iparcs availability 7247 <start-ISO-date> <end-ISO-date>
.venv/bin/tennisrungs iparcs check-slot 7247 <ISO-date> 09:30:00 11:30:00
```

MCP tools: `iparcs_search_facilities`, `iparcs_resource_detail`,
`iparcs_daily_availability`, `iparcs_check_slot`. Results include timestamp, source
and coverage; availability is not a hold or booking. See
[consumer evidence and boundaries](docs/iparcs-evidence.md).

`iparcs.py` retains the adapter protocol and court-only link, which does not
preserve date/time. The anonymous transport allowlist refuses login, drafts, carts,
checkout and order commit. The separate opt-in login helper below permits only
normal login and two authenticated identity reads; preparation and booking still
have no authenticated runtime transport.
No existing scheduling job is changed. A licensed official adapter may be added
separately. Payment/browser checkout remains separate.

## iParcs normal login: separately approved local command

The source-derived helper performs one normal login with a fresh anonymous jar,
then checks `/rest/common/logincheck` and `/rest/system/loginuser` using that same
jar. A positive customer ID and matching account identifier are required. This
flow passed synthetic tests; no real credential POST or authenticated readback
has been run. See [bootstrap evidence and remaining limits](docs/iparcs-auth-bootstrap.md).

After specific approval to transmit iParcs credentials, Ben runs this in Terminal
and enters credentials directly at the non-echo prompt:

```sh
.venv/bin/tennisrungs iparcs login --approve-credential-transmission
```

That command keeps the new session in memory for the validation only. With
**separate session-storage approval**, the exact command is:

```sh
.venv/bin/tennisrungs iparcs login --approve-credential-transmission --approve-session-storage
```

The optional item is macOS Keychain service `tennis-iparcs`, account
`atlantadprca-consumer-session`. It contains only this new first-party cookie jar,
CSRF value, cookie flags/expiry and tenant/identity metadata, never the password.
The HTTP helper permits only the fixed Atlanta HTTPS tenant. This is a full
account session, not a vendor-issued read-only credential. No protected
preparation tool reads that item or becomes enabled by creating it.

Bootstrap checks precede credential prompting. CAPTCHA, duplicate login (code
12), unfamiliar scope/security fields, signing/waiver flows, redirects and
unexpected CSRF rotation stop the flow. No retry or force logout exists. The
first login's possible effect on Ava's session, authenticated response schema,
rotation/expiry and Keychain ACL behavior remain live untested. No iParcs setup
approval is inferred from TennisRungs approval. Computer Use cannot operate the
blocked Terminal, and no connected secure 1Password injection route is available
in the development executor.

## Offline workflow and preparation plans

```sh
.venv/bin/tennisrungs workflow plan --input examples/workflow.json
.venv/bin/tennisrungs iparcs prepare-plan --input examples/iparcs-preparation.json
.venv/bin/tennisrungs iparcs auth-plan
```

These are deterministic local previews only. They do not schedule, send texts,
change calendars, acquire credentials, create drafts or dispatch protected calls.
`workflow reconcile` reads the configured existing journal without clearing it.
Source/authority assertions are unverified, explicit deadline overrides are
preserved, and autonomous withdrawal stays disabled.

See [workflow boundaries](docs/workflow.md) and
[offline pre-payment/auth contracts](docs/iparcs-preparation.md). Only anonymous
iParcs reads have live HTTP validation. Selection, validation and draft changes
have unknown/protected effects; reserve, checkout, waivers, deletion and payment
remain hard-denied. A new payment-page-ready application is not established.

## Development

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m build
```

CI runs offline tests and package builds; it receives no account secrets and does
not contact either vendor. Fixtures are synthetic. Do not commit HTML from account
pages, HAR files, cookies, credentials, operational ledgers or real match fixtures.

Vendor/ladder rules and terms still apply. This unofficial integration has no
guarantee of endpoint stability or permission from TennisRungs. Confirm support and
permitted use before enabling unattended authenticated activity.
