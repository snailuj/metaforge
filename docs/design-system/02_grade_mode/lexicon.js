/* ============================================================
   Metaforge UI Kit — fake lexicon
   A small, self-contained dataset so the prototype navigates
   like the real thesaurus. Mirrors the API's LookupResult shape:
   { word, rarity, senses: [{ pos, register, connotation, definition,
     usage_example, synonyms[], relations:{hypernyms,hyponyms,similar,
     antonyms}, collocations[] }] }
   Each related word carries a rarity so graph nodes colour correctly.
   ============================================================ */
(function () {
  // helper to tag a list of words with a rarity
  const W = (rarity, ...words) => words.map((word) => ({ word, rarity }));

  const LEXICON = {
    hungriness: {
      word: 'hungriness',
      rarity: 'unusual',
      senses: [
        {
          pos: 'noun',
          register: 'neutral',
          connotation: 'neutral',
          definition: 'strong desire for something (not food or drink)',
          usage_example: 'a hungriness for meaning that no book could satisfy',
          synonyms: [...W('common', 'hunger'), ...W('common', 'thirst'), ...W('unusual', 'thirstiness')],
          relations: {
            hypernyms: [...W('common', 'desire')],
            hyponyms: [...W('unusual', 'hankering'), ...W('rare', 'pining'), ...W('rare', 'wishfulness'), ...W('rare', 'wistfulness')],
            similar: [...W('unusual', 'yearning'), ...W('common', 'longing'), ...W('rare', 'edacity')],
            antonyms: [...W('common', 'satiety')],
          },
          collocations: [...W('common', 'affection'), ...W('unusual', 'appetence'), ...W('common', 'appetite'), ...W('common', 'cognition'), ...W('common', 'emotion'), ...W('common', 'experience')],
        },
        {
          pos: 'noun',
          register: 'neutral',
          connotation: 'negative',
          definition: 'prolonged unfulfilled desire or need',
          usage_example: '',
          synonyms: [...W('common', 'longing'), ...W('unusual', 'yearning')],
          relations: {
            hypernyms: [...W('common', 'desire')],
            hyponyms: [...W('unusual', 'hankering'), ...W('rare', 'pining'), ...W('rare', 'discontent')],
            similar: [...W('rare', 'nostalgia')],
            antonyms: [],
          },
          collocations: [...W('common', 'feel'), ...W('common', 'express'), ...W('common', 'fill')],
        },
      ],
    },

    melancholy: {
      word: 'melancholy',
      rarity: 'unusual',
      senses: [
        {
          pos: 'noun',
          register: 'poetic',
          connotation: 'negative',
          definition: 'a pensive, lingering sadness with no obvious cause',
          usage_example: 'a melancholy autumn evening',
          synonyms: [...W('common', 'sadness'), ...W('common', 'gloom'), ...W('unusual', 'sorrow'), ...W('rare', 'dolour')],
          relations: {
            hypernyms: [...W('common', 'emotion'), ...W('unusual', 'sadness')],
            hyponyms: [...W('rare', 'wistfulness'), ...W('rare', 'pensiveness')],
            similar: [...W('unusual', 'wistful'), ...W('common', 'pensive'), ...W('rare', 'saturnine')],
            antonyms: [...W('common', 'cheer'), ...W('common', 'joy')],
          },
          collocations: [...W('common', 'deep'), ...W('common', 'quiet'), ...W('unusual', 'sweet')],
        },
      ],
    },

    desire: {
      word: 'desire',
      rarity: 'common',
      senses: [
        {
          pos: 'noun',
          register: 'neutral',
          connotation: 'neutral',
          definition: 'a strong feeling of wanting to have or do something',
          usage_example: 'a burning desire to be understood',
          synonyms: [...W('common', 'wish'), ...W('common', 'longing'), ...W('unusual', 'craving'), ...W('unusual', 'yearning')],
          relations: {
            hypernyms: [...W('common', 'feeling')],
            hyponyms: [...W('unusual', 'hungriness'), ...W('rare', 'edacity'), ...W('unusual', 'hankering')],
            similar: [...W('common', 'hope'), ...W('unusual', 'appetite')],
            antonyms: [...W('common', 'aversion')],
          },
          collocations: [...W('common', 'fulfil'), ...W('common', 'express'), ...W('common', 'strong')],
        },
      ],
    },

    longing: {
      word: 'longing',
      rarity: 'common',
      senses: [
        {
          pos: 'noun',
          register: 'poetic',
          connotation: 'negative',
          definition: 'a yearning desire for something out of reach',
          usage_example: 'a quiet longing for somewhere she had never been',
          synonyms: [...W('unusual', 'yearning'), ...W('unusual', 'hungriness'), ...W('common', 'hunger')],
          relations: {
            hypernyms: [...W('common', 'desire')],
            hyponyms: [...W('rare', 'pining'), ...W('rare', 'nostalgia')],
            similar: [...W('unusual', 'wistfulness'), ...W('unusual', 'melancholy')],
            antonyms: [...W('common', 'contentment')],
          },
          collocations: [...W('common', 'deep'), ...W('common', 'wistful'), ...W('unusual', 'unspoken')],
        },
      ],
    },

    hunger: {
      word: 'hunger',
      rarity: 'common',
      senses: [
        {
          pos: 'noun',
          register: 'neutral',
          connotation: 'neutral',
          definition: 'a compelling need or desire for something',
          usage_example: 'a hunger for recognition',
          synonyms: [...W('unusual', 'hungriness'), ...W('common', 'longing'), ...W('common', 'thirst')],
          relations: {
            hypernyms: [...W('common', 'desire')],
            hyponyms: [...W('unusual', 'hankering'), ...W('rare', 'edacity')],
            similar: [...W('unusual', 'yearning'), ...W('unusual', 'appetence')],
            antonyms: [...W('common', 'satiety')],
          },
          collocations: [...W('common', 'feel'), ...W('common', 'satisfy'), ...W('common', 'deep')],
        },
      ],
    },
  };

  // Words that appear as related but have no full entry — generate a minimal
  // stub so navigation never dead-ends.
  const RARITY_BY_WORD = {};
  Object.values(LEXICON).forEach((e) => {
    RARITY_BY_WORD[e.word] = e.rarity;
    e.senses.forEach((s) => {
      const all = [...s.synonyms, ...s.relations.hypernyms, ...s.relations.hyponyms,
        ...s.relations.similar, ...s.relations.antonyms, ...s.collocations];
      all.forEach((rw) => { if (!(rw.word in RARITY_BY_WORD)) RARITY_BY_WORD[rw.word] = rw.rarity; });
    });
  });

  function stub(word) {
    const rarity = RARITY_BY_WORD[word] || 'unusual';
    return {
      word, rarity,
      senses: [{
        pos: 'noun', register: 'neutral', connotation: 'neutral',
        definition: 'a related sense in the lexicon — full entry not enriched yet',
        usage_example: '',
        synonyms: [], relations: { hypernyms: [], hyponyms: [], similar: [], antonyms: [] },
        collocations: [],
      }],
    };
  }

  // Autocomplete list (prefix match, sorted)
  const ALL_WORDS = Object.keys(RARITY_BY_WORD).sort();

  window.MF_LEXICON = {
    lookup(word) {
      const w = (word || '').trim().toLowerCase();
      return LEXICON[w] || (RARITY_BY_WORD[w] ? stub(w) : null);
    },
    suggest(prefix) {
      const p = (prefix || '').trim().toLowerCase();
      if (p.length < 1) return [];
      return ALL_WORDS.filter((w) => w.startsWith(p)).slice(0, 6).map((w) => {
        const e = LEXICON[w];
        return {
          word: w,
          rarity: RARITY_BY_WORD[w],
          sense_count: e ? e.senses.length : 1,
          definition: e ? e.senses[0].definition : 'a related word in the lexicon',
        };
      });
    },
    rarityOf(word) { return RARITY_BY_WORD[word] || 'unusual'; },
    examples: ['hungriness', 'melancholy', 'desire', 'longing', 'hunger'],
  };
})();
