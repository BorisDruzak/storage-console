from datetime import UTC, datetime

import pytest
from test_collector_outbox import heartbeat
from test_windows_runtime import prepared
from windows_capture_diagnostics import drain_watermark, drained_through, readonly_observer


def enqueue(loaded):
    revision = loaded.outbox.checkpoint("heartbeat").revision
    loaded.outbox.enqueue("heartbeat", heartbeat(loaded.outbox.collector_id),
                          "heartbeat", revision, {"cursor": str(revision + 1)})


def test_closed_batches_drain_even_when_the_producer_enqueues_more(tmp_path):
    loaded = prepared(tmp_path)
    observer = readonly_observer(loaded)
    enqueue(loaded)
    watermark = drain_watermark(observer)
    claim = loaded.outbox.claim(datetime.now(UTC))
    assert claim is not None and loaded.outbox.acknowledge(claim)
    enqueue(loaded)
    before = observer.status()
    assert before.pending_count == 1
    assert drained_through(observer, watermark)
    assert observer.status() == before


@pytest.mark.parametrize("quarantined", [False, True])
def test_unacknowledged_closed_batch_blocks_drain_in_every_state(tmp_path, quarantined):
    loaded = prepared(tmp_path)
    observer = readonly_observer(loaded)
    enqueue(loaded)
    watermark = drain_watermark(observer)
    if quarantined:
        claim = loaded.outbox.claim(datetime.now(UTC))
        assert claim is not None and loaded.outbox.quarantine(claim, "INVALID_RECEIPT")
    else:
        enqueue(loaded)
    before = observer.status()
    assert not drained_through(observer, watermark)
    assert observer.status() == before
