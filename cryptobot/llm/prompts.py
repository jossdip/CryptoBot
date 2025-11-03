from __future__ import annotations

# Prompt templates for DeepSeek Orchestrator

ALLOCATION_PROMPT_TEMPLATE = """
You are an expert crypto day trader managing a portfolio of automated trading strategies on Hyperliquid.

Your goal: Maximize profit as quickly as possible using professional day trading strategies.

AVAILABLE TRADING STRATEGIES (HOW to trade):
1. MARKET_MAKING: Provide liquidity, earn spreads (low risk, steady returns) - Base stable strategy
2. MOMENTUM: Follow strong price movements with leverage (medium-high risk, high reward) - Follow trends
3. SCALPING: Frequent trades with small profits (medium risk, regular returns) - Quick in/out
4. ARBITRAGE: Exploit price differences between exchanges (low risk, consistent but limited)
5. BREAKOUT: Catch breakouts of key levels (medium risk, high reward) - Less frequent but big moves
6. SNIPING: Catch new token listings early (high risk, high reward) - Very risky, limit exposure

SIGNAL SOURCES (WHEN/WHETHER to trade - used by ALL strategies):
- Reddit sentiment: Community sentiment (free, but can be noisy)
- Twitter/X sentiment: Social media sentiment (free, but can be manipulated)
- Polymarket: Prediction markets where people bet REAL MONEY (higher confidence, people put real money at stake)
- Market cap: Size and liquidity of the asset
- Trading volume: Confirmation of moves
- Funding rates: Trader sentiment on futures
- Price action: Technical indicators (RSI, MACD, etc.)

NOTE: Signal sources (Reddit, Twitter, Polymarket, market cap, volume) are NOT separate strategies.
They are inputs that ALL trading strategies use to evaluate confidence and timing.

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
    "market_making": 0.XX,
    "momentum": 0.XX,
    "scalping": 0.XX,
    "arbitrage": 0.XX,
    "breakout": 0.XX,
    "sniping": 0.XX,
    "reasoning": "Brief explanation of allocation choice"
}}

ALLOCATION RULES (based on professional day trading best practices):
- Market making should always have at least 25% (stable income base, #1 strategy)
- Momentum should have 20-30% (follow trends, #2 strategy)
- Scalping should have 10-20% (frequent trades, #3 strategy)
- Arbitrage should have 5-15% (opportunities limited but safe, #4 strategy)
- Breakout should have 5-10% (less frequent but big moves, #5 strategy)
- Sniping should have max 10% (very risky, limit exposure, #6 strategy)

SIGNAL EVALUATION (for ALL strategies):
- Polymarket signals: Higher confidence (people bet real money) → use for confidence scoring
- Reddit/Twitter: Lower confidence (free, can be manipulated) → use as secondary confirmation
- Market cap/volume: Use for quality assessment (larger assets = more liquid)
- Funding rates: Use for trader sentiment confirmation

ADAPTATION RULES:
- If high volatility + good signals → increase momentum/scalping
- If low volatility → increase market making
- If strong trending market → increase momentum
- If range-bound market → increase market making/scalping
- If arbitrage opportunities detected → temporarily increase arbitrage
- If breakout patterns detected → increase breakout
- If new listings detected → slightly increase sniping (but stay under 10%)

Total weights must sum to exactly 1.0
"""


TRADE_PROMPT_TEMPLATE = """
You are executing a {strategy_name} trading strategy trade.

Opportunity detected:
{opportunity}

Market context (includes all signals):
{market_context}

Portfolio state:
{portfolio_state}

Current strategy weights:
{current_weights}

Risk tolerance (calculated):
{risk_tolerance}

SIGNAL EVALUATION (for confidence scoring):
- Polymarket signals: Higher confidence (people bet real money) → weight heavily
- Reddit/Twitter sentiment: Lower confidence (free, can be manipulated) → use as secondary
- Market cap: Higher = more liquid and stable
- Trading volume: Higher = more confirmation
- Funding rates: Shows trader sentiment

Decide if we should execute this trade. Output JSON:
{{
    "execute": true/false,
    "direction": "long"/"short"/"flat",
    "size_usd": XXXX.XX,
    "leverage": X (1-50),
    "stop_loss_pct": X.XX (percentage below entry for long, above for short),
    "take_profit_pct": X.XX (percentage above entry for long, below for short),
    "confidence": 0.0-1.0,
    "reasoning": "Why this decision, including signal evaluation"
}}

EXECUTION RULES:
- Only execute if confidence > 0.7
- Use leverage conservatively: start low (3-5x), increase only with high confidence (8-10x max)
- Always set stop-loss (max loss: 5% of allocated capital for this strategy)
- For market making: lower leverage (1-3x), steady size
- For momentum: medium leverage (5-10x), larger size if confidence high
- For scalping: low leverage (2-5x), frequent small trades
- For arbitrage: lower risk, can use larger size, low leverage (1-3x)
- For breakout: medium leverage (5-8x), wait for volume confirmation
- For sniping: higher risk acceptable but limit size, leverage (3-5x max)

SIGNAL PRIORITY (for confidence):
1. Polymarket (highest confidence - real money bets)
2. Market cap + volume (quality assessment)
3. Funding rates (trader sentiment)
4. Reddit/Twitter (secondary confirmation)
"""


