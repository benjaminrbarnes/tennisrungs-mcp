# Resolved consumer login bootstrap

Evidence scope: anonymous GETs and public frontend source only. The new credential dispatcher is implemented and tested with synthetic responses. No real sign-in POST, password entry, cookie/CSRF value export, persistent credential creation, logout, browser-secret access, cart or application action occurred.

## Concrete results

Fresh normal flow is GET `/atlantadprca/signin` → HTTP 302 `/atlantadprca/signin?locale=en-US` → HTTP 200 HTML. The 302 issues anonymous session/UI/security cookies; HTML contains one static `window.__csrfToken` string. It stayed stable across repeated GETs in one anonymous jar and differed between independent fresh jars. This verifies acquisition/correlation, not server POST enforcement. Source module 7872 supplies it as `X-CSRF-Token` for non-GET. The new `acquire_anonymous_bootstrap()` implementation was live-tested successfully and sends only that GET/redirect. It performs no JavaScript evaluation and persists no secret values.

Fresh anonymous cookie names already include `atlantadprca_LOGGED_JSESSIONID`, `atlantadprca_JSESSIONID`, host `JSESSIONID`, FullPageView/NEW_CUI_STATUS, two BIGipServer routes and TS security cookies. Therefore those names do not prove authentication. Domains are host `anc.apm.activecommunities.com` or `.apm.activecommunities.com`, observed paths `/`. A same-jar anonymous logincheck returned HTTP 202/application `0021`. Earlier stateless logincheck returned `0002`; both are authentication boundaries. The `bootstrap` command prints only cookie names/scope/flags and CSRF-presence metadata, never values.

Use the complete fresh **process-issued first-party jar**, bound to this tenant's HTTPS requests. Minimal-cookie ablation is untested, but it need not block correct ordinary session handling: dropping routing/security cookies would be a guess. No browser profile or browser cookies are needed. The code rejects unknown domains/names, broader generic JSESSIONID scope and unexpected redirects. Any future persistence is separately approved; `.apm` cookie domain does not authorize sending this jar to another tenant/host. All outbound dispatch must enforce the fixed tenant origin and endpoint allowlist.

The normal page performs GET `/rest/user/sso/url?locale=en-US`; the anonymous read returned HTTP 202/application `0001`, empty body. Source treats `0001` as no SSO configuration. No SSO token was requested. Password-login contract is POST `/rest/user/signin?locale=en-US`, JSON login_name/password/signin_source_app:"0", plus fresh query locale:"en-US" and ak_properties:null. Source modules 704322/854436 establish those inert fields. The request also carries Page_info, X-Requested-With, JSON Content-Type and the bootstrap CSRF. Existing minimum-only builder is an offline legacy contract; prefer the new context-bound builder for future dispatch.

Current anonymous configuration is enable_recaptcha_for_account=true, enable_recaptcha_failed_count=1. Source formula is enabled AND (failed_count==0 OR NEED_VERIFY_RECAPTCHA challenge marker). The fresh jar has no marker, so the ordinary first attempt selects plain signIn; a challenge/failure must stop without a second attempt. This does not claim the server will accept a password without further verification. The builder refuses a plain request when current bootstrap indicates reCAPTCHA.

Duplicate login is numeric error_type **12**, not a guessed string. Frontend modules 539866/276814/854436 show that a false-success result with that type prompts the user and only retries after confirmation with force_logged_off:true. Its public message explicitly says the other tab/app session would be logged out and unsaved changes lost. The code classifies 12 (including a conservative numeric-string form) as STOP_DUPLICATE_LOGIN_PRESERVE_EXISTING_SESSION, with retry/storage false. No force flag is constructed. Whether the first ordinary login itself has any effect on Ava's existing session remains untested; the source establishes the force-retry behavior, not backend revocation guarantees.

Known result schema includes success, message, error_type, need_verify_recaptcha, redirect_url, security_sign_token, public_customer_id, campaign_id, ak_update_succeed; another source branch mentions access_token for ACAP sync. The previous classifier rejected all optional fields even when inert. The new source-specific classifier accepts known inert values while stopping on signing/waiver tokens, redirects, donations, activation/email flows, CAPTCHA, duplicate login, unknown fields or nonempty access tokens. It never exposes response messages or token values. Claims of success still leave authenticated_session_verified/storage_allowed/retry_allowed false until independent readback.

