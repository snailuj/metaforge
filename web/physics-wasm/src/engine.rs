//! The force layout. Same forces, order and constants as d3-force-3d with the
//! page's settings; see physics.ts in web/src/perf for what those are.
use crate::octree::Octree;
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

fn filled(len: usize, value: f32) -> Option<Vec<f32>> {
    let mut v = Vec::new();
    v.try_reserve_exact(len).ok()?;
    v.resize(len, value);
    Some(v)
}

pub struct Engine {
    /// Buffers are sized for these once, so the live counts can change freely.
    pub cap_n: usize,
    pub cap_m: usize,
    /// Live node count: every loop runs over `0..n` and never reads past it.
    pub n: usize,
    /// Live link count; `active_links` of them survive `prepare`.
    pub m: usize,
    pub active_links: usize,
    pub pos: Vec<f32>,
    pub vel: Vec<f32>,
    pub links: Vec<u32>,
    /// Rest length of each link; 30 until JS writes another.
    pub dist: Vec<f32>,
    /// Per node, 1 when the node is fixed at `fixed_pos` (d3's fx, fy, fz).
    pub fixed: Vec<u8>,
    pub fixed_pos: Vec<f32>,
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
    /// Allocates every buffer once, for up to `n` nodes and `m` links, and starts
    /// with all of them live. Returns None when a size is zero, overflows or
    /// cannot be reserved, so the caller can report failure instead of aborting.
    pub fn new(n: usize, m: usize) -> Option<Engine> {
        if n == 0 {
            return None;
        }
        Some(Engine {
            cap_n: n,
            cap_m: m,
            n,
            m,
            active_links: 0,
            pos: zeroed(n.checked_mul(3)?)?,
            vel: zeroed(n.checked_mul(3)?)?,
            links: zeroed(m.checked_mul(2)?)?,
            dist: filled(m, LINK_DISTANCE)?,
            fixed: zeroed(n)?,
            fixed_pos: zeroed(n.checked_mul(3)?)?,
            strength: zeroed(m)?,
            bias: zeroed(m)?,
            degree: zeroed(n)?,
            tree: Octree::with_capacity(n)?,
            rng: Lcg::new(),
            theta2: THETA * THETA,
            cell_scale: core::f32::consts::FRAC_1_SQRT_2,
        })
    }
    /// Sets how many nodes and links are live. Refused (false, nothing changed)
    /// beyond capacity, when the caller must re-create the engine larger.
    pub fn set_counts(&mut self, n: usize, m: usize) -> bool {
        if n > self.cap_n || m > self.cap_m {
            return false;
        }
        self.n = n;
        self.m = m;
        true
    }

    /// Call after JS has written the links and starting positions. Drops links
    /// that cannot apply, then derives degrees, strengths and biases as d3's
    /// link force does. Non-finite positions get d3's starting spiral, and
    /// velocities start at zero.
    pub fn prepare(&mut self) {
        let n = self.n as u32;
        let mut kept = 0;
        for k in 0..self.m {
            let (a, b) = (self.links[2 * k], self.links[2 * k + 1]);
            if a < n && b < n && a != b {
                self.links[2 * kept] = a;
                self.links[2 * kept + 1] = b;
                self.dist[kept] = self.dist[k];
                kept += 1;
            }
        }
        self.active_links = kept;
        self.degree[..self.n].iter_mut().for_each(|d| *d = 0);
        for k in 0..kept {
            self.degree[self.links[2 * k] as usize] += 1;
            self.degree[self.links[2 * k + 1] as usize] += 1;
        }
        for k in 0..kept {
            let ds = self.degree[self.links[2 * k] as usize] as f32;
            let dt = self.degree[self.links[2 * k + 1] as usize] as f32;
            self.strength[k] = 1.0 / ds.min(dt);
            self.bias[k] = ds / (ds + dt);
        }
        self.vel[..3 * self.n].iter_mut().for_each(|v| *v = 0.0);
        self.snap_fixed();
        let roll = core::f32::consts::PI * (3.0 - 5.0f32.sqrt());
        let yaw = core::f32::consts::PI * 20.0 / (9.0 + 221.0f32.sqrt());
        for i in 0..self.n {
            if self.pos[3 * i..3 * i + 3].iter().all(|v| v.is_finite()) {
                continue;
            }
            let radius = 10.0 * (0.5 + i as f32).cbrt();
            let (r, y) = (i as f32 * roll, i as f32 * yaw);
            self.pos[3 * i] = radius * r.sin() * y.cos();
            self.pos[3 * i + 1] = radius * r.cos();
            self.pos[3 * i + 2] = radius * r.sin() * y.sin();
        }
    }

