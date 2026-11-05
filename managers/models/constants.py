"""Allowed values shared by every manager. Import them from managers.models."""

# The 8 base themes. Known themes = these plus themes an admin has confirmed
# (data.load_known_themes()).
THEMES = (
    "Teaching Quality",
    "Assessment",
    "Facilities",
    "Administration",
    "Well-being",
    "Social Environment",
    "Workload",
    "Internship Placement",
)

# Labels with no real theme ("other", "n/a", "spam") become this; it never counts as a match.
UNCLEAR_THEME = "Unclear"

# Use these names instead of typing the strings (ground rule 6).
POSITIVE, NEUTRAL, NEGATIVE = "positive", "neutral", "negative"
SENTIMENTS = (POSITIVE, NEUTRAL, NEGATIVE)

LOW, MEDIUM, HIGH, CRITICAL = "low", "medium", "high", "critical"
# Order matters: the user/AI cross-check treats neighbours as one step apart.
SEVERITIES = (LOW, MEDIUM, HIGH, CRITICAL)

# FeedbackRecord.verification values (design reference 7.1).
PENDING, MATCHED, MISMATCH, UNVERIFIED, REVIEWED = (
    "pending", "matched", "mismatch", "unverified", "reviewed"
)
VERIFICATION = (PENDING, MATCHED, MISMATCH, UNVERIFIED, REVIEWED)
