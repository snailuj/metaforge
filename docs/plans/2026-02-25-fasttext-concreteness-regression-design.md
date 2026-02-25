# FastText Concreteness Regression — Design

**Goal:** Fill the concreteness coverage gap (48.5% → 80%+) by training a regression model to predict Brysbaert-scale concreteness scores from FastText 300d embeddings.

**Context:** The concreteness gate (P2) filters forge candidates by concreteness distance, but only 52,154 of 107,519 synsets have Brysbaert ratings. The remaining 55,365 synsets pass through unchecked. FastText embeddings are already available in the pipeline.

---

## Data Pipeline

- **Training data:** 52,154 synsets with Brysbaert scores (1.07–5.0, mean 3.33)
- **Features:** FastText 300d embeddings per synset
- **Synset embedding:** Mean of all lemma vectors in the synset (preserves distributional information from full synset)
- **OOV handling:** Synsets where no lemma has a FastText vector are skipped (no prediction possible)
- **Split:** 80/20 stratified train/test, stratified by concreteness quartile

## Model Shootout

Four models compared (all scikit-learn, CPU-only):

| Model | Why | Key hyperparameters |
|-------|-----|-------------------|
| Ridge | Linear baseline, fast, interpretable | alpha |
| SVR (RBF) | Literature winner (r=0.911 with FastText), non-linear | C, gamma, epsilon |
| k-NN | Geometry-based, no assumptions | k, distance weighting |
| Random Forest | Ensemble, robust to outliers | n_estimators, max_depth |

**Hyperparameter tuning:** 5-fold cross-validation via `GridSearchCV` on training set.

**Evaluation metrics** (on held-out 20% test set):
- Pearson r (primary — comparable to literature)
- R²
- RMSE (in Brysbaert scale units, 1-5)

**Performance:** Entire shootout completes in under 5 minutes. FastText loading is the slowest step.

## Gap-Filling & Integration

1. Best model predicts concreteness for all unrated synsets with FastText coverage
2. Predictions written to `synset_concreteness` with `source='fasttext_regression'`
3. Coverage stats logged (target: 80%+ total)
4. No model persistence — retrain from scratch each run (seconds, not hours)

Synsets with no FastText-covered lemmas remain unrated. The forge gate already handles NULL concreteness with pass-through.

## Dependencies

- `scikit-learn` added to `requirements.txt` (only new dependency)
- Existing: `numpy`, FastText vectors via symlink

## Literature Context

| Method | Embedding | Pearson r | Source |
|--------|-----------|-----------|--------|
| SVM regression | FastText 300d | 0.911 | Charbonnier & Wartena 2019 |
| k-NN | Skip-gram | ~0.80 | Ljubešić et al. 2018 |
| 4-layer NN | FastText | 0.91 | Bochkarev et al. 2022 |

Sources:
- [Charbonnier & Wartena 2019](https://aclanthology.org/W19-0415/)
- [Ljubešić et al. 2018](https://aclanthology.org/W18-3028/)
- [Wartena 2024 — Three Studies](https://aclanthology.org/2024.cogalex-1.17/)
