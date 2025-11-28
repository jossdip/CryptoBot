from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from collections import defaultdict

import httpx
from loguru import logger as log
from cryptobot.core.logging import get_llm_logger
from cryptobot.llm.prompts import TECHNICAL_ANALYSIS_PROMPT

# DeepSeek pricing (2024)
DEEPSEEK_INPUT_COST_HIT = 0.07 / 1_000_000
DEEPSEEK_INPUT_COST_MISS = 0.27 / 1_000_000
DEEPSEEK_OUTPUT_COST = 1.10 / 1_000_000


@dataclass
class LLMCostTracker:
    """Track LLM API costs."""
    total_calls: int = 0
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_cost: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    calls_by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    costs_by_type: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    start_time: float = field(default_factory=time.time)

    def record_call(self, call_type: str, tokens_input: int, tokens_output: int, from_cache: bool = False) -> None:
        self.total_calls += 1
        self.total_tokens_input += tokens_input
        self.total_tokens_output += tokens_output
        self.calls_by_type[call_type] += 1

        if from_cache:
            input_cost = tokens_input * DEEPSEEK_INPUT_COST_HIT
            self.cache_hits += 1
        else:
            input_cost = tokens_input * DEEPSEEK_INPUT_COST_MISS
            self.cache_misses += 1
        output_cost = tokens_output * DEEPSEEK_OUTPUT_COST
        self.total_cost += (input_cost + output_cost)
        self.costs_by_type[call_type] += (input_cost + output_cost)

    def get_stats(self) -> Dict[str, Any]:
        elapsed_hours = (time.time() - self.start_time) / 3600.0
        return {
            "total_calls": self.total_calls,
            "total_cost_usd": round(self.total_cost, 6),
            "calls_per_hour": round(self.total_calls / max(0.001, elapsed_hours), 2),
        }

    def reset(self) -> None:
        self.total_calls = 0
        self.total_tokens_input = 0
        self.total_tokens_output = 0
        self.total_cost = 0.0
        self.cache_hits = 0
        self.cache_misses = 0
        self.calls_by_type.clear()
        self.costs_by_type.clear()
        self.start_time = time.time()


@dataclass
class LLMClient:
    base_url: str
    api_key: str
    model: str
    _cache: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _cost_tracker: LLMCostTracker = field(default_factory=LLMCostTracker)

    @classmethod
    def from_env(cls) -> "LLMClient":
        base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
        api_key = os.getenv("LLM_API_KEY", "")
        model = os.getenv("LLM_MODEL", "deepseek-chat")
        return cls(base_url=base_url, api_key=api_key, model=model)

    def analyze_technical_context(self, symbol: str, ohlcv: str, rsi: float, volatility: float, volume_profile: str, funding_rate: float) -> Dict[str, Any]:
        """
        Analyze technical context using LLM to validate breakout.
        """
        if not self.api_key:
            return {"valid_breakout": False, "confidence": 0.0}
        
        prompt = TECHNICAL_ANALYSIS_PROMPT.format(
            symbol=symbol,
            lookback=len(ohlcv.splitlines()) if ohlcv else 0,
            ohlcv_data=ohlcv,
            rsi=rsi,
            volatility=volatility,
            volume_profile=volume_profile,
            funding_rate=funding_rate
        )

        return self.call(
            prompt=prompt,
            system_prompt="You are a strictly analytical technical trading assistant. Output JSON only.",
            temperature=0.1, # Low temp for consistent analysis
            max_tokens=256,
            json_mode=True
        )

    def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 512,
        json_mode: bool = True,
    ) -> Dict[str, Any]:
        if not self.api_key:
            return {}

        import hashlib
        import json
        import re
        import time as _time

        cache_key_src = {
            "prompt": prompt,
            "system_prompt": system_prompt or "",
            "temperature": temperature,
            "max_tokens": max_tokens,
            "model": self.model,
        }
        cache_key = hashlib.sha256(json.dumps(cache_key_src, sort_keys=True).encode("utf-8")).hexdigest()
        if cache_key in self._cache:
            self._cost_tracker.record_call("call_cached", 0, 0, from_cache=True)
            return self._cache[cache_key]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if json_mode:
            messages.append({"role": "system", "content": "Respond with only strict JSON."})
        messages.append({"role": "user", "content": prompt})

        for attempt in range(3):
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": self.model,
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    content = str(data["choices"][0]["message"]["content"]).strip()
                    usage = data.get("usage", {})
                    tokens_input = usage.get("prompt_tokens", 0)
                    tokens_output = usage.get("completion_tokens", 0)
                    
                    self._cost_tracker.record_call("generic", int(tokens_input), int(tokens_output), from_cache=False)
                    
                    if json_mode:
                        m = re.search(r"\{[\s\S]*\}", content)
                        content = m.group(0) if m else content
                        obj = json.loads(content)
                    else:
                        obj = {"text": content}
                    self._cache[cache_key] = obj
                    return obj
            except Exception as e:
                log.warning(f"LLM call failed attempt {attempt+1}: {e}")
                _time.sleep(1.0)

        return {}
