# Runs the GUI on the real Data, Logic and AI through InterimPipeline: python -m demo.gui_live [--seed]

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtWidgets import QApplication

from managers.ai_manager import AIManager, GroqClient, PromptLibrary
from managers.data_manager import DataManager
from managers.gui import MainWindow, QtProgressReporter
from managers.gui.data_reader import DataReader
from managers.gui.style import app_font, light_palette
from managers.io_manager import (
    CsvImporter, EntryValidator, JsonImporter, PasswordValidator, RecordBuilder, SessionResult, ThemeValidator,
)
from managers.logic_manager import LogicManager

from .interim_pipeline import InterimPipeline

MANAGERS = Path(__file__).resolve().parent.parent / "managers"
DATA_DIR = MANAGERS / "live_data"
ENV_FILE = MANAGERS / "config" / ".env"
SAMPLES = Path(__file__).resolve().parent.parent / "tests" / "ai_manager_samples"
FALLBACK_PASSWORD = "admin"


# The AI Manager, or None (an AI-down run) when the key or its label is missing.
def build_ai(data: DataManager, reporter: QtProgressReporter) -> AIManager | None:
    key, label = os.environ.get("GROQ_API_KEY"), os.environ.get("GROQ_KEY_LABEL")
    if not (key and label):
        logging.warning("GROQ_API_KEY and GROQ_KEY_LABEL are not both set: running with the AI down.")
        return None
    system_template, summary_prompt = data.load_prompts()
    prompts = PromptLibrary(system_template, summary_prompt, data.load_known_themes())
    return AIManager(GroqClient(key), label, prompts, reporter, data.load_token_log, data.save_token_log)


# The 12 stress-test entries with their hand labels, checked and built by I/O.
def build_seed(data: DataManager, validator: EntryValidator, builder: RecordBuilder) -> SessionResult:
    labels = {row["feedback_id"]: row for row in data.read_rows(SAMPLES / "stress-ans-key.json")}
    rows = []
    for row in data.read_rows(SAMPLES / "stress-input.json"):
        label = labels.get(row["feedback_id"], {})
        rows.append({**row, **{field: label.get(field) for field in ("theme", "sentiment", "severity")}})
    accepted, rejected = validator.validate_rows(rows)
    for number, reason in rejected:
        logging.warning("Seed row %d rejected: %s", number, reason)
    records = [builder.build(entry, source_file="stress-input.json") for entry in accepted]
    return SessionResult(records=records, source_file="stress-input.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="FeedbackLens GUI on the real managers")
    parser.add_argument("--seed", action="store_true", help="import the 12 stress-test entries on start")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    load_dotenv(ENV_FILE)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    app.setFont(app_font())

    data = DataManager(str(DATA_DIR))
    logic = LogicManager()
    logic.set_known_themes(data.load_known_themes())
    reporter = QtProgressReporter()
    ai = build_ai(data, reporter)
    validator = EntryValidator(ThemeValidator(logic))
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        logging.warning("ADMIN_PASSWORD is not set: using the demo password '%s'.", FALLBACK_PASSWORD)
        password = FALLBACK_PASSWORD

    builder = RecordBuilder()
    importers = [CsvImporter(data, validator, builder), JsonImporter(data, validator, builder)]
    window = MainWindow(InterimPipeline(data, logic, ai), DataReader(data), logic, validator,
                        importers=importers, reporter=reporter, password=PasswordValidator(password))
    window.resize(1440, 900)
    window.show()
    if args.seed:
        window.run_pipeline(build_seed(data, validator, builder))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
