# Первый живой Windows FILESERVER pilot

Граница MVP-PILOT-001: один явно выбранный local root, metadata-only,
operator CLI → strict HTTPS → API/PostgreSQL → русская Web Console.
Никаких Windows Service, USN, audit policy, ACL/SMB изменений или Discovery.
Автоматизированный disposable acceptance не заменяет operator acceptance реального FILESERVER.

## 1. Предварительные условия

Central stack настроен по [deployment runbook](../deployment/runbook-ru.md):
PostgreSQL 16+, migrations head, API, worker, Web, канонический HTTPS DNS origin,
доверенный сертификат, пользователь `storage_admin`. Пароли пользователей и ключи
collectors независимы. Основной сервер обновляет оператор, Codex не получает production access.

На FILESERVER: Windows, Python 3.13 x64 с `py -3.13`, Git для сборки wheel,
сеть до HTTPS origin, публичная CA chain в PEM. Откройте PowerShell **от администратора**:
существующий ProtectedState требует SYSTEM/Administrators. Учётная запись должна
читать metadata выбранного root; сканирование не повышает права доступа к данным.
Часы central/FILESERVER синхронизированы. Root — существующий ограниченный локальный
каталог, не UNC, не reparse point, не весь диск или всё дерево departments.
State и scope не могут содержать друг друга.

## 2. Обновить central до проверенного main

Для существующего production deployment выполняйте на central ВМ (пути — шаблон
из deployment runbook; используйте свои уже настроенные пути):

```bash
set -e
cd /opt/storage-control-plane
test -z "$(git status --porcelain)"
read -r -p 'Полный SHA принятого commit: ' PILOT_SHA
sudo git fetch origin
git merge-base --is-ancestor "$PILOT_SHA" origin/main
sudo bash deploy/scripts/backup-postgres.sh /etc/storage-control-plane/production.env
sudo systemctl stop storage-control-plane.service
sudo git checkout --detach "$PILOT_SHA"
sudoedit /etc/storage-control-plane/production.env
sudo bash deploy/scripts/preflight.sh /etc/storage-control-plane/production.env
sudo systemctl start storage-control-plane.service
sudo bash deploy/scripts/healthcheck.sh /etc/storage-control-plane/production.env
git rev-parse HEAD
```

В `sudoedit` согласованно установите `APP_RELEASE=<PILOT_SHA>`,
`API_IMAGE=storage-console-api:<PILOT_SHA>`, `WEB_IMAGE=storage-console-web:<PILOT_SHA>`.
Deploy существующего unit собирает образы чистого checkout, мигрирует и проверяет runtime.
Сохраните текущие DB credentials, project/state paths, origin и TLS. Не запускайте `down -v`.
Первое развёртывание, которое ещё не настроено, выполняется по полному deployment runbook.

## 3. Source, Windows collector и одноразовый ключ

1. Войдите в HTTPS Web Console как `storage_admin`, язык — русский.
2. **Источники данных** → тип `FILESERVER`, имя узла — реальное имя FILESERVER,
   идентификатор экземпляра — стабильная выбранная оператором identity этого источника.
   Нажмите **Зарегистрировать источник**.
3. В карточке source нажмите **Зарегистрировать collector**, тип `WINDOWS`.
4. Скопируйте collector UUID и одноразовый ключ из блока **Одноразовый показ ключа**.
   До heartbeat источник имеет `UNKNOWN` / «Нет данных» — это ожидаемо.
5. Не обновляйте страницу до копирования ключа; если ключ потерян, используйте
   **Обновить ключ**. Никогда не вставляйте ключ в argv, командную историю или Git.
   Activation локальная: новый enrollment protocol/дополнительный remote activate не нужен.

## 4. Trusted CA и установленный wheel на FILESERVER

Передайте FILESERVER только публичную CA chain (`.pem`), проверив её источник.
Закрытый ключ CA или HTTPS-сервера сюда не переносится. Origin должен совпадать с
DNS SAN сертификата. Браузеру доверие CA настраивается обычным административным способом;
CLI получает CA отдельно через `--ca`. TLS verification отключать нельзя.

