from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class LLMDecision:
    timestamp: float
    decision_type: str  # "allocation" or "trade"
    prompt: str
    response: str
    reasoning: str
    sentiment: str  # "confident", "cautious", "aggressive", "neutral"
    confidence: float
    metadata: Dict[str, Any]


def extract_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {}
        return {}


def derive_sentiment(obj: Dict[str, Any], default: str = "neutral") -> str:
    conf = obj.get("confidence")
    try:
        c = float(conf)
        if c >= 0.8:
            return "confident"
        if c >= 0.6:
            return "aggressive"
        if c >= 0.4:
            return "neutral"
        return "cautious"
    except Exception:
        return default


def extract_reasoning(text: str, fallback: str = "") -> str:
    # Heuristic: look for keys or explanations commonly returned by LLM
    obj = extract_json(text)
    for key in ("reasoning", "rationale", "explanation", "why"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # Fallback: truncate text as pseudo-reasoning
    snippet = text.strip()
    return snippet[:480]


def build_decision(
    *,
    timestamp: float,
    decision_type: str,
    prompt: str,
    raw_response: str | Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> LLMDecision:
    if isinstance(raw_response, dict):
        response_text = json.dumps(raw_response, ensure_ascii=False)
        obj = raw_response
    else:
        response_text = raw_response
        obj = extract_json(raw_response)
    reasoning = extract_reasoning(response_text, "")
    sentiment = derive_sentiment(obj)
    confidence = float(obj.get("confidence", 0.0)) if isinstance(obj, dict) else 0.0
    return LLMDecision(
        timestamp=timestamp,
        decision_type=decision_type,
        prompt=prompt,
        response=response_text,
        reasoning=reasoning,
        sentiment=sentiment,
        confidence=confidence,
        metadata=metadata or {},
    )


