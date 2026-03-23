"""
Centralised logging configuration.
Call setup_logging() once at startup (done in cli/commands.py).
"""
import logging
import sys
from pathlib import Path

from app.config.settings import settings


def setup_logging(log_level: str | None = None) -> None:
    level = log_level or settings.log_level
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Ensure log dir exists
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
    ]

    log_file = settings.logs_dir / "outbound_machine.log"
    file_handler = logging.FileHandler(log_file)
    handlers.append(file_handler)

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=numeric_level,
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
        force=True,
    )

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "playwright"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
