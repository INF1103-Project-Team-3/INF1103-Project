import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import logging

import io_manager
import data_manager
import logic_manager
import ai_manager


def refresh_aggregated_output(data_dir):
    """Re-aggregates every stored record and saves aggregated_output.json. Returns the stats.

    Admin reviews change processed_feedback.json, so running this picks them up without
    calling the AI. Only the latest copy of each feedback_id is used, and every record is
    checked and has the rules re-applied, so a reviewed entry is counted exactly once."""
    records = data_manager.load_feedback_records(base_dir=data_dir)
    latest = {record.get("feedback_id"): record for record in records if isinstance(record, dict)}
    valid_records, _ = logic_manager.split_valid_records(list(latest.values()))
    stats = logic_manager.aggregate_themes(
        [logic_manager.apply_feedback_rules(record) for record in valid_records])
    data_manager.aggregate_themes(stats, base_dir=data_dir)
    return stats


def refresh_dashboard(data_dir):
    """Brings the dashboard files up to date with any reviews done since the last import:
    the totals (aggregated_output.json) and the trend (trend_output.json). The trend still
    compares against the run before the last import, the same as when it was first made."""
    stats = refresh_aggregated_output(data_dir)
    try:
        history = data_manager.load_history(base_dir=data_dir)
    except ValueError as error:   # corrupt history file: left unchanged, trend not refreshed
        logging.error("%s The trend was not refreshed.", error)
        return
    if history:
        trend = logic_manager.compare_runs(stats, history[1] if len(history) > 1 else None)
        data_manager.save_trend(trend, filename=io_manager.TREND_FILE, base_dir=data_dir)


if __name__ == "__main__":

    # AI Manager config init
    logging.basicConfig(level=logging.WARNING)
    load_dotenv(os.path.join(ai_manager.BASE_DIR, "config", ".env"))
    api_key = os.environ.get("GROQ_API_KEY")
    key_label = os.environ.get("GROQ_KEY_LABEL")
    if not api_key or not key_label:
        logging.error("GROQ_API_KEY and GROQ_KEY_LABEL must be set in config/.env")
        raise SystemExit(1)

    # Every data_manager call below is pointed at the same folder the I/O manager uses.
    # (data_manager's own default is "/data", which on Windows is C:\data, a different folder.)
    DATA_DIR = io_manager.DATA_DIRECTORY
    os.environ["DATA_DIR"] = DATA_DIR    # receive_ai_input() reads this

    # Check if data folder is created, then load what is already stored (used by Search)
    data_manager.init_manager(os.path.join(DATA_DIR, "aggregated_output.json"))
    data_manager.load_feedback_records(base_dir=DATA_DIR)

    # Pick up any reviews done in an earlier session, so the dashboard shows them
    refresh_dashboard(DATA_DIR)

    # Handles dashboard, input, output
    io_payload = io_manager.main()    

    # Prevent ERROR MESSAGES WHEN USING OPTION 1 and 2
    if io_payload is None or io_payload == "exit":
        refresh_dashboard(DATA_DIR)    # saves any reviews just made in the dashboard
        sys.exit(0)


##########################Prevent duplicate entries###############################

    # Only this run's new entries go into the cache, never the whole input file.
    if isinstance(io_payload, tuple):  # admin import: (filename, bytes, mime_type)

        new_entries = json.loads(io_payload[1])
        source_file = io_payload[0]

    else:  # single entry: dict

        new_entries = [io_payload]
        source_file = "single entry"

    # Create feedback_before_ai.json
    data_manager.save_to_feedback_before_ai(new_entries, base_dir=DATA_DIR)
 
    # Classify each feedback_id once: skip anything already in feedback_store.json,

    # and collapse the duplicate copies earlier runs left in the cache.

    stored = data_manager.load_feedback_records(base_dir=DATA_DIR)
    done = {record.get("feedback_id") for record in stored}

    # feedback_ids must be unique. A new entry that reuses the id of DIFFERENT stored feedback
    # would be skipped without a word, so say which ones were skipped.
    stored_text = {record.get("feedback_id"): record.get("text") for record in stored}
    reused_ids = [entry["feedback_id"] for entry in new_entries
                  if entry["feedback_id"] in stored_text and entry["text"] != stored_text[entry["feedback_id"]]]
    if reused_ids:
        logging.warning("Skipped %d entries whose feedback_id is already used by different feedback: %s. "
                        "Give them new IDs and import them again.", len(reused_ids), ", ".join(reused_ids))

    pending = {}

    for entry in data_manager.load_or_create_feedback_before_ai(base_dir=DATA_DIR)["records"]:

        # --- ADD THESE 2 LINES TO AVOID THE ERROR: if entry["feedback_id"] not in done---
        #                                TypeError: 'NoneType' object is not subscriptable
        if not entry or not isinstance(entry, dict):
            continue
        # ---------------------------------------------



        if entry["feedback_id"] not in done:

            pending[entry["feedback_id"]] = entry

    entries = list(pending.values())

    if not entries:

        # Tell user that there are no new unclassified entries, so there is no need to run 
        # entries through API again
        io_manager.print_no_unclassified_notice()

        sys.exit(0)


