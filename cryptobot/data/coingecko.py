from __future__ import annotations

from typing import Dict, Optional

import httpx


_DEFAULT_MAP = {
    "BTC/USDT": "bitcoin",
    "ETH/USDT": "ethereum",
}


def _infer_id(symbol: str) -> Optional[str]:
    # Minimal mapping; extend as needed
    return _DEFAULT_MAP.get(symbol.upper())


def fetch_market_metadata(symbol: str) -> Dict:
    """Fetch basic coin metadata from CoinGecko free API. Best-effort and cost-efficient.
    Returns keys: market_cap, total_volume, market_cap_rank, name, symbol.
    """
    coin_id = _infer_id(symbol)
    if not coin_id:
        return {}
    try:
        url = f"https://api.coingecko.com/api/v3/coins/markets"
        params = {"vs_currency": "usd", "ids": coin_id}
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            if not data:
                return {}
            d = data[0]
            return {
                "name": d.get("name"),
                "symbol": d.get("symbol"),
                "market_cap": d.get("market_cap"),
                "total_volume": d.get("total_volume"),
                "market_cap_rank": d.get("market_cap_rank"),
            }
    except Exception:
        return {}


