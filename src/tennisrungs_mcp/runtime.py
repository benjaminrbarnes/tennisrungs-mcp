"""Construct a reader without logging in or creating persistent state."""
from .auth import Keychain
from .client import Client
from .transport import Transport
from .models import AuthenticationRequired


def runtime(*, use_keychain=False, use_file_session=False):
    if use_keychain and use_file_session:
        raise AuthenticationRequired("Choose exactly one session backend")
    if use_file_session:
        from .file_sessions import FileTransport
        transport = FileTransport()
    else:
        cookies = Keychain().read() if use_keychain else None
        transport = Transport(cookies)
    return Client(transport)
