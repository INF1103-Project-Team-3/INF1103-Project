from __future__ import annotations

import uuid
from datetime import datetime
from typing import Callable, Mapping

from managers.models import LABEL_FIELDS, TIMESTAMP_FORMAT, Action, FeedbackRecord


class RecordBuilder:
    """Creates the two model objects the input side owns: FeedbackRecord and Action.

    Both need a generated ID and a timestamp, so I keep those rules in this one
    place, and the console forms, the importers and the GUI all build objects
    through me. For a record I only fill in the input side's fields (ID, text,
    timestamp, source file and the writer's own labels); the AI, Logic and the
    pipeline fill in the rest later, so each field keeps one writer.
    """

    def __init__(self, clock: Callable[[], datetime] = datetime.now):
        self._clock = clock         # a parameter so a test can pass a fixed time

    def build(self, entry: Mapping[str, str], user: Mapping[str, str] | None = None,
              source_file: str | None = None) -> FeedbackRecord:
        """Build one record from a checked entry.

        Imported rows already carry a feedback_id and timestamp, so I keep them;
        typed feedback has only its text, so I create a new ID and use the
        current time. user is the writer's theme, sentiment and severity; if it
        is not given I take them from entry.
        """
        if user is None:
            user = {name: entry[name] for name in LABEL_FIELDS}
        return FeedbackRecord(
            entry.get("feedback_id") or self._new_id("fb"),
            entry["text"],
            entry.get("timestamp") or self._now(),
            source_file,
            dict(user))

    def build_action(self, theme: str, description: str, action_date: str,
                     keyword: str | None = None) -> Action:
        """Build one Action. Action checks its own fields and raises ValueError if one is bad."""
        return Action(self._new_id("act"), theme, description, action_date,
                      keyword or None, self._now())

    @staticmethod
    def _new_id(prefix: str) -> str:
        """e.g. fb_1a2b3c4d: short enough to type into a search, random enough not to clash."""
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    def _now(self) -> str:
        return self._clock().strftime(TIMESTAMP_FORMAT)
