from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv, find_dotenv


def load_local_environment() -> None:
    """Load environment variables from local files without overwriting existing env.

    Load order:
    1) ~/.cryptobot/.env (global, user-specific)
    2) ./.env (project-level)
    """
    home_env = Path.home() / ".cryptobot" / ".env"
    try:
        load_dotenv(dotenv_path=home_env, override=False)
    except Exception:
        # Best effort; ignore if file missing or unreadable
        pass
    # Then project-level .env (explicitly resolve path from current working directory)
    try:
        project_env = find_dotenv(usecwd=True)
        if project_env:
            load_dotenv(dotenv_path=project_env, override=False)
    except Exception:
        pass





