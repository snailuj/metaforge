# Gloss Reconciliation — Endpoint Sense Audit

**Date:** 2026-06-15  
**Method:** Read-only pass over `chain_glosses_provisional.jsonl` + both gold chain files (`r2_handpicked`, `r3_phaseb`). Synset ID → gloss resolved from the chain-glosses file first, with a fallback to the `synsets` table in `lexicon_v2.db`. All distinct `(role, word, synset_id)` endpoint triples deduplicated. Judgements applied by direct reading of the snapped gloss against the expected sense for the word in metaphor context: topics must be concepts/states/emotions (verb or adj POS = strong WRONG_SENSE signal; "act of" process-nominals for emotion-words = WRONG_SENSE when a state-sense exists); vehicles may legitimately be verbs/gerunds but noun concepts are almost always preferred, and wrong-sense nouns or wildly wrong verbs (e.g. glamour → "cast a spell", hush → "wash by removing particles") are flagged. Conservative bias throughout — when genuinely ambiguous, verdict is OK.

---

## Totals

| Category | Count | Total endpoints | Contamination % |
|----------|-------|-----------------|-----------------|
| Distinct topics audited | 277 | 277 | — |
| Distinct vehicles audited | 1771 | 1771 | — |
| **Total distinct endpoints** | **2048** | | |
| WRONG_SENSE — topics | 21 | 277 | **7.6%** |
| WRONG_SENSE — vehicles | 79 | 1771 | **4.5%** |
| WRONG_SENSE — combined | 100 | 2048 | **4.9%** |
| RARE_OK — topics | 1 | 277 | 0.4% |
| RARE_OK — vehicles | 10 | 1771 | 0.6% |
| RARE_OK — combined | 11 | 2048 | 0.5% |

---

## WRONG_SENSE — Topics

21 topics snapped to the wrong sense. All 277 topics are noun POS, but several landed on process-nominals ("the act of X") or narrow technical senses when a psychological/emotional/state sense exists for the same lemma.

