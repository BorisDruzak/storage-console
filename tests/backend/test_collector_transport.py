import base64
import json
import os
import shutil
import ssl
import subprocess
import sys
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

from collectors.common import transport as transport_module
from collectors.common.outbox import Claim
from collectors.common.transport import Transport, TransportError
from packages.contracts.common import BatchEnvelope
from packages.contracts.heartbeat import HeartbeatRecord


def prepared_claim(collector=None):
    collector = collector or uuid4()
    now = datetime.now(UTC)
    batch = BatchEnvelope[HeartbeatRecord](
        collector_id=collector,
        batch_id=str(uuid4()),
        schema_version=1,
        sent_at=now,
        first_event_at=now,
        last_event_at=now,
        record_count=1,
        records=[HeartbeatRecord(occurred_at=now, version="synthetic")],
    )
    return collector, Claim(
        batch.batch_id, "heartbeat", batch.model_dump_json().encode(), str(uuid4()), 0
    )


@pytest.mark.parametrize("timeout", [0, -1, 16, True, float("inf"), float("nan"), "15"])
def test_invalid_attempt_deadline_rejected(authorities, timeout):
    with pytest.raises(TransportError, match="^INVALID_CONFIG$"):
        Transport(
            "https://localhost",
            authorities[0] / "ca.pem",
            "a" * 43,
            timeout=timeout,
            collector_id=uuid4(),
        )


@pytest.mark.parametrize(
    "domain",
    [
        "heartbeat",
        "inventory",
        "changes",
        "telemetry",
        "events",
        "acl",
        "recovery",
        "hygiene",
        "diagnostics",
    ],
)
def test_fixed_domain_route_preserves_claim_bytes(authorities, servers, domain):
    server, origin = servers()
    collector, claim = prepared_claim()
    claim = replace(claim, domain=domain)
    assert (
        Transport(origin, authorities[0] / "ca.pem", "a" * 43, collector_id=collector)
        .send(claim)
        .kind
        == "accepted"
    )
    assert server.requests[0]["path"] == "/api/v1/ingest/" + domain
    assert server.requests[0]["body"] == claim.body


@pytest.mark.parametrize("invalid", ["domain", "collector", "batch", "body"])
def test_invalid_claim_rejected_before_starting_network_worker(authorities, monkeypatch, invalid):
    collector, claim = prepared_claim()
    if invalid == "domain":
        claim = replace(claim, domain="../other")
    elif invalid == "collector":
        collector = uuid4()
    elif invalid == "batch":
        claim = replace(claim, batch_id=str(uuid4()))
    else:
        claim = replace(claim, body=b"not json")
    transport = Transport(
        "https://localhost", authorities[0] / "ca.pem", "a" * 43, collector_id=collector
    )
    process = Mock()
    monkeypatch.setattr(transport_module.subprocess, "Popen", process)
    assert transport.send(claim).code == "HTTP_REJECTED"
    process.assert_not_called()


