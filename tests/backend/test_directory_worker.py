"""Partial collection and queue errors cannot move the Security bookmark."""

from datetime import UTC, datetime
from threading import Event
from uuid import uuid4

from test_directory_native import settings
from test_directory_store import Cipher

from collectors.windows_audit.directory_native import DirectoryError, DirectorySettings
from collectors.windows_audit.directory_store import DirectoryStore
from collectors.windows_audit.directory_worker import DirectoryWorker


class Native:
    def users(self, stop):
        yield {"page_index": 0, "records": [], "finished": False}
        raise DirectoryError("LDAP_UNAVAILABLE")


def test_partial_native_failure_enqueues_explicit_terminal_error(tmp_path):
    identity = uuid4()
    store = DirectoryStore(tmp_path / "directory.sqlite3", identity, Cipher())
    worker = DirectoryWorker(
        store, DirectorySettings.model_validate(settings()), Native(), targets=lambda: []
    )
    worker.collect(Event(), now=datetime.now(UTC))
    first = store.peek()
    from packages.contracts.directory import DirectoryPage

    page = DirectoryPage.model_validate_json(first.body)
    assert page.page_index == 0 and not page.finished
    from collectors.common.transport import DeliveryOutcome

    store.record_outcome(DeliveryOutcome("accepted", duplicate=False), now=0)
    failed = DirectoryPage.model_validate_json(store.peek().body)
    assert failed.snapshot_id == page.snapshot_id and failed.page_index == 1
    assert failed.finished and not failed.complete and failed.error_code == "LDAP_UNAVAILABLE"
    assert failed.total_records == 0 and not (tmp_path / "audit.sqlite3").exists()


def test_directory_config_and_queue_are_opt_in_to_audit_only():
    from collectors.windows_audit.configuration import AuditConfig

    assert "directory" in AuditConfig.model_fields
    assert AuditConfig.model_fields["directory"].default is None


def test_snapshot_reserves_bytes_for_terminal_error(monkeypatch):
    from test_directory_contract import user

    from collectors.windows_audit import directory_worker

    limit = 1600
    monkeypatch.setattr(directory_worker, "MAX_SNAPSHOT_BYTES", limit)
    monkeypatch.setattr(directory_worker, "TERMINAL_ERROR_RESERVE", 512)

    class RecordingStore:
        collector_id = uuid4()
        pages = []

        def enqueue(self, kind, value, **kwargs):
            self.pages.append(value)

        def delivery_state(self):
            return {}

        def save_state(self, value):
            pass

    class FailingNative:
        def users(self, stop):
            for index in range(2):
                yield {"page_index": index, "records": [user()], "finished": False}
            raise DirectoryError("LDAP_UNAVAILABLE")

    store = RecordingStore()
    worker = DirectoryWorker(
        store, DirectorySettings.model_validate(settings()), FailingNative(), targets=lambda: []
    )
    worker.collect(Event())
    assert sum(len(page.model_dump_json().encode()) for page in store.pages) <= limit
    assert store.pages[-1].finished and not store.pages[-1].complete
    assert store.pages[-1].total_records == sum(len(page.records) for page in store.pages[:-1])
