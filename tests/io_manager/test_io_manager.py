"""IOManager: whole sessions, from choosing a role to the SessionResult returned.

These are end-to-end tests of the I/O side: every class works together, and only
Data, Logic and the AI are replaced by fakes.
"""
import sys
import types

import pytest

from managers.io_manager.csv_importer import CsvImporter
from managers.io_manager.io_manager import IOManager
from managers.io_manager.json_importer import JsonImporter
from managers.io_manager.prompter import Prompter
from managers.io_manager.review_decision import ReviewDecision
from managers.io_manager.session_result import SessionResult

PASSWORD = "pw-from-env"
SETTINGS = "7"
FINISH = "8"                    # the last admin menu option
GOOD_ROW = {"feedback_id": "a1", "text": "Wifi keeps dropping", "timestamp": "2026-10-01T09:00:00",
            "theme": "Facilities", "sentiment": "negative", "severity": "high"}


@pytest.fixture
def session(prompter, screen, data, logic):
    """Factory: session(answers, secrets, password) runs one session and returns its result."""
    def run(answers, secrets=(PASSWORD,), password=PASSWORD):
        io = IOManager(screen.view, prompter(answers, secrets),
                       IOManager.create_importers(data, logic), data, logic, password)
        return io.run_session()
    return run


def test_a_user_gives_one_piece_of_feedback(session, screen):
    result = session(["user", "Good lectures", "1", "positive", "low"])
    assert isinstance(result, SessionResult)
    assert [r.text for r in result.records] == ["Good lectures"]
    assert "Thank you! Your response has been received." in screen.lines


def test_a_user_who_quits_gets_nothing_saved(session, screen):
    assert session(["user", "quit"]) is None
    assert "Cancelled." in screen.lines


def test_an_unknown_role_is_asked_again(session, screen):
    assert session(["boss", "quit"]) is None
    assert "  Invalid: please enter 'user' or 'admin'" in screen.lines


def test_admin_must_log_in_and_may_retry(session, screen, prompter):
    session(["admin", FINISH], secrets=["wrong", PASSWORD])
    assert "  Invalid: wrong password" in screen.lines
    assert prompter.secret_script.prompts == ["Admin password: ", "Admin password: "]
    assert "--- Admin ---" in screen.lines


def test_admin_who_presses_ctrl_d_at_the_password_is_not_let_in(screen, data, logic):
    # a typed password is never treated as "quit", so Ctrl-D is how an admin gives up
    def no_password(prompt):
        raise EOFError
    prompter = Prompter(screen.view, lambda prompt: "admin", no_password)
    assert IOManager(screen.view, prompter, [], data, logic, PASSWORD).run_session() is None
    assert "--- Admin ---" not in screen.lines


def test_admin_login_is_disabled_when_no_password_is_configured(session, screen):
    assert session(["admin"], secrets=[], password=None) is None
    assert "Admin login is disabled: no admin password is configured." in screen.lines


def test_admin_finishing_with_nothing_collected_returns_none(session, screen):
    assert session(["admin", FINISH]) is None
    assert "Cancelled." in screen.lines


def test_everything_the_admin_does_is_returned_in_one_result(session, data, make_record):
    data.files["week5.csv"] = [GOOD_ROW]
    data.queue = [make_record("fb_9", reasons=["Critical severity"])]
    result = session(["admin",
                      "1", "Typed by the admin", "1", "neutral", "low",      # feedback entry
                      "2", "week5.csv",                                      # import
                      "5", "d", "y",                                         # review: delete
                      "6", "1", "Extra tutorials", "2026-11-05", "",         # log an action
                      FINISH])
    assert [r.text for r in result.records] == ["Typed by the admin", "Wifi keeps dropping"]
    assert result.source_file == "week5.csv"
    assert result.decisions == [ReviewDecision.delete("fb_9")]
    assert [a.description for a in result.actions] == ["Extra tutorials"]


