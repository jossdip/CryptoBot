from __future__ import annotations

import os
import tempfile
import time

from cryptobot.core.config import LearningMemoryConfig
from cryptobot.monitor.storage import StorageManager
from cryptobot.learn.memory import Episode, EpisodeStore


def test_episode_store_knn_numeric_cosine() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "monitor.db")
        storage = StorageManager(db_path=db_path)
        mem = EpisodeStore(storage=storage, config=LearningMemoryConfig(enabled=True, embedder="none"))
        # Insert a few episodes with distinct features
        base_ts = time.time()
        e1 = Episode(id=None, timestamp=base_ts, strategy="momentum", symbol="BTC/USD:USD",
                     features={"price_median": 100.0, "volatility_1m": 0.01, "sent_reddit": 0.5},
                     decision={"direction": "long", "leverage": 5}, outcome={"pnl": 10.0})
        e2 = Episode(id=None, timestamp=base_ts + 1, strategy="momentum", symbol="BTC/USD:USD",
                     features={"price_median": 100.0, "volatility_1m": 0.02, "sent_reddit": -0.2},
                     decision={"direction": "short", "leverage": 3}, outcome={"pnl": -5.0})
        mem.add_episode(e1)
        mem.add_episode(e2)
        # Query kNN near e1 features
        knn = mem.knn({"price_median": 100.0, "volatility_1m": 0.0101, "sent_reddit": 0.49}, k=1)
        assert len(knn) == 1
        top_ep, sim = knn[0]
        assert isinstance(top_ep.decision, dict)
        assert sim <= 1.0 + 1e-6

