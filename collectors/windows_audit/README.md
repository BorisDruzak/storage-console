# Независимый Windows Security Audit Collector

Этап A STORAGE-AUDIT-001: отдельная служба `SosnadminStorageAudit`, модуль
`collectors.windows_audit.service`, собственные UUID/token, protected state,
DPAPI machine credentials и `audit.sqlite3`. Общие Win32 SCM/DPAPI primitives
переиспользуются как библиотеки; процесс, runtime lock, credentials, БД и USN
runtime существующего Collector не используются.

Режим A — `capture_only`: минимальные normalized свидетельства удерживаются
локально в зашифрованной очереди. Центральное принятие и корреляция относятся к
этапу B; `last_accepted_at=NULL`, статус OBSERVE, никакого ложного HEALTHY.
`configured=false` даёт NOT_CONFIGURED и не открывает Security subscription.

## Установка после отдельного разрешения

До разрешения оператора на FILESERVER эти действия запрещены. Native CI делает
их только на disposable GitHub Windows runner и в собственном fixture directory.

1. Проверить exact package/source SHA, CI и хеш wheel. Установить wheel в отдельный
   interpreter/venv под защищённым каталогом с доступом только SYSTEM/Administrators.
   `validate_installation` проверяет код и ancestors, не исправляет их ACL.
2. Новый UUID/token выдаётся для AUDIT_WINDOWS под существующим source на этапе B.
   Не брать токен/UUID существующего USN. Выделить новый защищённый state directory;
   никогда не указывать существующий USN state или SQLite.
3. Подать JSON configuration через stdin в
   `python -I -m collectors.windows_audit.cli initialize --state <approved-state>`.
   Не помещать token в argv, history, tracked JSON или лог. JSON содержит
   collector_id, source_id, stable host_id, отдельную generation, roots с
   canonical volume aliases, strict HTTPS origin, CA file и token. Безопасный
   режим по умолчанию: configured=false, initial_baseline=false.
4. `configured=true` разрешён только после проверки effective Audit File System,
   одобренной narrow SACL и GPO ownership. initial_baseline=true при первом
   enrollment фиксирует newest native anchor и до 64 последних 4624 текущего boot
   в локальном кэше. Это граница покрытия, а не историческая полнота.
5. `python -I -m collectors.windows_audit.cli install --state <approved-state>`,
   затем `start`. SCM: own process, LocalSystem, delayed auto start, bounded recovery.
   Status читает только state/pid собственной регистрации. Проверить независимость
   обоих PID/UUID/state/outbox и продолжение USN без restart.

## Upgrade и rollback

Сначала stop только Audit, записать исходные package/source SHA и protected backup
собственной конфигурации/SQLite/registration; existing USN не останавливать.
Установить проверенный wheel в защищённый interpreter. При изменении пути
interpreter старый CLI сначала проверяет и удаляет только свою STOPPED Audit
registration; новый CLI создаёт ту же Audit registration с новым command. Никакого
обхода SERVICE_CONFLICT и произвольного удаления чужой службы.

Сохранить identity/configuration/SQLite; schema этапа A неизменна. После запуска
проверить strict anchor, bookmark, очередь и byte-identical replay. Если package
несовместим, stop/uninstall только Audit, вернуть старый interpreter/registration,
запустить со сохранённой собственной state. Не откатывать bookmark отдельно от
очереди: это разрушает atomic receipt. Не удалять queue ради успешного запуска.
Установка/удаление службы не удаляет свидетельства или credentials.

AUDIT_GAP latch после 1102, strict miss, replaced RecordID/anchor или boot change
нельзя снять рестартом. Оператор рассматривает потерянный интервал и отдельно
утверждает новый baseline/generation в новом state, сохраняя старую очередь.
Нет automatic future-only fallback, очистки Security, изменения retention или SACL.

## Scope и ограничения

4663 передаётся только для File и явно одобренного локального root. Сравнение
Windows ordinal, не Unicode linguistic casefold. Проверка reparse ancestry
консервативная; она не доказывает исторический FileId/ancestry. path_quality
остаётся UNKNOWN до проверки event-time USN на этапе B. За пределами scope не
хранятся пути; наблюдаемое handle reuse инвалидирует прежнего кандидата. 4660
отправляется только при bounded nonzero handle/process/logon/SID/boot/generation
связке с scoped DELETE access; ObjectName всегда NULL. DELETE access само по себе
не объявляется удалением. 4624 передаётся только для единственного подходящего
scoped access; числовые ID, SID и времена проверяются, отсутствующий client NULL.

