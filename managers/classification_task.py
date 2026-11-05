"""ClassificationTask: call 1, classifying one feedback entry."""

import json

from ai_task import AITask
from prompt_library import UNCLEAR_THEME

MAX_COINED_THEME_WORDS = 3  # a longer label would be sent back in every later request
SENTIMENTS = ["positive", "neutral", "negative"]
SEVERITIES = ["low", "medium", "high", "critical"]
# Wait for the reset once fewer tokens than this remain. Kept at the tested
# value, although measured call 1 requests average ~1,700 tokens (max 2,295).
CLASSIFY_TOKEN_MARGIN = 1600


class ClassificationTask(AITask):
    """One classification request for one feedback entry.

    Only the entry's text and labels the model coined earlier go in the request,
    so human tags cannot anchor the model.
    """

    def __init__(self, entry: dict, system_prompt: str, themes: list[str], known_themes: list[str]):
        super().__init__(entry["feedback_id"], "feedback_classification", self._build_schema(), CLASSIFY_TOKEN_MARGIN)
        self.__text = entry["text"]
        self.__system_prompt = system_prompt
        self.__themes = themes
        self.__known_themes = known_themes
        self.__labels_by_key = {self._match_key(label): label for label in [*themes, UNCLEAR_THEME]}

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
        """Return True if result is a valid classification.

        Strict mode guarantees the shape, but not a non-empty theme or the length
        of a coined theme, which its schema subset cannot express.
        """
        if not isinstance(result, dict) or set(result) != set(self.schema["required"]):
            return False
        return (
            isinstance(result["theme"], str)
            and result["theme"].strip() != ""
            and (result["theme"] in self.__themes or len(result["theme"].split()) <= MAX_COINED_THEME_WORDS)
            and result["sentiment"] in SENTIMENTS
            and result["severity"] in SEVERITIES
        )

    def _clean(self, result: object) -> object:
        """Replace a spelling variant of a listed theme with its exact label.

        Matches on spelling only, so synonyms and plurals stay coined; merging
        on meaning is a labelling decision.
        """
        if isinstance(result, dict) and isinstance(result.get("theme"), str):
            result["theme"] = self.__labels_by_key.get(self._match_key(result["theme"]), result["theme"])
        return result

    def _match_key(self, label: str) -> str:
        """Return label in lowercase with only its letters and digits."""
        return "".join(character for character in label.lower() if character.isalnum())

    def _build_user_payload(self) -> dict[str, str | list[str]]:
        """Return the user message payload: the feedback text, plus coined themes if any."""
        payload: dict[str, str | list[str]] = {"text": self.__text}
        if self.__known_themes:  # omitted when empty, to avoid paying for an empty list
            payload["existing_new_themes"] = self.__known_themes
        return payload

    def _build_schema(self) -> dict:
        """Return the output schema. theme is free text, so the model can coin one.

        Strict mode requires every property in "required" and additionalProperties: false.
        """
        return {
            "type": "object",
            "properties": {
                "theme": {"type": "string"},
                "sentiment": {"type": "string", "enum": SENTIMENTS},
                "severity": {"type": "string", "enum": SEVERITIES},
            },
            "required": ["theme", "sentiment", "severity"],
            "additionalProperties": False,
        }