В elevated PowerShell, заменяя параметры через prompts, не через публичные файлы:

```powershell
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$PilotSha = Read-Host 'Полный SHA принятого commit'
$Source = 'C:\Temp\storage-console-pilot-source'
$CliHome = Join-Path $env:ProgramData 'Sosnadmin\StorageCollectorCli'
$State = Join-Path $env:ProgramData 'Sosnadmin\StorageCollector'
if (Test-Path -LiteralPath $Source) { throw 'Выберите новый каталог для pilot checkout' }
New-Item -ItemType Directory -Force -Path (Split-Path $Source), (Split-Path $State) | Out-Null
git clone https://github.com/BorisDruzak/storage-console.git $Source
if ($LASTEXITCODE -ne 0) { throw 'Clone failed' }
Set-Location $Source
git checkout --detach $PilotSha
if ($LASTEXITCODE -ne 0) { throw 'Checkout failed' }
py -3.13 -m venv $CliHome
if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 / venv failed' }
$Python = Join-Path $CliHome 'Scripts\python.exe'
& $Python -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Dependencies failed' }
& $Python -m pip wheel --no-deps --wheel-dir dist .
if ($LASTEXITCODE -ne 0) { throw 'Wheel build failed' }
$Wheel = Get-Item -LiteralPath (Join-Path $Source 'dist\storage_console-0.1.0-py3-none-any.whl')
& $Python -m pip install --no-deps --force-reinstall $Wheel.FullName
if ($LASTEXITCODE -ne 0) { throw 'Wheel install failed' }
$env:Path = (Join-Path $CliHome 'Scripts') + ';' + $env:Path
Set-Location $env:TEMP
storage-collector --help
if ($LASTEXITCODE -ne 0) { throw 'Installed entrypoint failed' }
```

Команда теперь запускает установленный wheel вне source checkout. Должны быть
четыре команды: `activate`, `status`, `inventory-once`, `run`.
Путь установки CLI не содержит collector credential. Existing pilot venv допускает
повторную установку wheel; смена scope требует отдельного state и отдельного collector.

## 5. Activate, status, inventory-once

В той же elevated PowerShell:

```powershell
$CollectorId = Read-Host 'Collector UUID из Web Console'
$Origin = Read-Host 'Канонический HTTPS origin без пути и query'
$Ca = Read-Host 'Полный путь к публичной CA chain PEM'
$Root = Read-Host 'ОДИН ограниченный существующий local root на FILESERVER'
storage-collector activate --state $State --collector-id $CollectorId --origin $Origin --ca $Ca --root $Root
if ($LASTEXITCODE -ne 0) { throw 'Activation failed' }
storage-collector status --state $State
if ($LASTEXITCODE -ne 0) { throw 'Status failed' }
storage-collector inventory-once --state $State --scan-seconds 600 --settle-seconds 60
if ($LASTEXITCODE -ne 0) { throw 'Inventory incomplete or not delivered; inspect status' }
storage-collector status --state $State
if ($LASTEXITCODE -ne 0) { throw 'Status failed' }
```

Ключ вводится в скрытый prompt activation. При недоступном secure prompt команда
завершается ошибкой, не переходит к вводу с echo. Для автоматизированного acceptance
есть `--key-stdin`: ключ поступает из приватного pipe, никогда из argv или plaintext-файла.

Status: collector UUID, origin hostname, один root, `Protected config: OK (DPAPI)`,
pending/quarantine counts, auth suspension, inventory/heartbeat checkpoint.
Ни token/ciphertext, ни root, ни paths/payload/CA contents не печатаются.
Status не создаёт и не мигрирует SQLite, не расшифровывает token и не снимает suspension.
Во время `run` state занят: сначала Ctrl+C, затем status.

