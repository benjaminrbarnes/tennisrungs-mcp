# TennisRungs MCP

[![Tests](https://github.com/benjaminrbarnes/tennisrungs-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/benjaminrbarnes/tennisrungs-mcp/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![MIT license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Give an MCP-compatible assistant read access to your TennisRungs ladders,
matches, proposals, rankings and player history. A CLI provides the same reads
and handles account login locally, outside the assistant's chat.

This is an **unofficial, read-only integration**. It uses normal HTTPS requests,
not browser automation or exported browser cookies. It cannot challenge players,
accept proposals, submit scores, withdraw matches or book courts. It is not
associated with or endorsed by TennisRungs.

## What it can read

| MCP tool | Returns | Login |
| --- | --- | --- |
| `list_current_ladders` | Current ladder memberships and season IDs | Required |
| `list_own_matches` | Your pending, proposed and accepted matches | Required |
| `list_own_proposals` | Proposals you posted | Required |
| `list_open_proposals` | Club-wide open proposals, including other ladders | Required |
| `get_rankings` | Standings for an exact ladder ID | Required |
| `get_player_history` | A player's results and original score strings | Not required |

Results include a source URL, observation timestamp, completeness flag and
warnings. An incomplete result is not proof that no matches exist. Ladder IDs
and player season-team IDs are different: use IDs returned by the tools rather
than guessing or reusing a previous season's identifiers.

Example questions for your assistant:

- “Which matches have I accepted, and which are still unscheduled?”
- “What open proposals are in my current ladder?”
- “Compare my opponent's results with mine against common opponents.”

Opponent phone-number lookup is not implemented. Court availability and
reservations belong in a separate court-availability connector.

## Install

Requires **Python 3.11 or newer on macOS or Linux**. Windows is not supported.
The commands below install from source; no PyPI release is assumed.

```sh
git clone https://github.com/benjaminrbarnes/tennisrungs-mcp.git
cd tennisrungs-mcp
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/tennisrungs --help
```

Keep the checkout and virtual environment in a local directory. Cloud-synced
Desktop/Documents folders can offload Python files and prevent the server from
starting. No browser extension, developer API key or browser-cookie export is
needed.

## Log in

Run this yourself in a local terminal:

```sh
.venv/bin/tennisrungs login --approve-session-storage
.venv/bin/tennisrungs --file-session ladders
.venv/bin/tennisrungs --file-session matches
```

Enter your account username and password at the prompts. The password is hidden
and **is not saved** by this command; only the verified website session is stored.
Never put passwords in chat, command arguments or an MCP configuration file.

Login makes one normal attempt. A rejected password, CAPTCHA, MFA or unexpected
security flow stops the operation. Complete account challenges through the
website; this project does not bypass them. If the session expires, rerun the
login command.

[Authentication and storage](docs/authentication.md) explains file locations,
optional unattended renewal and the legacy macOS Keychain option.

## Connect an MCP client

Add a stdio server to your client's MCP configuration, replacing the command
with the **absolute path** to your installed executable:

```json
{
  "mcpServers": {
    "tennisrungs": {
      "command": "/absolute/path/to/tennisrungs-mcp/.venv/bin/tennisrungs-mcp",
      "args": ["--file-session"]
    }
  }
}
```

Run the client under the same OS account that completed login. Restart or reload
its MCP connection after adding the configuration. Session renewal is observed
by the server without a restart. The MCP exposes only the six read tools above;
it has no login, password export or arbitrary HTTP tool.

For public player history alone, omit `--file-session`. Starting the server does
not log in or read a saved password file.

## CLI examples

```sh
# Use IDs returned by your account's current reads:
.venv/bin/tennisrungs --file-session open-proposals
.venv/bin/tennisrungs --file-session rankings <ladder-id>
.venv/bin/tennisrungs history <player-season-team-id>
```

Output is JSON. Account results can contain private names and match details;
keep them out of public logs and issue reports. A failed command exits with code
2 and reports a sanitized JSON error on stderr.

## Reliability and boundaries

Normal login, saved sessions and authenticated ladder/match reads have been
exercised against the live site in the maintained deployment, most recently on
November 6, 2026. CI uses synthetic fixtures and does not contact TennisRungs.
This is not a guarantee for every account, ladder format or future website change.

- The website does not provide a documented API contract for these endpoints.
  HTML changes can require parser updates.
- Website sessions are account-wide. “Read-only” is enforced by this client's
  tools and allowlisted read routes, not a vendor-issued read-only credential.
- HTTP 401/403, rate limits and schema drift stop without automatic retries or
  partial-success claims. Use infrequent reads and respect the site's rules.
- There is no background polling service, automatic renewal timer or write mode.

See [troubleshooting](docs/troubleshooting.md), [migration from the combined
prototype](docs/migration.md), [contributing](CONTRIBUTING.md) and
[security reporting](SECURITY.md).

## License

[MIT](LICENSE). TennisRungs names and trademarks belong to their respective owners.
