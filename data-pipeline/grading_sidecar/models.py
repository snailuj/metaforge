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

ChainSchemaVersion = Literal["chain.v1", "chain.v2"]
JudgementSchemaVersion = Literal["judgement.v1", "judgement.v2"]
# Flat v1 verdict — retained only for reading legacy records via normalise_judgement.
Label = Literal["live", "dead", "bad_path", "irrelevant"]
# v2 two-axis verdict: linkage (are the hops accurate?) + metaphor (is the endpoint apt?).
Linkage = Literal["good", "bad"]
MetaphorVerdict = Literal["live", "dead", "irrelevant"]
# Multi-select reading tiers. `legendary` is derived in a later milestone, not
# human-assigned, so it is not part of the human vocabulary.
Tier = Literal["strong", "ironic", "surprising"]
# Structured issue tags — orthogonal to the verdict axes. `bad_head` flags a
# mis-extracted head concept (a data-prep error), kept distinct from a `bad`
# linkage verdict so head-extraction noise stays out of the metaphor signal.
# `bad_sense` flags a wrong-sense snap (head lemma right, synset wrong) — a
# data-quality flag that marks the row sense-suspect for re-snap; like bad_head it
# is NOT linkage-forcing (the operator grades the intended sense).
Tag = Literal["merge", "padding", "leap", "bad_head", "bad_sense", "other"]
Confidence = Literal["high", "med", "low"]


