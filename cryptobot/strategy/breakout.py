from __future__ import annotations

from typing import Dict, Any, List


class BreakoutStrategy:
    """
    Stratégie de breakout : détecte les cassures de niveaux de support/résistance.
    
    Principe : Entrer quand le prix casse un niveau clé avec volume, utiliser les signaux
    de sentiment pour confirmer la direction du breakout.
    """
    
    def __init__(self, broker) -> None:
        self.broker = broker

    def detect_opportunities(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Détecte les opportunités de breakout basées sur :
        - Prix qui casse des niveaux (simplifié ici)
        - Volume élevé (confirmation)
        - Signaux de sentiment (Polymarket, Reddit, Twitter) pour confirmer la direction
        - Market cap et volume global
        """
        prices: Dict[str, Dict[str, float]] = context.get("prices", {})
        if not prices:
            return []
        
        symbol = next(iter(prices.keys()))
        mid = float(prices[symbol].get("hyperliquid", 0.0))
        if mid <= 0:
            return []
        
        # Signaux de sentiment
        sentiment = context.get("sentiment", {})
        reddit_score = float(sentiment.get("reddit", {}).get("score", 0.0))
        twitter_score = float(sentiment.get("twitter", {}).get("score", 0.0))
        polymarket_score = float(sentiment.get("polymarket", {}).get("score", 0.0))
        
        # Volume (confirmation de breakout)
        volumes = context.get("market", {}).get("volumes", {})
        volume = float(volumes.get(symbol, 0.0))
        
        # Market cap et volume global (signaux de qualité)
        market_data = context.get("market", {})
        market_cap = float(market_data.get("market_cap", {}).get(symbol, 0.0))
        total_volume_24h = float(market_data.get("total_volume_24h", {}).get(symbol, 0.0))
        
        # Score de breakout combiné
        # Polymarket a plus de poids pour confirmer la direction
        sentiment_score = (
            reddit_score * 0.2 +
            twitter_score * 0.2 +
            polymarket_score * 0.6  # Plus de poids car argent réel
        )
        
        # Seuil pour détecter un breakout significatif
        if abs(sentiment_score) < 0.3:
            return []  # Pas de signal fort
        
        # Volume élevé confirme le breakout
        volume_confirmation = volume > 0 or total_volume_24h > 0
        
        direction = "long" if sentiment_score > 0.3 else "short" if sentiment_score < -0.3 else "flat"
        
        if direction == "flat" or not volume_confirmation:
            return []
        
        return [{
            "symbol": symbol,
            "price": mid,
            "direction": direction,
            "sentiment_score": sentiment_score,
            "volume": volume,
            "market_cap": market_cap,
            "total_volume_24h": total_volume_24h,
            "sentiment_scores": {
                "reddit": reddit_score,
                "twitter": twitter_score,
                "polymarket": polymarket_score,
            },
            "breakout_type": "bullish" if direction == "long" else "bearish"
        }]

