"""Operator pilot CLI over the existing protected configuration and runtime."""

import argparse
import getpass
import os
import re
import signal
import sys
import threading
import time
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Never
from urllib.parse import urlsplit
from uuid import UUID

from collectors.common.delivery import Delivery
from collectors.common.outbox import Outbox, OutboxError
from collectors.common.transport import Transport, TransportError

from .capture_process import CaptureProcess
from .configuration import Loaded, PrivateConfig, _read, activate, load
from .errors import SecurityError
from .inventory import CaptureError, Scope
from .native import NativeInventory
from .producer import CaptureReport, _state, capture_heartbeat
from .runtime import Capture, Runtime
from .security import ProtectedState

DEFAULT_STATE = r"C:\ProgramData\Sosnadmin\StorageCollector"


class ArgumentsError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        # argparse's default error may echo an accidentally supplied credential.
        raise ArgumentsError


def _parser() -> Parser:
    parser = Parser(prog="storage-collector", description="Операторский Windows pilot")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("activate", "status", "inventory-once", "run"):
        child = commands.add_parser(command, help={
            "activate": "Активировать защищённое состояние",
            "status": "Прочитать безопасный статус",
            "inventory-once": "Однократно собрать и доставить metadata",
            "run": "Запустить foreground runtime; Ctrl+C — остановка",
        }[command])
        child.add_argument("--state", default=DEFAULT_STATE, help="Каталог защищённого состояния")
        if command == "activate":
            child.add_argument("--collector-id", type=UUID, required=True)
            child.add_argument("--origin", required=True)
            child.add_argument("--ca", type=Path, required=True)
            child.add_argument("--root", required=True, help="Один ограниченный local root")
            child.add_argument("--key-stdin", action="store_true", help="Ключ из private stdin")
        if command == "inventory-once":
            child.add_argument("--scan-seconds", type=int, default=600)
            child.add_argument("--settle-seconds", type=int, default=60)
    return parser


def _windows() -> bool:
    return os.name == "nt"


def _key(stdin: bool) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = sys.stdin.readline(45).rstrip("\r\n") if stdin else getpass.getpass(
                "Одноразовый ключ collector (ввод скрыт): "
            )
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
            raise SecurityError("CREDENTIAL_INVALID")
        return value
    except (EOFError, getpass.GetPassWarning):
        raise SecurityError("CREDENTIAL_INPUT_UNAVAILABLE") from None


def _scope(root: str, state: str) -> Scope:
    scope = Scope((root,))
    path = PureWindowsPath(scope.roots[0])
    private = PureWindowsPath(state)
    if len(path.parts) < 2 or path == private or path in private.parents or private in path.parents:
        raise CaptureError("INVALID_SCOPE")
    return scope


def _validate_root(scope: Scope) -> None:
    # Resolve/open the native root without advancing to its recursive children.
    observations = NativeInventory().scan(scope)
    try:
        first = next(observations)
        if first.error_code:
            raise CaptureError(first.error_code)
    finally:
        close = getattr(observations, "close", None)
        if close is not None:
            close()


def print_status(config: PrivateConfig, box: Outbox) -> None:
    status = box.status()
    print(f"Collector ID: {config.collector_id}")
    print(f"Origin hostname: {urlsplit(config.origin).hostname}")
    print(f"Корней scope: {len(config.roots)}")
    print("Protected config: OK (DPAPI)")
    print(f"В очереди: {status.pending_count}")
    print(f"В карантине: {status.quarantined_count}")
    print(f"Auth suspended: {'да' if box.auth_suspended() else 'нет'}")
    for stream, label in (("inventory", "Inventory"), ("heartbeat", "Heartbeat")):
        checkpoint = _state(
            box, "windows:" + stream, config.scope if stream == "inventory" else None,
        )
        value = checkpoint.value if isinstance(checkpoint.value, dict) else {}
        complete = value.get("completed")
        print(f"{label} checkpoint: revision={checkpoint.revision}; "
              f"sequence={value.get('sequence', 0)}; completed={complete}")


@dataclass(frozen=True)
class OnceResult:
    complete: bool
    records: int
    batches: int
    delivered: int
    pending: int
    errors: tuple[str, ...]


