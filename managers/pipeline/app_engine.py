from __future__ import annotations

import os
import sys
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


class AppEngine:
    def __init__(self, data_dir: str = "data") -> None:
        self._data_dir = data_dir
        self.data: DataManager | None = None
        self.logic: LogicManager | None = None
        self.ai: AIManager | None = None
        self.pipeline: PipelineManager | None = None

    def bootstrap_system(self, reporter: Any = None) -> PipelineContext:
        load_dotenv()
        api_key = os.getenv("GROQ_API_KEY", "")
        key_label = "GROQ_API_KEY" if api_key else ""

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

    def run(self, mode: str | None = None) -> None:
        selected_mode = mode or ("gui" if "--gui" in sys.argv else "cli")
        admin_password = os.getenv("ADMIN_PASSWORD", "")

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

            theme_validator = ThemeValidator(self.logic)
            entry_validator = EntryValidator(theme_validator)
            builder = RecordBuilder()
            importers = [
                CsvImporter(self.data, entry_validator, builder),
                JsonImporter(self.data, entry_validator, builder),
            ]
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

        theme_validator = ThemeValidator(self.logic)
        entry_validator = EntryValidator(theme_validator)
        builder = RecordBuilder()
        importers = [
            CsvImporter(self.data, entry_validator, builder),
            JsonImporter(self.data, entry_validator, builder),
        ]

        io_mgr = IOManager(
            view=view,
            prompter=prompter,
            importers=importers,
            data=self.data,
            logic=self.logic,
            admin_password=admin_password,
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
