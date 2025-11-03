# 🚀 Spécification Technique : Adaptation CryptoBot à Hyperliquid (LLM-Driven)

## 📋 Objectif

Adapter le bot CryptoBot pour trader sur **Hyperliquid** (futures perpétuels) avec un système **100% LLM-driven via DeepSeek**, supportant les modes **testnet** et **live**, optimisé pour **VPS Kali**, avec un système de **pondération dynamique** des stratégies pour maximiser les profits.

---

## 🎯 Architecture Globale

### **Stack Technique**
- **Exchange :** Hyperliquid (perpetuals futures)
- **LLM :** DeepSeek (pilotage 100% LLM)
- **API :** Hyperliquid Python SDK
- **Environnement :** VPS Kali Linux
- **Modes :** Testnet + Live (switching automatique)

### **Flux de Données**
```
Market Data (Hyperliquid) 
  → Data Aggregator
    → Strategy Signals (multiple sources)
      → DeepSeek LLM (Pondération Dynamique)
        → Risk Manager
          → Hyperliquid Broker (testnet/live)
            → Execution Engine
              → Portfolio Tracker
                → Performance Feedback → DeepSeek (learning loop)
```

---

## 1️⃣ Intégration Hyperliquid

### **1.1 Broker Hyperliquid**

**Fichier :** `cryptobot/broker/hyperliquid_broker.py`

**Fonctionnalités requises :**
- ✅ Support testnet ET live (mode switching)
- ✅ Gestion des perpétuels futures
- ✅ Levier jusqu'à 50x (configurable par stratégie)
- ✅ Orders : market, limit, stop-loss
- ✅ Portfolio tracking (balance, positions, PnL)
- ✅ Funding rate monitoring
- ✅ WebSocket pour updates temps réel

**Structure :**
```python
from hyperliquid_python_sdk import Client
from typing import Dict, Optional, Literal

class HyperliquidBroker:
    def __init__(
        self,
        wallet_address: str,
        private_key: str,
        testnet: bool = True,
        market_type: Literal["perpetual"] = "perpetual"
    ):
        self.testnet = testnet
        base_url = "https://api.hyperliquid-testnet.xyz" if testnet else "https://api.hyperliquid.xyz"
        self.client = Client(
            base_url=base_url,
            wallet_address=wallet_address,
            private_key=private_key
        )
    
    def place_order(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        size: float,
        leverage: int = 5,
        order_type: Literal["market", "limit"] = "market",
        price: Optional[float] = None,
        stop_loss: Optional[float] = None
    ) -> Dict:
        """Execute order on Hyperliquid"""
        # Implementation
        
    def get_portfolio(self) -> Dict:
        """Get current portfolio state"""
        # Implementation
        
    def get_funding_rate(self, symbol: str) -> float:
        """Get current funding rate"""
        # Implementation
```

**Configuration :**
- Wallet address et private key depuis `.env`
- Mode testnet/live depuis config YAML
- Support switching dynamique (testnet → live)

---

### **1.2 Data Provider Hyperliquid**

**Fichier :** `cryptobot/data/hyperliquid_live.py`

**Fonctionnalités :**
- ✅ OHLCV en temps réel (WebSocket)
- ✅ Ticker data (prix, volume, bid/ask)
- ✅ Orderbook depth (pour arbitrage)
- ✅ Funding rates
- ✅ New listings monitoring (pour sniping)

**Structure :**
```python
def hyperliquid_ohlcv(
    symbol: str,
    timeframe: str = "1m",
    testnet: bool = True,
    poll_sec: float = 1.0
) -> Iterable[Bar]:
    """Stream OHLCV bars from Hyperliquid"""
    # WebSocket stream implementation
```

---

### **1.3 Configuration**

**Fichier :** `configs/live.hyperliquid.yaml`

