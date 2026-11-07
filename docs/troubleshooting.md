# Troubleshooting

## Server does not start

1. Run the configured executable with `--help` in a terminal.
2. Check that the executable path is absolute and belongs to the installation's
   virtual environment. An MCP client may not inherit your shell's `PATH`.
3. Use Python 3.11+ on macOS or Linux. Windows is not supported.
4. If macOS reports `Resource deadlock avoided`, or imports hang, check whether
   iCloud has offloaded the checkout or virtual environment. Download the folder
   in Finder. For a durable deployment, use a local directory outside synced
   Desktop/Documents and recreate the virtual environment there; moving an
   existing virtual environment can leave broken absolute executable paths.

The server uses stdio. Do not add shell banners or print application diagnostics
to its stdout. Stop the terminal's test server before starting a duplicate client.

## AuthenticationRequired

An expired session, missing session, login-page redirect or HTTP 401/403 is not
an empty result. Run the explicit local login command again, then repeat the
original read. Check the account and client OS user. Stop on a rejected credential
or security challenge; do not loop through passwords or accounts.

`--file-session` reads a saved session; it does not automatically log in. Starting
without a session backend supports public player history only.

If Keychain reports a user-interaction error in a headless process, use the
normal session-file flow described in [authentication](authentication.md).

## InvalidInput or UnsupportedContract

Use a current ladder ID for standings and a player season-team ID for history.
These are not interchangeable. Malformed or changed website HTML produces an
explicit error. Never substitute remembered data or an empty list for a failure.

A result with `complete: false` means pagination, counts or source coverage need
review. Keep the warnings in any user-facing summary.

## HTTP 429

Stop requests, respect the site's retry guidance and reduce polling. This client
makes no automatic retries or attempts to evade rate limits.

## Missing phone numbers or booking commands

Phone/contact lookup and account/match/reservation writes are outside the scope
of this read-only integration. Court availability belongs in a separate connector.
