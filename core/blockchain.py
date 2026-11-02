"""
BlockChainT - Kompakt Blockchain Çekirdeği
==========================================
Toplam Arz: 1 Trilyon BCT
Cüzdan Oluşturma Ödülü: 1 BCT
İşlem Ücreti: %1 (Hazineye döner)
"""

import hashlib
import json
import time
import os
import threading
from typing import List, Dict, Optional, Tuple


# ── Sabitler ──────────────────────────────────────────────
TOTAL_SUPPLY = 1_000_000_000_000        # 1 Trilyon
TREASURY_ADDRESS = "BCT_HAZINE_0000000000000000000000000000000000000000"
FEE_PERCENT = 0.01                       # %1
MINING_DIFFICULTY = 3                    # Zorluk seviyesi (leading zeros)
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


class Transaction:
    """Tek bir işlem (transfer)."""

    def __init__(self, sender: str, receiver: str, amount: float,
                 fee: float = 0.0, signature: str = "",
                 timestamp: float = None, tx_type: str = "transfer"):
        self.sender = sender
        self.receiver = receiver
        self.amount = amount
        self.fee = fee
        self.signature = signature
        self.timestamp = timestamp or time.time()
        self.tx_type = tx_type  # "genesis", "reward", "transfer"

    def to_dict(self) -> dict:
        return {
            "sender": self.sender,
            "receiver": self.receiver,
            "amount": self.amount,
            "fee": self.fee,
            "net_amount": self.amount - self.fee,
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
            "timestamp": self.timestamp
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()


class Block:
    """Zincirdeki tek bir blok."""

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
        """Proof-of-Work: Hash'in başında 'difficulty' kadar sıfır olmalı."""
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
    """Ana blockchain sınıfı. Tüm işlemleri yönetir."""

    def __init__(self, auto_mine: bool = True):
        self.chain: List[Block] = []
        self.pending_transactions: List[Transaction] = []
        self.balances: Dict[str, float] = {}
        self.wallets: Dict[str, dict] = {}   # address -> {public_key, created_at}
        self.difficulty = MINING_DIFFICULTY
        self.auto_mine = auto_mine
        self.lock = threading.Lock()
        self.total_transactions = 0
        self.total_fees_collected = 0.0

        # Hazine başlangıç bakiyesi
        self.balances[TREASURY_ADDRESS] = TOTAL_SUPPLY

        # Kayıtlı veri varsa yükle, yoksa genesis oluştur
        if not self._load_state():
            self._create_genesis_block()

    # ── Genesis ───────────────────────────────────────────
    def _create_genesis_block(self):
        genesis_tx = Transaction(
            sender="GENESIS",
            receiver=TREASURY_ADDRESS,
            amount=TOTAL_SUPPLY,
            fee=0,
            signature="genesis_block_signature",
            tx_type="genesis"
        )
        block = Block(0, [genesis_tx], "0" * 64)
        block.mine(self.difficulty)
        self.chain.append(block)
        self._save_state()

    # ── Cüzdan ────────────────────────────────────────────
    def register_wallet(self, address: str, public_key: str) -> Tuple[bool, str]:
        with self.lock:
            if address in self.wallets:
                return False, "Bu cüzdan adresi zaten kayıtlı"

            self.wallets[address] = {
                "public_key": public_key,
                "created_at": time.time()
            }

            # Hazineden 1 BCT ödül dağıt
            if self.balances[TREASURY_ADDRESS] >= 1.0:
                reward_tx = Transaction(
                    sender=TREASURY_ADDRESS,
                    receiver=address,
                    amount=1.0,
                    fee=0,
                    signature="wallet_creation_reward",
                    tx_type="reward"
                )
                self.balances[TREASURY_ADDRESS] -= 1.0
                self.balances[address] = 1.0
                self.pending_transactions.append(reward_tx)
                self.total_transactions += 1

                if self.auto_mine:
                    self._mine_block()

                return True, "Cüzdan oluşturuldu! 1 BCT ödül yatırıldı."
            else:
                self.balances[address] = 0.0
                return True, "Cüzdan oluşturuldu ama hazine boş, ödül verilemedi."

    # ── İşlem (Transfer) ──────────────────────────────────
    def create_transaction(self, sender: str, receiver: str,
                           amount: float, signature: str) -> Tuple[bool, str, Optional[dict]]:
        with self.lock:
            # Doğrulamalar
            if sender == receiver:
                return False, "Kendinize transfer yapamazsınız", None
            if sender not in self.wallets and sender != TREASURY_ADDRESS:
                return False, "Gönderen cüzdan bulunamadı", None
            if receiver not in self.wallets and receiver != TREASURY_ADDRESS:
                return False, "Alıcı cüzdan bulunamadı", None
            if amount <= 0:
                return False, "Miktar pozitif olmalı", None

            # %1 ücret hesapla
            fee = round(amount * FEE_PERCENT, 8)
            net_amount = round(amount - fee, 8)

            # Bakiye kontrolü
            sender_balance = self.get_balance(sender)
            if sender_balance < amount:
                return False, f"Yetersiz bakiye. Mevcut: {sender_balance:.8f}, Gerekli: {amount:.8f}", None

            # İşlemi oluştur
            tx = Transaction(
                sender=sender,
                receiver=receiver,
                amount=amount,
                fee=fee,
                signature=signature,
                tx_type="transfer"
            )

            # Bakiyeleri güncelle
            self.balances[sender] = round(self.balances[sender] - amount, 8)
            self.balances[receiver] = round(self.balances.get(receiver, 0) + net_amount, 8)
            self.balances[TREASURY_ADDRESS] = round(self.balances[TREASURY_ADDRESS] + fee, 8)

            self.pending_transactions.append(tx)
            self.total_transactions += 1
            self.total_fees_collected = round(self.total_fees_collected + fee, 8)

            if self.auto_mine:
                self._mine_block()

            tx_info = {
                "tx_hash": tx.hash(),
                "sender": sender,
                "receiver": receiver,
                "amount": amount,
                "fee": fee,
                "net_amount": net_amount
            }

            return True, f"İşlem başarılı! Gönderilen: {net_amount} BCT, Ücret: {fee} BCT", tx_info

    # ── Madencilik ────────────────────────────────────────
    def _mine_block(self) -> Optional[Block]:
        if not self.pending_transactions:
            return None

        block = Block(
            index=len(self.chain),
            transactions=list(self.pending_transactions),
            previous_hash=self.chain[-1].hash
        )
        block.mine(self.difficulty)
        self.chain.append(block)
        self.pending_transactions = []
        self._save_state()
        return block

    def mine_pending(self) -> Tuple[Optional[dict], str]:
        with self.lock:
            if not self.pending_transactions:
                return None, "Bekleyen işlem yok"
            block = self._mine_block()
            if block:
                return block.to_dict(), f"Blok #{block.index} başarıyla kazıldı! ({len(block.transactions)} işlem)"
            return None, "Madencilik başarısız"

    # ── Sorgular ──────────────────────────────────────────
    def get_balance(self, address: str) -> float:
        return self.balances.get(address, 0.0)

    def get_chain_data(self) -> list:
        return [block.to_dict() for block in self.chain]

    def get_latest_blocks(self, count: int = 10) -> list:
        blocks = self.chain[-count:]
        return [b.to_dict() for b in reversed(blocks)]

    def get_all_transactions(self) -> list:
        txs = []
        for block in self.chain:
            for tx in block.transactions:
                tx_dict = tx.to_dict()
                tx_dict["block_index"] = block.index
                txs.append(tx_dict)
        return list(reversed(txs))

    def get_wallet_transactions(self, address: str) -> list:
        txs = []
        for block in self.chain:
            for tx in block.transactions:
                if tx.sender == address or tx.receiver == address:
                    tx_dict = tx.to_dict()
                    tx_dict["block_index"] = block.index
                    txs.append(tx_dict)
        return list(reversed(txs))

    def get_wallet_list(self) -> list:
        result = []
        for addr, info in self.wallets.items():
            result.append({
                "address": addr,
                "balance": self.get_balance(addr),
                "created_at": info.get("created_at", 0)
            })
        return sorted(result, key=lambda x: x["created_at"], reverse=True)

    def is_chain_valid(self) -> bool:
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]
            if current.hash != current.calculate_hash():
                return False
            if current.previous_hash != previous.hash:
                return False
        return True

    def get_stats(self) -> dict:
        treasury_balance = self.balances.get(TREASURY_ADDRESS, 0)
        circulating = TOTAL_SUPPLY - treasury_balance
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

    # ── Kaydetme / Yükleme ────────────────────────────────
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
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[UYARI] Durum kaydedilemedi: {e}")

    def _load_state(self) -> bool:
        path = os.path.join(DATA_DIR, "blockchain.json")
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)

            self.balances = state["balances"]
            self.wallets = state.get("wallets", {})
            self.total_transactions = state.get("total_transactions", 0)
            self.total_fees_collected = state.get("total_fees_collected", 0.0)

            # Zinciri yeniden oluştur
            self.chain = []
            for block_data in state["chain"]:
                txs = []
                for tx_data in block_data["transactions"]:
                    tx = Transaction(
                        sender=tx_data["sender"],
                        receiver=tx_data["receiver"],
                        amount=tx_data["amount"],
                        fee=tx_data["fee"],
                        signature=tx_data["signature"],
                        timestamp=tx_data["timestamp"],
                        tx_type=tx_data.get("tx_type", "transfer")
                    )
                    txs.append(tx)
                block = Block(
                    index=block_data["index"],
                    transactions=txs,
                    previous_hash=block_data["previous_hash"],
                    timestamp=block_data["timestamp"],
                    nonce=block_data["nonce"]
                )
                block.hash = block_data["hash"]
                self.chain.append(block)

            print(f"[BİLGİ] Blockchain yüklendi: {len(self.chain)} blok, {len(self.wallets)} cüzdan")
            return True
        except Exception as e:
            print(f"[UYARI] Durum yüklenemedi: {e}")
            return False

    def reset(self):
        """Blockchain'i sıfırla (dikkatli kullanın!)."""
        with self.lock:
            self.chain = []
            self.pending_transactions = []
            self.balances = {TREASURY_ADDRESS: TOTAL_SUPPLY}
            self.wallets = {}
            self.total_transactions = 0
            self.total_fees_collected = 0.0
            self._create_genesis_block()
            return True, "Blockchain sıfırlandı!"