```yaml
general:
  seed: 42
  start: "2024-01-01"
  end: "2030-01-01"
  timeframe: "1m"
  capital: 10000.0
  symbols: ["BTC/USD:USD", "ETH/USD:USD"]
  market_type: futures
  exchange_id: hyperliquid

hyperliquid:
  testnet: true  # false for live
  wallet_address: ""  # from .env
  private_key: ""  # from .env (never commit!)
  default_leverage: 10
  max_leverage: 50
  margin_mode: isolated

data:
  provider: hyperliquid
  steps_per_bar: 20
  monitor_new_listings: true  # for sniping

broker:
  fee_bps: 2  # Hyperliquid taker fee
  slippage_bps: 5
  testnet: true
  margin_mode: isolated
  default_leverage: 10
  max_leverage: 50

risk:
  max_position_pct: 1.0
  max_daily_drawdown_pct: 10
  max_leverage_per_strategy: 30  # safety limit

llm:
  enabled: true
  model: deepseek-chat
  base_url: https://api.deepseek.com/v1
  api_key: ""  # from .env
  decision_interval_sec: 30  # How often LLM makes decisions
  context_window_bars: 60  # Bars to send to LLM
  
strategy_weights:
  # DeepSeek will dynamically adjust these
  initial_weights:
    arbitrage: 0.20
    sniping: 0.15
    market_making: 0.30
    momentum: 0.15
    sentiment_reddit: 0.10
    sentiment_twitter: 0.10
  # LLM can modify these based on performance

sentiment:
  reddit:
    enabled: true
    subreddits: ["cryptocurrency", "bitcoin", "ethtrader"]
    check_interval_sec: 300
  twitter:
    enabled: true
    keywords: ["BTC", "ETH", "crypto"]
    check_interval_sec: 300

backtest:
  report:
    output_dir: logs/reports
```

---

## 2️⃣ Système LLM-Driven 100% DeepSeek

### **2.1 LLM Orchestrator**

**Fichier :** `cryptobot/llm/orchestrator.py`

**Fonctionnalités :**
- ✅ **Pondération dynamique** des stratégies
- ✅ **Décision globale** (quelle stratégie activer, avec quels poids)
- ✅ **Capital allocation** entre stratégies
- ✅ **Risk management** adaptatif
- ✅ **Learning loop** (feedback performance → ajustement)

**Structure :**
```python
@dataclass
class StrategyWeight:
    arbitrage: float = 0.20
    sniping: float = 0.15
    market_making: float = 0.30
    momentum: float = 0.15
    sentiment_reddit: float = 0.10
    sentiment_twitter: float = 0.10
    
    def normalize(self):
        """Ensure weights sum to 1.0"""
        total = sum(vars(self).values())
        for key in vars(self):
            setattr(self, key, getattr(self, key) / total)

class LLMOrchestrator:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self.weights = StrategyWeight()
        self.performance_history: List[Dict] = []
        
    def decide_strategy_allocation(
        self,
        market_data: Dict,
        portfolio_state: Dict,
        sentiment_data: Dict,
        performance_metrics: Dict
    ) -> StrategyWeight:
        """
        DeepSeek décide comment allouer le capital entre stratégies
        basé sur :
        - Conditions de marché actuelles
        - Performance historique de chaque stratégie
        - Sentiment social media
        - Opportunités détectées (arbitrage, sniping, etc.)
        """
        context = {
            "market": market_data,
            "portfolio": portfolio_state,
            "sentiment": sentiment_data,
            "performance": performance_metrics,
            "current_weights": vars(self.weights),
            "recent_returns": self._get_recent_returns()
        }
        
        prompt = self._build_allocation_prompt(context)
        response = self.llm.call(prompt)
        
        # Parse response and update weights
        new_weights = self._parse_strategy_weights(response)
        self.weights = new_weights
        return new_weights
        
    def decide_trade(
        self,
        strategy_name: str,
        opportunity: Dict,
        market_context: Dict
    ) -> Dict:
        """
        Pour une stratégie spécifique, DeepSeek décide :
        - Entrer ou pas ?
        - Taille de la position ?
        - Levier à utiliser ?
        - Stop-loss / take-profit ?
        """
        context = {
            "strategy": strategy_name,
            "opportunity": opportunity,
            "market": market_context,
            "current_weights": vars(self.weights),
            "risk_tolerance": self._calculate_risk_tolerance()
        }
        
        prompt = self._build_trade_prompt(context)
        response = self.llm.call(prompt)
        
        return self._parse_trade_decision(response)
    
    def update_performance(self, strategy: str, pnl: float):
        """Feedback loop : performance → ajustement pondérations"""
        self.performance_history.append({
            "strategy": strategy,
            "pnl": pnl,
            "timestamp": time.time()
        })
        # Keep only last 1000 entries
        if len(self.performance_history) > 1000:
            self.performance_history = self.performance_history[-1000:]
```

---

### **2.2 Prompts Optimisés pour DeepSeek**

**Fichier :** `cryptobot/llm/prompts.py`

