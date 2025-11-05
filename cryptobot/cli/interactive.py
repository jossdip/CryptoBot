from __future__ import annotations

import argparse
from typing import Any, Dict

from cryptobot.cli.logo import show_logo
from cryptobot.cli.shell import InteractiveShell
from cryptobot.core.config import AppConfig
from cryptobot.core.env import load_local_environment


def main() -> None:  # pragma: no cover - entrypoint
    parser = argparse.ArgumentParser(description="C4$H M4CH1N3 Interactive CLI")
    parser.add_argument("--config", type=str, default="configs/live.hyperliquid.yaml")
    args = parser.parse_args()

    load_local_environment()

    cfg = AppConfig.load(args.config)
    if bool(getattr(cfg.cli, "logo_enabled", True)):
        show_logo()

    context: Dict[str, Any] = {
        "config": cfg,
        "config_path": args.config,
    }
    shell = InteractiveShell(context)
    shell.run()


if __name__ == "__main__":  # pragma: no cover
    main()


