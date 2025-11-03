from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from collections import defaultdict

import httpx


# DeepSeek pricing (2024) - DeepSeek-V3 (Chat)
# Input: $0.07 per million tokens (cache hit), $0.27 per million (cache miss)
# Output: $1.10 per million tokens
DEEPSEEK_INPUT_COST_HIT = 0.07 / 1_000_000  # $0.07 per million
DEEPSEEK_INPUT_COST_MISS = 0.27 / 1_000_000  # $0.27 per million
DEEPSEEK_OUTPUT_COST = 1.10 / 1_000_000  # $1.10 per million


@dataclass
class LLMCostTracker:
    """Track LLM API costs for monitoring and optimization."""
    total_calls: int = 0
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_cost: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    calls_by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    costs_by_type: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    start_time: float = field(default_factory=time.time)

    def record_call(
        self,
        call_type: str,
        tokens_input: int,
        tokens_output: int,
        from_cache: bool = False,
    ) -> None:
        """Record a single LLM API call."""
        self.total_calls += 1
        self.total_tokens_input += tokens_input
        self.total_tokens_output += tokens_output
        self.calls_by_type[call_type] += 1

        # Calculate cost
        if from_cache:
            input_cost = tokens_input * DEEPSEEK_INPUT_COST_HIT
            self.cache_hits += 1
        else:
            input_cost = tokens_input * DEEPSEEK_INPUT_COST_MISS
            self.cache_misses += 1
        output_cost = tokens_output * DEEPSEEK_OUTPUT_COST
        call_cost = input_cost + output_cost

        self.total_cost += call_cost
        self.costs_by_type[call_type] += call_cost

    def get_stats(self) -> Dict[str, Any]:
        """Get current cost statistics."""
        elapsed_hours = (time.time() - self.start_time) / 3600.0
        return {
            "total_calls": self.total_calls,
            "total_tokens_input": self.total_tokens_input,
            "total_tokens_output": self.total_tokens_output,
            "total_cost_usd": round(self.total_cost, 6),
            "cache_hit_rate": round(self.cache_hits / max(1, self.total_calls), 3),
            "calls_per_hour": round(self.total_calls / max(0.001, elapsed_hours), 2),
            "cost_per_hour": round(self.total_cost / max(0.001, elapsed_hours), 6),
            "estimated_daily_cost": round(self.total_cost / max(0.001, elapsed_hours) * 24, 2),
            "estimated_monthly_cost": round(self.total_cost / max(0.001, elapsed_hours) * 24 * 30, 2),
            "calls_by_type": dict(self.calls_by_type),
            "costs_by_type": {k: round(v, 6) for k, v in self.costs_by_type.items()},
        }

    def reset(self) -> None:
        """Reset all counters."""
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

    def score_risk(self, context: Dict) -> float:
        if not self.api_key:
            return 1.0
        prompt = (
            "You are a crypto trading risk controller. Given the context, output a single number risk multiplier between 0.0 and 1.5.\n"
            "Higher implies higher confidence to size up. Lower implies reduce size.\n"
            f"Context: {context}\n"
            "Output only the number."
        )
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "You output only a number."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.2,
                        "max_tokens": 10,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                # Track cost
                tokens_input = data.get("usage", {}).get("prompt_tokens", len(prompt.split()) * 1.3)
                tokens_output = data.get("usage", {}).get("completion_tokens", 10)
                self._cost_tracker.record_call("score_risk", int(tokens_input), int(tokens_output), from_cache=False)
                return float(content)
        except Exception:
            return 1.0

    def decide_futures(self, context: Dict) -> Dict:
        """Return a decision dict: {direction: long|short|flat, leverage: int, confidence: float}.
        Fallback: neutral decision with leverage 1.
        """
        # Cheap default when no key configured
        if not self.api_key:
            return {"direction": "flat", "leverage": 1, "confidence": 0.0}

        prompt = (
            "You are an expert crypto futures trader. Given recent OHLCV and context, "
            "decide if the next action should be long, short, or flat (no position), and recommend leverage (1-20).\n"
            "Rules: prefer cost efficiency (user only has ~20 USDT); avoid overtrading; use higher leverage only when volatility is low and trend strong.\n"
            "Output strict JSON with keys: direction(one of 'long','short','flat'), leverage(integer 1..20), confidence(float 0..1). No extra text.\n"
            f"Context: {context}\n"
        )
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "Answer with only valid compact JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.2,
                        "max_tokens": 64,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                # Track cost
                tokens_input = data.get("usage", {}).get("prompt_tokens", len(prompt.split()) * 1.3)
                tokens_output = data.get("usage", {}).get("completion_tokens", 64)
                self._cost_tracker.record_call("decide_futures", int(tokens_input), int(tokens_output), from_cache=False)
                # Best-effort JSON extract
                import json, re
                m = re.search(r"\{[\s\S]*\}", content)
                obj = json.loads(m.group(0) if m else content)
                direction = str(obj.get("direction", "flat")).lower()
                if direction not in {"long", "short", "flat"}:
                    direction = "flat"
                lev = int(obj.get("leverage", 1))
                lev = max(1, min(20, lev))
                conf = float(obj.get("confidence", 0.0))
                conf = max(0.0, min(1.0, conf))
                return {"direction": direction, "leverage": lev, "confidence": conf}
        except Exception:
            return {"direction": "flat", "leverage": 1, "confidence": 0.0}

    def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 512,
        json_mode: bool = True,
    ) -> Dict[str, Any]:
        """Generic LLM call with basic caching and retry.

        - Caches responses by prompt content and key params
        - Retries with exponential backoff on transient errors
        - If json_mode, attempts to parse JSON robustly
        """
        # No key → behave deterministically
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
            "json_mode": json_mode,
            "model": self.model,
        }
        cache_key = hashlib.sha256(json.dumps(cache_key_src, sort_keys=True).encode("utf-8")).hexdigest()
        if cache_key in self._cache:
            # Estimate tokens for cache hit (same as original call)
            tokens_input = len(prompt.split()) * 1.3
            tokens_output = max_tokens * 0.3  # Estimate average output
            self._cost_tracker.record_call("call_cached", int(tokens_input), int(tokens_output), from_cache=True)
            return self._cache[cache_key]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if json_mode:
            messages.append({"role": "system", "content": "Respond with only strict JSON."})
        messages.append({"role": "user", "content": prompt})

        last_err: Optional[Exception] = None
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
                    # Track cost
                    tokens_input = data.get("usage", {}).get("prompt_tokens", len(prompt.split()) * 1.3)
                    tokens_output = data.get("usage", {}).get("completion_tokens", max_tokens * 0.3)
                    call_type = "call"  # Default, can be overridden by caller
                    self._cost_tracker.record_call(call_type, int(tokens_input), int(tokens_output), from_cache=False)
                    if json_mode:
                        m = re.search(r"\{[\s\S]*\}", content)
                        content = m.group(0) if m else content
                        obj = json.loads(content)
                    else:
                        obj = {"text": content}
                    self._cache[cache_key] = obj
                    return obj
            except Exception as e:  # pragma: no cover - network path
                last_err = e
                _time.sleep(1.5 ** attempt)

        # On failure, return empty dict for json_mode
        return {}
