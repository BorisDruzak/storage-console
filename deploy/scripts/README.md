# Deployment CLI

Полный deployment runbook — отдельная задача Wave0D. Эти команды рассчитаны на
Ubuntu24.04 с Python3.12+, Docker Engine и Compose>=2.20. Runtime использует Python3.13.

Каждая команда принимает **абсолютный путь** к operator env-файлу вне checkout:

```bash
bash deploy/scripts/preflight.sh /etc/storage-control-plane/production.env
bash deploy/scripts/deploy.sh /etc/storage-control-plane/production.env
bash deploy/scripts/healthcheck.sh /etc/storage-control-plane/production.env
bash deploy/scripts/stop.sh /etc/storage-control-plane/production.env
```

Env — UTF-8 файл0600, принадлежащий запускающему пользователю или root. Формат:
`KEY=VALUE`, без кавычек, `export`, expansion и повторяющихся ключей. Значения
никогда не выполняются как shell-код. Шаблон: `deploy/env/production.env.example`.
Пароль PostgreSQL генерируется один раз через `openssl rand -hex 32`; при обновлении
данных менять только env недостаточно для ротации уже созданной роли PostgreSQL.

Для сборки необходим чистый Git checkout, где HEAD равен полному `APP_RELEASE`.
API_IMAGE/WEB_IMAGE должны иметь этот release-тег. Альтернатива — два опубликованных
неизменяемых digest-образа с OCI revision label, соответствующим APP_RELEASE.
Смешивать сборку и digest-поставку нельзя. API и Web обновляются одной конфигурацией.

До запуска подготовьте state/postgres, state/diagnostics и backup-каталог.
Они не должны быть доступны группе/всем для записи. Diagnostics принадлежит UID10001.
TLS-сертификат и доверенный CA — обычные доступные файлы; закрытый ключ0600.
Auth-файл640 с группой101 доступен Nginx внутри контейнера; его родительский каталог
держите приватным. Поддерживаются SHA512-crypt и bcrypt с cost10–16; plaintext запрещён.
Это временный операторский шлюз; product AD/LDAP sessions/RBAC он не реализует.

Preflight проверяет Ubuntu,4 CPU,16GiB физической RAM (не менее15GiB usable),20GiB
свободного места, NTP, Docker, DNS, ближайшее истечение TLS, SAN/цепочку и пару ключа,
файлы/modes, каталоги и порты. Занятый порт допускается только у Web этого Compose-проекта.
Production hostname должен разрешаться на эту ВМ; исключения для production DNS нет.

Deploy получает неблокирующий lock в STATE_DIR. Образы собираются/проверяются до
остановки текущего runtime; затем PostgreSQL становится healthy, Web/API/worker
останавливаются, миграция выполняется отдельно и только после успеха запускается
новый runtime. Успех требует healthy-сервисов, строгого HTTPS с CA и HTTP308.
Healthcheck дополнительно проверяет, что DB/API/worker не публикуют порты,
а фактические image ID и OCI revision работающих API/worker/Web соответствуют
выбранным образам и APP_RELEASE.

При ошибке миграции писатели остаются остановленными. Автоматического downgrade,
rollback или восстановления БД нет. Исправьте причину в maintenance-режиме и повторите
deploy; совместимость rollback и backup/restore описываются в полном runbook.
Stop сохраняет постоянные каталоги; `down -v` эти скрипты не выполняют.

`install-docker.sh` запускается от root на Ubuntu24.04. Рабочие Docker/Compose он
не изменяет. При новой установке использует официальный HTTPS apt-репозиторий Docker;
пользователей в привилегированную группу docker автоматически не добавляет.

Systemd unit ожидает checkout `/opt/storage-control-plane` и root-owned env в
`/etc/storage-control-plane/production.env`. Перед установкой unit подготовьте все
внешние prerequisites. Ошибка preflight останавливает запуск; она не даёт TLS/auth/DNS
обхода. Сообщения CLI не раскрывают env и Docker output с интерполированными секретами.

## Backup и restore

```bash
bash deploy/scripts/backup-postgres.sh /etc/storage-control-plane/production.env
bash deploy/scripts/restore-postgres.sh /etc/storage-control-plane/production.env \
  /var/backups/storage-control-plane/backup-ARCHIVE_ID \
  --confirm storage-control-plane/storage_console
```

Backup использует `pg_dump --format=custom` из PostgreSQL16 service, проверяет TOC,
публикует каталог атомарно после fsync. Каталог700, dump/manifest600; manifest содержит
проект, БД, настроенный APP_RELEASE, размер и SHA256. APP_RELEASE в manifest — значение
конфигурации, а не заключение о совместимости схемы. Backup БД не включает TLS/env,
роли PostgreSQL, diagnostics и внешние хранилища; их защищённое копирование отдельно.
Не удаляйте предыдущие архивы до проверки нового restore; храните копию вне этой ВМ.

Restore принимает только приватный каталог непосредственно внутри BACKUP_DIR,
совпадающие проект/БД и checksum. Импортировать можно лишь доверенный собственный dump:
SQL архива выполняется с правами владельца БД. После проверки останавливаются Web/API/worker,
сохраняется отдельный safety-backup текущей БД и выполняется `pg_restore --clean --if-exists
--single-transaction --exit-on-error --no-owner --no-acl`. Ошибка SQL откатывает транзакцию;
успех и отказ оставляют сервисы записи остановленными. Объекты, отсутствующие в архиве,
`--clean` не удаляет; restore не создаёт заново весь кластер. Не добавляйте посторонние
объекты в управляемую БД.

Deploy/stop/backup/restore используют общий lock. Перед restore исключите внешних писателей,
проверьте совместимость кода со схемой восстановленного архива. Запускайте выбранный release
через deploy только после проверки. При таймауте проверьте PostgreSQL activity и завершение
операции: ошибка клиента сама по себе не доказывает прекращение серверной команды.
