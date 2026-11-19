//! Barnes-Hut octree in a preallocated arena of flat arrays, rebuilt every tick
//! with no allocation. Mirrors d3-octree and the many-body force in
//! d3-force-3d: a cube of power-of-two side anchored at the floor of the
//! minimum corner, leaves split at midpoints, coincident points chained.
use crate::rng::Lcg;

pub const NONE: u32 = u32::MAX;
/// Every node carries the same charge: the page keeps d3's default of -30.
pub const CHARGE: f32 = -30.0;
/// Two distinct floats can sit arbitrarily close, so splitting stops here and
/// the remaining points are chained like coincident ones. This also bounds the
/// arena: one insertion adds at most MAX_DEPTH internal nodes and one leaf.
const MAX_DEPTH: usize = 32;
/// d3's distanceMin is 1, so distanceMin2 is 1 as well.
const DISTANCE_MIN2: f32 = 1.0;

pub struct Octree {
    root: u32,
    pub nodes_used: usize,
    capacity: usize,
    /// Eight child indexes per node; only internal nodes use them.
    children: Vec<u32>,
    /// For a leaf the first point stored in it, for an internal node NONE.
    first: Vec<u32>,
    /// Cell width: the extent along x that d3's Barnes-Hut test uses.
    width: Vec<f32>,
    /// Centre of mass, three per node.
    com: Vec<f32>,
    /// Total charge of the cell.
    value: Vec<f32>,
    /// Next point in a coincident chain, per point.
    next: Vec<u32>,
    stack: Vec<u32>,
}

fn zeroed<T: Clone + Default>(len: usize) -> Option<Vec<T>> {
    let mut v = Vec::new();
    v.try_reserve_exact(len).ok()?;
    v.resize(len, T::default());
    Some(v)
}

impl Octree {
    /// Sized for the worst case so `build` never allocates. None if the size
    /// overflows or cannot be reserved.
    pub fn with_capacity(points: usize) -> Option<Octree> {
        let capacity = points.checked_mul(MAX_DEPTH)?.checked_add(8)?;
        Some(Octree {
            root: NONE,
            nodes_used: 0,
            capacity,
            children: zeroed(capacity.checked_mul(8)?)?,
            first: zeroed(capacity)?,
            width: zeroed(capacity)?,
            com: zeroed(capacity.checked_mul(3)?)?,
            value: zeroed(capacity)?,
            next: zeroed(points)?,
            stack: zeroed(MAX_DEPTH * 8 + 8)?,
        })
    }

    fn new_node(&mut self, width: f32, first: u32) -> u32 {
        let id = self.nodes_used;
        debug_assert!(id < self.capacity);
        self.nodes_used += 1;
        self.first[id] = first;
        self.width[id] = width;
        if first == NONE {
            self.children[id * 8..id * 8 + 8].fill(NONE);
        }
        id as u32
    }

    /// Rebuilds the tree over the first `n` points of `pos` (x, y, z per point)
    /// and accumulates charge. `n` is at most the capacity the tree was made for.
    /// `cell_scale` multiplies an internal cell's summed charge.
    pub fn build(&mut self, pos: &[f32], n: usize, cell_scale: f32) {
        debug_assert!(n <= self.next.len());
        self.nodes_used = 0;
        self.root = NONE;
        if n == 0 {
            return;
        }
        let mut lo = [f32::INFINITY; 3];
        let mut hi = [f32::NEG_INFINITY; 3];
        for p in pos.chunks_exact(3).take(n) {
            for k in 0..3 {
                lo[k] = lo[k].min(p[k]);
                hi[k] = hi[k].max(p[k]);
            }
        }
        // d3 starts from a unit cube on integer corners and doubles until every
        // point is inside; power-of-two sides keep midpoints exact.
        let origin = [lo[0].floor(), lo[1].floor(), lo[2].floor()];
        let mut side = 1.0f32;
        for _ in 0..120 {
            if (0..3).all(|k| hi[k] < origin[k] + side) {
                break;
            }
            side *= 2.0;
        }
        for i in 0..n {
            self.insert(i as u32, pos, origin, side);
        }
        self.accumulate(self.root, pos, cell_scale);
    }

    fn insert(&mut self, p: u32, pos: &[f32], origin: [f32; 3], side: f32) {
        let pi = p as usize;
        let pt = [pos[3 * pi], pos[3 * pi + 1], pos[3 * pi + 2]];
        self.next[pi] = NONE;
        if self.root == NONE {
            self.root = self.new_node(side, p);
            return;
        }
        let (mut cell, mut w) = (origin, side);
        let mut node = self.root;
        let mut parent = NONE;
        let mut slot = 0usize;
        let mut depth = 0usize;
        // Walk down to the leaf, or the empty slot, where the point belongs.
        while self.first[node as usize] == NONE {
            let h = w * 0.5;
            let oct = octant(pt, cell, h);
            narrow(&mut cell, pt, h);
            w = h;
            parent = node;
            slot = oct;
            let child = self.children[node as usize * 8 + oct];
            if child == NONE {
                let leaf = self.new_node(w, p);
                self.children[node as usize * 8 + oct] = leaf;
                return;
            }
            node = child;
            depth += 1;
        }
        // `node` is a leaf in the cell (cell, w), attached at parent[slot].
        loop {
            let q = self.first[node as usize] as usize;
            let same = pos[3 * q] == pt[0] && pos[3 * q + 1] == pt[1] && pos[3 * q + 2] == pt[2];
            if same || depth >= MAX_DEPTH {
                self.next[pi] = q as u32;
                self.first[node as usize] = p;
                return;
            }
            let inner = self.new_node(w, NONE);
            if parent == NONE {
                self.root = inner;
            } else {
                self.children[parent as usize * 8 + slot] = inner;
            }
            let h = w * 0.5;
            let new_oct = octant(pt, cell, h);
            let old_oct = octant([pos[3 * q], pos[3 * q + 1], pos[3 * q + 2]], cell, h);
            narrow(&mut cell, pt, h);
            w = h;
            self.width[node as usize] = h;
            self.children[inner as usize * 8 + old_oct] = node;
            if new_oct != old_oct {
                let leaf = self.new_node(h, p);
                self.children[inner as usize * 8 + new_oct] = leaf;
                return;
            }
            parent = inner;
            slot = new_oct;
            depth += 1;
        }
    }

