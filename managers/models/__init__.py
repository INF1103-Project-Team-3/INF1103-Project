"""Shared data classes and allowed values used by every manager."""

from .constants import (
    CRITICAL, HIGH, LOW, MATCHED, MEDIUM, MISMATCH, NEGATIVE, NEUTRAL, PENDING, POSITIVE,
    REVIEWED, SENTIMENTS, SEVERITIES, THEMES, UNCLEAR_THEME, UNVERIFIED, VERIFICATION,
)
from .feedback_record import FeedbackRecord
from .serializable import Serializable
