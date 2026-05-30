"""Pydantic models matching the JSONL schemas defined in
docs/superpowers/specs/2026-05-30-metaphor-grading-tool-design.md

Sections: "Data shapes -> Chain record" / "Judgement record" / "Design-note block".
"""
from __future__ import annotations
import datetime as dt
import hashlib
import unicodedata
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

ChainSchemaVersion = Literal["chain.v1"]
JudgementSchemaVersion = Literal["judgement.v1"]
Label = Literal["live", "dead", "bad_path", "irrelevant"]
Confidence = Literal["high", "med", "low"]


def normalise_phrase(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip().lower()


def compute_chain_signature(proposer: str, phrases: list[str]) -> str:
    """sha256(":".join([proposer] + [normalise(phrase) for phrase in phrases]))
    Stable across snap drift / head re-extraction (phrase-based, not synset-based)."""
    payload = ":".join([proposer] + [normalise_phrase(p) for p in phrases])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ChainStep(BaseModel):
    phrase: str = Field(min_length=1)
    head: str = Field(min_length=1)
    synset_id: Optional[str] = None


class ChainRecord(BaseModel):
    schema_version: ChainSchemaVersion
    topic: str
    topic_synset_id: str
    vehicle: str
    vehicle_synset_id: str
    proposer: str
    round: int = Field(ge=1)
    chain: list[ChainStep] = Field(min_length=2)
    chain_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: str  # ISO-8601 UTC

    @model_validator(mode="after")
    def _endpoint_canonicalisation(self) -> "ChainRecord":
        if (self.chain[0].phrase != self.topic
                or self.chain[0].head != self.topic
                or self.chain[0].synset_id != self.topic_synset_id):
            raise ValueError(
                "endpoint canonicalisation: chain[0] must equal topic/topic_synset_id"
            )
        if (self.chain[-1].phrase != self.vehicle
                or self.chain[-1].head != self.vehicle
                or self.chain[-1].synset_id != self.vehicle_synset_id):
            raise ValueError(
                "endpoint canonicalisation: chain[-1] must equal vehicle/vehicle_synset_id"
            )
        return self


class JudgementRecord(BaseModel):
    schema_version: JudgementSchemaVersion
    # Server injects ts when the client omits it — clients should not set this field.
    ts: str = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    judged_by: str
    round: int = Field(ge=1)
    topic: str
    topic_synset_id: str
    vehicle: str
    vehicle_synset_id: str
    proposer: str
    chain_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    label: Label
    confidence: Confidence = "high"
    notes: str = Field(default="", max_length=1000)
    supersedes_ts: Optional[str] = None


class DesignNotePost(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
