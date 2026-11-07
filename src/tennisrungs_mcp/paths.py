"""Fixed per-OS storage outside the checkout; ignore a child HOME override."""
import os
import pwd
import sys
from pathlib import Path


def data_directory():
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    if sys.platform == "darwin":
        return home / "Library/Application Support/tennisrungs-mcp"
    return home / ".local/share/tennisrungs-mcp"