**Prompt Allocation Stratégies :**
```python
ALLOCATION_PROMPT_TEMPLATE = """
You are an expert crypto trading AI managing a portfolio of automated strategies on Hyperliquid.

Your goal: Maximize profit as quickly as possible.

Available strategies:
1. ARBITRAGE: Exploit price differences between exchanges (low risk, consistent returns)
2. SNIPING: Catch new token listings early (high risk, high reward)
3. MARKET_MAKING: Provide liquidity, earn spreads (medium risk, steady returns)
4. MOMENTUM: Follow strong price movements with leverage (high risk, high reward)
5. SENTIMENT_REDDIT: Trade based on Reddit sentiment (medium risk, volatile)
6. SENTIMENT_TWITTER: Trade based on Twitter/X sentiment (medium risk, volatile)

Current market conditions:
{market_data}

Portfolio state:
{portfolio_state}

Recent performance by strategy:
{performance_metrics}

Sentiment data:
{sentiment_data}

Current capital allocation weights:
{current_weights}

Recent returns (last 24h):
{recent_returns}

Based on this context, output a JSON with new strategy weights (sum must equal 1.0):
{{
    "arbitrage": 0.XX,
    "sniping": 0.XX,
    "market_making": 0.XX,
    "momentum": 0.XX,
    "sentiment_reddit": 0.XX,
    "sentiment_twitter": 0.XX,
    "reasoning": "Brief explanation of allocation choice"
}}

Rules:
- If arbitrage opportunities are high → increase arbitrage weight
- If market is trending strongly → increase momentum weight
- If new listings detected → increase sniping weight (but limit to 15% max for safety)
- If sentiment is extremely bullish/bearish → increase sentiment weights
- Market making should always have at least 20% (stable income)
- Total weights must sum to exactly 1.0
"""
```

**Prompt Trade Decision :**
```python
TRADE_PROMPT_TEMPLATE = """
You are executing a {strategy_name} strategy trade.

Opportunity detected:
{opportunity}

Market context:
{market_context}

Portfolio state:
{portfolio_state}

Current strategy weights:
{current_weights}

Risk tolerance (calculated):
{risk_tolerance}

Decide if we should execute this trade. Output JSON:
{{
    "execute": true/false,
    "direction": "long"/"short"/"flat",
    "size_usd": XXXX.XX,
    "leverage": X (1-50),
    "stop_loss_pct": X.XX (percentage below entry for long, above for short),
    "take_profit_pct": X.XX (percentage above entry for long, below for short),
    "confidence": 0.0-1.0,
    "reasoning": "Why this decision"
}}

Rules:
- Only execute if confidence > 0.7
- Use leverage conservatively: start low, increase only with high confidence
- Always set stop-loss (max loss: 5% of allocated capital for this strategy)
- For sniping: higher risk acceptable but limit size
- For arbitrage: lower risk, can use larger size
"""
```

---

### **2.3 LLM Client Enhanced**

**Fichier :** `cryptobot/llm/client.py` (modifier existant)

**Ajouts nécessaires :**
- ✅ Méthode `call()` générique pour prompts personnalisés
- ✅ Caching des réponses (éviter appels redondants)
- ✅ Retry logic avec exponential backoff
- ✅ Token optimization (compression contexte)

```python
def call(
    self,
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 512,
    json_mode: bool = True
) -> Dict:
    """Generic LLM call with JSON parsing"""
    # Implementation with retry logic
```

---

## 3️⃣ Système de Pondération Dynamique

### **3.1 Strategy Weight Manager**

**Fichier :** `cryptobot/strategy/weight_manager.py`

**Fonctionnalités :**
- ✅ **Tracking performance** par stratégie
- ✅ **Recalcul des poids** basé sur ROI récent
- ✅ **Limites de sécurité** (ex: sniping max 15%)
- ✅ **Smoothing** (éviter changements trop brusques)

