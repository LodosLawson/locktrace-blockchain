"""
LockTrace (BCT) - Cross-Chain Bridge Engine
============================================
Manages 1:1 bidirectional bridging between LockTrace Layer-1 and EVM networks
(Base Mainnet, Arbitrum One, Ethereum, and Base Sepolia).
Enables seamless wrapping to wBCT and decentralized trading on Uniswap / PancakeSwap.
"""

import os
import sys
import time
import json
import sqlite3
import hashlib
import logging
import urllib.request
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("LockTrace.Bridge")

WBCT_OFFICIAL_CONTRACT = "0xA3C743113a41cFd0146917065d4578337Bb77254"
BURNED_TO_BRIDGE_TOPIC = "0x3275d83b87617ce084971fb014e237c81fb767cfb2fb708a12be7ec5a6c5afd0"


def verify_evm_burn_receipt(
    evm_tx_hash: str,
    expected_recipient: str,
    expected_amount: float,
    rpc_url: str = "https://mainnet.base.org",
    wbct_contract: str = WBCT_OFFICIAL_CONTRACT
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Cryptographically verifies that an EVM transaction on Base Mainnet successfully executed
    and emitted a valid `BurnedToBridge(sender, amount, recipient)` event matching parameters.
    Prevents forged unlock claims on LockTrace Layer-1.
    """
    clean_hash = (evm_tx_hash or "").strip().lower()
    if not (clean_hash.startswith("0x") and len(clean_hash) == 66):
        return False, "Invalid EVM transaction hash (0x... 66 hex characters required).", {}

    target_contract = (wbct_contract or WBCT_OFFICIAL_CONTRACT).strip().lower()
    clean_recipient = (expected_recipient or "").strip()

    req_payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_getTransactionReceipt",
        "params": [clean_hash],
        "id": 1
    }).encode("utf-8")

    req = urllib.request.Request(
        rpc_url or "https://mainnet.base.org",
        data=req_payload,
        headers={"Content-Type": "application/json", "User-Agent": "LockTraceBridge/1.5"}
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            res_data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"Base RPC connection failed while verifying burn tx {clean_hash}: {e}")
        return False, f"Failed to connect to Base Mainnet RPC: {e}", {"network_error": True}

    receipt = res_data.get("result")
    if not receipt:
        return False, "Transaction not yet confirmed or found on Base Mainnet.", {}

    # 1. Check status == 0x1
    status = receipt.get("status")
    if str(status) not in ("0x1", "1"):
        return False, "EVM transaction failed or reverted.", {}

    # 2. Check destination contract
    to_addr = str(receipt.get("to") or "").lower()
    if to_addr != target_contract:
        return False, f"Transaction was not sent to the official wBCT contract ({target_contract}).", {}

    # 3. Find BurnedToBridge event in logs
    logs = receipt.get("logs") or []
    matched_event = None

    for log in logs:
        log_addr = str(log.get("address") or "").lower()
        if log_addr != target_contract:
            continue

        topics = log.get("topics") or []
        if len(topics) >= 2 and str(topics[0]).lower() == BURNED_TO_BRIDGE_TOPIC.lower():
            try:
                sender_addr = "0x" + str(topics[1])[-40:].lower()
                raw_data = str(log.get("data") or "")
                if raw_data.startswith("0x"):
                    raw_data = raw_data[2:]
                data_bytes = bytes.fromhex(raw_data)

                # Decode amount (first 32 bytes)
                amount_wei = int.from_bytes(data_bytes[0:32], "big")
                amount_bct = float(Decimal(amount_wei) / Decimal(10 ** 18))

                # Decode locktraceRecipient (dynamic string)
                str_offset = int.from_bytes(data_bytes[32:64], "big")
                str_len = int.from_bytes(data_bytes[str_offset:str_offset + 32], "big")
                recip_bytes = data_bytes[str_offset + 32:str_offset + 32 + str_len]
                recip_str = recip_bytes.decode("utf-8", errors="replace").strip()

                if recip_str == clean_recipient and abs(amount_bct - expected_amount) < 0.0001:
                    matched_event = {
                        "sender": sender_addr,
                        "amount_bct": amount_bct,
                        "recipient": recip_str,
                        "block_number": receipt.get("blockNumber")
                    }
                    break
            except Exception as ex:
                logger.debug(f"Failed decoding burn log: {ex}")

    if not matched_event:
        return False, (
            "Valid wBCT BurnedToBridge event matching recipient or amount was not found in transaction receipt."
        ), {}

    return True, "Verified", matched_event

BRIDGE_VAULT_ADDRESS = "BCT_BRIDGE_VAULT_000000000000000000000000000000000"
SUPPORTED_CHAINS = {
    "base": {
        "name": "Base Mainnet",
        "chain_id": 8453,
        "explorer": "https://basescan.org",
        "contract_address": WBCT_OFFICIAL_CONTRACT,
        "uniswap_url": f"https://app.uniswap.org/#/swap?chain=base&outputCurrency={WBCT_OFFICIAL_CONTRACT}",
        "uniswap_pool_url": "https://app.uniswap.org/#/pool?chain=base",
        "sourcify_url": f"https://repo.sourcify.dev/8453/{WBCT_OFFICIAL_CONTRACT}",
        "recommended": True
    },
    "arbitrum": {
        "name": "Arbitrum One",
        "chain_id": 42161,
        "explorer": "https://arbiscan.io",
        "contract_address": "",
        "uniswap_url": "https://app.uniswap.org/#/swap?chain=arbitrum",
        "uniswap_pool_url": "https://app.uniswap.org/#/pool?chain=arbitrum",
        "recommended": False
    },
    "base-sepolia": {
        "name": "Base Sepolia (Testnet)",
        "chain_id": 84532,
        "explorer": "https://sepolia.basescan.org",
        "contract_address": "",
        "uniswap_url": "https://app.uniswap.org/#/swap?chain=base_sepolia",
        "recommended": False
    }
}

MIN_BRIDGE_AMOUNT = 1.00   # Minimum 1 BCT
MAX_BRIDGE_AMOUNT = 1_000_000_000.0  # Cap per bridge operation (1 Billion BCT)
BRIDGE_FEE_RATE = 0.002    # 0.2% bridge protocol fee (covers EVM gas costs)


class BridgeManager:
    def __init__(self, db_path: str = "blockchain.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bridge_transactions (
                    bridge_id TEXT PRIMARY KEY,
                    direction TEXT NOT NULL,           -- L1_TO_EVM or EVM_TO_L1
                    status TEXT NOT NULL,              -- PENDING, LOCKED, MINTED, COMPLETED, FAILED
                    bct_address TEXT NOT NULL,
                    evm_address TEXT NOT NULL,
                    chain TEXT NOT NULL DEFAULT 'base',
                    amount_bct REAL NOT NULL,
                    fee_bct REAL NOT NULL DEFAULT 0.0,
                    net_amount REAL NOT NULL,
                    tx_hash_l1 TEXT,
                    tx_hash_evm TEXT,
                    voucher_sig TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    error_message TEXT
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_bridge_bct_addr ON bridge_transactions (bct_address);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_bridge_evm_addr ON bridge_transactions (evm_address);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_bridge_status ON bridge_transactions (status);
            """)

    def get_bridge_config(self) -> Dict[str, Any]:
        """Returns public parameters, active contracts, and limits for the bridge."""
        contract_addr = os.environ.get("WBCT_CONTRACT_ADDRESS", WBCT_OFFICIAL_CONTRACT)
        return {
            "bridge_vault_address": BRIDGE_VAULT_ADDRESS,
            "wbct_contract_address": contract_addr if contract_addr else WBCT_OFFICIAL_CONTRACT,
            "supported_chains": SUPPORTED_CHAINS,
            "default_chain": "base",
            "min_amount": MIN_BRIDGE_AMOUNT,
            "max_amount": MAX_BRIDGE_AMOUNT,
            "fee_rate": BRIDGE_FEE_RATE,
            "conversion_ratio": "1 BCT = 1 wBCT (1:1 Peg)",
            "operational": True
        }

    def create_bridge_order(
        self,
        direction: str,
        bct_address: str,
        evm_address: str,
        amount_bct: float,
        chain: str = "base",
        tx_hash_l1: str = "",
        tx_hash_evm: str = ""
    ) -> Dict[str, Any]:
        """
        Registers an intent or record to bridge BCT <-> wBCT.
        """
        direction = direction.upper().strip()
        if direction not in ("L1_TO_EVM", "EVM_TO_L1"):
            return {"success": False, "error": "Invalid bridge direction. Must be L1_TO_EVM or EVM_TO_L1"}

        clean_bct = bct_address.strip()
        clean_evm = evm_address.strip().lower()

        if not (clean_bct.startswith("BCT") and len(clean_bct) == 43):
            return {"success": False, "error": "Invalid LockTrace BCT address format"}

        if not (clean_evm.startswith("0x") and len(clean_evm) == 42):
            return {"success": False, "error": "Invalid EVM destination address (0x... 42 chars required)"}

        if amount_bct < MIN_BRIDGE_AMOUNT:
            return {"success": False, "error": f"Minimum bridge amount is {MIN_BRIDGE_AMOUNT:.2f} BCT"}

        if amount_bct > MAX_BRIDGE_AMOUNT:
            return {"success": False, "error": f"Maximum bridge amount is {MAX_BRIDGE_AMOUNT:,.0f} BCT per transaction"}

        chain = chain.lower().strip()
        if chain not in SUPPORTED_CHAINS:
            chain = "base"

        fee = round(amount_bct * BRIDGE_FEE_RATE, 8)
        net = round(amount_bct - fee, 8)
        now = time.time()

        # Deduplication check: if order with this tx_hash already exists, return existing order
        if tx_hash_evm:
            with self._get_connection() as conn:
                existing = conn.execute(
                    "SELECT * FROM bridge_transactions WHERE tx_hash_evm = ? LIMIT 1",
                    (tx_hash_evm,)
                ).fetchone()
                if existing:
                    return {"success": True, "data": dict(existing)}

        if tx_hash_l1:
            with self._get_connection() as conn:
                existing = conn.execute(
                    "SELECT * FROM bridge_transactions WHERE tx_hash_l1 = ? LIMIT 1",
                    (tx_hash_l1,)
                ).fetchone()
                if existing:
                    return {"success": True, "data": dict(existing)}

        # Generate unique deterministic bridge identifier
        seed_str = f"{direction}:{clean_bct}:{clean_evm}:{amount_bct}:{now}:{os.urandom(8).hex()}"
        bridge_id = f"brg_{hashlib.sha256(seed_str.encode('utf-8')).hexdigest()[:24]}"

        if direction == "EVM_TO_L1":
            status = "BURNED" if tx_hash_evm else "PENDING"
        else:
            status = "LOCKED" if tx_hash_l1 else "PENDING"

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO bridge_transactions (
                    bridge_id, direction, status, bct_address, evm_address, chain,
                    amount_bct, fee_bct, net_amount, tx_hash_l1, tx_hash_evm,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bridge_id, direction, status, clean_bct, clean_evm, chain,
                amount_bct, fee, net, tx_hash_l1 or None, tx_hash_evm or None,
                now, now
            ))

        return {
            "success": True,
            "data": {
                "bridge_id": bridge_id,
                "direction": direction,
                "status": status,
                "bct_address": clean_bct,
                "evm_address": clean_evm,
                "chain": chain,
                "amount_bct": amount_bct,
                "fee_bct": fee,
                "net_amount": net,
                "bridge_vault_address": BRIDGE_VAULT_ADDRESS,
                "instructions": (
                    f"Send exactly {amount_bct:.8f} BCT to bridge vault '{BRIDGE_VAULT_ADDRESS}' "
                    f"with extra_data.bridge_id = '{bridge_id}' to complete the lock."
                    if direction == "L1_TO_EVM" and not tx_hash_l1 else
                    "Transaction registered. Processing verification."
                )
            }
        }

    def confirm_l1_lock(self, bridge_id: str, tx_hash_l1: str) -> Dict[str, Any]:
        """Marks Layer-1 lock as confirmed after on-chain block inclusion."""
        clean_hash = (tx_hash_l1 or "").strip().lower()
        if not clean_hash:
            return {"success": False, "error": "Valid Layer-1 transaction hash is required"}

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM bridge_transactions WHERE bridge_id = ?", (bridge_id,)).fetchone()
            if not row:
                return {"success": False, "error": "Bridge transaction not found"}
            if row["direction"] != "L1_TO_EVM":
                return {"success": False, "error": "Invalid bridge direction for L1 lock confirmation"}
            if row["status"] in ("COMPLETED", "FAILED"):
                return {"success": False, "error": f"Bridge order is already {row['status']}"}

            dup = conn.execute(
                "SELECT bridge_id FROM bridge_transactions WHERE lower(tx_hash_l1) = ? AND bridge_id != ? LIMIT 1",
                (clean_hash, bridge_id)
            ).fetchone()
            if dup:
                return {"success": False, "error": "This Layer-1 transaction hash is already bound to another bridge order"}

            conn.execute("""
                UPDATE bridge_transactions
                SET status = 'LOCKED', tx_hash_l1 = ?, updated_at = ?
                WHERE bridge_id = ?
            """, (clean_hash, time.time(), bridge_id))

        return {"success": True, "bridge_id": bridge_id, "status": "LOCKED"}

    def complete_bridge(self, bridge_id: str, tx_hash_evm: str = "") -> Dict[str, Any]:
        """Finalizes bridge order after wBCT mint or unlock."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM bridge_transactions WHERE bridge_id = ?", (bridge_id,)).fetchone()
            if not row:
                return {"success": False, "error": "Bridge transaction not found"}

            conn.execute("""
                UPDATE bridge_transactions
                SET status = 'COMPLETED', tx_hash_evm = coalesce(?, tx_hash_evm), updated_at = ?
                WHERE bridge_id = ?
            """, (tx_hash_evm or None, time.time(), bridge_id))

        return {"success": True, "bridge_id": bridge_id, "status": "COMPLETED"}

    def get_bridge_status(self, bridge_id: str) -> Optional[Dict[str, Any]]:
        """Queries the live status and details of a bridge operation."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM bridge_transactions WHERE bridge_id = ?", (bridge_id,)).fetchone()
            if not row:
                return None
            return dict(row)

    def get_history_by_address(self, address: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieves recent bridge orders for a given BCT or EVM address."""
        clean = address.strip().lower()
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM bridge_transactions
                WHERE lower(bct_address) = ? OR lower(evm_address) = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (clean, clean, limit)).fetchall()
            return [dict(r) for r in rows]

    def get_all_transactions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves recent cross-chain bridge and Base L2 wBCT operations."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM bridge_transactions
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

