"""SemCor-tagcount correction for the snapper's 'too specific' bias.

The gloss-match snapper (metaphor_disambiguate.vetted_topics_from_glossed) picks
the synset whose WordNet definition best matches the model's emitted gloss. When
the model emits a narrow gloss, that lands on a rare/narrow sense even though a
general dominant sense was intended (operator's 'too specific' bad_sense notes:
deficit -> the accounting sense not the general lack; tension -> physics not
emotional strain). `candidate_senses` predates the SemCor import and carries no
frequency signal at all — this module supplies it.

The prior is deliberately CONSERVATIVE: it only overrides the snap when a clearly
more-frequent sense exists (higher SemCor tagcount). All-zero-tagcount ties carry
no signal and are left untouched for the sense-set layer — guessing between two
equally-attested senses would trade one arbitrary pick for another.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def choose_sense(senses: list[dict], snapped_synset_id: str,
                 *, min_tagcount: int = 1) -> dict:
    """Correct a rare snap toward the lemma's dominant (max-tagcount) sense.

    senses: the lemma's candidate senses, each {synset_id, sensenum, tagcount}.
    snapped_synset_id: what the gloss-match snapper chose.

    Returns {synset_id, changed, from}: the corrected synset when a strictly
    more-frequent sense exists (its tagcount >= min_tagcount AND greater than the
    snapped sense's), else the original snap unchanged. Ties at the max, an
    already-dominant snap, all-zero tagcounts, and an unknown snapped synset all
    keep the original — the prior never flips between equally-attested senses nor
    fabricates a pick for a synset it can't see.
    """
    keep = {"synset_id": snapped_synset_id, "changed": False, "from": snapped_synset_id}
    by_id = {s["synset_id"]: s for s in senses}
    snapped = by_id.get(snapped_synset_id)
    if snapped is None:
        return keep
    snapped_tc = snapped.get("tagcount") or 0
    # The dominant sense: the single highest tagcount. A tie for the max carries
    # no directional signal (which of the equals?), so require a UNIQUE maximum.
    best = max(senses, key=lambda s: s.get("tagcount") or 0)
    best_tc = best.get("tagcount") or 0
    n_at_max = sum(1 for s in senses if (s.get("tagcount") or 0) == best_tc)
    if best_tc >= min_tagcount and best_tc > snapped_tc and n_at_max == 1:
        log.info("dominant_sense_prior: %s (tc=%d) -> %s (tc=%d)",
                 snapped_synset_id, snapped_tc, best["synset_id"], best_tc)
        return {"synset_id": best["synset_id"], "changed": True, "from": snapped_synset_id}
    return keep
