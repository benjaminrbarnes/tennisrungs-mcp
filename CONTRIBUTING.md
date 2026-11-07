# Contributing

Small bug reports, parser fixes and documentation improvements are welcome.
This project is deliberately limited to TennisRungs login and read-only data.
Please discuss new integrations or side-effect features before implementing them.

## Development

Use a local checkout outside cloud-offloaded directories and Python 3.11+:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
.venv/bin/python -m build
```

Tests use synthetic HTML, temporary private files and mocked HTTP. Do not use
real credentials, browser cookies, account pages, screenshots, network recordings
or personal match records as fixtures. Do not run live login or account operations
from CI. Parser changes should cover both the new shape and failure behavior when
coverage or identity is uncertain.

Before opening a PR:

- Run the tests and package build.
- Keep CLI help and the six MCP schemas consistent with the documentation.
- Preserve score orientation, season-specific identifiers and coverage warnings.
- Add a changelog entry for user-visible behavior changes.
- Check the diff and package contents for local paths, credentials and private data.

Never include secrets in command arguments, exception text, logs or test snapshots.
Report sensitive security findings through [the security process](SECURITY.md).

Contributions are provided under this project's MIT license. Keep dependencies
and copied material compatible with that license and retain required attribution.
