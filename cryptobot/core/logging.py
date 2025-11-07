from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from loguru import logger as _logger


def setup_logging(log_dir: str = "logs", level: str = "INFO") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # Allow env override for log level (e.g., DEBUG)
    level = str(os.getenv("CRYPTOBOT_LOG_LEVEL", level)).upper()

    _logger.remove()
    # Optional console sink can be disabled for background threads in interactive shell
    disable_console = str(os.getenv("CRYPTOBOT_DISABLE_CONSOLE_LOG", "0")).lower() in {"1", "true", "yes"}
    if not disable_console:
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

    # Optional dedicated LLM trace sink (JSONL), enabled when CRYPTOBOT_LLM_DEBUG is set
    llm_debug = str(os.getenv("CRYPTOBOT_LLM_DEBUG", "0")).lower() in {"1", "true", "yes"}
    if llm_debug:
        _logger.add(
            Path(log_dir) / "llm.log",
            rotation="10 MB",
            retention=10,
            level="DEBUG",
            enqueue=True,
            backtrace=False,
            diagnose=False,
            filter=lambda record: record["extra"].get("component") == "llm",
            serialize=True,
        )


def get_logger() -> _logger.__class__:
    return _logger


def get_llm_logger() -> _logger.__class__:
    """Return a logger bound for LLM tracing. Only emits to llm.log when LLM debug is enabled."""
    return _logger.bind(component="llm")
