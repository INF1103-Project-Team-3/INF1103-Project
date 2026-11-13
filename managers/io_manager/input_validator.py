from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class InputValidator(ABC):
    """Interface for anything that checks one typed answer.

    check() returns (value, "") when the answer is fine, or (None, reason)
    when it is not. Every validator answers in this same shape, the
    Prompter can ask any of them without knowing which one it has. That is the
    polymorphism I rely on in ask_until_valid().
    """

    @abstractmethod
    def check(self, answer: str) -> tuple[Any, str]:
        """Validate one answer. Returns (value, "") or (None, error message)."""
