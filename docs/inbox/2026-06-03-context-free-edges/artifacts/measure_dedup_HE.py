#!/usr/bin/env python3
"""H-E caching/dedup amortisation harness — measures recurrence on EXISTING dumps only.

No API calls. Quantifies whether a context-free edge cache changes the 100k cost
order-of-magnitude or is a constant-factor win. Reproduces the numbers in the H-E finding.

Run:
    python3 docs/inbox/2026-06-03-context-free-edges/artifacts/measure_dedup_HE.py
Inputs (existing, no generation):
    data-pipeline/grading/sonnet_chains_provisional_r1.jsonl     (200 chains: bridges+hops)
    data-pipeline/output/metaphor_spike_apt_phase2_*.jsonl        (200 topics x ~5.5 apt vehicles)
    data-pipeline/output/metaphor_spike_inapt_phase2_*.jsonl      (inapt vehicles, for cache-validity)
    data-pipeline/output/lexicon_v2.db                            (cluster profiles)
"""
import json, collections, math, glob, sqlite3, random, statistics, sys

ROOT = "."
CHAINS = f"{ROOT}/data-pipeline/grading/sonnet_chains_provisional_r1.jsonl"
APT = sorted(glob.glob(f"{ROOT}/data-pipeline/output/metaphor_spike_apt_phase2_*.jsonl"))[-1]
INAPT = sorted(glob.glob(f"{ROOT}/data-pipeline/output/metaphor_spike_inapt_phase2_*.jsonl"))[-1]
DB = f"{ROOT}/data-pipeline/output/lexicon_v2.db"
VOCAB = 107519  # synsets total = vehicle-vocabulary ceiling


def load(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def chain_recurrence():
    """Node vs edge reuse in the 200 generated chains (the cache-content inventory)."""
    chains = load(CHAINS)
    veh = collections.Counter(c["vehicle_synset_id"] for c in chains)
    inter = collections.Counter()
    hop_edges = collections.Counter()
    for c in chains:
        steps = c["chain"]
        for i in range(len(steps) - 1):
            hop_edges[(steps[i]["synset_id"], steps[i + 1]["synset_id"])] += 1
        for s in steps[1:-1]:
            inter[s["synset_id"]] += 1
    bridges = set((c["topic_synset_id"], c["vehicle_synset_id"]) for c in chains)
    total_edges = len(chains) + sum(hop_edges.values())
    distinct_edges = len(bridges) + len(hop_edges)
    return {
        "chains": len(chains),
        "vehicle_node_reuse": len(chains) / len(veh),
        "intermediate_node_reuse": sum(inter.values()) / max(1, len(inter)),
        "hop_edge_reuse": sum(hop_edges.values()) / len(hop_edges),
        "overall_edge_dedup": total_edges / distinct_edges,
    }


def vehicle_amortisation():
    """Cross-topic vehicle recurrence + Heaps' law growth (200-topic apt cohort)."""
    apt = load(APT)
    topic_veh = {r["topic"]: [m["vehicle"] for m in r["metaphors"]] for r in apt}
    topics = list(topic_veh)

    def rarefaction(order):
        seen, total, xs = set(), 0, []
        for t in order:
            for v in topic_veh[t]:
                total += 1; seen.add(v)
            xs.append((total, len(seen)))
        return xs

    # Heaps' law: distinct ~ K * total^beta  (beta<1 => sublinear => caching helps more at scale)
    curves = collections.defaultdict(list)
    for _ in range(200):
        o = topics[:]; random.shuffle(o)
        for total, distinct in rarefaction(o):
            curves[total].append(distinct)
    pts = [(x, statistics.mean(curves[x])) for x in sorted(curves) if x > 0]
    lx = [math.log(x) for x, _ in pts]; ly = [math.log(y) for _, y in pts]
    n = len(lx); sx = sum(lx); sy = sum(ly)
    sxx = sum(v * v for v in lx); sxy = sum(a * b for a, b in zip(lx, ly))
    beta = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    K = math.exp((sy - beta * sx) / n)

    def amort_at(N_topics):
        slots = N_topics * 10
        distinct = min(K * slots ** beta, VOCAB)  # clamp to vocabulary
        return slots, distinct, slots / distinct

    return {"K": K, "beta": beta, "projection": {N: amort_at(N) for N in (200, 1000, 10000, 100000)}}


def cache_validity():
    """Does (vehicle, shared-cluster) determine aptness? If a vehicle flips apt<->inapt across
    topics, a context-free (V,C) cache cannot decide topic->V aptness."""
    apt, inapt = load(APT), load(INAPT)
    apt_veh = collections.defaultdict(set); inapt_veh = collections.defaultdict(set)
    apt_pairs = set(); inapt_pairs = set()
    for r in apt:
        for m in r["metaphors"]:
            apt_veh[m["vehicle"]].add(r["topic"]); apt_pairs.add((r["topic"], m["vehicle"]))
    for r in inapt:
        for m in r.get("inapt_metaphors", []):
            inapt_veh[m["vehicle"]].add(r["topic"]); inapt_pairs.add((r["topic"], m["vehicle"]))
    multi = {v for v, ts in apt_veh.items() if len(ts) >= 2}
    contested = multi & set(inapt_veh)
    return {
        "multi_topic_vehicles": len(multi),
        "contested_flip_fraction": len(contested) / len(multi),
        "direct_contradictions": len(apt_pairs & inapt_pairs),
    }


def profile_collisions():
    """Exact cluster-profile collisions = ceiling on caching the topic-keyed Haiku propose step."""
    con = sqlite3.connect(DB)
    prof = collections.defaultdict(set)
    for s, c in con.execute("SELECT synset_id, cluster_id FROM synset_properties_curated"):
        prof[s].add(c)
    con.close()
    sigs = collections.Counter(frozenset(v) for v in prof.values())
    n = len(prof); distinct = len(sigs)
    return {"synsets": n, "distinct_profiles": distinct,
            "exact_cache_hit_ceiling": (n - distinct) / n}


if __name__ == "__main__":
    out = {
        "chain_recurrence": chain_recurrence(),
        "vehicle_amortisation": vehicle_amortisation(),
        "cache_validity": cache_validity(),
        "profile_collisions": profile_collisions(),
    }
    json.dump(out, sys.stdout, indent=2, default=str)
    print()
