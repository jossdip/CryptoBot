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

## Live futures paper (with optional testnet mirroring)

1. Configure env (DeepSeek optional, exchange keys optional for testnet)
```bash
export LLM_API_KEY=...            # optional DeepSeek
export LLM_BASE_URL=https://api.deepseek.com/v1
export LLM_MODEL=deepseek-chat

export EXCHANGE_API_KEY=...       # optional for testnet mirroring
export EXCHANGE_API_SECRET=...
```

2. Use the frugal live config (20 USDT, futures, isolated, leverage chosen by LLM)
```bash
python -m cryptobot.cli.live --config configs/live.frugal.yaml --provider ccxt
```

Notes:
- `general.market_type: futures` uses `binanceusdm` by default; set `general.exchange_id` to change.
- Orders are simulated in the paper broker; when `broker.place_on_testnet: true` and keys are set, market orders are also mirrored to the exchange testnet for realism.
- The LLM strategy decides direction (long/short/flat) and recommended leverage; risk and sizing remain capped by `risk.max_position_pct` and small capital.

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

## Trading en France - Solution Légal

**Problème :** Les exchanges comme Binance/Bybit/MEXC bloquent les futures pour les résidents français.

**Solution :** Utilisez Deribit (accepte les Français, trading 24/7, retrait bancaire simple).

**Guides disponibles :**
- 📋 **`RESUME_SOLUTION.md`** → Résumé ultra-simple (3 étapes)
- 📖 **`GUIDE_SOLUTION_FRANCE.md`** → Explication complète de toutes les solutions
- 🔧 **`GUIDE_DERIBIT_SETUP.md`** → Guide pratique étape par étape pour configurer Deribit
- ⚙️ **`configs/live.deribit.yaml`** → Configuration prête pour Deribit

**Démarrage rapide avec Deribit :**
1. Ouvrez un compte sur https://www.deribit.com/ (KYC requis, gratuit)
2. Créez une clé API (Account → API)
3. Mettez vos clés dans `.env` :
   ```
   EXCHANGE_API_KEY=votre_cle_deribit
   EXCHANGE_API_SECRET=votre_secret_deribit
   ```
4. Lancez : `python -m cryptobot.cli.live --config configs/live.deribit.yaml --provider ccxt`

**Important :** Déclarez vos gains aux impôts français (revenus de capitaux mobiliers).

## Disclaimers
This software is for research and paper-trading only. No financial advice. Use at your own risk.
