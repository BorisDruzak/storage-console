"""Own encrypted queue: bounded pages, immutable replay and independent failure."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from test_directory_contract import page

from collectors.common.transport import DeliveryOutcome
from collectors.windows_audit.directory_store import DirectoryStore, DirectoryStoreError
from packages.contracts.directory import DirectoryPage


class Cipher:
    def protect(self, value):
        return b"encrypted:" + value

    def unprotect(self, value):
        return value[len(b"encrypted:") :]


def frame(identity):
    return DirectoryPage.model_validate(page(collector_id=identity, sent_at=datetime.now(UTC)))


def test_reopen_lost_ack_and_route_preserve_the_same_page_bytes(tmp_path):
    identity = uuid4()
    path = tmp_path / "directory.sqlite3"
    store = DirectoryStore(path, identity, Cipher())
    value = frame(identity)
    store.enqueue("directory", value)
    claim = store.peek()
    assert claim.domain == "directory"
    store.record_outcome(DeliveryOutcome("retry", code="NETWORK"), now=0)
    reopened = DirectoryStore(path, identity, Cipher())
    assert reopened.peek().body == claim.body
    reopened.record_outcome(DeliveryOutcome("accepted", duplicate=True), now=10)
    assert reopened.peek() is None
    assert not (tmp_path / "audit.sqlite3").exists()


def test_capacity_retains_old_bytes_and_has_terminal_error_headroom(tmp_path):
    identity = uuid4()
    store = DirectoryStore(
        tmp_path / "directory.sqlite3", identity, Cipher(), max_bytes=8192, max_batches=2
    )
    store.enqueue("directory", frame(identity))
    claim = store.peek()
    with pytest.raises(DirectoryStoreError):
        store.enqueue("directory", frame(identity))
    assert store.peek().body == claim.body
    failed = DirectoryPage.model_validate(
        page(
            collector_id=identity,
            records=[],
            total_records=0,
            complete=False,
            error_code="DIRECTORY_LIMIT",
        )
    )
    store.enqueue("directory", failed, terminal_error=True)
    assert store.status()["backlog"] == 2


def test_foreign_identity_and_invalid_route_never_enter_the_queue(tmp_path):
    identity = uuid4()
    store = DirectoryStore(tmp_path / "directory.sqlite3", identity, Cipher())
    with pytest.raises(DirectoryStoreError):
        store.enqueue("directory", frame(uuid4()))
    with pytest.raises(DirectoryStoreError):
        store.enqueue("audit", frame(identity))
    assert store.peek() is None
