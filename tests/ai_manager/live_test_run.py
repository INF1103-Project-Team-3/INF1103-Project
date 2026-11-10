"""LiveTestRun: runs the AI Manager against the live API and reports the results.

Spends real tokens, so it has no test_ prefix and pytest and CI skip it. Run it with:
docker compose run --rm app python tests/ai_manager/live_test_run.py [reference|stress]
"""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

from managers.ai_manager import (  # noqa: E402
    AIManager, ConsoleProgressReporter, GroqClient, PromptLibrary
)
from managers.models import CRITICAL, FeedbackRecord, THEMES, UNCLEAR_THEME  # noqa: E402

CONFIG_DIR = REPO_ROOT / "managers" / "config"
TOKEN_LOG_FILE = CONFIG_DIR / "token-usage-log.json"
SAMPLES_DIR = REPO_ROOT / "tests" / "ai_manager_samples"
REFERENCE_ENTRIES_FILE = "test-output.json"  # the 25 reference entries; only their input fields are used
HUMAN_TAGS_FILE = "test-data-ans-key.json"  # hand labels, standing in for human tags
OUTPUT_FILE = "test-output-part2.json"
STRESS_ENTRIES_FILE = "stress-input.json"
STRESS_TAGS_FILE = "stress-ans-key.json"  # tagged by the user from scratch
STRESS_OUTPUT_FILE = "stress-output.json"
CATCH_RATE_PASS_MARK = 0.85  # set by the user before any AI run on the stress corpus
HUMAN_TAG_FIELDS = ("theme", "sentiment", "severity")