Успех `inventory-once`: exit `0`, «Инвентаризация завершена», metadata count > 0,
inventory batches > 0, pending `0`, ошибок `0`, inventory `completed=True`,
heartbeat revision > 0. Metadata count включает volume и файлы/каталоги; это не
тот же счётчик, что filesystem objects в UI. Sent count включает heartbeat и ранее
накопленную очередь. Partial scan, quarantine/auth failure или недоставленная очередь
возвращают `1`; неверные аргументы — `2`; остановка оператором — `130`.
Scan ограничен `--scan-seconds`, settlement — `--settle-seconds`; текущий bounded HTTPS
request/child stop может добавить до transport/stop budget к deadline.
Partial metadata сохраняется, но успех не заявляется. Повторный scan той же identity
не создаёт duplicate logical objects; это не USN и не доказательство удаления по отсутствию.

## 6. Что увидеть в русской Web Console

Сразу после успешного scan обновите страницу:

- **Источники данных**: FILESERVER, «Исправно» (`HEALTHY`) для **freshness**,
  в карточке — время heartbeat и collector count `1`. `lag/cursor` могут быть
  «Не определено»: этот inventory provider их не публикует.
- **Обзор → Ёмкость**: источники > 0, тома > 0, объекты файловой системы > 0.
- Карточка source → **Тома**: source filter уже установлен; реальный `volume:<GUID>`,
  filesystem (`NTFS`/поддерживаемая ОС filesystem), label, capacity/free и mount aliases.
  Drive letter — alias, а не canonical identity. Значения сохраняются после reload.
- **Общие папки SMB** пусты, shares `0`: текущий native provider не emits share metadata.
  Это разрешённое ограничение пилота, не synthetic data.
- Общий health и неполученные domains могут оставаться `UNKNOWN` / «Нет данных».
  Fresh heartbeat не доказывает здоровье storage, backup, SMB или ACL.

API доступен через текущую пользовательскую сессию; не переносите collector key
в browser console. Реальные paths/volume identity/label допустимы только внутри своего контура.

## 7. Foreground runtime и остановка

```powershell
storage-collector run --state $State
# Для остановки нажмите Ctrl+C и дождитесь «Runtime остановлен».
# Затем:
storage-collector status --state $State
```

Runtime использует существующие независимые heartbeat/delivery/capture, durable outbox,
heartbeat каждые 30 секунд и inventory раз в 3600 секунд. Не daemonize и не install service.
Ctrl+C инициирует bounded graceful shutdown; shell exit code `130` ожидаем.
После выхода можно повторить `inventory-once`, чтобы доставить оставшийся backlog.
После one-shot без runtime freshness закономерно устаревает согласно policy.

## 8. Troubleshooting

| Симптом | Действие оператора |
|---|---|
| `INVALID_CONFIG`, `TLS`, `TIMEOUT`, `NETWORK` | Проверить origin DNS/SAN, публичную CA chain, время и HTTPS reachability; не отключать verification. CA должна быть PEM без private key. |
| `AUTH_REQUIRED`, auth suspended после 401/403 | Проверить enabled collector/правильный UUID, получить новый key через UI и повторить activate с тем же identity/root. Status/run не снимают suspension. |
| `INVALID_SCOPE`, `NOT_FOUND`, `NOT_DIRECTORY`, `REPARSE_POINT` | Выбрать существующий ограниченный local directory; UNC, весь диск и overlap со state запрещены. Изменение принятого scope требует нового collector/state. |
| `ACCESS_DENIED`, partial scan | Проверить metadata read rights выбранного root, выбрать доступный меньший scope; CLI не изменяет ACL. Exit `1` остаётся ошибкой даже при доставке части metadata. |
| `PENDING_OUTBOX`, `CAPACITY`, `SCAN_TIMEOUT` | Исправить доставку или уменьшить scope, затем повторить inventory-once с тем же state. Не удалять SQLite; accepted replay idempotent. |
| Quarantined > 0 | Проверить fixed code/API compatibility; нельзя считать pilot успешным. Не публиковать payload и не снимать quarantine вручную. |
| `STATE_BUSY`, `UNSAFE_STATE`, `CREDENTIAL_MISMATCH` | Остановить свой foreground process; использовать elevated PowerShell и локальный защищённый state. После binding failure повторить activate с прежним identity/root. Не ослаблять DACL. |

