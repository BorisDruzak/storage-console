# Развёртывание Storage Control Plane

Команды ниже выполняются на целевой Ubuntu ВМ. Пример использует checkout
`/opt/storage-control-plane`, конфигурацию `/etc/storage-control-plane/production.env`
и Compose-проект `storage-control-plane`. Реальные DNS, SSH, сертификаты, пароли и DSN
хранятся вне Git. Перед выполнением замените значения примера своими.

## 1. Предварительные условия

Ubuntu24.04, минимум4CPU,16GiB физической RAM (preflight требует15GiB usable),
20GiB свободного места для первоначального запуска плюс место для роста БД, образов
и нескольких backup. Нужны Git, Python3.12+, Bash, curl, OpenSSL, синхронизированное время,
доступ к HTTPS-репозиториям Docker/образов и исходному Git. Production DNS должен разрешаться
в адрес этой ВМ; HTTP80/HTTPS443 доступны клиентам, PostgreSQL/API наружу не публикуются.

Оператор предоставляет TLS certificate/fullchain/key, CA для проверки и клиентского доверия,
а также приватную JSON-конфигурацию провайдеров входа. SSH-доступ и полномочия root настраиваются
администратором. ВМ, DNS, CA и firewall не создаются этими скриптами.

SPA показывает форму входа без авторизации; read API требует пользовательскую сессию и
разрешение роли. Вход использует явно выбранный локальный или LDAPS-провайдер, logout —
Origin и CSRF. Collector ingest использует независимый bearer. Доверие TLS, доступность
LDAPS и сопоставление AD-групп проверяются отдельно на целевой инфраструктуре.
Живые collectors и production shares этим пакетом не разворачиваются.

## 2. Подготовка ОС

```bash
sudo apt-get update
sudo apt-get install -y git python3 curl openssl ca-certificates
timedatectl status
timedatectl show -p NTPSynchronized --value
df -h /var/lib
```

Ожидается `NTPSynchronized=yes`. Причину отсутствия синхронизации исправляет администратор
ОС; preflight не отключает этот контроль. Не помещайте credentials в shell history.

## 3. Docker

Получите исходный checkout, затем установите Docker официальным скриптом:

```bash
sudo git clone https://github.com/BorisDruzak/storage-console.git /opt/storage-control-plane
cd /opt/storage-control-plane
sudo bash deploy/scripts/install-docker.sh
sudo docker info --format '{{.ServerVersion}}'
sudo docker compose version
```

Установщик предназначен для Ubuntu24.04/root и официального apt-репозитория Docker.
Рабочий Docker/Compose сохраняется. Требуется Compose>=2.20. Скрипт не добавляет пользователей
в группу docker; доступ к Docker эквивалентен административным полномочиям.
На стенде проверен путь с уже установленным Docker; свежая установка apt ещё требует
отдельной приёмки на чистой ВМ.

## 4. Каталоги и владельцы

```bash
sudo install -d -m 700 /etc/storage-control-plane
sudo install -d -m 700 /etc/storage-control-plane/tls /etc/storage-control-plane/auth
sudo install -d -m 700 /var/lib/storage-control-plane /var/backups/storage-control-plane
sudo install -d -o 70 -g 70 -m 700 /var/lib/storage-control-plane/postgres
sudo install -d -o 10001 -g 10001 -m 700 /var/lib/storage-control-plane/diagnostics
```

UID70 соответствует PostgreSQL16 Alpine в используемом образе, UID10001 — API/worker.
При изменении базовых образов перепроверьте владельцев. Не используйте symlink для state
или секретных файлов. Backup-каталог700, архивы600. Compose не создаёт отсутствующие bind-файлы.
Не запускайте `down -v`, не удаляйте state при смене release.

## 5. Конфигурация

```bash
sudo install -m 600 deploy/env/production.env.example /etc/storage-control-plane/production.env
git rev-parse HEAD
openssl rand -hex 32
sudoedit /etc/storage-control-plane/production.env
```

Укажите DNS, точный40-символьный SHA, `API_IMAGE=storage-console-api:SHA`,
`WEB_IMAGE=storage-console-web:SHA`, случайный64-hex POSTGRES_PASSWORD, постоянные пути и порты.
`APP_ORIGIN` — канонический HTTPS origin того же `STORAGE_HOSTNAME`, без завершающего `/`;
нестандартный внешний порт укажите явно. `AUTH_CONFIG_FILE` — абсолютный путь к приватному JSON.
Для поставки готовых образов оба image reference должны иметь `@sha256:DIGEST`; OCI revision
каждого должен совпадать с APP_RELEASE. Смешивать digest и сборку нельзя.
При сборке требуется чистый checkout точного SHA. Env0600 принадлежит root или запускающему
пользователю; это данные без `export`, eval, `$`-подстановок и неизвестных ключей.

