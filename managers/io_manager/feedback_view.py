from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Sequence

from ..models import FeedbackRecord

if TYPE_CHECKING:
    from ..ai_manager import AISummary
    from ..logic_manager import AggregationResult, TrendReport


class FeedbackView(ABC):
    """Interface for everything the application shows to a person.

    IOManager and the other I/O classes only ever talk to this interface, so
    ConsoleView (the terminal) can be swapped for any other front end, or for a
    test double, without changing them. This is the Liskov Substitution
    Principle in practice: any FeedbackView works wherever one is expected.
    """

    @abstractmethod
    def show_message(self, message: str) -> None:
        """Show an ordinary message."""

    @abstractmethod
    def show_notice(self, notice: str) -> None:
        """Show a prominent status notice."""

    @abstractmethod
    def show_dashboard(self, result: "AggregationResult | None",
                       trend: "TrendReport | None",
                       summary: "AISummary | None",
                       queue: Sequence[FeedbackRecord]) -> None:
        """Show the theme statistics, trend, AI summary and review queue."""

    @abstractmethod
    def show_search_results(self, records: Sequence[FeedbackRecord]) -> None:
        """Show the records a search found."""

    @abstractmethod
    def show_review_entry(self, record: FeedbackRecord, position: int, total: int) -> None:
        """Show one flagged record in full, ready for a decision."""

    @abstractmethod
    def show_rejected_rows(self, rejected: Sequence[tuple[int, str]]) -> None:
        """Show the rows an import rejected, with the reason for each."""
