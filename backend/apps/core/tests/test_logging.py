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


@pytest.mark.usefixtures("_restore_logging")
def test_dev_stdlib_record_renders_with_timestamp_and_level():
    configure_structlog(dev=True)
    rendered = _root_processor_formatter().format(_make_stdlib_record())
    assert "something happened" in rendered
    assert "warning" in rendered
    assert "apps.whatever" in rendered
    # ISO TimeStamper output.
    assert "T" in rendered and ":" in rendered


@pytest.mark.usefixtures("_restore_logging")
def test_reconfigure_does_not_stack_root_handlers():
    configure_structlog(dev=False)
    configure_structlog(dev=False)
    _root_processor_formatter()


@pytest.mark.usefixtures("_restore_logging")
def test_structlog_event_renders_through_same_formatter():
    configure_structlog(dev=False)
    # LoggerFactory routes structlog events through the stdlib logger, so a
    # handler on the stdlib logger sees the wrap_for_formatter-produced record.
    capture = _CaptureHandler()
    stdlib_logger = logging.getLogger("apps.whatever")
    stdlib_logger.addHandler(capture)
    try:
        structlog.get_logger("apps.whatever").info("structlog side")
    finally:
        stdlib_logger.removeHandler(capture)
    assert len(capture.records) == 1
    payload = json.loads(_root_processor_formatter().format(capture.records[0]))
    assert payload["event"] == "structlog side"
    assert payload["level"] == "info"
    assert payload["logger"] == "apps.whatever"
    assert payload["timestamp"]
