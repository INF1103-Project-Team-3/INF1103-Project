"""RuleEngine: runs the review rules and builds the review queue."""

from managers.models import REVIEWED, SEVERITIES, FeedbackRecord

from .rules import Rule


class RuleEngine:
    """Runs any list of rules over records without knowing which rules they
    are, so a new rule needs no change here (design reference 10.2, OCP)."""

    def __init__(self, rules: list[Rule]):
        """Raises TypeError if something in rules is not a Rule."""
        for rule in rules:
            if not isinstance(rule, Rule):
                raise TypeError(f"RuleEngine needs Rule objects, got {type(rule).__name__}")
        # a copy, so changing the caller's list later does not change the engine
        self.__rules = tuple(rules)

    @property
    def rules(self) -> tuple[Rule, ...]:
        return self.__rules

    def apply(self, records: list[FeedbackRecord]) -> None:
        """Clears each record's old reasons, then runs every rule on it.
        Reviewed records are skipped: an admin's decision is final."""
        for record in records:
            if record.verification == REVIEWED:
                continue
            record.clear_review()
            for rule in self.__rules:
                rule.apply(record)

    def review_queue(self, records: list[FeedbackRecord]) -> list[FeedbackRecord]:
        """The flagged records in triage order: most severe first, then grouped
        by theme, then by feedback_id so the order is stable."""
        return sorted((r for r in records if r.needs_review), key=self.__sort_key)

    @staticmethod
    def __sort_key(record: FeedbackRecord) -> tuple:
        # a record without a valid final severity sorts last instead of crashing the sort
        rank = SEVERITIES.index(record.severity) if record.severity in SEVERITIES else -1
        return (-rank, record.theme or "", record.feedback_id)
