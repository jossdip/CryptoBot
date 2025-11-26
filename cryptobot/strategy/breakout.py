from __future__ import annotations

from typing import Dict, Any, List
from cryptobot.strategy.base import BaseStrategy


class BreakoutStrategy(BaseStrategy):
    """
    Stratégie de breakout : détecte les cassures de niveaux de support/résistance.
    
    Principe : Entrer quand le prix casse un niveau clé avec volume, utiliser les signaux
    de sentiment pour confirmer la direction du breakout.
    """
    
    def detect_opportunities(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Détecte les opportunités de breakout.
        """
        data = self.parse_context(context)
        symbol = data["symbol"]
        mid = data["mid_price"]
        
        if not symbol or mid <= 0:
            return []
        
        # Signaux de sentiment
        sent = data["sentiment"]
        reddit_score = sent["reddit"]
        twitter_score = sent["twitter"]
        polymarket_score = sent["polymarket"]
        
        # Volume (confirmation de breakout)
        volume = data["market"]["volume"]
        
        # Market cap et volume global (signaux de qualité) - conservé du code original mais non standardisé dans BaseStrategy pour l'instant
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
