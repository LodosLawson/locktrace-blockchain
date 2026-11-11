use rayon::prelude::*;
use sha2::{Digest, Sha256};
use std::sync::atomic::{AtomicBool, Ordering};
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

    // Parallel chunking using Rayon
    let chunk_size = 50_000u64;
    let chunks: Vec<u64> = (0..max_nonces).step_by(chunk_size as usize).collect();

    let result = chunks.into_par_iter().find_map_any(|base| {
        if found.load(Ordering::Relaxed) {
            return None;
        }

        let limit = (base + chunk_size).min(max_nonces);
        let mut buffer = String::with_capacity(prefix.len() + 20 + suffix.len());

        for nonce in base..limit {
            if found.load(Ordering::Relaxed) {
                return None;
            }

            buffer.clear();
            buffer.push_str(prefix);
            buffer.push_str(&nonce.to_string());
            buffer.push_str(suffix);

            let hash = hex::encode(Sha256::digest(buffer.as_bytes()));
            if hash.starts_with(&target_prefix) {
                found.store(true, Ordering::Relaxed);
                return Some((nonce, hash));
            }
        }
        None
    });

    let elapsed = t_start.elapsed().as_secs_f64().max(0.0001);
    let estimated_hashes = if result.is_some() {
        result.as_ref().unwrap().0 as f64
    } else {
        max_nonces as f64
    };
    let hashrate = estimated_hashes / elapsed;

    match result {
        Some((winning_nonce, winning_hash)) => (true, winning_nonce, winning_hash, hashrate),
        None => (false, 0, String::new(), hashrate),
    }
}

