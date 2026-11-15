# FeedbackLens

**AI-assisted student feedback analyser**: INF1103 Programming Fundamentals, Team P6 Group 3.

FeedbackLens takes free-text student feedback, has a large language model check each entry's theme, sentiment and severity against the student's own, applies business rules to decide what an admin must review, and shows a dashboard of themes ranked by priority, with trends across runs, suggested actions and a measure of whether logged actions helped.

It is object-oriented Python 3.11, split into five managers that talk through a pipeline, with a terminal interface and a PySide6 GUI. It stores everything in JSON files, runs in Docker and calls the Groq API (`openai/gpt-oss-120b`). It keeps working when the AI is unavailable.

---

## Features

- **Two ways in:** students submit one entry with their own theme, sentiment and severity; admins can also type entries or import a CSV or JSON file.
- **Input validation:** every entry needs `text`, `theme`, `sentiment` and `severity`; imported rows also need `feedback_id` and `timestamp` (`YYYY-MM-DDTHH:MM:SS`). Text must contain letters and be at most 2,000 characters. Rejected rows are listed with the reason, and rows whose ID is already saved are skipped and reported.
- **AI check (Call 1):** each entry is classified once (theme, sentiment, severity and a one-line summary of at most 15 words). Requests retry on rate limits and server errors and pace themselves from Groq's rate-limit headers.
- **Business rules:** an entry goes to the review queue if its severity is **critical** (still counted), its theme is **new** (not counted until confirmed), its theme is **Unclear** (not counted), or the AI's values **conflict** with the student's (not counted until reviewed). Themes are normalised to the 8 base themes and any confirmed ones.
- **Statistics:** counts, sentiment and severity per theme, and a **0 to 100 priority score** (severe share 45, frequency 35, negative sentiment 20).
- **Trends:** each run compares every theme's priority with the previous run: Escalating, Easing, Steady, New or Not reported (a change of 5 points or more counts).
- **AI summary (Call 2):** an overall summary and one suggested action per theme, sent the entries' one-line summaries.
- **AI down:** with no key, a lost connection or a rejected key, the run still completes: entries keep the student's values, are marked Unverified and sent to the AI again next run, and suggested actions come from keyword rules, labelled as such.
- **Review:** admins set their own values, accept the AI's, or delete the entry; the GUI also offers the student's values and Confirm new theme.
- **Action tracking and impact (new feature):** admins log an action against a theme; each run compares negative feedback in the two weeks before and after it and labels it Effective, No change, Worse or Too early to tell, with a weekly chart.
- **GUI (advanced feature):** a PySide6 window (Dashboard, Add feedback, Feedback, Trends and actions, Settings) that runs the pipeline on a background thread, so pages stay usable during a run.
- **Safe storage:** corrupt data files are moved aside instead of overwritten, writes are atomic, and saved entries are never processed twice.

---

## Repository structure

```
.
├── managers/
│   ├── main.py              # entry point: python -m managers.main [--gui]
│   ├── models/              # FeedbackRecord, Action and the shared constants
│   ├── io_manager/          # terminal menus, validation, import, review
│   ├── ai_manager/          # Groq client, Call 1 and Call 2, retries, token log
│   ├── logic_manager/       # rules, statistics, priority, trends, impact, rule-based actions
│   ├── data_manager/        # JSON and CSV storage
│   ├── pipeline/            # AppEngine and the six pipeline steps
│   ├── gui/                 # PySide6 window, pages and widgets
│   └── config/
│       ├── system_prompt.txt, summary_prompt.txt   # the two prompts
│       └── .env.example                             # copy to .env and fill in
├── data/                    # what the app saves (git-ignored); test-input.json is a sample
├── submission/              # execution_script.py and its sample AI replies
├── tests/                   # pytest tests, one folder per manager plus the pipeline and GUI
├── requirements/            # requirements.txt (app) and gui.txt (PySide6, pytest-qt)
├── Dockerfile, docker-compose.yml, pytest.ini
└── .github/workflows/ci.yml
```

Each class has its own file, named after it.

---

## Getting started

### 1. Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/): the app runs in a container, so Python is not needed locally.
- A free Groq API key from [console.groq.com](https://console.groq.com/keys). Optional: without it the app runs with the AI unavailable.

### 2. Settings

Copy `managers/config/.env.example` to `managers/config/.env` and fill it in:

| Variable | Meaning |
|---|---|
| `GROQ_API_KEY` | Your Groq key |
| `GROQ_KEY_LABEL` | Any short name for that key; the daily token log is kept per label. The AI counts as unavailable without it |
| `ADMIN_PASSWORD` | The admin password; left empty, admin login is turned off |

`.env` is git-ignored and kept out of the Docker image. **Never commit it.**

### 3. Run

From the repository root:

```bash
docker compose build
```

```bash
docker compose run --rm app
```

That starts the terminal version. For the GUI:

```bash
docker compose up --build gui
```

then open http://localhost:6080. Without Docker, after `pip install -r requirements/requirements.txt -r requirements/gui.txt`, run `python -m managers.main` or `python -m managers.main --gui` from the repository root.

The repository is mounted into the container, so code changes apply without rebuilding and everything the app saves stays in `data/`.

---

## Using FeedbackLens

Choose **user** or **admin** at the start. Type `quit` at a prompt to cancel it.

**User:** enter one piece of feedback with its theme, sentiment and severity. In the terminal it is processed straight away; in the GUI it waits until an admin presses Process.

**Admin** (the password is `ADMIN_PASSWORD`):

| Option | What it does |
|---|---|
| 1. Feedback Entry | Type one entry |
| 2. CSV or JSON import | Import a file; asks again for a path it cannot read |
| 3. Dashboard | Themes by priority with trend status, summary, suggested actions and the review queue |
| 4. Search Feedback | Keyword search over saved feedback |
| 5. Review flagged feedback | Decide each flagged entry |
| 6. Log an action | Record an action against a theme, to measure its impact |
| 7. Settings | Known themes, add a theme, system status |
| 8. Finish and run analysis | Runs the pipeline on everything collected, then shows the dashboard |

The GUI offers the same through its pages; Process (or Save changes) starts a run.

Example import file:

```csv
feedback_id,text,timestamp,theme,sentiment,severity
fb_101,The lecture recordings are often missing audio.,2026-10-01T09:30:00,Teaching Quality,negative,medium
fb_102,Really enjoyed the guest talk on industry placements!,2026-10-01T11:00:00,Internship Placement,positive,low
```

---

## Themes

Teaching Quality · Assessment · Facilities · Administration · Well-being · Social Environment · Workload · Internship Placement

A student may write another theme. It is flagged as new and counted once an admin confirms it (in a review or in Settings); filler such as "n/a" becomes Unclear.

---

## Testing

```bash
docker compose run --rm app pytest tests/
```

```bash
docker compose run --rm app python submission/execution_script.py
```

The tests need no API key or network: the AI is replaced by a stub client, storage by temporary folders, and the GUI tests draw offscreen. `execution_script.py` checks the core logic with sample AI replies and prints a PASS / FAIL report (exit code 1 on a failure); pass `sample_ai_output1` or `sample_ai_output2` to use another sample.

CI runs on every pull request to `main` and in the merge queue: it compiles every Python file, builds the Docker image and runs the full test suite in it.
