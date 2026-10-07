# Codex Task — MVP-PILOT-001: первый живой FILESERVER → Storage Console

Приоритет: немедленный
Тип: вертикальный MVP / live pilot
Base revision: 758e526b8cbbbe9614739fcc13016f3e9edc3d2f или более новый main без расширения scope.

Основные требования:
- docs/spec/storage-control-plane-v0.1.md
- AGENTS.md

## 1. Цель

Замкнуть первый реальный end-to-end vertical slice:

~~~text
Storage Console
  ↓
storage_admin регистрирует FILESERVER source + Windows collector
  ↓
получает одноразовый collector key
  ↓
на FILESERVER запускается операторский CLI
  ↓
collector активируется
  ↓
однократно сканирует ОДИН ограниченный реальный scope
  ↓
heartbeat + inventory доставляются через HTTPS
  ↓
API сохраняет их в PostgreSQL
  ↓
пользователь видит реальные данные в русской Web Console
~~~

Главный результат задачи — не новый слой hardening, а видимые реальные данные.

## 2. Причина

В main уже есть:
- API/PostgreSQL/worker;
- русская Web Console;
- auth/RBAC;
- source/collector management;
- durable SQLite outbox;
- strict HTTPS delivery;
- Windows native inventory provider;
- Windows foreground Runtime.

Но операторского пути "взял collector key → запустил на FILESERVER → увидел данные" пока нет.

## 3. Жёсткий scope

В этой задаче реализовать только:

1. installable Windows CLI;
2. activate;
3. status;
4. inventory-once;
5. foreground run;
6. русский pilot runbook;
7. только минимальные UI/API изменения, если без них нельзя явно увидеть real ingest;
8. end-to-end acceptance через существующий HTTPS/API/PostgreSQL/Web stack.

НЕ реализовывать:

- Windows Service / SCM;
- USN;
- 4663/5145;
- ACL collector;
- VSS collector;
- telemetry collector;
- PVE collector;
- PBS collector;
- SMB operational collector;
- diagnostics runtime;
- Data Discovery;
- MCP;
- autonomous remediation;
- новую auth architecture;
- новый generic hardening framework;
- full 500k-object performance work;
- полный scan всего FILESERVER.

Unrelated defects записывать как follow-up и не исправлять в рамках этой задачи.

## 4. Pilot scope

Первый live pilot работает на одном явно заданном local root.

Никаких production path в Git.

Оператор задаёт root при activation, например:

~~~text
D:\Shares\Departments\<pilot-scope>
~~~

Первый pilot не должен сканировать весь D:\Shares\Departments.

## 5. CLI

Добавить installable entrypoint, предпочтительно:

~~~text
storage-collector
~~~

Минимальные команды:

~~~text
storage-collector activate
storage-collector status
storage-collector inventory-once
storage-collector run
~~~

Использовать stdlib argparse или текущий dependency set. Не вводить новый CLI framework без необходимости.

## 6. activate

Пример UX:

~~~powershell
storage-collector activate --state "C:\ProgramData\Sosnadmin\StorageCollector" --collector-id "<uuid>" --origin "https://<storage-console-host>" --ca "C:\Temp\storage-console-ca.pem" --root "D:\Shares\Departments\<pilot-scope>"
~~~

Collector key:
- не передавать обязательным argv-параметром;
- не сохранять plaintext;
- читать через secure prompt/stdin;
- использовать уже реализованный DPAPI/protected configuration path.

Команда должна:
1. проверить Windows;
2. проверить local root;
3. проверить CA/origin;
4. активировать protected state;
5. вывести краткое безопасное подтверждение;
6. не печатать token/evidence payload.

Не строить новый enrollment protocol: использовать существующий source/collector management.

## 7. status

Команда storage-collector status — быстрый read-only status.

Показать по-русски:
- collector ID;
- configured origin hostname;
- количество scope roots;
- protected config state;
- pending batches;
- quarantined batches;
- auth suspended;
- inventory checkpoint;
- heartbeat checkpoint;
- последний безопасный runtime summary, если он уже доступен.

Не показывать:
- token;
- encrypted token;
- batch payload;
- CA contents;
- file paths из inventory.

## 8. inventory-once

Ключевая MVP-команда.

Она должна:
1. load protected config;
2. выполнить один native inventory scan configured scope;
3. использовать существующий outbox;
4. доставить inventory batches;
5. доставить heartbeat;
6. дождаться bounded settlement;
7. сама завершиться;
8. вернуть exit code 0 только при complete + delivered.

Пример понятного summary:

~~~text
Инвентаризация завершена
Объектов: 1248
Пакетов: 6
Отправлено: 6
В очереди: 0
Ошибок: 0
~~~

Windows Service для этого не нужен.

## 9. run

Команда storage-collector run использует существующий foreground Runtime.

Требования:
- foreground;
- Ctrl+C → graceful bounded shutdown;
- heartbeat независим от inventory;
- existing durable outbox/delivery;
- no daemonization;
- no Windows Service;
- никаких изменений audit policy / SMB / ACL.

## 10. Packaging

После установки wheel команда должна быть доступна напрямую.

