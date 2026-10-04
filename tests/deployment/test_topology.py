from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_production_gateway_requires_tls_and_keeps_collector_auth_independent():
    nginx = (ROOT / "deploy/nginx/storage-console.conf").read_text(encoding="utf-8")
    assert "listen 443 ssl" in nginx
    assert "return 308 ${APP_ORIGIN}$request_uri" in nginx
    assert "auth_basic" not in nginx
    assert "location /api/v1/ingest/" in nginx
    assert "proxy_pass http://api:8000" in nginx


def test_production_compose_artifact_has_no_development_mode():
    content = (ROOT / "deploy/compose/docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "APP_ENV: production" in content
    assert "condition: service_completed_successfully" in content
    assert "create_host_path: false" in content
    assert "${STATE_DIR" in content
    assert "target: production" in content
    assert "5432:5432" not in content
    assert "8000:8000" not in content
    api = content.split("  api:\n", 1)[1].split("  worker:\n", 1)[0]
    assert "AUTH_CONFIG_FILE" in api and "APP_ORIGIN" in api
    assert "auth.json" in api and "read_only: true" in api
    assert "auth.json" not in content.split("  worker:\n", 1)[1]
