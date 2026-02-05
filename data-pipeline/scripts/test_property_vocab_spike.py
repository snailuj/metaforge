"""Test spike for property vocabulary generation (Solution 5 validation)."""
import json
from pathlib import Path
import pytest

SPIKE_OUTPUT = Path(__file__).parent.parent / "output" / "property_spike.json"

def test_spike_output_exists():
    """Verify spike generated output file."""
    assert SPIKE_OUTPUT.exists(), "Spike should create property_spike.json"

def test_spike_output_structure():
    """Verify spike output has expected structure."""
    with open(SPIKE_OUTPUT) as f:
        data = json.load(f)

    assert "synsets" in data
    assert "all_properties" in data
    assert "property_frequency" in data
    assert len(data["synsets"]) > 0, "Should have processed synsets"
    assert len(data["all_properties"]) > 0, "Should have extracted properties"

def test_property_diversity():
    """Verify spike captured diverse property types."""
    with open(SPIKE_OUTPUT) as f:
        data = json.load(f)

    props = data["all_properties"]
    # Should have at least 50 unique properties from 100 synsets
    assert len(props) >= 50, f"Expected 50+ properties, got {len(props)}"

    # Check for synonym clusters (indicates need for curation)
    # Example: 'wet', 'damp', 'moist' should all appear
    physical_props = [p for p in props if any(x in p.lower() for x in ['wet', 'damp', 'moist', 'dry'])]
    assert len(physical_props) >= 2, "Should capture synonym variants (wet/damp/moist)"

def test_property_frequency_distribution():
    """Verify frequency data captured for analysis.

    NOTE: Initial spike discovered LLM generates full sentences rather than
    short property terms. This test verifies data was captured; prompt
    refinement needed for shorter, reusable properties.
    """
    with open(SPIKE_OUTPUT) as f:
        data = json.load(f)

    freq = data["property_frequency"]
    # Verify frequency data exists (analysis happens in manual review)
    assert len(freq) > 0, "Should have property frequency data"

    # Stats should exist
    stats = data.get("stats", {})
    assert stats.get("total_properties", 0) > 0, "Should have total properties count"
    assert stats.get("unique_properties", 0) > 0, "Should have unique properties count"