Использовать project.scripts или эквивалент.

Acceptance проверяет installed wheel, а не только source checkout.

## 11. Видимый результат в Web Console

Не делать redesign.

После real ingest пользователь должен увидеть:

### Источники данных
- FILESERVER;
- fresh/online state после heartbeat;
- heartbeat timestamp;
- collector count;
- lag/freshness.

### Обзор
Минимально:
- Sources > 0;
- Volumes > 0;
- Filesystem objects > 0;
- Shares > 0, если Windows inventory provider реально публикует share metadata.

### Existing storage/read views
Показывать реальные:
- volume identity;
- filesystem;
- label/capacity, если contract поддерживает;
- share metadata;
- никакой synthetic/demo production data.

Если current UI не позволяет очевидно увидеть real inventory, разрешена ОДНА минимальная доработка:
- per-source inventory counts;
или
- очевидная source → volumes/shares связь.

Не строить новый dashboard.

## 12. Public repository boundary

Не коммитить:
- production IP;
- production origin;
- реальные usernames;
- SID;
- реальные file paths;
- collector key;
- diagnostic payload.

Допустимое sanitized evidence:
- counts;
- source type;
- generic FILESERVER role/name;
- timestamps;
- pass/fail;
- redacted UUID.

## 13. Русский pilot runbook

Создать:

~~~text
docs/pilot/windows-live-pilot-ru.md
~~~

Обязательно описать:
1. prerequisites;
2. deploy/update current main;
3. создать FILESERVER source через UI;
4. создать Windows collector;
5. получить one-time key;
6. подготовить trusted CA;
7. установить wheel на FILESERVER;
8. activate;
9. status;
10. inventory-once;
11. проверить UI;
12. run;
13. Ctrl+C stop;
14. troubleshooting: TLS trust, 401/403, invalid scope, ACCESS_DENIED, pending outbox;
15. cleanup local pilot state;
16. что нельзя публиковать.

Команды copy/paste-ready.

## 14. Automated end-to-end acceptance

### Central
Fresh disposable stack:
- PostgreSQL;
- migrations head;
- API;
- worker;
- web;
- HTTPS.

### Source
Через настоящий management flow:
- создать FILESERVER source;
- создать Windows collector;
- получить one-time key.

### Windows
На настоящем Windows integration environment:
1. install wheel;
2. activate;
3. status;
4. inventory-once;
5. scan bounded local tree;
6. strict HTTPS delivery;
7. PostgreSQL receives heartbeat + inventory.

### Database
Подтвердить:
- source exists;
- heartbeat exists;
- volume exists;
- filesystem_objects > 0;
- share rows, если provider их emits;
- replay не создаёт duplicate logical objects.

### Browser
Через реальный Playwright/browser:
- login;
- Источники данных;
- source fresh;
- Overview non-zero counts;
- volume/read data;
- reload retains real data.

## 15. Operator acceptance

Задача не считается окончательно закрытой только unit/integration tests.

Codex должен закончить точными командами для реального FILESERVER pilot, но не получать production access самостоятельно.

Checklist:

~~~text
[ ] central current main deployed
[ ] FILESERVER source created
[ ] collector created
[ ] one-time key received
[ ] collector activated
[ ] status OK
[ ] inventory-once exit 0
[ ] pending outbox = 0
[ ] FILESERVER fresh in UI
[ ] real volume visible
[ ] real inventory counts visible
[ ] filesystem objects > 0
~~~

## 16. Tests — только нужные MVP

CLI:
- bad platform/config/scope rejected;
- token absent from argv/repr/output;
- status safe;
- inventory-once success;
- inventory-once partial/error;
- Ctrl+C graceful;
- installed wheel entrypoint.

Integration:
- collector → HTTPS → PostgreSQL;
- lost ACK remains idempotent;
- heartbeat changes freshness from UNKNOWN;
- inventory appears in read API.

Web:
- non-zero real-data contract;
- source freshness;
- volume/share display;
- reload.

Не добавлять unrelated combinatorial hardening tests.

## 17. CI

Existing gates должны остаться зелёными:
- backend;
- frontend;
- compose-smoke;
- production-smoke;
- secrets.

Sonar:
- если configured → PASS required;
- если not configured → явно report SKIPPED;
- не заявлять Sonar PASS при skipped job.

## 18. STOP CONDITION

После MVP-PILOT-001 остановиться.

Не переходить автоматически к:
- Windows Service;
- USN;
- attribution;
- PVE/PBS;
- ACL;
- diagnostics;
- Discovery.

Финальный отчёт должен содержать только:
1. commits;
2. CI;
3. что теперь видно в UI;
4. точные live-pilot команды;
5. известные ограничения;
6. следующую задачу только как предложение.

## 19. Definition of Done

MVP-PILOT-001 выполнен, когда можно честно сказать:

"Мы запускаем одну команду на Windows, реальные metadata доходят через HTTPS до PostgreSQL, и пользователь видит реальные FILESERVER inventory/freshness данные в русской Web Console."

Не считать DoD выполненным только по unit/integration tests.

Ключевой результат — видимый end-to-end data flow.
