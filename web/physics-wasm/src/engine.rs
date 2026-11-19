//! The force layout. Same forces, order and constants as d3-force-3d with the
//! page's settings; see physics.ts in web/src/perf for what those are.
use crate::octree::Octree;
use crate::rng::Lcg;

/// d3 multiplies velocity by 1 - velocityDecay; the page sets 0.85, so 0.15 is kept.
const VELOCITY_RETAIN: f32 = 0.15;
const LINK_DISTANCE: f32 = 30.0;
/// d3's default theta is 0.9.
const THETA: f32 = 0.9;
/// Stored in `depth` for a node that is not part of the metaphor forest.
pub const NO_DEPTH: i32 = i32::MIN;

/// Constants of the forest depth force, as forestDepthForce takes them.
#[derive(Clone, Copy, Default)]
pub struct Ring {
    pub spacing: f32,
    pub offset: f32,
    pub strength: f32,
    pub flatten: f32,
}

fn zeroed<T: Clone + Default>(len: usize) -> Option<Vec<T>> {
    let mut v = Vec::new();
    v.try_reserve_exact(len).ok()?;
    v.resize(len, T::default());
    Some(v)
}

fn filled_with<T: Clone>(len: usize, value: T) -> Option<Vec<T>> {
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
    /// Forest depth per node, or NO_DEPTH. Depth 0 marks the root of the rings.
    pub depth: Vec<i32>,
    /// d3's alpha schedule. f64 like d3, so the step that crosses `alpha_min` matches.
    pub alpha: f64,
    pub alpha_min: f64,
    pub alpha_decay: f64,
    pub alpha_target: f64,
    /// Share of velocity kept each tick: 1 - velocity decay.
    pub velocity_retain: f32,
    pub ring: Ring,
    pub ring_on: bool,
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
            dist: filled_with(m, LINK_DISTANCE)?,
            depth: filled_with(n, NO_DEPTH)?,
            alpha: 1.0,
            alpha_min: 0.001,
            // d3's default: alpha reaches alpha_min after 300 steps.
            alpha_decay: 1.0 - 0.001f64.powf(1.0 / 300.0),
            alpha_target: 0.0,
            velocity_retain: VELOCITY_RETAIN,
            ring: Ring::default(),
            ring_on: false,
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

    /// Call after JS has written the links and starting positions. Equivalent to
    /// `refresh_links`, zeroing every velocity, then `place_unplaced`.
    pub fn prepare(&mut self) {
        self.refresh_links();
        self.vel[..3 * self.n].iter_mut().for_each(|v| *v = 0.0);
        self.place_unplaced();
    }

    /// Drops links that cannot apply (out of range, or a node to itself), then
    /// derives degrees, strengths and biases as d3's link force does. Positions
    /// and velocities are left alone, so the graph can change while it runs.
    pub fn refresh_links(&mut self) {
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
    }

    /// d3's `initializeNodes` for nodes that lack a state: a fixed node takes its
    /// fixed position, a node with a non-finite position gets d3's starting
    /// spiral, and a non-finite velocity becomes zero. Everything else is kept.
    pub fn place_unplaced(&mut self) {
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
        for i in 0..self.n {
            if self.vel[3 * i..3 * i + 3].iter().any(|v| !v.is_finite()) {
                self.vel[3 * i..3 * i + 3].fill(0.0);
            }
        }
    }

    /// One step with d3's force order: link, many-body, centre, then velocity
    /// decay and the position update.
    pub fn tick(&mut self, alpha: f32) {
        self.link_force(alpha);
        self.many_body(alpha);
        self.centre();
        self.apply_depth(alpha);
        self.integrate();
    }

    pub fn set_velocity_decay(&mut self, decay: f64) {
        self.velocity_retain = (1.0 - decay) as f32;
    }

    /// One step of d3's simulation: alpha moves towards its target, the forces
    /// run at the new alpha, then positions update. Returns false once alpha is
    /// below `alpha_min`, when d3 stops its timer; the caller should stop calling.
    pub fn step(&mut self) -> bool {
        self.alpha += (self.alpha_target - self.alpha) * self.alpha_decay;
        self.tick(self.alpha as f32);
        self.alpha >= self.alpha_min
    }

    pub fn tick_many(&mut self, alpha: f32, count: u32) {
        for _ in 0..count {
            self.tick(alpha);
        }
    }

    /// forestDepthForce from forest.ts, same maths: pulls each node that has a
    /// depth towards a sphere of radius offset + depth * spacing around the first
    /// depth-0 node, and flattens z towards that node's plane. d3 runs it after
    /// the centre force, as the app adds it last.
    pub fn apply_depth(&mut self, alpha: f32) {
        if !self.ring_on {
            return;
        }
        let Some(root) = (0..self.n).find(|&i| self.depth[i] == 0) else { return };
        let r = [self.pos[3 * root], self.pos[3 * root + 1], self.pos[3 * root + 2]];
        let Ring { spacing, offset, strength, flatten } = self.ring;
        for i in 0..self.n {
            let d = self.depth[i];
            if d == NO_DEPTH || d == 0 {
                continue;
            }
            let dx = [self.pos[3 * i] - r[0], self.pos[3 * i + 1] - r[1], self.pos[3 * i + 2] - r[2]];
            let mut dist = (dx[0] * dx[0] + dx[1] * dx[1] + dx[2] * dx[2]).sqrt();
            if dist == 0.0 {
                dist = 1e-3;
            }
            let k = ((offset + d as f32 * spacing - dist) / dist) * strength * alpha;
            self.vel[3 * i] += dx[0] * k;
            self.vel[3 * i + 1] += dx[1] * k;
            self.vel[3 * i + 2] += dx[2] * k - dx[2] * flatten * strength * alpha;
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
            *v *= self.velocity_retain;
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
mod alloc_count {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::cell::Cell;

    thread_local! {
        static COUNT: Cell<usize> = const { Cell::new(0) };
    }

    /// Counts allocations on the calling thread, so parallel tests do not disturb each other.
    pub struct Counting;

    unsafe impl GlobalAlloc for Counting {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            COUNT.with(|c| c.set(c.get() + 1));
            System.alloc(layout)
        }
        unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
            System.dealloc(ptr, layout)
        }
        unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
            COUNT.with(|c| c.set(c.get() + 1));
            System.realloc(ptr, layout, new_size)
        }
    }

    pub fn get() -> usize {
        COUNT.with(|c| c.get())
    }
}

