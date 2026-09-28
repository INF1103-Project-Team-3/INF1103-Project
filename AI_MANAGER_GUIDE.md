### **AI Manager: Quick Guide**
___

**What it does**: `ai_manager.py` sends each feedback entry to Groq (`openai/gpt-oss-120b`) and returns the entry with six AI fields added. Every LLM call in the app goes through it. It never prints (it uses `logging`) and holds no domain rules: `logic_manager` decides what the fields mean for review and counting.

### **Setup**
___

- **Dependencies**: Python 3.10 or later and `requests`; the caller also needs `python-dotenv` to load the key.
- **Key file**: create `config/.env` (git-ignored, never commit it) containing `GROQ_API_KEY=<your key>` and `GROQ_KEY_LABEL=main`. The label is any name for that key (e.g. `main`, `backup`), used only to track each key's daily token use.
- **Location**: keep `ai_manager.py` next to `config/`; it finds its files relative to itself.

| File in `config/` | Purpose |
|---|---|
| `system_prompt.txt`, `themes.json` | The prompt and the 8 canonical themes. Tuned and tested: do not edit without re-testing. |
| `test-input.json` | 30 sample input entries. |
| `test-output.json` | Real `classify_entry` output for those 30. Build and test your module against it without calling the API. |
| `test-data-ans-key.json` | Hand labels, for cross-checking accuracy only. |
| `token-usage-log.json` | Created automatically; local daily-token ledger (git-ignored). |

### **Usage**
___

```python
import logging, os
from dotenv import load_dotenv
import ai_manager

logging.basicConfig(level=logging.WARNING)  # shows ai_manager's warnings and errors
load_dotenv(os.path.join(ai_manager.BASE_DIR, "config", ".env"))
api_key, key_label = os.environ["GROQ_API_KEY"], os.environ["GROQ_KEY_LABEL"]

themes = ai_manager.load_canonical_themes()                 # once per run
prompt = ai_manager.load_system_prompt(themes)              # once per run
known = ai_manager.find_new_themes(stored_records, themes)  # stored_records: from data_manager

for entry in entries:                                       # entries: from io_manager
    record = ai_manager.classify_entry(entry, prompt, api_key, key_label, known)
    if record is None:                                      # failed after retries: retry next run
        continue
    known = ai_manager.find_new_themes([record], themes, known)
    # hand record to logic_manager.apply_record_rules, then data_manager
```

| Function | Returns |
|---|---|
| `load_canonical_themes(path=THEMES_PATH)` | The theme list. Raises `ValueError` if `themes.json` is malformed. |
| `load_system_prompt(canonical_themes, path=PROMPT_PATH)` | The prompt with `{themes}` filled in. Raises `ValueError` if the placeholder is missing. |
| `find_new_themes(records, canonical_themes, known_themes=None)` | `known_themes` plus any non-canonical themes in `records`, so a label the model coined earlier is reused, not reinvented. |
| `classify_entry(entry, system_prompt, api_key, key_label, known_themes=None)` | The classified record, or `None` if it failed. |

The remaining functions (`call_api`, `request_structured_output`, `aggregate_samples` and so on) are internal. Call 2 (`summarise`) is not written yet.

### **Input and Output**
___

**Input**: a dict with `feedback_id` and `text` (required) and `timestamp`. Any other keys are passed through unchanged.

**Output**: the same dict plus these six fields (see `test-output.json` for 30 real examples):

| Field | Values | How to read it |
|---|---|---|
| `theme` | a theme from `themes.json`, `"Unclear"`, or a new label of one to three words | `Unclear`: gibberish, spam, or no clear subject |
| `sentiment` | `positive` / `neutral` / `negative` | Mixed feedback follows the fixable complaint, not the praise |
| `severity` | `low` / `medium` / `high` / `critical` | `high`: blocks a task or access; `critical`: safety or urgent welfare |
| `summary` | text, 15 words at most | One-line restatement |
| `confidence` | 0.0 to 1.0 | The model's own estimate; it does ***not*** reliably track correctness |
| `agreement` | `1.0`, `0.67` or `0.33` | Share of the 3 samples that agreed on the least-agreed field. Below `1.0` means unstable: send to review |

### **Behaviour to Plan For**
___

- **Three calls per entry**: each entry is classified 3 times; theme, sentiment and severity take the majority value (the first sample's if all three differ).
- **Speed and quota**: about 25 to 35 seconds and 5,200 tokens per entry, so one key covers about 39 entries a day (200,000-token daily cap). `classify_entry` waits out rate limits itself, so your loop needs no `sleep`.
- **Failures**: network errors, rate limits and invalid output are retried (3 attempts per sample). If any sample still fails, it returns `None` and logs the reason; nothing is raised.