def test_hanging_worker_is_killed_and_reaped_within_whole_deadline(
    authorities, monkeypatch, tmp_path
):
    script = tmp_path / "hang.py"
    script.write_text("import time\ntime.sleep(30)\n")
    monkeypatch.setattr(transport_module, "_WORKER_PATH", script)
    real_popen = subprocess.Popen
    processes = []

    def capture(args, **kwargs):
        assert len(args) == 3 and args[1] == "-I"
        assert kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["stdin"] == subprocess.PIPE
        process = real_popen(args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(transport_module.subprocess, "Popen", capture)
    collector, claim = prepared_claim()
    transport = Transport(
        "https://localhost",
        authorities[0] / "ca.pem",
        "a" * 43,
        timeout=0.3,
        collector_id=collector,
    )
    started = time.monotonic()
    assert transport.send(claim).code == "TIMEOUT"
    assert time.monotonic() - started < 2.5
    assert len(processes) == 1 and processes[0].poll() is not None


def test_isolated_worker_starts_and_returns_only_fixed_fields_for_invalid_input():
    result = subprocess.run(
        [sys.executable, "-I", str(transport_module._WORKER_PATH)],
        input=b"{}",
        capture_output=True,
        timeout=3,
        check=True,
    )
    assert not result.stderr
    assert json.loads(result.stdout) == {
        "kind": "retry",
        "code": "NETWORK",
        "duplicate": None,
        "retry_after": None,
    }


def test_worker_own_deadline_exits_without_parent_cancellation(authorities, servers):
    server, origin = servers()
    server.reply = {"drip": True}
    _, claim = prepared_claim()
    config = {
        "url": origin + "/api/v1/ingest/heartbeat",
        "ca_data": (authorities[0] / "ca.pem").read_text(),
        "token": "a" * 43,
        "timeout": 3,
        "body": base64.b64encode(claim.body).decode("ascii"),
    }
    result = subprocess.run(
        [sys.executable, "-I", str(transport_module._WORKER_PATH)],
        input=json.dumps(config).encode(),
        capture_output=True,
        timeout=6,
    )
    assert result.returncode == 70 and not result.stdout and not result.stderr
    assert len(server.requests) == 1


@pytest.fixture(scope="module")
def authorities(tmp_path_factory):
    executable = shutil.which("openssl")
    if not executable and os.name == "nt":
        candidate = Path("C:/Program Files/Git/usr/bin/openssl.exe")
        executable = str(candidate) if candidate.is_file() else None
    if not executable:
        pytest.skip("Native TLS acceptance requires OpenSSL")
    result = []
    for hostname in ["localhost", "wrong.example.test"]:
        root = tmp_path_factory.mktemp("collector-tls")
        root.chmod(0o700)
        commands = [
            [
                "req",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-x509",
                "-days",
                "2",
                "-subj",
                "/CN=Synthetic Collector CA",
                "-addext",
                "basicConstraints=critical,CA:TRUE",
                "-addext",
                "keyUsage=critical,keyCertSign,cRLSign",
                "-addext",
                "subjectKeyIdentifier=hash",
                "-keyout",
                str(root / "ca.key"),
                "-out",
                str(root / "ca.pem"),
            ],
            [
                "req",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-subj",
                "/CN=" + hostname,
                "-keyout",
                str(root / "key.pem"),
                "-out",
                str(root / "leaf.csr"),
            ],
        ]
        (root / "extensions").write_text(
            "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n"
            "extendedKeyUsage=serverAuth\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n"
            "subjectAltName=DNS:" + hostname + "\n",
            encoding="ascii",
        )
        commands.append(
            [
                "x509",
                "-req",
                "-in",
                str(root / "leaf.csr"),
                "-CA",
                str(root / "ca.pem"),
                "-CAkey",
                str(root / "ca.key"),
                "-CAcreateserial",
                "-days",
                "2",
                "-extfile",
                str(root / "extensions"),
                "-out",
                str(root / "leaf.pem"),
            ]
        )
        for command in commands:
            subprocess.run(
                [executable, *command],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=20,
            )
        for filename in ["ca.key", "key.pem"]:
            (root / filename).chmod(0o600)
        result.append(root)
    return result


class Recorder(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        self.server.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": self.rfile.read(int(self.headers.get("Content-Length", "0"))),
            }
        )
        state = self.server.reply
        self.send_response(state.get("status", 202))
        self.send_header("Content-Type", "application/json")
        for name, value in state.get("headers", {}).items():
            self.send_header(name, value)
        body = state.get("body", b'{"accepted":true,"duplicate":false}')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            if state.get("drip"):
                for byte in body:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(0.15)
            else:
                self.wfile.write(body)
        except (OSError, ssl.SSLError):
            pass

    def do_CONNECT(self):
        self.server.requests.append({"path": self.path})
        self.send_response(502)
        self.end_headers()