**Structure :**
```python
class WeightManager:
    def __init__(self):
        self.weights = StrategyWeight()
        self.performance_tracker: Dict[str, List[float]] = {}
        
    def update_performance(self, strategy: str, pnl: float):
        """Track PnL for each strategy"""
        if strategy not in self.performance_tracker:
            self.performance_tracker[strategy] = []
        self.performance_tracker[strategy].append(pnl)
        # Keep last 100
        if len(self.performance_tracker[strategy]) > 100:
            self.performance_tracker[strategy] = self.performance_tracker[strategy][-100:]
    
    def get_performance_score(self, strategy: str, window: int = 24) -> float:
        """Calculate ROI score for last N hours"""
        if strategy not in self.performance_tracker:
            return 0.0
        recent = self.performance_tracker[strategy][-window:]
        if not recent:
            return 0.0
        return sum(recent) / len(recent)  # Average PnL
    
    def calculate_adaptive_weights(self) -> StrategyWeight:
        """
        Adjust weights based on recent performance
        Strategies with better recent performance get higher weights
        """
        scores = {
            strat: self.get_performance_score(strat) 
            for strat in ["arbitrage", "sniping", "market_making", "momentum", 
                         "sentiment_reddit", "sentiment_twitter"]
        }
        
        # Softmax normalization
        import numpy as np
        exp_scores = {k: np.exp(v * 10) for k, v in scores.items()}
        total = sum(exp_scores.values())
        
        new_weights = StrategyWeight(
            arbitrage=exp_scores["arbitrage"] / total,
            sniping=min(0.15, exp_scores["sniping"] / total),  # Cap at 15%
            market_making=max(0.20, exp_scores["market_making"] / total),  # Min 20%
            momentum=exp_scores["momentum"] / total,
            sentiment_reddit=exp_scores["sentiment_reddit"] / total,
            sentiment_twitter=exp_scores["sentiment_twitter"] / total
        )
        new_weights.normalize()
        
        # Smoothing: blend 70% new, 30% old
        self.weights = StrategyWeight(
            arbitrage=self.weights.arbitrage * 0.3 + new_weights.arbitrage * 0.7,
            sniping=self.weights.sniping * 0.3 + new_weights.sniping * 0.7,
            market_making=self.weights.market_making * 0.3 + new_weights.market_making * 0.7,
            momentum=self.weights.momentum * 0.3 + new_weights.momentum * 0.7,
            sentiment_reddit=self.weights.sentiment_reddit * 0.3 + new_weights.sentiment_reddit * 0.7,
            sentiment_twitter=self.weights.sentiment_twitter * 0.3 + new_weights.sentiment_twitter * 0.7
        )
        self.weights.normalize()
        
        return self.weights
```

---

## 4️⃣ Stratégies Individuelles

### **4.1 Arbitrage Strategy**

**Fichier :** `cryptobot/strategy/arbitrage.py`

**Fonctionnalités :**
- ✅ **Monitor prix** Hyperliquid vs autres exchanges (Binance, OKX, dYdX)
- ✅ **Détecter écarts** > seuil (0.1% minimum)
- ✅ **Exécuter rapidement** (API parallèles)
- ✅ **Gérer capital** entre exchanges

```python
class ArbitrageStrategy:
    def detect_opportunities(self) -> List[Dict]:
        """Scan for arbitrage opportunities"""
        # Compare prices across exchanges
        # Return list of opportunities with spread %
        
    def execute(self, opportunity: Dict) -> bool:
        """Execute arbitrage trade"""
        # Buy on cheaper exchange, sell on expensive
```

---

### **4.2 Sniping Strategy**

**Fichier :** `cryptobot/strategy/sniping.py`

**Fonctionnalités :**
- ✅ **Monitor nouveaux listings** Hyperliquid (API WebSocket)
- ✅ **Analyse rapide** (volume initial, market cap, etc.)
- ✅ **Entrée rapide** avec levier (si opportunité validée par LLM)
- ✅ **Stop-loss strict** (-5% max)

```python
class SnipingStrategy:
    def monitor_new_listings(self):
        """Watch for new token listings"""
        # WebSocket subscription to new listings
        
    def analyze_opportunity(self, token: Dict) -> Dict:
        """Quick analysis: volume, initial price action, etc."""
        
    def execute(self, token: str, llm_decision: Dict) -> bool:
        """Execute snipe based on LLM decision"""
```

---

### **4.3 Market Making Strategy**

**Fichier :** `cryptobot/strategy/market_making.py`

**Fonctionnalités :**
- ✅ **Place orders bid/ask** autour du mid price
- ✅ **Gérer spread optimal** (calculé par LLM)
- ✅ **Replace orders** quand exécutés
- ✅ **Éviter adverse selection** (surveillance constante)

```python
class MarketMakingStrategy:
    def calculate_spread(self, symbol: str, volatility: float) -> float:
        """LLM decides optimal spread based on volatility"""
        
    def place_maker_orders(self, symbol: str, mid_price: float, spread: float):
        """Place bid/ask orders"""
```

---

### **4.4 Momentum Strategy**

**Fichier :** `cryptobot/strategy/momentum.py`

**Fonctionnalités :**
- ✅ **Détecter breakouts** (prix, volume, RSI)
- ✅ **Entrer avec levier** (décidé par LLM)
- ✅ **Stop-loss / take-profit** adaptatifs

---

### **4.5 Sentiment Strategies**

