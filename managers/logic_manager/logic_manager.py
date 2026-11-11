"""LogicManager: everything the other parts ask of Logic."""

from datetime import date

from managers.models import MATCHED, REVIEWED, THEMES, UNVERIFIED, Action, FeedbackRecord

from .impact_analyser import ImpactAnalyser
from .record_validator import RecordValidator
from .results import AggregationResult, ImpactReport, TrendReport
from .rule_engine import RuleEngine
from .rules import CriticalSeverityRule, NewThemeRule, ReviewRule, UnclearThemeRule, UserAIMismatchRule
from .theme_aggregator import ThemeAggregator
from .theme_normaliser import ThemeNormaliser
from .trend_analyser import TrendAnalyser


class LogicManager:
    """The Logic part's public API (design reference 8.5). It creates and owns
    its parts. It never calls another manager, touches files or prints: the
    pipeline passes objects in and saves the objects that come back."""

    def __init__(self, rules: list[ReviewRule] | None = None, known_themes=THEMES):
        """rules=None uses the default rules; pass a list to choose your own."""
        self.__normaliser = ThemeNormaliser(known_themes)
        self.__validator = RecordValidator()
        self.__engine = RuleEngine(self.__default_rules() if rules is None else rules)
        self.__aggregator = ThemeAggregator(self.__normaliser)
        self.__analyser = TrendAnalyser()
        self.__impact = ImpactAnalyser(self.__normaliser, self.__aggregator)

    def set_known_themes(self, themes) -> None:
        """Updates the themes treated as known, e.g. after an admin confirms a new one."""
        self.__normaliser.set_known_themes(themes)

    def normalise_theme(self, label: str) -> str:
        """A base or confirmed theme, "Unclear", or the cleaned new label (7.4)."""
        return self.__normaliser.normalise(label)

    def validate(self, records: list[FeedbackRecord]) -> tuple[list, list]:
        """Returns (valid, invalid), where invalid is a list of (record, problems)."""
        return self.__validator.validate(records)

    def apply_rules(self, records: list[FeedbackRecord]) -> list[FeedbackRecord]:
        """Sets each record's final values and verification, then runs the rules.
        Reviewed records keep the admin's values. Expects validated records.
        Returns the same records."""
        for record in records:
            if record.verification != REVIEWED:
                self.__set_final_values(record)
        self.__engine.apply(records)
        return records

    def review_queue(self, records: list[FeedbackRecord]) -> list[FeedbackRecord]:
        """The flagged records, critical first."""
        return self.__engine.review_queue(records)

    def aggregate(self, records: list[FeedbackRecord]) -> AggregationResult:
        return self.__aggregator.aggregate(records)

    def compare_runs(self, current: AggregationResult, previous: AggregationResult | None) -> TrendReport:
        """Compares any two runs; previous is None on the first run."""
        return self.__analyser.compare(current, previous)

    def evaluate_actions(self, actions: list[Action], records: list[FeedbackRecord], today: date) -> list[ImpactReport]:
        """One ImpactReport per action, in the same order. Expects records that
        have been through the rules. Each action is checked against the others
        for overlap on the same theme."""
        return [self.__impact.evaluate(action, records, today, actions) for action in actions]

    def __default_rules(self) -> list[ReviewRule]:
        return [
            CriticalSeverityRule(),
            UnclearThemeRule(self.__normaliser),
            NewThemeRule(self.__normaliser),
            UserAIMismatchRule(self.__normaliser),
        ]

    def __set_final_values(self, record: FeedbackRecord) -> None:
        """The final values are the user's, with the theme normalised (7.1)."""
        user = record.user
        verification = UNVERIFIED if record.ai is None else MATCHED
        record.set_final(self.normalise_theme(user["theme"]), user["sentiment"], user["severity"], verification)