def normalise_phrase(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip().lower()


def compute_chain_signature(proposer: str, phrases: list[str]) -> str:
    """sha256(":".join([proposer] + [normalise(phrase) for phrase in phrases]))
    Stable across snap drift / head re-extraction (phrase-based, not synset-based)."""
    payload = ":".join([proposer] + [normalise_phrase(p) for p in phrases])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def vec_ref(phrase: str) -> str:
    """Canonical vec-node suffix: the SAME canonicaliser that keys
    chain_signature (one canonicaliser, never two), spaces to underscores."""
    return normalise_phrase(phrase).replace(" ", "_")


class AptSense(BaseModel):
    """A locally co-apt sense at one chain position. `intended` = the
    emit-the-sense gloss-match; `operator` = a grading tick. The snapper never
    writes here — co-aptness it can't validate stays out of the record."""
    synset_id: str = Field(min_length=1)
    source: Literal["intended", "operator"]


class ChainStep(BaseModel):
    phrase: str = Field(min_length=1)
    head: str = Field(min_length=1)
    synset_id: Optional[str] = None
    gloss: Optional[str] = None          # existing emit-the-sense field
    # Phrase-as-Node: explicit node kind. Absent -> derived from synset_id, so
    # every chain.v1 record reads as v2 without rewrite.
    node_ref: Optional[str] = None
    # Per-occurrence apt sense-set (spec §2.2/§2.4). Optional: an empty list is
    # a fully valid step that simply yields no derived siblings.
    apt_senses: list[AptSense] = Field(default_factory=list)

    def resolved_node_ref(self) -> str:
        if self.node_ref:
            return self.node_ref
        if self.synset_id:
            return f"syn:{self.synset_id}"
        return f"vec:{vec_ref(self.phrase)}"


class ChainRecord(BaseModel):
    schema_version: ChainSchemaVersion
    topic: str
    topic_synset_id: Optional[str] = None
    vehicle: str
    vehicle_synset_id: Optional[str] = None
    topic_node_ref: Optional[str] = None
    vehicle_node_ref: Optional[str] = None
    proposer: str
    round: int = Field(ge=1)
    chain: list[ChainStep] = Field(min_length=2)
    chain_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: str  # ISO-8601 UTC

    @model_validator(mode="after")
    def _endpoint_canonicalisation(self) -> "ChainRecord":
        first = self.chain[0]
        last = self.chain[-1]
        # Topic endpoint: phrase must match the top-level topic field.
        # v1 records have phrase==head==topic (single-word); v2 multi-word endpoints
        # have phrase==topic but head may differ (the head noun only).
        if first.phrase != self.topic:
            raise ValueError(
                "endpoint canonicalisation: chain[0] must equal topic/topic_synset_id"
            )
        if self.topic_synset_id is not None:
            if first.synset_id != self.topic_synset_id:
                raise ValueError(
                    "endpoint canonicalisation: chain[0] must equal topic/topic_synset_id"
                )
        else:
            # vec: endpoint — require matching node_ref
            ref = first.resolved_node_ref()
            if not self.topic_node_ref or self.topic_node_ref != ref:
                raise ValueError(
                    "endpoint canonicalisation: vec endpoint requires matching node_ref"
                )
        # Vehicle endpoint: phrase must match the top-level vehicle field.
        if last.phrase != self.vehicle:
            raise ValueError(
                "endpoint canonicalisation: chain[-1] must equal vehicle/vehicle_synset_id"
            )
        if self.vehicle_synset_id is not None:
            if last.synset_id != self.vehicle_synset_id:
                raise ValueError(
                    "endpoint canonicalisation: chain[-1] must equal vehicle/vehicle_synset_id"
                )
        else:
            # vec: endpoint — require matching node_ref
            ref = last.resolved_node_ref()
            if not self.vehicle_node_ref or self.vehicle_node_ref != ref:
                raise ValueError(
                    "endpoint canonicalisation: vec endpoint requires matching node_ref"
                )
        return self


class StepAptSense(BaseModel):
    """An operator-ticked apt sense at a specific chain step position.

    Keyed by step index within the graded chain; the synset the operator
    confirmed as co-apt at that position. Written by the grading UI to the
    verdict; used by judge-harness to build per-position sense context.
    """
    step_idx: int = Field(ge=0)
    synset_id: str = Field(min_length=1)


class JudgementRecord(BaseModel):
    """v2 grading verdict — bridge-scoped (keyed by chain_signature, never on a node).

    Replaces the flat v1 `label` with two orthogonal axes — `linkage` (are the path's
    edges accurate?) + `metaphor` (is the endpoint pairing apt?) — plus a multi-select
    `tiers` list. v1 records (carrying `label`) are read via normalise_judgement.
    """
    schema_version: JudgementSchemaVersion
    # Server injects ts when the client omits it — clients should not set this field.
    ts: str = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    judged_by: str
    round: int = Field(ge=1)
    topic: str
    topic_synset_id: Optional[str] = None
    vehicle: str
    vehicle_synset_id: Optional[str] = None
    topic_node_ref: Optional[str] = None
    vehicle_node_ref: Optional[str] = None
    proposer: str
    chain_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    linkage: Linkage
    metaphor: MetaphorVerdict
    tiers: list[Tier] = Field(default_factory=list)
    tags: list[Tag] = Field(default_factory=list)
    confidence: Confidence = "high"
    notes: str = Field(default="", max_length=1000)
    supersedes_ts: Optional[str] = None
    # Per-step operator sense ticks (empty = no ticks; intended senses are NOT
    # duplicated here — only operator selections beyond the pre-lit intended).
    step_apt_senses: list[StepAptSense] = Field(default_factory=list)


class JudgementRecordV1(BaseModel):
    """Legacy v1 grading verdict — flat single `label`, retained read-only.

    New grades are written as v2 (JudgementRecord). This model exists so the
    validator and any legacy reader can still validate the stored v1 lines; on
    read they are mapped to the two axes via normalise_judgement.
    """
    schema_version: Literal["judgement.v1"]
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


# v1 `label` → (linkage, metaphor). None where the flat label carried no signal on that
# axis: bad_path only asserted a broken route (metaphor unknown); irrelevant means the
# pairing is unconnected (linkage moot). See the design doc's migration table.
_V1_LABEL_MAP: dict[str, tuple[Optional[str], Optional[str]]] = {
    "live": ("good", "live"),
    "dead": ("good", "dead"),
    "bad_path": ("bad", None),
    "irrelevant": (None, "irrelevant"),
}


# Structural tags that imply a broken topic→vehicle bridge (bad linkage),
# regardless of whether the grader also tapped the linkage button. Julian treats
# these as implying bad linkage and skips the redundant tap (esp. mobile), so a
# stored linkage=good on a tagged row is an untouched default, not a positive.
# 'padding' is EXCLUDED — a padded path can still bridge a good pairing; 'other'
# is unspecified. Mirrors LINKAGE_FORCING_TAGS in web/src/components/mf-grade-panel.ts.
LINKAGE_FORCING_TAGS = ("bad_head", "leap", "merge")


def effective_linkage(norm: dict):
    """Linkage corrected for the tag-implies-bad-linkage convention (read-time).

    Returns 'bad' when the recorded linkage is bad OR any structural forcing tag is
    present; else the recorded linkage (which may be None for a v1 'irrelevant' row).
    Pure interpretation — never mutates the stored verdict.
    """
    if norm.get("linkage") == "bad":
        return "bad"
    if any(t in LINKAGE_FORCING_TAGS for t in (norm.get("tags") or [])):
        return "bad"
    return norm.get("linkage")


def has_bad_head(norm: dict) -> bool:
    """True when the row is tagged bad_head — a mis-extracted INTERMEDIATE head.

    The topic/vehicle endpoints are canonicalised (head==phrase, see ChainRecord),
    so bad_head can only land on an intermediate step: it never touches the pairing.
    The live/dead verdict therefore stays valid (a bad_head chain can be a live
    metaphor) and the row stays in the liveness count; bad_head still counts as bad
    LINKAGE (see effective_linkage). What it DOES corrupt is the mis-snapped
    intermediate synset → unreliable path geometry, so such rows are held out of the
    geometry concordance only.
    """
    return "bad_head" in (norm.get("tags") or [])


def normalise_judgement(raw: dict) -> dict:
    """Return a dict carrying linkage/metaphor/tiers regardless of v1/v2 source.

    Non-destructive — used on read so old `label` records and new axis records are
    uniform to consumers (latest-verdict, stats, edge colour). v2 records pass through
    (defaulting tiers to []); v1 records gain axes via _V1_LABEL_MAP and tiers=[].
    v1 records predate tiers entirely, so they get tiers=[] with no value-migration;
    a stray legacy `tier` key is harmlessly ignored. (Do NOT read this as "tiers are
    unused" — v2 records carry them routinely; that misreading once contaminated an
    audit.) The original keys (incl. `label`) are preserved.
    """
    if "linkage" in raw or "metaphor" in raw:
        return {**raw, "tiers": raw.get("tiers", []), "tags": raw.get("tags", [])}
    linkage, metaphor = _V1_LABEL_MAP.get(raw.get("label"), (None, None))
    return {**raw, "linkage": linkage, "metaphor": metaphor, "tiers": [], "tags": []}


class DesignNotePost(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


# Sense-check label — the operator's verdict on whether an endpoint's snapped
# synset is the intended sense. Keyed on the endpoint (role, word,
# snapped_synset_id), NOT a chain; chain_signature stores one representative chain
# for traceability back to context. Written to SENSE_LABELS_PATH only.
SenseLabelSchemaVersion = Literal["sense_label.v1"]
SenseRole = Literal["topic", "vehicle"]
SenseVerdict = Literal["right", "wrong", "rare_ok", "unsure", "split"]


class SenseLabel(BaseModel):
    schema_version: SenseLabelSchemaVersion = "sense_label.v1"
    # Server injects ts when the client omits it (mirrors JudgementRecord).
    ts: str = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    role: SenseRole
    word: str
    snapped_synset_id: str
    verdict: SenseVerdict
    # Set only for wrong / rare_ok (the sense the operator intended); else None.
    intended_synset_id: Optional[str] = None
    # Multi-select apt senses for 'split' verdict: the synset_ids the operator ticked.
    # Empty list is valid (flag-only, enumerate later). Unused for other verdicts.
    apt_synset_ids: list[str] = Field(default_factory=list)
    # One representative chain the endpoint appeared in (traceability, not a key).
    chain_signature: Optional[str] = None

    @model_validator(mode="after")
    def _intended_required_for_corrective_verdicts(self) -> "SenseLabel":
        if self.verdict in ("wrong", "rare_ok") and not self.intended_synset_id:
            raise ValueError(
                "intended_synset_id must be set when verdict is 'wrong' or 'rare_ok'"
            )
        return self
