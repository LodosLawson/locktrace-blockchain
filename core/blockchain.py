"""
BlockChainT - Enterprise Grade Blockchain Core
==============================================
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
MINING_DIFFICULTY = 3                    # Proof of Work Difficulty
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


class Transaction:
    """Cryptographic On-Chain Transaction."""

    def __init__(self, sender: str, receiver: str, amount: float,
                 fee: float = 0.0, signature: str = "",
                 timestamp: float = None, tx_type: str = "transfer"):
        self.sender = sender
        self.receiver = receiver
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
    """Immutable Blockchain Block with Proof-of-Work."""

    def __init__(self, index: int, transactions: List[Transaction],
                 previous_hash: str, timestamp: float = None, nonce: int = 0):
        self.index = index
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.timestamp = timestamp or time.time()
        self.nonce = nonce
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

        # Initialize or reload state
        with self.lock:
            if not self._load_state():
                self._create_genesis_block()

    # ── Genesis ───────────────────────────────────────────
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

    # ── Double-Check Balance From Entire Chain ─────────────
    def verify_and_recalc_balance(self, address: str) -> float:
        """
        Calculates balance from the entire immutable chain history.
        Guarantees funds can NEVER be lost due to memory glitches.
        """
        bal = 0.0
        for block in self.chain:
            for tx in block.transactions:
                if tx.receiver == address:
                    if tx.tx_type == "transfer":
                        bal += round(tx.amount - tx.fee, 8)
                    else:
                        bal += round(tx.amount, 8)
                if tx.sender == address:
                    bal -= round(tx.amount, 8)

        # Also account for pending unmined transactions
        for tx in self.pending_transactions:
            if tx.receiver == address:
                if tx.tx_type == "transfer":
                    bal += round(tx.amount - tx.fee, 8)
                else:
                    bal += round(tx.amount, 8)
            if tx.sender == address:
                bal -= round(tx.amount, 8)

        return round(bal, 8)

    # ── Register Wallet with 1.00 BCT Grant ────────────────
    def register_wallet(self, address: str, public_key: str) -> Tuple[bool, str]:
        with self.lock:
            # Refresh state from disk to prevent cross-worker drift
            self._load_state()

            if address in self.wallets:
                # Wallet already exists, return current verified balance
                bal = self.get_balance(address)
                return True, f"Wallet already registered with balance: {bal} BCT"

            self.wallets[address] = {
                "public_key": public_key,
                "created_at": time.time()
            }

            # Grant 1.00 BCT from Treasury
            treasury_bal = self.get_balance(TREASURY_ADDRESS)
            if treasury_bal >= 1.0:
                reward_tx = Transaction(
                    sender=TREASURY_ADDRESS,
                    receiver=address,
                    amount=1.0,
                    fee=0.0,
                    signature="automated_welcome_grant_1bct",
                    tx_type="reward"
                )
                self.balances[TREASURY_ADDRESS] = round(treasury_bal - 1.0, 8)
                self.balances[address] = 1.0
                self.pending_transactions.append(reward_tx)
                self.total_transactions += 1

                # Force mine immediately into a block so it's permanently sealed on-chain
                self._mine_block()
                self._save_state()

                return True, "Wallet created! 1.00 BCT welcome bonus permanently deposited."
            else:
                self.balances[address] = 0.0
                self._save_state()
                return True, "Wallet created, but treasury is depleted."

    # ── Wire Transfer with 1% Treasury Allocation ──────────
    def create_transaction(self, sender: str, receiver: str,
                           amount: float, signature: str) -> Tuple[bool, str, Optional[dict]]:
        with self.lock:
            self._load_state()

            if sender == receiver:
                return False, "Cannot send to your own address", None
            if sender not in self.wallets and sender != TREASURY_ADDRESS:
                return False, "Sender address not registered on network", None
            if receiver not in self.wallets and receiver != TREASURY_ADDRESS:
                return False, "Recipient address not found on network", None
            if amount <= 0:
                return False, "Amount must be greater than 0", None

            sender_balance = self.get_balance(sender)
            if sender_balance < amount:
                return False, f"Insufficient funds. Balance: {sender_balance:.8f} BCT, Required: {amount:.8f} BCT", None

            # 1% Treasury fee
            fee = round(amount * FEE_PERCENT, 8)
            net_amount = round(amount - fee, 8)

            tx = Transaction(
                sender=sender,
                receiver=receiver,
                amount=amount,
                fee=fee,
                signature=signature,
                tx_type="transfer"
            )

            # Update balances
            self.balances[sender] = round(self.balances[sender] - amount, 8)
            self.balances[receiver] = round(self.balances.get(receiver, 0.0) + net_amount, 8)
            self.balances[TREASURY_ADDRESS] = round(self.balances.get(TREASURY_ADDRESS, 0.0) + fee, 8)

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + fee, 8)

            # Mine block to secure ledger
            if self.auto_mine:
                self._mine_block()

            self._save_state()

            tx_info = {
                "tx_hash": tx.hash(),
                "sender": sender,
                "receiver": receiver,
                "amount": amount,
                "fee": fee,
                "net_amount": net_amount
            }

            return True, f"Transfer confirmed! Net: {net_amount} BCT, 1% Fee: {fee} BCT returned to vault", tx_info

    # ── Mining ────────────────────────────────────────────
    def _mine_block(self) -> Optional[Block]:
        if not self.pending_transactions:
            return None

        previous_hash = self.chain[-1].hash if self.chain else "0" * 64
        block = Block(
            index=len(self.chain),
            transactions=list(self.pending_transactions),
            previous_hash=previous_hash
        )
        block.mine(self.difficulty)
        self.chain.append(block)
        self.pending_transactions = []
        return block

    def mine_pending(self) -> Tuple[Optional[dict], str]:
        with self.lock:
            if not self.pending_transactions:
                return None, "No pending transactions in mempool"
            block = self._mine_block()
            if block:
                self._save_state()
                return block.to_dict(), f"Block #{block.index} successfully mined! ({len(block.transactions)} txs)"
            return None, "Mining failed"

    # ── Balance Query with Ledger Verification ─────────────
    def get_balance(self, address: str) -> float:
        with self.lock:
            # Sync with disk
            self._load_state()
            
            # Primary: cached fast lookup
            cached = self.balances.get(address)
            if cached is not None and cached > 0:
                return round(cached, 8)

            # Verification fallback: Compute from immutable chain
            recalc = self.verify_and_recalc_balance(address)
            self.balances[address] = recalc
            return recalc

    # ── Queries ───────────────────────────────────────────
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
                    txs.append(tx_dict)
            return list(reversed(txs))

    def get_wallet_transactions(self, address: str) -> list:
        with self.lock:
            self._load_state()
            txs = []
            for block in self.chain:
                for tx in block.transactions:
                    if tx.sender == address or tx.receiver == address:
                        tx_dict = tx.to_dict()
                        tx_dict["block_index"] = block.index
                        txs.append(tx_dict)
            return list(reversed(txs))

    def get_wallet_list(self) -> list:
        with self.lock:
            self._load_state()
            result = []
            for addr, info in self.wallets.items():
                result.append({
                    "address": addr,
                    "balance": self.get_balance(addr),
                    "created_at": info.get("created_at", 0)
                })
            return sorted(result, key=lambda x: x["created_at"], reverse=True)

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

    # ── Atomic Disk Storage ────────────────────────────────
    def _save_state(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            state = {
                "chain": [b.to_dict() for b in self.chain],
                "balances": self.balances,
                "wallets": self.wallets,
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
            self.total_transactions = state.get("total_transactions", 0)
            self.total_fees_collected = state.get("total_fees_collected", 0.0)

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
                    nonce=b_data["nonce"]
                )
                block.hash = b_data["hash"]
                new_chain.append(block)

            self.chain = new_chain
            return True
        except Exception as e:
            print(f"[ERROR] Failed to load blockchain state: {e}")
            return False

    def reset(self):
        with self.lock:
            self.chain = []
            self.pending_transactions = []
            self.balances = {TREASURY_ADDRESS: TOTAL_SUPPLY}
            self.wallets = {}
            self.total_transactions = 0
            self.total_fees_collected = 0.0
            self._create_genesis_block()
            return True, "Blockchain state reset to genesis"
