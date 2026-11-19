//! A 3D force layout matching d3-force-3d, exported as plain C functions for
//! WebAssembly. State lives in one engine per module instance; JS writes
//! positions and links straight into its buffers, then calls `prepare`.
mod engine;
mod octree;
mod rng;

use engine::Engine;
use std::cell::RefCell;

thread_local! {
    static ENGINE: RefCell<Option<Engine>> = const { RefCell::new(None) };
}

fn with_engine<R>(fallback: R, f: impl FnOnce(&mut Engine) -> R) -> R {
    ENGINE.with(|cell| match cell.borrow_mut().as_mut() {
        Some(engine) => f(engine),
        None => fallback,
    })
}

/// Allocates every buffer once, for up to `node_count` nodes and `link_count`
/// links, with all of them live. `set_counts` changes the live counts without
/// allocating. Returns 1 on success and 0 on failure, in which case no engine is kept.
#[no_mangle]
pub extern "C" fn init(node_count: u32, link_count: u32) -> u32 {
    ENGINE.with(|cell| {
        // Drop the old engine first so its memory can be reused by the new one.
        *cell.borrow_mut() = None;
        match Engine::new(node_count as usize, link_count as usize) {
            Some(engine) => {
                *cell.borrow_mut() = Some(engine);
                1
            }
            None => 0,
        }
    })
}

/// Sets how many nodes and links are live. Returns 0, changing nothing, beyond
/// the capacity given to `init`; the caller then re-inits larger and copies its state over.
#[no_mangle]
pub extern "C" fn set_counts(node_count: u32, link_count: u32) -> u32 {
    with_engine(0, |e| e.set_counts(node_count as usize, link_count as usize) as u32)
}

/// x, y, z per node. Valid until the next `init`.
#[no_mangle]
pub extern "C" fn positions_ptr() -> *const f32 {
    with_engine(std::ptr::null(), |e| e.pos.as_ptr())
}

/// Two node indexes per link. Write them here before `prepare`.
#[no_mangle]
pub extern "C" fn links_ptr() -> *mut u32 {
    with_engine(std::ptr::null_mut(), |e| e.links.as_mut_ptr())
}

#[no_mangle]
pub extern "C" fn prepare() {
    with_engine((), |e| e.prepare());
}

#[no_mangle]
pub extern "C" fn tick(alpha: f32) {
    with_engine((), |e| e.tick(alpha));
}

#[no_mangle]
pub extern "C" fn tick_many(alpha: f32, count: u32) {
    with_engine((), |e| e.tick_many(alpha, count));
}

/// x, y, z velocity per node. Write NaN for a node that has none yet.
#[no_mangle]
pub extern "C" fn velocities_ptr() -> *mut f32 {
    with_engine(std::ptr::null_mut(), |e| e.vel.as_mut_ptr())
}

/// One byte per node: 1 when the node is fixed at its `fixed_pos`.
#[no_mangle]
pub extern "C" fn fixed_ptr() -> *mut u8 {
    with_engine(std::ptr::null_mut(), |e| e.fixed.as_mut_ptr())
}

/// x, y, z per node: where a fixed node is held.
#[no_mangle]
pub extern "C" fn fixed_pos_ptr() -> *mut f32 {
    with_engine(std::ptr::null_mut(), |e| e.fixed_pos.as_mut_ptr())
}

/// One f32 per node: forest depth, or NaN for a node outside the forest.
#[no_mangle]
pub extern "C" fn depth_ptr() -> *mut f32 {
    with_engine(std::ptr::null_mut(), |e| e.depth.as_mut_ptr())
}

/// One f32 per link: its rest length. Starts at 30.
#[no_mangle]
pub extern "C" fn link_dist_ptr() -> *mut f32 {
    with_engine(std::ptr::null_mut(), |e| e.dist.as_mut_ptr())
}

/// Call after writing links or distances. Keeps positions and velocities.
#[no_mangle]
pub extern "C" fn refresh_links() {
    with_engine((), |e| e.refresh_links());
}

/// Fixed nodes take their fixed position, non-finite positions get d3's
/// starting spiral and non-finite velocities become zero.
#[no_mangle]
pub extern "C" fn place_unplaced() {
    with_engine((), |e| e.place_unplaced());
}

#[no_mangle]
pub extern "C" fn set_params(velocity_decay: f64, alpha_decay: f64, alpha_target: f64, alpha_min: f64) {
    with_engine((), |e| {
        e.set_velocity_decay(velocity_decay);
        e.alpha_decay = alpha_decay;
        e.alpha_target = alpha_target;
        e.alpha_min = alpha_min;
    });
}

#[no_mangle]
pub extern "C" fn set_alpha(alpha: f64) {
    with_engine((), |e| e.alpha = alpha);
}

#[no_mangle]
pub extern "C" fn get_alpha() -> f64 {
    with_engine(0.0, |e| e.alpha)
}

/// Turns the forest depth force on (non-zero `on`) or off, with forest.ts's options.
#[no_mangle]
pub extern "C" fn set_ring(on: u32, spacing: f32, offset: f32, strength: f32, flatten: f32) {
    with_engine((), |e| {
        e.ring = engine::Ring { spacing, offset, strength, flatten };
        e.ring_on = on != 0;
    });
}

/// Applies only the depth force, at `alpha`. For tests against forestDepthForce.
#[no_mangle]
pub extern "C" fn apply_depth(alpha: f32) {
    with_engine((), |e| e.apply_depth(alpha));
}

/// One d3 step: alpha moves towards its target, forces run, positions update.
/// Returns 0 once alpha is below its minimum, 1 while the layout should keep ticking.
#[no_mangle]
pub extern "C" fn step() -> u32 {
    with_engine(0, |e| e.step() as u32)
}

/// `count` steps in a row, none skipped (the warm-up). Returns the last step's result.
#[no_mangle]
pub extern "C" fn step_many(count: u32) -> u32 {
    with_engine(0, |e| (0..count).fold(true, |_, _| e.step()) as u32)
}
