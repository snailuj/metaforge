"""Populate synset_properties junction table from pilot data."""
import json
import sqlite3

from utils import PILOT_FILE, LEXICON_V2, normalise


def main():
    if not PILOT_FILE.exists():
        raise FileNotFoundError(f"Pilot file not found: {PILOT_FILE}")
    if not LEXICON_V2.exists():
        raise FileNotFoundError(f"Database not found: {LEXICON_V2}")

    print("Loading pilot data...")
    with open(PILOT_FILE) as f:
        pilot = json.load(f)

    # Get model from pilot config
    model_used = pilot.get("config", {}).get("model", "unknown")
    print(f"  Model used: {model_used}")

    conn = sqlite3.connect(LEXICON_V2)

    # Build property_id lookup from vocabulary
    prop_ids = {}
    for row in conn.execute("SELECT property_id, text FROM property_vocabulary"):
        prop_ids[row[1]] = row[0]

    print(f"  {len(prop_ids)} properties in vocabulary")

    # Create enrichment entries and link properties
    links = 0
    synsets_processed = 0

    for synset in pilot["synsets"]:
        synset_id = synset["id"]

        # Insert enrichment record
        conn.execute("""
            INSERT OR IGNORE INTO enrichment (synset_id, model_used)
            VALUES (?, ?)
        """, (synset_id, model_used))

        # Link properties
        for prop in synset.get("properties", []):
            prop_norm = normalise(prop)
            if prop_norm in prop_ids:
                conn.execute("""
                    INSERT OR IGNORE INTO synset_properties (synset_id, property_id)
                    VALUES (?, ?)
                """, (synset_id, prop_ids[prop_norm]))
                links += 1

        synsets_processed += 1

    conn.commit()
    conn.close()

    print(f"\nPopulation complete!")
    print(f"  Synsets processed: {synsets_processed}")
    print(f"  Synset-property links created: {links}")


if __name__ == "__main__":
    main()