def inventory_once(
    loaded: Loaded,
    *,
    stop: threading.Event | None = None,
    scan_seconds: int = 600,
    settle_seconds: int = 60,
    capture_factory: Callable[[], Capture] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> OnceResult:
    if not 1 <= scan_seconds <= 86400 or not 1 <= settle_seconds <= 600:
        raise SecurityError("INVALID_SETTINGS")
    stop = stop if stop is not None else threading.Event()
    delivery = Delivery(loaded.outbox, loaded.transport, prefer_heartbeat=True)
    capture: Capture | None = None
    report = CaptureReport(0, 0, False, ())
    delivered = 0
    errors: set[str] = set()

    def send() -> bool:
        nonlocal delivered
        result = delivery.run_once()
        delivered += int(result.state == "accepted")
        if result.state in {"suspended", "quarantined"}:
            errors.add(result.code or "HTTP_REJECTED")
            return False
        if result.state != "accepted":
            stop.wait(loaded.config.settings.poll_seconds)
        return True

    try:
        deadline = monotonic() + scan_seconds
        capture = capture_factory() if capture_factory else CaptureProcess(loaded)
        while not stop.is_set():
            current = capture.poll()
            if current is not None:
                report, capture = current, None
                break
            if monotonic() >= deadline:
                errors.add("SCAN_TIMEOUT")
                break
            if not send():
                break
        if capture is not None:
            report = capture.stop(loaded.config.settings.child_stop_seconds)
            capture = None
        errors.update(report.errors)
        if stop.is_set():
            errors.add("STOPPED")
        capture_heartbeat(
            loaded.outbox,
            error_code=report.errors[0] if report.errors else (
                None if report.completed else "NATIVE_FAILED"
            ),
        )
        deadline = monotonic() + settle_seconds
        while not stop.is_set() and monotonic() < deadline:
            if loaded.outbox.status().pending_count == 0 or not send():
                break
        status = loaded.outbox.status()
        if status.pending_count:
            errors.add("PENDING_OUTBOX")
        if status.quarantined_count:
            errors.add("QUARANTINED_OUTBOX")
        if loaded.outbox.auth_suspended():
            errors.add("AUTH_REQUIRED")
        return OnceResult(
            report.completed and not errors, report.records, report.batches,
            delivered, status.pending_count, tuple(sorted(errors)),
        )
    finally:
        delivery.close()
        if capture is not None:
            capture.stop(loaded.config.settings.child_stop_seconds)


def _execute(args: argparse.Namespace, stop: threading.Event) -> int:
    if not _windows():
        raise SecurityError("PLATFORM_UNSUPPORTED")
    if args.command == "activate":
        scope = _scope(args.root, args.state)
        _validate_root(scope)
        with args.ca.open("rb") as stream:
            ca = stream.read(128 * 1024 + 1)
        token = _key(args.key_stdin)
        # Validate TLS trust and origin before any persistent activation writes.
        Transport(args.origin, args.ca, token, collector_id=args.collector_id)
        with ProtectedState(Path(args.state), create=True) as state:
            activate(state, args.collector_id, args.origin, scope, token, ca)
        print("Collector активирован; защищённая конфигурация сохранена")
        print(f"Collector ID: {args.collector_id}; корней scope: 1")
        return 0
    protected = (
        ProtectedState(Path(args.state), read_only=True)
        if args.command == "status" else ProtectedState(Path(args.state))
    )
    with protected as state:
        if args.command == "status":
            config = _read(state)
            for suffix in ("", "-journal", "-wal", "-shm"):
                name = "outbox.sqlite3" + suffix
                if (state.root / name).exists():
                    state.validate_file(name)
            box = Outbox(
                state.root / "outbox.sqlite3", config.collector_id,
                config.settings.limits(), read_only=True,
            )
            if box.credential_binding() != config.credential_version:
                raise SecurityError("CREDENTIAL_MISMATCH")
            print_status(config, box)
            return 0
        loaded = load(state)
        if args.command == "run":
            print("Foreground runtime запущен; Ctrl+C — остановка", flush=True)
            runtime = Runtime(loaded)
            runtime.run(stop)
            for event in runtime.events[-3:]:
                print(f"Runtime: {event.kind}; code={event.code or 'OK'}; "
                      f"records={event.records}; batches={event.batches}")
            print("Runtime остановлен")
            return 130 if stop.is_set() else 0
        result = inventory_once(
            loaded, stop=stop, scan_seconds=args.scan_seconds, settle_seconds=args.settle_seconds,
        )
        print("Инвентаризация завершена" if result.complete else "Инвентаризация не подтверждена")
        print(f"Записей metadata: {result.records}\nПакетов inventory: {result.batches}\n"
              f"Отправлено (включая heartbeat/очередь): {result.delivered}\n"
              f"В очереди: {result.pending}\nОшибок: {len(result.errors)}")
        for code in result.errors:
            print(f"Код: {code}")
        return 0 if result.complete else (130 if stop.is_set() else 1)


def main(argv: Sequence[str] | None = None) -> int:
    # Redirected Windows streams inherit the host code page, which may not
    # represent Russian operator messages. Keep console and captured output UTF-8.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    stop = threading.Event()
    previous = signal.getsignal(signal.SIGINT)
    try:
        args = _parser().parse_args(argv)
        if args.command in {"inventory-once", "run"}:
            signal.signal(signal.SIGINT, lambda *_: stop.set())
        return _execute(args, stop)
    except ArgumentsError:
        print("Ошибка аргументов; storage-collector --help", file=sys.stderr)
        return 2
    except (SecurityError, CaptureError, OutboxError, TransportError) as error:
        print(f"Ошибка: {error.code}", file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("Ошибка: CONFIG_OR_STATE_INVALID", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Остановлено оператором", file=sys.stderr)
        return 130
    finally:
        signal.signal(signal.SIGINT, previous)


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
