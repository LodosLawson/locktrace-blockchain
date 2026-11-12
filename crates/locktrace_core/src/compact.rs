use serde::{Deserialize, Serialize};

/// Maximum byte size allowed for a serialized compact block payload (2 MB)
pub const MAX_COMPACT_BLOCK_BYTES: usize = 2 * 1024 * 1024;
/// Maximum number of transactions allowed in a single block
pub const MAX_BLOCK_TRANSACTIONS: u32 = 5_000;
/// Maximum allowable string length for block header metadata fields
pub const MAX_FIELD_LEN: usize = 256;

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
pub struct CompactHeader {
    pub index: u64,
    pub version: u32,
    pub merkle_root: String,
    pub miner: String,
    pub previous_hash: String,
    pub timestamp: f64,
    pub nonce: u64,
    pub difficulty: u32,
    pub hash: String,
}

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
pub struct CompactPrefilledTx {
    pub index: u32,
    pub raw_json: String,
}

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
pub struct NativeCompactBlock {
    pub compact_version: u32,
    pub header: CompactHeader,
    pub prefilled: Vec<CompactPrefilledTx>,
    pub short_ids: Vec<String>,
    pub total_transactions: u32,
}

impl NativeCompactBlock {
    /// Validates compact block structure against DoS, memory exhaustion and float anomalies.
    pub fn validate(&self) -> Result<(), String> {
        // AUD15-06: Strict compact_version validation (v1 standard)
        if self.compact_version != 1 {
            return Err(format!(
                "Unsupported compact block version: {}. Expected 1.",
                self.compact_version
            ));
        }

        // 1. Float timestamp validation (REV7-02: Prevent NaN/Infinity crash vectors)
        if !self.header.timestamp.is_finite() || self.header.timestamp < 0.0 {
            return Err("Compact block timestamp must be a finite, positive number".to_string());
        }

        // AUD12-06: Strict PoW difficulty boundary checks (1..=64)
        if self.header.difficulty < 1 || self.header.difficulty > 64 {
            return Err(format!(
                "Compact block difficulty ({}) must be in range 1..64",
                self.header.difficulty
            ));
        }

        // 2. Maximum transaction and list bounds
        if self.total_transactions > MAX_BLOCK_TRANSACTIONS {
            return Err(format!(
                "Total transactions ({}) exceeds maximum limit ({})",
                self.total_transactions, MAX_BLOCK_TRANSACTIONS
            ));
        }
        if self.prefilled.len() > MAX_BLOCK_TRANSACTIONS as usize {
            return Err(format!(
                "Prefilled transactions count ({}) exceeds maximum limit",
                self.prefilled.len()
            ));
        }
        if self.short_ids.len() > MAX_BLOCK_TRANSACTIONS as usize {
            return Err(format!(
                "Short IDs count ({}) exceeds maximum limit",
                self.short_ids.len()
            ));
        }

        // AUD15-06 & AUD16-04: Strict BIP-152 short_id validation (16 hex chars = 8 bytes) and duplicate rejection
        let mut seen_short_ids = std::collections::HashSet::with_capacity(self.short_ids.len());
        for sid in &self.short_ids {
            if sid.len() != 16 || !sid.chars().all(|c| c.is_ascii_hexdigit()) {
                return Err(format!(
                    "Invalid short_id format: '{}'. Expected exactly 16 hex characters.",
                    sid
                ));
            }
            if !seen_short_ids.insert(sid) {
                return Err(format!(
                    "Duplicate short_id ({}) detected in compact block",
                    sid
                ));
            }
        }

        // AUD12-06: Consistency invariant: sum of prefilled and short_ids must match total_transactions
        let total_items = self.prefilled.len() + self.short_ids.len();
        if total_items != self.total_transactions as usize {
            return Err(format!(
                "Sum of prefilled ({}) and short_ids ({}) must match total_transactions ({})",
                self.prefilled.len(), self.short_ids.len(), self.total_transactions
            ));
        }

        // AUD12-06 & AUD15-06: Index bounds, uniqueness, and raw_json memory validation for prefilled transactions
        const MAX_RAW_JSON_LEN: usize = 65_536;
        let mut seen_indices = std::collections::HashSet::with_capacity(self.prefilled.len());
        for p in &self.prefilled {
            if p.raw_json.is_empty() || p.raw_json.len() > MAX_RAW_JSON_LEN {
                return Err(format!(
                    "Prefilled transaction raw_json length ({}) out of valid range (1..{})",
                    p.raw_json.len(), MAX_RAW_JSON_LEN
                ));
            }
            if p.index >= self.total_transactions {
                return Err(format!(
                    "Prefilled transaction index ({}) out of range for total_transactions ({})",
                    p.index, self.total_transactions
                ));
            }
            if !seen_indices.insert(p.index) {
                return Err(format!(
                    "Duplicate prefilled transaction index ({}) in compact block",
                    p.index
                ));
            }
        }

        // 3. String field bounding and non-empty checks (AUD16-04)
        if self.header.hash.is_empty()
            || self.header.previous_hash.is_empty()
            || self.header.merkle_root.is_empty()
            || self.header.miner.is_empty()
        {
            return Err("Compact block header fields (hash, previous_hash, merkle_root, miner) cannot be empty".to_string());
        }
        if self.header.hash.len() > MAX_FIELD_LEN
            || self.header.previous_hash.len() > MAX_FIELD_LEN
            || self.header.merkle_root.len() > MAX_FIELD_LEN
            || self.header.miner.len() > MAX_FIELD_LEN
        {
            return Err("Compact block header field exceeds maximum allowed length".to_string());
        }

        Ok(())
    }
}

