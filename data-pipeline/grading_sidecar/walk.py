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
# Liveness bands that predict which metaphor verdict a grade will land on. Mirrors
# the Forge Reader rubric (>=7 LIVE/HIT, <=4 DEAD/INERT); the 5-6 mid-band is
# "serviceable" and predicts neither, so a mid-only topic carries no metaphor signal.
LIVE_THRESHOLD = 7
DEAD_THRESHOLD = 4


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

    def add(p) -> bool:
        if p is None or len(picks) >= n_max:
            return False
        if p["chain_signature"] in seen_sig or p["vehicle"] in seen_veh:
            return False
        picks.append(p)
        seen_sig.add(p["chain_signature"])
        seen_veh.add(p["vehicle"])
        return True

    def add_first(candidates) -> None:
        # Take the first candidate that actually lands — a single colliding head
        # (e.g. a weak path sharing the clearest-live vehicle) must not forfeit the
        # whole slot when a distinct-vehicle candidate is still available.
        for c in candidates:
            if add(c):
                return

    add(by_live[-1])                                                       # clearest-live
    add(by_live[0])                                                        # clearest-dead
    add_first(p for p in by_live if _is_weak(p))                           # exercise the panel
    add_first(sorted(paths, key=lambda p: abs(p["liveness"] - midpoint)))  # boundary
    for p in sorted(paths, key=lambda p: -abs(p["liveness"] - midpoint)):  # fill
        add(p)
    return picks


def topic_axis_signals(paths: list[dict]) -> set[str]:
    """The grading-panel axes a topic's paths are PREDICTED to exercise.

    Derived from triage only (we can't know the grade in advance, but the triage
    signal is a good prior): high liveness predicts a `metaphor:live` grade, low
    predicts `metaphor:dead`; each structural flag predicts the control where that
    fault lands (bad_head/leap → tags; weak_linkage → a bad linkage verdict). Used
    to steer the walk toward topics that can fill under-collected label axes.
    """
    sigs: set[str] = set()
    for p in paths:
        lv = p["liveness"]
        if lv >= LIVE_THRESHOLD:
            sigs.add("metaphor:live")
        if lv <= DEAD_THRESHOLD:
            sigs.add("metaphor:dead")
        if p.get("bad_head"):
            sigs.add("tag:bad_head")
        if p.get("leap"):
            sigs.add("tag:leap")
        if p.get("weak_linkage"):
            sigs.add("linkage:bad")
    return sigs


def collected_labels_from_verdicts(verdicts: list[dict]) -> dict[str, int]:
    """Count how often each steerable label-axis has already been graded.

    Verdicts are normalise_judgement-shaped dicts (linkage / metaphor / tags),
    so v1 and v2 records count uniformly. None-valued axes (e.g. v1 bad_path has
    no metaphor; irrelevant has no linkage) are skipped so they never appear as a
    bogus ``axis:None`` key. The result feeds the coverage deficit in build_walk.
    """
    counts: dict[str, int] = {}

    def bump(label: str) -> None:
        counts[label] = counts.get(label, 0) + 1

    for v in verdicts:
        metaphor = v.get("metaphor")
        if metaphor:
            bump(f"metaphor:{metaphor}")
        linkage = v.get("linkage")
        if linkage:
            bump(f"linkage:{linkage}")
        for tag in (v.get("tags") or []):
            if tag:
                bump(f"tag:{tag}")
    return counts


def _deficit(label: str, collected_labels: dict[str, int]) -> float:
    """How starved an axis is: 1.0 when never collected, decaying as it fills."""
    return 1.0 / (1.0 + collected_labels.get(label, 0))


def _steer(topic_paths: list[dict], collected_labels: dict[str, int]) -> float:
    """A topic's steering boost = the biggest coverage gap it can fill.

    Max (not sum) so the score focuses on the single most under-collected axis the
    topic reaches, rather than rewarding topics that touch many already-covered
    axes. With no labels yet, every deficit is 1.0 so this is a near-uniform offset
    and contrast spread decides — steering only differentiates as labels accrue.
    """
    sigs = topic_axis_signals(topic_paths)
    return max((_deficit(s, collected_labels) for s in sigs), default=0.0)


def _spread(topic_paths: list[dict]) -> int:
    lv = [p["liveness"] for p in topic_paths]
    return max(lv) - min(lv) if lv else 0


def build_walk(paths: list[dict], *, graded_sigs: set[str] | None = None,
               collected_labels: dict[str, int] | None = None,
               n_max: int = DEFAULT_N_MAX, midpoint: float = DEFAULT_MIDPOINT) -> list[dict]:
    """Flatten triaged paths into the signal-prioritised walk order.

    Skips already-graded paths, groups the rest by topic, builds each topic's
    dwell set, orders topics by a combined score = contrast potential (wide
    liveness spread = cheap, high-signal contrast) + label-coverage steering
    (boost topics that can fill the most under-collected grading-panel axis),
    then emits each topic's dwell set contiguously (you dwell, then advance).
    Each entry is annotated with its dwell position (dwell_index / dwell_n).

    `collected_labels` is the corpus-wide tally of axes already graded (from
    collected_labels_from_verdicts). Pass None to disable steering (pure spread
    ordering) — the steering term contributes 0 and the order is unchanged.
    """
    graded_sigs = graded_sigs or set()
    pending = [p for p in paths if p["chain_signature"] not in graded_sigs]

    by_topic: dict[str, list[dict]] = {}
    for p in pending:
        by_topic.setdefault(p["topic"], []).append(p)

    def topic_key(item):
        topic, tpaths = item
        # spread normalised to 0..1 so it composes with the 0..1 steering deficit;
        # off (collected_labels is None) the steer term is 0 and this reduces to
        # pure spread ordering. Flagged-first remains a final tiebreak.
        score = _spread(tpaths) / 10.0
        if collected_labels is not None:
            score += _steer(tpaths, collected_labels)
        has_flag = any(_is_weak(p) for p in tpaths)
        return (-score, 0 if has_flag else 1, topic)

    walk_out: list[dict] = []
    for topic, tpaths in sorted(by_topic.items(), key=topic_key):
        dwell = dwell_set(tpaths, n_max=n_max, midpoint=midpoint)
        for i, p in enumerate(dwell):
            walk_out.append({**p, "dwell_index": i, "dwell_n": len(dwell)})
    return walk_out
