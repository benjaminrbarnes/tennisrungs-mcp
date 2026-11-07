# Authentication and storage

Login is a local CLI operation. MCP tools never accept a website password,
perform a login, or invoke a password manager. No browser profile is inspected.

## Recommended: save the session, not the password

```sh
.venv/bin/tennisrungs login --approve-session-storage
```

The CLI requires a terminal, prompts for the account username and a hidden
password, submits the normal login form once, and verifies the authenticated
dashboard before saving a session. It refuses redirected password input and
getpass's echoing fallback. It stops on security challenges, denied access and
unexpected flows. A session is a sensitive credential even though it does not
contain the website password.

Files use the actual OS user's home directory, not a caller-supplied `HOME`:

| OS | Data directory |
| --- | --- |
| macOS | `~/Library/Application Support/tennisrungs-mcp/` |
| Linux | `~/.local/share/tennisrungs-mcp/` |

The directory must be owner-only, mode `0700`. `tennisrungs-session.json` must
be an owned regular file, mode `0600`. Symlinks, unexpected origins and malformed
cookie bundles are refused. Writes are atomic. Private data stays outside the
checkout, package and MCP configuration.

Use `--file-session` for subsequent reads. The running server reloads a replaced
session lazily, so repeating the login does not require restarting the MCP server.
There is no refresh timer or promise that a website session will never expire.

Deleting a local session file removes this client's stored copy; it does not
prove that the website revoked the session on its servers. Use the website's
account controls when server-side revocation is required.

## Optional: unattended renewal

Only configure this if you explicitly want to store your website password on the
machine. **The password file is plaintext, protected by OS ownership and file
permissions; it is not an encrypted password vault.**

```sh
.venv/bin/tennisrungs credentials bootstrap --approve-plaintext-storage
.venv/bin/tennisrungs login --credential-provider local-file --approve-session-storage
```

Bootstrap prompts for only the TennisRungs username/password pair without echo,
writes `credentials.env` in the same private directory, and performs no login.
It refuses to overwrite an existing file, including one created during the prompts. Never paste credentials into chat or
create this file in the repository.

The file parser accepts exactly two JSON-quoted values without shell expansion,
`eval`, dotenv sourcing or environment-variable overrides. Renewal uses this
fixed file, takes a per-user lock and makes one normal login attempt. It never
falls back to another account, a password manager or an interactive prompt.
Failures produce fixed diagnostics rather than server text or secret values.
There is no network login from MCP tool calls: an operator or a separately
authorized agent must invoke the CLI renewal explicitly.

## Legacy Keychain sessions (macOS only)

Existing opt-in macOS Keychain storage remains available:

```sh
.venv/bin/tennisrungs --keychain login --approve-session-storage
.venv/bin/tennisrungs --keychain ladders
.venv/bin/tennisrungs-mcp --keychain
```

The service is `tennisrungs-mcp.session.v1`, account `local-user`. Keychain access
can require a GUI session or user approval; it is not a reliable assumption for
headless agents. Do not combine `--keychain` and `--file-session`. No Keychain
entry is created or read by the default session-file flow.

There is no active 1Password service-account integration in this release.