/// Zero-copy JSON serialization of compact block
pub fn serialize_compact_block(block: &NativeCompactBlock) -> Result<Vec<u8>, String> {
    block.validate()?;
    serde_json::to_vec(block).map_err(|e| e.to_string())
}

/// Zero-copy JSON deserialization of compact block with strict size & NaN validation
pub fn deserialize_compact_block(bytes: &[u8]) -> Result<NativeCompactBlock, String> {
    if bytes.len() > MAX_COMPACT_BLOCK_BYTES {
        return Err(format!(
            "Payload size ({} bytes) exceeds maximum compact block limit ({} bytes)",
            bytes.len(),
            MAX_COMPACT_BLOCK_BYTES
        ));
    }
    let block: NativeCompactBlock = serde_json::from_slice(bytes).map_err(|e| e.to_string())?;
    block.validate()?;
    Ok(block)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dummy_header(ts: f64) -> CompactHeader {
        CompactHeader {
            index: 100,
            version: 1,
            merkle_root: "0000abc".to_string(),
            miner: "BCT_MINER".to_string(),
            previous_hash: "0000prev".to_string(),
            timestamp: ts,
            nonce: 42,
            difficulty: 4,
            hash: "0000hash".to_string(),
        }
    }

    #[test]
    fn test_valid_compact_block() {
        let block = NativeCompactBlock {
            compact_version: 1,
            header: dummy_header(1700000000.0),
            prefilled: vec![],
            short_ids: vec!["0123456789abcdef".to_string()],
            total_transactions: 1,
        };
        assert!(block.validate().is_ok());
        let serialized = serialize_compact_block(&block).expect("Serialization failed");
        let deserialized = deserialize_compact_block(&serialized).expect("Deserialization failed");
        assert_eq!(deserialized.header.index, 100);
    }

    #[test]
    fn test_nan_infinity_timestamp_rejected() {
        let nan_block = NativeCompactBlock {
            compact_version: 1,
            header: dummy_header(f64::NAN),
            prefilled: vec![],
            short_ids: vec![],
            total_transactions: 0,
        };
        assert!(nan_block.validate().is_err());

        let inf_block = NativeCompactBlock {
            compact_version: 1,
            header: dummy_header(f64::INFINITY),
            prefilled: vec![],
            short_ids: vec![],
            total_transactions: 0,
        };
        assert!(inf_block.validate().is_err());
    }

    #[test]
    fn test_oversized_tx_count_rejected() {
        let block = NativeCompactBlock {
            compact_version: 1,
            header: dummy_header(1700000000.0),
            prefilled: vec![],
            short_ids: vec![],
            total_transactions: 5001,
        };
        assert!(block.validate().is_err());
    }

    #[test]
    fn test_compact_block_aud12_06_invariants() {
        // 1. Difficulty out of 1..64 range rejected
        let mut block = NativeCompactBlock {
            compact_version: 1,
            header: dummy_header(1700000000.0),
            prefilled: vec![],
            short_ids: vec!["0123456789abcdef".to_string()],
            total_transactions: 1,
        };
        block.header.difficulty = 0;
        assert!(block.validate().is_err());
        block.header.difficulty = 65;
        assert!(block.validate().is_err());
        block.header.difficulty = 4;
        assert!(block.validate().is_ok());

        // 2. Sum mismatch: total_transactions = 2 but only 1 short_id
        block.total_transactions = 2;
        assert!(block.validate().is_err());
        block.total_transactions = 1;
        assert!(block.validate().is_ok());

        // 3. Prefilled index out of bounds
        block.total_transactions = 2;
        block.prefilled = vec![CompactPrefilledTx {
            index: 2, // Must be < 2 (0 or 1)
            raw_json: "{}".to_string(),
        }];
        block.short_ids = vec!["0123456789abcdef".to_string()];
        assert!(block.validate().is_err());

        // 4. Duplicate prefilled index
        block.total_transactions = 2;
        block.prefilled = vec![
            CompactPrefilledTx { index: 0, raw_json: "{}".to_string() },
            CompactPrefilledTx { index: 0, raw_json: "{}".to_string() },
        ];
        block.short_ids = vec![];
        assert!(block.validate().is_err());

        // 5. AUD15-06: Compact version mismatch
        block.compact_version = 2;
        assert!(block.validate().is_err());
        block.compact_version = 1;

        // 6. AUD15-06: Invalid short_id length or hex
        block.short_ids = vec!["invalid_short_id".to_string()];
        block.total_transactions = 3;
        assert!(block.validate().is_err());

        // 7. AUD16-04: Duplicate short_id rejected
        block.short_ids = vec!["0123456789abcdef".to_string(), "0123456789abcdef".to_string()];
        block.prefilled = vec![];
        block.total_transactions = 2;
        assert!(block.validate().is_err());

        // 8. AUD16-04: Empty header field rejected
        block.short_ids = vec!["0123456789abcdef".to_string()];
        block.total_transactions = 1;
        block.header.miner = String::new();
        assert!(block.validate().is_err());
    }

    #[test]
    fn test_oversized_bytes_rejected() {
        let huge_bytes = vec![0u8; MAX_COMPACT_BLOCK_BYTES + 1];
        assert!(deserialize_compact_block(&huge_bytes).is_err());
    }
}

