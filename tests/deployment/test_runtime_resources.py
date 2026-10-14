"""Kernel enforcement and ownership are required, not merely Compose declarations."""

import json
from types import SimpleNamespace

import pytest

from deploy.scripts.environment import ConfigError


@pytest.mark.parametrize("bad", [None, "unlimited", "swap", "kernel", "owner", "oom", "replicas"])
def test_runtime_resource_verifier_checks_actual_limits_and_kernel(monkeypatch, bad):
    from deploy.scripts import resources

    budgets = {"api": 768, "worker": 512, "postgres": 2048, "web": 128}
    commands = []

    def call(*args, **kwargs):
        commands.append(args)
        if args[0] == "ps":
            return "b" * 12 + ("\n" + "c" * 12 if bad == "replicas" else "")
        if args[0] == "exec" and args[3] == "sh":
            amount = budgets[args[2]] * 1024**2
            return f"{amount if bad != 'kernel' else 'max'}\n0\n1024\n"
        return "256MB|4MB|128MB|40\n"

    current = iter(budgets)

    def inspect(*args, **kwargs):
        service = next(current)
        amount = budgets[service] * 1024**2
        return json.dumps(
            [
                {
                    "Config": {
                        "Labels": {
                            "com.docker.compose.project": "other"
                            if bad == "owner"
                            else "synthetic",
                            "com.docker.compose.service": service,
                        }
                    },
                    "HostConfig": {
                        "Memory": 0 if bad == "unlimited" else amount,
                        "MemorySwap": -1 if bad == "swap" else amount,
                    },
                    "State": {"Running": True, "OOMKilled": bad == "oom"},
                }
            ]
        )

    monkeypatch.setattr(resources, "run", inspect)
    compose = SimpleNamespace(
        call=call,
        values={
            "PROJECT_NAME": "synthetic",
            "POSTGRES_USER": "synthetic",
            "POSTGRES_DB": "synthetic",
        },
    )
    if bad is None:
        resources.verify(compose)
        assert sum(command[0] == "exec" for command in commands) == 5
    else:
        with pytest.raises(ConfigError):
            resources.verify(compose)


def test_production_budgets_are_present_in_every_service():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2] / "deploy/compose/docker-compose.prod.yml"
    ).read_text()
    for service, limit in (
        ("api", "768m"),
        ("worker", "512m"),
        ("postgres", "2048m"),
        ("web", "128m"),
        ("migrate", "512m"),
    ):
        lines = []
        for line in text.split("  " + service + ":\n", 1)[1].splitlines():
            if line and not line.startswith("    "):
                break
            lines.append(line)
        block = "\n".join(lines)
        assert "mem_limit: " + limit in block and "memswap_limit: " + limit in block
