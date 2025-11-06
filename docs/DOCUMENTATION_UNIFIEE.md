# CryptoBot — Documentation unifiée

Bot de trading crypto modulaire, axé day-trading et futures, inspiré de nof1.ai. Il démarre par un socle simple en paper trading, puis évolue vers un ensemble de stratégies (ensemble) avec, en option, une orchestration pilotée par LLM (DeepSeek) et une intégration Hyperliquid (testnet et live).

Cette page consolide la documentation du dépôt, en supprimant les redondances et le contenu non essentiel.

---

## 1) Démarrage rapide

1. Créer l’environnement et installer les dépendances

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

2. Préparer l’environnement et la configuration

```bash
cp env.example .env             # ou docs/ENV_HYPERLIQUID_EXAMPLE.txt si vous visez Hyperliquid
cp configs/paper.sample.yaml configs/run.yaml
```

3. Lancer un run local (paper/backtest)

```bash
python -m cryptobot.cli.run --config configs/run.yaml
```

---

## 2) Concepts et architecture

- Modules clés: `core/` (config, types, logging), `data/` (fournisseurs de données), `broker/` (exécution simulée et gestion du portefeuille/risque), `strategy/` (stratégies), `llm/` (client, prompts, orchestration), `monitor/` (métriques et reporting), `cli/` (entrées de commande), `backtest/` (engine).
- Fonctionnement cyclique (≈ 30 à 90 s selon config): collecte des données → détection d’opportunités par stratégies → décisions (LLM si activé) → gestion du risque → exécution → suivi de performance.
- Orchestration LLM (optionnelle): distribution dynamique du capital entre stratégies et décision locale d’exécution/levier par opportunité.

Stratégies disponibles (base): arbitrage, sniping, market making, momentum, sentiment Reddit/Twitter.

---

## 3) Configuration (.env et YAML)

Placez les secrets dans `.env` uniquement (jamais dans YAML). Exemples utiles:

```bash
# DeepSeek (LLM) — optionnel mais requis si orchestration activée
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

# Hyperliquid — requis si vous utilisez Hyperliquid
HYPERLIQUID_WALLET_ADDRESS=0x...
HYPERLIQUID_TESTNET_PRIVATE_KEY=0x...   # testnet
HYPERLIQUID_LIVE_PRIVATE_KEY=0x...      # live (NE PAS COMMITTER)

# Exchanges CCXT (optionnel, ex. arbitrage)
EXCHANGE_API_KEY=...
EXCHANGE_API_SECRET=...
```

Extrait de config YAML (ex. Hyperliquid):

```yaml
general:
  capital: 10000.0
  symbols: ["BTC/USD:USD", "ETH/USD:USD"]
  timeframe: "1m"
  market_type: futures

hyperliquid:
  testnet: true           # false pour live
  default_leverage: 10
  max_leverage: 50

llm:
  decision_interval_sec: 60
  context_window_bars: 60

risk:
  max_position_pct: 1.0
  max_daily_drawdown_pct: 10
```

Note: le format des symboles dépend du provider/exchange utilisé.
- CCXT (ex. Binance): utilisez des symboles de type `BTC/USDT`.
- Hyperliquid: utilisez des symboles de type `BTC/USD:USD`.

Bonnes pratiques:
- Secrets uniquement dans `.env` (fichiers `.env` ignorés par git).
- Vous pouvez utiliser `~/.cryptobot/.env` (chargé automatiquement).
- Les overrides locaux de YAML peuvent être suffixés en `.local.yaml` (ignorés par git).

---

## 4) Lancer le bot

- Paper/live via CCXT (exchanges supportés):

```bash
python -m cryptobot.cli.live --config configs/live.frugal.yaml --provider ccxt
```

- Intégration Hyperliquid (testnet ou live):

```bash
# Testnet (recommandé au début)
python -m cryptobot.cli.live_hyperliquid --config configs/live.hyperliquid.yaml

# Mainnet (quand prêt: testnet=false et clé live dans .env)
python -m cryptobot.cli.live_hyperliquid --config configs/live.hyperliquid.yaml
```

Notes:
- Commencez toujours par le testnet, avec petit capital en live ensuite.
- Surveillez `logs/cryptobot.log` pendant l’exécution.

---

## 5) Hyperliquid — repères essentiels

Testnet vs live:
- Variables `.env` distinctes (clé privée testnet vs live).
- `hyperliquid.testnet: true/false` dans le YAML.
- Endpoint SDK/API: utilisez les URLs du SDK/documentation officielle Hyperliquid pour testnet/mainnet.

Démarrage rapide testnet:

```bash
pip install hyperliquid-python-sdk
cp docs/ENV_HYPERLIQUID_EXAMPLE.txt .env  # puis renseigner les valeurs
python -m cryptobot.cli.live_hyperliquid --config configs/live.hyperliquid.yaml
```

