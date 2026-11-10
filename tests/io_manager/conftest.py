"""Shared fakes and helpers for the I/O Manager tests.

The tests never touch a live AI, the real Logic or Data Manager, or real files.
I replace each of them with a small fake that does only what the I/O side
calls, so every test is fast and only fails because of I/O code.
"""

import pytest

from managers.models import FeedbackRecord, THEMES, UNCLEAR_THEME
from managers.io_manager.console_view import ConsoleView
from managers.io_manager.prompter import Prompter


class FakeLogic:
    """Stands in for LogicManager. I/O only ever calls normalise_theme(), and the
    real rules belong to Logic, so this fake keeps just enough of them to test with:
    base themes in any case map to their real name, filler words become Unclear,
    and anything else is a new theme in title case. It also records each call."""

    FILLER_WORDS = ("other", "n/a", "none", "spam")

    def __init__(self):
        self.calls = []

    def normalise_theme(self, label):
        self.calls.append(label)
        known = {theme.lower(): theme for theme in THEMES}
        cleaned = label.strip()
        if cleaned.lower() in self.FILLER_WORDS:
            return UNCLEAR_THEME
        return known.get(cleaned.lower(), cleaned.title())


@pytest.fixture
def logic():
    return FakeLogic()


class Screen:
    """A ConsoleView whose output goes into a list instead of the terminal."""

    def __init__(self):
        self.lines = []
        self.view = ConsoleView(writer=self.lines.append)

    @property
    def text(self):
        return "\n".join(self.lines)


@pytest.fixture
def screen():
    return Screen()


@pytest.fixture
def make_record():
    """Factory for FeedbackRecords in any stage: just typed in, after the AI
    (ai=...), after Logic (final=(theme, sentiment, severity, verification))
    and flagged (reasons=[...])."""
    def make(feedback_id="fb_00000001", text="The library wifi keeps dropping",
             user=None, ai=None, final=None, reasons=()):
        record = FeedbackRecord(
            feedback_id, text, "2026-10-01T09:00:00", None,
            user or {"theme": "Facilities", "sentiment": "negative", "severity": "high"})
        if ai:
            record.set_ai(**ai)
        if final:
            record.set_final(*final)
        for reason in reasons:
            record.add_review_reason(reason, excludes=False)
        return record
    return make


class Script:
    """Plays the person at the keyboard: hands out the scripted answers in order
    and remembers every question asked. Running out of answers fails the test,
    which catches a flow that asks more questions than expected."""

    def __init__(self, answers=()):
        self._answers = list(answers)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if not self._answers:
            raise AssertionError(f"no scripted answer left for {prompt!r}")
        return self._answers.pop(0)

    @property
    def unused(self):
        return list(self._answers)


@pytest.fixture
def prompter(screen):
    """Factory: prompter(answers, secrets) gives a Prompter that reads typed
    answers from one Script and hidden ones (passwords) from another."""
    def make(answers=(), secrets=()):
        make.script, make.secret_script = Script(answers), Script(secrets)
        return Prompter(screen.view, make.script, make.secret_script)
    return make


class FakeData:
    """Stands in for DataManager with in-memory data only, no files. read_rows()
    returns rows the test put in `files` (a CSV row with too many cells keeps the
    extras under the key None, as csv.DictReader does), and raises ValueError
    for any other path, as the real one does for a missing or corrupt file."""

    def __init__(self):
        self.files = {}
        self.themes = list(THEMES)
        self.records = []
        self.queue = []
        self.objects = {}

    def read_rows(self, path):
        if path not in self.files:
            raise ValueError(f"cannot read {path}")
        return self.files[path]

    def load_known_themes(self):
        return list(self.themes)

    def search_records(self, query):
        return [r for r in self.records if query.lower() in r.text.lower()]

    def load_review_queue(self):
        return list(self.queue)

    def load_object(self, name):
        return self.objects.get(name)


@pytest.fixture
def data():
    return FakeData()
