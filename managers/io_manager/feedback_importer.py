from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from .entry_validator import EntryValidator
from .import_result import ImportResult
from .record_builder import RecordBuilder

if TYPE_CHECKING:
    from managers.data_manager import DataManager


class FeedbackImporter(ABC):
    """Abstract base class for importing feedback rows from a file.

    import_file() is a template method: it holds every step the file types
    share (ask Data for the rows, check them, build records from the good ones).
    A subclass fills in only what really differs between file types:
      - extension     which files it handles
      - _row_problem  what can be wrong with a row's shape in that format

    So a new file type is one small subclass, and neither this class nor the
    code that calls it changes (Open/Closed Principle).

    I never open the file myself: Data reads and parses it through
    data.read_rows(), because file access is the Data Manager's job.
    """

    def __init__(self, data: "DataManager", validator: EntryValidator,
                 builder: RecordBuilder):
        self._data = data
        self._validator = validator     # shared with the GUI, so both apply the same rules
        self._builder = builder

    @property
    @abstractmethod
    def extension(self) -> str:
        """The file extension this importer handles, e.g. '.csv'."""

    @abstractmethod
    def _row_problem(self, raw: Any) -> str:
        """What is wrong with this row's shape in my file format, or "" if nothing."""

    @staticmethod
    def select(importers: Iterable["FeedbackImporter"], path: str) -> "FeedbackImporter | None":
        """The importer that handles this path's file type, or None if there is none.

        Polymorphism: the caller holds a list of FeedbackImporter and never
        checks the file type itself.
        """
        return next((i for i in importers if i.can_import(path)), None)

    def can_import(self, path: str) -> bool:
        return Path(path).suffix.lower() == self.extension

    def import_file(self, path: str) -> ImportResult:
        """Import one file. Raises ValueError if Data cannot read it or it has no rows."""
        rows = list(self._data.read_rows(path))
        if not rows:
            raise ValueError("the file has no rows")
        accepted, rejected = self._validator.validate_rows(rows, self._row_problem)
        source = Path(path).name
        records = [self._builder.build(entry, source_file=source) for entry in accepted]
        return ImportResult(source, records, rejected)
