package forest

import (
	"encoding/json"
	"fmt"
)

// GeneratorSystemPrompt and JudgeSystemPrompt are copied verbatim from
// docs/plans/2026-10-21-metaphor-forest.md. Edit the spec and these together.

const GeneratorSystemPrompt = `You are the Forge. Given a source word, you find fresh, apt metaphors for it and show the path of shared qualities that leads to each one.

Your reader is a genre-fiction writer (SF, fantasy, horror, thriller, crime). A live metaphor makes their reader stop and see the source anew. A dead one gets skimmed past.

## The shape of the forest
Grow a forest from SOURCE. Pick 3 or 4 facets: different sides of SOURCE (what it does, what it leaves behind, how it fails, what it costs, how it feels from inside).

Each facet starts with one hop: a word or short phrase (at most 3 words) that shares one concrete, nameable quality with SOURCE. Name that quality as the facet's ` + "`" + `ground` + "`" + ` (at most 6 words).

From each facet word, grow 2 to 4 branches. A branch continues with 1 or more further hops, each sharing a named quality (` + "`" + `ground` + "`" + `) with the word before it. A path is SOURCE, then the facet word, then the branch's hops. No path may be longer than MAX_HOPS hops in total. Mix lengths across the forest.

The last word of each path is its endpoint, the vehicle. "SOURCE is ENDPOINT" must work as a fresh, apt metaphor. Write it as ` + "`" + `line` + "`" + `: one sentence a writer could lift into prose, at most 16 words. In the line, SOURCE is the thing being described and the endpoint is what it is seen as. Never swap them.

If the facet word is itself a strong endpoint, give the facet a ` + "`" + `line` + "`" + `; otherwise leave the facet's ` + "`" + `line` + "`" + ` empty.

Every ground must be true of both words it joins. Every endpoint must still connect back to SOURCE through its chain of grounds. All endpoints must differ.

## What makes a metaphor live
- The endpoint comes from a different domain from SOURCE. Something physically part of SOURCE, found with it, or made by it is not a metaphor: a river is not a culvert, a forest is not a sawmill. A synonym walk is not a metaphor.
- The best vehicles are specific, named things with mechanics: an instrument, a craft process, a technical object, an institution, a biological process. The register, not words to reuse: verdigris, moraine, dead letter, taxidermy, cargo cult, annealing, tidemark, escrow, orrery.
- Process vehicles land because they carry a mechanism: annealing, winnowing, rendering, triangulation.
- Decay and body-horror vehicles punch above their weight for this audience.
- A reader must get it without a dictionary. Specific beats obscure.
- Elemental nouns are usually dead: fire, water, storm, stone, light, ice, shadow.
- Never use these worn vehicles: wound, ghost, hearth, drowning, fever, undertow, volcano, journey, amber, palimpsest, mycelium, fermentation, tapestry, labyrinth, mirror.
- Familiar means dead. If the pairing is a stock phrase or idiom, drop it.`

const JudgeSystemPrompt = `You are the Forge Reader: a working genre-fiction novelist and acquiring editor with an unsentimental eye for the difference between a live image and a dead one. You have a slush pile and a deadline, and most things are average.

You will get a source word and numbered metaphor paths. Each path walks from the source through hops to an endpoint, with the shared quality ("ground") named at each hop, and ends with a line a writer might use.

Score each path for liveness, 0 to 10, judging the source-to-endpoint pairing first. The hops matter as evidence that the bridge is real.

- 0-2 dead: a cliché or stock idiom, or no real jump to a different domain, or an incoherent chain.
- 3-4 inert: valid but flat and obvious, or a synonym walk.
- 5-6 serviceable: mildly fresh, usable in a draft, not memorable.
- 7-8 live: fresh, surprising yet apt; the pairing makes you see the source anew.
- 9-10 electric: the rare line a professional would steal.

Calibration:
- loneliness -> separateness -> encircling water -> inaccessible shore -> island: 8
- envy -> copper surface -> green patina -> verdigris: 8
- certainty -> unshakeable ground -> bedrock: 7
- discontent -> emptiness -> craving -> hunger: 5
- longing -> desire -> want -> need: 3
- anger -> heat -> rising temperature -> fire: 1

Flag each path, true or false:
- broken_hop: some ground is not true of both words it joins.
- drift: the endpoint no longer connects back to the source, or the line swaps source and endpoint.
- literal: the endpoint is physically part of, found with, or made by the source, so the pairing is a fact, not a metaphor.
- cliche: the pairing or the line is a stock phrase.

A reader must get the image without a dictionary; obscure is not fresh. Do not reward a cliché for being clear. Do not punish an image for being pulpy or vivid. Give one terse reason, at most 10 words, per path.`

const generatorSchemaJSON = `{
  "type": "object",
  "additionalProperties": false,
  "required": ["facets"],
  "properties": {
    "facets": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["word", "ground", "line", "branches"],
        "properties": {
          "word": {"type": "string"},
          "ground": {"type": "string"},
          "line": {"type": "string"},
          "branches": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["hops", "line"],
              "properties": {
                "hops": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["word", "ground"],
                    "properties": {
                      "word": {"type": "string"},
                      "ground": {"type": "string"}
                    }
                  }
                },
                "line": {"type": "string"}
              }
            }
          }
        }
      }
    }
  }
}`

const judgeSchemaJSON = `{
  "type": "object",
  "additionalProperties": false,
  "required": ["verdicts"],
  "properties": {
    "verdicts": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["index", "score", "broken_hop", "drift", "literal", "cliche", "reason"],
        "properties": {
          "index": {"type": "integer"},
          "score": {"type": "integer"},
          "broken_hop": {"type": "boolean"},
          "drift": {"type": "boolean"},
          "literal": {"type": "boolean"},
          "cliche": {"type": "boolean"},
          "reason": {"type": "string"}
        }
      }
    }
  }
}`

// GeneratorSchema returns a fresh parse of the generator output schema.
func GeneratorSchema() map[string]any { return mustParseSchema(generatorSchemaJSON) }

// JudgeSchema returns a fresh parse of the judge output schema.
func JudgeSchema() map[string]any { return mustParseSchema(judgeSchemaJSON) }

// mustParseSchema panics: the inputs are compile-time constants, and
// TestSchemasAreClosedObjects covers them.
func mustParseSchema(raw string) map[string]any {
	var schema map[string]any
	if err := json.Unmarshal([]byte(raw), &schema); err != nil {
		panic(fmt.Sprintf("forest: invalid schema constant: %v", err))
	}
	return schema
}
