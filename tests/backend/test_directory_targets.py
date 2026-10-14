"""Only selected and acknowledged audit witnesses drive current IP lookup."""

from test_windows_audit_events import xml
from test_windows_audit_runtime import runtime

from collectors.windows_audit.directory_targets import read_targets


def test_unselected_logons_and_unacknowledged_batches_are_not_lookup_targets(tmp_path):
    capture = runtime(tmp_path, [
        (xml(4624, record=1, IpAddress="192.0.2.10"), "b1"),
        (xml(4663, record=2), "b2"),
        (xml(4624, record=3, IpAddress="192.0.2.11", TargetLogonId="0x202"), "b3"),
    ], track_client_ips=True)
    assert capture.step() == "filtered"
    assert capture.step() == "accepted"
    assert read_targets(capture.store.path, capture.store.cipher) == []
    pending = capture.store.peek()
    capture.store.acknowledge(pending[0])
    assert read_targets(capture.store.path, capture.store.cipher) == ["192.0.2.10"]
    assert capture.step() == "filtered"
    assert read_targets(capture.store.path, capture.store.cipher) == ["192.0.2.10"]


def test_legacy_capture_omits_directory_cache_and_preserves_native_bytes(tmp_path):
    capture = runtime(tmp_path, [(xml(4663), "b10")])
    capture.step()
    assert "directory_targets" not in capture.store.checkpoint()[1]
