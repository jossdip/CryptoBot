from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional

import httpx


@dataclass
class LLMClient:
    base_url: str
    api_key: str
    model: str

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
                return float(content)
        except Exception:
            return 1.0
