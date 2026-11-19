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

/// Allocates every buffer for `node_count` nodes and `link_count` links.
/// Returns 1 on success and 0 on failure, in which case no engine is kept.
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
