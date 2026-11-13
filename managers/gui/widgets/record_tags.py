# Which tags (pills) a record shows, and the plain-English line for each review reason.

from datetime import datetime
from html import escape

from managers.models import CRITICAL, MATCHED, MISMATCH, PENDING, REVIEWED, UNVERIFIED

STATUS_TAGS = {
    MATCHED: ("Matched", "good"),
    REVIEWED: ("Reviewed", "info"),
    UNVERIFIED: ("Unverified", "caution"),
    PENDING: ("Waiting for AI", "neutral"),
    MISMATCH: ("Mismatch", "warn"),
}


def is_critical(record) -> bool:
    ai = record.ai or {}
    return CRITICAL in (record.user.get("severity"), ai.get("severity"), record.severity)


# How each of Logic's reasons starts -> (short pill text, pill kind).
REASON_TAGS = (
    ("critical", ("Critical", "critical")),
    ("new theme", ("New theme", "info")),
    ("unclear theme", ("Unclear theme", "caution")),
    ("ai disagrees", ("AI disagrees", "warn")),
)


# (text, pill kind) for one review reason; an unknown reason shows as it is.
def reason_tag(reason: str) -> tuple[str, str]:
    lowered = reason.lower()
    for start, tag in REASON_TAGS:
        if lowered.startswith(start):
            return tag
    return reason, "warn"


# Flagged records show their reasons (critical first); others show their status.
def record_tags(record) -> list[tuple[str, str]]:
    if record.needs_review:
        tags = [reason_tag(reason) for reason in record.review_reasons]
        return sorted(tags, key=lambda tag: tag[1] != "critical")
    return [STATUS_TAGS.get(record.verification, (record.verification.capitalize(), "neutral"))]


# One bullet for the detail panel: the pill text, then Logic's reason exactly as it wrote it.
def explain_reason(reason: str) -> str:
    label, _kind = reason_tag(reason)
    if label == reason:
        return f"<b>{escape(reason)}</b>"
    return f"<b>{escape(label)}:</b> {escape(reason)}"


# "2026-10-05T09:15:00" -> "5 Oct"; anything else is shown as it is.
def short_date(timestamp: str) -> str:
    try:
        moment = datetime.fromisoformat(timestamp)
    except (TypeError, ValueError):
        return timestamp or ""
    return f"{moment.day} {moment:%b}"


# "2026-10-05T09:15:00" -> "5 Oct 2026, 09:15".
def long_date(timestamp: str) -> str:
    try:
        moment = datetime.fromisoformat(timestamp)
    except (TypeError, ValueError):
        return timestamp or ""
    return f"{moment.day} {moment:%b %Y, %H:%M}"
