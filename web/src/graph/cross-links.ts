import type { LookupResult, RelatedWord } from '@/types/api'
import type { GraphLink } from './types'

/**
 * Find the node ID for a related word in the graph.
 * Checks disambiguated form (word__synsetId) first, then plain word.
 */
function resolveNodeId(
  word: string,
  synsetId: string,
  nodeIds: Set<string>,
): string | undefined {
  const disambiguated = `${word}__${synsetId}`
  if (nodeIds.has(disambiguated)) return disambiguated
  if (nodeIds.has(word)) return word
  return undefined
}

/**
 * Build a canonical key for a link pair so duplicates can be detected.
 * Always orders alphabetically so A→B and B→A produce the same key.
 */
function linkKey(a: string, b: string): string {
  return a < b ? `${a}\0${b}` : `${b}\0${a}`
}

/**
 * Compute cross-links between first-order nodes that share a synset.
 *
 * Two first-order nodes sharing a synset should be linked to each other,
 * turning the star topology into a richer mesh. The central word is excluded
 * since it already has direct links to all first-order nodes.
 */
export function computeCrossLinks(
  result: LookupResult,
  nodeIds: Set<string>,
): GraphLink[] {
  const centralWord = result.word
  const seen = new Set<string>()
  const links: GraphLink[] = []

  // Collect all related words grouped by synset ID.
  // Synonyms within a sense share the sense's synset_id.
  // Relations (hypernyms, hyponyms, similar) use their own synset_id.
  const synsetMembers = new Map<string, Set<string>>()

  function addToSynset(synsetId: string, rw: RelatedWord): void {
    // Skip the central word — it already has direct links
    if (rw.word === centralWord) return

    const nodeId = resolveNodeId(rw.word, synsetId, nodeIds)
    if (!nodeId) return

    let members = synsetMembers.get(synsetId)
    if (!members) {
      members = new Set()
      synsetMembers.set(synsetId, members)
    }
    members.add(nodeId)
  }

  for (const sense of result.senses) {
    // Synonyms share the sense's synset_id
    for (const syn of sense.synonyms) {
      addToSynset(sense.synset_id, syn)
    }

    // Relations use their own synset_id
    for (const hyper of sense.relations.hypernyms) {
      addToSynset(hyper.synset_id, hyper)
    }
    for (const hypo of sense.relations.hyponyms) {
      addToSynset(hypo.synset_id, hypo)
    }
    for (const sim of sense.relations.similar) {
      addToSynset(sim.synset_id, sim)
    }
  }

  // For each synset group with 2+ members, create pairwise cross-links
  for (const members of synsetMembers.values()) {
    const ids = [...members]
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const key = linkKey(ids[i], ids[j])
        if (ids[i] === ids[j] || seen.has(key)) continue
        seen.add(key)
        links.push({
          source: ids[i],
          target: ids[j],
          relationType: 'synonym',
          order: 1,
        })
      }
    }
  }

  return links
}
