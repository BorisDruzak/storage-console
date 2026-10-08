import os
from uuid import uuid4

import pytest
from test_collector_transport import authorities as authorities

from collectors.windows import configuration
from collectors.windows.capture_process import CaptureProcess
from collectors.windows.errors import SecurityError
from collectors.windows.inventory import Scope
from collectors.windows.producer import CaptureReport
from collectors.windows.security import ProtectedState


def test_worker_preserves_explicit_usn_failure():
    report = CaptureReport(0, 0, False, ("CONTINUITY_GAP",))
    assert CaptureProcess.decode(CaptureProcess.encode(report)) == report


def test_operator_can_parse_scoped_usn_enable_and_disable():
    from collectors.windows.cli import _parser

    for command in ("usn-enable", "usn-disable"):
        assert _parser().parse_args([command]).command == command


@pytest.mark.skipif(os.name != "nt", reason="Actual protected Windows state")
def test_usn_activation_survives_restart_without_changing_credentials(tmp_path, authorities):
    root = tmp_path / "metadata"
    root.mkdir()
    with ProtectedState(tmp_path / "state", create=True) as state:
        configuration.activate(state, uuid4(), "https://localhost", Scope((str(root),)),
                               "a" * 43, (authorities[0] / "ca.pem").read_bytes())
        before = state.read("config.json", 131072)
        binding = configuration.load(state).outbox.credential_binding()
        assert configuration.load(state).usn_enabled is False
        configuration.set_usn_enabled(state, True)
        assert state.read("config.json", 131072) == before
    with ProtectedState(tmp_path / "state") as state:
        loaded = configuration.load(state)
        assert loaded.usn_enabled is True
        assert loaded.outbox.credential_binding() == binding
        configuration.set_usn_enabled(state, False)
        assert configuration.load(state).usn_enabled is False
        assert state.read("config.json", 131072) == before


@pytest.mark.skipif(os.name != "nt", reason="Actual protected Windows state")
@pytest.mark.parametrize("raw", [b'{"enabled":true}', b'{"version":1,"version":1}',
                                 b'{"version":1,"scope":"wrong","enabled":true}'])
def test_invalid_activation_never_silently_disables_usn(tmp_path, authorities, raw):
    with ProtectedState(tmp_path / "state", create=True) as state:
        configuration.activate(state, uuid4(), "https://localhost", Scope((str(tmp_path),)),
                               "a" * 43, (authorities[0] / "ca.pem").read_bytes())
        state.write("usn-activation.json", raw)
        with pytest.raises(SecurityError, match="^CONFIG_INVALID$"):
            configuration.load(state)
