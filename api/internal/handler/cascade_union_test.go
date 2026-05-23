package handler

import (
	"reflect"
	"sort"
	"testing"

	"github.com/snailuj/metaforge/internal/db"
	"github.com/snailuj/metaforge/internal/forge"
)

func mkCand(id string, src forge.CandidateSource, sal float64) db.CascadeCandidate {
	return db.CascadeCandidate{
		SynsetID:    id,
		Word:        id + "-word",
		SalienceSum: sal,
		Source:      src,
	}
}

func TestUnionCandidates_EmbeddingOnlyPassesThrough(t *testing.T) {
	cluster := []db.CascadeCandidate(nil)
	emb := []db.CascadeCandidate{mkCand("E1", forge.SourceEmbedding, 0)}
	out := unionCandidates(cluster, emb)
	if len(out) != 1 || out[0].Source != forge.SourceEmbedding {
		t.Fatalf("embedding-only: want 1 SourceEmbedding row, got %+v", out)
	}
}

func TestUnionCandidates_ClusterOnlyPassesThrough(t *testing.T) {
	cluster := []db.CascadeCandidate{mkCand("C1", forge.SourceCluster, 3.0)}
	out := unionCandidates(cluster, nil)
	if len(out) != 1 || out[0].Source != forge.SourceCluster {
		t.Fatalf("cluster-only: want 1 SourceCluster row, got %+v", out)
	}
}

func TestUnionCandidates_OverlapWinsClusterAndTagsBoth(t *testing.T) {
	cluster := []db.CascadeCandidate{mkCand("X1", forge.SourceCluster, 5.5)}
	emb := []db.CascadeCandidate{mkCand("X1", forge.SourceEmbedding, 0)}
	out := unionCandidates(cluster, emb)
	if len(out) != 1 {
		t.Fatalf("overlap: want 1 row, got %d", len(out))
	}
	if out[0].Source != forge.SourceBoth {
		t.Errorf("overlap row Source: want %q, got %q", forge.SourceBoth, out[0].Source)
	}
	if out[0].SalienceSum != 5.5 {
		t.Errorf("overlap row must preserve cluster fields (SalienceSum=5.5), got %v", out[0].SalienceSum)
	}
}

func TestUnionCandidates_DisjointReturnsBothTaggedCorrectly(t *testing.T) {
	cluster := []db.CascadeCandidate{mkCand("C1", forge.SourceCluster, 4.0)}
	emb := []db.CascadeCandidate{mkCand("E1", forge.SourceEmbedding, 0)}
	out := unionCandidates(cluster, emb)
	sort.Slice(out, func(i, j int) bool { return out[i].SynsetID < out[j].SynsetID })
	want := []db.CascadeCandidate{
		mkCand("C1", forge.SourceCluster, 4.0),
		mkCand("E1", forge.SourceEmbedding, 0),
	}
	if !reflect.DeepEqual(out, want) {
		t.Errorf("disjoint mismatch:\n got %+v\nwant %+v", out, want)
	}
}

func TestUnionCandidates_BothNilReturnsEmptyNotNil(t *testing.T) {
	out := unionCandidates(nil, nil)
	if out == nil {
		t.Error("want non-nil empty slice, got nil")
	}
	if len(out) != 0 {
		t.Errorf("want empty, got %d entries", len(out))
	}
}
