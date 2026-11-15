from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from managers.ai_manager import (
    AIManager,
    AISummary,
    ConsoleProgressReporter,
    GroqClient,
    ProgressReporter,
    PromptLibrary,
)
from managers.data_manager import DataManager, JsonFileStore
from managers.io_manager import (
    ConsoleView,
    EntryValidator,
    IOManager,
    PasswordValidator,
    Prompter,
    ThemeValidator,
)
from managers.logic_manager import LogicManager

from .console_log_formatter import ConsoleLogFormatter
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
        self._data: DataManager | None = None
        self._logic: LogicManager | None = None
        self._ai: AIManager | None = None
        self._pipeline: PipelineManager | None = None
        self._ai_ready = False      # set by bootstrap_system: key and key label both present

    @staticmethod
    def _load_env() -> None:
        # Safe to call twice: existing environment variables are not overwritten
        load_dotenv(ENV_FILE)

    def bootstrap_system(self, reporter: ProgressReporter | None = None) -> None:
        self._load_env()
        # D20: a missing key or key label never stops the run; the AI just reports it down
        api_key = os.getenv("GROQ_API_KEY", "")
        key_label = os.getenv("GROQ_KEY_LABEL", "")
        self._ai_ready = bool(api_key and key_label)
        if not api_key or not key_label:
            logger.warning("GROQ_API_KEY or GROQ_KEY_LABEL is not set in %s; "
                           "the AI will be unavailable this session", ENV_FILE)

        store = JsonFileStore()
        self._data = DataManager(self._data_dir, store)

        known_themes = self._data.load_known_themes()
        self._logic = LogicManager(known_themes=known_themes)

        sys_prompt, sum_prompt = self._data.load_prompts()
        prompts = PromptLibrary(sys_prompt, sum_prompt, themes=known_themes)
        # Not ready means AI down (D20): the client gets no key, so Call 1 stops at
        # once instead of spending tokens on a run whose Call 2 is then skipped
        client = GroqClient(api_key=api_key if self._ai_ready else None)
        active_reporter = reporter or ConsoleProgressReporter()

        self._ai = AIManager(
            client=client,
            key_label=key_label,
            prompts=prompts,
            reporter=active_reporter,
            load_token_log=self._data.load_token_log,
            save_token_log=self._data.save_token_log,
        )

        self._pipeline = PipelineManager(data_dir=self._data_dir)
        self._pipeline.register_step(IngestionStep(self._data, self._logic, self._ai))
        self._pipeline.register_step(AIClassificationStep(self._ai, self._data))
        self._pipeline.register_step(LogicStep(self._logic, self._data))
        self._pipeline.register_step(SummaryStep(self._ai, self._logic, ai_ready=self._ai_ready))
        self._pipeline.register_step(ImpactStep(self._logic, self._data))
        self._pipeline.register_step(PersistenceStep(self._data))

    def _build_io_parts(self):
        """The entry validator for typed feedback and the standard importers,
        shared by the terminal and the GUI (8.3)."""
        entry_validator = EntryValidator(ThemeValidator(self._logic))
        return entry_validator, IOManager.create_importers(self._data, self._logic)

    @staticmethod
    def configure_logging(logger: logging.Logger | None = None) -> None:
        """Sets up console logging once, for the whole app: warnings and errors
        only, as plain lines without tracebacks (P4). Managers only log."""
        target = logger if logger is not None else logging.getLogger()
        if any(isinstance(h.formatter, ConsoleLogFormatter) for h in target.handlers):
            return
        handler = logging.StreamHandler()
        handler.setFormatter(ConsoleLogFormatter())
        target.addHandler(handler)
        target.setLevel(logging.WARNING)

    def execute_run(self, session, view) -> PipelineContext | None:
        """Runs the pipeline on one session. If a step fails or the user presses
        Ctrl-C, shows a plain message saying what was saved and returns None,
        instead of ending the app with a traceback."""
        try:
            return self._pipeline.execute_pipeline(session)
        except (Exception, KeyboardInterrupt) as error:
            view.show_message(self._stopped_message(self._pipeline.current_step, error))
            return None

    @staticmethod
    def _stopped_message(step, error: BaseException) -> str:
        during = getattr(step, "description", "the analysis")
        if isinstance(error, KeyboardInterrupt):
            first = f"The analysis was stopped (Ctrl-C) during {during}."
        else:
            first = f"The analysis stopped during {during} because of an error: {error}"
        if step is None or isinstance(step, IngestionStep):
            saved = ("Some of this session's changes may not have been saved; "
                     "check them and try again.")
        else:
            saved = ("This session's feedback, review decisions and actions were saved "
                     "and are included in the next run; this run's results may not have been saved.")
        return f"{first}\n{saved}"

    def run(self, mode: str | None = None) -> None:
        selected_mode = mode or ("gui" if "--gui" in sys.argv[1:] else "cli")
        self.configure_logging()
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

            assert self._pipeline is not None
            assert self._data is not None
            assert self._logic is not None

            entry_validator, importers = self._build_io_parts()
            pw_validator = PasswordValidator(admin_password) if admin_password else None
            reader = DataReader(self._data)

            window = MainWindow(
                pipeline=self._pipeline,
                data=reader,
                logic=self._logic,
                validators=entry_validator,
                importers=importers,
                reporter=reporter,
                password=pw_validator,
                ai_ready=self._ai_ready,
            )
            window.show()
            sys.exit(app.exec())

        # Default CLI mode
        self.bootstrap_system(reporter=ConsoleProgressReporter())
        assert self._pipeline is not None
        assert self._data is not None
        assert self._logic is not None

        view = ConsoleView()
        prompter = Prompter(view)

        _entry_validator, importers = self._build_io_parts()

        io_mgr = IOManager(
            view=view,
            prompter=prompter,
            importers=importers,
            data=self._data,
            logic=self._logic,
            admin_password=admin_password,
            ai_ready=self._ai_ready,
        )

        session = io_mgr.run_session()
        if session is not None:
            context = self.execute_run(session, view)
            if context is None:
                return
            self._show_run_dashboard(context, view)

    def _show_run_dashboard(self, context: PipelineContext, view) -> None:
        """Show the run's results. When Call 2 did not run or failed, the last
        AI summary is shown with its date, and this run's rule-based actions in
        place of the AI's (D21)."""
        summary = context.summary
        if summary is None:
            saved = self._data.load_object("summary")
            try:
                summary = AISummary.from_dict(saved) if saved else None
            except (KeyError, TypeError, ValueError):
                summary = None
        view.show_dashboard(context.result, context.trend, summary, context.review_queue,
                            context.fallback_actions)