## 9. Cleanup и operator acceptance

Сначала остановите foreground, убедитесь в pending `0` и quarantine `0`, затем
отключите pilot collector в UI. Центральные evidence/history остаются в PostgreSQL.
Удаление локального state теряет backlog и DPAPI credential; только для завершённого pilot:

```powershell
$ExpectedState = [IO.Path]::GetFullPath((Join-Path $env:ProgramData 'Sosnadmin\StorageCollector'))
$ActualState = [IO.Path]::GetFullPath($State)
if ($ActualState -ne $ExpectedState) { throw 'Cleanup target differs from this runbook pilot state' }
Get-Item -LiteralPath $ActualState
Remove-Item -LiteralPath $ActualState -Recurse -Force
```

Если используется отдельный custom state, оператор проверяет именно его абсолютный
путь перед удалением. CLI/исходники можно сохранить; новых служб нет.

- [ ] Central проверенного main SHA deployed и healthcheck прошёл.
- [ ] FILESERVER source, WINDOWS collector и одноразовый key созданы в UI.
- [ ] Activated, status OK, inventory-once exit 0.
- [ ] Pending 0, quarantine 0, auth suspension нет, complete inventory checkpoint.
- [ ] FILESERVER fresh, реальный volume/filesystem, object count > 0 видны.
- [ ] Reload сохраняет данные; operator acceptance реального root подтверждён.

Публиковать можно только counts, generic FILESERVER role, timestamps и pass/fail.
Нельзя публиковать production origin/IP/topology, usernames, SID, реальные paths,
volume/collector identities, keys, config/ciphertext/outbox, CA private keys, screenshots
с реальными данными или diagnostic payload. Issue не закрывается только по source/CI tests.
После этой проверки STOP; следующий scope определяется отдельно.

## 10. Проверка MVP-PILOT-002 на уже подключённом FILESERVER

После отдельного согласованного deployment версии с MVP-PILOT-002:

1. Откройте console в новом/чистом browser profile. Default locale ru-RU,
   timezone `Asia/Yekaterinburg` (+05); сохранённые preferences не перезаписываются.
2. При работающем foreground collector откройте Overview: sources, volumes и
   filesystem objects > 0, heartbeat freshness актуальна. Карточка «Ёмкость»
   показывает реальные used/free/total в IEC, процент, current/total volumes,
   count без актуальной ёмкости и время последней инвентаризации.
3. Проверьте состояние по худшему current volume: <70% «Исправно», 70–<80%
   «Наблюдение», 80–<90% «Предупреждение», >=90% «Критично». Summary percentage
   рассчитан по суммарным bytes и может быть ниже заполненности худшего тома.
4. В «Состояние хранилища» → «Тома» проверьте существующий DATA volume:
   filesystem и mount alias сохранены, total/free читаемые, quality «Полные данные»
   пока inventory младше `INVENTORY_STALE_SECONDS` (default 2 часа), даже через
   пять минут после inventory при heartbeat cadence 60 секунд.
5. Overview filesystem показывает NTFS, число томов и inventory time, но integrity
   остаётся «Нет данных». Неподдерживаемые domains и overall без evidence не зелёные.
6. Reload сохраняет данные. В «Настройки» выберите UTC, сохраните и повторите reload:
   время станет UTC и preference сохранится. DB timestamps по-прежнему UTC.

При stale/partial/unavailable inventory его capacity исключается из current totals.
Если ни одного пригодного измерения нет, capacity «Нет данных», bytes не определены.
HTTP evidence остаётся ограниченным максимум 35 секундами; истёкший ответ требует
refresh, даже если inventory policy составляет 2 часа. Не останавливайте и не
перенастраивайте live collector ради этой проверки.

Source/CI acceptance не заменяет live operator acceptance после deployment.
