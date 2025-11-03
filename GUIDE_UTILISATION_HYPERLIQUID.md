# 📖 Guide d'Utilisation : CryptoBot Hyperliquid LLM-Driven

## 🎯 Vue d'Ensemble

Ce bot de trading automatisé utilise **DeepSeek (LLM)** pour piloter entièrement les décisions de trading sur **Hyperliquid** (futures perpétuels). Le bot combine 6 stratégies différentes avec une **pondération dynamique** qui s'adapte automatiquement aux conditions de marché.

---

## 🏗️ Architecture : Comment le Bot Fonctionne

### **Flux de Données Principal**

```
1. Données Marché (Hyperliquid)
   ↓
2. Agrégateur de Contexte (collecte prix, volumes, funding rates, sentiment)
   ↓
3. Détection d'Opportunités (6 stratégies scannent en parallèle)
   ↓
4. DeepSeek LLM (décide : quelle stratégie activer ? avec quels poids ?)
   ↓
5. DeepSeek LLM (décide pour chaque trade : exécuter ? taille ? levier ?)
   ↓
6. Gestionnaire de Risque (valide et ajuste les tailles)
   ↓
7. Exécution Multi-Stratégies (place les ordres sur Hyperliquid)
   ↓
8. Suivi Performance (tracke PnL par stratégie)
   ↓
9. Feedback Loop → DeepSeek (apprend de ses performances)
   ↓
   (retour à l'étape 1 toutes les 30 secondes)
```

### **Composants Principaux**

#### **1. LLM Orchestrator** (`cryptobot/llm/orchestrator.py`)
- **Rôle** : Cerveau du bot piloté par DeepSeek
- **Fonctions** :
  - Décide comment répartir le capital entre les 6 stratégies (pondération dynamique)
  - Décide pour chaque opportunité détectée : exécuter ou pas ? taille ? levier ?
- **Fréquence** : Toutes les 30 secondes (configurable)

#### **2. Les 6 Stratégies**

| Stratégie | Description | Risque | Retour Attendu |
|-----------|-------------|--------|----------------|
| **Arbitrage** | Exploite les écarts de prix entre exchanges | Faible | Régulier |
| **Sniping** | Attrape les nouveaux listings tôt | Élevé | Élevé |
| **Market Making** | Fournit de la liquidité, gagne sur les spreads | Moyen | Stable |
| **Momentum** | Suit les mouvements de prix avec levier | Élevé | Élevé |
| **Sentiment Reddit** | Trade basé sur l'analyse Reddit (LLM) | Moyen | Volatile |
| **Sentiment Twitter** | Trade basé sur l'analyse Twitter (LLM) | Moyen | Volatile |

Chaque stratégie :
- Scanne le marché pour détecter des opportunités
- Envoie l'opportunité au LLM Orchestrator
- Exécute seulement si le LLM approuve (confidence > 0.7)

#### **3. Weight Manager** (`cryptobot/strategy/weight_manager.py`)
- **Rôle** : Ajuste automatiquement les poids des stratégies
- **Mécanisme** :
  - Track les performances de chaque stratégie
  - Augmente le poids des stratégies rentables
  - Réduit le poids des stratégies perdantes
  - Utilise un "smoothing" (70% nouveau / 30% ancien) pour éviter les changements brusques

#### **4. Multi-Strategy Executor** (`cryptobot/broker/executor.py`)
- **Rôle** : Exécute les trades en respectant l'allocation de capital
- **Fonctions** :
  - Alloue le capital selon les poids LLM
  - Place les ordres sur Hyperliquid
  - Gère les stop-loss et take-profit

#### **5. Performance Tracker** (`cryptobot/monitor/performance.py`)
- **Rôle** : Suit les performances et alimente le LLM
- **Métriques** :
  - PnL total par stratégie
  - Win rate
  - Sharpe ratio
  - Max drawdown
  - Ces métriques sont envoyées au LLM pour qu'il apprenne et s'adapte

---

## 🚀 Guide d'Installation et Configuration

### **Étape 1 : Installation des Dépendances**

```bash
# Installer Python 3.10+ si nécessaire
python3 --version

# Cloner/installer le projet
cd /opt/cryptobot  # ou votre répertoire

# Installer les dépendances
pip install -e .

# OU installer manuellement :
pip install pandas numpy pydantic pydantic-settings PyYAML httpx loguru rich ccxt python-dotenv websockets hyperliquid-python-sdk
```

### **Étape 2 : Configuration des Variables d'Environnement**

Créer un fichier `.env` dans le répertoire du projet :

```bash
# Copier l'exemple
cp docs/ENV_HYPERLIQUID_EXAMPLE.txt .env

# Éditer .env et remplir les valeurs
nano .env
```

**Variables requises :**

