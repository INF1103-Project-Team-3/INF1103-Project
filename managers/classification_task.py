"""ClassificationTask: call 1, classifying one feedback entry."""

import json

from ai_task import AITask

MAX_SUMMARY_WORDS = 15  # each record's one-line summary field
# Wait for the reset once fewer tokens than this remain. Kept at the tested
# value, although measured call 1 requests average ~1,700 tokens (max 2,295).
CLASSIFY_TOKEN_MARGIN = 1600

# Strict mode requires every property in "required" and additionalProperties: false.
CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "theme": {"type": "string"},
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "summary": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["theme", "sentiment", "severity", "summary", "confidence"],
    "additionalProperties": False,
}


class ClassificationTask(AITask):
    """One classification request for one feedback entry."""

    def __init__(self, entry: dict[str, str], system_prompt: str, known_themes: list[str]):
        super().__init__(entry["feedback_id"], "feedback_classification", CLASSIFY_SCHEMA, CLASSIFY_TOKEN_MARGIN)
        self.__text = entry["text"]
        self.__system_prompt = system_prompt
        self.__known_themes = known_themes

    def build_messages(self) -> list[dict[str, str]]:
        """Return the chat messages for one classification request.

        json.dumps stops the feedback text breaking the payload structure;
        instructions written inside the text are handled by the prompt.
        """
        return [
            {"role": "system", "content": self.__system_prompt},
            {"role": "user", "content": json.dumps(self._build_user_payload())},
        ]

    def validate(self, result: object) -> bool:
        """Return True if result is a valid five-field classification.

        Strict mode guarantees the shape but not a non-empty theme and summary,
        the confidence range or the summary word limit, which its schema subset
        cannot express.
        """
        props = CLASSIFY_SCHEMA["properties"]
        return (
            isinstance(result, dict)
            and set(result) == set(CLASSIFY_SCHEMA["required"])
            and isinstance(result["theme"], str)
            and result["theme"].strip() != ""
            and result["sentiment"] in props["sentiment"]["enum"]
            and result["severity"] in props["severity"]["enum"]
            and isinstance(result["confidence"], (int, float))
            and 0.0 <= result["confidence"] <= 1.0
            and isinstance(result["summary"], str)
            and result["summary"].strip() != ""
            and len(result["summary"].split()) <= MAX_SUMMARY_WORDS
        )

    def _build_user_payload(self) -> dict[str, str | list[str]]:
        """Return the user message payload: the feedback text, plus coined themes if any."""
        payload: dict[str, str | list[str]] = {"text": self.__text}
        if self.__known_themes:  # omitted when empty, to avoid paying for an empty list
            payload["existing_new_themes"] = self.__known_themes
        return payload
