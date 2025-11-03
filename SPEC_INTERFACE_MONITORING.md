# 🚀 Spécification Technique : Interface Interactive & Système de Monitoring Avancé

## 🎯 Instructions d'Exécution pour GPT-5 High

**Mission** : Implémenter un système d'interface interactive Linux et un système de monitoring avancé pour le CryptoBot.

**Approche** :
1. **Lire et comprendre** toute cette spécification
2. **Analyser** la codebase actuelle (notamment `cryptobot/cli/live_hyperliquid.py`, `cryptobot/monitor/`, `cryptobot/llm/orchestrator.py`)
3. **Implémenter** selon la checklist d'implémentation (section 3.5)
4. **Tester** chaque composant après implémentation
5. **Intégrer** tous les composants ensemble
6. **Valider** selon les critères de validation (section 4)

**Ordre d'implémentation recommandé** :
- Phase 1 : Interface Interactive (logo, prompt, shell, commandes de base)
- Phase 2 : Système de Monitoring (collecte, stockage, insights)
- Phase 3 : Intégration (liaison bot ↔ monitoring)
- Phase 4 : Commande Monitor avancée avec tous les paramètres

**Principes à respecter** :
- Code propre, optimisé, efficace
- Interface soignée et professionnelle
- Performance : le monitoring ne doit pas ralentir le trading
- Robustesse : gestion d'erreurs gracieuse
- Documentation : commentaires et docstrings complets

---

## 📋 Vue d'Ensemble

Cette spécification définit les améliorations à apporter au CryptoBot pour :
1. **Transformation en programme interactif Linux** avec interface CLI personnalisée, logo ASCII, prompt et commandes personnalisées
2. **Système de monitoring avancé en temps réel** avec rapports détaillés, métriques de performance, et insights de l'IA

---

## 🎯 Objectif 1 : Programme Interactif Linux Personnalisé

### 1.1 Interface CLI Interactive

Le bot doit être transformé en **programme interactif** qui se lance dans un shell Linux et offre une expérience utilisateur soignée et professionnelle.

#### 1.1.1 Logo ASCII au Démarrage

**Exigence** : Afficher un logo ASCII stylisé lors du démarrage du bot.

**Spécifications** :
- Logo ASCII de style crypto/trading (ex: graphique, BTC, ou symbole abstrait)
- Couleurs ANSI (si terminal supporte) pour un rendu professionnel
- Dimensions : 60-80 caractères de largeur max pour compatibilité
- Affichage centré si possible
- Version texte simple si terminal ne supporte pas les couleurs

**Exemple de structure** :
```
    ╔═══════════════════════════════════════════════════════╗
    ║                                                       ║
    ║         ██████╗ ██████╗ ██╗   ██╗███████╗            ║
    ║        ██╔════╝██╔═══██╗╚██╗ ██╔╝██╔════╝            ║
    ║        ██║     ██║   ██║ ╚████╔╝ ███████╗            ║
    ║        ██║     ██║   ██║  ╚██╔╝  ╚════██║            ║
    ║        ╚██████╗╚██████╔╝   ██║   ███████║            ║
    ║         ╚═════╝ ╚═════╝    ╚═╝   ╚══════╝            ║
    ║                                                       ║
    ║            🤖 CryptoBot Trading System 🤖            ║
    ║                                                       ║
    ╚═══════════════════════════════════════════════════════╝
```

**Fichier** : `cryptobot/cli/logo.py` - Module dédié pour générer et afficher le logo

#### 1.1.2 Prompt Personnalisé

**Exigence** : Remplacer le prompt système par défaut par un prompt personnalisé du bot.

**Spécifications** :
- Format : `[CryptoBot] > ` ou `cryptobot@hyperliquid > `
- Affichage du statut : `[ACTIVE]`, `[PAUSED]`, `[ERROR]`
- Affichage optionnel de la session active (ex: nombre de trades, PnL)
- Couleurs conditionnelles (vert=actif, jaune=pause, rouge=erreur)

**Exemple** :
```
[CryptoBot@Hyperliquid:ACTIVE] > 
```

**Fichier** : `cryptobot/cli/prompt.py` - Module pour gérer le prompt personnalisé

#### 1.1.3 Système de Commandes Personnalisées

**Exigence** : Implémenter un shell interactif avec des commandes personnalisées.

