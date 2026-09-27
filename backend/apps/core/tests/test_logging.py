"""configure_structlog — stdlib logging records must render through structlog.

72 of 74 app modules use ``logging.getLogger``; their records must pass
through the same ProcessorFormatter pipeline as structlog events, or prod
output degrades to bare message strings with no timestamp/level/name.
"""

import json
import logging

import pytest
import structlog

from apps.core.logging import configure_structlog


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _make_stdlib_record() -> logging.LogRecord:
    logger = logging.getLogger("apps.whatever")
    capture = _CaptureHandler()
    logger.addHandler(capture)
    try:
        logger.warning("something happened")
    finally:
        logger.removeHandler(capture)
    assert len(capture.records) == 1
    return capture.records[0]


def _root_processor_formatter() -> structlog.stdlib.ProcessorFormatter:
    formatters = [
        h.formatter
        for h in logging.getLogger().handlers
        if isinstance(h.formatter, structlog.stdlib.ProcessorFormatter)
    ]
    assert len(formatters) == 1, "root must carry exactly one structlog-formatted handler"
    return formatters[0]


@pytest.fixture
def _restore_logging():
    yield
    # Test settings import dev settings, which configured dev=True at import.
    configure_structlog(dev=True)


@pytest.mark.usefixtures("_restore_logging")
def test_prod_stdlib_record_renders_as_json_with_timestamp_level_name():
    configure_structlog(dev=False)
    rendered = _root_processor_formatter().format(_make_stdlib_record())
    payload = json.loads(rendered)
    assert payload["event"] == "something happened"
    assert payload["level"] == "warning"
    assert payload["logger"] == "apps.whatever"
    assert payload["timestamp"]
