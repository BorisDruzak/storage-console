# Source boundary

Подробные infrastructure research/evidence для проекта хранятся отдельно в приватном инфраструктурном репозитории владельца.

Этот публичный repository содержит только:
- product specification;
- implementation tasks;
- source code;
- sanitised fixtures/examples;
- generic deployment templates.

При реализации Codex не должен переносить сюда:
- production IP/FQDN/topology;
- реальные SID/учётные записи;
- ACL dumps;
- raw Windows/PVE/PBS logs;
- диагностические архивы;
- credentials/cert private keys.

Production values должны поступать через secrets/configuration out-of-band.
