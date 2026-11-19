//! The force layout. Same forces, order and constants as d3-force-3d with the
//! page's settings; see physics.ts in web/src/perf for what those are.
use crate::octree::{Octree, NONE};
use crate::rng::Lcg;

/// d3 multiplies velocity by 1 - velocityDecay; the page sets 0.85.
const VELOCITY_RETAIN: f32 = 0.15;
const LINK_DISTANCE: f32 = 30.0;
/// d3's default theta is 0.9.
const THETA: f32 = 0.9;

fn zeroed<T: Clone + Default>(len: usize) -> Option<Vec<T>> {
    let mut v = Vec::new();
    v.try_reserve_exact(len).ok()?;
    v.resize(len, T::default());
    Some(v)
}

pub struct Engine {
    pub n: usize,
    /// Links declared at init; `active_links` of them survive `prepare`.
    pub m: usize,
    pub active_links: usize,
    pub pos: Vec<f32>,
    pub vel: Vec<f32>,
    pub links: Vec<u32>,
    pub strength: Vec<f32>,
    pub bias: Vec<f32>,
    pub degree: Vec<u32>,
    tree: Octree,
    rng: Lcg,
    pub theta2: f32,
    /// d3-force-3d scales an internal cell's summed charge by sqrt(4 / children),
    /// which is sqrt(1/2) per level in 3D. 1.0 gives a plain Barnes-Hut sum.
    pub cell_scale: f32,
}