    /// Post-order: leaves take their point's position and the charge of every
    /// chained point; internal cells take the |charge|-weighted centre.
    fn accumulate(&mut self, node: u32, pos: &[f32], cell_scale: f32) {
        let nd = node as usize;
        let head = self.first[nd];
        if head != NONE {
            let mut count = 0.0f32;
            let mut q = head;
            while q != NONE {
                count += 1.0;
                q = self.next[q as usize];
            }
            let h = head as usize;
            self.com[3 * nd..3 * nd + 3].copy_from_slice(&pos[3 * h..3 * h + 3]);
            self.value[nd] = CHARGE * count;
            return;
        }
        let (mut sum, mut weight) = (0.0f32, 0.0f32);
        let mut c = [0.0f32; 3];
        for k in 0..8 {
            let child = self.children[nd * 8 + k];
            if child == NONE {
                continue;
            }
            self.accumulate(child, pos, cell_scale);
            let ch = child as usize;
            let v = self.value[ch];
            let a = v.abs();
            if a != 0.0 {
                sum += v;
                weight += a;
                for d in 0..3 {
                    c[d] += a * self.com[3 * ch + d];
                }
            }
        }
        if weight > 0.0 {
            for d in 0..3 {
                self.com[3 * nd + d] = c[d] / weight;
            }
            self.value[nd] = sum * cell_scale;
        } else {
            self.com[3 * nd..3 * nd + 3].fill(0.0);
            self.value[nd] = 0.0;
        }
    }

    /// Number of points reachable from the root, counting coincident chains.
    #[cfg(test)]
    pub fn points_reachable(&self) -> usize {
        let mut seen = 0;
        let mut stack = vec![self.root];
        while let Some(node) = stack.pop() {
            if node == NONE {
                continue;
            }
            let head = self.first[node as usize];
            if head == NONE {
                stack.extend_from_slice(&self.children[node as usize * 8..node as usize * 8 + 8]);
            } else {
                let mut q = head;
                while q != NONE {
                    seen += 1;
                    q = self.next[q as usize];
                }
            }
        }
        seen
    }

    /// Velocity change on point `i` from every other point, as d3's `apply`.
    pub fn force_on(&mut self, i: usize, pos: &[f32], alpha: f32, theta2: f32, rng: &mut Lcg) -> [f32; 3] {
        let mut dv = [0.0f32; 3];
        if self.root == NONE {
            return dv;
        }
        let p = [pos[3 * i], pos[3 * i + 1], pos[3 * i + 2]];
        let mut len = 1;
        self.stack[0] = self.root;
        while len > 0 {
            len -= 1;
            let nd = self.stack[len] as usize;
            let value = self.value[nd];
            if value == 0.0 {
                continue;
            }
            let mut d = [self.com[3 * nd] - p[0], self.com[3 * nd + 1] - p[1], self.com[3 * nd + 2] - p[2]];
            let w = self.width[nd];
            let mut l = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
            let head = self.first[nd];
            // Far enough to treat the whole cell as one body. d3 writes this as
            // w * w / theta2 < l; the product form also works for theta 0.
            if w * w < theta2 * l {
                separate(&mut d, &mut l, rng);
                let k = value * alpha / l;
                for a in 0..3 {
                    dv[a] += d[a] * k;
                }
                continue;
            }
            if head == NONE {
                // Eight pushes in reverse, so child 0 is visited first as in d3.
                for k in (0..8).rev() {
                    let child = self.children[nd * 8 + k];
                    if child != NONE {
                        self.stack[len] = child;
                        len += 1;
                    }
                }
                continue;
            }
            if head as usize != i || self.next[head as usize] != NONE {
                separate(&mut d, &mut l, rng);
            }
            let mut q = head;
            while q != NONE {
                if q as usize != i {
                    let k = CHARGE * alpha / l;
                    for a in 0..3 {
                        dv[a] += d[a] * k;
                    }
                }
                q = self.next[q as usize];
            }
        }
        dv
    }
}

/// d3 pushes coincident components apart with jiggle and limits the force of
/// very close pairs.
fn separate(d: &mut [f32; 3], l: &mut f32, rng: &mut Lcg) {
    for a in 0..3 {
        if d[a] == 0.0 {
            d[a] = rng.jiggle();
            *l += d[a] * d[a];
        }
    }
    if *l < DISTANCE_MIN2 {
        *l = (DISTANCE_MIN2 * *l).sqrt();
    }
}

fn octant(pt: [f32; 3], cell: [f32; 3], h: f32) -> usize {
    let right = pt[0] >= cell[0] + h;
    let bottom = pt[1] >= cell[1] + h;
    let deep = pt[2] >= cell[2] + h;
    (deep as usize) << 2 | (bottom as usize) << 1 | right as usize
}

fn narrow(cell: &mut [f32; 3], pt: [f32; 3], h: f32) {
    for a in 0..3 {
        if pt[a] >= cell[a] + h {
            cell[a] += h;
        }
    }
}
