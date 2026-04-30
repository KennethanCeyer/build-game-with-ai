from __future__ import annotations

import logging
import os


_CONFIGURED = False
_FORMAT = "%(levelname)s %(name)s %(message)s"


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = os.environ.get("BWAI_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format=_FORMAT)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
