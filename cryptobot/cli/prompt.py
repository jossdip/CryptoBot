from __future__ import annotations

from typing import Any, Dict


# Codes ANSI pour les couleurs
ANSI_RESET = "\x1b[0m"
ANSI_BOLD = "\x1b[1m"
ANSI_CYAN = "\x1b[36m"
ANSI_YELLOW = "\x1b[33m"
ANSI_MAGENTA = "\x1b[35m"
ANSI_GREEN = "\x1b[32m"
ANSI_BLUE = "\x1b[34m"
ANSI_RED = "\x1b[31m"
ANSI_WHITE = "\x1b[37m"


def _get_status_color_code(status: str) -> str:
    """Retourne le code ANSI approprié selon le statut."""
    status_upper = status.upper()
    if status_upper in ("ACTIVE", "RUNNING"):
        return ANSI_GREEN
    elif status_upper == "STOPPED":
        return ANSI_RED
    elif status_upper == "PAUSED":
        return ANSI_YELLOW
    elif status_upper in ("ERROR", "FAILED"):
        return ANSI_RED
    else:
        return ANSI_WHITE


def build_prompt(*, exchange: str, status: str, fmt: str = "[C4$H@{exchange}:{status}] > ", stats: Dict[str, Any] | None = None) -> str:
    """Construit un prompt coloré avec CSHMCHN stylisé."""
    # Remplacer C4$H par CSHMCHN avec des couleurs attrayantes
    # CSHMCHN avec des couleurs arc-en-ciel : C(cyan), S(yellow), H(magenta), M(green), C(cyan), H(magenta), N(blue)
    colored_name = (
        f"{ANSI_BOLD}{ANSI_CYAN}C{ANSI_RESET}"
        f"{ANSI_BOLD}{ANSI_YELLOW}S{ANSI_RESET}"
        f"{ANSI_BOLD}{ANSI_MAGENTA}H{ANSI_RESET}"
        f"{ANSI_BOLD}{ANSI_GREEN}M{ANSI_RESET}"
        f"{ANSI_BOLD}{ANSI_CYAN}C{ANSI_RESET}"
        f"{ANSI_BOLD}{ANSI_MAGENTA}H{ANSI_RESET}"
        f"{ANSI_BOLD}{ANSI_BLUE}N{ANSI_RESET}"
    )
    
    # Couleur du statut
    status_color = _get_status_color_code(status)
    colored_status = f"{status_color}{status}{ANSI_RESET}"
    
    # Exchange en cyan
    colored_exchange = f"{ANSI_CYAN}{exchange}{ANSI_RESET}"
    
    # Construire le prompt avec les couleurs
    prompt = f"[{colored_name}@{colored_exchange}:{colored_status}] > "
    
    return prompt


