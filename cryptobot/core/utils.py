from __future__ import annotations

def normalize_to_hyperliquid_coin(symbol: str) -> str:
    """
    Map common external symbol formats to Hyperliquid coin tickers.
    Examples:
    - 'BTC/USD:USD' -> 'BTC'
    - 'ETH/USDT'    -> 'ETH'
    - 'SOL'         -> 'SOL' (unchanged)
    """
    s = str(symbol or "").strip().upper()
    if not s:
        return s
    # Split by '/' first, take the base asset part
    if "/" in s:
        base = s.split("/", 1)[0]
    else:
        base = s
    # Remove any suffix like ':USD'
    base = base.replace(":USD", "")
    # Final cleanup: keep only alphanumerics (HL tickers are uppercase coin names)
    return "".join(ch for ch in base if ch.isalnum())

