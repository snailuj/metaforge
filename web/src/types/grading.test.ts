import { describe, it, expect } from 'vitest';
import { normaliseJudgement } from './grading';

describe('normaliseJudgement', () => {
    it('v2 normalises to a tiers array', () => {
        expect(
            normaliseJudgement({ linkage: 'good', metaphor: 'live', tiers: ['strong'] }).tiers,
        ).toEqual(['strong']);
        expect(normaliseJudgement({ linkage: 'good', metaphor: 'dead' }).tiers).toEqual([]);
    });

    it('v1 label normalises to empty tiers', () => {
        expect(normaliseJudgement({ label: 'live' }).tiers).toEqual([]);
    });

    it('v2 passes the two axes through', () => {
        const n = normaliseJudgement({ linkage: 'bad', metaphor: 'irrelevant' });
        expect(n.linkage).toBe('bad');
        expect(n.metaphor).toBe('irrelevant');
    });
});