def load_token_log() -> dict | None:
    """Stands in for data.load_token_log: {} if there is no log yet, None if it is corrupt."""
    try:
        return json.loads(TOKEN_LOG_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return None


def save_token_log(log: dict) -> None:
    """Stands in for data.save_token_log."""
    TOKEN_LOG_FILE.write_text(json.dumps(log, indent=2), encoding="utf-8")


class LiveTestRun:
    """One live run over a corpus of entries, with its labels as human tags."""

    def __init__(self, manager: AIManager, themes: list[str], samples_dir: Path = SAMPLES_DIR):
        self.__manager = manager
        self.__themes = themes
        self.__samples_dir = samples_dir
        self.__output_file = OUTPUT_FILE

    def run_reference(self) -> tuple[list[FeedbackRecord], list[FeedbackRecord], bool]:
        """Classify the reference entries. Returns classify_entries' (classified, pending, stopped)."""
        return self._run(self._load_tagged_records(REFERENCE_ENTRIES_FILE, HUMAN_TAGS_FILE), OUTPUT_FILE)

    def run_stress(self) -> tuple[list[FeedbackRecord], list[FeedbackRecord], bool]:
        """Classify the stress corpus. Returns classify_entries' (classified, pending, stopped)."""
        return self._run(self._load_tagged_records(STRESS_ENTRIES_FILE, STRESS_TAGS_FILE), STRESS_OUTPUT_FILE)

    def find_disagreements(self, records: list[FeedbackRecord]) -> list[str]:
        """Return a line per disagreement between human tags and the AI's, by the flag rule."""
        lines = []
        for record in records:
            for field in HUMAN_TAG_FIELDS:
                if not self._same_label(record.user[field], [record.ai[field]]):
                    lines.append(f"{record.feedback_id} {field}: human {record.user[field]}, AI {record.ai[field]}")
        return lines

    def find_coined_themes(self, records: list[FeedbackRecord]) -> list[str]:
        """Return the labels the AI coined, without repeats."""
        coined = []
        for record in records:
            theme = record.ai["theme"]
            if theme != UNCLEAR_THEME and theme not in self.__themes and theme not in coined:
                coined.append(theme)
        return coined

    def measure_catch_rate(self, records: list[FeedbackRecord]) -> tuple[int, int]:
        """Return (caught, total) when each human theme is swapped for every wrong listed label."""
        caught = 0
        total = 0
        for record in records:
            for wrong_label in [*self.__themes, UNCLEAR_THEME]:
                if not self._same_label(wrong_label, [record.user["theme"]]):
                    total += 1
                    caught += not self._same_label(wrong_label, [record.ai["theme"]])
        return caught, total

    def find_critical_results(self, records: list[FeedbackRecord]) -> list[str]:
        """Return a line per entry the human tagged critical, with the AI's severity."""
        return [
            f"{record.feedback_id}: AI {record.ai['severity']}" for record in records
            if self._same_label(record.user["severity"], [CRITICAL])
        ]

    def build_report(self, classified: list[FeedbackRecord], pending: list[FeedbackRecord], stopped: bool) -> str:
        """Return the results as text."""
        disagreements = self.find_disagreements(classified)
        flagged = {line.split()[0] for line in disagreements}
        caught, total = self.measure_catch_rate(classified)
        catch_rate = caught / total if total else 0
        verdict = "pass" if catch_rate >= CATCH_RATE_PASS_MARK else "fail"
        lines = [
            f"Classified {len(classified)}, pending {len(pending)}, stopped: {stopped}",
            f"Records flagged: {len(flagged)} of {len(classified)}",
            *[f"  {line}" for line in disagreements],
            f"Coined themes: {self.find_coined_themes(classified)}",
            f"Wrong theme tags caught: {caught} of {total} ({catch_rate:.1%}), "
            f"pass mark {CATCH_RATE_PASS_MARK:.0%}: {verdict}",
            f"Tagged critical by the human: {self.find_critical_results(classified)}",
            f"Output: {self.__samples_dir / self.__output_file}",
        ]
        return "\n".join(lines)

    def _run(
        self, records: list[FeedbackRecord], output_file: str
    ) -> tuple[list[FeedbackRecord], list[FeedbackRecord], bool]:
        """Classify records, saving each one as it finishes."""
        self.__output_file = output_file
        saved = []

        def save(record: FeedbackRecord) -> None:
            saved.append(record.to_dict())
            with open(self.__samples_dir / output_file, "w", encoding="utf-8") as file:
                json.dump(saved, file, indent=2)

        return self.__manager.classify_entries(records, [], save)

    def _same_label(self, label: str, others: list[str]) -> bool:
        """Return True if label matches any of others, ignoring case."""
        return label.casefold() in [other.casefold() for other in others]

    def _load_tagged_records(self, entries_file: str, tags_file: str) -> list[FeedbackRecord]:
        """Return a record per entry, with its labels as the user's values."""
        with open(self.__samples_dir / entries_file, encoding="utf-8") as file:
            entries = json.load(file)
        with open(self.__samples_dir / tags_file, encoding="utf-8") as file:
            labels = {label["feedback_id"]: label for label in json.load(file)}
        return [
            FeedbackRecord(
                entry["feedback_id"], entry["text"], entry["timestamp"], None,
                {field: labels[entry["feedback_id"]][field] for field in HUMAN_TAG_FIELDS},
            )
            for entry in entries
        ]


if __name__ == "__main__":
    load_dotenv(CONFIG_DIR / ".env")
    api_key = os.environ.get("GROQ_API_KEY")
    key_label = os.environ.get("GROQ_KEY_LABEL")
    if not api_key or not key_label:
        sys.exit("GROQ_API_KEY and GROQ_KEY_LABEL must be set in config/.env")
    prompts = PromptLibrary(
        (CONFIG_DIR / "system_prompt.txt").read_text(encoding="utf-8"),
        (CONFIG_DIR / "summary_prompt.txt").read_text(encoding="utf-8"),
        THEMES,
    )
    manager = AIManager(
        GroqClient(api_key), key_label, prompts, ConsoleProgressReporter(), load_token_log, save_token_log
    )
    live_run = LiveTestRun(manager, prompts.themes)
    corpus = sys.argv[1] if len(sys.argv) > 1 else "reference"
    results = live_run.run_stress() if corpus == "stress" else live_run.run_reference()
    print(live_run.build_report(*results))
