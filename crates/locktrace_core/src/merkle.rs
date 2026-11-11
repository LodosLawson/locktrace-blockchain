use sha2::{Digest, Sha256};

/// Computes canonical LockTrace Merkle root from transaction hash list.
pub fn compute_merkle_root(tx_hashes: &[String]) -> String {
    if tx_hashes.is_empty() {
        return "0".repeat(64);
    }

    let mut current_level: Vec<String> = tx_hashes
        .iter()
        .map(|h| h.trim().to_ascii_lowercase())
        .collect();

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

    current_level[0].clone()
}

/// Verifies an SPV Merkle inclusion proof against a block Merkle root in microseconds.
pub fn verify_spv_proof(
    target_hash: &str,
    merkle_root: &str,
    proof_steps: &[(String, String)],
) -> bool {
    let mut current = target_hash.trim().to_ascii_lowercase();
    for (dir, sibling) in proof_steps {
        let sib = sibling.trim().to_ascii_lowercase();
        let combined = if dir.eq_ignore_ascii_case("left") {
            format!("{}{}", sib, current)
        } else {
            format!("{}{}", current, sib)
        };
        current = hex::encode(Sha256::digest(combined.as_bytes()));
    }
    current.eq_ignore_ascii_case(merkle_root.trim())
}

