"""
Shared fake data, shaped exactly like what ai_manager.classify_entry() will
eventually return (see doc section 3.5). Every manager can import
SAMPLE_RECORDS to test against before ai_manager is actually linked in --
that way everyone's testing against the same fake data, not their own
one-off dicts.

Deliberately includes edge cases, not just the happy path: critical
severity, low confidence, a confidence exactly at the 0.5 boundary, and a
theme outside the fixed six (see "new themes" in the doc's open decisions).
"""

SAMPLE_RECORDS = [
    {
        "feedback_id": "fb_001",
        "text": "I can't keep up with the lecturer's slides, they move way too fast for me to take proper notes.",
        "timestamp": "2026-09-15T10:32:00",
        "theme": "Pacing",
        "sentiment": "negative",
        "severity": "medium",
        "summary": "Student struggles to keep up with fast-paced slides.",
        "confidence": 0.92,
    },
    {
        "feedback_id": "fb_002",
        "text": "The lecturer speaks so fast I genuinely cannot take notes, it's been like this all semester.",
        "timestamp": "2026-09-15T11:05:00",
        "theme": "Pacing",
        "sentiment": "negative",
        "severity": "high",
        "summary": "Persistent difficulty keeping up with lecture speed all semester.",
        "confidence": 0.88,
    },
    {
        "feedback_id": "fb_003",
        "text": "Someone in my project group keeps sending me threatening messages and I don't feel safe coming to campus.",
        "timestamp": "2026-09-15T14:12:00",
        "theme": "Social Environment",
        "sentiment": "negative",
        "severity": "critical",
        "summary": "Student receives threatening messages from a groupmate and feels unsafe on campus.",
        "confidence": 0.93,
    },
    {
        "feedback_id": "fb_004",
        "text": "asdkj not sure what to say here, idk",
        "timestamp": "2026-09-15T15:00:00",
        "theme": "Unclear",
        "sentiment": "neutral",
        "severity": "low",
        "summary": "No meaningful feedback provided.",
        "confidence": 0.15,  # below CONFIDENCE_MIN -> excluded from counted stats
    },
    {
        "feedback_id": "fb_005",
        "text": "The new lab benches are great, so much more space.",
        "timestamp": "2026-09-15T16:20:00",
        "theme": "Facilities",
        "sentiment": "positive",
        "severity": "low",
        "summary": "Student likes the extra space at the new lab benches.",
        "confidence": 0.95,
    },
    {
        "feedback_id": "fb_006",
        "text": "Marking criteria for the last assignment weren't clear at all.",
        "timestamp": "2026-09-16T09:10:00",
        "theme": "Assessment",
        "sentiment": "negative",
        "severity": "medium",
        "summary": "Unclear marking criteria for the last assignment.",
        "confidence": 0.80,
    },
    {
        "feedback_id": "fb_007",
        "text": "Lecture speed has been fine this week actually, easier to follow.",
        "timestamp": "2026-09-16T10:45:00",
        "theme": "Pacing",  # AI could plausibly have labelled this "Lecture Speed" instead -- worth watching for fragmentation
        "sentiment": "positive",
        "severity": "low",
        "summary": "Student found this week's lecture pace easier to follow.",
        "confidence": 0.78,
    },
    {
        "feedback_id": "fb_008",
        "text": "Timetable clash between two required modules again this term.",
        "timestamp": "2026-09-16T13:30:00",
        "theme": "Administration",
        "sentiment": "negative",
        "severity": "high",
        "summary": "Timetable clash between two required modules.",
        "confidence": 0.50,  # exactly at CONFIDENCE_MIN -- boundary case
    },
]