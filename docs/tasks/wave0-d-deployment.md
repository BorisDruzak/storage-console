# Codex Task — Wave 0D: Deployment Package and Runbook

## Goal

Подготовить воспроизводимое развёртывание центрального Storage Console на отдельной Ubuntu VM.

Задача не создаёт VM через PVE API.

## Target

- Ubuntu Server 24.04 LTS
- Docker Engine + Compose plugin
- Nginx
- PostgreSQL
- API
- Web
- Worker
- HTTPS only

Production hostname/IP/certificate paths задаются out-of-band.

## Deliverables

Создать:
- deploy/compose/docker-compose.prod.yml
- deploy/nginx/storage-console.conf
- deploy/systemd/storage-control-plane.service
- deploy/scripts/preflight.sh
- deploy/scripts/install-docker.sh
- deploy/scripts/deploy.sh
- deploy/scripts/backup-postgres.sh
- deploy/scripts/restore-postgres.sh
- deploy/scripts/healthcheck.sh
- deploy/env/production.env.example
- русский deployment runbook

## Persistent layout

Пример:
- /opt/storage-control-plane/
- /var/lib/storage-control-plane/postgres/
- /var/lib/storage-control-plane/diagnostics/
- /var/backups/storage-control-plane/

Не хранить persistent state только в container layer.

## Security

- no secrets in repo
- env 0600
- PostgreSQL не exposed to LAN
- API behind Nginx
- cert/key permissions documented
- health endpoints no secrets

## Preflight

Проверить:
- OS version
- CPU/RAM
- disk free
- DNS/hostname supplied by operator
- ports 80/443
- Docker
- certificate files in production mode
- system time

## Runbook

На русском:
1. prerequisites
2. OS prep
3. Docker
4. directories
5. env
6. TLS
7. deploy
8. migrations
9. health verification
10. rollback
11. DB backup
12. DB restore
13. update procedure
14. logs
15. Sentry/Sonar notes

## Constraints

Не:
- создавать VM автоматически;
- вызывать PVE mutation API;
- монтировать production shares;
- выставлять PostgreSQL наружу;
- разворачивать live collectors в этой задаче.

## Acceptance

1. Clean Ubuntu VM deployable by runbook.
2. Re-run deploy idempotent.
3. API/web/worker/postgres healthy.
4. HTTPS works with supplied cert.
5. HTTP -> HTTPS.
6. PostgreSQL not LAN-exposed.
7. Backup/restore scripts tested against disposable DB.
8. Upgrade preserves persistent data.
9. Runbook fully Russian.
10. No undocumented manual step except external prerequisites.
