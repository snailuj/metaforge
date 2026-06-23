#!/usr/bin/env python3
"""H-F — relational shortcuts (symmetry / transitivity) validity probe.

Tests whether metaphor edges can be multiplied "for free" via
  (1) SYMMETRY    t->v apt  =>  v->t apt
  (2) TRANSITIVITY a->b apt and b->c apt  =>  a->c apt

Two parts:
  PART A — OBSERVATIONAL (NO API). Runs on existing data:
           - apt cohort:  metaphor_spike_apt_phase2_*.jsonl   (1112 apt pairs)
           - inapt cohort: metaphor_spike_inapt_phase2_*.jsonl  (600 inapt pairs)
           - chains:       data-pipeline/grading/sonnet_chains_provisional_r1.jsonl
           Measures reverse-pair confirmation, transitive-closure precision,
           dual-labelling rate, and the nominal "free" edge multiplier.

  PART B — CAUSAL REVERSAL PROBE (COSTS API; orchestrator runs).
           The observational data can only show the generator *never produced*
           reverse/transitive edges; it cannot show they were *rejected*.
           Part B closes that gap: take N=20 high-confidence apt pairs (t->v),
           ask the LLM-judge to grade the REVERSED pair (v->t) context-free.
           If symmetry held, reversed pairs would grade `live` at ~the same rate.
           Prediction (H-F): reversed apt rate << forward apt rate.
           Cost: 20 judge calls (Haiku floor ~$0.07 cold, amortised in batch)
                 ~= one 5-min cache window ~= <$1.50. <=20-synset cohort: COMPLIANT.

No API calls are made by Part A. Part B only PRINTS the prompts + the cohort;
it does NOT shell out. The orchestrator wires it to lib/claude_client.py.
"""
import json, glob, sys
from collections import defaultdict, Counter

APT = sorted(glob.glob('data-pipeline/output/metaphor_spike_apt_phase2_*.jsonl'))[-1]
INAPT = sorted(glob.glob('data-pipeline/output/metaphor_spike_inapt_phase2_*.jsonl'))[-1]
CHAINS = 'data-pipeline/grading/sonnet_chains_provisional_r1.jsonl'


def load():
    apt = [json.loads(l) for l in open(APT)]
    inapt = [json.loads(l) for l in open(INAPT)]
    chains = [json.loads(l) for l in open(CHAINS)]
    apt_pairs = set((r['topic'], m['vehicle']) for r in apt for m in r.get('metaphors', []))
    inapt_idx = {(r['topic'], m['vehicle']): m
                 for r in inapt for m in r.get('inapt_metaphors', [])}
    inapt_pairs = set(inapt_idx)
    return apt, inapt, chains, apt_pairs, inapt_pairs, inapt_idx


