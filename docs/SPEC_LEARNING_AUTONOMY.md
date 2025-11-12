# SPEC — Learning System (Online Adaptation, Memory, BO, RL) for CryptoBot

Status: Draft for immediate implementation
Owner: GPT‑5 (Cursor)
Date: 2025‑11‑11
Scope: Live Hyperliquid mode (`cryptobot/cli/live_hyperliquid.py`) with LLM orchestration


## 1) Goal
Add an online learning layer that:
- Learns from each trade’s outcome (PnL/risk) to improve future decisions.
- Adapts strategy allocation and per‑strategy hyper‑parameters in real‑time.
- Enriches LLM prompts with a compact, relevant memory of similar past contexts.
- Provides an offline RL path to pretrain a policy for live blending.

Non‑goals: Do not remove existing LLM orchestration; learning runs hybrid with hard safety constraints.


## 2) High‑Level Architecture
- Memory module (episodes): persist decision context, action, and realized reward; expose kNN retrieval.
- Bandits:
  - Strategy Allocation Bandit (multi‑armed, Thompson Sampling) → weights by recent rewards.
  - Per‑strategy Param Bandit (contextual UCB/TS on discrete grids) for leverage, TP/SL, min_conf.
- Bayesian Optimization (BO) (optional): continuous tuning for a small set of parameters (later phase).
- RL (offline): PPO/SAC policy pretraining on backtest engine; live blending with LLM and bandits.
- Safety layer (“policy shield”): hard caps for leverage, sizing, min SL, circuit breaker, confidence gates.


## 3) Config Toggles (to add in `configs/live.hyperliquid.yaml`)
```yaml
learning:
  enabled: true
  # Allocation: how to combine LLM and Learning
  allocation_mode: hybrid   # {llm_only|bandit_only|hybrid}
  allocation_hybrid_blend: 0.5  # 0..1, fraction from bandit (rest from LLM)

  # Param tuning per strategy
  param_mode: bandit        # {static|bandit|bo}

  # Memory (episodes)
  memory:
    enabled: true
    knn_k: 8
    max_episodes: 50000
    embedder: "sbert-mini"  # {none|sbert-mini|openai-text-ada} — implement none + sbert-mini; others optional

  # Bandits
  bandits:
    update_cadence_sec: 60
    reward_cvar_alpha: 0.2     # CVaR alpha to penalize tail risk
    reward_scale: 1.0          # global scaling for stability
    per_strategy:
      default:
        leverage_grid: [2,4,6,8,10]
        tp_grid_pct: [0.006,0.008,0.010,0.012,0.015]
        sl_grid_pct: [0.004,0.005,0.006,0.008,0.010]
        min_conf_grid: [0.50,0.55,0.60,0.65,0.70]
      momentum:
        leverage_grid: [6,10,14,18,20]
      breakout:
        leverage_grid: [6,10,14,18,20]
      scalping:
        leverage_grid: [4,8,10,12]
      sniping:
        leverage_grid: [8,12,16,20,25]

  # Bayesian Optimization (Phase 2)
  bo:
    enabled: false
    min_samples: 100
    update_cadence_sec: 180

  # RL (Phase 3)
  rl:
    enabled: false
    policy_path: "models/policy_rl.pt"
    blend_weight: 0.25  # contribution of RL vs LLM in hybrid policy
```


## 4) Data Model (SQLite — extend `cryptobot/monitor/storage.py`)
Add tables:
- `episodes(id, timestamp, strategy, symbol, features_json, decision_json, outcome_json)`
  - `features_json`: compact dict of numeric features at decision time
  - `decision_json`: chosen action (direction, leverage, tp/sl/min_conf, size)
  - `outcome_json`: realized PnL, horizon used, risk metrics (drawdown proxy)
- `episode_embeddings(episode_id, vector BLOB)`
  - Optional if `embedder=none`; otherwise store float32 vector for kNN cosine.

Indexes:
- `episodes(timestamp)`; `episodes(strategy)`; `episode_embeddings(episode_id)`.


## 5) Features (to extract at decision time)
Use only numeric, stable features available today:
- Prices: median price, price_change_pct (1m), volatility (1m window), spread (if available).
- Sentiment: reddit/twitter/polymarket scores and confidence (0..1).
- Funding rate.
- Orderbook snapshot: top‑1 bid/ask and depth sums (if available).
- Portfolio signal: current leverage for the symbol, unrealized pnl (best‑effort).
- Strategy weight snapshot (current LLM weights) for context.

