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
from core.wallet import public_key_to_address, verify_signature
from core.storage import SQLiteStorage

logger = logging.getLogger("LockTrace")


ATOMIC_UNIT = 100_000_000                 # 1 BCT = 10^8 atomic units (prevents IEEE-754 drift at 1T scale)


def _to_units(val: float) -> int:
    return int((Decimal(str(val)) * ATOMIC_UNIT).to_integral_value(rounding=ROUND_HALF_UP))


TOTAL_SUPPLY = 1_000_000_000_000.0       # 1 Trillion BCT
TREASURY_ADDRESS = "BCT_HAZINE_0000000000000000000000000000000000000000"
BRIDGE_VAULT_ADDRESS = "BCT_BRIDGE_VAULT_000000000000000000000000000000000"

# Developer Verified Lost-Key Test Wallets (Non-spendable / Permanently Locked / Effective Burn)
LOST_KEY_TEST_WALLETS = {
    "BCTd9cdd72f3d0ad1766a17d13d3fbfd3a97cf0d11d",
    "BCTf8c255f129a61b296f197a7e70902c043c3da0bf",
    "BCT7404325cf37316e3c6396ff1eef80c4ef381c27b",
    "BCT4ebea3d0f7132475e4e7c22573696eab6267a191",
}
FEE_PERCENT = 0.01                       # 1%
MINER_FEE_SHARE = 0.50                   # 50% of the 1% fee allocated to block/validator reward pool
TREASURY_FEE_SHARE = 0.50                # 50% returned to Treasury Vault
BLOCK_REWARD = 0.05                      # 0.05 BCT fixed block subsidy from treasury
PROPOSER_REWARD_SHARE = 0.70             # 70% of reward pool to winning PoW block producer
VALIDATOR_POOL_SHARE = 0.30              # 30% of reward pool shared equally among active verified peer validators
MEMPOOL_MINER_WINDOW_SECONDS = 15.0      # Priority window for external PoW miners before fallback sealing
ACTIVE_MINER_TTL_SECONDS = 90.0          # Heartbeat window identifying live external PoW miners

# Hybrid Batching Parameters for Micro/Social Transactions (Süre + Kota)
LIKE_BATCH_WINDOW_SECONDS = 20.0       # Max wait time for likes batch (20 seconds)
LIKE_BATCH_QUOTA = 15                  # Max count threshold for likes batch (15 likes)

COMMENT_BATCH_WINDOW_SECONDS = 50.0    # Max wait time for comments batch (50 seconds)
COMMENT_BATCH_QUOTA = 10               # Max count threshold for comments batch (10 comments)

GENERAL_TX_BATCH_WINDOW_SECONDS = 20.0 # Standard transfer / micro tx window (20 seconds)
GENERAL_TX_BATCH_QUOTA = 25            # General transaction block threshold

MINING_DIFFICULTY = 3                    # Base Proof of Work Difficulty
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

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
    if clean_upper in (TREASURY_ADDRESS, "GENESIS_VAULT", BRIDGE_VAULT_ADDRESS):
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

    def to_dict(self) -> dict:
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
        return d

    def hash(self) -> str:
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
        return hashlib.sha256(data.encode()).hexdigest()


def compute_merkle_root(tx_hashes: List[str]) -> str:
    """Compute canonical binary SHA-256 Merkle root over ordered transaction hashes."""
    if not tx_hashes:
        return "0" * 64
    level = [str(h).strip().lower() for h in tx_hashes]
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
    level = [str(h).strip().lower() for h in tx_hashes]
    if target not in level:
        return None
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
    for step in (proof or []):
        sibling = str(step.get("hash", "")).strip().lower()
        pos = step.get("position")
        if pos == "right":
            current = hashlib.sha256(f"{current}{sibling}".encode("utf-8")).hexdigest()
        elif pos == "left":
            current = hashlib.sha256(f"{sibling}{current}".encode("utf-8")).hexdigest()
        else:
            return False
    return current == (expected_root or "").strip().lower()


