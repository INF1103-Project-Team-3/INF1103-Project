from __future__ import annotations

from typing import TYPE_CHECKING

from managers.models import SENTIMENTS, SEVERITIES, Action, FeedbackRecord

from .choice_validator import ChoiceValidator
from .feedback_view import FeedbackView
from .prompter import Prompter
from .record_builder import RecordBuilder
from .text_validator import TextValidator
from .theme_validator import ThemeValidator

if TYPE_CHECKING:
    from managers.data_manager import DataManager


class EntryForm:
    """Asks the person, question by question, for the two new things they can type in:
    a piece of feedback, or an action an admin took.

    I keep both in one class because they share the theme menu and the same way of
    working: ask, check each answer as it is typed, and build the object through
    the RecordBuilder. Each collect method returns the finished object, or None if
    the person quit part-way through.
    """

    OTHER_THEME_LABEL = "Other"     # last item of the theme menu; lets the person type a new theme
    MAX_DESCRIPTION_LENGTH = 200
    MAX_KEYWORD_LENGTH = 50

    def __init__(self, prompter: Prompter, view: FeedbackView, data: "DataManager",
                 theme_validator: ThemeValidator, builder: RecordBuilder):
        self._prompter = prompter
        self._view = view
        self._data = data
        self._theme_validator = theme_validator
        self._builder = builder
        self._text = TextValidator("text")
        self._sentiments = ChoiceValidator(SENTIMENTS)
        self._severities = ChoiceValidator(SEVERITIES)
        self._description = TextValidator("description", self.MAX_DESCRIPTION_LENGTH)
        # the keyword is optional and may be a number, so blank and no-letters are allowed
        self._keyword = TextValidator("keyword", self.MAX_KEYWORD_LENGTH,
                                      required=False, require_letter=False)

    def collect_feedback(self) -> FeedbackRecord | None:
        """Text, then the person's own theme, sentiment and severity for it."""
        text = self._prompter.ask_until_valid("Enter feedback (quit to cancel): ", self._text)
        if text is None:
            return None
        theme = self._pick_theme()
        if theme is None:
            return None
        sentiment = self._prompter.ask_until_valid(
            f"Sentiment ({'/'.join(SENTIMENTS)}): ", self._sentiments)
        if sentiment is None:
            return None
        severity = self._prompter.ask_until_valid(
            f"Severity ({'/'.join(SEVERITIES)}): ", self._severities)
        if severity is None:
            return None
        return self._builder.build(
            {"text": text}, {"theme": theme, "sentiment": sentiment, "severity": severity})

    def collect_action(self) -> Action | None:
        """A known theme, what was done, the date, and an optional keyword."""
        theme = self._pick_theme(allow_other=False)     # an action needs an existing theme
        if theme is None:
            return None
        description = self._prompter.ask_until_valid("What was done? ", self._description)
        if description is None:
            return None
        action_date = self._ask_date()
        if action_date is None:
            return None
        keyword = self._prompter.ask_until_valid(
            "Only measure feedback containing this word (Enter for all): ", self._keyword)
        if keyword is None:
            return None
        try:
            return self._builder.build_action(theme, description, action_date, keyword)
        except ValueError as exc:       # Action rejects any field it considers invalid
            self._view.show_message(f"  Invalid: {exc}")
            return None

    def _pick_theme(self, allow_other: bool = True) -> str | None:
        """Numbered menu of the known themes, plus "Other" to type a new one.

        The known themes come from the Data Manager (I only read them). A typed
        theme is cleaned up by the ThemeValidator.
        """
        options = list(self._data.load_known_themes())
        if allow_other:
            options.append(self.OTHER_THEME_LABEL)
        menu = "\n".join(["Theme:"] + [f"  {i}. {name}" for i, name in enumerate(options, 1)])
        self._view.show_message(menu)
        numbers = ChoiceValidator([str(i) for i in range(1, len(options) + 1)],
                                  error=f"enter a number from 1 to {len(options)}")
        choice = self._prompter.ask_until_valid(f"Choose a theme (1-{len(options)}): ", numbers)
        if choice is None:
            return None
        picked = options[int(choice) - 1]
        if allow_other and picked == self.OTHER_THEME_LABEL:
            return self._prompter.ask_until_valid("Type the theme: ", self._theme_validator)
        return picked

    def _ask_date(self) -> str | None:
        """Ask until a real calendar date written as YYYY-MM-DD is typed."""
        while True:
            answer = self._prompter.ask("Date of the action (YYYY-MM-DD): ")
            if answer is None:
                return None
            if Action.is_valid_date(answer):        # the Action decides what a valid date is
                return answer
            self._view.show_message("  Invalid: date must look like YYYY-MM-DD (e.g. 2026-11-05)")
