use sha2::{Digest, Sha256};
use std::collections::HashSet;

/// Computes canonical LockTrace Merkle root from transaction hash list.
/// Hardened against CVE-2012-2459 (Merkle tree collision via duplicate/odd leaves).
pub fn compute_merkle_root(tx_hashes: &[String]) -> Result<String, String> {
    if tx_hashes.is_empty() {
        return Ok("0".repeat(64));
    }

    let mut clean = Vec::with_capacity(tx_hashes.len());
    let mut unique_check = HashSet::with_capacity(tx_hashes.len());

    for h in tx_hashes {
        let trimmed = h.trim().to_ascii_lowercase();
        if trimmed.len() != 64 || !trimmed.chars().all(|c| c.is_ascii_hexdigit()) {
            return Err("Invalid transaction hash format in Merkle tree".to_string());
        }
        if !unique_check.insert(trimmed.clone()) {
            return Err("CVE-2012-2459: Duplicate transaction hashes in block".to_string());
        }
        clean.push(trimmed);
    }

    let mut current_level = clean;
    while current_level.len() > 1 {
        let mut next_level = Vec::with_capacity((current_level.len() + 1) / 2);
        for chunk in current_level.chunks(2) {
            let left = &chunk[0];
            let right = if chunk.len() > 1 { &chunk[1] } else { &chunk[0] };
            let combined = format!("{}{}", left, right);
            let digest = Sha256::digest(combined.as_bytes());
            next_level.push(hex::encode(digest));
        }
        current_level = next_level;
    }

    Ok(current_level[0].clone())
}

/// Verifies an SPV Merkle inclusion proof against a block Merkle root in microseconds.
/// Validates hash lengths, enforces strict directions, and handles single-tx blocks (LT-MRK-01).
pub fn verify_spv_proof(
    target_hash: &str,
    merkle_root: &str,
    proof_steps: &[(String, String)],
) -> bool {
    let target_clean = target_hash.trim().to_ascii_lowercase();
    let root_clean = merkle_root.trim().to_ascii_lowercase();

    if target_clean.len() != 64 || root_clean.len() != 64 {
        return false;
    }
    if !target_clean.chars().all(|c| c.is_ascii_hexdigit()) || !root_clean.chars().all(|c| c.is_ascii_hexdigit()) {
        return false;
    }

    if proof_steps.is_empty() {
        // In single-transaction blocks, leaf == root (proof path is empty)
        return target_clean == root_clean;
    }

    let mut current = target_clean;
    for (dir, sibling) in proof_steps {
        let sib = sibling.trim().to_ascii_lowercase();
        if sib.len() != 64 || !sib.chars().all(|c| c.is_ascii_hexdigit()) {
            return false;
        }

        let combined = if dir.eq_ignore_ascii_case("left") {
            format!("{}{}", sib, current)
        } else if dir.eq_ignore_ascii_case("right") {
            format!("{}{}", current, sib)
        } else {
            return false;
        };
        current = hex::encode(Sha256::digest(combined.as_bytes()));
    }

    current.eq_ignore_ascii_case(&root_clean)
}

