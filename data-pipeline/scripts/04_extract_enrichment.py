# data-pipeline/scripts/04_extract_enrichment.py
"""
Extract enriched data from synsets using Gemini Flash.

Extracts in a single call:
- Structural properties (for metaphor matching)
- Metonyms (2-3 per word)
- Connotation (positive/neutral/negative)
- Register (formal/neutral/informal/slang)
- Usage example (1-2 sentences)

Uses Gemini Flash 2.5 Lite by default. Escalate to Flash 2.5 or 3.0 if quality poor.
"""
import sqlite3
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Optional
from tqdm import tqdm

try:
    import google.generativeai as genai
except ImportError:
    raise ImportError("Run: pip install google-generativeai")

RAW_DIR = Path(__file__).parent.parent / "raw"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

BATCH_SIZE = 30  # Synsets per API call
RATE_LIMIT_DELAY = 1.0  # Seconds between calls

# Model selection - start with cheapest, escalate if quality poor
# Options: "gemini-2.5-flash-lite", "gemini-2.5-flash"
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

EXTRACTION_PROMPT = """You are extracting enriched linguistic data from word senses.

For each word sense, extract:
1. **properties**: 5-10 abstract/structural properties describing what it DOES, how it BEHAVES, or what ROLE it plays. Focus on properties that could apply to things in OTHER domains.
2. **metonyms**: 2-3 words commonly used as metonyms for this concept (e.g., "crown" for "monarchy"). Return empty array if none.
3. **connotation**: "positive", "neutral", or "negative"
4. **register**: "formal", "neutral", "informal", or "slang"
5. **usage_example**: One natural sentence using this word sense.

Return JSONL (one JSON object per line).

---

Input:
anchor.n.01 | a mechanical device that prevents a vessel from moving
river.n.01 | a large natural stream of water
grief.n.01 | intense sorrow caused by loss

Output:
{"id": "anchor.n.01", "properties": ["holds_in_place", "prevents_drift", "provides_stability", "heavy", "deployed_deliberately"], "metonyms": [], "connotation": "neutral", "register": "neutral", "usage_example": "The captain ordered the crew to drop anchor in the sheltered bay."}
{"id": "river.n.01", "properties": ["flows", "carries_things", "has_source_and_destination", "shaped_by_terrain", "can_overflow", "erodes_over_time"], "metonyms": [], "connotation": "neutral", "register": "neutral", "usage_example": "The river wound through the valley, carving its path over centuries."}
{"id": "grief.n.01", "properties": ["heavy", "comes_in_waves", "holds_in_place", "isolating", "gradually_subsides", "requires_processing"], "metonyms": ["tears", "mourning"], "connotation": "negative", "register": "neutral", "usage_example": "Her grief was overwhelming in the weeks after the funeral."}

---

Input:
{batch}

Output:
"""

def get_synsets_for_pilot(conn: sqlite3.Connection, limit: int = 1000) -> List[Dict]:
    """Get pilot synsets: high frequency + good POS coverage."""
    cursor = conn.execute("""
        SELECT s.synset_id, s.definition
        FROM synsets s
        JOIN lemmas l ON s.synset_id = l.synset_id
        JOIN frequencies f ON l.lemma = f.lemma
        WHERE s.pos IN ('n', 'v', 'a')
        GROUP BY s.synset_id
        ORDER BY MAX(f.zipf) DESC
        LIMIT ?
    """, (limit,))

    return [{"id": row[0], "definition": row[1]} for row in cursor.fetchall()]

def extract_batch(model, synsets: List[Dict]) -> List[Dict]:
    """Extract enrichment for a batch of synsets."""
    batch_input = "\n".join(
        f"{s['id']} | {s['definition']}" for s in synsets
    )

    prompt = EXTRACTION_PROMPT.replace("{batch}", batch_input)

    response = model.generate_content(prompt)

    # Parse JSONL output
    results = []
    for line in response.text.strip().split('\n'):
        line = line.strip()
        if line.startswith('{'):
            try:
                obj = json.loads(line)
                if 'id' in obj and 'properties' in obj:
                    results.append(obj)
            except json.JSONDecodeError:
                continue

    return results

def extract_enrichment():
    """Main extraction pipeline."""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY environment variable")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL_NAME)

    print(f"Using model: {MODEL_NAME}")

    conn = sqlite3.connect(OUTPUT_DIR / "lexicon.db")

    # Create enrichment table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS enrichment (
            synset_id TEXT PRIMARY KEY,
            properties TEXT NOT NULL,
            metonyms TEXT,
            connotation TEXT,
            register TEXT,
            usage_example TEXT,
            model_used TEXT,
            extracted_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_enrichment_synset ON enrichment(synset_id)")

    # Get pilot synsets
    synsets = get_synsets_for_pilot(conn, limit=1000)
    print(f"Processing {len(synsets)} synsets...")

    success_count = 0
    error_count = 0

    # Process in batches
    for i in tqdm(range(0, len(synsets), BATCH_SIZE), desc="Batches"):
        batch = synsets[i:i + BATCH_SIZE]

        try:
            results = extract_batch(model, batch)

            # Store results
            for r in results:
                conn.execute("""
                    INSERT OR REPLACE INTO enrichment
                    (synset_id, properties, metonyms, connotation, register, usage_example, model_used)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    r['id'],
                    json.dumps(r.get('properties', [])),
                    json.dumps(r.get('metonyms', [])),
                    r.get('connotation'),
                    r.get('register'),
                    r.get('usage_example'),
                    MODEL_NAME
                ))
                success_count += 1

            conn.commit()

        except Exception as e:
            print(f"\nError on batch {i}: {e}")
            error_count += len(batch)
            continue

        # Rate limiting
        time.sleep(RATE_LIMIT_DELAY)

    # Report
    print(f"\nExtracted enrichment for {success_count} synsets")
    print(f"Errors: {error_count}")

    # Sample output for quality review
    print("\n--- Sample output for quality review ---")
    cursor = conn.execute("""
        SELECT synset_id, properties, metonyms, connotation, register, usage_example
        FROM enrichment LIMIT 5
    """)
    for row in cursor:
        print(f"\n{row[0]}:")
        print(f"  Properties: {row[1]}")
        print(f"  Metonyms: {row[2]}")
        print(f"  Connotation: {row[3]}, Register: {row[4]}")
        print(f"  Example: {row[5]}")

    conn.close()

if __name__ == "__main__":
    extract_enrichment()
