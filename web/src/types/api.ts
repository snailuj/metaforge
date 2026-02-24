/** Mirrors Go thesaurus.RelatedWord */
export interface RelatedWord {
  word: string
  synset_id: string
  rarity?: string
}

/** Mirrors Go thesaurus.Relations */
export interface Relations {
  hypernyms: RelatedWord[]
  hyponyms: RelatedWord[]
  similar: RelatedWord[]
  antonyms: RelatedWord[]
}

/** Mirrors Go thesaurus.Sense */
export interface Sense {
  synset_id: string
  pos: string
  definition: string
  register?: string
  connotation?: string
  usage_example?: string
  synonyms: RelatedWord[]
  relations: Relations
  collocations?: RelatedWord[]
}

/** Mirrors Go thesaurus.LookupResult */
export interface LookupResult {
  word: string
  senses: Sense[]
  rarity?: string
}
