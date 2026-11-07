"""Logic Manager: checks records, applies the review rules, and works out the
statistics, trends and impact of actions. It imports only managers.models."""

from .logic_manager import LogicManager
from .results import AggregationResult, ThemeStats, TrendReport
from .rules import CriticalSeverityRule, NewThemeRule, ReviewRule, Rule, UnclearThemeRule, UserAIMismatchRule
