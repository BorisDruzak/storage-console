from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_production_gateway_requires_tls_and_keeps_collector_auth_independent():
    nginx = (ROOT / "deploy/nginx/storage-console.conf").read_text(encoding="utf-8")
    assert "listen 443 ssl" in nginx
    assert "return 308 https://${STORAGE_HOSTNAME}$request_uri" in nginx
    assert "auth_basic_user_file /etc/storage-console/auth/users.htpasswd" in nginx
    assert "location /api/v1/ingest/" in nginx
    assert "auth_basic off" in nginx
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
