import json
import os
import subprocess
from pathlib import Path
from typing import Any, cast

from deploy.scripts.environment import ConfigError

ROOT = Path(__file__).resolve().parents[2]


def run(args: list[str], *, timeout: int = 15, env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ConfigError("Команда недоступна или превысила время ожидания") from None
    if result.returncode:
        # Subprocess output may contain interpolated configuration or credentials.
        raise ConfigError(
            "Команда завершилась с ошибкой; используйте документированную диагностику"
        )
    return result.stdout


class Compose:
    def __init__(self, values: dict[str, str]):
        self.values = values
        self.environment = os.environ | values
        self.base = [
            "docker",
            "compose",
            "--env-file",
            "/dev/null",
            "-f",
            str(ROOT / "deploy/compose/docker-compose.prod.yml"),
            "-p",
            values["PROJECT_NAME"],
        ]

    def call(self, *args: str, timeout: int = 30) -> str:
        return run([*self.base, *args], timeout=timeout, env=self.environment)

    def services(self) -> list[dict[str, Any]]:
        text = self.call("ps", "--all", "--format", "json")
        if not text.strip():
            return []
        if text.lstrip().startswith("["):
            return cast(list[dict[str, Any]], json.loads(text))
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def owned_ports(self) -> set[tuple[str, int]]:
        identity = self.call("ps", "-q", "web").strip()
        if not identity:
            return set()
        containers = json.loads(run(["docker", "inspect", identity]))
        ports: set[tuple[str, int]] = set()
        for container in containers:
            labels = container["Config"]["Labels"]
            if labels.get("com.docker.compose.project") != self.values["PROJECT_NAME"]:
                raise ConfigError("Несовпадение владельца публикации портов")
            for bindings in container["NetworkSettings"]["Ports"].values():
                for binding in bindings or []:
                    ports.add((binding["HostIp"], int(binding["HostPort"])))
        return ports