#####################End of Prevent duplicate entries###############################
    

    # --- AI Manager Initialisation ---
    themes = ai_manager.load_canonical_themes()
    prompt = ai_manager.load_system_prompt(themes)
    summary_prompt = ai_manager.load_summary_prompt()

    # Seed the theme tracking list from any previously classified entries
    known = ai_manager.find_new_themes(data_manager.load_feedback_records(base_dir=DATA_DIR), themes)

    # Tell user, that main.py is calling the API
    io_manager.print_connection_notice()

    # --- Call 1: Dynamic Entry Classification ---
    # CONNECTED TO LIVE API: Loops through entries and requests classifications via live endpoints
    classified_records = []
    for entry in entries:
        record = ai_manager.classify_entry(entry, prompt, api_key, key_label, known)
        if record is None:  
            continue
        # Immediately feed back any newly coined theme into the 'known' list for the next loop
        known = ai_manager.find_new_themes([record], themes, known)
        classified_records.append(record)
    # --- End of Call 1: Dynamic Entry Classification ---

    # If the AI could not classify anything (API down, bad key), stop here. Saving a "run" with
    # no new data would replace the real trend with an all-Steady one. The entries stay in
    # feedback_before_ai.json and are retried on the next import.
    if not classified_records:
        logging.error("The AI could not classify any of the %d new entries. They were kept and "
                      "will be retried on the next import.", len(entries))
        sys.exit(1)


    # Produces classified.json
    data_manager.receive_ai_input(json.dumps(classified_records))

    # Tell user, main.py is compiling results and aggregate themes
    io_manager.print_compilation_notice()

    # Logic manager checks every record from the AI; malformed ones are set aside
    # (saved to invalid_records.json) and never counted
    valid_records, invalid_records = logic_manager.split_valid_records(classified_records)
    data_manager.save_invalid_records(invalid_records, base_dir=DATA_DIR)

    # Logic manager to process feedback from AI manager
    processed_feedbacks = [logic_manager.apply_feedback_rules(record) for record in valid_records]

    # Produces processed_feedback.json (this logic manager's processed feedback)
    data_manager.save_feedback_dict(processed_feedbacks, base_dir=DATA_DIR)


    # Re-aggregate over the FULL set of records (past + present) and save aggregated_output.json.
    # Reviewed entries are included with the admin's corrections.
    logic_output = refresh_aggregated_output(DATA_DIR)

    # Add this run's flagged entries to for_review.json (keeps the history, newest first)
    run_at = datetime.now().isoformat(timespec="seconds")
    review_queue = logic_manager.rank_review_queue(processed_feedbacks)
    data_manager.append_for_review(
        [{**record, "run_at": run_at, "source_file": source_file} for record in review_queue],
        sort_key=logic_manager.review_sort_key,
        unique_by=lambda record: record["feedback_id"],
        base_dir=DATA_DIR,
    )
    # End of create for_review.json

    # Trend comparison: this run vs the previous run. It is worked out BEFORE this run
    # is added to the history, so the newest history entry is the previous run.
    # Produces trend_output.json and aggregated_history.json
    try:
        history = data_manager.load_history(base_dir=DATA_DIR)
    except ValueError as error:   # corrupt history file: left unchanged so it can be repaired
        logging.error("%s The trend was not updated this run.", error)
    else:
        trend = logic_manager.compare_runs(logic_output, history[0] if history else None)
        data_manager.save_trend(trend, filename=io_manager.TREND_FILE, base_dir=DATA_DIR)
        data_manager.append_history({"run_at": run_at, "source_file": source_file, "stats": logic_output},
                                    base_dir=DATA_DIR)

    # Tell user AI summary is being requested from API
    io_manager.print_ai_request_notice()

        # # --- Call 2: Final Run Summary ---
    # CONNECTED TO LIVE API: Generates overall executive summaries using live stats data
    summary = ai_manager.summarise(logic_output, summary_prompt, api_key, key_label)
        # # --- End of Call 2: Final Run Summary ---

        # Create summary.json or replace summary.json with new summary
    if summary is not None:
        data_manager.update_summary_fields(
            root_updates={"overall_summary": summary.get("overall_summary")},
            item_updates=summary.get("theme_actions"),
            base_dir=DATA_DIR,
        )


    # === CALL: Final exit notice ===
    io_manager.print_goodbye()