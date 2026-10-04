from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from packages.contracts.sources import (
    CollectorCredential,
    CollectorView,
    CreateCollector,
    CreateSource,
    RotateCollector,
    SetCollectorEnabled,
    SourceRegistration,
)


def source_data(**changes):
    return dict(
        source_type="FILESERVER", hostname="Сервер-😀", instance_id="immutable-1", **changes
    )


def collector_data():
    return dict(
        id=uuid4(),
        source_node_id=uuid4(),
        collector_type="WINDOWS",
        version=None,
        enabled=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        last_seen_at=None,
    )


def test_source_registration_preserves_unicode_case_identity_and_default_cadence():
    data = CreateSource.model_validate(source_data(fqdn="Mixed.Сервер.example.test"))
    assert data.hostname == "Сервер-😀"
    assert data.fqdn == "Mixed.Сервер.example.test"
    assert data.instance_id == "immutable-1"
    assert data.expected_cadence_seconds == 60
    for cadence in (1, 86400):
        assert CreateSource.model_validate(source_data(expected_cadence_seconds=cadence))


@pytest.mark.parametrize("cadence", [True, False, "60", 60.0, None, 0, -1, 86401, 2**100])
def test_cadence_is_a_bounded_strict_integer(cadence):
    with pytest.raises(ValidationError):
        CreateSource.model_validate(source_data(expected_cadence_seconds=cadence))


@pytest.mark.parametrize("field", ["hostname", "instance_id", "fqdn"])
@pytest.mark.parametrize(
    "value",
    ["", " leading", "trailing ", "\x00host", "line\nhost", "\x7f", "\u200b", "\ud800", "x" * 256],
)
def test_source_identity_rejects_unsafe_or_unbounded_text(field, value):
    data = source_data()
    data[field] = value
    with pytest.raises(ValidationError):
        CreateSource.model_validate(data)


def test_source_text_rejects_coercion_and_allows_maximum_unicode_length():
    for value in (1, True, b"host", [], None):
        data = source_data()
        data["hostname"] = value
        with pytest.raises(ValidationError):
            CreateSource.model_validate(data)
    data = source_data()
    data["instance_id"] = "😀" * 255
    assert CreateSource.model_validate(data).instance_id == "😀" * 255


def test_management_contracts_reject_unknown_fields_and_types():
    for extra in (dict(token="private"), dict(id=str(uuid4())), dict(source_type="fileserver")):
        with pytest.raises(ValidationError):
            CreateSource.model_validate(source_data() | extra)
    for value in ("FILESERVER", "windows", "UNSUPPORTED", None):
        with pytest.raises(ValidationError):
            CreateCollector.model_validate(dict(collector_type=value))
    for kind in ("WINDOWS", "PVE", "PBS"):
        assert CreateCollector(collector_type=kind).collector_type == kind
    with pytest.raises(ValidationError):
        CreateCollector.model_validate(dict(collector_type="WINDOWS", source_node_id=str(uuid4())))
    assert RotateCollector.model_validate({})
    with pytest.raises(ValidationError):
        RotateCollector.model_validate(dict(token="private"))


@pytest.mark.parametrize("enabled", [0, 1, "true", "false", None, [], {}])
def test_enabled_is_strict_boolean(enabled):
    with pytest.raises(ValidationError):
        SetCollectorEnabled.model_validate(dict(enabled=enabled))


def test_enable_request_cannot_reassign_collector_or_supply_credentials():
    for enabled in (True, False):
        assert SetCollectorEnabled(enabled=enabled).enabled is enabled
    for extra in (dict(source_node_id=str(uuid4())), dict(token_hash="x" * 64)):
        with pytest.raises(ValidationError):
            SetCollectorEnabled.model_validate(dict(enabled=False) | extra)


def test_registration_timestamp_is_aware_and_normalized_to_utc():
    when = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=5)))
    data = source_data(id=uuid4(), created_at=when)
    registered = SourceRegistration.model_validate(data)
    assert registered.created_at == when
    assert registered.created_at.tzinfo == UTC
    assert registered.expected_cadence_seconds == 60
    data["created_at"] = datetime(2026, 1, 1)
    with pytest.raises(ValidationError):
        SourceRegistration.model_validate(data)


def test_collector_view_never_accepts_or_serializes_token_or_hash():
    data = collector_data()
    view = CollectorView.model_validate(data)
    assert set(view.model_dump()) == set(data)
    for key in ("token", "token_hash"):
        with pytest.raises(ValidationError):
            CollectorView.model_validate(data | {key: "synthetic-private"})


def test_credential_is_repr_hidden_and_only_json_serializer_reveals_it():
    token = "t" * 43  # Synthetic fixture, not an operational credential.
    value = CollectorCredential.model_validate(collector_data() | dict(token=token))
    assert token not in repr(value)
    assert token not in str(value)
    assert isinstance(value.model_dump()["token"], SecretStr)
    assert token not in repr(value.model_dump())
    assert value.model_dump(mode="json")["token"] == token
    assert token in value.model_dump_json()
    assert "token_hash" not in value.model_dump(mode="json")


@pytest.mark.parametrize("token", ["", "t" * 42, "t" * 44, "?" * 43, "т" * 43, "\n" + "t" * 42])
def test_credential_requires_exact_generated_token_shape(token):
    with pytest.raises(ValidationError):
        CollectorCredential.model_validate(collector_data() | dict(token=token))