impl Engine {
    /// Allocates every buffer once. Returns None when a size is zero, overflows
    /// or cannot be reserved, so the caller can report failure instead of aborting.
    pub fn new(n: usize, m: usize) -> Option<Engine> {
        if n == 0 {
            return None;
        }
        Some(Engine {
            n,
            m,
            active_links: 0,
            pos: zeroed(n.checked_mul(3)?)?,
            vel: zeroed(n.checked_mul(3)?)?,
            links: zeroed(m.checked_mul(2)?)?,
            strength: zeroed(m)?,
            bias: zeroed(m)?,
            degree: zeroed(n)?,
            tree: Octree::with_capacity(n)?,
            rng: Lcg::new(),
            theta2: THETA * THETA,
            cell_scale: core::f32::consts::FRAC_1_SQRT_2,
        })
    }
    pub fn prepare(&mut self) {
        todo!()
    }
    pub fn tick(&mut self, _alpha: f32) {
        todo!()
    }
    pub fn tick_many(&mut self, _alpha: f32, _count: u32) {
        todo!()
    }
    /// Repulsion between every pair, approximated by the octree.
    fn many_body(&mut self, alpha: f32) {
        self.tree.build(&self.pos, self.cell_scale);
        for i in 0..self.n {
            let dv = self.tree.force_on(i, &self.pos, alpha, self.theta2, &mut self.rng);
            for k in 0..3 {
                self.vel[3 * i + k] += dv[k];
            }
        }
    }
    #[allow(dead_code)]
    fn unused(&self) -> (u32, f32, f32) {
        (NONE, VELOCITY_RETAIN + LINK_DISTANCE, THETA)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Small seeded generator for test scenes (mulberry32).
    struct Seeded(u32);
    impl Seeded {
        fn next(&mut self) -> f32 {
            self.0 = self.0.wrapping_add(0x6d2b_79f5);
            let mut t = self.0;
            t = (t ^ (t >> 15)).wrapping_mul(t | 1);
            t ^= t.wrapping_add((t ^ (t >> 7)).wrapping_mul(t | 61));
            ((t ^ (t >> 14)) as f64 / 4_294_967_296.0) as f32
        }
    }

    fn scene(seed: u32, n: usize, m: usize) -> Engine {
        let mut r = Seeded(seed);
        let mut e = Engine::new(n, m).unwrap();
        for p in e.pos.iter_mut() {
            *p = (r.next() * 2.0 - 1.0) * 120.0;
        }
        for k in 0..m {
            let a = (r.next() * n as f32) as usize % n;
            // Offset by 1..n-1 so a link never joins a node to itself.
            let b = (a + 1 + (r.next() * (n - 1) as f32) as usize % (n - 1)) % n;
            e.links[2 * k] = a as u32;
            e.links[2 * k + 1] = b as u32;
        }
        e
    }

    /// Pairwise sum in f64 with d3's distance clamp: the reference the tree approximates.
    fn brute_force(e: &Engine, alpha: f32) -> Vec<[f64; 3]> {
        let p = |i: usize, k: usize| e.pos[3 * i + k] as f64;
        (0..e.n)
            .map(|i| {
                let mut v = [0.0f64; 3];
                for j in 0..e.n {
                    if i == j {
                        continue;
                    }
                    let d = [p(j, 0) - p(i, 0), p(j, 1) - p(i, 1), p(j, 2) - p(i, 2)];
                    let mut l = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
                    if l < 1.0 {
                        l = l.sqrt();
                    }
                    let w = -30.0 * alpha as f64 / l;
                    for k in 0..3 {
                        v[k] += d[k] * w;
                    }
                }
                v
            })
            .collect()
    }

    fn norm(v: [f64; 3]) -> f64 {
        (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt()
    }

    fn many_body_velocities(e: &mut Engine, alpha: f32) -> Vec<[f64; 3]> {
        e.vel.iter_mut().for_each(|v| *v = 0.0);
        e.many_body(alpha);
        (0..e.n).map(|i| [e.vel[3 * i] as f64, e.vel[3 * i + 1] as f64, e.vel[3 * i + 2] as f64]).collect()
    }

    // Rule: with no approximation (theta 0) the tree sums every pair, so it
    // must equal the brute-force pairwise sum.
    #[test]
    fn theta_zero_matches_brute_force() {
        let mut e = scene(11, 50, 0);
        e.theta2 = 0.0;
        let got = many_body_velocities(&mut e, 0.3);
        let want = brute_force(&e, 0.3);
        for i in 0..e.n {
            let err = norm([got[i][0] - want[i][0], got[i][1] - want[i][1], got[i][2] - want[i][2]]);
            assert!(err <= 1e-3 * norm(want[i]), "node {i}: error {err} against force {}", norm(want[i]));
        }
    }

    // Rule: with theta 0.9 the approximation costs accuracy, but a plain
    // Barnes-Hut sum stays within 5 per cent of the pairwise sum on average.
    // cell_scale 1.0 selects that plain sum; d3's own sqrt(1/2) per level is
    // a deliberate bias that the JS comparison test guards instead.
    #[test]
    fn theta_point_nine_stays_within_five_per_cent_on_average() {
        let mut e = scene(23, 500, 0);
        e.cell_scale = 1.0;
        let got = many_body_velocities(&mut e, 0.3);
        let want = brute_force(&e, 0.3);
        let (mut err, mut size) = (0.0, 0.0);
        for i in 0..e.n {
            err += norm([got[i][0] - want[i][0], got[i][1] - want[i][1], got[i][2] - want[i][2]]);
            size += norm(want[i]);
        }
        assert!(err / size < 0.05, "mean relative error {}", err / size);
    }

    // Rule: every point lands in the tree exactly once, including coincident
    // points and points that only differ in the last float digits.
    #[test]
    fn tree_holds_every_point_exactly_once() {
        let mut e = scene(5, 400, 0);
        e.pos[3..6].copy_from_slice(&[7.0, 7.0, 7.0]);
        e.pos[6..9].copy_from_slice(&[7.0, 7.0, 7.0]);
        let x = e.pos[9];
        e.pos[12] = x;
        e.pos[13] = e.pos[10];
        e.pos[14] = f32::from_bits(e.pos[11].to_bits() + 1);
        many_body_velocities(&mut e, 0.3);
        assert_eq!(e.tree.points_reachable(), 400);
        assert!(e.tree.nodes_used <= 400 * 32 + 8, "arena overrun");
    }
}