**Architecture** :
- Utiliser `cmd.Cmd` de Python ou `prompt_toolkit` pour le shell interactif
- Commandes doivent être modulaires et extensibles
- Auto-complétion des commandes
- Historique des commandes (flèche haut/bas)
- Gestion des erreurs avec messages clairs

**Commandes à implémenter** :

| Commande | Alias | Description | Paramètres |
|----------|-------|-------------|------------|
| `start` | `s` | Démarrer le bot de trading | `--config <path>` |
| `stop` | `st` | Arrêter le bot proprement | - |
| `pause` | `p` | Mettre en pause le bot | - |
| `resume` | `r` | Reprendre le bot | - |
| `status` | `stat` | Afficher le statut actuel | - |
| `monitor` | `m` | Lancer le monitoring en temps réel | `--trades <n>`, `--refresh <sec>` |
| `trades` | `t` | Afficher les derniers trades | `--limit <n>`, `--strategy <name>` |
| `performance` | `perf` | Afficher les métriques de performance | `--period <1h|24h|7d|all>` |
| `portfolio` | `port` | Afficher l'état du portefeuille | - |
| `strategies` | `strats` | Lister les stratégies actives | - |
| `weights` | `w` | Afficher/modifier les poids des stratégies | `--set <strategy>=<weight>` |
| `risk` | - | Afficher les paramètres de risque | - |
| `config` | `cfg` | Afficher/modifier la configuration | `--get <key>`, `--set <key>=<value>` |
| `logs` | `l` | Afficher les logs récents | `--level <INFO|DEBUG|ERROR>`, `--tail <n>` |
| `help` | `h`, `?` | Afficher l'aide | `[command]` |
| `exit` | `quit`, `q` | Quitter le bot | - |
| `clear` | `cls` | Nettoyer l'écran | - |
| `version` | `v` | Afficher la version | - |

**Fichier** : `cryptobot/cli/shell.py` - Shell interactif principal
**Fichier** : `cryptobot/cli/commands/` - Modules de commandes individuelles

#### 1.1.4 Structure de Fichiers pour l'Interface

```
cryptobot/
├── cli/
│   ├── __init__.py
│   ├── shell.py              # Shell interactif principal
│   ├── logo.py               # Logo ASCII
│   ├── prompt.py             # Gestion du prompt
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── base.py           # Classe de base pour les commandes
│   │   ├── start.py          # Commande start
│   │   ├── stop.py           # Commande stop
│   │   ├── monitor.py        # Commande monitor
│   │   ├── trades.py         # Commande trades
│   │   ├── performance.py    # Commande performance
│   │   ├── portfolio.py      # Commande portfolio
│   │   ├── strategies.py     # Commande strategies
│   │   └── ...
│   └── interactive.py        # Point d'entrée principal pour le mode interactif
```

#### 1.1.5 Point d'Entrée Principal

**Fichier** : `cryptobot/cli/interactive.py`

**Fonctionnalités** :
- Initialisation du bot
- Affichage du logo
- Chargement de la configuration
- Initialisation des composants (broker, LLM, strategies, etc.)
- Lancement du shell interactif
- Gestion propre des signaux (SIGINT, SIGTERM)

**Structure** :
```python
def main():
    # 1. Afficher logo
    # 2. Charger config
    # 3. Initialiser composants
    # 4. Créer instance du shell
    # 5. Lancer shell interactif
```

#### 1.1.6 Script d'Installation

**Fichier** : `scripts/install_interactive.sh`

**Exigences** :
- Installation comme commande système : `cryptobot` ou `cb`
- Ajout au PATH si nécessaire
- Vérification des dépendances
- Création de liens symboliques

**Mise à jour de `pyproject.toml`** :
```toml
[project.scripts]
cryptobot = "cryptobot.cli.interactive:main"
cb = "cryptobot.cli.interactive:main"
```

---

## 🎯 Objectif 2 : Système de Monitoring Avancé en Temps Réel

### 2.1 Architecture du Monitoring

Le système de monitoring doit être **modulaire**, **performant**, et **complet**.

#### 2.1.1 Composants Principaux

