from __future__ import annotations

import re
import textwrap
from typing import Any, Callable, Sequence

from managers.models import CRITICAL, HIGH, LABEL_FIELDS, UNCLEAR_THEME, FeedbackRecord

from .feedback_view import FeedbackView


class ConsoleView(FeedbackView):
    """The terminal implementation of FeedbackView.

    This is the only class that prints, so all screen layout lives here and the
    rest of the I/O code stays free of formatting. The output function is a
    constructor parameter (default print) so a test can capture what was shown.

    Logic's and AI's result objects hold a mix of objects (ThemeStats) and plain
    dictionaries (the trend headline), so I read every field through _get().
    """

    # column widths for the tables I print
    WIDTH = 82
    COLUMN_THEME = 22

    MERGED_THEME = 24
    MERGED_STATUS = 16
    MERGED_COUNT = 17
    MERGED_SENT = 8
    MERGED_URGENT = 6
    MERGED_GAP = "   "
    MERGED_WIDTH = (MERGED_THEME + MERGED_STATUS + MERGED_COUNT + MERGED_SENT
                    + MERGED_URGENT + len(MERGED_GAP) + 8)

    REVIEW_ID_WIDTH = 12
    REVIEW_REASON_WIDTH = 24
    REVIEW_SUMMARY_WIDTH = 22

    def __init__(self, writer: Callable[[str], None] = print):
        self._write = writer

    # ------------------------------------------------------------------
    # FeedbackView methods
    # ------------------------------------------------------------------

    def show_message(self, message: str) -> None:
        self._block([message])

    def show_notice(self, notice: str) -> None:
        bar = "=" * self.WIDTH
        self._block([bar, f"    {notice}", bar])

    def show_dashboard(self, result, trend, summary, queue: Sequence[FeedbackRecord]) -> None:
        if not self._get(result, "themes"):
            self._block(["No aggregated data yet."])
        else:
            # critical entries that are both counted in the statistics and flagged
            both = sum(1 for r in queue if r.counted and r.severity == CRITICAL)
            self._block(self._header(result, len(queue), both))
            self._block(self._overall(summary))
            self._block(self._trend_lines(trend))
            rows = self._rows(result, trend)
            # with a previous run to compare against, one merged table; otherwise a plain one
            self._block(self._merged_table(rows) if self._has_trend(trend)
                        else self._plain_table(rows))
            self._block(self._pending(result))
            self._block(self._actions(summary, rows))
        self._show_review_queue(queue)

    def show_search_results(self, records: Sequence[FeedbackRecord]) -> None:
        self._block([f"Found {len(records)} matching record(s):", "-" * self.WIDTH])
        for record in records:
            self._write(f"{record.feedback_id}   {self._tags(record.current_labels)}")
            self._write(self._wrap(self._display_text(record)))
            self._write("")

    def show_review_entry(self, record: FeedbackRecord, position: int, total: int) -> None:
        self._block([f"Review {position} of {total}   ID: {record.feedback_id}", "-" * self.WIDTH])
        self._write(self._wrap(record.text))
        self._write("")
        final = self._tags({name: getattr(record, name) for name in LABEL_FIELDS})
        self._write(f"  {'Student':<8}: {self._tags(record.user)}")
        ai = self._tags(record.ai) if record.ai else "no result (AI failed)"
        self._write(f"  {'AI':<8}: {ai}")
        self._write(f"  {'Final':<8}: {final or 'not checked yet'}")
        self._write(f"  {'Status':<8}: {record.verification}")
        if record.review_reasons:
            self._write(f"  {'Flagged':<8}: {'; '.join(record.review_reasons)}")

    def show_rejected_rows(self, rejected: Sequence[tuple[int, str]]) -> None:
        if rejected:
            self._block(["Rejected rows:"] + [f"  Row {n}: {reason}" for n, reason in rejected])

    # ------------------------------------------------------------------
    # Dashboard blocks. Each returns a list of lines and prints nothing;
    # show_dashboard() decides the order and prints them.
    # ------------------------------------------------------------------

    def _header(self, result: Any, queue_count: int, both_count: int) -> list[str]:
        lines = [f"FEEDBACK DASHBOARD    entries: {self._get(result, 'total_entries')}   "
                 f"counted: {self._get(result, 'counted_entries')}   for review: {queue_count}"]
        unverified = self._get(result, "unverified_count", 0)
        if unverified:
            lines.append(f"{unverified} record(s) unverified (AI failed, retried next run)")
        if both_count:
            entries = "entry is" if both_count == 1 else "entries are"
            lines.append(f"{both_count} critical {entries} in both: counted and for review")
        return lines + ["=" * self.WIDTH]

    def _overall(self, summary: Any) -> list[str]:
        text = self._clean(self._get(summary, "overall_summary", "") or "")
        if not text:
            return []
        # one bullet per sentence reads better than one long paragraph
        created = str(self._get(summary, "created_at") or "").replace("T", " ")
        title = f"OVERALL (summary from {created})" if created else "OVERALL"
        return [title] + [
            textwrap.fill(s, width=self.WIDTH, initial_indent="  - ", subsequent_indent="    ")
            for s in re.split(r"(?<=\.)\s+", text)]

    def _trend_lines(self, trend: Any) -> list[str]:
        if trend is None:
            return []
        if not self._has_trend(trend):
            message = self._get(trend, "message")      # e.g. "no earlier run to compare"
            return [message] if message else []
        previous = self._get(trend, "previous_run") or {}
        run_at = str(self._get(previous, "run_at", "")).replace("T", " ")
        headline = self._get(trend, "headline")
        return [f"Trend vs previous run ({run_at})",
                f"Entries: {self._text(headline, 'total_entries')}    "
                f"Negative: {self._text(headline, 'negative_percent')}"]

    def _pending(self, result: Any) -> list[str]:
        """New themes waiting for an admin to confirm them."""
        pending = self._get(result, "pending_themes") or {}       # theme -> record count
        if not pending:
            return []
        return ["NEW THEMES WAITING FOR CONFIRMATION"] + [
            f"  {name} ({count} record(s))" for name, count in pending.items()]

    def _actions(self, summary: Any, rows: list[tuple]) -> list[str]:
        """The AI's suggested action per theme, in the same order as the table."""
        suggested = {self._get(a, "theme"): self._get(a, "suggested_action")
                     for a in self._get(summary, "theme_actions", []) or []
                     if self._get(a, "theme") != UNCLEAR_THEME}    # nothing useful to suggest
        if not suggested:
            return []
        lines = ["SUGGESTED ACTIONS", "-" * self.WIDTH]
        for name, stats, _, _ in rows:
            if stats is not None and name in suggested:
                lines.append(textwrap.fill(
                    self._clean(str(suggested[name])), width=self.WIDTH,
                    initial_indent=f"{name:<{self.COLUMN_THEME}}",
                    subsequent_indent=" " * self.COLUMN_THEME))
        return lines

    def _plain_table(self, rows: list[tuple]) -> list[str]:
        lines = ["THEMES",
                 f"{'THEME':<{self.COLUMN_THEME}}{'COUNT':>5}  {'AVG SENT':>8}  "
                 f"{'HIGH+CRIT':>9}  {'PRIORITY':>8}", "-" * self.WIDTH]
        for name, stats, urgent, _ in rows:
            lines.append(f"{name:<{self.COLUMN_THEME}}{self._get(stats, 'count'):>5}  "
                         f"{self._get(stats, 'avg_sentiment'):>8.2f}  {urgent:>9}  "
                         f"{self._number(self._get(stats, 'priority')):>8}")
        return lines

    def _merged_table(self, rows: list[tuple]) -> list[str]:
        """Current figures and the change since the previous run, side by side."""
        lines = ["THEMES",
                 f"{'THEME':<{self.MERGED_THEME}}{'STATUS':<{self.MERGED_STATUS}}"
                 f"{'COUNT':<{self.MERGED_COUNT}}{'AVG SENT':>{self.MERGED_SENT}}"
                 f"{'H+C':>{self.MERGED_URGENT}}{self.MERGED_GAP}PRIORITY", "-" * self.MERGED_WIDTH]
        for name, stats, urgent, row in rows:
            # a theme can be missing from one side: show "-" instead of a number
            status = self._get(row, "status", "-") if row is not None else "-"
            count = (self._text(row, "count") if row is not None
                     else str(self._get(stats, "count")))
            priority = (self._text(row, "priority") if row is not None
                        else self._number(self._get(stats, "priority")))
            avg = f"{self._get(stats, 'avg_sentiment'):.2f}" if stats is not None else "-"
            high_crit = str(urgent) if stats is not None else "-"
            lines.append(f"{name:<{self.MERGED_THEME}}{status:<{self.MERGED_STATUS}}"
                         f"{count:<{self.MERGED_COUNT}}{avg:>{self.MERGED_SENT}}"
                         f"{high_crit:>{self.MERGED_URGENT}}{self.MERGED_GAP}{priority}")
        return lines + ["", "AVG SENT = average sentiment, H+C = high + critical entries"]

    def _rows(self, result: Any, trend: Any) -> list[tuple]:
        """One (theme, stats, urgent_count, trend_row) tuple per theme to display.

        With a trend, its themes come first (including themes that disappeared
        since the last run); themes that are new this run follow.
        """
        stats = {self._get(s, "theme"): s for s in self._get(result, "themes", []) or []}
        current = [(name, s, self._urgent(s), None) for name, s in stats.items()]
        if not self._has_trend(trend):
            return current
        trend_rows = {self._get(r, "theme"): r for r in self._get(trend, "themes", []) or []}
        merged = [(name, stats.get(name),
                   self._urgent(stats[name]) if name in stats else None, row)
                  for name, row in trend_rows.items()]
        merged.extend(item for item in current if item[0] not in trend_rows)
        return merged

    def _show_review_queue(self, queue: Sequence[FeedbackRecord]) -> None:
        if not queue:
            self._block(["REVIEW QUEUE", "-" * self.WIDTH, "Nothing waiting for review."])
            return
        lines = ["REVIEW QUEUE",
                 f"{'ID':<{self.REVIEW_ID_WIDTH}}{'THEME':<{self.COLUMN_THEME}}"
                 f"{'REASON':<{self.REVIEW_REASON_WIDTH}}FEEDBACK",
                 "-" * self.WIDTH]
        for r in queue:
            theme = str(r.current_labels["theme"] or "-")
            # I show the Logic Manager's own reason text rather than interpreting it
            reason = self._short(r.review_reasons[0] if r.review_reasons else "-",
                                 self.REVIEW_REASON_WIDTH)
            text = self._short(self._display_text(r), self.REVIEW_SUMMARY_WIDTH)
            lines.append(f"{r.feedback_id:<{self.REVIEW_ID_WIDTH}}{theme:<{self.COLUMN_THEME}}"
                         f"{reason:<{self.REVIEW_REASON_WIDTH}}{text}")
        self._block(lines)

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _block(self, lines: Sequence[str]) -> None:
        """Print a blank line, then the lines, so blocks are visually separated."""
        if lines:
            self._write("")
            for line in lines:
                self._write(line)

    @staticmethod
    def _display_text(record: FeedbackRecord) -> str:
        """The AI's short summary if it wrote one, otherwise the raw text.

        It is never required: there is none while the AI is down or for older
        records, and a saved record is restored without checks, so anything that
        is not real text (blank, a number, a list) also falls back to the text."""
        summary = (record.ai or {}).get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
        return record.text

    @staticmethod
    def _tags(values) -> str:
        values = values or {}
        return " | ".join(str(values[k]) for k in LABEL_FIELDS if values.get(k) not in (None, ""))

    @classmethod
    def _wrap(cls, text: str) -> str:
        return textwrap.fill(cls._clean(str(text)), width=cls.WIDTH,
                             initial_indent="  ", subsequent_indent="  ")

    @staticmethod
    def _short(text: str, width: int) -> str:
        return textwrap.shorten(ConsoleView._clean(str(text)), width=width, placeholder="...")

    @staticmethod
    def _clean(text: str) -> str:
        """Swap typographic characters for plain ones; some terminals cannot print them."""
        return (text.replace("\u2011", "-").replace("\u2019", "'")
                    .replace("\u2013", "-").replace("\u2014", "-"))

    @staticmethod
    def _urgent(stats: Any) -> int:
        """High + critical entries for one theme, added up from its severity counts."""
        counts = ConsoleView._get(stats, "severity_counts", {}) or {}
        return counts.get(HIGH, 0) + counts.get(CRITICAL, 0)

    @staticmethod
    def _has_trend(trend: Any) -> bool:
        return trend is not None and bool(ConsoleView._get(trend, "has_previous"))

    @staticmethod
    def _get(item: Any, name: str, default: Any = None) -> Any:
        """Read a field from an object or a dictionary, with a default."""
        if item is None:
            return default
        if isinstance(item, dict):
            return item.get(name, default)
        return getattr(item, name, default)

    @staticmethod
    def _text(item: Any, name: str) -> str:
        """Display text of a change field such as {'text': '12 (+3)'}, or the plain value."""
        field = ConsoleView._get(item, name)
        if field is None:
            return "-"
        text = ConsoleView._get(field, "text")
        return str(text) if text is not None else str(field)

    @staticmethod
    def _number(value: Any) -> str:
        return f"{value:.2f}" if isinstance(value, float) else str(value)
