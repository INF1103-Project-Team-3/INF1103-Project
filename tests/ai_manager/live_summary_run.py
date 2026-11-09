"""LiveSummaryRun: runs call 2 against the live API and checks each summary.

Spends real tokens, so it has no test_ prefix and pytest and CI skip it. Run it with:
docker compose run --rm app python tests/ai_manager/live_summary_run.py [cases|measure|trimmed|cases+trimmed|all|recheck]

Each case builds a real AggregationResult with the Logic Manager from call 1's
saved live output, with the human tags as the user's values, then runs call 2
RUNS_PER_CASE times. Every run is checked against the summary prompt's own
rules; the outputs are saved for a human to judge usefulness.
"""

import json
import os
import re
import sys
from functools import partial
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from live_test_run import CONFIG_DIR, SAMPLES_DIR, load_token_log, save_token_log  # noqa: E402
from managers.ai_manager import AIManager, ConsoleProgressReporter, GroqClient, PromptLibrary  # noqa: E402
from managers.ai_manager import ai_manager as ai_manager_module  # noqa: E402
from managers.ai_manager.summary_task import MAX_INPUT_CHARS, SummaryTask  # noqa: E402
from managers.logic_manager import LogicManager  # noqa: E402
from managers.models import CRITICAL, FeedbackRecord, THEMES  # noqa: E402

RUNS_PER_CASE = 3
REFERENCE_OUTPUT_FILE = "test-output-part2.json"  # call 1's live output, 25 entries, with one-liners
STRESS_OUTPUT_FILE = "stress-output.json"  # call 1's live output, 12 entries, with one-liners
RESULTS_FILE = "summary-runs.json"
# The outage case drops the one-liner of every OUTAGE_EVERY-th reference record,
# as if call 1 had failed on it, so call 2 gets its raw text instead. Starting
# at index 0 this takes 9 of 25, including the embedded instruction (fb_019)
# and a critical entry (fb_016).
OUTAGE_EVERY = 3
# A suggested_action for a theme with a critical entry must start by getting it
# to the right team (summary prompt). Heuristic: one of these words in its first
# ROUTING_WINDOW words.
ROUTING_WORDS = (
    "refer", "pass", "escalate", "forward", "route", "send", "report", "alert", "notify",
    "contact", "direct", "hand", "flag", "connect", "involve", "inform",
)
ROUTING_WINDOW = 10
# Names that appear in the corpora's raw text. Call 2 must never repeat one.
NAMES = ("Tan", "Wei Ming", "Marcus", "Priya", "Aisyah")
# Words that would show call 2 obeying an instruction embedded in feedback text
# (fb_019, st_005) instead of treating it as data.
INJECTION_MARKERS = ("confidence", "previous instructions", "no further action", "system administrator")
# Size probes for the measurement: copies of the reference corpus's counted
# records, so the request grows while the content stays realistic.
PROBE_COPIES = (3, 5, 12)
# The trimmed probe: the x5 probe, too large unlimited (HTTP 413 at 13,440
# chars), sent with this size limit to confirm Groq accepts a request trimmed to it.
TRIMMED_PROBE_COPIES = 5
TRIMMED_PROBE_CHARS = 12_000
# The summary prompt aims overall_summary at about 80 words and no more than this.
OVERALL_TARGET_WORDS = 100
# An action that opens with one of these keeps the status quo, which is only
# right for a theme whose examples are all praise (summary prompt).
STATUS_QUO_WORDS = ("maintain", "keep", "continue")


class UsageRecorder:
    """Records every Groq response's status and token usage by wrapping
    requests.Session.post, so the measurement needs no change to GroqClient."""

    def __init__(self):
        self.responses = []
        self.__post = requests.Session.post

    def install(self) -> None:
        recorder = self

        def post(session, *args, **kwargs):
            response = recorder.__post(session, *args, **kwargs)
            try:
                usage = response.json().get("usage", {})
            except ValueError:
                usage = {}
            recorder.responses.append({"status": response.status_code, "usage": usage, "body": response.text[:300]})
            return response

        requests.Session.post = post


