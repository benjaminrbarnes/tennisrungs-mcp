# Offline workflow planning and reconciliation

These commands integrate a pure decision sketch from a read-only workflow audit.
They do not run scheduling, Messages, Calendar, email, booking or match mutations.
Caller-supplied grants and observations are hypotheses, not verified authorization
or source evidence. Every result says `live_execution_enabled=false`,
`authority_verified=false`, `source_assertions_verified=false` and
`timer_installed=false`. A commit-ready label is a planning result only.

```sh
tennisrungs workflow plan --input examples/workflow.json
tennisrungs --state-dir /path/to/local/state workflow reconcile \
  --input /path/to/local/non-secret-observations.json --operation-key <existing-key>
```

MCP: `workflow_plan` and `workflow_reconcile`. MCP reconciliation reads only the
operator-configured state directory's `operations.sqlite3`; it does not take an
arbitrary database path. The CLI also branches before authenticated runtime setup.
It does not access Keychain even if unrelated global flags are supplied.

The input shape is `{intent, observation, now}`. Timestamps require explicit
offsets, cents must be integers and booleans cannot stand in for money or IDs.
Season ladder/team/venue identifiers are optional typed intent fields, not fixed
account constants. Calendar/recipient/text references remain opaque local fields;
changing them changes the intent hash. No actual contacts or calendar IDs are
bundled. Model-facing operation keys use hashes rather than echoing local labels.

Observations default to incomplete, stale and unverified scope. Their flags must
eventually be established by adapters, not a historical prompt or worker claim.
Unknown writes lead to reconciliation. Local ATTEMPTED, ACKNOWLEDGED and UNKNOWN
records block replay; VERIFIED/REJECTED records still require refreshed source
evidence. Journal rows are read with SQLite `mode=ro`, never cleared or recreated.
Missing journals fail without creating a directory/database.

## Deadlines and independent authority

Hard booking cutoff is start UTC minus 72 elapsed hours. New plans default to a
15-minute conservative margin; a supplied explicit guard is preserved, including
earlier historical policies. An override beyond the hard cutoff is rejected.
UTC arithmetic preserves elapsed intervals across DST. Poll and approval-check
times are returned as metadata only; no jobs or timers are installed.

Accepted matches always take the accepted branch at/after a deadline. They are
never withdrawn as missed proposals. Caller `withdrawal_atomic=true` cannot enable
unattended cancellation; the repository has no verified atomic vendor contract.
Each date retains its own budget/scope. No cap pooling, inherited approvals,
automatic accepted-match cancellation or payment replay is implemented.

Booking, proposal, calendar and message states are separate. Paid/Tentative is not
Approved. A pending permit does not reopen checkout. Calendar reconciliation needs
a pinned identity; uncertain messages need history readback and exact approved
recipient/text matching. The planner has no way to send or change either service.

## Audit evidence versus implemented runtime

The source audit used local recorded agent readbacks and narrowly scoped account
history. Recorded event/approval state was not fresh native discovery. Fresh
calendar discovery failed with Mach 4099, and the existing agent calendar connector
was unavailable to that worker. This repository therefore does not claim a working
Calendar adapter, pin a recorded user's ID, or substitute a UI mutation.

Raw transcripts, contact mappings, account IDs, session counters and baseline
fixtures were not copied into this repo. There is no measured speedup, token saving
or cost saving from running the replacement. The planner itself invokes no model;
that is not evidence that the live workflow has been migrated.

Missing production pieces include verified authority resolution, account snapshot
adapters, a durable dispatcher/lease/outbox, calendar discovery, contact verification,
message readback, mail classification and scheduler installation. Existing agent
jobs/skills remain authoritative and unchanged. One operational owner must be
selected before any future migration.
