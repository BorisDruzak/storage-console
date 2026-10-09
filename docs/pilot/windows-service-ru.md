# Windows Service — операторский checklist Stage B

Граница: existing heartbeat/inventory/outbox под native SCM. USN и последующие
контуры не входят в Stage B. Автоматизированный acceptance не заменяет живой
handover и перезагрузку FILESERVER.

**До live acceptance:** отдельный PR, независимый review, полный regression,
exact merged-main CI и зафиксированные source/wheel SHA256 в
[execution ledger](../acceptance/mvp-003-004-execution-ledger.md).
Не выполнять live handover без явного разрешения оператора. Перезагрузка требует
отдельного явного разрешения и согласованного maintenance window.

## Установка и права

Служба `SosnadminStorageCollector`: own-process, LocalSystem, Automatic (Delayed).
LocalSystem читает уже активированные machine-DPAPI config/CA/outbox с текущими
SYSTEM/Administrators-only разрешениями. Enrollment/Collector UUID не меняются.

В этой версии principal необходим для existing protected state/native capture;
collector не включает дополнительные token privileges. Least-privilege plan:
отдельная будущая проверка virtual service account/service SID и минимальных
read/metadata прав, с отдельно согласованной миграцией доступа к state.
Изменение DACL/account/AD не входит в этот delivery train.

Интерпретатор, installed wheel и зависимости должны находиться в доверенной
all-users installation вне пользовательских writable каталогов. CLI проверяет
owners/DACL, reparse points, ancestors, interpreter roots и внешние dependency
пути из `.pth` только чтением. Проверка ограничена 30 секундами/100000 entries.
Source checkout или unsafe installation отклоняются; CLI не исправляет ACL.
Подготовка нового доверенного package directory не разрешает менять существующие
FILESERVER ACL, shares, SMB, audit policy или USN Journal.

Wheel устанавливается обычным pip в выбранный interpreter по проверенному hash.
Project version остаётся `0.1.0`: номер версии не идентифицирует Stage B artifact.
Перед установкой сверить SHA256 wheel с manifest exact accepted source SHA.
Для замены wheel той же версии нужен explicit `pip install --force-reinstall`
(на остановленном runtime); dependency versions брать из `requirements.lock`.
Предпочесть отдельную новую доверенную installation, сохранив прежнюю для rollback.
Не заменять runtime binaries во время работы foreground/service.
Нужно сохранить прежний wheel/interpreter для rollback. Каталог protected state
остаётся прежним; не копировать его, ключи или сырые evidence в публичный Git.
Не передавать collector key через argv, environment или Event Log.

В elevated PowerShell подставить только уже подтверждённые operator paths:

```powershell
$collectorPython = '<доверенный installed Python.exe>'
$collectorState = '<существующий protected state directory>'
& $collectorPython -I -m collectors.windows.cli service install --state $collectorState
& $collectorPython -I -m collectors.windows.cli service status --state $collectorState
& $collectorPython -I -m collectors.windows.cli service start --state $collectorState
Get-Service SosnadminStorageCollector
sc.exe qc SosnadminStorageCollector
sc.exe qfailure SosnadminStorageCollector
```

Повторные install/start не создают второй runtime. Install не обновляет чужую или
несовместимую регистрацию и не включает disabled service. Для operator changes
нужны administrator rights; отсутствие прав возвращает fixed error code.
Короткие start/status/stop/uninstall без `--state` используют state из строго
проверенной регистрации SCM. Explicit `--state` должен совпадать с регистрацией;
произвольные дополнительные arguments или другой interpreter отклоняются.

## Контролируемый foreground → service handover

1. Зафиксировать старый package/hash, interpreter, foreground PID и state path
   в приватном operator evidence. В Console проверить source freshness/inventory.
2. Ctrl+C только в текущем foreground shell. Дождаться штатного завершения;
   не удалять runtime.lock и не завершать все процессы Python.
3. После остановки прочитать прежний локальный статус:

   ```powershell
   & $collectorPython -I -m collectors.windows.cli status --state $collectorState
   ```

4. Записать Collector UUID, credential binding, heartbeat/inventory checkpoints,
   pending/quarantine и auth suspension в приватный ledger. Не re-enroll.
5. Установить/start службу командами выше. Проверить queried binary path,
   LocalSystem, delayed start и recovery policy. Первый RUNNING допускается
   только после загрузки protected configuration.
6. Наблюдать три последовательных новых heartbeat в Console, текущую freshness
   и прежний inventory. SCM RUNNING означает состояние процесса и может
   сохраняться при auth suspension; это не доказательство HEALTHY.
7. Выполнить stop/start; при остановке сверить UUID/binding/checkpoints/queue.
   Затем подтвердить новый heartbeat и pending=0/quarantine=0 после drain.

```powershell
& $collectorPython -I -m collectors.windows.cli service stop --state $collectorState
& $collectorPython -I -m collectors.windows.cli status --state $collectorState
& $collectorPython -I -m collectors.windows.cli service start --state $collectorState
& $collectorPython -I -m collectors.windows.cli service status --state $collectorState
```

SCM status не берёт runtime lock и доступен во время работы. Локальный outbox
status намеренно читает protected state только после stop. STATE_BUSY при
foreground/service конкуренции не является поводом удалять lock или state.

