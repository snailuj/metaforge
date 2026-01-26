#!/usr/bin/env python3
"""
Process GloVe embeddings into binary format with word index.

Converts glove.6B.100d.txt (400,000 words × 100 dimensions) to:
- embeddings.bin: binary format with header + float32 vectors
- embeddings.idx: JSON mapping word → byte offset

Binary format:
- Header (8 bytes): vocab_size (uint32), dim (uint32)  
- Vectors: each vector = 100 × float32 = 400 bytes
- Total size: 8 + 400,000 × 400 = 160,000,008 bytes (~153MB)
"""

import json
import struct
from pathlib import Path

def main():
    # Paths
    raw_dir = Path(__file__).parent.parent / "raw"
    output_dir = Path(__file__).parent.parent / "output"
    
    glove_file = raw_dir / "glove.6B.100d.txt"
    embeddings_bin = output_dir / "embeddings.bin"
    embeddings_idx = output_dir / "embeddings.idx"
    
    print(f"Processing {glove_file}...")
    
    # Process GloVe file
    vocab = {}
    vectors = []
    word_count = 0
    
    with open(glove_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if line_num % 50000 == 0:
                print(f"  Processed {line_num:,} lines...")
            
            parts = line.strip().split(' ')
            word = parts[0]
            values = [float(x) for x in parts[1:]]
            
            vocab[word] = word_count
            vectors.append(values)
            word_count += 1
    
    print(f"Loaded {len(vectors):,} words with {len(vectors[0])} dimensions each")
    
    # Write binary embeddings file
    vocab_size = len(vectors)
    dim = len(vectors[0])
    
    print(f"Writing {embeddings_bin}...")
    
    with open(embeddings_bin, 'wb') as f:
        # Write header: vocab_size, dim as uint32 (little-endian)
        f.write(struct.pack('<II', vocab_size, dim))
        
        # Write vectors as float32
        for i, vector in enumerate(vectors):
            if i % 50000 == 0:
                print(f"  Wrote {i:,} vectors...")
            
            # Convert to float32 and pack
            float32_vector = [float(x) for x in vector]  # Ensure float32
            f.write(struct.pack(f'<{dim}f', *float32_vector))
    
    print(f"Binary file written: {embeddings_bin.stat().st_size:,} bytes")
    
    # Write word index (word → byte offset)
    print(f"Writing {embeddings_idx}...")
    
    # Calculate offsets: header (8 bytes) + vector_index × 400 bytes
    index = {}
    for word, vector_idx in vocab.items():
        byte_offset = 8 + (vector_idx * dim * 4)  # 4 bytes per float32
        index[word] = byte_offset
    
    with open(embeddings_idx, 'w') as f:
        json.dump(index, f, separators=(',', ':'))  # Compact JSON
    
    print(f"Index written with {len(index):,} word mappings")
    
    # Verification
    print("\nVerification:")
    print(f"  Expected file size: {8 + (vocab_size * dim * 4):,} bytes")
    print(f"  Actual file size: {embeddings_bin.stat().st_size:,} bytes")
    print(f"  Vectors: {vocab_size:,}")
    print(f"  Dimensions: {dim}")
    print(f"  Index entries: {len(index):,}")
    
    # Test access to a few words
    test_words = ['the', 'and', 'house']
    print(f"\nTesting vector access:")
    
    with open(embeddings_idx, 'r') as f:
        idx = json.load(f)
    
    with open(embeddings_bin, 'rb') as f:
        # Read header
        header_data = f.read(8)
        vocab_check, dim_check = struct.unpack('<II', header_data)
        
        for word in test_words:
            if word in idx:
                offset = idx[word]
                f.seek(offset)
                vector_data = f.read(dim * 4)
                vector = struct.unpack(f'<{dim}f', vector_data)
                print(f"  {word}: offset={offset}, first_3_values={[round(v, 4) for v in vector[:3]]}")

if __name__ == "__main__":
    main()