def test_a_wrong_file_type_or_unreadable_file_is_asked_again(session, screen, data):
    data.files["good.json"] = [GOOD_ROW]
    result = session(["admin", "2", "notes.txt", "missing.csv", "good.json", FINISH])
    assert "  Invalid: file must end in .csv, .json." in screen.lines
    assert any(line.startswith("  Invalid: could not read 'missing.csv'") for line in screen.lines)
    assert "Validated 1 of 1 row(s)." in screen.lines
    assert len(result.records) == 1


def test_search_re_asks_until_something_is_found(session, screen, data, make_record):
    data.records = [make_record("fb_1", text="Wifi drops in the library")]
    session(["admin", "4", "parking", "wifi", FINISH])
    assert "  No feedback found matching 'parking'. Try different terms." in screen.lines
    assert "Found 1 matching record(s):" in screen.lines


def test_a_record_is_not_offered_for_review_twice_in_one_session(session, screen, data, make_record):
    data.queue = [make_record("fb_9", reasons=["Critical severity"])]
    result = session(["admin", "5", "d", "y", "5", FINISH])
    assert len(result.decisions) == 1
    assert "Nothing waiting for review." in screen.lines


@pytest.fixture
def result_classes(monkeypatch):
    """Fake Logic and AI result classes for the dashboard. from_dict() refuses
    anything that is not a dictionary, as a real one would for a corrupt file."""
    class Strict:
        @classmethod
        def from_dict(cls, raw):
            if not isinstance(raw, dict):
                raise TypeError("corrupt saved data")
            return raw
    for module, names in (("managers.ai_manager", ["AISummary"]),
                          ("managers.logic_manager", ["AggregationResult", "TrendReport"])):
        fake = types.ModuleType(module)
        for name in names:
            setattr(fake, name, Strict)
        monkeypatch.setitem(sys.modules, module, fake)


def test_dashboard_with_corrupt_saved_data_does_not_crash(session, screen, data, result_classes):
    data.objects = {"aggregated_output": "corrupt", "summary": ["also", "corrupt"]}
    session(["admin", "3", FINISH])
    assert "No aggregated data yet." in screen.lines
    # the admin is told, through the view, which saved results were unreadable
    assert "  Note: the saved aggregated_output could not be read, so it is left out." in screen.lines
    assert "  Note: the saved summary could not be read, so it is left out." in screen.lines


def test_dashboard_offers_to_review_what_is_waiting(session, screen, data, make_record, result_classes):
    data.queue = [make_record("fb_9", reasons=["Critical severity"])]
    result = session(["admin", "3", "y", "d", "y", FINISH])
    assert result.decisions == [ReviewDecision.delete("fb_9")]


def test_answering_no_on_the_dashboard_starts_no_review(session, screen, data, make_record, result_classes):
    data.queue = [make_record("fb_9", reasons=["Critical severity"])]
    assert session(["admin", "3", "n", FINISH]) is None
    assert not any(line.startswith("Review 1 of") for line in screen.lines)


def status_line(screen, label):
    """The value shown for one line of the system status."""
    line = next(line for line in screen.lines if line.startswith(f"  {label}"))
    return line.split(": ", 1)[1]


def test_settings_shows_the_system_status_read_from_data(prompter, screen, data, logic, make_record):
    data.records = [make_record("fb_1"), make_record("fb_2")]
    data.queue = [make_record("fb_3")]
    data.history = [{"run_at": "2026-11-10T08:00:00"}, {"run_at": "2026-11-01T08:00:00"}]
    io = IOManager(screen.view, prompter(["admin", SETTINGS, "2", FINISH], [PASSWORD]),
                   [], data, logic, PASSWORD, ai_ready=True)
    io.run_session()
    assert f"Known themes ({len(data.themes)})" in screen.lines
    assert status_line(screen, "AI connection") == "ready"
    assert status_line(screen, "Processed records") == "2"
    assert status_line(screen, "Waiting for review") == "1"
    assert status_line(screen, "Last analysis run") == "2026-11-10 08:00:00"


