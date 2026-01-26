#!/usr/bin/env python3
"""
Import frequency data from SUBTLEX-UK into lexicon database.

SUBTLEX-UK format (tab-separated):
- Spelling: the word
- FreqCount: raw frequency count
- LogFreq(Zipf): Zipf frequency score

Rarity tier classification:
- common: Zipf >= 5
- uncommon: 4 <= Zipf < 5
- rare: 3 <= Zipf < 4
- archaic: Zipf < 3
"""

import sqlite3
import csv
from pathlib import Path
from typing import Optional

def get_rarity_tier(zipf: float) -> str:
    """Classify word rarity based on Zipf frequency."""
    if zipf >= 5:
        return 'common'
    elif zipf >= 4:
        return 'uncommon'
    elif zipf >= 3:
        return 'rare'
    else:
        return 'archaic'

def import_frequency_data(db_path: Path, subtlex_path: Path) -> None:
    """Import SUBTLEX-UK frequency data into the lexicon database."""
    
    # Verify input files exist
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    if not subtlex_path.exists():
        raise FileNotFoundError(f"SUBTLEX-UK file not found: {subtlex_path}")
    
    print(f"Opening database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create frequencies table
    print("Creating frequencies table...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS frequencies (
            lemma TEXT PRIMARY KEY,
            frequency INTEGER NOT NULL,
            zipf REAL NOT NULL,
            rarity TEXT NOT NULL CHECK (rarity IN ('common', 'uncommon', 'rare', 'archaic'))
        )
    ''')

    # Create index for faster lookups
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_frequencies_lemma ON frequencies(lemma)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_frequencies_zipf ON frequencies(zipf)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_frequencies_rarity ON frequencies(rarity)')
    
    # Read and import SUBTLEX-UK data
    print(f"Reading SUBTLEX-UK data from: {subtlex_path}")
    
    imported_count = 0
    skipped_count = 0
    
    with open(subtlex_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')

        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is line 1)
            try:
                spelling = row['Spelling'].strip().lower()
                freq_count = int(row['FreqCount'].strip())
                # Try LogFreq(Zipf) column, fall back to alternative column names if present
                zipf_raw = row.get('LogFreq(Zipf)') or row.get('SUBTLWF') or row.get('Lg10WF')
                if not zipf_raw:
                    print(f"Skipping row {row_num}: no Zipf frequency column found")
                    skipped_count += 1
                    continue
                zipf = float(zipf_raw.strip())
                
                # Skip empty or invalid entries
                if not spelling or freq_count < 0 or zipf < 0:
                    skipped_count += 1
                    continue
                
                rarity = get_rarity_tier(zipf)

                cursor.execute('''
                    INSERT OR REPLACE INTO frequencies (lemma, frequency, zipf, rarity)
                    VALUES (?, ?, ?, ?)
                ''', (spelling, freq_count, zipf, rarity))
                
                imported_count += 1
                
                if imported_count % 10000 == 0:
                    print(f"  Imported {imported_count:,} words...")
                    
            except (ValueError, IndexError) as e:
                print(f"Skipping row {row_num} due to error: {e}")
                skipped_count += 1
                continue
    
    # Commit transaction
    conn.commit()
    
    # Print statistics
    cursor.execute("SELECT COUNT(*) FROM frequencies")
    total_count = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT rarity, COUNT(*)
        FROM frequencies
        GROUP BY rarity
        ORDER BY COUNT(*) DESC
    ''')
    rarity_stats = cursor.fetchall()

    print(f"\nImport complete!")
    print(f"  Total words imported: {total_count:,}")
    print(f"  Words processed this run: {imported_count:,}")
    print(f"  Words skipped: {skipped_count:,}")
    print(f"\nRarity distribution:")
    for tier, count in rarity_stats:
        print(f"  {tier}: {count:,}")

    # Sample some words to verify
    cursor.execute('''
        SELECT lemma, zipf, rarity
        FROM frequencies
        ORDER BY zipf DESC
        LIMIT 5
    ''')
    top_words = cursor.fetchall()
    print(f"\nTop 5 most frequent words:")
    for word, zipf, tier in top_words:
        print(f"  {word}: Zipf {zipf:.2f} ({tier})")
    
    conn.close()

def main():
    """Main execution function."""
    # Set up paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    db_path = project_root / "output" / "lexicon.db"
    subtlex_path = project_root / "raw" / "SUBTLEX-UK.txt"
    
    try:
        import_frequency_data(db_path, subtlex_path)
        print(f"\nFrequency data successfully imported to {db_path}")

    except Exception as e:
        print(f"\nError importing frequency data: {e}")
        raise

if __name__ == "__main__":
    main()
