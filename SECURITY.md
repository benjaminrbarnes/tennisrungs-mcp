# Security

This is an unofficial client for authenticated website data. Website sessions are
account-wide credentials; the website does not issue a read-only scope for them.
The MCP interface and read transport restrict operations, but this is not a sandbox
for arbitrary Python code or another process running as the same OS user.

Only the current 0.2 release line is maintained. The combined 0.1 prototype should
not be used for unattended writes or new deployments.

## Reporting a vulnerability

Do not post passwords, cookies, tokens, private account data or exploit details in
a public issue. Use GitHub's **Security → Advisories → Report a vulnerability**
when private reporting is available. If it is unavailable, open a minimal issue
requesting a private reporting channel, without disclosing sensitive details.
No response-time or bug-bounty commitment is offered.

Useful reports identify the affected version, impact and a reproduction using
synthetic data. Avoid collecting other users' private data to demonstrate a bug.

## Boundaries

- Password entry and optional password storage are explicit local CLI operations.
- MCP tools do not log in, retrieve passwords, export cookies or accept arbitrary URLs.
- Credentials and sessions must stay outside the repository with owner-only modes.
- TLS verification remains enabled. Cross-site redirects, denied access, rate
  limits and unrecognized security challenges stop without alternate-route retries.
- CI has no account secrets and uses no live website operations.

See [authentication and storage](docs/authentication.md) for the plaintext-file
tradeoff and local-versus-server session revocation limits.
