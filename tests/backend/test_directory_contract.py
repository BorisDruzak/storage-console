"""Synthetic directory metadata; observations never confer an access role."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from packages.contracts.directory import (
    ClientNameObservation,
    DirectoryPage,
    DirectoryScope,
    DirectoryUser,
)

DOMAIN = "S-1-5-21-10-20-30"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def scope():
    return {"dns_domain": "example.test", "domain_sid": DOMAIN}


def user(**changes):
    return dict(sid=DOMAIN + "-1001", object_guid=uuid4(), account="synthetic-user",
                upn="synthetic-user@example.test", display_name="Тестовый пользователь",
                enabled=False, primary_group_id=513, **changes)


def page(**changes):
    value = dict(collector_id=uuid4(), batch_id=uuid4().hex, snapshot_id=uuid4(),
                 schema_version=1, sent_at=NOW, observed_at=NOW, scope=scope(),
                 page_index=0, records=[user()], finished=True, complete=True,
                 total_records=1)
    value.update(changes)
    return value


def test_disabled_user_and_nondefault_primary_group_remain_observations():
    value = user()
    value["primary_group_id"] = 1007
    record = DirectoryUser.model_validate(value)
    assert not record.enabled and record.primary_group_id == 1007
    assert "role" not in record.model_dump()
    assert DirectoryPage.model_validate(page()).complete


@pytest.mark.parametrize("field,value", [
    ("page_index", 512), ("page_index", True), ("total_records", 100001),
    ("records", [user()] * 257), ("finished", "true"), ("source_id", uuid4()),
    ("complete", False), ("error_code", "LDAP_UNAVAILABLE"),
    ("observed_at", NOW + timedelta(seconds=1)),
])
def test_page_bounds_and_terminal_consistency(field, value):
    invalid = page()
    invalid[field] = value
    with pytest.raises(ValidationError):
        DirectoryPage.model_validate(invalid)


def test_incomplete_terminal_and_nonterminal_page_are_explicit():
    partial = page(complete=False, error_code="LDAP_UNAVAILABLE")
    assert not DirectoryPage.model_validate(partial).complete
    collecting = page(finished=False, complete=False, total_records=None)
    assert not DirectoryPage.model_validate(collecting).finished


@pytest.mark.parametrize("value", [
    {"dns_domain": "other.test\n", "domain_sid": DOMAIN},
    {"dns_domain": "example.test", "domain_sid": "S-1-5-18"},
    {"dns_domain": "127.0.0.1", "domain_sid": DOMAIN},
])
def test_domain_scope_cannot_be_an_ip_or_system_identity(value):
    with pytest.raises(ValidationError):
        DirectoryScope.model_validate(value)


def test_foreign_user_sid_and_duplicate_identity_are_refused():
    foreign = user()
    foreign["sid"] = "S-1-5-21-40-50-60-1001"
    with pytest.raises(ValidationError):
        DirectoryPage.model_validate(page(records=[foreign]))
    duplicate = user()
    with pytest.raises(ValidationError):
        DirectoryPage.model_validate(page(records=[duplicate, duplicate], total_records=2))


def client(**changes):
    value = dict(collector_id=uuid4(), batch_id=uuid4().hex, schema_version=1,
                 sent_at=NOW, scope=scope(), client_ip="192.0.2.10", observed_at=NOW,
                 expires_at=NOW + timedelta(seconds=300), status="CONFIRMED_CURRENT",
                 ptr_name="client.example.test", forward_addresses=["192.0.2.10"],
                 computer_sid=DOMAIN + "-1002", computer_guid=uuid4(),
                 computer_name="CLIENT", enabled=True)
    value.update(changes)
    return value


def test_confirmed_current_client_requires_every_corresponding_witness():
    assert ClientNameObservation.model_validate(client()).status == "CONFIRMED_CURRENT"
    for changes in ({"forward_addresses": ["192.0.2.11"]}, {"enabled": False},
                    {"ptr_name": "client.other.test"}, {"computer_guid": None},
                    {"expires_at": NOW + timedelta(seconds=901)},
                    {"computer_sid": "S-1-5-21-40-50-60-1002"}):
        with pytest.raises(ValidationError):
            ClientNameObservation.model_validate(client(**changes))


def test_unknown_is_finite_and_does_not_assert_a_computer():
    value = client(status="UNKNOWN", reason="DNS_UNAVAILABLE", ptr_name=None,
                   forward_addresses=[], computer_sid=None, computer_guid=None,
                   computer_name=None, enabled=None, expires_at=NOW+timedelta(seconds=30))
    assert ClientNameObservation.model_validate(value).computer_name is None
    with pytest.raises(ValidationError):
        ClientNameObservation.model_validate(client(status="UNKNOWN", reason="DNS_UNAVAILABLE"))
