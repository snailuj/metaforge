//! The linear congruential generator d3-force-3d uses for jiggle, so a
//! coincident pair is pushed apart the same way and runs are repeatable.

pub struct Lcg(u32);

impl Lcg {
    /// d3 starts its generator at 1.
    pub fn new() -> Self {
        Lcg(1)
    }

    fn next(&mut self) -> f32 {
        self.0 = self.0.wrapping_mul(1_664_525).wrapping_add(1_013_904_223);
        self.0 as f32 / 4_294_967_296.0
    }

    /// A tiny offset in (-5e-7, 5e-7], used where d3 would divide by zero.
    pub fn jiggle(&mut self) -> f32 {
        (self.next() - 0.5) * 1e-6
    }
}
