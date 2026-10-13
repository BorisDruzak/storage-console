"""Independent operator CLI. Initialization secrets arrive via stdin, never argv."""

import json
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

from collectors.windows.cli import ArgumentsError, Parser
from collectors.windows.errors import SecurityError
from collectors.windows.scm import ServiceManager, ServiceSpec
from collectors.windows.security import ProtectedState
from collectors.windows.service_installation import validate_installation

from .configuration import AuditConfig, MachineCipher, activate, load
from .scm import AuditBackend, AuditServiceSpec
from .store import AuditStore, AuditStoreError


def main() -> int:
    parser = Parser(prog="storage-audit-collector")
    parser.add_argument(
        "action", choices=["initialize", "status", "install", "start", "stop", "uninstall"]
    )
    parser.add_argument("--state", required=True)
    try:
        args = parser.parse_args()
        spec = AuditServiceSpec(sys.executable, args.state)
        if args.action == "initialize":
            raw = sys.stdin.buffer.read(65537)
            if len(raw) > 65536:
                raise ValueError("AUDIT_CONFIG_INVALID")
            config = AuditConfig.model_validate_json(raw)
            if (Path(args.state) / "outbox.sqlite3").exists():
                raise ValueError("AUDIT_USN_STATE_FORBIDDEN")
            with ProtectedState(Path(args.state), create=True) as state:
                activate(state, config)
                store = AuditStore(
                    state.root / "audit.sqlite3", config.collector_id, MachineCipher()
                )
                if config.configured and config.initial_baseline:
                    from .events import parse_event
                    from .native import boot_epoch, latest_baseline, recent_session_xml
                    from .scope import AuditScope, Selector

                    boot, started = boot_epoch()
                    xml, bookmark = latest_baseline()
                    selector = Selector(AuditScope(config.roots))
                    for session_xml in reversed(recent_session_xml()):
                        event = parse_event(
                            session_xml,
                            host_id=config.host_id,
                            boot_id=boot,
                            generation=config.generation,
                        )
                        if event and event.occurred_at >= started:
                            selector.process(event)
                    store.commit(
                        bookmark,
                        {
                            "boot_id": boot,
                            "host_id": str(config.host_id),
                            "generation": str(config.generation),
                            "anchor_digest": sha256(xml.encode()).hexdigest(),
                            "selector": selector.snapshot(),
                            "last_collected_at": datetime.now(UTC).isoformat(),
                        },
                        None,
                    )
                state.validate_file("audit.sqlite3")
            print(json.dumps({"state": "INITIALIZED", "mode": config.mode}))
            return 0
        manager = ServiceManager(cast(ServiceSpec, spec), AuditBackend())
        if args.action == "status":
            status = manager.status()
            print(
                json.dumps(
                    {
                        "service": status.state if status else "NOT_INSTALLED",
                        "pid": status.pid if status else None,
                    }
                )
            )
            return 0
        if args.action in {"install", "start"}:
            validate_installation()
            with ProtectedState(Path(args.state)) as state:
                load(state)
                state.validate_file("audit.sqlite3")
        getattr(manager, args.action)()
        print(json.dumps({"state": "COMPLETED"}))
        return 0
    except (ArgumentsError, SecurityError, AuditStoreError, OSError, ValueError):
        print(json.dumps({"state": "FAILED", "code": "AUDIT_OPERATION_FAILED"}))
        return 1


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
