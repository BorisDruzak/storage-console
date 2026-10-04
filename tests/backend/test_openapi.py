import json
from pathlib import Path

from packages.contracts.export_openapi import generated_contract


def test_published_openapi_matches_runtime_and_covers_every_ingest_domain():
    published = Path("packages/contracts/openapi/storage-console-v1.json").read_text(
        encoding="utf-8"
    )
    assert published == generated_contract()
    spec = json.loads(published)
    routes = [
        "heartbeat",
        "telemetry",
        "changes",
        "events",
        "inventory",
        "acl",
        "recovery",
        "hygiene",
        "diagnostic-bundles",
    ]
    refs = set()
    for route in routes:
        operation = spec["paths"]["/api/v1/ingest/" + route]["post"]
        ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        refs.add(ref)
        schema = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]
        assert schema["additionalProperties"] is False
        assert schema["properties"]["schema_version"]["const"] == 1
        assert schema["properties"]["records"]["maxItems"] == 10000
        assert operation["security"] == [{"CollectorToken": []}]
        assert operation["responses"]["422"]["content"]["application/json"]["schema"][
            "$ref"
        ].endswith("/ApiError")
    assert len(refs) == len(routes)


def test_auth_contract_exposes_user_cookie_and_never_server_credentials():
    spec = json.loads(generated_contract())
    schemes = spec["components"]["securitySchemes"]
    assert schemes["UserSession"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "__Host-storage_session",
    }
    for path, method in (("me", "get"), ("logout", "post")):
        operation = spec["paths"]["/api/v1/auth/" + path][method]
        assert operation["security"] == [{"UserSession": []}]
    operation = spec["paths"]["/api/v1/auth/login"]["post"]
    assert "security" not in operation
    assert set(operation["responses"]) >= {"200", "401", "403", "413", "415", "422", "429", "503"}
    schemas = spec["components"]["schemas"]
    assert schemas["LoginRequest"]["properties"]["password"]["writeOnly"] is True
    assert set(schemas["UserResponse"]["properties"]) == {"id", "username", "roles"}
