from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from cryptobot.llm.client import LLMClient


@dataclass
class LLMRiskOverlay:
    enabled: bool = False
    client: Optional[LLMClient] = None

    def risk_multiplier(self, context: Optional[dict] = None) -> float:
        if not self.enabled:
            return 1.0
        if self.client is None:
            return 1.0
        try:
            mult = float(self.client.score_risk(context or {}))
            # clamp to a sane range
            if mult != mult or mult == float("inf") or mult == float("-inf"):
                return 1.0
            return max(0.0, min(1.5, mult))
        except Exception:
            return 1.0
