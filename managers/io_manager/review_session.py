from __future__ import annotations

from typing import Iterable, Sequence

from managers.models import SENTIMENTS, SEVERITIES, FeedbackRecord

from .choice_validator import ChoiceValidator
from .feedback_view import FeedbackView
from .prompter import Prompter
from .review_decision import ReviewDecision
from .theme_validator import ThemeValidator


class ReviewSession:
    """Walks an admin through the flagged records and collects their decisions.

    I never change a record here. Each choice becomes a ReviewDecision that
    goes back in the SessionResult, and the pipeline applies it later.
    """

    # the letters the admin types for each choice
    UPDATE, ACCEPT_AI, DELETE, SKIP = "u", "a", "d", "s"

    def __init__(self, view: FeedbackView, prompter: Prompter,
                 theme_validator: ThemeValidator):
        self._view = view
        self._prompter = prompter
        # one validator per label. Each one accepts a blank answer, because
        # pressing Enter means "keep the current value".
        self._fields = {
            "theme": theme_validator,       # IOManager passes one with allow_blank=True
            "sentiment": ChoiceValidator(SENTIMENTS, allow_blank=True),
            "severity": ChoiceValidator(SEVERITIES, allow_blank=True),
        }
        # letter -> handler. SKIP has no entry because it makes no decision.
        self._handlers = {
            self.UPDATE: self._update,
            self.ACCEPT_AI: self._accept_ai,
            self.DELETE: self._delete,
        }

    def run(self, queue: Sequence[FeedbackRecord],
            decided_ids: Iterable[str] = ()) -> list[ReviewDecision]:
        """Review every flagged record that has no decision yet. Returns the new decisions."""
        skip = set(decided_ids)
        pending = [r for r in queue if r.feedback_id not in skip]
        if not pending:
            self._view.show_message("Nothing waiting for review.")
            return []

        decisions: list[ReviewDecision] = []
        for position, record in enumerate(pending, start=1):
            self._view.show_review_entry(record, position, len(pending))
            choice = self._ask_choice(record)
            if choice is None:              # the admin quit: stop, keeping the decisions so far
                break
            handler = self._handlers.get(choice)
            decision = handler(record) if handler else None
            if decision is not None:
                decisions.append(decision)

        self._view.show_message(
            f"Review finished. {len(decisions)} decision(s) recorded; "
            "they are applied when the analysis runs.")
        return decisions

    # ---- one record --------------------------------------------------

    def _ask_choice(self, record: FeedbackRecord) -> str | None:
        options = [self.UPDATE, self.DELETE, self.SKIP]
        menu = "[u]pdate, [d]elete, [s]kip"
        if record.ai:                       # "accept AI" only makes sense if the AI produced values
            options.insert(1, self.ACCEPT_AI)
            menu = "[u]pdate, [a]ccept AI's values, [d]elete, [s]kip"
        validator = ChoiceValidator(options, error=f"enter one of: {', '.join(options)}")
        return self._prompter.ask_until_valid(f"\n  {menu} (quit to stop): ", validator)

    def _update(self, record: FeedbackRecord) -> ReviewDecision | None:
        self._view.show_message(
            "Press Enter to keep a value. Keeping all three approves the record as is\n"
            "(and confirms its theme if it is a new one).")
        answers = {}
        for field, validator in self._fields.items():
            current = record.current_labels[field]      # final if Logic set it, else the writer's
            value = self._prompter.ask_until_valid(f"  New {field} [{current}]: ", validator)
            if value is None:
                self._view.show_message("Update cancelled.")
                return None
            answers[field] = value or current       # blank means keep the current value
        return ReviewDecision.update(record.feedback_id, answers)

    def _accept_ai(self, record: FeedbackRecord) -> ReviewDecision:
        return ReviewDecision.update(record.feedback_id, record.ai)

    def _delete(self, record: FeedbackRecord) -> ReviewDecision | None:
        if self._prompter.confirm("  Delete this feedback permanently? (y/n): "):
            return ReviewDecision.delete(record.feedback_id)
        self._view.show_message("Delete cancelled.")
        return None
