from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from loguru import logger as _logger


def setup_logging(log_dir: str = "logs", level: str = "INFO") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    _logger.remove()
    _logger.add(
        sink=lambda msg: print(msg, end=""),
        level=level,
        colorize=True,
        backtrace=False,
        diagnose=False,
    )
    _logger.add(
        Path(log_dir) / "cryptobot.log",
        rotation="10 MB",
        retention=10,
        level=level,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )


def get_logger() -> _logger.__class__:
    return _logger
