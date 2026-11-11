use serde::{Deserialize, Serialize};

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

/// Zero-copy JSON serialization of compact block
pub fn serialize_compact_block(block: &NativeCompactBlock) -> Result<Vec<u8>, String> {
    serde_json::to_vec(block).map_err(|e| e.to_string())
}

/// Zero-copy JSON deserialization of compact block
pub fn deserialize_compact_block(bytes: &[u8]) -> Result<NativeCompactBlock, String> {
    serde_json::from_slice(bytes).map_err(|e| e.to_string())
}

