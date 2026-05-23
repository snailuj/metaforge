// unionCandidates merges two cascade candidate slices by SynsetID and
// stamps each row's Source tag. Cluster wins on conflict — the cluster
// row's full payload (salience_sum, contrast_count, shared_props) is
// preserved; only the Source tag changes to SourceBoth when the same
// synset also appears in the embedding slice. Order is deterministic
// in iteration over `cluster` first, then any embedding-only rows
// in their original order.
package handler

import (
	"log/slog"

	"github.com/snailuj/metaforge/internal/db"
	"github.com/snailuj/metaforge/internal/forge"
)

func unionCandidates(cluster, embedding []db.CascadeCandidate) []db.CascadeCandidate {
	out := make([]db.CascadeCandidate, 0, len(cluster)+len(embedding))
	clusterIDs := make(map[string]struct{}, len(cluster))
	embeddingIDs := make(map[string]struct{}, len(embedding))
	for _, e := range embedding {
		embeddingIDs[e.SynsetID] = struct{}{}
	}
	for _, c := range cluster {
		clusterIDs[c.SynsetID] = struct{}{}
		// Cluster row already carries Source=SourceCluster from
		// NewCascadeCandidate. If the same synset also appears in the
		// embedding hit set, upgrade the tag to SourceBoth so the
		// diagnostic captures the dual-path signal.
		if _, dual := embeddingIDs[c.SynsetID]; dual {
			c.Source = forge.SourceBoth
			// D5 observability lift: when the same vehicle synset is
			// surfaced via both paths, the cluster row wins and the
			// embedding row's SourceSynsetID (a potentially-different
			// primary-sense pick) is silently discarded. Log at Debug
			// so operators chasing a sense-mismatch can opt in. M05
			// type-aligned scoring is the proper resolution.
			slog.Debug("cascade union: cluster wins on dual-path conflict",
				"synset_id", c.SynsetID,
				"cluster_source_synset", c.SourceSynsetID)
		}
		out = append(out, c)
	}
	for _, e := range embedding {
		if _, clash := clusterIDs[e.SynsetID]; clash {
			continue // cluster row already represents this synset
		}
		// Embedding row already carries Source=SourceEmbedding from
		// NewCascadeCandidate.
		out = append(out, e)
	}
	return out
}
