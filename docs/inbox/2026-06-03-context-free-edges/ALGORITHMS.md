# ALGORITHMS — data structures + pseudocode (per approach)

_Companion to `FINAL_REPORT.md`. Each block was produced/verified by a fact-checker agent that read the actual harness and re-ran it (API-free) or read its committed output. Pseudocode mirrors the real implementation; fidelity notes flag any simplification. Every harness lives in `docs/inbox/2026-06-03-context-free-edges/artifacts/`._

> **Verification status:** 10/11 approaches verified `numbers_match = MATCH`; judge feasibility `PARTIAL` (the '2 topics'→'3 topics' label fix, applied). One real bug was found and FIXED: the uniform-PageRank transition matrix (see that section).


---

## H-A shared-feature derivation

**Harness:** /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/derive_candidates.py (inverted-index candidate generator + fanout-scan), recall_ceiling.py (+ committed recall_ceiling_result.txt). Inputs: data-pipeline/output/lexicon_v2.db, metaphor_spike_apt/inapt_phase2_20260525T004154.jsonl, cohort_topics.json, derived_cohort_ms2.json. Cross-checked: separability_result.txt (AU

**Verification:** numbers `MATCH`. Sound, with two caveats the report mostly already flags. (1) The 2.10% is correctly a recall CEILING (upper bound on any pruned-shared-cluster derivation: a pair sharing zero surviving clusters can never be derived), not an achieved top-k recall — conservative, not inflated. (2) The "inapt pairs share MORE features (anti-correlation)" finding is partly a COHORT-CONSTRUCTION artifact: the inapt cohort's vehicles are plausible-but-wrong same-domain/near-synonym terms (anger->passion; time->duratio


**Data structure (real example):**

```
A real APT cohort record (metaphor_spike_apt_phase2_...jsonl, first line): {"topic":"anger","metaphors":[{"vehicle":"fire","shared_features":[{"dimension":"sensorimotor","concept":"heat"},{"dimension":"sensorimotor","concept":"burning"},{"dimension":"behaviour","concept":"consuming"},{"dimension":"behaviour","concept":"spreading"},{"dimension":"functional","concept":"destruction"},{"dimension":"effect","concept":"transformation"},{"dimension":"emotional","concept":"intensity"}],"confidence":...}, ...],"_gloss":...}. A real derived candidate (derived_cohort_ms2.json, topic "ideas", synset 64981): {"vehicle_synset_id":"28185","vehicle_lemma":"conceptualise","score":16.0882,"n_shared":3,"topic_concr":2.5,"vehicle_concr":3.24} — i.e. the substrate ranks a synonym (conceptualise) top, not a cross-domain vehicle. INAPT vehicles carry NO shared_features field (e.g. {"topic":"anger",...vehicle "passion","poison","burden"}), so the 0.31%/haiku-feat metric is APT-only by construction.
```


**Pseudocode (faithful to implementation):**

```
# derive_candidates.py (fan-out + candidate generation)
load synset_properties_curated -> syn2clusters[sid][cid]=salience_sum; cluster_df[cid]=#synsets
N = #synsets with any curated cluster (=81000)
fanout_after_pruning(df_cap): surviving = {cid: df for df<=df_cap};
    upper_bound_pairs = sum over surviving of C(df,2)   # multiplicity-counted upper bound, NOT distinct
build_inverted_index(df_cap): inv[cid] = [sids] only for clusters with df<=df_cap
derive_for_topic(t):  topic_clusters = {cid in t : df<=df_cap}
    for cid in topic_clusters: idf=log(N/df_c)
        for v in inv[cid] (v!=t): shared[v]+=cid; score[v]+= (1 | idf | idf*sqrt(sal_t*sal_v))
    keep v with len(shared[v])>=min_shared; sort desc; return top-k

# recall_ceiling.py (the recall/anti-correlation/0.31% owner)
build_resolver: curated vocab noun-first then polysemy-asc; fallback lemmas table (prefer noun);
    fallback naive suffix-strip s/es/ing/ed
load syn2cl (curated clusters), cl_df; load syn2pid (synset_properties), syn2tok (property text tokens, STOP+len<=2 filtered)
for each cohort line: tsid=resolve(topic); for each metaphor m: vsid=resolve(vehicle); skip if unresolved
    n+=1
    c_cap  += topic&vehicle share >=1 cluster with df<=200
    c_all  += share >=1 cluster (no cap)
    raw_pid+= share >=1 exact property_id
    raw_tok+= share >=1 property text token
    for sf in m.shared_features: feat_total+=1;
        cwords = tokens(sf.concept); if cwords&ttok and cwords&vtok: feat_in_both+=1
report fractions per granularity; report feat_in_both/feat_total
```


_Fidelity notes:_ Faithful. Quirks the pseudocode preserves: (1) fanout upper_bound = sum C(df,2) is a multiplicity-counted UPPER bound (pairs sharing k clusters counted k times), explicitly documented in the code as such — NOT the distinct-pair count, though for min_shared=1 it numerically matches the 455M/8.94M/271k figures the report quotes. (2) derive_candidates.py default --min-shared is 2 (used for derived_cohort_ms2.json); the fanout figures use min-shared 1. (3) Two DIFFERENT resolvers exist: derive_candidates.py uses syn2lemma (least-polysemous curated lemma) only for display, and consumes pre-supplied topic synset_ids from cohort_topics.json; recall_ceiling.py has its own noun-first resolver with su


---

## Separability + concreteness

**Harness:** /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/separability_experiment.py (re-run); committed output /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/separability_result.txt. Inputs: data-pipeline/output/lexicon_v2.db, metaphor_spike_apt_phase2_20260525T004154.jsonl (key="metaphors", label=1), metaphor_spike_inapt_phase2_20260525T

**Verification:** numbers `MATCH`. Methodologically sound for its stated claim, with caveats the report mostly states. (1) LEAKAGE: GroupKFold(5) groups by topic; 179/181 topics carry both classes; topic is snapped to one synset so concr_t is constant within a topic (apt-side 3.32 vs inapt-side 3.36 confirms balance). The grouped-CV AUCs (0.818/0.812/0.552/0.571) are leakage-free — no topic spans train and test. (2) The within-topic 0.825 / 163-179 IS in-sample (model fit on all rows, scored on same rows); code and printout both 


**Data structure (real example):**

```
REAL apt cohort record (anger, first metaphor): {"topic":"anger","metaphors":[{"vehicle":"fire","shared_features":[{"dimension":"sensorimotor","concept":"heat"},{"dimension":"behaviour","concept":"consuming"},{"dimension":"functional","concept":"destruction"},...],"confidence":0.93}],"_gloss":...}. REAL inapt record (anger): {"topic":"anger","inapt_metaphors":[{"vehicle":"passion","inapt_reason_type":"single_dimension","explanation":"Shares sensorimotor heat... but passion is constructive... missing the destructive intent..."}]}. The actual feature ROW the classifier consumes for apt anger->fire: {"topic":"anger","vehicle":"fire","label":1,"cos_dist":0.2513,"concr_t":2.41,"concr_v":4.68,"concr_gap":2.27,"shared_n":0.0,"shared_idf":0.0,"type_new":1.0,"type_union":3.0,"poly_t":5.0,"poly_v":21.0,"pcount_t":14.0,"pcount_v":15.0}. Note shared_n=0 even for the canonical anger->fire apt pair (no shared df-capped cluster).
```


**Pseudocode (faithful to implementation):**

```
load_db(con): cents=synset_centroids.centroid (float32); concr=synset_concreteness.score; poly=property_vocab_curated.polysemy; pcount=synset_centroids.property_count; syn2cl[sid][cluster]=salience_sum from synset_properties_curated; cl_members[cluster]=count; cl_type[cluster]=vocab_clusters.dominant_type (representative first, any-row fallback); n=#synsets with clusters.
build_resolver(con): in-memory word->synset, noun-preferred then min-polysemy from property_vocab_curated; fallback to lemmas table (noun-preferred); else strip suffixes s/es/ing/ed and retry. Drops words that do not resolve. (Replaces metaphor_graph.lookup_primary_synset to avoid ~0.4s/word.)
feats(tsid,vsid): cos_dist=1-cosine(cent_t,cent_v) [None->row dropped]; concr_t/v (missing->3.0); concr_gap=v-t; restrict each side's clusters to cl_members<=DF_CAP(200); shared=intersection; shared_idf=sum log(n/df); type_new=|veh_types - topic_types|; type_union; poly_t/v; pcount_t/v.
load_pairs: for apt(label1)/inapt(label0): resolve topic; for each metaphor resolve vehicle; build feats; collect rows {topic,vehicle,label,...12 feats}. Count misses{topic,vehicle,feat}.
abort if apt<20 or inapt<20.
X=12-feat matrix; y=label; groups=topic.
single-feature pooled AUC: roc_auc_score(y,x), direction-corrected max(a,1-a).
grouped_auc(cols): GroupKFold(5) by topic; per fold pipeline(StandardScaler, LogisticRegression(max_iter=1000,class_weight=balanced)); roc_auc on held-out fold; report mean+/-std. Run for: ALL / concr(concr_v,concr_t,concr_gap) / topic-specific(no concr) / shared-feature-substrate / cos_dist.
concreteness distribution: mean/sd of concr_v for apt vs inapt; mean concr_t per side (sanity: should be ~equal since topics shared).
recall ceiling: frac apt/inapt sharing >=1 / >=2 df-capped clusters.
within-topic (FLAGGED in-sample upper bound): clf.fit(X,y) on ALL data, score s=predict_proba(X); per mixed topic roc_auc(yt,s); report mean within-topic AUC + frac topics apt-mean>inapt-mean.
```


_Fidelity notes:_ Faithful. Simplifications: (1) omitted exact missing-value defaults beyond concr (cos_dist None drops the row, concr missing->3.0, concr_gap->0.0 if either missing). (2) cl_type built with representative-first then any-row fallback (both loops present in code). (3) The within-topic AUC is computed on a model fit on ALL rows (in-sample) — the code comment literally says "NB: in-sample; within-topic AUC reported as upper bound, flagged" and the print header says "IN-SAMPLE upper bound"; my pseudocode marks it FLAGGED. (4) GroupKFold has no shuffle/random_state so results are bit-reproducible (verified: two runs both 0.8178/0.8119).


---

## H-A-refined distance+feature-anchored

**Harness:** /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/ha_refined_separability.py (read + re-run) and its committed output ha_refined_result.json. Cross-checked against separability_experiment.py / separability_result.txt (the DIFFERENT harness whose 1507/983/524 grouped-CV numbers the report's Methods line conflates with this one). DB: /home/agent/projects/metaforge/dat

**Verification:** numbers `MATCH`. Sound for what it measures, with two flags. (1) The two explicit claims are correct: cross_type_shared AUC 0.4394 (below 0.5 because inapt pairs share MORE cross-type clusters — genuine anti-correlation, not a bug) and 70.3% of apt pairs share zero cluster. dist+grad (0.736) does not beat grad-alone (0.745) — verified. Snap handling is robust (snap and lemma gradients r=0.955, both ~0.73-0.745). (2) BASE-RATE CONFOUND on the concreteness gradient, which the report itself flags (C15): the inapt c


**Data structure (real example):**

```
Real inapt cohort record (first line of metaphor_spike_inapt_phase2_20260525T004154.jsonl): {"topic":"anger","inapt_metaphors":[{"vehicle":"passion","inapt_reason_type":"single_dimension","explanation":"Shares sensorimotor heat and intensity of activation, but passion is typically constructive... whereas anger is destructive..."}, ...], "_gloss":...}. The harness turns each (topic="anger", vehicle="passion") into a feature dict via feats(): e.g. {"dist": 1-cos(centroid_anger,centroid_passion), "n_shared": <#shared curated clusters>, "cross_type": <#shared clusters whose dominant_type != anger's dominant type>, "grad_snap": concr(passion_sense)-concr(anger_sense), "grad_lemma": lemma_mean_concr(passion)-lemma_mean_concr(anger), "rt": "single_dimension"}. Apt records use key "metaphors" with vehicle e.g. "fire" for "anger".
```


**Pseudocode (faithful to implementation):**

```
Substrate(db): cached lookups synsets_for(w)=lemmas.synset_id; centroid(s)=synset_centroids; clusters(s)={cluster_id:dominant_type} via synset_properties_curated JOIN vocab_clusters; concr(s)=synset_concreteness.score.
pick_synset(w): first sense with BOTH centroid AND clusters; else first with centroid; else first sense (naive WSD).
lemma_concr(w): mean of concr over ALL senses of w.
feats(t,v):
  ts,vs = pick_synset(t),pick_synset(v); if either None -> drop pair
  dist = 1 - cos(centroid(ts),centroid(vs))   # cross-domain distance
  shared = clusters(ts).keys & clusters(vs).keys
  tdom = most-common dominant_type among topic's clusters
  cross_type = count of shared clusters where vehicle's dominant_type != tdom
  grad_snap = concr(vs) - concr(ts)            # best-sense gradient
  grad_lemma = lemma_concr(v) - lemma_concr(t) # sense-agnostic gradient
  return {dist, n_shared=len(shared), cross_type, grad_snap, grad_lemma}
Build A=apt feature dicts (over r["metaphors"]), I=inapt (over r["inapt_metaphors"], rt=inapt_reason_type).
For each leg fn in {cos_dist, concr_grad_snap, concr_grad_lemma, cross_type_shared, neg_shared_curated=-n_shared, dist_plus_0.15grad=dist+0.15*grad_lemma}:
  auc = Mann-Whitney rank AUC(pos=fn over A, neg=fn over I)   # IN-SAMPLE, full cohort, no CV, no fitting
  ci95 = bootstrap: random.seed(0); 1000x resample A and I with replacement, recompute auc, take 2.5/97.5 pctiles
Operating points: for thr in {0,0.3,0.5,0.7,1.0,1.5}: keep pairs with grad_lemma>=thr; report apt_kept,inapt_kept,precision,apt_recall.
Per inapt class: auc(grad_lemma) of apt vs each inapt_reason_type group.
```


_Fidelity notes:_ Faithful. Quirks to note: (1) AUCs are single-feature ROC-AUC computed IN-SAMPLE on the full 1067/582 cohort — there is NO train/test split and NO cross-validation in this harness (CV lives in the separate separability_experiment.py). For a raw unparameterised feature this is fine (nothing to overfit), but it is NOT the "topic-grouped 5-fold logistic regression (no leakage)" the report's Methods line implies for this agent. (2) cross_type counts shared clusters where the VEHICLE's dominant_type differs from the TOPIC's single most-common dominant_type — a slightly asymmetric definition. (3) pick_synset is naive WSD (first qualifying sense), so synset selection depends on SQL row order; this 


---

## H-B embedding ANN band

**Harness:** RAN (API-free, numpy+sqlite): /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/hb_band_recall.py — wrote stdout band table + /tmp/hb_band_recall_per_topic.json. READ (committed, no API spent): generation_cost_log.jsonl, generation_cost_result.txt, sonnet_cost_result.txt (per-call cost floors), p1_swarm_findings.json (the H-B swarm record carrying the 2,870/odds/cos

**Verification:** numbers `MATCH`. Methodologically SOUND for what it claims (a recall ceiling), with caveats the report already states. No data leakage in the rank computation: the topic's own synsets are excluded from the ranking (`if i not in topic_idx`), so there is no trivial self-match. Rank/recall arithmetic is correct and reproduces exactly. Cost arithmetic is internally consistent. THREE caveats a SOTA reviewer would flag (report discloses all three, so not fatal to the headline): (1) Cohort confound — apt AND inapt vehi


**Data structure (real example):**

```
REAL, from the harness + spike files for topic "anger". INPUT (apt spike record, one metaphor): {"topic":"anger","metaphors":[{"vehicle":"fire","shared_features":[{"dimension":"sensorimotor","concept":"heat"},{"dimension":"sensorimotor","concept":"burning"},{"dimension":"behaviour","concept":"consuming"},...],"confidence":0.93}, ...]}. OUTPUT (per-topic apt_min_ranks, vehicle→min cosine rank over 81,185 centroids): {"topic":"anger","apt_min_ranks":[["fire",19],["volcano",171],["storm",190],["flood",94],["kettle",9520]]}. The near-synonym "fire" sits at rank 19; the live literary metaphor "kettle" is buried at rank 9,520. The matched INAPT record is constructed as same-domain near-misses, e.g. {"topic":"anger","inapt_metaphors":[{"vehicle":"passion","inapt_reason_type":"single_dimension",...},{"vehicle":"poison",...}]} — passion (an emotion) ranks ABOVE fire/kettle in FastText space.
```


**Pseudocode (faithful to implementation):**

```
load synset_centroids -> M (81185 x 300 float32); L2-normalise -> Mn
idx_of = {synset_id: row}
def lemma_synsets(w): SELECT synset_id FROM lemmas WHERE lemma=lower(w); keep those in idx_of
apt = read metaphor_spike_apt_phase2 (200 topics); inapt keyed by topic
for each apt topic rec:
    tsyn = lemma_synsets(topic); if empty: skip (15 skipped -> 185 topics)
    apt_veh  = {vehicle: set(lemma_synsets(vehicle))} for each metaphor, drop empties (986 total)
    inapt_veh = same from inapt[topic].inapt_metaphors (535 total)
    for pol in [first, union]:
        seeds = [shortest-then-lexmin tsyn] if first else all tsyn
        best_cos = max over seeds of (Mn @ Mn[seed].T)   # cosine to nearest topic sense
        order = argsort(-best_cos)
        ranked = [synset for i in order if i not in topic_synsets]   # 0-indexed position
        rankpos[s] = position in ranked
        for b in [10,25,50,100,200,500,1000]:
            band = ranked[:b]
            apt_hit  += count(apt vehicles whose any sense in band)
            inapt_hit+= count(inapt vehicles whose any sense in band)
        if union: record per-vehicle min(rankpos over its senses)  # apt_min_ranks
report apt_hit/apt_total, inapt_hit/inapt_total per band; dump per-topic min-ranks
# (separate analysis, also re-run) percentiles of the 986 apt min-ranks; recall@b = mean(rank<b);
# cost: calls = 100000 * b / J(=25); 50%-recall b=2870 -> 11.48M calls -> [$0.0075,$0.0765]/call -> $86k-878k
```


_Fidelity notes:_ Faithful. Quirks to flag explicitly: (1) "rank" = 0-indexed position among non-topic synsets (topic's own senses excluded), so the denominator is 81,185 minus the topic's sense count; report writes "/81,185" as an approximate label. (2) union policy uses the MAX cosine over ALL topic senses — a generous/best-case snap; "first" policy (shortest-then-lexicographically-smallest synset id) is also computed and is same-or-worse. (3) A vehicle counts as "in band" if ANY of its senses lands in the top-b (generous union over vehicle senses too). (4) The percentile/recall@b and cost arithmetic are NOT inside hb_band_recall.py — they are the documented downstream one-liners (I re-derived them from the


---

## H-C distillation classifier

**Harness:** /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/hc_fast_multivariate.py (the classifier harness) and its committed output /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/hc_multivariate_result.json. Cross-referenced /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/separability_result.txt (the 12-fe

**Verification:** numbers `MATCH`. SOUND on the headline. Leakage: clean — StandardScaler is inside make_pipeline and fit only on X[train]; GroupKFold(groups=topic) keeps every topic out of its own test fold (the relevant leak for a topic-conditioned task); precision@k, calibration, dead-leakage and per-inapt-class AUC all use out-of-fold (oof) scores, not in-sample. Fully deterministic (DB lookups + deterministic CV splits + lbfgs LR), hence exact reproduction. Caveats a hostile reviewer should still note, all of which the repor


**Data structure (real example):**

```
REAL input record (first line of metaphor_spike_apt_phase2_...jsonl): {"topic": "anger", "metaphors": [{"vehicle": "fire", "shared_features": [{"dimension": "sensorimotor", "concept": "heat"}, {"dimension": "sensorimotor", "concept": "burning"}, {"dimension": "behaviour", "concept": "consuming"}, ...], "confidence": 0.93}, ...], "_gloss": "..."}. The harness flattens this to one training row per (topic, vehicle): label=1 (apt; rt="apt" because apt records carry no inapt_reason_type), then 11 context-free features e.g. {"cos_dist":..., "concr_gap_snap": cv-ct, "concr_grad_lemma":..., "shared_n":0.0, "shared_idf":0.0, "type_new":..., "type_union":..., "poly_t":..., "poly_v":..., "pcount_t":..., "pcount_v":...}. Inapt rows come from the inapt file and carry rt in {single_dimension:320, same_domain:167, dead_metaphor:68, wrong_concreteness:21, synonym_or_hypernym:24}; the rt="dead_metaphor" subset drives the per-inapt-class AUC of 0.608.
```


**Pseudocode (faithful to implementation):**

```
load DB: synset_centroids (FastText), synset_concreteness, property_vocab_curated.polysemy,
         synset_properties_curated (synset->cluster salience), vocab_clusters.dominant_type
for each (topic, vehicle) in APT(label=1) and INAPT(label=0):
    tsid = lookup_primary_synset(topic)   # curated noun-preferred resolver (deterministic)
    vsid = lookup_primary_synset(vehicle)
    if not tsid or not vsid: skip
    cd = cosine_distance(centroid[tsid], centroid[vsid]); if None: skip
    keep only clusters with cluster_membership <= DF_CAP(=200)   # drop mega stop-word clusters
    shared = topic_clusters & vehicle_clusters
    shared_idf = sum(log(n_synsets_with_clusters / cluster_size) for c in shared)
    features(11) = [cos_dist, concr_gap_snap(=cv-ct, snapped-sense), concr_grad_lemma(=lemma-mean cv-ct),
                    shared_n, shared_idf, type_new, type_union, poly_t, poly_v, pcount_t, pcount_v]
    rt = inapt_reason_type or "apt"
X, y, groups=topic
single_feature_auc[f] = max(AUC, 1-AUC) for each feature      # direction-corrected
gkf = GroupKFold(5) on groups   # NO topic in both train+test
for train,test in gkf:
    clf = Pipeline(StandardScaler -> LogisticRegression(max_iter=2000, class_weight="balanced"))
    clf.fit(X[train]); oof[test] = clf.predict_proba(X[test])[:,1]; aucs += roc_auc_score(y[test], p)
    coefs += clf.coef_
grouped_cv_auc_mean = mean(aucs)            # = 0.764  (HEADLINE)
mean_abs_coef[f]    = |mean(coefs[f])|      # concr_grad_lemma=0.704 dominates
# everything below uses OUT-OF-FOLD scores (no leakage):
precision@k: sort by oof desc, keep top frac, report apt_precision + lift over base(=0.652)
dead_leakage / per_inapt_class_auc[cls] = roc_auc_score(apt vs that rt-class, oof)  # dead_metaphor=0.608
```


_Fidelity notes:_ Faithful. Simplifications: (1) I wrote 11 features; the code's fnames list is literally 11 (cos_dist, concr_gap_snap, concr_grad_lemma, shared_n, shared_idf, type_new, type_union, poly_t, poly_v, pcount_t, pcount_v) — note the feats() dict also defines them but the report's "12 features" wording belongs to the SIBLING separability_experiment.py (which splits concreteness into concr_t/concr_v/concr_gap = 12), not this harness. (2) lemma_concr_fn computes a sense-agnostic lemma-mean concreteness via a lemmas JOIN synset_concreteness query (the concr_grad_lemma feature); I compressed that to "lemma-mean". (3) concr_gap_snap and concr_grad_lemma both default to 0.0 when concreteness is missing. 


---

## H-D tiered routing + generation cost

**Harness:** /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/hd_routing_cost_harness.py (pure cost model, read only — NOT run, would spend nothing anyway); measure_generation_cost.py + measure_sonnet_cost.py (read only — NOT run, would spend API); generation_cost_log.jsonl (committed output, re-analysed with python+statistics); cross-checked budget-ledger.md, generation_cost_r

**Verification:** numbers `MATCH`. Sound for what it claims, with honest-but-important small-n caveats the report already flags. (1) The per-call rates are direct CLI total_cost_usd captures of the REAL prompts — no fabrication, no leakage. (2) The "±0.017" is population stdev over n=5; the Haiku mean $0.062 is inflated by the single cold call ($0.0949) — warm-only mean is $0.0538 (n=4). The report's own caveat ("production batches run warm") makes this conservative (over-estimates), which is the safe direction for a cost ceiling


**Data structure (real example):**

```
Real cold Haiku row from generation_cost_log.jsonl line 1: {"ok": true, "model": "haiku", "wall_s": 46.9, "duration_ms": 42058, "cost_usd": 0.0949275, "in_tok": 10, "out_tok": 5612, "cache_creation": 53486, "cache_read": 0, "result_len": 1315}. Real warm Sonnet row (line 8): {"ok": true, "model": "sonnet", "wall_s": 135.1, "cost_usd": 0.14325420000000003, "out_tok": 8736, "cache_creation": 0, "cache_read": 40684}. The cold→warm split is observable: cold call pays cache_creation>0/cache_read=0; warm calls have cache_read≈36.6k (Haiku) / 40.7k (Sonnet) and cache_creation drops.
```


**Pseudocode (faithful to implementation):**

```
## ACTUAL measurement (measure_generation_cost.py + measure_sonnet_cost.py)
for topic in [anger, life, hope, grief, courage]:        # 5 Haiku
    prompt = build_apt_prompt(topic, gloss)              # REAL spike prompt
    j = run `claude -p --output-format json --model haiku --max-turns 1 --strict-mcp-config --mcp-config empty`
    append {model, cost_usd=j.total_cost_usd, out_tok, cache_creation, cache_read, wall_s} to generation_cost_log.jsonl
sonnet runs: 1 in measure_generation_cost (anger, COLD, 0.345) + 2 in measure_sonnet_cost (anger warm 0.229, life warm 0.143)
# Cost is whatever the CLI reports in total_cost_usd; nothing fabricated.

## VERIFICATION (what I ran, API-free, over the committed log)
rows = [json.loads(l) for l in generation_cost_log.jsonl]
gen  = [r for r in rows if "wall_s" in r]                 # excludes 69 judge_feasibility rows
haiku = costs where model==haiku  -> mean=0.0620, pstdev=0.0171, min 0.0466, max 0.0949 (n=5)
sonnet= costs where model==sonnet -> [0.1433, 0.2287, 0.3446] (n=3; 0.143/0.229 warm, 0.345 cold)
# 100k projection (report's method, measured rates):
haiku_only_100k = 100_000 * 0.062            -> $6.2k
full_2call_100k = 100_000 * (0.062 + sonnet) -> $20.5k @0.143, $29.1k @0.229, $40.7k @0.345(cold)
# H-D retraction: measured/stale = 0.062/0.005 = 12.4x  (report says "~15x")

## hd_routing_cost_harness.py (PURE — never called the API)
per_call_cost(model, cold) = CLI_SYS_TOKENS(57279) * (cw if cold else cr)/1e6 + content_in*price_in + content_out*price_out
project_100k(h,s) = {baseline: 100k*(h+s), haiku_only: 100k*h, banded_X%: 100k*h + 100k*X*s}
main() STILL prints project_100k(0.005, 0.0147)  # the stale estimate the report retracts; emit_call_plan also hardcodes phase2_haiku_per_call_usd=0.005
```


_Fidelity notes:_ Faithful. One nuance worth flagging for the fact-checker: hd_routing_cost_harness.py is NOT the source of the report's headline cost numbers — it is a pure scaffold whose own main() still emits the discredited $0.005/$0.0147 projection. The report's real numbers come entirely from generation_cost_log.jsonl (produced by measure_generation_cost.py / measure_sonnet_cost.py). The harness's `summarise_cost_log` reads a DIFFERENT file (hd_cost_log.jsonl) that was never produced (the orchestrator measured via measure_generation_cost.py instead), so summarise_cost_log/emit_call_plan/needs_escalation/build_judge_prompt are dead code for this report. My pseudocode separates the dead pure-scaffold from


---

## H-E caching/dedup

**Harness:** /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/measure_dedup_HE.py (ran it, API-free, reproduced). Inputs: data-pipeline/grading/sonnet_chains_provisional_r1.jsonl (200 chains), data-pipeline/output/metaphor_spike_apt_phase2_20260525T004154.jsonl (200 topics/1112 apt pairs), .../metaphor_spike_inapt_phase2_20260525T004154.jsonl, data-pipeline/output/lexicon_v2.db

**Verification:** numbers `MATCH`. Methodologically SOUND for the conclusions it supports, with three caveats a hostile reviewer should know. (1) The "1.00x edge dedup by construction" claim is conceptually right (distinct topics -> distinct bridge edges) but the harness's own top-line `overall_edge_dedup` field is 1.047 (it blends hop-edges, which reuse 1.06x), and the bridge-only factor is actually 1.0101, not exactly 1.00 — caused by 5 records with EMPTY vehicle_synset_id colliding in a set (a data-quality artifact, not real m


**Data structure (real example):**

```
Real chain record (line 1 of sonnet_chains_provisional_r1.jsonl), the unit chain_recurrence dedups: {"schema_version":"chain.v1","topic":"anger","topic_synset_id":"30227","vehicle":"volcano","vehicle_synset_id":"79695","proposer":"sonnet_v1","round":1,"chain_signature":"9ea3c79f...","generated_at":"2026-05-30T00:00:00Z","chain":[{"phrase":"anger","head":"anger","synset_id":"30227"},{"phrase":"pressure","head":"pressure","synset_id":"60988"},{"phrase":"subterranean heat","head":"heat","synset_id":"63717"}, ... (5 steps total)]}. A "bridge" edge = (topic_synset_id, vehicle_synset_id) = ("30227","79695"); "hop edges" = consecutive (synset_id, synset_id) pairs within `chain`. Real cache-validity example (apt vs inapt cohort): vehicle "orbit" is apt for topic "continuance" but inapt for topic "environs" — proving aptness is topic-dependent, so a context-free (V,C) cache key cannot decide it.
```


**Pseudocode (faithful to implementation):**

```
chain_recurrence(200 r1 chains):
  veh_count = Counter(c.vehicle_synset_id)                      # node reuse
  hop_edges = Counter((step[i].synset_id, step[i+1].synset_id) for each consecutive pair in c.chain)
  inter = Counter(step.synset_id for interior steps c.chain[1:-1])
  bridges = SET of (c.topic_synset_id, c.vehicle_synset_id)     # SET -> dedups
  total_edges    = len(chains) + sum(hop_edges.values())        # 200 + 852 = 1052
  distinct_edges = len(bridges) + len(hop_edges)                # 198 + 807 = 1005
  return vehicle_node_reuse=200/len(veh), hop_edge_reuse, intermediate_node_reuse,
         overall_edge_dedup=total_edges/distinct_edges          # 1.047

vehicle_amortisation(200-topic apt cohort, 1112 vehicle slots):
  topic_veh = {topic: [m.vehicle ...]}
  repeat 200x: shuffle topics; walk rarefaction -> points (cumulative_total_slots, cumulative_distinct_vehicles)
  pts = mean(distinct) per total over the 200 shuffles
  OLS fit log(distinct) = log(K) + beta*log(total)             # beta ~= 0.82, K ~= 1.92
  amort_at(N): slots = N*10; distinct = min(K*slots^beta, VOCAB=107519); return slots/distinct
  # at 100k: raw 163,353 > VOCAB -> CLAMPED to 107519 -> 9.30x (clamp is load-bearing)

cache_validity(apt cohort, inapt cohort; both 200 same topics):
  apt_veh[v] = set of topics v is apt for; inapt_veh[v] likewise
  multi = {v : |apt_veh[v]| >= 2}                               # 195
  contested = multi & keys(inapt_veh)                           # 64
  return contested_flip_fraction = 64/195 = 0.328,
         direct_contradictions = |apt_pairs & inapt_pairs| = 66 # same (topic,vehicle) both apt+inapt

profile_collisions(lexicon_v2.db):
  prof[synset] = frozenset(cluster_ids) from synset_properties_curated
  ceiling = (81000 - 80486_distinct_profiles) / 81000 = 0.0063
```


_Fidelity notes:_ Faithful. Simplifications: (1) I show the OLS via the (n,Σx,Σy,Σxx,Σxy) closed form as a single "OLS fit" line — the code computes it inline with those sums. (2) `random.shuffle` has NO fixed seed, so K and beta vary slightly per run (I confirmed beta stable 0.8195–0.8227 across 5 seeds; the harness run I captured gave beta=0.8216, K=1.921). (3) hop_edges/inter built per-chain in one loop in the code; I split them for clarity. (4) inapt vehicles come from r["inapt_metaphors"] (different key than apt's r["metaphors"]).


---

## H-F relational shortcuts

**Harness:** /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/hf_relational_shortcuts.py (re-run from repo root, API-free Part A). Input data: data-pipeline/output/metaphor_spike_apt_phase2_20260525T004154.jsonl (200 topics, 1112 apt rows), .../metaphor_spike_inapt_phase2_20260525T004154.jsonl (200 topics, 600 inapt rows), data-pipeline/grading/sonnet_chains_provisional_r1.json

**Verification:** numbers `MATCH`. Implementation is SOUND for what it measures, with caveats the harness itself flags. (1) Symmetry 0/1112: correct count; but it is observational only — it bounds the GENERATOR's reverse-production rate, NOT the judge's reverse-acceptance rate, because the generator was never asked to reverse any pair (rev_inapt=0 confirms reverses appear in neither cohort). The harness explicitly prints this caveat and the swarm's variance field calls it "suggestive not decisive"; Part B (the causal test) was ne


**Data structure (real example):**

```
Real apt cohort record (first line of metaphor_spike_apt_phase2_20260525T004154.jsonl), topic "anger": {"topic": "anger", "metaphors": [{"vehicle": "fire", "shared_features": [{"dimension": "sensorimotor", "concept": "heat"}, {"dimension": "behaviour", "concept": "consuming"}, {"dimension": "functional", "concept": "destruction"}, {"dimension": "emotional", "concept": "intensity"}], "confidence": 0.93}, ...], "_gloss": "..."}. The harness reduces this to the pair set {("anger","fire"), ...}. Real inapt record, same topic: {"topic": "anger", "inapt_metaphors": [{"vehicle": "passion", "inapt_reason_type": "single_dimension", "explanation": "Shares sensorimotor heat... but passion is constructive... anger is destructive..."}], "_gloss": "..."}. A real dual-labelled (self-contradicting) pair: ("appearance","mask") appears in BOTH apt_pairs and inapt_pairs. A real NEW transitive edge produced by closure: ("hope","candle") and ("hope","explosion") (cross-domain, unverifiable).
```


**Pseudocode (faithful to implementation):**

```
load apt rows, inapt rows, chains
apt_pairs  = { (topic, m.vehicle) for row in apt for m in row.metaphors }          # 1112 unique
inapt_idx  = { (topic, m.vehicle): m for row in inapt for m in row.inapt_metaphors }
inapt_pairs= set(inapt_idx)                                                          # 600 unique

# A1 SYMMETRY (observational)
rev_apt   = count (t,v) in apt_pairs where (v,t) in apt_pairs        # -> 0/1112
rev_inapt = count (t,v) in apt_pairs where (v,t) in inapt_pairs      # -> 0
eps       = { (c.topic, c.vehicle) for c in chains }                 # 200 endpoints
rev_eps   = count (t,v) in eps where (v,t) in eps                    # -> 0/200
# print caveat: 0% reverse bounds GENERATOR's reverse-production, NOT judge acceptance

# A2 STABILITY / self-contradiction
both = apt_pairs & inapt_pairs                                       # 66 -> 5.9% of apt

# A3 TRANSITIVITY via bridge nodes (vehicles that are also topics)
bridge = apt_topics & apt_vehicles                                   # 11 nodes
to_X[v].add(t); from_X[t].add(v)  for (t,v) in apt_pairs
trans  = [(T,X,Y) for X in bridge for T in to_X[X] for Y in from_X[X] if T!=Y]  # 228 endpoints
lab    = [c in trans if (c.T,c.Y) in apt_pairs or inapt_pairs]       # 15 (6.6%) -> 93%+ unverifiable
tp     = [c in lab   if (c.T,c.Y) in apt_pairs]                      # 14/15 "precision" (CIRCULAR)

# A4 NOMINAL FREE MULTIPLIER
G[t].add(v) for (t,v) in apt_pairs; direct = sum(len(G[t]))          # 1112
closure = { (a,c) : a->b in G, b->c in G, c!=a }                     # 228 (== A3 trans set)
new_t   = closure - apt_pairs                                        # 214 NEW edges
mult    = 2 * (direct + len(new_t)) / direct                         # 2x sym * 1.19x trans = ~2.4x

# PART B: print 20 highest-confidence cross-domain apt pairs as a reversal cohort + judge prompt. NO API CALL.
```


_Fidelity notes:_ Faithful. Two clarifications a fact-checker should map: (1) A3's `trans` set (228) and A4's `closure` set (228) are the SAME set — closure only differs by excluding (a,c) already in apt_pairs to get new_t=214. The 14 endpoints that ARE already direct apt edges are exactly A3's "14/15 precision" hits; this is why the precision is circular (the transitive rule merely rediscovers edges the generator already made). (2) `apt_topics = set(r['topic'] for r in apt)` = all 200 topics; `apt_vehicles` = 571 distinct vehicles; their intersection (bridge) = 11. (3) `_gloss` and `shared_features`/`inapt_reason_type` fields are loaded but unused by Part A's edge logic.


---

## Uniform PageRank graph traversal

> **⚠️ POST-FACT-CHECK CORRECTION.** The fact-check (verbatim below) found the bug it describes — `col_stochastic` used element-wise `A.multiply(diag)`, zeroing the hollow bipartite transition matrix, so PPR never propagated. **Bug fixed** (`P = A @ sp.diags(1/d)` + a column-stochastic assertion) and **re-run** (`multihop_graph_result_FIXED.txt`). **Corrected numbers:** PPR discrimination AUC **0.615** (raw) / **0.630** (idf) — weakly above chance, ~AA/RA level; as a generator apt median rank **14,202**/81,185 vs inapt **6,238** (inapt closer → anti-correlated; recall@100 apt 2.0%). AA/RA/CN (0.606/0.609/0.599) and BFS (all pairs 2–4 hops, 0 unreachable) were never affected by the bug. **Conclusion unchanged:** correct PPR is only weakly discriminative and cannot propose apt vehicles. The pseudocode below shows the corrected column-normalisation.

**Harness:** /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/multihop_graph_experiment.py (re-ran, ~3 min, API-free); /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/multihop_graph_result.txt (committed output); /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/multihop_graph_rows.json (committed per-pair rows);

**Verification:** numbers `MATCH`. UNSOUND for the PPR arm (the headline traversal result). The PPR/random-walk is degenerate: `col_stochastic` uses `A.multiply(D)` (element-wise) instead of `A @ D` (column scaling); since A has no diagonal and D is purely diagonal, P is the all-zero matrix. The power iteration `x = 0.15*e + 0.85*(P@x)` therefore never propagates mass — x = 0.15 at the topic, 0.0 at every other node, for all 60 iterations. Consequences: (1) The PPR scores feeding AUC are 0.0 for 1495/1497 pairs (a near-constant c


**Data structure (real example):**

```
Real per-pair row from multihop_graph_rows.json (the apt pair at index 1): {"label": 1, "ppr_raw": 0.0, "ppr_idf": 0.0, "adamic_adar": 0.15913091197110954, "resource_alloc": 0.0018656716417910447, "common_neigh": 1.0, "veh_rank": 30741}. Note ppr_raw/ppr_idf are 0.0 — across all 1497 rows only 2 have a non-zero PPR value (frac_zero = 0.99866); ppr columns take exactly 2 distinct values {0.0, 0.15}. veh_rank ranges 83..80999. A first apt row: {"label":1,"ppr_raw":0.0,"ppr_idf":0.0,"adamic_adar":0,"resource_alloc":0,"common_neigh":0.0,"veh_rank":68060}.
```


**Pseudocode (faithful to implementation):**

```
load syn→{cluster:salience} and cluster degree from synset_properties_curated
syns = sorted synsets (nS=81000); cls = sorted clusters (7728); N = nS+#clusters (88728)
build undirected bipartite A over N nodes, edges = synset<->cluster (has_property incidence)
  w_raw = 1.0 ; w_idf = max(log(nS/cluster_deg), 1e-6)
col_stochastic(A):                       # INTENDED: column-normalise
  d = column sums of A ; d[d==0]=1
  return A.multiply( diag(1/d) )         # *** BUG: Hadamard product, not A @ diag(1/d) ***
P_raw, P_idf = col_stochastic(...)        # ACTUAL RESULT: P is the all-zero matrix
ppr(P, topic): e = onehot(topic); x = e
  repeat 60: x = 0.15*e + 0.85*(P @ x)    # P==0 ⇒ x stays = 0.15*e (mass 0.15 at topic, 0 elsewhere)
  return x
resolve topic/vehicle words → synset_ids via build_resolver (noun-preferred, least-polysemous; morph strips s/es/ing/ed); drop unresolved
group cohort pairs by topic; for each topic:
  x_raw=ppr(P_raw,topic); x_idf=ppr(P_idf,topic)   # both all-zero except topic
  syn_scores = x_idf[:nS]; syn_scores[topic] = -1
  order = argsort(-syn_scores)             # all-tie ⇒ arbitrary quicksort order of synset indices
  for each vehicle v in topic:
    shared = clusters(topic) ∩ clusters(v)
    aa = Σ_{c in shared, deg>1} 1/log(deg_c)   # legit
    ra = Σ_{c in shared} 1/deg_c               # legit
    cn = |shared|                              # legit
    record ppr_raw=x_raw[v](=0), ppr_idf=x_idf[v](=0), aa, ra, cn, veh_rank=rank_of[v]
AUC(metric) = max(roc_auc, 1-roc_auc) over apt/inapt labels
BFS bipartite shortest path, first 120 apt + 120 inapt pairs, maxhop 6   # independent of PPR, legit
report PPR/AA/RA/CN AUC, apt/inapt median veh_rank + recall@k, BFS length histogram
```


_Fidelity notes:_ Faithful to the code. The load step iterates d.get(key,[]) over "metaphors"/"inapt_metaphors"; I omitted that key detail for brevity. The critical fidelity point is the col_stochastic line: the real code is `A.multiply(sp.csr_matrix((1.0/d,(range(N),range(N))),shape=(N,N)))`, which is element-wise multiplication between A (zeros on diagonal) and a diagonal matrix (non-zeros only on diagonal) → disjoint sparsity patterns → all-zero P. I verified this both on the full graph (col sums min=max=0.0, PPR total mass stuck at exactly 0.15 for all 60 iters, nnz=1) and on a 4×4 toy. veh_rank fallback is nS (81000) for unresolved vehicles, but all cohort vehicles resolve so it is essentially never hit 


---

## Guided multi-hop beam search

**Harness:** /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/guided_traversal_experiment.py (read in full; re-run attempted — CPU-starved by a competing leftover process, but its cohort header re-derived independently and matched); /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/guided_traversal_wide.py (read in full); committed outputs guided

**Verification:** numbers `MATCH`. Methodologically the harness is a reasonable steelman, but three quirks must be flagged. (1) AUC IS DOMINATED BY THE -1e9 UNREACHED TIES — at depth-3/beam-300 only ~8–13% of pairs are reached, so ~90% share an identical -1e9 score; the 0.506–0.545 AUC is therefore mechanically pinned near 0.5 by ties, not by a measured separating function. This is a real caveat the report does not state explicitly. HOWEVER it is CONSERVATIVE: it pulls AUC toward chance and thus *supports* the "fails to discrimin


**Data structure (real example):**

```
Real apt-cohort record (first line of metaphor_spike_apt_phase2_...jsonl): {"topic":"anger","metaphors":[{"vehicle":"fire","shared_features":[{"dimension":"sensorimotor","concept":"heat"},{"dimension":"sensorimotor","concept":"burning"},{"dimension":"behaviour","concept":"consuming"},...],"confidence":0.93},{"vehicle":"volcano",...},...],"_gloss":...}. Inapt record uses key "inapt_metaphors" with items {"vehicle":"passion","inapt_reason_type":...,"explanation":...}. The harness only consumes topic + vehicle strings (shared_features are ignored), resolves both to noun synset_ids via build_resolver, and emits per-pair rows: {"label":1,"reached":True/False,"rank":<int or 1e9>,"score":<float or -1e9>}. Verified noun-resolved cohort = 875 apt + 470 inapt = 1345 pairs over 174 topics (miss=52 topics unresolved).
```


**Pseudocode (faithful to implementation):**

```
load: resolve = build_resolver(con)  # noun-preferred, least-polysemous lemma->synset
  ids,C = [synset_id, L2-normed centroid] for synsets with pos=='n'   # 54431 nouns only (POS FILTER)
  cz[s] = (concreteness(s, default 3.0) - 1)/4                        # 0..1
pairs = []  # for (APT,label 1),(INAPT,label 0): t=resolve(topic); skip if t not a noun-centroid (miss++)
  for each vehicle m: v=resolve(m.vehicle); skip if v not a noun-centroid; pairs += (t_idx, v_idx, label)
group pairs by topic-index ti
for scheme in {smooth_only(c=0,k=0), +concr(c=0,k=2), +cross(c=2,k=0), +cross+concr(c=2,k=2)}:
  for ti, vlist in by_topic:
    front = beam_frontier(ti, depth=DEPTH, k=40, beam=BEAM, lam_cross=c, lam_concr=k):
        frontier = {ti: 0.0}
        repeat depth times:
            for each node r in frontier: nbr = top-40 cosine neighbours of r (dense C@C.T, self set -1)
                for j in nbr: step=cos(r,j); cross=1-cos(j,topic); score=cum[r]+step+lam_cross*cross
                    keep max score per j
            frontier = top-`beam` nodes by score
        endpoint score = path_score + lam_concr*cz[node] + lam_cross*(1-cos(node,topic))
    rank vehicles by frontier score
    per pair: reached = v in front; rank = rank_of.get(v, 1e9); score = front.get(v, -1e9)  # UNREACHED -> -1e9
  AUC = max(roc_auc(label, score), 1-roc_auc)   # over ALL 1345 pairs incl. ~90% tied at -1e9
  report apt/inapt reached%, median rank, recall@50/@200; compare apt recall@200 to HARDCODED "direct embedding 13%"
guided_traversal_wide.py: same beam_frontier, only scheme +cross+concr, depth{2,3} x beam{800,2000}, recall@200/@1000.
```


_Fidelity notes:_ Faithful. Simplifications: (1) the beam carries only a scalar cumulative score per node (a dict node->best_score), NOT full paths, so "median rank 1000000000" appears whenever <50% of a label's pairs are reached (median of mostly-1e9 ranks) — the result.txt shows median rank = 1e9 for every depth-3 beam-300 scheme. (2) AUC uses score (with -1e9 sentinel for unreached), NOT rank. (3) The "direct embedding recall@200=13%, median rank 2870" baseline is a HARDCODED print string carried from the separate H-B harness (hb_band_recall.py / C18) — it is NOT recomputed in this harness. (4) build_resolver does cheap suffix-strip morphology (s/es/ing/ed) and drops anything that doesn't resolve directly.


---

## LLM judge feasibility

**Harness:** /home/agent/projects/metaforge/docs/inbox/2026-06-03-context-free-edges/artifacts/judge_feasibility.py (read); judge_feasibility_rows.jsonl (read, 35 lines, the committed per-(sig,model) verdicts); judge_feasibility_result.txt (read, the interrupted stdout). Ground-truth source: /home/agent/projects/metaforge/.worktrees/next/data-pipeline/grading/judgements_provisional.jsonl. Re-ran the agreement/

**Verification:** numbers `PARTIAL`. Agreement and kappa are computed correctly (hand-rolled kappa == sklearn reference). BUT the probe is methodologically weak in ways the report only partly admits: (1) IN-SAMPLE — the judge grades the exact chains Julian graded; this is feasibility signal, not validation (the harness docstring says so). (2) TINY n=12. (3) SEVERE base-rate skew: 10/12 human-live, so only 2 human-dead chains (anchor->handhold, anchor->stone) exist; TN=2 is the entire negative class and the whole kappa rests on thos


**Data structure (real example):**

```
One row of judge_feasibility_rows.jsonl (the core input/output record), verbatim:
{"sig": "57f254d145f10b8863cce3fa9b6efb46943c23b298d17497601776635c12068e", "model": "sonnet", "topic": "anxiety", "vehicle": "whirlpool", "human": "live", "pred": "live"}
And the discriminating negative example (one of the only 2 human-dead chains, which carry the entire kappa signal):
{"sig": "228855e1faeafa6e5d3206f1923e8b58ab66777c0a71dbd090d6183429ed269a", "model": "haiku", "topic": "anchor", "vehicle": "handhold", "human": "dead", "pred": "dead"}
```


**Pseudocode (faithful to implementation):**

```
human = {}                       # latest-wins per chain_signature
for line in judgements_provisional.jsonl:        # live worktree
    r = json.loads(line)
    k, ts = r.chain_signature, r.ts
    if k not in human or ts >= human[k].ts: human[k] = r
human = {k: {topic, vehicle, (r.metaphor or r.label)}   # the v2 axis, falling back to v1 label
         for k,r in human.items() if (r.metaphor or r.label) in ("live","dead")}   # -> 21 verdicts, 15 live / 6 dead, topics anxiety/anchor/ambush
chains = {chain_signature: row for row in sonnet_chains_provisional_r1.jsonl}
items  = [(s,h,chains[s]) for s,h in human.items() if s in chains]    # 21 matched

done, rows = load(judge_feasibility_rows.jsonl)   # RESUMABLE: skip already-judged (sig,model)
for (s,h,ch) in items:
    path = " -> ".join(step.phrase for step in ch.chain)
    prompt = judge_prompt(h.topic, h.vehicle, path)   # "Is 'topic is (a) vehicle' LIVE or DEAD..." strict-JSON
    for m in ["haiku","sonnet","opus"]:
        if (s,m) in done: continue
        raw = claude_cli(prompt, model=m)             # <-- API; run TIMED OUT here (300s) at the 12th chain
        pred = parse_verdict(raw)                      # regex first {...}, .verdict
        append {sig,model,topic,vehicle,human,pred}

for m in models:                                  # scoring (API-free, what I re-ran)
    rs = [r for r in rows[m] if r.pred in ("live","dead")]
    agree = #(pred==human); TP,TN,FP,FN = confusion
    po = agree/n
    p_live = (TP+FP)/n ; h_live = nlive/n          # predicted-live rate, human-live rate
    pe = p_live*h_live + (1-p_live)*(1-h_live)      # Cohen's kappa expected-agreement
    kappa = (po-pe)/(1-pe)
    report agree, kappa, [TP TN FP FN]
```


_Fidelity notes:_ Faithful. Two simplifications to note: (1) the prompt also passes the chain's intermediate phrases as a "Proposed conceptual path", which I collapsed to `path` — exact text is in judge_prompt(). (2) The kappa is the standard 2x2 Cohen's marginal-product formula; I verified it equals sklearn.cohen_kappa_score to 3dp, so the hand-roll is correct, not a quirk. The only real-execution quirk is that the live API run TIMED OUT after 12 chains (the resume logic means a rerun would continue), so the committed rows are a partial run, not the full 21.

---

## Gloss-as-features (4th substrate)

**Harness:** `gloss_overlap_experiment.py` (API-free). **Verification:** AUC 0.537; apt share ≥1 gloss content word 4.6% vs inapt 11.8%.

**Data structure (real):** each synset has `definition` text (e.g. anger→ "(v) make angry"; fire→ "(n) the event of something burning…"). Per pair: tokenised content-word sets `T_topic`, `T_vehicle` (stopwords + len≤2 removed).

```
for (topic,vehicle,label) in apt∪inapt cohort:
    tt = content_tokens(topic_gloss)        # _gloss field, else synsets.definition
    vt = content_tokens(vehicle_definition)
    jaccard = |tt∩vt| / |tt∪vt| ;  shared = |tt∩vt|
AUC(jaccard, label) = 0.537 ; AUC(shared, label) = 0.536   # ≈ chance
frac apt sharing ≥1 = 4.6% ; inapt = 11.8%                 # inapt MORE (anti-correlated)
```

_Fidelity:_ exact. Vehicle gloss = `synsets.definition` of the resolved vehicle synset; topic gloss = the spike `_gloss` (falls back to definition). Resolver = the shared noun-preferred resolver.

---

## Signal-guided beam search — HUB-PENALTY variant (operator refinement)

**Harness:** `guided_traversal_hubpenalty.py` (API-free). **Verification:** no improvement — depth-2 apt recall@200 11.9%→10.9% as λ_hub 0→2; AUC 0.545→0.550; apt reach flat 13.9%.

**Idea:** down-weight a hop `prev→next` by the kNN **in-degree** of `next` (how many nodes have it as a top-K neighbour) — penalise routing through generic "god-node" hubs.

**Data structure (real):** kNN in-degree array over 54,431 noun synsets — `indeg.max()=407, mean=40.0, p99=161`; normalised `hubness_norm = (log1p(indeg)−min)/(max−min) ∈ [0,1]`.

```
indeg = kNN_indegree(C, k=40)                  # chunked argpartition over 54k×54k cosine
hpn   = normalise(log1p(indeg))                # 0..1
beam_hub(topic t, depth, λ_hub):
    frontier = {t: 0}
    repeat depth times:
        for node r in frontier, for j in topK_cosine(r, k=40):
            step  = cos(r,j) − λ_hub·hpn[j]     # HUB PENALTY on landing j
            cross = 1 − cos(j, t)               # cross-domain reward
            cand[j] = max(cand[j], frontier[r] + step + 2·cross)
        frontier = top-2000 of cand
    rank endpoints by frontier-score + 2·concreteness[node] + 2·cross
sweep depth{2,3} × λ_hub{0,0.5,1,2}: apt recall@200 ≤ 11.9% (< direct embedding 13%), AUC ≤ 0.550
```

_Fidelity:_ exact. The λ_hub=0 row reproduces the plain guided beam (depth-2 beam-2000: apt reach 13.9%, recall@200 11.9%; depth-3: 13.6%/7.0%), a consistency check.
