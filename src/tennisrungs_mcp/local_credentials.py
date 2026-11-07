"""Optional private TennisRungs password file; never parsed by the MCP server."""
import fcntl
import getpass
import json
import os
import stat
import sys
import tempfile
import warnings
from dataclasses import dataclass, field

from .models import AuthenticationRequired
from .paths import data_directory

FIELDS = {"tennisrungs": ("TENNISRUNGS_USERNAME", "TENNISRUNGS_PASSWORD")}
KEYS = {k for pair in FIELDS.values() for k in pair}
MAX_FILE = 131072


def credential_path():
    return data_directory() / "credentials.env"


@dataclass(frozen=True)
class Credentials:
    _values: dict = field(repr=False)

    def pair(self, provider):
        if provider not in FIELDS:
            raise AuthenticationRequired("Local credential provider not allowlisted")
        return tuple(self._values[k] for k in FIELDS[provider])


def _validate(values):
    if set(values) != KEYS:
        raise AuthenticationRequired("Exactly the TennisRungs username/password pair is required")
    for k, v in values.items():
        if not isinstance(v, str) or not v or len(v.encode()) > (8192 if k.endswith("PASSWORD") else 512):
            raise AuthenticationRequired("Private credential value missing or invalid; values suppressed")
    return Credentials(dict(values))


def _private_directory(path):
    try:
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise AuthenticationRequired("Credential directory must be private, owned and mode 0700")
    except OSError:
        raise AuthenticationRequired("Private credential directory unavailable; run the approved bootstrap") from None


def load():
    path = credential_path()
    _private_directory(path.parent)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > MAX_FILE:
                raise AuthenticationRequired("Credential file must be private, owned, regular and mode 0600")
            content = f.read(MAX_FILE + 1).decode("utf-8")
        values = {}
        for line in content.splitlines():
            key, sep, value = line.partition("=")
            if not sep or key not in KEYS or key in values:
                raise AuthenticationRequired("Private credential file schema invalid; values suppressed")
            # JSON string decoding only: '$', backticks and shell syntax are literal.
            values[key] = json.loads(value)
        return _validate(values)
    except (OSError, ValueError, UnicodeError):
        raise AuthenticationRequired("Private credential file unavailable/malformed; values suppressed") from None


def bootstrap(*, approve_plaintext_storage):
    if approve_plaintext_storage is not True:
        raise AuthenticationRequired("Explicit private plaintext storage approval required")
    if not sys.stdin.isatty():
        raise AuthenticationRequired("One-time credential entry requires a local hidden TTY; redirected input refused")
    path = credential_path()
    if path.exists() or path.is_symlink():
        raise AuthenticationRequired("Credential file already exists; it was not overwritten. Back it up and remove it explicitly before setup.")
    values = {}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            for provider in FIELDS:
                for key in FIELDS[provider]:
                    label = "password" if key.endswith("PASSWORD") else "username"
                    values[key] = getpass.getpass(f"{provider} {label} (hidden): ")
    except (getpass.GetPassWarning, EOFError):
        raise AuthenticationRequired("Secure non-echo credential prompt unavailable") from None
    credentials = _validate(values)
    path = credential_path()
    temp = None
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _private_directory(path.parent)
        fd, temp = tempfile.mkstemp(prefix=".credentials-", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            os.fchmod(f.fileno(), 0o600)
            for provider in FIELDS:
                for key in FIELDS[provider]:
                    f.write(key + "=" + json.dumps(credentials._values[key], ensure_ascii=False) + "\n")
            f.flush(); os.fsync(f.fileno())
        # Atomic creation must not clobber a file created during the prompts.
        os.link(temp, path, follow_symlinks=False)
        os.unlink(temp)
        temp = None
    except OSError:
        raise AuthenticationRequired("Private credential file installation failed; values suppressed") from None
    finally:
        if temp is not None:
            try: os.unlink(temp)
            except OSError: pass
    return {"credential_file_configured": True, "provider_count": 1,
            "directory_mode": "0700", "file_mode": "0600", "login_attempted": False}


def renew(provider, *, store_session=False):
    if provider not in FIELDS or type(store_session) is not bool:
        raise AuthenticationRequired("Local provider/storage selection invalid")
    credentials = load()  # No fallback to prompts or another credential source.
    path = credential_path().parent / (".renewal-" + provider + ".lock")
    try:
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "r+b") as lock:
            info = os.fstat(lock.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise AuthenticationRequired("Private renewal lock invalid")
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise AuthenticationRequired("Local renewal already in progress; no retry") from None
            user, password = credentials.pair(provider)
            # Existing normal login functions; no op or Keychain call is used.
            from .file_sessions import FileSessionStore
            try:
                from .auth import interactive_login
                cookies = interactive_login(user, password)
                if store_session:
                    FileSessionStore(provider).store(cookies)
                return {"provider": provider, "status": "OK", "authenticated_session_verified": True,
                        "session_stored": store_session}
            except Exception:
                # Never forward library exceptions or server text containing private data.
                return {"provider": provider, "status": "STOP", "reason": "LOGIN_FAILED"}

    except OSError:
        raise AuthenticationRequired("Local renewal lock unavailable; no login/retry") from None
