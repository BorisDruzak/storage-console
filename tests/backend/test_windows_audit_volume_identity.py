"""Native GUID aliases are stable volume identities, never drive-letter guesses."""

from uuid import uuid4

import pytest
from test_windows_audit_events import parse, xml

from collectors.windows_audit.scope import AuditScope


def test_selected_native_guid_is_emitted_as_canonical_volume_identity():
    identity = uuid4()
    scope = AuditScope({r"D:\Synthetic": "\\\\?\\Volume{" + str(identity).upper() + "}\\"})
    event = parse(xml(ObjectName=r"D:\Synthetic\report.txt"))
    selected = scope.select(event)
    assert selected is not None
    assert selected.volume_id == "volume:" + str(identity)


@pytest.mark.parametrize("alias", [
    "\\\\?\\Volume{not-a-guid}\\", "\\\\?\\Volume{" + str(uuid4()) + "}\\other",
    "\\\\?\\Volume{0123456789abcdef0123456789abcdef----}\\",
])
def test_native_guid_mapping_cannot_include_a_relative_path(alias):
    with pytest.raises(ValueError):
        AuditScope({r"D:\Synthetic": alias})
