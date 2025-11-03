from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class Command(ABC):
    name: str
    aliases: List[str] = []

    def __init__(self, context: Dict[str, Any]):
        self.context = context

    @abstractmethod
    def run(self, args: List[str]) -> None:  # pragma: no cover - simple CLI glue
        ...


