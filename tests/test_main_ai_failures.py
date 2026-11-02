import json
import os
import runpy

import pytest

import ai_manager
from llm_request_error import LLMRequestError
from stub_llm_client import StubLLMClient
from token_ledger import TokenLedger

MAIN_PATH = os.path.join(ai_manager.BASE_DIR, "main.py")
ENTRIES = [
    {"feedback_id": "fb_001", "text": "The slides move too fast.", "timestamp": "2026-09-15T10:32:00"},
    {"feedback_id": "fb_002", "text": "The printers are broken.", "timestamp": "2026-09-15T10:33:00"},
]
GOOD = json.dumps({"theme": "Facilities", "alternative_themes": [], "sentiment": "negative", "severity": "high"})
REJECTED = LLMRequestError("key rejected (HTTP 401)", LLMRequestError.AUTH, False)


def run_main(monkeypatch, tmp_path, client=None, api_key="key"):
    """Run main.py as a script on one import, with a temporary data folder and ledger."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("io_manager.DATA_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))  # main.py sets this; setenv restores it afterwards
    monkeypatch.setattr("io_manager.main", lambda: ("import.json", json.dumps(ENTRIES).encode(), "application/json"))
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr(ai_manager.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(ai_manager, "TokenLedger", lambda model, path: TokenLedger(model, str(tmp_path / "ledger.json")))
    for name, value in (("GROQ_API_KEY", api_key), ("GROQ_KEY_LABEL", "test")):
        if value:
            monkeypatch.setenv(name, value)
        else:
            monkeypatch.delenv(name, raising=False)
    if client is not None:
        monkeypatch.setattr("groq_client.GroqClient", lambda key: client)
    runpy.run_path(MAIN_PATH, run_name="__main__")


def test_empty_run_leaves_the_trend_untouched_and_skips_the_summary(monkeypatch, tmp_path):
    client = StubLLMClient(["not json"] * 6)

    run_main(monkeypatch, tmp_path, client)

    assert len(client.calls) == 6  # two entries, three attempts each, and no call 2
    assert not (tmp_path / "trend_output.json").exists()
    assert not (tmp_path / "aggregated_history.json").exists()


def test_empty_run_keeps_the_last_invalid_records(monkeypatch, tmp_path):
    invalid = tmp_path / "invalid_records.json"
    invalid.write_text('[{"feedback_id": "fb_000"}]', encoding="utf-8")

    run_main(monkeypatch, tmp_path, StubLLMClient(["not json"] * 6))

    assert json.loads(invalid.read_text(encoding="utf-8")) == [{"feedback_id": "fb_000"}]


def test_stopped_batch_skips_the_summary(monkeypatch, tmp_path):
    client = StubLLMClient([GOOD, REJECTED])

    run_main(monkeypatch, tmp_path, client)

    assert len(client.calls) == 2  # the rejected key stopped it, so no call 2


def test_classified_records_are_saved_one_at_a_time(monkeypatch, tmp_path):
    client = StubLLMClient([GOOD, REJECTED])

    run_main(monkeypatch, tmp_path, client)

    saved = json.loads((tmp_path / "classified_output.json").read_text(encoding="utf-8"))["records"]
    assert [record["feedback_id"] for record in saved] == ["fb_001"]
    assert saved[0]["ai_theme"] == "Facilities"


def test_full_batch_goes_on_to_the_summary(monkeypatch, tmp_path):
    client = StubLLMClient([GOOD, GOOD, "not json", "not json", "not json"])

    run_main(monkeypatch, tmp_path, client)

    assert len(client.calls) == 5
    assert client.calls[2]["schema_name"] == "feedback_summary"


def test_missing_key_keeps_the_app_running(monkeypatch, tmp_path, capsys):
    run_main(monkeypatch, tmp_path, api_key=None)

    output = capsys.readouterr().out
    assert "API key missing" in output
    assert "2 pending (fb_001, fb_002)" in output
    assert not (tmp_path / "trend_output.json").exists()


def test_records_left_pending_stay_in_the_cache(monkeypatch, tmp_path):
    run_main(monkeypatch, tmp_path, StubLLMClient([REJECTED]))

    cache = json.loads((tmp_path / "feedback_before_ai.json").read_text(encoding="utf-8"))["records"]
    assert [record["feedback_id"] for record in cache] == ["fb_001", "fb_002"]
