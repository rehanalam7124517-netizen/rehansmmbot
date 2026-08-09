import os
import json
import requests
from urllib.parse import quote
from datetime import datetime

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

TABLE = "bot_data"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=minimal"
}

for filename in os.listdir("."):

    if not filename.endswith(".json"):
        continue

    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

        payload = {
            "filename": filename,
            "data": data,
            "updated_at": datetime.utcnow().isoformat() + "Z"
        }

        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=HEADERS,
            json=payload,
            timeout=30
        )

        if response.status_code in (200, 201, 204):
            print(f"✅ Uploaded: {filename}")
        else:
            print(
                f"❌ Failed: {filename} | "
                f"{response.status_code} | "
                f"{response.text[:200]}"
            )

    except Exception as e:
        print(f"❌ Error: {filename} | {e}")

print("\n🎉 Migration finished.")
