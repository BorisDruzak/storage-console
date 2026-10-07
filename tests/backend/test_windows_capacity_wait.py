from test_windows_producer import NOW, SCOPE, box, observations

from collectors.windows.producer import capture_inventory


def test_capture_waits_for_delivery_without_rewriting_or_losing_records(tmp_path):
    outbox = box(tmp_path, max_retained_batches=1)
    delivered = []
    ticks = [0.0]

    def wait(delay):
        ticks[0] += delay
        claim = outbox.claim(NOW)
        assert claim is not None and outbox.acknowledge(claim)
        delivered.append(claim.body)

    report = capture_inventory(
        outbox,
        SCOPE,
        observations(),
        max_records=2,
        clock=lambda: NOW,
        capacity_wait_seconds=1,
        monotonic=lambda: ticks[0],
        wait=wait,
    )
    assert report.completed and report.records == 6 and report.batches == 3
    assert len(delivered) == 2 and outbox.status().pending_count == 1
    assert outbox.checkpoint("windows:inventory").revision == 3


def test_capacity_deadline_is_finite_and_interrupted_scan_never_claims_complete(tmp_path):
    outbox = box(tmp_path, max_retained_batches=1)
    ticks = [0.0]
    waits = []

    def wait(delay):
        waits.append(delay)
        ticks[0] += delay

    report = capture_inventory(
        outbox,
        SCOPE,
        observations(),
        max_records=2,
        clock=lambda: NOW,
        capacity_wait_seconds=0.3,
        monotonic=lambda: ticks[0],
        wait=wait,
    )
    assert report.errors == ("CAPACITY",) and report.records == 2 and not report.completed
    assert 2 <= len(waits) <= 4 and sum(waits) == 0.3
    assert outbox.checkpoint("windows:inventory").revision == 1


def test_capacity_wait_is_interruptible_without_advancing_checkpoint(tmp_path):
    outbox = box(tmp_path, max_retained_batches=1)
    stop = [False]

    def wait(delay):
        stop[0] = True

    report = capture_inventory(
        outbox,
        SCOPE,
        observations(),
        max_records=2,
        clock=lambda: NOW,
        capacity_wait_seconds=5,
        stopped=lambda: stop[0],
        wait=wait,
    )
    assert report.errors == ("STOPPED",) and report.records == 2 and not report.completed
    assert outbox.checkpoint("windows:inventory").revision == 1