1. **MonitorEngine** : Moteur principal de monitoring
2. **DataCollector** : Collecte des données en temps réel
3. **ReportGenerator** : Génération de rapports formatés
4. **LLMInsightsExtractor** : Extraction des insights de l'IA
5. **StateManager** : Gestion de l'état du bot

#### 2.1.2 Structure de Fichiers

```
cryptobot/
├── monitor/
│   ├── __init__.py
│   ├── engine.py              # Moteur principal
│   ├── collector.py           # Collecte de données
│   ├── reporter.py            # Génération de rapports
│   ├── insights.py            # Extraction insights IA
│   ├── state.py               # État (déjà existant, améliorer)
│   ├── performance.py         # Performance (déjà existant, améliorer)
│   ├── metrics.py             # Métriques avancées
│   └── display.py             # Affichage formaté (tables, graphiques ASCII)
```

### 2.2 Collecte de Données en Temps Réel

#### 2.2.1 Données à Collecter

**Trades** :
- Tous les trades (entrée, sortie, PnL, frais)
- Historique complet avec timestamp
- Métadonnées (stratégie, symbol, levier, confiance IA)

**Portefeuille** :
- Balance totale
- Positions ouvertes
- PnL réalisé/non réalisé
- Exposition par stratégie
- Exposition par symbole

**Performance** :
- Métriques par stratégie (win rate, avg win/loss, Sharpe, Max DD)
- Métriques globales (ROI, PnL total, nombre de trades)
- Courbe d'équité
- Métriques de risque (VaR, drawdown actuel)

**Décisions IA** :
- Dernières décisions d'allocation de stratégies
- Dernières décisions de trade (exécuté ou pas, pourquoi)
- Raisonnement de l'IA (extrait des prompts/réponses)
- Sentiments de l'IA (confiant, prudent, agressif, etc.)
- Ajustements récents (changements de poids, changements de comportement)

**Marché** :
- Prix actuels des symboles trackés
- Volumes
- Funding rates
- Sentiment (Reddit, Twitter, Polymarket)

#### 2.2.2 Stockage des Données

**Option 1** : SQLite (recommandé pour simplicité)
- Base de données locale : `~/.cryptobot/monitor.db`
- Tables : `trades`, `portfolio_snapshots`, `llm_decisions`, `performance_metrics`

**Option 2** : Fichiers JSON (plus simple mais moins performant)
- Dossier : `~/.cryptobot/monitor/`
- Fichiers : `trades.jsonl`, `portfolio.jsonl`, `llm_decisions.jsonl`

**Recommandation** : SQLite pour performance et requêtes complexes

**Fichier** : `cryptobot/monitor/storage.py` - Gestion du stockage

### 2.3 Extraction des Insights de l'IA

#### 2.3.1 Analyse des Décisions IA

**Fichier** : `cryptobot/monitor/insights.py`

**Fonctionnalités** :

1. **Extraction du Raisonnement** :
   - Analyser les prompts envoyés au LLM
   - Analyser les réponses du LLM
   - Extraire les justifications pour chaque décision
   - Parser les explications de l'IA

2. **Détection des Sentiments IA** :
   - Analyser le ton des réponses (confiant, prudent, agressif, neutre)
   - Détecter les changements d'humeur
   - Identifier les patterns de comportement

3. **Suivi des Ajustements** :
   - Détecter les changements de poids de stratégies
   - Identifier les changements de comportement (plus agressif, plus prudent)
   - Analyser les raisons des ajustements

4. **Métriques de Confiance** :
   - Niveau de confiance moyen par stratégie
   - Évolution de la confiance dans le temps
   - Corrélation confiance vs performance

**Intégration avec LLMOrchestrator** :
- Modifier `LLMOrchestrator` pour stocker les prompts et réponses
- Ajouter un champ `reasoning` dans les décisions
- Ajouter un champ `sentiment` dans les décisions

**Exemple de structure** :
```python
@dataclass
class LLMDecision:
    timestamp: float
    decision_type: str  # "allocation" or "trade"
    prompt: str
    response: str
    reasoning: str  # Extrait de la réponse
    sentiment: str  # "confident", "cautious", "aggressive", "neutral"
    confidence: float
    metadata: Dict[str, Any]
```

### 2.4 Génération de Rapports

#### 2.4.1 Rapport de Performance

**Fichier** : `cryptobot/monitor/reporter.py`

**Fonctionnalités** :

