"""TrendAnalyser: compares one run's statistics with an earlier run's."""

from .results import AggregationResult, ThemeStats, TrendReport


class TrendAnalyser:
    """Builds a TrendReport from any two runs, so the views only have to print it."""

    # a theme's priority must move at least this far to count as Escalating or Easing
    __THRESHOLD = 5
    __FIRST_RUN_MESSAGE = "First run - nothing to compare yet."

    def compare(self, current: AggregationResult, previous: AggregationResult | None) -> TrendReport:
        """previous is None on the first run: the report then has has_previous
        False and a message explaining why."""
        if previous is None:
            return TrendReport(False, message=self.__FIRST_RUN_MESSAGE)

        names = {stats.theme for stats in current.themes} | {stats.theme for stats in previous.themes}
        rows = [self.__theme_row(name, current.get(name), previous.get(name)) for name in names]
        rows.sort(key=lambda row: (TrendReport.STATUS_ORDER.index(row["status"]),
                                   -(row["priority"]["current"] or 0), row["theme"]))
        return TrendReport(
            True,
            previous_run={"run_at": previous.run_at, "source_file": previous.source_file},
            headline={
                "total_entries": self.__compare(previous.total_entries, current.total_entries),
                "counted_entries": self.__compare(previous.counted_entries, current.counted_entries),
                "negative_percent": self.__compare(previous.negative_percent, current.negative_percent,
                                                   unit="%", change_unit=" pts"),
                "status_counts": {status: sum(row["status"] == status for row in rows)
                                  for status in TrendReport.STATUS_ORDER},
            },
            themes=rows,
        )

    def __theme_row(self, name: str, current: ThemeStats | None, previous: ThemeStats | None) -> dict:
        return {
            "theme": name,
            "status": self.__status(current, previous),
            "count": self.__compare(previous.count if previous else 0, current.count if current else 0),
            "priority": self.__compare(previous.priority if previous else None,
                                       current.priority if current else None),
        }

    def __status(self, current: ThemeStats | None, previous: ThemeStats | None) -> str:
        """Decided only by how far the theme's priority moved."""
        if previous is None:
            return TrendReport.NEW
        if current is None:
            return TrendReport.NOT_REPORTED
        change = current.priority - previous.priority
        if change >= self.__THRESHOLD:
            return TrendReport.ESCALATING
        if change <= -self.__THRESHOLD:
            return TrendReport.EASING
        return TrendReport.STEADY

    def __compare(self, previous: int | None, current: int | None, unit: str = "", change_unit: str = "") -> dict:
        """{"previous", "current", "change", "text"} for one number, where text
        is ready to print, e.g. '36 -> 50 (+14)'. A missing side (None) is shown
        as '-' and has no change."""
        if previous is None or current is None:
            before = f"{previous}{unit}" if previous is not None else "-"
            after = f"{current}{unit}" if current is not None else "-"
            return {"previous": previous, "current": current, "change": None, "text": f"{before} -> {after}"}
        change = current - previous
        signed = "0" if change == 0 else f"{change:+d}{change_unit}"
        return {"previous": previous, "current": current, "change": change,
                "text": f"{previous}{unit} -> {current}{unit} ({signed})"}
