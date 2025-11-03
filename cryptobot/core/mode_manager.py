from __future__ import annotations

import os

from cryptobot.core.config import AppConfig


class ModeManager:
    def __init__(self, config: AppConfig) -> None:
        self.testnet = bool(config.broker.testnet)
        self.wallet_address = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
        self.private_key = os.getenv(
            "HYPERLIQUID_TESTNET_PRIVATE_KEY" if self.testnet else "HYPERLIQUID_LIVE_PRIVATE_KEY",
            "",
        )

    def is_testnet(self) -> bool:
        return self.testnet

    def get_api_endpoint(self) -> str:
        if self.testnet:
            return "https://api.hyperliquid-testnet.xyz"
        return "https://api.hyperliquid.xyz"


