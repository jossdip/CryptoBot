from __future__ import annotations

import os
import tempfile
import time

from cryptobot.monitor.storage import StorageManager


def test_storage_episode_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "monitor.db")
        sm = StorageManager(db_path=db_path)
        eid = sm.record_episode(
            timestamp=time.time(),
            strategy="scalping",
            symbol="BTC/USD:USD",
            features={"a": 1.0},
            decision={"direction": "long"},
            outcome={"pnl": 0.1},
        )
        assert isinstance(eid, int) and eid > 0
        eps = sm.query_episodes(limit=10, strategy="scalping")
        assert len(eps) >= 1
        assert eps[0]["strategy"] == "scalping"

