from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from cryptobot.llm.client import LLMClient
from cryptobot.core.logging import get_llm_logger


@dataclass
class LLMRiskOverlay:
    enabled: bool = False
    client: Optional[LLMClient] = None

    def risk_multiplier(self, context: Optional[dict] = None) -> float:
        if not self.enabled:
            get_llm_logger().debug({
                "event": "llm_overlay_skip",
                "reason": "disabled",
            })
            return 1.0
        if self.client is None:
            get_llm_logger().debug({
                "event": "llm_overlay_skip",
                "reason": "no_client",
            })
            return 1.0
        try:
            ctx = context or {}
            get_llm_logger().debug({
                "event": "llm_overlay_call",
                "context_keys": list(ctx.keys()),
            })
            mult = float(self.client.score_risk(ctx))
            # clamp to a sane range
            if mult != mult or mult == float("inf") or mult == float("-inf"):
                return 1.0
            out = max(0.0, min(1.5, mult))
            get_llm_logger().debug({
                "event": "llm_overlay_result",
                "multiplier": mult,
                "clamped": out,
            })
            return out
        except Exception:
            return 1.0
