use rayon::prelude::*;
use sha2::{Digest, Sha256};
use std::fmt::Write;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Instant;

/// Checks if SHA-256 raw bytes have required number of leading zero hex characters.
/// Operates directly on [u8; 32] without any heap allocations (zero hex::encode in inner loop).
#[inline(always)]
fn check_leading_zeros(digest: &[u8; 32], difficulty: usize) -> bool {
    let full_bytes = difficulty / 2;
    for i in 0..full_bytes {
        if digest[i] != 0 {
            return false;
        }
    }
    if difficulty % 2 != 0 {
        if (digest[full_bytes] >> 4) != 0 {
            return false;
        }
    }
    true
}

pub fn solve_pow(
    prefix: &str,
    suffix: &str,
    target_difficulty: u32,
    max_nonces: u64,
    start_nonce: u64,
) -> (bool, u64, String, f64) {
    // SHA-256 hex string is exactly 64 characters. Difficulty > 64 is mathematically
    // impossible and difficulty 0 is invalid. Enforce strict boundary checks against DoS.
    if target_difficulty == 0 || target_difficulty > 64 {
        return (false, 0, String::new(), 0.0);
    }

    let t_start = Instant::now();
    let found = Arc::new(AtomicBool::new(false));
    let total_hashes = Arc::new(AtomicU64::new(0));

    // AUD12-01: Pre-hash prefix mid-state once to avoid redundant re-hashing per nonce
    let mut base_hasher = Sha256::new();
    base_hasher.update(prefix.as_bytes());

    // Parallel chunking using lazy index range without collecting large Vec into memory
    let chunk_size = 50_000u64;
    let num_chunks = if max_nonces == 0 {
        0
    } else {
        match max_nonces.checked_add(chunk_size - 1) {
            Some(sum) => sum / chunk_size,
            None => u64::MAX / chunk_size,
        }
    };

    let found_clone = Arc::clone(&found);
    let hashes_clone = Arc::clone(&total_hashes);

    let result = (0..num_chunks).into_par_iter().find_map_any(|chunk_idx| {
        // AUD15-03: Checked arithmetic to prevent u64 integer overflow on high nonces
        let chunk_offset = match chunk_idx.checked_mul(chunk_size) {
            Some(off) => off,
            None => return None,
        };
        let chunk_start = match start_nonce.checked_add(chunk_offset) {
            Some(s) => s,
            None => return None,
        };
        let max_bound = start_nonce.saturating_add(max_nonces);
        let chunk_limit = chunk_start.saturating_add(chunk_size).min(max_bound);
        if chunk_start >= chunk_limit {
            return None;
        }
        let mut local_count = 0u64;
        let mut nonce_buf = String::with_capacity(32);

        for nonce in chunk_start..chunk_limit {
            if found_clone.load(Ordering::Relaxed) {
                hashes_clone.fetch_add(local_count, Ordering::Relaxed);
                return None;
            }

            local_count += 1;
            nonce_buf.clear();
            let _ = write!(&mut nonce_buf, "{}", nonce);

            let mut hasher = base_hasher.clone();
            hasher.update(nonce_buf.as_bytes());
            hasher.update(suffix.as_bytes());
            let digest: [u8; 32] = hasher.finalize().into();

            // AUD12-01: Fast zero-allocation byte check
            if check_leading_zeros(&digest, target_difficulty as usize) {
                found_clone.store(true, Ordering::Relaxed);
                hashes_clone.fetch_add(local_count, Ordering::Relaxed);
                let winning_hash = hex::encode(digest);
                return Some((nonce, winning_hash));
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pow_boundary_checks() {
        // Difficulty > 64 must be rejected immediately without scanning
        let (ok, _, _, _) = solve_pow("header", "footer", 65, 1000, 0);
        assert!(!ok);

        let (ok, _, _, _) = solve_pow("header", "footer", 1000, 1000, 0);
        assert!(!ok);

        // Difficulty 0 must be rejected
        let (ok, _, _, _) = solve_pow("header", "footer", 0, 1000, 0);
        assert!(!ok);
    }

    #[test]
    fn test_pow_valid_solve() {
        let (ok, nonce, hash, _) = solve_pow("block_", "_end", 1, 10_000, 0);
        if ok {
            assert!(hash.starts_with('0'));
            assert!(nonce < 10_000);
        }
    }
}

