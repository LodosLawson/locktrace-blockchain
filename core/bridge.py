"""
LockTrace (BCT) - Cross-Chain Bridge Engine
============================================
Manages 1:1 bidirectional bridging between LockTrace Layer-1 and EVM networks
(Base Mainnet, Arbitrum One, Ethereum, and Base Sepolia).
Enables seamless wrapping to wBCT and decentralized trading on Uniswap / PancakeSwap.
"""

import os
import sys
import math
import time
import json
import sqlite3
import hashlib
import logging
import contextlib
import urllib.request
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
from core.wallet import normalize_bct_address

logger = logging.getLogger("LockTrace.Bridge")

WBCT_OFFICIAL_CONTRACT = "0xCa6152Ae0E785F90ED65cd706B386E5B83D0EB28"
BURNED_TO_BRIDGE_TOPIC = "0x3275d83b87617ce084971fb014e237c81fb767cfb2fb708a12be7ec5a6c5afd0"
BASE_RPC_FALLBACKS = [
    "https://mainnet.base.org",
    "https://base-rpc.publicnode.com",
    "https://1rpc.io/base",
    "https://base.meowrpc.com"
]


def _call_base_rpc(payload: dict, primary_rpc: str = "https://mainnet.base.org", timeout: int = 10) -> Optional[Dict[str, Any]]:
    """Helper to query Base RPC with automatic failover across fallback endpoints."""
    endpoints = [primary_rpc] + [ep for ep in BASE_RPC_FALLBACKS if ep != primary_rpc]
    req_bytes = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "LockTraceBridge/2.0"}

    for ep in endpoints:
        try:
            req = urllib.request.Request(ep, data=req_bytes, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                res = json.loads(response.read().decode("utf-8"))
                if res and "result" in res:
                    return res
        except Exception as e:
            logger.debug(f"RPC {ep} attempt failed: {e}")
            continue
    return None


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

    res_data = _call_base_rpc(
        {"jsonrpc": "2.0", "method": "eth_getTransactionReceipt", "params": [clean_hash], "id": 1},
        primary_rpc=rpc_url or "https://mainnet.base.org",
        timeout=12
    )

    if not res_data:
        logger.warning(f"All Base RPC connections failed while verifying burn tx {clean_hash}")
        return False, "Failed to connect to Base Mainnet RPC endpoint.", {"network_error": True}

    receipt = res_data.get("result")
    if not receipt:
        return False, "Transaction not yet confirmed or found on Base Mainnet.", {}

    # 1. Check status == 0x1
    status = receipt.get("status")
    if str(status) not in ("0x1", "1"):
        return False, "EVM transaction failed or reverted.", {}

    # 2. Check destination contract (supports direct calls and EIP-7702 / ERC-4337 Smart Account bundlers
    #    where receipt.to is the bundler/paymaster and target_contract emits the log in receipt.logs)
    to_addr = str(receipt.get("to") or "").lower()
    logs = receipt.get("logs") or []
    has_contract_log = any(str(lg.get("address") or "").lower() == target_contract for lg in logs)
    if to_addr != target_contract and not has_contract_log:
        return False, f"Transaction was not sent to the official wBCT contract ({target_contract}).", {}

    # 2b. Check EVM confirmation depth + canonical blockHash (reorg protection - LT-02 Fail-Closed Hardening)
    receipt_block = receipt.get("blockNumber")
    receipt_block_hash = str(receipt.get("blockHash") or "").strip().lower()
    if not receipt_block:
        return False, "EVM blockNumber missing from transaction receipt.", {}
    if not (receipt_block_hash.startswith("0x") and len(receipt_block_hash) == 66):
        return False, "EVM blockHash missing or invalid in transaction receipt.", {}
    confs = 0
    try:
        rb_int = int(receipt_block, 16) if isinstance(receipt_block, str) and receipt_block.startswith("0x") else int(receipt_block)
        b_data = _call_base_rpc(
            {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 2},
            primary_rpc=rpc_url or "https://mainnet.base.org",
            timeout=8
        )
        if not b_data:
            return False, "Could not verify Base EVM confirmation depth; RPC failed.", {"network_error": True}
        latest_block = int(b_data.get("result", "0x0"), 16)
        confs = (latest_block - rb_int + 1) if latest_block >= rb_int else 0
        min_confs = int(os.environ.get("MIN_EVM_CONFIRMATIONS", "12"))
        if confs < min_confs:
            return False, f"EVM transaction has {confs} confirmation(s); at least {min_confs} required for reorg security.", {"confirmations": confs, "required": min_confs}

        # 2c. Verify receipt.blockHash matches the canonical Base block at receipt_block height
        canon_blk_res = _call_base_rpc(
            {"jsonrpc": "2.0", "method": "eth_getBlockByNumber", "params": [hex(rb_int), False], "id": 3},
            primary_rpc=rpc_url or "https://mainnet.base.org",
            timeout=8
        )
        canon_blk = (canon_blk_res or {}).get("result") if isinstance(canon_blk_res, dict) else None
        if not isinstance(canon_blk, dict) or not canon_blk.get("hash"):
            return False, "Could not verify canonical Base block hash; RPC failed.", {"network_error": True}
        canonical_hash = str(canon_blk.get("hash") or "").strip().lower()
        if canonical_hash != receipt_block_hash:
            logger.warning(f"Base reorg/hash mismatch for burn tx {clean_hash}: receipt={receipt_block_hash}, canonical={canonical_hash}")
            return False, "EVM receipt blockHash does not match canonical Base block (reorg protection).", {"reorg_detected": True}
    except Exception as e:
        logger.warning(f"Could not verify confirmation depth: {e}")
        return False, "Could not verify Base EVM confirmation depth; reorg guard failed.", {"network_error": True}

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

                # LT-SOL-02: Canonical address normalization (BCT prefix + lowercase hex)
                def _to_canonical_bct(addr: str) -> str:
                    s = (addr or "").strip()
                    if s.upper().startswith("BCT") and len(s) == 43:
                        return "BCT" + s[3:].lower()
                    return s

                canon_recip = _to_canonical_bct(recip_str)
                canon_expected = _to_canonical_bct(clean_recipient)
                expected_wei = int((Decimal(str(expected_amount)) * Decimal(10 ** 18)).to_integral_value())

                # Allow up to 10^10 wei (1e-8 BCT = 1 L1 atomic unit) tolerance against IEEE-754 float serialization drift
                if canon_recip == canon_expected and abs(amount_wei - expected_wei) <= 10 ** 10:
                    matched_event = {
                        "sender": sender_addr,
                        "amount_bct": float((Decimal(amount_wei) / Decimal(10 ** 18)).quantize(Decimal("0.00000001"))),
                        "recipient": canon_recip,
                        "block_number": receipt.get("blockNumber"),
                        "block_hash": canonical_hash,
                        "confirmations": confs,
                    }
                    break
            except Exception as ex:
                logger.debug(f"Failed decoding burn log: {ex}")

    if not matched_event:
        return False, (
            "Valid wBCT BurnedToBridge event matching recipient or amount was not found in transaction receipt."
        ), {}

    return True, "Verified", matched_event

_TRANSIENT_BRIDGE_MARKERS = (
    "pending", "mempool", "not yet", "confirmation", "reorg security",
    "network_error", "timeout", "timed out", "rpc", "connect",
    "insufficient locked balance", "bekleniyor",
)


def is_transient_bridge_error(msg: str) -> bool:
    """F-08: Errors that are retryable (unconfirmed / mempool / RPC / reserve) must never mark an order FAILED."""
    low = str(msg or "").lower()
    return any(k in low for k in _TRANSIENT_BRIDGE_MARKERS)


BRIDGE_VAULT_ADDRESS = "BCT_BRIDGE_VAULT_000000000000000000000000000000000"
SUPPORTED_CHAINS = {
    "base": {
        "name": "Base Mainnet (Coinbase L2)",
        "short_name": "Base Mainnet (8453)",
        "chain_id": 8453,
        "chain_id_hex": "0x2105",
        "is_testnet": False,
        "explorer": "https://basescan.org",
        "contract_address": WBCT_OFFICIAL_CONTRACT,
        "uniswap_url": f"https://app.uniswap.org/#/swap?chain=base&outputCurrency={WBCT_OFFICIAL_CONTRACT}",
        "uniswap_pool_url": "https://app.uniswap.org/#/pool?chain=base",
        "sourcify_url": f"https://repo.sourcify.dev/8453/{WBCT_OFFICIAL_CONTRACT}",
        "recommended": True
    },
    "base-sepolia": {
        "name": "Base Sepolia (Coinbase L2 Testnet)",
        "short_name": "Base Sepolia Testnet (84532)",
        "chain_id": 84532,
        "chain_id_hex": "0x14a34",
        "is_testnet": True,
        "explorer": "https://sepolia.basescan.org",
        "contract_address": WBCT_OFFICIAL_CONTRACT,
        "uniswap_url": "https://app.uniswap.org/#/swap?chain=base_sepolia",
        "recommended": False
    },
    "arbitrum": {
        "name": "Arbitrum One (L2)",
        "short_name": "Arbitrum One (42161)",
        "chain_id": 42161,
        "chain_id_hex": "0xa4b1",
        "is_testnet": False,
        "explorer": "https://arbiscan.io",
        "contract_address": "",
        "uniswap_url": "https://app.uniswap.org/#/swap?chain=arbitrum",
        "uniswap_pool_url": "https://app.uniswap.org/#/pool?chain=arbitrum",
        "recommended": False
    }
}

MIN_BRIDGE_AMOUNT = 15.00  # Temporary 2-way minimum bridge limit (15 BCT)
MAX_BRIDGE_AMOUNT = 50.00  # Temporary 2-way maximum bridge limit (50 BCT; will be lifted in the future)
BRIDGE_FEE_RATE = 0.002    # 0.2% bridge protocol fee (covers EVM gas costs)


class BridgeManager:
    def __init__(self, db_path: str = "blockchain.db"):
        self.db_path = db_path
        self._init_db()

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=15000;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

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
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_bridge_unique_evm_claim
                ON bridge_transactions (tx_hash_evm)
                WHERE direction = 'EVM_TO_L1' AND tx_hash_evm IS NOT NULL AND tx_hash_evm != '';
            """)
            try:
                conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_bridge_unique_l1_lock
                    ON bridge_transactions (lower(tx_hash_l1))
                    WHERE direction = 'L1_TO_EVM' AND tx_hash_l1 IS NOT NULL AND tx_hash_l1 != '';
                """)
            except sqlite3.IntegrityError:
                pass

    def get_bridge_config(self) -> Dict[str, Any]:
        """Returns public parameters, active contracts, and limits for the bridge."""
        raw_env = os.environ.get("WBCT_CONTRACT_ADDRESS", "").strip()
        deprecated = {
            "0xa3c743113a41cfd0146917065d4578337bb77254",
            "0x5e5d957b240c9e4a51613f58c6c242b710519b41",
        }
        contract_addr = (
            WBCT_OFFICIAL_CONTRACT
            if (not raw_env or raw_env.lower() in deprecated)
            else raw_env
        )
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

        clean_bct = normalize_bct_address(bct_address)
        clean_evm = (evm_address or "").strip().lower()

        if not (clean_bct.startswith("BCT") and len(clean_bct) == 43):
            return {"success": False, "error": "Invalid LockTrace BCT address format"}

        if not (clean_evm.startswith("0x") and len(clean_evm) == 42):
            return {"success": False, "error": "Invalid EVM destination address (0x... 42 chars required)"}

        if not isinstance(amount_bct, (int, float)) or not math.isfinite(amount_bct):
            return {"success": False, "error": "Bridge amount must be a finite number"}

        if amount_bct < MIN_BRIDGE_AMOUNT:
            return {"success": False, "error": f"Temporary bridge limit: minimum amount is {MIN_BRIDGE_AMOUNT:.2f} BCT (both directions; this limit will be lifted in the future)."}

        if amount_bct > MAX_BRIDGE_AMOUNT:
            return {"success": False, "error": f"Temporary bridge limit: maximum amount is {MAX_BRIDGE_AMOUNT:.2f} BCT per transfer (both directions; this limit will be lifted in the future)."}

        chain = chain.lower().strip()
        if chain not in SUPPORTED_CHAINS:
            chain = "base"

        fee = round(amount_bct * BRIDGE_FEE_RATE, 8)
        net = round(amount_bct - fee, 8)
        now = time.time()

        # Deduplication check: if order with this tx_hash already exists, validate direction match
        if tx_hash_evm:
            with self._get_connection() as conn:
                existing = conn.execute(
                    "SELECT * FROM bridge_transactions WHERE lower(tx_hash_evm) = lower(?) LIMIT 1",
                    (tx_hash_evm,)
                ).fetchone()
                if existing:
                    ex = dict(existing)
                    if str(ex.get("direction", "")).upper() != direction:
                        return {
                            "success": False,
                            "error": f"This EVM transaction hash already belongs to a {ex.get('direction')} order and cannot be used for {direction}."
                        }
                    return {"success": True, "data": ex}

        if tx_hash_l1:
            with self._get_connection() as conn:
                existing = conn.execute(
                    "SELECT * FROM bridge_transactions WHERE lower(tx_hash_l1) = lower(?) LIMIT 1",
                    (tx_hash_l1,)
                ).fetchone()
                if existing:
                    ex = dict(existing)
                    if (str(ex.get("bct_address", "")).lower() != clean_bct.lower()
                            or str(ex.get("evm_address", "")).lower() != clean_evm):
                        return {"success": False, "error": "This Layer-1 lock transaction is already bound to a different bridge order."}
                    return {"success": True, "data": ex}

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

