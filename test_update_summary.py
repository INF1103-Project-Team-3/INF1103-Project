from data_manager1 import update_summary_fields
import json

DATA_DIR = "./data"

# Test updating sum_001 summary text and overall_summary key
success = update_summary_fields(
    root_updates={
        "overall_summary": "System review complete with zero open blockers."
    },
    item_updates={
        "summary_id": "sum_001",
        "summary": "Docker volume mount configuration finalized."
    },
    base_dir=DATA_DIR
)

if success:
    with open(f"{DATA_DIR}/summary.json", "r") as f:
        print("\nUpdated summary.json Content:\n")
        print(f.read())