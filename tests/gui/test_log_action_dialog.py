import re

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QLineEdit  # noqa: E402

from managers.gui.dialogs.log_action_dialog import LogActionDialog  # noqa: E402
from managers.models import THEMES  # noqa: E402


def make_dialog(qtbot, theme=None):
    dialog = LogActionDialog(list(THEMES), theme=theme)
    qtbot.addWidget(dialog)
    return dialog


def test_empty_description_shows_the_error_and_builds_nothing(qtbot):
    dialog = make_dialog(qtbot)
    dialog.accept()
    assert dialog.action is None
    assert "description" in dialog.error_text


def test_valid_input_builds_an_action(qtbot):
    dialog = make_dialog(qtbot, theme="Facilities")
    dialog.findChild(QLineEdit, "descriptionEdit").setText("Upgraded library Wi-Fi")
    dialog.findChild(QLineEdit, "keywordEdit").setText("  wifi ")
    dialog.accept()
    action = dialog.action
    assert action is not None
    assert action.theme == "Facilities"
    assert action.keyword == "wifi"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", action.action_date)
    assert action.action_id.startswith("act_")
