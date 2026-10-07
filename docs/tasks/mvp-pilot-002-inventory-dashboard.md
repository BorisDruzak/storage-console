# Codex Task — MVP-PILOT-002: сделать живой inventory полезным на Overview

Приоритет: следующий после MVP-PILOT-001  
Тип: product vertical slice / read model + UI  
Base revision: `153662178058f3f5debc69f524ac521be75091c4`

Основные требования:
- `docs/spec/storage-control-plane-v0.1.md`
- `AGENTS.md`
- `docs/pilot/windows-live-pilot-ru.md`

## 1. Контекст

MVP-PILOT-001 уже доказал живой путь:

```text
FILESERVER
→ Windows Collector
→ HTTPS ingest
→ PostgreSQL
→ Web Console
```

В production-like operator pilot уже видны:
- один FILESERVER source;
- свежий heartbeat;
- реальный NTFS volume;
- capacity/free;
- mount alias;
- ненулевое количество filesystem objects.

Но Overview всё ещё показывает большинство карточек как «Нет данных», а volume быстро становится «Устаревшие данные».

Причина volume stale уже видна в коде:
- source freshness использует `source_nodes.expected_cadence_seconds` как heartbeat cadence;
- `apps/api/read/storage.py` применяет тот же cadence к `volumes.last_seen_at`;
- Windows runtime собирает inventory значительно реже heartbeat.

То есть heartbeat freshness и inventory freshness сейчас ошибочно связаны.

Также default UI timezone сейчас `UTC`, хотя product specification требует business default `Asia/Yekaterinburg`.

## 2. Goal

Без добавления новых collectors сделать уже имеющиеся реальные FILESERVER inventory-данные полезными оператору.

После задачи пользователь должен открыть Overview и увидеть:

```text
Свежесть данных
  Исправно

Ёмкость
  <state из реального capacity>
  Использовано: ...
  Свободно: ...
  Всего: ...
  Томов с актуальными данными: ...

Файловая система NTFS
  Health: Нет данных
  Наблюдаемый факт: NTFS volume получен
  Последняя инвентаризация: ...
  Проверка целостности ещё не собирается
```

При этом остальные неподдерживаемые domains остаются честно `UNKNOWN / Нет данных`.

## 3. Жёсткий scope

Реализовать только:

1. раздельную freshness semantics для heartbeat и inventory;
2. inventory-derived Capacity summary;
3. полезный Overview на основе уже существующих volume/object данных;
4. честное отображение filesystem inventory без ложного health;
5. human-readable capacity;
6. business timezone default `Asia/Yekaterinburg`;
7. regression tests;
8. обновление implementation status.

НЕ реализовывать:

- новые Windows collector providers;
- SMB/DFS collector;
- VSS;
- ACL;
- telemetry;
- PVE/PBS;
- USN;
- attribution;
- diagnostics;
- Data Discovery;
- MCP;
- Windows Service;
- generic health engine rewrite;
- forecasting/growth;
- alerting/incidents;
- auto-remediation;
- UI redesign.

## 4. Исправить inventory freshness

### Текущая ошибка

Не использовать heartbeat `expected_cadence_seconds` для `Volume.quality` или `Share.quality`.

Heartbeat может приходить каждые десятки секунд, inventory — существенно реже.

### MVP policy

Добавить отдельный central setting:

```text
inventory_stale_seconds
```

Default:

```text
7200
```

Это временная централизованная MVP policy для inventory evidence, а не полноценный per-source policy engine.

Требования:
- Pydantic validation: разумный bounded positive interval;
- production env example;
- deployment documentation;
- read API использует этот threshold для volume/share quality;
- HTTP evidence validity также не должна истекать по heartbeat cadence для storage rows.

### Quality rules

Для volume:

- future timestamp → `UNAVAILABLE`;
- age > `inventory_stale_seconds` → `STALE`;
- current, но total/free отсутствуют → `PARTIAL`;
- current + capacity complete → `COMPLETE`.

Для share использовать ту же inventory validity semantics, когда shares появятся.

### Required regression

При:
- heartbeat cadence = 60 sec;
- inventory age = 5 min;
- inventory stale threshold = 2 h;

volume обязан оставаться `COMPLETE`, а не `STALE`.

После превышения inventory threshold → `STALE`.

## 5. Capacity summary contract

Расширить `GET /api/v1/overview` минимальным typed read model.

Добавить, например:

```text
capacity:
  state
  total_bytes
  used_bytes
  free_bytes
  used_percent
  volume_count
  current_volume_count
  unavailable_volume_count
  latest_inventory_at
```

Имена можно скорректировать под существующий style, но semantics должны сохраниться.

Не возвращать raw paths/GUIDs в Overview summary.

## 6. Capacity state

Использовать статические thresholds из frozen v0.1 capacity model:

- used < 70% → `HEALTHY`
- 70% <= used < 80% → `OBSERVE`
- 80% <= used < 90% → `WARNING`
- used >= 90% → `CRITICAL`

Это только **capacity state по измеренной заполненности**, не общее здоровье storage.

### Unknown semantics

- нет current volume capacity evidence → `UNKNOWN`;
- только PARTIAL/STALE/UNAVAILABLE evidence → `UNKNOWN`;
- UNKNOWN нельзя отображать зелёным;
- наличие stale/partial volumes должно быть явно видно count-ом.

При нескольких current volumes использовать худшее измеренное состояние.

Не реализовывать forecast в этой задаче.

## 7. Не строить generic Health Engine

Для MVP-PILOT-002 не требуется записывать generic `health_signals/findings/incidents` для всех domains.

Допустим отдельный typed inventory-derived `capacity` read summary в Overview.