```bash
# Hyperliquid (OBLIGATOIRE)
HYPERLIQUID_WALLET_ADDRESS=0x...              # Votre adresse wallet
HYPERLIQUID_TESTNET_PRIVATE_KEY=0x...         # Clé privée pour testnet
HYPERLIQUID_LIVE_PRIVATE_KEY=0x...            # Clé privée pour live (NE PAS COMMITTER!)

# DeepSeek LLM (OBLIGATOIRE)
LLM_API_KEY=sk-...                            # Clé API DeepSeek
LLM_BASE_URL=https://api.deepseek.com/v1      # URL DeepSeek (par défaut)
LLM_MODEL=deepseek-chat                       # Modèle DeepSeek (par défaut)

# Optionnel : Autres exchanges pour arbitrage
BINANCE_API_KEY=...
BINANCE_API_SECRET=...

# Optionnel : Reddit pour sentiment
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=...

# Optionnel : Twitter pour sentiment
TWITTER_BEARER_TOKEN=...
```

**⚠️ SÉCURITÉ :**
- **NE JAMAIS** committer le fichier `.env`
- Garder les clés privées **SÉCURISÉES**
- Utiliser le testnet d'abord pour tester

### **Étape 3 : Configuration YAML**

Éditer `configs/live.hyperliquid.yaml` :

```yaml
general:
  capital: 10000.0                    # Capital de départ (USD)
  symbols: ["BTC/USD:USD", "ETH/USD:USD"]  # Symboles à trader
  timeframe: "1m"                    # Timeframe (1m, 5m, etc.)

hyperliquid:
  testnet: true                      # true = testnet, false = live
  default_leverage: 10               # Levier par défaut
  max_leverage: 50                   # Levier maximum

llm:
  decision_interval_sec: 30          # Fréquence des décisions LLM (secondes)
  context_window_bars: 60            # Nombre de barres envoyées au LLM

strategy_weights:
  initial_weights:
    arbitrage: 0.20                  # 20% du capital
    sniping: 0.15                    # 15% du capital
    market_making: 0.30               # 30% du capital
    momentum: 0.15                   # 15% du capital
    sentiment_reddit: 0.10           # 10% du capital
    sentiment_twitter: 0.10          # 10% du capital
    # Total doit faire 1.0

risk:
  max_position_pct: 1.0              # Max 100% du capital par position
  max_daily_drawdown_pct: 10         # Stop si drawdown > 10%
  max_leverage_per_strategy: 30      # Levier max par stratégie
```

---

## ▶️ Utilisation

### **Mode Testnet (Recommandé pour commencer)**

```bash
# 1. Configurer testnet: true dans configs/live.hyperliquid.yaml
# 2. Lancer le bot
python -m cryptobot.cli.live_hyperliquid --config configs/live.hyperliquid.yaml

# OU utiliser le script console
cryptobot-live-hl --config configs/live.hyperliquid.yaml
```

**Que se passe-t-il ?**
- Le bot se connecte au testnet Hyperliquid
- Collecte les données de marché
- DeepSeek décide toutes les 30 secondes
- Place des ordres virtuels (testnet)
- Track les performances

### **Mode Live (Production)**

```bash
# 1. Configurer testnet: false dans configs/live.hyperliquid.yaml
# 2. Vérifier que HYPERLIQUID_LIVE_PRIVATE_KEY est dans .env
# 3. Commencer avec un petit capital (100-500 USD)
# 4. Lancer le bot
python -m cryptobot.cli.live_hyperliquid --config configs/live.hyperliquid.yaml
```

**⚠️ ATTENTION :**
- Tester d'abord sur testnet
- Commencer avec un petit montant
- Surveiller les performances
- Le bot utilise de l'argent réel !

---

## 📊 Monitoring et Logs

### **Logs en Temps Réel**

Les logs sont écrits dans `logs/cryptobot.log` :

```bash
# Suivre les logs en temps réel
tail -f logs/cryptobot.log

# Filtrer les erreurs
tail -f logs/cryptobot.log | grep ERROR
```

### **Métriques de Performance**

Le `PerformanceTracker` génère des métriques :
- PnL total par stratégie
- Win rate
- Sharpe ratio
- Max drawdown

Ces métriques sont envoyées au LLM pour qu'il s'adapte.

### **Dashboard (Optionnel)**

Si vous avez configuré le dashboard :
```bash
python -m cryptobot.cli.live_hyperliquid --config configs/live.hyperliquid.yaml --with-dashboard
```

Accéder à : `http://localhost:8000`

---

## 🔧 Déploiement sur VPS Kali

### **1. Installation du Service Systemd**

```bash
# Copier le service
sudo cp deploy/cryptobot-hyperliquid.service /etc/systemd/system/

# Éditer le service pour adapter les chemins
sudo nano /etc/systemd/system/cryptobot-hyperliquid.service

# Recharger systemd
sudo systemctl daemon-reload

# Activer le service (démarrage automatique)
sudo systemctl enable cryptobot-hyperliquid

# Démarrer le service
sudo systemctl start cryptobot-hyperliquid

# Vérifier le statut
sudo systemctl status cryptobot-hyperliquid

# Voir les logs
sudo journalctl -u cryptobot-hyperliquid -f
```

### **2. Script de Monitoring**

