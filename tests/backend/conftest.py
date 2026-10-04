import hashlib
import os
import secrets
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, text

from apps.api.main import create_app
from apps.api.user_auth.bootstrap import bootstrap_admin
from apps.api.user_auth.dependencies import UserAuth
from apps.api.user_auth.sessions import SessionStore
from packages.shared.auth.configuration import AuthConfig
from packages.shared.models import metadata
from packages.shared.models.core import collectors, source_nodes
from packages.shared.models.security import roles, user_roles, users
from packages.shared.settings import Settings


@pytest.fixture
def ingest_setup():
    base = create_engine(os.environ["TEST_DATABASE_URL"])
    schema = "test_" + uuid4().hex
    with base.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        os.environ["TEST_DATABASE_URL"], connect_args={"options": f"-csearch_path={schema}"}
    )
    metadata.create_all(engine)
    source, collector = uuid4(), uuid4()
    token = secrets.token_urlsafe(32)
    with engine.begin() as connection:
        connection.execute(
            insert(source_nodes).values(
                id=source, source_type="FILESERVER", hostname="synthetic", instance_id=str(source)
            )
        )
        connection.execute(
            insert(collectors).values(
                id=collector,
                source_node_id=source,
                collector_type="WINDOWS",
                token_hash=hashlib.sha256(("collector:" + token).encode()).hexdigest(),
            )
        )
    client = TestClient(create_app(Settings(), engine))
    try:
        yield client, engine, collector, token, source
    finally:
        client.close()
        engine.dispose()
        with base.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


@pytest.fixture
def session_setup(ingest_setup):
    _, engine, *_ = ingest_setup
    user, role = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(users).values(id=user, username="synthetic", auth_provider="local")
        )
        connection.execute(insert(roles).values(id=role, code="storage_admin"))
        connection.execute(insert(user_roles).values(user_id=user, role_id=role))
    return SessionStore(engine), engine, user, role


@pytest.fixture
def authenticated_setup(ingest_setup):
    _, engine, collector, bearer, source = ingest_setup
    origin = "https://storage.example.test"
    password = secrets.token_urlsafe(32)
    bootstrap_admin(engine, "synthetic-read-admin", password)
    auth = UserAuth(engine, AuthConfig(origin, True))
    with TestClient(create_app(Settings(), engine, user_auth=auth), base_url=origin) as client:
        response = client.post(
            "/api/v1/auth/login",
            headers={"Origin": origin},
            json={"provider": "local", "username": "synthetic-read-admin", "password": password},
        )
        assert response.status_code == 200
        yield client, engine, collector, bearer, source