**Fichiers :** `cryptobot/strategy/sentiment_reddit.py`, `cryptobot/strategy/sentiment_twitter.py`

**Fonctionnalités :**
- ✅ **Scraper Reddit** (`cryptobot/web/reddit.py` existe déjà)
- ✅ **Scraper Twitter/X** (`cryptobot/web/twitter.py` existe déjà)
- ✅ **Analyse sentiment** (positive/negative/neutral score)
- ✅ **Signal trading** si sentiment extrême (bullish/bearish)

**Utiliser LLM pour analyser sentiment** (plus efficace que modèle simple)

```python
class SentimentStrategy:
    def analyze_sentiment(self, posts: List[str]) -> Dict:
        """LLM analyzes sentiment, returns score -1.0 to 1.0"""
        prompt = f"Analyze crypto sentiment from these posts: {posts}\nOutput JSON: {{'score': -1.0 to 1.0, 'confidence': 0.0-1.0}}"
        return self.llm.call(prompt)
```

---

## 5️⃣ Data Aggregation & Context Building

### **5.1 Market Context Aggregator**

**Fichier :** `cryptobot/data/context_aggregator.py`

**Fonctionnalités :**
- ✅ **Agrège toutes les données** nécessaires pour LLM
- ✅ **Format optimisé** pour prompts
- ✅ **Cache** pour éviter appels API redondants

```python
class MarketContextAggregator:
    def build_context(
        self,
        symbols: List[str],
        include_sentiment: bool = True,
        include_orderbook: bool = False
    ) -> Dict:
        """Build comprehensive market context for LLM"""
        return {
            "prices": self._get_prices(symbols),
            "volumes": self._get_volumes(symbols),
            "funding_rates": self._get_funding_rates(symbols),
            "orderbook_depths": self._get_orderbooks(symbols) if include_orderbook else {},
            "sentiment": self._get_sentiment() if include_sentiment else {},
            "new_listings": self._get_new_listings(),
            "portfolio": self._get_portfolio_state()
        }
```

---

## 6️⃣ Risk Management Adaptatif

### **6.1 LLM Risk Manager**

**Fichier :** `cryptobot/broker/llm_risk.py`

**Fonctionnalités :**
- ✅ **LLM décide risk tolerance** basé sur performance récente
- ✅ **Ajuste position sizes** dynamiquement
- ✅ **Adapte stop-loss** selon volatilité

```python
class LLMRiskManager:
    def calculate_position_size(
        self,
        strategy: str,
        opportunity: Dict,
        confidence: float,
        market_volatility: float
    ) -> float:
        """LLM decides position size based on risk/return"""
        context = {
            "strategy": strategy,
            "opportunity": opportunity,
            "confidence": confidence,
            "volatility": market_volatility,
            "portfolio": self.get_portfolio_state()
        }
        prompt = f"Calculate optimal position size (USD): {context}\nOutput: {{'size_usd': XXXX.XX}}"
        decision = self.llm.call(prompt)
        return decision["size_usd"]
```

---

## 7️⃣ Execution Engine

### **7.1 Multi-Strategy Executor**

**Fichier :** `cryptobot/broker/executor.py`

**Fonctionnalités :**
- ✅ **Gère plusieurs stratégies en parallèle**
- ✅ **Capital allocation** selon poids LLM
- ✅ **Priorité des trades** (arbitrage > market making > momentum > sniping)
- ✅ **Circuit breaker** (stop si drawdown > limite)

```python
class MultiStrategyExecutor:
    def execute_strategy(self, strategy_name: str, decision: Dict, weights: StrategyWeight):
        """Execute trade for specific strategy"""
        allocated_capital = self.portfolio.total_capital * getattr(weights, strategy_name)
        
        # Execute with allocated capital
        self.broker.place_order(
            symbol=decision["symbol"],
            side=decision["direction"],
            size_usd=min(decision["size_usd"], allocated_capital),
            leverage=decision["leverage"],
            stop_loss=decision.get("stop_loss_pct"),
            take_profit=decision.get("take_profit_pct")
        )
```

---

## 8️⃣ Performance Tracking & Learning Loop

### **8.1 Performance Tracker**

**Fichier :** `cryptobot/monitor/performance.py`

**Fonctionnalités :**
- ✅ **Track PnL par stratégie**
- ✅ **Track ROI, Sharpe ratio, max drawdown**
- ✅ **Feed back to LLM** pour ajustement

