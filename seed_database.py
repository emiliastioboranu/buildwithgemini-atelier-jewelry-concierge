"""Seed script for Atelier Jewelry Concierge Firestore database using REST API with retries."""

import json
import subprocess
import time
import urllib.request

PROJECT_ID = "qwiklabs-gcp-02-7f7d198e8c1e"

SAMPLE_JEWELRY = [
    {
        "id": "ring-001",
        "name": "Eternity Solitaire Diamond Ring",
        "category": "Rings",
        "material": "18k Yellow Gold",
        "gemstone": "Diamond",
        "price": 1250.00,
        "description": "A timeless 18k yellow gold ring featuring a brilliant solitaire diamond.",
        "stock": 5,
    },
    {
        "id": "necklace-002",
        "name": "Celestial Sapphire Pendant Necklace",
        "category": "Necklaces",
        "material": "Sterling Silver",
        "gemstone": "Blue Sapphire",
        "price": 480.00,
        "description": "Elegant sterling silver chain with a deep blue sapphire pendant surrounded by delicate zircon accents.",
        "stock": 8,
    },
    {
        "id": "earrings-003",
        "name": "Royal Emerald Drop Earrings",
        "category": "Earrings",
        "material": "18k White Gold",
        "gemstone": "Emerald",
        "price": 890.00,
        "description": "Stunning 18k white gold drop earrings with vivid green Colombian emeralds.",
        "stock": 3,
    },
    {
        "id": "bracelet-004",
        "name": "Art Deco Ruby Tennis Bracelet",
        "category": "Bracelets",
        "material": "Rose Gold",
        "gemstone": "Ruby",
        "price": 1600.00,
        "description": "Exquisite rose gold tennis bracelet set with vibrant rubies in a classic vintage style.",
        "stock": 4,
    },
    {
        "id": "ring-005",
        "name": "Minimalist Pearl Band Ring",
        "category": "Rings",
        "material": "14k Yellow Gold",
        "gemstone": "Akoya Pearl",
        "price": 320.00,
        "description": "Delicate 14k gold band featuring a lustrous Akoya freshwater pearl.",
        "stock": 12,
    },
]


def encode_val(val):
    if isinstance(val, str):
        return {"stringValue": val}
    elif isinstance(val, (int, float)):
        return {"doubleValue": float(val)}
    elif isinstance(val, bool):
        return {"booleanValue": val}
    return {"stringValue": str(val)}


def seed_database():
    token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
    print(f"Seeding Firestore for project '{PROJECT_ID}' via REST API...")

    for item in SAMPLE_JEWELRY:
        doc_id = item["id"]
        fields = {k: encode_val(v) for k, v in item.items() if k != "id"}
        url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents/jewelry_items/{doc_id}"

        success = False
        for attempt in range(3):
            time.sleep(1)
            req = urllib.request.Request(
                url,
                data=json.dumps({"fields": fields}).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                method="PATCH",
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    print(f"Seeded item: {doc_id} -> {item['name']} (status {resp.status})")
                    success = True
                    break
            except Exception as e:
                print(f"Attempt {attempt + 1} failed for {doc_id}: {e}")

        if not success:
            print(f"Failed to seed {doc_id} after 3 attempts.")

    print("Seeding complete!")


if __name__ == "__main__":
    seed_database()
