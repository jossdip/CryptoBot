from __future__ import annotations

from typing import Dict, Any, Optional, List
from dataclasses import dataclass

@dataclass
class StrategyParams:
    # Default params, can be updated by FastEngine
    min_obi: float = 0.3
    depth_levels: int = 5

class ScalpingStrategy:
    """
    HFT Microstructure Strategy (Order Book Imbalance).
    Replaces old sentiment-based scalping for sub-millisecond reaction.
    """
    def __init__(self):
        self.params = StrategyParams()

    def update_market_data(self, coin: str, mid: float, ts: float):
        # Legacy/Info update - not used in HFT path
        pass

    def process_tick(self, symbol: str, book_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process L2 Book update immediately.
        Returns signal dict if opportunity found, else None.
        """
        levels = book_data.get("levels")
        if not levels or len(levels) < 2:
            return None
            
        bids = levels[0]
        asks = levels[1]
        
        if not bids or not asks:
            return None
            
        # Calculate Order Book Imbalance (OBI)
        # OBI = (BidVol - AskVol) / (BidVol + AskVol)
        # Use top N levels to gauge immediate pressure
        
        depth = getattr(self.params, 'depth_levels', 5)
        
        bid_vol = 0.0
        ask_vol = 0.0
        
        # Hyperliquid L2 levels are dicts: {'px': '...', 'sz': '...', 'n': ...}
        for i in range(min(len(bids), depth)):
            bid_vol += float(bids[i]['sz'])
            
        for i in range(min(len(asks), depth)):
            ask_vol += float(asks[i]['sz'])
            
        if (bid_vol + ask_vol) == 0:
            return None
            
        obi = (bid_vol - ask_vol) / (bid_vol + ask_vol)
        
        # Mid price for limit placement
        best_bid = float(bids[0]['px'])
        best_ask = float(asks[0]['px'])
        mid_price = (best_bid + best_ask) / 2.0
        
        # Threshold from params (FastEngine updates this)
        threshold = getattr(self.params, 'min_obi', 0.3)
        
        direction = "flat"
        if obi > threshold:
            direction = "long"
            # Place limit at best bid to be maker, or cross if urgent?
            # For HFT scalping, usually want to join the bid.
            price = best_bid 
        elif obi < -threshold:
            direction = "short"
            price = best_ask
            
        if direction != "flat":
            return {
                "symbol": symbol,
                "direction": direction,
                "price": price,
                "is_maker": True,
                "obi": obi,
                "timestamp": book_data.get("time")
            }
            
        return None
