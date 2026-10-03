from typing import cast

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.types import Event, Hint

from packages.shared.settings import Settings


def sanitize_event(event: Event, _: Hint) -> Event:
    """Keep diagnosis structure, discard arbitrary payloads and exception values."""
    fields = {'event_id', 'timestamp', 'platform', 'level', 'logger', 'release', 'environment'}
    result = cast(Event, {key: value for key, value in event.items() if key in fields})
    if event.get('exception'):
        result['exception'] = {'values': [{
            'type': value.get('type'),
            'stacktrace': {'frames': [{
                key: frame[key] for key in ('filename', 'function', 'lineno') if key in frame
            } for frame in value.get('stacktrace', {}).get('frames', [])]},
        } for value in event['exception'].get('values', [])]}
    return result


def configure_sentry(settings: Settings) -> None:
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            release=settings.app_release,
            send_default_pii=False,
            before_send=sanitize_event,
            include_local_variables=False,
            traces_sample_rate=0.0,
            integrations=[FastApiIntegration()],
        )
