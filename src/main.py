import json
 
import io_manager
 
 
def main():
    payload = io_manager.main()
    if payload is None:
        return  # cancelled, or no valid rows to send
 
    # --- Temporary checker: confirms the payload arrived. ----------------------
    if isinstance(payload, str):  # single entry: JSON string
        print("\n[check] single entry:", json.loads(payload))
    else:  # file import: (filename, bytes, mime_type)
        filename, content, mime_type = payload
        print(f"\n[check] file: {filename} ({mime_type}, {len(content)} bytes)")
        print("[check] rows:", json.loads(content))
    # ----------------------------------------------------------------------------
 
 
if __name__ == "__main__":
    main()