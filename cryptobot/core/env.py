from __future__ import annotations

from pathlib import Path
import os

from dotenv import load_dotenv


def load_local_environment() -> None:
    """Load environment variables from a single canonical location.

    Canonical path: <project_root>/.env (derived from this package location),
    which OVERRIDES any already-set variables. If that file does not exist,
    we fallback to ~/.cryptobot/.env (also with override=True).
    The resolved path is exposed via CRYPTOBOT_ENV_PATH for diagnostics.
    """
    # Resolve project root from the installed package path, independent of CWD
    project_root = Path(__file__).resolve().parents[2]
    root_env = project_root / ".env"

    loaded = False
    try:
        if root_env.exists():
            load_dotenv(dotenv_path=root_env, override=True)
            os.environ["CRYPTOBOT_ENV_PATH"] = str(root_env)
            loaded = True
        else:
            # Legacy fallback for old setups
            home_env = Path.home() / ".cryptobot" / ".env"
            if home_env.exists():
                load_dotenv(dotenv_path=home_env, override=True)
                os.environ["CRYPTOBOT_ENV_PATH"] = str(home_env)
                loaded = True
    except Exception:
        # Best-effort; do not crash on env loading issues
        pass

    # If nothing was loaded, still indicate the intended canonical path
    if not loaded:
        os.environ.setdefault("CRYPTOBOT_ENV_PATH", str(root_env))





