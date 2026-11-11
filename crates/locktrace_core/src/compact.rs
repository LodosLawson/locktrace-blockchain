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

/// Zero-copy binary serialization of compact block using bincode
pub fn serialize_compact_block(block: &NativeCompactBlock) -> Result<Vec<u8>, String> {
    bincode::serialize(block).map_err(|e| e.to_string())
}

/// Zero-copy binary deserialization of compact block using bincode
pub fn deserialize_compact_block(bytes: &[u8]) -> Result<NativeCompactBlock, String> {
    bincode::deserialize(bytes).map_err(|e| e.to_string())
}
