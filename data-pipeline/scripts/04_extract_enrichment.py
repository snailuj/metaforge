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
import logging
from pathlib import Path
from typing import List, Dict, Optional
from tqdm import tqdm

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

try:
    import google.generativeai as genai
except ImportError:
    raise ImportError("Run: pip install google-generativeai")

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
except ImportError:
    raise ImportError("Run: pip install tenacity")

RAW_DIR = Path(__file__).parent.parent / "raw"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

BATCH_SIZE = 30  # Synsets per API call
RATE_LIMIT_DELAY = 1.0  # Seconds between calls

# Model selection - start with cheapest, escalate if quality poor
# Options: "gemini-2.5-flash-lite", "gemini-2.5-flash"
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

EXTRACTION_PROMPT = """System Role: You are an expert Linguistic Data Scientist specializing in semantic analysis and figurative language.

Task Guidelines: Analyze the provided word_sense | definition pairs and generate a JSONL response for each.

1. Properties (CRITICAL: Minimum 5 required): Extract 5-10 abstract, structural, or functional properties.

Constraint: Decompose simple objects. Describe what it does, how it moves, or what it is made of.

2. Metonyms (The "Creative Writer" Check): List 2-3 words used metonymically or symbolically to stand in for this concept. Strictly NO synonyms.

You MUST check for these specific Metonymy Types:

Place for Industry: (e.g., "Wall Street" -> Finance, "Hollywood" -> Film).

Body Part for Function: (e.g., "Stomach" -> Appetite, "Brain" -> Intellect).

Object/Clothing for Role: (e.g., "Crown" -> Monarchy, "Badge" -> Police, "Suits" -> Executives).

Tool for Activity: (e.g., "Pen" -> Writing, "Sword" -> Warfare).

Effect for Cause: (e.g., "Tears" -> Grief).

If the word has no common creative metonym (like "sand" or "proton"), return [].

3. Connotation: Assess the emotional weight: "positive", "neutral", or "negative". Lean away from "neutral" if any bias exists.

4. Register: "formal", "neutral", "informal", or "slang".

5. Usage Example: A natural sentence demonstrating the sense.

Few-Shot Examples (Pattern Matching):

Input: judiciary.n.01 | the system of law courts that administer justice Output: {"id": "judiciary.n.01", "properties": ["interprets_law", "resolves_disputes", "hierarchical_structure", "impartial", "government_branch", "checks_power"], "metonyms": ["the_bench", "the_gavel"], "connotation": "neutral", "register": "formal", "usage_example": "The judiciary must remain independent of political pressure."}

Input: business.n.01 | the activity of providing goods and services Output: {"id": "business.n.01", "properties": ["generates_profit", "requires_capital", "involves_risk", "commercial_exchange", "competitive"], "metonyms": ["suits", "corporate_ladder"], "connotation": "neutral", "register": "neutral", "usage_example": "They are in the business of selling used cars."}

Input: intellect.n.01 | the capacity for rational thought or inference Output: {"id": "intellect.n.01", "properties": ["processes_information", "solves_problems", "abstract_reasoning", "distinguishes_truth", "can_be_developed"], "metonyms": ["brain", "grey_matter"], "connotation": "positive", "register": "neutral", "usage_example": "Her keen intellect allowed her to solve the puzzle quickly."}

Input Batch: {batch}

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

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    reraise=True
)
def extract_batch(model, synsets: List[Dict]) -> List[Dict]:
    """Extract enrichment for a batch of synsets with retry logic."""
    batch_input = "\n".join(
        f"{s['id']} | {s['definition']}" for s in synsets
    )

    prompt = EXTRACTION_PROMPT.replace("{batch}", batch_input)

    response = model.generate_content(prompt)

    # Parse JSONL output
    results = []
    for line_num, line in enumerate(response.text.strip().split('\n'), 1):
        line = line.strip()
        if line.startswith('{'):
            try:
                obj = json.loads(line)
                if 'id' in obj and 'properties' in obj:
                    results.append(obj)
            except json.JSONDecodeError as e:
                logging.warning(f"Failed to parse JSON on line {line_num}: {line[:50]}... Error: {e}")
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

        except (ConnectionError, TimeoutError, ValueError, KeyError) as e:
            logging.error(f"Error on batch {i}: {type(e).__name__}: {e}")
            error_count += len(batch)
            conn.rollback()
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