Define a deterministic ordering → feature vector `List[float]`. Persist the dict too for auditability.


## 6) Modules to Create

### 6.1 `cryptobot/learn/memory.py`
- `Episode` dataclass: features: Dict[str, float], decision: Dict[str, Any], outcome: Dict[str, Any].
- `EpisodeStore`:
  - `add_episode(episode: Episode) -> None`
  - `query_recent(limit: int) -> List[Episode]`
  - `knn(features: Dict[str, float], k: int) -> List[Tuple[Episode, float]]` (cosine sim; fallback to numeric features if no embeddings)
- Embeddings:
  - If `embedder=none`: normalize numeric vector, cosine on CPU.
  - If `embedder=sbert-mini`: optional `sentence-transformers` small model; build an input string from features (key:value); cache and store vector.
  - Implement robust fallbacks (no network / no model → use numeric).

### 6.2 `cryptobot/learn/bandits.py`
- `StrategyAllocationBandit`:
  - Arms = strategies: market_making, momentum, scalping, arbitrage, breakout, sniping.
  - Maintain per‑arm Beta or Gaussian posterior (TS). Reward = CVaR‑penalized PnL (see §7).
  - API:
    - `propose_weights() -> Dict[str,float]` (softmax of samples; normalize; clamp to [0.0, 1.0])
    - `update(strategy: str, reward: float) -> None`

- `ParamBandit` (per strategy):
  - Discrete action grid (from config). Contextual variant: map features→bucket (e.g., volatility and sentiment binned), maintain separate stats per bucket.
  - API:
    - `propose(strategy: str, features: Dict[str,float]) -> Dict[str, Any]` (lev, tp, sl, min_conf)
    - `update(strategy: str, features, reward) -> None`


### 6.3 `cryptobot/learn/bo.py` (Phase 2, optional)
- Minimal Bayesian optimizer on a few continuous params: `tp_pct`, `sl_pct`, `limit_offset_pct`.
- Heuristic TPE/GP‑like: keep best N samples per bucket of features; propose around elites (no heavy deps).
- API:
  - `suggest(strategy, features) -> Dict[str, float]`
  - `update(strategy, features, reward) -> None`


### 6.4 `cryptobot/learn/env.py` + `scripts/train_rl.py` (Phase 3)
- Gym‑like env wrapping `backtest.engine`:
  - Observation = standardized features (same as episodes).
  - Action = {execute?, direction, leverage, tp, sl}.
  - Reward = PnL − risk_penalty (fees/slippage included), clipped.
- Training script (`stable-baselines3` if available; else placeholder interface).
- Save policy to `models/policy_rl.pt` and provide `Policy` class with `predict(obs)`.


## 7) Reward Shaping (risk‑aware)
Let raw PnL = (exit−entry)*size − fees.
- Scale: `reward = PnL * reward_scale`.
- CVaR penalty (alpha from config): maintain rolling distribution; subtract an estimate of tail losses.
- Drawdown penalty: subtract term proportional à recent DD proxy.
Clip rewards to a sensible range to stabilize TS/UCB.


## 8) Integration Points in `cryptobot/cli/live_hyperliquid.py`
1) Bootstrap (after orchestrator/weight_manager instantiation):
   - Construct `EpisodeStore`, `StrategyAllocationBandit`, `ParamBandit`, optional `BO`.
   - Read config `learning.*` and wire modes.

2) Before LLM trade decision (per opportunity):
   - If `learning.memory.enabled`: query kNN with current features; summarize top‑k as “similar contexts” to enrich LLM prompt (append to `market_context` under `learning_memory`).

3) Strategy allocation per loop:
   - If `learning.enabled`:
     - Compute bandit weights via `propose_weights()`.
     - Blend with LLM weights depending on `allocation_mode`:
       - `llm_only`: keep LLM.
       - `bandit_only`: use bandit.
       - `hybrid`: `w = blend*bandit + (1−blend)*LLM`, then normalize.
     - Persist new weights to monitor storage (existing mechanism).