@pytest.mark.parametrize("ai_ready, shown", [(True, "ready"), (False, "not configured (no API key)"),
                                             (None, "not reported")])
def test_the_ai_connection_is_whatever_app_engine_reports(prompter, screen, data, logic, ai_ready, shown):
    # only AppEngine may read the API key, so it tells IOManager whether the AI is ready
    io = IOManager(screen.view, prompter(["admin", SETTINGS, "2", FINISH], [PASSWORD]),
                   [], data, logic, PASSWORD, ai_ready=ai_ready)
    io.run_session()
    assert status_line(screen, "AI connection") == shown
    assert status_line(screen, "Last analysis run") == "never"


def test_adding_a_theme_returns_it_for_the_pipeline_to_save(session, screen, logic):
    result = session(["admin", SETTINGS, "1", "parking fees", "2", FINISH])
    assert result.themes_to_add == ["Parking Fees"]          # cleaned up by Logic
    assert logic.calls == ["parking fees"]
    assert "  'Parking Fees' will be added when the analysis runs." in screen.lines


@pytest.mark.parametrize("typed", ["workload", "WORKLOAD", "  Workload "])
def test_a_theme_that_is_already_known_is_not_added_again(session, screen, typed):
    assert session(["admin", SETTINGS, "1", typed, "2", FINISH]) is None
    assert "  'Workload' is already a known theme." in screen.lines


def test_the_same_new_theme_is_not_queued_twice(session, screen):
    result = session(["admin", SETTINGS, "1", "car park", "1", "Car Park", "2", FINISH])
    assert result.themes_to_add == ["Car Park"]
    assert "  'Car Park' is already a known theme." in screen.lines


def test_a_confirmed_theme_from_data_counts_as_known(session, screen, data):
    data.themes = data.themes + ["Car Park"]
    assert session(["admin", SETTINGS, "1", "car park", "2", FINISH]) is None
    assert "  'Car Park' is already a known theme." in screen.lines


def test_a_filler_word_is_not_a_usable_theme(session, screen):
    assert session(["admin", SETTINGS, "1", "n/a", "2", FINISH]) is None
    assert "  Invalid: that is not a usable theme name." in screen.lines


def test_an_empty_theme_is_asked_again_and_quit_cancels(session, screen):
    assert session(["admin", SETTINGS, "1", "", "quit", "2", FINISH]) is None
    assert "  Invalid: theme cannot be empty" in screen.lines


def test_settings_shows_the_theme_waiting_to_be_added(session, screen):
    session(["admin", SETTINGS, "1", "Car Park", "2", FINISH])
    assert "Added this session, saved when you finish:" in screen.lines
    assert "  Car Park" in screen.lines


def test_show_notice_is_shown_prominently(screen, prompter, data, logic):
    io = IOManager(screen.view, prompter(), [], data, logic, PASSWORD)
    io.show_notice(IOManager.NOTICE_CONNECTING)
    assert "    CONNECTING TO API & RUNNING" in screen.lines


def test_create_importers_gives_csv_and_json_importers(data, logic):
    importers = IOManager.create_importers(data, logic)
    assert [type(i) for i in importers] == [CsvImporter, JsonImporter]


def test_app_engine_can_build_everything_from_the_public_names(data, logic):
    # AppEngine may import only from the package (design rule), so this builds
    # the I/O side exactly as AppEngine does in terminal mode. AppEngine uses
    # the default keyboard reader; the test types the answers instead.
    import managers.io_manager as io_package
    answers = iter(["user", "Good lectures", "1", "positive", "low"])
    printed = []
    view = io_package.ConsoleView(writer=printed.append)
    io = io_package.IOManager(view, io_package.Prompter(view, lambda prompt: next(answers)),
                              io_package.IOManager.create_importers(data, logic),
                              data, logic, admin_password=None)
    result = io.run_session()
    assert isinstance(result, io_package.SessionResult)
    assert result.records[0].text == "Good lectures"
