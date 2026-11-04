"""FeedbackRecord: one piece of feedback and what each manager adds to it."""

from typing import Self

from .constants import MATCHED, MISMATCH, PENDING, REVIEWED, SENTIMENTS, SEVERITIES, UNVERIFIED
from .serializable import Serializable


class FeedbackRecord(Serializable):
    """One piece of feedback. Each field has exactly one writer (design reference 5.2):

    - I/O: the constructor (feedback_id, text, timestamp, source_file, user)
    - AI: set_ai()
    - Logic: set_final(), add_review_reason(), clear_review()
    - Pipeline, for an admin's decision: mark_reviewed()

    Everyone else only reads the properties.
    """

    # reviewed is set only by mark_reviewed(), so Logic can never overwrite an admin's decision
    _LOGIC_VERIFICATION = (MATCHED, MISMATCH, UNVERIFIED)

    def __init__(
        self,
        feedback_id: str,
        text: str,
        timestamp: str,
        source_file: str | None,
        user: dict[str, str],
    ):
        self.__feedback_id = feedback_id
        self.__text = text
        self.__timestamp = timestamp
        self.__source_file = source_file
        self.__user = dict(user)
        self.__ai = None
        # final values stay None until Logic checks the record
        self.__theme = None
        self.__sentiment = None
        self.__severity = None
        self.__verification = PENDING
        self.__review_reasons = []
        self.__excluded = False

    @property
    def feedback_id(self) -> str:
        return self.__feedback_id

    @property
    def text(self) -> str:
        return self.__text

    @property
    def timestamp(self) -> str:
        """When it was written, YYYY-MM-DDTHH:MM:SS."""
        return self.__timestamp

    @property
    def source_file(self) -> str | None:
        """The imported file's name, or None if the feedback was typed in."""
        return self.__source_file

    @property
    def user(self) -> dict[str, str]:
        """The writer's own theme, sentiment and severity (a copy)."""
        return dict(self.__user)

    @property
    def ai(self) -> dict[str, str] | None:
        """The AI's theme, sentiment and severity (a copy), or None if the AI failed or has not run."""
        return dict(self.__ai) if self.__ai is not None else None

    @property
    def theme(self) -> str | None:
        """Final theme used in statistics; None until Logic checks the record."""
        return self.__theme

    @property
    def sentiment(self) -> str | None:
        return self.__sentiment

    @property
    def severity(self) -> str | None:
        return self.__severity

    @property
    def verification(self) -> str:
        """One of VERIFICATION: how the final values were decided."""
        return self.__verification

    @property
    def review_reasons(self) -> list[str]:
        """Why the record was flagged (a copy)."""
        return list(self.__review_reasons)

    @property
    def needs_review(self) -> bool:
        return bool(self.__review_reasons)

    @property
    def counted(self) -> bool:
        """True once Logic has checked the record and no reason excludes it from statistics."""
        return self.__verification != PENDING and not self.__excluded

    def set_ai(self, theme: str, sentiment: str, severity: str) -> None:
        """AI: stores the AI's values. Raises ValueError for a value not in the constants."""
        self.__check_values(theme, sentiment, severity)
        self.__ai = {"theme": theme, "sentiment": sentiment, "severity": severity}

    def set_final(self, theme: str, sentiment: str, severity: str, verification: str) -> None:
        """Logic: stores the final values and the verification result
        (matched, mismatch or unverified). Raises ValueError for any other value."""
        self.__check_values(theme, sentiment, severity)
        if verification not in self._LOGIC_VERIFICATION:
            raise ValueError(
                f"verification must be one of {self._LOGIC_VERIFICATION}, got {verification!r} "
                "(an admin's decision goes through mark_reviewed)"
            )
        self.__theme, self.__sentiment, self.__severity = theme, sentiment, severity
        self.__verification = verification

    def add_review_reason(self, reason: str, excludes: bool) -> None:
        """Logic: flags the record. excludes=True also stops it being counted."""
        self.__review_reasons.append(reason)
        if excludes:
            self.__excluded = True

    def clear_review(self) -> None:
        """Logic: removes every reason before the rules run again."""
        self.__review_reasons = []
        self.__excluded = False

    def mark_reviewed(self, theme: str, sentiment: str, severity: str) -> None:
        """Pipeline: applies an admin's decision. The record is counted from now on."""
        self.__check_values(theme, sentiment, severity)
        self.__theme, self.__sentiment, self.__severity = theme, sentiment, severity
        self.__verification = REVIEWED
        self.clear_review()

    def to_dict(self) -> dict:
        return {
            "feedback_id": self.__feedback_id,
            "text": self.__text,
            "timestamp": self.__timestamp,
            "source_file": self.__source_file,
            "user": self.user,
            "ai": self.ai,
            "theme": self.__theme,
            "sentiment": self.__sentiment,
            "severity": self.__severity,
            "verification": self.__verification,
            "review_reasons": self.review_reasons,
            "needs_review": self.needs_review,
            "counted": self.counted,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Rebuilds a record saved by to_dict(). Values are restored as saved,
        not checked: RecordValidator reports bad ones. Raises KeyError if
        feedback_id, text, timestamp or user is missing."""
        record = cls(data["feedback_id"], data["text"], data["timestamp"],
                     data.get("source_file"), data["user"])
        record.__ai = dict(data["ai"]) if data.get("ai") is not None else None
        record.__theme = data.get("theme")
        record.__sentiment = data.get("sentiment")
        record.__severity = data.get("severity")
        record.__verification = data.get("verification", PENDING)
        record.__review_reasons = list(data.get("review_reasons", []))
        record.__excluded = not data.get("counted", False)
        return record

    def __repr__(self) -> str:
        return f"FeedbackRecord({self.__feedback_id!r}, verification={self.__verification!r})"

    @staticmethod
    def __check_values(theme: str, sentiment: str, severity: str) -> None:
        """Raises ValueError unless the theme is non-empty text and the
        sentiment and severity are allowed values."""
        if not isinstance(theme, str) or not theme.strip():
            raise ValueError(f"theme must be non-empty text, got {theme!r}")
        if sentiment not in SENTIMENTS:
            raise ValueError(f"sentiment must be one of {SENTIMENTS}, got {sentiment!r}")
        if severity not in SEVERITIES:
            raise ValueError(f"severity must be one of {SEVERITIES}, got {severity!r}")
