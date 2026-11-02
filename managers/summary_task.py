"""SummaryTask: call 2, summarising one run's aggregated stats."""

import json

from ai_task import AITask

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
    """One summary request for one run's stats."""

    def __init__(self, stats: dict, system_prompt: str):
        """stats is logic_manager.aggregate_themes' output."""
        super().__init__(
            SUMMARY_REQUEST_ID, "feedback_summary", SUMMARY_SCHEMA, SUMMARY_TOKEN_MARGIN, SUMMARY_MAX_COMPLETION_TOKENS
        )
        self.__stats = stats
        self.__system_prompt = system_prompt
        self.__theme_names = [theme["theme"] for theme in stats["themes"]]

    def build_messages(self) -> list[dict[str, str]]:
        """Return the chat messages for the summary request."""
        return [
            {"role": "system", "content": self.__system_prompt},
            {"role": "user", "content": json.dumps(self.__stats)},
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