@pytest.fixture
def servers(authorities):
    instances = []

    def start(authority=0, *, tls=True):
        server = HTTPServer(("127.0.0.1", 0), Recorder)
        server.requests = []
        server.reply = {}
        if tls:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(
                authorities[authority] / "leaf.pem", authorities[authority] / "key.pem"
            )
            server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        instances.append((server, thread))
        return server, ("https" if tls else "http") + "://localhost:" + str(server.server_port)

    yield start
    for server, thread in instances:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_real_https_transmits_exact_bytes_and_keeps_credentials_out_of_repr(authorities, servers):
    server, origin = servers()
    collector, claim = prepared_claim()
    transport = Transport(origin, authorities[0] / "ca.pem", "a" * 43, collector_id=collector)
    outcome = transport.send(claim)
    assert outcome.kind == "accepted" and outcome.duplicate is False
    assert server.requests == [
        {
            "path": "/api/v1/ingest/heartbeat",
            "authorization": "Bearer " + "a" * 43,
            "body": claim.body,
        }
    ]
    assert "a" * 43 not in repr(transport) + repr(outcome)


@pytest.mark.parametrize("failure", ["untrusted", "hostname"])
def test_strict_tls_rejects_untrusted_ca_and_wrong_hostname(authorities, servers, failure):
    server, origin = servers(1 if failure == "hostname" else 0)
    collector, claim = prepared_claim()
    ca = authorities[1] / "ca.pem"
    outcome = Transport(origin, ca, "a" * 43, collector_id=collector).send(claim)
    assert outcome.kind == "retry" and outcome.code == "TLS"
    assert not server.requests


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_never_reaches_another_origin(authorities, servers, status):
    target, destination = servers(tls=False)
    server, origin = servers()
    server.reply = {"status": status, "headers": {"Location": destination + "/target"}}
    collector, claim = prepared_claim()
    outcome = Transport(origin, authorities[0] / "ca.pem", "a" * 43, collector_id=collector).send(
        claim
    )
    assert outcome.kind == "quarantined" and outcome.code == "REDIRECT"
    assert not target.requests and len(server.requests) == 1


def test_ambient_proxy_is_ignored(authorities, servers, monkeypatch):
    proxy, destination = servers(tls=False)
    server, origin = servers()
    monkeypatch.setenv("HTTPS_PROXY", destination)
    monkeypatch.setenv("https_proxy", destination)
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    collector, claim = prepared_claim()
    outcome = Transport(origin, authorities[0] / "ca.pem", "a" * 43, collector_id=collector).send(
        claim
    )
    assert outcome.kind == "accepted" and len(server.requests) == 1 and not proxy.requests


@pytest.mark.parametrize(
    "body",
    [
        b'{"accepted":false,"duplicate":false}',
        b'{"accepted":true,"duplicate":1}',
        b'{"duplicate":false}',
        b'{"accepted":true,"duplicate":false,"extra":1}',
        b'{"accepted":true,"accepted":false,"duplicate":false}',
        b"not json",
        b"x" * 32769,
    ],
    ids=["rejected", "nonboolean", "missing", "extra", "duplicate-key", "not-json", "oversized"],
)
def test_malformed_or_oversized_receipt_never_confirms_delivery(authorities, servers, body):
    server, origin = servers()
    server.reply = {"body": body}
    collector, claim = prepared_claim()
    outcome = Transport(origin, authorities[0] / "ca.pem", "a" * 43, collector_id=collector).send(
        claim
    )
    assert outcome.kind == "retry" and outcome.code == "INVALID_RECEIPT"


def test_slow_response_cannot_extend_whole_attempt_deadline(authorities, servers):
    server, origin = servers()
    server.reply = {"drip": True}
    collector, claim = prepared_claim()
    transport = Transport(
        origin, authorities[0] / "ca.pem", "a" * 43, timeout=0.7, collector_id=collector
    )
    started = time.monotonic()
    outcome = transport.send(claim)
    assert outcome.kind == "retry" and outcome.code == "TIMEOUT"
    assert time.monotonic() - started < 2.5


