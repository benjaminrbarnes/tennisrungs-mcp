# iParcs preparation: offline implemented, protected runtime disabled

Imported source-derived preparation contracts and synthetic tests from a separate
task. No authenticated iParcs transport or credential store is configured. No
protected endpoint has been called by this integration. The only live-verified
consumer operations remain anonymous facility search, details and availability.

```sh
tennisrungs iparcs prepare-plan --input examples/iparcs-preparation.json
tennisrungs iparcs compare-cart --input /path/to/local/sanitized-cart-snapshots.json
tennisrungs iparcs auth-plan
```

MCP tools `iparcs_preparation_plan` and `iparcs_compare_cart_snapshots` are pure
local functions. They never construct `PreparationClient`, a transport, browser,
credential provider or scheduler. Comparison inputs must be sanitized; do not use
HARs, cookies, CSRF values, passwords, cards or full account dumps. Matching local
snapshots does not verify a live browser or final payment-page amount.

## Contract library and effect boundaries

`iparcs_preparation.py` implements an injectable contract/test client: selection
patterns, validation, proceed/draft readback, event type/name updates, cart parsing,
concurrency tokens and fingerprint comparison. No concrete protected transport is
supplied. Its default denies mutation. Any later dispatcher must verify direct
human authority independently of the `TestPermission` structure.

Pattern generation **and validation** may write selection/session/draft state or
hold a slot. They are not harmless reads. GET `/rest/preparation` may initialize
cart/order state. All require separately approved exact target experiments before
live use. Proceed definitely changes draft/mini-cart state; hold lifetime and staff
notification timing remain unverified.

For injected tests, mutation requires matching selection hash, explicit selected
customer, operation scope, approval reference/expiry, acknowledgment of unknown
effects, and a durable checkpoint callback. Court/date/time/attendance/name/type/
cap bind the selection. No budget is inferred. Semantic or readback failure after
an acknowledged mutation marks reconciliation required. No uncertain/completed
operation is automatically replayed. A mock callback is not a validated durable
production journal or cross-process lease.

Reserve, checkout, waiver/disclaimer answers, deletion, payment, quick reservation
and sign-in are hard-denied by the preparation client even with a test permission.
Reserve may complete an application instead of merely adding to cart. POST
`/rest/checkout` may finalize a zero-payment request. Thus a new payment-page-ready
application cannot be promised while those boundaries remain forbidden.

The handoff model uses a fixed tenant URL and local fingerprint; no state token is
placed in its URL. A separate browser session sharing the client cart is unproven.
Candidate `/newcart/checkout` is shown only if a supplied snapshot claims existing
checkout eligibility; final payment total and live browser verification remain
false. On mismatch, stop rather than exporting a session or resubmitting.

## Direct normal-login helper: exact remaining gaps

`iparcs_auth_contract.py` contains an offline in-memory request builder and safe
response classifier. Known source shape: POST `/rest/user/signin`, JSON
`login_name`, `password`, `signin_source_app:"0"`; source HTTP helper uses
`X-CSRF-Token`. Secret-bearing fields have no dataclass repr or tool output. A
future local non-echo prompt helper refuses echoing/redirected input, but is not
wired to a login command and has never been used with real credentials.

The following prevent a truthful functioning login dispatcher today:

- Exact fresh anonymous CSRF/bootstrap acquisition and its cookie binding.
- Minimal sufficient tenant-bound session/routing cookie set and safe persistence.
- Complete legal-waiver, redirect and duplicate-login response schemas.
- Whether a new normal login could displace the existing agent's session.
- Harmless authenticated logincheck/readback validation.
- Separate iParcs credential-entry and Keychain storage approval.

The classifier stops on CAPTCHA, failures/duplicate login, unfamiliar fields,
waiver/redirect flows and unknown session scope. It never enables force logout,
retry or storage—even when an offline response claims success. It is a contract
helper, not a fake live-auth implementation. TennisRungs approval does not cover
the proposed separate iParcs Keychain item.

Before any protected test, obtain a concrete target, permitted stages and exact
user approval. A pattern/validation experiment must exclude proceed, reserve,
checkout, waivers, staff notification, payment and deletion; unexpected state
requires stopping and separate cleanup authorization. No such experiment was run.