Sécurité:
- Ne placez pas la clé privée mainnet tant que vous n’êtes pas prêt pour le live.
- Conservez un levier modéré, définissez des limites de drawdown.

---

## 6) France — solutions légales (résumé)

- Deribit (recommandé pour démarrer): accepte les résidents français, trading 24/7 sur BTC/ETH, compatible CCXT.
  - Étapes: créer compte (KYC), créer clé API (trade/read), adapter `exchange_id` et symboles si usage CCXT.
- Interactive Brokers: régulé, légal, mais API différente (via `ib_insync`), pas 24/7, plus complexe.

Évitez les contournements (VPN, compte tiers, etc.). Déclarez vos gains conformément à la législation française.

---

## 7) Orchestration LLM (optionnelle)

Si activée, DeepSeek prend deux rôles:
- Allocation dynamique entre stratégies (poids ajustés selon performance et marché).
- Décision par opportunité (exécuter? taille USD? levier? SL/TP?).

Bonnes pratiques coûts/latence:
- Intervalle de décision ≥ 60–90 s, contexte compact, filtrage préalable d’opportunités.
- Suivre un budget mensuel et journaliser les coûts.

---

## 8) Monitoring et logs

- Logs: `logs/cryptobot.log` (suivi en temps réel recommandé).

```bash
tail -f logs/cryptobot.log
```

- Métriques/Performances: le module `monitor/` calcule PnL, win rate, Sharpe, drawdown et peut alimenter l’orchestrateur LLM.
- Une commande `monitor` peut être disponible selon votre build CLI pour afficher en continu les trades/performances/insights.

---

## 9) Déploiement sur VPS (Linux)

Installation rapide (automatisée):

```bash
ssh user@your-vps
curl -o setup_vps.sh https://raw.githubusercontent.com/jossdip/CryptoBot/main/deploy/setup_vps.sh
chmod +x setup_vps.sh
./setup_vps.sh https://github.com/jossdip/CryptoBot.git main
```

Ensuite:

```bash
cd ~/CryptoBot
cp env.example .env && nano .env
sudo ./deploy/install_service.sh paper   # ou live
sudo journalctl -u cryptobot-paper@$(whoami) -f
```

Mises à jour:

```bash
cd ~/CryptoBot
./deploy/update.sh paper  # ou live
```

---

## 10) Dépannage (checklist courte)

- Rien ne se lance / clé LLM consommée inopinément:
  - Vérifier services actifs: `sudo systemctl list-units | grep cryptobot`
  - Arrêter les services: `sudo systemctl stop cryptobot-*@$(whoami)`
  - Tuer les processus orphelins: `pkill -f "cryptobot"`

- Testnet CCXT n’est pas utilisé:
  - Config `place_on_testnet: true` (si applicable au broker concerné) et clés testnet dans `.env`.

- Erreurs d’authentification exchange:
  - Vérifier `EXCHANGE_API_KEY/SECRET` dans `.env` et permissions (Read/Trade).

- Logs vides / permissions:
  - `chmod -R 755 logs/`

---

## 11) Coûts LLM — ordre de grandeur et optimisations

- Budget typique: ~15–60 USD/mois selon activité et réglages (après optimisations de fréquence/contexte/cache).
- Réduire les coûts:
  - Augmenter `decision_interval_sec` (ex. 60–90 s).
  - Réduire la fenêtre de contexte envoyée au LLM.
  - Filtrer les opportunités avant d’appeler le LLM.
  - Mettre en place un budget mensuel et du caching.

Surveiller régulièrement les coûts (ex. script `scripts/show_llm_costs.py`).

---

## 12) Sécurité et conformité

- Ne commitez jamais `.env` (assurez-vous qu’il est ignoré par git).
- Limitez les permissions clés API et utilisez l’IP whitelisting si possible.
- Débutez sur testnet, puis live avec petit capital.
- Respectez la réglementation locale (déclaration des gains, etc.).

---

## 13) Annexes

Exemple d’utilisation (paper → live frugal CCXT → Hyperliquid):

```bash
# Paper/backtest
python -m cryptobot.cli.run --config configs/run.yaml

# Live CCXT frugal
python -m cryptobot.cli.live --config configs/live.frugal.yaml --provider ccxt

# Hyperliquid testnet/live
python -m cryptobot.cli.live_hyperliquid --config configs/live.hyperliquid.yaml
```

Exemple `.env` (extrait):

```bash
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
HYPERLIQUID_WALLET_ADDRESS=0x...
HYPERLIQUID_TESTNET_PRIVATE_KEY=0x...
# HYPERLIQUID_LIVE_PRIVATE_KEY=0x...    # à n’ajouter qu’en live
```

—

Avertissement: ce logiciel est fourni pour la recherche et le paper-trading. Aucune recommandation financière. Utilisation à vos risques.


