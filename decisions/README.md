# Decisions

Key architectural and implementation decisions for Hyperliquid integration and LLM orchestration.

## 2025-11-11 — Hyperliquid trading reliability improvements

- Introduced resilient retry wrapper for SDK calls (market_open, order, update_leverage, get_funding_rate) with conservative exponential backoff on transient network/ratelimit errors.
- Ensured `Info` client is instantiated with the correct chain (TESTNET/MAINNET) tied to runtime mode to avoid cross-network state mismatches.
- Standardized client IDs for orders when not provided by callers for better traceability and idempotency.
- Hardened order placement flow:
  - Market orders prefer `market_open` when available, else `order(..., OrderType.Market)`, else fallback variants.
  - Limit orders prefer `order(..., OrderType.Limit)`; if enum/signature unavailable, degrade to `market_open` to prioritize execution reliability.
  - Added rounding/quantization guards using Info metadata for size and price, with adjust-and-retry on wire rounding errors.
- Portfolio querying selects the best available address (signer vs provided wallet) and now uses explicit chain + base_url for reliability.

Rationale: Aligns with Hyperliquid SDK best practices, reduces intermittent failures, and ensures the bot executes trades reliably in both testnet and mainnet modes without manual intervention.

## 2025-11-11 — PnL-driven strategy tilt with calculated risk

Changes implemented to target higher capital multiples while prioritizing risk control via information density, LLM confidence, and protective mechanics:

- Configuration (configs/live.hyperliquid.yaml):
  - Expanded universe: added `SOL/USD:USD`, `AVAX/USD:USD`, `DOGE/USD:USD`, `LINK/USD:USD`.
  - Strategy weights tilted to directional alpha:
    - market_making 0.05, momentum 0.40, breakout 0.25, scalping 0.20, sniping 0.10, arbitrage 0.05.
  - LLM cadence and gates:
    - decision_interval_sec=30, allocation_interval_sec=60.
    - max_opportunities_per_cycle=12, min_opportunity_score=0.25.
    - min_confidence_to_execute=0.65 (dynamic tuning remains active).
  - Risk:
    - max_position_pct=3.0.
- Live engine (cryptobot/cli/live_hyperliquid.py):
  - Runtime defaults tuned for risk-first execution:
    - min_hold_seconds reduced to 12s for faster lock-in on short-horizon trades.
    - market making passive_order_fraction_of_alloc set to 0.0 by default.
  - Passive maker fallback now strictly disabled unless `passive_order_fraction_of_alloc > 0` in runtime params.
  - Automatic protective brackets when LLM omits them:
    - Defaults per strategy: momentum/breakout (TP 1.0%, SL 0.6%), scalping (TP 0.7%, SL 0.5%), sniping (TP 1.5%, SL 1.0%).
    - Placed as reduce-only where supported.

Rationale: Emphasize high-conviction directional trades driven by richer context and LLM confidence while systematically constraining downside through default brackets, shorter holds, and disabling passive liquidity provision unless explicitly enabled.

## 2025-11-11 — Learning System Specification (Bandits, Memory, BO, RL)

- A detailed implementation spec is available at: `docs/SPEC_LEARNING_AUTONOMY.md`.
- Scope: online adaptation via bandits (allocation + per-strategy params), context memory with kNN prompt enrichment, optional Bayesian optimization for continuous params, and an offline RL path to pretrain a policy for hybrid live use.
- Rollout plan: shadow → hybrid (low blend) → hybrid (higher blend); strict safety constraints remain enforced at execution.

## 2025-11-11 — Learning System Implementation (Phase 1: Memory + Bandits)

- Config: added `learning.*` block to `AppConfig` and `configs/live.hyperliquid.yaml` (default disabled).
- Storage: extended SQLite schema with `episodes` and `episode_embeddings` + CRUD helpers.
- Modules:
  - `cryptobot/learn/memory.py`: `Episode` and `EpisodeStore` with numeric-cosine kNN (SBERT optional, disabled by default).
  - `cryptobot/learn/bandits.py`: `StrategyAllocationBandit` (Gaussian TS-like), `ParamBandit` (per-parameter UCB over discrete grids).
- Integration (`cryptobot/cli/live_hyperliquid.py`):
  - Allocation: optional blend between LLM and bandit weights (`llm_only|bandit_only|hybrid` with blend factor).
  - Memory: kNN of recent episodes enriches LLM market context (`learning_memory.similar_contexts`).
  - Params: per-strategy suggestions for leverage/TP/SL/min_conf with a final safety shield (leverage cap, SL floor).
  - Feedback: matured proxy PnL updates bandits and records episodes.
- Tests: unit tests cover memory kNN, bandits propose/update, and storage roundtrip for episodes.