```bash
# Rendre exécutable
chmod +x scripts/monitor.sh

# Lancer manuellement (ou via cron)
./scripts/monitor.sh

# OU ajouter au cron (vérifie toutes les 5 minutes)
*/5 * * * * /opt/cryptobot/scripts/monitor.sh
```

### **3. Rotation des Logs**

Configurer logrotate pour éviter que les logs prennent trop de place :

```bash
sudo nano /etc/logrotate.d/cryptobot
```

Contenu :
```
/opt/cryptobot/logs/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
```

---

## ⚙️ Personnalisation

### **Ajuster les Poids des Stratégies**

Éditer `configs/live.hyperliquid.yaml` :

```yaml
strategy_weights:
  initial_weights:
    arbitrage: 0.30      # Augmenter arbitrage
    sniping: 0.05        # Réduire sniping (trop risqué)
    market_making: 0.40  # Augmenter market making (stable)
    # etc.
```

**Note** : Le LLM ajuste automatiquement ces poids en fonction des performances, mais vous pouvez forcer des valeurs initiales.

### **Changer la Fréquence de Décision**

```yaml
llm:
  decision_interval_sec: 60  # Décisions toutes les 60 secondes au lieu de 30
```

### **Ajuster le Levier**

```yaml
hyperliquid:
  default_leverage: 5    # Réduire le levier (plus sûr)
  max_leverage: 20       # Limiter le levier max
```

### **Modifier les Limites de Risque**

```yaml
risk:
  max_position_pct: 0.5           # Max 50% du capital par position
  max_daily_drawdown_pct: 5       # Stop si drawdown > 5%
  max_leverage_per_strategy: 10   # Levier max réduit
```

---

## 🐛 Dépannage

### **Erreur : "Hyperliquid Python SDK is not installed"**

```bash
pip install hyperliquid-python-sdk
```

### **Erreur : "LLM API key not configured"**

Vérifier que `LLM_API_KEY` est dans `.env` :
```bash
grep LLM_API_KEY .env
```

### **Erreur : "Wallet address or private key missing"**

Vérifier que les variables Hyperliquid sont dans `.env` :
```bash
grep HYPERLIQUID .env
```

### **Le Bot ne Place Pas d'Ordres**

Vérifier :
1. Mode testnet/live correct dans la config
2. Clés API valides dans `.env`
3. Capital suffisant
4. Logs pour voir les décisions LLM (confidence peut être < 0.7)

### **Les Logs Sont Vides**

Vérifier les permissions :
```bash
chmod -R 755 logs/
```

---

## 📈 Optimisations Recommandées

### **1. Commencer Progressivement**

1. **Testnet** (1-2 semaines) : Valider que tout fonctionne
2. **Live avec petit capital** (100-500 USD) : Tester en réel
3. **Augmenter progressivement** : Si performances OK

### **2. Surveiller les Performances**

- Vérifier quotidiennement les logs
- Analyser les métriques par stratégie
- Identifier les stratégies les plus rentables

### **3. Ajuster Dynamiquement**

Le bot s'adapte automatiquement, mais vous pouvez :
- Modifier les poids initiaux si vous avez des préférences
- Ajuster les limites de risque selon votre tolérance
- Tester différentes fréquences de décision

### **4. Sécurité**

- **NE JAMAIS** committer `.env`
- Utiliser des clés API avec permissions limitées
- Activer 2FA sur Hyperliquid
- Backup régulier de la configuration

---

## 🔄 Cycle de Vie du Bot

1. **Démarrage** : Charge config → Connexion Hyperliquid → Initialisation LLM
2. **Boucle Principale** (toutes les 30 secondes) :
   - Collecte données marché
   - LLM décide allocation stratégies
   - Chaque stratégie détecte opportunités
   - LLM décide pour chaque opportunité (exécuter ? taille ? levier ?)
   - Exécution des trades approuvés
   - Mise à jour des performances
3. **Apprentissage Continu** : Le LLM ajuste les pondérations en fonction des résultats
4. **Arrêt** : Ctrl+C ou arrêt du service systemd

---

## 📝 Résumé des Commandes Essentielles

```bash
# Démarrer le bot (testnet)
python -m cryptobot.cli.live_hyperliquid --config configs/live.hyperliquid.yaml

# Voir les logs
tail -f logs/cryptobot.log

# Démarrer le service systemd
sudo systemctl start cryptobot-hyperliquid

# Voir le statut du service
sudo systemctl status cryptobot-hyperliquid

# Arrêter le bot
sudo systemctl stop cryptobot-hyperliquid
```

---

## 🎓 Conclusion

Ce bot est **100% piloté par DeepSeek LLM** qui :
- Décide comment allouer le capital entre stratégies
- Décide pour chaque trade (exécuter ? taille ? levier ?)
- Apprend de ses performances et s'adapte

**Commencez par le testnet**, puis passez progressivement au live avec un petit capital. Surveillez les performances et ajustez la configuration selon vos besoins.

**Bon trading ! 🚀**

