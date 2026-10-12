import json
import os
import sys
from dotenv import load_dotenv
import logging

import io_manager
import data_manager1
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



    # Check if data folder is created
    data_manager1.init_manager()



    # Handles dashboard, input, output
    io_payload = io_manager.main()    

    # Prevent ERROR MESSAGES WHEN USING OPTION 1 and 2
    if io_payload is None or io_payload == "search" or io_payload == "exit":
        print("Workflow terminated or read-only action completed safely. Exiting.")
        sys.exit(0)


###############################################################################################

    # Only this run's new entries go into the cache, never the whole input file.
    if isinstance(io_payload, tuple):  # admin import: (filename, bytes, mime_type)

        new_entries = json.loads(io_payload[1])

    else:  # single entry: dict

        new_entries = [io_payload]

    # Create feedback_before_ai.json
    data_manager1.save_to_feedback_before_ai(new_entries)
 
    # Classify each feedback_id once: skip anything already in feedback_store.json,

    # and collapse the duplicate copies earlier runs left in the cache.

    done = {record.get("feedback_id") for record in data_manager1.load_feedback_records()}

    pending = {}

    for entry in data_manager1.load_or_create_feedback_before_ai()["records"]:

        # --- ADD THESE 2 LINES TO AVOID THE ERROR: if entry["feedback_id"] not in done---
        #                                TypeError: 'NoneType' object is not subscriptable
        if not entry or not isinstance(entry, dict):
            continue
        # ---------------------------------------------



        if entry["feedback_id"] not in done:

            pending[entry["feedback_id"]] = entry

    entries = list(pending.values())

    if not entries:

        print("Nothing new to classify.")

        sys.exit(0)


###############################################################################################


    # --- AI Manager Initialisation ---
    themes = ai_manager.load_canonical_themes()
    prompt = ai_manager.load_system_prompt(themes)
    summary_prompt = ai_manager.load_summary_prompt()

    # Seed the theme tracking list from any previously classified entries
    known = ai_manager.find_new_themes(data_manager1.load_feedback_records(), themes)


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
    data_manager1.receive_ai_input(json.dumps(classified_records))

    # Logic manager to process feedback from AI manager
    processed_feedbacks = [logic_manager.apply_feedback_rules(record) for record in classified_records]

    # Produces aggregate_output.json (but not aggregate_output, this is logic manager's processed feedback)
    data_manager1.save_feedback_dict(processed_feedbacks)

    ######################
    # 1. PULL ALL ENTRIES from aggregated_output.json(That contains logic manager's processed feedback) 
    # using the data manager
    all_records = data_manager1.load_feedback_records()

    # 2. Re-run the aggregate themes over the FULL set of records (past + present)
    logic_output = logic_manager.aggregate_themes(all_records)

############################################


        # # --- Call 2: Final Run Summary ---
    # CONNECTED TO LIVE API: Generates overall executive summaries using live stats data
    summary = ai_manager.summarise(logic_output, summary_prompt, api_key, key_label)
        # # --- End of Call 2: Final Run Summary ---

        # Create summary.json or replace summary.jsoon with new summary
    if summary is not None:
        data_manager1.update_summary_fields(
            root_updates={"overall_summary": summary.get("overall_summary")},
            item_updates=summary.get("theme_actions")
        )