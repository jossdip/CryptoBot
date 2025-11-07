from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import time


def _expand(path: str) -> str:
    return os.path.expandvars(os.path.expanduser(path))


class StorageManager:
    """Lightweight SQLite-backed storage for monitoring data.

    Tables:
      - trades
      - portfolio_snapshots
      - llm_decisions
      - performance_metrics
      - weights_history
      - runtime_status (singleton row id=1)
    """

    def __init__(self, db_path: str = "~/.cryptobot/monitor.db") -> None:
        # Allow overriding the monitor DB path via environment to share status across sessions
        env_override = os.getenv("CRYPTOBOT_MONITOR_DB")
        self.db_path = _expand(env_override or db_path)
        Path(os.path.dirname(self.db_path)).mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    strategy TEXT,
                    symbol TEXT,
                    side TEXT,
                    size REAL,
                    entry REAL,
                    exit REAL,
                    pnl REAL,
                    fees REAL,
                    confidence REAL,
                    metadata TEXT
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    timestamp REAL,
                    balance REAL,
                    equity REAL,
                    unrealized_pnl REAL,
                    positions_json TEXT
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_decisions (
                    timestamp REAL,
                    decision_type TEXT,
                    prompt TEXT,
                    response TEXT,
                    reasoning TEXT,
                    sentiment TEXT,
                    confidence REAL,
                    metadata TEXT
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    timestamp REAL,
                    strategy TEXT,
                    pnl REAL,
                    roi REAL,
                    win_rate REAL,
                    sharpe REAL,
                    max_drawdown REAL,
                    metadata TEXT
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS weights_history (
                    timestamp REAL,
                    market_making REAL,
                    momentum REAL,
                    scalping REAL,
                    arbitrage REAL,
                    breakout REAL,
                    sniping REAL
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_status (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    pid INTEGER,
                    status TEXT,
                    started_at REAL,
                    last_heartbeat REAL,
                    desired_stop INTEGER DEFAULT 0,
                    config_path TEXT,
                    testnet INTEGER,
                    wallet_address TEXT
                );
                """
            )
            # Ensure a singleton row exists
            self._conn.execute(
                """
                INSERT OR IGNORE INTO runtime_status (id, status, desired_stop)
                VALUES (1, 'STOPPED', 0)
                """
            )

    def record_trade(
        self,
        *,
        timestamp: float,
        strategy: str,
        symbol: str,
        side: str,
        size: float,
        entry: float,
        exit: float,
        pnl: float,
        fees: float = 0.0,
        confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO trades (timestamp, strategy, symbol, side, size, entry, exit, pnl, fees, confidence, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    float(timestamp),
                    strategy,
                    symbol,
                    side,
                    float(size),
                    float(entry),
                    float(exit),
                    float(pnl),
                    float(fees),
                    float(confidence) if confidence is not None else None,
                    json.dumps(metadata or {}),
                ),
            )

    def record_portfolio_snapshot(
        self,
        *,
        timestamp: float,
        balance: float,
        equity: float,
        unrealized_pnl: float,
        positions: Dict[str, Any],
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO portfolio_snapshots (timestamp, balance, equity, unrealized_pnl, positions_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    float(timestamp),
                    float(balance),
                    float(equity),
                    float(unrealized_pnl),
                    json.dumps(positions or {}),
                ),
            )

    def record_llm_decision(
        self,
        *,
        timestamp: float,
        decision_type: str,
        prompt: str,
        response: str,
        reasoning: str,
        sentiment: str,
        confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO llm_decisions (timestamp, decision_type, prompt, response, reasoning, sentiment, confidence, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    float(timestamp),
                    decision_type,
                    prompt,
                    response,
                    reasoning,
                    sentiment,
                    float(confidence) if confidence is not None else None,
                    json.dumps(metadata or {}),
                ),
            )

    def record_performance_metric(
        self,
        *,
        timestamp: float,
        strategy: str,
        pnl: float,
        roi: float = 0.0,
        win_rate: float = 0.0,
        sharpe: float = 0.0,
        max_drawdown: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO performance_metrics (timestamp, strategy, pnl, roi, win_rate, sharpe, max_drawdown, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    float(timestamp),
                    strategy,
                    float(pnl),
                    float(roi),
                    float(win_rate),
                    float(sharpe),
                    float(max_drawdown),
                    json.dumps(metadata or {}),
                ),
            )

    def record_weights(
        self,
        *,
        timestamp: float,
        weights: Dict[str, float],
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO weights_history (timestamp, market_making, momentum, scalping, arbitrage, breakout, sniping)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    float(timestamp),
                    float(weights.get("market_making", 0.35)),
                    float(weights.get("momentum", 0.25)),
                    float(weights.get("scalping", 0.15)),
                    float(weights.get("arbitrage", 0.12)),
                    float(weights.get("breakout", 0.08)),
                    float(weights.get("sniping", 0.05)),
                ),
            )

    def latest_weights(self) -> Optional[Dict[str, float]]:
        row = self._conn.execute(
            "SELECT market_making, momentum, scalping, arbitrage, breakout, sniping FROM weights_history ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return {
            "market_making": float(row[0]),
            "momentum": float(row[1]),
            "scalping": float(row[2]),
            "arbitrage": float(row[3]),
            "breakout": float(row[4]),
            "sniping": float(row[5]),
        }

    def recent_performance(self, limit: int = 200) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT timestamp, strategy, pnl FROM performance_metrics ORDER BY timestamp DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "timestamp": float(r[0]),
                "strategy": str(r[1]),
                "pnl": float(r[2]),
            })
        return out

    # Query helpers
    def recent_trades(self, limit: int = 10, *, strategy: Optional[str] = None, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        q = "SELECT timestamp, strategy, symbol, side, size, entry, exit, pnl, fees, confidence, metadata FROM trades"
        conds: List[str] = []
        args: List[Any] = []
        if strategy:
            conds.append("strategy = ?")
            args.append(strategy)
        if symbol:
            conds.append("symbol = ?")
            args.append(symbol)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY timestamp DESC LIMIT ?"
        args.append(int(limit))
        rows = self._conn.execute(q, tuple(args)).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "timestamp": float(r[0]),
                    "strategy": r[1],
                    "symbol": r[2],
                    "side": r[3],
                    "size": float(r[4]),
                    "entry": float(r[5]),
                    "exit": float(r[6]),
                    "pnl": float(r[7]),
                    "fees": float(r[8]),
                    "confidence": float(r[9]) if r[9] is not None else None,
                    "metadata": json.loads(r[10] or "{}"),
                }
            )
        return out

    def latest_portfolio(self) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT timestamp, balance, equity, unrealized_pnl, positions_json FROM portfolio_snapshots ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return {
            "timestamp": float(row[0]),
            "balance": float(row[1]),
            "equity": float(row[2]),
            "unrealized_pnl": float(row[3]),
            "positions": json.loads(row[4] or "{}"),
        }

    def recent_llm_decisions(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT timestamp, decision_type, reasoning, sentiment, confidence, metadata FROM llm_decisions ORDER BY timestamp DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "timestamp": float(r[0]),
                    "decision_type": r[1],
                    "reasoning": r[2],
                    "sentiment": r[3],
                    "confidence": float(r[4]) if r[4] is not None else None,
                    "metadata": json.loads(r[5] or "{}"),
                }
            )
        return out

    # Runtime status helpers (single instance coordination)
    def set_runtime_started(self, *, pid: int, config_path: str, testnet: bool, wallet_address: str) -> None:
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO runtime_status (id, pid, status, started_at, last_heartbeat, desired_stop, config_path, testnet, wallet_address)
                VALUES (1, ?, 'ACTIVE', ?, ?, 0, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    pid=excluded.pid,
                    status='ACTIVE',
                    started_at=excluded.started_at,
                    last_heartbeat=excluded.last_heartbeat,
                    desired_stop=0,
                    config_path=excluded.config_path,
                    testnet=excluded.testnet,
                    wallet_address=excluded.wallet_address
                """,
                (int(pid), float(now), float(now), str(config_path), 1 if testnet else 0, str(wallet_address)),
            )

    def set_runtime_stopped(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE runtime_status
                SET status='STOPPED', last_heartbeat=? , desired_stop=0
                WHERE id=1
                """,
                (float(time.time()),),
            )

    def record_runtime_heartbeat(self, *, pid: Optional[int] = None) -> None:
        with self._lock, self._conn:
            if pid is None:
                self._conn.execute(
                    "UPDATE runtime_status SET last_heartbeat=?, status='ACTIVE' WHERE id=1",
                    (float(time.time()),),
                )
            else:
                self._conn.execute(
                    "UPDATE runtime_status SET last_heartbeat=?, status='ACTIVE', pid=? WHERE id=1",
                    (float(time.time()), int(pid)),
                )

    def get_runtime_status(self) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT pid, status, started_at, last_heartbeat, desired_stop, config_path, testnet, wallet_address FROM runtime_status WHERE id=1"
        ).fetchone()
        if not row:
            return None
        return {
            "pid": int(row[0]) if row[0] is not None else None,
            "status": str(row[1]) if row[1] is not None else "STOPPED",
            "started_at": float(row[2]) if row[2] is not None else None,
            "last_heartbeat": float(row[3]) if row[3] is not None else None,
            "desired_stop": bool(row[4]) if row[4] is not None else False,
            "config_path": str(row[5]) if row[5] is not None else None,
            "testnet": bool(row[6]) if row[6] is not None else None,
            "wallet_address": str(row[7]) if row[7] is not None else None,
        }

    def request_runtime_stop(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE runtime_status SET desired_stop=1 WHERE id=1")

    def clear_runtime_stop_request(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE runtime_status SET desired_stop=0 WHERE id=1")

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass


