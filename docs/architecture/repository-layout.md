# Структура monorepo

~~~text
storage-console/
├─ apps/
│  ├─ api/
│  ├─ web/
│  └─ worker/
├─ collectors/
│  ├─ windows/
│  ├─ pve/
│  └─ pbs/
├─ packages/
│  ├─ contracts/
│  ├─ i18n/
│  └─ shared/
├─ migrations/
├─ mcp/
├─ deploy/
│  ├─ compose/
│  ├─ nginx/
│  ├─ scripts/
│  └─ systemd/
├─ tests/
├─ docs/
└─ .github/
~~~

## Компоненты

### apps/api
Storage API, auth/RBAC, ingest/read endpoints.

### apps/web
Русская Web Console.

### apps/worker
State/alert engine, aggregation, retention, background jobs.

### collectors/windows
USN, inventory, SMB/DFS/FSRM/VSS, ACL, Windows telemetry/events.

### collectors/pve
PVE/QEMU/ZFS/network/storage telemetry.

### collectors/pbs
Backup/recovery metadata.

### packages/contracts
Versioned API/ingest contracts.

### packages/i18n
Translation catalogs and locale tooling.

### mcp
Read-only MCP server consuming Storage API only.
