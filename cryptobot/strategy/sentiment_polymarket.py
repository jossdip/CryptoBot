from __future__ import annotations

from typing import Dict, Any, List

from cryptobot.llm.client import LLMClient
from cryptobot.web.polymarket import fetch_markets


class SentimentPolymarketStrategy:
    """
    Stratégie basée sur les paris réels sur Polymarket.
    
    Principe : Les utilisateurs mettent de l'argent réel sur Polymarket, donc il y a
    plus de chances qu'ils disent la vérité et qu'ils aient fait des recherches.
    On utilise les probabilités des marchés Polymarket (ex: "Bitcoin va monter > 50k")
    comme signal de sentiment.
    """
    
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def analyze_sentiment(self, markets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyse le sentiment basé sur les probabilités Polymarket.
        
        Pour chaque marché Polymarket lié au crypto, on extrait :
        - La probabilité actuelle (ex: 70% que BTC monte > 50k)
        - Le volume de paris (plus de volume = plus de confiance)
        - La tendance récente (les probabilités montent/descendent)
        
        On envoie tout au LLM pour qu'il interprète le sentiment global.
        """
        if not markets:
            return {"score": 0.0, "confidence": 0.0}
        
        # Construire le contexte pour le LLM
        market_summary = []
        for market in markets[:20]:  # Limiter à 20 marchés
            question = market.get("question", "")
            prob_yes = market.get("prob_yes", 0.5)  # Probabilité que "Oui" gagne
            volume = market.get("volume_usd", 0.0)
            liquidity = market.get("liquidity", 0.0)
            
            market_summary.append({
                "question": question[:200],  # Tronquer
                "prob_yes": prob_yes,
                "volume_usd": volume,
                "liquidity": liquidity,
            })
        
        prompt = (
            f"Analyze crypto sentiment from these Polymarket prediction markets where people bet real money:\n"
            f"{market_summary}\n\n"
            f"Interpretation rules:\n"
            f"- If prob_yes > 0.7 for bullish predictions (BTC/ETH going up) → bullish sentiment\n"
            f"- If prob_yes < 0.3 for bullish predictions → bearish sentiment\n"
            f"- Higher volume_usd and liquidity → more reliable signal (people put real money)\n"
            f"- If multiple markets agree (all bullish or all bearish) → stronger signal\n\n"
            f"Output JSON: {{\"score\": -1.0 to 1.0 (bullish=positive, bearish=negative), \"confidence\": 0.0-1.0}}"
        )
        
        result = self.llm.call(prompt=prompt, json_mode=True) or {"score": 0.0, "confidence": 0.0}
        return result

    def detect_opportunities(self, keywords: List[str]) -> Dict[str, Any]:
        """
        Détecte les opportunités basées sur les marchés Polymarket.
        
        On cherche les marchés Polymarket qui mentionnent les keywords (BTC, ETH, crypto, etc.)
        et on analyse leur sentiment.
        """
        texts: List[str] = []
        markets_found: List[Dict[str, Any]] = []
        
        for kw in keywords:
            # Chercher les marchés Polymarket liés à ce keyword
            markets = fetch_markets(topic=kw, limit=50)
            
            for market in markets:
                question = str(market.get("question", ""))
                # Filtrer les marchés pertinents (qui mentionnent crypto/BTC/ETH/etc.)
                if any(k.lower() in question.lower() for k in keywords):
                    markets_found.append(market)
                    texts.append(question[:300])
        
        # Analyser le sentiment basé sur les marchés trouvés
        sentiment = self.analyze_sentiment(markets_found[:50]) if markets_found else {"score": 0.0, "confidence": 0.0}
        
        # Ajouter des métadonnées pour le LLM orchestrator
        sentiment["source"] = "polymarket"
        sentiment["markets_count"] = len(markets_found)
        sentiment["total_volume"] = sum(float(m.get("volume_usd", 0.0)) for m in markets_found)
        
        return sentiment