Не переписывать существующий `domain_health()`.

`overall_state` не должен становиться HEALTHY только потому, что capacity нормальный: остальные domains всё ещё без evidence.

## 8. Filesystem card — честная semantics

Наличие NTFS volume не доказывает NTFS integrity.

Поэтому:

- domain state `FILESYSTEM` остаётся `UNKNOWN`, пока нет integrity evidence;
- но карточка должна показывать уже известные inventory facts.

Минимально показать:
- число обнаруженных volumes;
- filesystem type(s), например NTFS;
- время последнего inventory;
- localized пояснение: «Данные о целостности файловой системы ещё не собираются».

Не использовать wording «NTFS исправен» без integrity evidence.

Если удобнее, добавить в Overview небольшой typed `inventory` summary:
- latest_inventory_at;
- volume_count;
- filesystem types/counts;
- filesystem_objects.

Не делать отдельный новый domain engine.

## 9. Overview UI

### Capacity card

Вместо пустого:

```text
Ёмкость
Нет данных
```

при наличии current real capacity показывать:

- localized state;
- использовано;
- свободно;
- всего;
- процент;
- current volumes / total volumes;
- latest inventory time.

### Filesystem card

Оставить health state честным:

```text
Файловая система NTFS
Нет данных
```

но ниже добавить inventory evidence:
- обнаружено томов;
- filesystem types;
- latest inventory;
- integrity evidence unavailable.

### Existing counts

Сохранить:
- sources;
- volumes;
- shares;
- filesystem objects.

Не скрывать реальные non-zero counts.

## 10. Human-readable sizes

Добавить один общий formatter.

IEC units:
- КиБ
- МиБ
- ГиБ
- ТиБ

Требования:
- ru-RU number formatting;
- разумная точность;
- при необходимости exact bytes можно оставить secondary/title;
- не показывать огромные raw integers как основной UX.

Использовать formatter как минимум:
- Overview Capacity;
- Volumes table total/free.

## 11. Timezone

Исправить default Web preference:

```text
UTC
→
Asia/Yekaterinburg
```

Требования:
- новый/чистый браузер показывает business time +05;
- пользователь всё ещё может выбрать UTC или другую IANA timezone;
- явно сохранённую существующую preference не перезаписывать;
- ru-RU остаётся default locale.

Regression:
- known UTC timestamp должен отображаться как соответствующее время Asia/Yekaterinburg.

Не менять timestamps в БД: они остаются UTC/timestamptz.

## 12. Data truthfulness

Обязательные правила:

- source freshness != storage health;
- inventory current != filesystem integrity healthy;
- capacity healthy != overall system healthy;
- stale data не использовать как current capacity state;
- отсутствующие SMB/VSS/ACL/PVE/PBS данные остаются UNKNOWN;
- не добавлять synthetic/demo data в production UI.

## 13. API / client compatibility

Если Overview contract расширяется:
- обновить Pydantic contract;
- OpenAPI;
- generated TS;
- standalone validators;
- API drift checks;
- frontend typed client.

Не ломать старые read endpoints.

## 14. Tests

Backend минимум:

1. heartbeat cadence не делает свежий hourly inventory stale;
2. volume становится stale только по inventory threshold;
3. missing capacity → PARTIAL/UNKNOWN;
4. capacity thresholds 69.x / 70 / 80 / 90;
5. multiple volumes → worst capacity state;
6. no capacity evidence → UNKNOWN;
7. stale evidence не даёт HEALTHY;
8. overview capacity totals арифметически согласованы;
9. overall health остаётся UNKNOWN при неизвестных domains.

Frontend минимум:

1. Capacity card с real non-zero contract;
2. Unknown capacity state;
3. Filesystem inventory evidence + health UNKNOWN;
4. human-readable IEC sizes;
5. default Asia/Yekaterinburg;
6. explicit UTC preference remains UTC;
7. no machine enum leakage;
8. existing ru-RU i18n gate.

Playwright:
- Overview с current inventory;
- Volumes table;
- reload;
- default timezone check.

## 15. Live operator acceptance

После deploy на current central и при работающем FILESERVER collector:

### Overview

Должно быть:
- Источники > 0;
- Тома > 0;
- Объекты файловой системы > 0;
- Свежесть данных = current;
- Capacity card НЕ «Нет данных»;
- реальные total/free/used;
- state по capacity threshold.

### Volume page

Реальный DATA volume:
- filesystem;
- mount alias;
- total/free;
- quality = current/complete пока inventory младше threshold;
- human-readable size.

### Filesystem

- NTFS inventory evidence видно;
- integrity state остаётся «Нет данных».

### Time

Все UI timestamps по default показываются в `Asia/Yekaterinburg`, если пользователь не выбрал другое.

## 16. STOP CONDITION

После MVP-PILOT-002 остановиться.

Не переходить автоматически к:
- Service;
- USN;
- SMB;
- VSS;
- ACL;
- PVE/PBS;
- telemetry;
- diagnostics.

Финальный отчёт:
1. commits;
2. CI;
3. скрин/описание нового Overview;
4. live acceptance result;
5. known limitations;
6. следующая задача только как предложение.

## 17. Definition of Done

Задача выполнена, когда уже собранные реальные FILESERVER inventory data дают оператору полезный dashboard:

- Capacity имеет измеренное состояние и значения;
- volume data не становятся stale по heartbeat cadence;
- filesystem inventory виден без ложного заявления о здоровье;
- размеры читаемые;
- время отображается в Asia/Yekaterinburg по умолчанию;
- остальные неподдерживаемые domains честно остаются UNKNOWN.

Цель — повысить полезность уже работающего vertical slice, а не расширить количество collectors.
