from __future__ import annotations

from typing import Dict, Any, List


class ScalpingStrategy:
    """
    Stratégie de scalping : trades fréquents avec profits faibles mais réguliers.
    
    Principe : Entrer et sortir rapidement (minutes) pour capturer de petits mouvements.
    Utilise les signaux (sentiment, volume, funding rates) pour évaluer la confiance.
    """
    
    def __init__(self, broker) -> None:
        self.broker = broker

    def detect_opportunities(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Détecte les opportunités de scalping basées sur :
        - Volatilité à court terme
        - Volume élevé
        - Signaux de sentiment (Reddit, Twitter, Polymarket)
        - Funding rates
        """
        prices: Dict[str, Dict[str, float]] = context.get("prices", {})
        if not prices:
            return []
        
        symbol = next(iter(prices.keys()))
        mid = float(prices[symbol].get("hyperliquid", 0.0))
        if mid <= 0:
            return []
        
        # Signaux de sentiment (Reddit, Twitter, Polymarket)
        sentiment = context.get("sentiment", {})
        reddit_score = float(sentiment.get("reddit", {}).get("score", 0.0))
        twitter_score = float(sentiment.get("twitter", {}).get("score", 0.0))
        polymarket_score = float(sentiment.get("polymarket", {}).get("score", 0.0))
        
        # Volume (signal de liquidité)
        volumes = context.get("market", {}).get("volumes", {})
        volume = float(volumes.get(symbol, 0.0))
        
        # Funding rate (signal de sentiment des traders)
        funding_rates = context.get("market", {}).get("funding_rates", {})
        funding_rate = float(funding_rates.get(symbol, 0.0))
        
        # Score de scalping combiné
        # Polymarket a plus de poids (argent réel)
        signal_strength = (
            reddit_score * 0.2 +
            twitter_score * 0.2 +
            polymarket_score * 0.4 +  # Plus de poids car argent réel
            (1.0 if volume > 0 else 0.0) * 0.1 +
            (1.0 if abs(funding_rate) > 0.0001 else 0.0) * 0.1
        )
        
        direction = "long" if signal_strength > 0.1 else "short" if signal_strength < -0.1 else "flat"
        
        if direction == "flat":
            return []
        
        return [{
            "symbol": symbol,
            "price": mid,
            "direction": direction,
            "signal_strength": signal_strength,
            "volume": volume,
            "funding_rate": funding_rate,
            "sentiment_scores": {
                "reddit": reddit_score,
                "twitter": twitter_score,
                "polymarket": polymarket_score,
            }
        }]

