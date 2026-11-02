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
import time
import os
import threading
from typing import List, Dict, Optional, Tuple


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
    """Cryptographic On-Chain Transaction."""

    def __init__(self, sender: str, receiver: str, amount: float,
                 fee: float = 0.0, signature: str = "",
                 timestamp: float = None, tx_type: str = "transfer"):
        self.sender = sender.strip()
        self.receiver = receiver.strip()
        self.amount = float(amount)
        self.fee = float(fee)
        self.signature = signature
        self.timestamp = timestamp or time.time()
        self.tx_type = tx_type

    def to_dict(self) -> dict:
        net = round(self.amount - self.fee, 8) if self.tx_type == "transfer" else round(self.amount, 8)
        return {
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

    def hash(self) -> str:
        data = json.dumps({
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "fee": self.fee,
            "timestamp": self.timestamp,
            "tx_type": self.tx_type
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()


class Block:
    """Immutable Blockchain Block with Proof-of-Work and Miner Attribution."""

    def __init__(self, index: int, transactions: List[Transaction],
                 previous_hash: str, timestamp: float = None, nonce: int = 0,
                 miner: str = ""):
        self.index = index
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.timestamp = timestamp or time.time()
        self.nonce = nonce
        self.miner = miner or "Genesis-Validator"
        self.hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        block_data = json.dumps({
            "index": self.index,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "previous_hash": self.previous_hash,
            "timestamp": self.timestamp,
            "nonce": self.nonce
        }, sort_keys=True)
        return hashlib.sha256(block_data.encode()).hexdigest()

    def mine(self, difficulty: int):
        target = "0" * difficulty
        self.hash = self.calculate_hash()
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self.calculate_hash()

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "hash": self.hash,
            "previous_hash": self.previous_hash,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "miner": self.miner,
            "transaction_count": len(self.transactions),
            "transactions": [tx.to_dict() for tx in self.transactions]
        }


class Blockchain:
    """Thread-safe, crash-resilient Blockchain Ledger."""

    def __init__(self, auto_mine: bool = True):
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

        with self.lock:
            if not self._load_state():
                self._create_genesis_block()
            self._init_default_nodes()

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

    def verify_and_recalc_balance(self, address: str) -> float:
        """Calculate mathematically exact balance from immutable on-chain history."""
        clean_addr = address.strip()
        bal = 0.0
        for block in self.chain:
            # Check if this block has a mining_reward transaction
            has_mining_reward = any(t.tx_type == "mining_reward" for t in block.transactions)

            for tx in block.transactions:
                if tx.receiver == clean_addr:
                    if tx.tx_type == "transfer":
                        bal += round(tx.amount - tx.fee, 8)
                    else:
                        bal += round(tx.amount, 8)
                if tx.sender == clean_addr:
                    bal -= round(tx.amount, 8)
                if clean_addr == TREASURY_ADDRESS and tx.tx_type == "transfer" and tx.fee > 0:
                    bal += round(tx.fee, 8)

        for tx in self.pending_transactions:
            if tx.receiver == clean_addr:
                if tx.tx_type == "transfer":
                    bal += round(tx.amount - tx.fee, 8)
                else:
                    bal += round(tx.amount, 8)
            if tx.sender == clean_addr:
                bal -= round(tx.amount, 8)

        return round(bal, 8)

    def register_wallet(self, address: str, public_key: str) -> Tuple[bool, str]:
        with self.lock:
            self._load_state()
            clean_addr = address.strip()

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
                "public_key": public_key or self.wallets.get(clean_addr, {}).get("public_key", ""),
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
                           amount: float, signature: str) -> Tuple[bool, str, Optional[dict]]:
        with self.lock:
            self._load_state()

            clean_sender = sender.strip()
            clean_receiver = receiver.strip()

            if clean_sender == clean_receiver:
                return False, "Cannot send funds to your own address", None

            if not is_valid_bct_address(clean_sender):
                return False, f"Invalid sender address format: '{clean_sender}'", None

            if not is_valid_bct_address(clean_receiver):
                return False, f"Invalid recipient address format: '{clean_receiver}'. Must be BCT followed by 40 hex characters.", None

            # Auto-register receiver wallet if not present (Decentralized permissionless model)
            if clean_receiver not in self.wallets and clean_receiver != TREASURY_ADDRESS:
                self.wallets[clean_receiver] = {
                    "public_key": "",
                    "created_at": time.time()
                }

            if amount <= 0:
                return False, "Amount must be strictly positive", None

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

    def _mine_block(self, miner_address: str = "") -> Optional[Block]:
        clean_miner = (miner_address or "").strip()
        if not self.pending_transactions and not (clean_miner and is_valid_bct_address(clean_miner)):
            return None

        # Calculate 50% transaction fee cut for miner
        total_fees = sum(tx.fee for tx in self.pending_transactions if tx.tx_type == "transfer")
        miner_fee_cut = round(total_fees * MINER_FEE_SHARE, 8)

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

    def get_wallet_transactions(self, address: str) -> list:
        with self.lock:
            self._load_state()
            clean_addr = address.strip()
            txs = []
            for block in self.chain:
                for tx in block.transactions:
                    if tx.sender == clean_addr or tx.receiver == clean_addr:
                        tx_dict = tx.to_dict()
                        tx_dict["block_index"] = block.index
                        tx_dict["block_hash"] = block.hash
                        txs.append(tx_dict)
            return list(reversed(txs))

    def is_chain_valid(self) -> bool:
        with self.lock:
            for i in range(1, len(self.chain)):
                current = self.chain[i]
                previous = self.chain[i - 1]
                if current.hash != current.calculate_hash():
                    return False
                if current.previous_hash != previous.hash:
                    return False
            return True

    def register_or_ping_node(self, node_id: str, name: str = "",
                              endpoint: str = "", role: str = "Peer Node",
                              location: str = "Decentralized",
                              block_height: int = 0,
                              miner_address: str = "",
                              version: str = "1.2.0") -> dict:
        with self.lock:
            self._load_state()
            clean_id = (node_id or "").strip()
            if not clean_id:
                clean_id = f"node-{int(time.time())}"

            node_info = self.nodes.get(clean_id, {
                "node_id": clean_id,
                "created_at": time.time(),
                "is_genesis": False,
                "blocks_mined": 0,
                "total_rewards": 0.0
            })

            clean_miner = (miner_address or "").strip()
            node_info.update({
                "name": (name or "").strip() or node_info.get("name", f"Community Node ({clean_id[:8]})"),
                "endpoint": (endpoint or "").strip() or node_info.get("endpoint", "p2p-client"),
                "role": role or node_info.get("role", "Peer Node"),
                "location": location or node_info.get("location", "Global"),
                "miner_address": clean_miner or node_info.get("miner_address", ""),
                "last_seen": time.time(),
                "status": "online",
                "version": version or "1.2.0",
                "block_height": max(block_height, node_info.get("block_height", 0), len(self.chain))
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
            treasury_balance = self.get_balance(TREASURY_ADDRESS)
            circulating = max(0.0, TOTAL_SUPPLY - treasury_balance)
            return {
                "total_supply": TOTAL_SUPPLY,
                "total_supply_formatted": f"{TOTAL_SUPPLY:,.0f}",
                "treasury_balance": treasury_balance,
                "treasury_formatted": f"{treasury_balance:,.8f}",
                "circulating_supply": circulating,
                "circulating_formatted": f"{circulating:,.8f}",
                "total_blocks": len(self.chain),
                "total_wallets": len(self.wallets),
                "total_transactions": self.total_transactions,
                "total_fees_collected": self.total_fees_collected,
                "pending_transactions": len(self.pending_transactions),
                "difficulty": self.difficulty,
                "chain_valid": self.is_chain_valid(),
                "latest_block_hash": self.chain[-1].hash if self.chain else "N/A"
            }

    def _save_state(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            state = {
                "chain": [b.to_dict() for b in self.chain],
                "balances": self.balances,
                "wallets": self.wallets,
                "nodes": self.nodes,
                "total_transactions": self.total_transactions,
                "total_fees_collected": self.total_fees_collected
            }
            path = os.path.join(DATA_DIR, "blockchain.json")
            tmp_path = path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception as e:
            print(f"[ERROR] Failed to save blockchain state: {e}")

    def _load_state(self) -> bool:
        path = os.path.join(DATA_DIR, "blockchain.json")
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)

            self.balances = state.get("balances", {})
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
                        tx_type=t_data.get("tx_type", "transfer")
                    )
                    txs.append(tx)
                block = Block(
                    index=b_data["index"],
                    transactions=txs,
                    previous_hash=b_data["previous_hash"],
                    timestamp=b_data["timestamp"],
                    nonce=b_data["nonce"],
                    miner=b_data.get("miner", "Genesis-Validator")
                )
                block.hash = b_data["hash"]
                new_chain.append(block)

            self.chain = new_chain
            return True
        except Exception as e:
            print(f"[ERROR] Failed to load blockchain state: {e}")
            return False
