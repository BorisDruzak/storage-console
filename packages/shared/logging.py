import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Allowlisted machine events; never serialize arbitrary exception/config values."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            'timestamp': datetime.now(UTC).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'event': getattr(record, 'event', 'runtime_log'),
        })


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access'):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
