"""
BlockChainT - Enterprise Grade Blockchain Core (Hardened & Transparent)
========================================================================
Total Supply: 1 Trillion BCT
Wallet Genesis Reward: 1.00 BCT
Transaction Fee: 1% (Returned to Treasury Vault)
Atomic Persistence & On-Chain Ledger Verification
"""

import hashlib
import json
import math
import re
import time
import os
import threading
import secrets
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
MINER_FEE_SHARE = 0.50                   # 50% of the 1% fee directly to the block miner
TREASURY_FEE_SHARE = 0.50                # 50% returned to Treasury Vault
BLOCK_REWARD = 0.05                      # 0.05 BCT fixed block subsidy from treasury
MINING_DIFFICULTY = 3                    # Proof of Work Difficulty
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


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
                 miner: str = "", version: int = 2, merkle_root: str = ""):
        self.index = index
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.timestamp = timestamp or time.time()
        self.nonce = nonce
        self.miner = miner or "Genesis-Validator"
        self.version = int(version)
        self.merkle_root = merkle_root or compute_merkle_root([tx.hash() for tx in self.transactions])
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
            "version": "1.2.0",
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

            if self.auto_mine:
                self._mine_block()

            # Synchronize balances directly from the verified ledger
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
                "net_amount": net_amount
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

            # Mine block to record on-chain immediately
            block = self._mine_block()

            # Record in fast index
            self.space_posts[post_id] = {
                "post_id": post_id,
                "author": clean_author,
                "content": clean_text,
                "timestamp": tx.timestamp,
                "tx_hash": tx.hash(),
                "block_index": block.index if block else len(self.chain),
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
                "block_index": block.index if block else len(self.chain),
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

            block = self._mine_block()

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
                "block_index": block.index if block else len(self.chain),
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

            block = self._mine_block()

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
                "block_index": block.index if block else len(self.chain),
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

    def _mine_block(self, miner_address: str = "", require_pending: bool = False) -> Optional[Block]:
        clean_miner = (miner_address or "").strip()
        if require_pending and not self.pending_transactions:
            return None
        if not self.pending_transactions and not (clean_miner and is_valid_bct_address(clean_miner)):
            return None

        # Calculate transaction fee cuts for miner (50% for transfers, 100% of designated validator fee for space actions)
        transfer_fees = sum(tx.fee for tx in self.pending_transactions if tx.tx_type == "transfer")
        space_miner_fees = sum(tx.fee for tx in self.pending_transactions if tx.tx_type in ("space_post", "space_like", "space_comment"))
        miner_fee_cut = round(transfer_fees * MINER_FEE_SHARE + space_miner_fees, 8)

        # Base block subsidy from treasury
        treasury_bal = self.verify_and_recalc_balance(TREASURY_ADDRESS)
        subsidy = BLOCK_REWARD if treasury_bal >= BLOCK_REWARD else 0.0

        block_txs = list(self.pending_transactions)
        total_miner_payout = 0.0

        # If miner address is provided and valid, add Coinbase mining reward transaction
        if clean_miner and is_valid_bct_address(clean_miner) and clean_miner != TREASURY_ADDRESS:
            total_miner_payout = round(subsidy + miner_fee_cut, 8)
            if total_miner_payout > 0:
                coinbase_tx = Transaction(
                    sender=TREASURY_ADDRESS,
                    receiver=clean_miner,
                    amount=total_miner_payout,
                    fee=0.0,
                    signature=f"coinbase_pow_reward_block_{len(self.chain)}",
                    tx_type="mining_reward"
                )
                block_txs.append(coinbase_tx)
                self.total_transactions += 1

                # Ensure miner wallet is registered
                if clean_miner not in self.wallets:
                    self.wallets[clean_miner] = {"public_key": "", "created_at": time.time()}

        previous_hash = self.chain[-1].hash if self.chain else "0" * 64
        block = Block(
            index=len(self.chain),
            transactions=block_txs,
            previous_hash=previous_hash,
            miner=clean_miner or "Genesis-Validator"
        )
        block.mine(self.difficulty)
        self.chain.append(block)
        self.pending_transactions = []

        # Update node statistics if miner matches a registered node
        if clean_miner:
            for n_id, node in self.nodes.items():
                if node.get("miner_address") == clean_miner or node.get("endpoint") == clean_miner:
                    node["blocks_mined"] = node.get("blocks_mined", 0) + 1
                    node["total_rewards"] = round(node.get("total_rewards", 0.0) + total_miner_payout, 8)
                    node["block_height"] = len(self.chain)

        # Sync balances directly from verified ledger
        if clean_miner and clean_miner != TREASURY_ADDRESS:
            self.balances[clean_miner] = self.verify_and_recalc_balance(clean_miner)
        self.balances[TREASURY_ADDRESS] = self.verify_and_recalc_balance(TREASURY_ADDRESS)

        self._save_state()
        return block

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
            # Try index
            try:
                idx = int(query)
                if 0 <= idx < len(self.chain):
                    return self.chain[idx].to_dict()
            except ValueError:
                pass
            # Try hash
            for b in self.chain:
                if b.hash.lower() == query.lower() or b.previous_hash.lower() == query.lower():
                    return b.to_dict()
            return None

    def get_tx_by_hash(self, tx_hash: str) -> Optional[dict]:
        with self.lock:
            self._load_state()
            target = tx_hash.strip().lower()
            for b in self.chain:
                for tx in b.transactions:
                    if tx.hash().lower() == target:
                        d = tx.to_dict()
                        d["block_index"] = b.index
                        d["block_hash"] = b.hash
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
                    txs.append(tx_dict)
            return list(reversed(txs))

    def mine_pending_block(self, miner_address: str = "") -> Optional[Block]:
        """Thread-safe mining entrypoint for external miner nodes; strictly requires pending transactions."""
        with self.lock:
            self._load_state()
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
            target = "0" * self.difficulty
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
                if not current.hash.startswith(target):
                    return False
                expected_merkle = compute_merkle_root([tx.hash() for tx in current.transactions])
                if current.merkle_root != expected_merkle:
                    return False
            return True

    @staticmethod
    def _sanitize_node_field(val: str, max_len: int = 64) -> str:
        cleaned = re.sub(r'[<>"\'`\x00-\x1f\x7f]', '', str(val or '')).strip()
        return cleaned[:max_len]

    def register_or_ping_node(self, node_id: str, name: str = "",
                              endpoint: str = "", role: str = "Peer Node",
                              location: str = "Decentralized",
                              block_height: int = 0,
                              miner_address: str = "",
                              version: str = "1.2.0") -> dict:
        with self.lock:
            self._load_state()
            raw_id = re.sub(r'[^a-zA-Z0-9._-]', '', (node_id or "").strip())[:64]
            clean_id = raw_id or f"node-{secrets.token_hex(4)}"

            existing = self.nodes.get(clean_id)
            if existing and existing.get("is_genesis"):
                # Protect Genesis Validator metadata from external spoofing
                existing["last_seen"] = time.time()
                existing["block_height"] = len(self.chain)
                self._save_state()
                return dict(existing)

            # Cap registry size to prevent memory/disk DoS (max 200 peer nodes)
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
                "total_rewards": 0.0
            }

            clean_miner = (miner_address or "").strip()
            if clean_miner and not is_valid_bct_address(clean_miner):
                clean_miner = ""

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
                "version": safe_version or "1.2.0",
                "block_height": max(safe_height, len(self.chain))
            })
            self.nodes[clean_id] = node_info
            self._save_state()
            return node_info

    def get_nodes(self) -> List[dict]:
        with self.lock:
            self._load_state()
            self._init_default_nodes()
            now = time.time()
            res = []
            for n_id, n in self.nodes.items():
                copy_n = dict(n)
                # If node hasn't pinged in 15 minutes, mark inactive
                if not copy_n.get("is_genesis") and (now - copy_n.get("last_seen", 0) > 900):
                    copy_n["status"] = "offline"
                else:
                    copy_n["status"] = "online"
                copy_n["uptime_seconds"] = int(now - copy_n.get("created_at", now))
                res.append(copy_n)
            # Sort Genesis first, then by last_seen
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
                "difficulty": self.difficulty,
                "storage_engine": "sqlite-wal",
                "chain_valid": self.is_chain_valid(),
                "latest_block_hash": self.chain[-1].hash if self.chain else "N/A",
                "latest_merkle_root": self.chain[-1].merkle_root if self.chain else "N/A",
            }

    def _save_state(self):
        try:
            active_dir = self._get_active_data_dir()
            os.makedirs(active_dir, exist_ok=True)
            # Update monotonic per-wallet nonces before persisting
            tx_counts: Dict[str, int] = {}
            for blk in self.chain:
                for tx in blk.transactions:
                    tx_counts[tx.sender] = tx_counts.get(tx.sender, 0) + 1
            for addr, w_info in self.wallets.items():
                if isinstance(w_info, dict):
                    w_info["nonce"] = tx_counts.get(addr, 0)

            blocks_dicts = [b.to_dict() for b in self.chain]

            # 1) Primary ACID SQLite WAL persistence (incremental block writes + revision bump)
            storage = self._get_storage()
            new_rev = storage.save_state(
                blocks_dicts=blocks_dicts,
                wallets=self.wallets,
                nodes=self.nodes,
                total_transactions=self.total_transactions,
                total_fees_collected=self.total_fees_collected,
            )
            self._loaded_revision = new_rev

            # 2) Atomic JSON mirror snapshot for transparent archival backup
            state = {
                "chain": blocks_dicts,
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

    def _load_state(self) -> bool:
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
                # O(1) fast-path: In-memory state is already synchronized with SQLite WAL revision
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
                )
                block.hash = b_data["hash"]
                new_chain.append(block)

            self.chain = new_chain
            self._loaded_revision = rev

            # Reconstruct Space Posts, Likes & Comments deterministically from on-chain history
            self.space_posts = {}
            for block in self.chain:
                for tx in block.transactions:
                    if tx.tx_type == "space_post" and tx.extra_data:
                        pid = tx.extra_data.get("post_id")
                        if pid:
                            self.space_posts[pid] = {
                                "post_id": pid,
                                "author": tx.sender,
                                "content": tx.extra_data.get("content", ""),
                                "timestamp": tx.timestamp,
                                "tx_hash": tx.hash(),
                                "block_index": block.index,
                                "likes_count": 0,
                                "likes": [],
                                "comments_count": 0,
                                "comments": [],
                                "author_earnings": 0.0
                            }
                    elif tx.tx_type == "space_like" and tx.extra_data:
                        pid = tx.extra_data.get("post_id")
                        liker = tx.sender
                        if pid in self.space_posts:
                            if liker not in self.space_posts[pid]["likes"]:
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
                                "tx_hash": tx.hash()
                            }
                            self.space_posts[pid]["comments"].append(cmt)
                            self.space_posts[pid]["comments_count"] += 1
                            self.space_posts[pid]["author_earnings"] = round(
                                self.space_posts[pid]["author_earnings"] + tx.extra_data.get("author_cut", 0.004), 8
                            )

            return True
        except Exception as e:
            print(f"[ERROR] Failed to load blockchain state: {e}")
            return False
