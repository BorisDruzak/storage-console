# STORAGE-AUDIT-001 — Windows Security Audit Collector + корреляция с NTFS USN

Статус: ТЗ для Codex. НЕ реализовано. Репозиторий: BorisDruzak/storage-console.

## 0. Цель и явные границы

Создать **отдельный от существующего USN Collector контур доказательств**, позволяющий установить, **какая учётная запись** использовала доступ к файлу, через какой Windows logon session и, когда это подтверждается журналом, с какого клиентского IP/компьютера. Подтверждённые Windows Security Events связывать с уже сохранёнными USN CREATE/WRITE/RENAME/DELETE; не приписывать пользователю действие только потому, что доступ и USN появились рядом по времени.

~~~text
FILESERVER
  существующая служба SosnadminStorageCollector -> USN / FileId / change_events
  новая независимая SosnadminStorageAudit -> Security Events 4663,4660,4624
                            | own bookmark + encrypted state + durable outbox
                            v
                    strict HTTPS / PostgreSQL
                            |
       immutable audit evidence + event correlation + explicit uncertainty
                            |
             Web Console: «Источники и подтверждения»
~~~

**Не входит в задачу:** версии/восстановление содержимого файлов; Windows Event Forwarding (WEF), SIEM/отдельный централизованный EVTX archive; Event ID 5145; массовый аудит всех отделов; изменение содержимого файлов; автоматическая реакция/блокировки/ремедиация; 72-часовой повторный USN soak.

## 1. Сверить код и текущие задачи до разработки

Изучить актуальный main и реально развёрнутые версии (не подменять deployed SHA локальным HEAD):
- docs/spec/storage-control-plane-v0.1.md, docs/acceptance/usn-soak-001.md;
- Issue #22 и docs/tasks/mvp-005-history-and-statistics.md — там параллельно развивается чувствительная история и права;
- collectors/windows/{service,scm,security,runtime,usn_state}.py;
- collectors/common/{outbox,transport,delivery}.py;
- packages/contracts/{events,changes,read,sources}.py;
- packages/shared/models/activity.py; packages/shared/ingest/activity.py;
- apps/api/{ingest,read/activity,read/sources,source_control/registry,user_auth/sessions}.py;
- Alembic и Windows/PG/Web tests; AGENTS.md/runbooks.

Сейчас EvidenceRecord знает WINDOWS_4663, WINDOWS_4660, WINDOWS_5145, COLLECTOR, но не WINDOWS_4624; существующая таблица collector_events сохраняет свидетельства, но реальной Windows Security ingestion и correlation engine ещё нет.

**Архитектурная ловушка:** apps/api/read/sources.py считает общую freshness с учётом всех enabled collectors; apps/api/read/activity.py считает непрерывный USN только при collector_count == 1. Регистрация второго Audit Collector без разделения ролей может превратить корректную USN Activity в UNKNOWN. Исправить и проверить это ДО подключения новой службы. Нельзя создавать фиктивный дублирующий FILESERVER source для обхода.

Исходный 72h USN-SOAK-001 остаётся FAIL; исправления PR #20/#21 не дают права объявить long-term PASS. Этот task не повторяет soak.

## 2. Источники и уровни доказательности

**4663**: Windows учётная запись использовала access right к объекту с ObjectName/ObjectType/AccessMask, SubjectLogonId, SID, HandleId и ProcessId/Name при наличии. Это **не** математическое доказательство, что ровно этот пользователь породил USN WRITE; 4663 фиксирует использование права на объект.

**4660**: объект действительно удалён, но ObjectName отсутствует. Допустима осторожная связка с 4663 через nonzero HandleId + тот же host/boot epoch + logon ID + process + время/порядок, иначе путь/исполнитель UNKNOWN. 4663 DELETE access не доказывает удаление: такое право может использоваться и при rename.

**4624**: создана успешная logon session; Type 3 — network logon. TargetLogonId может связываться с SubjectLogonId; SourceNetworkAddress и WorkstationName могут отсутствовать или быть неприменимыми. По IP нельзя достоверно восстановить имя физического ПК и тем более человека за ним.

**USN**: время, canonical volume, FileId, тип изменения, old/new path; пользователя или IP в USN нет.

Классы вывода:
- ACCESS_OBSERVED — сам факт Windows audit access известной учётной записи;
- CORRELATED_HIGH — единственный сильный кандидат с доказанной связкой, при подходящем AccessMask/файле/контексте/порядке; результат **обоснованная атрибуция**, не юридически доказанная личность;
- AMBIGUOUS — несколько кандидатов, alias/handle reuse, общий пользователь, неясный путь/время;
- UNKNOWN / NOT_CONFIGURED / GAP — нет нужного свидетельства, аудит не настроен либо потерян интервал.

Хранить кандидатов, reject reasons, provenance и ID исходных событий. Не назначать произвольный confidence=1.0 при приёме события, не заполнять actor/client из времени+пути, не затирать USN evidence. Отдельно различать «учётная запись в 4663» и «предположительный исполнитель изменения». При двух подходящих SID/сеансах явный AMBIGUOUS.

