# Atlanta iParcs anonymous consumer reads

Imported from a separate permitted research task, investigated 2026-10-13.
This adapter uses the **consumer REST interface**, not the licensed organization
System API. Verification labels below distinguish observed reads from source-only
write contracts. Source handoff: `ADAPTER_SPEC.md` from the separate research task.
No raw account
responses, cookie values or CSRF values have been copied into this repository.

Origin/tenant: `https://anc.apm.activecommunities.com/atlantadprca`.

| Operation | Method/path under tenant | Evidence |
|---|---|---|
| Facility search | POST `/rest/reservation/resource?locale=en-US` | Normal browser query observed; anonymous direct HTTP 200/application 0000 verified |
| Court detail | GET `/rest/reservation/resource/detail/{id}` | Anonymous direct HTTP 200/0000 verified |
| Daily calendar | GET `/rest/reservation/resource/availability/daily/{id}` | Anonymous direct HTTP 200/0000 verified |
| Search options | GET `/rest/reservation/resource/searchoptions` | Anonymous direct HTTP 200/0000 verified; allowlisted but no separate MCP tool |
| Existing permits/history | Consumer account routes | Browser reads/source contracts; authenticated client replay unverified and not exposed |
| Proceed/form/reserve | Consumer reservation write routes | Source-only contracts; not called or exposed |
| Checkout/order commit | POST `/rest/checkout`, `/rest/checkout/order/commit` | Source-only, consequential; not called or exposed |

Public calls use observed JSON/form content types, `X-Requested-With` and
`page_info` headers, without cookies, CSRF, login, a browser profile or retries.
The sole allowed POST is facility **search**. Checkout can finalize a zero-payment
reservation: it must never be classified as harmless staging.

Search uses `body.items`, `body.total`, `next_start_index` and the ephemeral
`search_client_id`. Wrapper record counts were inconsistent. Multi-page behavior
is source-derived/offline-tested; an exhausted page before known total raises
incomplete-coverage error. The adapter never returns such partial data as complete.

Calendar reads use inclusive date ranges with customer/company ID zero. They are
chunked into 42-day windows; every requested day must be returned exactly once.
Unknown statuses, closures, gaps and incomplete coverage fail closed. A slot must
fit inside one available interval. Inconsistent midnight/cross-day entries are
rejected rather than interpreted as extra court hours. No availability response
creates a hold or guarantees successful booking.

Verified public Bagley court resources: court 1–4 are `7245`–`7248`, outdoor tennis
type `53`, center `66`, Tennis event type `27`. Reverify facility rules before any
future booking implementation; these IDs are tenant data, not general constants.

Atlanta wall times use `America/New_York`. Ambiguous/nonexistent DST times require
explicit offsets. The existing workflow's conservative guard is 72 elapsed hours
plus 15 minutes before match start, calculated through UTC; it is not a claim
that the portal itself requires the 15-minute margin.

Authentication research observed tenant JSESSIONID-family session cookies and a
CSRF header for protected non-GET requests; no Bearer mechanism was established.
The smallest sufficient cookie bundle, refresh behavior and secure credential
ingress are unverified. No authenticated client is configured. Site terms,
vendor support and frontend version drift remain separate operational risks.

Original handoff: 13 offline tests plus live anonymous search/detail/availability
reads. Combined repo adds CLI/MCP result wrappers, redirect refusal, stricter
coverage/type checks and regression tests. No account login, draft, cart, waiver,
reservation or payment operation is part of this adapter.

Combined-client live smoke: anonymous search returned four Bagley resources;
court 3 detail returned the expected resource envelope; a three-day availability
request returned all three requested days. No account credentials were used.
