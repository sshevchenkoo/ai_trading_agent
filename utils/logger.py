import structlog
import logging
from config import settings


def setup_logging():
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


def get_logger(name: str):
    return structlog.get_logger(name)
