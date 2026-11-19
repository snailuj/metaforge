import { describe, it, expect } from 'vitest'
import { buildScene } from './scene'
import { createPhysics } from './physics'

// Rule: ticking the layout moves words and never produces a non-number.
describe('createPhysics', () => {
  it('moves at least one word in 10 ticks and writes no NaN', () => {
    const scene = buildScene(1, 100, 150)
    const physics = createPhysics(scene)
    const before = new Float32Array(300)
    const after = new Float32Array(300)
    physics.writePositions(before)
    for (let i = 0; i < 10; i++) physics.tick()
    physics.writePositions(after)
    expect(Array.from(after).some((v, i) => v !== before[i])).toBe(true)
    expect(Array.from(after).every(v => !Number.isNaN(v))).toBe(true)
  })

  it('starts from the scene positions', () => {
    const scene = buildScene(3, 20, 30)
    const out = new Float32Array(60)
    createPhysics(scene).writePositions(out)
    expect(Array.from(out)).toEqual(Array.from(scene.positions))
  })

  it('keeps doing full work on every tick, however long it runs', () => {
    const scene = buildScene(1, 50, 75)
    const physics = createPhysics(scene)
    const a = new Float32Array(150)
    const b = new Float32Array(150)
    for (let i = 0; i < 400; i++) physics.tick()
    physics.writePositions(a)
    physics.tick()
    physics.writePositions(b)
    // Alpha is held, so the layout keeps jostling instead of freezing.
    expect(Array.from(b).some((v, i) => v !== a[i])).toBe(true)
  })

  it('does not touch the scene it was built from', () => {
    const scene = buildScene(1, 30, 40)
    const copy = Array.from(scene.positions)
    const physics = createPhysics(scene)
    for (let i = 0; i < 5; i++) physics.tick()
    expect(Array.from(scene.positions)).toEqual(copy)
  })

  // Rule: ticking in a batch does exactly the work of ticking one by one, so
  // timing a batch and dividing measures the same thing as timing one tick.
  it('tickMany(n) leaves the layout where n single ticks leave it', () => {
    const scene = buildScene(2, 40, 60)
    const batched = createPhysics(scene)
    const single = createPhysics(scene)
    batched.tickMany(12)
    for (let i = 0; i < 12; i++) single.tick()
    const a = new Float32Array(120)
    const b = new Float32Array(120)
    batched.writePositions(a)
    single.writePositions(b)
    expect(Array.from(a)).toEqual(Array.from(b))
  })
})
