from __future__ import annotations

import os
import json
import ast
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
        def _llm_pretty_formatter(record: dict) -> str:
            # Extract payload from message (dict serialized as str) or JSON
            raw_msg = record.get("message", "")
            payload: dict
            try:
                payload = ast.literal_eval(raw_msg) if isinstance(raw_msg, str) else {}
            except Exception:
                try:
                    payload = json.loads(raw_msg)
                except Exception:
                    payload = {"text": raw_msg}

            extra = record.get("extra", {}) or {}
            def g(key: str):
                return payload.get(key, extra.get(key))

            # Configurable truncation for prompt/response
            try:
                max_chars = int(os.getenv("CRYPTOBOT_LLM_PRETTY_MAX_CHARS", "4000"))
            except Exception:
                max_chars = 4000

            def truncate(txt: object) -> str:
                s = "" if txt is None else str(txt)
                return s if len(s) <= max_chars else (s[:max_chars] + "... (truncated)")

            ts = record.get("time").strftime("%Y-%m-%d %H:%M:%S") if record.get("time") else ""
            lvl = record.get("level").name if record.get("level") else "INFO"
            header = f"{ts} | {lvl} | LLM {g('event') or ''}"

            meta_keys = (
                "req_id", "call", "model", "latency_ms", "tokens",
                "estimated_cost_usd", "json_mode", "temperature", "max_tokens", "attempt",
            )
            meta = [f"{k}={g(k)}" for k in meta_keys if g(k) is not None]
            lines = [header]
            if meta:
                lines.append("  " + " ".join(meta))

            if g("context_keys") is not None:
                lines.append("  context_keys: " + ", ".join(map(str, g("context_keys"))))
            if g("recent_lengths") is not None:
                try:
                    lines.append("  recent_lengths:\n" + json.dumps(g("recent_lengths"), indent=2, ensure_ascii=False))
                except Exception:
                    pass
            if g("weights") is not None:
                try:
                    lines.append("  weights:\n" + json.dumps(g("weights"), indent=2, ensure_ascii=False))
                except Exception:
                    pass
            if g("decision") is not None:
                try:
                    lines.append("  decision:\n" + json.dumps(g("decision"), indent=2, ensure_ascii=False))
                except Exception:
                    pass
            if g("usage") is not None:
                try:
                    lines.append("  usage:\n" + json.dumps(g("usage"), indent=2, ensure_ascii=False))
                except Exception:
                    pass
            if g("reason") is not None:
                lines.append(f"  reason: {g('reason')}")

            if g("prompt") is not None:
                lines.append("\nPrompt:\n" + truncate(g("prompt")))
            if g("response") is not None:
                lines.append("\nResponse:\n" + truncate(g("response")))

            return "\n".join(lines) + "\n"

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
        _logger.add(
            Path(log_dir) / "llm_pretty.log",
            rotation="10 MB",
            retention=10,
            level="DEBUG",
            enqueue=True,
            backtrace=False,
            diagnose=False,
            filter=lambda record: record["extra"].get("component") == "llm",
            format=_llm_pretty_formatter,
        )


def get_logger() -> _logger.__class__:
    return _logger


def get_llm_logger() -> _logger.__class__:
    """Return a logger bound for LLM tracing. Only emits to llm.log when LLM debug is enabled."""
    return _logger.bind(component="llm")
