"""ImpactAnalyser: was an action followed by less negative feedback on its theme?"""

import re
from datetime import date, timedelta

from managers.models import CRITICAL, HIGH, NEGATIVE, UNVERIFIED, Action, FeedbackRecord

from .results import ImpactReport
from .theme_aggregator import ThemeAggregator
from .theme_normaliser import ThemeNormaliser


class ImpactAnalyser:
    """Compares two equal windows either side of an action's date. The result
    shows a change that came after the action, not proof that it caused it."""

    __WINDOW_DAYS = 14          # each window is at most this long
    __MIN_AFTER_DAYS = 7        # a shorter after window is too early to tell
    __MIN_ENTRIES = 3           # fewer matching entries in both windows is too early to tell
    __CHANGE_PERCENT = 30       # negative per week must move this much to count
    __PRIORITY_POINTS = 5       # priority must move this much to count

    def __init__(self, normaliser: ThemeNormaliser, aggregator: ThemeAggregator, weeks: int = 4):
        """weeks: how many weeks either side of the action date the chart data covers."""
        self.__normaliser = normaliser
        self.__aggregator = aggregator
        self.__weeks = weeks

    def evaluate(self, action: Action, records: list[FeedbackRecord], today: date,
                 other_actions: list[Action] = ()) -> ImpactReport:
        """Expects records that have been through the rules. Today's feedback
        counts, so a report can change on a later run the same day.
        other_actions are checked for overlap; the action itself is skipped."""
        start = date.fromisoformat(action.action_date)
        theme = self.__normaliser.normalise(action.theme)
        matching = [r for r in records if r.counted and r.theme == theme and self.__mentions(r, action.keyword)]
        weekly = self.__weekly(matching, start, today)
        if start >= today:
            return ImpactReport(action, ImpactReport.TOO_EARLY,
                                f"Too early to tell: the action is dated {action.action_date}, so there is no "
                                f"feedback after it yet.", weekly=weekly)

        days = min((today - start).days + 1, self.__WINDOW_DAYS)
        before = self.__measure(theme, matching, records, start - timedelta(days=days), days)
        after = self.__measure(theme, matching, records, start, days)

        label, message = self.__judge(action, theme, before, after)
        warnings = self.__overlaps(action, theme, before, after, other_actions) + self.__unverified(before, after)
        return ImpactReport(action, label, message, before, after, weekly, warnings)

    def __weekly(self, matching: list[FeedbackRecord], start: date, today: date) -> list[dict]:
        """{week_start, negative, total} for each week either side of the action
        date. Weeks are counted from the action date, and weeks that have not
        started yet are left out, so a chart shows a gap rather than zeros."""
        weeks = []
        for offset in range(-self.__weeks, self.__weeks):
            first_day = start + timedelta(weeks=offset)
            if first_day > today:
                break
            inside = [r for r in matching if first_day <= self.__day(r) < first_day + timedelta(weeks=1)]
            weeks.append({"week_start": first_day.isoformat(),
                          "negative": sum(r.sentiment == NEGATIVE for r in inside),
                          "total": len(inside)})
        return weeks

    def __overlaps(self, action: Action, theme: str, before: dict, after: dict,
                   other_actions: list[Action]) -> list[str]:
        """A warning for each other action on the same theme dated inside the two windows."""
        first_day, last_day = before["start"], after["end"]
        return [f"Another action on {theme} ({other.description}, {other.action_date}) falls inside these "
                f"windows, so this change can't be put down to one action."
                for other in other_actions
                if other.action_id != action.action_id
                and self.__normaliser.normalise(other.theme) == theme
                and first_day <= other.action_date <= last_day]

    @staticmethod
    def __unverified(before: dict, after: dict) -> list[str]:
        count = before["unverified"] + after["unverified"]
        if not count:
            return []
        entries = "entry is" if count == 1 else "entries are"
        return [f"{count} of the measured {entries} unverified: the AI hasn't checked them yet."]

    def __measure(self, theme: str, matching: list[FeedbackRecord], records: list[FeedbackRecord],
                  first_day: date, days: int) -> dict:
        """The numbers for one window: first_day and the days after it."""
        last_day = first_day + timedelta(days=days - 1)
        inside = [r for r in matching if first_day <= self.__day(r) <= last_day]
        counted_in_window = sum(r.counted and first_day <= self.__day(r) <= last_day for r in records)
        negative = sum(r.sentiment == NEGATIVE for r in inside)
        stats = self.__aggregator.aggregate(inside).get(theme)
        return {
            "start": first_day.isoformat(),
            "end": last_day.isoformat(),
            "days": days,
            "entries": len(inside),
            "negative": negative,
            "negative_per_week": round(negative * 7 / days, 1),
            "share_percent": round(100 * len(inside) / counted_in_window) if counted_in_window else 0,
            "priority": stats.priority if stats else 0,
            "high_or_critical": sum(r.severity in (HIGH, CRITICAL) for r in inside),
            "unverified": sum(r.verification == UNVERIFIED for r in inside),
        }

    def __judge(self, action: Action, theme: str, before: dict, after: dict) -> tuple[str, str]:
        if after["days"] < self.__MIN_AFTER_DAYS:
            return ImpactReport.TOO_EARLY, (
                f"Too early to tell: only {after['days']} day(s) of feedback since {action.action_date}; "
                f"at least {self.__MIN_AFTER_DAYS} are needed.")
        entries = before["entries"] + after["entries"]
        if entries < self.__MIN_ENTRIES:
            return ImpactReport.TOO_EARLY, (
                f"Too early to tell: only {entries} matching entries in the two {after['days']}-day windows; "
                f"at least {self.__MIN_ENTRIES} are needed.")

        change = self.__percent_change(before["negative_per_week"], after["negative_per_week"])
        priority_change = after["priority"] - before["priority"]
        if change <= -self.__CHANGE_PERCENT and priority_change <= -self.__PRIORITY_POINTS:
            label = ImpactReport.EFFECTIVE
        elif change >= self.__CHANGE_PERCENT or priority_change >= self.__PRIORITY_POINTS:
            label = ImpactReport.WORSE
        else:
            label = ImpactReport.NO_CHANGE
        return label, self.__message(action, theme, before, after)

    @staticmethod
    def __percent_change(before: float, after: float) -> float:
        """How far after moved from before, in percent. From zero, any rise counts as a full rise."""
        if before == 0:
            return 100.0 if after > 0 else 0.0
        return 100 * (after - before) / before

    @staticmethod
    def __message(action: Action, theme: str, before: dict, after: dict) -> str:
        """e.g. "Since Upgraded library Wi-Fi (2026-10-01), negative Facilities feedback mentioning
        'wifi' fell from 3.0 to 0.5 per week, and its priority dropped from 86 to 24." """
        def moved(old, new, down, up, unit=""):
            if new == old:
                return f"stayed at {old:g}{unit}"
            return f"{down if new < old else up} from {old:g} to {new:g}{unit}"

        mentioning = f" mentioning '{action.keyword}'" if action.keyword else ""
        return (f"Since {action.description} ({action.action_date}), negative {theme} feedback{mentioning} "
                f"{moved(before['negative_per_week'], after['negative_per_week'], 'fell', 'rose', ' per week')}, "
                f"and its priority {moved(before['priority'], after['priority'], 'dropped', 'rose')}.")

    @staticmethod
    def __mentions(record: FeedbackRecord, keyword: str | None) -> bool:
        """True with no keyword, or when the text has the keyword as a whole word, in any case."""
        if keyword is None:
            return True
        return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", record.text, re.IGNORECASE) is not None

    @staticmethod
    def __day(record: FeedbackRecord) -> date:
        return date.fromisoformat(record.timestamp[:10])
