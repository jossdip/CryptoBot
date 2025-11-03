# 🎯 Résumé Rapide : Comment le Bot Fonctionne

## 🔄 Cycle Principal (Toutes les 30 secondes)

```
┌─────────────────────────────────────────────────────────┐
│  1. Collecte Données Marché (Hyperliquid)                │
│     - Prix, volumes, funding rates                        │
│     - Sentiment Reddit/Twitter                            │
│     - Portfolio actuel                                    │
└──────────────────────┬──────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  2. Détection d'Opportunités (6 Stratégies)             │
│     • Arbitrage → écarts de prix entre exchanges         │
│     • Sniping → nouveaux listings                        │
│     • Market Making → spreads bid/ask                    │
│     • Momentum → mouvements de prix                       │
│     • Sentiment Reddit → analyse LLM des posts          │
│     • Sentiment Twitter → analyse LLM des tweets         │
└──────────────────────┬──────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  3. DeepSeek LLM → Décision 1 : Allocation Stratégies   │
│     "Comment répartir le capital entre les 6 stratégies?" │
│     → Poids dynamiques (ex: arbitrage=30%, sniping=5%)   │
└──────────────────────┬──────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  4. Pour chaque opportunité détectée :                  │
│                                                          │
│     DeepSeek LLM → Décision 2 : Trade ?                 │
│     "Dois-je exécuter ce trade ?"                        │
│     → execute: true/false                                │
│     → size_usd: XXXX.XX                                  │
│     → leverage: X                                        │
│     → stop_loss, take_profit                             │
│     → confidence: 0.0-1.0 (doit être > 0.7 pour exécuter)│
└──────────────────────┬──────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  5. Exécution Multi-Stratégies                           │
│     - Alloue capital selon poids LLM                      │
│     - Place ordres sur Hyperliquid                       │
│     - Stop-loss / Take-profit automatiques               │
└──────────────────────┬──────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  6. Suivi Performance                                    │
│     - Track PnL par stratégie                           │
│     - Calcul métriques (win rate, Sharpe, drawdown)      │
│     - Envoie au LLM pour apprentissage                   │
└──────────────────────┬──────────────────────────────────┘
                        ↓
                    (Boucle)
```

## 🧠 Le LLM (DeepSeek) est le Cerveau

Le bot est **100% LLM-driven** :

1. **Décision Globale** : Comment allouer le capital entre les 6 stratégies ?
   - Analyse conditions de marché
   - Analyse performances récentes
   - Analyse sentiment social
   - → Produit des poids dynamiques

2. **Décision Locale** : Pour chaque opportunité détectée, faut-il trader ?
   - Analyse l'opportunité spécifique
   - Analyse le contexte marché
   - Analyse le portfolio actuel
   - Analyse le risque
   - → Produit une décision de trade (exécuter ? taille ? levier ?)

3. **Apprentissage Continu** : Le LLM reçoit les performances passées
   - Identifie les stratégies rentables → augmente leurs poids
   - Identifie les stratégies perdantes → réduit leurs poids
   - S'adapte automatiquement aux conditions de marché

## ⚙️ Installation Rapide

```bash
# 1. Installer dépendances
pip install -e .

# 2. Configurer .env
cp docs/ENV_HYPERLIQUID_EXAMPLE.txt .env
nano .env  # Remplir les clés

# 3. Configurer configs/live.hyperliquid.yaml
nano configs/live.hyperliquid.yaml  # Ajuster si besoin

# 4. Lancer (testnet)
python -m cryptobot.cli.live_hyperliquid --config configs/live.hyperliquid.yaml
```

## 🎛️ Paramètres Clés à Ajuster

| Paramètre | Où ? | Impact |
|-----------|------|--------|
| **Capital** | `configs/live.hyperliquid.yaml` → `general.capital` | Montant de départ |
| **Levier** | `hyperliquid.default_leverage` | Risque/retour |
| **Fréquence** | `llm.decision_interval_sec` | Vitesse de décision |
| **Poids Stratégies** | `strategy_weights.initial_weights` | Allocation initiale |
| **Limite Risque** | `risk.max_daily_drawdown_pct` | Protection drawdown |

## 🚨 Points d'Attention

- ✅ **Tester d'abord sur testnet** (testnet: true)
- ✅ **Commencer avec petit capital** (100-500 USD)
- ✅ **Surveiller les logs** (`tail -f logs/cryptobot.log`)
- ⚠️ **NE JAMAIS committer `.env`**
- ⚠️ **Le bot utilise de l'argent réel en mode live**

## 📊 Exemple de Décision LLM

**Décision 1 - Allocation :**
```json
{
  "arbitrage": 0.30,      // 30% du capital
  "sniping": 0.05,        // 5% du capital
  "market_making": 0.35,  // 35% du capital
  "momentum": 0.15,       // 15% du capital
  "sentiment_reddit": 0.10, // 10% du capital
  "sentiment_twitter": 0.05, // 5% du capital
  "reasoning": "Arbitrage opportunities high, market making stable, reducing risky sniping"
}
```

**Décision 2 - Trade :**
```json
{
  "execute": true,
  "direction": "long",
  "size_usd": 500.0,
  "leverage": 5,
  "stop_loss_pct": 2.0,
  "take_profit_pct": 3.0,
  "confidence": 0.85,
  "reasoning": "Strong momentum signal with low volatility, conservative leverage"
}
```

## 🎓 En Résumé

1. **Le bot scanne le marché** avec 6 stratégies en parallèle
2. **DeepSeek décide** comment allouer le capital et quels trades faire
3. **Le bot exécute** les ordres approuvés sur Hyperliquid
4. **Le bot apprend** de ses performances et s'adapte

**C'est tout ! Le LLM fait tout le travail de décision. 🧠✨**

