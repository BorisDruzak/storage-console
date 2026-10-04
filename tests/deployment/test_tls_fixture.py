import shutil
import subprocess

import pytest

from tests.deployment.smoke_production import setup_tls


@pytest.mark.skipif(
    shutil.which("openssl") is None, reason="OpenSSL fixture requires native executable"
)
def test_disposable_tls_fixture_passes_strict_server_chain_and_hostname(tmp_path):
    setup_tls(tmp_path)
    arguments = [
        "openssl",
        "verify",
        "-x509_strict",
        "-purpose",
        "sslserver",
        "-CAfile",
        str(tmp_path / "ca.pem"),
    ]
    valid = subprocess.run(
        [*arguments, "-verify_hostname", "storage.example.test", str(tmp_path / "cert.pem")],
        capture_output=True,
    )
    assert valid.returncode == 0, "Disposable CA/leaf must pass strict X.509 server validation"
    invalid = subprocess.run(
        [*arguments, "-verify_hostname", "other.example.test", str(tmp_path / "cert.pem")],
        capture_output=True,
    )
    assert invalid.returncode != 0, "Disposable TLS must reject the wrong server hostname"
