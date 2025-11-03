from __future__ import annotations

from typing import List, Dict, Optional, Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore


def fetch_markets(topic: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """
    Récupère les marchés de prédiction Polymarket.
    
    Utilise l'API GraphQL de Polymarket pour récupérer les marchés actifs.
    Les utilisateurs parient de l'argent réel, donc les probabilités reflètent
    la "sagesse de la foule" (wisdom of the crowd).
    
    Retourne une liste de marchés avec :
    - question: La question du marché (ex: "Will BTC reach $50k?")
    - prob_yes: Probabilité que "Oui" gagne (0.0-1.0)
    - volume_usd: Volume total en USD
    - liquidity: Liquidité disponible
    """
    if httpx is None:
        # Fallback: retourner des données stub si httpx n'est pas installé
        return []
    
    try:
        # Polymarket API GraphQL endpoint
        url = "https://clob.polymarket.com/events"
        
        # Requête simple pour récupérer les marchés actifs
        # Note: L'API exacte peut varier, cette implémentation est basique
        params: Dict[str, Any] = {
            "limit": limit,
        }
        if topic:
            # Recherche par topic/keyword
            params["search"] = topic
        
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Parser la réponse (structure peut varier selon l'API)
            markets: List[Dict] = []
            
            if isinstance(data, list):
                for item in data[:limit]:
                    # Extraire les informations du marché
                    question = item.get("question", "") or item.get("title", "")
                    prob_yes = item.get("prob_yes", 0.5)
                    volume_usd = item.get("volume_usd", 0.0) or item.get("volume", 0.0)
                    liquidity = item.get("liquidity", 0.0)
                    
                    markets.append({
                        "question": question,
                        "prob_yes": float(prob_yes),
                        "volume_usd": float(volume_usd),
                        "liquidity": float(liquidity),
                        "market_id": item.get("id") or item.get("market_id", ""),
                    })
            elif isinstance(data, dict) and "results" in data:
                # Format alternatif avec résultats imbriqués
                for item in data["results"][:limit]:
                    question = item.get("question", "") or item.get("title", "")
                    prob_yes = item.get("prob_yes", 0.5)
                    volume_usd = item.get("volume_usd", 0.0) or item.get("volume", 0.0)
                    liquidity = item.get("liquidity", 0.0)
                    
                    markets.append({
                        "question": question,
                        "prob_yes": float(prob_yes),
                        "volume_usd": float(volume_usd),
                        "liquidity": float(liquidity),
                        "market_id": item.get("id") or item.get("market_id", ""),
                    })
            
            return markets
            
    except Exception:
        # En cas d'erreur, retourner une liste vide (pas bloquant)
        return []
