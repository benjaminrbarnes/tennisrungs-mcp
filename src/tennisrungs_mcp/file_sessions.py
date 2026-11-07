"""Fixed private session files. No passwords, Keychain, arbitrary paths or exports."""
import json
import os
import stat
import tempfile
import hashlib
from datetime import datetime, timezone

from .models import AuthenticationRequired
from .local_credentials import credential_path, _private_directory
from .transport import Transport, validate_cookies

ORIGINS = {"tennisrungs": "https://app.tennisrungs.com"}


def session_path(provider):
    if provider not in ORIGINS:
        raise AuthenticationRequired("Session provider not allowlisted")
    return credential_path().parent / (provider + "-session.json")


def validate_session(provider, raw):
    if provider != "tennisrungs":
        raise AuthenticationRequired("Session provider not allowlisted")
    return validate_cookies(raw)


class FileSessionStore:
    def __init__(self, provider):
        self.provider = provider
        self.path = session_path(provider)

    def read(self):
        _private_directory(self.path.parent)
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as f:
                info = os.fstat(f.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 262144:
                    raise AuthenticationRequired("Session file must be private, owned, regular and mode 0600")
                raw = json.loads(f.read(262145))
            if not isinstance(raw, dict) or set(raw) != {"schema", "provider", "origin", "issued_at", "session"} or type(raw["schema"]) is not int or raw["schema"] != 1 or raw["provider"] != self.provider or raw["origin"] != ORIGINS[self.provider]:
                raise AuthenticationRequired("Session file binding invalid; values suppressed")
            return validate_session(self.provider, raw["session"])
        except (OSError, ValueError, UnicodeError):
            raise AuthenticationRequired("Private site session unavailable; use approved local-file renewal") from None

    def store(self, session):
        validate_session(self.provider, session)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _private_directory(self.path.parent)
        raw = {"schema": 1, "provider": self.provider, "origin": ORIGINS[self.provider],
               "issued_at": datetime.now(timezone.utc).isoformat(), "session": session}
        temp = None
        try:
            fd, temp = tempfile.mkstemp(prefix=".session-", dir=self.path.parent)
            with os.fdopen(fd, "w") as f:
                os.fchmod(f.fileno(), 0o600)
                json.dump(raw, f)
                f.flush(); os.fsync(f.fileno())
            os.replace(temp, self.path)
            temp = None
        except OSError:
            raise AuthenticationRequired("Private session storage failed; values suppressed") from None
        finally:
            if temp is not None:
                try: os.unlink(temp)
                except OSError: pass


class FileTransport(Transport):
    """Lazy session-only loading lets MCP initialize and observe later renewals."""
    def __init__(self):
        super().__init__()
        self._file_digest = None

    def request(self, method, path, *, private=False, data=None, params=None):
        if private:
            cookies = FileSessionStore("tennisrungs").read()
            digest = hashlib.sha256(json.dumps(cookies, sort_keys=True).encode()).hexdigest()
            if digest != self._file_digest:
                fresh = Transport(cookies)
                try:
                    self.client.cookies.clear()
                    for cookie in fresh.client.cookies.jar:
                        self.client.cookies.jar.set_cookie(cookie)
                finally:
                    fresh.close()
                self._file_digest = digest
        return super().request(method, path, private=private, data=data, params=params)