**Structure :**
```python
class PerformanceTracker:
    def track_trade(self, strategy: str, entry: float, exit: float, size: float, fees: float):
        """Record trade result"""
        
    def get_strategy_metrics(self, strategy: str, window_hours: int = 24) -> Dict:
        """Calculate metrics for strategy"""
        return {
            "total_pnl": ...,
            "roi_pct": ...,
            "win_rate": ...,
            "avg_win": ...,
            "avg_loss": ...,
            "sharpe_ratio": ...,
            "max_drawdown": ...
        }
    
    def feed_to_llm(self) -> Dict:
        """Build performance summary for LLM learning"""
        return {
            "by_strategy": {
                strat: self.get_strategy_metrics(strat) 
                for strat in ["arbitrage", "sniping", "market_making", ...]
            },
            "overall": self.get_overall_metrics()
        }
```

---

## 9️⃣ Configuration Testnet/Live

### **9.1 Mode Switching**

**Fichier :** `cryptobot/core/mode_manager.py`

**Fonctionnalités :**
- ✅ **Détection automatique** mode (testnet/live depuis config)
- ✅ **Switching sécurisé** (validation avant switch)
- ✅ **Séparation claire** des clés API testnet/live

```python
class ModeManager:
    def __init__(self, config: AppConfig):
        self.testnet = config.broker.testnet
        self.wallet_address = os.getenv("HYPERLIQUID_WALLET_ADDRESS")
        self.private_key = os.getenv(
            "HYPERLIQUID_TESTNET_PRIVATE_KEY" if self.testnet 
            else "HYPERLIQUID_LIVE_PRIVATE_KEY"
        )
        
    def is_testnet(self) -> bool:
        return self.testnet
        
    def get_api_endpoint(self) -> str:
        if self.testnet:
            return "https://api.hyperliquid-testnet.xyz"
        return "https://api.hyperliquid.xyz"
```

---

## 🔟 VPS Kali Optimizations

### **10.1 System Requirements**

- ✅ **Python 3.10+**
- ✅ **Dependencies :** `hyperliquid-python-sdk`, `httpx`, `pandas`, etc.
- ✅ **Service systemd** pour démarrage auto
- ✅ **Log rotation** (logs volumineux)

### **10.2 Service Setup**

**Fichier :** `deploy/cryptobot-hyperliquid.service`

```ini
[Unit]
Description=CryptoBot Hyperliquid Trading Bot
After=network.target

[Service]
Type=simple
User=cryptobot
WorkingDirectory=/opt/cryptobot
Environment="PYTHONPATH=/opt/cryptobot"
EnvironmentFile=/opt/cryptobot/.env
ExecStart=/usr/bin/python3 -m cryptobot.cli.live --config configs/live.hyperliquid.yaml --provider hyperliquid
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### **10.3 Monitoring**

**Script :** `scripts/monitor.sh`

```bash
#!/bin/bash
# Monitor bot health, restart if crashed, alert on errors
```

---

## 1️⃣1️⃣ Main Loop Architecture

### **11.1 Live Runner Enhanced**

**Fichier :** `cryptobot/cli/live_hyperliquid.py` (nouveau)

**Structure :**
```python
def main():
    # Load config
    cfg = AppConfig.load("configs/live.hyperliquid.yaml")
    
    # Initialize components
    mode_manager = ModeManager(cfg)
    broker = HyperliquidBroker(
        wallet_address=mode_manager.wallet_address,
        private_key=mode_manager.private_key,
        testnet=mode_manager.is_testnet()
    )
    
    llm_client = LLMClient.from_env()
    orchestrator = LLMOrchestrator(llm_client)
    weight_manager = WeightManager()
    
    # Strategy instances
    strategies = {
        "arbitrage": ArbitrageStrategy(broker),
        "sniping": SnipingStrategy(broker),
        "market_making": MarketMakingStrategy(broker),
        "momentum": MomentumStrategy(broker),
        "sentiment_reddit": SentimentStrategy(broker, source="reddit"),
        "sentiment_twitter": SentimentStrategy(broker, source="twitter")
    }
    
    executor = MultiStrategyExecutor(broker, orchestrator)
    performance_tracker = PerformanceTracker()
    context_aggregator = MarketContextAggregator(broker)
    
    # Main loop
    while True:
        try:
            # 1. Gather market context
            context = context_aggregator.build_context(
                symbols=cfg.general.symbols,
                include_sentiment=True,
                include_orderbook=True
            )
            
            # 2. LLM decides strategy weights
            weights = orchestrator.decide_strategy_allocation(
                market_data=context["market"],
                portfolio_state=context["portfolio"],
                sentiment_data=context["sentiment"],
                performance_metrics=performance_tracker.feed_to_llm()
            )
            
            # 3. Update weight manager
            weight_manager.weights = weights
            
            # 4. For each strategy (based on weights)
            for strategy_name, strategy_instance in strategies.items():
                weight = getattr(weights, strategy_name)
                if weight < 0.05:  # Skip if weight too low
                    continue
                
                # Detect opportunities
                opportunities = strategy_instance.detect_opportunities(context)
                
                for opportunity in opportunities:
                    # LLM decides on this specific trade
                    decision = orchestrator.decide_trade(
                        strategy_name=strategy_name,
                        opportunity=opportunity,
                        market_context=context
                    )
                    
                    if decision.get("execute") and decision.get("confidence", 0) > 0.7:
                        # Execute
                        executor.execute_strategy(strategy_name, decision, weights)
                        
                        # Track
                        performance_tracker.record_trade_start(
                            strategy=strategy_name,
                            entry_price=opportunity["price"],
                            size=decision["size_usd"]
                        )
            
            # 5. Update performance tracking
            performance_tracker.update_positions(broker.get_portfolio())
            
            # 6. Sleep
            time.sleep(cfg.llm.decision_interval_sec)
            
        except Exception as e:
            log.error(f"Error in main loop: {e}")
            time.sleep(10)
