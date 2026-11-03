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
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Optional, Tuple
from core.wallet import public_key_to_address, verify_signature
from core.storage import SQLiteStorage


ATOMIC_UNIT = 100_000_000                 # 1 BCT = 10^8 atomic units (prevents IEEE-754 drift at 1T scale)


def _to_units(val: float) -> int:
    return int((Decimal(str(val)) * ATOMIC_UNIT).to_integral_value(rounding=ROUND_HALF_UP))


TOTAL_SUPPLY = 1_000_000_000_000.0       # 1 Trillion BCT
TREASURY_ADDRESS = "BCT_HAZINE_0000000000000000000000000000000000000000"
FEE_PERCENT = 0.01                       # 1%
MINER_FEE_SHARE = 0.50                   # 50% of the 1% fee allocated to block/validator reward pool
TREASURY_FEE_SHARE = 0.50                # 50% returned to Treasury Vault
BLOCK_REWARD = 0.05                      # 0.05 BCT fixed block subsidy from treasury
PROPOSER_REWARD_SHARE = 0.70             # 70% of reward pool to winning PoW block producer
VALIDATOR_POOL_SHARE = 0.30              # 30% of reward pool shared equally among active verified peer validators
MEMPOOL_MINER_WINDOW_SECONDS = 15.0      # Priority window for external PoW miners before fallback sealing
ACTIVE_MINER_TTL_SECONDS = 90.0          # Heartbeat window identifying live external PoW miners
MINING_DIFFICULTY = 3                    # Base Proof of Work Difficulty
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

RELEASE_AUTHORITY_ADDRESS = "BCT5014d104d8063cbe2d64faea57925e96295ac3b8"
RELEASE_AUTHORITY_PUBKEY = (
    "5c8eca3d56c054b5b95a353e245efb3e014d85a33e8cb7e395b8a249d97a61c"
    "bdb35454f75f38d56c9fd34525411720208983d4ce27ed0fa34ddb09d2a08ff9c"
)


def verify_frontend_manifest(manifest: dict) -> Tuple[bool, str]:
    """Cryptographically verify a signed frontend release manifest against RELEASE_AUTHORITY_PUBKEY."""
    if not isinstance(manifest, dict):
        return False, "Geçersiz manifest formatı."
    ver = str(manifest.get("version", "")).strip()
    index_sha = str(manifest.get("index_html_sha256", "")).strip().lower()
    sw_sha = str(manifest.get("sw_js_sha256", "")).strip().lower()
    ipfs_cid = str(manifest.get("ipfs_cid_v1", "")).strip()
    pub = str(manifest.get("authority_public_key", "")).strip().lower()
    sig = str(manifest.get("signature", "")).strip()

    if not ver or len(index_sha) != 64 or not ipfs_cid or not sig:
        return False, "Eksik sürüm sağlama toplamı (SHA-256) veya imza alanı."
    if pub != RELEASE_AUTHORITY_PUBKEY.lower() or public_key_to_address(pub) != RELEASE_AUTHORITY_ADDRESS:
        return False, "Yetkisiz sürüm imzalayıcı açık anahtarı (Release Authority mismatch)!"

    canonical_msg = f"LOCKTRACE_FRONTEND_RELEASE:{ver}:{index_sha}:{sw_sha}:{ipfs_cid}"
    if not verify_signature(RELEASE_AUTHORITY_PUBKEY, canonical_msg, sig):
        return False, "ECDSA sürüm imzası geçersiz! Manifest manipüle edilmiş."
    return True, "Doğrulandı"


