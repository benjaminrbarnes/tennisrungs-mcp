"""Synthetic temporary state only; real credentials, Keychain and network are denied."""
import asyncio
import json
import socket

import httpx
import pytest

from tennisrungs_mcp import auth, local_credentials as lc, file_sessions as fs
from tennisrungs_mcp.models import AuthenticationRequired
from tennisrungs_mcp.runtime import runtime
from tennisrungs_mcp.server import make_server
from tennisrungs_mcp.client import Client


@pytest.fixture(autouse=True)
def private_offline(monkeypatch, tmp_path):
    folder = tmp_path / "private"
    folder.mkdir(mode=0o700)
    path = folder / "credentials.env"
    monkeypatch.setattr(lc, "credential_path", lambda: path)
    monkeypatch.setattr(fs, "credential_path", lambda: path)
    def denied(*args, **kwargs):
        pytest.fail("unexpected live operation or Keychain")
    monkeypatch.setattr(auth, "Keychain", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    return path


def values():
    return {"TENNISRUNGS_USERNAME": "synthetic-user",
            "TENNISRUNGS_PASSWORD": 'synthetic-password-$()-`literal`-\\"'}


def populate(path):
    path.write_text("".join(k + "=" + json.dumps(v) + "\n" for k, v in values().items()))
    path.chmod(0o600)


def cookie(value="synthetic-site-cookie"):
    return [{"name": "synthetic", "value": value, "domain": ".tennisrungs.com", "path": "/", "expires": None}]


def test_password_file_is_literal_not_shell_or_environment(private_offline, monkeypatch):
    populate(private_offline)
    monkeypatch.setenv("TENNISRUNGS_PASSWORD", "untrusted-environment")
    creds = lc.load()
    assert creds.pair("tennisrungs") == tuple(values().values())
    assert "synthetic" not in repr(creds)
    with pytest.raises(AuthenticationRequired):
        creds.pair("other")


@pytest.mark.parametrize("content", [
    'export TENNISRUNGS_USERNAME=secret\n', 'UNKNOWN="secret"\n',
    'TENNISRUNGS_USERNAME=$(evil)\n',
    'TENNISRUNGS_USERNAME="x"\nTENNISRUNGS_USERNAME="y"\n',
    'TENNISRUNGS_USERNAME="x"\n',
])
def test_malformed_and_incomplete_password_files_fail_closed(private_offline, content):
    private_offline.write_text(content)
    private_offline.chmod(0o600)
    with pytest.raises(AuthenticationRequired) as exc:
        lc.load()
    assert "secret" not in str(exc.value) and "evil" not in str(exc.value)


def test_permissions_and_symlinks_are_refused(private_offline):
    populate(private_offline)
    private_offline.chmod(0o644)
    with pytest.raises(AuthenticationRequired): lc.load()
    private_offline.chmod(0o600)
    private_offline.parent.chmod(0o755)
    with pytest.raises(AuthenticationRequired): lc.load()
    private_offline.parent.chmod(0o700)
    other = private_offline.with_name("other")
    private_offline.rename(other)
    private_offline.symlink_to(other)
    with pytest.raises(AuthenticationRequired): lc.load()


def test_bootstrap_only_prompts_for_tennisrungs_and_never_logs_in(private_offline, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    prompts = []
    inputs = iter(values().values())
    def prompt(label):
        prompts.append(label)
        return next(inputs)
    monkeypatch.setattr(lc.getpass, "getpass", prompt)
    result = lc.bootstrap(approve_plaintext_storage=True)
    assert len(prompts) == 2 and all("tennisrungs" in p for p in prompts)
    assert result["provider_count"] == 1 and not result["login_attempted"]
    assert private_offline.stat().st_mode & 0o777 == 0o600
    assert lc.load().pair("tennisrungs") == tuple(values().values())
    assert "synthetic" not in capsys.readouterr().out + json.dumps(result)


def test_bootstrap_refuses_existing_file_without_prompt_or_overwrite(private_offline, monkeypatch):
    private_offline.write_text("existing-state-not-to-be-replaced")
    before = private_offline.read_bytes()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(lc.getpass, "getpass", lambda *a: pytest.fail("must not prompt"))
    with pytest.raises(AuthenticationRequired, match="not overwritten"):
        lc.bootstrap(approve_plaintext_storage=True)
    assert private_offline.read_bytes() == before


def test_bootstrap_requires_explicit_consent_and_hidden_tty(monkeypatch):
    monkeypatch.setattr(lc.getpass, "getpass", lambda *a: pytest.fail("must not prompt"))
    with pytest.raises(AuthenticationRequired): lc.bootstrap(approve_plaintext_storage=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(AuthenticationRequired): lc.bootstrap(approve_plaintext_storage=True)


def test_renewal_performs_one_login_and_stores_only_session(private_offline, monkeypatch):
    populate(private_offline)
    calls = []
    def login(user, password):
        calls.append((user, password))
        return cookie()
    monkeypatch.setattr(auth, "interactive_login", login)
    result = lc.renew("tennisrungs", store_session=True)
    assert calls == [tuple(values().values())]
    assert result["authenticated_session_verified"] and result["session_stored"]
    assert fs.FileSessionStore("tennisrungs").read() == cookie()
    assert "PASSWORD" not in fs.session_path("tennisrungs").read_text()
    assert "synthetic" not in json.dumps(result)


def test_failed_login_does_not_retry_store_or_reveal_exception(private_offline, monkeypatch):
    populate(private_offline)
    calls = []
    def fail(*args):
        calls.append(1)
        raise RuntimeError("synthetic-secret-server-text")
    monkeypatch.setattr(auth, "interactive_login", fail)
    result = lc.renew("tennisrungs", store_session=True)
    assert calls == [1] and result["status"] == "STOP"
    assert "synthetic" not in json.dumps(result)
    assert not fs.session_path("tennisrungs").exists()


def test_missing_password_file_has_no_prompt_or_fallback(monkeypatch):
    monkeypatch.setattr(lc.getpass, "getpass", lambda *a: pytest.fail("no fallback"))
    with pytest.raises(AuthenticationRequired): lc.renew("tennisrungs", store_session=True)


def test_interactive_session_storage_needs_no_password_file(private_offline):
    private_offline.parent.rmdir()
    fs.FileSessionStore("tennisrungs").store(cookie())
    assert not private_offline.exists()
    assert private_offline.parent.stat().st_mode & 0o777 == 0o700
    assert fs.session_path("tennisrungs").stat().st_mode & 0o777 == 0o600


def test_session_provider_origin_modes_and_extra_fields(private_offline):
    with pytest.raises(AuthenticationRequired): fs.FileSessionStore("other")
    bad = cookie()
    bad[0]["domain"] = ".example.invalid"
    with pytest.raises(AuthenticationRequired): fs.FileSessionStore("tennisrungs").store(bad)
    bad = cookie()
    bad[0]["password"] = "synthetic-secret"
    with pytest.raises(AuthenticationRequired): fs.FileSessionStore("tennisrungs").store(bad)
    store = fs.FileSessionStore("tennisrungs")
    store.store(cookie())
    store.path.chmod(0o644)
    with pytest.raises(AuthenticationRequired): store.read()
    store.path.chmod(0o600)
    raw = json.loads(store.path.read_text())
    raw["origin"] = "https://example.invalid"
    store.path.write_text(json.dumps(raw))
    with pytest.raises(AuthenticationRequired): store.read()


def test_file_runtime_initializes_without_reading_credentials():
    client = runtime(use_file_session=True)
    try:
        with pytest.raises(AuthenticationRequired): client.list_current_ladders()
    finally:
        client.transport.close()


def test_running_transport_observes_replaced_session():
    store = fs.FileSessionStore("tennisrungs")
    store.store(cookie("synthetic-one"))
    seen = []
    transport = fs.FileTransport()
    transport.client.close()
    def handler(request):
        seen.append(request.headers.get("cookie", ""))
        return httpx.Response(200, text="<fieldset>safe</fieldset>")
    transport.client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        transport.get("/Player", private=True)
        store.store(cookie("synthetic-two"))
        transport.get("/Player", private=True)
        assert "synthetic-one" in seen[0] and "synthetic-two" in seen[1]
    finally:
        transport.close()


def test_mcp_discovery_never_reads_passwords_or_registers_writes(monkeypatch):
    monkeypatch.setattr(lc, "load", lambda: pytest.fail("must not read password file"))
    async def check():
        names = {tool.name for tool in await make_server(Client(None)).list_tools()}
        assert len(names) == 6
        assert not names.intersection({"propose_match", "accept_proposal", "report_score", "withdraw_proposal"})
    asyncio.run(check())


def test_bootstrap_does_not_clobber_a_file_created_during_input(private_offline, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    inputs = iter(values().values())
    def prompt(label):
        private_offline.write_text("intervening-state")
        return next(inputs)
    monkeypatch.setattr(lc.getpass, "getpass", prompt)
    with pytest.raises(AuthenticationRequired):
        lc.bootstrap(approve_plaintext_storage=True)
    assert private_offline.read_text() == "intervening-state"
    assert not list(private_offline.parent.glob('.credentials-*'))
