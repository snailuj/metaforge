import { describe, it, expect } from 'vitest'
import { displayLine } from './line'

// Rule: a line that opens by stating "SOURCE is ENDPOINT" and then elaborates
// after a , : ; or dash shows only the elaboration, capitalised. Any other
// line shows exactly as the model wrote it.
describe('displayLine', () => {
  it.each([
    ['Immanence is woodworm, living inside the beam it slowly hollows out.', 'immanence', 'woodworm', 'Living inside the beam it slowly hollows out.'],
    ['Immanence is grain: the pattern runs through the wood, not painted across its face.', 'immanence', 'grain', 'The pattern runs through the wood, not painted across its face.'],
    ['Her patience was a sacrificial anode, corroding quietly so the hull stayed sound.', 'patience', 'sacrificial anode', 'Corroding quietly so the hull stayed sound.'],
    ['Patience is an escapement, letting the spring unwind one measured tooth at a time.', 'patience', 'escapement', 'Letting the spring unwind one measured tooth at a time.'],
    ['His patience was a seed vault: everything kept viable against the thaw.', 'patience', 'seed vault', 'Everything kept viable against the thaw.'],
    ['Grief is a slow tide; it takes the shore by inches.', 'grief', 'tide', 'It takes the shore by inches.'],
    ['Doubts are woodworms -- small, patient, everywhere.', 'doubt', 'woodworm', 'Small, patient, everywhere.'],
    ['Doubt is woodworm — small, patient, everywhere.', 'doubt', 'woodworm', 'Small, patient, everywhere.'],
    ['IMMANENCE IS WOODWORM, living inside.', 'immanence', 'woodworm', 'Living inside.'],
  ])('strips the opening clause of %j', (line, source, endpoint, want) => {
    expect(displayLine(line, source, endpoint)).toBe(want)
  })

  it.each([
    // The clause carries the meaning: nothing follows a separator.
    ['Immanence is the woodworm in the beam.', 'immanence', 'woodworm'],
    ['Immanence is woodworm.', 'immanence', 'woodworm'],
    // Not the copular shape.
    ['Her patience kept its grudge like a bog body, tanned and unrotted for decades.', 'patience', 'bog body'],
    ['His patience had healed into a keloid, thickening past the injury it was meant to close.', 'patience', 'keloid'],
    ['The solera of her patience: old years kept, new ones blended in.', 'patience', 'solera'],
    // Source and endpoint swapped, or the endpoint not named in the clause.
    ['Woodworm is immanence, living inside.', 'immanence', 'woodworm'],
    ['Immanence is quiet, living inside.', 'immanence', 'woodworm'],
    // Nothing left after the separator.
    ['Immanence is woodworm:  ', 'immanence', 'woodworm'],
    ['', 'immanence', 'woodworm'],
  ])('leaves %j unchanged', (line, source, endpoint) => {
    expect(displayLine(line, source, endpoint)).toBe(line)
  })

  it('treats regex characters in the words literally', () => {
    expect(displayLine('C++ is a lathe, turning out parts.', 'c++', 'lathe')).toBe('Turning out parts.')
    expect(displayLine('Cxx is a lathe, turning out parts.', 'c++', 'lathe')).toBe('Cxx is a lathe, turning out parts.')
  })
})
