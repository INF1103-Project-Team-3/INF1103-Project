import json
import os
import sys
from sample_ai_output import SAMPLE_RECORDS
import io_manager
import data_manager1
import logic_manager
import ai_manager
from dotenv import load_dotenv
import logging


if __name__ == "__main__":

    logging.basicConfig(level=logging.WARNING)
    load_dotenv(os.path.join(ai_manager.BASE_DIR, "config", ".env"))
    api_key = os.environ.get("GROQ_API_KEY")
    key_label = os.environ.get("GROQ_KEY_LABEL")
    if not api_key or not key_label:
        logging.error("GROQ_API_KEY and GROQ_KEY_LABEL must be set in config/.env")
        raise SystemExit(1)

    data_manager1.init_manager()
        
    # Handles dashboard, input, output
    io_payload = io_manager.main()

    # --- INPUT/OUTPUT FIX FOR SYSTEM CUTOFF (OPTIONS 3 & 4) ---
    # If option 3 (None), option 4 ("search"), or a cancellation occurs, 
    # terminate the program instantly so read-only actions do not create files or invoke the AI loop.
    if not io_payload or io_payload == "search":
        print("Read-only operation completed. Exiting workflow.")
        sys.exit(0)

    # For options 1 and 2, test-input.json is hardcoded as the initial raw data entry file.
    filename = io_manager.TEST_INPUT_FILE
    
    # 2. Read the data out of the test-input.json file
    user_input_feedback = io_manager.read_json(filename)

    # 3. Save these feedback inputs into the data manager's persistent storage cache
    if user_input_feedback:
        data_manager1.save_to_feedback_before_ai(user_input_feedback)

    # 4. Pull the loaded entries back out from the data manager to hand directly to the AI loop
    # (By calling load_or_create_feedback_before_ai, we extract the unified list under the 'records' key)
    data_cache = data_manager1.load_or_create_feedback_before_ai()
    entries = data_cache.get("records", [])


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
        # Immediately feed back any newly coined theme into the 'known' list for the next loop iteration
        known = ai_manager.find_new_themes([record], themes, known)
        classified_records.append(record)


    # --- REMOVED MOCK DATA PLACEHOLDER ---
    # If the live API fails or comes back empty, fall back to SAMPLE_RECORDS to keep pipeline intact
    if not classified_records:
        classified_records = SAMPLE_RECORDS 
    # --- REMOVED MOCK DATA PLACEHOLDER ---


    # This automatically produces sequential text file logs on disk (ai_output_1.json, etc.)
    data_manager1.receive_ai_input(json.dumps(classified_records))

    # Logic manager to process feedback from AI manager
    processed_feedbacks = [logic_manager.apply_feedback_rules(record) for record in classified_records]

    # --- Commit the processed feedback cleanly to data storaage ---
    # This automatically produces the /data/feedback_store.json file
    data_manager1.save_feedback_dict(processed_feedbacks)

    # Logic manager to create input for AI manager summary
    logic_output = logic_manager.aggregate_themes(processed_feedbacks)

    # # --- Call 2: Final Run Summary ---
    # CONNECTED TO LIVE API: Generates overall executive summaries using live stats data
    summary = ai_manager.summarise(logic_output, summary_prompt, api_key, key_label)

    # This produces the main /data/summary.json base statistical distribution fields file
    data_manager1.save_summary(logic_output)

    # --- FIX 3: Guard summary field parsing against NoneType API responses ---
    # This automatically injects overall_summary text and theme_actions arrays into summary.json
    if summary is not None:
        data_manager1.update_summary_fields(
            root_updates={"overall_summary": summary.get("overall_summary")},
            item_updates=summary.get("theme_actions")
        )


    # review queue for logic manager
    review_queue = logic_manager.rank_review_queue(processed_feedbacks)
   



    # PLACEHOLDER SEARCH COMMAND, SHOULD BE IN IO MANAGER
    if io_payload == "search":
        while True:
            query = input("\nEnter search keywords (or type 'exit' to quit): ").strip()
            
            if query.lower() in ("exit", "quit", "q"):
                print("Exiting search console. Goodbye!")
                break
                
            if not query:
                continue
                
            results = data_manager1.search_records(query)
            
            print(f"\nFound {len(results)} matching feedback entry/entries:\n")
            print("-" * 65)
            
            if results:
                for idx, item in enumerate(results, 1):
                    text = item.get('text') or item.get('feedback') or item.get('summary') or 'N/A'
                    topic = item.get('topic') or item.get('theme') or 'N/A'
                    
                    print(f"Result #{idx}")
                    print(f"  Feedback ID : {item.get('feedback_id', 'N/A')}")
                    print(f"  Feedback    : {text}")
                    print(f"  Timestamp   : {item.get('timestamp', 'N/A')}")
                    print(f"  Sentiment   : {str(item.get('sentiment', 'N/A')).upper()}")
                    print(f"  Severity    : {str(item.get('severity', 'N/A')).upper()}")
                    print(f"  Topic       : {topic}")
                    print("-" * 65)
            else:
                print("No records matched your search query.")

    # PLACEHOLDER SEARCH COMMAND, SHOULD BE IN IO MANAGER



    