## Deadlines, auth и recovery

Startup deadline 30 секунд; stop использует existing runtime stop_seconds +
3 секунды для host cleanup (maximum 123). Pending состояния обновляют checkpoint;
CLI ждёт не более 150 секунд. При failed cleanup завершается только собственный
service process; native capture принадлежит Job Object KILL_ON_JOB_CLOSE.

Explicit STOP/SHUTDOWN не запускает recovery. Abrupt crash: restart через
10, 30 и 60 секунд; последующие сбои повторяют задержку 60 секунд. Failure count
reset через 86400 секунд. Нет reboot action или arbitrary recovery command.
`service install` обновляет только распознанную прежнюю политику (restart/NONE),
проверив полную identity регистрации; disabled registration не изменяется.
Startup/config/auth failures не
должны исправляться re-enrollment, снятием suspension или изменением ACL.

Runtime повторяет только SQLITE_BUSY/SQLITE_LOCKED (включая extended codes)
с interruptible backoff 0.1–2 секунды и бюджетом 30 секунд на операцию.

На Windows проверка обычного rollback journal с `st_nlink=0` повторно проверяет
путь до трёх раз с паузами 1 ms: commit может в этот момент удалять journal.
Инвентаризация повторяет запись того же batch/checkpoint при BUSY/LOCKED в пределах
существующего `capacity_wait_seconds`; остаток бюджета ограничивает ожидание SQLite.
Принимается только исчезнувший либо заново проверенный безопасный файл.
Устойчивый zero-link, hardlink, directory и reparse point остаются запрещены;
основной database и WAL/SHM не получают такого исключения.
Повреждение SQLite, IOERR/FULL и неизвестные ошибки остаются fatal. При повторе
после ошибки acknowledge сохраняется durable lease; ingest остаётся idempotent.
Очередь и checkpoints не очищаются.

Application Event 1 сохраняет исходный machine code и отдельный
`RUNTIME_DIAGNOSTIC` с JSON: stage, exception type, numeric sqlite_errorcode,
до 12 project module/function/line frames. Сообщения исключений, SQL, locals,
credentials и абсолютные пути не записываются. Fatal delivery exception
передаётся в host после cleanup; детали также записываются до cleanup, чтобы
вторичная ошибка остановки не скрыла первичный сбой. Временная блокировка
записывается один раз на retry episode, без сообщения на каждую попытку.
Сохранение зависит от доступности Windows Event Log; при отказе системного
журналирования отсутствие записи не означает отсутствие сбоя.

При outage queue/checkpoints сохраняются. После восстановления strict HTTPS
backlog доставляется existing idempotent ingest. Pending claim после stop/crash
может ждать durable lease (default 60 секунд); не очищать leases/batches вручную.
Срок drain учитывать вместе с transport deadline и реальным размером backlog.

SERVICE_RECOVERY_PENDING: STOPPED после crash ещё может иметь queued restart.
Нельзя считать это подтверждённой operator stop. Дождаться recovery и остановить
работающую службу либо явно удалить её регистрацию через uninstall. Uninstall
сохраняет state и отменяет queued recovery; concurrent start дренируется bounded.
SERVICE_CONFLICT/UNSAFE_SERVICE_INSTALLATION — остановиться и проверить package
installation/registration; не менять ACL или чужие service entries автоматически.

Application Event Log содержит только fixed machine codes. Raw exception text,
token, source identity, root paths и содержимое документов туда не записываются.

## Real reboot — отдельный обязательный gate

До согласованного окна записать явное разрешение, время, before identity,
queue/checkpoints и rollback readiness в приватный evidence. Этот документ
**не разрешает перезагрузку** и не содержит команду автоматического reboot.

После operator reboot, без интерактивного login и ручного CLI run:

- service работает с прежними binary/principal/delayed start settings;
- UUID/binding сохранены; нет второго collector/runtime;
- источник получает свежие heartbeat в обоснованном окне startup/cadence/TTL;
- inventory сохраняется/обновляется, pending drain→0, quarantine=0;
- нет неожиданных CPU/SMB проблем и изменений ACL/audit/USN configuration.

GATE B остаётся BLOCKED без реально выполненной и проверенной перезагрузки.
Нельзя переходить к Stage C по disposable tests или по одному SCM RUNNING.

## Rollback

1. Остановить service; проверить завершение и сохранённый state/checkpoints.
2. Удалить только регистрацию:

   ```powershell
   & $collectorPython -I -m collectors.windows.cli service uninstall --state $collectorState
   ```

3. Вернуть прежний проверенный wheel/interpreter. Не удалять config, CA, outbox,
   evidence store, source registration или credentials.
4. Запустить прежний foreground runtime с тем же state; проверить новое
   heartbeat/inventory и queue drain. Не выполнять service/foreground параллельно.

Проверка rollback выполняется на synthetic disposable setup. Возвращать live
FILESERVER назад можно только в рамках явно разрешённого operator handover.

Upgrade: старым доверенным interpreter выполнить stop/uninstall, зафиксировать
сохранённые UUID/binding/queue/checkpoints; затем новым проверенным wheel/interpreter
выполнить install с тем же `--state`, start и acceptance. Регистрация на иной binary
path не обновляется молча: новый CLI сначала корректно вернёт SERVICE_CONFLICT.
