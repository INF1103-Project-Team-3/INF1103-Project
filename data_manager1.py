import json
import sys

if len(sys.argv) != 2:
    print("Usage: python main.py <json-file>")
    sys.exit(1)

filename = sys.argv[1]

try:
    with open(filename, "r", encoding="utf-8") as file:
        data = json.load(file)

    print(json.dumps(data, indent=2))

except FileNotFoundError:
    print(f"Error: File not found: {filename}")
    sys.exit(1)

except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON: {e}")
    sys.exit(1)