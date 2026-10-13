import os
from pathlib import Path

from .auth import Keychain
from .client import Client
from .journal import Journal
from .transport import Transport


def runtime(*, use_keychain=False, writes=False, state_dir=None):
    # Read-only public runs do not create state or query Keychain.
    cookies = Keychain().read() if use_keychain else None
    journal = None
    if writes:
        folder = Path(state_dir) if state_dir else Path.home() / "Library/Application Support/tennisrungs-mcp"
        journal = Journal(folder / "operations.sqlite3")
    return Client(Transport(cookies), journal, writes_enabled=writes)
