"""structlog configuration, used by both dev and prod settings.

Stdlib ``logging.getLogger`` records (the majority of app modules) render
through the same processor chain as structlog events via
``ProcessorFormatter``, so every line carries timestamp/level/logger name
in both the dev console and prod JSON output.
"""

import logging

import structlog
from structlog.typing import Processor


def configure_structlog(*, dev: bool) -> None:
    renderer: Processor = (
        structlog.dev.ConsoleRenderer(colors=True) if dev else structlog.processors.JSONRenderer()
    )
    # Doubles as ProcessorFormatter's foreign_pre_chain so stdlib records
    # get the same enrichment as structlog events.
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    # Re-configuration (e.g. repeated settings import) must not stack handlers.
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
