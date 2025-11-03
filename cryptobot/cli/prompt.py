from __future__ import annotations

from typing import Any, Dict


def build_prompt(*, exchange: str, status: str, fmt: str = "[CryptoBot@{exchange}:{status}] > ", stats: Dict[str, Any] | None = None) -> str:
    s = fmt.format(exchange=exchange, status=status)
    return s


