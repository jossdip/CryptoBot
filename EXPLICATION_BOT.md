# Explication Complète du Bot CryptoBot - Version Futures

## Vue d'Ensemble

Le bot a été transformé pour faire du **trading futures avec leviers** en utilisant :
- Des données **réelles** du marché (via CCXT)
- Une stratégie **DeepSeek AI** qui choisit direction (long/short) et levier
- Un **paper trading** pur (simulation complète, pas d'argent réel)
- Un capital de départ de **1000 USDT** de simulation

---

## Architecture Globale : Comment le Bot Fonctionne

### 1. **Collecte des Données en Temps Réel** (`cryptobot/data/ccxt_live.py`)

**Processus :**
- Se connecte à l'exchange **Bybit** (choisi pour la France, excellent pour futures)
- Utilise le **testnet** de Bybit pour récupérer les données sans risque
- Récupère les barres OHLCV (Open, High, Low, Close, Volume) chaque minute
- Envoie ces barres au reste du système en streaming

**Fonctionnalités ajoutées :**
- Support du mode `futures` (au lieu de `spot`)
- Mode testnet activable pour récupérer des données de démo
- Fonction `fetch_mark_price()` pour obtenir le prix de marque (important pour futures)

**Pourquoi Bybit ?**
- Accepte les traders français sans restriction
- Excellent support futures avec leviers jusqu'à 100x
- Liquidité élevée
- Testnet gratuit disponible
- API bien documentée et supportée par CCXT

---

### 2. **Collecte de Métadonnées** (`cryptobot/data/coingecko.py`)

**Processus :**
- Récupère des informations supplémentaires sur la crypto via CoinGecko (API gratuite)
- Données : nom, market cap, volume total, rang par capitalisation
- Ces infos sont envoyées à l'IA DeepSeek pour enrichir son contexte de décision

**Coût :** Gratuit (CoinGecko free tier)

---

### 3. **Broker Paper Futures** (`cryptobot/broker/futures_paper.py`)

C'est le **cœur du système de trading simulé**. Il simule un compte de trading futures.

**Fonctionnalités principales :**

#### A. **Gestion du Portefeuille (`FuturesPortfolio`)**
- `cash` : Solde disponible en USDT (capital de départ : 1000 USDT)
- `positions` : Positions ouvertes (long ou short, quantité positive/négative)
- `isolated_margin` : Marge isolée par symbole (chaque position a sa propre marge)
- `leverage_map` : Levier par symbole choisi par l'IA

#### B. **Calcul de l'Equity**
```
Equity = Cash + Profit/Perte Non Réalisé
P&L Non Réalisé = (Prix Actuel - Prix d'Entrée) × Quantité
```
- Si position LONG : P&L positif si prix monte
- Si position SHORT : P&L positif si prix baisse

#### C. **Exécution d'Ordres (`market_order`)**
Quand l'IA décide d'ouvrir/fermer une position :

1. **Application du slippage** : Prix d'exécution ajusté (simulation de l'impact sur le marché)
2. **Calcul de la marge requise** :
   ```
   Marge Requise = (Notional de Position) / Levier
   ```
   - Exemple : Position de 5000 USDT avec levier 5x = 1000 USDT de marge
3. **Vérification de solvabilité** : On vérifie si on a assez de cash pour la marge + frais
4. **Déduction des frais** : Frais de trading (~0.02% sur futures)
5. **Mise à jour de la position** :
   - LONG : Quantité positive, P&L positif si prix monte
   - SHORT : Quantité négative, P&L positif si prix baisse
   - Calcul du prix moyen pondéré si on augmente une position existante

**Mode Marge Isolée :**
- Chaque position est isolée : si une position perd tout, elle ne peut pas faire faillite sur une autre
- Plus sûr pour commencer

---

### 4. **Stratégie IA DeepSeek** (`cryptobot/llm/client.py` + `cryptobot/strategy/llm_strategy.py`)

**Processus de Décision :**

#### Étape 1 : Collecte du Contexte
- 60 dernières barres OHLCV (données de marché)
- Métadonnées de la crypto (market cap, volume, etc.)
- Position actuelle (si on a une position ouverte)

#### Étape 2 : Appel à DeepSeek
L'IA reçoit un prompt spécialisé :
```
"Tu es un expert en trading futures crypto. 
Décide si on doit être LONG, SHORT, ou FLAT (pas de position).
Recommandez un levier entre 1 et 20.
Règles : 
- Utilisateur a seulement ~1000 USDT (sois cost-efficient)
- Éviter l'overtrading
- Utiliser un levier plus élevé seulement si volatilité faible et tendance forte"
```