POSTGRES_PASSWORD и идентификаторы существующей БД сохраняются при обновлении. Изменение
env-пароля не меняет пароль существующей PostgreSQL-роли. Не публикуйте `compose config`,
полный container inspect или env: они содержат секреты.

## 6. TLS и операторский доступ

Администратор безопасно доставляет fullchain, private key и CA в пути из env.
Fullchain содержит leaf и intermediates; закрытый ключ600, родительские каталоги700.
SAN должен покрывать production DNS; preflight требует минимум7дней до истечения,
валидную CA-цепочку и совпадение публичных ключей cert/key.

```bash
sudo chmod 600 /etc/storage-control-plane/tls/privkey.pem
sudo chmod 644 /etc/storage-control-plane/tls/fullchain.pem /etc/storage-control-plane/tls/ca-chain.pem
sudoedit /etc/storage-control-plane/auth/auth.json
sudo chown 10001:10001 /etc/storage-control-plane/auth/auth.json
sudo chmod 600 /etc/storage-control-plane/auth/auth.json
```

Минимальный JSON для явно включённого аварийного локального входа:

```json
{"version":1,"origin":"https://storage.example.test","local_enabled":true}
```

Origin должен точно совпадать с `APP_ORIGIN`. Файл обычный, без symlink/hardlink, не больше
32KiB, UID10001 и mode0600. Он монтируется только в API; пароль технической AD-учётной
записи не передаётся через env. Пользователя создайте интерактивно после запуска по
[инструкции bootstrap](local-admin-ru.md); стандартной учётной записи нет.

Для LDAPS добавьте объект `ldap`: DNS `hostname`, `base_dn`, `bind_dn`, `bind_password`,
`ca_file` и `group_roles` (полный DN группы → список ролей). Допустимы роли `storage_admin`,
`storage_operator`, `auditor`, `analyst`, `viewer`. Проверяются сертификат, DNS-имя и цепочка
LDAPS636; незашифрованного fallback нет. В JSON используйте контейнерный путь
`/run/secrets/storage-console/directory-ca.pem`; внешний публичный CA задаётся через
`DIRECTORY_CA_FILE` (при отсутствии используется `TLS_CA_FILE`).
Публичный CA должен быть читаемым внутри контейнера UID10001: например, root-owned mode0644.
Родительский каталог на хосте остаётся700; bind mount открывается Docker. Не назначайте
CA права закрытого ключа0600. Отдельный DIRECTORY_CA_FILE имеет те же права чтения.
Техническая учётная запись должна иметь минимальные права чтения каталога;
её пароль храните только в этом приватном JSON.
Настройте доверие публичному CA на клиентах отдельным административным способом.
Не используйте `curl -k`; закрытый ключ CA на ВМ приложения не нужен.

## 7. Первый запуск и systemd

```bash
cd /opt/storage-control-plane
sudo bash deploy/scripts/preflight.sh /etc/storage-control-plane/production.env
sudo bash deploy/scripts/deploy.sh /etc/storage-control-plane/production.env
sudo install -m 644 deploy/systemd/storage-control-plane.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable storage-control-plane.service
sudo systemctl start storage-control-plane.service
```

Preflight проверяет ресурсы, NTP, Docker/Compose, файлы, DNS, TLS, auth и порты.
Deploy блокирует конкурирующие операции, проверяет образы и читает конфигурацию провайдеров
под UID10001 в изолированном контейнере без сети до остановки сервисов. Затем запускает PostgreSQL, останавливает
Web/API/worker, выполняет миграцию и запускает runtime после её успеха. Повторный запуск
сохраняет постоянные данные. Unit oneshot/RemainAfterExit: `active (exited)` означает успешное
завершение запуска; текущая работоспособность отдельно подтверждается healthcheck.

## 8. Миграции

Миграции выполняет отдельный контейнер `migrate` командой `alembic upgrade head`.
Не запускайте второй migrator или downgrade одновременно с приложением. При ошибке
миграции Web/API/worker остаются остановленными, PostgreSQL и постоянные файлы сохраняются.
Проверьте причину и совместимость выбранного release, затем повторите deploy.
Автоматического rollback схемы или восстановления БД нет.

## 9. Проверка работы

```bash
sudo bash deploy/scripts/healthcheck.sh /etc/storage-control-plane/production.env
curl --fail --cacert /etc/storage-control-plane/tls/ca-chain.pem https://storage.example.test/ready
curl --fail --cacert /etc/storage-control-plane/tls/ca-chain.pem https://storage.example.test/
```

