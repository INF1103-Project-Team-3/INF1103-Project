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

    # Handles dashboard, input, output
    io_payload = io_manager.main()    

    # Prevent ERROR MESSAGES WHEN USING OPTION 1 and 2
    if io_payload is None or io_payload == "exit":
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

    done = {record.get("feedback_id") for record in data_manager.load_feedback_records(base_dir=DATA_DIR)}

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


    # 1. PULL ALL ENTRIES from processed_feedback.json (that contains logic manager's processed feedback)
    # using the data manager
    all_records = data_manager.load_feedback_records(base_dir=DATA_DIR)

    # An admin review adds a corrected copy of an entry to the same file, so keep only the
    # latest copy of each feedback_id, then check and re-apply the rules to every record.
    # Otherwise reviewed entries would be counted twice, or never counted at all.
    latest = {record.get("feedback_id"): record for record in all_records if isinstance(record, dict)}
    valid_all, _ = logic_manager.split_valid_records(list(latest.values()))
    all_records = [logic_manager.apply_feedback_rules(record) for record in valid_all]

    # 2. Re-run the aggregate themes over the FULL set of records (past + present)
    logic_output = logic_manager.aggregate_themes(all_records)


    # Save aggregated_output.json here
    data_manager.aggregate_themes(logic_output, base_dir=DATA_DIR)

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
    history = data_manager.load_history(base_dir=DATA_DIR)
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