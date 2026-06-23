# Pilot: context-free-hop clause — old vs new chain generation (2026-06-03)

**What this is.** Apples-to-apples regeneration of the round-1 grading cohort
(20 topics × 10 vehicles) with the context-free-hop clause added to
`run_chain_spike.build_prompt` (commit d1b3a837). Same topics, same Haiku
candidate vehicles, same model (`claude-sonnet-4-6`) — **only the prompt differs**,
so any change in path structure is attributable to the clause. New chains:
`/tmp/stagea_pilot/sonnet_chains_NEW.jsonl` (not committed — pilot output).

**Purpose.** Validate whether the clause actually reduces context-bound hops
*before* committing to a full-cohort regen (which would orphan existing verdicts
via new `chain_signature`s). Julian's hand-grading on these same 20 topics is the
ground truth; this artifact is deliberately **not** auto-judged for
context-boundness.

**Objective metrics (107 matched topic→vehicle pairs):**
- Avg steps/chain: **OLD 5.30 → NEW 4.21** (min/max OLD 4/7, NEW 3/5). Chains got
  ~1 step shorter. ⚠️ **Watch this:** shorter could mean Sonnet *removed
  context-scaffolding steps* (good — those were often the context-bound connectors)
  OR *made bigger leaps* (bad). This is the key thing to eyeball.
- Multi-word intermediate steps (a rough `bad_head` risk surface): **OLD 57% →
  NEW 53%** ≈ unchanged. The context-free clause does **not** target head
  extraction, so `bad_head` risk persists (e.g. NEW `motionless hunter`,
  `cocked strike`). That stays W4 / head-extraction's job.
