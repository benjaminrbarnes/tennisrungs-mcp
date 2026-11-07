# Changelog

## 0.2.0

Focused public-release preparation:

- Added the MIT license, package metadata, quick start, MCP configuration example,
  contributor guide, security policy and troubleshooting/migration documentation.
- Kept six read-only TennisRungs tools and local account login/session renewal.
- Removed iParcs, booking/workflow plans, match/score mutations, operation journals
  and the unused 1Password renewal experiment.
- Restricted the read transport to known read routes; mutation calls are unavailable.
- Optional password setup now requests only TennisRungs credentials and refuses to
  overwrite an existing password file. Session-only login needs no password file.
- Added Linux private-data paths while preserving the macOS session-file format.
- Added tests for removed actions, session isolation, secret-safe failures and
  first-login session storage; expanded CI to macOS and Linux.

See [migration](docs/migration.md) before changing an existing combined deployment.

## 0.1.0

Initial combined research prototype, including TennisRungs reads, guarded write
experiments, Atlanta iParcs adapters and offline workflow planning. Superseded by
the narrower read-only package; historical commits are not a supported write API.
