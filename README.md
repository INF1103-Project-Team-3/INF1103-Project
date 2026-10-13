# FeedbackLens

**AI-powered student feedback analyser** — INF1103 Programming Fundamentals, Team P6 Group 3.

FeedbackLens takes free-text student feedback, classifies every entry with a large language model (theme, sentiment, severity, summary, confidence), applies business rules to decide what needs a human to look at it, and shows administrators a dashboard of themes ranked by priority with AI-suggested actions.

The program is procedural Python (no classes), stores everything in flat JSON files, runs in a Docker container and calls the Groq API with the `openai/gpt-oss-120b` model.

---

## Features

- **Two ways in:** users type a single piece of feedback; admins can also import a whole CSV or JSON file.
- **Input validation:** every entry needs `feedback_id`, `text` and `timestamp` (`YYYY-MM-DDTHH:MM:SS`); text must contain letters and be at most 2,000 characters. Rejected rows are listed with the reason.
- **AI classification (call 1):** each entry is classified **3 times** and the answers are combined by majority vote. An `agreement` score records how far the three runs agreed.
- **Business rules:** an entry is flagged for review if it is **critical**, if confidence is **below 0.5**, or if the three AI runs **did not fully agree**. Low-confidence or low-agreement entries are left out of the statistics until reviewed.
- **Theme statistics:** counts, sentiment and severity mix per theme, plus a **0–100 priority score** (severity 45, frequency 35, negative sentiment 20).
- **AI summary (call 2):** an overall summary and one suggested action per theme.
- **Admin dashboard and review queue:** themes ranked by priority, suggested actions, and a review queue sorted critical-first where the admin can **update**, **delete** or **skip** each flagged entry.
- **Search:** admins can search stored feedback by keyword.
- **No double processing:** entries already classified are skipped, so re-running never spends API tokens on the same feedback twice.
- **Rate-limit aware:** API calls retry on 429/5xx errors and pace themselves from Groq's rate-limit headers; daily token use is logged locally.

---

## Repository structure

```
.
├── managers/
│   ├── main.py              # entry point: runs the whole pipeline
│   ├── io_manager.py        # menus, input, validation, dashboard, review, search
│   ├── ai_manager.py        # Groq API calls (classification + summary)
│   ├── logic_manager.py     # business rules, aggregation, priority score, trends
│   ├── data_manager.py      # all JSON storage
│   └── config/
│       ├── system_prompt.txt, summary_prompt.txt   # tuned prompts (re-test before editing)
│       ├── themes.json                              # the 8 canonical themes
│       ├── test-input.json, test-output.json        # 30 sample entries + real AI output
│       ├── test-data-ans-key.json                   # hand labels for accuracy checks
│       └── .env                                     # your API key (git-ignored, create it yourself)
├── data/                    # runtime data used by the app
├── output/                  # results from running logic_manager on its own
├── submission/
│   ├── execution_script.py  # runs the logic pipeline on sample data, no API needed
│   └── sample_ai_output.py  # shared fake AI records, including edge cases
├── tests/                   # pytest tests (io_manager)
├── requirements/requirements.txt
├── Dockerfile, docker-compose.yml
├── AI_MANAGER_GUIDE.md      # how to use ai_manager in more detail
└── .github/workflows/ci.yml # CI: syntax check on every PR to main
```

---

## Getting started

### 1. Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (the app runs inside a container, so you don't need Python installed locally)
- A free Groq API key from [console.groq.com](https://console.groq.com/keys)

### 2. Add your API key

Create `managers/config/.env`:

```
GROQ_API_KEY=your_key_here
GROQ_KEY_LABEL=main
```

`GROQ_KEY_LABEL` is just a name for the key, used to track its daily token use. **Never commit `.env`**; it is already in `.gitignore`.

### 3. Build and run the container

From the repository root:

```bash
docker compose build          # first time, or after changing requirements/Dockerfile
docker compose run --rm app   # starts FeedbackLens
```

Use `run` (not `up`) so the terminal stays interactive and you can type at the prompts. `--rm` removes the container when you exit.

The container runs `python managers/main.py` on Python 3.11. Your local project folder is mounted at `/Project` and your `data/` folder at `/data`, so code changes apply without rebuilding and all results stay in `data/` on your machine between runs.

---

## Using FeedbackLens

When it starts, choose **user** or **admin**. Type `q` or `quit` at any prompt to cancel.

**User:** type one piece of feedback. It is validated, saved and sent through the pipeline.

**Admin** (default password: `123456`, set by `ADMIN_PASSWORD` in `managers/io_manager.py`):

| Option | What it does |
|---|---|
| 1. Feedback Entry | Add a single entry (shows its generated ID) |
| 2. CSV or JSON import | Import a file from the `data/` folder. Needs columns `feedback_id`, `text`, `timestamp`; extra columns are ignored. CSVs are converted to JSON first. |
| 3. Dashboard | Theme table ranked by priority, suggested actions, and the review queue |
| 4. Search Feedback | Keyword search over stored feedback |

In the review queue each flagged entry can be:
- **[u]pdate** — change theme, severity or sentiment (press Enter to keep a value; keeping all three approves it). The record leaves the queue and is added to the statistics.
- **[d]elete** — remove it permanently (asks for confirmation).
- **[s]kip** — leave it for later.

Example import file (`data/my_feedback.csv`):

```csv
feedback_id,text,timestamp
fb_101,The lecture recordings are often missing audio.,2026-10-01T09:30:00
fb_102,Really enjoyed the guest talk on industry placements!,2026-10-01T11:00:00
```

---

## Themes

Teaching Quality · Assessment · Facilities · Administration · Well-being · Social Environment · Workload · Internship Placement

The AI may suggest a new theme when nothing fits; close variants are mapped back to these eight by `logic_manager.normalise_theme`.

---

## Testing

All commands run inside the container:

```bash
# unit tests
docker compose run --rm app sh -c "pip install pytest && pytest tests/"

# logic pipeline on sample data (no API key needed)
docker compose run --rm app python submission/execution_script.py

# logic_manager on the 30 saved AI outputs, including trend vs the previous run
docker compose run --rm app python managers/logic_manager.py   # writes to output/
```

CI runs on every pull request to `main` and checks that all Python files compile.