- Vehicle substitution: 107 matched; 93 dropped, 93 newly introduced (~47% churn
  from Sonnet's editorial licence — unmatched vehicles are listed per topic below).

**Headline (the case Julian flagged):**
- OLD: `ambush → stillness → camouflage → patient pose → lightning strike → mantis`
- NEW: `ambush → motionless hunter → cocked strike → explosive release → mantis`
- The context-bound `stillness→camouflage` hop is gone; chain is tighter.

---

# Chain cohort comparison — round-1 (old prompt) vs pilot (context-free)

- Matched (same topic+vehicle): **107**
- round-1 (old prompt)-only vehicles (substituted away): **93**
- pilot (context-free)-only vehicles (newly introduced): **93**

For each matched vehicle the two paths sit one above the other so a context-bound hop in one but not the other is easy to spot.

## ambush

**ambush → mantis**
- round-1 (old prompt): ambush → stillness → camouflage → patient pose → lightning strike → mantis
- pilot (context-free): ambush → motionless hunter → cocked strike → explosive release → mantis

**ambush → sinkhole**
- round-1 (old prompt): ambush → false solidity → hidden erosion → structural weakness → sudden collapse → sinkhole
- pilot (context-free): ambush → apparent solidity → hidden void → sudden collapse → sinkhole

**ambush → snake**
- round-1 (old prompt): ambush → concealment → coiled stillness → cold patience → invisible threat → sudden strike → snake
- pilot (context-free): ambush → hidden predator → coiled patience → lightning strike → snake

**ambush → spring**
- round-1 (old prompt): ambush → stored intention → compressed energy → invisible readiness → sudden release → spring
- pilot (context-free): ambush → patient stillness → stored tension → spring

_dropped in pilot (context-free): avalanche, fault, gannet, mine, mousetrap, trapdoor_
_new in pilot (context-free): deadfall, flytrap, iceberg, thunderclap, tsunami, volcano_

## anchor

**anchor → keystone**
- round-1 (old prompt): anchor → prevents drift → holds everything together → keystone
- pilot (context-free): anchor → hold → capstone → keystone

**anchor → lodestone**
- round-1 (old prompt): anchor → holds fast → fixed point → orients → lodestone
- pilot (context-free): anchor → hold → draw → lodestone

**anchor → root**
- round-1 (old prompt): anchor → drops → grips seabed → buried hold → root
- pilot (context-free): anchor → weight → ground → root

_dropped in pilot (context-free): bedrock, habit, handhold, home, plummet, stone, tendon_
_new in pilot (context-free): gravity, hearth, keel, mainstay, plumb, polestar, threshold_

## anger

**anger → abscess**
- round-1 (old prompt): anger → wound → infection → festering → pressure → abscess
- pilot (context-free): anger → festering → pus → abscess

**anger → fermentation**
- round-1 (old prompt): anger → containment → slow heat → transformation → fermentation
- pilot (context-free): anger → bitterness → acidity → fermentation

**anger → flood**
- round-1 (old prompt): anger → overwhelm → surge → rising water → flood
- pilot (context-free): anger → surge → overflow → flood

**anger → venom**
- round-1 (old prompt): anger → hostility → toxicity → secretion → venom
- pilot (context-free): anger → hostility → sting → venom

**anger → volcano**
- round-1 (old prompt): anger → pressure → subterranean heat → magma → volcano
- pilot (context-free): anger → pressure → magma → volcano

_dropped in pilot (context-free): avalanche, blister, fault, forge, kettle_
_new in pilot (context-free): bile, fever, riptide, rust, static_

## anxiety

**anxiety → fermentation**
- round-1 (old prompt): anxiety → suppression → sealed container → pressure building → fermentation
- pilot (context-free): anxiety → bottled agitation → pressurised vessel → fermentation

**anxiety → pendulum**
- round-1 (old prompt): anxiety → rumination → oscillation → rhythmic return → pendulum
- pilot (context-free): anxiety → restless cycling → rhythmic oscillation → pendulum

**anxiety → quicksand**
- round-1 (old prompt): anxiety → urge to escape → struggle → deepening entrapment → quicksand
- pilot (context-free): anxiety → avoidance → deepening entrapment → quicksand

**anxiety → swarm**
- round-1 (old prompt): anxiety → intrusive thought → multiplication → encirclement → swarm
- pilot (context-free): anxiety → intrusive thought → buzzing mass → swarm

**anxiety → tinnitus**
- round-1 (old prompt): anxiety → hypervigilance → listening for threats → internal signal → signal without source → tinnitus
- pilot (context-free): anxiety → mental static → inescapable hum → tinnitus

**anxiety → undertow**
- round-1 (old prompt): anxiety → surface calm → hidden current → downward pull → undertow
- pilot (context-free): anxiety → surface calm → hidden current → undertow

**anxiety → whirlpool**
- round-1 (old prompt): anxiety → circular thought → centripetal pull → entrapment → whirlpool
- pilot (context-free): anxiety → circular thought → inward pull → vortex → whirlpool

_dropped in pilot (context-free): debt, overcast, static_
_new in pilot (context-free): barometer, fissure, fog_

## argument

**argument → dance**
- round-1 (old prompt): argument → exchange → call and response → partners in tension → dance
- pilot (context-free): argument → exchange of moves → rhythmic response → dance

**argument → duel**
- round-1 (old prompt): argument → confrontation → two combatants → ritual of engagement → single combat → duel
- pilot (context-free): argument → direct confrontation → contest of honour → duel

**argument → fermentation**
- round-1 (old prompt): argument → opposing forces → contained pressure → rising heat → chemical change → fermentation
- pilot (context-free): argument → competing agents → pressure → agitation → fermentation

**argument → siege**
- round-1 (old prompt): argument → opposition → fortified position → sustained assault → war of attrition → siege
- pilot (context-free): argument → contested position → defensive entrenchment → sustained assault → siege

**argument → wrestling**
- round-1 (old prompt): argument → clash → bodily struggle → grappling for leverage → wrestling
- pilot (context-free): argument → struggle for dominance → grappling → wrestling

_dropped in pilot (context-free): chess, counterpoint, erosion, trial, weaving_
_new in pilot (context-free): combustion, earthquake, storm, surgery, tide_

## courage

**courage → compass**
- round-1 (old prompt): courage → orientation under disruption → pointing true → magnetic needle → compass
- pilot (context-free): courage → unwavering orientation → true north → compass

**courage → keel**
- round-1 (old prompt): courage → stability under pressure → hidden load-bearing structure → ship's backbone → keel
- pilot (context-free): courage → steadiness → structural spine → keel

**courage → mountain**
- round-1 (old prompt): courage → effort against resistance → sustained ascent → exposed summit → mountain
- pilot (context-free): courage → resistance → strain → ascent → mountain

**courage → river**
- round-1 (old prompt): courage → persistence → carving through resistance → channelled current → river
- pilot (context-free): courage → pressing on → wearing down resistance → current → river

**courage → tightrope**
- round-1 (old prompt): courage → exposure to risk → forward motion above void → suspended cord → tightrope
- pilot (context-free): courage → exposed position → balance under threat → tightrope

_dropped in pilot (context-free): bellows, chrysalis, fuse, graft, keystone_
_new in pilot (context-free): flint, hawk, surgeon, trapeze, winter_

## deadline

**deadline → cliff**
- round-1 (old prompt): deadline → limit → edge → drop → cliff
- pilot (context-free): deadline → edge → drop → cliff

**deadline → guillotine**
- round-1 (old prompt): deadline → judgment → descending blade → severance → guillotine
- pilot (context-free): deadline → judgment → severance → guillotine

**deadline → scythe**
- round-1 (old prompt): deadline → harvest → reaping → sweeping blade → scythe
- pilot (context-free): deadline → harvest → cutting → scythe

**deadline → terminus**
- round-1 (old prompt): deadline → fixed endpoint → journey's end → tracks ending → terminus
- pilot (context-free): deadline → journey → arrival → terminus

**deadline → tide**
- round-1 (old prompt): deadline → approach → rising water → inexorable overwhelm → tide
- pilot (context-free): deadline → pressure → surge → tide

**deadline → watershed**
- round-1 (old prompt): deadline → turning point → ridge line → drainage split → watershed
- pilot (context-free): deadline → turning point → divide → watershed

_dropped in pilot (context-free): frost, noose, portcullis, singularity_
_new in pilot (context-free): avalanche, curtain, drawbridge, fuse_

## doubt

**doubt → fog**
- round-1 (old prompt): doubt → clarity → gradual obscuring → loss of bearings → fog
- pilot (context-free): doubt → suspended certainty → obscured horizon → fog

**doubt → palimpsest**
- round-1 (old prompt): doubt → prior certainty → erasure → overwriting → traces beneath → palimpsest
- pilot (context-free): doubt → overwritten certainty → layered inscription → palimpsest

**doubt → scales**
- round-1 (old prompt): doubt → competing claims → weighing → oscillation → scales
- pilot (context-free): doubt → suspended judgment → oscillation → scales

**doubt → tinnitus**
- round-1 (old prompt): doubt → inner quiet → persistent questioning → unlocatable noise → tinnitus
- pilot (context-free): doubt → persistent intrusion → unresolvable noise → tinnitus

**doubt → undertow**
- round-1 (old prompt): doubt → apparent certainty → hidden current → backward pull → undertow
- pilot (context-free): doubt → hidden force → subsurface current → undertow

_dropped in pilot (context-free): crossroads, fermentation, penumbra, tremor, vertigo_
_new in pilot (context-free): mirage, quicksand, rust, shadow, static_

## gridlock

**gridlock → amber**
- round-1 (old prompt): gridlock → total immobility → suspended animation → tree resin → amber
- pilot (context-free): gridlock → suspended motion → enclosed in resin → amber

**gridlock → clot**
- round-1 (old prompt): gridlock → blocked flow → vessel → aggregated cells → clot
- pilot (context-free): gridlock → stagnant flow → coagulation → clot

**gridlock → logjam**
- round-1 (old prompt): gridlock → dense accumulation → waterway → floating timber → logjam
- pilot (context-free): gridlock → blocked flow → jammed river → logjam

**gridlock → mire**
- round-1 (old prompt): gridlock → trapped in place → soft ground → waterlogged earth → peat → mire
- pilot (context-free): gridlock → immovable press → boggy ground → mire

**gridlock → siege**
- round-1 (old prompt): gridlock → encirclement → denied access → prolonged blockade → siege
- pilot (context-free): gridlock → city cut off → surrounded perimeter → siege

_dropped in pilot (context-free): doldrums, filibuster, knot, permafrost, stalemate_
_new in pilot (context-free): cramp, crystallisation, deadlock, ossification, silt_

## grief

**grief → amber**
- round-1 (old prompt): grief → loss → past moment → clinging → resin → hardening → amber
- pilot (context-free): grief → memory → preservation → resin → amber

**grief → permafrost**
- round-1 (old prompt): grief → numbness → cold → deep freeze → permafrost
- pilot (context-free): grief → dormancy → cold → frozen ground → permafrost

**grief → wound**
- round-1 (old prompt): grief → pain → rawness → bleeding → wound
- pilot (context-free): grief → pain → laceration → raw flesh → wound

_dropped in pilot (context-free): drought, ocean, palimpsest, revenant, sediment, tinnitus, winter_
_new in pilot (context-free): calcification, eclipse, molt, rust, silt, undertow, vertigo_

## heart

**heart → bellows**
- round-1 (old prompt): heart → muscular wall → rhythmic compression → forced flow → bellows
- pilot (context-free): heart → chamber → compression → bellows

**heart → drum**
- round-1 (old prompt): heart → heartbeat → percussive thud → resonant chamber → drum
- pilot (context-free): heart → hollow body → rhythmic beating → drum

**heart → forge**
- round-1 (old prompt): heart → rhythmic beat → hammering stroke → heat generation → forge
- pilot (context-free): heart → vital heat → sustained flame → forge

**heart → fountain**
- round-1 (old prompt): heart → blood → rhythmic surge → upward jet → fountain
- pilot (context-free): heart → pressure → rhythmic outflow → fountain

**heart → pump**
- round-1 (old prompt): heart → blood → fluid pressure → propulsion → pump
- pilot (context-free): heart → pulsation → pressure → pump

**heart → spring**
- round-1 (old prompt): heart → muscular contraction → elastic deformation → stored energy → recoil → spring
- pilot (context-free): heart → contraction → elastic recoil → spring

**heart → sun**
- round-1 (old prompt): heart → blood → circulation → radial outflow → sun
- pilot (context-free): heart → warmth → radiance → sun

**heart → tide**
- round-1 (old prompt): heart → blood → systolic surge → diastolic retreat → tide
- pilot (context-free): heart → rhythmic surge → tide

_dropped in pilot (context-free): geyser, metronome_
_new in pilot (context-free): clock, loom_

## hope

**hope → compass**
- round-1 (old prompt): hope → orientation → pull → magnetic attraction → compass
- pilot (context-free): hope → orientation → true north → compass

**hope → ember**
- round-1 (old prompt): hope → persistence → residual warmth → smouldering → ember
- pilot (context-free): hope → tenacity → last warmth → ember

**hope → horizon**
- round-1 (old prompt): hope → forward orientation → gaze → distance → vanishing line → horizon
- pilot (context-free): hope → forward gaze → receding line → horizon

**hope → seed**
- round-1 (old prompt): hope → expectation → latency → dormancy → germination → seed
- pilot (context-free): hope → unseen future → buried promise → seed

_dropped in pilot (context-free): antenna, covenant, dawn, leaven, threshold, trellis_
_new in pilot (context-free): ballast, bridge, fermentation, migration, spring, tide_

## ideas

**ideas → fermentation**
- round-1 (old prompt): ideas → raw ingredients → slow change → transformation → fermentation
- pilot (context-free): ideas → incubation → latent energy → chemical reaction → fermentation

**ideas → mycelium**
- round-1 (old prompt): ideas → invisible connections → underground network → filaments → mycelium
- pilot (context-free): ideas → association → hidden connections → spreading network → mycelium

**ideas → sediment**
- round-1 (old prompt): ideas → accumulation → layering → compression → sediment
- pilot (context-free): ideas → accumulation → layering → compression → sediment

**ideas → spore**
- round-1 (old prompt): ideas → propagation → dormancy → resilience → spore
- pilot (context-free): ideas → dormant potential → wide dispersal → spore

**ideas → tide**
- round-1 (old prompt): ideas → rhythm → ebb → return → tide
- pilot (context-free): ideas → recurring obsession → returning rhythm → gravitational pull → tide

_dropped in pilot (context-free): crystallisation, fracture, leaven, seeds, threads_
_new in pilot (context-free): compass, contagion, crystal, light, seed_

## life

**life → fermentation**
- round-1 (old prompt): life → organic substance → contained process → slow time → decay → transformation → fermentation
- pilot (context-free): life → organic matter → slow transformation → chemical conversion → fermentation

**life → fugue**
- round-1 (old prompt): life → temporal unfolding → recurring themes → multiple voices → counterpoint → resolution → fugue
- pilot (context-free): life → recurring theme → variation → counterpoint → fugue

**life → garden**
- round-1 (old prompt): life → growth → tended earth → seasonal death → renewal → garden
- pilot (context-free): life → organic growth → seasonal rhythm → tended plot → garden

**life → migration**
- round-1 (old prompt): life → movement → instinct → seasonal compulsion → passage → arrival → migration
- pilot (context-free): life → animal being → instinctual drive → seasonal passage → migration

**life → palimpsest**
- round-1 (old prompt): life → experience → layered memory → partial erasure → persisting traces → palimpsest
- pilot (context-free): life → memory → inscription → scraped surface → palimpsest

**life → river**
- round-1 (old prompt): life → duration → continuous flow → obstacle → carved channel → river
- pilot (context-free): life → passage → continuous flow → carving path → river

**life → story**
- round-1 (old prompt): life → events → causal sequence → meaning-making → narrative → story
- pilot (context-free): life → experience → meaning-making → structured narrative → story

**life → tapestry**
- round-1 (old prompt): life → moments → interwoven threads → emerging pattern → whole image → tapestry
- pilot (context-free): life → thread → weaving → pattern → tapestry

**life → tide**
- round-1 (old prompt): life → rhythm → external pull → ebb → return → tide
- pilot (context-free): life → rhythmic cycle → lunar pull → heaving sea → tide

_dropped in pilot (context-free): compost_
_new in pilot (context-free): eclipse_

## light

**light → breath**
- round-1 (old prompt): light → radiation → permeation → animating force → breath
- pilot (context-free): light → radiant source → warm exhalation → breath

**light → candle**
- round-1 (old prompt): light → point source → glow → flame → warmth → candle
- pilot (context-free): light → gentle glow → tended flame → candle

**light → fountain**
- round-1 (old prompt): light → emission → upward burst → arcing spray → falling return → fountain
- pilot (context-free): light → emanation from source → arcing spray → fountain

**light → river**
- round-1 (old prompt): light → flow → current → transparency → river
- pilot (context-free): light → radiant flow → streaming current → river

**light → tide**
- round-1 (old prompt): light → wave → oscillation → rhythm → advance and retreat → tide
- pilot (context-free): light → wave motion → rhythmic advance → shore-covering swell → tide

_dropped in pilot (context-free): arrow, bloom, honey, thread, veil_
_new in pilot (context-free): aurora, dawn, fire, rumour, spore_

## mirror

**mirror → conscience**
- round-1 (old prompt): mirror → self-reflection → introspection → moral judgement → conscience
- pilot (context-free): mirror → self-examination → moral reflection → conscience

**mirror → echo**
- round-1 (old prompt): mirror → reflection → sound reflection → echo
- pilot (context-free): mirror → reflection → reverberation → echo

**mirror → ghost**
- round-1 (old prompt): mirror → reflected self → spectral double → ghost
- pilot (context-free): mirror → doppelganger → haunting presence → ghost

**mirror → portrait**
- round-1 (old prompt): mirror → reflected face → painted likeness → portrait
- pilot (context-free): mirror → reflected face → painted likeness → portrait

**mirror → pupil**
- round-1 (old prompt): mirror → reflected image → miniature self → eye → pupil
- pilot (context-free): mirror → reflection → catchlight → pupil

**mirror → shadow**
- round-1 (old prompt): mirror → likeness → cast outline → shadow
- pilot (context-free): mirror → cast form → shadow

**mirror → twin**
- round-1 (old prompt): mirror → identical double → shared face → twin
- pilot (context-free): mirror → doubled self → identical sibling → twin

_dropped in pilot (context-free): daguerreotype, lake, moon_
_new in pilot (context-free): mercury, oracle, water_

## recursion

**recursion → dream**
- round-1 (old prompt): recursion → nested execution → one context suspended inside another → consciousness folded within itself → dream
- pilot (context-free): recursion → descent → deepening sleep → dream

**recursion → echo**
- round-1 (old prompt): recursion → call returning a call → repetition bouncing back on itself → sound fading through diminishing copies → echo
- pilot (context-free): recursion → repetition → reverberation → echo

**recursion → fractal**
- round-1 (old prompt): recursion → self-application → pattern within pattern → scale invariance → fractal
- pilot (context-free): recursion → self-similarity → scaling → fractal

**recursion → fugue**
- round-1 (old prompt): recursion → theme re-entry → voice imitating prior voice → counterpoint through self-quotation → fugue
- pilot (context-free): recursion → theme → imitation → voice → fugue

**recursion → matryoshka**
- round-1 (old prompt): recursion → nested call → smaller instance inside larger → container concealing its own copy → matryoshka
- pilot (context-free): recursion → nesting → inner copy → matryoshka

**recursion → mirror**
- round-1 (old prompt): recursion → self-reflection → image containing its own image → infinite regress → mirror
- pilot (context-free): recursion → reflection → infinite regress → mirror

**recursion → ouroboros**
- round-1 (old prompt): recursion → self-invocation → end looping back to beginning → tail meeting mouth → ouroboros
- pilot (context-free): recursion → self-reference → circular closure → ouroboros

_dropped in pilot (context-free): genealogy, quine, vortex_
_new in pilot (context-free): labyrinth, onion, spiral_

## road

**road → artery**
- round-1 (old prompt): road → carries traffic → circulation → distribution network → artery
- pilot (context-free): road → conduit → vessel → artery

**road → furrow**
- round-1 (old prompt): road → cut into earth → ploughed → directed growth → furrow
- pilot (context-free): road → track → trough → furrow

**road → groove**
- round-1 (old prompt): road → worn by passage → carved channel → directing movement → groove
- pilot (context-free): road → rut → groove

**road → river**
- round-1 (old prompt): road → channel → carries flow → carves terrain → river
- pilot (context-free): road → flow → current → river

**road → scar**
- round-1 (old prompt): road → cuts through land → wound → healed mark → scar
- pilot (context-free): road → cut → wound → scar

**road → spine**
- round-1 (old prompt): road → central axis → structural support → segmented column → spine
- pilot (context-free): road → axis → spinal cord → spine

_dropped in pilot (context-free): circuit, corridor, seam, thread_
_new in pilot (context-free): capillary, meridian, suture, tendril_

## threshold

**threshold → chrysalis**
- round-1 (old prompt): threshold → metamorphosis → suspension → sealed casing → chrysalis
- pilot (context-free): threshold → transition → metamorphosis → chrysalis

**threshold → membrane**
- round-1 (old prompt): threshold → boundary → selective barrier → permeability → membrane
- pilot (context-free): threshold → boundary → filter → membrane

**threshold → meniscus**
- round-1 (old prompt): threshold → surface → liquid's edge → tension between states → meniscus
- pilot (context-free): threshold → boundary surface → curved interface → meniscus

_dropped in pilot (context-free): dawn, event horizon, flashpoint, inflection, precipice, synapse, watershed_
_new in pilot (context-free): airlock, cliff, fault, horizon, isthmus, keystone, solstice_

## time

**time → debt**
- round-1 (old prompt): time → duration → accrual → compounding → obligation → debt
- pilot (context-free): time → passing → burden → debt

**time → glacier**
- round-1 (old prompt): time → duration → geological scale → slow movement → erosive force → glacier
- pilot (context-free): time → accumulation → compression → glacier

**time → river**
- round-1 (old prompt): time → passage → flow → current → direction → irreversibility → river
- pilot (context-free): time → passage → current → river

**time → thread**
- round-1 (old prompt): time → continuity → sequence → strand → spinning → thread
- pilot (context-free): time → continuity → spinning → thread

**time → tide**
- round-1 (old prompt): time → recurrence → cycle → rhythm → rise and fall → tide
- pilot (context-free): time → rhythm → cycle → tide

_dropped in pilot (context-free): fire, loom, palimpsest, scar, sediment_
_new in pilot (context-free): erosion, fermentation, hourglass, orbit, scroll_