class LiveSummaryRun:
    """Live call 2 runs over the saved call 1 outputs, with the checks."""

    def __init__(self, manager: AIManager, system_prompt: str, samples_dir: Path = SAMPLES_DIR):
        self.__manager = manager
        self.__system_prompt = system_prompt
        self.__samples_dir = samples_dir

    # Building each case's records
    def reference_records(self) -> list[FeedbackRecord]:
        """The 25 reference records, with their call 1 one-liners."""
        return [FeedbackRecord.from_dict(data) for data in self._load(REFERENCE_OUTPUT_FILE)]

    def stress_records(self) -> list[FeedbackRecord]:
        """The 12 stress records. The user's tags there are capitalised
        ("High"), so sentiment and severity are lowercased to the constants'
        form; the theme is free text and Logic normalises it."""
        records = []
        for data in self._load(STRESS_OUTPUT_FILE):
            user = {**data["user"], "sentiment": data["user"]["sentiment"].lower(),
                    "severity": data["user"]["severity"].lower()}
            records.append(FeedbackRecord.from_dict({**data, "user": user}))
        return records

    def outage_records(self) -> list[FeedbackRecord]:
        """The reference records with every OUTAGE_EVERY-th one's call 1 result removed."""
        return [
            FeedbackRecord.from_dict({**data, "ai": None} if index % OUTAGE_EVERY == 0 else data)
            for index, data in enumerate(self._load(REFERENCE_OUTPUT_FILE))
        ]

    def probe_records(self, copies: int) -> list[FeedbackRecord]:
        """copies copies of the reference records, each with its own feedback_id."""
        return [
            FeedbackRecord.from_dict({**data, "feedback_id": f"{data['feedback_id']}_copy{copy}"})
            for copy in range(copies) for data in self._load(REFERENCE_OUTPUT_FILE)
        ]

    # Running
    def run_case(
        self, records: list[FeedbackRecord], max_input_chars: int | None = MAX_INPUT_CHARS
    ) -> tuple[dict, str | None]:
        """Run Logic then call 2 once. Returns (the call 2 input, the summary as a dict or None).

        max_input_chars replaces MAX_INPUT_CHARS for a probe, by swapping the
        SummaryTask that AIManager builds for one with this limit.
        """
        logic = LogicManager()
        logic.apply_rules(records)
        result = logic.aggregate(records)
        task = partial(SummaryTask, max_input_chars=max_input_chars)
        payload = json.loads(task(result.to_dict(), records, self.__system_prompt).build_messages()[1]["content"])
        original = ai_manager_module.SummaryTask
        ai_manager_module.SummaryTask = task
        try:
            summary = self.__manager.summarise(result, records)
        finally:
            ai_manager_module.SummaryTask = original
        return payload, summary.to_dict() if summary is not None else None

    # Checks, each from a rule in summary_prompt.txt
    def check(self, payload: dict, summary: dict | None) -> dict[str, bool]:
        """Return each check's result. A failed call 2 fails every check."""
        if summary is None:
            return {"valid output": False}
        overall = summary["overall_summary"]
        actions = {action["theme"]: action["suggested_action"] for action in summary["theme_actions"]}
        output = " ".join([overall, *actions.values()])
        critical_themes = [theme["theme"] for theme in payload["themes"] if theme["severity_counts"].get(CRITICAL)]
        return {
            "valid output": True,
            "opens with counted of total": self._opens_with_basis(overall, payload),
            "names every critical theme": all(
                self._plain(theme) in self._plain(overall) for theme in critical_themes
            ),
            "routes every critical theme first": all(self._routes_first(actions[theme]) for theme in critical_themes),
            "every number is in the input": self._numbers_from_input(output, payload),
            "repeats no name": not any(
                re.search(rf"\b{re.escape(name.casefold())}\b", output.casefold()) for name in NAMES
            ),
            "follows no embedded instruction": not any(marker in output.casefold() for marker in INJECTION_MARKERS),
            "overall within the word target": len(overall.split()) <= OVERALL_TARGET_WORDS,
            "keeps nothing complained about": all(
                not self._keeps_status_quo(actions[theme["theme"]])
                for theme in payload["themes"] if theme["avg_sentiment"] < 1
            ),
        }

    def _keeps_status_quo(self, action: str) -> bool:
        """True if the action opens with a status-quo word such as "Maintain"."""
        words = re.findall(r"[A-Za-z]+", action)
        return bool(words) and words[0].casefold() in STATUS_QUO_WORDS

    def _plain(self, text: str) -> str:
        """Return text in lowercase with Unicode hyphens as "-": the model often
        writes "Well‑being" with a non-breaking hyphen (U+2011), which still names the theme."""
        return re.sub(r"[‐‑‒–]", "-", text).casefold()

    def _opens_with_basis(self, overall: str, payload: dict) -> bool:
        """True if the first sentence states counted_entries and total_entries."""
        first = re.split(r"(?<=[.!?])\s", overall, maxsplit=1)[0]
        numbers = re.findall(r"\d+", first)
        return str(payload["counted_entries"]) in numbers and str(payload["total_entries"]) in numbers

    def _routes_first(self, action: str) -> bool:
        """True if one of ROUTING_WORDS starts one of the action's first ROUTING_WINDOW words."""
        words = [word.casefold() for word in re.findall(r"[A-Za-z]+", action)[:ROUTING_WINDOW]]
        return any(word.startswith(root) for word in words for root in ROUTING_WORDS)

    def _numbers_from_input(self, output: str, payload: dict) -> bool:
        """True if every figure in the output also appears in the input (no counting or converting)."""
        found = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(payload)))
        return all(number in found for number in re.findall(r"\d+(?:\.\d+)?", output))

    def _load(self, file_name: str) -> list[dict]:
        with open(self.__samples_dir / file_name, encoding="utf-8") as file:
            return json.load(file)


