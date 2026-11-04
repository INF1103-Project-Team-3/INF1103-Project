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
    "theme": "Teaching Quality",
    "sentiment": "negative",
    "severity": "medium",
    "summary": "Lecturer's slides move too fast, preventing the student from taking proper notes.",
    "confidence": 0.9,
    "agreement": 1.0
  },
  {
    "feedback_id": "fb_002",
    "text": "The new lab benches are great, so much more space to work with during practicals.",
    "timestamp": "2026-09-15T11:05:00",
    "theme": "Facilities",
    "sentiment": "positive",
    "severity": "low",
    "summary": "Student praises new lab benches for providing more space during practical sessions.",
    "confidence": 0.96,
    "agreement": 1.0
  },
  {
    "feedback_id": "fb_003",
    "text": "Marking criteria for the last assignment was never explained, so I had no idea what was expected.",
    "timestamp": "2026-09-15T13:47:00",
    "theme": "Assessment",
    "sentiment": "negative",
    "severity": "medium",
    "summary": "Student didn't receive marking criteria, leaving assignment expectations unclear.",
    "confidence": 0.92,
    "agreement": 1.0
  },
  {
    "feedback_id": "fb_004",
    "text": "Someone in my project group keeps sending me threatening messages and I don't feel safe coming to campus.",
    "timestamp": "2026-09-16T09:12:00",
    "theme": "Social Environment",
    "sentiment": "negative",
    "severity": "critical",
    "summary": "Student receives threatening messages from a groupmate and feels unsafe on campus.",
    "confidence": 0.96,
    "agreement": 1.0
  },
  {
    "feedback_id": "fb_005",
    "text": "The portal to check module timetables keeps timing out, I've had to retry five times this week.",
    "timestamp": "2026-09-16T14:20:00",
    "theme": "Administration",
    "sentiment": "negative",
    "severity": "medium",
    "summary": "Portal for timetables frequently times out, requiring multiple retries each week.",
    "confidence": 0.92,
    "agreement": 0.67
  },
  {
    "feedback_id": "fb_006",
    "text": "Everything feels like too much lately and the deadlines keep piling up, I don't know how I'll get through this semester.",
    "timestamp": "2026-09-17T08:03:00",
    "theme": "Well-being",
    "sentiment": "negative",
    "severity": "high",
    "summary": "Student feels overwhelmed by increasing deadlines and doubts managing the semester.",
    "confidence": 0.85,
    "agreement": 1.0
  },
  {
    "feedback_id": "fb_007",
    "text": "asdkjf aslkdjf woot lol",
    "timestamp": "2026-09-17T15:41:00",
    "theme": "Unclear",
    "sentiment": "neutral",
    "severity": "low",
    "summary": "Text contains no meaningful feedback.",
    "confidence": 0.0,
    "agreement": 1.0
  },
  {
    "feedback_id": "fb_008",
    "text": "It's fine I guess, could be better could be worse, hard to say really.",
    "timestamp": "2026-09-18T10:58:00",
    "theme": "Unclear",
    "sentiment": "neutral",
    "severity": "low",
    "summary": "Student expresses vague mixed feelings about experience, neither clearly positive nor negative.",
    "confidence": 0.4,
    "agreement": 1.0
  },
  {
    "feedback_id": "fb_010",
    "text": "The air conditioning in the lecture theatre has been broken for two weeks, it's unbearable sitting through a 2 hour class.",
    "timestamp": "2026-09-19T09:30:00",
    "theme": "Facilities",
    "sentiment": "negative",
    "severity": "high",
    "summary": "Broken air conditioning makes 2‑hour lecture unbearable for student.",
    "confidence": 0.92,
    "agreement": 0.67
  },
  {
    "feedback_id": "fb_011",
    "text": "The grading rubric for the group project was changed three days before submission without any announcement, we prepared for the wrong criteria entirely.",
    "timestamp": "2026-09-19T11:14:00",
    "theme": "Assessment",
    "sentiment": "negative",
    "severity": "high",
    "summary": "Rubric changed three days before deadline without notice, causing students to prepare for wrong criteria.",
    "confidence": 0.88,
    "agreement": 1.0
  },
  {
    "feedback_id": "fb_012",
    "text": "The tutorial goes over the same worked example three times, we've all understood it after the first pass, it's a waste of the session.",
    "timestamp": "2026-09-19T13:02:00",
    "theme": "Teaching Quality",
    "sentiment": "negative",
    "severity": "low",
    "summary": "Tutorial repeats example unnecessarily, wasting session time after students understand it.",
    "confidence": 0.9,
    "agreement": 0.67
  },
  {
    "feedback_id": "fb_013",
    "text": "My IWSP placement company has had me doing photocopying and data entry with nothing related to my course, for the past two months.",
    "timestamp": "2026-09-19T15:47:00",
    "theme": "Internship Placement",
    "sentiment": "negative",
    "severity": "medium",
    "summary": "Placement tasks are unrelated to the course, limited to photocopying and data entry.",
    "confidence": 0.85,
    "agreement": 0.67
  },
  {
    "feedback_id": "fb_014",
    "text": "Printing credits run out so fast every trimester, I end up paying out of pocket just to submit hard copy reports.",
    "timestamp": "2026-09-19T17:30:00",
    "theme": "Facilities",
    "sentiment": "negative",
    "severity": "medium",
    "summary": "Printing credits deplete each trimester, forcing student to pay out-of-pocket for required hard copies.",
    "confidence": 0.88,
    "agreement": 1.0
  },
  {
    "feedback_id": "fb_015",
    "text": "I've been feeling so overwhelmed lately that I don't see the point in continuing anymore, and I don't really know who I'm supposed to tell.",
    "timestamp": "2026-09-20T08:11:00",
    "theme": "Well-being",
    "sentiment": "negative",
    "severity": "critical",
    "summary": "Student feels overwhelming distress and sees no point continuing, uncertain whom to confide in.",
    "confidence": 0.96,
    "agreement": 1.0
  }
]