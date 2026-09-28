"""
main.py

    input.json (dynamic - swapped in via Docker volume mount)
        -> I/O Manager       (takes the file, loads and validates it, returns records)
        -> AI Manager        (1st call: process the records)
        -> Data Manager      (stores the AI Manager's output)
        -> Logic Manager     (retrieves that data from the Data Manager)
        -> AI Manager        (2nd call: generate a summary)
        -> Data Manager      (stores the summary)
"""

import os

# =====================================================================
# Change according to specifications
# =====================================================================
import io_manager
import ai_manager
import logic_manager
import data_manager


def main():
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

    # --- Step 2: AI Manager (1st call) ---------------------------------
    # Every record from the I/O Manager passes through the AI here.
    ai_output = ai_manager.process(io_output)

    # --- Step 3: Data Manager (store the AI output) --------------------
    # CHANGE HERE: the label is how the Data Manager tells the two saves
    # in this run apart, so the second save doesn't overwrite the first.
    data_manager.save(ai_output, label="ai_output")

    # --- Step 4: Logic Manager (retrieves data from the Data Manager) ---
    # The Logic Manager works on what was just stored, not on the AI
    # output passed directly - the Data Manager is the hand-off point.
    stored_data = data_manager.load(label="ai_output")
    logic_output = logic_manager.process(stored_data)

    # --- Step 5: AI Manager (2nd call - summary) ------------------------
    # Different job from the 1st call, so it uses a separate function.
    summary = ai_manager.summarize(logic_output)

    # --- Step 6: Data Manager (store the summary) ------------------------
    data_manager.save(summary, label="summary")


if __name__ == "__main__":
    main()
