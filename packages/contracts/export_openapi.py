"""Generate or verify the public contract without connecting to a database."""

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine

from apps.api.main import create_app
from packages.shared.settings import Settings

CONTRACT_PATH = Path(__file__).with_name("openapi") / "storage-console-v1.json"


def generated_contract() -> str:
    engine = create_engine("sqlite://")
    try:
        application = create_app(Settings(database_url="sqlite://", sentry_dsn=""), engine)
        return (
            json.dumps(application.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = generated_contract()
    if args.check:
        if not CONTRACT_PATH.exists() or CONTRACT_PATH.read_text(encoding="utf-8") != content:
            raise SystemExit("Published OpenAPI differs from runtime; regenerate the contract.")
        print("OpenAPI matches runtime.")
    else:
        CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONTRACT_PATH.write_text(content, encoding="utf-8", newline="\n")
        print("Public OpenAPI generated.")


if __name__ == "__main__":
    main()