class Block:
    """Immutable Blockchain Block with Proof-of-Work, Merkle Root, and Miner Attribution."""

    def __init__(self, index: int, transactions: List[Transaction],
                 previous_hash: str, timestamp: float = None, nonce: int = 0,
                 miner: str = "", version: int = 2, merkle_root: str = "",
                 attestations_count: int = 0):
        self.index = index
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.timestamp = timestamp or time.time()
        self.nonce = nonce
        self.miner = miner or "Genesis-Validator"
        self.version = int(version)
        self.merkle_root = merkle_root or compute_merkle_root([tx.hash() for tx in self.transactions])
        self.attestations_count = int(attestations_count or 0)
        self.hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        if self.version >= 2:
            # v2 Header: Cryptographically commits merkle_root & miner into PoW hash
            payload = {
                "index": self.index,
                "version": self.version,
                "merkle_root": self.merkle_root,
                "miner": self.miner,
                "transactions": [tx.to_dict() for tx in self.transactions],
                "previous_hash": self.previous_hash,
                "timestamp": self.timestamp,
                "nonce": self.nonce,
            }
        else:
            # v1 Legacy Header: Preserves 100% hash validity for historical mainnet blocks 0..N
            payload = {
                "index": self.index,
                "transactions": [tx.to_dict() for tx in self.transactions],
                "previous_hash": self.previous_hash,
                "timestamp": self.timestamp,
                "nonce": self.nonce,
            }
        block_data = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(block_data.encode()).hexdigest()

    def mine(self, difficulty: int):
        self.merkle_root = compute_merkle_root([tx.hash() for tx in self.transactions])
        target = "0" * difficulty
        self.hash = self.calculate_hash()
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self.calculate_hash()

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "version": self.version,
            "hash": self.hash,
            "previous_hash": self.previous_hash,
            "merkle_root": self.merkle_root,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "miner": self.miner,
            "attestations_count": getattr(self, "attestations_count", 0),
            "transaction_count": len(self.transactions),
            "transactions": [tx.to_dict() for tx in self.transactions]
        }


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
        self._custom_data_dir = data_dir
        self._storage: Optional[SQLiteStorage] = None
        self._storage_dir_bound = ""
        self._loaded_revision = -1
        self._profile_cache: Dict[str, Tuple[int, float, dict]] = {}
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
            "version": "1.9.8",
            "block_height": len(self.chain),
            "is_genesis": True
        }
        if "node-stockholm-validator-01" not in self.nodes:
            self.nodes["node-stockholm-validator-01"] = genesis_node
        else:
            self.nodes["node-stockholm-validator-01"]["last_seen"] = time.time()
            self.nodes["node-stockholm-validator-01"]["block_height"] = len(self.chain)

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

    def verify_and_recalc_units(self, address: str) -> int:
        """Calculate exact balance in 10^8 integer atomic units (immune to IEEE-754 float64 drift)."""
        clean_addr = address.strip()
        units = 0
        fee_bearing_types = (
            "transfer", "space_post", "space_like", "space_comment", "space_follow",
            "bns_register", "bns_transfer", "bns_set_price", "bns_buy",
            "bns_accept_offer"
        )

        for block in self.chain:
            for tx in block.transactions:
                amt_u = _to_units(tx.amount)
                fee_u = _to_units(tx.fee)
                if tx.receiver == clean_addr:
                    if tx.tx_type in ("transfer", "space_post", "bns_register", "bns_buy", "bns_accept_offer"):
                        units += (amt_u - fee_u)
                    elif tx.tx_type == "bns_transfer":
                        # Only credit receiver if receiver is TREASURY_ADDRESS (for legacy bns_transfer where receiver was recipient wallet, credit goes to Treasury below)
                        if clean_addr == TREASURY_ADDRESS:
                            units += (amt_u - fee_u)
                    elif tx.tx_type in ("space_like", "space_comment", "space_follow"):
                        units += _to_units(tx.extra_data.get("treasury_cut", 0.0) if tx.extra_data else 0.0)
                    else:
                        units += amt_u
                elif clean_addr == TREASURY_ADDRESS and tx.tx_type == "bns_transfer":
                    # Ensure 80% treasury_cut of bns_transfer is always credited to TREASURY_ADDRESS
                    units += (amt_u - fee_u)
                if tx.sender == clean_addr:
                    units -= amt_u
                if tx.tx_type in ("space_like", "space_comment") and tx.extra_data:
                    if clean_addr == tx.extra_data.get("author"):
                        units += _to_units(tx.extra_data.get("author_cut", 0.0))
                if tx.tx_type == "space_follow" and tx.extra_data:
                    if clean_addr == tx.extra_data.get("target"):
                        units += _to_units(tx.extra_data.get("creator_cut", 0.0))
                if clean_addr == TREASURY_ADDRESS and tx.tx_type in fee_bearing_types and fee_u > 0:
                    units += fee_u

        for tx in self.pending_transactions:
            amt_u = _to_units(tx.amount)
            fee_u = _to_units(tx.fee)
            if tx.receiver == clean_addr:
                if tx.tx_type in ("transfer", "space_post", "bns_register", "bns_buy", "bns_accept_offer"):
                    units += (amt_u - fee_u)
                elif tx.tx_type == "bns_transfer":
                    if clean_addr == TREASURY_ADDRESS:
                        units += (amt_u - fee_u)
                elif tx.tx_type in ("space_like", "space_comment", "space_follow"):
                    units += _to_units(tx.extra_data.get("treasury_cut", 0.0) if tx.extra_data else 0.0)
                else:
                    units += amt_u
            elif clean_addr == TREASURY_ADDRESS and tx.tx_type == "bns_transfer":
                units += (amt_u - fee_u)
            if tx.sender == clean_addr:
                units -= amt_u
            if tx.tx_type in ("space_like", "space_comment") and tx.extra_data:
                if clean_addr == tx.extra_data.get("author"):
                    units += _to_units(tx.extra_data.get("author_cut", 0.0))
            if tx.tx_type == "space_follow" and tx.extra_data:
                if clean_addr == tx.extra_data.get("target"):
                    units += _to_units(tx.extra_data.get("creator_cut", 0.0))
            if clean_addr == TREASURY_ADDRESS and tx.tx_type in fee_bearing_types and fee_u > 0:
                units += fee_u

        return units

    def verify_and_recalc_balance(self, address: str) -> float:
        """Calculate mathematically exact balance from immutable on-chain history."""
        return round(self.verify_and_recalc_units(address) / ATOMIC_UNIT, 8)

    def _verify_actor_signature(self, actor_address: str, payload: str,
                                signature: str, public_key: str = "") -> Tuple[bool, str]:
        """Cryptographically verify ECDSA signature and bind public key to actor_address."""
        clean_addr = (actor_address or "").strip()
        if clean_addr.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT", "GENESIS"):
            return False, "System treasury address cannot be a direct transaction sender."
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

        # On-chain & mempool signature replay protection
        clean_sig = signature.strip()
        for ptx in self.pending_transactions:
            if ptx.signature == clean_sig:
                return False, "Replay transaction signature rejected (already in mempool)!"
        for blk in self.chain[-100:]:
            for btx in blk.transactions:
                if btx.signature == clean_sig:
                    return False, "Replay transaction signature rejected (already confirmed on-chain)!"

        if clean_addr not in self.wallets:
            self.wallets[clean_addr] = {"public_key": pub_hex, "created_at": time.time()}
        elif not self.wallets[clean_addr].get("public_key"):
            self.wallets[clean_addr]["public_key"] = pub_hex

        return True, "OK"

    def register_wallet(self, address: str, public_key: str, grant_welcome_bonus: bool = True) -> Tuple[bool, str]:
        with self.lock:
            self._load_state()
            clean_addr = address.strip()
            clean_pub = (public_key or "").strip()

            if not is_valid_bct_address(clean_addr) or clean_addr.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT"):
                return False, "Invalid wallet address format."

            if clean_pub:
                derived = public_key_to_address(clean_pub)
                if derived != clean_addr:
                    return False, "Public key does not match wallet address cryptographically!"

            current_bal = self.verify_and_recalc_balance(clean_addr)

            # Check if this address has EVER received the welcome bonus in any block
            has_received_reward = any(
                tx.receiver == clean_addr and tx.tx_type == "reward"
                for block in self.chain
                for tx in block.transactions
            ) or any(
                tx.receiver == clean_addr and tx.tx_type == "reward"
                for tx in self.pending_transactions
            )

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
                if self.auto_mine:
                    self._mine_block()

            # Always sync actual balance from verified ledger
            final_bal = self.verify_and_recalc_balance(clean_addr)
            self.balances[clean_addr] = final_bal
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()
            return True, f"Wallet registered successfully! Available balance: {final_bal} BCT"

    def create_transaction(self, sender: str, receiver: str,
                           amount: float, signature: str,
                           public_key: str = "", signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
        with self.lock:
            self._load_state()

            clean_sender = sender.strip()
            clean_receiver = receiver.strip()

            if clean_sender == clean_receiver:
                return False, "Cannot send funds to your own address", None

            if clean_sender.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT", "GENESIS"):
                return False, "Reserved system address cannot initiate standard transfers", None

            if not is_valid_bct_address(clean_sender):
                return False, f"Invalid sender address format: '{clean_sender}'", None

            if not is_valid_bct_address(clean_receiver):
                return False, f"Invalid recipient address format: '{clean_receiver}'. Must be BCT followed by 40 hex characters.", None

            if not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount <= 0:
                return False, "Amount must be a finite positive number", None

            amount = round(float(amount), 8)
            if amount < 0.00000001:
                return False, "Minimum transfer amount is 0.00000001 BCT", None

            expected_payload = signed_payload or f"{clean_sender}{clean_receiver}{amount}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_sender, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            # Auto-register receiver wallet if not present (Decentralized permissionless model)
            if clean_receiver not in self.wallets and clean_receiver != TREASURY_ADDRESS:
                self.wallets[clean_receiver] = {
                    "public_key": "",
                    "created_at": time.time()
                }

            sender_balance = self.verify_and_recalc_balance(clean_sender)
            if sender_balance < amount:
                return False, f"Insufficient balance. Your balance is {sender_balance:.8f} BCT, attempted to send {amount:.8f} BCT", None

            # Calculate 1% fee returned to treasury
            fee = round(amount * FEE_PERCENT, 8)
            net_amount = round(amount - fee, 8)

            tx = Transaction(
                sender=clean_sender,
                receiver=clean_receiver,
                amount=amount,
                fee=fee,
                signature=signature,
                tx_type="transfer"
            )

            self.pending_transactions.append(tx)
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

    def create_space_post(self, author: str, content: str, signature: str = "",
                          public_key: str = "", signed_payload: str = "",
                          bns_name: str = "") -> Tuple[bool, str, Optional[dict]]:
        """
        Creates an immutable, on-chain thought/tweet in LockTrace Space.
        Cost: 0.10 BCT.
        Tokenomics: 80% (0.08 BCT) returns to Treasury (circulating supply deflation),
        20% (0.02 BCT) is validator/miner fee.
        Character Limit: 3 - 280 characters.
        Automatically packages into a PoW block!
        """
        with self.lock:
            self._load_state()
            clean_author = author.strip()
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

            # Seal immediately on-chain if auto_mine is enabled
            block = self._mine_block() if self.auto_mine else self._seal_or_queue_mempool()

            # Record in fast index
            self.space_posts[post_id] = {
                "post_id": post_id,
                "author": clean_author,
                "author_bns": assigned_bns,
                "is_anonymous": (assigned_bns == "anonymous"),
                "content": clean_text,
                "timestamp": tx.timestamp,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool",
                "likes_count": 0,
                "likes": [],
                "comments_count": 0,
                "comments": [],
                "author_earnings": 0.0
            }

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
            clean_liker = liker.strip()
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
            like_cost = 0.01
            if liker_bal < like_cost:
                return False, f"Insufficient balance! Like fee is {like_cost:.2f} BCT. Current balance: {liker_bal:.4f} BCT.", None

            author_address = post["author"]
            author_cut = 0.002
            treasury_cut = 0.007
            miner_fee = 0.001
            sig = signature

            extra_data = {
                "post_id": pid,
                "author": author_address,
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

            # Update optimistic index immediately for real-time responsiveness
            if clean_liker not in post["likes"]:
                post["likes"].append(clean_liker)
                post["likes_count"] = len(post["likes"])
                post["author_earnings"] = round(post["author_earnings"] + author_cut, 8)

            self.balances[clean_liker] = self.verify_and_recalc_balance(clean_liker)
            self.balances[author_address] = self.verify_and_recalc_balance(author_address)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            # Hybrid Batching Evaluation (Quota or Timeout Trigger)
            block = None
            if self.auto_mine:
                ready, trigger_reason = self._check_batch_ready()
                if ready:
                    block = self._mine_block()

            res = {
                "post_id": pid,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool_batched",
                "batch_window_seconds": LIKE_BATCH_WINDOW_SECONDS,
                "batch_quota": LIKE_BATCH_QUOTA,
                "likes_count": post["likes_count"],
                "author_earned": author_cut,
                "liker_new_balance": self.balances[clean_liker]
            }
            msg = ("Post liked and sealed into block!" if block
                   else f"Post liked! Queued in 20s batch pool.")
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
            clean_commenter = commenter.strip()
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
            comment_cost = 0.02
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
            author_cut = 0.004
            treasury_cut = 0.014
            miner_fee = 0.002
            comment_id = f"cmt_{secrets.token_hex(6)}"
            sig = signature

            extra_data = {
                "post_id": pid,
                "comment_id": comment_id,
                "author": author_address,
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

            # Update index
            cmt_obj = {
                "comment_id": comment_id,
                "commenter": clean_commenter,
                "commenter_bns": assigned_bns,
                "is_anonymous": (assigned_bns == "anonymous"),
                "content": clean_text,
                "timestamp": tx.timestamp,
                "tx_hash": tx.hash()
            }
            post["comments"].append(cmt_obj)
            post["comments_count"] = len(post["comments"])
            post["author_earnings"] = round(post["author_earnings"] + author_cut, 8)

            self.balances[clean_commenter] = self.verify_and_recalc_balance(clean_commenter)
            self.balances[author_address] = self.verify_and_recalc_balance(author_address)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            # Hybrid Batching Evaluation (Quota or Timeout Trigger)
            block = None
            if self.auto_mine:
                ready, trigger_reason = self._check_batch_ready()
                if ready:
                    block = self._mine_block()

            res = {
                "post_id": pid,
                "comment": cmt_obj,
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool_batched",
                "batch_window_seconds": COMMENT_BATCH_WINDOW_SECONDS,
                "batch_quota": COMMENT_BATCH_QUOTA,
                "author_earned": author_cut,
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
            clean_follower = (follower or "").strip()
            clean_target = (target or "").strip()

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
            follow_cost = 1.00
            if follower_bal < follow_cost:
                return False, f"Insufficient balance! Follow fee is {follow_cost:.2f} BCT. Current balance: {follower_bal:.4f} BCT.", None

            creator_cut = 0.50
            miner_fee = 0.30
            treasury_cut = 0.20

            extra_data = {
                "target": clean_target,
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

            # Update optimistic state immediately
            if clean_target not in self.follows:
                self.follows[clean_target] = []
            if clean_follower not in self.follows[clean_target]:
                self.follows[clean_target].append(clean_follower)

            if clean_follower not in self.following:
                self.following[clean_follower] = []
            if clean_target not in self.following[clean_follower]:
                self.following[clean_follower].append(clean_target)

            self.balances[clean_follower] = self.verify_and_recalc_balance(clean_follower)
            self.balances[clean_target] = self.verify_and_recalc_balance(clean_target)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            block = None
            if self.auto_mine:
                block = self._mine_block()

            res = {
                "target": clean_target,
                "follower": clean_follower,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool_batched",
                "followers_count": len(self.follows[clean_target]),
                "creator_earned": creator_cut,
                "follower_new_balance": self.balances[clean_follower]
            }
            msg = ("Creator followed and sealed on-chain!" if block
                   else "Creator followed! Queued in mempool.")
            return True, msg, res

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

    def get_space_feed(self, limit: int = 50, feed_type: str = "for_you", tag: str = "", author: str = "") -> list:
        with self.lock:
            self._load_state()
            feed = list(self.space_posts.values())

            # Enrich posts with entity tags
            for p in feed:
                if "entities" not in p:
                    p["entities"] = self.extract_space_entities(p.get("content", ""))

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
                # Time-Decay Gravity scoring with discovery jitter
                def _calc_for_you_score(p):
                    age_h = max(0.05, (now_sec - float(p.get("timestamp", now_sec))) / 3600.0)
                    likes = len(p.get("likes", [])) if isinstance(p.get("likes"), list) else int(p.get("likes_count", 0))
                    comments = len(p.get("comments", [])) if isinstance(p.get("comments"), list) else int(p.get("comments_count", 0))
                    eng = (likes * 2) + (comments * 3) + 1.0
                    jitter = (int(hashlib.md5(str(p.get("post_id", "")).encode()).hexdigest()[:4], 16) % 5) * 0.15
                    return (eng / ((age_h + 1.5) ** 1.25)) + jitter

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
        """Calculates top trending hashtags (#) and cashtags ($) across space posts."""
        with self.lock:
            self._load_state()
            tag_counts = {}
            for p in self.space_posts.values():
                content = p.get("content", "")
                ents = self.extract_space_entities(content)
                for h in ents.get("hashtags", []):
                    tag_counts[h] = tag_counts.get(h, 0) + 1
                for c in ents.get("cashtags", []):
                    tag_counts[c] = tag_counts.get(c, 0) + 1

            sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
            return {
                "tags": [{"tag": t[0], "count": t[1], "type": "cashtag" if t[0].startswith("$") else "hashtag"} for t in sorted_tags[:top_n]],
                "total_tags_count": len(sorted_tags)
            }

    def get_space_post(self, post_id: str) -> Optional[dict]:
        with self.lock:
            self._load_state()
            return self.space_posts.get(post_id.strip())

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
                clean_viewer,
                "BCTd9cdd72f3d0ad1766a17d13d3fbfd3a97cf0d11d",
                "BCTf8c255f129a61b296f197a7e70902c043c3da0bf",
                "BCT7404325cf37316e3c6396ff1eef80c4ef381c27b",
                "BCT4ebea3d0f7132475e4e7c22573696eab6267a191",
                "BCT0000000000000000000000000000000000000000"
            }

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

                result.append({
                    "address": addr,
                    "bns_name": bns,
                    "display_name": display_name,
                    "bio": bio,
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
        if length < 3 or length > 24:
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
                return {
                    "available": False,
                    "reason": "Name must be between 3 and 24 characters (lowercase letters, digits, hyphens).",
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
            clean = (query or "").strip().lower()
            if clean.startswith("@"):
                clean = clean[1:]
            if clean.endswith(".bct"):
                rec = self.bns_records.get(clean)
                if rec:
                    return dict(rec)
                norm = self._normalize_bns_name(clean)
                return dict(self.bns_records.get(norm)) if norm in self.bns_records else None

            if is_valid_bct_address(query.strip()):
                addr = query.strip()
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
            clean_owner = owner.strip()
            if not is_valid_bct_address(clean_owner):
                return False, f"Invalid owner address: '{clean_owner}'", None

            pricing = self.get_bns_pricing(name)
            if not pricing["valid"]:
                return False, "Handle must be 3-24 characters long containing only lowercase letters, digits, or hyphens.", None

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

            self.bns_records[full_name] = {
                "name": full_name,
                "owner": clean_owner,
                "registered_at": tx.timestamp,
                "updated_at": tx.timestamp,
                "block_index": block.index if block else "Mempool",
                "tx_hash": tx.hash(),
                "status": "confirmed" if block else "mempool",
                "sale_price": 0.0,
                "cost": cost,
                "history": [{
                    "action": "registered",
                    "by": clean_owner,
                    "timestamp": tx.timestamp,
                    "tx_hash": tx.hash(),
                    "block": block.index if block else "Mempool"
                }]
            }
            if clean_owner not in self.bns_reverse:
                self.bns_reverse[clean_owner] = full_name

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
            clean_from = current_owner.strip()
            clean_to = to_address.strip()
            norm = self._normalize_bns_name(name)

            if not is_valid_bct_address(clean_from) or not is_valid_bct_address(clean_to):
                return False, "Invalid sender or recipient address.", None
            if clean_from == clean_to:
                return False, "Recipient address cannot be identical to sender address.", None
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

            block = self._mine_block() if self.auto_mine else self._seal_or_queue_mempool()

            rec["owner"] = clean_to
            rec["sale_price"] = 0.0
            rec["updated_at"] = tx.timestamp
            rec["history"].append({
                "action": "transferred",
                "from": clean_from,
                "to": clean_to,
                "timestamp": tx.timestamp,
                "tx_hash": tx.hash(),
                "block": block.index if block else "Mempool"
            })

            if self.bns_reverse.get(clean_from) == norm:
                other = next((n for n, r in self.bns_records.items() if r.get("owner") == clean_from), "")
                if other:
                    self.bns_reverse[clean_from] = other
                else:
                    self.bns_reverse.pop(clean_from, None)
            if clean_to not in self.bns_reverse:
                self.bns_reverse[clean_to] = norm

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
            clean_owner = owner.strip()
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

            rec["sale_price"] = price
            rec["updated_at"] = tx.timestamp
            rec["history"].append({
                "action": "price_listed" if price > 0 else "unlisted",
                "price": price,
                "timestamp": tx.timestamp,
                "tx_hash": tx.hash(),
                "block": block.index if block else "Mempool"
            })
            self._save_state()

            msg = f"'{norm}' listed on marketplace for {price} BCT!" if price > 0 else f"'{norm}' unlisted from marketplace."
            return True, msg, {"name": norm, "owner": clean_owner, "sale_price": price}

    def bns_buy(self, name: str, buyer: str, signature: str = "",
                public_key: str = "", signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
        with self.lock:
            self._load_state()
            clean_buyer = buyer.strip()
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

            buyer_bal = self.verify_and_recalc_balance(clean_buyer)
            if buyer_bal < sale_price:
                return False, f"Insufficient balance to purchase '{norm}'. Price: {sale_price} BCT, Balance: {buyer_bal} BCT.", None

            expected_payload = signed_payload or f"BNS_BUY:{norm}:{clean_buyer}:{seller}:{sale_price}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_buyer, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            # Standard 1% network trade fee
            fee = round(sale_price * 0.01, 8)
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

            rec["owner"] = clean_buyer
            rec["sale_price"] = 0.0
            rec["updated_at"] = tx.timestamp
            rec["history"].append({
                "action": "purchased",
                "buyer": clean_buyer,
                "seller": seller,
                "price": sale_price,
                "timestamp": tx.timestamp,
                "tx_hash": tx.hash(),
                "block": block.index if block else "Mempool"
            })

            if self.bns_reverse.get(seller) == norm:
                other = next((n for n, r in self.bns_records.items() if r.get("owner") == seller), "")
                if other:
                    self.bns_reverse[seller] = other
                else:
                    self.bns_reverse.pop(seller, None)
            if clean_buyer not in self.bns_reverse:
                self.bns_reverse[clean_buyer] = norm

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
            clean_owner = owner.strip()
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

            rec["updated_at"] = tx.timestamp
            rec["history"].append({
                "action": "set_primary",
                "owner": clean_owner,
                "timestamp": tx.timestamp,
                "tx_hash": tx.hash(),
                "block": block.index if block else "Mempool"
            })
            self.bns_reverse[clean_owner] = norm
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
            clean_bidder = bidder.strip()
            if not is_valid_bct_address(clean_bidder):
                return False, f"Invalid bidder address: '{clean_bidder}'", None

            norm = self._normalize_bns_name(name)
            if norm not in self.bns_records:
                return False, f"'{norm}' is not registered on-chain.", None

            rec = self.bns_records[norm]
            owner = rec.get("owner", "")
            if clean_bidder == owner:
                return False, "You cannot make an offer on your own domain.", None

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

            if "offers" not in rec or not isinstance(rec["offers"], dict):
                rec["offers"] = {}

            # Auto-supersede any previous active offer from the same bidder on this domain
            for prev_oid, prev_o in rec["offers"].items():
                if isinstance(prev_o, dict) and prev_o.get("bidder") == clean_bidder and prev_o.get("status") == "active":
                    prev_o["status"] = "superseded"
                    prev_o["resolved_at"] = tx.timestamp

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
            rec["offers"][offer_id] = offer_obj
            rec["updated_at"] = tx.timestamp
            rec["history"].append({
                "action": "offer_placed",
                "bidder": clean_bidder,
                "amount": amount,
                "offer_id": offer_id,
                "timestamp": tx.timestamp,
                "tx_hash": tx.hash(),
                "block": block.index if block else "Mempool"
            })
            self._save_state()

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
            clean_owner = owner.strip()
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

            bidder = target_offer.get("bidder", "")
            amount = float(target_offer.get("amount", 0.0))

            expected_payload = signed_payload or f"BNS_ACCEPT_OFFER:{norm}:{clean_owner}:{offer_id}:{bidder}:{amount}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_owner, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            # Verify bidder still has sufficient balance
            bidder_bal = self.verify_and_recalc_balance(bidder)
            if bidder_bal < amount:
                target_offer["status"] = "expired"
                self._save_state()
                return False, f"Bidder no longer has sufficient funds ({bidder_bal:.4f} BCT available). Offer marked expired.", None

            # Standard 1% network trade fee
            fee = round(amount * 0.01, 8)
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
                sender=bidder,
                receiver=clean_owner,
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

            # Transfer ownership
            rec["owner"] = bidder
            rec["sale_price"] = 0.0
            rec["updated_at"] = tx.timestamp
            target_offer["status"] = "accepted"
            target_offer["accepted_at"] = tx.timestamp
            target_offer["accept_tx_hash"] = tx.hash()

            # Mark all other active offers on this domain as superseded
            for o_id, off in offers.items():
                if o_id != offer_id and off.get("status") == "active":
                    off["status"] = "superseded"

            rec["history"].append({
                "action": "offer_accepted",
                "buyer": bidder,
                "bidder": bidder,
                "seller": clean_owner,
                "price": amount,
                "amount": amount,
                "offer_id": offer_id,
                "timestamp": tx.timestamp,
                "tx_hash": tx.hash(),
                "block": block.index if block else "Mempool"
            })

            # Update reverse lookups
            if self.bns_reverse.get(clean_owner) == norm:
                other = next((n for n, r in self.bns_records.items() if r.get("owner") == clean_owner), "")
                if other:
                    self.bns_reverse[clean_owner] = other
                else:
                    self.bns_reverse.pop(clean_owner, None)
            if bidder not in self.bns_reverse:
                self.bns_reverse[bidder] = norm

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
            clean_actor = actor.strip()
            norm = self._normalize_bns_name(name)
            if norm not in self.bns_records:
                return False, f"'{norm}' is not registered.", None

            rec = self.bns_records[norm]
            offers = rec.get("offers", {})
            if not isinstance(offers, dict) or offer_id not in offers:
                return False, "Offer not found.", None

            target_offer = offers[offer_id]
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

            clean_cache_key = raw.lower()
            if clean_cache_key.startswith("@"):
                clean_cache_key = clean_cache_key[1:]

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
            elif is_valid_bct_address(raw):
                target_address = raw
                primary_handle = self.bns_reverse.get(target_address, "")
            elif is_valid_bct_address(raw.upper()):
                target_address = raw.upper()
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

            if any(target_address.lower() == addr.lower() for addr in LOST_KEY_TEST_WALLETS):
                tag = "Geliştirici Doğruladı: Private Key Kayıp (Özel Test Adresi)"
                tag_type = "lost_key_burn"
                is_lost_key_burn = True
                lost_key_note = "Geliştirici doğruladı: Private key kayıp özel test adresidir (Dolaşım dışı / Fiili Yakım / Kilitli)"
            elif target_address == TREASURY_ADDRESS:
                tag = "Genesis Treasury (Escrowed)"
                tag_type = "treasury"
            elif target_address == BRIDGE_VAULT_ADDRESS:
                tag = "Bridge Vault (Base 1:1 Collateral)"
                tag_type = "bridge_vault"
            elif any(n.get("miner_address") == target_address for n in self.nodes.values()):
                tag = "Validator / Mining Node"
                tag_type = "validator"

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
                if tx.sender == target_address or tx.receiver == target_address:
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
                    if tx.sender == target_address or tx.receiver == target_address:
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

            profile_res = {
                "address": target_address,
                "primary_handle": primary_handle,
                "balance": balance,
                "holding_percentage": holding_pct,
                "circulating_percentage": circ_pct,
                "tag": tag,
                "tag_type": tag_type,
                "is_lost_key_burn": is_lost_key_burn,
                "lost_key_note": lost_key_note,
                "total_tx_count": total_tx_count,
                "owned_handles": owned_handles,
                "social_stats": {
                    "total_posts": len(user_posts),
                    "total_likes_received": total_likes_rec,
                    "total_comments_received": total_cmts_rec,
                    "total_royalties_earned": total_royalties,
                    "total_likes_given": total_likes_given,
                    "total_comments_given": total_cmts_given
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
        return False, "Free mock token acquisition is disabled. BCT tokens can be earned on LockTrace Space by sharing thoughts, comments/likes, or node mining.", None

    def execute_fiat_sale(self, seller_address: str, bct_amount: float,
                          payout_info: str = "", currency: str = "USD",
                          bct_per_usd: float = 100.0) -> Tuple[bool, str, Optional[dict]]:
        """Disabled: Initial welcome grant cannot be dumped for free fiat."""
        return False, "Direct fiat withdrawal is disabled. BCT balances can be used on the LockTrace Space thought network and for transfers.", None

    def execute_bridge_unlock(self, recipient_address: str, amount_bct: float,
                              evm_tx_hash: str, evm_sender: str = "") -> Tuple[bool, str, Optional[dict]]:
        """
        Executes verified Layer-1 unlock after wBCT burn on Base Mainnet.
        Transfers native BCT from BRIDGE_VAULT_ADDRESS (or TREASURY) to recipient_address.
        Strictly idempotent: Prevents double-unlocking the same evm_tx_hash.
        """
        with self.lock:
            self._load_state()
            clean_recipient = (recipient_address or "").strip()
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
        """Extracts a normalized host/IP identifier to prevent a single host/IP from running Sybil nodes."""
        client_ip = str(node.get("client_ip", "") or "").strip().lower()
        if client_ip and client_ip not in ("", "unknown", "127.0.0.1", "::1"):
            return f"ip:{client_ip}"
        ep = str(node.get("endpoint", "") or "").strip().lower()
        if ep.startswith("http"):
            try:
                parsed = urllib.parse.urlparse(ep)
                if parsed.hostname:
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
            m_addr = str(n.get("miner_address", "") or "").strip()
            if not is_valid_bct_address(m_addr) or m_addr == TREASURY_ADDRESS:
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
        clean_exclude = (exclude_miner or "").strip()
        candidates = []
        for _nid, n in self.nodes.items():
            if n.get("is_genesis"):
                continue
            m_addr = str(n.get("miner_address", "") or "").strip()
            if not is_valid_bct_address(m_addr) or m_addr in (TREASURY_ADDRESS, clean_exclude):
                continue
            if (ts - float(n.get("last_seen", 0))) > 300.0:
                continue
            if not n.get("auth_verified", False):
                continue
            attested_h = int(n.get("attested_height", -1))
            if attested_h < max(0, block_index - 5):
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

    def get_current_difficulty(self) -> int:
        """Adaptive PoW difficulty: scales smoothly when a large fleet of external PoW miners is active."""
        active_miners = len(self.get_active_peer_miners())
        if active_miners >= 8:
            return self.difficulty + 1
        return self.difficulty

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

    def _run_batch_sequencer_loop(self):
        while self._stop_sequencer and not self._stop_sequencer.is_set():
            try:
                time.sleep(1.0)
                with self.lock:
                    if self.auto_mine and self.pending_transactions:
                        ready, reason = self._check_batch_ready()
                        if ready:
                            blk = self._mine_block()
                            if blk:
                                logger.info(f"[BATCH SEQUENCER] Auto-sealed block #{blk.index} ({len(blk.transactions)} txs, trigger: {reason})")
            except Exception as e:
                logger.error(f"[BATCH SEQUENCER] loop exception: {e}")

    def _seal_or_queue_mempool(self) -> Optional[Block]:
        """Seals immediately if batch ready; otherwise queues in shared mempool."""
        if not self.auto_mine:
            return None
        ready, _ = self._check_batch_ready()
        if ready:
            return self._mine_block()
        return None

    def _sweep_overdue_mempool(self) -> Optional[Block]:
        """Safety-net sequencer: if pending mempool transactions wait longer than MEMPOOL_MINER_WINDOW_SECONDS, seal them."""
        if not self.auto_mine or not self.pending_transactions:
            return None
        now = time.time()
        oldest_ts = min(float(tx.timestamp or now) for tx in self.pending_transactions)
        if (now - oldest_ts) >= MEMPOOL_MINER_WINDOW_SECONDS:
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
        - 70% to Block Producer (`mining_reward`) + 30% split equally across verified active peer validators (`validator_reward`).
        - 100% to Block Producer if no other eligible peer validators are online.
        """
        clean_miner = (miner_address or "").strip()
        if not clean_miner or not is_valid_bct_address(clean_miner) or clean_miner == TREASURY_ADDRESS:
            return [], {"total_reward": 0.0, "proposer_reward": 0.0, "validator_pool_reward": 0.0, "validators_rewarded": []}

        transfer_fees_u = sum(_to_units(tx.fee) for tx in pending_txs if tx.tx_type in ("transfer", "bns_buy", "bns_accept_offer"))
        space_and_bns_fees_u = sum(
            _to_units(tx.fee) for tx in pending_txs if tx.tx_type in ("space_post", "space_like", "space_comment", "space_follow", "bns_register", "bns_transfer")
        )
        miner_fee_cut_u = (transfer_fees_u // 2) + space_and_bns_fees_u

        treasury_units = self.verify_and_recalc_units(TREASURY_ADDRESS)
        subsidy_target_u = _to_units(BLOCK_REWARD)
        subsidy_u = subsidy_target_u if treasury_units >= subsidy_target_u else 0
        total_pool_u = subsidy_u + miner_fee_cut_u

        if total_pool_u <= 0:
            return [], {"total_reward": 0.0, "proposer_reward": 0.0, "validator_pool_reward": 0.0, "validators_rewarded": []}

        det_ts = round(float(fixed_timestamp if fixed_timestamp is not None else time.time()), 3)
        validators = self.get_eligible_validators(exclude_miner=clean_miner, block_index=block_index, now=det_ts)

        reward_txs: List[Transaction] = []
        validators_breakdown: List[dict] = []

        if validators and total_pool_u >= 100:
            val_pool_u = (total_pool_u * 30) // 100
            per_val_u = val_pool_u // len(validators)
            actual_val_total_u = per_val_u * len(validators)
            proposer_u = total_pool_u - actual_val_total_u
        else:
            proposer_u = total_pool_u
            per_val_u = 0
            actual_val_total_u = 0

        if proposer_u > 0:
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

        if per_val_u > 0:
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
                        extra_data={"node_id": v_nid, "proposer": clean_miner},
                    )
                )
                validators_breakdown.append({"node_id": v_nid, "miner_address": v_addr, "reward": val_amt})

        breakdown = {
            "total_reward": float(Decimal(total_pool_u) / Decimal(ATOMIC_UNIT)),
            "proposer_reward": float(Decimal(proposer_u) / Decimal(ATOMIC_UNIT)),
            "validator_pool_reward": float(Decimal(actual_val_total_u) / Decimal(ATOMIC_UNIT)),
            "validators_rewarded": validators_breakdown,
        }
        return reward_txs, breakdown

    def _apply_reward_accounting(self, clean_miner: str, breakdown: dict):
        """Updates node mining & validator reward counters and registers newly rewarded addresses."""
        now = time.time()
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
                    with urllib.request.urlopen(req, timeout=2.5):
                        pass
                except Exception:
                    pass

        body = json.dumps({"block": block_dict, "network_height": len(self.chain)}).encode("utf-8")
        threading.Thread(target=_worker, args=(peers, body), daemon=True).start()

    def _mine_block(self, miner_address: str = "", require_pending: bool = False) -> Optional[Block]:
        clean_miner = (miner_address or "").strip()
        if require_pending and not self.pending_transactions:
            return None
        if not self.pending_transactions and not (clean_miner and is_valid_bct_address(clean_miner)):
            return None

        block_index = len(self.chain)
        block_txs = list(self.pending_transactions)
        reward_txs, breakdown = self._build_reward_transactions(block_txs, clean_miner, block_index)
        if reward_txs:
            block_txs.extend(reward_txs)
            self.total_transactions += len(reward_txs)

        previous_hash = self.chain[-1].hash if self.chain else "0" * 64
        diff = self.get_current_difficulty()
        block = Block(
            index=block_index,
            transactions=block_txs,
            previous_hash=previous_hash,
            miner=clean_miner or "Genesis-Validator",
        )
        block.mine(diff)
        self.chain.append(block)
        self.pending_transactions = []

        self._apply_reward_accounting(clean_miner, breakdown)
        self._load_in_memory_bns_index()
        self._load_in_memory_space_index()
        self._save_state()
        self._broadcast_block_to_peers(block.to_dict())
        return block

    def build_mining_template(self, miner_address: str, node_id: str = "") -> Tuple[bool, str, Optional[dict]]:
        """
        Generates a deterministic v2 PoW candidate block template (`getblocktemplate`) for external miner nodes.
        External nodes compute SHA-256 PoW locally and submit the solved block via `submit_mined_block`.
        """
        with self.lock:
            self._load_state(sweep_overdue=False)
            clean_miner = (miner_address or "").strip()
            if not is_valid_bct_address(clean_miner) or clean_miner.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT"):
                return False, "Invalid miner wallet address.", None

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

            template_ts = round(time.time(), 3)
            user_txs = list(self.pending_transactions[:100])
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

            clean_miner = str(block_data.get("miner", "") or "").strip()
            if not is_valid_bct_address(clean_miner) or clean_miner.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT"):
                return False, "Invalid miner wallet address.", None

            submitted_idx = int(block_data.get("index", -1))
            submitted_hash = str(block_data.get("hash", "") or "").strip().lower()
            submitted_prev = str(block_data.get("previous_hash", "") or "").strip().lower()
            submitted_nonce = int(block_data.get("nonce", -1))
            submitted_ts = round(float(block_data.get("timestamp", 0.0)), 3)
            submitted_ver = int(block_data.get("version", 2))

            if submitted_ver < 2 or submitted_nonce < 0:
                return False, "Only v2 Merkle PoW block format is accepted.", None

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

            if abs(time.time() - submitted_ts) > 300:
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
                tx_obj = Transaction(
                    sender=str(t_dict.get("sender", "")),
                    receiver=str(t_dict.get("receiver", "")),
                    amount=float(t_dict.get("amount", 0.0)),
                    fee=float(t_dict.get("fee", 0.0)),
                    signature=str(t_dict.get("signature", "")),
                    timestamp=float(t_dict.get("timestamp", 0.0)),
                    tx_type=t_type,
                    extra_data=t_dict.get("extra_data"),
                )
                h = tx_obj.hash()
                if t_type in ("mining_reward", "validator_reward"):
                    submitted_reward_hashes.append(h)
                else:
                    if h not in mempool_by_hash or h in seen_user_hashes:
                        return False, "Unrecognized or duplicate mempool transaction in block!", None
                    seen_user_hashes.add(h)
                    matched_user_txs.append(mempool_by_hash[h])

            if not matched_user_txs:
                return False, "Block must contain at least 1 valid mempool transaction.", None

            expected_reward_txs, breakdown = self._build_reward_transactions(
                matched_user_txs, clean_miner, expected_idx, fixed_timestamp=submitted_ts
            )
            expected_reward_hashes = [t.hash() for t in expected_reward_txs]
            if submitted_reward_hashes != expected_reward_hashes:
                return False, "Block reward distribution does not match protocol rules!", None

            # 4. Reconstruct candidate block and verify Merkle Root + SHA-256 Proof-of-Work
            final_txs = matched_user_txs + expected_reward_txs
            expected_merkle = compute_merkle_root([t.hash() for t in final_txs])
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
            clean_miner = (miner_address or "").strip()
            clean_pub = (public_key or "").strip()
            clean_hash = (block_hash or "").strip().lower()

            if not clean_id or not is_valid_bct_address(clean_miner) or clean_miner == TREASURY_ADDRESS:
                return False, "Invalid node ID or wallet address.", None
            if not clean_pub or not signature:
                return False, "Validator signature missing.", None
            if public_key_to_address(clean_pub) != clean_miner:
                return False, "Public key does not match validator wallet address!", None
            ts_str = str(timestamp).strip()
            if abs(time.time() - float(ts_str)) > 300:
                return False, "Attestation timestamp expired or invalid.", None
            if block_index < 0 or block_index >= len(self.chain):
                return False, f"Block #{block_index} is not yet available.", None

            target_block = self.chain[block_index]
            if target_block.hash.lower() != clean_hash:
                return False, "Block hash mismatch against canonical chain! (Fork or corrupted data)", None

            msg = f"ATTEST:{clean_id}:{block_index}:{clean_hash}:{ts_str}"
            if not verify_signature(clean_pub, msg, signature):
                return False, "Invalid validator ECDSA signature!", None

            existing = self.nodes.get(clean_id)
            if existing and existing.get("is_genesis"):
                return False, "Genesis node identity cannot be claimed externally.", None
            if existing and existing.get("owner_public_key") and existing["owner_public_key"] != clean_pub:
                return False, "This node_id is registered to another cryptographic key!", None

            storage = self._get_storage()
            inserted, total_att = storage.record_attestation(
                block_index=block_index,
                node_id=clean_id,
                miner_address=clean_miner,
                block_hash=clean_hash,
                signature=signature,
                timestamp=float(timestamp),
            )
            target_block.attestations_count = total_att

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
            clean_addr = address.strip()
            recalc = self.verify_and_recalc_balance(clean_addr)
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
        with self.lock:
            self._load_state(sweep_overdue=False)
            return self._mine_block(miner_address=miner_address, require_pending=True)

    def get_wallet_transactions(self, address: str) -> list:
        with self.lock:
            self._load_state()
            clean_addr = address.strip()

            # Fast indexed path: query SQLite index
            storage = self._get_storage()
            confirmed_txs = []
            if storage:
                try:
                    confirmed_txs = storage.get_transactions_for_address(clean_addr, limit=200)
                    for ctx in confirmed_txs:
                        ctx["status"] = "confirmed"
                        extra = ctx.get("extra_data") or {}
                        if extra.get("author") == clean_addr and ctx.get("sender") != clean_addr:
                            ctx["is_author_royalty"] = True
                            ctx["royalty_amount"] = extra.get("author_cut", 0.0)
                except Exception:
                    confirmed_txs = []

            if not confirmed_txs and self.chain:
                # Fallback to chain iteration if index not yet populated
                for block in reversed(self.chain):
                    for tx in block.transactions:
                        is_author_royalty = (
                            tx.tx_type in ("space_like", "space_comment")
                            and bool(tx.extra_data)
                            and tx.extra_data.get("author") == clean_addr
                            and tx.sender != clean_addr
                        )
                        if tx.sender == clean_addr or tx.receiver == clean_addr or is_author_royalty:
                            tx_dict = tx.to_dict()
                            tx_dict["block_index"] = block.index
                            tx_dict["block_hash"] = block.hash
                            tx_dict["status"] = "confirmed"
                            if is_author_royalty:
                                tx_dict["is_author_royalty"] = True
                                tx_dict["royalty_amount"] = tx.extra_data.get("author_cut", 0.0)
                            confirmed_txs.append(tx_dict)

            # Mempool pending transactions
            pending_txs = []
            for tx in self.pending_transactions:
                is_author_royalty = (
                    tx.tx_type in ("space_like", "space_comment")
                    and bool(tx.extra_data)
                    and tx.extra_data.get("author") == clean_addr
                    and tx.sender != clean_addr
                )
                if tx.sender == clean_addr or tx.receiver == clean_addr or is_author_royalty:
                    tx_dict = tx.to_dict()
                    tx_dict["block_index"] = None
                    tx_dict["block_hash"] = "MEMPOOL"
                    tx_dict["status"] = "mempool"
                    if is_author_royalty:
                        tx_dict["is_author_royalty"] = True
                        tx_dict["royalty_amount"] = tx.extra_data.get("author_cut", 0.0)
                    pending_txs.append(tx_dict)

            return pending_txs + confirmed_txs

    def get_account_nonce(self, address: str) -> int:
        """Compute exact sequential outgoing transaction nonce for an address from on-chain + pending history."""
        with self.lock:
            self._load_state()
            clean_addr = (address or "").strip()
            if not clean_addr:
                return 0
            count = sum(
                1 for block in self.chain for tx in block.transactions if tx.sender == clean_addr
            ) + sum(
                1 for tx in self.pending_transactions if tx.sender == clean_addr
            )
            return count

    def get_holders(self, page: int = 1, limit: int = 10) -> dict:
        """Returns ordered list of all accounts holding native BCT with balances, roles, and supply percentages."""
        with self.lock:
            self._load_state()
            all_addrs = set(self.wallets.keys())
            all_addrs.add(TREASURY_ADDRESS)
            all_addrs.add(BRIDGE_VAULT_ADDRESS)

            tx_counts = {}
            for block in self.chain:
                for tx in block.transactions:
                    if tx.sender:
                        all_addrs.add(tx.sender)
                        tx_counts[tx.sender] = tx_counts.get(tx.sender, 0) + 1
                    if tx.receiver:
                        all_addrs.add(tx.receiver)
                        tx_counts[tx.receiver] = tx_counts.get(tx.receiver, 0) + 1
            for tx in self.pending_transactions:
                if tx.sender:
                    all_addrs.add(tx.sender)
                    tx_counts[tx.sender] = tx_counts.get(tx.sender, 0) + 1
                if tx.receiver:
                    all_addrs.add(tx.receiver)
                    tx_counts[tx.receiver] = tx_counts.get(tx.receiver, 0) + 1

            holders = []
            for addr in all_addrs:
                clean_addr = addr.strip()
                if not clean_addr:
                    continue
                bal = self.verify_and_recalc_balance(clean_addr)
                if bal <= 0 and clean_addr not in (TREASURY_ADDRESS, BRIDGE_VAULT_ADDRESS) and tx_counts.get(clean_addr, 0) == 0:
                    continue

                tag = "User Wallet"
                tag_type = "user"
                if any(clean_addr.lower() == a.lower() for a in LOST_KEY_TEST_WALLETS):
                    tag = "Geliştirici Doğruladı: Private Key Kayıp (Özel Test Adresi)"
                    tag_type = "lost_key_burn"
                elif clean_addr == TREASURY_ADDRESS:
                    tag = "Treasury Vault (Locked Reserve)"
                    tag_type = "treasury"
                elif clean_addr == BRIDGE_VAULT_ADDRESS:
                    tag = "Bridge Vault (Base 1:1 wBCT)"
                    tag_type = "bridge_vault"
                elif any(n.get("miner_address") == clean_addr for n in self.nodes.values()):
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
                    "is_contract": clean_addr in (TREASURY_ADDRESS, BRIDGE_VAULT_ADDRESS),
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
            base_target = "0" * self.difficulty
            genesis = self.chain[0]
            if genesis.merkle_root != compute_merkle_root([tx.hash() for tx in genesis.transactions]):
                return False
            for i in range(1, len(self.chain)):
                current = self.chain[i]
                previous = self.chain[i - 1]
                if current.index != previous.index + 1:
                    return False
                if current.hash != current.calculate_hash():
                    return False
                if current.previous_hash != previous.hash:
                    return False
                if not current.hash.startswith(base_target):
                    return False
                expected_merkle = compute_merkle_root([tx.hash() for tx in current.transactions])
                if current.merkle_root != expected_merkle:
                    return False
            return True

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
        version: str = "1.9.8",
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
                self._save_state()
                return dict(existing)

            clean_miner = (miner_address or "").strip()
            if clean_miner and not is_valid_bct_address(clean_miner):
                clean_miner = ""

            # Cryptographic ECDSA ownership pin: once a node_id is bound to an ECDSA public_key, reject unauthenticated takeovers!
            clean_pub = (public_key or "").strip()
            auth_ok = False
            ts_str = str(timestamp).strip() if timestamp is not None else ""
            if clean_pub and signature and ts_str:
                try:
                    if abs(time.time() - float(ts_str)) <= 600:
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
            safe_role = self._sanitize_node_field(role, 48)
            safe_location = self._sanitize_node_field(location, 64)
            safe_version = self._sanitize_node_field(version, 24)
            safe_height = max(0, min(int(block_height or 0), len(self.chain) + 1000))

            node_info.update({
                "name": safe_name or node_info.get("name", f"Community Node ({clean_id[:8]})"),
                "endpoint": safe_endpoint or node_info.get("endpoint", "p2p-client"),
                "role": safe_role or node_info.get("role", "Peer Node"),
                "location": safe_location or node_info.get("location", "Global"),
                "miner_address": clean_miner or node_info.get("miner_address", ""),
                "last_seen": time.time(),
                "status": "online",
                "version": safe_version or node_info.get("version", "1.9.8"),
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
            self._save_state()
            return dict(node_info)

    def get_nodes(self) -> List[dict]:
        with self.lock:
            self._load_state()
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
                self._save_state()

            res = []
            for _n_id, n in self.nodes.items():
                copy_n = dict(n)
                copy_n.pop("owner_public_key", None)
                copy_n.pop("client_ip", None)
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
            lost_key_units = sum(self.verify_and_recalc_units(addr) for addr in LOST_KEY_TEST_WALLETS)
            # Dead/lost test wallet coins are subtracted from circulation as effective permanent burn
            circulating_units = max(0, total_units - treasury_units - vault_units - lost_key_units)
            treasury_dec = Decimal(treasury_units) / Decimal(ATOMIC_UNIT)
            vault_dec = Decimal(vault_units) / Decimal(ATOMIC_UNIT)
            lost_key_dec = Decimal(lost_key_units) / Decimal(ATOMIC_UNIT)
            effective_burned_units = treasury_units + lost_key_units
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
                "reward_model": "70% PoW Proposer / 30% Active Validator Quorum",
                "difficulty": self.get_current_difficulty(),
                "storage_engine": "sqlite-wal",
                "chain_valid": self.is_chain_valid(),
                "latest_block_hash": self.chain[-1].hash if self.chain else "N/A",
                "latest_merkle_root": self.chain[-1].merkle_root if self.chain else "N/A",
            }

    def _load_in_memory_bns_index(self):
        """Reconstructs BNS (.bct handles) registry & marketplace deterministically from confirmed blocks + live mempool."""
        self.bns_records = {}
        self.bns_reverse = {}
        all_sources = [(b.index, "confirmed", tx) for b in self.chain for tx in b.transactions] + [
            ("Mempool", "mempool", tx) for tx in self.pending_transactions
        ]
        for b_idx, status_lbl, tx in all_sources:
            if tx.tx_type == "bns_register" and tx.extra_data:
                name = tx.extra_data.get("name")
                if not name:
                    continue
                owner = tx.extra_data.get("owner", tx.sender)
                tier = tx.extra_data.get("tier", "")
                cost = float(tx.extra_data.get("cost", tx.amount))
                self.bns_records[name] = {
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
                if owner not in self.bns_reverse:
                    self.bns_reverse[owner] = name
            elif tx.tx_type == "bns_transfer" and tx.extra_data:
                name = tx.extra_data.get("name")
                from_addr = tx.extra_data.get("from_address", tx.sender)
                to_addr = tx.extra_data.get("to_address", tx.receiver)
                if name and name in self.bns_records:
                    rec = self.bns_records[name]
                    rec["owner"] = to_addr
                    rec["sale_price"] = 0.0
                    rec["updated_at"] = tx.timestamp
                    rec["history"].append({
                        "action": "transferred",
                        "from": from_addr,
                        "to": to_addr,
                        "timestamp": tx.timestamp,
                        "tx_hash": tx.hash(),
                        "block": b_idx
                    })
                    if self.bns_reverse.get(from_addr) == name:
                        other = next((n for n, r in self.bns_records.items() if r.get("owner") == from_addr), "")
                        if other:
                            self.bns_reverse[from_addr] = other
                        else:
                            self.bns_reverse.pop(from_addr, None)
                    if to_addr not in self.bns_reverse:
                        self.bns_reverse[to_addr] = name
            elif tx.tx_type == "bns_set_price" and tx.extra_data:
                name = tx.extra_data.get("name")
                price = float(tx.extra_data.get("price", 0.0))
                if name and name in self.bns_records:
                    self.bns_records[name]["sale_price"] = price
                    self.bns_records[name]["updated_at"] = tx.timestamp
                    self.bns_records[name]["history"].append({
                        "action": "listed_for_sale" if price > 0 else "unlisted",
                        "price": price,
                        "timestamp": tx.timestamp,
                        "tx_hash": tx.hash(),
                        "block": b_idx
                    })
            elif tx.tx_type == "bns_buy" and tx.extra_data:
                name = tx.extra_data.get("name")
                buyer = tx.extra_data.get("buyer", tx.sender)
                seller = tx.extra_data.get("seller", tx.receiver)
                price = float(tx.extra_data.get("price", tx.amount))
                if name and name in self.bns_records:
                    rec = self.bns_records[name]
                    rec["owner"] = buyer
                    rec["sale_price"] = 0.0
                    rec["updated_at"] = tx.timestamp
                    rec["history"].append({
                        "action": "purchased",
                        "buyer": buyer,
                        "seller": seller,
                        "price": price,
                        "timestamp": tx.timestamp,
                        "tx_hash": tx.hash(),
                        "block": b_idx
                    })
                    if self.bns_reverse.get(seller) == name:
                        other = next((n for n, r in self.bns_records.items() if r.get("owner") == seller), "")
                        if other:
                            self.bns_reverse[seller] = other
                        else:
                            self.bns_reverse.pop(seller, None)
                    if buyer not in self.bns_reverse:
                        self.bns_reverse[buyer] = name
            elif tx.tx_type == "bns_set_primary" and tx.extra_data:
                name = tx.extra_data.get("name")
                owner = tx.extra_data.get("owner", tx.sender)
                if name and owner and name in self.bns_records:
                    rec = self.bns_records[name]
                    if rec.get("owner") == owner:
                        rec["updated_at"] = tx.timestamp
                        rec["history"].append({
                            "action": "set_primary",
                            "owner": owner,
                            "timestamp": tx.timestamp,
                            "tx_hash": tx.hash(),
                            "block": b_idx
                        })
                        self.bns_reverse[owner] = name
            elif tx.tx_type == "bns_offer" and tx.extra_data:
                name = tx.extra_data.get("name")
                bidder = tx.extra_data.get("bidder", tx.sender)
                owner = tx.extra_data.get("owner", tx.receiver)
                offer_id = tx.extra_data.get("offer_id")
                amount = float(tx.extra_data.get("amount", 0.0))
                if name and offer_id and name in self.bns_records:
                    rec = self.bns_records[name]
                    if "offers" not in rec or not isinstance(rec["offers"], dict):
                        rec["offers"] = {}
                    # Auto-supersede any previous active offer from the same bidder on this domain
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
                bidder = tx.extra_data.get("bidder", tx.sender)
                seller = tx.extra_data.get("seller", tx.receiver)
                amount = float(tx.extra_data.get("amount", tx.amount))
                if name and name in self.bns_records:
                    rec = self.bns_records[name]
                    rec["owner"] = bidder
                    rec["sale_price"] = 0.0
                    rec["updated_at"] = tx.timestamp
                    if "offers" in rec and isinstance(rec["offers"], dict) and offer_id in rec["offers"]:
                        rec["offers"][offer_id]["status"] = "accepted"
                        rec["offers"][offer_id]["resolved_at"] = tx.timestamp
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
                    if self.bns_reverse.get(seller) == name:
                        other = next((n for n, r in self.bns_records.items() if r.get("owner") == seller), "")
                        if other:
                            self.bns_reverse[seller] = other
                        else:
                            self.bns_reverse.pop(seller, None)
                    if bidder not in self.bns_reverse:
                        self.bns_reverse[bidder] = name
            elif tx.tx_type == "bns_cancel_offer" and tx.extra_data:
                name = tx.extra_data.get("name")
                offer_id = tx.extra_data.get("offer_id")
                actor = tx.extra_data.get("actor", tx.sender)
                status = tx.extra_data.get("status", "cancelled")
                if name and name in self.bns_records:
                    rec = self.bns_records[name]
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

    def _load_in_memory_space_index(self):
        """Reconstructs Space Posts, Likes, Comments & Follows deterministically from confirmed blocks + live mempool."""
        self.space_posts = {}
        self.follows = {}
        self.following = {}
        all_sources = [(b.index, "confirmed", tx) for b in self.chain for tx in b.transactions] + [
            ("Mempool", "mempool", tx) for tx in self.pending_transactions
        ]
        for b_idx, status_lbl, tx in all_sources:
            if tx.tx_type == "space_post" and tx.extra_data:
                pid = tx.extra_data.get("post_id")
                if pid:
                    if "bns_name" in tx.extra_data:
                        raw_bns = str(tx.extra_data.get("bns_name") or "").strip().lower()
                        if raw_bns in ("anonymous", "anon"):
                            author_bns = "anonymous"
                        elif raw_bns and self.bns_records.get(raw_bns, {}).get("owner") == tx.sender:
                            author_bns = raw_bns
                        else:
                            author_bns = ""
                    else:
                        author_bns = self.bns_reverse.get(tx.sender, "")
                    self.space_posts[pid] = {
                        "post_id": pid,
                        "author": tx.sender,
                        "author_bns": author_bns,
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
            elif tx.tx_type == "space_like" and tx.extra_data:
                pid = tx.extra_data.get("post_id")
                liker = tx.sender
                if pid in self.space_posts and liker not in self.space_posts[pid]["likes"]:
                    self.space_posts[pid]["likes"].append(liker)
                    self.space_posts[pid]["likes_count"] += 1
                    self.space_posts[pid]["author_earnings"] = round(
                        self.space_posts[pid]["author_earnings"] + tx.extra_data.get("author_cut", 0.002), 8
                    )
            elif tx.tx_type == "space_comment" and tx.extra_data:
                pid = tx.extra_data.get("post_id")
                if pid in self.space_posts:
                    if "bns_name" in tx.extra_data:
                        raw_bns = str(tx.extra_data.get("bns_name") or "").strip().lower()
                        if raw_bns in ("anonymous", "anon"):
                            cmt_bns = "anonymous"
                        elif raw_bns and self.bns_records.get(raw_bns, {}).get("owner") == tx.sender:
                            cmt_bns = raw_bns
                        else:
                            cmt_bns = ""
                    else:
                        cmt_bns = self.bns_reverse.get(tx.sender, "")
                    cmt = {
                        "comment_id": tx.extra_data.get("comment_id", f"cmt_{secrets.token_hex(4)}"),
                        "commenter": tx.sender,
                        "commenter_bns": cmt_bns,
                        "is_anonymous": (cmt_bns == "anonymous" or bool(tx.extra_data.get("is_anonymous"))),
                        "content": tx.extra_data.get("content", ""),
                        "timestamp": tx.timestamp,
                        "tx_hash": tx.hash(),
                        "status": status_lbl,
                    }
                    self.space_posts[pid]["comments"].append(cmt)
                    self.space_posts[pid]["comments_count"] += 1
                    self.space_posts[pid]["author_earnings"] = round(
                        self.space_posts[pid]["author_earnings"] + tx.extra_data.get("author_cut", 0.004), 8
                    )
            elif tx.tx_type == "space_follow" and tx.extra_data:
                target = tx.extra_data.get("target")
                follower = tx.sender
                if target and follower:
                    if target not in self.follows:
                        self.follows[target] = []
                    if follower not in self.follows[target]:
                        self.follows[target].append(follower)
                    if follower not in self.following:
                        self.following[follower] = []
                    if target not in self.following[follower]:
                        self.following[follower].append(target)

    def _save_state(self):
        try:
            active_dir = self._get_active_data_dir()
            os.makedirs(active_dir, exist_ok=True)
            tx_counts: Dict[str, int] = {}
            for blk in self.chain:
                for tx in blk.transactions:
                    tx_counts[tx.sender] = tx_counts.get(tx.sender, 0) + 1
            for tx in self.pending_transactions:
                tx_counts[tx.sender] = tx_counts.get(tx.sender, 0) + 1
            for addr, w_info in self.wallets.items():
                if isinstance(w_info, dict):
                    w_info["nonce"] = tx_counts.get(addr, 0)

            blocks_dicts = [b.to_dict() for b in self.chain]
            pending_dicts = [tx.to_dict() for tx in self.pending_transactions]

            storage = self._get_storage()
            new_rev = storage.save_state(
                blocks_dicts=blocks_dicts,
                wallets=self.wallets,
                nodes=self.nodes,
                total_transactions=self.total_transactions,
                total_fees_collected=self.total_fees_collected,
                pending_dicts=pending_dicts,
            )
            self._loaded_revision = new_rev

            state = {
                "chain": blocks_dicts,
                "pending_transactions": pending_dicts,
                "balances": self.balances,
                "wallets": self.wallets,
                "nodes": self.nodes,
                "total_transactions": self.total_transactions,
                "total_fees_collected": self.total_fees_collected,
            }
            path = os.path.join(active_dir, "blockchain.json")
            tmp_path = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception as e:
            print(f"[ERROR] Failed to save blockchain state: {e}")

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
            new_chain = []
            for b_data in chain_data:
                txs = []
                for t_data in b_data["transactions"]:
                    tx = Transaction(
                        sender=t_data["sender"],
                        receiver=t_data["receiver"],
                        amount=t_data["amount"],
                        fee=t_data.get("fee", 0.0),
                        signature=t_data.get("signature", ""),
                        timestamp=t_data.get("timestamp"),
                        tx_type=t_data.get("tx_type", "transfer"),
                        extra_data=t_data.get("extra_data")
                    )
                    txs.append(tx)
                b_ver = int(b_data.get("version", 1))
                b_merkle = b_data.get("merkle_root") or compute_merkle_root([tx.hash() for tx in txs])
                block = Block(
                    index=b_data["index"],
                    transactions=txs,
                    previous_hash=b_data["previous_hash"],
                    timestamp=b_data["timestamp"],
                    nonce=b_data["nonce"],
                    miner=b_data.get("miner", "Genesis-Validator"),
                    version=b_ver,
                    merkle_root=b_merkle,
                    attestations_count=int(b_data.get("attestations_count", 0)),
                )
                block.hash = b_data["hash"]
                new_chain.append(block)

            pending_raw = state.get("pending_transactions", [])
            new_pending: List[Transaction] = []
            for p_data in pending_raw:
                new_pending.append(
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
                )

            self.chain = new_chain
            self.pending_transactions = new_pending
            self._loaded_revision = rev
            self._load_in_memory_bns_index()
            self._load_in_memory_space_index()

            if sweep_overdue:
                self._sweep_overdue_mempool()

            return True
        except Exception as e:
            print(f"[ERROR] Failed to load blockchain state: {e}")
            return False