def test_public_ca_snapshot_does_not_reload_replaced_file(authorities, servers, tmp_path):
    _, origin = servers()
    ca = tmp_path / "ca.pem"
    ca.write_bytes((authorities[0] / "ca.pem").read_bytes())
    collector, claim = prepared_claim()
    transport = Transport(origin, ca, "a" * 43, collector_id=collector)
    ca.write_text("not a certificate", encoding="ascii")
    assert transport.send(claim).kind == "accepted"


@pytest.mark.parametrize(
    "status,kind,code",
    [
        (400, "quarantined", "HTTP_REJECTED"),
        (404, "quarantined", "HTTP_REJECTED"),
        (409, "quarantined", "HTTP_REJECTED"),
        (413, "quarantined", "HTTP_REJECTED"),
        (415, "quarantined", "HTTP_REJECTED"),
        (422, "quarantined", "HTTP_REJECTED"),
        (401, "suspended", "AUTH_REQUIRED"),
        (403, "suspended", "AUTH_REQUIRED"),
        (429, "retry", "RATE_LIMITED"),
        (503, "retry", "SERVER_ERROR"),
        (204, "retry", "INVALID_RECEIPT"),
        (408, "retry", "TIMEOUT"),
    ],
)
def test_http_classification_never_echoes_response_body(authorities, servers, status, kind, code):
    server, origin = servers()
    server.reply = {"status": status, "body": b"synthetic private response"}
    collector, claim = prepared_claim()
    outcome = Transport(origin, authorities[0] / "ca.pem", "a" * 43, collector_id=collector).send(
        claim
    )
    assert (outcome.kind, outcome.code) == (kind, code)
    assert "synthetic private" not in repr(outcome)


def test_retry_after_is_bounded_and_duplicate_receipt_is_valid(authorities, servers):
    server, origin = servers()
    server.reply = {"status": 429, "headers": {"Retry-After": "999999"}}
    collector, claim = prepared_claim()
    transport = Transport(origin, authorities[0] / "ca.pem", "a" * 43, collector_id=collector)
    assert transport.send(claim).retry_after == 300
    server.reply = {"body": b'{"accepted":true,"duplicate":true}'}
    outcome = transport.send(claim)
    assert outcome.kind == "accepted" and outcome.duplicate is True


@pytest.mark.parametrize(
    "origin",
    [
        "http://synthetic.example.test",
        "https://synthetic.example.test/path",
        "https://user:synthetic@synthetic.example.test",
        "https://127.0.0.1",
        "https://synthetic.example.test?query=1",
        "https://synthetic.example.test#fragment",
    ],
)
def test_invalid_origin_is_rejected_before_ca_or_network(tmp_path, monkeypatch, origin):
    context = Mock(side_effect=AssertionError("CA must not be read for invalid configuration"))
    monkeypatch.setattr("ssl.create_default_context", context)
    with pytest.raises(TransportError) as failure:
        Transport(origin, tmp_path / "ca.pem", "a" * 43, collector_id=uuid4())
    assert failure.value.code == "INVALID_CONFIG"
    context.assert_not_called()


@pytest.mark.parametrize("token", ["", "a" * 42, "a" * 44, "a" * 42 + "\n"])
def test_invalid_credential_never_reaches_a_socket_or_error_text(tmp_path, monkeypatch, token):
    context = Mock(side_effect=AssertionError("CA must not be read for invalid configuration"))
    monkeypatch.setattr("ssl.create_default_context", context)
    with pytest.raises(TransportError) as failure:
        Transport(
            "https://synthetic.example.test", tmp_path / "ca.pem", token, collector_id=uuid4()
        )
    assert str(failure.value) == "INVALID_CONFIG"
    context.assert_not_called()