    /// One step with d3's force order: link, many-body, centre, then velocity
    /// decay and the position update.
    pub fn tick(&mut self, alpha: f32) {
        self.link_force(alpha);
        self.many_body(alpha);
        self.centre();
        self.integrate();
    }

    pub fn tick_many(&mut self, alpha: f32, count: u32) {
        for _ in 0..count {
            self.tick(alpha);
        }
    }

    /// Springs towards each link's own distance. Like d3 it measures the gap after this
    /// tick's velocity so far, and splits the push by degree bias.
    fn link_force(&mut self, alpha: f32) {
        for k in 0..self.active_links {
            let s = self.links[2 * k] as usize;
            let t = self.links[2 * k + 1] as usize;
            let mut d = [0.0f32; 3];
            for a in 0..3 {
                d[a] = self.pos[3 * t + a] + self.vel[3 * t + a] - self.pos[3 * s + a] - self.vel[3 * s + a];
                if d[a] == 0.0 {
                    d[a] = self.rng.jiggle();
                }
            }
            let l = (d[0] * d[0] + d[1] * d[1] + d[2] * d[2]).sqrt();
            let f = (l - self.dist[k]) / l * alpha * self.strength[k];
            let b = self.bias[k];
            for a in 0..3 {
                let push = d[a] * f;
                self.vel[3 * t + a] -= push * b;
                self.vel[3 * s + a] += push * (1.0 - b);
            }
        }
    }

    /// d3's centre force: shift every node by the mean position (strength 1).
    /// Summed in f64 so the mean does not drift with the node count.
    fn centre(&mut self) {
        if self.n == 0 {
            return;
        }
        let mut mean = [0.0f64; 3];
        for p in self.pos[..3 * self.n].chunks_exact(3) {
            for a in 0..3 {
                mean[a] += p[a] as f64;
            }
        }
        for a in 0..3 {
            let shift = (mean[a] / self.n as f64) as f32;
            if shift != 0.0 {
                for i in 0..self.n {
                    self.pos[3 * i + a] -= shift;
                }
            }
        }
    }

    /// Moves each fixed node to its fixed position, as d3 does when it takes nodes.
    fn snap_fixed(&mut self) {
        for i in (0..self.n).filter(|&i| self.fixed[i] != 0) {
            self.pos[3 * i..3 * i + 3].copy_from_slice(&self.fixed_pos[3 * i..3 * i + 3]);
        }
    }

    /// Velocity decay and the position update. A fixed node takes its fixed
    /// position and loses its velocity instead, whatever the forces did to it.
    fn integrate(&mut self) {
        let live = 3 * self.n;
        for (p, v) in self.pos[..live].iter_mut().zip(self.vel[..live].iter_mut()) {
            *v *= VELOCITY_RETAIN;
            *p += *v;
        }
        for i in (0..self.n).filter(|&i| self.fixed[i] != 0) {
            self.pos[3 * i..3 * i + 3].copy_from_slice(&self.fixed_pos[3 * i..3 * i + 3]);
            self.vel[3 * i..3 * i + 3].fill(0.0);
        }
    }

