import os
import socket
import ssl
import subprocess
import threading
from types import SimpleNamespace
from uuid import UUID

import pytest

from packages.shared.auth.configuration import AuthConfigurationError, parse_auth_config
from packages.shared.auth.ldap_provider import DirectoryProvider, directory_server
from packages.shared.auth.providers import ProviderUnavailable


def config(ca="/run/secrets/ca.pem"):
    return parse_auth_config(
        {
            "version": 1,
            "origin": "https://storage.example.test",
            "local_enabled": True,
            "ldap": {
                "hostname": "ad.example.test",
                "base_dn": "DC=example,DC=test",
                "bind_dn": "CN=reader,DC=example,DC=test",
                "bind_password": "synthetic-secret",
                "ca_file": ca,
                "group_roles": {"CN=readers,DC=example,DC=test": ["viewer"]},
            },
        }
    ).ldap


class FakeConnection:
    def __init__(self, responses, bind=True):
        self.responses, self.bound, self.closed = responses, bind, False
        self.result = {"result": 0 if bind else 49}
        self.response = []
        self.filters = []

    def bind(self):
        return self.bound

    def search(self, base, search_filter, **kwargs):
        self.filters.append(search_filter)
        self.response = self.responses.pop(0)
        return True

    def unbind(self):
        self.closed = True


def entry(dn, attributes=None, raw=None):
    return {
        "type": "searchResEntry",
        "dn": dn,
        "attributes": attributes or {},
        "raw_attributes": raw or {},
    }


@pytest.fixture
def fake_tls(monkeypatch):
    # Protocol unit tests replace transport; real trust/hostname tests below do not.
    monkeypatch.setattr("packages.shared.auth.ldap_provider.directory_server", lambda config: None)


def test_nested_ad_membership_and_guid_identity(monkeypatch, fake_tls):
    guid = UUID("2c2a3e5a-88de-47af-ae43-3a160bade373")
    user = entry(
        "CN=alice,DC=example,DC=test",
        {"sAMAccountName": ["Alice"]},
        {"objectGUID": [guid.bytes_le]},
    )
    service = FakeConnection([[user], [entry("CN=readers,DC=example,DC=test")]])
    personal = FakeConnection([])
    created = []

    def connect(server, **kwargs):
        created.append(kwargs)
        return service if len(created) == 1 else personal

    monkeypatch.setattr("packages.shared.auth.ldap_provider.Connection", connect)
    subject = DirectoryProvider(config()).authenticate("ALICE", "synthetic-password")
    assert subject.subject == str(guid)
    assert subject.roles == frozenset({"viewer"})
    assert subject.username == "alice"
    assert "member:1.2.840.113556.1.4.1941:=" in service.filters[1]
    assert created[1]["user"] == "CN=alice,DC=example,DC=test"
    assert all(not item["auto_referrals"] and item["read_only"] for item in created)
    assert service.closed and personal.closed


@pytest.mark.parametrize(
    "case", ["ambiguous", "unmapped", "bad_guid", "referral", "wrong_password"]
)
def test_directory_negative_controls(monkeypatch, fake_tls, case):
    user = entry(
        "CN=alice,DC=example,DC=test", {"sAMAccountName": ["Alice"]}, {"objectGUID": [b"a" * 16]}
    )
    users = [user, user] if case == "ambiguous" else [user]
    if case == "bad_guid":
        user["raw_attributes"]["objectGUID"] = [b"short"]
    if case == "referral":
        users.append({"type": "searchResRef", "uri": "ldap://other.example.test"})
    groups = [] if case == "unmapped" else [entry("CN=readers,DC=example,DC=test")]
    service, personal = (
        FakeConnection([users, groups]),
        FakeConnection([], bind=case != "wrong_password"),
    )
    connections = iter([service, personal])
    monkeypatch.setattr(
        "packages.shared.auth.ldap_provider.Connection", lambda *args, **kwargs: next(connections)
    )
    assert DirectoryProvider(config()).authenticate("alice", "synthetic-password") is None
    assert service.closed


@pytest.mark.parametrize("failure", ["directory", "timeout"])
def test_outage_is_value_free_and_no_local_fallback(monkeypatch, fake_tls, failure):
    from ldap3.core.exceptions import LDAPSocketOpenError

    def fail(*args, **kwargs):
        error = TimeoutError if failure == "timeout" else LDAPSocketOpenError
        raise error("synthetic-secret and directory details")

    monkeypatch.setattr("packages.shared.auth.ldap_provider.Connection", fail)
    with pytest.raises(ProviderUnavailable, match="^AUTH_PROVIDER_UNAVAILABLE$"):
        DirectoryProvider(config()).authenticate("alice", "synthetic-password")


def test_account_filter_injection_is_escaped(monkeypatch, fake_tls):
    service = FakeConnection([[]])
    monkeypatch.setattr("packages.shared.auth.ldap_provider.Connection", lambda *a, **k: service)
    assert (
        DirectoryProvider(config()).authenticate("*)(sAMAccountName=*)", "synthetic-password")
        is None
    )
    assert "sAMAccountName=\\2a\\29\\28sAMAccountName=\\2a\\29" in service.filters[0]


@pytest.mark.parametrize(
    "username,password", [("alice\x00", "x"), ("alice", ""), ("alice", "\ud800")]
)
def test_invalid_input_never_opens_directory_connection(monkeypatch, fake_tls, username, password):
    monkeypatch.setattr(
        "packages.shared.auth.ldap_provider.Connection",
        lambda *a, **k: pytest.fail("connection opened"),
    )
    assert DirectoryProvider(config()).authenticate(username, password) is None


def test_missing_ca_is_configuration_failure_before_any_login(tmp_path):
    with pytest.raises(AuthConfigurationError, match="^AUTH_CONFIG_INVALID$"):
        DirectoryProvider(config(str(tmp_path / "absent-ca.pem")))


@pytest.mark.skipif(os.name != "posix", reason="Authoritative Linux TLS handshake")
@pytest.mark.parametrize("case", ["valid", "wrong_host", "untrusted"])
def test_real_tls_requires_trust_and_dns_identity(tmp_path, case):
    hostname = "other.example.test" if case == "wrong_host" else "ad.example.test"
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-subj",
            "/CN=" + hostname,
            "-addext",
            "subjectAltName=DNS:" + hostname,
        ],
        check=True,
        capture_output=True,
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(3)

    def serve():
        try:
            with listener.accept()[0] as peer, context.wrap_socket(peer, server_side=True):
                pass
        except (OSError, ssl.SSLError):
            pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    server = directory_server(config(str(cert)))
    if case == "untrusted":
        server.tls.ca_certs_file = None
    assert server.ssl and server.port == 636
    assert server.tls.validate == ssl.CERT_REQUIRED
    assert ssl.SSLContext(server.tls.version).minimum_version == ssl.TLSVersion.TLSv1_2
    connection = SimpleNamespace(
        socket=socket.create_connection(listener.getsockname(), timeout=3), server=server
    )
    try:
        if case == "valid":
            server.tls.wrap_socket(connection, do_handshake=True)
            assert connection.socket.version() == "TLSv1.2"
        else:
            from ldap3.core.exceptions import LDAPCertificateError

            with pytest.raises((ssl.SSLError, LDAPCertificateError)):
                server.tls.wrap_socket(connection, do_handshake=True)
    finally:
        connection.socket.close()
        thread.join(4)
        listener.close()
