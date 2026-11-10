import json
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import logging

import io_manager
import data_manager
import logic_manager
# The AI Manager is a package now (D8); the flat ai_manager module is gone.
from managers.ai_manager import AIManager, ConsoleProgressReporter, GroqClient, PromptLibrary


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
    # D20: the app must keep working with the AI down, so a missing key or key
    # label no longer exits. Either one makes this an AI-down run: Call 1 and
    # Call 2 are skipped, records keep the user's values and are marked
    # unverified by Logic, and the AI retries them on the next run that has both.
    # The label is needed as well as the key because the token ledger counts
    # each key's daily use under it.
    logging.basicConfig(level=logging.WARNING)
    load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")  # managers/config/.env
    api_key = os.environ.get("GROQ_API_KEY")
    key_label = os.environ.get("GROQ_KEY_LABEL")
    ai_configured = bool(api_key and key_label)
    if not ai_configured:
        logging.error("GROQ_API_KEY and GROQ_KEY_LABEL must both be set in managers/config/.env. "
                      "The AI is skipped this run and records keep the user's values.")

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
    

    # --- AI Manager Initialisation (section 6, step 0) ---
    # HANDOVER TO THE PIPELINE OWNER (A20, A25): this block and Call 2 below are
    # written against the Part 2 interfaces (sections 6 and 8). The code around
    # them is still Part 1's (dict entries, data_manager / logic_manager module
    # functions), so it needs, from the pipeline:
    #   data           a DataManager (load_prompts, load_known_themes, load_records,
    #                  update_pending, load_token_log, save_token_log)
    #   records        this run's new and unverified records, as FeedbackRecord objects
    #   stored_records every stored FeedbackRecord, so the AI reuses labels it coined
    #   result         LogicManager.aggregate(...)'s AggregationResult for this run
    # Moving these lines into AIClassificationStep and SummaryStep keeps the
    # control flow below unchanged.
    system_template, summary_prompt = data.load_prompts()
    prompts = PromptLibrary(system_template, summary_prompt, data.load_known_themes())
    ai = AIManager(
        GroqClient(api_key), key_label, prompts, ConsoleProgressReporter(), data.load_token_log, data.save_token_log
    )

    # --- Call 1: classify every new or unverified record (section 6, step 3) ---
    # classify_entries never exits: it returns (classified, pending, stopped).
    # stopped is True when the API is down for the whole batch (a rejected key,
    # every attempt lost to connection errors, or a rate-limit wait over a
    # minute), after about 96 seconds at worst; the records not reached are left
    # pending. Each classified record is saved at once through on_classified, so
    # paid work survives a crash.
    if ai_configured:
        # Tell user, that main.py is calling the API
        io_manager.print_connection_notice()
        classified_records, pending_records, ai_stopped = ai.classify_entries(
            records, stored_records, on_classified=data.update_pending
        )
    else:
        # AI-down run (no key or label): nothing is sent, every record stays pending.
        classified_records, pending_records, ai_stopped = [], list(records), True
    # --- End of Call 1 ---

    # D20: an AI failure never stops the run. Part 1 exited here when nothing was
    # classified; now the run carries on to the Logic Manager. A record whose
    # Call 1 failed keeps ai = None, so Logic gives it the user's values, marks
    # it unverified and still counts it (section 7.1), and it is sent to the AI
    # again on the next run. The trend is updated as normal (C20).
    if ai_stopped:
        logging.warning("The AI is unavailable: %d of %d records keep the user's values and will be "
                        "retried on the next run.", len(pending_records), len(records))


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

    # --- Call 2: the run's summary (section 6, step 5) ---
    # Skipped when Call 1 stopped: the API is then unlikely to answer, and each
    # attempt would add up to 30 seconds. summarise also returns None when every
    # attempt fails, including Groq refusing an oversized request (HTTP 413).
    # Either way the last saved summary stays, with its created_at date, and
    # Logic's keyword-matched actions stand in for the AI's (D21, A24, A25:
    # logic.suggest_actions(result, records), not built yet).
    summary = None
    if not ai_stopped:
        # Tell user AI summary is being requested from API
        io_manager.print_ai_request_notice()
        summary = ai.summarise(result, records)
    # --- End of Call 2 ---

    # Save the new summary over summary.json only when Call 2 succeeded, so a
    # failed or skipped Call 2 never erases the last good one (section 9).
    if summary is not None:
        data.save_object("summary", summary)


    # === CALL: Final exit notice ===
    io_manager.print_goodbye()