    /// Repulsion between every pair, approximated by the octree.
    fn many_body(&mut self, alpha: f32) {
        self.tree.build(&self.pos, self.n, self.cell_scale);
        for i in 0..self.n {
            let dv = self.tree.force_on(i, &self.pos, alpha, self.theta2, &mut self.rng);
            for k in 0..3 {
                self.vel[3 * i + k] += dv[k];
            }
        }
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

    fn dist(e: &Engine, a: usize, b: usize) -> f32 {
        (0..3).map(|k| (e.pos[3 * a + k] - e.pos[3 * b + k]).powi(2)).sum::<f32>().sqrt()
    }

    // Rule: a link pulls its ends towards the link distance and the pull does
    // not overshoot, however many ticks run.
    #[test]
    fn linked_pair_settles_near_the_link_distance_without_overshoot() {
        let mut e = Engine::new(2, 1).unwrap();
        e.pos.copy_from_slice(&[-30.0, 0.0, 0.0, 30.0, 0.0, 0.0]);
        e.links.copy_from_slice(&[0, 1]);
        e.prepare();
        let mut closest = f32::INFINITY;
        for _ in 0..200 {
            e.tick(0.3);
            closest = closest.min(dist(&e, 0, 1));
        }
        let last = dist(&e, 0, 1);
        assert!(closest >= 20.0, "overshot to {closest}");
        assert!(last < 40.0 && last > 25.0, "ended at {last}");
    }

    fn centroid(e: &Engine) -> [f64; 3] {
        let mut m = [0.0f64; 3];
        for i in 0..e.n {
            for k in 0..3 {
                m[k] += e.pos[3 * i + k] as f64 / e.n as f64;
            }
        }
        m
    }

    // Rule: the centre force moves the mean to the origin and nothing blows
    // up over a long run on a graph the size of the page's. d3 applies the
    // centre force before the position update, so a tick ends with a small
    // residual from the mean velocity (0.01 to 0.03 per axis in d3 itself on
    // this scene); the exact pin holds straight after the centre step.
    #[test]
    fn long_run_stays_finite_and_centred() {
        let mut e = scene(1, 100, 150);
        e.prepare();
        for _ in 0..300 {
            e.tick(0.3);
        }
        assert!(e.pos.iter().all(|v| v.is_finite()));
        assert!(centroid(&e).iter().all(|m| m.abs() < 5e-2), "centroid after a tick {:?}", centroid(&e));
        e.centre();
        assert!(centroid(&e).iter().all(|m| m.abs() < 1e-3), "centroid after centring {:?}", centroid(&e));
    }

    // Rule: the same inputs give the same bits, so a run can be reproduced.
    #[test]
    fn same_inputs_give_bit_identical_positions() {
        let run = || {
            let mut e = scene(2, 100, 150);
            e.prepare();
            for _ in 0..50 {
                e.tick(0.3);
            }
            e.pos.iter().map(|v| v.to_bits()).collect::<Vec<_>>()
        };
        assert_eq!(run(), run());
    }

    // Rule: coincident nodes are pushed apart by jiggle instead of producing
    // a division by zero.
    #[test]
    fn coincident_nodes_stay_finite() {
        let mut e = scene(3, 20, 20);
        e.pos.copy_within(0..3, 3);
        e.prepare();
        for _ in 0..20 {
            e.tick(0.3);
        }
        assert!(e.pos.iter().all(|v| v.is_finite()));
        assert!(dist(&e, 0, 1) > 0.0, "the pair was never separated");
    }

    // Rule: a link that cannot be applied (out of range, or from a node to
    // itself) is dropped, so it can never put NaN into the layout.
    #[test]
    fn unusable_links_are_ignored() {
        let mut e = scene(4, 10, 3);
        e.links.copy_from_slice(&[0, 99, 2, 2, 3, 4]);
        e.prepare();
        assert_eq!(e.active_links, 1);
        for _ in 0..10 {
            e.tick(0.3);
        }
        assert!(e.pos.iter().all(|v| v.is_finite()));
    }

    // Rule: link strength and bias follow d3's degree formulas.
    #[test]
    fn strength_and_bias_follow_degrees() {
        let mut e = Engine::new(4, 3).unwrap();
        e.pos.copy_from_slice(&[0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0]);
        e.links.copy_from_slice(&[0, 1, 0, 2, 0, 3]);
        e.prepare();
        assert_eq!(e.degree, vec![3, 1, 1, 1]);
        assert_eq!(e.strength, vec![1.0, 1.0, 1.0]);
        assert_eq!(e.bias, vec![0.75, 0.75, 0.75]);
    }

    // Rule: spare capacity changes nothing a viewer can see. An engine with room
    // to grow gives the same bits as one sized exactly, and growing the live
    // counts never moves a buffer (JS holds pointers into them).
    #[test]
    fn spare_capacity_gives_the_same_bits_as_an_exact_engine() {
        let exact = {
            let mut e = scene(8, 40, 60);
            e.prepare();
            for _ in 0..30 {
                e.tick(0.3);
            }
            e.pos.iter().map(|v| v.to_bits()).collect::<Vec<_>>()
        };
        let roomy = {
            let src = scene(8, 40, 60);
            let mut e = Engine::new(100, 200).unwrap();
            assert!(e.set_counts(40, 60));
            e.pos[..120].copy_from_slice(&src.pos);
            e.links[..120].copy_from_slice(&src.links);
            e.prepare();
            for _ in 0..30 {
                e.tick(0.3);
            }
            assert!(e.pos[120..].iter().all(|v| *v == 0.0), "a tick wrote past the live nodes");
            e.pos[..120].iter().map(|v| v.to_bits()).collect::<Vec<_>>()
        };
        assert_eq!(exact, roomy);
    }

    #[test]
    fn counts_beyond_capacity_are_refused_and_buffers_never_move() {
        let mut e = Engine::new(10, 20).unwrap();
        let (p, l) = (e.pos.as_ptr(), e.links.as_ptr());
        assert!(e.set_counts(4, 3));
        assert!(e.set_counts(10, 20));
        assert!(!e.set_counts(11, 3));
        assert!(!e.set_counts(3, 21));
        assert_eq!((e.n, e.m), (10, 20), "a refused call must leave the counts alone");
        assert!(e.set_counts(0, 0));
        assert_eq!((p, l), (e.pos.as_ptr(), e.links.as_ptr()));
    }

    // Rule: each link pulls towards its own distance, and dropping an unusable
    // link keeps every other link's distance with it.
    #[test]
    fn each_link_settles_near_its_own_distance() {
        let mut e = Engine::new(6, 4).unwrap();
        e.pos.copy_from_slice(&[0.0, 0.0, 0.0, 40.0, 0.0, 0.0, 500.0, 0.0, 0.0, 540.0, 0.0, 0.0, 900.0, 0.0, 0.0, 940.0, 0.0, 0.0]);
        // The second link is out of range and is dropped; the others keep 20, 52 and 80.
        // Repulsion holds each pair a few units beyond its distance, hence the margin.
        e.links.copy_from_slice(&[0, 1, 2, 99, 4, 5, 2, 3]);
        e.dist.copy_from_slice(&[20.0, 7.0, 52.0, 80.0]);
        e.prepare();
        assert_eq!(e.active_links, 3);
        for _ in 0..300 {
            e.tick(0.3);
        }
        assert!((dist(&e, 0, 1) - 20.0).abs() < 6.0, "pair 0-1 at {}", dist(&e, 0, 1));
        assert!((dist(&e, 4, 5) - 52.0).abs() < 6.0, "pair 4-5 at {}", dist(&e, 4, 5));
        assert!((dist(&e, 2, 3) - 80.0).abs() < 6.0, "pair 2-3 at {}", dist(&e, 2, 3));
    }

    // Rule: a fixed node does not move by more than 1e-6 over 100 ticks while
    // its neighbours do. The centre force shifts every position, so this also
    // proves the fixed position wins over it.
    #[test]
    fn a_fixed_node_stays_put_while_its_neighbours_move() {
        let mut e = scene(9, 30, 45);
        e.prepare();
        e.fixed[4] = 1;
        e.fixed_pos[12..15].copy_from_slice(&[e.pos[12], e.pos[13], e.pos[14]]);
        let (before, others_before) = ([e.pos[12], e.pos[13], e.pos[14]], e.pos[..12].to_vec());
        for _ in 0..100 {
            e.tick(0.3);
        }
        for k in 0..3 {
            assert!((e.pos[12 + k] - before[k]).abs() < 1e-6, "fixed node drifted on axis {k}");
            assert_eq!(e.vel[12 + k], 0.0);
        }
        let moved = e.pos[..12].iter().zip(&others_before).map(|(a, b)| (a - b).abs()).fold(0.0, f32::max);
        assert!(moved > 1.0, "the free neighbours never moved ({moved}), so the test proves nothing");
    }

    // Rule: like d3, a fixed position wins the moment it is set: the node jumps
    // to it on prepare, and on the next tick if it is set later.
    #[test]
    fn a_fixed_position_is_taken_up_at_once() {
        let mut e = scene(10, 10, 12);
        e.fixed[2] = 1;
        e.fixed_pos[6..9].copy_from_slice(&[7.0, -8.0, 9.0]);
        e.prepare();
        assert_eq!(&e.pos[6..9], &[7.0, -8.0, 9.0]);
        e.fixed[3] = 1;
        e.fixed_pos[9..12].copy_from_slice(&[1.0, 2.0, 3.0]);
        e.tick(0.3);
        assert_eq!(&e.pos[9..12], &[1.0, 2.0, 3.0]);
    }

    // Rule: tick_many is exactly count single ticks.
    #[test]
    fn tick_many_equals_repeated_ticks() {
        let mut a = scene(6, 60, 90);
        let mut b = scene(6, 60, 90);
        a.prepare();
        b.prepare();
        a.tick_many(0.3, 7);
        for _ in 0..7 {
            b.tick(0.3);
        }
        assert_eq!(a.pos.iter().map(|v| v.to_bits()).collect::<Vec<_>>(), b.pos.iter().map(|v| v.to_bits()).collect::<Vec<_>>());
    }
}
