# RecordTags: which tags (pills) a record shows, and the plain-English line for each review reason.

from html import escape

from managers.models import CRITICAL, MATCHED, MISMATCH, PENDING, REVIEWED, UNVERIFIED


class RecordTags:
    STATUS_TAGS = {
        MATCHED: ("Matched", "good"),
        REVIEWED: ("Reviewed", "info"),
        UNVERIFIED: ("Unverified", "caution"),
        PENDING: ("Waiting for AI", "neutral"),
        MISMATCH: ("Mismatch", "warn"),
    }

    # How each of Logic's reasons starts -> (short pill text, pill kind).
    REASON_TAGS = (
        ("critical", ("Critical", "critical")),
        ("new theme", ("New theme", "info")),
        ("unclear theme", ("Unclear theme", "caution")),
        ("ai disagrees", ("AI disagrees", "warn")),
    )

    @staticmethod
    def is_critical(record) -> bool:
        ai = record.ai or {}
        return CRITICAL in (record.user.get("severity"), ai.get("severity"), record.severity)

    # (text, pill kind) for one review reason; an unknown reason shows as it is.
    @classmethod
    def reason_tag(cls, reason: str) -> tuple[str, str]:
        lowered = reason.lower()
        for start, tag in cls.REASON_TAGS:
            if lowered.startswith(start):
                return tag
        return reason, "warn"

    # Flagged records show their reasons (critical first); others show their status.
    @classmethod
    def tags(cls, record) -> list[tuple[str, str]]:
        if record.needs_review:
            tags = [cls.reason_tag(reason) for reason in record.review_reasons]
            return sorted(tags, key=lambda tag: tag[1] != "critical")
        return [cls.STATUS_TAGS.get(record.verification, (record.verification.capitalize(), "neutral"))]

    # One bullet for the detail panel: the pill text, then Logic's reason exactly as it wrote it.
    @classmethod
    def explain_reason(cls, reason: str) -> str:
        label, _kind = cls.reason_tag(reason)
        if label == reason:
            return f"<b>{escape(reason)}</b>"
        return f"<b>{escape(label)}:</b> {escape(reason)}"
