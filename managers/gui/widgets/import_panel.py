# ImportPanel: pick a CSV or JSON file and preview what I/O's importer accepts and rejects.

from dataclasses import replace
from html import escape

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton

from managers.io_manager import FeedbackImporter

from .card import Card

MAX_LISTED = 15
PREVIEWED = 5
FILE_FILTER = "Feedback files (*.csv *.json)"


# Shows the rows an import would add, the rejected rows with reasons, and IDs already saved.
# Emits import_ready(ImportResult) holding only the new records.
class ImportPanel(Card):
    import_ready = Signal(object)

    def __init__(self, importers, data, parent=None):
        super().__init__(padding=20, spacing=12, parent=parent)
        self.__importers = list(importers or [])
        self.__data = data
        self.__result = None

        hint = QLabel("A .csv or .json file with feedback_id, text, timestamp, theme, sentiment and "
                      "severity for every row. Rows with a problem are listed and left out.")
        hint.setObjectName("statusLine")
        hint.setWordWrap(True)
        self.__choose = QPushButton("Choose file…")
        self.__choose.clicked.connect(self.__on_choose)
        top = QHBoxLayout()
        top.addWidget(hint, 1)
        top.addWidget(self.__choose)

        self.__summary = QLabel("")
        self.__summary.setObjectName("cardTitle")
        self.__summary.setWordWrap(True)
        self.__details = QLabel("")
        self.__details.setObjectName("reasonList")
        self.__details.setWordWrap(True)
        self.__error = QLabel("")
        self.__error.setObjectName("errorText")
        self.__error.setWordWrap(True)
        self.__add = QPushButton("Add to queue")
        self.__add.setObjectName("primaryButton")
        self.__add.clicked.connect(self.__on_add)
        bottom = QHBoxLayout()
        bottom.addStretch()
        bottom.addWidget(self.__add)

        self.body.addLayout(top)
        self.body.addWidget(self.__summary)
        self.body.addWidget(self.__details)
        self.body.addWidget(self.__error)
        self.body.addLayout(bottom)
        if not self.__importers:
            self.__choose.setEnabled(False)
            self.__show_error("Importing isn't available here (no importers were given).")
        else:
            self.__clear()

    # Imports and previews one file; nothing is queued until Add to queue.
    def load_file(self, path: str) -> None:
        self.__clear()
        importer = FeedbackImporter.select(self.__importers, path)
        if importer is None:
            self.__show_error("Only .csv and .json files can be imported.")
            return
        try:
            result = importer.import_file(path)
        except (ValueError, OSError) as error:
            self.__show_error(f"Couldn't import {path}: {error}")
            return
        saved = {r.feedback_id for r in [*self.__data.load_records(), *self.__data.load_pending()]}
        new = [r for r in result.records if r.feedback_id not in saved]
        skipped = len(result.records) - len(new)
        self.__result = replace(result, records=new)

        parts = [f"{len(new)} ready"]
        if result.rejected:
            parts.append(f"{len(result.rejected)} rejected")
        if skipped:
            parts.append(f"{skipped} already saved")
        self.__summary.setText(f"{result.source_file}: {result.total} rows · {', '.join(parts)}")
        self.__details.setText(self.__describe(new, result.rejected, skipped))
        self.__add.setText(f"Add {len(new)} {'entry' if len(new) == 1 else 'entries'} to queue")
        self.__add.setEnabled(bool(new))

    # Lists rows an import rejected (QtFeedbackView.show_rejected_rows); nothing to queue.
    def show_rejected(self, rejected) -> None:
        self.__clear()
        rejected = list(rejected)
        self.__summary.setText(f"{len(rejected)} {'row was' if len(rejected) == 1 else 'rows were'} rejected")
        self.__details.setText(self.__describe([], rejected, 0))

    def __on_choose(self, *_args) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Import feedback", "", FILE_FILTER)
        if path:
            self.load_file(path)

    def __on_add(self, *_args) -> None:
        if self.__result is None or not self.__result.records:
            return
        result = self.__result
        self.import_ready.emit(result)
        self.__clear()
        self.__summary.setText(f"Queued {len(result.records)} entries from {result.source_file}.")
        self.__summary.show()

    @staticmethod
    def __describe(new, rejected, skipped) -> str:
        lines = []
        if rejected:
            lines.append("<b>Rejected rows</b>")
            lines += [f"Row {number}: {escape(reason)}" for number, reason in rejected[:MAX_LISTED]]
            if len(rejected) > MAX_LISTED:
                lines.append(f"…and {len(rejected) - MAX_LISTED} more")
        if skipped:
            lines.append(f"{skipped} rows have IDs that are already saved, so they are skipped.")
        if new:
            lines.append("<b>First entries</b>")
            for record in new[:PREVIEWED]:
                text = record.text if len(record.text) <= 70 else record.text[:69] + "…"
                lines.append(f"{escape(record.feedback_id)} · {escape(record.user['theme'])} · {escape(text)}")
        return "<br>".join(lines)

    def __clear(self) -> None:
        self.__result = None
        self.__summary.setText("No file chosen yet.")
        self.__details.clear()
        self.__error.hide()
        self.__add.setText("Add to queue")
        self.__add.setEnabled(False)

    def __show_error(self, text: str) -> None:
        self.__error.setText(text)
        self.__error.show()
