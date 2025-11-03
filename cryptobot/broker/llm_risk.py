from __future__ import annotations

from typing import Dict, Any

from cryptobot.llm.client import LLMClient


class LLMRiskManager:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def get_portfolio_state(self) -> Dict[str, Any]:
        # Hook for future integration; return minimal state for LLM context
        return {}

    def calculate_position_size(
        self,
        strategy: str,
        opportunity: Dict[str, Any],
        confidence: float,
        market_volatility: float,
    ) -> float:
        context = {
            "strategy": strategy,
            "opportunity": opportunity,
            "confidence": confidence,
            "volatility": market_volatility,
            "portfolio": self.get_portfolio_state(),
        }
        prompt = (
            f"Calculate optimal position size (USD): {context}\n"
            "Output: {\"size_usd\": XXXX.XX}"
        )
        decision = self.llm.call(prompt=prompt, json_mode=True)
        try:
            return float(decision.get("size_usd", 0.0))
        except Exception:
            return 0.0


