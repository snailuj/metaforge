"""Compare A/B enrichment variants side-by-side.

Analyses:
- Property count distributions
- Unique vs shared properties
- Sensory vs structural balance (heuristic classification)
- Property diversity (unique props per synset)
- Top properties by frequency
- Same-synset comparison examples

Usage:
    python compare_ab.py
"""
import json
from pathlib import Path
from collections import Counter

from utils import OUTPUT_DIR


# Heuristic word lists for classifying properties as sensory vs structural.
# Not exhaustive — just enough for a rough split analysis.
SENSORY_MARKERS = {
    'warm', 'hot', 'cold', 'cool', 'soft', 'hard', 'rough', 'smooth',
    'bright', 'dark', 'loud', 'quiet', 'sweet', 'bitter', 'sour', 'salty',
    'fragrant', 'aromatic', 'pungent', 'stinky', 'musty', 'earthy',
    'heavy', 'light', 'wet', 'dry', 'sharp', 'dull', 'shiny', 'matte',
    'luminous', 'glowing', 'flickering', 'opaque', 'translucent',
    'crunchy', 'crispy', 'slimy', 'sticky', 'fuzzy', 'velvety',
    'colourful', 'colorful', 'vibrant', 'muted', 'pale', 'vivid',
    'noisy', 'silent', 'hushed', 'booming', 'tinkling', 'resonant',
    'breathy', 'whispery', 'thunderous', 'melodic', 'shrill',
    'waxy', 'oily', 'gritty', 'powdery', 'silky', 'coarse', 'tender',
    'burning', 'freezing', 'tepid', 'scorching', 'icy', 'chilly',
    'fragile', 'delicate', 'sturdy', 'rigid', 'pliable', 'elastic',
    'dense', 'airy', 'thick', 'thin', 'bulky', 'compact', 'massive',
    'radiant', 'dim', 'sparkling', 'gleaming', 'shadowy',
}

STRUCTURAL_MARKERS = {
    'sequential', 'cascading', 'cyclical', 'recursive', 'iterative',
    'dependent', 'independent', 'interconnected', 'networked', 'linked',
    'causal', 'conditional', 'hierarchical', 'parallel', 'branching',
    'cumulative', 'incremental', 'progressive', 'regressive',
    'enabling', 'constraining', 'facilitating', 'blocking', 'mediating',
    'transactional', 'transformative', 'generative', 'destructive',
    'productive', 'consumptive', 'distributive', 'aggregating',
    'systematic', 'methodical', 'procedural', 'strategic', 'tactical',
    'functional', 'operational', 'structural', 'organisational',
    'regulated', 'governed', 'coordinated', 'synchronised',
    'directional', 'oriented', 'targeted', 'focused', 'diffuse',
    'binding', 'releasing', 'absorbing', 'emitting', 'transmitting',
    'propagating', 'amplifying', 'dampening', 'stabilising',
    'catalytic', 'inhibitory', 'accelerating', 'decelerating',
    'voluntary', 'involuntary', 'intentional', 'deliberate', 'reflexive',
    'collaborative', 'competitive', 'cooperative', 'adversarial',
    'reciprocal', 'unilateral', 'mutual', 'one-directional',
}


def classify_property(prop: str) -> str:
    """Classify a property as sensory, structural, or ambiguous."""
    p = prop.lower().strip()
    is_sensory = p in SENSORY_MARKERS
    is_structural = p in STRUCTURAL_MARKERS
    if is_sensory and not is_structural:
        return 'sensory'
    elif is_structural and not is_sensory:
        return 'structural'
    return 'ambiguous'


