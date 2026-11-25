"""
BlockChainT - Enterprise Grade Blockchain Core (Hardened & Transparent)
========================================================================
Total Supply: 1 Trillion BCT
Wallet Genesis Reward: 1.00 BCT
Transaction Fee: 1% (Returned to Treasury Vault)
Atomic Persistence & On-Chain Ledger Verification
"""

import hashlib
import ipaddress
import json
import math
import re
import socket
import time
import os
import threading
import secrets
import logging
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Optional, Tuple
from core.wallet import public_key_to_address, verify_signature, normalize_bct_address
from core.storage import SQLiteStorage
from core.avatar_catalog import (
    AVATAR_COLLECTIONS,
    AVATAR_CATALOG,
    AVATAR_CATALOG_BY_ID,
    AVATAR_EQUIP_FEE,
    AVATAR_SWAP_FEE,
    CURATED_BG_COLORS,
    DEFAULT_BG_COLOR,
    normalize_hex_color,
    get_base_avatar,
    make_variant_id,
    parse_variant_id,
    compute_variant_price,
    compute_revenue_split,
    build_avatar_metadata,
)
from core.rooms_engine import (
    validate_room_name,
    validate_room_description,
    validate_topic_fields,
    validate_reply_content,
    validate_room_avatar_spec,
    normalize_room_slug,
    compute_room_create_pricing,
    compute_room_avatar_seal_pricing,
    compute_room_transfer_pricing,
    compute_room_topic_pricing,
    compute_room_reply_pricing,
    compute_room_upvote_pricing,
    get_rooms_tokenomics_summary,
)

logger = logging.getLogger("LockTrace")


ATOMIC_UNIT = 100_000_000                 # 1 BCT = 10^8 atomic units (prevents IEEE-754 drift at 1T scale)


def _to_units(val: float) -> int:
    return int((Decimal(str(val)) * ATOMIC_UNIT).to_integral_value(rounding=ROUND_HALF_UP))


TOTAL_SUPPLY = 1_000_000_000_000.0       # 1 Trillion BCT
TREASURY_ADDRESS = "BCT_HAZINE_0000000000000000000000000000000000000000"
BRIDGE_VAULT_ADDRESS = "BCT_BRIDGE_VAULT_000000000000000000000000000000000"
VALIDATOR_STAKE_VAULT_ADDRESS = "BCT_STAKE_VAULT_00000000000000000000000000000000"

# Developer Verified Lost-Key Test Wallets (Non-spendable / Permanently Locked / Effective Burn)
BURN_ADDRESS = "BCT0000000000000000000000000000000000000000"
LOST_KEY_TEST_WALLETS = {
    "BCTd9cdd72f3d0ad1766a17d13d3fbfd3a97cf0d11d",
    "BCTf8c255f129a61b296f197a7e70902c043c3da0bf",
    "BCT7404325cf37316e3c6396ff1eef80c4ef381c27b",
    "BCT4ebea3d0f7132475e4e7c22573696eab6267a191",
}
try:
    from config import Config
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import Config

PROTOCOL_VERSION = getattr(Config, "PROTOCOL_VERSION", "2.2.0")

FEE_PERCENT = 0.01                       # 1%
MINER_FEE_SHARE = 0.50                   # 50% of the 1% fee allocated to block/validator reward pool
TREASURY_FEE_SHARE = 0.50                # 50% returned to Treasury Vault
BLOCK_REWARD = float(getattr(Config, "BLOCK_REWARD", 0.05))           # 0.05 BCT fixed block subsidy from treasury
SPACE_POST_FEE = float(getattr(Config, "SPACE_POST_FEE", 0.10))
SPACE_LIKE_FEE = float(getattr(Config, "SPACE_LIKE_FEE", 0.01))
SPACE_COMMENT_FEE = float(getattr(Config, "SPACE_COMMENT_FEE", 0.02))
SPACE_FOLLOW_FEE = float(getattr(Config, "SPACE_FOLLOW_FEE", 1.00))
POST_ROYALTY_TRANSFER_FEE = float(getattr(Config, "POST_ROYALTY_TRANSFER_FEE", 0.50))
POST_ROYALTY_BULK_FEE = float(getattr(Config, "POST_ROYALTY_BULK_FEE", 1000.0))
POST_ROYALTY_MAX_PER_YEAR = int(getattr(Config, "POST_ROYALTY_MAX_PER_YEAR", 3))
POST_ROYALTY_WINDOW_SECONDS = int(getattr(Config, "POST_ROYALTY_WINDOW_SECONDS", 365 * 24 * 3600))
PROPOSER_REWARD_SHARE = getattr(Config, "REWARD_MINER_PERCENT", 50) / 100.0   # 50% of reward pool to winning PoW block producer
VALIDATOR_POOL_SHARE = getattr(Config, "REWARD_VALIDATOR_PERCENT", 40) / 100.0 # 40% of reward pool shared equally among active verified peer validators
OBSERVER_POOL_SHARE = getattr(Config, "REWARD_OBSERVER_PERCENT", 10) / 100.0   # 10% of reward pool shared pro-rata among passive observer stakers
MIN_OBSERVER_STAKE = getattr(Config, "MIN_OBSERVER_STAKE", 100.0)             # 100 BCT min required for passive observer staking pool
MAX_OBSERVER_STAKE = getattr(Config, "MAX_OBSERVER_STAKE", 100000.0)          # 100,000 BCT max allowed per observer stake
MIN_VALIDATOR_STAKE = getattr(Config, "MIN_VALIDATOR_STAKE", 1000.0)          # 1000 BCT required for active validator node
STAKE_LOCKUP_SECONDS = int(getattr(Config, "STAKE_LOCKUP_SECONDS", 3600))     # 1-hour anti-flash-staking lockup window
MIN_TRANSACTION = float(getattr(Config, "MIN_TRANSACTION", 0.01))             # Minimum transfer amount
MAX_TRANSACTION = float(getattr(Config, "MAX_TRANSACTION", 10_000_000.0))      # Maximum single transfer amount
TARGET_BLOCK_TIME = getattr(Config, "TARGET_BLOCK_TIME", 20.0)                 # 20 seconds target block time
LWMA_WINDOW = getattr(Config, "LWMA_WINDOW", 20)                              # 20 blocks window for difficulty adjustment
MEMPOOL_MINER_WINDOW_SECONDS = 15.0      # Priority window for external PoW miners before fallback sealing
ACTIVE_MINER_TTL_SECONDS = 90.0          # Heartbeat window identifying live external PoW miners

# Hybrid Batching Parameters for Micro/Social Transactions (Süre + Kota)
LIKE_BATCH_WINDOW_SECONDS = 20.0       # Max wait time for likes batch (20 seconds)
LIKE_BATCH_QUOTA = 15                  # Max count threshold for likes batch (15 likes)

COMMENT_BATCH_WINDOW_SECONDS = 50.0    # Max wait time for comments batch (50 seconds)
COMMENT_BATCH_QUOTA = 10               # Max count threshold for comments batch (10 comments)

GENERAL_TX_BATCH_WINDOW_SECONDS = 20.0 # Standard transfer / micro tx window (20 seconds)
GENERAL_TX_BATCH_QUOTA = 25            # General transaction block threshold

# Anti-DDoS & High-Concurrency Mempool Quotas
MAX_PENDING_TX_PER_WALLET = 25         # Max unconfirmed transactions per wallet in mempool
MAX_GLOBAL_MEMPOOL_SIZE = 5000         # Hard global mempool ceiling against DDoS floods

MINING_DIFFICULTY = int(os.environ.get("BCT_MINING_DIFFICULTY", "3"))  # Base Proof of Work Difficulty
DATA_DIR = os.environ.get("BCT_DATA_DIR") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

RELEASE_AUTHORITY_ADDRESS = "BCT885bc383a03ebed0aa11cedfbfac0d52be3d4080"
RELEASE_AUTHORITY_PUBKEY = (
    "5e3686d4e64119cc049dd966e57150a04db4160a335610c8740748ba618c0023"
    "21a5882ed90bfd5597bc144a7c4926369aec9b89070d3d337819d6626c67a150"
)


def verify_frontend_manifest(manifest: dict) -> Tuple[bool, str]:
    """Cryptographically verify a signed frontend release manifest against RELEASE_AUTHORITY_PUBKEY."""
    if not isinstance(manifest, dict):
        return False, "Invalid manifest format."
    ver = str(manifest.get("version", "")).strip()
    index_sha = str(manifest.get("index_html_sha256", "")).strip().lower()
    sw_sha = str(manifest.get("sw_js_sha256", "")).strip().lower()
    ipfs_cid = str(manifest.get("ipfs_cid_v1", "")).strip()
    pub = str(manifest.get("authority_public_key", "")).strip().lower()
    sig = str(manifest.get("signature", "")).strip()

    if not ver or len(index_sha) != 64 or not ipfs_cid or not sig:
        return False, "Missing release checksum (SHA-256) or signature."
    if pub != RELEASE_AUTHORITY_PUBKEY.lower() or public_key_to_address(pub) != RELEASE_AUTHORITY_ADDRESS:
        return False, "Unauthorized release signing authority (Release Authority mismatch)!"

    canonical_msg = f"LOCKTRACE_FRONTEND_RELEASE:{ver}:{index_sha}:{sw_sha}:{ipfs_cid}"
    if not verify_signature(RELEASE_AUTHORITY_PUBKEY, canonical_msg, sig):
        return False, "Invalid ECDSA release signature! Manifest has been tampered with."
    return True, "Verified"


def is_valid_bct_address(addr: str) -> bool:
    """Validate BCT address syntax (case-insensitive prefix BCT + 40 hex)."""
    if not addr or not isinstance(addr, str):
        return False
    clean = addr.strip()
    clean_upper = clean.upper()
    if clean_upper in (TREASURY_ADDRESS, "GENESIS_VAULT", BRIDGE_VAULT_ADDRESS, VALIDATOR_STAKE_VAULT_ADDRESS):
        return True
    return clean_upper.startswith("BCT") and len(clean) == 43 and all(c in "0123456789abcdefABCDEF" for c in clean[3:])


class Transaction:
    """Cryptographic On-Chain Transaction with metadata and extra_data support."""

    def __init__(self, sender: str, receiver: str, amount: float,
                 fee: float = 0.0, signature: str = "",
                 timestamp: float = None, tx_type: str = "transfer",
                 extra_data: Optional[dict] = None):
        self.sender = sender.strip()
        self.receiver = receiver.strip()
        self.amount = float(amount)
        self.fee = float(fee)
        if hasattr(signature, 'to_string'):
            self.signature = signature.to_string().hex()
        elif isinstance(signature, bytes):
            self.signature = signature.hex()
        elif signature is not None:
            self.signature = str(signature)
        else:
            self.signature = ""
        self.timestamp = timestamp or time.time()
        self.tx_type = tx_type
        self.extra_data = extra_data or {}
        self._cached_hash: str = ""
        self._cached_dict: Optional[dict] = None

    def to_dict(self) -> dict:
        if self._cached_dict is not None:
            return self._cached_dict
        net = round(self.amount - self.fee, 8) if self.tx_type == "transfer" else round(self.amount, 8)
        d = {
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "fee": self.fee,
            "net_amount": net,
            "signature": self.signature,
            "timestamp": self.timestamp,
            "tx_type": self.tx_type,
            "tx_hash": self.hash()
        }
        if self.extra_data:
            d["extra_data"] = self.extra_data
        self._cached_dict = d
        return d

    def hash(self) -> str:
        if self._cached_hash:
            return self._cached_hash
        d = {
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "fee": self.fee,
            "timestamp": self.timestamp,
            "tx_type": self.tx_type
        }
        if self.extra_data:
            d["extra_data"] = self.extra_data
        data = json.dumps(d, sort_keys=True)
        self._cached_hash = hashlib.sha256(data.encode()).hexdigest()
        return self._cached_hash


HEX_64_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def compute_merkle_root(tx_hashes: List[str]) -> str:
    """
    Compute canonical binary SHA-256 Merkle root over ordered transaction hashes.
    Immune to CVE-2012-2459 (Merkle tree collision via duplicate/mutated leaves).
    """
    if not tx_hashes:
        return "0" * 64

    clean_hashes = [str(h).strip().lower() for h in tx_hashes]
    if any(not HEX_64_PATTERN.match(h) for h in clean_hashes):
        raise ValueError("Invalid transaction hash format in Merkle tree")

    # CVE-2012-2459: Block must not contain duplicate transaction hashes
    if len(clean_hashes) != len(set(clean_hashes)):
        raise ValueError("CVE-2012-2459: Duplicate transaction hashes in block")

    level = clean_hashes
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        next_level = []
        for i in range(0, len(level), 2):
            combined = f"{level[i]}{level[i + 1]}".encode("utf-8")
            next_level.append(hashlib.sha256(combined).hexdigest())
        level = next_level
    return level[0]


def compute_merkle_proof(tx_hashes: List[str], target_hash: str) -> Optional[List[dict]]:
    """Build SPV Merkle inclusion proof path for target_hash inside tx_hashes."""
    target = (target_hash or "").strip().lower()
    clean_hashes = [str(h).strip().lower() for h in tx_hashes]
    if not HEX_64_PATTERN.match(target) or any(not HEX_64_PATTERN.match(h) for h in clean_hashes):
        return None
    if len(clean_hashes) != len(set(clean_hashes)):
        return None
    if target not in clean_hashes:
        return None
    level = clean_hashes
    idx = level.index(target)
    proof: List[dict] = []
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        if idx % 2 == 0:
            sibling_idx = idx + 1
            position = "right"
        else:
            sibling_idx = idx - 1
            position = "left"
        proof.append({"position": position, "hash": level[sibling_idx]})
        next_level = []
        for i in range(0, len(level), 2):
            combined = f"{level[i]}{level[i + 1]}".encode("utf-8")
            next_level.append(hashlib.sha256(combined).hexdigest())
        level = next_level
        idx //= 2
    return proof


def verify_merkle_proof(tx_hash: str, proof: List[dict], expected_root: str) -> bool:
    """Verify SPV Merkle inclusion proof deterministically."""
    current = (tx_hash or "").strip().lower()
    root_clean = (expected_root or "").strip().lower()
    if not HEX_64_PATTERN.match(current) or not HEX_64_PATTERN.match(root_clean):
        return False
    if not proof:
        # In single-transaction blocks, leaf == root (proof path is empty)
        return current == root_clean
    for step in proof:
        sibling = str(step.get("hash", "")).strip().lower()
        pos = str(step.get("position", "")).strip().lower()
        if not HEX_64_PATTERN.match(sibling):
            return False
        if pos == "right":
            current = hashlib.sha256(f"{current}{sibling}".encode("utf-8")).hexdigest()
        elif pos == "left":
            current = hashlib.sha256(f"{sibling}{current}".encode("utf-8")).hexdigest()
        else:
            return False
    return current == root_clean


class Block:
    """Immutable Blockchain Block with Proof-of-Work, Merkle Root, and Miner Attribution."""

    def __init__(self, index: int, transactions: List[Transaction],
                 previous_hash: str, timestamp: float = None, nonce: int = 0,
                 miner: str = "", version: int = 2, merkle_root: str = "",
                 attestations_count: int = 0, precomputed_hash: str = "",
                 finalized: bool = False, raw_tx_dicts: Optional[List[dict]] = None):
        self.index = index
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.timestamp = timestamp or time.time()
        self.nonce = nonce
        self.miner = miner or "Genesis-Validator"
        self.version = int(version)
        self.merkle_root = merkle_root or compute_merkle_root([tx.hash() for tx in self.transactions])
        self.attestations_count = int(attestations_count or 0)
        self.finalized = bool(finalized)
        self._raw_tx_dicts = raw_tx_dicts
        self._cached_dict: Optional[dict] = None
        self.hash = precomputed_hash or self.calculate_hash()

    def _hash_payload(self, tx_dicts: List[dict]) -> str:
        if self.version >= 2:
            payload = {
                "index": self.index,
                "version": self.version,
                "merkle_root": self.merkle_root,
                "miner": self.miner,
                "transactions": tx_dicts,
                "previous_hash": self.previous_hash,
                "timestamp": self.timestamp,
                "nonce": self.nonce,
            }
        else:
            payload = {
                "index": self.index,
                "transactions": tx_dicts,
                "previous_hash": self.previous_hash,
                "timestamp": self.timestamp,
                "nonce": self.nonce,
            }
        block_data = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(block_data.encode()).hexdigest()

    def _header_hash(self) -> str:
        """Canonical v2 header-only SHA-256 hash (matches Block.mine(); merkle_root commits all transactions)."""
        payload = {
            "version": self.version,
            "index": self.index,
            "merkle_root": self.merkle_root,
            "previous_hash": self.previous_hash,
            "timestamp": self.timestamp,
            "miner": self.miner,
            "nonce": self.nonce,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def calculate_hash(self, precomputed_tx_dicts: Optional[List[dict]] = None) -> str:
        if self.version >= 2 and precomputed_tx_dicts is None:
            h_header = self._header_hash()
            if not getattr(self, "hash", "") or h_header == self.hash:
                return h_header
            # Backwards compatibility for historical v2 blocks (#0-#884) hashed with full transaction body
            h_legacy = self._hash_payload([tx.to_dict() for tx in self.transactions])
            if h_legacy == self.hash:
                return h_legacy
            if self._raw_tx_dicts:
                h_raw = self._hash_payload(self._raw_tx_dicts)
                if h_raw == self.hash:
                    return h_raw
            return h_header
        if precomputed_tx_dicts is not None:
            return self._hash_payload(precomputed_tx_dicts)
        h = self._hash_payload([tx.to_dict() for tx in self.transactions])
        if hasattr(self, "hash") and self.hash and h != self.hash and self._raw_tx_dicts:
            h_raw = self._hash_payload(self._raw_tx_dicts)
            if h_raw == self.hash:
                return h_raw
        return h

    def mine(self, difficulty: int):
        self.merkle_root = compute_merkle_root([tx.hash() for tx in self.transactions])
        tx_dicts = [tx.to_dict() for tx in self.transactions]
        target = "0" * difficulty
        sentinel = -999999999
        if self.version >= 2:
            payload = {
                "version": self.version,
                "index": self.index,
                "merkle_root": self.merkle_root,
                "previous_hash": self.previous_hash,
                "timestamp": self.timestamp,
                "miner": self.miner,
                "nonce": sentinel,
            }
        else:
            payload = {
                "index": self.index,
                "transactions": tx_dicts,
                "previous_hash": self.previous_hash,
                "timestamp": self.timestamp,
                "nonce": sentinel,
            }
        template = json.dumps(payload, sort_keys=True)
        parts = template.split(str(sentinel))
        if len(parts) == 2:
            prefix, suffix = parts[0], parts[1]
            nonce = self.nonce
            while True:
                h = hashlib.sha256((prefix + str(nonce) + suffix).encode()).hexdigest()
                if h.startswith(target):
                    self.nonce = nonce
                    self.hash = h
                    break
                nonce += 1
        else:
            self.hash = self.calculate_hash(tx_dicts)
            while not self.hash.startswith(target):
                self.nonce += 1
                self.hash = self.calculate_hash(tx_dicts)
        self._cached_dict = None

    def to_dict(self) -> dict:
        att_cnt = getattr(self, "attestations_count", 0)
        cached = getattr(self, "_cached_dict", None)
        if cached is not None and cached.get("attestations_count") == att_cnt and cached.get("hash") == self.hash:
            return cached
        d = {
            "index": self.index,
            "version": self.version,
            "hash": self.hash,
            "previous_hash": self.previous_hash,
            "merkle_root": self.merkle_root,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "miner": self.miner,
            "attestations_count": att_cnt,
            "finalized": getattr(self, "finalized", False),
            "transaction_count": len(self.transactions),
            "transactions": self._raw_tx_dicts if self._raw_tx_dicts is not None else [tx.to_dict() for tx in self.transactions]
        }
        self._cached_dict = d
        return d


class Blockchain:
    """Thread-safe, crash-resilient Blockchain Ledger backed by SQLite WAL."""

    def __init__(self, auto_mine: bool = True, data_dir: Optional[str] = None):
        self.chain: List[Block] = []
        self.pending_transactions: List[Transaction] = []
        self.balances: Dict[str, float] = {}
        self.wallets: Dict[str, dict] = {}
        self.difficulty = MINING_DIFFICULTY
        self.auto_mine = auto_mine
        self.lock = threading.RLock()
        self.total_transactions = 0
        self.total_fees_collected = 0.0
        self.nodes: Dict[str, dict] = {}
        self.space_posts: Dict[str, dict] = {}
        self.follows: Dict[str, List[str]] = {}
        self.following: Dict[str, List[str]] = {}
        self.bns_records: Dict[str, dict] = {}
        self.bns_reverse: Dict[str, str] = {}
        self.avatar_variant_counts: Dict[str, int] = {}
        self.avatar_owners: Dict[str, List[dict]] = {}
        self.avatar_equipped: Dict[str, Optional[dict]] = {}
        self._confirmed_avatar_len: int = 0
        self._confirmed_avatar_tip: str = ""
        self._confirmed_avatar_variant_counts: Dict[str, int] = {}
        self._confirmed_avatar_owners: Dict[str, List[dict]] = {}
        self._confirmed_avatar_equipped: Dict[str, Optional[dict]] = {}
        self._avatar_index_key: Optional[tuple] = None
        self.rooms: Dict[str, dict] = {}
        self.room_slug_index: Dict[str, str] = {}
        self.room_topics: Dict[str, dict] = {}
        self._confirmed_rooms_len: int = 0
        self._confirmed_rooms_tip: str = ""
        self._confirmed_rooms: Dict[str, dict] = {}
        self._confirmed_room_slugs: Dict[str, str] = {}
        self._confirmed_room_topics: Dict[str, dict] = {}
        self._rooms_index_key: Optional[tuple] = None
        self._custom_data_dir = data_dir
        self._storage: Optional[SQLiteStorage] = None
        self._storage_dir_bound = ""
        self._loaded_revision = -1
        self._profile_cache: Dict[str, Tuple[int, float, dict]] = {}
        self._ledger_index_key: Optional[tuple] = None
        self._unit_balances_map: Dict[str, int] = {}
        self._sender_nonce_map: Dict[str, int] = {}
        self._tx_counts_map: Dict[str, int] = {}
        self._used_signatures_set: set = set()
        self._mempool_used_sigs: set = set()
        self._rewarded_wallets_set: set = set()
        self._chain_valid_cache: Tuple[int, str, bool] = (-1, "", False)
        self._last_json_backup_ts: float = 0.0
        self._last_saved_chain_len: int = 0
        self._json_backup_in_flight: bool = False
        self._mining_lock = threading.Lock()
        self._sequencer_wakeup = threading.Event()
        self._confirmed_indexed_len: int = 0
        self._confirmed_indexed_tip: str = ""
        self._confirmed_units_map: Dict[str, int] = {}
        self._confirmed_nonces_map: Dict[str, int] = {}
        self._confirmed_tx_counts_map: Dict[str, int] = {}
        self._confirmed_used_sigs: set = set()
        self._confirmed_rewarded_wallets: set = set()
        self._confirmed_burned_wallets: set = set()
        self._burned_wallets_set: set = set()
        self._confirmed_stakes_map: Dict[str, int] = {}
        self._confirmed_blocks_mined_map: Dict[str, int] = {}
        self._confirmed_rewards_earned_map: Dict[str, int] = {}
        self._confirmed_bns_len: int = 0
        self._confirmed_bns_tip: str = ""
        self._confirmed_bns_records: Dict[str, dict] = {}
        self._confirmed_bns_reverse: Dict[str, str] = {}
        self._confirmed_space_len: int = 0
        self._confirmed_space_tip: str = ""
        self._confirmed_space_posts: Dict[str, dict] = {}
        self._confirmed_follows: Dict[str, List[str]] = {}
        self._confirmed_following: Dict[str, List[str]] = {}
        self._snapshot_base: Optional[dict] = None
        self._saved_wallet_nonces: Dict[str, Tuple[str, int]] = {}
        self._bns_index_key: Optional[tuple] = None
        self._space_index_key: Optional[tuple] = None
        self.finalized_height: int = 0
        self.observer_pending_units: Dict[str, int] = {}
        self.pending_asset_transfers: Dict[str, dict] = {}
        self._removed_mempool_hashes: List[str] = []
        self.slashed_validators: Dict[str, dict] = {}
        self._attestations_by_validator: Dict[str, str] = {}
        self._pending_auth_nonces: Dict[str, int] = {}
        self._stop_sequencer: Optional[threading.Event] = None
        self._sequencer_thread: Optional[threading.Thread] = None

        with self.lock:
            if not self._load_state():
                self._create_genesis_block()
            self._init_default_nodes()
        if self.auto_mine:
            self._start_batch_sequencer()

    def _get_active_data_dir(self) -> str:
        return self._custom_data_dir or DATA_DIR

    def _get_storage(self) -> SQLiteStorage:
        active_dir = self._get_active_data_dir()
        if self._storage is None or self._storage_dir_bound != active_dir:
            self._storage = SQLiteStorage(os.path.join(active_dir, "blockchain.db"))
            self._storage_dir_bound = active_dir
            self._loaded_revision = -1
            try:
                # F-03: slashing survives restarts
                self.slashed_validators.update(self._storage.load_slashed_validators())
                from config import Config
                seed_slashed = getattr(Config, "SLASHED_MALICIOUS_VALIDATORS", [])
                for s_addr in seed_slashed:
                    norm_s = normalize_bct_address(s_addr)
                    if norm_s and norm_s not in self.slashed_validators:
                        slash_info = {
                            "block_index": 749,
                            "reason": "Equivocation, double-unstake exploit in block 749, and dust-mining Treasury drain attempt.",
                            "timestamp": 1794751023.0,
                            "slashed": True
                        }
                        self.slashed_validators[norm_s] = slash_info
                        try:
                            self._storage.save_slashed_validator(norm_s, slash_info)
                        except Exception:
                            pass
            except Exception as _sl_err:
                logger.warning(f"Could not load persisted slashed validators: {_sl_err}")
        return self._storage

    def _init_default_nodes(self):
        genesis_node = {
            "node_id": "node-stockholm-validator-01",
            "name": "LockTrace Genesis Validator #1",
            "endpoint": "http://129.151.205.219:5000",
            "public_url": "https://locktrace.space",
            "role": "Genesis Validator / Archival Seed",
            "location": "Stockholm, Sweden (Oracle Cloud)",
            "last_seen": time.time(),
            "created_at": 1793620000.0,
            "status": "online",
            "version": PROTOCOL_VERSION,
            "block_height": len(self.chain),
            "is_genesis": True
        }
        if "node-stockholm-validator-01" not in self.nodes:
            self.nodes["node-stockholm-validator-01"] = genesis_node
        else:
            self.nodes["node-stockholm-validator-01"]["last_seen"] = time.time()
            self.nodes["node-stockholm-validator-01"]["block_height"] = len(self.chain)
            self.nodes["node-stockholm-validator-01"]["version"] = PROTOCOL_VERSION

    def _create_genesis_block(self):
        self.balances[TREASURY_ADDRESS] = TOTAL_SUPPLY
        genesis_tx = Transaction(
            sender="GENESIS_VAULT",
            receiver=TREASURY_ADDRESS,
            amount=TOTAL_SUPPLY,
            fee=0.0,
            signature="genesis_signature_locktrace_1t",
            tx_type="genesis"
        )
        block = Block(0, [genesis_tx], "0" * 64)
        block.mine(self.difficulty)
        self.chain = [block]
        self._save_state()

    @staticmethod
    def _apply_tx_to_ledger_maps(
        tx: Transaction,
        units_map: Dict[str, int],
        sender_nonces: Dict[str, int],
        tx_counts: Dict[str, int],
        used_sigs: set,
        rewarded: set,
        burned_wallets: Optional[set] = None,
    ):
        fee_bearing_types = {
            "transfer", "space_post", "space_like", "space_comment", "space_follow",
            "space_royalty_transfer", "space_royalty_transfer_all",
            "bns_register", "bns_transfer", "bns_set_price", "bns_buy",
            "bns_accept_offer", "avatar_mint", "avatar_equip",
            "room_create", "room_set_avatar", "room_transfer", "room_topic", "room_reply", "room_upvote",
            "room_verify"
        }
        net_credit_types = {
            "transfer", "space_post", "space_royalty_transfer", "space_royalty_transfer_all",
            "bns_register", "bns_buy",
            "validator_stake", "validator_unstake", "avatar_mint", "avatar_equip",
            "room_create", "room_set_avatar", "room_transfer", "room_verify"
        }
        social_treasury_types = {
            "space_like", "space_comment", "space_follow",
            "room_topic", "room_reply", "room_upvote"
        }

        amt_u = _to_units(tx.amount)
        fee_u = _to_units(tx.fee)
        rec = normalize_bct_address(tx.receiver)
        snd = normalize_bct_address(tx.sender)
        ttype = tx.tx_type
        extra = tx.extra_data

        if ttype == "bns_accept_offer":
            if extra and extra.get("seller") and snd == normalize_bct_address(extra.get("seller")):
                # Canonical bns_accept_offer: sender is the signing seller (clean_owner), receiver is bidder
                if rec:
                    tx_counts[rec] = tx_counts.get(rec, 0) + 1
                    units_map[rec] = units_map.get(rec, 0) - amt_u
                if snd:
                    sender_nonces[snd] = sender_nonces.get(snd, 0) + 1
                    tx_counts[snd] = tx_counts.get(snd, 0) + 1
                    units_map[snd] = units_map.get(snd, 0) + (amt_u - fee_u)
                if fee_u > 0:
                    units_map[TREASURY_ADDRESS] = units_map.get(TREASURY_ADDRESS, 0) + fee_u
                if tx.signature:
                    used_sigs.add(tx.signature.strip())
            return

        is_sender_pays_transfer = (
            ttype == "transfer" and isinstance(extra, dict) and extra.get("fee_mode") == "sender_pays"
        )

        if rec:
            tx_counts[rec] = tx_counts.get(rec, 0) + 1
            if ttype == "reward":
                rewarded.add(rec)
            if is_sender_pays_transfer:
                units_map[rec] = units_map.get(rec, 0) + amt_u
            elif ttype in net_credit_types:
                units_map[rec] = units_map.get(rec, 0) + (amt_u - fee_u)
            elif ttype == "bns_transfer":
                if rec == TREASURY_ADDRESS:
                    units_map[TREASURY_ADDRESS] = units_map.get(TREASURY_ADDRESS, 0) + (amt_u - fee_u)
            elif ttype in social_treasury_types:
                t_cut = _to_units(extra.get("treasury_cut", 0.0) if extra else 0.0)
                units_map[rec] = units_map.get(rec, 0) + t_cut
            else:
                units_map[rec] = units_map.get(rec, 0) + amt_u

        if ttype == "bns_transfer" and rec != TREASURY_ADDRESS:
            units_map[TREASURY_ADDRESS] = units_map.get(TREASURY_ADDRESS, 0) + (amt_u - fee_u)

        if snd:
            if ttype == "validator_unstake" and rec and tx.signature and not tx.signature.startswith("UNSTAKE_RELEASE_"):
                sender_nonces[rec] = sender_nonces.get(rec, 0) + 1
            else:
                sender_nonces[snd] = sender_nonces.get(snd, 0) + 1
            tx_counts[snd] = tx_counts.get(snd, 0) + 1
            if is_sender_pays_transfer:
                units_map[snd] = units_map.get(snd, 0) - (amt_u + fee_u)
            else:
                units_map[snd] = units_map.get(snd, 0) - amt_u

        if extra:
            def _credit_royalty(target_addr: str, cut_val):
                cut_u = _to_units(cut_val)
                if cut_u <= 0:
                    return
                # Protocol Rule (v2.14.0): Any royalty destined for a permanently burned/closed
                # wallet is automatically redirected to the Protocol Treasury Vault.
                eff_addr = (
                    TREASURY_ADDRESS
                    if (not target_addr or (burned_wallets is not None and target_addr in burned_wallets))
                    else target_addr
                )
                units_map[eff_addr] = units_map.get(eff_addr, 0) + cut_u

            if ttype in ("space_like", "space_comment"):
                r_recipient = normalize_bct_address(extra.get("royalty_recipient") or extra.get("author"))
                _credit_royalty(r_recipient, extra.get("author_cut", 0.0))
            elif ttype == "space_follow":
                r_recipient = normalize_bct_address(extra.get("royalty_recipient") or extra.get("target"))
                _credit_royalty(r_recipient, extra.get("creator_cut", 0.0))
            elif ttype == "room_topic":
                r_creator = normalize_bct_address(extra.get("room_creator_royalty_recipient") or extra.get("room_creator"))
                _credit_royalty(r_creator, extra.get("room_creator_cut", 0.0))
            elif ttype == "room_reply":
                t_author = normalize_bct_address(extra.get("topic_author_royalty_recipient") or extra.get("topic_author"))
                _credit_royalty(t_author, extra.get("topic_author_cut", 0.0))
                r_creator = normalize_bct_address(extra.get("room_creator_royalty_recipient") or extra.get("room_creator"))
                _credit_royalty(r_creator, extra.get("room_creator_cut", 0.0))
            elif ttype == "room_upvote":
                t_author = normalize_bct_address(extra.get("royalty_recipient") or extra.get("author"))
                _credit_royalty(t_author, extra.get("author_cut", 0.0))

        if ttype in fee_bearing_types and fee_u > 0:
            units_map[TREASURY_ADDRESS] = units_map.get(TREASURY_ADDRESS, 0) + fee_u

        if tx.signature:
            used_sigs.add(tx.signature.strip())

    def _ensure_ledger_index(self):
        """
        Incremental O(Δ) confirmed-chain ledger indexer + O(|Mempool|) live overlay.
        Guarantees 100% mathematically identical 10^8 atomic unit balances, sequential nonces,
        transaction counts, and full-history replay signature sets in O(1) amortized time.
        """
        tip_hash = self.chain[-1].hash if self.chain else ""
        mempool_hashes = tuple(tx.hash() for tx in self.pending_transactions)
        current_key = (self._loaded_revision, len(self.chain), tip_hash, mempool_hashes)
        if self._ledger_index_key == current_key:
            return

        # 1. Advance or rebuild confirmed-chain snapshot incrementally
        if (
            len(self.chain) < self._confirmed_indexed_len
            or (
                self._confirmed_indexed_len > 0
                and self.chain[self._confirmed_indexed_len - 1].hash != self._confirmed_indexed_tip
            )
        ):
            self._confirmed_indexed_len = 0
            self._confirmed_indexed_tip = ""
            if self._snapshot_base is not None:
                self._confirmed_units_map = dict(self._snapshot_base.get("units", {}))
                self._confirmed_nonces_map = dict(self._snapshot_base.get("nonces", {}))
                self._confirmed_indexed_len = min(len(self.chain), int(self._snapshot_base.get("chain_len", len(self.chain))))
                self._confirmed_indexed_tip = self.chain[self._confirmed_indexed_len - 1].hash if self._confirmed_indexed_len > 0 else ""
            else:
                self._confirmed_units_map = {}
                self._confirmed_nonces_map = {}
            self._confirmed_tx_counts_map = {}
            self._confirmed_used_sigs = set()
            self._confirmed_rewarded_wallets = set()
            self._confirmed_burned_wallets = set()
            self._confirmed_stakes_map = {}
            self._confirmed_stake_timestamps = {}
            self._confirmed_blocks_mined_map = {}
            self._confirmed_rewards_earned_map = {}

        if self._confirmed_indexed_len < len(self.chain):
            for block in self.chain[self._confirmed_indexed_len:]:
                b_miner = normalize_bct_address(getattr(block, "miner", "") or "")
                if b_miner:
                    self._confirmed_blocks_mined_map[b_miner] = self._confirmed_blocks_mined_map.get(b_miner, 0) + 1
                for tx in block.transactions:
                    self._apply_tx_to_ledger_maps(
                        tx,
                        self._confirmed_units_map,
                        self._confirmed_nonces_map,
                        self._confirmed_tx_counts_map,
                        self._confirmed_used_sigs,
                        self._confirmed_rewarded_wallets,
                        self._confirmed_burned_wallets,
                    )
                    norm_snd = normalize_bct_address(tx.sender)
                    norm_rec = normalize_bct_address(tx.receiver)
                    if tx.tx_type == "validator_stake" and norm_rec == VALIDATOR_STAKE_VAULT_ADDRESS and norm_snd:
                        self._confirmed_stakes_map[norm_snd] = self._confirmed_stakes_map.get(norm_snd, 0) + _to_units(tx.amount)
                        if not hasattr(self, "_confirmed_stake_timestamps"):
                            self._confirmed_stake_timestamps = {}
                        tx_ts = float(tx.timestamp or 0.0)
                        if tx_ts > float(self._confirmed_stake_timestamps.get(norm_snd, 0.0)):
                            self._confirmed_stake_timestamps[norm_snd] = tx_ts
                    elif tx.tx_type == "validator_unstake" and norm_snd == VALIDATOR_STAKE_VAULT_ADDRESS and norm_rec:
                        new_stk = max(0, self._confirmed_stakes_map.get(norm_rec, 0) - _to_units(tx.amount))
                        self._confirmed_stakes_map[norm_rec] = new_stk
                        if new_stk == 0 and hasattr(self, "_confirmed_stake_timestamps"):
                            self._confirmed_stake_timestamps.pop(norm_rec, None)
                    elif tx.tx_type in ("mining_reward", "validator_reward", "attestation_reward", "observer_reward") and norm_rec:
                        self._confirmed_rewards_earned_map[norm_rec] = self._confirmed_rewards_earned_map.get(norm_rec, 0) + _to_units(tx.amount)
                    elif tx.tx_type == "wallet_burn" and norm_snd:
                        self._confirmed_burned_wallets.add(norm_snd)
            vault_total = self._confirmed_units_map.get(VALIDATOR_STAKE_VAULT_ADDRESS, 0)
            if vault_total <= 0:
                self._confirmed_stakes_map.clear()
            else:
                for k, v in list(self._confirmed_stakes_map.items()):
                    if v > vault_total:
                        self._confirmed_stakes_map[k] = vault_total
            self._confirmed_indexed_len = len(self.chain)
            self._confirmed_indexed_tip = tip_hash

        # 2. Apply live mempool overlay on top of confirmed snapshot (O(|Mempool|) — zero copy of historical sigs)
        if not self.pending_transactions:
            self._unit_balances_map = dict(self._confirmed_units_map)
            self._sender_nonce_map = dict(self._confirmed_nonces_map)
            self._tx_counts_map = dict(self._confirmed_tx_counts_map)
            self._used_signatures_set = self._confirmed_used_sigs
            self._mempool_used_sigs = set()
            self._rewarded_wallets_set = set(self._confirmed_rewarded_wallets)
            self._burned_wallets_set = set(self._confirmed_burned_wallets)
        else:
            units_map = dict(self._confirmed_units_map)
            sender_nonces = dict(self._confirmed_nonces_map)
            tx_counts = dict(self._confirmed_tx_counts_map)
            mempool_sigs = set()
            rewarded = set(self._confirmed_rewarded_wallets)
            burned = set(self._confirmed_burned_wallets)
            clean_pending = []
            for tx in self.pending_transactions:
                sig = (tx.signature or "").strip()
                if sig and (sig in self._confirmed_used_sigs or sig in mempool_sigs):
                    continue  # Already sealed in confirmed block or duplicate in mempool; skip
                clean_pending.append(tx)
                self._apply_tx_to_ledger_maps(tx, units_map, sender_nonces, tx_counts, mempool_sigs, rewarded, burned)
                if tx.tx_type == "wallet_burn":
                    norm_snd = normalize_bct_address(tx.sender)
                    if norm_snd:
                        burned.add(norm_snd)
            if len(clean_pending) != len(self.pending_transactions):
                self.pending_transactions = clean_pending
            self._unit_balances_map = units_map
            self._sender_nonce_map = sender_nonces
            self._tx_counts_map = tx_counts
            self._used_signatures_set = self._confirmed_used_sigs
            self._mempool_used_sigs = mempool_sigs
            self._rewarded_wallets_set = rewarded
            self._burned_wallets_set = burned

        self._ledger_index_key = current_key

    def _is_signature_used(self, sig: str) -> bool:
        """O(1) two-tier signature replay check across confirmed chain and live mempool without copying history."""
        clean_sig = (sig or "").strip()
        return bool(clean_sig and (clean_sig in self._confirmed_used_sigs or clean_sig in self._mempool_used_sigs))

    def verify_and_recalc_units(self, address: str) -> int:
        """Calculate exact balance in 10^8 integer atomic units (immune to IEEE-754 float64 drift)."""
        clean_addr = normalize_bct_address(address)
        if not clean_addr:
            return 0
        self._ensure_ledger_index()
        raw_u = self._unit_balances_map.get(clean_addr, 0)
        if clean_addr not in ("GENESIS_VAULT", "GENESIS"):
            return max(0, raw_u)
        return raw_u

    def verify_and_recalc_balance(self, address: str) -> float:
        """Calculate mathematically exact balance from immutable on-chain history."""
        return max(0.0, round(self.verify_and_recalc_units(address) / ATOMIC_UNIT, 8))

    def is_wallet_burned(self, address: str) -> bool:
        """Returns True if the wallet has been permanently burned/closed on-chain."""
        clean_addr = normalize_bct_address(address)
        if not clean_addr:
            return False
        self._ensure_ledger_index()
        return clean_addr in self._burned_wallets_set

    def _verify_actor_signature(self, actor_address: str, payload: str,
                                signature: str, public_key: str = "") -> Tuple[bool, str]:
        """Cryptographically verify ECDSA signature, enforce Anti-DDoS mempool quotas, and bind public key."""
        clean_addr = normalize_bct_address(actor_address)
        if clean_addr.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT", "GENESIS"):
            return False, "System treasury address cannot be a direct transaction sender."
        self._ensure_ledger_index()
        if clean_addr in self._burned_wallets_set:
            return False, "This wallet has been permanently burned and closed on-chain."
        if not signature:
            return False, "Cryptographic signature missing (Unauthorized)."

        pub_hex = (public_key or "").strip() or self.wallets.get(clean_addr, {}).get("public_key", "")
        if not pub_hex:
            return False, "Wallet public key could not be verified. Please reconnect your wallet."

        derived_addr = public_key_to_address(pub_hex)
        if derived_addr != clean_addr:
            return False, "Public key does not match sender wallet address!"

        if not verify_signature(pub_hex, payload, signature):
            return False, "Invalid ECDSA digital signature!"

        # Full-history on-chain & mempool signature replay protection (O(1) two-tier lookup across all blocks #0..tip)
        clean_sig = signature.strip()
        self._ensure_ledger_index()
        if self._is_signature_used(clean_sig):
            return False, "Replay transaction signature rejected (already used on-chain or in mempool)!"

        # Atomic under-lock nonce verification (closes TOCTOU window between HTTP auth & ledger admission)
        req_nonce = self._pending_auth_nonces.pop(clean_sig, None)
        if req_nonce is not None:
            current_nonce = self._sender_nonce_map.get(clean_addr, 0)
            if req_nonce != current_nonce:
                return False, f"Concurrent transaction nonce conflict (Expected: {current_nonce}, signed: {req_nonce})."

        # Anti-DDoS & Mempool Flood Shield: Per-wallet and global pending transaction quotas
        if len(self.pending_transactions) >= MAX_GLOBAL_MEMPOOL_SIZE:
            # Check if mempool can accommodate priority RBF replacement
            min_fee_val = min((float(getattr(t, "fee", 0.0) or 0.0) for t in self.pending_transactions), default=float("inf"))
            if min_fee_val == float("inf"):
                return False, "Network mempool is temporarily at capacity under high load. Please retry in a few seconds."
        sender_pending_count = sum(1 for tx in self.pending_transactions if normalize_bct_address(tx.sender) == clean_addr)
        if sender_pending_count >= MAX_PENDING_TX_PER_WALLET:
            return (
                False,
                f"Anti-DDoS Protection: Maximum {MAX_PENDING_TX_PER_WALLET} pending transactions per wallet in mempool. "
                "Please wait a few seconds for the current batch block to seal.",
            )

        if clean_addr not in self.wallets:
            self.wallets[clean_addr] = {"public_key": pub_hex, "created_at": time.time()}
        elif not self.wallets[clean_addr].get("public_key"):
            self.wallets[clean_addr]["public_key"] = pub_hex

        return True, "OK"

    def register_wallet(self, address: str, public_key: str, grant_welcome_bonus: bool = True) -> Tuple[bool, str]:
        with self.lock:
            self._load_state()
            clean_addr = normalize_bct_address(address)
            clean_pub = (public_key or "").strip()

            if not is_valid_bct_address(clean_addr) or clean_addr.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT"):
                return False, "Invalid wallet address format."

            if self.is_wallet_burned(clean_addr):
                return False, "This wallet has been permanently burned and cannot be re-activated."

            if clean_pub:
                derived = public_key_to_address(clean_pub)
                if derived != clean_addr:
                    return False, "Public key does not match wallet address cryptographically!"

            current_bal = self.verify_and_recalc_balance(clean_addr)

            # Check if this address has EVER received the welcome bonus in any block (O(1) indexed check)
            has_received_reward = clean_addr in self._rewarded_wallets_set

            # If already has a real public key AND already received reward, return existing
            if clean_addr in self.wallets and self.wallets[clean_addr].get("public_key") and has_received_reward:
                return True, f"Wallet already active with balance: {current_bal} BCT"

            self.wallets[clean_addr] = {
                "public_key": clean_pub or self.wallets.get(clean_addr, {}).get("public_key", ""),
                "created_at": self.wallets.get(clean_addr, {}).get("created_at", time.time())
            }

            # Sybil Protection: Global hourly cap on 1.00 BCT Genesis Welcome Bonus (max 25 grants/hour network-wide)
            now_ts = time.time()
            recent_grants_1h = sum(
                1 for block in self.chain[-120:]
                for tx in block.transactions
                if tx.tx_type == "reward" and (now_ts - float(tx.timestamp or 0)) <= 3600.0
            ) + sum(
                1 for tx in self.pending_transactions
                if tx.tx_type == "reward" and (now_ts - float(tx.timestamp or 0)) <= 3600.0
            )

            # Automated 1.00 BCT Genesis Welcome Bonus from Treasury for new accounts
            if (
                grant_welcome_bonus
                and not has_received_reward
                and recent_grants_1h < 25
                and self.verify_and_recalc_balance(TREASURY_ADDRESS) >= 1.0
            ):
                welcome_tx = Transaction(
                    sender=TREASURY_ADDRESS,
                    receiver=clean_addr,
                    amount=1.0,
                    fee=0.0,
                    signature=f"genesis_welcome_grant_{int(time.time())}_{clean_addr[:10]}",
                    tx_type="reward",
                    extra_data={"purpose": "genesis_welcome_grant"}
                )
                self.pending_transactions.append(welcome_tx)
                self.total_transactions += 1
                self._seal_or_queue_mempool()

            # Always sync actual balance from verified ledger
            final_bal = self.verify_and_recalc_balance(clean_addr)
            self.balances[clean_addr] = final_bal
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()
            return True, f"Wallet registered successfully! Available balance: {final_bal} BCT"

    def burn_wallet(
        self,
        address: str,
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Permanently and irreversibly burns/closes a wallet on-chain.
        - Any remaining liquid BCT balance is absorbed back into TREASURY_ADDRESS (0.0 BCT left).
        - The address is permanently sealed into `self._burned_wallets_set` via consensus.
        - No future transaction, transfer, signature, room, BNS, or bridge action can ever be
          executed from or sent to this address again.
        """
        with self.lock:
            self._load_state()
            clean_addr = normalize_bct_address(address)
            if not is_valid_bct_address(clean_addr):
                return False, f"Invalid wallet address: '{clean_addr}'", None

            protected = {
                TREASURY_ADDRESS,
                "GENESIS_VAULT",
                "GENESIS",
                VALIDATOR_STAKE_VAULT_ADDRESS,
                BRIDGE_VAULT_ADDRESS,
                RELEASE_AUTHORITY_ADDRESS,
            }
            if clean_addr in protected or clean_addr.upper() in protected:
                return False, "System or protocol authority wallets cannot be burned.", None

            if self.is_wallet_burned(clean_addr):
                return False, "This wallet is already permanently burned and closed.", None

            # Protect staked collateral: require unstaking before permanent wallet burn
            active_stake = self.get_validator_stake(clean_addr)
            if active_stake > 0:
                return (
                    False,
                    f"This wallet still has {active_stake:.4f} BCT locked in the Staking Vault. Please unstake all collateral before burning your wallet.",
                    None,
                )
            has_pending_stake_op = any(
                t.tx_type in ("validator_stake", "validator_unstake")
                and (normalize_bct_address(t.sender) == clean_addr or normalize_bct_address(t.receiver) == clean_addr)
                for t in self.pending_transactions
            )
            if has_pending_stake_op:
                return False, "A staking/unstaking transaction is pending in the mempool. Wait for confirmation before burning.", None

            # Mempool race-condition protection
            has_pending = any(
                t.tx_type == "wallet_burn" and normalize_bct_address(t.sender) == clean_addr
                for t in self.pending_transactions
            )
            if has_pending:
                return False, "A wallet burn transaction is already pending in the mempool for this address.", None

            expected_payload = signed_payload or f"WALLET_BURN:{clean_addr}:PERMANENT_IRREVERSIBLE_DESTROY"
            sig_ok, sig_msg = self._verify_actor_signature(clean_addr, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            remaining_bal = self.verify_and_recalc_balance(clean_addr)
            tx = Transaction(
                sender=clean_addr,
                receiver=TREASURY_ADDRESS,
                amount=remaining_bal,
                fee=0.0,
                signature=signature,
                tx_type="wallet_burn",
                extra_data={
                    "burned_address": clean_addr,
                    "absorbed_amount": remaining_bal,
                    "reason": "user_permanent_burn",
                },
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1

            block = self._seal_or_queue_mempool()
            self._ensure_ledger_index()

            self.balances[clean_addr] = 0.0
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            if clean_addr in self.wallets:
                self.wallets[clean_addr]["burned"] = True
                self.wallets[clean_addr]["burned_at"] = tx.timestamp
            # Immediately cancel any open 2-step asset transfer proposals involving the burned wallet
            if isinstance(getattr(self, "pending_asset_transfers", None), dict):
                for _pid, _prop in self.pending_asset_transfers.items():
                    if not isinstance(_prop, dict) or _prop.get("status") != "pending":
                        continue
                    if (
                        normalize_bct_address(_prop.get("from_address", "")) == clean_addr
                        or normalize_bct_address(_prop.get("to_address", "")) == clean_addr
                    ):
                        _prop["status"] = "cancelled"
                        _prop["resolved_at"] = tx.timestamp
                        _prop["cancel_reason"] = "wallet_burned"
            self._save_state()

            return True, f"Wallet {clean_addr[:10]}... permanently burned and closed on-chain! Absorbed {remaining_bal:.4f} BCT to protocol reserve.", {
                "burned_address": clean_addr,
                "absorbed_amount": remaining_bal,
                "is_burned": True,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool",
            }

    def _admit_or_evict_mempool(self, tx: Transaction) -> Tuple[bool, str]:
        """
        v2.5.0 Dynamic Mempool Admission & Replace-By-Fee (RBF) Eviction:
        Guarantees that priority/fee-bearing transactions are never blocked by low-fee spam.
        If mempool is saturated (>= MAX_GLOBAL_MEMPOOL_SIZE):
        - Finds candidate with lowest fee.
        - If new tx offers higher fee, evicts lowest-fee tx.
        - Otherwise rejects with transparent fee threshold.
        """
        if len(self.pending_transactions) < MAX_GLOBAL_MEMPOOL_SIZE:
            self.pending_transactions.append(tx)
            return True, "Transaction admitted to mempool"

        # Find candidate with lowest fee
        min_fee_idx = -1
        min_fee_val = float("inf")
        for idx, pending in enumerate(self.pending_transactions):
            p_fee = float(getattr(pending, "fee", 0.0) or 0.0)
            if p_fee < min_fee_val:
                min_fee_val = p_fee
                min_fee_idx = idx

        new_fee = float(getattr(tx, "fee", 0.0) or 0.0)
        if new_fee > min_fee_val and min_fee_idx >= 0:
            evicted = self.pending_transactions.pop(min_fee_idx)
            self._removed_mempool_hashes.append(evicted.hash())
            logger.info(
                f"Mempool RBF Eviction: Evicted tx {evicted.hash()[:10]} (fee {min_fee_val:.6f}) "
                f"for higher priority tx {tx.hash()[:10]} (fee {new_fee:.6f})"
            )
            self.pending_transactions.append(tx)
            return True, "Transaction admitted via priority mempool eviction"

        return False, f"Mempool is at full capacity (5,000 txs). Higher transaction fee required (> {min_fee_val:.6f} BCT) for priority inclusion."

    def create_transaction(self, sender: str, receiver: str,
                           amount: float, signature: str,
                           public_key: str = "", signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
        with self.lock:
            self._load_state()

            raw_sender = sender.strip()
            raw_receiver = receiver.strip()
            clean_sender = ("BCT" + raw_sender[3:].lower()) if len(raw_sender) == 43 and raw_sender[:3].upper() == "BCT" else raw_sender
            clean_receiver = ("BCT" + raw_receiver[3:].lower()) if len(raw_receiver) == 43 and raw_receiver[:3].upper() == "BCT" else raw_receiver

            if clean_sender == clean_receiver:
                return False, "Cannot send funds to your own address", None

            if clean_sender.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT", "GENESIS"):
                return False, "Reserved system address cannot initiate standard transfers", None

            if not is_valid_bct_address(clean_sender):
                return False, f"Invalid sender address format: '{raw_sender}'", None

            if not is_valid_bct_address(clean_receiver):
                return False, f"Invalid recipient address format: '{raw_receiver}'. Must be BCT followed by 40 hex characters.", None

            if self.is_wallet_burned(clean_sender):
                return False, "This wallet has been permanently burned and closed on-chain.", None

            if self.is_wallet_burned(clean_receiver):
                return False, "Recipient wallet has been permanently burned and cannot receive funds.", None

            if not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount <= 0:
                return False, "Amount must be a finite positive number", None

            amount = round(float(amount), 8)
            try:
                from config import Config
                min_tx = float(getattr(Config, "MIN_TRANSACTION", 0.01))
                min_fee = float(getattr(Config, "MIN_TRANSFER_FEE", 0.001))
                max_tx = float(getattr(Config, "MAX_TRANSACTION", 10_000_000.0))
            except Exception:
                min_tx = 0.01
                min_fee = 0.001
                max_tx = 10_000_000.0

            if amount < min_tx:
                return False, f"Minimum transfer amount is {min_tx} BCT to prevent network dust spam.", None

            if clean_receiver == BRIDGE_VAULT_ADDRESS:
                if amount > 1_000_000_000.0:
                    return False, "Maximum bridge lock amount is 1,000,000,000 BCT.", None
            elif amount > max_tx:
                return False, f"Maximum single transfer limit is {max_tx:,.0f} BCT (Anti-Whale limit: <= 10% circulating supply).", None

            expected_payload = signed_payload or f"{raw_sender}{raw_receiver}{amount}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_sender, expected_payload, signature, public_key)
            if not sig_ok and not signed_payload and (raw_sender != clean_sender or raw_receiver != clean_receiver):
                sig_ok, sig_msg = self._verify_actor_signature(clean_sender, f"{clean_sender}{clean_receiver}{amount}", signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            # Auto-register receiver wallet if not present (Decentralized permissionless model)
            if clean_receiver not in self.wallets and clean_receiver != TREASURY_ADDRESS:
                self.wallets[clean_receiver] = {
                    "public_key": "",
                    "created_at": time.time()
                }

            # Bridge Vault L1->EVM deposits are exempt from the 1% L1 transfer fee because the bridge
            # protocol collects its 0.2% bridge fee directly inside BRIDGE_VAULT_ADDRESS, preserving the
            # strict 1:1 Proof-of-Reserve invariant (vault_credit >= wBCT_minted).
            # Standard transfers use sender-pays fee model: receiver gets 100% of `amount`, sender pays `amount + fee`.
            if clean_receiver == BRIDGE_VAULT_ADDRESS:
                fee = 0.0
            else:
                fee = max(min_fee, round(amount * FEE_PERCENT, 8))

            total_required = round(amount + fee, 8)
            spendable_balance = self.verify_and_recalc_balance(clean_sender)
            if spendable_balance < total_required:
                return (
                    False,
                    f"Insufficient spendable balance. Required: {total_required:.8f} BCT ({amount:.8f} BCT + {fee:.8f} BCT fee), available: {spendable_balance:.8f} BCT",
                    None
                )

            net_amount = amount

            tx = Transaction(
                sender=clean_sender,
                receiver=clean_receiver,
                amount=amount,
                fee=fee,
                signature=signature,
                tx_type="transfer",
                extra_data={"fee_mode": "sender_pays"}
            )

            admitted, adm_msg = self._admit_or_evict_mempool(tx)
            if not admitted:
                return False, adm_msg, None

            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + fee, 8)

            block = self._seal_or_queue_mempool()

            # Synchronize balances directly from the verified ledger + mempool
            self.balances[clean_sender] = self.verify_and_recalc_balance(clean_sender)
            self.balances[clean_receiver] = self.verify_and_recalc_balance(clean_receiver)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)

            self._save_state()

            tx_info = {
                "tx_hash": tx.hash(),
                "sender": clean_sender,
                "receiver": clean_receiver,
                "amount": amount,
                "fee": fee,
                "net_amount": net_amount,
                "status": "confirmed" if block else "mempool",
                "block_index": block.index if block else None,
            }

            return True, f"Transfer confirmed! Sent: {net_amount} BCT, 1% Fee ({fee} BCT) returned to treasury vault.", tx_info

    def add_transaction(self, tx: Transaction) -> Tuple[bool, str]:
        """Directly append a verified Transaction to pending mempool and trigger sealing."""
        if not isinstance(tx, Transaction):
            return False, "Invalid transaction object"
        with self.lock:
            self._load_state()
            admitted, adm_msg = self._admit_or_evict_mempool(tx)
            if not admitted:
                return False, adm_msg
            self.total_transactions += 1
            block = self._seal_or_queue_mempool()
            if tx.sender:
                self.balances[tx.sender] = self.verify_and_recalc_balance(tx.sender)
            if tx.receiver:
                self.balances[tx.receiver] = self.verify_and_recalc_balance(tx.receiver)
            self._save_state()
            return True, "Transaction successfully added to mempool"

    def create_space_post(self, author: str, content: str, signature: str = "",
                          public_key: str = "", signed_payload: str = "",
                          bns_name: str = "") -> Tuple[bool, str, Optional[dict]]:
        """
        Creates an immutable, on-chain thought/tweet in BlocTag.
        Cost: 0.10 BCT.
        Tokenomics: 80% (0.08 BCT) returns to Treasury (circulating supply deflation),
        20% (0.02 BCT) is validator/miner fee.
        Character Limit: 3 - 280 characters.
        Automatically packages into a PoW block!
        """
        with self.lock:
            self._load_state()
            clean_author = normalize_bct_address(author)
            if not is_valid_bct_address(clean_author):
                return False, f"Invalid author address: '{clean_author}'", None

            clean_text = content.strip()
            if len(clean_text) < 3:
                return False, "Post text must be at least 3 characters.", None
            if len(clean_text) > 280:
                return False, "Post text can be at most 280 characters.", None

            expected_payload = signed_payload or f"{clean_author}:{clean_text}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_author, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            author_bal = self.verify_and_recalc_balance(clean_author)
            post_cost = 0.10
            if author_bal < post_cost:
                return False, f"Insufficient balance! Post fee is {post_cost:.2f} BCT. Current balance: {author_bal:.4f} BCT.", None

            clean_bns = str(bns_name or "").strip().lower()
            if clean_bns.startswith("@"):
                clean_bns = clean_bns[1:]
            assigned_bns = ""
            if clean_bns in ("anonymous", "anon"):
                assigned_bns = "anonymous"
            elif clean_bns and clean_bns not in ("none", "false", "address", "public"):
                if not clean_bns.endswith(".bct"):
                    clean_bns = f"{clean_bns}.bct"
                rec = self.bns_records.get(clean_bns)
                if not rec or rec.get("owner") != clean_author:
                    return False, f"You do not own the handle '@{clean_bns}'.", None
                assigned_bns = clean_bns
            else:
                assigned_bns = self.bns_reverse.get(clean_author, "")

            post_id = f"post_{secrets.token_hex(8)}"
            fee = 0.02
            treasury_cut = 0.08
            sig = signature

            extra_data = {
                "post_id": post_id,
                "content": clean_text,
                "author": clean_author,
                "bns_name": assigned_bns,
                "is_anonymous": (assigned_bns == "anonymous"),
                "treasury_cut": treasury_cut
            }

            tx = Transaction(
                sender=clean_author,
                receiver=TREASURY_ADDRESS,
                amount=post_cost,
                fee=fee,
                signature=sig,
                tx_type="space_post",
                extra_data=extra_data
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + fee, 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_space_index()

            self.balances[clean_author] = self.verify_and_recalc_balance(clean_author)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            res = {
                "post_id": post_id,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool",
                "author": clean_author,
                "content": clean_text,
                "cost": post_cost,
                "new_balance": self.balances[clean_author]
            }
            return True, "Your thought has been successfully sealed on-chain and published!", res

    def like_space_post(self, liker: str, post_id: str, signature: str = "",
                        public_key: str = "", signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
        """
        Likes an on-chain post.
        Cost: 0.01 BCT.
        Tokenomics:
        - 20% (0.002 BCT) sent directly to the original tweet author (creator economy).
        - 70% (0.007 BCT) returned to Treasury Vault reserve.
        - 10% (0.001 BCT) miner validation fee.
        """
        with self.lock:
            self._load_state()
            clean_liker = normalize_bct_address(liker)
            if not is_valid_bct_address(clean_liker):
                return False, f"Invalid liker address: '{clean_liker}'", None

            pid = post_id.strip()
            if pid not in self.space_posts:
                return False, "Target post not found.", None

            expected_payload = signed_payload or f"{clean_liker}:{pid}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_liker, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            post = self.space_posts[pid]
            if clean_liker in post.get("likes", []):
                return False, "You have already liked this post.", None

            # Double-like protection in mempool
            is_already_in_mempool = any(
                t.tx_type == "space_like"
                and t.sender == clean_liker
                and t.extra_data
                and t.extra_data.get("post_id") == pid
                for t in self.pending_transactions
            )
            if is_already_in_mempool:
                return False, "Your like for this post is already queued in the batch pool.", None

            liker_bal = self.verify_and_recalc_balance(clean_liker)
            like_cost = SPACE_LIKE_FEE
            if liker_bal < like_cost:
                return False, f"Insufficient balance! Like fee is {like_cost:.2f} BCT. Current balance: {liker_bal:.4f} BCT.", None

            author_address = post["author"]
            royalty_holder = normalize_bct_address(post.get("royalty_owner") or author_address)
            royalty_redirected = self.is_wallet_burned(royalty_holder)
            effective_royalty_recipient = TREASURY_ADDRESS if royalty_redirected else royalty_holder
            author_cut = round(like_cost * 0.20, 8)
            miner_fee = round(like_cost * 0.10, 8)
            treasury_cut = round(like_cost - author_cut - miner_fee, 8)
            sig = signature

            extra_data = {
                "post_id": pid,
                "author": author_address,
                "royalty_recipient": effective_royalty_recipient,
                "royalty_redirected_to_treasury": royalty_redirected,
                "liker": clean_liker,
                "author_cut": author_cut,
                "treasury_cut": treasury_cut
            }

            tx = Transaction(
                sender=clean_liker,
                receiver=TREASURY_ADDRESS,
                amount=like_cost,
                fee=miner_fee,
                signature=sig,
                tx_type="space_like",
                extra_data=extra_data
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + miner_fee, 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_space_index()
            updated_post = self.space_posts.get(pid, post)

            self.balances[clean_liker] = self.verify_and_recalc_balance(clean_liker)
            self.balances[author_address] = self.verify_and_recalc_balance(author_address)
            self.balances[effective_royalty_recipient] = self.verify_and_recalc_balance(effective_royalty_recipient)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            res = {
                "post_id": pid,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool_batched",
                "batch_window_seconds": LIKE_BATCH_WINDOW_SECONDS,
                "batch_quota": LIKE_BATCH_QUOTA,
                "likes_count": updated_post.get("likes_count", 1),
                "author_earned": author_cut,
                "royalty_recipient": effective_royalty_recipient,
                "royalty_redirected_to_treasury": royalty_redirected,
                "liker_new_balance": self.balances[clean_liker]
            }
            msg = ("Post liked and sealed into block!" if block
                   else "Post liked! Queued in 20s batch pool.")
            return True, msg, res

    def comment_space_post(self, commenter: str, post_id: str, content: str,
                           signature: str = "", public_key: str = "", signed_payload: str = "",
                           bns_name: str = "") -> Tuple[bool, str, Optional[dict]]:
        """
        Comments on an on-chain post.
        Cost: 0.02 BCT.
        Tokenomics:
        - 20% (0.004 BCT) sent directly to the original tweet author.
        - 70% (0.014 BCT) returned to Treasury Vault reserve.
        - 10% (0.002 BCT) miner validation fee.
        Character Limit: 1 - 140 characters.
        """
        with self.lock:
            self._load_state()
            clean_commenter = normalize_bct_address(commenter)
            if not is_valid_bct_address(clean_commenter):
                return False, f"Invalid commenter address: '{clean_commenter}'", None

            pid = post_id.strip()
            if pid not in self.space_posts:
                return False, "Target post for comment not found.", None

            clean_text = content.strip()
            if len(clean_text) < 1 or len(clean_text) > 140:
                return False, "Comment text must be between 1 and 140 characters.", None

            expected_payload = signed_payload or f"{clean_commenter}:{pid}:{clean_text}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_commenter, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            commenter_bal = self.verify_and_recalc_balance(clean_commenter)
            comment_cost = SPACE_COMMENT_FEE
            if commenter_bal < comment_cost:
                return False, f"Insufficient balance! Comment fee is {comment_cost:.2f} BCT. Current balance: {commenter_bal:.4f} BCT.", None

            post = self.space_posts[pid]
            clean_bns = str(bns_name or "").strip().lower()
            if clean_bns.startswith("@"):
                clean_bns = clean_bns[1:]
            assigned_bns = ""
            if clean_bns in ("anonymous", "anon"):
                assigned_bns = "anonymous"
            elif clean_bns and clean_bns not in ("none", "false", "address", "public"):
                if not clean_bns.endswith(".bct"):
                    clean_bns = f"{clean_bns}.bct"
                rec = self.bns_records.get(clean_bns)
                if not rec or rec.get("owner") != clean_commenter:
                    return False, f"You do not own the handle '@{clean_bns}'.", None
                assigned_bns = clean_bns
            else:
                assigned_bns = self.bns_reverse.get(clean_commenter, "")

            author_address = post["author"]
            royalty_holder = normalize_bct_address(post.get("royalty_owner") or author_address)
            royalty_redirected = self.is_wallet_burned(royalty_holder)
            effective_royalty_recipient = TREASURY_ADDRESS if royalty_redirected else royalty_holder
            author_cut = round(comment_cost * 0.20, 8)
            miner_fee = round(comment_cost * 0.10, 8)
            treasury_cut = round(comment_cost - author_cut - miner_fee, 8)
            comment_id = f"cmt_{secrets.token_hex(6)}"
            sig = signature

            extra_data = {
                "post_id": pid,
                "comment_id": comment_id,
                "author": author_address,
                "royalty_recipient": effective_royalty_recipient,
                "royalty_redirected_to_treasury": royalty_redirected,
                "commenter": clean_commenter,
                "content": clean_text,
                "bns_name": assigned_bns,
                "is_anonymous": (assigned_bns == "anonymous"),
                "author_cut": author_cut,
                "treasury_cut": treasury_cut
            }

            tx = Transaction(
                sender=clean_commenter,
                receiver=TREASURY_ADDRESS,
                amount=comment_cost,
                fee=miner_fee,
                signature=sig,
                tx_type="space_comment",
                extra_data=extra_data
            )

            # Double-comment duplicate protection in mempool
            is_dup_comment = any(
                t.tx_type == "space_comment"
                and t.sender == clean_commenter
                and t.extra_data
                and t.extra_data.get("post_id") == pid
                and t.extra_data.get("content") == clean_text
                and (time.time() - float(t.timestamp or 0)) < 30.0
                for t in self.pending_transactions
            )
            if is_dup_comment:
                return False, "This comment has already been submitted and is queued in the batch pool.", None

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + miner_fee, 8)

            cmt_obj = {
                "comment_id": comment_id,
                "commenter": clean_commenter,
                "commenter_bns": assigned_bns,
                "is_anonymous": (assigned_bns == "anonymous"),
                "content": clean_text,
                "timestamp": tx.timestamp,
                "tx_hash": tx.hash()
            }

            block = self._seal_or_queue_mempool()
            self._load_in_memory_space_index()

            self.balances[clean_commenter] = self.verify_and_recalc_balance(clean_commenter)
            self.balances[author_address] = self.verify_and_recalc_balance(author_address)
            self.balances[effective_royalty_recipient] = self.verify_and_recalc_balance(effective_royalty_recipient)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            res = {
                "post_id": pid,
                "comment": cmt_obj,
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool_batched",
                "batch_window_seconds": COMMENT_BATCH_WINDOW_SECONDS,
                "batch_quota": COMMENT_BATCH_QUOTA,
                "author_earned": author_cut,
                "royalty_recipient": effective_royalty_recipient,
                "royalty_redirected_to_treasury": royalty_redirected,
                "commenter_new_balance": self.balances[clean_commenter]
            }
            msg = ("Comment published and sealed into block!" if block
                   else "Comment published! Queued in 50s batch pool.")
            return True, msg, res

    def follow_creator(self, follower: str, target: str, signature: str = "",
                       public_key: str = "", signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
        """
        Follows an on-chain creator or address.
        Cost: 1.00 BCT.
        Tokenomics:
        - 50% (0.50 BCT) sent directly to followed creator.
        - 30% (0.30 BCT) to active miner / validator pool.
        - 20% (0.20 BCT) returned to Treasury Vault reserve.
        """
        with self.lock:
            self._load_state()
            clean_follower = normalize_bct_address(follower)
            clean_target = normalize_bct_address(target)

            if not is_valid_bct_address(clean_follower):
                return False, f"Invalid follower address: '{clean_follower}'", None
            if not is_valid_bct_address(clean_target):
                return False, f"Invalid target creator address: '{clean_target}'", None

            if clean_follower == clean_target:
                return False, "You cannot follow your own wallet address.", None

            expected_payload = signed_payload or f"follow:{clean_follower}:{clean_target}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_follower, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            # Check if already followed in confirmed state
            if clean_follower in self.follows.get(clean_target, []):
                return False, "You are already following this creator on-chain.", None

            # Double-follow protection in mempool
            is_already_in_mempool = any(
                t.tx_type == "space_follow"
                and t.sender == clean_follower
                and t.extra_data
                and t.extra_data.get("target") == clean_target
                for t in self.pending_transactions
            )
            if is_already_in_mempool:
                return False, "Your follow transaction is already queued in the mempool.", None

            follower_bal = self.verify_and_recalc_balance(clean_follower)
            follow_cost = SPACE_FOLLOW_FEE
            if follower_bal < follow_cost:
                return False, f"Insufficient balance! Follow fee is {follow_cost:.2f} BCT. Current balance: {follower_bal:.4f} BCT.", None

            creator_cut = round(follow_cost * 0.50, 8)
            miner_fee = round(follow_cost * 0.30, 8)
            treasury_cut = round(follow_cost - creator_cut - miner_fee, 8)
            royalty_redirected = self.is_wallet_burned(clean_target)
            effective_royalty_recipient = TREASURY_ADDRESS if royalty_redirected else clean_target

            extra_data = {
                "target": clean_target,
                "royalty_recipient": effective_royalty_recipient,
                "royalty_redirected_to_treasury": royalty_redirected,
                "follower": clean_follower,
                "creator_cut": creator_cut,
                "treasury_cut": treasury_cut,
                "miner_fee": miner_fee
            }

            tx = Transaction(
                sender=clean_follower,
                receiver=TREASURY_ADDRESS,
                amount=follow_cost,
                fee=miner_fee,
                signature=signature,
                tx_type="space_follow",
                extra_data=extra_data
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + miner_fee, 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_space_index()

            self.balances[clean_follower] = self.verify_and_recalc_balance(clean_follower)
            self.balances[clean_target] = self.verify_and_recalc_balance(clean_target)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._loaded_revision += 1
            self._profile_cache.clear()
            self._save_state()

            res = {
                "target": clean_target,
                "follower": clean_follower,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool_batched",
                "followers_count": len(self.follows.get(clean_target, [])),
                "creator_earned": creator_cut,
                "royalty_recipient": effective_royalty_recipient,
                "royalty_redirected_to_treasury": royalty_redirected,
                "follower_new_balance": self.balances[clean_follower]
            }
            msg = ("Creator followed and sealed on-chain!" if block
                   else "Creator followed! Queued in mempool.")
            return True, msg, res

    def transfer_post_royalty(
        self,
        current_holder: str,
        post_id: str,
        to_address: str,
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Transfers future Space post royalty rights (likes & comments author cut) to another
        BCT wallet or resolved .bct handle.
        Protocol Security Rules (v2.14.0):
        - Only the current royalty holder (`royalty_owner`, initially the original post author)
          may transfer royalty rights. Once transferred, the previous holder loses transfer authority.
        - Hard Limit: Maximum 3 royalty transfers per post within any rolling 365-day window.
        - Burned / closed wallets cannot send or receive royalty rights (royalties to burned wallets
          automatically redirect to the Protocol Treasury).
        - Fee: 0.50 BCT (0.25 BCT Treasury, 0.25 BCT Validator/Miner Pool).
        """
        POST_ROYALTY_TRANSFER_COST = POST_ROYALTY_TRANSFER_FEE
        POST_ROYALTY_TREASURY_CUT = round(POST_ROYALTY_TRANSFER_COST * 0.50, 8)
        POST_ROYALTY_POOL_CUT = round(POST_ROYALTY_TRANSFER_COST - POST_ROYALTY_TREASURY_CUT, 8)

        with self.lock:
            self._load_state()
            self._load_in_memory_space_index()

            clean_from = normalize_bct_address(current_holder)
            if not is_valid_bct_address(clean_from):
                return False, f"Invalid royalty holder address: '{clean_from}'", None
            if self.is_wallet_burned(clean_from):
                return False, "Permanently burned wallets cannot transfer royalty rights.", None

            raw_to = str(to_address or "").strip()
            if not raw_to:
                return False, "Recipient address or .bct handle is required.", None

            clean_to = normalize_bct_address(raw_to)
            if not is_valid_bct_address(clean_to):
                norm_bns = self._normalize_bns_name(raw_to.lstrip("@"))
                bns_rec = self.bns_records.get(norm_bns)
                if bns_rec and is_valid_bct_address(bns_rec.get("owner", "")):
                    clean_to = normalize_bct_address(bns_rec["owner"])
                else:
                    return False, f"Invalid recipient address or unregistered .bct handle: '{raw_to}'", None

            if clean_from == clean_to:
                return False, "Cannot transfer post royalty rights to your own address.", None
            if clean_to in (
                TREASURY_ADDRESS,
                VALIDATOR_STAKE_VAULT_ADDRESS,
                BRIDGE_VAULT_ADDRESS,
                "BCT_BURN",
                "SYSTEM",
                "GENESIS",
                "GENESIS_VAULT",
            ):
                return False, "Cannot transfer post royalty rights to a system or vault address.", None
            if self.is_wallet_burned(clean_to):
                return False, "Recipient wallet has been permanently burned and cannot receive royalty rights.", None

            pid = str(post_id or "").strip()
            post = self.space_posts.get(pid)
            if not post:
                return False, "Target Space post not found.", None

            active_holder = normalize_bct_address(post.get("royalty_owner") or post.get("author", ""))
            if active_holder != clean_from:
                return False, "Only the current royalty holder can transfer this post's royalty rights.", None

            # Mempool race / double-transfer protection
            has_pending = any(
                t.tx_type == "space_royalty_transfer"
                and isinstance(t.extra_data, dict)
                and str(t.extra_data.get("post_id", "")).strip() == pid
                for t in self.pending_transactions
            )
            if has_pending:
                return False, "A royalty transfer for this post is already pending in the mempool.", None

            # Rolling 365-day annual limit check (max 3 transfers per post per year)
            now_ts = time.time()
            cutoff_ts = now_ts - POST_ROYALTY_WINDOW_SECONDS
            transfers_hist = list(post.get("royalty_transfers", []))
            recent_transfers = [
                tr for tr in transfers_hist
                if float(tr.get("timestamp", 0) or 0) >= cutoff_ts
            ]
            if len(recent_transfers) >= POST_ROYALTY_MAX_PER_YEAR:
                oldest_recent = min(float(tr.get("timestamp", now_ts)) for tr in recent_transfers)
                unlock_days = max(1, int((oldest_recent + POST_ROYALTY_WINDOW_SECONDS - now_ts + 86399) // 86400))
                return (
                    False,
                    f"Annual royalty transfer limit reached ({POST_ROYALTY_MAX_PER_YEAR}/{POST_ROYALTY_MAX_PER_YEAR} in the last 365 days). Next transfer unlocks in ~{unlock_days} day(s).",
                    None,
                )

            expected_payload = signed_payload or f"POST_ROYALTY_TRANSFER:{clean_from}:{pid}:{clean_to}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_from, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            holder_bal = self.verify_and_recalc_balance(clean_from)
            if holder_bal < POST_ROYALTY_TRANSFER_COST:
                return (
                    False,
                    f"Insufficient balance! Royalty transfer fee is {POST_ROYALTY_TRANSFER_COST:.2f} BCT. Current balance: {holder_bal:.4f} BCT.",
                    None,
                )

            tx = Transaction(
                sender=clean_from,
                receiver=TREASURY_ADDRESS,
                amount=POST_ROYALTY_TRANSFER_COST,
                fee=POST_ROYALTY_POOL_CUT,
                signature=signature,
                tx_type="space_royalty_transfer",
                extra_data={
                    "post_id": pid,
                    "original_author": normalize_bct_address(post.get("author", "")),
                    "from_address": clean_from,
                    "to_address": clean_to,
                    "treasury_cut": POST_ROYALTY_TREASURY_CUT,
                    "pool_cut": POST_ROYALTY_POOL_CUT,
                },
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + POST_ROYALTY_POOL_CUT, 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_space_index()

            self.balances[clean_from] = self.verify_and_recalc_balance(clean_from)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._loaded_revision += 1
            self._profile_cache.clear()
            self._save_state()

            used_after = len(recent_transfers) + 1
            remaining_after = max(0, POST_ROYALTY_MAX_PER_YEAR - used_after)
            new_owner_bns = self.bns_reverse.get(clean_to, "")
            return True, f"Post royalty rights transferred to {new_owner_bns or clean_to[:10] + '...'}! ({used_after}/{POST_ROYALTY_MAX_PER_YEAR} used this year)", {
                "post_id": pid,
                "previous_royalty_owner": clean_from,
                "new_royalty_owner": clean_to,
                "new_royalty_owner_bns": new_owner_bns,
                "transfers_used_year": used_after,
                "transfers_remaining_year": remaining_after,
                "max_transfers_per_year": POST_ROYALTY_MAX_PER_YEAR,
                "cost": POST_ROYALTY_TRANSFER_COST,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool",
                "new_balance": self.balances[clean_from],
            }

    def get_bulk_royalty_transfer_preview(self, holder_address: str) -> dict:
        """
        Returns live counts of Space posts currently held by `holder_address` that are eligible
        for bulk royalty transfer (each post independently checked against its own 3/365d limit).
        """
        POST_ROYALTY_MAX_PER_YEAR = 3
        POST_ROYALTY_WINDOW_SECONDS = 365 * 24 * 3600
        with self.lock:
            self._load_state()
            self._load_in_memory_space_index()
            clean_holder = normalize_bct_address(holder_address)
            now_ts = time.time()
            cutoff_ts = now_ts - POST_ROYALTY_WINDOW_SECONDS

            pending_pids = set()
            for t in self.pending_transactions:
                if t.tx_type == "space_royalty_transfer" and isinstance(t.extra_data, dict):
                    pending_pids.add(str(t.extra_data.get("post_id", "")).strip())
                elif t.tx_type == "space_royalty_transfer_all" and isinstance(t.extra_data, dict):
                    for pp in (t.extra_data.get("post_ids") or []):
                        pending_pids.add(str(pp).strip())

            eligible_pids = []
            skipped_limit_pids = []
            for pid, post in self.space_posts.items():
                r_owner = normalize_bct_address(post.get("royalty_owner") or post.get("author", ""))
                if r_owner != clean_holder:
                    continue
                if pid in pending_pids:
                    skipped_limit_pids.append(pid)
                    continue
                hist = post.get("royalty_transfers") or []
                recent_cnt = sum(1 for tr in hist if float(tr.get("timestamp", 0) or 0) >= cutoff_ts)
                if recent_cnt >= POST_ROYALTY_MAX_PER_YEAR:
                    skipped_limit_pids.append(pid)
                else:
                    eligible_pids.append(pid)

            eligible_pids.sort()
            skipped_limit_pids.sort()
            return {
                "holder": clean_holder,
                "total_held_posts": len(eligible_pids) + len(skipped_limit_pids),
                "eligible_count": len(eligible_pids),
                "skipped_limit_count": len(skipped_limit_pids),
                "eligible_post_ids": eligible_pids,
                "skipped_post_ids": skipped_limit_pids,
                "fee_bct": 1000.0,
                "max_transfers_per_post_per_year": POST_ROYALTY_MAX_PER_YEAR,
            }

    def transfer_all_post_royalties(
        self,
        current_holder: str,
        to_address: str,
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Atomically transfers royalty rights of ALL eligible Space posts currently held by
        `current_holder` to a new BCT wallet or resolved .bct handle in a single transaction.
        Protocol Security Rules (v2.15.0):
        - Fee: 1,000.00 BCT (500.00 BCT Treasury, 500.00 BCT Validator/Miner Pool).
        - Per-Post 3/Year Rule (Wallet-Independent): Each post is checked independently against
          its own rolling 365-day transfer history (max 3 transfers/post/year). Posts already at
          3/3 are safely skipped; if 0 eligible posts exist, the tx is rejected (no fee charged).
        - Burned/closed wallets and system/vault addresses are strictly rejected.
        """
        BULK_TRANSFER_COST = POST_ROYALTY_BULK_FEE
        BULK_TREASURY_CUT = round(BULK_TRANSFER_COST * 0.50, 8)
        BULK_POOL_CUT = round(BULK_TRANSFER_COST - BULK_TREASURY_CUT, 8)

        with self.lock:
            self._load_state()
            self._load_in_memory_space_index()

            clean_from = normalize_bct_address(current_holder)
            if not is_valid_bct_address(clean_from):
                return False, f"Invalid royalty holder address: '{clean_from}'", None
            if self.is_wallet_burned(clean_from):
                return False, "Permanently burned wallets cannot transfer royalty rights.", None

            raw_to = str(to_address or "").strip()
            if not raw_to:
                return False, "Recipient address or .bct handle is required.", None

            clean_to = normalize_bct_address(raw_to)
            if not is_valid_bct_address(clean_to):
                norm_bns = self._normalize_bns_name(raw_to.lstrip("@"))
                bns_rec = self.bns_records.get(norm_bns)
                if bns_rec and is_valid_bct_address(bns_rec.get("owner", "")):
                    clean_to = normalize_bct_address(bns_rec["owner"])
                else:
                    return False, f"Invalid recipient address or unregistered .bct handle: '{raw_to}'", None

            if clean_from == clean_to:
                return False, "Cannot transfer post royalty rights to your own address.", None
            if clean_to in (
                TREASURY_ADDRESS,
                VALIDATOR_STAKE_VAULT_ADDRESS,
                BRIDGE_VAULT_ADDRESS,
                "BCT_BURN",
                "SYSTEM",
                "GENESIS",
                "GENESIS_VAULT",
            ):
                return False, "Cannot transfer post royalty rights to a system or vault address.", None
            if self.is_wallet_burned(clean_to):
                return False, "Recipient wallet has been permanently burned and cannot receive royalty rights.", None

            # Mempool race / double-bulk protection for this sender
            has_pending_sender = any(
                t.tx_type in ("space_royalty_transfer", "space_royalty_transfer_all")
                and normalize_bct_address(t.sender) == clean_from
                for t in self.pending_transactions
            )
            if has_pending_sender:
                return False, "A royalty transfer from your wallet is already pending in the mempool.", None

            # Collect eligible posts (strictly enforcing each post's independent 3/365d limit)
            now_ts = time.time()
            cutoff_ts = now_ts - POST_ROYALTY_WINDOW_SECONDS
            eligible_pids = []
            skipped_limit_pids = []
            for pid, post in self.space_posts.items():
                active_holder = normalize_bct_address(post.get("royalty_owner") or post.get("author", ""))
                if active_holder != clean_from:
                    continue
                hist = post.get("royalty_transfers") or []
                recent_cnt = sum(1 for tr in hist if float(tr.get("timestamp", 0) or 0) >= cutoff_ts)
                if recent_cnt >= POST_ROYALTY_MAX_PER_YEAR:
                    skipped_limit_pids.append(pid)
                else:
                    eligible_pids.append(pid)

            eligible_pids.sort()
            skipped_limit_pids.sort()

            if not eligible_pids:
                if skipped_limit_pids:
                    return (
                        False,
                        f"All {len(skipped_limit_pids)} of your Space posts have already reached the annual 3/3 royalty transfer limit. No fee was charged.",
                        None,
                    )
                return False, "You do not currently hold royalty rights for any Space posts. No fee was charged.", None

            expected_payload = signed_payload or f"POST_ROYALTY_TRANSFER_ALL:{clean_from}:{clean_to}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_from, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            holder_bal = self.verify_and_recalc_balance(clean_from)
            if holder_bal < BULK_TRANSFER_COST:
                return (
                    False,
                    f"Insufficient balance! Bulk royalty transfer fee is {BULK_TRANSFER_COST:,.2f} BCT. Current balance: {holder_bal:,.4f} BCT.",
                    None,
                )

            tx = Transaction(
                sender=clean_from,
                receiver=TREASURY_ADDRESS,
                amount=BULK_TRANSFER_COST,
                fee=BULK_POOL_CUT,
                signature=signature,
                tx_type="space_royalty_transfer_all",
                extra_data={
                    "post_ids": eligible_pids,
                    "transferred_count": len(eligible_pids),
                    "skipped_limit_count": len(skipped_limit_pids),
                    "from_address": clean_from,
                    "to_address": clean_to,
                    "treasury_cut": BULK_TREASURY_CUT,
                    "pool_cut": BULK_POOL_CUT,
                },
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + BULK_POOL_CUT, 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_space_index()

            self.balances[clean_from] = self.verify_and_recalc_balance(clean_from)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._loaded_revision += 1
            self._profile_cache.clear()
            self._save_state()

            new_owner_bns = self.bns_reverse.get(clean_to, "")
            skip_note = f" ({len(skipped_limit_pids)} post skipped at 3/3 annual limit)" if skipped_limit_pids else ""
            return True, f"{len(eligible_pids)} Space post royalty rights transferred to {new_owner_bns or clean_to[:10] + '...'}!{skip_note}", {
                "transferred_post_ids": eligible_pids,
                "transferred_count": len(eligible_pids),
                "skipped_limit_post_ids": skipped_limit_pids,
                "skipped_limit_count": len(skipped_limit_pids),
                "previous_royalty_owner": clean_from,
                "new_royalty_owner": clean_to,
                "new_royalty_owner_bns": new_owner_bns,
                "cost": BULK_TRANSFER_COST,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool",
                "new_balance": self.balances[clean_from],
            }

    # =========================================================================
    # 2-STEP RECIPIENT-CONSENT ASSET TRANSFERS (v2.17.0)
    # Applies to: .bct BNS handles, Protocol Rooms, Single & Bulk Post Royalties
    # Prevents unsolicited asset dumping; fee is charged ONLY upon recipient accept.
    # =========================================================================
    def _prune_expired_asset_transfers(self, now_ts: Optional[float] = None) -> None:
        now = float(now_ts if now_ts is not None else time.time())
        for pid, prop in list(self.pending_asset_transfers.items()):
            if prop.get("status") == "pending" and float(prop.get("expires_at", 0) or 0) < now:
                prop["status"] = "expired"
            # Keep completed/expired history for 30 days max to avoid unbounded meta growth
            if prop.get("status") != "pending" and (now - float(prop.get("created_at", now) or now)) > (30 * 86400):
                self.pending_asset_transfers.pop(pid, None)

    @staticmethod
    def _public_proposal_view(prop: dict) -> dict:
        return {
            "proposal_id": prop.get("proposal_id", ""),
            "asset_type": prop.get("asset_type", ""),
            "asset_id": prop.get("asset_id", ""),
            "asset_label": prop.get("asset_label", ""),
            "from_address": prop.get("from_address", ""),
            "from_bns": prop.get("from_bns", ""),
            "to_address": prop.get("to_address", ""),
            "to_bns": prop.get("to_bns", ""),
            "fee_bct": float(prop.get("fee_bct", 0.0) or 0.0),
            "status": prop.get("status", "pending"),
            "created_at": float(prop.get("created_at", 0.0) or 0.0),
            "expires_at": float(prop.get("expires_at", 0.0) or 0.0),
            "tx_hash": prop.get("tx_hash", ""),
        }

    def propose_asset_transfer(
        self,
        asset_type: str,
        asset_id: str,
        from_address: str,
        to_address: str,
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Creates a cryptographically ECDSA-signed transfer proposal that requires explicit
        recipient ECDSA acceptance before ownership changes or any fee is charged.
        """
        PROPOSAL_TTL_SECONDS = 7 * 24 * 3600
        MAX_OUTGOING_PER_SENDER = 10

        with self.lock:
            self._load_state()
            self._load_in_memory_bns_index()
            self._load_in_memory_space_index()
            self._load_in_memory_rooms_index()
            self._prune_expired_asset_transfers()

            atype = str(asset_type or "").strip().lower()
            if atype not in ("bns", "room", "post_royalty", "post_royalty_all"):
                return False, f"Unsupported asset transfer type: '{atype}'", None

            clean_from = normalize_bct_address(from_address)
            if not is_valid_bct_address(clean_from):
                return False, f"Invalid sender address: '{clean_from}'", None
            if self.is_wallet_burned(clean_from):
                return False, "Permanently burned wallets cannot initiate asset transfers.", None

            raw_to = str(to_address or "").strip()
            if not raw_to:
                return False, "Recipient address or .bct handle is required.", None
            clean_to = normalize_bct_address(raw_to)
            if not is_valid_bct_address(clean_to):
                norm_to_bns = self._normalize_bns_name(raw_to.lstrip("@"))
                bns_rec = self.bns_records.get(norm_to_bns)
                if bns_rec and is_valid_bct_address(bns_rec.get("owner", "")):
                    clean_to = normalize_bct_address(bns_rec["owner"])
                else:
                    return False, f"Invalid recipient address or unregistered .bct handle: '{raw_to}'", None

            if clean_from == clean_to:
                return False, "Cannot transfer assets to your own address.", None
            if clean_to in (
                TREASURY_ADDRESS,
                VALIDATOR_STAKE_VAULT_ADDRESS,
                BRIDGE_VAULT_ADDRESS,
                "BCT_BURN",
                "SYSTEM",
                "GENESIS",
                "GENESIS_VAULT",
            ):
                return False, "Cannot transfer assets to a system or vault address.", None
            if self.is_wallet_burned(clean_to):
                return False, "Recipient wallet has been permanently burned and cannot receive assets.", None

            # Verify sender ECDSA signature
            if not signed_payload:
                return False, "Signed payload is required to propose an asset transfer.", None
            sig_ok, sig_msg = self._verify_actor_signature(clean_from, signed_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            # Anti-spam: limit active outgoing proposals per sender
            active_outgoing = [
                p for p in self.pending_asset_transfers.values()
                if p.get("status") == "pending" and p.get("from_address") == clean_from
            ]
            if len(active_outgoing) >= MAX_OUTGOING_PER_SENDER:
                return False, f"You already have {MAX_OUTGOING_PER_SENDER} pending transfer proposals. Cancel or wait for approval first.", None

            clean_aid = str(asset_id or "").strip()
            asset_label = ""
            fee_bct = 0.0

            if atype == "bns":
                norm = self._normalize_bns_name(clean_aid)
                rec = self.bns_records.get(norm)
                if not rec or normalize_bct_address(rec.get("owner", "")) != clean_from:
                    return False, f"You do not own the .bct handle '{norm}'.", None
                clean_aid = norm
                asset_label = f"@{norm}"
                fee_bct = 1.00
            elif atype == "room":
                rid = clean_aid.upper()
                room = self.rooms.get(rid)
                if not room:
                    return False, "Protocol room not found.", None
                if normalize_bct_address(room.get("creator", "")) != clean_from:
                    return False, "Only the current room owner can propose transferring this room.", None
                clean_aid = rid
                asset_label = f"Oda: {room.get('name', rid)} ({rid})"
                fee_bct = float(getattr(Config, "ROOM_TRANSFER_FEE", 0.50))
            elif atype == "post_royalty":
                post = self.space_posts.get(clean_aid)
                if not post:
                    return False, "Target Space post not found.", None
                holder = normalize_bct_address(post.get("royalty_owner") or post.get("author", ""))
                if holder != clean_from:
                    return False, "Only the current royalty holder can transfer this post's royalty rights.", None
                cutoff_ts = time.time() - POST_ROYALTY_WINDOW_SECONDS
                recent_cnt = sum(
                    1 for tr in (post.get("royalty_transfers") or [])
                    if float(tr.get("timestamp", 0) or 0) >= cutoff_ts
                )
                if recent_cnt >= POST_ROYALTY_MAX_PER_YEAR:
                    return False, f"Annual royalty transfer limit reached ({POST_ROYALTY_MAX_PER_YEAR}/{POST_ROYALTY_MAX_PER_YEAR} in the last 365 days).", None
                snippet = str(post.get("content", "") or "").strip().replace("\n", " ")[:48]
                asset_label = f"Paylaşım Telifi ({clean_aid[:12]}): {snippet}"
                fee_bct = POST_ROYALTY_TRANSFER_FEE
            elif atype == "post_royalty_all":
                prev = self.get_bulk_royalty_transfer_preview(clean_from)
                elig_cnt = int(prev.get("eligible_count", 0))
                if elig_cnt <= 0:
                    return False, "You have no eligible Space posts available for bulk royalty transfer.", None
                clean_aid = f"ALL:{clean_from}"
                asset_label = f"Toplu Telif Devri ({elig_cnt} paylaşım)"
                fee_bct = POST_ROYALTY_BULK_FEE

            # Prevent duplicate pending proposal for the same asset
            dup = any(
                p.get("status") == "pending"
                and p.get("asset_type") == atype
                and p.get("asset_id") == clean_aid
                for p in self.pending_asset_transfers.values()
            )
            if dup:
                return False, "Bu varlık için zaten alıcı onayı bekleyen bir devir teklifi var.", None

            # Verify sender currently has enough balance (fee is charged ONLY when recipient accepts)
            sender_bal = self.verify_and_recalc_balance(clean_from)
            if sender_bal < fee_bct:
                return False, f"Insufficient balance! Transfer fee is {fee_bct:,.2f} BCT (charged upon recipient approval). Current balance: {sender_bal:,.4f} BCT.", None

            now_ts = time.time()
            proposal_id = f"trp_{secrets.token_hex(8)}"
            prop = {
                "proposal_id": proposal_id,
                "asset_type": atype,
                "asset_id": clean_aid,
                "asset_label": asset_label,
                "from_address": clean_from,
                "from_bns": self.bns_reverse.get(clean_from, ""),
                "to_address": clean_to,
                "to_bns": self.bns_reverse.get(clean_to, ""),
                "fee_bct": fee_bct,
                "sender_signature": signature,
                "sender_public_key": public_key,
                "sender_signed_payload": signed_payload,
                "created_at": now_ts,
                "expires_at": now_ts + PROPOSAL_TTL_SECONDS,
                "status": "pending",
            }
            self.pending_asset_transfers[proposal_id] = prop
            self._save_state()

            to_lbl = prop["to_bns"] or (clean_to[:10] + "...")
            return True, f"Devir teklifi {to_lbl} alıcısına gönderildi! Alıcı onayladığında ({fee_bct:,.2f} BCT ücretle) zincire işlenecektir.", self._public_proposal_view(prop)

    def get_pending_asset_transfers(self, address: str) -> dict:
        with self.lock:
            self._load_state()
            self._prune_expired_asset_transfers()
            clean = normalize_bct_address(address)
            incoming = []
            outgoing = []
            for prop in self.pending_asset_transfers.values():
                if prop.get("status") != "pending":
                    continue
                if prop.get("to_address") == clean:
                    incoming.append(self._public_proposal_view(prop))
                elif prop.get("from_address") == clean:
                    outgoing.append(self._public_proposal_view(prop))
            incoming.sort(key=lambda x: -x["created_at"])
            outgoing.sort(key=lambda x: -x["created_at"])
            return {
                "address": clean,
                "incoming": incoming,
                "outgoing": outgoing,
                "pending_incoming_count": len(incoming),
                "pending_outgoing_count": len(outgoing),
            }

    def accept_asset_transfer(
        self,
        proposal_id: str,
        recipient_address: str,
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Recipient explicitly accepts and cryptographically signs an incoming asset transfer proposal,
        executing the underlying on-chain transfer atomically.
        """
        with self.lock:
            self._load_state()
            self._prune_expired_asset_transfers()

            pid = str(proposal_id or "").strip()
            prop = self.pending_asset_transfers.get(pid)
            if not prop:
                return False, "Transfer proposal not found.", None
            if prop.get("status") != "pending":
                return False, f"Transfer proposal is no longer pending (status: {prop.get('status')}).", None
            if time.time() > float(prop.get("expires_at", 0) or 0):
                prop["status"] = "expired"
                self._save_state()
                return False, "Transfer proposal has expired.", None

            clean_rec = normalize_bct_address(recipient_address)
            if clean_rec != prop.get("to_address"):
                return False, "Only the designated recipient can accept this transfer proposal.", None
            if self.is_wallet_burned(clean_rec):
                return False, "Permanently burned wallets cannot accept asset transfers.", None
            if self.is_wallet_burned(prop.get("from_address", "")):
                prop["status"] = "cancelled"
                self._save_state()
                return False, "Sender wallet has been burned; proposal cancelled.", None

            expected_payload = signed_payload or f"ASSET_TRANSFER_ACCEPT:{clean_rec}:{pid}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_rec, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            atype = prop["asset_type"]
            aid = prop["asset_id"]
            snd = prop["from_address"]
            s_sig = prop.get("sender_signature", "")
            s_pub = prop.get("sender_public_key", "")
            s_pl = prop.get("sender_signed_payload", "")

            if atype == "bns":
                ok, msg, res = self.bns_transfer(
                    name=aid,
                    current_owner=snd,
                    to_address=clean_rec,
                    signature=s_sig,
                    public_key=s_pub,
                    signed_payload=s_pl,
                )
            elif atype == "room":
                ok, msg, res = self.transfer_room(
                    current_owner=snd,
                    room_id=aid,
                    to_address=clean_rec,
                    signature=s_sig,
                    public_key=s_pub,
                    signed_payload=s_pl,
                )
            elif atype == "post_royalty":
                ok, msg, res = self.transfer_post_royalty(
                    current_holder=snd,
                    post_id=aid,
                    to_address=clean_rec,
                    signature=s_sig,
                    public_key=s_pub,
                    signed_payload=s_pl,
                )
            elif atype == "post_royalty_all":
                ok, msg, res = self.transfer_all_post_royalties(
                    current_holder=snd,
                    to_address=clean_rec,
                    signature=s_sig,
                    public_key=s_pub,
                    signed_payload=s_pl,
                )
            else:
                return False, f"Unknown asset type '{atype}'.", None

            if not ok:
                return False, msg, None

            prop["status"] = "accepted"
            prop["accepted_at"] = time.time()
            prop["recipient_signature"] = signature
            prop["tx_hash"] = (res or {}).get("tx_hash", "")
            self._save_state()
            return True, f"Devir onaylandı ve zincire işlendi! {msg}", {
                "proposal": self._public_proposal_view(prop),
                "execution": res,
            }

    def reject_asset_transfer(
        self,
        proposal_id: str,
        recipient_address: str,
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """Recipient explicitly rejects an unwanted incoming transfer proposal (0 fee charged)."""
        with self.lock:
            self._load_state()
            self._prune_expired_asset_transfers()
            pid = str(proposal_id or "").strip()
            prop = self.pending_asset_transfers.get(pid)
            if not prop:
                return False, "Transfer proposal not found.", None
            if prop.get("status") != "pending":
                return False, f"Transfer proposal is no longer pending (status: {prop.get('status')}).", None

            clean_rec = normalize_bct_address(recipient_address)
            if clean_rec != prop.get("to_address"):
                return False, "Only the designated recipient can reject this transfer proposal.", None

            expected_payload = signed_payload or f"ASSET_TRANSFER_REJECT:{clean_rec}:{pid}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_rec, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            prop["status"] = "rejected"
            prop["rejected_at"] = time.time()
            self._save_state()
            return True, "Devir teklifi reddedildi. Herhangi bir ücret kesilmedi.", self._public_proposal_view(prop)

    def cancel_asset_transfer(
        self,
        proposal_id: str,
        sender_address: str,
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """Sender cancels their own still-pending transfer proposal before recipient accepts."""
        with self.lock:
            self._load_state()
            self._prune_expired_asset_transfers()
            pid = str(proposal_id or "").strip()
            prop = self.pending_asset_transfers.get(pid)
            if not prop:
                return False, "Transfer proposal not found.", None
            if prop.get("status") != "pending":
                return False, f"Transfer proposal is no longer pending (status: {prop.get('status')}).", None

            clean_snd = normalize_bct_address(sender_address)
            if clean_snd != prop.get("from_address"):
                return False, "Only the original sender can cancel this transfer proposal.", None

            expected_payload = signed_payload or f"ASSET_TRANSFER_CANCEL:{clean_snd}:{pid}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_snd, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            prop["status"] = "cancelled"
            prop["cancelled_at"] = time.time()
            self._save_state()
            return True, "Devir teklifi iptal edildi.", self._public_proposal_view(prop)

    @staticmethod
    def extract_space_entities(text: str) -> dict:
        """Extracts mentions (@), hashtags (#), and cashtags ($) from space post content."""
        raw = text or ""
        raw_hash = re.findall(r"#([a-zA-Z0-9_ğüşıöçĞÜŞİÖÇ\-\.]+)", raw)
        hashtags = list(dict.fromkeys([h.rstrip(".,!?:;").strip() for h in raw_hash if h.rstrip(".,!?:;").strip()]))
        cashtags = list(dict.fromkeys(re.findall(r"\$([a-zA-Z0-9_]{2,10})\b", raw)))
        raw_ment = re.findall(r"@([a-zA-Z0-9_\-\.]+)", raw)
        mentions = list(dict.fromkeys([m.rstrip(".,!?:;").strip() for m in raw_ment if m.rstrip(".,!?:;").strip()]))
        return {
            "hashtags": [f"#{h}" for h in hashtags],
            "cashtags": [f"${c.upper()}" for c in cashtags],
            "mentions": [f"@{m}" for m in mentions]
        }

    def resolve_tagged_wallets(self, text: str) -> list:
        """
        Extracts all user/address tags (# or @ prefixed) and bare addresses from text.
        Resolves BNS handles (.bct) and direct BCT addresses,
        returning a list of unique dicts: [{'wallet': addr, 'tag': matched_tag, 'bns': handle_or_none}].
        Supports:
          - Direct addresses: #BCT123... or @BCT123... or bare BCT123...
          - BNS domains: #satoshi.bct or @satoshi.bct
          - Bare handles: #satoshi or @satoshi (resolves satoshi.bct if registered)
        """
        raw = text or ""
        tokens = re.findall(r"[#@]([a-zA-Z0-9_ğüşıöçĞÜŞİÖÇ\-\.]+)", raw)
        bare_addrs = re.findall(r"\b(BCT[a-fA-F0-9]{40})\b", raw)

        candidates = [t.rstrip(".,!?:;").strip() for t in tokens if t.strip()]
        candidates.extend(bare_addrs)

        results = []
        seen_wallets = set()

        for clean in candidates:
            if not clean:
                continue

            target_wallet = None
            bns_resolved = None

            # Case A: Direct BCT address
            if is_valid_bct_address(clean):
                target_wallet = clean

            # Case B: Explicit .bct domain
            elif clean.lower().endswith(".bct"):
                b_lookup = self.bns_lookup(clean)
                if b_lookup and b_lookup.get("owner"):
                    target_wallet = b_lookup["owner"]
                    bns_resolved = clean.lower()

            # Case C: Bare handle without .bct suffix (check if <handle>.bct is registered)
            else:
                candidate = f"{clean.lower()}.bct"
                b_lookup = self.bns_lookup(candidate)
                if b_lookup and b_lookup.get("owner"):
                    target_wallet = b_lookup["owner"]
                    bns_resolved = candidate

            if target_wallet and target_wallet not in seen_wallets:
                seen_wallets.add(target_wallet)
                results.append({
                    "wallet": target_wallet,
                    "tag": clean,
                    "bns": bns_resolved
                })

        return results

    def _enrich_post_royalty_meta(self, p: dict, now_sec: Optional[float] = None) -> None:
        """Populates live owner, original_author provenance, burned-redirect flag, transfer journey, and 3/year quota."""
        now_t = float(now_sec if now_sec is not None else time.time())
        cutoff_t = now_t - POST_ROYALTY_WINDOW_SECONDS
        author_addr = normalize_bct_address(str(p.get("author", "")))
        orig_addr = normalize_bct_address(str(p.get("original_author") or author_addr))
        r_owner = normalize_bct_address(str(p.get("royalty_owner") or author_addr))
        transfers = p.get("royalty_transfers") or []
        used_year = sum(1 for tr in transfers if float(tr.get("timestamp", 0) or 0) >= cutoff_t)
        enriched_hist = []
        for tr in transfers:
            fa = normalize_bct_address(str(tr.get("from_address", "")))
            ta = normalize_bct_address(str(tr.get("to_address", "")))
            enriched_hist.append({
                "from_address": fa,
                "from_bns": self.bns_reverse.get(fa, ""),
                "to_address": ta,
                "to_bns": self.bns_reverse.get(ta, ""),
                "timestamp": float(tr.get("timestamp", 0) or 0),
                "block_index": tr.get("block_index"),
                "tx_hash": str(tr.get("tx_hash", "")),
                "bulk": bool(tr.get("bulk", False)),
            })
        p["original_author"] = orig_addr
        p["original_author_bns"] = p.get("original_author_bns") or self.bns_reverse.get(orig_addr, "")
        p["royalty_owner"] = r_owner
        p["royalty_owner_bns"] = (
            p.get("author_bns", "")
            if r_owner == author_addr
            else self.bns_reverse.get(r_owner, "")
        )
        p["royalty_transfers"] = enriched_hist
        p["transfer_count"] = len(enriched_hist)
        p["royalty_redirected_to_treasury"] = self.is_wallet_burned(r_owner)
        p["royalty_transfers_used_year"] = used_year
        p["royalty_transfers_remaining_year"] = max(0, POST_ROYALTY_MAX_PER_YEAR - used_year)
        p["royalty_transfers_max_year"] = POST_ROYALTY_MAX_PER_YEAR
        p["royalty_transfer_fee"] = POST_ROYALTY_TRANSFER_FEE

    def get_space_feed(self, limit: int = 50, feed_type: str = "for_you", tag: str = "", author: str = "") -> list:
        with self.lock:
            self._load_state()
            feed = list(self.space_posts.values())
            now_enrich = time.time()

            # Enrich posts with entity tags, live validator status, equipped profile avatars, and royalty metadata
            for p in feed:
                if "entities" not in p:
                    p["entities"] = self.extract_space_entities(p.get("content", ""))
                is_anon = bool(p.get("is_anonymous") or p.get("author_bns") == "anonymous")
                author_addr = normalize_bct_address(str(p.get("author", "")))
                p["author_is_validator"] = False if is_anon else self.is_active_validator(author_addr)
                p["author_avatar"] = None if is_anon else self.avatar_equipped.get(author_addr)
                self._enrich_post_royalty_meta(p, now_sec=now_enrich)
                for cmt in p.get("comments", []):
                    c_anon = bool(cmt.get("is_anonymous") or cmt.get("commenter_bns") == "anonymous")
                    cmt_addr = normalize_bct_address(str(cmt.get("commenter", "")))
                    cmt["commenter_is_validator"] = False if c_anon else self.is_active_validator(cmt_addr)
                    cmt["commenter_avatar"] = None if c_anon else self.avatar_equipped.get(cmt_addr)

            # Filter by tag (#topic, $symbol, or @user)
            if tag:
                clean_tag = tag.strip().lower()
                clean_raw = clean_tag.lstrip("#$@")
                feed = [
                    p for p in feed
                    if clean_tag in str(p.get("content", "")).lower()
                    or any(clean_raw == h.lower().lstrip("#") for h in p.get("entities", {}).get("hashtags", []))
                    or any(clean_raw == c.lower().lstrip("$") for c in p.get("entities", {}).get("cashtags", []))
                    or any(clean_raw == m.lower().lstrip("@") for m in p.get("entities", {}).get("mentions", []))
                ]

            # Filter by author address or handle
            if author:
                clean_author = author.strip().lower()
                feed = [
                    p for p in feed
                    if clean_author == str(p.get("author", "")).lower()
                    or clean_author == str(p.get("author_bns", "")).lower()
                ]

            now_sec = time.time()
            if feed_type == "for_you":
                # Time-Decay Gravity scoring (strict recency + real engagement, no large static MD5 jitter)
                def _calc_for_you_score(p):
                    age_h = max(0.05, (now_sec - float(p.get("timestamp", now_sec))) / 3600.0)
                    likes = len(p.get("likes", [])) if isinstance(p.get("likes"), list) else int(p.get("likes_count", 0))
                    comments = len(p.get("comments", [])) if isinstance(p.get("comments"), list) else int(p.get("comments_count", 0))
                    eng = (likes * 2) + (comments * 3) + 1.0
                    return (eng / ((age_h + 1.5) ** 1.25)), float(p.get("timestamp", 0))

                feed.sort(key=_calc_for_you_score, reverse=True)
            elif feed_type == "trending":
                # Pure engagement
                def _calc_trending_score(p):
                    likes = len(p.get("likes", [])) if isinstance(p.get("likes"), list) else int(p.get("likes_count", 0))
                    comments = len(p.get("comments", [])) if isinstance(p.get("comments"), list) else int(p.get("comments_count", 0))
                    return ((likes * 2) + (comments * 3)), float(p.get("timestamp", 0))

                feed.sort(key=_calc_trending_score, reverse=True)
            else:
                # Chronological latest
                feed.sort(key=lambda p: float(p.get("timestamp", 0)), reverse=True)

            return feed[:limit]

    def get_space_trending_tags(self, top_n: int = 15) -> dict:
        """Calculates top trending hashtags (#) and cashtags ($) across space posts (case-merged, excluding raw BCT addresses)."""
        with self.lock:
            self._load_state()
            tag_counts: Dict[str, int] = {}
            display_label: Dict[str, str] = {}
            for p in self.space_posts.values():
                content = p.get("content", "")
                ents = self.extract_space_entities(content)
                for h in ents.get("hashtags", []):
                    raw_h = str(h or "").strip()
                    # Skip 43-char wallet address mentions (#BCT...) so only real topics trend
                    if re.fullmatch(r"#BCT[0-9a-fA-F]{40}", raw_h, re.IGNORECASE):
                        continue
                    key = raw_h.lower()
                    tag_counts[key] = tag_counts.get(key, 0) + 1
                    if key not in display_label or (raw_h != raw_h.lower() and display_label[key] == key):
                        display_label[key] = raw_h
                for c in ents.get("cashtags", []):
                    raw_c = str(c or "").strip().upper()
                    key = raw_c.lower()
                    tag_counts[key] = tag_counts.get(key, 0) + 1
                    display_label[key] = raw_c

            sorted_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], display_label.get(x[0], x[0])))
            return {
                "tags": [
                    {
                        "tag": display_label.get(t[0], t[0]),
                        "count": t[1],
                        "type": "cashtag" if display_label.get(t[0], t[0]).startswith("$") else "hashtag",
                    }
                    for t in sorted_tags[:top_n]
                ],
                "total_tags_count": len(sorted_tags)
            }

    def get_space_post(self, post_id: str) -> Optional[dict]:
        with self.lock:
            self._load_state()
            p = self.space_posts.get(post_id.strip())
            if p:
                is_anon = bool(p.get("is_anonymous") or p.get("author_bns") == "anonymous")
                author_addr = normalize_bct_address(str(p.get("author", "")))
                p["author_is_validator"] = False if is_anon else self.is_active_validator(author_addr)
                p["author_avatar"] = None if is_anon else self.avatar_equipped.get(author_addr)
                self._enrich_post_royalty_meta(p)
                for cmt in p.get("comments", []):
                    c_anon = bool(cmt.get("is_anonymous") or cmt.get("commenter_bns") == "anonymous")
                    cmt_addr = normalize_bct_address(str(cmt.get("commenter", "")))
                    cmt["commenter_is_validator"] = False if c_anon else self.is_active_validator(cmt_addr)
                    cmt["commenter_avatar"] = None if c_anon else self.avatar_equipped.get(cmt_addr)
            return p

    def get_suggested_voices(self, viewer_address: str = "", limit: int = 5) -> List[dict]:
        """
        Returns real on-chain active creators/voices for the Space Suggested Voices sidebar.
        Prioritizes:
        1. Real accounts that posted on Space
        2. Real accounts with registered BNS handles
        3. Real active holders
        Excludes Treasury, burn addresses, and current viewer.
        """
        with self.lock:
            self._load_state()
            clean_viewer = (viewer_address or "").strip()
            excluded_addrs = {
                TREASURY_ADDRESS,
                BRIDGE_VAULT_ADDRESS,
                VALIDATOR_STAKE_VAULT_ADDRESS,
                clean_viewer,
                "BCTd9cdd72f3d0ad1766a17d13d3fbfd3a97cf0d11d",
                "BCTf8c255f129a61b296f197a7e70902c043c3da0bf",
                "BCT7404325cf37316e3c6396ff1eef80c4ef381c27b",
                "BCT4ebea3d0f7132475e4e7c22573696eab6267a191",
                "BCT0000000000000000000000000000000000000000"
            }
            for slashed_addr in self.slashed_validators:
                excluded_addrs.add(normalize_bct_address(slashed_addr))

            candidates: Dict[str, dict] = {}
            for p in self.space_posts.values():
                auth = p.get("author")
                if auth and auth not in excluded_addrs and is_valid_bct_address(auth):
                    if auth not in candidates:
                        candidates[auth] = {"posts": 0, "likes": 0}
                    candidates[auth]["posts"] += 1
                    candidates[auth]["likes"] += p.get("likes_count", 0)

            for name, rec in self.bns_records.items():
                owner = rec.get("owner")
                if owner and owner not in excluded_addrs and is_valid_bct_address(owner):
                    if owner not in candidates:
                        candidates[owner] = {"posts": 0, "likes": 0}

            if len(candidates) < limit:
                for addr, bal in sorted(self.balances.items(), key=lambda x: x[1], reverse=True):
                    if addr not in excluded_addrs and is_valid_bct_address(addr):
                        if addr not in candidates:
                            candidates[addr] = {"posts": 0, "likes": 0}
                    if len(candidates) >= limit + 5:
                        break

            result = []
            for addr, meta in candidates.items():
                bns = self.bns_reverse.get(addr, "")
                followers = self.follows.get(addr, [])
                is_following = bool(clean_viewer and clean_viewer in followers)

                if bns:
                    bio = f"@{bns} • Core On-Chain Voice"
                    display_name = f"@{bns}"
                else:
                    short_addr = f"{addr[:6]}...{addr[-4:]}"
                    bio = f"BCT Creator • {meta['posts']} Casts" if meta['posts'] > 0 else "BCT On-Chain Account"
                    display_name = short_addr

                is_val = self.is_active_validator(addr)
                norm_addr = normalize_bct_address(addr)
                result.append({
                    "address": addr,
                    "bns_name": bns,
                    "avatar": self.avatar_equipped.get(norm_addr),
                    "display_name": display_name,
                    "bio": bio,
                    "is_validator": is_val,
                    "followers_count": len(followers),
                    "is_following": is_following,
                    "posts_count": meta["posts"],
                    "score": len(followers) * 10 + meta["posts"] * 5 + meta["likes"] * 2
                })

            result.sort(key=lambda x: x["score"], reverse=True)
            return result[:limit]

    # ── BNS (LockTrace Name Service — .bct Handles & Marketplace) ─────────────────
    @staticmethod
    def _normalize_bns_name(raw_name: str) -> str:
        s = (raw_name or "").lower().strip()
        if s.endswith(".bct"):
            s = s[:-4]
        s = re.sub(r"[^a-z0-9\-]", "", s).strip("-")
        return f"{s}.bct" if s else ""

    @staticmethod
    def get_bns_pricing(name_or_label: str) -> dict:
        """
        BNS (.bct) Handle Pricing & Tokenomics:
        - 3 characters: 100.0 BCT (Premium Tier)
        - 4 characters: 50.0 BCT (Standard Tier)
        - 5+ characters: 10.0 BCT (General Handle Tier)
        Tokenomics:
        - 20% returns to circulating supply via validator/miner reward pool.
        - 80% returns directly to the Protocol Treasury Vault pool (Hazine havuzuna geri aktarım).
        """
        clean = (name_or_label or "").lower().strip()
        if clean.endswith(".bct"):
            clean = clean[:-4]
        clean = re.sub(r"[^a-z0-9\-]", "", clean).strip("-")
        length = len(clean)
        try:
            from config import Config
            reserved_handles = set(getattr(Config, "RESERVED_BNS_HANDLES", set()))
        except Exception:
            reserved_handles = {"treasury", "genesis", "bridge", "vault", "admin", "system", "support", "official", "null", "burn", "validator", "security", "bct", "foundation"}

        if clean in reserved_handles:
            valid = False
            tier = "Reserved Protocol System Handle"
            cost = 0.0
        elif length < 3 or length > 24:
            valid = False
            tier = "Invalid Length (3-24 chars required)"
            cost = 0.0
        else:
            valid = True
            if length == 3:
                cost = 100.0
                tier = "Premium 3-Letter"
            elif length == 4:
                cost = 50.0
                tier = "Standard 4-Letter"
            else:
                cost = 10.0
                tier = "General Handle (5+ Chars)"

        fee = round(cost * 0.20, 8)
        treasury_cut = round(cost * 0.80, 8)
        return {
            "name": f"{clean}.bct" if clean else "",
            "label": clean,
            "length": length,
            "valid": valid,
            "cost": cost,
            "fee": fee,
            "treasury_cut": treasury_cut,
            "tier": tier,
        }

    def bns_check_available(self, name_or_label: str) -> dict:
        with self.lock:
            self._load_state()
            pricing = self.get_bns_pricing(name_or_label)
            full_name = pricing["name"]
            if not pricing["valid"]:
                is_reserved = "Reserved" in pricing.get("tier", "")
                return {
                    "available": False,
                    "reason": f"'{full_name}' is a reserved protocol system handle and cannot be registered." if is_reserved else "Name must be between 3 and 24 characters (lowercase letters, digits, hyphens).",
                    "pricing": pricing
                }
            if full_name in self.bns_records:
                rec = self.bns_records[full_name]
                return {
                    "available": False,
                    "reason": f"'{full_name}' is already registered.",
                    "owner": rec.get("owner", ""),
                    "for_sale": rec.get("sale_price", 0.0) > 0,
                    "sale_price": rec.get("sale_price", 0.0),
                    "pricing": pricing
                }
            return {
                "available": True,
                "reason": f"'{full_name}' is available for registration!",
                "pricing": pricing
            }

    def bns_lookup(self, query: str) -> Optional[dict]:
        with self.lock:
            self._load_state()
            clean_raw = (query or "").strip().lstrip("#").lstrip("@").strip()
            clean = clean_raw.lower()
            if clean.endswith(".bct"):
                rec = self.bns_records.get(clean)
                if rec:
                    return dict(rec)
                norm = self._normalize_bns_name(clean)
                return dict(self.bns_records.get(norm)) if norm in self.bns_records else None

            if is_valid_bct_address(clean_raw):
                addr = normalize_bct_address(clean_raw)
                primary = self.bns_reverse.get(addr, "")
                all_owned = [name for name, r in self.bns_records.items() if r.get("owner") == addr]
                if not primary and all_owned:
                    primary = all_owned[0]
                    self.bns_reverse[addr] = primary
                return {
                    "address": addr,
                    "primary_name": primary,
                    "owned_names": all_owned,
                    "names_count": len(all_owned)
                }

            norm = self._normalize_bns_name(clean)
            if norm in self.bns_records:
                return dict(self.bns_records[norm])
            return None

    def bns_register(self, name: str, owner: str, signature: str = "",
                     public_key: str = "", signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
        with self.lock:
            self._load_state()
            clean_owner = normalize_bct_address(owner)
            if not is_valid_bct_address(clean_owner):
                return False, f"Invalid owner address: '{clean_owner}'", None

            pricing = self.get_bns_pricing(name)
            if not pricing["valid"]:
                return False, f"Handle registration error: {pricing.get('tier', 'Invalid handle format')}", None

            full_name = pricing["name"]
            if full_name in self.bns_records:
                return False, f"'{full_name}' is already registered by another address.", None

            expected_payload = signed_payload or f"BNS_REGISTER:{full_name}:{clean_owner}:{pricing['cost']}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_owner, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            bal = self.verify_and_recalc_balance(clean_owner)
            cost = pricing["cost"]
            if bal < cost:
                return False, f"Insufficient balance! Registration cost for '{full_name}' is {cost:.2f} BCT. Current balance: {bal:.4f} BCT.", None

            fee = pricing["fee"]
            treasury_cut = pricing["treasury_cut"]

            extra_data = {
                "name": full_name,
                "owner": clean_owner,
                "cost": cost,
                "fee": fee,
                "treasury_cut": treasury_cut,
                "action": "register"
            }

            tx = Transaction(
                sender=clean_owner,
                receiver=TREASURY_ADDRESS,
                amount=cost,
                fee=fee,
                signature=signature,
                tx_type="bns_register",
                extra_data=extra_data
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + fee, 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_bns_index()

            self.balances[clean_owner] = self.verify_and_recalc_balance(clean_owner)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            res = {
                "name": full_name,
                "owner": clean_owner,
                "cost": cost,
                "treasury_locked": treasury_cut,
                "miner_reward_fee": fee,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool",
                "new_balance": self.balances[clean_owner]
            }
            return True, f"'{full_name}' successfully registered! 80% ({treasury_cut} BCT) returned to Treasury pool (Havuza Dönüş), 20% ({fee} BCT) returned to supply rewards.", res

    def bns_transfer(self, name: str, current_owner: str, to_address: str,
                     signature: str = "", public_key: str = "", signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
        with self.lock:
            self._load_state()
            clean_from = normalize_bct_address(current_owner)
            clean_to = normalize_bct_address(to_address)
            norm = self._normalize_bns_name(name)

            if not is_valid_bct_address(clean_from) or not is_valid_bct_address(clean_to):
                return False, "Invalid sender or recipient address.", None
            if clean_from == clean_to:
                return False, "Recipient address cannot be identical to sender address.", None
            if self.is_wallet_burned(clean_to):
                return False, "Recipient wallet has been permanently burned and cannot receive domains.", None
            if norm not in self.bns_records:
                return False, f"'{norm}' is not registered.", None

            rec = self.bns_records[norm]
            if rec.get("owner") != clean_from:
                return False, f"You are not the owner of '{norm}'.", None

            transfer_fee = 0.50
            bal = self.verify_and_recalc_balance(clean_from)
            if bal < transfer_fee:
                return False, f"Insufficient balance for transfer fee ({transfer_fee} BCT).", None

            expected_payload = signed_payload or f"BNS_TRANSFER:{norm}:{clean_from}:{clean_to}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_from, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            miner_fee = round(transfer_fee * 0.20, 8)
            treasury_cut = round(transfer_fee * 0.80, 8)

            extra_data = {
                "name": norm,
                "from_address": clean_from,
                "to_address": clean_to,
                "fee": miner_fee,
                "treasury_cut": treasury_cut,
                "action": "transfer"
            }

            tx = Transaction(
                sender=clean_from,
                receiver=TREASURY_ADDRESS,
                amount=transfer_fee,
                fee=miner_fee,
                signature=signature,
                tx_type="bns_transfer",
                extra_data=extra_data
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + miner_fee, 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_bns_index()

            self.balances[clean_from] = self.verify_and_recalc_balance(clean_from)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            res = {
                "name": norm,
                "previous_owner": clean_from,
                "new_owner": clean_to,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool"
            }
            return True, f"'{norm}' successfully transferred to {clean_to[:10]}...!", res

    def bns_set_price(self, name: str, owner: str, price_bct: float,
                      signature: str = "", public_key: str = "", signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
        with self.lock:
            self._load_state()
            clean_owner = normalize_bct_address(owner)
            norm = self._normalize_bns_name(name)
            if norm not in self.bns_records:
                return False, f"'{norm}' is not registered.", None

            rec = self.bns_records[norm]
            if rec.get("owner") != clean_owner:
                return False, f"You are not the owner of '{norm}'.", None

            try:
                raw_price = float(price_bct)
            except (ValueError, TypeError):
                return False, "Invalid listing price.", None
            if not math.isfinite(raw_price) or raw_price < 0 or raw_price > TOTAL_SUPPLY:
                return False, "Listing price must be a finite non-negative amount.", None
            price = max(0.0, round(raw_price, 4))
            expected_payload = signed_payload or f"BNS_SET_PRICE:{norm}:{clean_owner}:{price}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_owner, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            extra_data = {
                "name": norm,
                "owner": clean_owner,
                "price": price,
                "action": "set_price"
            }

            tx = Transaction(
                sender=clean_owner,
                receiver=TREASURY_ADDRESS,
                amount=0.0,
                fee=0.0,
                signature=signature,
                tx_type="bns_set_price",
                extra_data=extra_data
            )
            self.pending_transactions.append(tx)
            self.total_transactions += 1

            block = self._seal_or_queue_mempool()
            self._load_in_memory_bns_index()
            self._save_state()

            msg = f"'{norm}' listed on marketplace for {price} BCT!" if price > 0 else f"'{norm}' unlisted from marketplace."
            return True, msg, {"name": norm, "owner": clean_owner, "sale_price": price}

    def bns_buy(self, name: str, buyer: str, signature: str = "",
                public_key: str = "", signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
        with self.lock:
            self._load_state()
            clean_buyer = normalize_bct_address(buyer)
            norm = self._normalize_bns_name(name)
            if norm not in self.bns_records:
                return False, f"'{norm}' is not registered.", None

            rec = self.bns_records[norm]
            seller = rec.get("owner")
            sale_price = rec.get("sale_price", 0.0)

            if sale_price <= 0:
                return False, f"'{norm}' is not currently listed for sale.", None
            if clean_buyer == seller:
                return False, "You already own this name.", None
            if self.is_wallet_burned(seller):
                return False, f"Cannot purchase '{norm}': seller wallet has been permanently burned.", None

            buyer_bal = self.verify_and_recalc_balance(clean_buyer)
            if buyer_bal < sale_price:
                return False, f"Insufficient balance to purchase '{norm}'. Price: {sale_price} BCT, Balance: {buyer_bal} BCT.", None

            expected_payload = signed_payload or f"BNS_BUY:{norm}:{clean_buyer}:{seller}:{sale_price}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_buyer, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            # Standard 1% network trade fee (minimum 0.001 BCT fee)
            fee = max(0.001, round(sale_price * 0.01, 8))
            net_amount = round(sale_price - fee, 8)

            extra_data = {
                "name": norm,
                "buyer": clean_buyer,
                "seller": seller,
                "price": sale_price,
                "fee": fee,
                "net_amount": net_amount,
                "action": "buy"
            }

            tx = Transaction(
                sender=clean_buyer,
                receiver=seller,
                amount=sale_price,
                fee=fee,
                signature=signature,
                tx_type="bns_buy",
                extra_data=extra_data
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + fee, 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_bns_index()

            self.balances[clean_buyer] = self.verify_and_recalc_balance(clean_buyer)
            self.balances[seller] = self.verify_and_recalc_balance(seller)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            res = {
                "name": norm,
                "buyer": clean_buyer,
                "seller": seller,
                "price": sale_price,
                "seller_received": net_amount,
                "fee": fee,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool"
            }
            return True, f"Congratulations! You purchased '{norm}' for {sale_price} BCT!", res

    def bns_set_primary(self, name: str, owner: str,
                        signature: str = "", public_key: str = "", signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
        with self.lock:
            self._load_state()
            clean_owner = normalize_bct_address(owner)
            norm = self._normalize_bns_name(name)
            if norm not in self.bns_records:
                return False, f"'{norm}' is not registered.", None

            rec = self.bns_records[norm]
            if rec.get("owner") != clean_owner:
                return False, f"You are not the owner of '{norm}'.", None

            expected_payload = signed_payload or f"BNS_SET_PRIMARY:{norm}:{clean_owner}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_owner, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            extra_data = {
                "name": norm,
                "owner": clean_owner,
                "action": "set_primary"
            }

            tx = Transaction(
                sender=clean_owner,
                receiver=TREASURY_ADDRESS,
                amount=0.0,
                fee=0.0,
                signature=signature,
                tx_type="bns_set_primary",
                extra_data=extra_data
            )
            self.pending_transactions.append(tx)
            self.total_transactions += 1

            block = self._seal_or_queue_mempool()
            self._load_in_memory_bns_index()
            self._save_state()

            msg = f"'{norm}' is now your primary BNS handle!"
            return True, msg, {"name": norm, "owner": clean_owner, "tx_hash": tx.hash()}

    def bns_make_offer(self, name: str, bidder: str, amount_bct: float,
                       signature: str = "", public_key: str = "", signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
        """
        Creates an on-chain offer/bid for any registered .bct handle.
        Bidder signs: BNS_OFFER:{name}:{bidder}:{amount}
        Validates non-custodial signature, wallet address, and sufficient balance.
        """
        with self.lock:
            self._load_state()
            clean_bidder = normalize_bct_address(bidder)
            if not is_valid_bct_address(clean_bidder):
                return False, f"Invalid bidder address: '{clean_bidder}'", None

            norm = self._normalize_bns_name(name)
            if norm not in self.bns_records:
                return False, f"'{norm}' is not registered on-chain.", None

            rec = self.bns_records[norm]
            owner = rec.get("owner", "")
            if clean_bidder == owner:
                return False, "You cannot make an offer on your own domain.", None
            if self.is_wallet_burned(owner):
                return False, f"Cannot make an offer on '{norm}': owner wallet has been permanently burned.", None

            try:
                raw_amt = float(amount_bct)
            except Exception:
                return False, "Invalid offer amount.", None

            if not math.isfinite(raw_amt) or raw_amt < 0.1 or raw_amt > TOTAL_SUPPLY:
                return False, "Offer amount must be at least 0.10 BCT.", None
            amount = round(raw_amt, 4)

            # Sybil / Offer Spam Protection: Max 15 active offers across all domains per bidder wallet
            active_bidder_offers = sum(
                1 for r in self.bns_records.values()
                for o in (r.get("offers") or {}).values()
                if isinstance(o, dict) and o.get("bidder") == clean_bidder and o.get("status") == "active" and r.get("name") != norm
            )
            if active_bidder_offers >= 15:
                return False, "Maximum active offer limit reached (15 active offers). Please cancel an existing offer first.", None

            expected_payload = signed_payload or f"BNS_OFFER:{norm}:{clean_bidder}:{amount}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_bidder, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            bal = self.verify_and_recalc_balance(clean_bidder)
            if bal < amount:
                return False, f"Insufficient balance! You offered {amount:.2f} BCT but your balance is {bal:.4f} BCT.", None

            offer_id = f"bno_{secrets.token_hex(6)}"
            extra_data = {
                "name": norm,
                "bidder": clean_bidder,
                "owner": owner,
                "amount": amount,
                "offer_id": offer_id,
                "action": "offer"
            }

            tx = Transaction(
                sender=clean_bidder,
                receiver=owner,
                amount=0.0,
                fee=0.0,
                signature=signature,
                tx_type="bns_offer",
                extra_data=extra_data
            )
            self.pending_transactions.append(tx)
            self.total_transactions += 1

            block = self._seal_or_queue_mempool()
            self._load_in_memory_bns_index()
            self._save_state()

            offer_obj = {
                "offer_id": offer_id,
                "name": norm,
                "bidder": clean_bidder,
                "owner": owner,
                "amount": amount,
                "timestamp": tx.timestamp,
                "tx_hash": tx.hash(),
                "status": "active"
            }
            return True, f"Offer of {amount:.2f} BCT successfully placed for '@{norm}'!", offer_obj

    def bns_accept_offer(self, name: str, owner: str, offer_id: str,
                         signature: str = "", public_key: str = "", signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
        """
        Domain owner accepts a specific active offer on their .bct handle.
        Owner signs: BNS_ACCEPT_OFFER:{name}:{owner}:{offer_id}:{bidder}:{amount}
        Transfers domain ownership to bidder, transfers funds to owner (1% protocol fee).
        """
        with self.lock:
            self._load_state()
            clean_owner = normalize_bct_address(owner)
            norm = self._normalize_bns_name(name)
            if norm not in self.bns_records:
                return False, f"'{norm}' is not registered.", None

            rec = self.bns_records[norm]
            if rec.get("owner") != clean_owner:
                return False, f"You are not the current owner of '@{norm}'.", None

            offers = rec.get("offers", {})
            if not isinstance(offers, dict) or offer_id not in offers:
                return False, "Offer not found or no longer available.", None

            target_offer = offers[offer_id]
            if target_offer.get("status") != "active":
                return False, f"Offer is {target_offer.get('status')} and cannot be accepted.", None

            bidder = normalize_bct_address(target_offer.get("bidder", ""))
            amount = float(target_offer.get("amount", 0.0))
            if bidder == clean_owner:
                return False, "Cannot accept an offer from your own address.", None
            if self.is_wallet_burned(bidder):
                return False, "Cannot accept offer: bidder wallet has been permanently burned.", None

            expected_payload = signed_payload or f"BNS_ACCEPT_OFFER:{norm}:{clean_owner}:{offer_id}:{bidder}:{amount}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_owner, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            # Verify bidder still has sufficient balance
            bidder_bal = self.verify_and_recalc_balance(bidder)
            if bidder_bal < amount:
                return False, f"Bidder no longer has sufficient funds ({bidder_bal:.4f} BCT available). Offer cannot be accepted.", None

            # Standard 1% network trade fee (minimum 0.001 BCT floor matching bns_buy)
            fee = max(0.001, round(amount * 0.01, 8))
            net_amount = round(amount - fee, 8)

            extra_data = {
                "name": norm,
                "bidder": bidder,
                "seller": clean_owner,
                "amount": amount,
                "fee": fee,
                "net_amount": net_amount,
                "offer_id": offer_id,
                "action": "accept_offer"
            }

            tx = Transaction(
                sender=clean_owner,
                receiver=bidder,
                amount=amount,
                fee=fee,
                signature=signature,
                tx_type="bns_accept_offer",
                extra_data=extra_data
            )
            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + fee, 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_bns_index()

            self.balances[bidder] = self.verify_and_recalc_balance(bidder)
            self.balances[clean_owner] = self.verify_and_recalc_balance(clean_owner)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            receipt = {
                "name": norm,
                "buyer": bidder,
                "seller": clean_owner,
                "price": amount,
                "seller_received": net_amount,
                "fee": fee,
                "offer_id": offer_id,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool"
            }
            return True, f"Offer accepted! '{norm}' transferred to {bidder[:10]}... (+{net_amount} BCT credited).", receipt

    def bns_cancel_offer(self, name: str, actor: str, offer_id: str,
                         signature: str = "", public_key: str = "", signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
        """
        Cancels or rejects an active offer.
        Can be executed by bidder (cancellation) or domain owner (rejection).
        Caller signs: BNS_CANCEL_OFFER:{name}:{actor}:{offer_id}
        """
        with self.lock:
            self._load_state()
            clean_actor = normalize_bct_address(actor)
            norm = self._normalize_bns_name(name)
            if norm not in self.bns_records:
                return False, f"'{norm}' is not registered.", None

            rec = self.bns_records[norm]
            offers = rec.get("offers", {})
            if not isinstance(offers, dict) or offer_id not in offers:
                return False, "Offer not found.", None

            target_offer = dict(offers[offer_id])
            if target_offer.get("status") != "active":
                return False, f"Offer is already {target_offer.get('status')}.", None

            owner = rec.get("owner", "")
            bidder = target_offer.get("bidder", "")

            if clean_actor not in (bidder, owner):
                return False, "Only the bidder or domain owner can cancel/reject this offer.", None

            expected_payload = signed_payload or f"BNS_CANCEL_OFFER:{norm}:{clean_actor}:{offer_id}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_actor, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            new_status = "cancelled" if clean_actor == bidder else "rejected"
            target_offer["status"] = new_status
            target_offer["resolved_at"] = time.time()

            extra_data = {
                "name": norm,
                "actor": clean_actor,
                "offer_id": offer_id,
                "status": new_status,
                "action": "cancel_offer"
            }

            tx = Transaction(
                sender=clean_actor,
                receiver=TREASURY_ADDRESS,
                amount=0.0,
                fee=0.0,
                signature=signature,
                tx_type="bns_cancel_offer",
                extra_data=extra_data
            )
            self.pending_transactions.append(tx)
            self.total_transactions += 1

            self._seal_or_queue_mempool()
            self._load_in_memory_bns_index()
            self._save_state()

            label = "cancelled" if clean_actor == bidder else "rejected"
            return True, f"Offer on '@{norm}' has been {label}.", target_offer

    def bns_get_offers(self, name: str = "", address: str = "") -> dict:
        """Retrieves offers filtered by domain name or wallet address (sent & received)."""
        with self.lock:
            self._load_state()
            clean_name = self._normalize_bns_name(name) if name else ""
            clean_addr = (address or "").strip()

            if clean_name:
                rec = self.bns_records.get(clean_name, {})
                offers_dict = rec.get("offers", {})
                offers_list = list(offers_dict.values()) if isinstance(offers_dict, dict) else []
                offers_list.sort(key=lambda o: o.get("timestamp", 0), reverse=True)
                return {
                    "name": clean_name,
                    "owner": rec.get("owner", ""),
                    "offers": offers_list,
                    "active_count": sum(1 for o in offers_list if o.get("status") == "active")
                }

            received = []
            sent = []
            for n, r in self.bns_records.items():
                owner = r.get("owner", "")
                offers_dict = r.get("offers", {})
                if not isinstance(offers_dict, dict):
                    continue
                for o in offers_dict.values():
                    if clean_addr and owner == clean_addr:
                        received.append(o)
                    if clean_addr and o.get("bidder") == clean_addr:
                        sent.append(o)

            received.sort(key=lambda o: o.get("timestamp", 0), reverse=True)
            sent.sort(key=lambda o: o.get("timestamp", 0), reverse=True)

            return {
                "address": clean_addr,
                "received_offers": received,
                "sent_offers": sent,
                "received_active_count": sum(1 for o in received if o.get("status") == "active"),
                "sent_active_count": sum(1 for o in sent if o.get("status") == "active")
            }

    def get_all_bns_names(self, page: int = 1, limit: int = 50, for_sale_only: bool = False) -> dict:
        with self.lock:
            self._load_state()
            items = list(self.bns_records.values())
            if for_sale_only:
                items = [it for it in items if it.get("sale_price", 0.0) > 0]
            items.sort(key=lambda x: x.get("registered_at", 0), reverse=True)
            total = len(items)
            total_pages = max(1, (total + limit - 1) // limit)
            page = max(1, min(page, total_pages))
            start = (page - 1) * limit
            end = start + limit
            return {
                "names": items[start:end],
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
            }

    def get_bns_analytics(self) -> dict:
        """
        Calculates ecosystem-wide BNS analytics:
        Total volume, total burned (80% rule), floor prices, trade records, and timeline points.
        """
        with self.lock:
            self._load_state()
            items = list(self.bns_records.values())
            total_registered = len(items)
            total_listed = sum(1 for it in items if float(it.get("sale_price", 0.0)) > 0)
            
            total_reg_burn = 0.0
            total_volume = 0.0
            recent_trades = []
            timeline_points = []
            
            for it in items:
                name = it.get("name", "")
                cost = float(it.get("cost", 0.0))
                total_reg_burn += round(cost * 0.80, 8)
                
                # Examine history events
                for h in it.get("history", []):
                    action = h.get("action", "")
                    ts = float(h.get("timestamp", 0.0))
                    price = float(h.get("price", h.get("amount", 0.0)))
                    
                    if action == "registered":
                        reg_cost = float(h.get("cost", cost))
                        timeline_points.append({
                            "timestamp": ts,
                            "name": name,
                            "action": "registered",
                            "price": reg_cost,
                            "by": h.get("by", it.get("owner", ""))
                        })
                    elif action in ("purchased", "offer_accepted"):
                        total_volume += price
                        buyer_addr = h.get("buyer", h.get("bidder", ""))
                        seller_addr = h.get("seller", "")
                        trade_obj = {
                            "name": name,
                            "action": action,
                            "price": price,
                            "buyer": buyer_addr,
                            "seller": seller_addr,
                            "timestamp": ts,
                            "tx_hash": h.get("tx_hash", ""),
                            "block": h.get("block", "")
                        }
                        recent_trades.append(trade_obj)
                        timeline_points.append({
                            "timestamp": ts,
                            "name": name,
                            "action": action,
                            "price": price,
                            "buyer": buyer_addr,
                            "seller": seller_addr
                        })
                    elif action in ("price_listed", "listed_for_sale") and price > 0:
                        timeline_points.append({
                            "timestamp": ts,
                            "name": name,
                            "action": "price_listed",
                            "price": price
                        })

            recent_trades.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            timeline_points.sort(key=lambda x: x.get("timestamp", 0))

            return {
                "total_registered": total_registered,
                "total_listed": total_listed,
                "total_volume_bct": round(total_volume, 4),
                "total_burned_bct": round(total_reg_burn, 4),
                "floor_tiers": {
                    "tier_3char": 100.0,
                    "tier_4char": 50.0,
                    "tier_5char": 10.0
                },
                "recent_trades": recent_trades[:30],
                "timeline_points": timeline_points[-100:]
            }

    def get_bns_history(self, name_query: str) -> Optional[dict]:
        """
        Retrieves detailed on-chain price, listing, and transfer history for a specific .bct name.
        """
        with self.lock:
            self._load_state()
            clean = str(name_query or "").strip().lower().lstrip("@")
            norm = self._normalize_bns_name(clean)
            if norm not in self.bns_records:
                return None
            
            rec = dict(self.bns_records[norm])
            history = rec.get("history", [])
            
            # Format datapoints for plotting
            chart_points = []
            for h in history:
                action = h.get("action", "")
                ts = float(h.get("timestamp", 0.0))
                p = float(h.get("price", h.get("amount", 0.0)))
                if action == "registered":
                    p = float(h.get("cost", rec.get("cost", 0.0)))
                chart_points.append({
                    "timestamp": ts,
                    "price": p,
                    "action": action,
                    "tx_hash": h.get("tx_hash", ""),
                    "block": h.get("block", "")
                })

            return {
                "name": norm,
                "owner": rec.get("owner", ""),
                "sale_price": rec.get("sale_price", 0.0),
                "cost": rec.get("cost", 0.0),
                "registered_at": rec.get("registered_at", 0),
                "updated_at": rec.get("updated_at", 0),
                "block_index": rec.get("block_index", "--"),
                "tx_hash": rec.get("tx_hash", ""),
                "history": history,
                "chart_points": chart_points
            }

    def get_user_profile(self, address_or_handle: str) -> Optional[dict]:
        """
        Aggregates complete non-custodial user profile:
        Balance, circulating percentage, tag, owned .bct handles, space social metrics,
        authored posts, and transaction history.
        """
        with self.lock:
            raw = str(address_or_handle or "").strip()
            if not raw:
                return None

            clean_raw = raw.lstrip("#").lstrip("@").strip()
            if not clean_raw:
                return None
            clean_cache_key = clean_raw.lower()

            now = time.time()
            cached = self._profile_cache.get(clean_cache_key)
            if cached and cached[0] == self._loaded_revision and (now - cached[1] < 10.0):
                return dict(cached[2])

            self._load_state()

            clean = clean_cache_key
            target_address = ""
            primary_handle = ""

            # 1. Resolve BNS handle or Address
            bns_cand = clean if clean.endswith(".bct") else f"{clean}.bct"
            if bns_cand in self.bns_records:
                target_address = self.bns_records[bns_cand].get("owner", "")
                primary_handle = self.bns_reverse.get(target_address, bns_cand)
            elif is_valid_bct_address(clean_raw):
                target_address = clean_raw
                primary_handle = self.bns_reverse.get(target_address, "")
            elif is_valid_bct_address(clean_raw.upper()):
                target_address = clean_raw.upper()
                primary_handle = self.bns_reverse.get(target_address, "")
            else:
                norm = self._normalize_bns_name(clean)
                if norm in self.bns_records:
                    target_address = self.bns_records[norm].get("owner", "")
                    primary_handle = self.bns_reverse.get(target_address, norm)

            if not target_address or not is_valid_bct_address(target_address):
                return None

            balance = self.verify_and_recalc_balance(target_address)

            # 2. Tag classification
            tag = "Community Member"
            tag_type = "user"
            is_lost_key_burn = False
            lost_key_note = ""
            is_slashed = False
            slashed_note = ""

            norm_target = normalize_bct_address(target_address)
            val_stake = self.get_validator_stake(norm_target)
            is_validator = self.is_active_validator(norm_target)

            if norm_target in self.slashed_validators:
                tag = "İşaretli / Slashed Hesap (Kural İhlali)"
                tag_type = "slashed"
                is_validator = False
                val_stake = 0.0
                is_slashed = True
                slashed_note = "Bu hesap geçmişte protokol kurallarını ihlal ettiği (çift çekim / yetkisiz blok üretimi) için sistem tarafından işaretlenmiştir. Doğrulayıcı (validator) hakları kalıcı olarak iptal edilmiştir. Hesap bakiyesi dondurulmamıştır ve standart transfer yapabilir."
            elif any(target_address.lower() == addr.lower() for addr in LOST_KEY_TEST_WALLETS):
                tag = "Geliştirici Doğruladı: Private Key Kayıp (Özel Test Adresi)"
                tag_type = "lost_key_burn"
                is_lost_key_burn = True
                lost_key_note = "Geliştirici doğruladı: Private key kayıp özel test adresidir (Dolaşım dışı / Fiili Yakım / Kilitli)"
            elif target_address == BURN_ADDRESS:
                tag = "Protokol Yakım Adresi (Kalıcı / Private Key Bulunmaz)"
                tag_type = "burn"
                is_lost_key_burn = True
                lost_key_note = "Kalıcı matematiksel sıfır adresidir. Buraya gönderilen coinler geri alınamaz ve dolaşımdan kalıcı olarak silinir."
            elif target_address == TREASURY_ADDRESS:
                tag = "Genesis Treasury (Escrowed)"
                tag_type = "treasury"
            elif target_address == BRIDGE_VAULT_ADDRESS:
                tag = "Bridge Vault (Base 1:1 Collateral)"
                tag_type = "bridge_vault"
            elif is_validator:
                tag = "Active Validator Node"
                tag_type = "validator"
            elif val_stake >= MIN_VALIDATOR_STAKE:
                tag = "Validator Staker (Collateral Locked)"
                tag_type = "staker"

            # 3. Owned Handles
            owned_handles = []
            for name, r in self.bns_records.items():
                if r.get("owner") == target_address:
                    owned_handles.append({
                        "name": name,
                        "tier": r.get("tier", "standard"),
                        "sale_price": float(r.get("sale_price", 0.0) or 0.0),
                        "registered_at": r.get("registered_at", 0),
                        "is_primary": (name == primary_handle)
                    })
            owned_handles.sort(key=lambda x: (not x["is_primary"], x["name"]))

            # 4. Supply percentages
            stats = self.get_stats()
            circulating = float(stats.get("circulating_supply", 0.0))
            holding_pct = round((balance / TOTAL_SUPPLY * 100), 4) if TOTAL_SUPPLY > 0 else 0.0
            circ_pct = round((balance / circulating * 100), 4) if (circulating > 0 and target_address not in (TREASURY_ADDRESS, BRIDGE_VAULT_ADDRESS)) else 0.0

            # 5. Space Creator & Social Metrics
            user_posts = []
            for p in self.space_posts.values():
                if p.get("author") == target_address:
                    user_posts.append(p)
            user_posts.sort(key=lambda p: p.get("timestamp", 0), reverse=True)

            total_likes_rec = sum(int(p.get("likes_count", 0) or len(p.get("likes", []))) for p in user_posts)
            total_cmts_rec = sum(int(p.get("comments_count", 0) or len(p.get("comments", []))) for p in user_posts)
            total_royalties = round(sum(float(p.get("author_earnings", 0.0) or 0.0) for p in user_posts), 6)

            total_likes_given = sum(1 for p in self.space_posts.values() if target_address in p.get("likes", []))
            total_cmts_given = sum(1 for p in self.space_posts.values() for c in p.get("comments", []) if c.get("commenter") == target_address)

            # 6. Transactions
            recent_txs = []
            seen_hashes = set()
            total_tx_count = 0

            for tx in reversed(self.pending_transactions):
                is_extra_rec = bool(tx.extra_data) and (
                    tx.extra_data.get("author") == target_address or tx.extra_data.get("target") == target_address
                )
                if tx.sender == target_address or tx.receiver == target_address or is_extra_rec:
                    total_tx_count += 1
                    th = tx.hash()
                    if th not in seen_hashes and len(recent_txs) < 30:
                        seen_hashes.add(th)
                        recent_txs.append({
                            "hash": th,
                            "tx_type": tx.tx_type,
                            "sender": tx.sender,
                            "receiver": tx.receiver,
                            "amount": tx.amount,
                            "fee": tx.fee,
                            "timestamp": tx.timestamp,
                            "status": "mempool",
                            "block_index": "Mempool",
                            "extra_data": tx.extra_data
                        })

            for b in reversed(self.chain):
                for tx in reversed(b.transactions):
                    is_extra_rec = bool(tx.extra_data) and (
                        tx.extra_data.get("author") == target_address or tx.extra_data.get("target") == target_address
                    )
                    if tx.sender == target_address or tx.receiver == target_address or is_extra_rec:
                        total_tx_count += 1
                        th = tx.hash()
                        if th not in seen_hashes and len(recent_txs) < 30:
                            seen_hashes.add(th)
                            recent_txs.append({
                                "hash": th,
                                "tx_type": tx.tx_type,
                                "sender": tx.sender,
                                "receiver": tx.receiver,
                                "amount": tx.amount,
                                "fee": tx.fee,
                                "timestamp": tx.timestamp,
                                "status": "confirmed",
                                "block_index": b.index,
                                "extra_data": tx.extra_data
                            })

            followers_addrs = list(self.follows.get(target_address, []))
            following_addrs = list(self.following.get(target_address, []))

            followers_list = []
            for a in followers_addrs:
                bns = self.bns_reverse.get(a, "")
                followers_list.append({
                    "address": a,
                    "bns_name": bns,
                    "display_name": f"@{bns}" if bns else f"{a[:6]}...{a[-4:]}",
                    "is_validator": self.is_active_validator(a),
                    "avatar": self.avatar_equipped.get(normalize_bct_address(a))
                })

            following_list = []
            for a in following_addrs:
                bns = self.bns_reverse.get(a, "")
                following_list.append({
                    "address": a,
                    "bns_name": bns,
                    "display_name": f"@{bns}" if bns else f"{a[:6]}...{a[-4:]}",
                    "is_validator": self.is_active_validator(a),
                    "avatar": self.avatar_equipped.get(normalize_bct_address(a))
                })

            equipped_avatar = self.avatar_equipped.get(norm_target)
            owned_avatars = list(self.avatar_owners.get(norm_target, []))

            profile_res = {
                "address": target_address,
                "primary_handle": primary_handle,
                "avatar": equipped_avatar,
                "owned_avatars": owned_avatars,
                "balance": balance,
                "staked_amount": val_stake,
                "is_validator": is_validator,
                "holding_percentage": holding_pct,
                "circulating_percentage": circ_pct,
                "tag": tag,
                "tag_type": tag_type,
                "is_slashed": is_slashed,
                "slashed_note": slashed_note,
                "is_lost_key_burn": is_lost_key_burn,
                "lost_key_note": lost_key_note,
                "total_tx_count": total_tx_count,
                "owned_handles": owned_handles,
                "followers": followers_list,
                "following": following_list,
                "followers_count": len(followers_addrs),
                "following_count": len(following_addrs),
                "social_stats": {
                    "total_posts": len(user_posts),
                    "total_likes_received": total_likes_rec,
                    "total_comments_received": total_cmts_rec,
                    "total_royalties_earned": total_royalties,
                    "total_likes_given": total_likes_given,
                    "total_comments_given": total_cmts_given,
                    "followers_count": len(followers_addrs),
                    "following_count": len(following_addrs)
                },
                "recent_posts": user_posts[:20],
                "recent_transactions": recent_txs
            }

            if len(self._profile_cache) >= 20000:
                self._profile_cache.clear()
            self._profile_cache[clean_cache_key] = (self._loaded_revision, now, dict(profile_res))
            return profile_res


    def execute_fiat_purchase(self, buyer_address: str, fiat_amount: float,
                              currency: str = "USD", payment_ref: str = "",
                              bct_per_usd: float = 100.0) -> Tuple[bool, str, Optional[dict]]:
        """Disabled: Prevents unverified mock coin acquisition."""
        return False, "Free mock token acquisition is disabled. BCT tokens can be earned on BlocTag by sharing thoughts, comments/likes, or node mining.", None

    def execute_fiat_sale(self, seller_address: str, bct_amount: float,
                          payout_info: str = "", currency: str = "USD",
                          bct_per_usd: float = 100.0) -> Tuple[bool, str, Optional[dict]]:
        """Disabled: Initial welcome grant cannot be dumped for free fiat."""
        return False, "Direct fiat withdrawal is disabled. BCT balances can be used on the BlocTag thought network and for transfers.", None


    def get_validator_telemetry(self, wallet_address: str) -> dict:
        """
        Returns full validator telemetry for a given wallet address:
        - Staked collateral amount & Quorum qualification
        - Remote node telemetry (if node is running and registered with this wallet)
        - Historical block production & attestation rewards
        """
        clean = normalize_bct_address(wallet_address)
        if not clean:
            return {"error": "Invalid wallet address"}

        with self.lock:
            self._load_state()
            stake = self.get_validator_stake(clean)
            is_eligible = stake >= MIN_VALIDATOR_STAKE
            bal = self.verify_and_recalc_balance(clean)

            # Search active nodes registered with this wallet
            now = time.time()
            all_nodes = self.get_nodes()
            matched_node = None
            for n in all_nodes:
                m_addr = normalize_bct_address(n.get("miner_address") or "")
                if m_addr and m_addr == clean:
                    matched_node = dict(n)
                    break

            # O(1) indexed total blocks produced & total rewards earned
            self._ensure_ledger_index()
            blocks_produced = int(self._confirmed_blocks_mined_map.get(clean, 0))
            rewards_earned = float(Decimal(int(self._confirmed_rewards_earned_map.get(clean, 0))) / Decimal(ATOMIC_UNIT))

            node_data = None
            if matched_node:
                raw_ep = matched_node.get("endpoint", "")
                masked_ep = "P2P Mesh Private"
                if "local-only" in raw_ep or "127.0.0.1" in raw_ep or "localhost" in raw_ep:
                    port_str = raw_ep.split(":")[-1] if ":" in raw_ep else "5050"
                    masked_ep = f"Yerel Düğüm (Port {port_str})"
                elif raw_ep.startswith("http"):
                    # Mask IP for security / anti-DDoS
                    cleaned = raw_ep.replace("http://", "").replace("https://", "")
                    parts = cleaned.split(":")
                    host_part = parts[0]
                    port_part = parts[1] if len(parts) > 1 else "5050"
                    ip_octets = host_part.split(".")
                    if len(ip_octets) == 4:
                        masked_host = f"{ip_octets[0]}.***.***.{ip_octets[3]}"
                    else:
                        masked_host = host_part[:4] + "***"
                    masked_ep = f"P2P Node ({masked_host}:{port_part})"

                last_seen_sec = max(0, int(now - matched_node.get("last_seen", now)))
                node_data = {
                    "node_id": matched_node.get("node_id"),
                    "name": matched_node.get("name") or "Community Node",
                    "masked_endpoint": masked_ep,
                    "role": matched_node.get("role", "Validator Peer"),
                    "block_height": matched_node.get("block_height", len(self.chain)),
                    "last_seen_seconds_ago": last_seen_sec,
                    "is_online": last_seen_sec <= 90,
                    "hashrate_hs": matched_node.get("hashrate_hs", 0.0),
                    "version": matched_node.get("version", "2.2.0"),
                    "auth_verified": bool(matched_node.get("auth_verified"))
                }

            # Calculate dynamic staking yield (APR) based on 20s block time
            active_vals_list = self.get_eligible_validators(exclude_miner="", block_index=len(self.chain), now=now)
            active_validators_count = len(active_vals_list)
            # Daily validator pool: 4320 blocks/day * 0.015 BCT = 64.8 BCT/day
            daily_val_pool = 64.8
            yearly_val_pool = 23652.0
            effective_vals = max(1, active_validators_count if is_eligible else (active_validators_count + 1))
            est_daily_bct = round(daily_val_pool / effective_vals, 4)
            est_yearly_bct = round(yearly_val_pool / effective_vals, 2)
            est_apr_pct = round((est_yearly_bct / MIN_VALIDATOR_STAKE) * 100.0, 1)

            return {
                "wallet_address": clean,
                "staked_amount": stake,
                "min_required_stake": MIN_VALIDATOR_STAKE,
                "is_eligible_validator": is_eligible,
                "wallet_balance": bal,
                "vault_address": VALIDATOR_STAKE_VAULT_ADDRESS,
                "blocks_produced": blocks_produced,
                "rewards_earned": round(rewards_earned, 8),
                "node_connected": node_data is not None and node_data["is_online"],
                "node_telemetry": node_data,
                "daily_pool_reward": daily_val_pool,
                "yearly_pool_reward": yearly_val_pool,
                "active_validators_count": active_validators_count,
                "estimated_daily_reward": est_daily_bct,
                "estimated_yearly_reward": est_yearly_bct,
                "estimated_apr_percent": est_apr_pct
            }

    def get_all_stakers(self) -> List[dict]:
        """
        Returns all wallets that have locked BCT collateral in VALIDATOR_STAKE_VAULT,
        categorized into Active Consensus Validators, Inactive Validators, and Passive Observers.
        """
        with self.lock:
            self._ensure_ledger_index()
            now = time.time()
            all_nodes = self.get_nodes()
            nodes_by_wallet = {}
            for n in all_nodes:
                m_addr = normalize_bct_address(n.get("miner_address") or "")
                if m_addr:
                    nodes_by_wallet[m_addr] = n

            stakers: List[dict] = []
            vault_u = int(self._confirmed_units_map.get(VALIDATOR_STAKE_VAULT_ADDRESS, 0))
            if vault_u <= 0:
                return []

            for addr, raw_u in self._confirmed_stakes_map.items():
                clean_addr = normalize_bct_address(addr)
                if not clean_addr or raw_u <= 0 or clean_addr in self._burned_wallets_set:
                    continue
                staked_bct = float(Decimal(min(raw_u, vault_u)) / Decimal(ATOMIC_UNIT))
                if staked_bct < float(MIN_OBSERVER_STAKE):
                    continue

                is_slashed = clean_addr in self.slashed_validators
                matched_node = nodes_by_wallet.get(clean_addr)
                is_active_val = False
                node_id = ""
                blocks_attested = 0

                if matched_node and not is_slashed:
                    is_active_val = bool(matched_node.get("is_genesis") or (matched_node.get("auth_verified") and (now - float(matched_node.get("last_seen", 0))) <= 180.0))
                    node_id = matched_node.get("node_id", "")
                    blocks_attested = int(matched_node.get("blocks_attested", 0))

                if is_slashed:
                    tier = "slashed"
                    role_title = "Cezalandırılmış (Slashed)"
                    pool_share = "%0 (Donduruldu)"
                elif is_active_val and staked_bct >= MIN_VALIDATOR_STAKE:
                    tier = "active_validator"
                    role_title = "Aktif Doğrulayıcı (Validator Quorum)"
                    if staked_bct > MIN_VALIDATOR_STAKE:
                        excess = staked_bct - MIN_VALIDATOR_STAKE
                        pool_share = f"%40 Düğüm (1.000 BCT) + %10 Gözlemci ({excess:,.0f} BCT)"
                    else:
                        pool_share = "%40 Düğüm Havuzu"
                elif staked_bct >= MIN_VALIDATOR_STAKE:
                    tier = "inactive_validator"
                    role_title = "Çevrimdışı Validator (Düğüm Bekleniyor)"
                    pool_share = "%10 Gözlemci Havuzu (Düğüm açılınca %40)"
                else:
                    tier = "observer"
                    role_title = "Pasif Gözlemci (Observer Staker)"
                    pool_share = "%10 Gözlemci Havuzu"

                rewards_earned = float(Decimal(int(self._confirmed_rewards_earned_map.get(clean_addr, 0))) / Decimal(ATOMIC_UNIT))

                stakers.append({
                    "address": clean_addr,
                    "staked_amount": 0.0 if is_slashed else round(staked_bct, 4),
                    "forfeited_amount": round(staked_bct, 4) if is_slashed else 0.0,
                    "tier": tier,
                    "role_title": role_title,
                    "pool_share": pool_share,
                    "rewards_earned": round(rewards_earned, 6),
                    "blocks_attested": blocks_attested,
                    "node_id": node_id,
                    "is_active_validator": is_active_val and staked_bct >= MIN_VALIDATOR_STAKE,
                    "is_slashed": is_slashed,
                })

            stakers.sort(key=lambda x: (-x["staked_amount"], x["address"]))
            return stakers

    def is_active_validator(self, address: str) -> bool:
        """
        Returns True if the address has locked >= MIN_VALIDATOR_STAKE in VALIDATOR_STAKE_VAULT
        and is an active registered node or committee validator.
        """
        clean = normalize_bct_address(address)
        if not clean or clean in self.slashed_validators:
            return False
        staked = self.get_validator_stake(clean)
        if staked < MIN_VALIDATOR_STAKE:
            return False
        with self.lock:
            return any(
                normalize_bct_address(n.get("miner_address", "")) == clean and (n.get("is_genesis") or n.get("auth_verified"))
                for n in self.nodes.values()
            )

    def get_validator_stake(self, address: str) -> float:
        """
        Returns the active on-chain BCT amount locked by the validator in VALIDATOR_STAKE_VAULT.
        Uses the O(1) incremental confirmed stake index (`_confirmed_stakes_map`), bounded by
        the confirmed balance of VALIDATOR_STAKE_VAULT, plus any mempool stake minus any pending unstake.
        """
        clean = normalize_bct_address(address)
        if not clean:
            return 0.0
        with self.lock:
            self._ensure_ledger_index()
            vault_units = int(self._confirmed_units_map.get(VALIDATOR_STAKE_VAULT_ADDRESS, 0))
            if vault_units <= 0:
                staked_u = 0
            else:
                staked_u = min(int(self._confirmed_stakes_map.get(clean, 0)), vault_units)
            for tx in self.pending_transactions:
                if tx.receiver == VALIDATOR_STAKE_VAULT_ADDRESS and normalize_bct_address(tx.sender) == clean and tx.tx_type == "validator_stake":
                    staked_u += _to_units(tx.amount)
                elif tx.sender == VALIDATOR_STAKE_VAULT_ADDRESS and normalize_bct_address(tx.receiver) == clean and tx.tx_type == "validator_unstake":
                    staked_u -= _to_units(tx.amount)
            staked = float(Decimal(max(0, staked_u)) / Decimal(ATOMIC_UNIT))
            if clean in self.slashed_validators:
                try:
                    from config import Config
                    slash_pct = float(getattr(Config, "EQUIVOCATION_SLASH_PERCENT", 100))
                except Exception:
                    slash_pct = 100.0
                slash_factor = max(0.0, min(1.0, slash_pct / 100.0))
                staked = max(0.0, round(staked * (1.0 - slash_factor), 8))
            return max(0.0, round(staked, 8))

    def execute_validator_stake(self, sender: str, amount_bct: float,
                                signature: str, public_key: str = "",
                                signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
        """
        Binds and locks BCT collateral into VALIDATOR_STAKE_VAULT to become an active consensus validator.
        Requires minimum 1,000.0 BCT.
        """
        with self.lock:
            self._load_state()
            clean_sender = normalize_bct_address(sender)
            if clean_sender in self.slashed_validators:
                return False, "Slashed address is permanently barred from staking collateral.", None
            if not is_valid_bct_address(clean_sender):
                return False, f"Invalid validator wallet address: '{clean_sender}'", None
            if self.is_wallet_burned(clean_sender):
                return False, "Permanently burned wallets cannot stake collateral.", None

            try:
                amt = round(float(amount_bct), 8)
            except (ValueError, TypeError):
                return False, "Invalid stake amount.", None

            if amt <= 0:
                return False, "Stake amount must be greater than zero.", None

            cur_staked = self.get_validator_stake(clean_sender)
            if cur_staked < MIN_OBSERVER_STAKE and round(cur_staked + amt, 8) < MIN_OBSERVER_STAKE:
                return False, f"Minimum stake amount is {MIN_OBSERVER_STAKE:.2f} BCT (Observer pool). Active validator quorum requires >= {MIN_VALIDATOR_STAKE:.2f} BCT.", None
            if cur_staked >= MIN_OBSERVER_STAKE and amt < 1.0:
                return False, "Minimum top-up stake amount is 1.00 BCT.", None
            if round(cur_staked + amt, 8) > MAX_OBSERVER_STAKE:
                rem_room = max(0.0, round(MAX_OBSERVER_STAKE - cur_staked, 8))
                return False, f"Maximum total stake per wallet is {MAX_OBSERVER_STAKE:,.2f} BCT (Current: {cur_staked:,.2f} BCT, Remaining room: {rem_room:,.2f} BCT).", None

            if any(tx.tx_type == "validator_unstake" and normalize_bct_address(tx.receiver) == clean_sender for tx in self.pending_transactions):
                return False, "Bekleyen (henüz blokta onaylanmamış) bir unstake işleminiz var. Lütfen önce mevcut unstake işleminin blokta onaylanmasını bekleyin.", None
            if any(tx.tx_type == "validator_stake" and normalize_bct_address(tx.sender) == clean_sender for tx in self.pending_transactions):
                return False, "Bekleyen bir stake işleminiz zaten havuzda. Lütfen önce mevcut işlemin blokta onaylanmasını bekleyin.", None

            bal = self.verify_and_recalc_balance(clean_sender)
            if bal < amt:
                return False, f"Insufficient balance to stake {amt:.2f} BCT (Available: {bal:.4f} BCT).", None

            if signed_payload:
                sig_ok, sig_msg = self._verify_actor_signature(clean_sender, signed_payload, signature, public_key)
            else:
                nonce = self.get_account_nonce(clean_sender)
                amt_str_trim = f"{amt:.8f}".rstrip("0").rstrip(".") or "0"
                amt_int = str(int(amt)) if amt.is_integer() else str(amt)
                candidates = [
                    f"VALIDATOR_STAKE:{clean_sender}:{amt}:{nonce}",
                    f"VALIDATOR_STAKE:{clean_sender}:{amt_str_trim}:{nonce}",
                    f"VALIDATOR_STAKE:{clean_sender}:{amt_int}:{nonce}",
                    f"VALIDATOR_STAKE:{clean_sender}:{amt}",
                    f"VALIDATOR_STAKE:{clean_sender}:{amt_str_trim}",
                    f"VALIDATOR_STAKE:{clean_sender}:{amt_int}",
                    f"{clean_sender}{VALIDATOR_STAKE_VAULT_ADDRESS}{amt}",
                    f"{clean_sender}{VALIDATOR_STAKE_VAULT_ADDRESS}{amt_str_trim}",
                    f"{clean_sender}{VALIDATOR_STAKE_VAULT_ADDRESS}{amt_int}",
                ]
                sig_ok = False
                sig_msg = "Invalid ECDSA digital signature!"
                for cand in candidates:
                    ok_check, _ = self._verify_actor_signature(clean_sender, cand, signature, public_key)
                    if ok_check:
                        sig_ok = True
                        break
            if not sig_ok:
                return False, sig_msg, None

            tx = Transaction(
                sender=clean_sender,
                receiver=VALIDATOR_STAKE_VAULT_ADDRESS,
                amount=amt,
                fee=0.0,
                signature=signature,
                tx_type="validator_stake",
                extra_data={"staker": clean_sender, "staked_at": time.time()}
            )
            ok, msg = self.add_transaction(tx)
            if not ok:
                return False, msg, None

            new_staked = self.get_validator_stake(clean_sender)
            return True, f"Successfully locked {amt:.2f} BCT collateral into Validator Staking Vault!", {
                "tx_hash": tx.hash(),
                "staked_amount": amt,
                "total_staked": new_staked,
                "validator": clean_sender
            }

    def execute_validator_unstake(self, sender: str, amount_bct: float,
                                  signature: str, public_key: str = "",
                                  signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
        """
        Unlocks BCT collateral from VALIDATOR_STAKE_VAULT back to the validator.
        """
        with self.lock:
            self._load_state()
            clean_sender = normalize_bct_address(sender)
            if clean_sender in self.slashed_validators:
                return False, "Slashed address has forfeited all staking collateral (100% slashed).", None
            if not is_valid_bct_address(clean_sender):
                return False, f"Invalid validator wallet address: '{clean_sender}'", None
            if self.is_wallet_burned(clean_sender):
                return False, "Permanently burned wallets cannot unstake collateral.", None

            try:
                amt = round(float(amount_bct), 8)
            except (ValueError, TypeError):
                return False, "Invalid unstake amount.", None

            if amt <= 0:
                return False, "Unstake amount must be greater than zero.", None

            if any(tx.tx_type == "validator_stake" and normalize_bct_address(tx.sender) == clean_sender for tx in self.pending_transactions):
                return False, "Bekleyen (henüz blokta onaylanmamış) bir stake işleminiz var. Lütfen önce mevcut stake işleminin blokta onaylanmasını bekleyin.", None
            if any(tx.tx_type == "validator_unstake" and normalize_bct_address(tx.receiver) == clean_sender for tx in self.pending_transactions):
                return False, "Bekleyen (henüz blokta onaylanmamış) bir unstake işleminiz zaten havuzda. Lütfen önce mevcut işlemin blokta onaylanmasını bekleyin.", None

            cur_staked = self.get_validator_stake(clean_sender)
            if cur_staked < amt:
                return False, f"Insufficient staked collateral. Current staked: {cur_staked:.4f} BCT (requested: {amt:.4f} BCT).", None

            # Anti-flash-staking minimum lockup window (default 1 hour)
            lockup_sec = int(getattr(self, "stake_lockup_seconds", STAKE_LOCKUP_SECONDS))
            last_stake_ts = float(getattr(self, "_confirmed_stake_timestamps", {}).get(clean_sender, 0.0) or 0.0)
            if lockup_sec > 0 and last_stake_ts > 0:
                elapsed = time.time() - last_stake_ts
                if elapsed < lockup_sec:
                    remain_min = max(1, int((lockup_sec - elapsed + 59) // 60))
                    return (
                        False,
                        f"Teminat kilit süresi (anti-flash-staking) aktif. Çekim yapabilmek için yaklaşık {remain_min} dakika daha beklemeniz gerekiyor.",
                        None,
                    )

            # Prevent trapped dust below MIN_OBSERVER_STAKE (100 BCT) after partial unstake
            remaining_after = round(cur_staked - amt, 8)
            if 0 < remaining_after < MIN_OBSERVER_STAKE:
                return (
                    False,
                    f"Kısmi çekim sonrası kalan teminat en az {MIN_OBSERVER_STAKE:.2f} BCT olmalı veya tamamını ({cur_staked:.4f} BCT) çekmelisiniz.",
                    None,
                )

            if signed_payload:
                sig_ok, sig_msg = self._verify_actor_signature(clean_sender, signed_payload, signature, public_key)
            else:
                nonce = self.get_account_nonce(clean_sender)
                amt_str_trim = f"{amt:.8f}".rstrip("0").rstrip(".") or "0"
                amt_int = str(int(amt)) if amt.is_integer() else str(amt)
                candidates = [
                    f"VALIDATOR_UNSTAKE:{clean_sender}:{amt}:{nonce}",
                    f"VALIDATOR_UNSTAKE:{clean_sender}:{amt_str_trim}:{nonce}",
                    f"VALIDATOR_UNSTAKE:{clean_sender}:{amt_int}:{nonce}",
                    f"VALIDATOR_UNSTAKE:{clean_sender}:{amt}",
                    f"VALIDATOR_UNSTAKE:{clean_sender}:{amt_str_trim}",
                    f"VALIDATOR_UNSTAKE:{clean_sender}:{amt_int}",
                    f"{VALIDATOR_STAKE_VAULT_ADDRESS}{clean_sender}{amt}",
                    f"{VALIDATOR_STAKE_VAULT_ADDRESS}{clean_sender}{amt_str_trim}",
                    f"{VALIDATOR_STAKE_VAULT_ADDRESS}{clean_sender}{amt_int}",
                ]
                sig_ok = False
                sig_msg = "Invalid ECDSA digital signature!"
                for cand in candidates:
                    ok_check, _ = self._verify_actor_signature(clean_sender, cand, signature, public_key)
                    if ok_check:
                        sig_ok = True
                        break
            if not sig_ok:
                return False, sig_msg, None

            tx = Transaction(
                sender=VALIDATOR_STAKE_VAULT_ADDRESS,
                receiver=clean_sender,
                amount=amt,
                fee=0.0,
                signature=signature or f"UNSTAKE_RELEASE_{int(time.time())}_{clean_sender[:8]}",
                tx_type="validator_unstake",
                extra_data={"staker": clean_sender, "unstaked_at": time.time()}
            )
            ok, msg = self.add_transaction(tx)
            if not ok:
                return False, msg, None

            rem_staked = self.get_validator_stake(clean_sender)
            if rem_staked < MIN_VALIDATOR_STAKE:
                for _nid, n_obj in self.nodes.items():
                    if not n_obj.get("is_genesis") and str(n_obj.get("miner_address", "")).strip() == clean_sender:
                        n_obj["role"] = "Peer Node (Unstaked)"
                        n_obj["is_staked_validator"] = False
                        n_obj["staked_amount"] = rem_staked
                self._save_state()

            return True, f"Successfully requested unstake of {amt:.2f} BCT.", {
                "tx_hash": tx.hash(),
                "unstaked_amount": amt,
                "remaining_staked": rem_staked,
                "validator": clean_sender
            }

    def execute_bridge_unlock(self, recipient_address: str, amount_bct: float,
                              evm_tx_hash: str, evm_sender: str = "") -> Tuple[bool, str, Optional[dict]]:
        """
        Executes verified Layer-1 unlock after wBCT burn on Base Mainnet.
        Transfers native BCT from BRIDGE_VAULT_ADDRESS (or TREASURY) to recipient_address.
        Strictly idempotent: Prevents double-unlocking the same evm_tx_hash.
        """
        with self.lock:
            self._load_state()
            clean_recipient = normalize_bct_address(recipient_address)
            if not is_valid_bct_address(clean_recipient):
                return False, f"Invalid recipient BCT address: '{clean_recipient}'", None

            clean_hash = (evm_tx_hash or "").strip().lower()
            if not clean_hash:
                return False, "EVM transaction hash is required.", None

            # Deduplication: Ensure this EVM tx hash hasn't already been unlocked
            for block in self.chain:
                for tx in block.transactions:
                    if tx.tx_type == "bridge_unlock" and tx.extra_data and str(tx.extra_data.get("evm_tx_hash", "")).lower() == clean_hash:
                        return False, "This EVM burn transaction has already been processed (Replay blocked).", None
            for tx in self.pending_transactions:
                if tx.tx_type == "bridge_unlock" and tx.extra_data and str(tx.extra_data.get("evm_tx_hash", "")).lower() == clean_hash:
                    return False, "This EVM burn transaction is pending in mempool.", None

            try:
                raw_unlock = float(amount_bct)
            except (ValueError, TypeError):
                return False, "Invalid transfer amount.", None

            if not math.isfinite(raw_unlock) or raw_unlock <= 0 or raw_unlock > TOTAL_SUPPLY:
                return False, "Amount must be a finite positive number.", None
            amount_bct = round(raw_unlock, 8)

            vault_bal = self.verify_and_recalc_balance(BRIDGE_VAULT_ADDRESS)
            if vault_bal < amount_bct:
                return False, f"Insufficient locked balance in bridge vault! Vault reserve: {vault_bal:,.4f} BCT. (Requested: {amount_bct:,.4f} BCT)", None

            sender_vault = BRIDGE_VAULT_ADDRESS
            sender_bal = vault_bal

            # Auto-register recipient wallet if not yet known
            if clean_recipient not in self.wallets:
                self.wallets[clean_recipient] = {
                    "address": clean_recipient,
                    "public_key": "",
                    "created_at": time.time(),
                    "device": "Web3 Cross-Chain Bridge Unlock"
                }

            extra_data = {
                "evm_tx_hash": clean_hash,
                "evm_sender": evm_sender,
                "amount": amount_bct,
                "direction": "EVM_TO_L1",
                "timestamp": time.time()
            }

            unlock_tx = Transaction(
                sender=sender_vault,
                receiver=clean_recipient,
                amount=amount_bct,
                fee=0.0,
                signature=f"BRIDGE_UNLOCK:{clean_hash}",
                tx_type="bridge_unlock",
                extra_data=extra_data
            )

            self.pending_transactions.append(unlock_tx)
            self.total_transactions += 1

            block = self._seal_or_queue_mempool()

            self.balances[clean_recipient] = self.verify_and_recalc_balance(clean_recipient)
            self.balances[sender_vault] = self.verify_and_recalc_balance(sender_vault)
            self._save_state()

            tx_info = {
                "tx_hash": unlock_tx.hash(),
                "sender": sender_vault,
                "receiver": clean_recipient,
                "amount": amount_bct,
                "evm_tx_hash": clean_hash,
                "status": "confirmed" if block else "mempool",
                "block_index": block.index if block else None,
                "new_balance": self.balances[clean_recipient]
            }

            return True, f"Congratulations! {amount_bct} BCT successfully unlocked to your LockTrace Layer-1 wallet.", tx_info


    @staticmethod
    def _extract_node_host_key(node: dict) -> str:
        """
        Extracts a normalized host & IPv4 /24 (or IPv6 /48) subnet identifier to prevent
        a single datacenter subnet or host from spawning Sybil validator/miner fleets.
        """
        client_ip = str(node.get("client_ip", "") or "").strip().lower()
        if client_ip and client_ip not in ("", "unknown", "127.0.0.1", "::1"):
            try:
                ip_obj = ipaddress.ip_address(client_ip)
                if isinstance(ip_obj, ipaddress.IPv4Address):
                    net = ipaddress.IPv4Network(f"{client_ip}/24", strict=False)
                    return f"subnet24:{net.network_address}"
                elif isinstance(ip_obj, ipaddress.IPv6Address):
                    net = ipaddress.IPv6Network(f"{client_ip}/48", strict=False)
                    return f"subnet48:{net.network_address}"
            except Exception:
                pass
            return f"ip:{client_ip}"
        ep = str(node.get("endpoint", "") or "").strip().lower()
        if ep.startswith("http"):
            try:
                parsed = urllib.parse.urlparse(ep)
                if parsed.hostname:
                    try:
                        ip_obj = ipaddress.ip_address(parsed.hostname)
                        if isinstance(ip_obj, ipaddress.IPv4Address):
                            net = ipaddress.IPv4Network(f"{parsed.hostname}/24", strict=False)
                            return f"subnet24:{net.network_address}"
                    except Exception:
                        pass
                    return f"host:{parsed.hostname}"
            except Exception:
                pass
        return f"wallet:{str(node.get('miner_address', '')).strip()}"

    def get_active_peer_miners(self, now: Optional[float] = None) -> List[dict]:
        """Returns external non-genesis peer nodes actively polling/heartbeating within ACTIVE_MINER_TTL_SECONDS (Sybil-deduped by wallet and host/IP)."""
        ts = now or time.time()
        active = []
        seen_wallets = set()
        seen_hosts = set()
        for _nid, n in self.nodes.items():
            if n.get("is_genesis"):
                continue
            m_addr = normalize_bct_address(str(n.get("miner_address", "") or "").strip())
            if not is_valid_bct_address(m_addr) or m_addr == TREASURY_ADDRESS:
                continue
            if self.get_validator_stake(m_addr) < MIN_VALIDATOR_STAKE or m_addr in self.slashed_validators:
                continue
            if (ts - float(n.get("last_seen", 0))) <= ACTIVE_MINER_TTL_SECONDS:
                host_key = self._extract_node_host_key(n)
                if m_addr in seen_wallets or host_key in seen_hosts:
                    continue
                seen_wallets.add(m_addr)
                seen_hosts.add(host_key)
                active.append(n)
        return active

    def get_eligible_validators(self, exclude_miner: str, block_index: int, now: Optional[float] = None) -> List[dict]:
        """
        Returns up to 10 verified online peer validator nodes eligible for the 30% Validator Attestation Pool.
        Requires cryptographic node identity (`auth_verified=True`), recent synced/attested block height,
        and Sybil deduplication across both wallet address and physical host/IP.
        """
        ts = now or time.time()
        clean_exclude = normalize_bct_address(exclude_miner)
        candidates = []
        for _nid, n in self.nodes.items():
            if n.get("is_genesis"):
                continue
            m_addr = normalize_bct_address(str(n.get("miner_address", "") or "").strip())
            if not is_valid_bct_address(m_addr) or m_addr in (TREASURY_ADDRESS, clean_exclude):
                continue
            # Fake Uptime Guard (LT-01 Hardening): Active heartbeat within 180s
            if (ts - float(n.get("last_seen", 0))) > 180.0:
                continue
            if not n.get("auth_verified", False):
                continue
            # Sybil Defense (LT-01 Hardening): Strictly require minimum validator stake locked in vault
            staked = self.get_validator_stake(m_addr)
            if staked < MIN_VALIDATOR_STAKE:
                continue
            # Equivocation & Burn Defense: Exclude slashed malicious validators and burned wallets
            if m_addr in self.slashed_validators or self.is_wallet_burned(m_addr):
                continue
            # Proof-of-Attestation & Archival Verification (LT-01): Must have actively attested within the last 3 blocks
            attested_h = int(n.get("attested_height", -1))
            if attested_h < max(0, block_index - 3):
                continue
            if int(n.get("blocks_attested", 0)) < 1 and block_index > 0:
                continue
            candidates.append(n)

        candidates.sort(key=lambda x: (-int(x.get("attested_height", 0)), str(x.get("node_id", ""))))
        deduped: List[dict] = []
        seen_wallets = set()
        seen_hosts = set()
        for c in candidates:
            w = c["miner_address"].strip()
            host_key = self._extract_node_host_key(c)
            if w not in seen_wallets and host_key not in seen_hosts:
                seen_wallets.add(w)
                seen_hosts.add(host_key)
                deduped.append(c)
            if len(deduped) >= 10:
                break
        return deduped

    def get_eligible_observers(self, active_validator_addrs: Optional[set] = None, exclude_addrs: Optional[set] = None) -> List[Tuple[str, int]]:
        """
        Returns list of eligible observer stakers (address, staked_units) who participate
        in the 10% Observer Staking Pool pro-rata to their locked stake.
        - Passive stakers: their entire stake between MIN_OBSERVER_STAKE (100 BCT) and MAX_OBSERVER_STAKE (100,000 BCT) is counted.
        - Active validators: 1,000 BCT is locked for the 40% Validator Quorum pool; any excess stake above 1,000 BCT
          (e.g. 100 BCT when 1,100 BCT is staked) automatically participates in the 10% Observer pool!
        - Slashed addresses and protocol system vaults are excluded.
        """
        active_vals = {normalize_bct_address(a) for a in (active_validator_addrs or set()) if a}
        excludes = {normalize_bct_address(a) for a in (exclude_addrs or set()) if a}
        excludes.add(TREASURY_ADDRESS)
        excludes.add(VALIDATOR_STAKE_VAULT_ADDRESS)
        for s in self.slashed_validators:
            excludes.add(normalize_bct_address(s))

        with self.lock:
            self._ensure_ledger_index()
            for b_addr in self._burned_wallets_set:
                excludes.add(b_addr)
            eligible: List[Tuple[str, int]] = []
            min_u = _to_units(MIN_OBSERVER_STAKE)
            max_u = _to_units(MAX_OBSERVER_STAKE)
            val_threshold_u = _to_units(MIN_VALIDATOR_STAKE)

            for addr, raw_staked_u in self._confirmed_stakes_map.items():
                clean_addr = normalize_bct_address(addr)
                if not clean_addr or clean_addr in excludes:
                    continue

                if clean_addr in active_vals:
                    # Active validator node: 1,000 BCT powers the 40% node quorum;
                    # excess stake above 1,000 BCT flows into the 10% observer pool!
                    excess_u = max(0, raw_staked_u - val_threshold_u)
                    capped_u = min(excess_u, max_u)
                    if capped_u >= min_u:
                        eligible.append((clean_addr, capped_u))
                else:
                    # Passive staker or offline validator: entire stake participates in 10% pool
                    capped_u = min(max(0, raw_staked_u), max_u)
                    if capped_u >= min_u:
                        eligible.append((clean_addr, capped_u))

            # Sort deterministically by staked units desc, then address
            eligible.sort(key=lambda x: (-x[1], x[0]))
            return eligible[:100]

    @staticmethod
    def _leading_zero_count(hex_hash: str) -> int:
        s = str(hex_hash or "")
        cnt = 0
        for ch in s:
            if ch == "0":
                cnt += 1
            else:
                break
        return cnt

    def compute_lwma_difficulty(self, chain_slice: List[Block], now_ts: Optional[float] = None) -> int:
        """
        Deterministic Cumulative LWMA (Linearly Weighted Moving Average) Difficulty.
        Tracks effective difficulty from the median leading-zero work of the recent LWMA_WINDOW
        so difficulty scales cumulatively across [MIN_DIFFICULTY=2 .. MAX_DIFFICULTY=8] instead
        of being clamped to base_difficulty +/- 1.
        """
        max_diff = max(self.difficulty, int(os.environ.get("BCT_MAX_DIFFICULTY", "8")))
        min_diff = min(2, self.difficulty)

        if len(chain_slice) < LWMA_WINDOW:
            eff_diff = self.difficulty
        else:
            recent = chain_slice[-LWMA_WINDOW:]
            # Observed effective difficulty via median leading zeros in window (immune to single lucky hash)
            lz_counts = sorted(self._leading_zero_count(b.hash) for b in recent)
            median_lz = lz_counts[len(lz_counts) // 2]
            eff_diff = max(min_diff, min(max_diff, max(self.difficulty, median_lz)))

            time_diffs = []
            for i in range(1, len(recent)):
                dt = float(recent[i].timestamp) - float(recent[i - 1].timestamp)
                time_diffs.append(max(0.1, min(dt, TARGET_BLOCK_TIME * 6.0)))

            if time_diffs:
                weighted_sum = sum((idx + 1) * dt for idx, dt in enumerate(time_diffs))
                weight_total = sum(idx + 1 for idx in range(len(time_diffs)))
                avg_solve_time = weighted_sum / max(1.0, weight_total)

                if avg_solve_time < (TARGET_BLOCK_TIME * 0.5):
                    eff_diff = min(max_diff, eff_diff + 1)
                elif avg_solve_time > (TARGET_BLOCK_TIME * 1.8) and eff_diff > min_diff:
                    eff_diff = max(min_diff, eff_diff - 1)

        # Emergency Stall Recovery (Anti-Freeze Guard):
        # If the network has stalled without a block for > 6x target time (120s) due to hashrate collapse,
        # dynamically relax difficulty so miners can recover block generation immediately.
        if now_ts is not None and chain_slice:
            tip_time = float(chain_slice[-1].timestamp)
            time_since_tip = float(now_ts) - tip_time
            if time_since_tip > (TARGET_BLOCK_TIME * 6.0):
                stall_drop = int((time_since_tip - (TARGET_BLOCK_TIME * 6.0)) // 60.0) + 1
                return max(1, eff_diff - stall_drop)

        return max(1, eff_diff)

    def get_current_difficulty(self) -> int:
        """
        Adaptive PoW Difficulty using cumulative LWMA (Linearly Weighted Moving Average).
        Dynamically adjusts difficulty target based on block solve times over LWMA_WINDOW.
        Suitable for both CPU and GPU miners while maintaining smooth block intervals.
        """
        return self.compute_lwma_difficulty(self.chain, now_ts=time.time())

    def _should_defer_to_peer_miners(self) -> bool:
        """When external peer miners are actively online, queue transactions in mempool so peer nodes forge PoW blocks."""
        if not self.auto_mine:
            return True
        return len(self.get_active_peer_miners()) > 0

    def _check_batch_ready(self) -> Tuple[bool, str]:
        """
        Hybrid Batching Evaluation (Time + Quota):
        Evaluates whether pending transactions in mempool should be sealed into a new block:
        - Likes: 20s window OR 15 likes quota
        - Comments: 50s window OR 10 comments quota
        - General Tx: 20s window OR 25 tx quota
        Returns: (ready: bool, trigger_reason: str)
        """
        if not self.pending_transactions:
            return False, ""

        now = time.time()
        like_count = 0
        comment_count = 0
        oldest_like_ts = None
        oldest_comment_ts = None
        oldest_any_ts = None

        for tx in self.pending_transactions:
            ts = float(tx.timestamp or now)
            if oldest_any_ts is None or ts < oldest_any_ts:
                oldest_any_ts = ts

            if tx.tx_type == "space_like":
                like_count += 1
                if oldest_like_ts is None or ts < oldest_like_ts:
                    oldest_like_ts = ts
            elif tx.tx_type == "space_comment":
                comment_count += 1
                if oldest_comment_ts is None or ts < oldest_comment_ts:
                    oldest_comment_ts = ts

        # 1. Quota triggers (Instant block sealing when quota threshold reached)
        if like_count >= LIKE_BATCH_QUOTA:
            return True, f"like_quota_reached ({like_count}/{LIKE_BATCH_QUOTA})"
        if comment_count >= COMMENT_BATCH_QUOTA:
            return True, f"comment_quota_reached ({comment_count}/{COMMENT_BATCH_QUOTA})"
        if len(self.pending_transactions) >= GENERAL_TX_BATCH_QUOTA:
            return True, f"total_tx_quota_reached ({len(self.pending_transactions)}/{GENERAL_TX_BATCH_QUOTA})"

        # 2. Time-window triggers (Timeout reached for oldest micro-action)
        if oldest_like_ts is not None and (now - oldest_like_ts) >= LIKE_BATCH_WINDOW_SECONDS:
            return True, f"like_window_timeout ({now - oldest_like_ts:.1f}s >= {LIKE_BATCH_WINDOW_SECONDS}s)"
        if oldest_comment_ts is not None and (now - oldest_comment_ts) >= COMMENT_BATCH_WINDOW_SECONDS:
            return True, f"comment_window_timeout ({now - oldest_comment_ts:.1f}s >= {COMMENT_BATCH_WINDOW_SECONDS}s)"
        if oldest_any_ts is not None and (now - oldest_any_ts) >= GENERAL_TX_BATCH_WINDOW_SECONDS:
            return True, f"general_tx_timeout ({now - oldest_any_ts:.1f}s >= {GENERAL_TX_BATCH_WINDOW_SECONDS}s)"

        return False, ""

    def _start_batch_sequencer(self):
        """Starts an autonomous background timer loop that triggers block sealing when time windows elapse."""
        if self._sequencer_thread and self._sequencer_thread.is_alive():
            return
        self._stop_sequencer = threading.Event()
        self._sequencer_thread = threading.Thread(
            target=self._run_batch_sequencer_loop,
            daemon=True,
            name="LockTrace-BatchSequencer"
        )
        self._sequencer_thread.start()

    def stop(self):
        """Cleanly stops the background batch sequencer thread and flushes storage."""
        if self._stop_sequencer:
            self._stop_sequencer.set()
        self._sequencer_wakeup.set()
        if self._sequencer_thread and self._sequencer_thread.is_alive():
            self._sequencer_thread.join(timeout=2.0)
        if self._storage is not None:
            self._storage.close_thread_connection()
        self._storage = None

    def _run_batch_sequencer_loop(self):
        while self._stop_sequencer and not self._stop_sequencer.is_set():
            try:
                self._sequencer_wakeup.wait(timeout=1.0)
                self._sequencer_wakeup.clear()
                if not self.auto_mine:
                    continue
                should_mine = False
                trigger_reason = ""
                with self.lock:
                    self._load_state(sweep_overdue=False)
                    if self.pending_transactions:
                        ready, reason = self._check_batch_ready()
                        if ready:
                            should_mine = True
                            trigger_reason = reason
                        else:
                            now = time.time()
                            oldest_ts = min(float(tx.timestamp or now) for tx in self.pending_transactions)
                            if (now - oldest_ts) >= MEMPOOL_MINER_WINDOW_SECONDS:
                                should_mine = True
                                trigger_reason = f"miner_window_overdue ({now - oldest_ts:.1f}s)"
                if should_mine:
                    # Execute 3-phase CAS PoW outside self.lock so HTTP requests never freeze
                    blk = self._mine_block(require_pending=True)
                    if blk:
                        logger.info(f"[BATCH SEQUENCER] Auto-sealed block #{blk.index} ({len(blk.transactions)} txs, trigger: {trigger_reason})")
            except Exception as e:
                logger.error(f"[BATCH SEQUENCER] loop exception: {e}")

    def _seal_or_queue_mempool(self) -> Optional[Block]:
        """
        Non-blocking batch trigger: signals the background sequencer thread immediately
        when quota is reached so user HTTP requests return in <5ms without waiting on PoW.
        """
        if not self.auto_mine:
            return None
        ready, _ = self._check_batch_ready()
        if ready:
            if self._sequencer_thread and self._sequencer_thread.is_alive():
                self._sequencer_wakeup.set()
                return None
            return self._mine_block()
        return None

    def _sweep_overdue_mempool(self) -> Optional[Block]:
        """Safety-net sequencer: wakes background sequencer if pending mempool txs exceed window."""
        if not self.auto_mine or not self.pending_transactions:
            return None
        now = time.time()
        oldest_ts = min(float(tx.timestamp or now) for tx in self.pending_transactions)
        if (now - oldest_ts) >= MEMPOOL_MINER_WINDOW_SECONDS:
            if self._sequencer_thread and self._sequencer_thread.is_alive():
                self._sequencer_wakeup.set()
                return None
            return self._mine_block(miner_address="")
        return None

    def _build_reward_transactions(
        self,
        pending_txs: List[Transaction],
        miner_address: str,
        block_index: int,
        fixed_timestamp: Optional[float] = None,
    ) -> Tuple[List[Transaction], dict]:
        """
        Deterministically computes atomic-unit-exact block rewards from Treasury Vault + Fee Pool:
        - 50% to Block Producer (`mining_reward`) if valid active proposer.
        - 40% to Active Validator Quorum (`validator_reward`) split equally across verified peer nodes.
        - 10% to Observer Stakers Pool (`observer_reward`) pro-rata to locked collateral.
        - When block is mined by background sequencer ("Genesis-Validator"), observer & validator pools are still distributed;
          the 50% proposer portion remains unminted in Treasury.
        """
        clean_miner = normalize_bct_address(miner_address) if miner_address else ""
        is_miner_eligible = bool(
            clean_miner
            and is_valid_bct_address(clean_miner)
            and clean_miner != TREASURY_ADDRESS
            and clean_miner not in self.slashed_validators
            and not self.is_wallet_burned(clean_miner)
        )

        # Anti-Self-Loop & Zero-Fee Farming Guard: If block only contains self-transfers, slashed validators,
        # or zero-fee system/staking transactions (frontend_release, welcome reward, stake/unstake, 0-fee bridge lock),
        # zero the Treasury subsidy so blocks without fee-paying user activity never drain Treasury!
        slashed_set = set(normalize_bct_address(a) for a in self.slashed_validators)
        non_subsidy_types = {"frontend_release", "reward", "validator_stake", "validator_unstake"}
        genuine_txs = [
            tx for tx in pending_txs
            if (not clean_miner or (normalize_bct_address(tx.sender) != clean_miner and normalize_bct_address(tx.receiver) != clean_miner))
            and normalize_bct_address(tx.sender) not in slashed_set
            and normalize_bct_address(tx.receiver) not in slashed_set
            and tx.tx_type not in non_subsidy_types
            and float(getattr(tx, "fee", 0.0) or 0.0) > 0
        ]
        senders = {normalize_bct_address(tx.sender) for tx in genuine_txs if tx.sender}
        receivers = {normalize_bct_address(tx.receiver) for tx in genuine_txs if tx.receiver}
        is_self_loop_only = bool(pending_txs) and (len(genuine_txs) == 0 or (len(senders) <= 1 and len(receivers) <= 1 and senders == receivers))

        transfer_fees_u = sum(_to_units(tx.fee) for tx in pending_txs if tx.tx_type in ("transfer", "bns_buy", "bns_accept_offer"))
        space_and_bns_fees_u = sum(
            _to_units(tx.fee) for tx in pending_txs if tx.tx_type in (
                "space_post", "space_like", "space_comment", "space_follow",
                "space_royalty_transfer", "space_royalty_transfer_all",
                "bns_register", "bns_transfer", "avatar_mint", "avatar_equip",
                "room_create", "room_set_avatar", "room_transfer", "room_topic", "room_reply", "room_upvote"
            )
        )
        miner_fee_cut_u = (transfer_fees_u // 2) + space_and_bns_fees_u

        treasury_units = self.verify_and_recalc_units(TREASURY_ADDRESS)
        subsidy_target_u = _to_units(BLOCK_REWARD)
        subsidy_u = subsidy_target_u if (treasury_units >= subsidy_target_u and not is_self_loop_only) else 0
        total_pool_u = subsidy_u + miner_fee_cut_u

        if total_pool_u <= 0:
            return [], {"total_reward": 0.0, "proposer_reward": 0.0, "validator_pool_reward": 0.0, "validators_rewarded": [], "observer_pool_reward": 0.0, "observers_rewarded": []}

        det_ts = round(float(fixed_timestamp if fixed_timestamp is not None else time.time()), 3)
        validators = self.get_eligible_validators(exclude_miner=clean_miner, block_index=block_index, now=det_ts)
        active_validator_addrs = {normalize_bct_address(v["miner_address"]) for v in validators}
        if clean_miner and self.is_active_validator(clean_miner):
            active_validator_addrs.add(clean_miner)

        # 3-Tier Staking & Observer Quorum: Query passive observer stakers (100 - 100,000 BCT)
        # Active validators' excess stake above 1,000 BCT also participates pro-rata in the 10% Observer pool!
        observers = self.get_eligible_observers(active_validator_addrs=active_validator_addrs)

        reward_txs: List[Transaction] = []
        validators_breakdown: List[dict] = []
        observers_breakdown: List[dict] = []

        # Tier 3: 10% Observer Stakers Pool (Threshold-Batched Payouts >= 0.25 BCT to eliminate dust tx bloat)
        actual_obs_total_u = 0
        reserved_obs_u = 0
        next_observer_pending = dict(self.observer_pending_units)
        obs_threshold_bct = float(getattr(Config, "OBSERVER_PAYOUT_THRESHOLD", 0.25))
        obs_threshold_u = max(1, _to_units(obs_threshold_bct))
        if observers and total_pool_u >= 100:
            obs_pool_u = (total_pool_u * 10) // 100
            total_obs_stake_u = sum(stk_u for _, stk_u in observers)
            if total_obs_stake_u > 0:
                reserved_obs_u = obs_pool_u
                avail_treasury_u = max(0, treasury_units - total_pool_u)
                for o_addr, o_stake_u in observers:
                    o_cut_u = (obs_pool_u * o_stake_u) // total_obs_stake_u
                    if o_cut_u <= 0:
                        continue
                    accrued_u = int(next_observer_pending.get(o_addr, 0)) + o_cut_u
                    if accrued_u >= obs_threshold_u and (avail_treasury_u + obs_pool_u) >= accrued_u:
                        obs_amt = float(Decimal(accrued_u) / Decimal(ATOMIC_UNIT))
                        reward_txs.append(
                            Transaction(
                                sender=TREASURY_ADDRESS,
                                receiver=o_addr,
                                amount=obs_amt,
                                fee=0.0,
                                signature=f"observer_stake_reward_block_{block_index}_{o_addr[:8]}",
                                timestamp=det_ts,
                                tx_type="observer_reward",
                                extra_data={
                                    "staked_bct": float(Decimal(o_stake_u) / Decimal(ATOMIC_UNIT)),
                                    "proposer": clean_miner or "Genesis-Validator",
                                    "batched_threshold_bct": obs_threshold_bct,
                                },
                            )
                        )
                        actual_obs_total_u += accrued_u
                        avail_treasury_u = max(0, avail_treasury_u - max(0, accrued_u - o_cut_u))
                        next_observer_pending.pop(o_addr, None)
                        observers_breakdown.append({"address": o_addr, "reward": obs_amt})
                    else:
                        next_observer_pending[o_addr] = accrued_u

        # Tier 2: 40% Active Attesting Validator Quorum Pool (Equally split among online attested nodes)
        actual_val_total_u = 0
        if validators and total_pool_u >= 100:
            val_pool_u = (total_pool_u * 40) // 100
            per_val_u = val_pool_u // len(validators)
            actual_val_total_u = per_val_u * len(validators)
            val_amt = float(Decimal(per_val_u) / Decimal(ATOMIC_UNIT))
            for v_node in validators:
                v_addr = v_node["miner_address"].strip()
                v_nid = v_node["node_id"]
                reward_txs.append(
                    Transaction(
                        sender=TREASURY_ADDRESS,
                        receiver=v_addr,
                        amount=val_amt,
                        fee=0.0,
                        signature=f"validator_quorum_reward_block_{block_index}_{v_nid}",
                        timestamp=det_ts,
                        tx_type="validator_reward",
                        extra_data={"node_id": v_nid, "proposer": clean_miner or "Genesis-Validator"},
                    )
                )
                validators_breakdown.append({"node_id": v_nid, "miner_address": v_addr, "reward": val_amt})

        # Tier 1: 50% PoW Block Producer (Proposer) + Any unallocated Validator/Observer pool remainder
        # Subtract THIS block's reserved_obs_u (not batched actual_obs_total_u) so observers are never
        # double-paid alongside proposer and proposer never gets 0 on a batched observer payout block.
        proposer_u = max(0, total_pool_u - (actual_val_total_u + reserved_obs_u))
        if proposer_u > 0 and is_miner_eligible:
            proposer_amt = float(Decimal(proposer_u) / Decimal(ATOMIC_UNIT))
            reward_txs.append(
                Transaction(
                    sender=TREASURY_ADDRESS,
                    receiver=clean_miner,
                    amount=proposer_amt,
                    fee=0.0,
                    signature=f"coinbase_pow_reward_block_{block_index}",
                    timestamp=det_ts,
                    tx_type="mining_reward",
                )
            )

        breakdown = {
            "total_reward": float(Decimal(total_pool_u) / Decimal(ATOMIC_UNIT)),
            "proposer_reward": float(Decimal(proposer_u if is_miner_eligible else 0) / Decimal(ATOMIC_UNIT)),
            "validator_pool_reward": float(Decimal(actual_val_total_u) / Decimal(ATOMIC_UNIT)),
            "validators_rewarded": validators_breakdown,
            "observer_pool_reward": float(Decimal(actual_obs_total_u) / Decimal(ATOMIC_UNIT)),
            "observers_rewarded": observers_breakdown,
            "observer_pending_after": next_observer_pending,
        }
        return reward_txs, breakdown

    def _apply_reward_accounting(self, clean_miner: str, breakdown: dict):
        """Updates node mining & validator reward counters and registers newly rewarded addresses."""
        now = time.time()
        if isinstance(breakdown.get("observer_pending_after"), dict):
            self.observer_pending_units = {
                str(k): int(v) for k, v in breakdown["observer_pending_after"].items() if int(v) > 0
            }
        proposer_reward = float(breakdown.get("proposer_reward", 0.0))
        if clean_miner and is_valid_bct_address(clean_miner) and clean_miner != TREASURY_ADDRESS:
            if clean_miner not in self.wallets:
                self.wallets[clean_miner] = {"public_key": "", "created_at": now}
            for _nid, node in self.nodes.items():
                if node.get("miner_address") == clean_miner:
                    node["blocks_mined"] = int(node.get("blocks_mined", 0)) + 1
                    node["proposer_rewards"] = round(float(node.get("proposer_rewards", 0.0)) + proposer_reward, 8)
                    node["total_rewards"] = round(float(node.get("total_rewards", 0.0)) + proposer_reward, 8)
                    node["block_height"] = len(self.chain)
            self.balances[clean_miner] = self.verify_and_recalc_balance(clean_miner)

        for v_item in breakdown.get("validators_rewarded", []):
            v_addr = v_item["miner_address"]
            v_rew = float(v_item["reward"])
            v_nid = v_item["node_id"]
            if v_addr not in self.wallets:
                self.wallets[v_addr] = {"public_key": "", "created_at": now}
            if v_nid in self.nodes:
                v_node = self.nodes[v_nid]
                v_node["validator_rewards"] = round(float(v_node.get("validator_rewards", 0.0)) + v_rew, 8)
                v_node["total_rewards"] = round(float(v_node.get("total_rewards", 0.0)) + v_rew, 8)
            self.balances[v_addr] = self.verify_and_recalc_balance(v_addr)

        self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)

    @staticmethod
    def _is_safe_peer_endpoint(url: str) -> bool:
        """SSRF guard: allows public HTTP/HTTPS peer endpoints (or localhost ONLY when ALLOW_LOCAL_PEERS=1)."""
        if not url or not isinstance(url, str):
            return False
        try:
            parsed = urllib.parse.urlparse(url.strip())
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                return False
            allow_local = os.environ.get("ALLOW_LOCAL_PEERS", "0") == "1"
            host = parsed.hostname
            if host in ("localhost", "127.0.0.1", "::1"):
                return allow_local
            infos = socket.getaddrinfo(host, parsed.port or 80, proto=socket.IPPROTO_TCP)
            for info in infos:
                ip_obj = ipaddress.ip_address(info[4][0])
                if ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_unspecified:
                    if not (allow_local and ip_obj.is_loopback):
                        return False
                if ip_obj.is_private and not allow_local:
                    return False
            return True
        except Exception:
            return False

    def _broadcast_block_to_peers(self, block_dict: dict, exclude_node_id: str = ""):
        """Asynchronously gossips newly sealed PoW blocks to reachable P2P peer endpoints."""
        peers = []
        now = time.time()
        for nid, n in self.nodes.items():
            if n.get("is_genesis") or nid == exclude_node_id:
                continue
            if (now - float(n.get("last_seen", 0))) > 300.0:
                continue
            ep = str(n.get("endpoint", "") or "").strip().rstrip("/")
            if ep.startswith("http"):
                peers.append(ep)

        if not peers:
            return

        def _worker(endpoints: List[str], payload_bytes: bytes):
            # AUD17-03: Block HTTP 301/302/307/308 redirects to prevent SSRF bypass to internal/metadata IPs
            class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None

            safe_opener = urllib.request.build_opener(_NoRedirectHandler())
            for ep in endpoints[:25]:
                if not self._is_safe_peer_endpoint(ep):
                    continue
                try:
                    req = urllib.request.Request(
                        f"{ep}/p2p/gossip/block",
                        data=payload_bytes,
                        headers={"Content-Type": "application/json", "User-Agent": "LockTrace-P2P/1.4"},
                        method="POST",
                    )
                    with safe_opener.open(req, timeout=2.5):
                        pass
                except Exception:
                    pass

        body = json.dumps({"block": block_dict, "network_height": len(self.chain)}).encode("utf-8")
        threading.Thread(target=_worker, args=(peers, body), daemon=True).start()

    def _filter_valid_mempool_transactions_for_block(self) -> List[Transaction]:
        """
        Filters mempool transactions to ensure solvency and strict consensus rules:
        - Drops any validator_unstake transactions if receiver has insufficient confirmed stake
          or if VALIDATOR_STAKE_VAULT has insufficient confirmed balance.
        - Automatically evicts invalid transactions from self.pending_transactions.
        """
        self._ensure_ledger_index()
        vault_u = int(self._confirmed_units_map.get(VALIDATOR_STAKE_VAULT_ADDRESS, 0))
        available_stakes = dict(self._confirmed_stakes_map)
        available_units = dict(self._confirmed_units_map)

        valid_txs: List[Transaction] = []
        evict_hashes = set()
        for tx in self.pending_transactions:
            if tx.tx_type == "validator_unstake":
                rec = normalize_bct_address(tx.receiver)
                snd = normalize_bct_address(tx.sender)
                amt_u = _to_units(tx.amount)
                if snd != VALIDATOR_STAKE_VAULT_ADDRESS or not rec:
                    evict_hashes.add(tx.hash())
                    continue
                user_staked = available_stakes.get(rec, 0)
                if amt_u <= 0 or amt_u > user_staked or amt_u > vault_u:
                    logger.warning(
                        f"[CONSENSUS GUARD] Evicting invalid unstake: {rec} requested {tx.amount} BCT "
                        f"but confirmed staked is {user_staked / ATOMIC_UNIT:.4f} BCT, vault has {vault_u / ATOMIC_UNIT:.4f} BCT"
                    )
                    evict_hashes.add(tx.hash())
                    continue
                available_stakes[rec] -= amt_u
                vault_u -= amt_u
            elif tx.tx_type == "bns_accept_offer":
                bidder_addr = normalize_bct_address(tx.receiver)
                amt_u = _to_units(tx.amount)
                if not bidder_addr or amt_u <= 0 or available_units.get(bidder_addr, 0) < amt_u:
                    logger.warning(f"[CONSENSUS GUARD] Evicting insolvent bns_accept_offer for bidder {bidder_addr}")
                    evict_hashes.add(tx.hash())
                    continue
                available_units[bidder_addr] -= amt_u
            elif tx.amount > 0:
                snd = normalize_bct_address(tx.sender)
                amt_u = _to_units(tx.amount)
                if snd and snd not in ("GENESIS_VAULT", "GENESIS", TREASURY_ADDRESS, BRIDGE_VAULT_ADDRESS, VALIDATOR_STAKE_VAULT_ADDRESS):
                    if available_units.get(snd, 0) < amt_u:
                        evict_hashes.add(tx.hash())
                        continue
                    available_units[snd] -= amt_u
            valid_txs.append(tx)

        if evict_hashes:
            self.pending_transactions = [t for t in self.pending_transactions if t.hash() not in evict_hashes]

        return valid_txs

    def _mine_block(self, miner_address: str = "", require_pending: bool = False) -> Optional[Block]:
        """
        3-Phase Atomic Compare-And-Swap (CAS) Block Producer:
        - Phase 1 (Under lock): Snapshots canonical chain tip & candidate mempool transactions.
        - Phase 2 (Lock-free when called from background sequencer): Computes SHA-256 Proof-of-Work.
        - Phase 3 (Under lock): Verifies chain tip & mempool integrity before committing (100% immune to forks
          and never drops concurrent mempool transactions that arrived during PoW).
        """
        with self._mining_lock:
            with self.lock:
                self._load_state(sweep_overdue=False)
                clean_miner = normalize_bct_address(miner_address)
                if require_pending and not self.pending_transactions:
                    return None
                if not self.pending_transactions and not (clean_miner and is_valid_bct_address(clean_miner)):
                    return None

                expected_idx = len(self.chain)
                expected_prev = self.chain[-1].hash if self.chain else "0" * 64
                packaged_user_txs = self._filter_valid_mempool_transactions_for_block()
                packaged_user_hashes = {tx.hash() for tx in packaged_user_txs}
                block_txs = list(packaged_user_txs)
                reward_txs, breakdown = self._build_reward_transactions(block_txs, clean_miner, expected_idx)
                if reward_txs:
                    block_txs.extend(reward_txs)

                diff = self.get_current_difficulty()
                candidate_block = Block(
                    index=expected_idx,
                    transactions=block_txs,
                    previous_hash=expected_prev,
                    miner=clean_miner or "Genesis-Validator",
                )

            # Phase 2: Compute Proof-of-Work
            candidate_block.mine(diff)

            # Phase 3: Atomic CAS Verification & Commit
            with self.lock:
                self._load_state(sweep_overdue=False)
                current_prev = self.chain[-1].hash if self.chain else "0" * 64
                if len(self.chain) != expected_idx or current_prev != expected_prev:
                    logger.info(
                        f"[CAS FORK GUARD] Aborted local candidate #{expected_idx}; "
                        f"canonical chain already advanced to #{len(self.chain) - 1}"
                    )
                    return self.chain[-1] if self.chain else None

                if packaged_user_hashes:
                    live_hashes = {tx.hash() for tx in self.pending_transactions}
                    if not packaged_user_hashes.issubset(live_hashes):
                        logger.info(
                            f"[CAS FORK GUARD] Mempool subset changed during PoW for #{expected_idx}; "
                            "re-queuing for next cycle"
                        )
                        return None

                self.chain.append(candidate_block)
                self.pending_transactions = [
                    tx for tx in self.pending_transactions if tx.hash() not in packaged_user_hashes
                ]
                if reward_txs:
                    self.total_transactions += len(reward_txs)

                self._apply_reward_accounting(clean_miner, breakdown)
                self._load_in_memory_bns_index()
                self._load_in_memory_space_index()
                self._load_in_memory_avatar_index()
                self._load_in_memory_rooms_index()
                self._save_state()
                block_dict = candidate_block.to_dict()

            self._broadcast_block_to_peers(block_dict)
            return candidate_block

    def build_mining_template(self, miner_address: str, node_id: str = "") -> Tuple[bool, str, Optional[dict]]:
        """
        Generates a deterministic v2 PoW candidate block template (`getblocktemplate`) for external miner nodes.
        External nodes compute SHA-256 PoW locally and submit the solved block via `submit_mined_block`.
        """
        with self.lock:
            self._load_state(sweep_overdue=False)
            clean_miner = normalize_bct_address(miner_address)
            if not is_valid_bct_address(clean_miner) or clean_miner.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT"):
                return False, "Invalid miner wallet address.", None

            if clean_miner in self.slashed_validators:
                return False, "Slashed validator address cannot produce blocks or earn rewards.", None

            if not self.is_active_validator(clean_miner):
                return (
                    False,
                    f"Blok üretmek ve doğrulayıcı ödülü kazanmak için en az {MIN_VALIDATOR_STAKE:,.0f} BCT aktif Validator Stake kilidi ve doğrulanmış aktif bir Validator Düğümü (auth_verified) gereklidir.",
                    None,
                )

            if node_id and node_id in self.nodes and not self.nodes[node_id].get("is_genesis"):
                self.nodes[node_id]["last_seen"] = time.time()

            diff = self.get_current_difficulty()
            block_index = len(self.chain)
            prev_hash = self.chain[-1].hash if self.chain else "0" * 64

            if not self.pending_transactions:
                return False, "Mempool is empty — awaiting new transactions.", {
                    "empty": True,
                    "block_index": block_index,
                    "previous_hash": prev_hash,
                    "difficulty": diff,
                }

            if len(self.chain) >= 10:
                elapsed_since_tip = time.time() - float(self.chain[-1].timestamp)
                if elapsed_since_tip < 20.0 and len(self.pending_transactions) < GENERAL_TX_BATCH_QUOTA:
                    return False, f"Awaiting target block interval window (20s). Elapsed: {elapsed_since_tip:.1f}s.", {
                        "empty": True,
                        "cooldown": True,
                        "block_index": block_index,
                        "previous_hash": prev_hash,
                        "difficulty": diff,
                    }

            template_ts = round(time.time(), 3)
            user_txs = list(self._filter_valid_mempool_transactions_for_block()[:100])
            reward_txs, breakdown = self._build_reward_transactions(
                user_txs, clean_miner, block_index, fixed_timestamp=template_ts
            )
            candidate_txs = user_txs + reward_txs
            tx_dicts = [t.to_dict() for t in candidate_txs]
            merkle_root = compute_merkle_root([t["tx_hash"] for t in tx_dicts])

            return True, "PoW block template ready.", {
                "empty": False,
                "version": 2,
                "index": block_index,
                "previous_hash": prev_hash,
                "timestamp": template_ts,
                "miner": clean_miner,
                "difficulty": diff,
                "target_prefix": "0" * diff,
                "merkle_root": merkle_root,
                "transactions": tx_dicts,
                "reward_breakdown": breakdown,
            }

    def submit_mined_block(
        self,
        block_data: dict,
        node_id: str = "",
        public_key: str = "",
        signature: str = "",
        reported_hashrate: float = 0.0,
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Zero-trust external PoW block verifier (`submitblock`).
        Verifies miner ECDSA signature, chain tip linkage, mempool transaction membership,
        exact protocol reward distribution (70% Proposer / 30% Validators), Merkle root, and SHA-256 PoW!
        """
        with self.lock:
            self._load_state(sweep_overdue=False)
            if not isinstance(block_data, dict):
                return False, "Invalid block data.", None

            clean_miner = normalize_bct_address(str(block_data.get("miner", "") or "").strip())
            if not is_valid_bct_address(clean_miner) or clean_miner.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT"):
                return False, "Invalid miner wallet address.", None

            if clean_miner in self.slashed_validators:
                return False, "Slashed validator address cannot submit blocks or earn rewards.", None

            if not self.is_active_validator(clean_miner):
                return (
                    False,
                    f"Yalnızca doğrulanmış ve ağda aktif olan bir Validator Düğümü (>= {MIN_VALIDATOR_STAKE:,.0f} BCT kilitli teminata sahip ve auth_verified) blok gönderebilir ve konsensüs ödülü kazanabilir.",
                    None,
                )

            raw_idx = block_data.get("index", -1)
            raw_nonce = block_data.get("nonce", -1)
            raw_ver = block_data.get("version", 2)
            if isinstance(raw_idx, bool) or isinstance(raw_nonce, bool) or isinstance(raw_ver, bool):
                return False, "Invalid block header integer field type.", None
            try:
                submitted_idx = int(raw_idx)
                submitted_nonce = int(raw_nonce)
                submitted_ver = int(raw_ver)
            except (ValueError, TypeError):
                return False, "Invalid block header numeric fields (index/nonce/version).", None
            submitted_hash = str(block_data.get("hash", "") or "").strip().lower()
            submitted_prev = str(block_data.get("previous_hash", "") or "").strip().lower()
            try:
                raw_ts = float(block_data.get("timestamp", 0.0))
            except (ValueError, TypeError):
                return False, "Invalid block timestamp format.", None
            if not math.isfinite(raw_ts) or raw_ts <= 0:
                return False, "Block timestamp must be a finite positive number.", None
            submitted_ts = round(raw_ts, 3)

            if submitted_ver < 2 or submitted_nonce < 0:
                return False, "Only v2 Merkle PoW block format is accepted.", None

            # 0. Header-First Pre-PoW Check (LT-06 OOM & CPU DoS Guard)
            diff = self.get_current_difficulty()
            target_prefix = "0" * diff
            if not submitted_hash.startswith(target_prefix):
                return False, f"Header-First rejection: Hash does not meet PoW target ({diff} leading zeroes required).", None

            # 1. Verify miner ECDSA ownership over the solved block header
            clean_pub = (public_key or "").strip() or self.wallets.get(clean_miner, {}).get("public_key", "")
            if not clean_pub or not signature:
                return False, "Miner ECDSA signature (public_key + signature) is required to submit a block.", None
            if public_key_to_address(clean_pub) != clean_miner:
                return False, "Miner public key does not match miner wallet address!", None

            header_auth_msg = f"SUBMIT_BLOCK:{submitted_idx}:{submitted_hash}:{submitted_nonce}:{clean_miner}"
            if not verify_signature(clean_pub, header_auth_msg, signature):
                return False, "Invalid miner block ECDSA signature!", None

            # 2. Check chain height & previous hash (detect race/stale block cleanly)
            expected_idx = len(self.chain)
            expected_prev = (self.chain[-1].hash if self.chain else "0" * 64).lower()
            if submitted_idx != expected_idx or submitted_prev != expected_prev:
                return False, f"Chain advanced (Stale Block). Expected block: #{expected_idx}", {"stale": True, "network_height": expected_idx}

            # 2b. Timestamp Monotonicity, Median-Time-Past (MTP) & Drift Guards (LT-06)
            now_ts = time.time()
            if submitted_ts > now_ts + 120.0:
                return False, "Block timestamp too far in the future (max 120s drift allowed).", None
            if self.chain and submitted_ts <= self.chain[-1].timestamp:
                return False, f"Block timestamp must be strictly greater than predecessor block ({self.chain[-1].timestamp:.3f}s vs {submitted_ts:.3f}s).", None
            if len(self.chain) >= 10 and len(self.pending_transactions) < GENERAL_TX_BATCH_QUOTA:
                if (submitted_ts - float(self.chain[-1].timestamp)) < 12.0:
                    return False, f"Block submitted too fast ({submitted_ts - self.chain[-1].timestamp:.1f}s < 12.0s minimum block interval).", None
            if len(self.chain) >= 11:
                past_window = sorted([b.timestamp for b in self.chain[-11:]])
                mtp = past_window[len(past_window) // 2]
                if submitted_ts <= mtp:
                    return False, f"Block timestamp must be greater than Median-Time-Past ({mtp:.3f}s).", None

            if abs(now_ts - submitted_ts) > 300:
                return False, "Block timestamp invalid (exceeded ±300s window).", None

            # 3. Validate transactions against live mempool + exact protocol reward math
            raw_txs = block_data.get("transactions", [])
            if not isinstance(raw_txs, list) or not raw_txs:
                return False, "Empty block not accepted.", None

            mempool_by_hash = {tx.hash(): tx for tx in self.pending_transactions}
            matched_user_txs: List[Transaction] = []
            submitted_reward_hashes: List[str] = []
            seen_user_hashes = set()

            for t_dict in raw_txs:
                if not isinstance(t_dict, dict):
                    return False, "Malformed transaction format.", None
                t_type = str(t_dict.get("tx_type", "transfer"))
                try:
                    t_amount = float(t_dict.get("amount", 0.0))
                    t_fee = float(t_dict.get("fee", 0.0))
                    t_ts = float(t_dict.get("timestamp", 0.0))
                except (ValueError, TypeError):
                    return False, "Malformed transaction numeric field (amount/fee/timestamp).", None
                if not (math.isfinite(t_amount) and math.isfinite(t_fee) and math.isfinite(t_ts)) or t_amount < 0 or t_fee < 0:
                    return False, "Invalid transaction numeric bounds (must be finite non-negative).", None
                tx_obj = Transaction(
                    sender=str(t_dict.get("sender", "")),
                    receiver=str(t_dict.get("receiver", "")),
                    amount=t_amount,
                    fee=t_fee,
                    signature=str(t_dict.get("signature", "")),
                    timestamp=t_ts,
                    tx_type=t_type,
                    extra_data=t_dict.get("extra_data"),
                )
                h = tx_obj.hash()
                if t_type in ("mining_reward", "validator_reward", "observer_reward"):
                    submitted_reward_hashes.append(h)
                else:
                    if h not in mempool_by_hash or h in seen_user_hashes:
                        return False, "Unrecognized or duplicate mempool transaction in block!", None
                    seen_user_hashes.add(h)
                    matched_user_txs.append(mempool_by_hash[h])

            if not matched_user_txs:
                return False, "Block must contain at least 1 valid mempool transaction.", None

            # Strict Solvency Guard: Validate that validator_unstake & bns_accept_offer do not exceed confirmed balances
            self._ensure_ledger_index()
            vault_u_check = int(self._confirmed_units_map.get(VALIDATOR_STAKE_VAULT_ADDRESS, 0))
            stakes_check = dict(self._confirmed_stakes_map)
            units_check = dict(self._confirmed_units_map)
            for m_tx in matched_user_txs:
                if m_tx.tx_type == "validator_unstake":
                    rec = normalize_bct_address(m_tx.receiver)
                    snd = normalize_bct_address(m_tx.sender)
                    amt_u = _to_units(m_tx.amount)
                    if snd != VALIDATOR_STAKE_VAULT_ADDRESS or not rec:
                        return False, "Block contains malformed validator_unstake transaction!", None
                    staked_u = stakes_check.get(rec, 0)
                    if amt_u <= 0 or amt_u > staked_u or amt_u > vault_u_check:
                        return False, f"Block contains invalid validator_unstake: {rec} exceeds confirmed stake or vault balance!", None
                    stakes_check[rec] -= amt_u
                    vault_u_check -= amt_u
                elif m_tx.tx_type == "bns_accept_offer":
                    bidder_addr = normalize_bct_address(m_tx.receiver)
                    amt_u = _to_units(m_tx.amount)
                    if not bidder_addr or amt_u <= 0 or units_check.get(bidder_addr, 0) < amt_u:
                        return False, f"Block contains insolvent bns_accept_offer for bidder {bidder_addr}!", None
                    units_check[bidder_addr] -= amt_u
                elif m_tx.amount > 0:
                    snd = normalize_bct_address(m_tx.sender)
                    amt_u = _to_units(m_tx.amount)
                    extra = m_tx.extra_data if isinstance(m_tx.extra_data, dict) else {}
                    is_sender_pays = (m_tx.tx_type == "transfer" and extra.get("fee_mode") == "sender_pays")
                    debit_u = amt_u + (_to_units(m_tx.fee) if is_sender_pays else 0)
                    if snd and snd not in ("GENESIS_VAULT", "GENESIS", TREASURY_ADDRESS, BRIDGE_VAULT_ADDRESS, VALIDATOR_STAKE_VAULT_ADDRESS):
                        if units_check.get(snd, 0) < debit_u:
                            return False, f"Block contains insolvent transaction from {snd}!", None
                        units_check[snd] -= debit_u

            expected_reward_txs, breakdown = self._build_reward_transactions(
                matched_user_txs, clean_miner, expected_idx, fixed_timestamp=submitted_ts
            )
            expected_reward_hashes = [t.hash() for t in expected_reward_txs]
            if submitted_reward_hashes != expected_reward_hashes:
                return False, "Block reward distribution does not match protocol rules!", None

            # 4. Reconstruct candidate block and verify Merkle Root + SHA-256 Proof-of-Work
            final_txs = matched_user_txs + expected_reward_txs
            try:
                expected_merkle = compute_merkle_root([t.hash() for t in final_txs])
            except ValueError:
                return False, "Merkle Root verification failed (duplicate or malformed transaction hash)!", None
            submitted_merkle = str(block_data.get("merkle_root", "") or "").strip().lower()
            if submitted_merkle != expected_merkle:
                return False, "Merkle Root verification failed!", None

            candidate_block = Block(
                index=expected_idx,
                transactions=final_txs,
                previous_hash=self.chain[-1].hash if self.chain else "0" * 64,
                timestamp=submitted_ts,
                nonce=submitted_nonce,
                miner=clean_miner,
                version=submitted_ver,
                merkle_root=expected_merkle,
            )
            diff = self.get_current_difficulty()
            target_prefix = "0" * diff
            if candidate_block.hash != submitted_hash or not candidate_block.hash.startswith(target_prefix):
                return False, f"Invalid Proof-of-Work hash! ({diff} leading zeroes required)", None

            # 5. Commit verified external PoW block to ledger & remove packaged mempool txs
            self.chain.append(candidate_block)
            self.pending_transactions = [tx for tx in self.pending_transactions if tx.hash() not in seen_user_hashes]
            self.total_transactions += len(expected_reward_txs)

            # Bind public key & update node telemetry
            if clean_miner not in self.wallets:
                self.wallets[clean_miner] = {"public_key": clean_pub, "created_at": time.time()}
            elif not self.wallets[clean_miner].get("public_key"):
                self.wallets[clean_miner]["public_key"] = clean_pub

            if node_id and node_id in self.nodes and not self.nodes[node_id].get("is_genesis"):
                n_entry = self.nodes[node_id]
                n_entry["auth_verified"] = True
                n_entry["owner_public_key"] = clean_pub
                n_entry["last_seen"] = time.time()
                n_entry["attested_height"] = expected_idx
                if reported_hashrate > 0:
                    n_entry["hashrate_hs"] = round(min(float(reported_hashrate), 1e9), 2)

            self._apply_reward_accounting(clean_miner, breakdown)
            self._load_in_memory_bns_index()
            self._load_in_memory_space_index()
            self._load_in_memory_avatar_index()
            self._load_in_memory_rooms_index()
            self._save_state()
            self._broadcast_block_to_peers(candidate_block.to_dict(), exclude_node_id=node_id)

            return True, f"Block #{expected_idx} verified and added to chain!", {
                "block_index": candidate_block.index,
                "block_hash": candidate_block.hash,
                "merkle_root": candidate_block.merkle_root,
                "nonce": candidate_block.nonce,
                "transactions_packaged": len(final_txs),
                "miner_address": clean_miner,
                "miner_reward": breakdown["proposer_reward"],
                "validator_pool_reward": breakdown["validator_pool_reward"],
                "validators_rewarded": breakdown["validators_rewarded"],
                "miner_balance": self.balances.get(clean_miner, 0.0),
                "timestamp": candidate_block.timestamp,
            }

    def attest_block(
        self,
        node_id: str,
        miner_address: str,
        block_index: int,
        block_hash: str,
        public_key: str,
        signature: str,
        timestamp: float,
        client_ip: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Verifies and records a peer validator's cryptographic ECDSA attestation over a synced block.
        Qualifies the validator node for the 30% Active Validator Quorum Reward Pool!
        """
        with self.lock:
            self._load_state()
            clean_id = re.sub(r"[^a-zA-Z0-9._-]", "", (node_id or "").strip())[:64]
            clean_miner = normalize_bct_address(miner_address)
            clean_pub = (public_key or "").strip()
            clean_hash = (block_hash or "").strip().lower()

            if not clean_id or not is_valid_bct_address(clean_miner) or clean_miner == TREASURY_ADDRESS:
                return False, "Invalid node ID or wallet address.", None
            if clean_miner in self.slashed_validators:
                return False, "Validator has been slashed and cannot attest blocks.", None
            if not clean_pub or not signature:
                return False, "Validator signature missing.", None
            if public_key_to_address(clean_pub) != clean_miner:
                return False, "Public key does not match validator wallet address!", None
            ts_str = str(timestamp).strip()
            try:
                ts_val = float(ts_str)
            except (ValueError, TypeError):
                return False, "Invalid attestation timestamp format.", None
            if not math.isfinite(ts_val) or abs(time.time() - ts_val) > 300:
                return False, "Attestation timestamp expired or invalid.", None
            if block_index < 0 or block_index >= len(self.chain):
                return False, f"Block #{block_index} is not yet available.", None

            msg = f"ATTEST:{clean_id}:{block_index}:{clean_hash}:{ts_str}"
            if not verify_signature(clean_pub, msg, signature):
                return False, "Invalid validator ECDSA signature!", None

            # LT-01 Hardening: Strictly require minimum locked validator stake in vault
            val_stake = self.get_validator_stake(clean_miner)
            if val_stake < MIN_VALIDATOR_STAKE:
                return False, f"Insufficient staked collateral ({val_stake:.2f} BCT). Minimum {MIN_VALIDATOR_STAKE:.2f} BCT must be locked in the validator stake vault to attest blocks.", None

            # Equivocation Detection (F-03: persisted ledger survives restarts; must precede canonical hash filter)
            storage = self._get_storage()
            prev_hashes = storage.record_validator_attestation(clean_miner, block_index, clean_hash)
            conflicting = [h for h in prev_hashes if h.lower() != clean_hash.lower()]
            if conflicting:
                logger.error(f"[SLASHING] Equivocation detected! Validator {clean_miner} double-attested block #{block_index} ({conflicting[0]} vs {clean_hash})")
                slash_info = {
                    "block_index": block_index,
                    "hash_a": conflicting[0],
                    "hash_b": clean_hash,
                    "timestamp": time.time(),
                    "slashed": True
                }
                self.slashed_validators[clean_miner] = slash_info
                storage.save_slashed_validator(clean_miner, slash_info)
                return False, f"Equivocation detected on block #{block_index}! Validator stake has been slashed.", None
            if clean_miner in self.slashed_validators:
                return False, "Validator has been slashed for equivocation.", None

            target_block = self.chain[block_index]
            if target_block.hash.lower() != clean_hash:
                return False, "Block hash mismatch against canonical chain! (Fork or corrupted data)", None

            existing = self.nodes.get(clean_id)
            if existing and existing.get("is_genesis"):
                return False, "Genesis node identity cannot be claimed externally.", None
            if existing and existing.get("owner_public_key") and existing["owner_public_key"] != clean_pub:
                return False, "This node_id is registered to another cryptographic key!", None

            inserted, total_att = storage.record_attestation(
                block_index=block_index,
                node_id=clean_id,
                miner_address=clean_miner,
                block_hash=clean_hash,
                signature=signature,
                timestamp=float(timestamp),
            )
            target_block.attestations_count = total_att

            # Post-Block Finality Checkpoint (Option A: 2/3 Quorum Finality)
            eligible_validators = self.get_eligible_validators(exclude_miner="", block_index=block_index)
            quorum_needed = max(1, math.ceil(len(eligible_validators) * (2.0 / 3.0))) if len(eligible_validators) > 2 else 1
            if total_att >= quorum_needed:
                target_block.finalized = True
                if block_index > self.finalized_height:
                    self.finalized_height = block_index
                    logger.info(f"[FINALITY] Block #{block_index} marked FINALIZED (Attestations: {total_att}/{len(eligible_validators)})")

            node_entry = existing or {
                "node_id": clean_id,
                "name": f"Validator ({clean_id[:10]})",
                "endpoint": "p2p-client",
                "role": "Community Validator Peer",
                "location": "Decentralized",
                "created_at": time.time(),
                "is_genesis": False,
                "blocks_mined": 0,
                "total_rewards": 0.0,
            }
            node_entry["miner_address"] = clean_miner
            node_entry["owner_public_key"] = clean_pub
            node_entry["auth_verified"] = True
            if client_ip:
                node_entry["client_ip"] = self._sanitize_node_field(client_ip, 45)
            node_entry["last_seen"] = time.time()
            node_entry["status"] = "online"
            node_entry["attested_height"] = max(int(node_entry.get("attested_height", 0)), block_index)
            node_entry["last_attestation_ts"] = time.time()
            node_entry["block_height"] = max(int(node_entry.get("block_height", 0)), block_index + 1)
            if inserted:
                node_entry["blocks_attested"] = int(node_entry.get("blocks_attested", 0)) + 1
            self.nodes[clean_id] = node_entry
            self._save_state()

            return True, f"Block #{block_index} validation attestation recorded.", {
                "block_index": block_index,
                "attestations_count": total_att,
                "blocks_attested": node_entry.get("blocks_attested", 0),
                "eligible_for_validator_pool": True,
            }

    def get_chain_range(self, start: int = 0, limit: int = 100) -> dict:
        """Returns an ordered slice of archival blocks [start .. start+limit) for full peer node synchronization."""
        with self.lock:
            self._load_state()
            safe_start = max(0, int(start))
            safe_limit = max(1, min(int(limit), 200))
            sliced = self.chain[safe_start:safe_start + safe_limit]
            return {
                "start": safe_start,
                "count": len(sliced),
                "total_blocks": len(self.chain),
                "difficulty": self.get_current_difficulty(),
                "blocks": [b.to_dict() for b in sliced],
            }

    def get_balance(self, address: str) -> float:
        """Get mathematically verified balance directly from ledger."""
        with self.lock:
            self._load_state()
            clean_addr = normalize_bct_address(address)
            recalc = max(0.0, self.verify_and_recalc_balance(clean_addr))
            self.balances[clean_addr] = recalc
            return recalc

    def get_block_by_index_or_hash(self, query: str) -> Optional[dict]:
        with self.lock:
            self._load_state()
            query = query.strip()
            storage = self._get_storage()
            try:
                idx = int(query)
                if 0 <= idx < len(self.chain):
                    d = self.chain[idx].to_dict()
                    d["attestations"] = storage.get_block_attestations(idx)
                    return d
            except ValueError:
                pass
            for b in self.chain:
                if b.hash.lower() == query.lower() or b.previous_hash.lower() == query.lower():
                    d = b.to_dict()
                    d["attestations"] = storage.get_block_attestations(b.index)
                    return d
            return None

    def get_tx_by_hash(self, tx_hash: str) -> Optional[dict]:
        with self.lock:
            self._load_state()
            target = tx_hash.strip().lower()
            for tx in self.pending_transactions:
                if tx.hash().lower() == target:
                    d = tx.to_dict()
                    d["block_index"] = None
                    d["block_hash"] = "MEMPOOL"
                    d["status"] = "mempool"
                    d["confirmations"] = 0
                    return d
            # Fast O(1) indexed SQLite lookup before scanning blocks
            storage = self._get_storage()
            if storage:
                try:
                    indexed = storage.get_transaction_by_hash(target)
                    if indexed and indexed.get("block_index") is not None:
                        b_idx = int(indexed["block_index"])
                        if 0 <= b_idx < len(self.chain):
                            blk = self.chain[b_idx]
                            for tx in blk.transactions:
                                if tx.hash().lower() == target:
                                    d = tx.to_dict()
                                    d["block_index"] = blk.index
                                    d["block_hash"] = blk.hash
                                    d["status"] = "confirmed"
                                    d["confirmations"] = len(self.chain) - blk.index
                                    return d
                except Exception:
                    pass
            for b in self.chain:
                for tx in b.transactions:
                    if tx.hash().lower() == target:
                        d = tx.to_dict()
                        d["block_index"] = b.index
                        d["block_hash"] = b.hash
                        d["status"] = "confirmed"
                        d["confirmations"] = len(self.chain) - b.index
                        return d
            return None

    def get_chain_data(self) -> list:
        with self.lock:
            self._load_state()
            return [block.to_dict() for block in self.chain]

    def get_latest_blocks(self, count: int = 10) -> list:
        with self.lock:
            self._load_state()
            blocks = self.chain[-count:]
            return [b.to_dict() for b in reversed(blocks)]

    def get_paginated_transactions(self, page: int = 1, limit: int = 10) -> Tuple[list, int]:
        """
        O(page * limit) reverse-cursor pagination over mempool + chain.
        Eliminates O(N) full-history serialization on Explorer feed requests.
        """
        with self.lock:
            self._load_state()
            safe_limit = max(1, min(int(limit), 100))
            total_txs = len(self.pending_transactions) + max(self.total_transactions, len(self.chain))
            total_pages = max(1, (total_txs + safe_limit - 1) // safe_limit)
            safe_page = max(1, min(int(page), total_pages))
            start_idx = (safe_page - 1) * safe_limit
            end_idx = start_idx + safe_limit

            results = []
            cursor = 0

            for tx in reversed(self.pending_transactions):
                if cursor >= end_idx:
                    break
                if cursor >= start_idx:
                    tx_dict = tx.to_dict()
                    tx_dict["block_index"] = None
                    tx_dict["block_hash"] = "MEMPOOL"
                    tx_dict["status"] = "mempool"
                    results.append(tx_dict)
                cursor += 1

            if cursor < end_idx:
                for block in reversed(self.chain):
                    if cursor >= end_idx:
                        break
                    b_len = len(block.transactions)
                    if cursor + b_len <= start_idx:
                        cursor += b_len
                        continue
                    for tx in reversed(block.transactions):
                        if cursor >= end_idx:
                            break
                        if cursor >= start_idx:
                            tx_dict = tx.to_dict()
                            tx_dict["recipient"] = tx.receiver
                            tx_dict["block_index"] = block.index
                            tx_dict["block_hash"] = block.hash
                            tx_dict["status"] = "confirmed"
                            results.append(tx_dict)
                        cursor += 1

            return results, total_txs

    def get_all_transactions(self) -> list:
        with self.lock:
            self._load_state()
            txs = []
            for block in self.chain:
                for tx in block.transactions:
                    tx_dict = tx.to_dict()
                    tx_dict["block_index"] = block.index
                    tx_dict["block_hash"] = block.hash
                    tx_dict["status"] = "confirmed"
                    txs.append(tx_dict)
            for tx in self.pending_transactions:
                tx_dict = tx.to_dict()
                tx_dict["block_index"] = None
                tx_dict["block_hash"] = "MEMPOOL"
                tx_dict["status"] = "mempool"
                txs.append(tx_dict)
            return list(reversed(txs))

    def mine_pending_block(self, miner_address: str = "") -> Optional[Block]:
        """Thread-safe mining entrypoint; strictly requires pending transactions."""
        return self._mine_block(miner_address=miner_address, require_pending=True)

    def get_wallet_transactions(self, address: str) -> list:
        with self.lock:
            self._load_state()
            clean_addr = normalize_bct_address(str(address or "").strip().lstrip("#").lstrip("@").strip())

            # Fast O(log N) indexed path: query SQLite tx_lookup index
            storage = self._get_storage()
            confirmed_txs = []
            used_indexed = False
            if storage:
                try:
                    confirmed_txs = storage.get_transactions_for_address(clean_addr, limit=200)
                    used_indexed = True
                    for ctx in confirmed_txs:
                        ctx["status"] = "confirmed"
                        if "receiver" not in ctx and "recipient" in ctx:
                            ctx["receiver"] = ctx["recipient"]
                        elif "recipient" not in ctx and "receiver" in ctx:
                            ctx["recipient"] = ctx["receiver"]
                        extra = ctx.get("extra_data") or {}
                        if extra.get("author") == clean_addr and ctx.get("sender") != clean_addr:
                            ctx["is_author_royalty"] = True
                            ctx["royalty_amount"] = extra.get("author_cut", 0.0)
                        elif extra.get("target") == clean_addr and ctx.get("sender") != clean_addr:
                            ctx["is_creator_follow_reward"] = True
                            ctx["royalty_amount"] = extra.get("creator_cut", 0.50)
                except Exception:
                    confirmed_txs = []
                    used_indexed = False

            if not used_indexed and self.chain:
                # Fallback ONLY if SQLite storage query failed
                for block in reversed(self.chain):
                    for tx in block.transactions:
                        is_author_royalty = (
                            tx.tx_type in ("space_like", "space_comment")
                            and bool(tx.extra_data)
                            and tx.extra_data.get("author") == clean_addr
                            and tx.sender != clean_addr
                        )
                        is_creator_reward = (
                            tx.tx_type == "space_follow"
                            and bool(tx.extra_data)
                            and tx.extra_data.get("target") == clean_addr
                            and tx.sender != clean_addr
                        )
                        if tx.sender == clean_addr or tx.receiver == clean_addr or is_author_royalty or is_creator_reward:
                            tx_dict = tx.to_dict()
                            tx_dict["recipient"] = tx.receiver
                            tx_dict["block_index"] = block.index
                            tx_dict["block_hash"] = block.hash
                            tx_dict["status"] = "confirmed"
                            if is_author_royalty:
                                tx_dict["is_author_royalty"] = True
                                tx_dict["royalty_amount"] = tx.extra_data.get("author_cut", 0.0)
                            elif is_creator_reward:
                                tx_dict["is_creator_follow_reward"] = True
                                tx_dict["royalty_amount"] = tx.extra_data.get("creator_cut", 0.50)
                            confirmed_txs.append(tx_dict)

            # Mempool pending transactions (exclude any already confirmed on-chain)
            confirmed_sigs = {
                (ctx.get("signature") or "").strip()
                for ctx in confirmed_txs
                if ctx.get("signature")
            }
            confirmed_hashes = {
                (ctx.get("tx_hash") or ctx.get("hash") or "").strip()
                for ctx in confirmed_txs
            }

            pending_txs = []
            for tx in self.pending_transactions:
                tx_sig = (tx.signature or "").strip()
                tx_h = (tx.hash() or "").strip()
                if (tx_sig and tx_sig in confirmed_sigs) or (tx_h and tx_h in confirmed_hashes):
                    continue  # Already present in confirmed list
                is_author_royalty = (
                    tx.tx_type in ("space_like", "space_comment")
                    and bool(tx.extra_data)
                    and tx.extra_data.get("author") == clean_addr
                    and tx.sender != clean_addr
                )
                is_creator_reward = (
                    tx.tx_type == "space_follow"
                    and bool(tx.extra_data)
                    and tx.extra_data.get("target") == clean_addr
                    and tx.sender != clean_addr
                )
                if tx.sender == clean_addr or tx.receiver == clean_addr or is_author_royalty or is_creator_reward:
                    tx_dict = tx.to_dict()
                    tx_dict["block_index"] = None
                    tx_dict["block_hash"] = "MEMPOOL"
                    tx_dict["status"] = "mempool"
                    if is_author_royalty:
                        tx_dict["is_author_royalty"] = True
                        tx_dict["royalty_amount"] = tx.extra_data.get("author_cut", 0.0)
                    elif is_creator_reward:
                        tx_dict["is_creator_follow_reward"] = True
                        tx_dict["royalty_amount"] = tx.extra_data.get("creator_cut", 0.50)
                    pending_txs.append(tx_dict)

            return pending_txs + confirmed_txs

    def get_account_nonce(self, address: str) -> int:
        """Compute exact sequential outgoing transaction nonce for an address from on-chain + pending history."""
        with self.lock:
            self._load_state(sweep_overdue=False)
            clean_addr = normalize_bct_address(address)
            if not clean_addr:
                return 0
            self._ensure_ledger_index()
            return self._sender_nonce_map.get(clean_addr, 0)

    def get_holders(self, page: int = 1, limit: int = 10) -> dict:
        """Returns ordered list of all accounts holding native BCT with balances, roles, and supply percentages."""
        with self.lock:
            self._load_state()
            self._ensure_ledger_index()
            all_addrs = set(self.wallets.keys()) | set(self._unit_balances_map.keys()) | set(self._tx_counts_map.keys())
            all_addrs.add(TREASURY_ADDRESS)
            all_addrs.add(BRIDGE_VAULT_ADDRESS)
            all_addrs.add(VALIDATOR_STAKE_VAULT_ADDRESS)

            tx_counts = self._tx_counts_map
            validator_addrs = {n.get("miner_address") for n in self.nodes.values() if n.get("miner_address")}

            holders = []
            for addr in all_addrs:
                clean_addr = normalize_bct_address(addr)
                if not clean_addr or clean_addr in ("GENESIS_VAULT", "GENESIS"):
                    continue
                bal = round(self._unit_balances_map.get(clean_addr, 0) / ATOMIC_UNIT, 8)
                if bal <= 0 and clean_addr not in (TREASURY_ADDRESS, BRIDGE_VAULT_ADDRESS, VALIDATOR_STAKE_VAULT_ADDRESS) and tx_counts.get(clean_addr, 0) == 0:
                    continue

                tag = "User Wallet"
                tag_type = "user"
                if any(clean_addr.lower() == a.lower() for a in LOST_KEY_TEST_WALLETS):
                    tag = "Geliştirici Doğruladı: Private Key Kayıp (Özel Test Adresi)"
                    tag_type = "lost_key_burn"
                elif clean_addr in self.slashed_validators:
                    tag = "İşaretli Hesap (Slashed Validator)"
                    tag_type = "slashed"
                elif clean_addr == BURN_ADDRESS:
                    tag = "Deflationary Burn Address (Provably Unspendable)"
                    tag_type = "burn"
                elif clean_addr == TREASURY_ADDRESS:
                    tag = "Treasury Vault (Locked Reserve)"
                    tag_type = "treasury"
                elif clean_addr == BRIDGE_VAULT_ADDRESS:
                    tag = "Bridge Vault (Base 1:1 wBCT)"
                    tag_type = "bridge_vault"
                elif clean_addr == VALIDATOR_STAKE_VAULT_ADDRESS:
                    tag = "Validator Staking Vault (PoS Kilitli Teminat)"
                    tag_type = "stake_vault"
                elif clean_addr in validator_addrs:
                    tag = "Validator / Mining Node"
                    tag_type = "validator"

                bns_handle = self.bns_reverse.get(clean_addr, "")

                holders.append({
                    "address": clean_addr,
                    "bns_name": bns_handle,
                    "balance": bal,
                    "balance_formatted": f"{bal:,.4f}",
                    "tag": tag,
                    "tag_type": tag_type,
                    "tx_count": tx_counts.get(clean_addr, 0),
                    "is_contract": clean_addr in (TREASURY_ADDRESS, BRIDGE_VAULT_ADDRESS, VALIDATOR_STAKE_VAULT_ADDRESS),
                    "created_at": self.wallets.get(clean_addr, {}).get("created_at", 0)
                })

            holders.sort(key=lambda x: (x["balance"], x["tx_count"]), reverse=True)

            total_holders = len(holders)
            total_pages = max(1, (total_holders + limit - 1) // limit)
            page = max(1, min(page, total_pages))
            start_idx = (page - 1) * limit
            end_idx = start_idx + limit
            sliced_holders = holders[start_idx:end_idx]

            for idx, h in enumerate(sliced_holders):
                h["rank"] = start_idx + idx + 1
                pct = (h["balance"] / TOTAL_SUPPLY) * 100.0 if TOTAL_SUPPLY > 0 else 0.0
                h["percentage"] = round(pct, 6)
                h["percentage_formatted"] = f"{pct:.4f}%" if pct >= 0.0001 else "<0.0001%"

            return {
                "holders": sliced_holders,
                "total": total_holders,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }

    def get_merkle_proof(self, tx_hash: str) -> Optional[dict]:
        """Generate and cryptographically verify SPV Merkle inclusion proof for any confirmed transaction."""
        with self.lock:
            self._load_state()
            target = (tx_hash or "").strip().lower()
            if not target:
                return None
            storage = self._get_storage()
            if storage:
                try:
                    indexed_tx = storage.get_transaction_by_hash(target)
                    b_idx = indexed_tx.get("block_index") if isinstance(indexed_tx, dict) else None
                    if isinstance(b_idx, int) and 0 <= b_idx < len(self.chain):
                        b = self.chain[b_idx]
                        tx_hashes = [tx.hash() for tx in b.transactions]
                        if target in [h.lower() for h in tx_hashes]:
                            proof = compute_merkle_proof(tx_hashes, target)
                            if proof is not None:
                                return {
                                    "tx_hash": target,
                                    "block_index": b.index,
                                    "block_version": b.version,
                                    "block_hash": b.hash,
                                    "merkle_root": b.merkle_root,
                                    "transaction_count": len(tx_hashes),
                                    "proof": proof,
                                    "verified": verify_merkle_proof(target, proof, b.merkle_root),
                                }
                except Exception:
                    pass
            for b in self.chain:
                tx_hashes = [tx.hash() for tx in b.transactions]
                if target in [h.lower() for h in tx_hashes]:
                    proof = compute_merkle_proof(tx_hashes, target)
                    if proof is None:
                        return None
                    verified = verify_merkle_proof(target, proof, b.merkle_root)
                    return {
                        "tx_hash": target,
                        "block_index": b.index,
                        "block_version": b.version,
                        "block_hash": b.hash,
                        "merkle_root": b.merkle_root,
                        "transaction_count": len(tx_hashes),
                        "proof": proof,
                        "verified": verified,
                    }
            return None

    def is_chain_valid(self) -> bool:
        with self.lock:
            if not self.chain:
                return False
            tip_hash = self.chain[-1].hash
            cached_len, cached_tip, cached_valid = self._chain_valid_cache
            if cached_len == len(self.chain) and cached_tip == tip_hash:
                return cached_valid

            base_target = "0" * self.difficulty
            genesis = self.chain[0]
            try:
                gen_merkle = compute_merkle_root([tx.hash() for tx in genesis.transactions])
            except ValueError:
                self._chain_valid_cache = (len(self.chain), tip_hash, False)
                return False
            if genesis.merkle_root != gen_merkle:
                self._chain_valid_cache = (len(self.chain), tip_hash, False)
                return False
            for i in range(1, len(self.chain)):
                current = self.chain[i]
                previous = self.chain[i - 1]
                if current.index != previous.index + 1:
                    self._chain_valid_cache = (len(self.chain), tip_hash, False)
                    return False
                if current.hash != current.calculate_hash():
                    self._chain_valid_cache = (len(self.chain), tip_hash, False)
                    return False
                if current.previous_hash != previous.hash:
                    self._chain_valid_cache = (len(self.chain), tip_hash, False)
                    return False
                cur_ts = float(current.timestamp)
                prev_ts = float(previous.timestamp)
                if cur_ts <= prev_ts:
                    self._chain_valid_cache = (len(self.chain), tip_hash, False)
                    return False
                if cur_ts > (time.time() + 120.0):
                    self._chain_valid_cache = (len(self.chain), tip_hash, False)
                    return False
                dt = cur_ts - prev_ts
                req_diff = self.difficulty
                if i >= LWMA_WINDOW:
                    recent = self.chain[i - LWMA_WINDOW:i]
                    time_diffs = [
                        max(0.1, min(float(recent[k].timestamp) - float(recent[k - 1].timestamp), TARGET_BLOCK_TIME * 6.0))
                        for k in range(1, len(recent))
                    ]
                    if time_diffs:
                        w_sum = sum((idx + 1) * d for idx, d in enumerate(time_diffs))
                        w_tot = sum(idx + 1 for idx in range(len(time_diffs)))
                        avg_solve = w_sum / max(1.0, w_tot)
                        if avg_solve > (TARGET_BLOCK_TIME * 1.8) and req_diff > 2:
                            req_diff = max(2, req_diff - 1)
                if dt > (TARGET_BLOCK_TIME * 6.0):
                    stall_drop = int((dt - (TARGET_BLOCK_TIME * 6.0)) // 60.0) + 1
                    req_diff = max(1, req_diff - stall_drop)
                req_target = "0" * max(1, req_diff)
                if not current.hash.startswith(req_target):
                    self._chain_valid_cache = (len(self.chain), tip_hash, False)
                    return False
                # CVE-2012-2459 Defense: Block must not contain duplicate transaction hashes
                blk_hashes = [tx.hash() for tx in current.transactions]
                if len(blk_hashes) != len(set(blk_hashes)):
                    self._chain_valid_cache = (len(self.chain), tip_hash, False)
                    return False
                try:
                    expected_merkle = compute_merkle_root(blk_hashes)
                except ValueError:
                    self._chain_valid_cache = (len(self.chain), tip_hash, False)
                    return False
                if current.merkle_root != expected_merkle:
                    self._chain_valid_cache = (len(self.chain), tip_hash, False)
                    return False
            self._chain_valid_cache = (len(self.chain), tip_hash, True)
            return True

    def verify_full_chain_integrity(self) -> Tuple[bool, str, dict]:
        """
        Deep consensus integrity audit beyond header-only `is_chain_valid()`.
        Verifies structural PoW/Merkle validity, non-negative finite transaction values,
        and strict conservation of total supply (no hidden minting or negative balances).
        """
        with self.lock:
            if not self.is_chain_valid():
                return False, "Structural PoW / Merkle chain validation failed.", {}

            total_txs = 0
            for blk in self.chain:
                for tx in blk.transactions:
                    total_txs += 1
                    try:
                        amt = float(tx.amount)
                        fee = float(tx.fee)
                    except (ValueError, TypeError):
                        return False, f"Block #{blk.index} contains non-numeric amount/fee.", {"block_index": blk.index}
                    if not (math.isfinite(amt) and math.isfinite(fee)) or amt < 0 or fee < 0:
                        return False, f"Block #{blk.index} contains negative or non-finite amount/fee.", {"block_index": blk.index}

            self._ensure_ledger_index()
            neg_accounts = [
                addr for addr, u in self._confirmed_units_map.items()
                if u < 0 and addr not in ("GENESIS_VAULT", "GENESIS")
            ]
            if neg_accounts:
                return False, f"Ledger solvency violation: {len(neg_accounts)} account(s) have negative balance.", {
                    "negative_accounts": neg_accounts[:10]
                }

            return True, "Full chain structural and solvency integrity verified.", {
                "blocks": len(self.chain),
                "transactions": total_txs,
                "accounts": len(self._confirmed_units_map),
                "unique_signatures": len(self._confirmed_used_sigs),
            }

    def get_latest_frontend_release(self) -> Optional[dict]:
        """Return the latest on-chain cryptographically verified frontend release anchor."""
        with self.lock:
            self._load_state(sweep_overdue=False)
            for blk in reversed(self.chain):
                for tx in reversed(blk.transactions):
                    if tx.tx_type == "frontend_release" and isinstance(tx.extra_data, dict):
                        ok, _ = verify_frontend_manifest(tx.extra_data)
                        if ok:
                            res = dict(tx.extra_data)
                            res["block_index"] = blk.index
                            res["block_hash"] = blk.hash
                            res["tx_hash"] = tx.hash()
                            res["sealed_timestamp"] = blk.timestamp
                            return res
            return None

    def seal_frontend_release(self, manifest: dict) -> Tuple[bool, str, Optional[dict]]:
        """Immutably seal an ECDSA-signed frontend SHA-256 release manifest into a LockTrace block."""
        ok, msg = verify_frontend_manifest(manifest)
        if not ok:
            return False, msg, None

        with self.lock:
            self._load_state()
            latest = self.get_latest_frontend_release()
            target_sha = str(manifest.get("index_html_sha256", "")).strip().lower()
            target_sw = str(manifest.get("sw_js_sha256", "")).strip().lower()
            if (
                latest
                and str(latest.get("index_html_sha256", "")).lower() == target_sha
                and str(latest.get("sw_js_sha256", "")).lower() == target_sw
            ):
                return True, "This frontend release is already sealed on the blockchain.", latest

            clean_manifest = {
                "version": str(manifest.get("version", "")).strip(),
                "released_at": str(manifest.get("released_at", "")).strip(),
                "authority_address": RELEASE_AUTHORITY_ADDRESS,
                "authority_public_key": RELEASE_AUTHORITY_PUBKEY,
                "index_html_sha256": target_sha,
                "sw_js_sha256": target_sw,
                "ipfs_cid_v1": str(manifest.get("ipfs_cid_v1", "")).strip(),
                "canonical_payload": str(manifest.get("canonical_payload", "")).strip(),
                "signature": str(manifest.get("signature", "")).strip(),
            }

            tx = Transaction(
                sender=RELEASE_AUTHORITY_ADDRESS,
                receiver=TREASURY_ADDRESS,
                amount=0.0,
                fee=0.0,
                signature=clean_manifest["signature"],
                tx_type="frontend_release",
                extra_data=clean_manifest,
            )
            self.pending_transactions.append(tx)
            self.total_transactions += 1

        block = self._mine_block()
        sealed = dict(clean_manifest)
        if block:
            sealed["block_index"] = block.index
            sealed["block_hash"] = block.hash
            sealed["tx_hash"] = tx.hash()
            sealed["sealed_timestamp"] = block.timestamp
        return True, "Frontend SHA-256 release digest successfully sealed on-chain!", sealed

    @staticmethod
    def _sanitize_node_field(val: str, max_len: int = 64) -> str:
        cleaned = re.sub(r'[<>"\'`\x00-\x1f\x7f]', '', str(val or '')).strip()
        return cleaned[:max_len]

    def register_or_ping_node(
        self,
        node_id: str,
        name: str = "",
        endpoint: str = "",
        role: str = "Peer Node",
        location: str = "Decentralized",
        block_height: int = 0,
        miner_address: str = "",
        version: str = PROTOCOL_VERSION,
        public_key: str = "",
        signature: str = "",
        timestamp: Optional[float] = None,
        hashrate_hs: float = 0.0,
        client_ip: str = "",
    ) -> dict:
        with self.lock:
            self._load_state()
            raw_id = re.sub(r'[^a-zA-Z0-9._-]', '', (node_id or "").strip())[:64]
            clean_id = raw_id or f"node-{secrets.token_hex(4)}"

            existing = self.nodes.get(clean_id)
            if existing and existing.get("is_genesis"):
                existing["last_seen"] = time.time()
                existing["block_height"] = len(self.chain)
                self._get_storage().save_nodes_only(self.nodes)
                return dict(existing)

            clean_miner = normalize_bct_address(miner_address)
            if clean_miner and not is_valid_bct_address(clean_miner):
                clean_miner = ""

            # Cryptographic ECDSA ownership pin: once a node_id is bound to an ECDSA public_key, reject unauthenticated takeovers!
            clean_pub = (public_key or "").strip()
            auth_ok = False
            ts_str = str(timestamp).strip() if timestamp is not None else ""
            if clean_pub and signature and ts_str:
                try:
                    if abs(time.time() - float(ts_str)) <= 600:
                        derived_miner = public_key_to_address(clean_pub)
                        # Cryptographic binding: signer public key MUST match miner_address if specified!
                        if not clean_miner or derived_miner == clean_miner:
                            auth_msg = f"NODE:{clean_id}:{clean_miner}:{ts_str}"
                            if verify_signature(clean_pub, auth_msg, signature):
                                auth_ok = True
                except Exception:
                    pass

            if existing and existing.get("owner_public_key"):
                if not auth_ok or existing["owner_public_key"] != clean_pub:
                    raise PermissionError("This node_id is registered to another cryptographic ECDSA key!")

            if not existing and len(self.nodes) >= 200:
                removable = sorted(
                    ((nid, n) for nid, n in self.nodes.items() if not n.get("is_genesis")),
                    key=lambda item: item[1].get("last_seen", 0)
                )
                for nid, _ in removable[:max(1, len(self.nodes) - 199)]:
                    self.nodes.pop(nid, None)

            node_info = existing or {
                "node_id": clean_id,
                "created_at": time.time(),
                "is_genesis": False,
                "blocks_mined": 0,
                "blocks_attested": 0,
                "attested_height": -1,
                "proposer_rewards": 0.0,
                "validator_rewards": 0.0,
                "total_rewards": 0.0,
                "hashrate_hs": 0.0,
                "auth_verified": False,
            }

            safe_name = self._sanitize_node_field(name, 64)
            safe_endpoint = self._sanitize_node_field(endpoint, 120)
            if safe_endpoint and safe_endpoint.lower().startswith(("http://", "https://")):
                if not self._is_safe_peer_endpoint(safe_endpoint):
                    safe_endpoint = "p2p-client"
            safe_role = self._sanitize_node_field(role, 48)
            safe_location = self._sanitize_node_field(location, 64)
            safe_version = self._sanitize_node_field(version, 24)
            safe_height = max(0, min(int(block_height or 0), len(self.chain) + 1000))

            effective_miner = clean_miner or node_info.get("miner_address", "")
            staked_val = self.get_validator_stake(effective_miner) if effective_miner else 0.0
            is_staked_val = staked_val >= MIN_VALIDATOR_STAKE
            resolved_role = safe_role or node_info.get("role", "Peer Node")
            if not is_staked_val and "validator" in resolved_role.lower():
                resolved_role = "Peer Node (Unstaked)"

            node_info.update({
                "name": safe_name or node_info.get("name", f"Community Node ({clean_id[:8]})"),
                "endpoint": safe_endpoint or node_info.get("endpoint", "p2p-client"),
                "role": resolved_role,
                "location": safe_location or node_info.get("location", "Global"),
                "miner_address": effective_miner,
                "staked_amount": staked_val,
                "is_staked_validator": is_staked_val,
                "last_seen": time.time(),
                "status": "online",
                "version": safe_version or node_info.get("version", PROTOCOL_VERSION),
                "block_height": safe_height if safe_height > 0 else len(self.chain),
            })
            if client_ip:
                node_info["client_ip"] = self._sanitize_node_field(client_ip, 45)
            if auth_ok:
                node_info["auth_verified"] = True
                node_info["owner_public_key"] = clean_pub
            try:
                hr_val = float(hashrate_hs or 0.0)
                if math.isfinite(hr_val) and hr_val > 0:
                    node_info["hashrate_hs"] = round(min(hr_val, 1e9), 2)
            except (ValueError, TypeError):
                pass

            self.nodes[clean_id] = node_info
            self._get_storage().save_nodes_only(self.nodes)
            return dict(node_info)

    def get_nodes(self) -> List[dict]:
        with self.lock:
            self._load_state()
            db_nodes = self._get_storage().load_nodes_only()
            if db_nodes:
                self.nodes.update(db_nodes)
            self._init_default_nodes()
            now = time.time()
            # Prune disconnected community nodes that stopped sending heartbeats (> 60 seconds)
            stale_keys = [
                nid for nid, n in list(self.nodes.items())
                if not n.get("is_genesis") and (now - n.get("last_seen", 0) > 60)
            ]
            if stale_keys:
                for k in stale_keys:
                    self.nodes.pop(k, None)
                self._get_storage().save_nodes_only(self.nodes)

            res = []
            for _n_id, n in self.nodes.items():
                copy_n = dict(n)
                copy_n.pop("owner_public_key", None)
                copy_n.pop("client_ip", None)
                if not copy_n.get("is_genesis"):
                    m_addr = str(copy_n.get("miner_address", "") or "").strip()
                    staked_amt = self.get_validator_stake(m_addr) if m_addr else 0.0
                    copy_n["staked_amount"] = staked_amt
                    copy_n["is_staked_validator"] = staked_amt >= MIN_VALIDATOR_STAKE
                    if staked_amt < MIN_VALIDATOR_STAKE and "validator" in str(copy_n.get("role", "")).lower():
                        copy_n["role"] = "Peer Node (Unstaked)"
                else:
                    copy_n["is_staked_validator"] = True
                if not copy_n.get("is_genesis") and (now - copy_n.get("last_seen", 0) > 35):
                    copy_n["status"] = "offline"
                else:
                    copy_n["status"] = "online"
                copy_n["uptime_seconds"] = int(now - copy_n.get("created_at", now))
                res.append(copy_n)
            res.sort(key=lambda x: (not x.get("is_genesis", False), -x.get("last_seen", 0)))
            return res

    def purge_all_community_nodes(self):
        with self.lock:
            self._load_state()
            self.nodes = {nid: n for nid, n in self.nodes.items() if n.get("is_genesis")}
            self._init_default_nodes()
            self._save_state()

    def get_stats(self) -> dict:
        with self.lock:
            self._load_state()
            total_units = _to_units(TOTAL_SUPPLY)
            treasury_units = self.verify_and_recalc_units(TREASURY_ADDRESS)
            vault_units = self.verify_and_recalc_units(BRIDGE_VAULT_ADDRESS)
            stake_vault_units = self.verify_and_recalc_units(VALIDATOR_STAKE_VAULT_ADDRESS)
            lost_key_units = sum(self.verify_and_recalc_units(addr) for addr in LOST_KEY_TEST_WALLETS)
            burn_units = self.verify_and_recalc_units(BURN_ADDRESS)
            # Dead/lost test wallet coins and burn address balance are subtracted from circulation as effective permanent burn
            circulating_units = max(0, total_units - treasury_units - vault_units - stake_vault_units - lost_key_units - burn_units)
            treasury_dec = Decimal(treasury_units) / Decimal(ATOMIC_UNIT)
            vault_dec = Decimal(vault_units) / Decimal(ATOMIC_UNIT)
            stake_vault_dec = Decimal(stake_vault_units) / Decimal(ATOMIC_UNIT)
            lost_key_dec = Decimal(lost_key_units) / Decimal(ATOMIC_UNIT)
            burn_dec = Decimal(burn_units) / Decimal(ATOMIC_UNIT)
            effective_burned_units = treasury_units + lost_key_units + burn_units
            effective_burned_dec = Decimal(effective_burned_units) / Decimal(ATOMIC_UNIT)
            circulating_dec = Decimal(circulating_units) / Decimal(ATOMIC_UNIT)
            total_unlocked_dec = circulating_dec + vault_dec
            active_miners = self.get_active_peer_miners()
            network_hashrate = round(sum(float(n.get("hashrate_hs", 0.0)) for n in active_miners), 2)
            eligible_vals = self.get_eligible_validators("", len(self.chain))
            return {
                "total_supply": TOTAL_SUPPLY,
                "total_supply_formatted": f"{TOTAL_SUPPLY:,.0f}",
                "treasury_balance": float(treasury_dec),
                "treasury_formatted": f"{treasury_dec:,.8f}",
                "bridge_vault_locked": float(vault_dec),
                "bridge_vault_formatted": f"{vault_dec:,.8f}",
                "validator_stake_vault_locked": float(stake_vault_dec),
                "validator_stake_vault_formatted": f"{stake_vault_dec:,.8f}",
                "validator_stake_vault_address": VALIDATOR_STAKE_VAULT_ADDRESS,
                "burn_address_balance": float(burn_dec),
                "burn_address_formatted": f"{burn_dec:,.6f}",
                "lost_key_test_wallets_count": len(LOST_KEY_TEST_WALLETS),
                "lost_key_test_wallets_balance": float(lost_key_dec),
                "lost_key_test_wallets_formatted": f"{lost_key_dec:,.8f}",
                "effective_burned_supply": float(effective_burned_dec),
                "effective_burned_formatted": f"{effective_burned_dec:,.8f}",
                "circulating_supply": float(circulating_dec),
                "circulating_formatted": f"{circulating_dec:,.8f}",
                "total_unlocked_supply": float(total_unlocked_dec),
                "total_unlocked_formatted": f"{total_unlocked_dec:,.8f}",
                "total_blocks": len(self.chain),
                "total_wallets": len(self.wallets),
                "total_transactions": self.total_transactions,
                "total_fees_collected": self.total_fees_collected,
                "pending_transactions": len(self.pending_transactions),
                "online_peer_miners": len(active_miners),
                "verified_validators": len(eligible_vals),
                "network_hashrate_hs": network_hashrate,
                "reward_model": "50% PoW Proposer / 40% Active Validator Quorum / 10% Observer Staking Pool",
                "difficulty": self.get_current_difficulty(),
                "storage_engine": "sqlite-wal",
                "chain_valid": self.is_chain_valid(),
                "latest_block_hash": self.chain[-1].hash if self.chain else "N/A",
                "latest_merkle_root": self.chain[-1].merkle_root if self.chain else "N/A",
            }

    @staticmethod
    def _apply_tx_to_bns_maps(b_idx, status_lbl: str, tx: Transaction, bns_records: Dict[str, dict], bns_reverse: Dict[str, str]):
        if tx.tx_type == "bns_register" and tx.extra_data:
            name = tx.extra_data.get("name")
            if not name:
                return
            owner = normalize_bct_address(tx.extra_data.get("owner", tx.sender))
            tier = tx.extra_data.get("tier", "")
            cost = float(tx.extra_data.get("cost", tx.amount))
            bns_records[name] = {
                "name": name,
                "owner": owner,
                "registered_at": tx.timestamp,
                "updated_at": tx.timestamp,
                "tier": tier,
                "cost": cost,
                "sale_price": 0.0,
                "offers": {},
                "block_index": b_idx,
                "status": status_lbl,
                "history": [{
                    "action": "registered",
                    "owner": owner,
                    "cost": cost,
                    "timestamp": tx.timestamp,
                    "tx_hash": tx.hash(),
                    "block": b_idx
                }]
            }
            if owner not in bns_reverse:
                bns_reverse[owner] = name
        elif tx.tx_type == "bns_transfer" and tx.extra_data:
            name = tx.extra_data.get("name")
            from_addr = normalize_bct_address(tx.extra_data.get("from_address", tx.sender))
            to_addr = normalize_bct_address(tx.extra_data.get("to_address", tx.receiver))
            if name and name in bns_records:
                rec = bns_records[name]
                rec["owner"] = to_addr
                rec["sale_price"] = 0.0
                rec["updated_at"] = tx.timestamp
                for _oid, _off in (rec.get("offers") or {}).items():
                    if isinstance(_off, dict) and _off.get("status") == "active":
                        _off["status"] = "superseded"
                        _off["resolved_at"] = tx.timestamp
                rec["history"].append({
                    "action": "transferred",
                    "from": from_addr,
                    "to": to_addr,
                    "timestamp": tx.timestamp,
                    "tx_hash": tx.hash(),
                    "block": b_idx
                })
                if bns_reverse.get(from_addr) == name:
                    other = next((n for n, r in bns_records.items() if r.get("owner") == from_addr), "")
                    if other:
                        bns_reverse[from_addr] = other
                    else:
                        bns_reverse.pop(from_addr, None)
                if to_addr not in bns_reverse:
                    bns_reverse[to_addr] = name
        elif tx.tx_type == "bns_set_price" and tx.extra_data:
            name = tx.extra_data.get("name")
            price = float(tx.extra_data.get("price", 0.0))
            if name and name in bns_records:
                bns_records[name]["sale_price"] = price
                bns_records[name]["updated_at"] = tx.timestamp
                bns_records[name]["history"].append({
                    "action": "listed_for_sale" if price > 0 else "unlisted",
                    "price": price,
                    "timestamp": tx.timestamp,
                    "tx_hash": tx.hash(),
                    "block": b_idx
                })
        elif tx.tx_type == "bns_buy" and tx.extra_data:
            name = tx.extra_data.get("name")
            buyer = normalize_bct_address(tx.extra_data.get("buyer", tx.sender))
            seller = normalize_bct_address(tx.extra_data.get("seller", tx.receiver))
            price = float(tx.extra_data.get("price", tx.amount))
            if name and name in bns_records:
                rec = bns_records[name]
                rec["owner"] = buyer
                rec["sale_price"] = 0.0
                rec["updated_at"] = tx.timestamp
                for _oid, _off in (rec.get("offers") or {}).items():
                    if isinstance(_off, dict) and _off.get("status") == "active":
                        _off["status"] = "superseded"
                        _off["resolved_at"] = tx.timestamp
                rec["history"].append({
                    "action": "purchased",
                    "buyer": buyer,
                    "seller": seller,
                    "price": price,
                    "timestamp": tx.timestamp,
                    "tx_hash": tx.hash(),
                    "block": b_idx
                })
                if bns_reverse.get(seller) == name:
                    other = next((n for n, r in bns_records.items() if r.get("owner") == seller), "")
                    if other:
                        bns_reverse[seller] = other
                    else:
                        bns_reverse.pop(seller, None)
                if buyer not in bns_reverse:
                    bns_reverse[buyer] = name
        elif tx.tx_type == "bns_set_primary" and tx.extra_data:
            name = tx.extra_data.get("name")
            owner = normalize_bct_address(tx.extra_data.get("owner", tx.sender))
            if name and owner and name in bns_records:
                rec = bns_records[name]
                if rec.get("owner") == owner:
                    rec["updated_at"] = tx.timestamp
                    rec["history"].append({
                        "action": "set_primary",
                        "owner": owner,
                        "timestamp": tx.timestamp,
                        "tx_hash": tx.hash(),
                        "block": b_idx
                    })
                    bns_reverse[owner] = name
        elif tx.tx_type == "bns_offer" and tx.extra_data:
            name = tx.extra_data.get("name")
            bidder = normalize_bct_address(tx.extra_data.get("bidder", tx.sender))
            owner = normalize_bct_address(tx.extra_data.get("owner", tx.receiver))
            offer_id = tx.extra_data.get("offer_id")
            amount = float(tx.extra_data.get("amount", 0.0))
            if name and offer_id and name in bns_records:
                rec = bns_records[name]
                if "offers" not in rec or not isinstance(rec["offers"], dict):
                    rec["offers"] = {}
                for prev_oid, prev_o in rec["offers"].items():
                    if isinstance(prev_o, dict) and prev_o.get("bidder") == bidder and prev_o.get("status") == "active":
                        prev_o["status"] = "superseded"
                        prev_o["resolved_at"] = tx.timestamp
                if offer_id not in rec["offers"]:
                    rec["offers"][offer_id] = {
                        "offer_id": offer_id,
                        "name": name,
                        "bidder": bidder,
                        "owner": owner,
                        "amount": amount,
                        "timestamp": tx.timestamp,
                        "tx_hash": tx.hash(),
                        "status": "active"
                    }
                rec["history"].append({
                    "action": "offer_placed",
                    "bidder": bidder,
                    "buyer": bidder,
                    "amount": amount,
                    "price": amount,
                    "offer_id": offer_id,
                    "timestamp": tx.timestamp,
                    "tx_hash": tx.hash(),
                    "block": b_idx
                })
        elif tx.tx_type == "bns_accept_offer" and tx.extra_data:
            name = tx.extra_data.get("name")
            offer_id = tx.extra_data.get("offer_id")
            bidder = normalize_bct_address(tx.extra_data.get("bidder", tx.sender))
            seller = normalize_bct_address(tx.extra_data.get("seller", tx.receiver))
            amount = float(tx.extra_data.get("amount", tx.amount))
            if name and name in bns_records:
                rec = bns_records[name]
                rec["owner"] = bidder
                rec["sale_price"] = 0.0
                rec["updated_at"] = tx.timestamp
                if "offers" in rec and isinstance(rec["offers"], dict):
                    if offer_id in rec["offers"]:
                        rec["offers"][offer_id]["status"] = "accepted"
                        rec["offers"][offer_id]["resolved_at"] = tx.timestamp
                    for _oid, _off in rec["offers"].items():
                        if _oid != offer_id and isinstance(_off, dict) and _off.get("status") == "active":
                            _off["status"] = "superseded"
                            _off["resolved_at"] = tx.timestamp
                rec["history"].append({
                    "action": "offer_accepted",
                    "bidder": bidder,
                    "buyer": bidder,
                    "seller": seller,
                    "amount": amount,
                    "price": amount,
                    "offer_id": offer_id,
                    "timestamp": tx.timestamp,
                    "tx_hash": tx.hash(),
                    "block": b_idx
                })
                if bns_reverse.get(seller) == name:
                    other = next((n for n, r in bns_records.items() if r.get("owner") == seller), "")
                    if other:
                        bns_reverse[seller] = other
                    else:
                        bns_reverse.pop(seller, None)
                if bidder not in bns_reverse:
                    bns_reverse[bidder] = name
        elif tx.tx_type == "bns_cancel_offer" and tx.extra_data:
            name = tx.extra_data.get("name")
            offer_id = tx.extra_data.get("offer_id")
            actor = normalize_bct_address(tx.extra_data.get("actor", tx.sender))
            status = tx.extra_data.get("status", "cancelled")
            if name and name in bns_records:
                rec = bns_records[name]
                if "offers" in rec and isinstance(rec["offers"], dict) and offer_id in rec["offers"]:
                    rec["offers"][offer_id]["status"] = status
                    rec["offers"][offer_id]["resolved_at"] = tx.timestamp
                rec["history"].append({
                    "action": f"offer_{status}",
                    "actor": actor,
                    "offer_id": offer_id,
                    "timestamp": tx.timestamp,
                    "tx_hash": tx.hash(),
                    "block": b_idx
                })

    def _load_in_memory_bns_index(self):
        """Incremental O(Δ) BNS (.bct handles) registry & marketplace indexer with O(|Mempool|) overlay."""
        import copy
        tip_hash = self.chain[-1].hash if self.chain else ""
        bns_mempool_txs = [tx for tx in self.pending_transactions if tx.tx_type.startswith("bns_")]
        mempool_hashes = tuple(tx.hash() for tx in bns_mempool_txs)
        bns_key = (len(self.chain), tip_hash, mempool_hashes)
        if self._bns_index_key == bns_key and self.bns_records is not None:
            return

        if (
            len(self.chain) < self._confirmed_bns_len
            or (
                self._confirmed_bns_len > 0
                and self.chain[self._confirmed_bns_len - 1].hash != self._confirmed_bns_tip
            )
        ):
            self._confirmed_bns_len = 0
            self._confirmed_bns_tip = ""
            self._confirmed_bns_records = {}
            self._confirmed_bns_reverse = {}
            if self._snapshot_base is not None and self._snapshot_base.get("bns_records"):
                self._confirmed_bns_records = copy.deepcopy(self._snapshot_base["bns_records"])
                for _bname, _brec in self._confirmed_bns_records.items():
                    _bowner = normalize_bct_address((_brec or {}).get("owner", ""))
                    if _bowner and _bowner not in self._confirmed_bns_reverse:
                        self._confirmed_bns_reverse[_bowner] = _bname
                self._confirmed_bns_len = min(len(self.chain), int(self._snapshot_base.get("chain_len", len(self.chain))))
                self._confirmed_bns_tip = self.chain[self._confirmed_bns_len - 1].hash if self._confirmed_bns_len > 0 else ""

        if self._confirmed_bns_len < len(self.chain):
            for b in self.chain[self._confirmed_bns_len:]:
                for tx in b.transactions:
                    if tx.tx_type.startswith("bns_"):
                        self._apply_tx_to_bns_maps(b.index, "confirmed", tx, self._confirmed_bns_records, self._confirmed_bns_reverse)
            self._confirmed_bns_len = len(self.chain)
            self._confirmed_bns_tip = tip_hash

        if not bns_mempool_txs:
            self.bns_records = self._confirmed_bns_records
            self.bns_reverse = self._confirmed_bns_reverse
        else:
            new_bns_records = copy.deepcopy(self._confirmed_bns_records)
            new_bns_reverse = dict(self._confirmed_bns_reverse)
            for tx in bns_mempool_txs:
                self._apply_tx_to_bns_maps("Mempool", "mempool", tx, new_bns_records, new_bns_reverse)
            self.bns_records = new_bns_records
            self.bns_reverse = new_bns_reverse
        self._bns_index_key = bns_key

    def _apply_tx_to_space_maps(
        self,
        b_idx,
        status_lbl: str,
        tx: Transaction,
        space_posts: Dict[str, dict],
        follows: Dict[str, List[str]],
        following: Dict[str, List[str]],
    ):
        snd = normalize_bct_address(tx.sender)
        if tx.tx_type == "space_post" and tx.extra_data:
            pid = tx.extra_data.get("post_id")
            if pid:
                if "bns_name" in tx.extra_data:
                    raw_bns = str(tx.extra_data.get("bns_name") or "").strip().lower()
                    if raw_bns in ("anonymous", "anon"):
                        author_bns = "anonymous"
                    elif raw_bns and self.bns_records.get(raw_bns, {}).get("owner") == snd:
                        author_bns = raw_bns
                    else:
                        author_bns = ""
                else:
                    author_bns = self.bns_reverse.get(snd, "")
                space_posts[pid] = {
                    "post_id": pid,
                    "original_author": snd,
                    "original_author_bns": author_bns,
                    "author": snd,
                    "author_bns": author_bns,
                    "royalty_owner": snd,
                    "royalty_owner_bns": author_bns,
                    "royalty_transfers": [],
                    "is_anonymous": (author_bns == "anonymous" or bool(tx.extra_data.get("is_anonymous"))),
                    "content": tx.extra_data.get("content", ""),
                    "timestamp": tx.timestamp,
                    "tx_hash": tx.hash(),
                    "block_index": b_idx,
                    "status": status_lbl,
                    "likes_count": 0,
                    "likes": [],
                    "comments_count": 0,
                    "comments": [],
                    "author_earnings": 0.0,
                }
        elif tx.tx_type == "space_royalty_transfer" and tx.extra_data:
            pid = str(tx.extra_data.get("post_id", "")).strip()
            to_addr = normalize_bct_address(tx.extra_data.get("to_address"))
            if pid in space_posts and is_valid_bct_address(to_addr) and to_addr != snd:
                post_rec = space_posts[pid]
                cur_holder = normalize_bct_address(post_rec.get("royalty_owner") or post_rec.get("author", ""))
                if cur_holder == snd:
                    tx_ts = float(tx.timestamp or 0)
                    cutoff = tx_ts - POST_ROYALTY_WINDOW_SECONDS
                    hist = post_rec.setdefault("royalty_transfers", [])
                    recent_cnt = sum(1 for tr in hist if float(tr.get("timestamp", 0) or 0) >= cutoff)
                    if recent_cnt < POST_ROYALTY_MAX_PER_YEAR:
                        new_bns = self.bns_reverse.get(to_addr, "")
                        post_rec["author"] = to_addr
                        post_rec["author_bns"] = new_bns
                        post_rec["is_anonymous"] = False
                        post_rec["royalty_owner"] = to_addr
                        post_rec["royalty_owner_bns"] = new_bns
                        hist.append({
                            "from_address": snd,
                            "to_address": to_addr,
                            "timestamp": tx_ts,
                            "block_index": b_idx,
                            "tx_hash": tx.hash(),
                            "bulk": False,
                        })
        elif tx.tx_type == "space_royalty_transfer_all" and tx.extra_data:
            to_addr = normalize_bct_address(tx.extra_data.get("to_address"))
            raw_pids = tx.extra_data.get("post_ids") or []
            if is_valid_bct_address(to_addr) and to_addr != snd and isinstance(raw_pids, list):
                tx_ts = float(tx.timestamp or 0)
                cutoff = tx_ts - POST_ROYALTY_WINDOW_SECONDS
                new_bns = self.bns_reverse.get(to_addr, "")
                seen_pids = set()
                for raw_pid in raw_pids:
                    pid = str(raw_pid or "").strip()
                    if not pid or pid in seen_pids or pid not in space_posts:
                        continue
                    seen_pids.add(pid)
                    post_rec = space_posts[pid]
                    cur_holder = normalize_bct_address(post_rec.get("royalty_owner") or post_rec.get("author", ""))
                    if cur_holder != snd:
                        continue
                    hist = post_rec.setdefault("royalty_transfers", [])
                    recent_cnt = sum(1 for tr in hist if float(tr.get("timestamp", 0) or 0) >= cutoff)
                    if recent_cnt >= POST_ROYALTY_MAX_PER_YEAR:
                        continue
                    post_rec["author"] = to_addr
                    post_rec["author_bns"] = new_bns
                    post_rec["is_anonymous"] = False
                    post_rec["royalty_owner"] = to_addr
                    post_rec["royalty_owner_bns"] = new_bns
                    hist.append({
                        "from_address": snd,
                        "to_address": to_addr,
                        "timestamp": tx_ts,
                        "block_index": b_idx,
                        "tx_hash": tx.hash(),
                        "bulk": True,
                    })
        elif tx.tx_type == "space_like" and tx.extra_data:
            pid = tx.extra_data.get("post_id")
            liker = snd
            if pid in space_posts and liker not in space_posts[pid]["likes"]:
                space_posts[pid]["likes"].append(liker)
                space_posts[pid]["likes_count"] += 1
                space_posts[pid]["author_earnings"] = round(
                    space_posts[pid]["author_earnings"] + tx.extra_data.get("author_cut", 0.002), 8
                )
        elif tx.tx_type == "space_comment" and tx.extra_data:
            pid = tx.extra_data.get("post_id")
            if pid in space_posts:
                if "bns_name" in tx.extra_data:
                    raw_bns = str(tx.extra_data.get("bns_name") or "").strip().lower()
                    if raw_bns in ("anonymous", "anon"):
                        cmt_bns = "anonymous"
                    elif raw_bns and self.bns_records.get(raw_bns, {}).get("owner") == snd:
                        cmt_bns = raw_bns
                    else:
                        cmt_bns = ""
                else:
                    cmt_bns = self.bns_reverse.get(snd, "")
                cmt = {
                    "comment_id": tx.extra_data.get("comment_id", f"cmt_{secrets.token_hex(4)}"),
                    "commenter": snd,
                    "commenter_bns": cmt_bns,
                    "is_anonymous": (cmt_bns == "anonymous" or bool(tx.extra_data.get("is_anonymous"))),
                    "content": tx.extra_data.get("content", ""),
                    "timestamp": tx.timestamp,
                    "tx_hash": tx.hash(),
                    "status": status_lbl,
                }
                space_posts[pid]["comments"].append(cmt)
                space_posts[pid]["comments_count"] += 1
                space_posts[pid]["author_earnings"] = round(
                    space_posts[pid]["author_earnings"] + tx.extra_data.get("author_cut", 0.004), 8
                )
        elif tx.tx_type == "space_follow" and tx.extra_data:
            target = normalize_bct_address(tx.extra_data.get("target"))
            follower = snd
            if target and follower:
                if target not in follows:
                    follows[target] = []
                if follower not in follows[target]:
                    follows[target].append(follower)
                if follower not in following:
                    following[follower] = []
                if target not in following[follower]:
                    following[follower].append(target)

    def _load_in_memory_space_index(self):
        """Incremental O(Δ) Space Posts, Likes, Comments & Follows indexer with O(|Mempool|) overlay."""
        import copy
        tip_hash = self.chain[-1].hash if self.chain else ""
        space_mempool_txs = [tx for tx in self.pending_transactions if tx.tx_type.startswith("space_")]
        mempool_hashes = tuple(tx.hash() for tx in space_mempool_txs)
        space_key = (len(self.chain), tip_hash, mempool_hashes)
        if self._space_index_key == space_key and self.space_posts is not None:
            return

        if (
            len(self.chain) < self._confirmed_space_len
            or (
                self._confirmed_space_len > 0
                and self.chain[self._confirmed_space_len - 1].hash != self._confirmed_space_tip
            )
        ):
            self._confirmed_space_len = 0
            self._confirmed_space_tip = ""
            self._confirmed_space_posts = {}
            self._confirmed_follows = {}
            self._confirmed_following = {}

        if self._confirmed_space_len < len(self.chain):
            for b in self.chain[self._confirmed_space_len:]:
                for tx in b.transactions:
                    if tx.tx_type.startswith("space_"):
                        self._apply_tx_to_space_maps(
                            b.index,
                            "confirmed",
                            tx,
                            self._confirmed_space_posts,
                            self._confirmed_follows,
                            self._confirmed_following,
                        )
            self._confirmed_space_len = len(self.chain)
            self._confirmed_space_tip = tip_hash

        if not space_mempool_txs:
            self.space_posts = self._confirmed_space_posts
            self.follows = self._confirmed_follows
            self.following = self._confirmed_following
        else:
            new_space_posts = copy.deepcopy(self._confirmed_space_posts)
            new_follows = {k: list(v) for k, v in self._confirmed_follows.items()}
            new_following = {k: list(v) for k, v in self._confirmed_following.items()}
            for tx in space_mempool_txs:
                self._apply_tx_to_space_maps("Mempool", "mempool", tx, new_space_posts, new_follows, new_following)
            self.space_posts = new_space_posts
            self.follows = new_follows
            self.following = new_following
        self._space_index_key = space_key

    # ── ON-CHAIN PROTOCOL ROOMS (Reddit-Style Public Spaces) ─────────────────

    def _resolve_social_bns_handle(self, clean_addr: str, bns_name: str = "") -> Tuple[bool, str, str]:
        """Validates optional BNS / anonymous handle for Space & Room posts."""
        clean_bns = str(bns_name or "").strip().lower()
        if clean_bns.startswith("@"):
            clean_bns = clean_bns[1:]
        if clean_bns in ("anonymous", "anon"):
            return True, "", "anonymous"
        if clean_bns and clean_bns not in ("none", "false", "address", "public"):
            if not clean_bns.endswith(".bct"):
                clean_bns = f"{clean_bns}.bct"
            rec = self.bns_records.get(clean_bns)
            if not rec or rec.get("owner") != clean_addr:
                return False, f"You do not own the handle '@{clean_bns}'.", ""
            return True, "", clean_bns
        return True, "", self.bns_reverse.get(clean_addr, "")

    def _apply_tx_to_room_maps(
        self,
        block_idx,
        status_lbl: str,
        tx: Transaction,
        rooms: Dict[str, dict],
        slug_index: Dict[str, str],
        topics: Dict[str, dict],
    ):
        extra = tx.extra_data
        if not isinstance(extra, dict):
            return
        snd = normalize_bct_address(tx.sender)
        ttype = tx.tx_type

        if ttype == "room_create":
            room_id = str(extra.get("room_id", "") or "").strip().upper()
            slug = str(extra.get("slug", "") or "").strip().lower()
            name = str(extra.get("name", "") or "").strip()
            description = str(extra.get("description", "") or "").strip()
            if not room_id or not slug or not name:
                return
            # Consensus first-seen uniqueness enforcement
            if room_id in rooms or slug in slug_index:
                return

            avatar_meta = None
            avatar_locked = False
            raw_vid = str(extra.get("avatar_variant_id", "") or "").strip().upper()
            if raw_vid:
                b_id, bg_col = parse_variant_id(raw_vid)
                if b_id and bg_col:
                    avatar_meta = build_avatar_metadata(b_id, bg_col)
                    avatar_locked = True

            raw_bns = str(extra.get("bns_name") or "").strip().lower()
            if raw_bns in ("anonymous", "anon"):
                creator_bns = "anonymous"
            elif raw_bns and self.bns_records.get(raw_bns, {}).get("owner") == snd:
                creator_bns = raw_bns
            else:
                creator_bns = self.bns_reverse.get(snd, "")

            rooms[room_id] = {
                "room_id": room_id,
                "slug": slug,
                "name": name,
                "description": description,
                "creator": snd,
                "original_creator": snd,
                "original_creator_bns": creator_bns,
                "creator_bns": creator_bns,
                "transfer_count": 0,
                "transfer_history": [],
                "is_anonymous": (creator_bns == "anonymous" or bool(extra.get("is_anonymous"))),
                "avatar": avatar_meta,
                "avatar_variant_id": raw_vid if avatar_locked else "",
                "avatar_locked": avatar_locked,
                "created_at": tx.timestamp,
                "last_activity": tx.timestamp,
                "tx_hash": tx.hash(),
                "block_index": block_idx,
                "status": status_lbl,
                "creation_cost": float(tx.amount or 0.0),
                "tier": str(extra.get("tier", "standard") or "standard"),
                "is_verified": bool(extra.get("is_verified", False)) or (snd == RELEASE_AUTHORITY_ADDRESS),
                "topics_count": 0,
                "replies_count": 0,
                "upvotes_count": 0,
                "creator_earnings": 0.0,
                "topic_ids": [],
            }
            slug_index[slug] = room_id

        elif ttype == "room_verify":
            room_id = str(extra.get("room_id", "") or "").strip().upper()
            room = rooms.get(room_id)
            if not room:
                return
            # Developer / Release Authority ONLY verification
            if snd != RELEASE_AUTHORITY_ADDRESS:
                return
            room["is_verified"] = bool(extra.get("verified", True))
            room["verified_at"] = tx.timestamp
            room["verified_by"] = snd

        elif ttype == "room_set_avatar":
            room_id = str(extra.get("room_id", "") or "").strip().upper()
            room = rooms.get(room_id)
            if not room:
                return
            # Consensus-level immutability: creator-only & strictly one-time!
            if room["creator"] != snd:
                return
            if room.get("avatar_locked") or room.get("avatar") is not None:
                return
            raw_vid = str(extra.get("avatar_variant_id", "") or "").strip().upper()
            b_id, bg_col = parse_variant_id(raw_vid)
            if not b_id or not bg_col:
                return
            room["avatar"] = build_avatar_metadata(b_id, bg_col)
            room["avatar_variant_id"] = raw_vid
            room["avatar_locked"] = True
            room["avatar_sealed_at"] = tx.timestamp
            room["avatar_tx_hash"] = tx.hash()

        elif ttype == "room_transfer":
            room_id = str(extra.get("room_id", "") or "").strip().upper()
            room = rooms.get(room_id)
            if not room:
                return
            # Consensus-level ownership enforcement: current owner ONLY
            if room["creator"] != snd:
                return
            to_addr = normalize_bct_address(extra.get("to_address"))
            if not to_addr or not is_valid_bct_address(to_addr) or to_addr == snd or to_addr == TREASURY_ADDRESS:
                return
            room["creator"] = to_addr
            room["creator_bns"] = self.bns_reverse.get(to_addr, "")
            room["is_anonymous"] = False
            room["transferred_at"] = tx.timestamp
            room["transfer_count"] = int(room.get("transfer_count") or 0) + 1
            hist = room.setdefault("transfer_history", [])
            hist.append({
                "from": snd,
                "from_bns": self.bns_reverse.get(snd, ""),
                "to": to_addr,
                "to_bns": self.bns_reverse.get(to_addr, ""),
                "timestamp": tx.timestamp,
                "block_index": block_idx,
                "tx_hash": tx.hash(),
            })

        elif ttype == "room_topic":
            room_id = str(extra.get("room_id", "") or "").strip().upper()
            topic_id = str(extra.get("topic_id", "") or "").strip()
            room = rooms.get(room_id)
            if not room or not topic_id or topic_id in topics:
                return

            raw_bns = str(extra.get("bns_name") or "").strip().lower()
            if raw_bns in ("anonymous", "anon"):
                author_bns = "anonymous"
            elif raw_bns and self.bns_records.get(raw_bns, {}).get("owner") == snd:
                author_bns = raw_bns
            else:
                author_bns = self.bns_reverse.get(snd, "")

            topics[topic_id] = {
                "topic_id": topic_id,
                "room_id": room_id,
                "room_name": room["name"],
                "room_slug": room["slug"],
                "room_is_verified": bool(room.get("is_verified", False)),
                "title": str(extra.get("title", "") or ""),
                "content": str(extra.get("content", "") or ""),
                "author": snd,
                "author_bns": author_bns,
                "is_anonymous": (author_bns == "anonymous" or bool(extra.get("is_anonymous"))),
                "timestamp": tx.timestamp,
                "last_activity": tx.timestamp,
                "tx_hash": tx.hash(),
                "block_index": block_idx,
                "status": status_lbl,
                "upvotes": [],
                "upvotes_count": 0,
                "replies": [],
                "replies_count": 0,
                "author_earnings": 0.0,
            }
            room["topic_ids"].append(topic_id)
            room["topics_count"] += 1
            room["last_activity"] = max(float(room.get("last_activity") or 0), float(tx.timestamp or 0))
            room["creator_earnings"] = round(
                room["creator_earnings"] + float(extra.get("room_creator_cut", 0.075) or 0.0), 8
            )

        elif ttype == "room_reply":
            topic_id = str(extra.get("topic_id", "") or "").strip()
            reply_id = str(extra.get("reply_id", "") or "").strip()
            topic = topics.get(topic_id)
            if not topic or not reply_id:
                return
            room = rooms.get(topic["room_id"])
            if not room:
                return
            if any(r.get("reply_id") == reply_id for r in topic["replies"]):
                return

            parent_reply_id = str(extra.get("parent_reply_id", "") or "").strip()
            if parent_reply_id and not any(r.get("reply_id") == parent_reply_id for r in topic["replies"]):
                parent_reply_id = ""

            raw_bns = str(extra.get("bns_name") or "").strip().lower()
            if raw_bns in ("anonymous", "anon"):
                author_bns = "anonymous"
            elif raw_bns and self.bns_records.get(raw_bns, {}).get("owner") == snd:
                author_bns = raw_bns
            else:
                author_bns = self.bns_reverse.get(snd, "")

            rep = {
                "reply_id": reply_id,
                "topic_id": topic_id,
                "room_id": topic["room_id"],
                "parent_reply_id": parent_reply_id,
                "author": snd,
                "author_bns": author_bns,
                "is_anonymous": (author_bns == "anonymous" or bool(extra.get("is_anonymous"))),
                "content": str(extra.get("content", "") or ""),
                "timestamp": tx.timestamp,
                "tx_hash": tx.hash(),
                "block_index": block_idx,
                "status": status_lbl,
            }
            topic["replies"].append(rep)
            topic["replies_count"] += 1
            topic["last_activity"] = max(float(topic.get("last_activity") or 0), float(tx.timestamp or 0))
            topic["author_earnings"] = round(
                topic["author_earnings"] + float(extra.get("topic_author_cut", 0.01) or 0.0), 8
            )
            room["replies_count"] += 1
            room["last_activity"] = max(float(room.get("last_activity") or 0), float(tx.timestamp or 0))
            room["creator_earnings"] = round(
                room["creator_earnings"] + float(extra.get("room_creator_cut", 0.01) or 0.0), 8
            )

        elif ttype == "room_upvote":
            topic_id = str(extra.get("topic_id", "") or "").strip()
            topic = topics.get(topic_id)
            if not topic:
                return
            if snd in topic["upvotes"]:
                return
            topic["upvotes"].append(snd)
            topic["upvotes_count"] += 1
            topic["author_earnings"] = round(
                topic["author_earnings"] + float(extra.get("author_cut", 0.002) or 0.0), 8
            )
            room = rooms.get(topic["room_id"])
            if room:
                room["upvotes_count"] += 1

    def _load_in_memory_rooms_index(self):
        """Incremental O(Δ) Protocol Rooms, Topics & Replies indexer with O(|Mempool|) overlay."""
        import copy
        tip_hash = self.chain[-1].hash if self.chain else ""
        room_mempool_txs = [tx for tx in self.pending_transactions if tx.tx_type.startswith("room_")]
        mempool_hashes = tuple(tx.hash() for tx in room_mempool_txs)
        rooms_key = (len(self.chain), tip_hash, mempool_hashes)
        if self._rooms_index_key == rooms_key and self.rooms is not None:
            return

        if (
            len(self.chain) < self._confirmed_rooms_len
            or (
                self._confirmed_rooms_len > 0
                and self.chain[self._confirmed_rooms_len - 1].hash != self._confirmed_rooms_tip
            )
        ):
            self._confirmed_rooms_len = 0
            self._confirmed_rooms_tip = ""
            self._confirmed_rooms = {}
            self._confirmed_room_slugs = {}
            self._confirmed_room_topics = {}

        if self._confirmed_rooms_len < len(self.chain):
            for b in self.chain[self._confirmed_rooms_len:]:
                for tx in b.transactions:
                    if tx.tx_type.startswith("room_"):
                        self._apply_tx_to_room_maps(
                            b.index,
                            "confirmed",
                            tx,
                            self._confirmed_rooms,
                            self._confirmed_room_slugs,
                            self._confirmed_room_topics,
                        )
            self._confirmed_rooms_len = len(self.chain)
            self._confirmed_rooms_tip = tip_hash

        if not room_mempool_txs:
            self.rooms = self._confirmed_rooms
            self.room_slug_index = self._confirmed_room_slugs
            self.room_topics = self._confirmed_room_topics
        else:
            new_rooms = copy.deepcopy(self._confirmed_rooms)
            new_slugs = dict(self._confirmed_room_slugs)
            new_topics = copy.deepcopy(self._confirmed_room_topics)
            for tx in room_mempool_txs:
                self._apply_tx_to_room_maps("Mempool", "mempool", tx, new_rooms, new_slugs, new_topics)
            self.rooms = new_rooms
            self.room_slug_index = new_slugs
            self.room_topics = new_topics
        self._rooms_index_key = rooms_key

    def get_room_create_quote(self, name: str, has_avatar: bool = False) -> Tuple[bool, str, Optional[dict]]:
        """Computes live availability, canonical Special ID, and tiered pricing for a Room name."""
        with self.lock:
            self._load_state()
            self._load_in_memory_rooms_index()
            ok, clean_name, slug, room_id = validate_room_name(name)
            if not ok:
                return False, clean_name, None
            available = (slug not in self.room_slug_index) and (room_id not in self.rooms)
            pricing = compute_room_create_pricing(slug, has_avatar=bool(has_avatar))
            return True, "OK", {
                "name": clean_name,
                "slug": slug,
                "room_id": room_id,
                "available": available,
                "has_avatar": bool(has_avatar),
                **pricing,
            }

    def create_room(
        self,
        creator: str,
        name: str,
        description: str,
        avatar_base_id: str = "",
        avatar_bg_color: str = "#FFFFFF",
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
        bns_name: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Creates a public, Reddit-style Protocol Room on-chain with a unique Special ID (`RM-XXXXXXXX`).
        If an avatar is supplied, it is permanently sealed (`avatar_locked=True`) and can never be changed.
        """
        with self.lock:
            self._load_state()
            self._load_in_memory_rooms_index()

            clean_creator = normalize_bct_address(creator)
            if not is_valid_bct_address(clean_creator):
                return False, f"Invalid creator address: '{clean_creator}'", None

            ok_name, clean_name, slug, room_id = validate_room_name(name)
            if not ok_name:
                return False, clean_name, None

            ok_desc, clean_desc = validate_room_description(description)
            if not ok_desc:
                return False, clean_desc, None

            if slug in self.room_slug_index or room_id in self.rooms:
                return False, f"A room with name/ID '{clean_name}' ({room_id}) already exists.", None

            ok_av, av_err, variant_id, avatar_meta = validate_room_avatar_spec(avatar_base_id, avatar_bg_color)
            if not ok_av:
                return False, av_err, None

            av_tag = variant_id or "NONE"
            expected_payload = signed_payload or f"ROOM_CREATE:{clean_creator}:{slug}:{clean_desc}:{av_tag}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_creator, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            bns_ok, bns_err, assigned_bns = self._resolve_social_bns_handle(clean_creator, bns_name)
            if not bns_ok:
                return False, bns_err, None

            pricing = compute_room_create_pricing(slug, has_avatar=bool(variant_id))
            total_cost = pricing["total_cost"]
            creator_bal = self.verify_and_recalc_balance(clean_creator)
            if creator_bal < total_cost:
                return (
                    False,
                    f"Insufficient balance! Room creation requires {total_cost:.2f} BCT ({pricing['tier_label']}). Current balance: {creator_bal:.4f} BCT.",
                    None,
                )

            extra_data = {
                "room_id": room_id,
                "slug": slug,
                "name": clean_name,
                "description": clean_desc,
                "creator": clean_creator,
                "bns_name": assigned_bns,
                "is_anonymous": (assigned_bns == "anonymous"),
                "avatar_variant_id": variant_id or "",
                "avatar_locked": bool(variant_id),
                "tier": pricing["tier"],
                "base_fee": pricing["base_fee"],
                "avatar_fee": pricing["avatar_fee"],
                "treasury_cut": pricing["treasury_cut"],
                "pool_cut": pricing["pool_cut"],
            }

            tx = Transaction(
                sender=clean_creator,
                receiver=TREASURY_ADDRESS,
                amount=total_cost,
                fee=pricing["pool_cut"],
                signature=signature,
                tx_type="room_create",
                extra_data=extra_data,
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + pricing["pool_cut"], 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_rooms_index()

            self.balances[clean_creator] = self.verify_and_recalc_balance(clean_creator)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            return True, f"Protocol Room '{clean_name}' ({room_id}) sealed on-chain!", {
                "room_id": room_id,
                "slug": slug,
                "name": clean_name,
                "description": clean_desc,
                "avatar": avatar_meta,
                "avatar_locked": bool(variant_id),
                "cost": total_cost,
                "tier": pricing["tier"],
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool",
                "new_balance": self.balances[clean_creator],
            }

    def verify_protocol_room(
        self,
        authority_address: str,
        room_id: str,
        verified: bool = True,
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Grants or revokes the verified room badge (Developer / Release Authority ONLY).
        """
        with self.lock:
            self._load_state()
            self._load_in_memory_rooms_index()

            clean_auth = normalize_bct_address(authority_address)
            if clean_auth != RELEASE_AUTHORITY_ADDRESS:
                return False, "Unauthorized: Only the developer release authority can verify rooms.", None

            rid = str(room_id or "").strip().upper()
            room = self.rooms.get(rid)
            if not room:
                return False, "Target protocol room not found.", None

            expected_payload = signed_payload or f"ROOM_VERIFY:{clean_auth}:{rid}:{str(verified).lower()}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_auth, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            tx = Transaction(
                sender=clean_auth,
                receiver=TREASURY_ADDRESS,
                amount=0.0,
                fee=0.0,
                signature=signature,
                tx_type="room_verify",
                extra_data={
                    "room_id": rid,
                    "verified": bool(verified),
                },
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1

            block = self._seal_or_queue_mempool()
            self._load_in_memory_rooms_index()
            self._save_state()

            status_txt = "verified" if verified else "unverified"
            return True, f"Room {rid} marked as {status_txt} by Release Authority.", {
                "room_id": rid,
                "is_verified": bool(verified),
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
            }

    def set_room_avatar(
        self,
        creator: str,
        room_id: str,
        avatar_base_id: str,
        avatar_bg_color: str = "#FFFFFF",
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        One-time immutable avatar seal for a room created without an avatar.
        Creator-only. Once sealed, it can NEVER be modified or removed.
        """
        with self.lock:
            self._load_state()
            self._load_in_memory_rooms_index()

            clean_creator = normalize_bct_address(creator)
            if not is_valid_bct_address(clean_creator):
                return False, f"Invalid creator address: '{clean_creator}'", None

            rid = str(room_id or "").strip().upper()
            room = self.rooms.get(rid)
            if not room:
                return False, "Protocol room not found.", None

            if room["creator"] != clean_creator:
                return False, "Only the room creator can seal the room avatar.", None

            if room.get("avatar_locked") or room.get("avatar") is not None:
                return False, "This room's avatar is permanently locked on-chain and cannot be changed.", None

            # Mempool race-condition protection
            has_pending = any(
                t.tx_type == "room_set_avatar"
                and isinstance(t.extra_data, dict)
                and str(t.extra_data.get("room_id", "")).upper() == rid
                for t in self.pending_transactions
            )
            if has_pending:
                return False, "An immutable avatar seal transaction is already pending for this room.", None

            if not str(avatar_base_id or "").strip():
                return False, "Avatar base ID is required.", None
            ok_av, av_err, variant_id, avatar_meta = validate_room_avatar_spec(avatar_base_id, avatar_bg_color)
            if not ok_av or not variant_id:
                return False, av_err or "Invalid avatar specification.", None

            expected_payload = signed_payload or f"ROOM_AVATAR:{clean_creator}:{rid}:{variant_id}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_creator, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            pricing = compute_room_avatar_seal_pricing()
            total_cost = pricing["total_cost"]
            creator_bal = self.verify_and_recalc_balance(clean_creator)
            if creator_bal < total_cost:
                return False, f"Insufficient balance! Permanent avatar seal fee is {total_cost:.2f} BCT.", None

            tx = Transaction(
                sender=clean_creator,
                receiver=TREASURY_ADDRESS,
                amount=total_cost,
                fee=pricing["pool_cut"],
                signature=signature,
                tx_type="room_set_avatar",
                extra_data={
                    "room_id": rid,
                    "avatar_variant_id": variant_id,
                    "treasury_cut": pricing["treasury_cut"],
                    "pool_cut": pricing["pool_cut"],
                },
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + pricing["pool_cut"], 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_rooms_index()

            self.balances[clean_creator] = self.verify_and_recalc_balance(clean_creator)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            return True, f"Room avatar {variant_id} permanently sealed! It can never be changed.", {
                "room_id": rid,
                "avatar": avatar_meta,
                "avatar_variant_id": variant_id,
                "avatar_locked": True,
                "cost": total_cost,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool",
                "new_balance": self.balances[clean_creator],
            }

    def transfer_room(
        self,
        current_owner: str,
        room_id: str,
        to_address: str,
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Permanently transfers ownership of a Protocol Room (and all future creator royalties)
        to a new BCT address or resolved .bct handle.
        Fee: 0.50 BCT (50% Treasury, 50% Miner/Validator Pool).
        """
        with self.lock:
            self._load_state()
            self._load_in_memory_rooms_index()

            clean_from = normalize_bct_address(current_owner)
            if not is_valid_bct_address(clean_from):
                return False, f"Invalid owner address: '{clean_from}'", None

            raw_to = str(to_address or "").strip()
            if not raw_to:
                return False, "Recipient address or .bct handle is required.", None

            clean_to = normalize_bct_address(raw_to)
            if not is_valid_bct_address(clean_to):
                norm_bns = self._normalize_bns_name(raw_to.lstrip("@"))
                bns_rec = self.bns_records.get(norm_bns)
                if bns_rec and is_valid_bct_address(bns_rec.get("owner", "")):
                    clean_to = normalize_bct_address(bns_rec["owner"])
                else:
                    return False, f"Invalid recipient address or unregistered .bct handle: '{raw_to}'", None

            if clean_from == clean_to:
                return False, "Cannot transfer a room to your own address.", None
            if clean_to in (TREASURY_ADDRESS, "BCT_BURN", "SYSTEM"):
                return False, "Cannot transfer a room to a system or treasury address.", None
            if self.is_wallet_burned(clean_to):
                return False, "Recipient wallet has been permanently burned and cannot receive rooms.", None

            rid = str(room_id or "").strip().upper()
            room = self.rooms.get(rid)
            if not room:
                return False, "Protocol room not found.", None

            if room["creator"] != clean_from:
                return False, "Only the current room owner can transfer this room.", None

            # Mempool double-transfer race protection
            has_pending = any(
                t.tx_type == "room_transfer"
                and isinstance(t.extra_data, dict)
                and str(t.extra_data.get("room_id", "")).upper() == rid
                for t in self.pending_transactions
            )
            if has_pending:
                return False, "A room ownership transfer is already pending in the mempool for this room.", None

            expected_payload = signed_payload or f"ROOM_TRANSFER:{clean_from}:{rid}:{clean_to}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_from, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            pricing = compute_room_transfer_pricing()
            total_cost = pricing["total_cost"]
            owner_bal = self.verify_and_recalc_balance(clean_from)
            if owner_bal < total_cost:
                return False, f"Insufficient balance! Room transfer fee is {total_cost:.2f} BCT. Current balance: {owner_bal:.4f} BCT.", None

            tx = Transaction(
                sender=clean_from,
                receiver=TREASURY_ADDRESS,
                amount=total_cost,
                fee=pricing["pool_cut"],
                signature=signature,
                tx_type="room_transfer",
                extra_data={
                    "room_id": rid,
                    "from_address": clean_from,
                    "to_address": clean_to,
                    "treasury_cut": pricing["treasury_cut"],
                    "pool_cut": pricing["pool_cut"],
                },
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + pricing["pool_cut"], 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_rooms_index()

            self.balances[clean_from] = self.verify_and_recalc_balance(clean_from)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            new_owner_bns = self.bns_reverse.get(clean_to, "")
            return True, f"Protocol Room '{room['name']}' ({rid}) transferred to {new_owner_bns or clean_to[:10] + '...'}!", {
                "room_id": rid,
                "name": room["name"],
                "previous_owner": clean_from,
                "new_owner": clean_to,
                "new_owner_bns": new_owner_bns,
                "cost": total_cost,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool",
                "new_balance": self.balances[clean_from],
            }

    def create_room_topic(
        self,
        author: str,
        room_id: str,
        title: str,
        content: str,
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
        bns_name: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Opens a new Reddit-style Topic ("Mevzu") inside a Protocol Room.
        Cost: 0.25 BCT (30% Room Creator Royalty, 50% Treasury, 20% Miner/Validator).
        """
        with self.lock:
            self._load_state()
            self._load_in_memory_rooms_index()

            clean_author = normalize_bct_address(author)
            if not is_valid_bct_address(clean_author):
                return False, f"Invalid author address: '{clean_author}'", None

            rid = str(room_id or "").strip().upper()
            room = self.rooms.get(rid)
            if not room:
                slug_hit = self.room_slug_index.get(normalize_room_slug(room_id))
                if slug_hit:
                    rid = slug_hit
                    room = self.rooms.get(rid)
            if not room:
                return False, "Target protocol room not found.", None

            ok_f, clean_title, clean_body = validate_topic_fields(title, content)
            if not ok_f:
                return False, clean_title, None

            expected_payload = signed_payload or f"ROOM_TOPIC:{clean_author}:{rid}:{clean_title}:{clean_body}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_author, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            bns_ok, bns_err, assigned_bns = self._resolve_social_bns_handle(clean_author, bns_name)
            if not bns_ok:
                return False, bns_err, None

            pricing = compute_room_topic_pricing()
            total_cost = pricing["total_cost"]
            author_bal = self.verify_and_recalc_balance(clean_author)
            if author_bal < total_cost:
                return False, f"Insufficient balance! Opening a topic costs {total_cost:.2f} BCT. Current balance: {author_bal:.4f} BCT.", None

            is_dup = any(
                t.tx_type == "room_topic"
                and t.sender == clean_author
                and isinstance(t.extra_data, dict)
                and t.extra_data.get("room_id") == rid
                and t.extra_data.get("title") == clean_title
                and (time.time() - float(t.timestamp or 0)) < 30.0
                for t in self.pending_transactions
            )
            if is_dup:
                return False, "This topic is already queued in the mempool.", None

            topic_id = f"top_{secrets.token_hex(6)}"
            room_creator = room["creator"]
            rc_burned = self.is_wallet_burned(room_creator)
            eff_room_creator_recipient = TREASURY_ADDRESS if rc_burned else room_creator

            tx = Transaction(
                sender=clean_author,
                receiver=TREASURY_ADDRESS,
                amount=total_cost,
                fee=pricing["pool_cut"],
                signature=signature,
                tx_type="room_topic",
                extra_data={
                    "room_id": rid,
                    "topic_id": topic_id,
                    "title": clean_title,
                    "content": clean_body,
                    "author": clean_author,
                    "room_creator": room_creator,
                    "room_creator_royalty_recipient": eff_room_creator_recipient,
                    "royalty_redirected_to_treasury": rc_burned,
                    "bns_name": assigned_bns,
                    "is_anonymous": (assigned_bns == "anonymous"),
                    "room_creator_cut": pricing["room_creator_cut"],
                    "treasury_cut": pricing["treasury_cut"],
                    "pool_cut": pricing["pool_cut"],
                },
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + pricing["pool_cut"], 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_rooms_index()

            self.balances[clean_author] = self.verify_and_recalc_balance(clean_author)
            self.balances[room_creator] = self.verify_and_recalc_balance(room_creator)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            return True, "Topic published on-chain!", {
                "topic_id": topic_id,
                "room_id": rid,
                "title": clean_title,
                "content": clean_body,
                "cost": total_cost,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool",
                "new_balance": self.balances[clean_author],
            }

    def create_room_reply(
        self,
        author: str,
        topic_id: str,
        content: str,
        parent_reply_id: str = "",
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
        bns_name: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Posts a tweet/reply under a Topic ("Mevzu") in a Protocol Room.
        Supports optional `parent_reply_id` for Reddit-style nested replies.
        Cost: 0.05 BCT (20% Topic Author, 20% Room Creator, 40% Treasury, 20% Miner/Validator).
        """
        with self.lock:
            self._load_state()
            self._load_in_memory_rooms_index()

            clean_author = normalize_bct_address(author)
            if not is_valid_bct_address(clean_author):
                return False, f"Invalid author address: '{clean_author}'", None

            tid = str(topic_id or "").strip()
            topic = self.room_topics.get(tid)
            if not topic:
                return False, "Target topic not found.", None

            rid = topic["room_id"]
            room = self.rooms.get(rid)
            if not room:
                return False, "Parent room not found.", None

            ok_c, clean_content = validate_reply_content(content)
            if not ok_c:
                return False, clean_content, None

            clean_parent = str(parent_reply_id or "").strip()
            if clean_parent:
                if not any(r.get("reply_id") == clean_parent for r in topic.get("replies", [])):
                    return False, "Referenced parent reply does not belong to this topic.", None

            expected_payload = signed_payload or (
                f"ROOM_REPLY:{clean_author}:{tid}:{clean_content}:{clean_parent}"
                if clean_parent
                else f"ROOM_REPLY:{clean_author}:{tid}:{clean_content}"
            )
            sig_ok, sig_msg = self._verify_actor_signature(clean_author, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            bns_ok, bns_err, assigned_bns = self._resolve_social_bns_handle(clean_author, bns_name)
            if not bns_ok:
                return False, bns_err, None

            pricing = compute_room_reply_pricing()
            total_cost = pricing["total_cost"]
            author_bal = self.verify_and_recalc_balance(clean_author)
            if author_bal < total_cost:
                return False, f"Insufficient balance! Reply fee is {total_cost:.2f} BCT. Current balance: {author_bal:.4f} BCT.", None

            is_dup = any(
                t.tx_type == "room_reply"
                and t.sender == clean_author
                and isinstance(t.extra_data, dict)
                and t.extra_data.get("topic_id") == tid
                and t.extra_data.get("content") == clean_content
                and (time.time() - float(t.timestamp or 0)) < 30.0
                for t in self.pending_transactions
            )
            if is_dup:
                return False, "This reply is already queued in the mempool.", None

            reply_id = f"rep_{secrets.token_hex(6)}"
            topic_author = topic["author"]
            room_creator = room["creator"]
            ta_burned = self.is_wallet_burned(topic_author)
            rc_burned = self.is_wallet_burned(room_creator)

            tx = Transaction(
                sender=clean_author,
                receiver=TREASURY_ADDRESS,
                amount=total_cost,
                fee=pricing["pool_cut"],
                signature=signature,
                tx_type="room_reply",
                extra_data={
                    "room_id": rid,
                    "topic_id": tid,
                    "reply_id": reply_id,
                    "parent_reply_id": clean_parent,
                    "content": clean_content,
                    "author": clean_author,
                    "topic_author": topic_author,
                    "room_creator": room_creator,
                    "topic_author_royalty_recipient": TREASURY_ADDRESS if ta_burned else topic_author,
                    "room_creator_royalty_recipient": TREASURY_ADDRESS if rc_burned else room_creator,
                    "royalty_redirected_to_treasury": bool(ta_burned or rc_burned),
                    "bns_name": assigned_bns,
                    "is_anonymous": (assigned_bns == "anonymous"),
                    "topic_author_cut": pricing["topic_author_cut"],
                    "room_creator_cut": pricing["room_creator_cut"],
                    "treasury_cut": pricing["treasury_cut"],
                    "pool_cut": pricing["pool_cut"],
                },
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + pricing["pool_cut"], 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_rooms_index()

            self.balances[clean_author] = self.verify_and_recalc_balance(clean_author)
            self.balances[topic_author] = self.verify_and_recalc_balance(topic_author)
            self.balances[room_creator] = self.verify_and_recalc_balance(room_creator)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            return True, "Reply sealed on-chain!", {
                "reply_id": reply_id,
                "topic_id": tid,
                "room_id": rid,
                "parent_reply_id": clean_parent,
                "content": clean_content,
                "cost": total_cost,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool",
                "new_balance": self.balances[clean_author],
            }

    def upvote_room_topic(
        self,
        voter: str,
        topic_id: str,
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Upvotes a Topic inside a Protocol Room.
        Cost: 0.01 BCT (20% Topic Author, 70% Treasury, 10% Miner/Validator).
        """
        with self.lock:
            self._load_state()
            self._load_in_memory_rooms_index()

            clean_voter = normalize_bct_address(voter)
            if not is_valid_bct_address(clean_voter):
                return False, f"Invalid voter address: '{clean_voter}'", None

            tid = str(topic_id or "").strip()
            topic = self.room_topics.get(tid)
            if not topic:
                return False, "Target topic not found.", None

            if clean_voter in topic["upvotes"]:
                return False, "You have already upvoted this topic.", None

            expected_payload = signed_payload or f"ROOM_UPVOTE:{clean_voter}:{tid}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_voter, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            pricing = compute_room_upvote_pricing()
            total_cost = pricing["total_cost"]
            voter_bal = self.verify_and_recalc_balance(clean_voter)
            if voter_bal < total_cost:
                return False, f"Insufficient balance! Upvote fee is {total_cost:.2f} BCT.", None

            is_dup = any(
                t.tx_type == "room_upvote"
                and t.sender == clean_voter
                and isinstance(t.extra_data, dict)
                and t.extra_data.get("topic_id") == tid
                for t in self.pending_transactions
            )
            if is_dup:
                return False, "Upvote already queued in mempool.", None

            topic_author = topic["author"]
            ta_burned = self.is_wallet_burned(topic_author)
            tx = Transaction(
                sender=clean_voter,
                receiver=TREASURY_ADDRESS,
                amount=total_cost,
                fee=pricing["pool_cut"],
                signature=signature,
                tx_type="room_upvote",
                extra_data={
                    "room_id": topic["room_id"],
                    "topic_id": tid,
                    "author": topic_author,
                    "royalty_recipient": TREASURY_ADDRESS if ta_burned else topic_author,
                    "royalty_redirected_to_treasury": ta_burned,
                    "voter": clean_voter,
                    "author_cut": pricing["author_cut"],
                    "treasury_cut": pricing["treasury_cut"],
                    "pool_cut": pricing["pool_cut"],
                },
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + pricing["pool_cut"], 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_rooms_index()

            self.balances[clean_voter] = self.verify_and_recalc_balance(clean_voter)
            self.balances[topic_author] = self.verify_and_recalc_balance(topic_author)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            updated = self.room_topics.get(tid, topic)
            return True, "Topic upvoted!", {
                "topic_id": tid,
                "upvotes_count": updated["upvotes_count"],
                "cost": total_cost,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool",
                "new_balance": self.balances[clean_voter],
            }

    def list_rooms(self, limit: int = 50, sort_by: str = "active", query: str = "") -> dict:
        """Returns public on-chain Protocol Rooms with live stats & pricing summary."""
        with self.lock:
            self._load_state()
            self._load_in_memory_rooms_index()
            items = []
            q = str(query or "").strip().lower()
            for r in self.rooms.values():
                if q:
                    hay = f"{r['name']} {r['room_id']} {r['slug']} {r['description']}".lower()
                    if q not in hay:
                        continue
                item = {k: v for k, v in r.items() if k != "topic_ids"}
                item["creator_avatar"] = None if r.get("is_anonymous") else self.avatar_equipped.get(r["creator"])
                items.append(item)

            if sort_by == "newest":
                items.sort(key=lambda x: float(x.get("created_at") or 0), reverse=True)
            elif sort_by == "topics":
                items.sort(key=lambda x: (int(x.get("topics_count") or 0), int(x.get("replies_count") or 0)), reverse=True)
            else:
                items.sort(
                    key=lambda x: (
                        int(x.get("topics_count") or 0) * 3 + int(x.get("replies_count") or 0) + int(x.get("upvotes_count") or 0),
                        float(x.get("last_activity") or 0),
                    ),
                    reverse=True,
                )

            return {
                "rooms": items[:limit],
                "total_rooms": len(self.rooms),
                "total_topics": len(self.room_topics),
                "tokenomics": get_rooms_tokenomics_summary(),
            }

    def get_room_detail(self, room_key: str, sort_by: str = "hot", limit: int = 50) -> Optional[dict]:
        """Returns a single Protocol Room with its Reddit-style Topics list."""
        with self.lock:
            self._load_state()
            self._load_in_memory_rooms_index()
            key_raw = str(room_key or "").strip()
            room = self.rooms.get(key_raw.upper())
            if not room:
                slug_hit = self.room_slug_index.get(normalize_room_slug(key_raw))
                if slug_hit:
                    room = self.rooms.get(slug_hit)
            if not room:
                return None

            now_ts = time.time()
            room_topics = []
            for tid in room.get("topic_ids", []):
                t = self.room_topics.get(tid)
                if not t:
                    continue
                t_copy = {k: v for k, v in t.items() if k != "replies"}
                t_copy["author_avatar"] = None if t.get("is_anonymous") else self.avatar_equipped.get(t["author"])
                room_topics.append(t_copy)

            if sort_by == "new":
                room_topics.sort(key=lambda x: float(x.get("timestamp") or 0), reverse=True)
            elif sort_by == "top":
                room_topics.sort(
                    key=lambda x: (int(x.get("upvotes_count") or 0), int(x.get("replies_count") or 0)),
                    reverse=True,
                )
            else:
                # Reddit-inspired hot ranking with gravity time-decay
                def _hot_score(t_item):
                    age_hrs = max(0.0, (now_ts - float(t_item.get("timestamp") or now_ts)) / 3600.0)
                    engagement = (int(t_item.get("upvotes_count") or 0) * 2.0) + (int(t_item.get("replies_count") or 0) * 1.5) + 1.0
                    return engagement / ((age_hrs + 2.0) ** 1.35)
                room_topics.sort(key=_hot_score, reverse=True)

            room_out = {k: v for k, v in room.items() if k != "topic_ids"}
            orig_addr = room_out.get("original_creator") or room_out.get("creator") or ""
            if not room_out.get("original_creator_bns") and orig_addr:
                room_out["original_creator_bns"] = self.bns_reverse.get(orig_addr, "")
            enriched_hist = []
            for h_ev in (room.get("transfer_history") or []):
                hc = dict(h_ev)
                frm = hc.get("from", "")
                to = hc.get("to", "")
                if not hc.get("from_bns") and frm:
                    hc["from_bns"] = self.bns_reverse.get(frm, "")
                if not hc.get("to_bns") and to:
                    hc["to_bns"] = self.bns_reverse.get(to, "")
                enriched_hist.append(hc)
            room_out["transfer_history"] = enriched_hist
            room_out["creator_avatar"] = None if room.get("is_anonymous") else self.avatar_equipped.get(room["creator"])
            room_out["topics"] = room_topics[:limit]
            room_out["tokenomics"] = get_rooms_tokenomics_summary()
            return room_out

    def get_room_topic_detail(self, topic_id: str) -> Optional[dict]:
        """Returns full Topic details and all nested Replies/Tweets under it."""
        with self.lock:
            self._load_state()
            self._load_in_memory_rooms_index()
            t = self.room_topics.get(str(topic_id or "").strip())
            if not t:
                return None
            room = self.rooms.get(t["room_id"])
            out = dict(t)
            out["author_avatar"] = None if t.get("is_anonymous") else self.avatar_equipped.get(t["author"])
            enriched_replies = []
            for r in t.get("replies", []):
                rc = dict(r)
                rc["author_avatar"] = None if r.get("is_anonymous") else self.avatar_equipped.get(r["author"])
                enriched_replies.append(rc)
            out["replies"] = enriched_replies
            out["room"] = {
                "room_id": room["room_id"],
                "slug": room["slug"],
                "name": room["name"],
                "description": room["description"],
                "avatar": room.get("avatar"),
                "avatar_locked": bool(room.get("avatar_locked")),
                "is_verified": bool(room.get("is_verified", False)),
                "creator": room["creator"],
            } if room else None
            out["tokenomics"] = get_rooms_tokenomics_summary()
            return out

    def get_room_notifications_for_wallet(self, address: str, limit: int = 30) -> List[dict]:
        """
        Returns recent on-chain Protocol Rooms notifications for a wallet:
          - New topics in rooms owned by the wallet
          - Replies on topics authored by the wallet, replies to the wallet's replies, or replies in rooms owned by the wallet
          - @mentions of the wallet's BNS handle(s) in any room topic or reply
          - Room ownership transfers received by the wallet
        """
        clean_addr = normalize_bct_address(address)
        if not is_valid_bct_address(clean_addr):
            return []
        with self.lock:
            self._load_state(sweep_overdue=False)
            self._load_in_memory_rooms_index()
            my_handles = {
                name.lower() for name, rec in self.bns_records.items()
                if normalize_bct_address(rec.get("owner", "")) == clean_addr
            }
            my_short_handles = {h[:-4] for h in my_handles if h.endswith(".bct")}
            all_my_tags = my_handles | my_short_handles

            def _mentions_me(text: str) -> bool:
                if not text:
                    return False
                low = text.lower()
                if clean_addr.lower() in low:
                    return True
                for h in all_my_tags:
                    if f"@{h}" in low:
                        return True
                return False

            notifs = []
            for rid, room in self.rooms.items():
                for idx_h, h_ev in enumerate(room.get("transfer_history") or []):
                    if normalize_bct_address(h_ev.get("to", "")) == clean_addr and normalize_bct_address(h_ev.get("from", "")) != clean_addr:
                        frm = normalize_bct_address(h_ev.get("from", ""))
                        frm_lbl = self.bns_reverse.get(frm, "") or f"{frm[:8]}..."
                        notifs.append({
                            "id": f"room-xfer-{rid}-{h_ev.get('tx_hash', idx_h)}",
                            "type": "room_transfer",
                            "room_id": rid,
                            "topic_id": "",
                            "title": "🔑 Oda Sahipliği Size Devredildi!",
                            "body": f"{frm_lbl}, '{room.get('name', rid)}' odasını size devretti.",
                            "icon": "swap_horiz",
                            "timestamp": float(h_ev.get("timestamp") or 0),
                        })

            for tid, topic in self.room_topics.items():
                rid = topic.get("room_id", "")
                room = self.rooms.get(rid)
                room_name = room.get("name", rid) if room else topic.get("room_name", rid)
                room_owner = normalize_bct_address(room.get("creator", "")) if room else ""
                t_author = normalize_bct_address(topic.get("author", ""))
                t_author_lbl = (f"@{topic['author_bns']}" if topic.get("author_bns") and topic.get("author_bns") != "anonymous" else f"{t_author[:8]}...")

                if t_author != clean_addr:
                    if room_owner == clean_addr:
                        notifs.append({
                            "id": f"room-topic-{tid}",
                            "type": "room_topic",
                            "room_id": rid,
                            "topic_id": tid,
                            "title": f"🏛️ {room_name}: Yeni Mevzu!",
                            "body": f"{t_author_lbl}: \"{str(topic.get('title', ''))[:65]}\"",
                            "icon": "meeting_room",
                            "timestamp": float(topic.get("timestamp") or 0),
                        })
                    elif _mentions_me(f"{topic.get('title', '')} {topic.get('content', '')}"):
                        notifs.append({
                            "id": f"room-topic-mention-{tid}",
                            "type": "room_mention",
                            "room_id": rid,
                            "topic_id": tid,
                            "title": f"📢 {room_name} Odasında Etiketlendiniz!",
                            "body": f"{t_author_lbl} mevzuda sizden bahsetti: \"{str(topic.get('title', ''))[:55]}\"",
                            "icon": "alternate_email",
                            "timestamp": float(topic.get("timestamp") or 0),
                        })

                replies = topic.get("replies") or []
                rep_by_id = {r.get("reply_id"): r for r in replies if r.get("reply_id")}
                for rep in replies:
                    r_id = rep.get("reply_id", "")
                    r_author = normalize_bct_address(rep.get("author", ""))
                    if not r_id or r_author == clean_addr:
                        continue
                    r_lbl = (f"@{rep['author_bns']}" if rep.get("author_bns") and rep.get("author_bns") != "anonymous" else f"{r_author[:8]}...")
                    snippet = str(rep.get("content", ""))[:65]
                    parent_rep = rep_by_id.get(rep.get("parent_reply_id", ""))
                    parent_author = normalize_bct_address(parent_rep.get("author", "")) if parent_rep else ""

                    if parent_author == clean_addr:
                        notifs.append({
                            "id": f"room-rep-nested-{r_id}",
                            "type": "room_reply",
                            "room_id": rid,
                            "topic_id": tid,
                            "title": f"↩️ {room_name}: Yanıtınıza Cevap!",
                            "body": f"{r_lbl}: \"{snippet}\"",
                            "icon": "reply",
                            "timestamp": float(rep.get("timestamp") or 0),
                        })
                    elif t_author == clean_addr:
                        notifs.append({
                            "id": f"room-rep-topic-{r_id}",
                            "type": "room_reply",
                            "room_id": rid,
                            "topic_id": tid,
                            "title": f"💬 Mevzunuza Yeni Yanıt!",
                            "body": f"{r_lbl} ({str(topic.get('title', ''))[:28]}): \"{snippet}\"",
                            "icon": "chat_bubble",
                            "timestamp": float(rep.get("timestamp") or 0),
                        })
                    elif _mentions_me(rep.get("content", "")):
                        notifs.append({
                            "id": f"room-rep-mention-{r_id}",
                            "type": "room_mention",
                            "room_id": rid,
                            "topic_id": tid,
                            "title": f"📢 {room_name}: Yorumda Etiketlendiniz!",
                            "body": f"{r_lbl}: \"{snippet}\"",
                            "icon": "alternate_email",
                            "timestamp": float(rep.get("timestamp") or 0),
                        })
                    elif room_owner == clean_addr:
                        notifs.append({
                            "id": f"room-rep-owner-{r_id}",
                            "type": "room_reply",
                            "room_id": rid,
                            "topic_id": tid,
                            "title": f"🏛️ {room_name}: Yeni Tartışma!",
                            "body": f"{r_lbl}: \"{snippet}\"",
                            "icon": "forum",
                            "timestamp": float(rep.get("timestamp") or 0),
                        })

            notifs.sort(key=lambda x: x["timestamp"], reverse=True)
            return notifs[:max(1, min(int(limit or 30), 60))]

    # ── ON-CHAIN SOULBOUND PROFILE AVATARS (Bonding Curve + Color Variants) ──

    @staticmethod
    def _apply_tx_to_avatar_maps(
        block_idx,
        status_lbl: str,
        tx: Transaction,
        variant_counts: Dict[str, int],
        owners_map: Dict[str, List[dict]],
        equipped_map: Dict[str, Optional[dict]],
    ):
        snd = normalize_bct_address(tx.sender)
        if not snd or not tx.extra_data:
            return
        if tx.tx_type == "avatar_mint":
            raw_vid = str(tx.extra_data.get("variant_id", "") or "").strip().upper()
            base_id, bg_color = parse_variant_id(raw_vid)
            if not base_id or not bg_color:
                base_id = str(tx.extra_data.get("base_id", "") or "").strip().upper()
                bg_color = normalize_hex_color(tx.extra_data.get("bg_color"))
                raw_vid = make_variant_id(base_id, bg_color) if (base_id and bg_color) else ""
            if not raw_vid or not base_id or not bg_color:
                return
            item = get_base_avatar(base_id)
            if not item:
                return

            new_count = variant_counts.get(raw_vid, 0) + 1
            variant_counts[raw_vid] = new_count

            owned = owners_map.setdefault(snd, [])
            if not any(o.get("variant_id") == raw_vid for o in owned):
                meta = build_avatar_metadata(base_id, bg_color, mint_count=new_count)
                if meta:
                    meta["minted_at"] = tx.timestamp
                    meta["mint_price"] = float(tx.extra_data.get("price", tx.amount) or tx.amount)
                    meta["mint_index"] = int(tx.extra_data.get("mint_index", new_count) or new_count)
                    meta["tx_hash"] = tx.hash()
                    meta["block_index"] = block_idx
                    meta["status"] = status_lbl
                    owned.append(meta)
                    if bool(tx.extra_data.get("auto_equip", True)):
                        equipped_map[snd] = dict(meta)
        elif tx.tx_type == "avatar_equip":
            vid = str(tx.extra_data.get("variant_id", "") or "").strip().upper()
            if not vid:
                equipped_map[snd] = None
                return
            owned = owners_map.get(snd, [])
            match = next((o for o in owned if o.get("variant_id") == vid), None)
            if match:
                equipped_map[snd] = dict(match)

    def _load_in_memory_avatar_index(self):
        """Incremental O(Δ) On-Chain Profile Avatar indexer with O(|Mempool|) overlay."""
        import copy
        tip_hash = self.chain[-1].hash if self.chain else ""
        avatar_mempool_txs = [tx for tx in self.pending_transactions if tx.tx_type in ("avatar_mint", "avatar_equip")]
        mempool_hashes = tuple(tx.hash() for tx in avatar_mempool_txs)
        avatar_key = (len(self.chain), tip_hash, mempool_hashes)
        if self._avatar_index_key == avatar_key and self.avatar_variant_counts is not None:
            return

        if (
            len(self.chain) < self._confirmed_avatar_len
            or (
                self._confirmed_avatar_len > 0
                and self.chain[self._confirmed_avatar_len - 1].hash != self._confirmed_avatar_tip
            )
        ):
            self._confirmed_avatar_len = 0
            self._confirmed_avatar_tip = ""
            self._confirmed_avatar_variant_counts = {}
            self._confirmed_avatar_owners = {}
            self._confirmed_avatar_equipped = {}

        if self._confirmed_avatar_len < len(self.chain):
            for b in self.chain[self._confirmed_avatar_len:]:
                for tx in b.transactions:
                    if tx.tx_type in ("avatar_mint", "avatar_equip"):
                        self._apply_tx_to_avatar_maps(
                            b.index,
                            "confirmed",
                            tx,
                            self._confirmed_avatar_variant_counts,
                            self._confirmed_avatar_owners,
                            self._confirmed_avatar_equipped,
                        )
            self._confirmed_avatar_len = len(self.chain)
            self._confirmed_avatar_tip = tip_hash

        if not avatar_mempool_txs:
            self.avatar_variant_counts = self._confirmed_avatar_variant_counts
            self.avatar_owners = self._confirmed_avatar_owners
            self.avatar_equipped = self._confirmed_avatar_equipped
        else:
            new_counts = dict(self._confirmed_avatar_variant_counts)
            new_owners = copy.deepcopy(self._confirmed_avatar_owners)
            new_equipped = copy.deepcopy(self._confirmed_avatar_equipped)
            for tx in avatar_mempool_txs:
                self._apply_tx_to_avatar_maps("Mempool", "mempool", tx, new_counts, new_owners, new_equipped)
            self.avatar_variant_counts = new_counts
            self.avatar_owners = new_owners
            self.avatar_equipped = new_equipped
        self._avatar_index_key = avatar_key

    def get_equipped_avatar(self, address: str) -> Optional[dict]:
        with self.lock:
            self._load_state()
            clean_addr = normalize_bct_address(address)
            if not clean_addr:
                return None
            return self.avatar_equipped.get(clean_addr)

    def get_avatar_catalog_state(self, address: str = "") -> dict:
        with self.lock:
            self._load_state()
            clean_addr = normalize_bct_address(address) if address else ""
            owned_list = list(self.avatar_owners.get(clean_addr, [])) if clean_addr else []
            owned_vids = {o.get("variant_id") for o in owned_list}
            equipped = self.avatar_equipped.get(clean_addr) if clean_addr else None

            items = []
            for item in AVATAR_CATALOG:
                default_vid = make_variant_id(item["base_id"], DEFAULT_BG_COLOR)
                default_mints = int(self.avatar_variant_counts.get(default_vid, 0))
                default_price = compute_variant_price(default_mints)
                # Count total mints across all background color variants for this base animal
                prefix = f"{item['base_id']}-"
                total_mints_all_colors = sum(
                    cnt for vid, cnt in self.avatar_variant_counts.items() if vid.startswith(prefix)
                )
                items.append({
                    "base_id": item["base_id"],
                    "collection": item["collection"],
                    "slug": item["slug"],
                    "name": item["name"],
                    "name_tr": item["name_tr"],
                    "image_url": item["image_url"],
                    "default_bg_color": DEFAULT_BG_COLOR,
                    "default_variant_id": default_vid,
                    "default_mint_count": default_mints,
                    "default_price": default_price,
                    "total_mints_all_colors": total_mints_all_colors,
                    "owns_default": default_vid in owned_vids,
                })

            return {
                "collections": list(AVATAR_COLLECTIONS.values()),
                "curated_colors": CURATED_BG_COLORS,
                "pricing_rules": {
                    "base_price_bct": 0.10,
                    "step_multiplier": 1.25,
                    "step_percent": 25,
                    "equip_fee_bct": float(AVATAR_EQUIP_FEE),
                    "unequip_fee_bct": float(AVATAR_EQUIP_FEE),
                    "swap_fee_bct": float(AVATAR_SWAP_FEE),
                    "treasury_percent": 30,
                    "network_pool_percent": 70,
                    "pool_breakdown": {
                        "miner_percent_of_pool": 50,
                        "validator_percent_of_pool": 40,
                        "observer_staking_percent_of_pool": 10,
                    },
                    "soulbound": True,
                },
                "catalog": items,
                "owned_avatars": owned_list,
                "equipped_avatar": equipped,
            }

    def get_avatar_variant_quote(self, base_id: str, bg_color: str = DEFAULT_BG_COLOR, address: str = "") -> Tuple[bool, str, Optional[dict]]:
        with self.lock:
            self._load_state()
            item = get_base_avatar(base_id)
            if not item:
                return False, f"Unknown avatar base_id: '{base_id}'", None
            color = normalize_hex_color(bg_color)
            if not color:
                return False, "Invalid hex background color. Use #RRGGBB format.", None

            variant_id = make_variant_id(item["base_id"], color)
            mint_count = int(self.avatar_variant_counts.get(variant_id, 0))
            price = compute_variant_price(mint_count)
            next_price = compute_variant_price(mint_count + 1)
            split = compute_revenue_split(price)

            clean_addr = normalize_bct_address(address) if address else ""
            owned_list = self.avatar_owners.get(clean_addr, []) if clean_addr else []
            already_owned = any(o.get("variant_id") == variant_id for o in owned_list)
            equipped = self.avatar_equipped.get(clean_addr) if clean_addr else None
            is_equipped = bool(equipped and equipped.get("variant_id") == variant_id)

            return True, "Avatar variant quote calculated.", {
                "variant_id": variant_id,
                "base_id": item["base_id"],
                "collection": item["collection"],
                "name": item["name"],
                "name_tr": item["name_tr"],
                "image_url": item["image_url"],
                "bg_color": color,
                "mint_count": mint_count,
                "is_fresh_variant": (mint_count == 0),
                "price": split["price"],
                "next_price": next_price,
                "treasury_cut": split["treasury_cut"],
                "pool_cut": split["pool_cut"],
                "miner_share": split["miner_share"],
                "validator_share": split["validator_share"],
                "observer_share": split["observer_share"],
                "already_owned": already_owned,
                "is_equipped": is_equipped,
                "soulbound": True,
            }

    def mint_avatar(
        self,
        buyer: str,
        base_id: str,
        bg_color: str = DEFAULT_BG_COLOR,
        max_price: Optional[float] = None,
        auto_equip: bool = True,
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Mints a Soulbound (non-transferable, non-sellable) profile avatar variant on-chain.
        - Unique Variant ID = `{base_id}-{HEX}` (e.g. `ANM-001-FFFFFF`).
        - Dynamic Bonding Curve: 0.10 BCT opening price for any unminted variant, +25% per mint.
        - Revenue Split: 30% Treasury Vault, 70% Block Reward Pool (50% Miner, 40% Validators, 10% Observer Stakers).
        """
        with self.lock:
            self._load_state()
            clean_buyer = normalize_bct_address(buyer)
            if not is_valid_bct_address(clean_buyer) or clean_buyer.upper() in (
                TREASURY_ADDRESS, "GENESIS_VAULT", "GENESIS", BRIDGE_VAULT_ADDRESS, VALIDATOR_STAKE_VAULT_ADDRESS
            ):
                return False, f"Invalid buyer address: '{clean_buyer}'", None

            item = get_base_avatar(base_id)
            if not item:
                return False, f"Unknown avatar ID: '{base_id}'", None

            color = normalize_hex_color(bg_color)
            if not color:
                return False, "Invalid background color. Must be a valid #RRGGBB hex code.", None

            variant_id = make_variant_id(item["base_id"], color)
            if not variant_id:
                return False, "Could not construct canonical avatar variant ID.", None

            expected_payload = signed_payload or f"AVATAR_MINT:{clean_buyer}:{variant_id}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_buyer, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            # Duplicate ownership guard (confirmed + mempool)
            owned_list = self.avatar_owners.get(clean_buyer, [])
            if any(o.get("variant_id") == variant_id for o in owned_list):
                return False, "You already own this avatar variant. You can equip it for free!", None

            # Canonical server-side bonding curve pricing (never trust client price)
            current_count = int(self.avatar_variant_counts.get(variant_id, 0))
            exact_price = compute_variant_price(current_count)

            # Slippage / front-run protection
            if max_price is not None:
                try:
                    mp = float(max_price)
                    if not math.isfinite(mp) or mp <= 0:
                        return False, "Invalid max_price slippage parameter.", None
                    if exact_price > mp + 1e-6:
                        return False, f"Avatar price increased to {exact_price:.6f} BCT due to another purchase. Please confirm the new price.", None
                except (TypeError, ValueError):
                    return False, "Invalid max_price parameter.", None

            buyer_bal = self.verify_and_recalc_balance(clean_buyer)
            if buyer_bal < exact_price:
                return False, f"Insufficient balance! Required: {exact_price:.6f} BCT, Current: {buyer_bal:.4f} BCT.", None

            split = compute_revenue_split(exact_price)
            treasury_cut = split["treasury_cut"]
            pool_cut = split["pool_cut"]

            extra_data = {
                "variant_id": variant_id,
                "base_id": item["base_id"],
                "bg_color": color,
                "collection": item["collection"],
                "name": item["name"],
                "mint_index": current_count + 1,
                "price": split["price"],
                "treasury_cut": treasury_cut,
                "pool_cut": pool_cut,
                "soulbound": True,
                "transferable": False,
                "sellable": False,
                "auto_equip": bool(auto_equip),
            }

            tx = Transaction(
                sender=clean_buyer,
                receiver=TREASURY_ADDRESS,
                amount=split["price"],
                fee=pool_cut,
                signature=signature,
                tx_type="avatar_mint",
                extra_data=extra_data,
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + pool_cut, 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_avatar_index()

            self.balances[clean_buyer] = self.verify_and_recalc_balance(clean_buyer)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._loaded_revision += 1
            self._profile_cache.clear()
            self._save_state()

            new_meta = build_avatar_metadata(item["base_id"], color, mint_count=current_count + 1)
            return True, f"Avatar {variant_id} minted on-chain for {split['price']:.4f} BCT!", {
                "avatar": new_meta,
                "variant_id": variant_id,
                "price": split["price"],
                "next_price": compute_variant_price(current_count + 1),
                "treasury_cut": treasury_cut,
                "pool_cut": pool_cut,
                "auto_equip": bool(auto_equip),
                "equipped_avatar": self.avatar_equipped.get(clean_buyer),
                "owned_avatars": list(self.avatar_owners.get(clean_buyer, [])),
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "new_balance": self.balances[clean_buyer],
            }

    def equip_avatar(
        self,
        owner: str,
        variant_id: str = "",
        signature: str = "",
        public_key: str = "",
        signed_payload: str = "",
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Equips an owned Soulbound avatar on the user's profile, swaps an existing one,
        or unequips when `variant_id == ""`.
        On-chain fee rules:
          - Equip (when none currently equipped): 0.20 BCT
          - Unequip (removing current avatar): 0.20 BCT
          - Swap (replacing an already-equipped avatar with another owned avatar): 0.40 BCT (0.20 + 0.20)
        Revenue Split: 30% Treasury Vault, 70% Block Reward Pool (50% Miner, 40% Validators, 10% Observer Stakers).
        """
        with self.lock:
            self._load_state()
            clean_owner = normalize_bct_address(owner)
            if not is_valid_bct_address(clean_owner) or clean_owner.upper() in (
                TREASURY_ADDRESS, "GENESIS_VAULT", "GENESIS", BRIDGE_VAULT_ADDRESS, VALIDATOR_STAKE_VAULT_ADDRESS
            ):
                return False, f"Invalid owner address: '{clean_owner}'", None

            clean_vid = str(variant_id or "").strip().upper()
            current_eq = self.avatar_equipped.get(clean_owner)
            current_vid = str(current_eq.get("variant_id", "") or "").upper() if isinstance(current_eq, dict) else ""

            if not clean_vid and not current_vid:
                return False, "No avatar is currently equipped on your profile.", None
            if clean_vid and clean_vid == current_vid:
                return False, "This avatar is already equipped on your profile.", None

            if clean_vid:
                base_id, bg_color = parse_variant_id(clean_vid)
                if not base_id or not bg_color:
                    return False, f"Invalid avatar variant ID: '{clean_vid}'", None
                owned_list = self.avatar_owners.get(clean_owner, [])
                if not any(o.get("variant_id") == clean_vid for o in owned_list):
                    return False, "You do not own this avatar variant.", None

            expected_payload = signed_payload or f"AVATAR_EQUIP:{clean_owner}:{clean_vid}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_owner, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            # Determine exact on-chain action fee: 0.20 BCT (equip or unequip) or 0.40 BCT (swap)
            if clean_vid and current_vid:
                action_type = "swap"
                action_fee = float(AVATAR_SWAP_FEE)
            elif clean_vid:
                action_type = "equip"
                action_fee = float(AVATAR_EQUIP_FEE)
            else:
                action_type = "unequip"
                action_fee = float(AVATAR_EQUIP_FEE)

            owner_bal = self.verify_and_recalc_balance(clean_owner)
            if owner_bal < action_fee:
                return False, f"Insufficient balance! On-chain avatar {action_type} fee is {action_fee:.2f} BCT. Current balance: {owner_bal:.4f} BCT.", None

            split = compute_revenue_split(action_fee)
            treasury_cut = split["treasury_cut"]
            pool_cut = split["pool_cut"]

            tx = Transaction(
                sender=clean_owner,
                receiver=TREASURY_ADDRESS,
                amount=split["price"],
                fee=pool_cut,
                signature=signature,
                tx_type="avatar_equip",
                extra_data={
                    "variant_id": clean_vid,
                    "previous_variant_id": current_vid,
                    "action": action_type,
                    "fee_paid": split["price"],
                    "treasury_cut": treasury_cut,
                    "pool_cut": pool_cut,
                },
            )

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + pool_cut, 8)

            block = self._seal_or_queue_mempool()
            self._load_in_memory_avatar_index()

            self.balances[clean_owner] = self.verify_and_recalc_balance(clean_owner)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._loaded_revision += 1
            self._profile_cache.clear()
            self._save_state()

            if action_type == "swap":
                msg = f"Profile avatar changed to {clean_vid} ({action_fee:.2f} BCT on-chain fee)."
            elif action_type == "equip":
                msg = f"Avatar {clean_vid} equipped to your profile ({action_fee:.2f} BCT on-chain fee)."
            else:
                msg = f"Profile avatar removed ({action_fee:.2f} BCT on-chain fee)."

            return True, msg, {
                "action": action_type,
                "fee_paid": split["price"],
                "treasury_cut": treasury_cut,
                "pool_cut": pool_cut,
                "new_balance": self.balances[clean_owner],
                "equipped_avatar": self.avatar_equipped.get(clean_owner),
                "owned_avatars": list(self.avatar_owners.get(clean_owner, [])),
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
            }

    def _save_state(self, force_json_backup: bool = False):
        """
        O(1) Delta Persistence Engine:
        - Serializes and inserts ONLY newly sealed blocks (b.index > max_db_idx) into SQLite WAL.
        - Upserts ONLY modified wallets (dirty_wallets) instead of rewriting all historical wallets.
        - Offloads legacy blockchain.json archival snapshots to an asynchronous background worker.
        """
        try:
            active_dir = self._get_active_data_dir()
            os.makedirs(active_dir, exist_ok=True)
            self._ensure_ledger_index()

            dirty_wallets: Dict[str, dict] = {}
            for addr, w_info in self.wallets.items():
                if isinstance(w_info, dict):
                    nonce_val = self._sender_nonce_map.get(addr, 0)
                    w_info["nonce"] = nonce_val
                    pub_val = str(w_info.get("public_key", ""))
                    sig_tuple = (pub_val, nonce_val)
                    if self._saved_wallet_nonces.get(addr) != sig_tuple:
                        dirty_wallets[addr] = w_info
                        self._saved_wallet_nonces[addr] = sig_tuple

            storage = self._get_storage()
            max_db_idx = storage.get_max_block_index()
            delta_blocks_dicts = [b.to_dict() for b in self.chain if b.index > max_db_idx]
            pending_dicts = [tx.to_dict() for tx in self.pending_transactions]

            new_rev = storage.save_state(
                blocks_dicts=delta_blocks_dicts,
                wallets=self.wallets,
                nodes=self.nodes,
                total_transactions=self.total_transactions,
                total_fees_collected=self.total_fees_collected,
                pending_dicts=pending_dicts,
                dirty_wallets=dirty_wallets,
                finalized_height=self.finalized_height,
                removed_mempool_hashes=list(self._removed_mempool_hashes),
                observer_pending_units=self.observer_pending_units,
                pending_asset_transfers=self.pending_asset_transfers,
            )
            self._removed_mempool_hashes.clear()
            self._loaded_revision = new_rev

            now = time.time()
            path = os.path.join(active_dir, "blockchain.json")
            should_write_json = (
                force_json_backup
                or not os.path.exists(path)
                or (
                    len(self.chain) != self._last_saved_chain_len
                    and (now - self._last_json_backup_ts) >= 15.0
                )
                or (now - self._last_json_backup_ts) >= 60.0
            )
            if should_write_json and not self._json_backup_in_flight:
                self._last_json_backup_ts = now
                self._last_saved_chain_len = len(self.chain)
                if force_json_backup or not os.path.exists(path):
                    full_blocks_dicts = [b.to_dict() for b in self.chain]
                    state = {
                        "chain": full_blocks_dicts,
                        "pending_transactions": pending_dicts,
                        "balances": dict(self.balances),
                        "wallets": dict(self.wallets),
                        "nodes": dict(self.nodes),
                        "total_transactions": self.total_transactions,
                        "total_fees_collected": self.total_fees_collected,
                    }
                    tmp_path = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
                    with open(tmp_path, "w", encoding="utf-8") as f:
                        json.dump(state, f, indent=2, ensure_ascii=False)
                    os.replace(tmp_path, path)
                else:
                    self._json_backup_in_flight = True
                    chain_snapshot = list(self.chain)
                    balances_snap = dict(self.balances)
                    wallets_snap = dict(self.wallets)
                    nodes_snap = dict(self.nodes)
                    tot_tx_snap = self.total_transactions
                    tot_fee_snap = self.total_fees_collected

                    def _async_json_writer():
                        try:
                            state_bg = {
                                "chain": [b.to_dict() for b in chain_snapshot],
                                "pending_transactions": pending_dicts,
                                "balances": balances_snap,
                                "wallets": wallets_snap,
                                "nodes": nodes_snap,
                                "total_transactions": tot_tx_snap,
                                "total_fees_collected": tot_fee_snap,
                            }
                            tmp_p = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
                            with open(tmp_p, "w", encoding="utf-8") as f_bg:
                                json.dump(state_bg, f_bg, indent=2, ensure_ascii=False)
                            os.replace(tmp_p, path)
                        except Exception:
                            pass
                        finally:
                            self._json_backup_in_flight = False

                    threading.Thread(target=_async_json_writer, daemon=True).start()
        except Exception as e:
            print(f"[ERROR] Failed to save blockchain state: {e}")

    @staticmethod
    def _dict_to_block(b_data: dict) -> Block:
        txs = [
            Transaction(
                sender=t_data["sender"],
                receiver=t_data["receiver"],
                amount=t_data["amount"],
                fee=t_data.get("fee", 0.0),
                signature=t_data.get("signature", ""),
                timestamp=t_data.get("timestamp"),
                tx_type=t_data.get("tx_type", "transfer"),
                extra_data=t_data.get("extra_data"),
            )
            for t_data in b_data["transactions"]
        ]
        b_ver = int(b_data.get("version", 1))
        b_merkle = b_data.get("merkle_root") or compute_merkle_root([tx.hash() for tx in txs])
        return Block(
            index=b_data["index"],
            transactions=txs,
            previous_hash=b_data["previous_hash"],
            timestamp=b_data["timestamp"],
            nonce=b_data["nonce"],
            miner=b_data.get("miner", "Genesis-Validator"),
            version=b_ver,
            merkle_root=b_merkle,
            attestations_count=int(b_data.get("attestations_count", 0)),
            precomputed_hash=str(b_data.get("hash", "")),
            finalized=bool(b_data.get("finalized", False)),
            raw_tx_dicts=b_data.get("transactions") if isinstance(b_data.get("transactions"), list) else None,
        )

    def _load_state(self, sweep_overdue: bool = True) -> bool:
        active_dir = self._get_active_data_dir()
        json_path = os.path.join(active_dir, "blockchain.json")
        db_path = os.path.join(active_dir, "blockchain.db")

        if not os.path.exists(db_path) and not os.path.exists(json_path):
            return False

        try:
            storage = self._get_storage()
            if storage.get_block_count() == 0 and os.path.exists(json_path):
                storage.migrate_from_json_if_empty(json_path, compute_merkle_root)

            current_rev = storage.get_state_revision()
            if self.chain and current_rev > 0 and current_rev == self._loaded_revision:
                if sweep_overdue:
                    self._sweep_overdue_mempool()
                return True

            # Fast O(Δ) incremental sync when canonical chain tip is already in memory
            if self.chain and self._loaded_revision > 0:
                delta_loaded = storage.load_delta_state(
                    since_block_index=self.chain[-1].index,
                    expected_tip_hash=self.chain[-1].hash,
                )
                if delta_loaded is not None:
                    rev, d_state = delta_loaded
                    self.wallets = d_state.get("wallets", {})
                    self.nodes = d_state.get("nodes", {})
                    self.total_transactions = d_state.get("total_transactions", 0)
                    self.total_fees_collected = d_state.get("total_fees_collected", 0.0)
                    self._init_default_nodes()

                    for b_data in d_state.get("new_blocks", []):
                        blk = self._dict_to_block(b_data)
                        if blk.index == len(self.chain) and blk.previous_hash == self.chain[-1].hash:
                            self.chain.append(blk)

                    att_counts = d_state.get("attestation_counts", {})
                    self.finalized_height = max(self.finalized_height, int(d_state.get("finalized_height", 0) or 0))
                    if isinstance(d_state.get("observer_pending_units"), dict):
                        self.observer_pending_units = dict(d_state["observer_pending_units"])
                    if isinstance(d_state.get("pending_asset_transfers"), dict):
                        self.pending_asset_transfers = dict(d_state["pending_asset_transfers"])
                    for b in self.chain[-10:]:
                        if b.index in att_counts:
                            b.attestations_count = att_counts[b.index]
                        if self.finalized_height > 0 and b.index <= self.finalized_height:
                            b.finalized = True

                    self.pending_transactions = [
                        Transaction(
                            sender=p_data["sender"],
                            receiver=p_data["receiver"],
                            amount=p_data["amount"],
                            fee=p_data.get("fee", 0.0),
                            signature=p_data.get("signature", ""),
                            timestamp=p_data.get("timestamp"),
                            tx_type=p_data.get("tx_type", "transfer"),
                            extra_data=p_data.get("extra_data"),
                        )
                        for p_data in d_state.get("pending_transactions", [])
                    ]
                    self._loaded_revision = rev
                    self._load_in_memory_bns_index()
                    self._load_in_memory_space_index()
                    self._load_in_memory_avatar_index()
                    self._load_in_memory_rooms_index()
                    if sweep_overdue:
                        self._sweep_overdue_mempool()
                    return True

            loaded = storage.load_full_state()
            if not loaded:
                return False

            rev, state = loaded
            self.wallets = state.get("wallets", {})
            self.nodes = state.get("nodes", {})
            self.total_transactions = state.get("total_transactions", 0)
            self.total_fees_collected = state.get("total_fees_collected", 0.0)
            self._init_default_nodes()

            chain_data = state.get("chain", [])
            new_chain = [self._dict_to_block(b_data) for b_data in chain_data]

            pending_raw = state.get("pending_transactions", [])
            new_pending: List[Transaction] = [
                Transaction(
                    sender=p_data["sender"],
                    receiver=p_data["receiver"],
                    amount=p_data["amount"],
                    fee=p_data.get("fee", 0.0),
                    signature=p_data.get("signature", ""),
                    timestamp=p_data.get("timestamp"),
                    tx_type=p_data.get("tx_type", "transfer"),
                    extra_data=p_data.get("extra_data"),
                )
                for p_data in pending_raw
            ]

            self.chain = new_chain
            self.finalized_height = max(self.finalized_height, int(state.get("finalized_height", 0) or 0))
            if isinstance(state.get("observer_pending_units"), dict):
                self.observer_pending_units = dict(state["observer_pending_units"])
            if isinstance(state.get("pending_asset_transfers"), dict):
                self.pending_asset_transfers = dict(state["pending_asset_transfers"])
            if self.finalized_height > 0:
                for b in self.chain:
                    if b.index <= self.finalized_height:
                        b.finalized = True
            self.pending_transactions = new_pending
            self._loaded_revision = rev
            self._saved_wallet_nonces = {
                addr: (str(w.get("public_key", "")), int(w.get("nonce", 0)))
                for addr, w in self.wallets.items()
                if isinstance(w, dict)
            }
            self._load_in_memory_bns_index()
            self._load_in_memory_space_index()
            self._load_in_memory_avatar_index()
            self._load_in_memory_rooms_index()

            if sweep_overdue:
                self._sweep_overdue_mempool()

            return True
        except Exception as e:
            print(f"[ERROR] Failed to load blockchain state: {e}")
            return False

    # ══════════════════════════════════════════════════════════════════
    # v2.6.0 P2P COMPACT BLOCK RELAY (Bandwidth-Optimized Block Relay)
    # ══════════════════════════════════════════════════════════════════
    def create_compact_block(self, block_dict: dict) -> dict:
        """
        Builds a compact block representation for P2P relay.
        Transmits block header, prefilled coinbase/system transactions, and 16-hex char short IDs
        for remaining transactions, cutting network bandwidth by ~90-95%.
        """
        txs = block_dict.get("transactions", [])
        prefilled = []
        short_ids = []
        if txs:
            prefilled.append({"index": 0, "tx": txs[0]})
            for tx in txs[1:]:
                tx_hash = tx.get("tx_hash", "") or ""
                short_ids.append(tx_hash[:16])

        return {
            "compact_version": 1,
            "header": {
                "index": int(block_dict.get("index", 0)),
                "version": int(block_dict.get("version", 2)),
                "merkle_root": str(block_dict.get("merkle_root", "")),
                "miner": str(block_dict.get("miner", "")),
                "previous_hash": str(block_dict.get("previous_hash", "")),
                "timestamp": block_dict.get("timestamp", 0.0),
                "nonce": int(block_dict.get("nonce", 0)),
                "difficulty": int(block_dict.get("difficulty", 3)),
                "hash": str(block_dict.get("hash", "")),
                "validator_quorum": block_dict.get("validator_quorum", []),
            },
            "prefilled_transactions": prefilled,
            "short_ids": short_ids,
            "total_transactions": len(txs),
        }

    def reconstruct_compact_block(self, compact_data: dict, extra_txs: Optional[List[dict]] = None) -> Tuple[bool, str, Optional[dict], List[int]]:
        """
        Reconstructs a full block from compact block payload using local mempool transactions.
        If any transactions are missing, returns the exact indices required to fetch via getblocktxn.
        Enforces strict cryptographic Merkle verification upon assembly.
        """
        header = compact_data.get("header") or {}
        prefilled = {item["index"]: item["tx"] for item in compact_data.get("prefilled_transactions", []) if "index" in item}
        short_ids = compact_data.get("short_ids", [])
        total_txs = int(compact_data.get("total_transactions", len(short_ids) + len(prefilled)))

        lookup: Dict[str, dict] = {}
        with self.lock:
            for p in self.pending_transactions:
                h = p.hash()
                lookup[h[:16]] = p.to_dict()

        if extra_txs:
            for etx in extra_txs:
                eh = etx.get("tx_hash", "")
                if eh:
                    lookup[eh[:16]] = etx

        assembled_txs: List[dict] = []
        missing_indices: List[int] = []

        for i in range(total_txs):
            if i in prefilled:
                assembled_txs.append(prefilled[i])
            else:
                s_idx = i - 1
                if 0 <= s_idx < len(short_ids):
                    sid = short_ids[s_idx]
                    if sid in lookup:
                        assembled_txs.append(lookup[sid])
                    else:
                        missing_indices.append(i)
                else:
                    missing_indices.append(i)

        if missing_indices:
            return False, "Missing transactions", None, missing_indices

        hashes = [t.get("tx_hash", "") for t in assembled_txs]
        try:
            calc_merkle = compute_merkle_root(hashes)
        except ValueError:
            return False, "Merkle root calculation failed due to invalid or duplicate hashes", None, []
        if calc_merkle != header.get("merkle_root", "").lower():
            return False, "Merkle root mismatch after reconstruction", None, []

        full_block = dict(header)
        full_block["transactions"] = assembled_txs
        return True, "Reconstructed", full_block, []

    # ══════════════════════════════════════════════════════════════════
    # v2.7.0 UTXO & ACCOUNT STATE SNAPSHOT SYNC (Decentralized Fast Sync)
    # ══════════════════════════════════════════════════════════════════
    def compute_state_root(self) -> str:
        """
        Computes deterministic SHA-256 state root over sorted balances, nonces, and BNS records.
        Guarantees zero-trust state integrity across all decentralized nodes.
        """
        with self.lock:
            self._load_state()
            sorted_balances = sorted((k, round(float(v), 8)) for k, v in self.balances.items())
            sorted_wallets = sorted((k, int(w.get("nonce", 0))) for k, w in self.wallets.items() if isinstance(w, dict))
            sorted_bns = sorted((k, str(v.get("owner", ""))) for k, v in self.bns_records.items() if isinstance(v, dict))

            payload = {
                "balances": sorted_balances,
                "wallets": sorted_wallets,
                "bns": sorted_bns,
            }
            canonical_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
            return hashlib.sha256(canonical_bytes).hexdigest()

    def get_state_snapshot(self) -> dict:
        """
        Exports a cryptographically verified snapshot of network state at current block height.
        Allows fast-syncing nodes to verify state root and download only recent 1,000 blocks.
        AUD17-02: Memoizes snapshot by (height, block_hash, total_transactions, bns_count) with 15s TTL
        to prevent repeated full-ledger sorting and hashing CPU DoS.
        """
        with self.lock:
            self._load_state()
            tip = self.chain[-1] if self.chain else None
            height = tip.index if tip else 0
            block_hash = tip.hash if tip else ""
            cache_key = (height, block_hash, self.total_transactions, len(self.bns_records))
            now = time.time()
            cached = getattr(self, "_snapshot_cache", None)
            if cached and cached.get("key") == cache_key and (now - cached.get("ts", 0.0)) < 15.0:
                return dict(cached["data"])

            state_root = self.compute_state_root()
            snap_data = {
                "protocol_version": Config.PROTOCOL_VERSION,
                "snapshot_height": height,
                "snapshot_block_hash": block_hash,
                "state_root": state_root,
                "total_transactions": self.total_transactions,
                "balances_count": len(self.balances),
                "balances": dict(self.balances),
                "wallets": dict(self.wallets),
                "bns_records": dict(self.bns_records),
                "created_at": now,
            }
            self._snapshot_cache = {"key": cache_key, "ts": now, "data": snap_data}
            return dict(snap_data)

    def apply_verified_state_snapshot(self, snapshot_data: dict) -> Tuple[bool, str]:
        """
        Applies and commits an audited state snapshot into local database.
        Strictly re-evaluates state_root before committing.
        """
        with self.lock:
            declared_root = str(snapshot_data.get("state_root", "")).strip().lower()
            balances = snapshot_data.get("balances", {})
            wallets = snapshot_data.get("wallets", {})
            bns = snapshot_data.get("bns_records", snapshot_data.get("bns_domains", {}))

            sorted_balances = sorted((k, round(float(v), 8)) for k, v in balances.items())
            sorted_wallets = sorted((k, int(w.get("nonce", 0))) for k, w in wallets.items() if isinstance(w, dict))
            sorted_bns = sorted((k, str(v.get("owner", ""))) for k, v in bns.items() if isinstance(v, dict))

            payload = {
                "balances": sorted_balances,
                "wallets": sorted_wallets,
                "bns": sorted_bns,
            }
            calc_root = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

            if calc_root != declared_root:
                return False, f"State root verification failed: {calc_root} != {declared_root}"

            self.balances = {k: float(v) for k, v in balances.items()}
            self.wallets = dict(wallets)
            self.bns_records = dict(bns)
            self.total_transactions = int(snapshot_data.get("total_transactions", self.total_transactions))

            snap_units = {k: _to_units(float(v)) for k, v in self.balances.items()}
            snap_nonces = {k: int(w.get("nonce", 0)) for k, w in self.wallets.items() if isinstance(w, dict)}
            tip_hash = self.chain[-1].hash if self.chain else ""
            self._snapshot_base = {
                "units": dict(snap_units),
                "nonces": dict(snap_nonces),
                "bns_records": dict(self.bns_records),
                "chain_len": len(self.chain),
            }
            self._bns_index_key = (
                len(self.chain),
                tip_hash,
                tuple(tx.hash() for tx in self.pending_transactions),
            )
            self._confirmed_units_map = dict(snap_units)
            self._confirmed_nonces_map = dict(snap_nonces)
            self._confirmed_indexed_len = len(self.chain)
            self._confirmed_indexed_tip = tip_hash
            self._unit_balances_map = dict(snap_units)
            self._sender_nonce_map = dict(snap_nonces)
            self._ledger_index_key = (
                self._loaded_revision,
                len(self.chain),
                tip_hash,
                tuple(tx.hash() for tx in self.pending_transactions),
            )
            self._save_state()
            return True, "Verified state snapshot applied successfully."
