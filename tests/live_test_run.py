"""LiveTestRun: runs the AI Manager against the live API and reports the results.

Spends real tokens, so it has no test_ prefix and pytest and CI skip it. Run it with:
docker compose run --rm app python tests/live_test_run.py [reference|stress]
"""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "managers"))

from dotenv import load_dotenv  # noqa: E402

import ai_manager  # noqa: E402
from console_progress_reporter import ConsoleProgressReporter  # noqa: E402
from groq_client import GroqClient  # noqa: E402
from prompt_library import PromptLibrary  # noqa: E402

SAMPLES_DIR = REPO_ROOT / "tests" / "ai_manager_samples"
REFERENCE_ENTRIES_FILE = "test-output.json"  # the 25 reference entries; only their input fields are used
HUMAN_TAGS_FILE = "test-data-ans-key.json"  # hand labels, standing in for human tags
OUTPUT_FILE = "test-output-part2.json"
STRESS_ENTRIES_FILE = "stress-input.json"
STRESS_TAGS_FILE = "stress-ans-key.json"  # tagged by the user from scratch
STRESS_OUTPUT_FILE = "stress-output.json"
UNCLEAR_THEME = "Unclear"
CATCH_RATE_PASS_MARK = 0.85  # set by the user before any AI run on the stress corpus
INPUT_FIELDS = ("feedback_id", "text", "timestamp")
HUMAN_TAG_FIELDS = ("theme", "sentiment", "severity")


class LiveTestRun:
    """One live run over a corpus of entries, with its labels as human tags."""

    def __init__(self, manager: ai_manager.AIManager, themes: list[str], samples_dir: Path = SAMPLES_DIR):
        self.__manager = manager
        self.__themes = themes
        self.__samples_dir = samples_dir
        self.__output_file = OUTPUT_FILE

    def run_reference(self) -> tuple[list[dict], list[dict], bool]:
        """Classify the reference entries. Returns classify_entries' (classified, pending, stopped)."""
        return self._run(self._load_tagged_entries(REFERENCE_ENTRIES_FILE, HUMAN_TAGS_FILE), OUTPUT_FILE)

    def run_stress(self) -> tuple[list[dict], list[dict], bool]:
        """Classify the stress corpus. Returns classify_entries' (classified, pending, stopped)."""
        return self._run(self._load_tagged_entries(STRESS_ENTRIES_FILE, STRESS_TAGS_FILE), STRESS_OUTPUT_FILE)

    def find_disagreements(self, records: list[dict]) -> list[str]:
        """Return a line per disagreement between human tags and the AI's, by the flag rule."""
        lines = []
        for record in records:
            for field in HUMAN_TAG_FIELDS:
                if not self._same_label(record[field], [record[f"ai_{field}"]]):
                    lines.append(f"{record['feedback_id']} {field}: human {record[field]}, AI {record[f'ai_{field}']}")
        return lines

    def find_coined_themes(self, records: list[dict]) -> list[str]:
        """Return the labels the AI coined, without repeats."""
        coined = []
        for record in records:
            theme = record["ai_theme"]
            if theme != UNCLEAR_THEME and theme not in self.__themes and theme not in coined:
                coined.append(theme)
        return coined

    def measure_catch_rate(self, records: list[dict]) -> tuple[int, int]:
        """Return (caught, total) when each human theme is swapped for every wrong listed label."""
        caught = 0
        total = 0
        for record in records:
            for wrong_label in [*self.__themes, UNCLEAR_THEME]:
                if not self._same_label(wrong_label, [record["theme"]]):
                    total += 1
                    caught += not self._same_label(wrong_label, [record["ai_theme"]])
        return caught, total

    def find_critical_results(self, records: list[dict]) -> list[str]:
        """Return a line per entry the human tagged critical, with the AI's severity."""
        return [
            f"{record['feedback_id']}: AI {record['ai_severity']}" for record in records
            if self._same_label(record["severity"], ["critical"])
        ]

    def build_report(self, classified: list[dict], pending: list[dict], stopped: bool) -> str:
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

    def _run(self, entries: list[dict], output_file: str) -> tuple[list[dict], list[dict], bool]:
        """Classify entries, saving each record as it finishes."""
        self.__output_file = output_file
        saved = []

        def save(record: dict) -> None:
            saved.append(record)
            with open(self.__samples_dir / output_file, "w", encoding="utf-8") as file:
                json.dump(saved, file, indent=2)

        return self.__manager.classify_entries(entries, [], save)

    def _same_label(self, label: str, others: list[str]) -> bool:
        """Return True if label matches any of others, ignoring case."""
        return label.casefold() in [other.casefold() for other in others]

    def _load_tagged_entries(self, entries_file: str, tags_file: str) -> list[dict]:
        """Return the entries' input fields, plus their labels as human tags."""
        with open(self.__samples_dir / entries_file, encoding="utf-8") as file:
            entries = json.load(file)
        with open(self.__samples_dir / tags_file, encoding="utf-8") as file:
            labels = {label["feedback_id"]: label for label in json.load(file)}
        return [
            {
                **{field: entry[field] for field in INPUT_FIELDS},
                **{field: labels[entry["feedback_id"]][field] for field in HUMAN_TAG_FIELDS},
            }
            for entry in entries
        ]


if __name__ == "__main__":
    load_dotenv(os.path.join(ai_manager.BASE_DIR, "config", ".env"))
    api_key = os.environ.get("GROQ_API_KEY")
    key_label = os.environ.get("GROQ_KEY_LABEL")
    if not api_key or not key_label:
        sys.exit("GROQ_API_KEY and GROQ_KEY_LABEL must be set in config/.env")
    prompts = PromptLibrary()
    live_run = LiveTestRun(
        ai_manager.AIManager(GroqClient(api_key), key_label, prompts, ConsoleProgressReporter()), prompts.themes
    )
    corpus = sys.argv[1] if len(sys.argv) > 1 else "reference"
    results = live_run.run_stress() if corpus == "stress" else live_run.run_reference()
    print(live_run.build_report(*results))
