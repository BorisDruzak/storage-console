"""Verify actual production container and PostgreSQL resource bounds."""

import json
import re

from deploy.scripts.commands import Compose, run
from deploy.scripts.environment import ConfigError

BUDGETS_MIB = {"api": 768, "worker": 512, "postgres": 2048, "web": 128}


def verify(compose: Compose) -> None:
    try:
        for service, mib in BUDGETS_MIB.items():
            identity = compose.call("ps", "-q", service).strip()
            if not re.fullmatch(r"[0-9a-f]{12,64}", identity):
                raise ValueError
            rows = json.loads(run(["docker", "inspect", identity]))
            if len(rows) != 1:
                raise ValueError
            row = rows[0]
            labels = row["Config"]["Labels"]
            expected = mib * 1024**2
            if (
                labels.get("com.docker.compose.project") != compose.values["PROJECT_NAME"]
                or labels.get("com.docker.compose.service") != service
                or row["HostConfig"]["Memory"] != expected
                or row["HostConfig"]["MemorySwap"] != expected
                or not row["State"]["Running"]
                or row["State"]["OOMKilled"]
            ):
                raise ValueError
            values = compose.call(
                "exec",
                "-T",
                service,
                "sh",
                "-c",
                "cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.swap.max "
                "/sys/fs/cgroup/memory.current",
            ).splitlines()
            if len(values) != 3 or list(map(int, values[:2])) != [expected, 0]:
                raise ValueError
            if not 0 <= int(values[2]) <= expected:
                raise ValueError
        database = compose.call(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            compose.values["POSTGRES_USER"],
            "-d",
            compose.values["POSTGRES_DB"],
            "-At",
            "-c",
            "SELECT current_setting('shared_buffers')||'|'||current_setting('work_mem')||'|'"
            "||current_setting('maintenance_work_mem')||'|'||current_setting('max_connections');",
        ).strip()
        if database != "256MB|4MB|128MB|40":
            raise ValueError
    except (ValueError, KeyError, TypeError, IndexError):
        raise ConfigError("Лимиты памяти контейнеров и PostgreSQL не подтверждены") from None
