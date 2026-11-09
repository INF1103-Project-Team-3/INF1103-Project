"""SummaryTask: call 2, summarising one run's stats and the counted records' one-liners."""

import json

from managers.models import FeedbackRecord, SEVERITIES

from .ai_task import AITask

MAX_OVERALL_SUMMARY_WORDS = 120  # overall_summary; the prompt aims for ~80
MAX_ACTION_WORDS = 30  # each suggested_action
SUMMARY_REQUEST_ID = "summary"  # call 2's entry in the token ledger
# Reasoning counts as output. Without an explicit limit Groq stops at 3,072
# output tokens, and call 2 can reason past that before writing any JSON
# (2026-10-06: every such request failed with json_validate_failed). Call 1
# stays well under it and keeps the default.
SUMMARY_MAX_COMPLETION_TOKENS = 5000
# A call 2 attempt uses ~4,200-5,200 tokens, or ~7,400 if it reaches the
# output cap, so a retry waits for the reset unless this many remain.
SUMMARY_TOKEN_MARGIN = 5000
# A counted record with no one-liner (call 1 failed while the API was down, or
# it was saved before call 1 wrote one) sends its raw text instead, cut to
# this many characters so one entry costs about as much as a few one-liners (D18).
MAX_TEXT_CHARS = 300
# Size limit on the user message, in characters of the JSON sent (D19), about
# 55 one-liners. Measured live on 2026-11-10 against Groq's 8,000 tokens-per-
# minute limit: an 8,522-char input was accepted, 13,440 was refused (HTTP 413),
# and the same 11,938-char input was estimated at 7,556 then 8,956 tokens, so
# Groq's estimate varies and the limit sits below the one size seen to pass.
# None would send every example, as Part 1 did.
MAX_INPUT_CHARS = 8_000

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_summary": {"type": "string"},
        "theme_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "theme": {"type": "string"},
                    "suggested_action": {"type": "string"},
                },
                "required": ["theme", "suggested_action"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["overall_summary", "theme_actions"],
    "additionalProperties": False,
}


