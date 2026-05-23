// unionCandidates merges two cascade candidate slices by SynsetID and
// stamps each row's Source tag. Cluster wins on conflict — the cluster
// row's full payload (salience_sum, contrast_count, shared_props) is
// preserved; only the Source tag changes to SourceBoth when the same
// synset also appears in the embedding slice. Order is deterministic
// in iteration over `cluster` first, then any embedding-only rows
// in their original order.
package handler

import (
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
		c.Source = forge.SourceCluster
		if _, dual := embeddingIDs[c.SynsetID]; dual {
			c.Source = forge.SourceBoth
		}
		out = append(out, c)
	}
	for _, e := range embedding {
		if _, clash := clusterIDs[e.SynsetID]; clash {
			continue // cluster row already represents this synset
		}
		e.Source = forge.SourceEmbedding
		out = append(out, e)
	}
	return out
}