## Implemented local flow

`iparcs_login_bootstrap.py` obtains and validates the fresh anonymous context.
`iparcs_login.py` dispatches one POST through that same opener/jar, then requires
application `0000` from both GET `/rest/common/logincheck?locale=en-US` and GET
`/rest/system/loginuser?locale=en-US`. Public frontend API/action/reducer source
establishes `body.user.customerid`, `loginname` and `email`. The helper requires a
positive integer customer ID and an entered account identifier matching loginname
or email. Cookie presence and a successful sign-in result alone are insufficient.

Only the exact POST and those two GETs are allowlisted. Unexpected redirects,
CSRF header rotation, cookie scope and result schemas stop before persistence.
Transport failures produce sanitized errors and are never retried. The CLI
checks bootstrap/security requirements before prompting and refuses non-TTY or
echoing password input. The MCP server exposes no credential or login tool.

Synthetic tests cover the single POST/two-read order, identity matching, anonymous
readback denial, CAPTCHA/duplicate/waiver/redirect/unknown-field stops, cookie flag
preservation, optional storage, timeout/no retry, CSRF rotation and CLI approval
gates. The complete suite passed **183 tests and 4 subtests**. Anonymous bootstrap
was live verified during research against application version 26.13.45. No real
credential dispatcher or Keychain item has been exercised.

## Exact commands and separate approval

Public metadata only, with no password prompt or persistence:

```sh
.venv/bin/tennisrungs iparcs bootstrap
```

After explicit approval for one normal iParcs credential transmission, Ben opens
Terminal and runs the reviewed helper with the existing account identifier and
password entered directly in its hidden prompt:

```sh
.venv/bin/tennisrungs iparcs login --approve-credential-transmission
```

That keeps the session in memory only. With separate storage approval:

```sh
.venv/bin/tennisrungs iparcs login --approve-credential-transmission --approve-session-storage
```

The optional item is macOS Keychain service `tennis-iparcs`, account
`atlantadprca-consumer-session`. It stores the newly issued complete first-party
cookie jar (including received flags/expiry), bootstrap CSRF, tenant/origin,
issuance time and a hashed identity check, never the password. Dispatch remains
bound to `https://anc.apm.activecommunities.com/atlantadprca`; broader cookie
domains do not authorize another tenant or host. This session is account-wide,
not a vendor-scoped read-only credential. No preparation runtime consumes it.
The optional Keychain write can replace an existing item with those exact names;
it occurs only after both identity reads succeed. Delete that item using Keychain
Access to remove local access; that does not establish server-side revocation.

TennisRungs approval does not cover iParcs transmission/storage. No existing
browser cookies are exported. Computer Use returned "Computer Use is not allowed
to use the app 'com.apple.Terminal' for safety reasons." No supported secure
password injection tool is exposed, and installed 1Password CLI is not connected.
Ben's manual hidden-prompt input needs no CLI setup or password disclosure to the
model. No alternate Terminal control route is used.

## Live limits and next permitted test

Successful sign-in, actual authenticated response schema, post-auth cookie/CSRF
rotation, binding enforcement, session expiry/renewal/revocation, Keychain ACL
behavior and coexistence with Ava remain untested. Even the first ordinary login's
effect on an existing Ava session is unknown. The separate force-login path is
explicitly excluded. Site changes may require source review before another
attempt. Python/OS can retain transient secret bytes; no secure-erasure guarantee
is made. There is no automated refresh, 1Password integration or credential
installation.

The next live test needs specific approval for the credential POST and the two
identity reads, optionally a separate Keychain write. It does not authorize
patterns, validation, preparation, drafts, cart changes, reservations, checkout,
waivers, staff notification, payment, deletion or any existing automation change.
If the normal flow requests any excluded stage, stop without retry. No newly
created application or payment-page-ready handoff has been established.