class SummaryTask(AITask):
    """One summary request for one run.

    The input keeps Part 1's shape, which summary_prompt.txt was tuned on:
    the run's counts, then per theme its counts and an example per counted
    record, each pairing the record's severity with its one-line summary.
    """

    def __init__(
        self,
        stats: dict,
        records: list[FeedbackRecord],
        system_prompt: str,
        max_input_chars: int | None = MAX_INPUT_CHARS,
    ):
        """stats is AggregationResult.to_dict()'s output; records are the
        run's records, of which only the counted ones become examples."""
        super().__init__(
            SUMMARY_REQUEST_ID, "feedback_summary", SUMMARY_SCHEMA, SUMMARY_TOKEN_MARGIN, SUMMARY_MAX_COMPLETION_TOKENS
        )
        self.__system_prompt = system_prompt
        self.__theme_names = [theme["theme"] for theme in stats["themes"]]
        self.__payload = self._build_payload(stats, records, max_input_chars)

    def build_messages(self) -> list[dict[str, str]]:
        """Return the chat messages for the summary request."""
        return [
            {"role": "system", "content": self.__system_prompt},
            {"role": "user", "content": json.dumps(self.__payload)},
        ]

    def validate(self, result: object) -> bool:
        """Return True if result is a valid summary of this run's themes.

        Strict mode guarantees the shape but not what its schema subset cannot
        express: one action per input theme, in input order with the exact
        name, no empty text, and the word limits.
        """
        if not isinstance(result, dict) or set(result) != set(SUMMARY_SCHEMA["required"]):
            return False
        actions = result["theme_actions"]
        return (
            isinstance(result["overall_summary"], str)
            and result["overall_summary"].strip() != ""
            and len(result["overall_summary"].split()) <= MAX_OVERALL_SUMMARY_WORDS
            and isinstance(actions, list)
            and all(
                isinstance(action, dict)
                and isinstance(action.get("theme"), str)
                and isinstance(action.get("suggested_action"), str)
                for action in actions
            )
            and [action["theme"] for action in actions] == self.__theme_names
            and all(action["suggested_action"].strip() != "" for action in actions)
            and all(len(action["suggested_action"].split()) <= MAX_ACTION_WORDS for action in actions)
        )

    def _build_payload(self, stats: dict, records: list[FeedbackRecord], max_input_chars: int | None) -> dict:
        """Return the user message payload in Part 1's shape.

        AggregationResult names the run's sentiment totals sentiment_counts;
        they go out as sentiment_distribution, the name the prompt explains,
        and fields the prompt does not describe (priority, unverified,
        pending_themes and the like) are left out (C35).
        """
        examples = self._group_examples(records)
        payload = {
            "total_entries": stats["total_entries"],
            "counted_entries": stats["counted_entries"],
            "sentiment_distribution": stats["sentiment_counts"],
            "themes": [
                {
                    "theme": theme["theme"],
                    "count": theme["count"],
                    "severity_counts": theme["severity_counts"],
                    "avg_sentiment": theme["avg_sentiment"],
                    "examples": examples.get(theme["theme"], []),
                }
                for theme in stats["themes"]
            ],
        }
        if max_input_chars is not None:
            self._trim(payload, max_input_chars)
        return payload

    def _group_examples(self, records: list[FeedbackRecord]) -> dict[str, list[dict[str, str]]]:
        """Return each theme's examples, most severe first.

        Only counted records are used, grouped by their final theme, the same
        grouping Logic counts by, so every example matches its theme's counts.
        The sort is stable, so equal severities keep the records' order.
        """
        by_theme = {}
        for record in records:
            if record.counted:
                by_theme.setdefault(record.theme, []).append(self._example(record))
        for examples in by_theme.values():
            examples.sort(key=lambda example: SEVERITIES.index(example["severity"]), reverse=True)
        return by_theme

    def _example(self, record: FeedbackRecord) -> dict[str, str]:
        """Return one record's example: its final severity and its one-liner.

        A record with no one-liner sends its raw text under the same key,
        cut to MAX_TEXT_CHARS, so the prompt needs no second kind of example.
        """
        summary = (record.ai or {}).get("summary")
        if not summary:
            summary = record.text[:MAX_TEXT_CHARS]
        return {"severity": record.severity, "summary": summary}

    def _trim(self, payload: dict, max_input_chars: int) -> None:
        """Drop examples until the payload fits in max_input_chars (D19).

        Each step drops the least severe example left, taking it from the
        theme with the most examples, so small themes keep their voice; every
        theme keeps at least one, so its suggested_action has something to
        rest on. If the payload still does not fit, it is sent as it is: call
        2 may then fail, and the last summary stays. When anything was
        dropped, examples_shown and examples_total tell the model so.
        """
        total = sum(len(theme["examples"]) for theme in payload["themes"])
        shown = total
        while self._size(payload, shown, total) > max_input_chars:
            theme = self._next_to_trim(payload["themes"])
            if theme is None:
                break
            theme["examples"].pop()  # the theme's least severe, as each list is sorted most severe first
            shown -= 1
        if shown < total:
            payload["examples_shown"] = shown
            payload["examples_total"] = total

    def _next_to_trim(self, themes: list[dict]) -> dict | None:
        """Return the theme to drop an example from next, or None if every theme is down to one.

        The candidate is each theme's last (least severe) example. The least
        severe candidate goes first; among equals, the theme with the most
        examples, and among those the first listed, i.e. the more frequent.
        """
        candidates = [theme for theme in themes if len(theme["examples"]) > 1]
        if not candidates:
            return None
        lowest = min(SEVERITIES.index(theme["examples"][-1]["severity"]) for theme in candidates)
        at_lowest = [theme for theme in candidates if SEVERITIES.index(theme["examples"][-1]["severity"]) == lowest]
        return max(at_lowest, key=lambda theme: len(theme["examples"]))

    def _size(self, payload: dict, shown: int, total: int) -> int:
        """Return the length of the user message, counting the shown/total fields once anything is dropped."""
        if shown < total:
            payload = {**payload, "examples_shown": shown, "examples_total": total}
        return len(json.dumps(payload))
