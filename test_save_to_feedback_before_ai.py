import os
from pathlib import Path
from data_manager1 import save_to_feedback_before_ai, load_or_create_feedback_before_ai

# Use environment variable or fallback to local ./data folder
DATA_DIR = os.getenv("DATA_DIR", "./data")

print(f"Targeting directory: {Path(DATA_DIR).resolve()}")

# 1. Sample payload containing MULTIPLE feedback items at once
incoming_batch = [
    {
        "feedback_id": "raw_fb_001",
        "user_input": "System response time is fast.",
        "source": "cli"
    },
    {
        "feedback_id": "raw_fb_002",
        "user_input": "Need ability to store batches before AI processes them.",
        "source": "ai_pipeline"
    }
]

# 2. Save batch to feedback_before_ai.json
print("\nSaving batch data into feedback_before_ai.json...")
save_to_feedback_before_ai(incoming_batch, base_dir=DATA_DIR)

# 3. Read back from disk to confirm
saved_data = load_or_create_feedback_before_ai(base_dir=DATA_DIR)

print(f"\n[SUCCESS] File saved!")
print(f"Total entries in feedback_before_ai.json: {len(saved_data['records'])}")
print("\nCurrent File Content:")
print(saved_data)