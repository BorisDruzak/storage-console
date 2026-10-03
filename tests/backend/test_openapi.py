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