## 3. Неприкосновенность FILESERVER и разрешения

**Стадии A/B — только разработка и read-only preflight.**
- Запрещено включать auditpol, менять файловую SACL/DACL, GPO, Security log retention/size, NTFS USN, SMB, существующий Collector service, source credentials.
- Не включать Audit Detailed File Share (5145) или глобальный аудит всех файлов. Для 4663 нужен включённый Audit File System и подходящая **SACL целевой папки**; отсутствие любого условия = NOT_CONFIGURED.
- Команды read-only preflight: проверить effective Audit File System/Audit Logon, GPO ownership, уже существующую SACL на утверждённом pilot root, Security channel bounds/retention, примерный Event ID rate и разрешение на чтение журнала. Секреты, real paths/SID/учётки/IP — только private evidence.
- Только после **отдельного явного разрешения** можно: поставить новую Audit-службу на FILESERVER, создать новую синтетическую папку, добавить узкую SACL Success для записи/удаления именно на неё, включить при необходимости Audit File System, выполнить тестовый CRUD и восстановить исходную конфигурацию. Оператор утверждает конкретную папку, изменение policy, план отката, две доменные тестовые учётки и два клиентских ПК. Никаких паролей Codex не запрашивает и не сохраняет.
- Если policy управляет GPO, подготовить запрос владельцу GPO, не менять её локальным обходом.
- Нельзя перезагружать FILESERVER. Нельзя очищать или увеличивать Security log без отдельного согласования.
- Собирать только необходимые поля и записи внутри утверждённого scope; не передавать в центр все несвязанные 4624/4660 и посторонние пути. Отчёты в публичном Git — исключительно обезличенные. Production raw XML/EVTX не публиковать.

## 4. Стадия A — независимый Windows Security Collector

Создать отдельную native SCM службу SosnadminStorageAudit с собственными DPAPI machine-scoped credentials, collector UUID, protected state, Windows Event Log bookmark, SQLite durable outbox, recovery policy, installation/upgrade/rollback и статусом. Нельзя использовать ту же SQLite БД, runtime.lock или процесс existing SosnadminStorageCollector; отказ Audit не должен останавливать USN.

- Читать **только** Security Event Log через Win32 Windows Event Log APIs: EvtQuery/EvtSubscribe, EvtCreateBookmark, EvtUpdateBookmark, EvtRender, EvtSeek/EvtNext. Поддерживать строгий resume EvtSubscribeStartAfterBookmark|EvtSubscribeStrict и обработку ERROR_EVT_QUERY_RESULT_STALE. Нельзя silently switch to future-only при утерянном bookmark.
- Filter/parse Events 4663/4660/4624 плюс 1102 как признак Security log clear; machine fields из XML EventData/System по имени, не по локализованному Event Viewer Message. Обрабатывать версии, отсутствующие поля, UTF-16/Cyrillic, числа hex, незнакомые схемы без падения всей службы.
- Persist: Security channel/generation, host stable identity, event RecordID, provider GUID, event version/time UTC, SID/domain/account, Subject/TargetLogonId, process id/name, nonzero HandleId, ObjectName/ObjectType/AccessMask, LogonType, SourceNetworkAddress/WorkstationName если есть, evidence digest и quality.
- Match/local scope: только одобренные местные каталоги. 4663 вне scope отбрасывать до отправки; безымянный 4660 удерживать только в небольшом bounded pending-cache для связки с 4663; 4624 — ограниченный локальный session cache, передавать только при связи со scoped access. Не сохранять в центр лишние логины всего сервера.
- Обрабатывать Windows mount aliases/volume GUID, event-time path, case-insensitive names, moves/renames, hardlinks, junction/reparse. Если event-time ancestry сомнительна — UNKNOWN, не используйте текущий путь как исторический факт.
- Durable event identity: host + Security channel + validated log generation + EventRecordID. RecordID может повториться после clear. Bookmark и original outbox receipt atomic; на restart/lost ACK не терять уже считанные записи, не удваивать эффект на сервере. Gap/rollover/clear фиксировать как latched AUDIT_GAP; переход к новому baseline — отдельное решение.
- Не считать скачок EventRecordID между **отфильтрованными EventIDs** разрывом по умолчанию. Проверять реальную непрерывность через bounds/bookmark API.
- Ограничить CPU/RAM/queue/backpressure/частоту отправки, log rollover margin, refresh, accepted/filter counts, read errors; не допускать перегрузки Security Log/FILESERVER.
- Никаких raw file bytes/всего Security XML на backend по умолчанию. Собственная служба продолжает работать, если USN временно недоступен.

**GATE A:** Windows real native tests на disposable VM/owned Security fixture, installed-wheel SCM + DPAPI, bookmark→restart→replay, gap/clear, false path leakage, 4663/4660/4624 schema, EXPLICIT нет production modifications. Independent focused review, exact PR CI и merged-main CI. Не требовать real SACL changes для code PASS.
