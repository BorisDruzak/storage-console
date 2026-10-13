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

## 5. Стадия B — central evidence, разделённая freshness и correlation engine

**B1. Регистрация и доставка:**
- Добавить отдельный тип AUDIT_WINDOWS под уже существующий FILESERVER source. UUID и токен существующего WINDOWS/USN Collector не менять, новый Audit Collector получает собственный токен/credential binding. Не выдавать чужому источнику доступ к audit events.
- В source_data / Activity ввести **независимые роли и свежесть stream**: USN continuity выводить только из правильного WINDOWS/USN collector; Audit NOT_CONFIGURED/HEALTHY/STALE/GAP учитывать отдельно. Проверить матрицу 0,1,2 collectors, перестановка успешного heartbeat, disabled/audit missing, healthy-USN/stopped-audit, healthy-audit/stopped-USN. Старое правило collector_count==1 больше не должно портить USN после регистрации Audit.
- Имеющийся /api/v1/ingest/events и EvidenceRecord расширять **аддитивно** и с версионированным контрактом либо создать типизированный /api/v1/ingest/audit-events, совместимый со strict HTTPS/auth, byte-identical batch replay, max body limits, idempotent receipt. Существующее требование confidence нельзя использовать для выдуманной степени доверия при сборе.
- PostgreSQL хранит **immutable минимальные normalized evidence**: source_id/audit_collector_id, channel+generation+EventRecordID, event kind/time, SID/account/domain, logon ID, handle/process, scope path, access mask, доступные поля client, digest, first_received_at. Уникальный ключ на реальную event identity. Повторное принятие тождественного evidence не создаёт вторую запись; повторная запись с тем же ключом и иными полями — CONFLICT, не бесшумный overwrite.
- Retention отдельным будущим операторским решением, не добавлять автоматическую очистку журнала. Полный raw EVTX/WEF архив и 5145 не входят в данную задачу. Существующие change_events и path history не переписывать и не очищать.
- Миграции Alembic нужны минимальные: индексы по event identity, source, event time, logon, file path/volume, linkage. Без дорогих background reindex на production без предварительного EXPLAIN/rollback.
- Отдельная аудит-диагностика: enabled/configured, last collected/last accepted, bookmark age, gap, filtered/outside events, backlog, queue/quarantine, error codes, responsible policy/SACL. Не превращать отсутствие аудита в «история подтверждена».

**B2. Correlation Engine:**
- Offline/asynchronous idempotent matching после принятия обеих независимых последовательностей. Допускать out-of-order arrival и длительное outbox replay; до получения обеих сторон статус UNKNOWN.
- 4663↔4660: один host/log generation, nonzero HandleId + SubjectLogonId + process/context + надёжная последовательность/ограниченное время; 4660 без сопоставленного 4663 **без ObjectName** не должен получить выдуманный путь.
- 4663↔4624: один host/boot-session epoch, matching SubjectLogonId→TargetLogonId, логон до доступа и правдоподобный lifetime. 4624 Network Type 3 может иметь IP/workstation; если нет — оставить NULL. Совпадающий числовой LogonId после перезагрузки не доказывает ту же сессию.
- Audit↔USN: canonical source/volume + event-time path/identity + compatible AccessMask and USN reason + bounded time/correlation window, уникальность кандидата. Временное совпадение одного файла, без других сильных связок, НЕ CORRELATED_HIGH.
- Для WRITE, RENAME, DELETE вести **разные** критерии; 4663 DELETE access может соответствовать RENAME; 4660 не содержит имени; возможны SAVE AS/temp file replacement, hard links, shared sessions. Не приписывать операцию конкретному пользователю автоматически, если доказательств недостаточно.
- Хранить many-to-many candidate evidence с method, class, rejection reason и version корреляционного правила. Повторное выполнение engine не плодит линков, изменение вывода не изменяет исходные свидетельства.
- Если имеются сразу UserA и UserB для одного FileId/времени без однозначного соответствия — AMBIGUOUS, actor NULL. Положительный факт access для конкретной учётки можно показывать отдельно от actor-корреляции.
- Индексированная bounded обработка без синхронного N×M SQL join в HTTP запросе; проверить EXPLAIN + >=100k synthetic events, limits по времени и памяти.

