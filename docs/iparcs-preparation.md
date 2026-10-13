# iParcs preparation: offline implemented, protected runtime disabled

Imported source-derived preparation contracts and synthetic tests from a separate
task. No authenticated iParcs transport or credential store is configured. No
protected endpoint has been called by this integration. Live-verified consumer
operations are anonymous facility search, details, availability and the separate
normal sign-in bootstrap. No real credential POST or authenticated readback was
performed.

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

## Direct normal-login helper

The CLI login helper is implemented and tested with synthetic responses, separate
from this preparation client. Anonymous bootstrap acquisition and source-specific
security/duplicate-login classification are resolved. It permits exactly one
normal credential POST, followed by same-session logincheck and loginuser reads.
It requires a matching positive customer identity before optional, separately
approved Keychain storage. It exposes no password or session values. See the
[reviewed commands and remaining live gaps](iparcs-auth-bootstrap.md).

Real sign-in, authenticated schemas, post-auth cookie/CSRF rotation and expiry,
Keychain ACL behavior, and the first login's possible effect on Ava's session are
untested. No real credentials or session were stored. CAPTCHA, failures/duplicate
login, unfamiliar fields, signing/waiver/redirect flows and unknown cookie scope
stop it; it never retries or forces logout. TennisRungs approval does not cover
iParcs credential transmission or its separate Keychain item. A successful login
does not enable the preparation transport or authorize any application stage.

Before any protected test, obtain a concrete target, permitted stages and exact
user approval. A pattern/validation experiment must exclude proceed, reserve,
checkout, waivers, staff notification, payment and deletion; unexpected state
requires stopping and separate cleanup authorization. No such experiment was run.