Кэши ограничены количеством и байтами; очередь 64 MiB/1024 batches; обработка
не более 64 событий в секунду. Backpressure не сдвигает bookmark. Каждые 30 s
обновляются native channel bounds/capacity и rollover margin; status содержит
bookmark age, counters, backlog, gap и fixed-code read errors. Номера между
отфильтрованными EventIDs не трактуются как потеря журнала.

`preflight.ps1` выполняет только чтение и отдаёт обезличенные aggregates. Pilot
root передаётся только после его отдельного утверждения; без него SACL UNKNOWN.
Не выполнять auditpol /set, SACL/GPO changes, очистку Security или CRUD на FILESERVER
в стадиях A/B. Нет 5145, WEF, SIEM, raw XML/EVTX archive, content collection или remediation.

## Центральная доставка и правила v1 (этап B)

`mode: deliver` включает собственную HTTPS delivery thread. Capture_only остаётся
по умолчанию. UUID/token берутся из регистрации AUDIT_WINDOWS на существующем
FILESERVER source; существующий WINDOWS collector и его credential не заменяются.
Нужен зарегистрированный canonical volume. Immutable batches из audit.sqlite3
повторяются теми же байтами; новый формат heartbeat не меняет receipt digest старого
USN heartbeat. AUTH_REQUIRED и HTTP_REJECTED/REDIRECT сохраняют suspension/quarantine,
свидетельства не удаляются. Перед операторским разрешением повторной доставки
проверить binding/token/контракт; вручную очищать очередь запрещено.

Чувствительные API `/api/v1/audit/*` и legacy Activity требуют
read_sensitive_activity (storage_admin). Поиск использует POST body + Origin/CSRF.
UI различает факт доступа в Security Event, вывод об исполнителе USN и текущую
coverage; SID, LogonId и числовые идентификаторы передаются также точными строками.
Никакого определения физического ПК по IP или личности человека не выполняется.

Rule windows-security-usn-v1 допускает HIGH только для единственной DELETE chain
4663 DELETE -> 4660 -> USN FILE_DELETE. Нужны совпадающие host/boot/generation,
SID/logon/process/nonzero handle, строгий RecordID order, ограниченное время,
4624 session, независимое предшествующее WINDOWS inventory FileId/link_count=1
не старше 60 секунд, датированные volume aliases и coverage обоих потоков до/после.
Это отдельные witnesses; target change не подтверждает собственную identity.
Повторный worker идемпотентен; поздний второй контекст отменяет actor и даёт AMBIGUOUS.

CREATE disposition, границы aggregated WRITE и двухименная audit chain для RENAME
отсутствуют в текущих потоках. Для этих операций v1 показывает access candidates,
UNKNOWN/ACCESS_OBSERVED и причину, без автоматического HIGH. Нужные для пилота
inventory/heartbeat witnesses должны поступить обычным расписанием; ради теста
не менять и не перезапускать существующий USN Collector. Если witnesses отсутствуют,
пилот остаётся PARTIAL/BLOCKED. Исходный USN-SOAK-001 FAIL этим не отменяется.

Миграция 0007 добавляет audit-only tables/indexes и immutable triggers на evidence,
identity/health observations (UPDATE/DELETE/TRUNCATE запрещены). Retention является
будущим операторским решением. До central deploy: custom pg_dump, pg_restore --list,
SHA256 и копия вне VM; сохранить старые API/Web images/env. Rollback API/Web к
предыдущему release допустим с additive schema; удаление новых audit tables или
восстановление БД — только явная maintenance операция с backup. Нельзя выполнять
широкий downgrade через 0005: он намеренно блокирует потерю path-only history.

Deliver mode требует список operator-approved `audit_sids` (до 16 SID) в sealed
config. AuditQuerySystemPolicy и GetNamedSecurityInfoW каждые 30 секунд read-only
подтверждают effective File System Success и inheritable write/append/delete ACE
для всех этих SID на каждом approved root и существующих descendants. Только
selected scope: максимум 256 объектов, без reparse; превышение лимита или
защищённый descendant без необходимых ACE не дают verified. Root inheritance
сама по себе не доказывает SACL descendants. Это периодические dated witnesses,
не гарантия неизменности policy между наблюдениями. ACL/права и policy не меняются. Нет
подтверждения при старте -> NOT_CONFIGURED; потеря после старта -> latched
AUDIT_CONFIGURATION_CHANGED / GAP. После C rollback нельзя оставлять configured
службу с отсутствующей SACL в HEALTHY: статус автоматически теряет подтверждение.
