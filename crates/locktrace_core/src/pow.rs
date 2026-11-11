use rayon::prelude::*;
use sha2::{Digest, Sha256};
use std::fmt::Write;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Instant;

pub fn solve_pow(
    prefix: &str,
    suffix: &str,
    target_difficulty: u32,
    max_nonces: u64,
) -> (bool, u64, String, f64) {
    let t_start = Instant::now();
    let target_prefix = "0".repeat(target_difficulty as usize);
    let found = Arc::new(AtomicBool::new(false));
    let total_hashes = Arc::new(AtomicU64::new(0));

    // Parallel chunking using lazy index range without collecting large Vec into memory
    let chunk_size = 50_000u64;
    let num_chunks = if max_nonces == 0 {
        0
    } else {
        (max_nonces + chunk_size - 1) / chunk_size
    };

    let found_clone = Arc::clone(&found);
    let hashes_clone = Arc::clone(&total_hashes);

    let result = (0..num_chunks).into_par_iter().find_map_any(|chunk_idx| {
        let base = chunk_idx * chunk_size;
        let limit = (base + chunk_size).min(max_nonces);
        let mut local_count = 0u64;
        let mut buffer = String::with_capacity(prefix.len() + 32 + suffix.len());

        for nonce in base..limit {
            if found_clone.load(Ordering::Relaxed) {
                hashes_clone.fetch_add(local_count, Ordering::Relaxed);
                return None;
            }

            local_count += 1;
            buffer.clear();
            buffer.push_str(prefix);
            let _ = write!(&mut buffer, "{}", nonce);
            buffer.push_str(suffix);

            let hash = hex::encode(Sha256::digest(buffer.as_bytes()));
            if hash.starts_with(&target_prefix) {
                found_clone.store(true, Ordering::Relaxed);
                hashes_clone.fetch_add(local_count, Ordering::Relaxed);
                return Some((nonce, hash));
            }
        }

        hashes_clone.fetch_add(local_count, Ordering::Relaxed);
        None
    });

    let elapsed = t_start.elapsed().as_secs_f64().max(0.0001);
    let actual_hashes = total_hashes.load(Ordering::Relaxed) as f64;
    let hashrate = actual_hashes / elapsed;

    match result {
        Some((winning_nonce, winning_hash)) => (true, winning_nonce, winning_hash, hashrate),
        None => (false, 0, String::new(), hashrate),
    }
}

