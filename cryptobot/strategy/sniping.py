from __future__ import annotations

from typing import Dict, Any, List

from loguru import logger as log

from cryptobot.broker.hyperliquid_broker import HyperliquidBroker
from cryptobot.llm.client import LLMClient


class SnipingStrategy:
    def __init__(self, broker: HyperliquidBroker, llm: LLMClient | None = None) -> None:
        self.broker = broker
        self.llm = llm

    def monitor_new_listings(self) -> List[Dict[str, Any]]:
        """Placeholder: return detected new listings if any."""
        return []

    def analyze_opportunity(self, token: Dict[str, Any]) -> Dict[str, Any]:
        """Quick analysis; call LLM when available."""
        if self.llm is None:
            return {"score": 0.0, "confidence": 0.0}
        prompt = (
            f"Given this new listing context, rate attractiveness 0..1. Token: {token}. "
            "Respond with JSON: {\"score\": float, \"confidence\": float}"
        )
        return self.llm.call(prompt=prompt, json_mode=True) or {"score": 0.0, "confidence": 0.0}

    def detect_opportunities(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Combine monitoring and quick filters
        return self.monitor_new_listings()

    def execute(self, token: str, decision: Dict[str, Any]) -> bool:
        try:
            size_usd = float(decision.get("size_usd", 0.0))
            if size_usd <= 0:
                return False
            direction = str(decision.get("direction", "long")).lower()
            side = "buy" if direction == "long" else "sell"
            resp = self.broker.place_order(symbol=token, side=side, size=0.001, order_type="market")
            return bool(resp.get("ok", False))
        except Exception as e:
            log.error(f"Sniping execution failed: {e}")
            return False