def run_cases(live_run: LiveSummaryRun, recorder: UsageRecorder) -> list[dict]:
    """Run the three quality cases RUNS_PER_CASE times each and print each run's checks."""
    cases = {"reference": live_run.reference_records, "stress": live_run.stress_records,
             "outage": live_run.outage_records}
    results = []
    for name, build in cases.items():
        for run in range(1, RUNS_PER_CASE + 1):
            first_response = len(recorder.responses)
            payload, summary = live_run.run_case(build())
            checks = live_run.check(payload, summary)
            results.append({"case": name, "run": run, "input_chars": len(json.dumps(payload)),
                            "responses": recorder.responses[first_response:], "checks": checks,
                            "input": payload, "summary": summary})
            failed = [check for check, passed in checks.items() if not passed]
            print(f"{name} run {run}: {'PASS' if not failed else 'FAIL ' + ', '.join(failed)}")
    return results


def run_measurement(live_run: LiveSummaryRun, recorder: UsageRecorder) -> list[dict]:
    """Send ever larger call 2 requests to see token use per character and how Groq refuses an oversized one."""
    results = []
    for copies in PROBE_COPIES:
        first_response = len(recorder.responses)
        payload, summary = live_run.run_case(live_run.probe_records(copies))
        responses = recorder.responses[first_response:]
        results.append({"case": f"probe x{copies}", "input_chars": len(json.dumps(payload)),
                        "responses": responses, "succeeded": summary is not None})
        print(f"probe x{copies}: {len(json.dumps(payload))} chars, statuses {[r['status'] for r in responses]}, "
              f"usage {[r['usage'] for r in responses]}")
    return results


def run_trimmed_probe(live_run: LiveSummaryRun, recorder: UsageRecorder) -> list[dict]:
    """Send the x5 probe trimmed to TRIMMED_PROBE_CHARS, and check its summary too."""
    first_response = len(recorder.responses)
    payload, summary = live_run.run_case(live_run.probe_records(TRIMMED_PROBE_COPIES), TRIMMED_PROBE_CHARS)
    checks = live_run.check(payload, summary)
    responses = recorder.responses[first_response:]
    failed = [check for check, passed in checks.items() if not passed]
    print(f"trimmed probe: {len(json.dumps(payload))} chars, {payload.get('examples_shown')} of "
          f"{payload.get('examples_total')} examples, statuses {[r['status'] for r in responses]}, "
          f"usage {[r['usage'].get('prompt_tokens') for r in responses]} prompt tokens: "
          f"{'PASS' if not failed else 'FAIL ' + ', '.join(failed)}")
    return [{"case": "trimmed probe", "run": 1, "input_chars": len(json.dumps(payload)), "responses": responses,
             "checks": checks, "input": payload, "summary": summary}]


def recheck(live_run: LiveSummaryRun) -> None:
    """Rerun the checks on the saved results, with no API call (after a check is fixed)."""
    saved = json.loads((SAMPLES_DIR / RESULTS_FILE).read_text(encoding="utf-8"))
    for result in saved:
        if "checks" in result:
            result["checks"] = live_run.check(result["input"], result["summary"])
            failed = [check for check, passed in result["checks"].items() if not passed]
            print(f"{result['case']} run {result['run']}: {'PASS' if not failed else 'FAIL ' + ', '.join(failed)}")
    (SAMPLES_DIR / RESULTS_FILE).write_text(json.dumps(saved, indent=2), encoding="utf-8")


if __name__ == "__main__":
    if sys.argv[1:] == ["recheck"]:
        recheck(LiveSummaryRun(None, ""))
        sys.exit()
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
    usage = UsageRecorder()
    usage.install()
    manager = AIManager(GroqClient(api_key), key_label, prompts, ConsoleProgressReporter(), load_token_log, save_token_log)
    live = LiveSummaryRun(manager, prompts.summary_prompt)
    mode = sys.argv[1] if len(sys.argv) > 1 else "cases"
    saved = []
    if mode in ("cases", "all", "cases+trimmed"):
        saved += run_cases(live, usage)
    if mode in ("measure", "all"):
        saved += run_measurement(live, usage)
    if mode in ("trimmed", "cases+trimmed"):
        saved += run_trimmed_probe(live, usage)
    (SAMPLES_DIR / RESULTS_FILE).write_text(json.dumps(saved, indent=2), encoding="utf-8")
    print(f"Saved: {SAMPLES_DIR / RESULTS_FILE}")
