import { describe, it, expect } from 'vitest';
import { normaliseJudgement, TAGS } from './grading';

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

describe('normaliseJudgement tags (W3)', () => {
    it('v2 record returns its tags', () => {
        expect(normaliseJudgement({ linkage: 'good', metaphor: 'live', tags: ['bad_head'] }).tags).toEqual(['bad_head']);
    });
    it('v2 record without tags defaults to empty', () => {
        expect(normaliseJudgement({ linkage: 'good', metaphor: 'dead' }).tags).toEqual([]);
    });
    it('v1 label record returns empty tags', () => {
        expect(normaliseJudgement({ label: 'live' }).tags).toEqual([]);
    });
    it('TAGS vocabulary includes bad_head', () => {
        expect(TAGS).toContain('bad_head');
    });
});
