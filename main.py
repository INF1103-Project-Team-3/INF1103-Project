"""
main.py

    input.json (dynamic - swapped in via Docker volume mount)
        -> I/O Manager       (takes the file, loads and validates it, returns records)
        -> Data Manager      (stores the input records)
        -> AI Manager        (1st call: classifies each stored record)
        -> Data Manager      (stores the AI Manager's output)
        -> Logic Manager     (retrieves that data from the Data Manager)
        -> AI Manager        (2nd call: generate a summary)
        -> Data Manager      (stores the summary)
"""

import logging
import os

from dotenv import load_dotenv

# =====================================================================
# Change according to specifications
# =====================================================================
import io_manager
import ai_manager
import logic_manager
import data_manager


def main():
    # --- Setup (once per run) ------------------------------------------
    # Set up logging first so warnings from every manager are shown.
    # A missing key or bad config fails here before anything else is done.
    logging.basicConfig(level=logging.WARNING)
    load_dotenv(os.path.join(ai_manager.BASE_DIR, "config", ".env"))
    api_key = os.environ["GROQ_API_KEY"]
    key_label = os.environ["GROQ_KEY_LABEL"]
    themes = ai_manager.load_canonical_themes()
    prompt = ai_manager.load_system_prompt(themes)

    # -------------------------------------------------------------
    # Path to the input JSON. Read from the INPUT_FILE env var set in
    # the Dockerfile (or overridden at `docker run` time), so the file
    # can be swapped without rebuilding the image. main.py only passes
    # the path along - it does not open the file.
    # -------------------------------------------------------------
    input_path = os.environ.get("INPUT_FILE", "input.json")

    # --- Step 1: I/O Manager ------------------------------------------
    # CHANGE HERE if your function has a different name.
    # Takes the file path, reads and validates the JSON, and returns
    # the cleaned records. Bad or missing files are handled inside it.
    io_output = io_manager.process(input_path)

    # --- Step 2: Data Manager (store the input records) -----------------
    # CHANGE HERE: label is a placeholder, as in the other saves.
    data_manager.save(io_output, label="input")

    # --- Step 3: AI Manager (1st call: classify) -------------------------
    # Themes the model coined in earlier runs, fed back so it reuses them.
    # data_manager.load() must return [] when nothing is stored yet.
    known = ai_manager.find_new_themes(data_manager.load(label="classified_records"), themes)
    # known: ["Unclear"]

    entries = data_manager.load(label="input")
    # entries (same shape as config/test-input.json):
    # [{"feedback_id": "fb_001",
    #   "text": "I can't keep up with the lecturer's slides, ...",
    #   "timestamp": "2026-09-15T10:32:00"}, ...]

    classified_records = []
    for entry in entries:
        record = ai_manager.classify_entry(entry, prompt, api_key, key_label, known)
        # record: entry plus six AI fields, or None if it failed after retries
        # {"feedback_id": "fb_001", "text": "...", "timestamp": "...",
        #  "theme": "Teaching Quality",  # themes.json, "Unclear" or a new label
        #  "sentiment": "negative",      # positive / neutral / negative
        #  "severity": "medium",         # low / medium / high / critical
        #  "summary": "Lecturer's slides move too fast, ...",  # 15 words max
        #  "confidence": 0.9,            # 0.0 to 1.0; flag confidence < 0.9 for review
        #  "agreement": 1.0}             # 1.0 / 0.67 / 0.33; below 1.0: unstable
        if record is None:  # not stored anywhere, so classified_records can be shorter than entries
            continue
        known = ai_manager.find_new_themes([record], themes, known)
        classified_records.append(record)
    # classified_records (same shape as config/test-output.json): [record, record, ...]
    # Review rules (e.g. agreement below 1.0, critical severity) belong in logic_manager.

    # --- Step 4: Data Manager (store the classified records) -----------
    # CHANGE HERE: the label is how the Data Manager tells the saves
    # in this run apart, so one save doesn't overwrite another.
    data_manager.save(classified_records, label="classified_records")

    # --- Step 5: Logic Manager (retrieves data from the Data Manager) ---
    # The Logic Manager works on what was just stored, not on the AI
    # output passed directly - the Data Manager is the hand-off point.
    stored_data = data_manager.load(label="classified_records")
    logic_output = logic_manager.process(stored_data)

    # --- Step 6: AI Manager (2nd call - summary) ------------------------
    # Different job from the 1st call, so it uses a separate function.
    summary = ai_manager.summarize(logic_output)

    # --- Step 7: Data Manager (store the summary) ------------------------
    data_manager.save(summary, label="summary")


if __name__ == "__main__":
    main()