#### Étape 3 : Réponse Formatée JSON
```json
{
  "direction": "long" | "short" | "flat",
  "leverage": 5,  // entre 1 et 20
  "confidence": 0.75  // entre 0 et 1
}
```

#### Étape 4 : Cooldown Intelligent
- Ne rappelle pas DeepSeek trop souvent (minimum 60 secondes)
- Réutilise la dernière décision si le marché n'a pas assez bougé (filtre ATR)

**Optimisations coût :**
- Limite les appels à l'API DeepSeek
- Downsampling des données (60 barres au lieu de 180)
- Prompt court et efficace (~64 tokens max)

---

### 5. **Gestion des Risques** (`cryptobot/broker/risk.py`)

**Limites de Protection :**

#### A. **Taille Maximale de Position**
```
Max Notional = Equity × max_position_pct × Levier
```
- `max_position_pct` : 20% par défaut
- Exemple : Equity 1000 USDT, levier 5x → Max 1000 USDT de position (20% × 5)

#### B. **Calcul de la Quantité Autorisée**
```
Quantité Autorisée = (Max Notional - Notional Actuel) / Prix
```
- Empêche de sur-allouer
- Prend en compte le levier pour permettre des positions plus grandes avec marge limitée

**Exemple concret :**
- Equity : 1000 USDT
- Prix BTC : 50000 USDT
- Levier choisi : 5x
- Max position : 20% × 5 = 100% de l'equity = 1000 USDT
- Quantité max : 1000 / 50000 = 0.02 BTC

---

### 6. **Boucle de Trading Live** (`cryptobot/cli/live.py`)

**Flux d'Exécution :**

```
1. Initialisation
   ├─ Charge la config (market_type=futures, exchange=bybit, capital=1000)
   ├─ Crée le broker futures paper
   ├─ Initialise DeepSeek client
   └─ Se connecte à Bybit testnet

2. Collecte des Barres (chaque minute)
   └─ live_ohlcv() → Bar

3. Accumulation de l'Historique
   └─ On garde les 50+ dernières barres pour calculer les indicateurs

4. Quand assez de données (50 barres) :
   ├─ Calcul des indicateurs techniques (EMA, RSI, ATR)
   ├─ Appel à l'IA DeepSeek avec contexte
   │  └─ Réponse : {direction, leverage, confidence}
   ├─ Calcul du sizing avec risk manager
   ├─ Si direction = LONG et sizing OK :
   │  └─ OUVRIR position LONG avec le levier choisi
   ├─ Si direction = SHORT et sizing OK :
   │  └─ OUVRIR position SHORT avec le levier choisi
   ├─ Si direction = FLAT et position ouverte :
   │  └─ FERMER la position complète
   └─ Mise à jour de l'equity survivee du monitoring

5. Répétition infinie (toutes les minutes)
```

**Logs importants :**
```
OPEN/LONG +0.02 BTC @ 50000.00 lev=5
OPEN/SHORT -0.015 BTC @ 50200.00 lev=8
CLOSE 0.02 BTC @ 51000.00
```

---

### 7. **Réplicateur Testnet (Optionnel)** (`cryptobot/broker/testnet_replicator.py`)

**Rôle :** Copie les ordres paper sur le testnet de l'exchange pour validation

**Actuellement :** DÉSACTIVÉ (`place_on_testnet: false`)

**Pourquoi ?**
- On reste en paper trading pur pour l'instant
- Permet de garder cette fonctionnalité pour plus tard si besoin

**Comment ça marcherait si activé :**
- Chaque ordre paper est également envoyé au testnet Bybit
- Permet de voir si les ordres passeraient vraiment
- Aucun risque car testnet (fonds virtuels)

---

## Configuration Clé (`configs/live.frugal.yaml`)

```yaml
general:
  capital: 1000.0           # Capital de départ en USDT
  market_type: futures      # Mode futures (pas spot)
  exchange_id: bybit        # Exchange choisi (Bybit pour la France)

broker:
  fee_bps: 2                # Frais 0.02% (réaliste pour futures)
  margin_mode: isolated     # Marge isolée (sécurisé)
  default_leverage: 5       # Levier par défaut si IA ne choisit pas
  max_leverage: 20          # Levier maximum autorisé
  place_on_testnet: false   # IMPORTANT : paper trading pur (pas d'ordres réels)

risk:
  max_position_pct: 0.2     # Max 20% de l'equity par position (× levier)
```

