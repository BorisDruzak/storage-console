# Общая очередь и HTTPS-доставка

Реализованы библиотечные `Outbox`, `Transport` и `Delivery` для Python3.13+.
Они не собирают данные файловой системы, PVE/PBS и не устанавливают Windows Service.
Живые collectors и pilot-приёмка остаются следующими этапами.

`Outbox(path, collector_id)` хранит неизменяемые bytes пакета и checkpoint в одной
SQLite-транзакции. `enqueue(domain, batch, stream, expected_revision, checkpoint)`
проверяет существующий typed BatchEnvelope; конфликт revision или нехватка места
не продвигают checkpoint. После потери подтверждения повторяйте тот же пакет и
transition; устаревший transition требует перечитать checkpoint. Не создавайте
новый batch ID для повторной отправки уже сохранённого пакета.

`Transport(origin, ca, token, collector_id=collector_id)` принимает фиксированный
HTTPS origin с DNS-именем, публичный CA и текущий ключ из защищённой конфигурации.
Проверяются цепочка, hostname и TLS1.2+. Редиректы и ambient proxies запрещены.
Секрет передаётся изолированному процессу через stdin в памяти; он отсутствует
в arguments, SQLite, результатах и repr. Попытка ограничена15секундами целиком.
CA снимок фиксируется при создании transport; изменение доверия требует нового
экземпляра. Домен `diagnostics` отправляется на существующий `/diagnostic-bundles`;
остальные восемь доменов используют одноимённые ingest routes.

`Delivery(outbox, transport).run_once()` выполняет одну попытку вне SQLite-транзакции.
Только точный202 Receipt с `accepted=true` и boolean `duplicate` удаляет текущую
lease. Потеря ответа допускает byte-identical replay и `duplicate=true` после
серверного commit. Retry ограничен backoff1–300секунд; постоянное отклонение
сохраняет пакет в quarantine. Пакет с backoff/lease/quarantine блокирует только
свой stream; другие streams могут продолжать отправку.

Для Windows runtime `Limits` поддерживает `heartbeat_reserve_batches` и
`heartbeat_reserve_bytes`: все остальные домены вместе не могут занять этот резерв.
Проверки общего лимита и резерва выполняются в одной write-транзакции, включая
retained lease/quarantine. Heartbeat подчиняется общему лимиту; переполненная очередь
heartbeat тоже может остановить сбор. По умолчанию оба резерва равны0.
`Delivery(..., prefer_heartbeat=True, heartbeat_burst=4)` отдаёт heartbeat не более
четырёх последовательных попыток, после чего предоставляет очередь допустимому
пакету другого домена. Если такой пакет отсутствует, heartbeat продолжает доставку.
`Outbox.claim(..., heartbeat_priority='normal'|'first'|'last')` меняет только порядок
между streams; более ранний retained пакет своего stream нельзя обойти.

401/403 сохраняют auth suspension после перезапуска. Новый transport сам по себе
не возобновляет очередь: для непривязанной общей очереди оператор должен явно вызвать
`refresh_credentials(new_transport)`; Windows runtime использует новую credential version.
Идентичность collector UUID должна совпадать; автоматической выдачи ключа нет.
Поздний ответ старого sender/lease не отменяет обновление и не удаляет новую lease.
`close()` прекращает новые попытки; незавершённый пакет остаётся reclaimable.

SQLite schema1/2 обновляется до3 атомарно, с сохранением всех пакетов, receipts и
checkpoints. Schema3 добавляет `credential_binding()` и явный
`activate_credentials(UUID)`: новая credential version меняет generation, снимает
auth suspension и аннулирует все старые lease одной транзакцией. Повтор той же
version ничего не возобновляет; для привязанного state `resume_auth()` запрещён.
Код schema1/2 не открывает schema3; rollback старого кода требует
согласованной работы с версией state. В Linux каталог должен принадлежать service
user и иметь700, state-файлы600; symlink/hardlink отвергаются. Установка защищённых
Windows ACL выполняется библиотекой `ProtectedState`; установленная служба и её
учётная запись остаются обязательной отдельной runtime-приёмкой.

Проверки очереди/transport: `pytest tests/backend/test_collector_outbox.py
tests/backend/test_collector_transport.py tests/backend/test_collector_delivery.py -q`.
Настоящие HTTPS/PostgreSQL/crash/rotation проверки: `pytest
tests/backend/test_collector_delivery_integration.py -q`; нужен OpenSSL и
`TEST_DATABASE_URL` отдельной одноразовой тестовой базы. Не направляйте тесты на
рабочую БД. Полный scope и evidence: [план](../../docs/superpowers/plans/2026-10-04-collector-delivery.md).
