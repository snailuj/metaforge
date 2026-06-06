"""Signal-prioritised grading walk — acquisition ordering for next/prev grading.

Turns triaged paths into a flat, ordered list so the grader spends each grade on
the highest-signal next path. Two ideas (agreed design):

- **Per-topic dwell, not per-path shuffle.** The walk orders TOPICS; for each you
  linger over a small DWELL SET, then advance. A topic gets "fleshed out" (n>1
  tells us far more than n=1) before you move on, and you keep one topic's context.

- **The dwell set maximises signal per grade.** It captures live/dead CONTRAST
  (clearest-live + clearest-dead) AND exercises the rest of the grading panel by
  pulling in a structurally-weak path (where bad_head / leap / weak-linkage live),
  deduped by vehicle (two chains of the same topic→vehicle pairing are redundant
  for the linkage signal), clamped to n_max. `n` therefore emerges from what the
  topic offers — small for an obvious topic, larger for a rich/ambiguous one.

Pure functions over plain dicts so they're trivially testable; the route layer
joins triage scores + structural flags + verdicts and feeds them in.

A path dict carries: chain_signature, topic, vehicle, liveness (0-10 int),
bad_head/leap/weak_linkage (bool structural flags).
"""
from __future__ import annotations

DEFAULT_N_MAX = 5
DEFAULT_MIDPOINT = 5.0


def _is_weak(p: dict) -> bool:
    return bool(p.get("bad_head") or p.get("leap") or p.get("weak_linkage"))


def assemble_paths(chains: list[dict], *, liveness_by_sig: dict[str, int],
                   structural_by_sig: dict[str, dict],
                   default_liveness: int = int(DEFAULT_MIDPOINT)) -> list[dict]:
    """Join chain records with triage liveness + structural flags into the minimal
    path dicts build_walk consumes (keyed by chain_signature).

    Untriaged chains keep `default_liveness` (the midpoint) so they still appear in
    the walk, mid-ranked, rather than vanishing; missing structural data = unflagged.
    """
    out: list[dict] = []
    for c in chains:
        sig = c["chain_signature"]
        st = structural_by_sig.get(sig) or {}
        out.append({
            "chain_signature": sig,
            "topic": c["topic"],
            "vehicle": c["vehicle"],
            "liveness": liveness_by_sig.get(sig, default_liveness),
            "bad_head": bool(st.get("bad_head")),
            "leap": bool(st.get("leap")),
            "weak_linkage": bool(st.get("weak_linkage")),
        })
    return out


def dwell_set(paths: list[dict], *, n_max: int = DEFAULT_N_MAX,
              midpoint: float = DEFAULT_MIDPOINT) -> list[dict]:
    """Select the contrastive, panel-exercising subset to grade for ONE topic.

    Priority of inclusion (each subject to vehicle-dedup): clearest-live (max
    liveness) → clearest-dead (min) → one structurally-weak path → one boundary
    (closest to midpoint) → then fill toward n_max by most-contrastive remaining.
    Returns picks ordered for grading: live, dead, weak, boundary, extras.
    """
    if not paths:
        return []
    by_live = sorted(paths, key=lambda p: p["liveness"])
    picks: list[dict] = []
    seen_sig: set[str] = set()
    seen_veh: set[str] = set()

    def add(p):
        if p is None or len(picks) >= n_max:
            return
        if p["chain_signature"] in seen_sig or p["vehicle"] in seen_veh:
            return
        picks.append(p)
        seen_sig.add(p["chain_signature"])
        seen_veh.add(p["vehicle"])

    add(by_live[-1])                                              # clearest-live
    add(by_live[0])                                              # clearest-dead
    add(next((p for p in by_live if _is_weak(p)), None))        # exercise the panel
    add(min(paths, key=lambda p: abs(p["liveness"] - midpoint)))  # boundary
    for p in sorted(paths, key=lambda p: -abs(p["liveness"] - midpoint)):  # fill
        add(p)
    return picks


def _spread(topic_paths: list[dict]) -> int:
    lv = [p["liveness"] for p in topic_paths]
    return max(lv) - min(lv) if lv else 0


def build_walk(paths: list[dict], *, graded_sigs: set[str] | None = None,
               n_max: int = DEFAULT_N_MAX, midpoint: float = DEFAULT_MIDPOINT) -> list[dict]:
    """Flatten triaged paths into the signal-prioritised walk order.

    Skips already-graded paths, groups the rest by topic, builds each topic's
    dwell set, orders topics by contrast potential (wide liveness spread =
    cheap, high-signal contrast; ties broken toward topics that carry a
    structural flag so the panel gets exercised early), then emits each topic's
    dwell set contiguously (you dwell, then advance). Each entry is annotated
    with its position in the topic's dwell (dwell_index / dwell_n).
    """
    graded_sigs = graded_sigs or set()
    pending = [p for p in paths if p["chain_signature"] not in graded_sigs]

    by_topic: dict[str, list[dict]] = {}
    for p in pending:
        by_topic.setdefault(p["topic"], []).append(p)

    def topic_key(item):
        topic, tpaths = item
        has_flag = any(_is_weak(p) for p in tpaths)
        # wide spread first; among equal spreads, flagged topics first; then name
        return (-_spread(tpaths), 0 if has_flag else 1, topic)

    walk_out: list[dict] = []
    for topic, tpaths in sorted(by_topic.items(), key=topic_key):
        dwell = dwell_set(tpaths, n_max=n_max, midpoint=midpoint)
        for i, p in enumerate(dwell):
            walk_out.append({**p, "dwell_index": i, "dwell_n": len(dwell)})
    return walk_out
