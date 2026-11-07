"""Explicit interactive login and opt-in Keychain storage; no browser cookie access.

Normal login and stored-session reads have been exercised against the live site.
Credentials are submitted only by the local login command, never through MCP.
"""
import ctypes
import json
import sys
from urllib.parse import urljoin, urlparse

import httpx

from .models import AuthenticationRequired, UnsupportedContract
from .parsers import soup, is_login
from .transport import BASE, Transport

SERVICE = "tennisrungs-mcp.session.v1"
ACCOUNT = "local-user"


class Keychain:
    """macOS Security.framework; secret bytes never enter command-line arguments."""

    def __init__(self, *, service=SERVICE, account=ACCOUNT):
        self.service, self.account = service, account
        if sys.platform != "darwin":
            raise AuthenticationRequired("macOS Keychain is unavailable on this platform")
        self.lib = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        self.cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.lib.SecKeychainFindGenericPassword.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)]
        self.lib.SecKeychainAddGenericPassword.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        self.lib.SecKeychainItemModifyAttributesAndData.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
        self.lib.SecKeychainItemFreeContent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.cf.CFRelease.argtypes = [ctypes.c_void_p]

    def _find(self):
        length, data, item = ctypes.c_uint32(), ctypes.c_void_p(), ctypes.c_void_p()
        service, account = self.service.encode(), self.account.encode()
        status = self.lib.SecKeychainFindGenericPassword(None, len(service), service, len(account), account, ctypes.byref(length), ctypes.byref(data), ctypes.byref(item))
        return status, length, data, item

    def read(self):
        status, length, data, item = self._find()
        if status:
            raise AuthenticationRequired("Approved Keychain session unavailable")
        try:
            return json.loads(ctypes.string_at(data, length.value))
        except (ValueError, UnicodeError):
            raise AuthenticationRequired("Invalid Keychain session bundle") from None
        finally:
            self.lib.SecKeychainItemFreeContent(None, data)
            if item.value:
                self.cf.CFRelease(item)

    def store(self, cookies):
        # Called ONLY after explicit --approve-session-storage and successful login.
        secret = json.dumps(cookies).encode()
        status, _, data, item = self._find()
        if status == 0:
            self.lib.SecKeychainItemFreeContent(None, data)
            result = self.lib.SecKeychainItemModifyAttributesAndData(item, None, len(secret), secret)
            if item.value:
                self.cf.CFRelease(item)
        elif status == -25300:  # errSecItemNotFound
            service, account = self.service.encode(), self.account.encode()
            result = self.lib.SecKeychainAddGenericPassword(None, len(service), service, len(account), account, len(secret), secret, None)
        else:
            raise AuthenticationRequired("Keychain access refused")
        if result:
            raise AuthenticationRequired("Keychain storage failed")


def interactive_login(username, password):
    """One normal form submission. Returns session only after dashboard verification.

    No CAPTCHA/security challenge bypass, alternate account routes, or guesses.
    Actual token fields are taken from the fetched form. A bearer API is not assumed.
    """
    transport = Transport()
    try:
        r = transport.client.get(BASE + "/Account/Login")
        if r.status_code != 200:
            raise AuthenticationRequired(f"Login page returned HTTP {r.status_code}; stop for supported renewal")
        s = soup(r.text)
        if s.select_one('[data-sitekey], iframe[src*="recaptcha"], input[name="g-recaptcha-response"]'):
            raise AuthenticationRequired("Login requires a security challenge; complete it through the website")
        password_input = s.select_one('input[type="password"][name]')
        form = password_input.find_parent("form") if password_input else None
        if not form or form.get("method", "get").lower() != "post":
            raise UnsupportedContract("Normal password-login form not established")
        action = urljoin(BASE + "/Account/Login", form.get("action", ""))
        if urlparse(action).scheme != "https" or urlparse(action).netloc != "app.tennisrungs.com" or urlparse(action).path != "/Account/Login":
            raise UnsupportedContract("Unexpected login destination; no credential transmission")
        user = form.find("input", attrs={"name": lambda n: n and n.lower() in ["username", "user_name"]})
        if not user:
            raise UnsupportedContract("Username field not established")
        fields = [(e["name"], e.get("value", "")) for e in form.select('input[type="hidden"][name]')]
        fields += [(user["name"], username), (password_input["name"], password)]
        result = transport.client.post(action, data=dict(fields))
        if result.status_code not in (200, 302, 303):
            raise AuthenticationRequired("Normal login failed; no alternate attempt made")
        if result.status_code == 200 and is_login(result.text):
            raise AuthenticationRequired("Login rejected or additional verification required")
        # Requests only same-site /Player; do not follow unknown credential redirects.
        html = transport.get("/Player", private=True)
        if not soup(html).select_one("#tabs-1"):
            raise AuthenticationRequired("Authenticated dashboard not verified")
        cookies = transport.cookie_bundle()
        if not cookies:
            raise AuthenticationRequired("Cookie session not established; different auth mechanism requires research")
        return cookies
    except httpx.RequestError:
        raise AuthenticationRequired("Login transport failed; details suppressed") from None
    finally:
        transport.close()
