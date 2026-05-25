# bradley_terry.py
"""Bradley-Terry ranking for cross-lineage prompt comparison.

Uses a simplified ELO-style update rather than full MLE:
each trial's mean reciprocal rank determines the actual score,
compared against the expected score from the current rating.

This gives a single scalar rating per prompt variant that stabilises
after ~10-15 trials, answering "which lineage should we invest in?"
"""
import numpy as np


DEFAULT_RATING = 1500.0
K_FACTOR = 32.0  # ELO K-factor — controls update magnitude


class BradleyTerryRanker:
    """Track and update prompt variant ratings across trials.

    Each trial's per-pair results update the prompt's rating using
    ELO-style updates where the "opponent" is a virtual baseline
    prompt at the default rating.
    """

    def __init__(self, k_factor: float = K_FACTOR):
        self.ratings: dict[str, float] = {}
        self.trial_counts: dict[str, int] = {}
        self.k_factor = k_factor

    def record_trial(
        self,
        prompt_id: str,
        per_pair: list[dict],
    ) -> float:
        """Record a trial's results and update the prompt's rating.

        Args:
            prompt_id: Unique identifier for the prompt variant.
            per_pair: List of dicts with 'reciprocal_rank' field.

        Returns:
            Updated rating for this prompt.
        """
        if prompt_id not in self.ratings:
            self.ratings[prompt_id] = DEFAULT_RATING
            self.trial_counts[prompt_id] = 0

        rating = self.ratings[prompt_id]
        self.trial_counts[prompt_id] += 1

        # Compute actual score: mean reciprocal rank across pairs
        rrs = [p.get("reciprocal_rank", 0.0) for p in per_pair]
        actual_score = float(np.mean(rrs)) if rrs else 0.0

        # Expected score from current rating vs baseline
        expected = 1.0 / (1.0 + 10.0 ** ((DEFAULT_RATING - rating) / 400.0))

        # Update
        rating += self.k_factor * (actual_score - expected)
        self.ratings[prompt_id] = rating

        return rating

    def get_rating(self, prompt_id: str) -> float:
        """Get the current rating for a prompt (default if unknown)."""
        return self.ratings.get(prompt_id, DEFAULT_RATING)

    def to_dict(self) -> dict:
        """Serialise ranker state."""
        return {
            "ratings": dict(self.ratings),
            "trial_counts": dict(self.trial_counts),
            "k_factor": self.k_factor,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BradleyTerryRanker":
        """Restore ranker from serialised state."""
        ranker = cls(k_factor=data.get("k_factor", K_FACTOR))
        ranker.ratings = dict(data.get("ratings", {}))
        ranker.trial_counts = dict(data.get("trial_counts", {}))
        return ranker
