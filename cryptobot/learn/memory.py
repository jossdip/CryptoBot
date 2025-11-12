from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from cryptobot.core.config import LearningMemoryConfig
from cryptobot.monitor.storage import StorageManager


@dataclass
class Episode:
    id: Optional[int]
    timestamp: float
    strategy: str
    symbol: str
    features: Dict[str, float]
    decision: Dict[str, Any]
    outcome: Dict[str, Any]


class EpisodeStore:
    def __init__(self, storage: StorageManager, config: LearningMemoryConfig) -> None:
        self.storage = storage
        self.cfg = config
        self._embedder_name = (self.cfg.embedder or "none").lower()
        self._embedder = None
        # Lazy init embedder if requested and available
        if self._embedder_name == "sbert-mini":
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
                # Use a tiny model name if available; avoid download if not present locally
                self._embedder = SentenceTransformer("paraphrase-MiniLM-L6-v2")
            except Exception:
                # Degrade gracefully to numeric vector similarity
                self._embedder = None
                self._embedder_name = "none"

    def _features_to_vector(self, features: Dict[str, float]) -> np.ndarray:
        # Deterministic ordering by sorted keys
        keys = sorted(features.keys())
        vals: List[float] = []
        for k in keys:
            try:
                v = float(features[k])
                if np.isfinite(v):
                    vals.append(v)
                else:
                    vals.append(0.0)
            except Exception:
                vals.append(0.0)
        if not vals:
            return np.zeros((1,), dtype=np.float32)
        vec = np.asarray(vals, dtype=np.float32)
        # Normalize to unit length to stabilize cosine
        n = np.linalg.norm(vec) or 1.0
        return (vec / float(n)).astype(np.float32)

    def _features_to_text(self, features: Dict[str, float]) -> str:
        # Build a simple "k:v" string, sorted keys
        parts: List[str] = []
        for k in sorted(features.keys()):
            try:
                parts.append(f"{k}:{float(features[k]):.6f}")
            except Exception:
                parts.append(f"{k}:0.0")
        return " ".join(parts)

    def add_episode(self, episode: Episode) -> int:
        """Persist episode; store embedding if embedder is available. Returns episode id."""
        eid = self.storage.record_episode(
            timestamp=float(episode.timestamp),
            strategy=str(episode.strategy),
            symbol=str(episode.symbol),
            features=episode.features,
            decision=episode.decision,
            outcome=episode.outcome,
        )
        if eid and self._embedder_name != "none" and self._embedder is not None and bool(self.cfg.enabled):
            try:
                text = self._features_to_text(episode.features)
                vec = self._embedder.encode([text])[0]  # type: ignore[attr-defined]
                self.storage.record_episode_embedding(episode_id=eid, vector=[float(x) for x in vec])
            except Exception:
                # Ignore embedding errors entirely
                pass
        return int(eid or 0)

    def query_recent(self, limit: int) -> List[Episode]:
        rows = self.storage.query_episodes(limit=int(limit))
        out: List[Episode] = []
        for r in rows:
            try:
                out.append(
                    Episode(
                        id=int(r.get("id", 0)),
                        timestamp=float(r.get("timestamp", 0.0)),
                        strategy=str(r.get("strategy", "")),
                        symbol=str(r.get("symbol", "")),
                        features={k: float(v) for k, v in (r.get("features", {}) or {}).items()},
                        decision=r.get("decision", {}) or {},
                        outcome=r.get("outcome", {}) or {},
                    )
                )
            except Exception:
                continue
        return out

    def knn(self, features: Dict[str, float], k: int) -> List[Tuple[Episode, float]]:
        """Return top-k similar episodes by cosine similarity (numeric fallback).
        Embeddings (when available) are currently only stored; numeric fallback is used for retrieval to avoid heavy dependencies.
        """
        if not bool(self.cfg.enabled):
            return []
        # Limit the recent window for efficiency
        window = min(int(self.cfg.max_episodes), 2000)
        episodes = self.query_recent(limit=window)
        if not episodes:
            return []
        q = self._features_to_vector(features)
        sims: List[Tuple[int, float]] = []
        vecs: List[np.ndarray] = []
        for idx, ep in enumerate(episodes):
            v = self._features_to_vector(ep.features)
            vecs.append(v)
            try:
                sims.append((idx, float(np.dot(q, v))))
            except Exception:
                sims.append((idx, 0.0))
        sims.sort(key=lambda x: x[1], reverse=True)
        top = sims[: max(1, int(k))]
        return [(episodes[i], float(s)) for i, s in top]


