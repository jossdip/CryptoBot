# CryptoBot

Modular, scalable crypto day-trading bot inspired by nof1.ai. Starts with a simple, reproducible paper-trading baseline and grows into an ensemble with arbitrage, halving-bias, sniping, and optional LLM risk overlay.

## Quickstart

1. Create a virtualenv and install deps
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

2. Copy env and config
```bash
cp .env.example .env
cp configs/paper.sample.yaml configs/run.yaml
```

3. Run paper trading/backtest
```bash
python -m cryptobot.cli.run --config configs/run.yaml
```

## Features (phase 1)
- Random-walk market generator for deterministic paper-trading
- Paper broker with fees, slippage, portfolio and risk limits
- nof1-style baseline intraday strategy (EMA + RSI gating + volatility filter)
- Backtest engine and basic report (CAGR, Sharpe, MaxDD, hit rate)
- Config-driven; modular strategies and data providers

## Roadmap (phase 2+)
- Arbitrage, halving bias, sniping strategy modules
- Weighted ensemble with capital allocation
- Optional LLM risk overlay (DeepSeek/Qwen adapters)
- Web crawling for sentiment (Twitter, Reddit, Polymarket)

## Project structure
```
cryptobot/
  core/          # types, config, logging, utils
  data/          # providers (random_walk, exchange in future)
  broker/        # paper execution, portfolio, risk
  strategy/      # strategies: base, nof1, stubs
  llm/           # risk overlay adapters
  web/           # crawlers stubs
  backtest/      # engine and reporting
  cli/           # entrypoint
configs/
logs/ context/ decisions/ strategy/
```

## Disclaimers
This software is for research and paper-trading only. No financial advice. Use at your own risk.