---

## Sécurité et Paper Trading

**Garanties que tout est en simulation :**

1. **Broker Paper** : `FuturesPaperBroker` simule tout localement
2. **Pas d'API Keys nécessaire** pour le paper trading (sauf si testnet activé)
3. **Testnet uniquement** : Même les données viennent du testnet Bybit
4. **`place_on_testnet: false`** : Aucun ordre n'est envoyé à l'exchange

**Pour activer le testnet plus tard :**
- Ajouter des clés API Bybit testnet dans `.env`
- Mettre `place_on_testnet: true`
- Les ordres seront copiés sur testnet (toujours sans risque)

---

## Coûts et Optimisations

### Coûts DeepSeek API :
- **20 USD de crédit** (comme mentionné)
- Appels foam avec cooldown de 60s minimum
- Prompts courts (~64 tokens max)
- Downsampling des données

**Estimation :**
- ~60 appels/heure max (1/minute)
- Coût par appel : ~0.001-0.002 USD
- Coût/heure : ~0.06-0.12 USD
- 20 USD = ~167-333 heures de trading

### Optimisations appliquées :
- Cooldown intelligent
- Filtre ATR (pas d'appel si marché trop calme)
- Downsampling des données
- Prompts concis

---

## Résultats Attendus

Le bot va :
1. Analyser le marché BTC/USDT en temps réel
2. Décider toutes les minutes (ou moins souvent avec cooldown)
3. Ouvrir des positions LONG ou SHORT avec levier choisi par l'IA
4. Gérer le risque automatiquement
5. Logger tous les trades pour analyse

**Comparaison avec nof1.ai :**
- Même approche : IA qui décide direction + levier
- Paper trading pour tester avant de risquer de l'argent réel
- Focus sur cost-efficiency (petit capital, optimisations)

---

## Commandes pour Démarrer

```bash
# 1. Configurer les variables d'environnement (.env)
export LLM_API_KEY=sk-...              # Votre clé DeepSeek
export LLM_BASE_URL=https://api.deepseek.com/v1
export LLM_MODEL=deepseek-chat

# Les clés exchange ne sont PAS nécessaires pour paper trading pur

# 2. Lancer le bot
python -m cryptobot.cli.live --config configs/live.frugal.yaml --provider ccxt

# 3. Monitorer (optionnel)
# Ouvrir http://localhost:8000 dans un navigateur
python -m cryptobot.cli.live --config configs/live.frugal.yaml --provider ccxt --with-dashboard
```

---

## Flux de Données Complet

```
Bybit Testnet (API)
    ↓
[CCXT Live Data] → Barres OHLCV toutes les minutes
    ↓
[Historique Accumulé] → 50+ barres pour indicateurs
    ↓
[Stratégie LLM] → Analyse + Appel DeepSeek
    ↓
[Décision] → {direction: long|short|flat, leverage: 5-20}
    ↓
[Risk Manager] → Calcule sizing autorisé
    ↓
[Futures Paper Broker] → Simule l'exécution
    ↓
[Portfolio Updated] → Mise à jour equity, positions, P&L
    ↓
[Monitoring] → Logs + Dashboard (si activé)
    ↓
[Répétition] → Retour au début toutes les minutes
```

---

## Points Techniques Importants

1. **Marge Isolée** : Chaque position est isolée, plus sûr
2. **Gestion du Sell/Buy** : 
   - `buy` en futures = ouvrir LONG ou fermer SHORT
   - `sell` en futures = ouvrir SHORT ou fermer LONG
3. **Calcul de l'Equity** : Prend en compte les P&L non réalisés
4. **Frais Réalistes** : 0.02% taker fee + slippage 0.05%
5. **Protection** : Max 20% de l'equity par position (avant levier)

---

## Conclusion

Le bot est maintenant un système complet de **paper trading futures avec IA** :
- ✅ Données réelles du marché
- ✅ IA DeepSeek qui choisit direction et levier
- ✅ Simulation complète avec marge, frais, slippage
- ✅ Gestion des risques intégrée
- ✅ 100% paper trading (aucun risque financier)
- ✅ Optimisé pour cost-efficiency (20 USD de crédit DeepSeek)

Prêt à tester et voir comment l'IA trade avec un capital de 1000 USDT simulé !

