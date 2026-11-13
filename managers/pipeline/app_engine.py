from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from managers.ai_manager import (
    AIManager,
    ConsoleProgressReporter,
    GroqClient,
    PromptLibrary,
)
from managers.data_manager import DataManager, JsonFileStore
from managers.io_manager import (
    ConsoleView,
    CsvImporter,
    EntryValidator,
    IOManager,
    JsonImporter,
    PasswordValidator,
    Prompter,
    RecordBuilder,
    ThemeValidator,
)
from managers.logic_manager import LogicManager

from .pipeline_context import PipelineContext
from .pipeline_manager import PipelineManager
from .steps import (
    AIClassificationStep,
    ImpactStep,
    IngestionStep,
    LogicStep,
    PersistenceStep,
    SummaryStep,
)

logger = logging.getLogger(__name__)

MANAGERS_DIR = Path(__file__).resolve().parents[1]      # .../managers
REPO_ROOT = MANAGERS_DIR.parent
ENV_FILE = MANAGERS_DIR / "config" / ".env"             # 4.3: config/ holds .env
DEFAULT_DATA_DIR = str(REPO_ROOT / "data")              # 4.3: "data", relative to the repo root


class AppEngine:
    def __init__(self, data_dir: str = DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self.data: DataManager | None = None
        self.logic: LogicManager | None = None
        self.ai: AIManager | None = None
        self.pipeline: PipelineManager | None = None

    @staticmethod
    def _load_env() -> None:
        # Safe to call twice: existing environment variables are not overwritten
        load_dotenv(ENV_FILE)

    def bootstrap_system(self, reporter: Any = None) -> PipelineContext:
        self._load_env()
        # D20: a missing key or key label never stops the run; the AI just reports it down
        api_key = os.getenv("GROQ_API_KEY", "")
        key_label = os.getenv("GROQ_KEY_LABEL", "")
        self.ai_ready = bool(api_key and key_label)
        if not api_key or not key_label:
            logger.warning("GROQ_API_KEY or GROQ_KEY_LABEL is not set in %s; "
                           "the AI will be unavailable this session", ENV_FILE)

        store = JsonFileStore()
        self.data = DataManager(self._data_dir, store)

        known_themes = self.data.load_known_themes()
        self.logic = LogicManager(known_themes=known_themes)

        sys_prompt, sum_prompt = self.data.load_prompts()
        prompts = PromptLibrary(sys_prompt, sum_prompt, themes=known_themes)
        client = GroqClient(api_key=api_key)
        active_reporter = reporter or ConsoleProgressReporter()

        self.ai = AIManager(
            client=client,
            key_label=key_label,
            prompts=prompts,
            reporter=active_reporter,
            load_token_log=self.data.load_token_log,
            save_token_log=self.data.save_token_log,
        )

        self.pipeline = PipelineManager(data_dir=self._data_dir)
        self.pipeline.register_step(IngestionStep(self.data, self.logic, self.ai))
        self.pipeline.register_step(AIClassificationStep(self.ai, self.data))
        self.pipeline.register_step(LogicStep(self.logic, self.data))
        self.pipeline.register_step(SummaryStep(self.ai, self.logic))
        self.pipeline.register_step(ImpactStep(self.logic, self.data))
        self.pipeline.register_step(PersistenceStep(self.data))

        return PipelineContext(data_dir=self._data_dir)

    def _build_io_parts(self):
        """Validators, builder and importers, shared by the terminal and the GUI (8.3)."""
        theme_validator = ThemeValidator(self.logic)
        entry_validator = EntryValidator(theme_validator)
        builder = RecordBuilder()
        importers = [
            CsvImporter(self.data, entry_validator, builder),
            JsonImporter(self.data, entry_validator, builder),
        ]
        return entry_validator, importers

    def run(self, mode: str | None = None) -> None:
        selected_mode = mode or ("gui" if "--gui" in sys.argv[1:] else "cli")
        self._load_env()    # must happen BEFORE reading ADMIN_PASSWORD
        admin_password = os.getenv("ADMIN_PASSWORD", "")
        if not admin_password:
            logger.warning("ADMIN_PASSWORD is not set in %s; admin login is turned off", ENV_FILE)

        if selected_mode == "gui":
            from PySide6.QtWidgets import QApplication
            from managers.gui import MainWindow, QtProgressReporter
            from managers.gui.data_reader import DataReader

            app = QApplication.instance() or QApplication(sys.argv)
            reporter = QtProgressReporter()
            self.bootstrap_system(reporter=reporter)

            assert self.pipeline is not None
            assert self.data is not None
            assert self.logic is not None

            entry_validator, importers = self._build_io_parts()
            pw_validator = PasswordValidator(admin_password) if admin_password else None
            reader = DataReader(self.data)

            window = MainWindow(
                pipeline=self.pipeline,
                data=reader,
                logic=self.logic,
                validators=entry_validator,
                importers=importers,
                reporter=reporter,
                password=pw_validator,
                ai_ready=self.ai_ready,
            )
            window.show()
            sys.exit(app.exec())

        # Default CLI mode
        self.bootstrap_system(reporter=ConsoleProgressReporter())
        assert self.pipeline is not None
        assert self.data is not None
        assert self.logic is not None

        view = ConsoleView()
        prompter = Prompter(view)

        _entry_validator, importers = self._build_io_parts()

        io_mgr = IOManager(
            view=view,
            prompter=prompter,
            importers=importers,
            data=self.data,
            logic=self.logic,
            admin_password=admin_password,
            ai_ready=self.ai_ready,
        )

        session = io_mgr.run_session()
        if session is not None:
            context = self.pipeline.execute_pipeline(session)
            view.show_dashboard(
                context.result,
                context.trend,
                context.summary,
                context.review_queue,
            )