Замените DNS примером своего контура. Healthcheck требует healthy PostgreSQL/API/worker/Web,
соответствующие фактические image ID/revision, только Web published ports, строгий TLS,
readiness200, anonymous Web200, anonymous read/me401 и canonical HTTP308→HTTPS. После входа оператор проверяет
страницы Web и read API; generic ready не доказывает правильность данных, collectors или Sentry.
Отсутствие DNS не обходится production-скриптами. Тестовые resolver/сертификаты применяются
только в изолированном smoke и не являются production-приёмкой.

## 10. Возврат предыдущего release

Сохраните текущий backup и точные SHA/image references перед обновлением. Для возврата
предыдущего кода сначала докажите его совместимость с текущей схемой и историей Alembic.
Checkout старого SHA и старые образы сами по себе не доказывают совместимость. Если старый
migrator не распознаёт текущую revision, deploy завершится отказом.

При совместимой схеме остановите unit, выберите проверенный checkout/images/env release
и повторите deploy/start по процедуре обновления. При несовместимой схеме восстановление
проверенного соответствующего backup выполняется в согласованном maintenance-окне:
оно теряет изменения БД после момента backup. Нельзя автоматически downgrade или restore
в ответ на ошибку запуска. Не переписывайте Git history ради rollback.

## 11. Backup PostgreSQL

```bash
cd /opt/storage-control-plane
sudo bash deploy/scripts/backup-postgres.sh /etc/storage-control-plane/production.env
```

Сохраните напечатанный путь `backup-ID`. Архив содержит custom pg_dump и manifest с размером,
SHA256, проектом/БД и настроенным APP_RELEASE. Он публикуется атомарно после fsync и проверки
TOC; неуспешный dump не продвигается. Снимок pg_dump внутренне согласован при текущих записях.
APP_RELEASE не является доказательством совместимости схемы. Архив включает управляемую
схему public; другие схемы, TLS/env, роли PostgreSQL,
diagnostics, внешние shares и архивы источников в этот dump не входят.
Копируйте backup за пределы ВМ защищённым каналом; не удаляйте старый до проверенного restore.
Не загружайте DB dump в Git, публичный CI artifact или обращение поддержки.

## 12. Restore PostgreSQL

Restore выполняется только после явного разрешения перезаписи выбранной БД и выбора
совместимого release. Сначала остановите unit и исключите внешние подключения-писатели.
PostgreSQL должен работать; при остановке всего unit запустите только его:

```bash
sudo systemctl stop storage-control-plane.service
sudo PYTHONPATH=/opt/storage-control-plane python3 - <<'PY'
from pathlib import Path
from deploy.scripts.environment import load_environment
from deploy.scripts.commands import Compose
v = load_environment(Path('/etc/storage-control-plane/production.env'))
Compose(v).call('up', '-d', '--wait', '--wait-timeout', '120', 'postgres', timeout=150)
PY
sudo bash /opt/storage-control-plane/deploy/scripts/restore-postgres.sh \
  /etc/storage-control-plane/production.env \
  /var/backups/storage-control-plane/backup-ID \
  --confirm storage-control-plane/storage_console
```

Архив должен лежать непосредственно в BACKUP_DIR, иметь700/600 и совпадающие проект/БД,
размер/SHA256. Импортируйте только доверенные собственные архивы: SQL выполняется с правами
владельца БД. После проверки скрипт останавливает Web/API/worker, сохраняет safety-backup
текущей БД. pg_restore полностью преобразует архив public в приватный SQL до изменения БД;
затем psql заменяет всю public schema и восстанавливает данные/историю Alembic внутри одной
транзакции с ON_ERROR_STOP. Без успешного safety-backup restore не начинается. Ошибка SQL
откатывает всю транзакцию, runtime остаётся остановленным. Позднее добавленные migration
tables удаляются; весь кластер не пересоздаётся. БД выделена приложению: посторонние схемы,
объекты и зависимости на public не допускаются. Для render SQL/safety-backup нужно свободное
место сверх исходного dump. При timeout проверьте pg_stat_activity и завершение серверной операции
перед последующим запуском. Проверьте восстановленные данные/схему, затем выполните deploy
и start unit. Safety-backup остаётся до отдельной проверки результата.

## 13. Обновление

```bash
sudo bash /opt/storage-control-plane/deploy/scripts/backup-postgres.sh \
  /etc/storage-control-plane/production.env
sudo systemctl stop storage-control-plane.service
cd /opt/storage-control-plane
sudo git fetch origin
sudo git checkout --detach VERIFIED_RELEASE_SHA
sudoedit /etc/storage-control-plane/production.env
sudo bash deploy/scripts/preflight.sh /etc/storage-control-plane/production.env
sudo systemctl start storage-control-plane.service
sudo bash deploy/scripts/healthcheck.sh /etc/storage-control-plane/production.env
```

