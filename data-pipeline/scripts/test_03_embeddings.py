import pytest
import json
import struct
from pathlib import Path

def test_embeddings_files_created():
    """Should create embeddings.bin and embeddings.idx after processing."""
    output_dir = Path(__file__).parent.parent / "output"
    
    embeddings_bin = output_dir / "embeddings.bin"
    embeddings_idx = output_dir / "embeddings.idx"
    
    assert embeddings_bin.exists(), "embeddings.bin not found - run 03_process_embeddings.py first"
    assert embeddings_idx.exists(), "embeddings.idx not found - run 03_process_embeddings.py first"

def test_embeddings_binary_format():
    """embeddings.bin should have correct binary format with header and vectors."""
    embeddings_bin = Path(__file__).parent.parent / "output" / "embeddings.bin"
    
    with open(embeddings_bin, 'rb') as f:
        # Read header: vocab_size and dim as uint32 (8 bytes total)
        header_data = f.read(8)
        assert len(header_data) == 8, "Header should be 8 bytes"
        
        vocab_size, dim = struct.unpack('<II', header_data)
        assert vocab_size == 400000, f"Expected vocab size 400000, got {vocab_size}"
        assert dim == 100, f"Expected dimension 100, got {dim}"
        
        # Check we have data for all vectors
        file_size = embeddings_bin.stat().st_size
        expected_size = 8 + (vocab_size * dim * 4)  # header + vectors (float32 = 4 bytes)
        assert file_size == expected_size, f"Expected file size {expected_size}, got {file_size}"

def test_embeddings_index_format():
    """embeddings.idx should be JSON mapping word to byte offset."""
    embeddings_idx = Path(__file__).parent.parent / "output" / "embeddings.idx"
    
    with open(embeddings_idx, 'r') as f:
        index = json.load(f)
    
    assert isinstance(index, dict), "Index should be a dictionary"
    assert len(index) == 400000, f"Expected 400000 words in index, got {len(index)}"
    
    # Test known words
    assert 'the' in index, "Common word 'the' missing from index"
    assert 'and' in index, "Common word 'and' missing from index"
    assert 'house' in index, "Common word 'house' missing from index"
    
    # Test offset format (should be integer)
    for word, offset in list(index.items())[:10]:  # Test first 10 entries
        assert isinstance(offset, int), f"Offset for '{word}' should be integer, got {type(offset)}"
        assert offset >= 8, f"Offset for '{word}' should be >= 8 (after header), got {offset}"

def test_embeddings_vector_access():
    """Should be able to read vectors using index offsets."""
    embeddings_bin = Path(__file__).parent.parent / "output" / "embeddings.bin"
    embeddings_idx = Path(__file__).parent.parent / "output" / "embeddings.idx"
    
    with open(embeddings_idx, 'r') as f:
        index = json.load(f)
    
    with open(embeddings_bin, 'rb') as f:
        # Read header to get dimension
        vocab_size, dim = struct.unpack('<II', f.read(8))
        
        # Test reading a known vector
        word = 'the'
        offset = index[word]
        f.seek(offset)
        vector_data = f.read(dim * 4)  # 100 float32 values
        
        assert len(vector_data) == dim * 4, f"Vector data should be {dim * 4} bytes"
        
        # Unpack and verify we get 100 float values
        vector = struct.unpack(f'<{dim}f', vector_data)
        assert len(vector) == dim, f"Should have {dim} dimensions, got {len(vector)}"
        
        # Check some basic properties of the vector
        assert all(isinstance(v, float) for v in vector), "All vector values should be floats"
        assert not any(v == 0.0 for v in vector), "Vector should not contain all zeros (GloVe vectors are dense)"

def test_embeddings_coverage():
    """Should have embeddings for all words in GloVe file."""
    embeddings_idx = Path(__file__).parent.parent / "output" / "embeddings.idx"
    
    with open(embeddings_idx, 'r') as f:
        index = json.load(f)
    
    # Should have exactly 400,000 entries
    assert len(index) == 400000, f"Expected 400000 words, got {len(index)}"
    
    # All keys should be strings
    for word in index.keys():
        assert isinstance(word, str), f"Word '{word}' should be string"

def test_known_vectors_have_reasonable_values():
    """Known words should have reasonable embedding values."""
    embeddings_bin = Path(__file__).parent.parent / "output" / "embeddings.bin"
    embeddings_idx = Path(__file__).parent.parent / "output" / "embeddings.idx"
    
    with open(embeddings_idx, 'r') as f:
        index = json.load(f)
    
    with open(embeddings_bin, 'rb') as f:
        # Skip header
        struct.unpack('<II', f.read(8))
        
        # Test a few common words
        test_words = ['the', 'and', 'house', 'computer']
        
        for word in test_words:
            if word in index:  # Word might exist
                offset = index[word]
                f.seek(offset)
                vector_data = f.read(100 * 4)
                vector = struct.unpack('<100f', vector_data)
                
                # GloVe vectors typically have values in reasonable range
                max_val = max(vector)
                min_val = min(vector)
                
                assert max_val < 10.0, f"Vector for '{word}' has unusually high max value: {max_val}"
                assert min_val > -10.0, f"Vector for '{word}' has unusually low min value: {min_val}"
                assert not all(v == 0.0 for v in vector), f"Vector for '{word}' is all zeros"