**B3. Read API, UI и права:**
- Права по умолчанию только storage_admin. Учитывать Issue #22 MVP-005, где добавляется/планируется read_sensitive_activity; если он ещё не в main, установить минимум equivalent permission и договориться о rebase; не перетирать чужие изменения. Доступ всем ролям с общим read запрещён.
- Endpoint «Источники изменений / Аудит» и расширение существующей истории: для USN event показывать учётку/SID (только если доказана correlation), session и source IP/workstation **только при наличии**, метод сопоставления, список EventRecordID и 4663/4660/4624 evidence, класс уверенности, coverage/gap, ссылки на объекты. Actor без доказательств «Не определён».
- Для сырого audit evidence показать факт «учётная запись использовала право доступа к объекту», а не выдавать это за подтверждённое USN изменение. В пользовательской истории различать доступ, изменение и подтверждённый delete.
- Фильтры admin-only по событию, пользователю/SID, дате, FileId и client IP. Строки с чувствительными путями/учётками/IP не размещать в GET query URLs, referrer, server logs, public screenshots. Использовать безопасный авторизованный POST body/CSRF где применимо. Обойти RBAC прямой ссылкой или CSV нельзя.
- Никаких персональных данных в public fixture. UI ru-RU (+ en-US), Asia/Yekaterinburg, desktop/mobile; OpenAPI/generated TS validators из реального schema source.

**GATE B:** 0/1/2-collector regressions, actual isolated HTTPS/PostgreSQL evidence ingest, source freshness и preexisting USN/Overview не регрессируют; correlation cases с разными SID, разные LogonId, ambiguous multiuser и 4660 missing path. Exact-head and merged-main six CI jobs, independent review, backup/rollback prior central deployment; строго 401/403/200 проверки. На FILESERVER audit policy пока не менять.

## 6. Стадия C — реальные 2 доменных пользователя и 2 компьютера

**Сначала получить отдельное разрешение оператора** на конкретный узкий pilot. До разрешения C=BLOCKED, без production изменений.

Codex готовит PRIVATELY:
1. Согласованный синтетический каталог **внутри существующего monitored root**, не рабочие файлы отделов, с точным путём в приватном runbook; read-only снимок прав/DACL/SACL и GPO/effective Audit File System.
2. Утверждённые Success audit ACE **только** для записи/изменения/удаления в тестовом каталоге; если Audit File System не включён — проект минимального изменения по согласованию с GPO owner. Не включать глобальный аудит всех file shares / 5145 / массовый аудит чтений.
3. Расчёт вероятного объёма событий и риска переполнения Security Log, время пилота, разрешённые действия, revert procedure. Не чистить журнал и не менять его размер автоматически.
4. Две доменные учётные записи и два разных компьютера определяет и авторизует оператор. Пароли Codex не получает, учётки/IP/пути не пишет в публичный репозиторий.

**После согласования:**
- Установить отдельную service из проверенного wheel, убедиться, что existing USN service не останавливался; каждая служба имеет собственный PID/state/collector token/outbox, оба потока independently HEALTHY/UNKNOWN.
- UserA с PC-A, затем UserB с PC-B выполняют каждый свои санкционированные **CREATE, WRITE, RENAME, DELETE** на файлах только в test directory через SMB. Отдельно можно проверить неоднозначную ситуацию двух пользователей над одним test file, но только после согласования.
- Проверить реальные Windows Security 4663 и 4624 и наличие 4660 для DELETE при корректном SACL. Нет события — NO EVIDENCE, не писать фиктивное «атрибутировано».
- Подтвердить, что в audit evidence реально представлены 2 разных SID, их 4624 Subject/Target logon IDs различимы и соответствуют двум разным сеансам, USN matches корректны. Источник PC/IP указывать только если Security содержит эти данные; если Windows не сообщает второй IP/host, не заявлять, что два компьютера **установлены по журналу**, даже если оператор работал на них.
- Проверить путь и FileId before/after RENAME, DELETE через 4660/4663/USN без «лишнего удаления» из одного DELETE AccessMask; качество AMBIGUOUS и UNKNOWN должно быть продемонстрировано отдельным негативным сценарием.
- Пропустить restart Audit-service и, с отдельным разрешением, кратковременную потерю HTTPS, затем продемонстрировать byte-identical replay, отсутствие повторных event IDs, сохранение bookmark; убедиться, что USN продолжал работать.
- Реальный admin браузер: история одного файла, «Источники», две разные учётки, время, наличие/отсутствие client IP и доказательства; отдельный viewer/analyst/operator/auditor 403/no-sensitive-payload; mobile + reload.
- При согласовании удалить только собственный synthetic directory; вернуть **только** временно изменённые SACL/policy (учесть GPO), подтвердить исходные значения. Оставить новую службу running или остановить согласно отдельному решению оператора.
- Подтвердить отсутствие изменений SMB/USN journal/рабочих ACL; никаких reboot FILESERVER.

