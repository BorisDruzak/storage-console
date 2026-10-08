"""A bounded native USN pass, with explicit initial baseline and latched gaps."""

from collections.abc import Callable
from contextlib import closing

from collectors.common.outbox import Outbox, OutboxError
from packages.contracts.inventory import FileObjectRecord, VolumeRecord

from .inventory import CaptureError, Scope
from .native import NativeInventory
from .producer import CaptureReport
from .usn import UsnError
from .usn_native import NativeJournal
from .usn_state import UsnState


def _bootstrap(
    box: Outbox, scope: Scope, journal: NativeJournal, stopped: Callable[[], bool],
) -> None:
    missing = [volume for volume in journal.volumes
               if UsnState(box, volume, scope.fingerprint).status == "USN_BOOTSTRAP"]
    if not missing:
        return
    before = {}
    for volume in missing:
        with closing(journal.open(volume)) as stream:
            before[volume] = stream.query()
    cache: dict[str, dict[str, dict[str, object]]] = {volume: {} for volume in missing}
    native = NativeInventory()
    for root in scope.roots:
        iterator = native._root(journal._api, root)
        first = True
        try:
            for observation in iterator:
                if stopped():
                    raise CaptureError("STOPPED")
                if observation.error_code:
                    raise UsnError("USN_PATH_UNKNOWN")
                record = observation.record
                if isinstance(record, VolumeRecord):
                    continue
                if not isinstance(record, FileObjectRecord):
                    raise UsnError("USN_STATE_INVALID")
                if record.volume_identity in cache:
                    entries = cache[record.volume_identity]
                    if len(entries) >= 100000:
                        raise UsnError("USN_CAPACITY")
                    values: dict[str, object] = {"name": record.name,
                                                 "parent": record.parent_file_id}
                    if first:
                        values["root"] = record.relative_path
                    elif record.file_id in entries:
                        # Multiple native paths for one FileId cannot establish a
                        # unique cached ancestry baseline. Never choose an alias.
                        raise UsnError("USN_PATH_UNKNOWN")
                    entries[record.file_id] = values
                first = False
        finally:
            iterator.close()
    for volume in missing:
        state = UsnState(box, volume, scope.fingerprint)
        if state.cursor or state.status != "USN_BOOTSTRAP":
            raise UsnError("USN_STATE_INVALID")
        with closing(journal.open(volume)) as stream:
            info = stream.query()
            cursor = before[volume].next_usn
            info.require_cursor(before[volume].journal_id, cursor)
            # Enumeration is not a snapshot. Prove that no cached object or
            # approved parent changed while constructing its ancestry. Outside
            # volume noise is read but never cached or uploaded. Bound this
            # validation; failure leaves an uninitialized UNKNOWN baseline.
            for _ in range(8):
                if cursor >= info.next_usn:
                    break
                if stopped():
                    raise CaptureError("STOPPED")
                next_cursor, records = stream.read(info.journal_id, cursor)
                if any(record.file_id in cache[volume] or record.parent_id in cache[volume]
                       for record in records):
                    raise UsnError("USN_PATH_UNKNOWN")
                if next_cursor <= cursor:
                    raise UsnError("USN_STATE_INVALID")
                cursor = next_cursor
            if cursor < info.next_usn:
                raise UsnError("USN_CAPACITY")
        # Begin a new window after a proven unchanged ancestry enumeration;
        # historical changes before this baseline are not claimed as recovered.
        state.initialize(info.journal_id, info.next_usn, cache[volume])


def capture_usn(
    box: Outbox, scope: Scope, *, stopped: Callable[[], bool] = lambda: False,
) -> CaptureReport:
    records, batches = 0, 0
    state: UsnState | None = None
    try:
        journal = NativeJournal(scope)
        _bootstrap(box, scope, journal, stopped)
        for volume in journal.volumes:
            state = UsnState(box, volume, scope.fingerprint)
            if state.status not in (None, "USN_PATH_UNKNOWN"):
                raise UsnError(state.status or "USN_UNAVAILABLE")
            with closing(journal.open(volume)) as stream:
                target = stream.query().next_usn
                # At most eight 256-record transitions per pass, even on a busy
                # volume. Other workers keep heartbeat/inventory/delivery alive.
                for _ in range(8):
                    if stopped():
                        raise CaptureError("STOPPED")
                    info = stream.query()
                    state.check_continuity(
                        info.journal_id, max(info.first_usn, info.lowest_valid_usn), info.next_usn,
                    )
                    if state.status not in (None, "USN_PATH_UNKNOWN"):
                        raise UsnError(state.status or "USN_UNAVAILABLE")
                    cursor = state.cursor
                    if cursor >= target:
                        break
                    next_cursor, raw = stream.read(info.journal_id, cursor)
                    if next_cursor == cursor:
                        break
                    if len(raw) > 256:
                        next_cursor, raw = raw[256].usn, raw[:256]
                    while True:
                        try:
                            events = state.consume(info.journal_id, next_cursor, raw)
                            break
                        except OutboxError as error:
                            if (error.code not in {"INVALID_BATCH", "INVALID_CHECKPOINT"}
                                    or len(raw)<=1):
                                raise
                            # The rejected transition committed nothing. Reduce
                            # its prefix to satisfy encoded body/cache bounds;
                            # reread the remainder from this exact durable cursor.
                            count = max(1, len(raw)//2)
                            next_cursor, raw = raw[count].usn, raw[:count]
                    records += len(events)
                    batches += int(bool(events))
                    if state.cursor == cursor:
                        raise UsnError(state.status or "USN_STATE_INVALID")
                if state.cursor < target:
                    raise UsnError("USN_LAG")
            if state.status is not None:
                raise UsnError(state.status)
        return CaptureReport(records, batches, True, ())
    except UsnError as error:
        if state is not None and error.code in {
            "CONTINUITY_GAP", "USN_UNSUPPORTED", "USN_MALFORMED", "USN_ACCESS_DENIED",
            "USN_VOLUME_LOST", "USN_UNAVAILABLE", "USN_STATE_INVALID",
        }:
            state.fail(error.code)
        return CaptureReport(records, batches, False, (error.code,))
    except CaptureError as error:
        return CaptureReport(records, batches, False, (error.code,))
    except OutboxError as error:
        return CaptureReport(records, batches, False,
                             ("USN_CAPACITY" if error.code == "CAPACITY" else "USN_STATE_INVALID",))
