from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from cryptobot.llm.client import LLMClient
from cryptobot.llm.prompts import ALLOCATION_PROMPT_TEMPLATE, TRADE_PROMPT_TEMPLATE, POSITION_PROMPT_TEMPLATE, RUNTIME_PARAMS_PROMPT_TEMPLATE
from cryptobot.core.logging import get_llm_logger


@dataclass
class StrategyWeight:
    """
    Pondération des stratégies de trading (COMMENT trader).
    Les signaux (Reddit, Twitter, Polymarket, market cap, volume, etc.) 
    sont utilisés par le LLM pour évaluer la confiance et décider quand trader,
    mais ne sont PAS des stratégies séparées.
    """
    market_making: float = 0.35  # Base stable, revenus réguliers (stratégie #1 en day trading)
    momentum: float = 0.25  # Suit les tendances fortes (stratégie #2)
    scalping: float = 0.15  # Trades fréquents, profits réguliers (stratégie #3)
    arbitrage: float = 0.12  # Opportunités sûres mais limitées (stratégie #4)
    breakout: float = 0.08  # Moins fréquent mais gros potentiel (stratégie #5)
    sniping: float = 0.05  # Très risqué, limité (stratégie #6)

    def normalize(self) -> None:
        total = float(sum(vars(self).values()))
        if total <= 0.0:
            return
        for key in vars(self):
            setattr(self, key, float(getattr(self, key)) / total)


