/** Mirrors Go thesaurus.RelatedWord */
export interface RelatedWord {
  word: string
  synset_id: string
}

/** Mirrors Go thesaurus.Relations */
export interface Relations {
  hypernyms: RelatedWord[]
  hyponyms: RelatedWord[]
  similar: RelatedWord[]
}

/** Mirrors Go thesaurus.Sense */
export interface Sense {
  synset_id: string
  pos: string
  definition: string
  synonyms: RelatedWord[]
  relations: Relations
}

/** Mirrors Go thesaurus.LookupResult */
export interface LookupResult {
  word: string
  senses: Sense[]
}
