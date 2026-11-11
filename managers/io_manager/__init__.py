"""The I/O Manager package: everything a person types in or sees in the terminal.

I re-export the public classes, so other code can write
`from managers.io_manager import IOManager`. Everything else is
an internal helper. One class per file, named after the class.

  Entry point       : IOManager (runs one session, returns a SessionResult)
  What it returns   : SessionResult, ReviewDecision
  Display           : FeedbackView (interface), ConsoleView (terminal)
  Input             : Prompter (AppEngine creates it and passes it in)
  Checking input    : EntryValidator, ThemeValidator, PasswordValidator
  Building objects  : RecordBuilder (feedback records and actions)
  Importing files   : FeedbackImporter (abstract), CsvImporter, JsonImporter,
                      ImportResult (what one import produced)

Internal: EntryForm, ReviewSession, InputValidator (interface),
ChoiceValidator, TextValidator.
"""
from .console_view import ConsoleView
from .csv_importer import CsvImporter
from .entry_validator import EntryValidator
from .feedback_importer import FeedbackImporter
from .feedback_view import FeedbackView
from .import_result import ImportResult
from .io_manager import IOManager
from .json_importer import JsonImporter
from .password_validator import PasswordValidator
from .prompter import Prompter
from .record_builder import RecordBuilder
from .review_decision import ReviewDecision
from .session_result import SessionResult
from .theme_validator import ThemeValidator

__all__ = [
    "IOManager", "SessionResult", "ReviewDecision", "FeedbackView", "ConsoleView", "Prompter",
    "FeedbackImporter", "CsvImporter", "JsonImporter", "ImportResult", "EntryValidator",
    "ThemeValidator", "PasswordValidator", "RecordBuilder",
]