VERIFIED_RELEASE_SHA — проверенный полный SHA, а env APP_RELEASE/API_IMAGE/WEB_IMAGE
обновляются согласованно. Сохраните пароль/БД/project/state paths; изучите миграции и
результаты CI заранее. После обновления подтвердите данные, actual images и Web.
При незавершённой миграции не запускайте старый runtime без проверки совместимости.

### Переход с foundation named volume на production bind storage

Это отдельная maintenance-процедура для существующей foundation-инсталляции.
До остановки подготовьте новый чистый checkout, production env/TLS/auth/DNS и пустой
STATE_DIR/postgres по разделам1–6. Сохраните прежний checkout, его env и named volume.
В production env сохраните прежние PROJECT_NAME, POSTGRES_USER и POSTGRES_DB:
backup/restore намеренно запрещает смену проекта/БД. BACKUP_DIR должен быть вне checkout.
Для новой пустой PostgreSQL-инсталляции можно выбрать новый пароль; восстановление
public schema не переносит роли и их пароли. Это не смена пароля существующей роли.

1. В прежнем checkout остановите только `web api worker` через прежний Compose/env/project.
   PostgreSQL оставьте работающим. Исключите других писателей и автоматический restart
   старого systemd unit. Не допускайте записей между финальным backup и переносом.
2. Из нового checkout выполните `backup-postgres.sh` с подготовленным production env.
   Фиксированный Compose wrapper адресует уже работающий PostgreSQL того же PROJECT_NAME;
   эта команда не запускает/не заменяет контейнер. Проверьте manifest/проект/БД и сохраните
   архив вне ВМ. APP_RELEASE в manifest — настроенный новый release; исходную Git/Alembic
   revision фиксируйте отдельно в приватном протоколе переноса.
3. Выполните `stop.sh` с production env. Постоянный старый named volume сохраняется.
   Запустите только `postgres` по Python-команде раздела12: Compose заменит его контейнер
   на production service с новым bind-каталогом. Перед restore проверьте фактический mount
   и что это новая пустая БД, а не прежний named volume или чужая инсталляция.
4. Восстановите финальный архив командой раздела12 с точным `--confirm PROJECT_NAME/POSTGRES_DB`.
   Safety-backup пустой целевой public schema также сохраняется. Проверьте исходную
   Alembic revision и ожидаемые данные до запуска миграций.
5. Выполните production deploy и проверки раздела9. Миграции должны распознать исходную
   revision и сохранить данные. Подключайте unit только к новому checkout/env.
   Старый named volume не удаляйте до завершения приёмки и проверки внешней копии backup.

Репетиция переноса выполняется в отдельном Compose-проекте/каталоге и на loopback-портах,
без изменения основной БД. Копию source dump можно импортировать непосредственно в
свежую изолированную БД инструментами PostgreSQL с явной проверкой обеих целей; это не
основание изменять manifest или отключать project guards production restore CLI.
Проверено восстановление foundation revision0001 в bind storage и миграция до0003
с сохранением heartbeat-данных. Изолированный HTTPS probe с явным client resolver проверяет
сертификат, но не закрывает gate настоящего DNS и клиентского браузерного доверия.

## 14. Журналы и диагностика

```bash
sudo systemctl status storage-control-plane.service --no-pager
sudo journalctl -u storage-control-plane.service -n 50 --no-pager
```

Для Compose используйте фиксированный файл и валидированный env через Python wrapper,
не `source production.env`. Например, замените вызов выше для PostgreSQL на
`Compose(v).call('logs', '--tail', '50', 'api', 'worker', 'web')` и напечатайте результат
только в приватном административном терминале. CLI скрывает stderr команд, чтобы случайно
не вывести secrets. Журналы Docker ограничены10MiB×3 на сервис; Nginx access log отключён.
Перед передачей логов удалите credentials, DSN, пользовательские данные и внутреннюю топологию.
Не считайте успех systemd или `/ready` подтверждением внешних интеграций.

## 15. Sentry, Sonar и границы приёмки

SENTRY_DSN задаётся приватно в env; отсутствие DSN оставляет интеграцию выключенной.
Проверяйте реальное принятие события/trace, APP_RELEASE/environment и отсутствие персональных
данных отдельным согласованным тестом. Указание DSN не является доказательством доставки.

GitHub CI запускает backend/frontend/Compose/secrets. Для Sonar нужны repository variable
SONAR_HOST_URL и secret SONAR_TOKEN; без URL job пропускается. Skipped не равен успешному
quality gate. Внешний Sonar/live Sentry, полные продуктовые auth/roles и чистая Ubuntu install
остаются самостоятельными приёмочными пунктами. Документация и Git publication не означают
обновления работающей ВМ: фиксируйте фактический SHA, images, состояние сервисов, данные,
строгий клиентский HTTPS и результат backup/restore отдельно.