def load_variant(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def analyse_variant(data: dict) -> dict:
    """Compute detailed metrics for a variant."""
    synsets = data['synsets']
    all_props = []
    prop_counts = []
    classifications = Counter()

    for s in synsets:
        props = s.get('properties', [])
        prop_counts.append(len(props))
        all_props.extend(props)
        for p in props:
            classifications[classify_property(p)] += 1

    prop_freq = Counter(all_props)
    unique = set(all_props)

    return {
        'total_synsets': len(synsets),
        'total_properties': len(all_props),
        'unique_properties': len(unique),
        'avg_per_synset': round(len(all_props) / len(synsets), 2),
        'min_per_synset': min(prop_counts),
        'max_per_synset': max(prop_counts),
        'median_per_synset': sorted(prop_counts)[len(prop_counts) // 2],
        'top_20': prop_freq.most_common(20),
        'classification': dict(classifications),
        'classification_pct': {
            k: round(v / sum(classifications.values()) * 100, 1)
            for k, v in classifications.items()
        },
        'unique_per_synset': round(len(unique) / len(synsets), 2),
        'all_props_set': unique,
        'synset_map': {s['id']: s for s in synsets},
        'prop_freq': prop_freq,
    }


def print_comparison(a: dict, b: dict):
    """Print formatted side-by-side comparison."""

    print("=" * 70)
    print("A/B ENRICHMENT COMPARISON")
    print("  A = Original prompt (5-10 properties)")
    print("  B = Dual-dimension prompt (10-15 properties)")
    print("=" * 70)

    print("\n--- Volume ---")
    print(f"{'Metric':<30} {'A':>10} {'B':>10} {'Δ':>10}")
    print("-" * 60)
    for label, ka, kb in [
        ('Total properties', 'total_properties', 'total_properties'),
        ('Unique properties', 'unique_properties', 'unique_properties'),
        ('Avg per synset', 'avg_per_synset', 'avg_per_synset'),
        ('Min per synset', 'min_per_synset', 'min_per_synset'),
        ('Max per synset', 'max_per_synset', 'max_per_synset'),
        ('Median per synset', 'median_per_synset', 'median_per_synset'),
        ('Unique/synset ratio', 'unique_per_synset', 'unique_per_synset'),
    ]:
        va, vb = a[ka], b[kb]
        if isinstance(va, float):
            delta = f"+{vb - va:.2f}" if vb > va else f"{vb - va:.2f}"
            print(f"{label:<30} {va:>10.2f} {vb:>10.2f} {delta:>10}")
        else:
            delta = f"+{vb - va}" if vb > va else f"{vb - va}"
            print(f"{label:<30} {va:>10} {vb:>10} {delta:>10}")

    print("\n--- Sensory vs Structural Classification ---")
    print(f"{'Category':<20} {'A count':>10} {'A %':>8} {'B count':>10} {'B %':>8}")
    print("-" * 56)
    for cat in ['sensory', 'structural', 'ambiguous']:
        ac = a['classification'].get(cat, 0)
        ap = a['classification_pct'].get(cat, 0)
        bc = b['classification'].get(cat, 0)
        bp = b['classification_pct'].get(cat, 0)
        print(f"{cat:<20} {ac:>10} {ap:>7.1f}% {bc:>10} {bp:>7.1f}%")

    print("\n--- Property Overlap ---")
    shared = a['all_props_set'] & b['all_props_set']
    only_a = a['all_props_set'] - b['all_props_set']
    only_b = b['all_props_set'] - a['all_props_set']
    print(f"  Shared:  {len(shared)} properties appear in both")
    print(f"  Only A:  {len(only_a)} unique to variant A")
    print(f"  Only B:  {len(only_b)} unique to variant B")
    print(f"  Jaccard: {len(shared) / len(a['all_props_set'] | b['all_props_set']):.3f}")

    print("\n--- Top 20 Properties ---")
    print(f"{'Rank':<6} {'Variant A':<25} {'#':>4}   {'Variant B':<25} {'#':>4}")
    print("-" * 70)
    for i in range(20):
        pa, ca = a['top_20'][i] if i < len(a['top_20']) else ('—', '')
        pb, cb = b['top_20'][i] if i < len(b['top_20']) else ('—', '')
        print(f"{i+1:<6} {pa:<25} {ca:>4}   {pb:<25} {cb:>4}")

    # Same-synset comparison for 10 interesting examples
    print("\n--- Same-Synset Examples (10 samples) ---")
    # Pick synsets that are in both and have interesting properties
    shared_ids = set(a['synset_map'].keys()) & set(b['synset_map'].keys())
    sample_ids = sorted(shared_ids)[:10]

    for sid in sample_ids:
        sa = a['synset_map'][sid]
        sb = b['synset_map'][sid]
        print(f"\n  {sa['lemma']} ({sa.get('pos', '?')}): {sa['definition'][:60]}...")
        pa = sa.get('properties', [])
        pb = sb.get('properties', [])
        print(f"    A ({len(pa)}): {', '.join(pa)}")
        print(f"    B ({len(pb)}): {', '.join(pb)}")
        # Show what B added that A didn't have
        new_in_b = set(p.lower() for p in pb) - set(p.lower() for p in pa)
        if new_in_b:
            print(f"    B adds: {', '.join(sorted(new_in_b)[:8])}")


def main():
    a_path = OUTPUT_DIR / "ab_variant_A.json"
    b_path = OUTPUT_DIR / "ab_variant_B.json"

    if not a_path.exists() or not b_path.exists():
        raise FileNotFoundError("Run both variants first (enrich_ab.py)")

    a_data = load_variant(a_path)
    b_data = load_variant(b_path)

    a_metrics = analyse_variant(a_data)
    b_metrics = analyse_variant(b_data)

    print_comparison(a_metrics, b_metrics)


if __name__ == "__main__":
    main()