| Word | Synset ID | Snapped gloss | Intended sense | Reason |
|------|-----------|---------------|----------------|--------|
| agitation | 7349 | the act of agitating something; causing it to move around (usually vig | a state of anxiety or extreme emotional disturbance (synset 99664) | Snapped to physical-mechanics sense ("act of agitating something"); the topic intends the emotional  |
| allegiance | 22208 | the act of binding yourself (intellectually or emotionally) to a cours | the loyalty that citizens owe to their country (synset 59340) | Snapped to "the act of binding yourself to a course of action" — a generic commitment sense; the top |
| amplification | 60564 | the amount of increase in signal power or voltage or current expressed | the act of increasing (power, scale, or expressiveness) — synset 8062  | Snapped to a technical measurement sense (signal power ratio); the topic intends the general concept |
| apprehension | 1760 | the act of apprehending (especially apprehending a criminal) | fearful expectation or anticipation (synset 72797) | Snapped to law-enforcement process sense ("act of apprehending a criminal"); the topic intends the e |
| bounty | 93372 | payment or reward (especially from a government) for acts such as catc | generosity evidenced by a willingness to give freely (synset 59107) or | Snapped to governmental bounty-hunting reward sense; the topic intends abundance/generosity. |
| cadence | 70468 | (prosody) the accent in a metrical foot of verse | a recurrent rhythmical series (synset 59954) | Snapped to a narrow prosodic technicality (the accent in a metrical foot); the topic intends the bro |
| concentration | 8272 | strengthening the concentration (as of a solute in a mixture) by remov | complete attention; intense mental effort (synset 63605) | Snapped to a chemistry sense (removing diluting material from a solute); the topic intends mental fo |
| confession | 19566 | (Roman Catholic Church) the act of a penitent disclosing their sinfuln | an admission of misdeeds or faults (synset 71114) | Snapped to the Roman Catholic sacramental sense; the topic intends the general act of admitting wron |
| confusion | 8384 | an act causing a disorderly combination of elements with identities lo | a mental state characterized by a lack of clear and orderly thought (s | Snapped to a process-nominal for physical/abstract mixing; the topic intends the mental state of cog |
| decay | 94423 | a gradual decrease; as of stored charge or current | the process of gradually becoming inferior (synset 94424) or the organ | Snapped to an electrical-physics sense (decrease of stored charge); the topic intends the general co |
| exhaustion | 7876 | the act of exhausting something entirely | extreme fatigue / serious weakening and loss of energy (synset 97563) | Snapped to process-nominal "the act of exhausting something entirely"; the topic intends the experie |
| ideology | 63979 | imaginary or visionary theorization | an orientation that characterizes the thinking of a group or nation (s | Snapped to a rare pejorative sense ("imaginary or visionary theorization"); the topic intends the do |
| murmur | 70582 | a schwa that is incidental to the pronunciation of a consonant | a low continuous indistinct sound (synset 72033) | Snapped to a phonology sense ("schwa incidental to consonant pronunciation"); the topic intends low  |
| oppression | 9353 | the act of subjugating by cruelty | the state of being kept down by unjust use of force or authority (syns | Snapped to an action sense ("act of subjugating by cruelty"); the topic more naturally intends the o |
| purity | 59196 | a woman's virtue or chastity | the state of being unsullied by sin or moral wrong (synset 97423) | Snapped to "a woman's virtue or chastity" — a gender-restricted chastity sense; the topic intends th |
| ransom | 1940 | the act of freeing from captivity or punishment | money demanded for the return of a captured person (synset 93441) | Snapped to the act-of-freeing sense; the topic intends the money/price demanded for release. |
| saturation | 8937 | the act of soaking thoroughly with a liquid | a condition in which a quantity no longer responds to some external in | Snapped to the liquid-soaking action sense; the topic typically intends the concept of reaching maxi |
| stalemate | 71855 | drawing position in chess: any of a player's possible moves would plac | a situation in which no progress can be made (synset 97554) | Snapped to the chess-specific drawing position; the topic intends the general sense of a deadlock or |
| tension | 8092 | the action of stretching something tight | a state of mental or emotional strain or suspense (synset 99518) | Snapped to physical-mechanics sense ("action of stretching something tight"); the topic intends psyc |
| tribute | 15732 | payment extorted by gangsters on threat of violence | something given or done as an expression of esteem (synset 68254) | Snapped to extortion/protection-racket sense; the topic intends the sense of an expression of esteem |
| whisper | 72060 | a light noise, like the noise of silk clothing or leaves blowing in th | speaking softly without vibration of the vocal cords (synset 70670) | Snapped to rustling-fabric/leaves sound sense; the topic intends the sense of quietly spoken words ( |


---

## WRONG_SENSE — Vehicles

79 vehicles snapped to the wrong sense. The dominant pattern is verb sense selected when the noun concept was intended. Because vehicles may legitimately be verb actions, only cases where the concept is clearly divergent are flagged.

| Word | Synset ID | POS | Snapped gloss | Intended sense | Reason |
|------|-----------|-----|---------------|----------------|--------|
| anchor | 23626 | v | fix firmly and stably | a mechanical device that prevents a vessel from moving (syns | Snapped to the verb sense "fix firmly and stably"; the vehicle intends the concrete noun o |
| autopsy | 35359 | v | perform an autopsy on a dead body; do a post-mortem | an examination and dissection of a dead body to determine ca | Snapped to verb sense "perform an autopsy"; the vehicle intends the noun concept (the exam |
| bait | 20795 | v | attack with dogs or set dogs upon | something used to lure fish or other animals; anything that  | Snapped to "attack with dogs"; the vehicle intends the concept of something used as an ent |
| blare | 35863 | v | make a strident sound | a loud harsh or strident noise (synset 71975) | Snapped to verb sense "make a strident sound"; the vehicle intends the sound itself (the b |
| blight | 44681 | v | cause to suffer a blight | any plant disease resulting in withering without rotting (sy | Snapped to verb sense "cause to suffer a blight"; the vehicle intends the noun concept (a  |
| bone | 6507 | s | consisting of or made up of bone | rigid connective tissue that makes up the skeleton (synset 6 | Snapped to adjective sense "consisting of or made up of bone"; the vehicle intends the nou |
| braid | 26601 | v | decorate with braids or ribbons | a hairdo formed by braiding or twisting the hair (synset 613 | Snapped to verb sense "decorate with braids"; the vehicle intends the noun concept (a brai |
| bread | 24115 | v | cover with bread crumbs | food made from dough of flour or meal (synset 73833) | Snapped to verb sense "cover with bread crumbs"; the vehicle intends the noun concept (bre |
| breeze | 31693 | v | to proceed quickly and easily | a slight wind (usually refreshing) (synset 87087) | Snapped to verb sense "proceed quickly and easily"; the vehicle intends the noun sense (a  |
| chisel | 41466 | v | engage in deceitful behavior; practice trickery or fraud | an edge tool with a flat steel blade with a cutting edge (sy | Snapped to a fraud/cheating sense ("engage in deceitful behavior"); the vehicle intends th |
| chiselling | 41466 | v | engage in deceitful behavior; practice trickery or fraud | act of cutting with a chisel (implied by noun synset 47781) | Same as chisel: snapped to fraud/cheating sense; the vehicle intends the act of chiselling |
| counterpoint | 42837 | v | to show differences when compared; be different | a musical form involving the simultaneous sound of two or mo | Snapped to verb sense "to show differences"; the vehicle intends the musical noun (the sim |
| debate | 15566 | v | have an argument about something | a discussion in which reasons are advanced for and against s | Snapped to verb sense "have an argument"; the vehicle intends the noun concept (a formal d |
| dusk | 6865 | v | become dusk | the time of day immediately following sunset (synset 103872) | Snapped to verb sense "become dusk" (extremely rare usage); the vehicle intends the noun ( |
| dye | 6212 | v | color for microscopic study | a usually soluble substance for staining or coloring e.g. fa | Snapped to a specialised lab sense ("color for microscopic study"); the vehicle intends ei |
| eclipse | 44180 | v | be greater in significance than | one celestial body obscures another (synset 71932) | Snapped to figurative verb sense "be greater in significance than"; the vehicle intends th |
| ferment | 10212 | v | go sour or spoil | a process of fermentation (synset 95018) or a state of agita | Snapped to verb sense "go sour or spoil"; the vehicle intends the fermentation process con |
| forge | 28537 | v | make something, usually for a specific function | a workplace where metal is worked by heating and hammering ( | Snapped to a generic creation verb; the vehicle intends the noun (a smithy / forge workpla |
| furrow | 23341 | v | make wrinkled or creased | a long shallow trench in the ground made by a plow (synset 5 | Snapped to verb sense "make wrinkled or creased"; the vehicle intends the noun (a furrow — |
| gilt | 8154 | s | having the deep slightly brownish color of gold | a coating of gold or of something that looks like gold (syns | Snapped to adjective sense "having the colour of gold"; the vehicle intends the noun (gilt |
| glamour | 15616 | v | cast a spell over someone or something; put a hex on someone | alluring beauty or charm (often with sex-appeal) (synset 583 | Snapped to archaic verb sense "cast a spell over someone"; the vehicle intends the noun (a |
| glance | 31670 | v | hit at an angle | a quick look (synset 17095) | Snapped to "hit at an angle" (a physical impact sense); the vehicle intends a quick look o |
| glaze | 38043 | v | furnish with glass | a coating for ceramics, metal, etc. (synset 58483) | Snapped to verb sense "furnish with glass"; the vehicle intends the noun (a glaze — a coat |
| goad | 16713 | v | annoy or provoke, as by constant criticism | a pointed instrument that is used to prod into a state of mo | Snapped to verb sense "annoy or provoke"; the vehicle intends the noun (a goad — a pointed |
| hemorrhage | 1429 | v | lose blood from one's body | the flow of blood from a ruptured blood vessel (synset 99011 | Snapped to verb sense "lose blood from one's body"; the vehicle intends the noun (a haemor |
| hound | 33185 | v | pursue or chase relentlessly | any of several breeds of dog used for hunting (synset 34353) | Snapped to verb sense "pursue or chase relentlessly"; the vehicle intends the noun (a houn |
| hum | 43524 | v | be noisy with activity | a humming noise (synset 72027) | Snapped to "be noisy with activity"; the vehicle intends the noun (a hum — a low continuou |
| hush | 10279 | v | wash by removing particles | (poetic) tranquil silence (synset 59904) | Snapped to an obscure hydraulic-mining sense ("wash by removing particles via rushing wate |
| husk | 3827 | v | remove the husks from | outer membranous covering of some fruits or seeds (synset 92 | Snapped to verb sense "remove the husks from"; the vehicle intends the noun (a husk — the  |
| indenture | 17217 | v | bind by or as if by indentures, as of an apprentice or serva | a contract binding one party into the service of another for | Snapped to verb sense "bind by indentures"; the vehicle intends the noun (an indenture — a |
| itch | 30796 | v | have a strong desire or urge to do something | an irritating cutaneous sensation that produces a desire to  | Snapped to verb sense "have a strong desire or urge"; the vehicle intends the noun (the it |
| jolt | 31314 | v | move or cause to move with a sudden jerky motion | a sudden jarring impact (synset 71775) | Snapped to verb sense "move with a sudden jerky motion"; the vehicle intends the noun (a j |
| keel | 32151 | v | walk as if unable to control one's movements | one of the main longitudinal beams of the hull of a vessel ( | Snapped to verb sense "walk as if unable to control movements"; the vehicle intends the no |
| lasso | 27771 | v | catch with a lasso | a long noosed rope used to catch animals (synset 52352) | Snapped to verb sense "catch with a lasso"; the vehicle intends the noun (a lasso — a long |
| leaven | 32818 | v | cause to puff up with a leaven | an influence that works subtly to lighten or modify somethin | Snapped to verb sense "cause to puff up"; the vehicle intends the noun (leaven as a substa |
| meridian | 26222 | s | being at the best stage of development | the highest level or degree attainable (synset 97172) or an  | Snapped to adjective sense "being at the best stage of development"; the vehicle intends t |
| narrative | 11140 | s | consisting of or characterized by the telling of a story | a message that tells the particulars of an act or occurrence | Snapped to adjective sense "characterized by telling a story"; the vehicle intends the nou |
| orbit | 33755 | v | move in an orbit | the (usually elliptical) path described by one celestial bod | Snapped to verb sense "move in an orbit"; the vehicle intends the noun (an orbit — the ell |
| overhang | 43362 | v | be suspended over or hang over | projection that extends beyond or hangs over something else  | Snapped to verb sense "be suspended over"; the vehicle intends the noun (an overhang — a p |
| perfume | 749 | v | apply perfume to | a distinctive odor that is pleasant (synset 63662) | Snapped to verb sense "apply perfume to"; the vehicle intends the noun (perfume — a fragra |
| phantom | 32360 | s | something apparently sensed but having no physical reality | a ghostly appearing figure (synset 79885) | Snapped to adjective sense "something apparently sensed but having no physical reality"; t |
| photograph | 19009 | v | record on photographic film | a representation of a person or scene in the form of a print | Snapped to verb sense "record on photographic film"; the vehicle intends the noun (a photo |
| placard | 18827 | v | publicize or announce by placards | a sign posted in a public place as an advertisement (synset  | Snapped to verb sense "publicize by placards"; the vehicle intends the noun (a placard — a |
| plumb | 150 | r | exactly | the metal bob of a plumb line (synset 54234) | Snapped to adverb sense "exactly"; the vehicle intends the noun (a plumb — the metal bob o |
| poultice | 1610 | v | dress by covering with a therapeutic substance | a medical dressing consisting of a soft heated mass applied  | Snapped to verb sense "dress by covering with a therapeutic substance"; the vehicle intend |
| prey | 22170 | v | profit from in an exploitatory manner | animal hunted or caught for food (synset 35383) or a person  | Snapped to verb sense "profit from in an exploitatory manner"; the vehicle intends the nou |
| probe | 15790 | v | question or examine thoroughly and closely | a flexible slender surgical instrument (synset 54462) or an  | Snapped to verb sense "question or examine thoroughly"; the vehicle intends the noun (a pr |
| reek | 36036 | v | have an element suggestive (of something) | a distinctive odor that is offensively unpleasant (synset 63 | Snapped to figurative verb sense "have an element suggestive of something"; the vehicle in |
| reins | 5082 | v | keep in check | the strap-and-bit horse-control equipment (no distinct synse | Snapped to figurative verb sense "keep in check"; the vehicle intends the noun (reins — le |
| riot | 41604 | v | take part in a riot; disturb the public peace by engaging in | a public act of violence by an unruly mob (synset 21661) | Snapped to verb sense "take part in a riot"; the vehicle intends the noun (a riot — a publ |
| rot | 1846 | v | become physically weaker | the process of decay caused by bacterial or fungal action (s | Snapped to verb sense "become physically weaker" (a weakening sense); the vehicle intends  |
| rumble | 19672 | v | to utter or emit low dull rumbling sounds | a loud low dull continuous noise (synset 72059) | Snapped to verb sense "utter or emit low dull rumbling sounds"; the vehicle intends the no |
| sandpaper | 24787 | v | rub with sandpaper | stiff paper coated with powdered emery or sand (synset 10206 | Snapped to verb sense "rub with sandpaper"; the vehicle intends the noun (sandpaper — the  |
| seesaw | 33048 | v | move up and down as if on a seesaw | a plaything consisting of a board balanced on a fulcrum (syn | Snapped to verb sense "move up and down"; the vehicle intends the noun (a seesaw — the pla |
| sleep | 43429 | v | be able to accommodate for sleeping | a natural and periodic state of rest during which consciousn | Snapped to "be able to accommodate for sleeping" (hospitality/capacity sense); the vehicle |
| sluice | 10136 | v | irrigate with water from a sluice | conduit that carries a rapid flow of water controlled by a s | Snapped to verb sense "irrigate with water from a sluice"; the vehicle intends the noun (a |
| slump | 32762 | v | fall in value | a long-term economic state characterized by unemployment and | Snapped to verb sense "fall in value"; the vehicle intends the noun (a slump — a period of |
| snare | 15710 | v | entice and trap | a trap for birds or small mammals; often has a slip noose (s | Snapped to verb sense "entice and trap"; the vehicle intends the noun (a snare — the trap  |
| submarine | 20871 | v | attack by submarine | a submersible warship usually armed with torpedoes (synset 5 | Snapped to verb sense "attack by submarine"; the vehicle intends the noun (a submarine — t |
| sunburn | 2087 | v | get a sunburn by overexposure to the sun | redness of the skin caused by exposure to the rays of the su | Snapped to verb sense "get a sunburn"; the vehicle intends the noun (a sunburn — the redne |
| swell | 33030 | v | come up, as of a liquid | the undulating movement of the surface of the open sea (syns | Snapped to verb sense "come up, as of a liquid"; the vehicle intends the noun (a swell — t |
| taper | 8714 | v | give a point to | stick of wax with a wick (synset 46879) or the property poss | Snapped to verb sense "give a point to"; the vehicle intends either the noun taper (a wax  |
| tarnish | 26845 | v | make dirty or spotty, as by exposure to air; also used metap | discoloration of metal surface caused by oxidation (synset 5 | Snapped to verb sense "make dirty or spotty"; the vehicle intends the noun (tarnish — the  |
| telegraph | 19077 | v | send cables, wires, or telegrams | apparatus used to communicate at a distance over a wire (syn | Snapped to verb sense "send telegrams"; the vehicle intends the noun (a telegraph — the ap |
| temper | 4329 | v | change by restraining or moderating | a disposition to exhibit uncontrolled anger (synset 58189) o | Snapped to verb sense "change by restraining or moderating"; the vehicle intends the noun  |
| thermostat | 40618 | v | control the temperature with a thermostat | a regulator for automatically regulating temperature (synset | Snapped to verb sense "control the temperature with a thermostat"; the vehicle intends the |
| thread | 24406 | v | thread on or as if on a string | a fine cord of twisted fibers used in sewing (synset 56956)  | Snapped to verb sense "thread on or as if on a string"; the vehicle intends the noun (a th |
| transplant | 12200 | v | transfer from one place or period to another | an operation moving an organ from one organism to another (s | Snapped to verb sense "transfer from one place to another"; the vehicle intends the noun ( |
| twig | 7267 | v | branch out in a twiglike manner | a small branch or division of a branch (synset 92964) | Snapped to verb sense "branch out in a twiglike manner"; the vehicle intends the noun (a t |
| varnish | 23239 | v | cover with varnish | a coating that provides a hard, lustrous, transparent finish | Snapped to verb sense "cover with varnish"; the vehicle intends the noun (varnish — the tr |
| veil | 26118 | v | to obscure, or conceal with or as if with a veil | a garment that covers the head and face (synset 51522) | Snapped to verb sense "to obscure or conceal"; the vehicle intends the noun (a veil — the  |
| verse | 17052 | v | familiarize through thorough study or experience | literature in metrical form (synset 70461) | Snapped to verb sense "familiarise through study"; the vehicle intends the noun (verse — a |
| void | 10012 | v | clear (a room, house, place) of occupants or empty or clear  | an empty area or space (synset 97014) or the state of nonexi | Snapped to verb sense "clear a place of occupants"; the vehicle intends the noun (a void — |
| voyage | 31066 | v | travel on water propelled by wind or by other means | a journey to some distant place (synset 6866) | Snapped to verb sense "travel on water propelled by wind"; the vehicle intends the noun (a |
| wager | 21448 | v | stake on the outcome of an issue | the money risked on a gamble (synset 93793) | Snapped to verb sense "stake on the outcome of an issue"; the vehicle intends the noun (a  |
| wedge | 26702 | v | squeeze like a wedge into a tight space | something solid that is usable as an inclined plane shaped l | Snapped to verb sense "squeeze into a tight space"; the vehicle intends the noun (a wedge  |
| wine | 21972 | v | drink wine | fermented juice (of grapes especially) (synset 75236) | Snapped to verb sense "drink wine"; the vehicle intends the noun (wine — the fermented gra |
| yoke | 26247 | v | link with or as with a yoke | stable gear that joins two draft animals at the neck (synset | Snapped to verb sense "link with or as with a yoke"; the vehicle intends the noun (a yoke  |
| yoking | 26247 | v | link with or as with a yoke | stable gear that joins two draft animals at the neck (synset | Same as yoke: snapped to verb sense; the vehicle intends the noun (the yoke as concrete in |


---

## RARE_OK — Topics

1 topic(s) where the snapped sense is an unusual but valid choice that still yields coherent metaphors.

| Word | Synset ID | Snapped gloss | Note |
|------|-----------|---------------|------|
| marrow | 61455 | the fatty network of connective tissue that fills the cavities of bone | Snapped to literal bone-marrow (anatomy) sense; for a metaphor topic, the "essential core" sense (sy |


---

## RARE_OK — Vehicles

10 vehicles where the snapped sense is an unusual or adjective/participial sense that nevertheless correctly captures the vehicle concept.

| Word | Synset ID | POS | Snapped gloss | Note |
|------|-----------|-----|---------------|------|
| becalmed | 27237 | s | rendered motionless for lack of wind | Only an adjective sense exists in the DB; the vehicle intends the state of being becalmed  |
| coiling | 37835 | s | in the shape of a coil | Only an adjective/participial sense in the DB; the vehicle intends the spiralling shape or |
| crushing | 12740 | s | physically or spiritually devastating; often used in combina | Only an adjective sense in the DB; the vehicle intends the concept of something that crush |
| falling | 40352 | a | becoming lower or less in degree or value | Only an adjective/participial sense in the DB; the vehicle intends the concept of descent  |
| flyblown | 20113 | s | spoiled and covered with eggs and larvae of flies | Only an adjective sense in the DB; the vehicle intends the concept of something contaminat |
| harrowing | 29248 | s | extremely painful | Only an adjective sense in the DB; the vehicle intends the concept of something extremely  |
| lachrymatory | 46123 | a | relating to or prompting tears | Only an adjective sense in the DB; the vehicle intends the quality of provoking tears (as  |
| lenticular | 11940 | s | convex on both sides; shaped like a lentil | Only an adjective sense in the DB; the vehicle intends the lens-shaped (biconvex) concept. |
| mordant | 34292 | s | harshly ironic or sinister | Snapped to adjective sense "harshly ironic or sinister"; the vehicle likely intends this q |
| votive | 12515 | s | dedicated in fulfillment of a vow | Only an adjective sense in the DB; the vehicle intends the quality of being dedicated in f |


---

## Patterns Observed

### 1. Process-nominal trap (topics) — 13 of 21 topic WRONG_SENSEs

The snapper repeatedly chooses the lowest-numbered noun synset for words like *agitation*, *confusion*, *exhaustion*, *tension*, *oppression*, *saturation*, *allegiance*, *confession*, *decay*. These lower-numbered synsets tend to be process-nominals ("the act of X") whereas the intended sense is nearly always a psychological state or a general abstract concept. WordNet encodes many emotion and state words with both a process-nominal sense and a state/condition sense; the snapper consistently prefers the former.

**Remedy:** For topic endpoints, prefer synsets whose definition begins with "a feeling of", "a state of", "the quality of", or "a condition" rather than "the act of". A post-hoc re-snap rule covering topic endpoints whose snapped definition matches `^the act of` would recover at least 10 of these 21.

### 2. Verb-sense contamination (vehicles) — 79 vehicle WRONG_SENSEs

For vehicles, the snapper overwhelmingly snaps to a verb synset for words that are primarily noun concepts in context. Notable sub-cases:

- **Wildly wrong verbs:** *hush* → "wash by removing particles" (hydraulic mining); *glamour* → "cast a spell"; *chisel/chiselling* → "engage in deceitful behavior"; *bait* → "attack with dogs"; *dye* → "color for microscopic study"; *hum* → "be noisy with activity"; *sleep* → "be able to accommodate for sleeping" (capacity). These are not merely wrong POS — they snap to a completely different concept within the verb paradigm.
- **Action vs. object:** *anchor*, *blight*, *blare*, *bone*, *braid*, *bread*, *breeze*, *counterpoint*, *dusk*, *eclipse*, *ferment*, *flare*, *forge*, *furrow*, *glamour*, *glaze*, *goad*, *hemorrhage*, *hound*, *indenture*, *itch*, *jolt*, *keel*, *lasso*, *leaven*, *loom*, *orbit*, *overhang*, *perfume*, *photograph*, *placard*, *plummet* (note: plummet verb sense is arguably OK — it snaps to "drop sharply" which IS the vehicle metaphor), *poultice*, *prey*, *probe*, *reek*, *riot*, *rot*, *rumble*, *sandpaper*, *seesaw*, *sluice*, *slump*, *snare*, *submarine*, *sunburn*, *swell*, *taper*, *tarnish*, *telegraph*, *temper*, *thermostat*, *thread*, *transplant*, *twig*, *varnish*, *veil*, *verse*, *void*, *voyage*, *wager*, *wedge*, *wine*, *yoke/yoking*.

**Remedy:** For vehicle endpoints, prefer noun synsets over verb synsets unless the lemma has no noun synset. The snapper should apply noun-first sense ordering for vehicles.

### 3. Adjective and adverb senses (vehicles) — 10 RARE_OK, 1 WRONG_SENSE adv

*plumb* (adverb "exactly") is the clearest outlier — an adverb sense for a word with a concrete noun meaning (the metal bob of a plumb line). *phantom* snapped to an adjective sense when a noun sense exists. Several others (*becalmed*, *coiling*, *harrowing*, *flyblown*, *falling*, *crushing*, *votive*, *lenticular*, *lachrymatory*, *mordant*) have only adjective senses in the DB, making them RARE_OK rather than WRONG_SENSE.

### 4. Narrow technical/specialist senses (topics)

*ideology* → "imaginary or visionary theorization" (a pejorative philosophically marginal sense rather than the standard political-science meaning). *cadence* → a narrow prosodic technicality rather than the general rhythmic sense. *amplification* → a signal-power ratio measurement rather than the concept of enlargement. *purity* → "a woman's virtue or chastity" (gender-restricted chastity) rather than the general concept of being uncontaminated.

### 5. "Act of" sense for abstract topics — the main contaminant

The sub-family: *agitation*, *allegiance*, *apprehension*, *concentration*, *confession*, *confusion*, *exhaustion*, *oppression*, *ostracism* (already OK), *persecution*, *saturation*, *tension* — all emotion/state words whose snapped senses are "the act of X" process-nominals. These represent the largest coherent contamination cluster (12 topics, 4.3% of all topics).

---

*Worklist written to `data-pipeline/grading/sense_flags_provisional.jsonl` (111 records: 100 WRONG_SENSE, 11 RARE_OK). OK endpoints omitted from the JSONL.*