1. **Rapport de Trades** :
   - Liste des X derniers trades
   - Filtrage par stratégie, symbole, période
   - Tri par PnL, date, confiance
   - Format : tableau ASCII avec couleurs

2. **Rapport de Performance** :
   - Métriques globales (PnL total, ROI, nombre de trades)
   - Métriques par stratégie
   - Graphiques ASCII (courbe d'équité, distribution PnL)
   - Comparaison avec période précédente

3. **Rapport de Portefeuille** :
   - Balance totale
   - Positions ouvertes
   - Exposition par stratégie/symbole
   - PnL réalisé/non réalisé

4. **Rapport IA** :
   - Dernières décisions et raisonnements
   - Sentiments récents
   - Ajustements effectués
   - Niveaux de confiance

#### 2.4.2 Format d'Affichage

**Utiliser `rich`** pour :
- Tables formatées
- Couleurs et styles
- Barres de progression
- Graphiques ASCII (via `rich.progress` et `rich.console`)

**Exemple de rapport** :
```
╔══════════════════════════════════════════════════════════════╗
║              CryptoBot Performance Report                    ║
║                    Last 24 Hours                             ║
╠══════════════════════════════════════════════════════════════╣
║  Total PnL:        +$1,234.56  (+5.2%)                      ║
║  Total Trades:     42                                         ║
║  Win Rate:         67%                                        ║
║  Avg Win:          +$89.12                                    ║
║  Avg Loss:         -$34.56                                    ║
║  Sharpe Ratio:     2.34                                       ║
║  Max Drawdown:     -$234.00  (-1.2%)                         ║
╚══════════════════════════════════════════════════════════════╝
```

### 2.5 Commande de Monitoring

#### 2.5.1 Commande `monitor`

**Fichier** : `cryptobot/cli/commands/monitor.py`

**Syntaxe** :
```bash
monitor [OPTIONS]
```

**Options** :
- `--trades <n>` : Afficher les N derniers trades (défaut: 10)
- `--refresh <sec>` : Rafraîchir toutes les N secondes (défaut: 5)
- `--strategy <name>` : Filtrer par stratégie
- `--symbol <symbol>` : Filtrer par symbole
- `--period <1h|24h|7d|all>` : Période d'analyse
- `--format <table|json|compact>` : Format d'affichage
- `--insights` : Afficher les insights IA
- `--live` : Mode live avec rafraîchissement automatique

**Exemple d'utilisation** :
```bash
[CryptoBot@Hyperliquid:ACTIVE] > monitor --trades 20 --refresh 3 --insights --live
```

#### 2.5.2 Affichage en Temps Réel

**Fonctionnalités** :
- Rafraîchissement automatique de l'écran
- Mise en surbrillance des nouvelles données
- Indicateurs visuels (flèches, couleurs) pour les changements
- Barres de progression pour les métriques
- Graphiques ASCII pour les tendances

**Structure** :
```
┌─────────────────────────────────────────────────────────┐
│  CryptoBot Live Monitor - Last Update: 14:23:45        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  📊 Portfolio Summary                                   │
│  Balance: $10,234.56  │  PnL: +$234.56 (+2.3%)        │
│  Open Positions: 3  │  Total Trades: 42               │
│                                                         │
│  📈 Recent Trades (Last 5)                              │
│  [Table formatée avec trades récents]                  │
│                                                         │
│  🤖 AI Insights                                         │
│  Sentiment: Confident  │  Last Adjustment: 2m ago     │
│  Reasoning: "Market shows strong momentum, increasing   │
│             exposure to momentum strategy..."           │
│                                                         │
│  ⚡ Strategy Performance                                │
│  [Barres de performance par stratégie]                 │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 2.6 Intégration avec le Bot Principal

#### 2.6.1 Modifications Nécessaires

**Dans `live_hyperliquid.py`** :
- Ajouter hooks pour enregistrer toutes les décisions IA
- Enregistrer les trades dans le système de monitoring
- Enregistrer les snapshots de portefeuille
- Enregistrer les décisions d'allocation

**Dans `LLMOrchestrator`** :
- Stocker les prompts et réponses complets
- Extraire le raisonnement des réponses
- Détecter le sentiment

**Dans `PerformanceTracker`** :
- Améliorer le tracking des métriques
- Ajouter plus de détails (timestamps, métadonnées)

#### 2.6.2 Thread de Monitoring

**Option** : Créer un thread séparé qui collecte les données en continu
- Thread principal : Trading
- Thread monitoring : Collecte et stockage des données

**Fichier** : `cryptobot/monitor/engine.py`

```python
class MonitorEngine:
    def __init__(self, broker, orchestrator, performance_tracker):
        self.broker = broker
        self.orchestrator = orchestrator
        self.performance_tracker = performance_tracker
        self.collector = DataCollector()
        self.storage = StorageManager()
        self.running = False
        
    def start(self):
        """Démarrer le thread de monitoring"""
        
    def stop(self):
        """Arrêter le thread de monitoring"""
        
    def collect_data(self):
        """Collecter les données en continu"""
```

### 2.7 Paramètres de la Commande Monitor

#### 2.7.1 Paramètres Détaillés

**`--trades <n>`** :
- Afficher les N derniers trades
- Format : Tableau avec colonnes : Timestamp, Strategy, Symbol, Side, Size, Entry, Exit, PnL, Fees, Confidence
- Tri : Par défaut par timestamp (plus récent en premier)
- Filtrage : Par stratégie (`--strategy`), symbole (`--symbol`), période (`--period`)

**`--revenues`** :
- Afficher les revenus totaux
- Détail par stratégie
- Détail par période (1h, 24h, 7d, 30d, all)
- Graphique ASCII de l'évolution

**`--gains`** :
- Afficher uniquement les trades gagnants
- Total des gains
- Moyenne des gains
- Plus gros gain

**`--losses`** :
- Afficher uniquement les trades perdants
- Total des pertes
- Moyenne des pertes
- Plus grosse perte

**`--insights`** :
- Afficher les derniers raisonnements de l'IA
- Afficher les sentiments de l'IA
- Afficher les ajustements récents
- Afficher l'évolution de la confiance

**`--refresh <sec>`** :
- Rafraîchir l'affichage toutes les N secondes
- Mode live continu
- Indicateur de dernière mise à jour

**`--format <table|json|compact>`** :
- `table` : Format tableau avec `rich` (défaut)
- `json` : Format JSON pour scripts
- `compact` : Format compact sur une seule ligne

### 2.8 Exemple de Sortie Complète

```
╔════════════════════════════════════════════════════════════════════╗
║              🤖 CryptoBot Live Monitor 🤖                          ║
║              Last Update: 2024-01-15 14:23:45                     ║
╠════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  📊 PORTFOLIO SUMMARY                                              ║
║  ──────────────────────────────────────────────────────────────── ║
║  Total Balance:     $10,234.56                                    ║
║  Realized PnL:      +$1,456.78  (+16.5%)                          ║
║  Unrealized PnL:    +$234.56   (+2.3%)                            ║
║  Open Positions:    3                                            ║
║  Total Trades:      142                                           ║
║                                                                    ║
║  💰 REVENUES (Last 24h)                                            ║
║  ──────────────────────────────────────────────────────────────── ║
║  Total:             +$234.56                                       ║
║  By Strategy:                                                     ║
║    • Market Making:  +$123.45  (52.7%)                           ║
║    • Momentum:       +$67.89   (29.0%)                           ║
║    • Scalping:       +$34.12   (14.6%)                           ║
║    • Arbitrage:      +$9.10    (3.9%)                            ║
║                                                                    ║
║  📈 RECENT TRADES (Last 5)                                        ║
║  ──────────────────────────────────────────────────────────────── ║
║  Time      │ Strategy      │ Symbol │ Side │ Size    │ PnL      ║
║  ──────────┼───────────────┼────────┼──────┼─────────┼──────────║
║  14:23:12  │ Market Making │ BTC    │ BUY  │ $500.00 │ +$12.34  ║
║  14:22:45  │ Momentum      │ ETH    │ LONG │ $1000.00│ +$45.67  ║
║  14:21:30  │ Scalping      │ BTC    │ SELL │ $300.00 │ -$5.23   ║
║  14:20:15  │ Market Making │ ETH    │ BUY  │ $400.00 │ +$8.90   ║
║  14:19:00  │ Momentum      │ BTC    │ LONG │ $800.00 │ +$23.45  ║
║                                                                    ║
║  🎯 PERFORMANCE METRICS                                            ║
║  ──────────────────────────────────────────────────────────────── ║
║  Win Rate:          67%  ████████████████░░░░░░░░                  ║
║  Avg Win:           +$89.12                                         ║
║  Avg Loss:          -$34.56                                        ║
║  Sharpe Ratio:      2.34                                            ║
║  Max Drawdown:      -$234.00  (-1.2%)                              ║
║                                                                    ║
║  🤖 AI INSIGHTS                                                     ║
║  ──────────────────────────────────────────────────────────────── ║
║  Current Sentiment: 🟢 Confident                                   ║
║  Last Adjustment:   2 minutes ago                                  ║
║                                                                    ║
║  Recent Reasoning:                                                 ║
║  "Market shows strong upward momentum with high volume.            ║
║   Increasing exposure to momentum strategy (25% → 30%).            ║
║   Reducing market making allocation due to low spreads.            ║
║   Confidence level: High (0.85)"                                   ║
║                                                                    ║
║  Strategy Weights:                                                 ║
║  • Market Making:   30%  ████████████████░░░░░░░░                  ║
║  • Momentum:        30%  ████████████████░░░░░░░░                  ║
║  • Scalping:        15%  ████████░░░░░░░░░░░░░░░░                  ║
║  • Arbitrage:       12%  ██████░░░░░░░░░░░░░░░░░░                  ║
║  • Breakout:         8%  ████░░░░░░░░░░░░░░░░░░░░                  ║
║  • Sniping:          5%  ██░░░░░░░░░░░░░░░░░░░░░░                  ║
║                                                                    ║
║  ⚡ STRATEGY PERFORMANCE                                            ║
║  ──────────────────────────────────────────────────────────────── ║
║  Market Making:  PnL: +$456.78  │ Win Rate: 72%  │ Trades: 45   ║
║  Momentum:       PnL: +$234.56  │ Win Rate: 65%  │ Trades: 32   ║
║  Scalping:       PnL: +$123.45  │ Win Rate: 68%  │ Trades: 28   ║
║  Arbitrage:      PnL: +$67.89   │ Win Rate: 75%  │ Trades: 12   ║
║  Breakout:       PnL: +$45.67   │ Win Rate: 60%  │ Trades: 15   ║
║  Sniping:        PnL: +$12.34   │ Win Rate: 55%  │ Trades: 10   ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝
```

---

## 🔧 Implémentation Technique

### 3.1 Dépendances Supplémentaires

**Ajouter à `requirements.txt`** :
```
prompt-toolkit>=3.0.0  # Pour le shell interactif
rich>=13.9.4           # Déjà présent, pour l'affichage
sqlalchemy>=2.0.0      # Pour SQLite (optionnel, peut utiliser sqlite3 directement)
```

### 3.2 Structure de Configuration

**Ajouter à la config YAML** :
```yaml
cli:
  interactive: true
  logo_enabled: true
  prompt_format: "[CryptoBot@{exchange}:{status}] > "
  
monitor:
  enabled: true
  storage_type: "sqlite"  # ou "json"
  storage_path: "~/.cryptobot/monitor.db"
  collect_interval_sec: 5
  retention_days: 30
  llm_insights_enabled: true
```

### 3.3 Gestion des Erreurs

- Toutes les commandes doivent gérer les erreurs proprement
- Messages d'erreur clairs et informatifs
- Logging des erreurs pour débogage
- Fallback gracieux si le monitoring échoue

### 3.4 Performance

- Le monitoring ne doit pas impacter les performances du trading
- Utiliser des threads pour la collecte de données
- Mise en cache des données fréquemment accédées
- Optimisation des requêtes de base de données

### 3.5 Tests

**Fichiers de tests** :
- `tests/test_cli_shell.py`
- `tests/test_monitor_engine.py`
- `tests/test_monitor_insights.py`
- `tests/test_monitor_reporter.py`

---

## 📝 Checklist d'Implémentation

### Phase 1 : Interface Interactive
- [ ] Créer `cryptobot/cli/logo.py` avec logo ASCII
- [ ] Créer `cryptobot/cli/prompt.py` pour gestion du prompt
- [ ] Créer `cryptobot/cli/shell.py` avec shell interactif
- [ ] Créer `cryptobot/cli/commands/` avec toutes les commandes
- [ ] Créer `cryptobot/cli/interactive.py` comme point d'entrée
- [ ] Mettre à jour `pyproject.toml` avec les scripts
- [ ] Créer script d'installation
- [ ] Tester toutes les commandes

### Phase 2 : Système de Monitoring
- [ ] Créer `cryptobot/monitor/engine.py`
- [ ] Créer `cryptobot/monitor/collector.py`
- [ ] Créer `cryptobot/monitor/storage.py`
- [ ] Créer `cryptobot/monitor/insights.py`
- [ ] Créer `cryptobot/monitor/reporter.py`
- [ ] Créer `cryptobot/monitor/display.py`
- [ ] Améliorer `cryptobot/monitor/performance.py`
- [ ] Améliorer `cryptobot/monitor/state.py`

### Phase 3 : Intégration
- [ ] Modifier `live_hyperliquid.py` pour intégrer le monitoring
- [ ] Modifier `LLMOrchestrator` pour stocker les décisions
- [ ] Créer la commande `monitor` dans le shell
- [ ] Tester le monitoring en temps réel
- [ ] Optimiser les performances

### Phase 4 : Documentation et Tests
- [ ] Documenter toutes les commandes
- [ ] Créer des tests unitaires
- [ ] Créer des tests d'intégration
- [ ] Mettre à jour le README
- [ ] Créer un guide d'utilisation

---

## 🎨 Design et UX

### Principes de Design
- **Clarté** : Interface claire et intuitive
- **Efficacité** : Commandes rapides et raccourcis
- **Esthétique** : Rendu soigné avec couleurs et formatage
- **Performance** : Réactivité immédiate
- **Robustesse** : Gestion d'erreurs gracieuse

### Couleurs et Styles
- **Vert** : Succès, positif, actif
- **Rouge** : Erreur, perte, danger
- **Jaune** : Avertissement, pause
- **Bleu** : Information, neutre
- **Cyan** : IA, insights
- **Magenta** : Commandes, actions

---

## 🚀 Commandes d'Utilisation

### Lancement du Bot
```bash
# Installation
pip install -e .
# ou
python -m pip install -e .

# Lancement
cryptobot
# ou
cb
```

### Exemples d'Utilisation

```bash
# Démarrer le bot
[CryptoBot@Hyperliquid:STOPPED] > start --config configs/live.hyperliquid.yaml

# Monitorer en temps réel
[CryptoBot@Hyperliquid:ACTIVE] > monitor --trades 20 --refresh 3 --insights --live

# Voir les derniers trades
[CryptoBot@Hyperliquid:ACTIVE] > trades --limit 10 --strategy momentum

# Voir les performances
[CryptoBot@Hyperliquid:ACTIVE] > performance --period 24h

# Voir le portefeuille
[CryptoBot@Hyperliquid:ACTIVE] > portfolio

# Voir les insights IA
[CryptoBot@Hyperliquid:ACTIVE] > monitor --insights

# Pause/Resume
[CryptoBot@Hyperliquid:ACTIVE] > pause
[CryptoBot@Hyperliquid:PAUSED] > resume
```

---

## ✅ Critères de Validation

Le système est considéré comme **complet** lorsque :

1. ✅ Le bot démarre avec un logo ASCII et un prompt personnalisé
2. ✅ Toutes les commandes sont fonctionnelles
3. ✅ Le monitoring collecte toutes les données en temps réel
4. ✅ Les rapports affichent correctement toutes les métriques
5. ✅ Les insights IA sont extraits et affichés
6. ✅ La commande `monitor` fonctionne avec tous les paramètres
7. ✅ Les performances du trading ne sont pas impactées
8. ✅ L'interface est soignée, propre et professionnelle
9. ✅ Tous les tests passent
10. ✅ La documentation est complète

---

## 📚 Références

- Architecture actuelle : `cryptobot/cli/live_hyperliquid.py`
- Monitoring actuel : `cryptobot/monitor/performance.py`, `cryptobot/monitor/state.py`
- LLM Orchestrator : `cryptobot/llm/orchestrator.py`
- Documentation Rich : https://rich.readthedocs.io/
- Documentation Prompt Toolkit : https://python-prompt-toolkit.readthedocs.io/

---

**Fin de la Spécification**