#[cfg(test)]
#[global_allocator]
static ALLOCATOR: alloc_count::Counting = alloc_count::Counting;

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

    fn ring_scene() -> Engine {
        let mut e = Engine::new(5, 0).unwrap();
        // Root, a ring-1 node inside its ring, a ring-1 node outside it, a node
        // with no depth, and a ring-2 node.
        e.pos.copy_from_slice(&[10.0, 20.0, 30.0, 12.0, 20.0, 30.0, 10.0, 20.0, 230.0, 40.0, 50.0, 60.0, 10.0, 120.0, 30.0]);
        e.depth.copy_from_slice(&[0, 1, 1, NO_DEPTH, 2]);
        e.ring = Ring { spacing: 52.0, offset: 22.0, strength: 0.08, flatten: 0.6 };
        e.ring_on = true;
        e
    }

    // Rule: the forest depth force pulls a node of depth d towards radius
    // offset + d * spacing around the depth-0 node, flattens z towards the
    // root's plane, and leaves the root and nodes with no depth alone.
    #[test]
    fn depth_force_pulls_forest_nodes_to_their_ring_and_ignores_the_rest() {
        let mut e = ring_scene();
        e.apply_depth(0.5);
        let v = |i: usize| [e.vel[3 * i], e.vel[3 * i + 1], e.vel[3 * i + 2]];
        assert_eq!(v(0), [0.0; 3], "the root is not moved");
        assert_eq!(v(3), [0.0; 3], "a node with no depth is not moved");
        // Node 1 sits 2 from the root, ring radius 74: pushed outward along +x.
        let want_k = ((22.0 + 52.0 - 2.0) / 2.0) * 0.08 * 0.5;
        assert!((v(1)[0] - 2.0 * want_k).abs() < 1e-3, "got {:?}", v(1));
        assert_eq!(v(1)[1], 0.0);
        // Node 2 sits 200 away, outside radius 74: pulled back along -z, plus the flattening.
        let k2 = ((74.0 - 200.0) / 200.0) * 0.08 * 0.5;
        assert!((v(2)[2] - (200.0 * k2 - 200.0 * 0.6 * 0.08 * 0.5)).abs() < 1e-3, "got {:?}", v(2));
        // Node 4 is depth 2: ring radius 22 + 104 = 126, and it sits 100 away.
        assert!(v(4)[1] > 0.0, "a node inside its ring is pushed out");
    }

    // Rule: with the force off, or with no depth-0 node, nothing moves.
    #[test]
    fn depth_force_does_nothing_when_off_or_rootless() {
        let mut e = ring_scene();
        e.ring_on = false;
        e.apply_depth(0.5);
        assert!(e.vel.iter().all(|v| *v == 0.0));
        e.ring_on = true;
        e.depth[0] = NO_DEPTH;
        e.apply_depth(0.5);
        assert!(e.vel.iter().all(|v| *v == 0.0));
    }

    fn app_settings(e: &mut Engine) {
        e.set_velocity_decay(0.85);
        e.alpha_decay = 0.005;
    }

    // Rule: alpha decays towards the target by the alpha decay each step, as d3
    // does before it runs the forces, and step reports false on the step that
    // takes it below alpha min. With the app's settings that is step 1379, and
    // a step after it keeps reporting false.
    #[test]
    fn alpha_decays_as_d3_and_reports_when_it_falls_below_the_minimum() {
        let mut e = scene(12, 20, 30);
        app_settings(&mut e);
        e.prepare();
        let mut want = 1.0f64;
        let mut running = 0;
        while e.step() {
            running += 1;
            want += (0.0 - want) * 0.005;
            assert_eq!(e.alpha, want, "alpha after {running} steps");
            assert!(running < 5000, "never settled");
        }
        assert_eq!(running + 1, 1379);
        assert!(e.alpha < 0.001 && e.alpha > 0.00099);
    }

    // Rule: a non-zero alpha target holds alpha above the minimum for as long
    // as it is set (d3's drag keeps the simulation hot this way).
    #[test]
    fn alpha_target_keeps_the_simulation_running() {
        let mut e = scene(13, 10, 12);
        app_settings(&mut e);
        e.prepare();
        e.alpha_target = 0.3;
        for _ in 0..3000 {
            assert!(e.step());
        }
        assert!((e.alpha - 0.3).abs() < 1e-6);
    }

    // Rule: the velocity decay the app sets (0.85) leaves 0.15 of the velocity, as before.
    #[test]
    fn velocity_decay_defaults_to_the_apps_setting() {
        let mut e = Engine::new(1, 0).unwrap();
        assert_eq!(e.velocity_retain, 0.15);
        e.set_velocity_decay(0.6);
        assert!((e.velocity_retain - 0.4).abs() < 1e-7);
    }

    // Rule: a step at alpha a is the same as a tick at alpha a, the alpha schedule being the only difference.
    #[test]
    fn step_runs_the_same_forces_as_tick() {
        let mut a = scene(14, 30, 40);
        let mut b = scene(14, 30, 40);
        a.prepare();
        b.prepare();
        a.alpha_decay = 0.0;
        a.alpha = 0.3;
        a.step();
        b.tick(0.3);
        assert_eq!(a.pos.iter().map(|v| v.to_bits()).collect::<Vec<_>>(), b.pos.iter().map(|v| v.to_bits()).collect::<Vec<_>>());
    }

    // Rule: a step never allocates. Every buffer is made up front, so the
    // wasm heap cannot grow, and views onto it cannot detach, while ticking.
    #[test]
    fn step_allocates_nothing() {
        let mut e = scene(15, 120, 180);
        e.pos.copy_within(0..3, 3); // a coincident pair exercises the chained leaf
        e.fixed[7] = 1;
        e.fixed_pos[21..24].copy_from_slice(&[1.0, 2.0, 3.0]);
        e.depth[0] = 0;
        e.depth[1..30].iter_mut().for_each(|d| *d = 1);
        e.ring = Ring { spacing: 52.0, offset: 22.0, strength: 0.08, flatten: 0.6 };
        e.ring_on = true;
        e.prepare();
        e.step(); // warm-up in case anything is allocated lazily
        let before = alloc_count::get();
        for _ in 0..25 {
            e.step();
        }
        e.refresh_links();
        assert_eq!(alloc_count::get() - before, 0, "allocations during steps");
    }

    // Rule: when the graph changes, links are re-derived and only the nodes
    // without a position are placed: every other position and velocity stays
    // exactly as it was, so a growing graph does not jolt.
    #[test]
    fn refreshing_links_and_placing_new_nodes_keeps_existing_state() {
        let mut e = scene(16, 12, 14);
        e.prepare();
        for _ in 0..5 {
            e.step();
        }
        let (pos, vel) = (e.pos.clone(), e.vel.clone());
        e.pos[3 * 11..3 * 11 + 3].fill(f32::NAN);
        e.vel[3 * 11..3 * 11 + 3].fill(f32::NAN);
        e.links[0] = 2;
        e.links[1] = 3;
        e.refresh_links();
        e.place_unplaced();
        assert_eq!(e.pos[..33], pos[..33]);
        assert_eq!(e.vel[..33], vel[..33]);
        assert_eq!(&e.vel[33..36], &[0.0; 3]);
        // d3's starting spiral for node index 11.
        let radius = 10.0 * (0.5f32 + 11.0).cbrt();
        let roll = 11.0 * core::f32::consts::PI * (3.0 - 5.0f32.sqrt());
        assert!((e.pos[34] - radius * roll.cos()).abs() < 1e-4);
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
