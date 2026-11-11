# Runs the GUI on sample data, with no API calls.

import sys

from PySide6.QtWidgets import QApplication

from managers.gui import MainWindow, QtProgressReporter
from managers.gui.style import app_font, light_palette

from .fake_data_manager import FakeDataManager
from .fake_pipeline import FakePipeline
from .sample_data import build_sample_actions, build_sample_history, build_sample_records, load_ai_answers

DEMO_PASSWORD = "admin"


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    app.setFont(app_font())
    reporter = QtProgressReporter()
    data = FakeDataManager(build_sample_records(), build_sample_actions(), build_sample_history())
    pipeline = FakePipeline(reporter, data, load_ai_answers())
    window = MainWindow(pipeline, data, logic=None, validators=None, importers=None, reporter=reporter,
                        check_password=lambda password: password == DEMO_PASSWORD)
    window.resize(1440, 900)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