4) Param suggestion (after LLM decision, before execution):
   - If `param_mode=bandit|bo`: request suggested `{leverage,tp_pct,sl_pct,min_conf}` from learner; combine with LLM outputs (LLM overrides only if stricter risk? or take max/min based on safety).
   - Apply safety shield: clamp leverage ≤ cfg, enforce `sl_pct ≥ floor`, ensure `min_conf ≥ global_min`.

5) After execution and maturation:
   - On matured pending evaluation: compute reward with §7; record an `Episode` (features, decision, outcome).
   - `allocation_bandit.update(strategy, reward)`.
   - `param_bandit.update(strategy, features, reward)` (and `bo.update` if enabled).

6) Storage:
   - Add write paths in `cryptobot/monitor/storage.py`: `record_episode(...)`, `query_episodes(...)`, `record_embedding(...)`, `get_knn(...)` (simple CPU cosine or SQL + Python loop).


## 9) Safety Constraints (must enforce after any learning suggestion)
- Respect `broker.max_leverage`, `risk.max_position_pct`.
- Enforce `min_conf >= 0.50` (or dynamic threshold already implemented, whichever is stricter).
- Enforce `sl_pct >= 0.004` (0.4%) for directionals (configurable).
- Circuit breaker: keep current DD gate and LLM confidence gating; learning cannot bypass them.
- If any component fails (exceptions, empty memory), degrade gracefully to pure LLM.


## 10) Minimal Dependencies and Fallbacks
- Use stdlib + numpy. Avoid heavy network/model downloads by default.
- Embedding: default to `embedder=none`. Implement SBERT only if available; else skip.
- BO: implement lightweight heuristic first; avoid `scikit-optimize` dependency unless present.
- RL: implement interface stubs; actual training script can be optional.

If any optional dependency is missing, log a warning and proceed with available functionality.


## 11) Acceptance Criteria
- When `learning.enabled=true` in hybrid mode:
  - Strategy weights drift measurably toward higher‑reward strategies over 50+ trades in a dry‑run simulation (unit testable via synthetic rewards).
  - ParamBandit converges to more profitable discrete params on a synthetic environment.
  - kNN memory enriches prompts (presence of `learning_memory` keys) without breaking existing LLM calls.
  - No regression: with `learning.enabled=false`, behavior identical to current live path.
- Safety: no suggestion violates leverage/size/SL minima; circuit breaker remains effective.
- Storage: new tables created; episodes accumulated; query functions return expected counts.


## 12) Test Plan
- Unit:
  - Memory: feature vectorization stable ordering; kNN returns closest by cosine.
  - Bandit: TS posterior update; monotone reaction to positive/negative rewards.
  - ParamBandit: converges to winning arm on stationary reward simulation.
  - Storage: roundtrip episode write/read; schema integrity.
- Integration (no network):
  - Simulate decisions and matured rewards; verify weights shift and params suggested by bandit affect next proposals.
  - Toggle modes `llm_only|bandit_only|hybrid` and `static|bandit` param paths.
- E2E (optional):
  - Dry‑run live loop with mock broker and mock prices; ensure learning calls do not block or crash.


## 13) Implementation Tasks (ordered)
1) Config: add `learning` block (see §3). Make defaults non‑intrusive (enabled but hybrid_blend small, or ship disabled by default if preferred).
2) Storage: extend `cryptobot/monitor/storage.py` with episodes and embeddings tables + CRUD.
3) Memory: implement `cryptobot/learn/memory.py` (numeric cosine first; stub embedder).
4) Bandits: implement `cryptobot/learn/bandits.py` (allocation and param bandits).
5) Integration: wire into `cryptobot/cli/live_hyperliquid.py` at points (§8), guarded by config flags.
6) Tests: unit tests for memory/bandits/storage; integration test for weight drift under synthetic rewards.
7) (Phase 2) BO: minimal heuristic module + integration when `param_mode=bo`.
8) (Phase 3) RL: create env + training script stubs; no live dependency unless `learning.rl.enabled`.
9) Docs: update `decisions/README.md` with a short summary and reference to this spec.


## 14) Rollout
- Step 1: Ship in SHADOW mode (learning collects data; no effect on execution).
- Step 2: Enable HYBRID with `allocation_hybrid_blend=0.3`, `param_mode=bandit`.
- Step 3: Increase blend if stable; optionally enable BO/RL later.


## 15) Notes
- All learning outputs are advisory; the execution shield applies last.
- Keep logs explicit for auditability; record version and config snapshot alongside episodes.


