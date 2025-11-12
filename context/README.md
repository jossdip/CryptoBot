# Context

Rolling summary of project state, tasks in progress, and resources.

This directory is updated as part of Hyperliquid integration and LLM-driven orchestration work.

## 2025-11-11 — Current state

- Hyperliquid live trading path hardened:
  - SDK call retries with backoff for transient errors.
  - Correct chain selection (TESTNET/MAINNET) in `Info` client to match runtime mode.
  - Order flow robust across SDK variants; limit degrades to market when necessary.
  - Size/price quantization prevents float-to-wire rounding issues.
- CLI runner (`cryptobot/cli/live_hyperliquid.py`) validates presence of keys, initializes broker, and records heartbeats/monitoring.

Next steps (optional):
- Integrate real-time WS market data in `cryptobot/data/hyperliquid_live.py` (currently synthetic fallback).
- Expand monitoring of order statuses/fills via SDK stream if/when exposed.