class LLMOrchestrator:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self.weights = StrategyWeight()
        self.performance_history: List[Dict[str, Any]] = []
        # Optional sink to record decisions (set by monitor/interactive layer)
        self._decision_sink: Optional[Callable[[Dict[str, Any]], None]] = None
        # Last runtime parameters decided by LLM (optional)
        self._runtime_params: Dict[str, Any] = {}

    def set_decision_sink(self, sink: Optional[Callable[[Dict[str, Any]], None]]) -> None:
        self._decision_sink = sink

    def _get_recent_returns(self, window: int = 24) -> List[Dict[str, Any]]:
        return self.performance_history[-window:]

    def _build_allocation_prompt(self, context: Dict[str, Any]) -> str:
        return ALLOCATION_PROMPT_TEMPLATE.format(
            market_data=context.get("market"),
            portfolio_state=context.get("portfolio"),
            performance_metrics=context.get("performance"),
            sentiment_data=context.get("sentiment"),
            current_weights=context.get("current_weights"),
            recent_returns=context.get("recent_returns"),
        )

    def _build_trade_prompt(self, context: Dict[str, Any]) -> str:
        return TRADE_PROMPT_TEMPLATE.format(
            strategy_name=context.get("strategy"),
            opportunity=context.get("opportunity"),
            market_context=context.get("market"),
            portfolio_state=context.get("portfolio"),
            current_weights=context.get("current_weights"),
            risk_tolerance=context.get("risk_tolerance"),
        )

    def _parse_strategy_weights(self, llm_response: Dict[str, Any]) -> StrategyWeight:
        # best effort parsing; ensure constraints
        sw = StrategyWeight(
            market_making=max(0.25, float(llm_response.get("market_making", self.weights.market_making))),  # Min 25%
            momentum=float(llm_response.get("momentum", self.weights.momentum)),
            scalping=float(llm_response.get("scalping", self.weights.scalping)),
            arbitrage=float(llm_response.get("arbitrage", self.weights.arbitrage)),
            breakout=float(llm_response.get("breakout", self.weights.breakout)),
            sniping=min(0.10, float(llm_response.get("sniping", self.weights.sniping))),  # Max 10%
        )
        sw.normalize()
        return sw

    def _parse_trade_decision(self, llm_response: Dict[str, Any]) -> Dict[str, Any]:
        # Normalize fields and defaults
        execute = bool(llm_response.get("execute", False))
        direction = str(llm_response.get("direction", "flat")).lower()
        if direction not in {"long", "short", "flat"}:
            direction = "flat"
        size_usd = max(0.0, float(llm_response.get("size_usd", 0.0)))
        leverage = max(1, min(50, int(llm_response.get("leverage", 1))))
        sl = llm_response.get("stop_loss_pct")
        tp = llm_response.get("take_profit_pct")
        confidence = float(llm_response.get("confidence", 0.0))
        return {
            "execute": execute,
            "direction": direction,
            "size_usd": size_usd,
            "leverage": leverage,
            "stop_loss_pct": float(sl) if sl is not None else None,
            "take_profit_pct": float(tp) if tp is not None else None,
            "confidence": max(0.0, min(1.0, confidence)),
        }

    def _calculate_risk_tolerance(self) -> float:
        # Simple heuristic; integrate richer logic later
        if not self.performance_history:
            return 0.5
        recent = self.performance_history[-50:]
        avg_pnl = sum(float(x.get("pnl", 0.0)) for x in recent) / max(1, len(recent))
        # map PnL into 0..1 risk tolerance
        return max(0.0, min(1.0, 0.5 + avg_pnl))

    def decide_strategy_allocation(
        self,
        market_data: Dict[str, Any],
        portfolio_state: Dict[str, Any],
        sentiment_data: Dict[str, Any],
        performance_metrics: Dict[str, Any],
    ) -> StrategyWeight:
        context = {
            "market": market_data,
            "portfolio": portfolio_state,
            "sentiment": sentiment_data,
            "performance": performance_metrics,
            "current_weights": vars(self.weights),
            "recent_returns": self._get_recent_returns(),
        }
        get_llm_logger().debug({
            "event": "orchestrator_build_prompt",
            "type": "allocation",
            "context_keys": list(context.keys()),
        })
        prompt = self._build_allocation_prompt(context)
        response = self.llm.call(prompt=prompt, json_mode=True)
        new_weights = self._parse_strategy_weights(response)
        self.weights = new_weights
        get_llm_logger().debug({
            "event": "orchestrator_decision",
            "type": "allocation",
            "weights": vars(new_weights),
        })
        # Record decision (best-effort)
        try:
            from time import time as _time
            from json import dumps as _dumps
            from cryptobot.monitor.insights import build_decision as _build_decision

            if self._decision_sink:
                decision = _build_decision(
                    timestamp=_time(),
                    decision_type="allocation",
                    prompt=prompt,
                    raw_response=response if isinstance(response, dict) else _dumps(response),
                    metadata={"type": "allocation"},
                )
                self._decision_sink(
                    {
                        "timestamp": decision.timestamp,
                        "decision_type": decision.decision_type,
                        "prompt": decision.prompt,
                        "response": decision.response,
                        "reasoning": decision.reasoning,
                        "sentiment": decision.sentiment,
                        "confidence": decision.confidence,
                        "metadata": decision.metadata,
                    }
                )
        except Exception:
            pass
        return new_weights

    def decide_trade(
        self,
        strategy_name: str,
        opportunity: Dict[str, Any],
        market_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        context = {
            "strategy": strategy_name,
            "opportunity": opportunity,
            "market": market_context,
            "portfolio": market_context.get("portfolio", {}),
            "current_weights": vars(self.weights),
            "risk_tolerance": self._calculate_risk_tolerance(),
        }
        get_llm_logger().debug({
            "event": "orchestrator_build_prompt",
            "type": "trade",
            "strategy": strategy_name,
            "context_keys": list(context.keys()),
        })
        prompt = self._build_trade_prompt(context)
        response = self.llm.call(prompt=prompt, json_mode=True)
        decision = self._parse_trade_decision(response)
        get_llm_logger().debug({
            "event": "orchestrator_decision",
            "type": "trade",
            "strategy": strategy_name,
            "decision": decision,
        })
        # Record decision (best-effort)
        try:
            from time import time as _time
            from json import dumps as _dumps
            from cryptobot.monitor.insights import build_decision as _build_decision

            if self._decision_sink:
                d = _build_decision(
                    timestamp=_time(),
                    decision_type="trade",
                    prompt=prompt,
                    raw_response=response if isinstance(response, dict) else _dumps(response),
                    metadata={"strategy": strategy_name, "opportunity": opportunity},
                )
                self._decision_sink(
                    {
                        "timestamp": d.timestamp,
                        "decision_type": d.decision_type,
                        "prompt": d.prompt,
                        "response": d.response,
                        "reasoning": d.reasoning,
                        "sentiment": d.sentiment,
                        "confidence": d.confidence,
                        "metadata": d.metadata,
                    }
                )
        except Exception:
            pass
        return decision

    def update_performance(self, strategy: str, pnl: float) -> None:
        self.performance_history.append({
            "strategy": strategy,
            "pnl": float(pnl),
            "timestamp": time.time(),
        })
        if len(self.performance_history) > 1000:
            self.performance_history = self.performance_history[-1000:]

    # Position management (exits)
    def _build_position_prompt(self, context: Dict[str, Any]) -> str:
        return POSITION_PROMPT_TEMPLATE.format(
            position=context.get("position"),
            market_context=context.get("market"),
            portfolio_state=context.get("portfolio"),
            risk_tolerance=context.get("risk_tolerance"),
        )

    def _parse_position_decision(self, llm_response: Dict[str, Any]) -> Dict[str, Any]:
        close = bool(llm_response.get("close", False))
        size_pct = float(llm_response.get("size_pct", 0.0))
        order_type = str(llm_response.get("order_type", "market")).lower()
        limit_offset_pct = float(llm_response.get("limit_offset_pct", 0.0005))
        confidence = float(llm_response.get("confidence", 0.0))
        set_bracket = bool(llm_response.get("set_bracket", False))
        tp_pct = float(llm_response.get("tp_pct", 0.0))
        sl_pct = float(llm_response.get("sl_pct", 0.0))
        trailing_pct = float(llm_response.get("trailing_pct", 0.0))
        # Clamp values
        if close:
            size_pct = max(0.1, min(1.0, size_pct))
        else:
            size_pct = 0.0
        if order_type not in {"market", "limit"}:
            order_type = "market"
        limit_offset_pct = max(0.0001, min(0.005, limit_offset_pct))
        # Bracket clamps
        if set_bracket and not close:
            tp_pct = max(0.002, min(0.02, tp_pct or 0.008))
            sl_pct = max(0.003, min(0.02, sl_pct or 0.005))
            trailing_pct = max(0.0, min(0.02, trailing_pct or 0.0))
        else:
            set_bracket = False
        return {
            "close": close,
            "size_pct": size_pct,
            "order_type": order_type,
            "limit_offset_pct": limit_offset_pct,
            "confidence": max(0.0, min(1.0, confidence)),
            "set_bracket": set_bracket,
            "tp_pct": tp_pct if set_bracket else 0.0,
            "sl_pct": sl_pct if set_bracket else 0.0,
            "trailing_pct": trailing_pct if set_bracket else 0.0,
        }

    def decide_position_management(
        self,
        *,
        position: Dict[str, Any],
        market_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        context = {
            "position": position,
            "market": market_context,
            "portfolio": market_context.get("portfolio", {}),
            "risk_tolerance": self._calculate_risk_tolerance(),
        }
        get_llm_logger().debug({
            "event": "orchestrator_build_prompt",
            "type": "position",
            "context_keys": list(context.keys()),
        })
        prompt = self._build_position_prompt(context)
        response = self.llm.call(prompt=prompt, json_mode=True)
        decision = self._parse_position_decision(response)
        get_llm_logger().debug({
            "event": "orchestrator_decision",
            "type": "position",
            "decision": decision,
        })
        # Record decision (best-effort)
        try:
            from time import time as _time
            from json import dumps as _dumps
            from cryptobot.monitor.insights import build_decision as _build_decision
            if self._decision_sink:
                d = _build_decision(
                    timestamp=_time(),
                    decision_type="position",
                    prompt=prompt,
                    raw_response=response if isinstance(response, dict) else _dumps(response),
                    metadata={"position": position},
                )
                self._decision_sink(
                    {
                        "timestamp": d.timestamp,
                        "decision_type": d.decision_type,
                        "prompt": d.prompt,
                        "response": d.response,
                        "reasoning": d.reasoning,
                        "sentiment": d.sentiment,
                        "confidence": d.confidence,
                        "metadata": d.metadata,
                    }
                )
        except Exception:
            pass
        return decision

    # Runtime parameter tuning (LLM-controlled)
    def _build_params_prompt(self, *, market_data: Dict[str, Any], portfolio_state: Dict[str, Any], performance_metrics: Dict[str, Any]) -> str:
        return RUNTIME_PARAMS_PROMPT_TEMPLATE.format(
            market_data=market_data,
            portfolio_state=portfolio_state,
            performance_metrics=performance_metrics,
        )

    def _parse_runtime_params(self, llm_response: Dict[str, Any]) -> Dict[str, Any]:
        # Defensive extraction and clamping
        out = {
            "market_making": {
                "edge_margin_bps": 2.0,
                "k_vol": 1.0,
                "passive_order_fraction_of_alloc": 0.02,
                "passive_order_usd_cap": 250.0,
                "passive_order_min_usd": 10.0,
            },
            "risk": {
                "min_hold_seconds": 20.0,
            },
        }
        try:
            mm = llm_response.get("market_making", {}) if isinstance(llm_response, dict) else {}
            rk = llm_response.get("risk", {}) if isinstance(llm_response, dict) else {}
            def clamp(v, lo, hi, dv):
                try:
                    x = float(v)
                    if x != x:  # NaN
                        return dv
                    return max(lo, min(hi, x))
                except Exception:
                    return dv
            out["market_making"]["edge_margin_bps"] = clamp(mm.get("edge_margin_bps"), 0.5, 10.0, out["market_making"]["edge_margin_bps"])
            out["market_making"]["k_vol"] = clamp(mm.get("k_vol"), 0.0, 3.0, out["market_making"]["k_vol"])
            out["market_making"]["passive_order_fraction_of_alloc"] = clamp(mm.get("passive_order_fraction_of_alloc"), 0.0, 0.2, out["market_making"]["passive_order_fraction_of_alloc"])
            out["market_making"]["passive_order_usd_cap"] = clamp(mm.get("passive_order_usd_cap"), 0.0, 2000.0, out["market_making"]["passive_order_usd_cap"])
            out["market_making"]["passive_order_min_usd"] = clamp(mm.get("passive_order_min_usd"), 0.0, 250.0, out["market_making"]["passive_order_min_usd"])
            out["risk"]["min_hold_seconds"] = clamp(rk.get("min_hold_seconds"), 5.0, 120.0, out["risk"]["min_hold_seconds"])
        except Exception:
            pass
        return out

    def decide_runtime_parameters(
        self,
        *,
        market_data: Dict[str, Any],
        portfolio_state: Dict[str, Any],
        performance_metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        ctx = {
            "market": market_data,
            "portfolio": portfolio_state,
            "performance": performance_metrics,
        }
        get_llm_logger().debug({
            "event": "orchestrator_build_prompt",
            "type": "params",
            "context_keys": list(ctx.keys()),
        })
        prompt = self._build_params_prompt(
            market_data=market_data,
            portfolio_state=portfolio_state,
            performance_metrics=performance_metrics,
        )
        response = self.llm.call(prompt=prompt, json_mode=True)
        params = self._parse_runtime_params(response)
        self._runtime_params = params
        get_llm_logger().debug({
            "event": "orchestrator_decision",
            "type": "params",
            "params": params,
        })
        # Sink (optional)
        try:
            from time import time as _time
            from json import dumps as _dumps
            from cryptobot.monitor.insights import build_decision as _build_decision
            if self._decision_sink:
                d = _build_decision(
                    timestamp=_time(),
                    decision_type="params",
                    prompt=prompt,
                    raw_response=response if isinstance(response, dict) else _dumps(response),
                    metadata={"type": "runtime_params"},
                )
                self._decision_sink(
                    {
                        "timestamp": d.timestamp,
                        "decision_type": d.decision_type,
                        "prompt": d.prompt,
                        "response": d.response,
                        "reasoning": d.reasoning,
                        "sentiment": d.sentiment,
                        "confidence": d.confidence,
                        "metadata": d.metadata,
                    }
                )
        except Exception:
            pass
        return params