def is_valid_bct_address(addr: str) -> bool:
    """Validate BCT address syntax (case-insensitive prefix BCT + 40 hex)."""
    if not addr or not isinstance(addr, str):
        return False
    clean = addr.strip()
    clean_upper = clean.upper()
    if clean_upper == TREASURY_ADDRESS or clean_upper == "GENESIS_VAULT":
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
        self._custom_data_dir = data_dir
        self._storage: Optional[SQLiteStorage] = None
        self._storage_dir_bound = ""
        self._loaded_revision = -1

        with self.lock:
            if not self._load_state():
                self._create_genesis_block()
            self._init_default_nodes()

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
            "version": "1.4.0",
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
        fee_bearing_types = ("transfer", "space_post", "space_like", "space_comment")

        for block in self.chain:
            for tx in block.transactions:
                amt_u = _to_units(tx.amount)
                fee_u = _to_units(tx.fee)
                if tx.receiver == clean_addr:
                    if tx.tx_type in ("transfer", "space_post"):
                        units += (amt_u - fee_u)
                    elif tx.tx_type in ("space_like", "space_comment"):
                        units += _to_units(tx.extra_data.get("treasury_cut", 0.0) if tx.extra_data else 0.0)
                    else:
                        units += amt_u
                if tx.sender == clean_addr:
                    units -= amt_u
                if tx.tx_type in ("space_like", "space_comment") and tx.extra_data:
                    if clean_addr == tx.extra_data.get("author"):
                        units += _to_units(tx.extra_data.get("author_cut", 0.0))
                if clean_addr == TREASURY_ADDRESS and tx.tx_type in fee_bearing_types and fee_u > 0:
                    units += fee_u

        for tx in self.pending_transactions:
            amt_u = _to_units(tx.amount)
            fee_u = _to_units(tx.fee)
            if tx.receiver == clean_addr:
                if tx.tx_type in ("transfer", "space_post"):
                    units += (amt_u - fee_u)
                elif tx.tx_type in ("space_like", "space_comment"):
                    units += _to_units(tx.extra_data.get("treasury_cut", 0.0) if tx.extra_data else 0.0)
                else:
                    units += amt_u
            if tx.sender == clean_addr:
                units -= amt_u
            if tx.tx_type in ("space_like", "space_comment") and tx.extra_data:
                if clean_addr == tx.extra_data.get("author"):
                    units += _to_units(tx.extra_data.get("author_cut", 0.0))
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
            return False, "Sistem hazine adresi doğrudan işlem göndericisi olamaz."
        if not signature:
            return False, "Kriptografik imza eksik (Unauthorized)."

        pub_hex = (public_key or "").strip() or self.wallets.get(clean_addr, {}).get("public_key", "")
        if not pub_hex:
            return False, "Cüzdan açık anahtarı (public key) doğrulanamadı. Lütfen cüzdanınızı yeniden bağlayın."

        derived_addr = public_key_to_address(pub_hex)
        if derived_addr != clean_addr:
            return False, "Açık anahtar (public key) ile gönderici adresi uyuşmuyor!"

        if not verify_signature(pub_hex, payload, signature):
            return False, "Geçersiz ECDSA dijital imza!"

        if clean_addr not in self.wallets:
            self.wallets[clean_addr] = {"public_key": pub_hex, "created_at": time.time()}
        elif not self.wallets[clean_addr].get("public_key"):
            self.wallets[clean_addr]["public_key"] = pub_hex

        return True, "OK"

    def register_wallet(self, address: str, public_key: str) -> Tuple[bool, str]:
        with self.lock:
            self._load_state()
            clean_addr = address.strip()
            clean_pub = (public_key or "").strip()

            if not is_valid_bct_address(clean_addr) or clean_addr.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT"):
                return False, "Geçersiz cüzdan adresi formatı."

            if clean_pub:
                derived = public_key_to_address(clean_pub)
                if derived != clean_addr:
                    return False, "Açık anahtar (public key) cüzdan adresiyle kriptografik olarak eşleşmiyor!"

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

            if not has_received_reward:
                treasury_bal = self.verify_and_recalc_balance(TREASURY_ADDRESS)
                if treasury_bal >= 1.0:
                    reward_tx = Transaction(
                        sender=TREASURY_ADDRESS,
                        receiver=clean_addr,
                        amount=1.0,
                        fee=0.0,
                        signature="automated_welcome_grant_1bct",
                        tx_type="reward"
                    )
                    self.pending_transactions.append(reward_tx)
                    self.total_transactions += 1
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
                          public_key: str = "", signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
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
                return False, "Düşünce metni en az 3 karakter olmalıdır.", None
            if len(clean_text) > 280:
                return False, "Düşünce metni maksimum 280 karakter olabilir.", None

            expected_payload = signed_payload or f"{clean_author}:{clean_text}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_author, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            author_bal = self.verify_and_recalc_balance(clean_author)
            post_cost = 0.10
            if author_bal < post_cost:
                return False, f"Yetersiz bakiye! Paylaşım ücreti {post_cost:.2f} BCT'dir. Mevcut bakiyeniz: {author_bal:.4f} BCT.", None

            post_id = f"post_{secrets.token_hex(8)}"
            fee = 0.02
            treasury_cut = 0.08
            sig = signature

            extra_data = {
                "post_id": post_id,
                "content": clean_text,
                "author": clean_author,
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

            # Seal immediately if no external miners are online; otherwise queue in shared mempool for PoW nodes
            block = self._seal_or_queue_mempool()

            # Record in fast index
            self.space_posts[post_id] = {
                "post_id": post_id,
                "author": clean_author,
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
            return True, "Düşünceniz blokzincire başarıyla mühürlendi ve yayımlandı!", res

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
                return False, "Beğenilmek istenen gönderi bulunamadı.", None

            expected_payload = signed_payload or f"{clean_liker}:{pid}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_liker, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            post = self.space_posts[pid]
            if clean_liker in post.get("likes", []):
                return False, "Bu gönderiyi zaten beğendiniz.", None

            liker_bal = self.verify_and_recalc_balance(clean_liker)
            like_cost = 0.01
            if liker_bal < like_cost:
                return False, f"Yetersiz bakiye! Beğeni ücreti {like_cost:.2f} BCT'dir. Mevcut bakiyeniz: {liker_bal:.4f} BCT.", None

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

            block = self._seal_or_queue_mempool()

            # Update index
            if clean_liker not in post["likes"]:
                post["likes"].append(clean_liker)
                post["likes_count"] = len(post["likes"])
                post["author_earnings"] = round(post["author_earnings"] + author_cut, 8)

            self.balances[clean_liker] = self.verify_and_recalc_balance(clean_liker)
            self.balances[author_address] = self.verify_and_recalc_balance(author_address)
            self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)
            self._save_state()

            res = {
                "post_id": pid,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool",
                "likes_count": post["likes_count"],
                "author_earned": author_cut,
                "liker_new_balance": self.balances[clean_liker]
            }
            return True, f"Gönderi beğenildi! {author_cut} BCT yazarın cüzdanına aktarıldı.", res

    def comment_space_post(self, commenter: str, post_id: str, content: str,
                           signature: str = "", public_key: str = "", signed_payload: str = "") -> Tuple[bool, str, Optional[dict]]:
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
                return False, "Yorum yapılacak gönderi bulunamadı.", None

            clean_text = content.strip()
            if len(clean_text) < 1 or len(clean_text) > 140:
                return False, "Yorum metni 1 ile 140 karakter arasında olmalıdır.", None

            expected_payload = signed_payload or f"{clean_commenter}:{pid}:{clean_text}"
            sig_ok, sig_msg = self._verify_actor_signature(clean_commenter, expected_payload, signature, public_key)
            if not sig_ok:
                return False, sig_msg, None

            commenter_bal = self.verify_and_recalc_balance(clean_commenter)
            comment_cost = 0.02
            if commenter_bal < comment_cost:
                return False, f"Yetersiz bakiye! Yorum ücreti {comment_cost:.2f} BCT'dir. Mevcut bakiyeniz: {commenter_bal:.4f} BCT.", None

            post = self.space_posts[pid]
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

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + miner_fee, 8)

            block = self._seal_or_queue_mempool()

            # Update index
            cmt_obj = {
                "comment_id": comment_id,
                "commenter": clean_commenter,
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

            res = {
                "post_id": pid,
                "comment": cmt_obj,
                "block_index": block.index if block else "Mempool",
                "status": "confirmed" if block else "mempool",
                "author_earned": author_cut,
                "commenter_new_balance": self.balances[clean_commenter]
            }
            return True, f"Yorumunuz blokzincire işlendi! {author_cut} BCT yazarın hesabına geçti.", res

    def get_space_feed(self, limit: int = 50) -> list:
        with self.lock:
            self._load_state()
            feed = list(self.space_posts.values())
            feed.sort(key=lambda p: p.get("timestamp", 0), reverse=True)
            return feed[:limit]

    def get_space_post(self, post_id: str) -> Optional[dict]:
        with self.lock:
            self._load_state()
            return self.space_posts.get(post_id.strip())

    def execute_fiat_purchase(self, buyer_address: str, fiat_amount: float,
                              currency: str = "USD", payment_ref: str = "",
                              bct_per_usd: float = 100.0) -> Tuple[bool, str, Optional[dict]]:
        """Disabled: Prevents unverified mock coin acquisition."""
        return False, "Doğrudan test amaçlı bedava token alımı durdurulmuştur. BCT tokenları LockTrace Space üzerinde düşünce paylaşarak, yorum/beğeni toplayarak veya düğüm (node) madenciliği ile kazanılabilir.", None

    def execute_fiat_sale(self, seller_address: str, bct_amount: float,
                          payout_info: str = "", currency: str = "USD",
                          bct_per_usd: float = 100.0) -> Tuple[bool, str, Optional[dict]]:
        """Disabled: Initial welcome grant cannot be dumped for free fiat."""
        return False, "Doğrudan nakit çıkışı durdurulmuştur. Dağıtılan cüzdan bakiyeleri LockTrace Space düşünce ağı üzerinde ve transferlerde kullanılabilir.", None

    def get_active_peer_miners(self, now: Optional[float] = None) -> List[dict]:
        """Returns external non-genesis peer nodes actively polling/heartbeating within ACTIVE_MINER_TTL_SECONDS."""
        ts = now or time.time()
        active = []
        for _nid, n in self.nodes.items():
            if n.get("is_genesis"):
                continue
            m_addr = str(n.get("miner_address", "") or "").strip()
            if not is_valid_bct_address(m_addr) or m_addr == TREASURY_ADDRESS:
                continue
            if (ts - float(n.get("last_seen", 0))) <= ACTIVE_MINER_TTL_SECONDS:
                active.append(n)
        return active

    def get_eligible_validators(self, exclude_miner: str, block_index: int, now: Optional[float] = None) -> List[dict]:
        """
        Returns up to 10 verified online peer validator nodes eligible for the 30% Validator Attestation Pool.
        Requires cryptographic node identity (`auth_verified=True`) and recent synced/attested block height.
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
        for c in candidates:
            w = c["miner_address"].strip()
            if w not in seen_wallets:
                seen_wallets.add(w)
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

    def _seal_or_queue_mempool(self) -> Optional[Block]:
        """Seals immediately if 0 external peer miners are online; otherwise queues in shared SQLite mempool."""
        if not self.auto_mine:
            return None
        if self._should_defer_to_peer_miners():
            return None
        return self._mine_block()

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

        transfer_fees_u = sum(_to_units(tx.fee) for tx in pending_txs if tx.tx_type == "transfer")
        space_fees_u = sum(
            _to_units(tx.fee) for tx in pending_txs if tx.tx_type in ("space_post", "space_like", "space_comment")
        )
        miner_fee_cut_u = (transfer_fees_u // 2) + space_fees_u

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
                return False, "Geçersiz madenci cüzdan adresi.", None

            if node_id and node_id in self.nodes and not self.nodes[node_id].get("is_genesis"):
                self.nodes[node_id]["last_seen"] = time.time()

            diff = self.get_current_difficulty()
            block_index = len(self.chain)
            prev_hash = self.chain[-1].hash if self.chain else "0" * 64

            if not self.pending_transactions:
                return False, "Mempool boş — yeni işlem bekleniyor.", {
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

            return True, "PoW blok şablonu hazır.", {
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
                return False, "Geçersiz blok verisi.", None

            clean_miner = str(block_data.get("miner", "") or "").strip()
            if not is_valid_bct_address(clean_miner) or clean_miner.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT"):
                return False, "Geçersiz madenci cüzdan adresi.", None

            submitted_idx = int(block_data.get("index", -1))
            submitted_hash = str(block_data.get("hash", "") or "").strip().lower()
            submitted_prev = str(block_data.get("previous_hash", "") or "").strip().lower()
            submitted_nonce = int(block_data.get("nonce", -1))
            submitted_ts = round(float(block_data.get("timestamp", 0.0)), 3)
            submitted_ver = int(block_data.get("version", 2))

            if submitted_ver < 2 or submitted_nonce < 0:
                return False, "Yalnızca v2 Merkle PoW blok formatı kabul edilmektedir.", None

            # 1. Verify miner ECDSA ownership over the solved block header
            clean_pub = (public_key or "").strip() or self.wallets.get(clean_miner, {}).get("public_key", "")
            if not clean_pub or not signature:
                return False, "Blok gönderimi için madenci ECDSA imzası (public_key + signature) zorunludur.", None
            if public_key_to_address(clean_pub) != clean_miner:
                return False, "Madenci açık anahtarı (public_key) madenci cüzdan adresiyle eşleşmiyor!", None

            header_auth_msg = f"SUBMIT_BLOCK:{submitted_idx}:{submitted_hash}:{submitted_nonce}:{clean_miner}"
            if not verify_signature(clean_pub, header_auth_msg, signature):
                return False, "Geçersiz madenci blok ECDSA imzası!", None

            # 2. Check chain height & previous hash (detect race/stale block cleanly)
            expected_idx = len(self.chain)
            expected_prev = (self.chain[-1].hash if self.chain else "0" * 64).lower()
            if submitted_idx != expected_idx or submitted_prev != expected_prev:
                return False, f"Zincir ilerledi (Stale Block). Beklenen blok: #{expected_idx}", {"stale": True, "network_height": expected_idx}

            if abs(time.time() - submitted_ts) > 300:
                return False, "Blok zaman damgası geçersiz (±300 sn sınırı aşıldı).", None

            # 3. Validate transactions against live mempool + exact protocol reward math
            raw_txs = block_data.get("transactions", [])
            if not isinstance(raw_txs, list) or not raw_txs:
                return False, "Boş blok kabul edilmez.", None

            mempool_by_hash = {tx.hash(): tx for tx in self.pending_transactions}
            matched_user_txs: List[Transaction] = []
            submitted_reward_hashes: List[str] = []
            seen_user_hashes = set()

            for t_dict in raw_txs:
                if not isinstance(t_dict, dict):
                    return False, "Bozuk işlem formatı.", None
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
                        return False, "Blokta mempool'da bulunmayan veya mükerrer işlem tespit edildi!", None
                    seen_user_hashes.add(h)
                    matched_user_txs.append(mempool_by_hash[h])

            if not matched_user_txs:
                return False, "Blok en az 1 geçerli mempool işlemi içermelidir.", None

            expected_reward_txs, breakdown = self._build_reward_transactions(
                matched_user_txs, clean_miner, expected_idx, fixed_timestamp=submitted_ts
            )
            expected_reward_hashes = [t.hash() for t in expected_reward_txs]
            if submitted_reward_hashes != expected_reward_hashes:
                return False, "Blok ödül dağılımı protokol kurallarıyla uyuşmuyor!", None

            # 4. Reconstruct candidate block and verify Merkle Root + SHA-256 Proof-of-Work
            final_txs = matched_user_txs + expected_reward_txs
            expected_merkle = compute_merkle_root([t.hash() for t in final_txs])
            submitted_merkle = str(block_data.get("merkle_root", "") or "").strip().lower()
            if submitted_merkle != expected_merkle:
                return False, "Merkle Root doğrulaması başarısız!", None

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
                return False, f"Geçersiz Proof-of-Work hash! ({diff} sıfır hedefi sağlanmadı)", None

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
            self._load_in_memory_space_index()
            self._save_state()
            self._broadcast_block_to_peers(candidate_block.to_dict(), exclude_node_id=node_id)

            return True, f"Blok #{expected_idx} doğrulandı ve zincire eklendi!", {
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
                return False, "Geçersiz düğüm kimliği veya cüzdan adresi.", None
            if not clean_pub or not signature:
                return False, "Doğrulayıcı imzası eksik.", None
            if public_key_to_address(clean_pub) != clean_miner:
                return False, "Açık anahtar doğrulayıcı cüzdan adresiyle eşleşmiyor!", None
            ts_str = str(timestamp).strip()
            if abs(time.time() - float(ts_str)) > 300:
                return False, "Attestation zaman damgası geçersiz.", None
            if block_index < 0 or block_index >= len(self.chain):
                return False, f"Blok #{block_index} henüz mevcut değil.", None

            target_block = self.chain[block_index]
            if target_block.hash.lower() != clean_hash:
                return False, "Blok özeti (hash) ana zincirle uyuşmuyor! (Fork/Bozuk veri)", None

            msg = f"ATTEST:{clean_id}:{block_index}:{clean_hash}:{ts_str}"
            if not verify_signature(clean_pub, msg, signature):
                return False, "Geçersiz doğrulayıcı ECDSA imzası!", None

            existing = self.nodes.get(clean_id)
            if existing and existing.get("is_genesis"):
                return False, "Genesis düğümü kimliği dışarıdan kullanılamaz.", None
            if existing and existing.get("owner_public_key") and existing["owner_public_key"] != clean_pub:
                return False, "Bu node_id başka bir kriptografik anahtara kayıtlı!", None

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
            node_entry["last_seen"] = time.time()
            node_entry["status"] = "online"
            node_entry["attested_height"] = max(int(node_entry.get("attested_height", 0)), block_index)
            node_entry["block_height"] = max(int(node_entry.get("block_height", 0)), block_index + 1)
            if inserted:
                node_entry["blocks_attested"] = int(node_entry.get("blocks_attested", 0)) + 1
            self.nodes[clean_id] = node_entry
            self._save_state()

            return True, f"Blok #{block_index} doğrulama onayı (attestation) kaydedildi.", {
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
            txs = []
            for block in self.chain:
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
                        txs.append(tx_dict)
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
                    txs.append(tx_dict)
            return list(reversed(txs))

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
                return True, "Bu frontend sürümü zaten blokzincire mühürlenmiş durumda.", latest

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
            return True, "Frontend SHA-256 sürüm özeti blokzincire başarıyla mühürlendi!", sealed

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
        version: str = "1.4.0",
        public_key: str = "",
        signature: str = "",
        timestamp: Optional[float] = None,
        hashrate_hs: float = 0.0,
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
                    raise PermissionError("Bu node_id başka bir kriptografik ECDSA anahtarına kayıtlı!")

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
                "version": safe_version or node_info.get("version", "1.4.0"),
                "block_height": safe_height if safe_height > 0 else len(self.chain),
            })
            if auth_ok:
                node_info["auth_verified"] = True
                node_info["owner_public_key"] = clean_pub
            if hashrate_hs and float(hashrate_hs) > 0:
                node_info["hashrate_hs"] = round(min(float(hashrate_hs), 1e9), 2)

            self.nodes[clean_id] = node_info
            self._save_state()
            return dict(node_info)

    def get_nodes(self) -> List[dict]:
        with self.lock:
            self._load_state()
            self._init_default_nodes()
            now = time.time()
            res = []
            for _n_id, n in self.nodes.items():
                copy_n = dict(n)
                copy_n.pop("owner_public_key", None)
                if not copy_n.get("is_genesis") and (now - copy_n.get("last_seen", 0) > 900):
                    copy_n["status"] = "offline"
                else:
                    copy_n["status"] = "online"
                copy_n["uptime_seconds"] = int(now - copy_n.get("created_at", now))
                res.append(copy_n)
            res.sort(key=lambda x: (not x.get("is_genesis", False), -x.get("last_seen", 0)))
            return res

    def get_stats(self) -> dict:
        with self.lock:
            self._load_state()
            total_units = _to_units(TOTAL_SUPPLY)
            treasury_units = self.verify_and_recalc_units(TREASURY_ADDRESS)
            circulating_units = max(0, total_units - treasury_units)
            treasury_dec = Decimal(treasury_units) / Decimal(ATOMIC_UNIT)
            circulating_dec = Decimal(circulating_units) / Decimal(ATOMIC_UNIT)
            active_miners = self.get_active_peer_miners()
            network_hashrate = round(sum(float(n.get("hashrate_hs", 0.0)) for n in active_miners), 2)
            eligible_vals = self.get_eligible_validators("", len(self.chain))
            return {
                "total_supply": TOTAL_SUPPLY,
                "total_supply_formatted": f"{TOTAL_SUPPLY:,.0f}",
                "treasury_balance": float(treasury_dec),
                "treasury_formatted": f"{treasury_dec:,.8f}",
                "circulating_supply": float(circulating_dec),
                "circulating_formatted": f"{circulating_dec:,.8f}",
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

    def _load_in_memory_space_index(self):
        """Reconstructs Space Posts, Likes & Comments deterministically from confirmed blocks + live mempool."""
        self.space_posts = {}
        all_sources = [(b.index, "confirmed", tx) for b in self.chain for tx in b.transactions] + [
            ("Mempool", "mempool", tx) for tx in self.pending_transactions
        ]
        for b_idx, status_lbl, tx in all_sources:
            if tx.tx_type == "space_post" and tx.extra_data:
                pid = tx.extra_data.get("post_id")
                if pid:
                    self.space_posts[pid] = {
                        "post_id": pid,
                        "author": tx.sender,
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
                    cmt = {
                        "comment_id": tx.extra_data.get("comment_id", f"cmt_{secrets.token_hex(4)}"),
                        "commenter": tx.sender,
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
            self._load_in_memory_space_index()

            if sweep_overdue:
                self._sweep_overdue_mempool()

            return True
        except Exception as e:
            print(f"[ERROR] Failed to load blockchain state: {e}")
            return False
