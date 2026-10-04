import contextlib
import json
import os
import stat
import sys
from collections.abc import Iterator
from pathlib import Path

from deploy.scripts.commands import ROOT, Compose, run
from deploy.scripts.environment import ConfigError, load_environment
from deploy.scripts.preflight import preflight


@contextlib.contextmanager
def deployment_lock(values: dict[str, str]) -> Iterator[None]:
    if os.name != "posix":
        raise ConfigError("Deployment выполняется на Ubuntu")
    import fcntl

    try:
        fd = os.open(
            Path(values["STATE_DIR"]) / ".deployment.lock",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(fd, "w") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                raise ConfigError("Недопустимый lock-файл deployment")
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
    except OSError:
        raise ConfigError("Deployment заблокирован или каталог недоступен") from None


def healthcheck(values: dict[str, str], compose: Compose) -> None:
    services = {row["Service"]: row for row in compose.services() if not row.get("OneOff")}
    for name in ("postgres", "api", "worker", "web"):
        row = services.get(name, {})
        if row.get("State") != "running" or row.get("Health") != "healthy":
            raise ConfigError("Один из обязательных сервисов не healthy")
        if name != "web" and any(port.get("PublishedPort") for port in row.get("Publishers") or []):
            raise ConfigError("PostgreSQL/API/worker не должны публиковать порты")
        if name != "postgres":
            image_ref = values["WEB_IMAGE" if name == "web" else "API_IMAGE"]
            expected_id = run(
                ["docker", "image", "inspect", "--format", "{{.Id}}", image_ref]
            ).strip()
            identity = run(
                [
                    "docker",
                    "container",
                    "inspect",
                    "--format",
                    '{{.Image}} {{index .Config.Labels "org.opencontainers.image.revision"}}',
                    str(row["ID"]),
                ]
            ).split()
            if identity != [expected_id, values["APP_RELEASE"]]:
                raise ConfigError("Работающий контейнер не соответствует образу release")
    host, port = values["STORAGE_HOSTNAME"], values["HTTPS_PORT"]
    tls = [
        "curl",
        "--silent",
        "--show-error",
        "--max-time",
        "10",
        "--cacert",
        values["TLS_CA_FILE"],
    ]
    ready = json.loads(run([*tls, "--fail", f"https://{host}:{port}/ready"]))
    if ready != {"status": "ok"}:
        raise ConfigError("HTTPS readiness не подтверждена")
    code = run([*tls, "-o", "/dev/null", "-w", "%{http_code}", f"https://{host}:{port}/"])
    if code != "200":
        raise ConfigError("Web должен показывать форму входа")
    for path in ("/api/v1/auth/me", "/api/v1/overview"):
        denied = run(
            [*tls, "-o", "/dev/null", "-w", "%{http_code}", f"https://{host}:{port}{path}"]
        )
        if denied != "401":
            raise ConfigError("Anonymous пользователь не должен получать данные API")
    redirect = run(
        [
            "curl",
            "--silent",
            "--show-error",
            "--max-time",
            "10",
            "-D",
            "-",
            "-o",
            "/dev/null",
            f"http://{host}:{values['HTTP_PORT']}/",
        ]
    )
    lines = redirect.splitlines()
    if (
        not lines
        or " 308 " not in lines[0]
        or not any(line.lower() == f"location: {values['APP_ORIGIN']}/" for line in lines)
    ):
        raise ConfigError("HTTP должен перенаправлять на canonical HTTPS hostname")
    print("HTTPS, HTTP redirect и сервисы: проверены")


def verify_images(values: dict[str, str]) -> None:
    for key in ("API_IMAGE", "WEB_IMAGE"):
        images = json.loads(run(["docker", "image", "inspect", values[key]]))
        labels = images[0]["Config"].get("Labels") or {}
        if labels.get("org.opencontainers.image.revision") != values["APP_RELEASE"]:
            raise ConfigError("Revision образа не соответствует APP_RELEASE")


def verify_auth_configuration(values: dict[str, str]) -> None:
    # Validate as the actual API UID before stopping writers; operator need not
    # read the private JSON. Network is disabled and no configuration is printed.
    script = """import os
from pathlib import Path
from packages.shared.auth.configuration import load_auth_config, AuthConfigurationError
from packages.shared.auth.ldap_provider import DirectoryProvider
config = load_auth_config(Path('/run/secrets/storage-console/auth.json'))
if config.origin != os.environ['APP_ORIGIN']:
    raise AuthConfigurationError()
if config.ldap is not None:
    DirectoryProvider(config.ldap)
"""
    args = [
        "docker",
        "run",
        "--rm",
        "--user",
        "10001:10001",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "-e",
        "APP_ORIGIN=" + values["APP_ORIGIN"],
    ]
    for source, target in (
        (values["AUTH_CONFIG_FILE"], "auth.json"),
        (values.get("DIRECTORY_CA_FILE") or values["TLS_CA_FILE"], "directory-ca.pem"),
    ):
        args.extend(
            [
                "--mount",
                f"type=bind,src={source},dst=/run/secrets/storage-console/{target},readonly",
            ]
        )
    run([*args, values["API_IMAGE"], "python", "-c", script], timeout=30)


def verify_source(values: dict[str, str]) -> None:
    revision = run(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).strip()
    changes = run(["git", "-C", str(ROOT), "status", "--porcelain"])
    if revision != values["APP_RELEASE"] or changes.strip():
        raise ConfigError("Сборка разрешена только из чистого checkout точного APP_RELEASE")


def deploy(values: dict[str, str], compose: Compose) -> None:
    with deployment_lock(values):
        preflight(values, compose)
        print("Preflight: проверен", flush=True)
        digests = ["@sha256:" in values[key] for key in ("API_IMAGE", "WEB_IMAGE")]
        if all(digests):
            compose.call("pull", "postgres", "api", "web", timeout=900)
        elif not any(digests):
            verify_source(values)
            compose.call("build", "--quiet", "api", "web", timeout=900)
        else:
            raise ConfigError("API и Web должны использовать единый способ поставки образов")
        verify_images(values)
        verify_auth_configuration(values)
        print("Образы release: проверены", flush=True)
        compose.call("up", "-d", "--wait", "--wait-timeout", "120", "postgres", timeout=150)
        compose.call("stop", "web", "api", "worker", timeout=60)
        # This one-shot must succeed before any new API/worker starts. A failed
        # migration leaves writers stopped; no automatic schema downgrade/restore.
        compose.call("run", "--rm", "--no-deps", "-T", "migrate", timeout=180)
        print("Миграция: выполнена", flush=True)
        compose.call(
            "up",
            "-d",
            "--no-deps",
            "--wait",
            "--wait-timeout",
            "180",
            "api",
            "worker",
            "web",
            timeout=210,
        )
        healthcheck(values, compose)
        print("Deployment завершён", flush=True)


def main() -> int:
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in {"preflight", "deploy", "healthcheck", "stop"}:
            raise ConfigError("Использование: команда /absolute/path/production.env")
        values = load_environment(Path(sys.argv[2]))
        compose = Compose(values)
        action = sys.argv[1]
        if action == "preflight":
            preflight(values, compose)
            print("Preflight: проверен")
        elif action == "deploy":
            deploy(values, compose)
        elif action == "healthcheck":
            healthcheck(values, compose)
        else:
            with deployment_lock(values):
                compose.call("stop", timeout=60)
                print("Сервисы остановлены; постоянные данные сохранены")
        return 0
    except (ConfigError, ValueError, KeyError, IndexError, OSError):
        # Only intentionally safe diagnostics are printed, never Python traceback
        # or Docker/config output with interpolated secrets.
        error = sys.exception()
        print(
            str(error) if isinstance(error, ConfigError) else "Ошибка deployment-проверки",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
