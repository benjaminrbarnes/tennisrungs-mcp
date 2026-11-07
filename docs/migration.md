# Migrating from the combined 0.1 prototype

Version 0.2 focuses on TennisRungs login and reads. The following prototype
features have been removed from this package:

- Atlanta iParcs availability, login, identity, cart and preparation code.
- Proposal creation/acceptance/withdrawal and score submission.
- Offline booking/workflow planners, operation journals and `--enable-writes`.
- The unconfigured 1Password service-account renewal experiment.

Use a separate court-availability connector for public court data. No replacement
iParcs repository or new account login is required by this package.

## Existing clients

Keep the six TennisRungs read tools in your client's allowlist. Remove retired
`iparcs_*`, `workflow_*` and write-tool entries, then reload the MCP connection.
The six remaining tool names and JSON result fields are unchanged.

Stored TennisRungs session-file schema and the macOS storage location remain
compatible. Existing macOS Keychain sessions are still opt-in. No command scans,
migrates, deletes or rewrites another integration's credentials or session files.

For source installs, create a new virtual environment or reinstall the package
with its dependencies. Do not point a running deployment at a changing development
worktree. Verify discovery and a bounded authenticated read before switching an
agent's command path. Preserve the existing installation until that succeeds.

## Optional password files

The old prototype's four-key password file is no longer accepted. It is never
automatically modified. Interactive session-only login does not use that file
and needs no password-file migration.

If you need unattended renewal, first retain a private backup of the old file and
explicitly move it out of the fixed credential path. Then use the new two-prompt
bootstrap. Do not discard a shared legacy file while another installed integration
still relies on it. Never commit either file or include it in a bug report.
