from __future__ import annotations

import sys
import threading
import time
from typing import Optional

from rich.console import Console


LOGO = r"""

      /$$     /$$$$$$  /$$   /$$  /$$$$$$  /$$   /$$       /$$      /$$ /$$   /$$  /$$$$$$  /$$   /$$   /$$   /$$   /$$  /$$$$$$     /$$   
  /$$$$$$  /$$__  $$| $$  | $$ /$$__  $$| $$  | $$      | $$$    /$$$| $$  | $$ /$$__  $$| $$  | $$ /$$$$  | $$$ | $$ /$$__  $$  /$$$$$$ 
 /$$__  $$| $$  \__/| $$  | $$| $$  \__/| $$  | $$      | $$$$  /$$$$| $$  | $$| $$  \__/| $$  | $$|_  $$  | $$$$| $$|__/  \ $$ /$$__  $$
| $$  \__/| $$      | $$$$$$$$|  $$$$$$ | $$$$$$$$      | $$ $$/$$ $$| $$$$$$$$| $$      | $$$$$$$$  | $$  | $$ $$ $$   /$$$$$/| $$  \__/
|  $$$$$$ | $$      |_____  $$ \____  $$| $$__  $$      | $$  $$$| $$|_____  $$| $$      | $$__  $$  | $$  | $$  $$$$  |___  $$|  $$$$$$ 
 \____  $$| $$    $$      | $$ /$$  \ $$| $$  | $$      | $$\  $ | $$      | $$| $$    $$| $$  | $$  | $$  | $$\  $$$ /$$  \ $$ \____  $$
 /$$  \ $$|  $$$$$$/      | $$|  $$$$$$/| $$  | $$      | $$ \/  | $$      | $$|  $$$$$$/| $$  | $$ /$$$$$$| $$ \  $$|  $$$$$$/ /$$  \ $$
|  $$$$$$/ \______/       |__/ \______/ |__/  |__/      |__/     |__/      |__/ \______/ |__/  |__/|______/|__/  \__/ \______/ |  $$$$$$/
 \_  $$_/                                                                                                                       \_  $$_/ 
   \__/                                                                                                                           \__/   
                                                                                                                                         
"""

# Frames d'animation pour les dollars qui tournent
DOLLAR_FRAMES = ["$", "₿", "€", "£", "¥", "₽", "₹", "₩"]
SPINNER_FRAMES = ["◐", "◓", "◑", "◒"]
ROTATING_DOLLARS = ["$", "$$", "$$$", "$$$$", "$$$", "$$", "$"]


class AnimatedLogo:
    """Gère l'affichage animé du logo en haut du terminal."""
    
    def __init__(self):
        self.console = Console()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_index = 0
        self._dollar_index = 0
        self._logo_height = len(LOGO.split('\n'))
        
    def _get_animated_logo(self) -> str:
        """Retourne le logo avec des dollars animés."""
        # Sélectionner le frame de dollar actuel
        dollar_char = DOLLAR_FRAMES[self._dollar_index % len(DOLLAR_FRAMES)]
        spinner = SPINNER_FRAMES[self._frame_index % len(SPINNER_FRAMES)]
        
        # Créer une version animée du logo en remplaçant certains $ par des caractères animés
        lines = LOGO.split('\n')
        animated_lines = []
        
        for i, line in enumerate(lines):
            if i == 0:  # Première ligne - ajouter un spinner et dollar animé
                animated_line = f"  {spinner} {dollar_char} " + line.lstrip()
            elif i < len(lines) - 2:  # Lignes du milieu - remplacer quelques $ par des caractères animés
                # Remplacer quelques $ par le dollar animé pour créer un effet de rotation
                if '$' in line:
                    # Remplacer le premier $ et quelques autres selon l'index
                    char_list = list(line)
                    dollar_count = 0
                    for j, char in enumerate(char_list):
                        if char == '$' and dollar_count < 3:  # Remplacer jusqu'à 3 $ par ligne
                            # Utiliser l'index pour créer un pattern de rotation
                            if (j + self._dollar_index) % 4 == 0:
                                char_list[j] = dollar_char
                                dollar_count += 1
                    animated_line = ''.join(char_list)
                else:
                    animated_line = line
            else:
                animated_line = line
            animated_lines.append(animated_line)
        
        return '\n'.join(animated_lines)
    
    def _render_logo(self) -> None:
        """Affiche le logo animé en haut du terminal."""
        if not sys.stdout.isatty():
            return
        
        try:
            # Sauvegarder la position du curseur
            sys.stdout.write('\x1b[s')  # Save cursor position
            sys.stdout.flush()
            
            # Aller en haut du terminal
            sys.stdout.write('\x1b[H')  # Move cursor to home position
            
            # Effacer depuis le curseur jusqu'à la fin de l'écran
            sys.stdout.write('\x1b[J')  # Clear from cursor to end of screen
            
            # Afficher le logo animé avec des codes ANSI cyan
            animated_logo = self._get_animated_logo()
            # Écrire directement dans stdout pour éviter les problèmes avec print
            sys.stdout.write(f"\x1b[36m{animated_logo}\x1b[0m")
            
            # Restaurer la position du curseur
            sys.stdout.write('\x1b[u')  # Restore cursor position
            sys.stdout.flush()
        except (IOError, OSError, AttributeError):
            # Si l'écriture échoue (terminal fermé, etc.), ignorer silencieusement
            pass
    
    def _animation_loop(self) -> None:
        """Boucle d'animation dans un thread séparé."""
        while self._running:
            self._frame_index += 1
            self._dollar_index += 1
            self._render_logo()
            time.sleep(0.3)  # 300ms entre chaque frame
    
    def start(self) -> None:
        """Démarre l'animation."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._animation_loop, daemon=True)
        self._thread.start()
        # Afficher immédiatement
        self._render_logo()
    
    def stop(self) -> None:
        """Arrête l'animation."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
    
    def refresh(self) -> None:
        """Force un rafraîchissement du logo."""
        self._render_logo()


# Instance globale pour l'animation
_animated_logo: Optional[AnimatedLogo] = None


def show_logo() -> None:
    """Affiche le logo une fois (sans animation)."""
    console = Console()
    console.print(f"[cyan]{LOGO}[/cyan]")


def start_animated_logo() -> AnimatedLogo:
    """Démarre l'animation permanente du logo."""
    global _animated_logo
    if _animated_logo is None:
        _animated_logo = AnimatedLogo()
    _animated_logo.start()
    return _animated_logo


def stop_animated_logo() -> None:
    """Arrête l'animation du logo."""
    global _animated_logo
    if _animated_logo:
        _animated_logo.stop()


def refresh_animated_logo() -> None:
    """Rafraîchit le logo animé (utile après un clear)."""
    global _animated_logo
    if _animated_logo:
        _animated_logo.refresh()


