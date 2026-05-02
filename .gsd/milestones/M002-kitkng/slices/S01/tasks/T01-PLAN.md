---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T01: Define FastTextVectors container and refactor loader

Create a FastTextVectors dataclass in utils.py holding a numpy float32 matrix (n × 300) and a word_to_idx dict[str, int]. Implement __contains__ and __getitem__ for ergonomic access. Refactor load_fasttext_vectors() to parse directly into numpy rows instead of Python tuples. Update _fasttext_cache type. TDD: write tests for the new container's __contains__, __getitem__, .matrix shape, and .dim properties first.

## Inputs

- `Current load_fasttext_vectors() implementation in utils.py:58-101`
- `_fasttext_cache type at utils.py:55`

## Expected Output

- `FastTextVectors dataclass with matrix: np.ndarray, word_to_idx: dict[str, int], __contains__, __getitem__`
- `load_fasttext_vectors() returns FastTextVectors instead of dict[str, tuple]`
- `_fasttext_cache updated to dict[str, FastTextVectors]`
- `Tests for container behaviour and loader output`

## Verification

python -m pytest data-pipeline/scripts/test_utils.py -v && grep -r 'tuple\[float' data-pipeline/scripts/utils.py | wc -l returns 0
