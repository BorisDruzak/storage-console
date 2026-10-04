# Windows Collector

Резерв модуля: implementation начинается после Wave 0. Live collection пока отсутствует.
Будущий Windows Service отправляет metadata/telemetry в API; не меняет audit policy или инфраструктуру.

[Общие outbox/HTTPS delivery](../common/README.md) реализованы; установка Windows
Service/ACL, USN continuity и живой inventory ещё не приняты.
