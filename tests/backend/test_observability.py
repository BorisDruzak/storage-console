import json

from packages.shared.observability import sanitize_event


def test_sentry_excludes_runtime_secrets_and_storage_evidence():
    event = {
        'event_id': 'example-event', 'level': 'error', 'environment': 'test',
        'request': {'data': 'private', 'headers': {'authorization': 'private'}},
        'user': {'username': 'private'}, 'extra': {'database_url': 'private'},
        'breadcrumbs': {'values': [{'message': 'private'}]},
        'exception': {'values': [{'type': 'RuntimeError', 'value': 'private',
                                  'stacktrace': {'frames': [{'filename': 'main.py',
                                      'function': 'run', 'lineno': 5,
                                      'vars': {'token': 'private'}}]}}]},
    }
    sanitized = sanitize_event(event, {})
    assert sanitized['event_id'] == 'example-event'
    assert sanitized['exception']['values'][0]['type'] == 'RuntimeError'
    assert sanitized['exception']['values'][0]['stacktrace']['frames'][0]['function'] == 'run'
    assert 'private' not in json.dumps(sanitized)