```

---

## 1️⃣2️⃣ Variables d'Environnement

**Fichier :** `.env.hyperliquid.example`

```bash
# Hyperliquid
HYPERLIQUID_WALLET_ADDRESS=0x...
HYPERLIQUID_TESTNET_PRIVATE_KEY=0x...  # For testnet
HYPERLIQUID_LIVE_PRIVATE_KEY=0x...     # For live (NEVER COMMIT!)

# DeepSeek LLM
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

# Optional: Other exchange APIs for arbitrage
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
OKX_API_KEY=...
OKX_API_SECRET=...

# Reddit API (for sentiment)
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=...

# Twitter API (for sentiment)
TWITTER_BEARER_TOKEN=...
```

---

## 1️⃣3️⃣ Checklist Implémentation

### **Phase 1 : Foundation**
- [ ] Créer `hyperliquid_broker.py` avec support testnet/live
- [ ] Créer `hyperliquid_live.py` pour data streaming
- [ ] Créer `live.hyperliquid.yaml` config
- [ ] Setup variables `.env`

### **Phase 2 : LLM System**
- [ ] Créer `orchestrator.py` (pondération stratégies)
- [ ] Créer `prompts.py` (templates optimisés)
- [ ] Modifier `llm/client.py` (ajouter `call()` générique)
- [ ] Tester prompts avec DeepSeek

### **Phase 3 : Strategies**
- [ ] Créer `arbitrage.py`
- [ ] Créer `sniping.py`
- [ ] Créer `market_making.py`
- [ ] Créer `momentum.py`
- [ ] Améliorer `sentiment_reddit.py` et `sentiment_twitter.py`

### **Phase 4 : Execution & Risk**
- [ ] Créer `weight_manager.py`
- [ ] Créer `executor.py`
- [ ] Créer `llm_risk.py`
- [ ] Créer `performance.py`

### **Phase 5 : Integration**
- [ ] Créer `context_aggregator.py`
- [ ] Créer `live_hyperliquid.py` (main loop)
- [ ] Créer `mode_manager.py`

### **Phase 6 : Testing**
- [ ] Tester sur testnet Hyperliquid
- [ ] Valider chaque stratégie individuellement
- [ ] Tester pondération dynamique
- [ ] Tester learning loop

### **Phase 7 : Deployment**
- [ ] Setup VPS Kali
- [ ] Install dependencies
- [ ] Configurer service systemd
- [ ] Monitoring setup
- [ ] Tester en live avec petit montant (100-500$)

---

## 1️⃣4️⃣ Suggestions Additionnelles (Optimisations)

### **14.1 Prompt Engineering Optimizations**

- ✅ **Few-shot examples** : Ajouter exemples réussis dans prompts
- ✅ **Chain-of-thought** : Forcer LLM à expliquer raisonnement
- ✅ **Temperature adaptatif** : Plus bas (0.1) pour décisions critiques, plus haut (0.3) pour créativité
- ✅ **Prompt compression** : Utiliser DeepSeek pour compresser contexte avant envoi au LLM principal

### **14.2 Performance Optimizations**

- ✅ **Caching LLM calls** : Cache réponses pour contextes similaires (éviter coûts)
- ✅ **Batch processing** : Grouper plusieurs décisions en un appel LLM
- ✅ **Async execution** : Paralléliser appels API (Hyperliquid, sentiment scrapers)
- ✅ **Connection pooling** : Réutiliser connexions HTTP/WebSocket

### **14.3 Risk Management Enhancements**

- ✅ **Circuit breakers** : Auto-stop si drawdown > X% ou erreurs > Y
- ✅ **Position limits** : Limite max par stratégie (éviter concentration)
- ✅ **Volatility-based sizing** : Réduire taille en haute volatilité
- ✅ **Correlation tracking** : Éviter stratégies corrélées simultanément

### **14.4 Strategy Enhancements**

- ✅ **Funding rate arbitrage** : Exploiter funding rates négatifs/positifs
- ✅ **Cross-exchange triangular arbitrage** : BTC/ETH sur Hyperliquid vs ETH/USDT vs BTC/USDT ailleurs
- ✅ **Liquidation sniping** : Monitor positions proches liquidation, snip juste avant
- ✅ **Flash loan arbitrage** : Si supporté par Hyperliquid

### **14.5 Learning & Adaptation**

- ✅ **A/B testing** : Tester nouvelles pondérations en parallèle (10% capital)
- ✅ **Reinforcement learning** : Framework RL pour optimiser pondérations (optionnel, avancé)
- ✅ **Backtesting** : Rejouer stratégies sur données historiques avant activation
- ✅ **Performance attribution** : Analyser quelles stratégies contribuent le plus aux profits

### **14.6 Monitoring & Alerts**

- ✅ **Telegram/Discord alerts** : Notifications trades importants, erreurs, profits
- ✅ **Dashboard web** : Interface pour voir performance en temps réel
- ✅ **Logs structurés** : JSON logs pour analyse facile
- ✅ **Metrics export** : Prometheus/Grafana pour visualisation

### **14.7 Capital Efficiency**

- ✅ **Portfolio margining** : Optimiser utilisation marge entre stratégies
- ✅ **Partial fills handling** : Gérer ordres partiellement exécutés
- ✅ **Funding rate optimization** : Éviter payer funding en prenant positions qui en reçoivent
- ✅ **Gas optimization** : Minimiser transactions on-chain (Hyperliquid est déjà optimisé)

### **14.8 Advanced Features**

- ✅ **Multi-symbol correlation** : Trader paires corrélées simultanément
- ✅ **Options trading** : Si Hyperliquid ajoute options (futur)
- ✅ **Social signals aggregation** : Combiner Reddit + Twitter + Discord + Telegram
- ✅ **News sentiment** : Intégrer analyse news crypto (RSS feeds, API)

### **14.9 Security Enhancements**

- ✅ **Key encryption** : Chiffrer clés privées au repos
- ✅ **Rate limiting** : Limiter appels API (éviter bans)
- ✅ **IP whitelisting** : Whitelist IP VPS sur Hyperliquid
- ✅ **Backup strategy** : Backup configuration et clés régulièrement

### **14.10 Cost Optimization**

- ✅ **LLM call batching** : Réduire nombre appels DeepSeek (coûts)
- ✅ **Token optimization** : Compresser contexte envoyé à LLM
- ✅ **Strategy prioritization** : Focus sur stratégies les plus rentables (réduire nombre)
- ✅ **Sleep optimization** : Adapter fréquence décisions selon activité marché

---

## 1️⃣5️⃣ Priorités d'Implémentation

### **MVP (Minimum Viable Product)**
1. ✅ Hyperliquid broker (testnet/live)
2. ✅ LLM orchestrator basique
3. ✅ 2 stratégies (market making + arbitrage)
4. ✅ Pondération statique (pas encore dynamique)
5. ✅ Main loop basique

### **Version 1.0**
1. ✅ Toutes les stratégies implémentées
2. ✅ Pondération dynamique
3. ✅ Performance tracking
4. ✅ Risk management LLM-driven

### **Version 2.0**
1. ✅ Toutes les optimisations suggérées
2. ✅ Advanced features
3. ✅ Monitoring dashboard
4. ✅ Backtesting framework

---

## 🎯 Objectif Final

**Système 100% LLM-driven qui :**
- ✅ Maximise les profits le plus rapidement possible
- ✅ S'adapte dynamiquement aux conditions de marché
- ✅ Apprend de ses performances passées
- ✅ Gère le risque intelligemment
- ✅ Fonctionne 24/7 sur VPS Kali
- ✅ Supporte testnet ET live

---

**Document prêt pour GPT-5 High. Commencez par Phase 1 (Foundation), puis progressivement jusqu'à Version 2.0. 💰**