def part_a(apt, inapt, chains, apt_pairs, inapt_pairs, inapt_idx):
    print('=' * 64)
    print('PART A — OBSERVATIONAL (no API)')
    print('=' * 64)

    # --- A1 SYMMETRY ---
    rev_apt = sum(1 for (t, v) in apt_pairs if (v, t) in apt_pairs)
    rev_inapt = sum(1 for (t, v) in apt_pairs if (v, t) in inapt_pairs)
    print(f'\n[A1 symmetry] apt pairs whose reverse is ALSO apt:   '
          f'{rev_apt}/{len(apt_pairs)} ({100*rev_apt/len(apt_pairs):.2f}%)')
    print(f'[A1 symmetry] apt pairs whose reverse is INAPT:        {rev_inapt}')
    # endpoint symmetry from generated chains
    eps = set((c['topic'], c['vehicle']) for c in chains)
    rev_eps = sum(1 for (t, v) in eps if (v, t) in eps)
    print(f'[A1 symmetry] generated topic->vehicle endpoints whose reverse '
          f'was also generated: {rev_eps}/{len(eps)}')
    print('  CAVEAT: 0% reverse is consistent with asymmetry but is NOT proof — the '
          'generator was never asked to reverse. Part B is the causal test.')

    # --- A2 DUAL-LABELLING (single direct edge already unstable) ---
    both = sorted(apt_pairs & inapt_pairs)
    print(f'\n[A2 stability] pairs labelled BOTH apt AND inapt: {len(both)} '
          f'({100*len(both)/len(apt_pairs):.1f}% of apt). Genuine context-dependence '
          '(different sense/framing flips the verdict). If a DIRECT edge is this '
          'unstable, a DERIVED (reversed/transitive) edge cannot be trusted.')

    # --- A3 TRANSITIVITY via the bridge set (topics that are also vehicles) ---
    apt_topics = set(r['topic'] for r in apt)
    apt_vehicles = set(v for (_, v) in apt_pairs)
    to_X, from_X = defaultdict(set), defaultdict(set)
    for (t, v) in apt_pairs:
        to_X[v].add(t); from_X[t].add(v)
    bridge = sorted(apt_topics & apt_vehicles)
    trans = [(T, X, Y) for X in bridge for T in to_X[X] for Y in from_X[X] if T != Y]
    lab = [c for c in trans if (c[0], c[2]) in apt_pairs or (c[0], c[2]) in inapt_pairs]
    tp = [c for c in lab if (c[0], c[2]) in apt_pairs]
    base = len(apt_pairs) / (len(apt_pairs) + len(inapt_pairs))
    print(f'\n[A3 transitivity] bridge vehicles (topic AND vehicle): {len(bridge)}')
    print(f'[A3 transitivity] derivable T->X->Y endpoints: {len(trans)}')
    print(f'[A3 transitivity]   with ANY independent label: {len(lab)} '
          f'({100*len(lab)/len(trans):.1f}%) -> 93%+ unverifiable')
    print(f'[A3 transitivity]   precision on labelled slice: {len(tp)}/{len(lab)} '
          f'(cohort apt base-rate = {100*base:.0f}%; the "precision" is CIRCULAR — '
          'the label exists only because T independently generated Y).')

    # --- A4 NOMINAL FREE MULTIPLIER + garbage sample ---
    G = defaultdict(set)
    for (t, v) in apt_pairs:
        G[t].add(v)
    direct = sum(len(s) for s in G.values())
    closure = set()
    for a in G:
        for b in G[a]:
            for c in G.get(b, ()):
                if c != a:
                    closure.add((a, c))
    new_t = closure - apt_pairs
    mult = 2 * (direct + len(new_t)) / direct  # 2x symmetry * transitive growth
    print(f'\n[A4 temptation] direct apt edges {direct}; NEW transitive edges '
          f'{len(new_t)}; naive free multiplier ~{mult:.1f}x (2x sym * '
          f'{(direct+len(new_t))/direct:.2f}x trans). Falls right in the '
          '"looks like it solves the 4x budget" zone — that is the trap.')
    print('[A4 temptation] sample NEW transitive edges (inspect for cross-domain garbage):')
    for e in list(new_t)[:12]:
        print('    ', e[0], '->', e[1])


def part_b_cohort(apt, apt_pairs):
    """Select N=20 high-confidence apt pairs for the causal reversal probe.
    Prints the cohort + the judge prompts. NO API CALL HERE."""
    print('\n' + '=' * 64)
    print('PART B — CAUSAL REVERSAL PROBE (orchestrator executes; <=20 pairs)')
    print('=' * 64)
    # rank apt pairs by stated confidence; cross-domain (topic != vehicle lemma)
    ranked = []
    for r in apt:
        for m in r.get('metaphors', []):
            ranked.append((m.get('confidence', 0), r['topic'], m['vehicle']))
    ranked.sort(reverse=True)
    cohort, seen = [], set()
    for conf, t, v in ranked:
        if v in seen or t in seen:
            continue  # keep the 20 synsets distinct (<=20-synset rule)
        cohort.append((t, v, conf)); seen.add(t); seen.add(v)
        if len(cohort) >= 20:
            break
    print(f'\nReversal cohort (forward apt -> grade the REVERSE v->t):')
    for t, v, conf in cohort:
        print(f'    forward apt: {t:>16} -> {v:<16} (conf {conf})   '
              f'PROBE: grade  {v} -> {t}')
    print('\nJUDGE PROMPT TEMPLATE (one Haiku call per reversed pair, context-free):')
    print('  """Treat this as a standalone metaphor with NO surrounding context.')
    print('     Is "{v} is a {t}" a LIVE cross-domain metaphor (genuine, non-clichéd,')
    print('     crosses semantic domains) or DEAD/INAPT (synonym, same-domain,')
    print('     cliché, or forced)? Answer: live | dead | inapt. One word + 1 clause."""')
    print('\nDECISION RULE:')
    print('  reversed_live_rate = (#reversed graded live) / 20')
    print('  H-F symmetry is VALIDATED only if reversed_live_rate >= 0.7 * forward_rate.')
    print('  Prediction (asymmetry): reversed_live_rate << forward_rate (expect <0.3).')
    print('  If validated -> symmetry gives a free 2x; if refuted -> symmetry is a')
    print('  quality trap, do NOT add reverse edges. Cost: ~20 calls, <$1.50 batched.')
    return cohort


if __name__ == '__main__':
    data = load()
    part_a(*data)
    part_b_cohort(data[0], data[3])
