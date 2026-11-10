# Which tags (pills) a record shows, and the plain-English line for each review reason.

from datetime import datetime

from managers.models import CRITICAL, MATCHED, MISMATCH, PENDING, REVIEWED, SEVERITIES, UNVERIFIED

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


# (text, pill kind) for one review reason.
def reason_tag(reason: str) -> tuple[str, str]:
    lowered = reason.lower()
    if lowered.startswith("critical"):
        return "Critical", "critical"
    if "theme" in lowered and "unrecognised" in lowered:
        return reason, "caution"
    if "theme" in lowered:
        return reason, "info"
    return reason, "warn"


# Flagged records show their reasons (critical first); others show their status.
def record_tags(record) -> list[tuple[str, str]]:
    if record.needs_review:
        tags = [reason_tag(reason) for reason in record.review_reasons]
        return sorted(tags, key=lambda tag: tag[1] != "critical")
    return [STATUS_TAGS.get(record.verification, (record.verification.capitalize(), "neutral"))]


# One bullet for the detail panel, e.g. "Severity gap: low vs critical is 3 levels apart.".
def explain_reason(reason: str, record) -> str:
    user, ai = record.user, record.ai or {}
    lowered = reason.lower()
    if lowered.startswith("critical"):
        if ai.get("severity") == CRITICAL:
            return f"<b>Critical:</b> the AI rated this critical (the student chose {user.get('severity')})."
        return f"<b>Critical:</b> the student rated this critical (the AI chose {ai.get('severity', '—')})."
    if "severity" in lowered and ai.get("severity"):
        gap = abs(SEVERITIES.index(user["severity"]) - SEVERITIES.index(ai["severity"]))
        return f"<b>{reason}:</b> {user['severity']} vs {ai['severity']} is {gap} levels apart."
    for field in ("theme", "sentiment"):
        if field in lowered and ai.get(field):
            return f"<b>{reason}:</b> the student chose {user[field]}, the AI chose {ai[field]}."
    return f"<b>{reason}</b>"


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