**GATE C PASS** только если реальные события от двух доменных учёток правильно разделены и обе имеют как минимум одну обоснованно связанную USN операцию, а для данных клиента явным текстом указано, что именно проверено Windows Security. Если реальные атрибуции невозможны из-за недоступной SACL/GPO/IP — честный BLOCKED или PARTIAL, не fake PASS. Никаких 72-часовых наблюдений.

## 7. Test matrix: RED→GREEN, bounded scope

- Parse versions 4663/4660/4624, fields absent, hex masks, Cyrillic/long paths, invalid provider/version, localized Message ignored; file vs registry object.
- 4660 no ObjectName and HandleId=0x0, same HandleId across different process/logon/boot; DELETE AccessMask during rename **not** DELETE.
- 4624 network Type3 vs local/service Type2/5, missing IP/workstation, reused LogonId across boots.
- Different SID/PC sessions + simultaneous access; correctly AMBIGUOUS without false user.
- Canonical volume/drive aliases/as-of paths; rename/delete/hardlinks/parent renames; never fabricated old path.
- EventRecordID repeated after log clear; bookmark strict miss, 1102, log overwrite, query stale, out-of-order/pending events. Do not mark ID gaps caused by filtering unrelated events as a log loss.
- Exact same event replay once vs twice and duplicate with changed payload -> conflict, transactional bookmark+queue recovery after crash and lost ACK.
- Without policy/SACL: NOT_CONFIGURED, USN changes still visible and remain un-attributed.
- Audit-down/USN-up and USN-down/Audit-up remain separate statuses; no false healthy and no interrupted old Collector.
- Outside-scope events, raw Security XML, unrelated 4624, passwords and unsafe paths never sent/published.
- Native own-process Windows SCM/LocalSystem tests on installed package plus real isolated HTTPS/PG, 100k synthetic events backend query plan.
- Existing migration upgrade/check/downgrade, code generation, backend/frontend/windows-pilot/compose-smoke/production-smoke/secrets intact; Sonar SKIPPED if unconfigured. i18n and real Playwright admin/mobile, 401/403.

## 8. Границы выполнения, отчёт и STOP

Создать и вести docs/acceptance/storage-audit-001-ledger.md:
- A source SHA + native tests + preflight results (sanitized) + exact CI + gate;
- B migration/backend, separate collector registration, isolated real ingest, USN freshness regressions, admin-only API + exact CI + gate;
- C separate operator approval, 2 users/2 PCs actual evidence, UI, restart/replay, rollback, exact deployed SHA + gate.

Каждый этап: narrow RED failing test → fix → GREEN → targeted/full relevant regression → independent Critical/Important review → separate PR → exact PR and merged-main CI → acceptance. Не затягивать бесконечными unrelated reviews; не ослаблять действующие gates.

Перед central deploy: проверенная PostgreSQL backup и копия вне VM, rollback for DB/API/Web, strict TLS, existing FILESERVER source and old-USN state retained. Конфликты с Issue #22 решать rebasing latest main и минимальными договорёнными изменениями Activity/RBAC, не перезаписывать чужую историю.

Codex **не имеет** разрешения на установку новой службы и изменение SACL/auditpol только потому, что пользователь дал это техническое задание. Подготовить implementation и чек-лист, запросить отдельное разрешение для C. После реальной приёмки Stage C — STOP, никакого автоматического 5145/WEF/SIEM/versions.

Итог: реальные события и ссылки на evidence, роль/сеанс/клиент когда доказуемо, объяснимые UNKNOWN/AMBIGUOUS, стабильный старый USN, список фактов и ограничений, PR/CI/deployed SHAs, требуемые дальнейшие действия.

## 9. References (Microsoft)

- 4663: https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/event-4663
- 4660: https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/event-4660
- 4624: https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/event-4624
- Advanced Audit Policy and file SACL: https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/plan/security-best-practices/advanced-audit-policy-configuration
- Windows Event Log bookmarks: https://learn.microsoft.com/en-us/windows/win32/wes/bookmarking-events
- EvtSubscribe strict: https://learn.microsoft.com/en-us/windows/win32/api/winevt/ne-winevt-evt_subscribe_flags
- Security log clear 1102: https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/event-1102
