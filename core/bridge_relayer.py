"""
LockTrace (BCT) - Automated Cross-Chain Bridge Relayer
======================================================
Monitors verified Layer-1 lock transactions in `blockchain.db`
and automatically broadcasts `mintFromBridge` transactions on Base Mainnet.
"""

import os
import sys
import time
import json
import sqlite3
import logging
import re
from decimal import Decimal
from typing import Dict, Any, Optional
try:
    from web3 import Web3
    HAS_WEB3 = True
except ImportError:
    Web3 = None
    HAS_WEB3 = False

logger = logging.getLogger("LockTrace.Relayer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

BASE_RPC_URL = os.environ.get("BASE_RPC_URL", "https://mainnet.base.org")
WBCT_CONTRACT = os.environ.get("WBCT_CONTRACT_ADDRESS", "0xA3C743113a41cFd0146917065d4578337Bb77254")
# AUD17B-06: Prioritize active data/blockchain.db over bare root paths
_default_db = "/opt/blockchaint/data/blockchain.db" if os.path.exists("/opt/blockchaint/data/blockchain.db") else (
    "/opt/blockchaint/blockchain.db" if os.path.exists("/opt/blockchaint/blockchain.db") else (
        "data/blockchain.db" if os.path.exists("data/blockchain.db") else "blockchain.db"
    )
)
DB_PATH = os.environ.get("BCT_DB_PATH", _default_db)
RELAYER_KEY_PATH = os.environ.get("RELAYER_KEY_PATH", "/opt/blockchaint/relayer_wallet.json")
CHAIN_ID = 8453  # Base Mainnet

try:
    from core.bridge import is_transient_bridge_error
except Exception:  # standalone execution fallback
    def is_transient_bridge_error(msg: str) -> bool:
        low = str(msg or "").lower()
        return any(k in low for k in ("pending", "mempool", "not yet", "confirmation", "reorg security",
                                      "network_error", "timeout", "rpc", "connect", "insufficient locked balance"))

# F-06: relayer-side mint guardrails (mirrors WrappedBCT.sol maxMintPerTx / dailyMintLimit)
MAX_MINT_PER_TX_BCT = Decimal(os.environ.get("MAX_MINT_PER_TX_BCT", "1000000"))
DAILY_MINT_LIMIT_BCT = Decimal(os.environ.get("DAILY_MINT_LIMIT_BCT", "5000000"))

WBCT_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "string", "name": "locktraceTxHash", "type": "string"}
        ],
        "name": "mintFromBridge",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "string", "name": "txHashStr", "type": "string"}],
        "name": "processedL1Transactions",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "relayer", "type": "address"}],
        "name": "isBridgeRelayer",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "sender", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
            {"indexed": False, "internalType": "string", "name": "locktraceRecipient", "type": "string"}
        ],
        "name": "BurnedToBridge",
        "type": "event"
    }
]


class BridgeRelayer:
    def __init__(self, db_path: str = DB_PATH, key_path: str = RELAYER_KEY_PATH):
        self.db_path = db_path
        self.key_path = key_path
        if not HAS_WEB3:
            self.w3 = None
            self.contract = None
            self.account = None
            logger.info("web3 library not installed. BridgeRelayer is inactive on this standard node.")
            return
        self.w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL, request_kwargs={"headers": {"User-Agent": "Mozilla/5.0"}}))
        self.contract = self.w3.eth.contract(address=Web3.to_checksum_address(WBCT_CONTRACT), abi=WBCT_ABI)
        self.account = self._load_or_create_wallet()

    def _load_or_create_wallet(self):
        from eth_account import Account
        # 1. Environment variable (Highest priority & zero-leakage)
        env_pk = os.environ.get("BCT_RELAYER_PRIVATE_KEY", "").strip()
        if env_pk:
            if not env_pk.startswith("0x") and len(env_pk) == 64:
                env_pk = "0x" + env_pk
            try:
                acct = Account.from_key(env_pk)
                logger.info(f"Loaded Bridge Relayer wallet from BCT_RELAYER_PRIVATE_KEY: {acct.address}")
                return acct
            except Exception as e:
                logger.error(f"Failed to load relayer key from environment variable: {e}")
                return None

        # 2. File path if explicitly configured and exists
        if self.key_path and os.path.exists(self.key_path):
            try:
                with open(self.key_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                pk = data.get("private_key", "").strip()
                if not pk.startswith("0x") and len(pk) == 64:
                    pk = "0x" + pk
                acct = Account.from_key(pk)
                logger.info(f"Loaded Bridge Relayer wallet from file {self.key_path}: {acct.address}")
                return acct
            except Exception as e:
                logger.error(f"Failed to load key from {self.key_path}: {e}")
                return None

        # 3. Fallback: Never auto-generate or write sensitive keys to disk on arbitrary nodes
        logger.info("No bridge relayer key configured (BCT_RELAYER_PRIVATE_KEY). Running in standard node mode.")
        return None

    def get_status(self) -> Dict[str, Any]:
        """Returns relayer health, balance, and authorization status."""
        # AUD17B-05: Guard against NoneType AttributeError if web3 library is missing or disconnected
        if not HAS_WEB3 or self.w3 is None:
            return {
                "status": "disabled",
                "message": "web3 library not available or initialized. Bridge relayer is inactive.",
                "contract_address": WBCT_CONTRACT,
                "connected": False
            }
        if not self.account:
            return {
                "status": "disabled",
                "message": "Relayer private key not set. Bridge relayer is inactive on this node.",
                "contract_address": WBCT_CONTRACT,
                "connected": bool(self.w3.is_connected()) if self.w3 else False
            }
        try:
            bal_wei = self.w3.eth.get_balance(self.account.address)
            bal_eth = self.w3.from_wei(bal_wei, "ether")
            is_auth = self.contract.functions.isBridgeRelayer(self.account.address).call()
            owner = self.contract.functions.owner().call()
            return {
                "relayer_address": self.account.address,
                "eth_balance": float(bal_eth),
                "is_authorized": bool(is_auth or (self.account.address.lower() == owner.lower())),
                "contract_owner": owner,
                "contract_address": WBCT_CONTRACT,
                "connected": self.w3.is_connected()
            }
        except Exception as e:
            logger.error(f"Failed to fetch relayer status: {e}")
            return {"error": "Failed to fetch relayer status", "relayer_address": self.account.address}

    def process_pending_locks(self) -> int:
        """Finds all verified L1 locked orders that haven't been minted on EVM yet."""
        if not self.account:
            return 0
        if not os.path.exists(self.db_path):
            return 0

        # Check relayer ETH balance on Base Mainnet first
        try:
            bal_wei = self.w3.eth.get_balance(self.account.address)
            if bal_wei < self.w3.to_wei(0.00005, "ether"):
                bal_eth = float(self.w3.from_wei(bal_wei, "ether"))
                logger.warning(
                    f"Relayer has low ETH balance ({bal_eth:.8f} ETH). "
                    f"Base gas requires ~0.0001 ETH. Please fund {self.account.address} with Base ETH to resume automatic minting."
                )
                return 0
        except Exception as e:
            logger.error(f"Failed to check relayer balance: {e}")
            return 0

        self._recheck_stalled_locks()

        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        
        try:
            rows = conn.execute("""
                SELECT bridge_id, direction, status, bct_address, evm_address,
                       net_amount, tx_hash_l1, created_at
                FROM bridge_transactions
                WHERE status = 'LOCKED'
                  AND direction = 'L1_TO_EVM'
                  AND (tx_hash_evm IS NULL OR tx_hash_evm = '')
                  AND tx_hash_l1 IS NOT NULL
                ORDER BY created_at ASC
                LIMIT 10
            """).fetchall()
        finally:
            conn.close()

        if not rows:
            return 0

        logger.info(f"Found {len(rows)} pending bridge lock(s) awaiting Base EVM mint.")
        processed = 0

        for r in rows:
            bridge_id = r["bridge_id"]
            evm_dest = r["evm_address"]
            l1_hash = str(r["tx_hash_l1"] or "").strip()
            clean_l1 = l1_hash.lower().removeprefix("0x")

            # AUD19-01: Validate L1 tx hash format (must be 64 hex characters)
            if not re.fullmatch(r"[0-9a-f]{64}", clean_l1):
                logger.error(f"Bridge {bridge_id}: Invalid tx_hash_l1 format ({l1_hash}). Marking FAILED to unblock queue.")
                self._mark_failed(bridge_id, "Geçersiz L1 işlem özeti formatı (64-hex karakter bekleniyor).")
                continue

            # AUD17B-06 & AUD19-01: Direct Decimal parsing with non-positive guard
            try:
                net_amt_dec = Decimal(str(r["net_amount"]))
            except Exception:
                net_amt_dec = Decimal("0")

            if net_amt_dec <= Decimal("0"):
                logger.error(f"Bridge {bridge_id}: Non-positive net amount ({net_amt_dec}). Marking FAILED to unblock queue.")
                self._mark_failed(bridge_id, "Geçersiz veya sıfır köprü kilit tutarı.")
                continue

            amt_wei = int((net_amt_dec * Decimal(10 ** 18)).to_integral_value())
            if amt_wei <= 0:
                logger.error(f"Bridge {bridge_id}: amt_wei <= 0 after 18-decimal conversion. Marking FAILED.")
                self._mark_failed(bridge_id, "Geçersiz veya sıfır wei tutarı.")
                continue

            # F-06: per-transaction cap -> human review; rolling 24h cap -> defer
            if net_amt_dec > MAX_MINT_PER_TX_BCT:
                logger.error(f"Bridge {bridge_id}: {net_amt_dec} BCT exceeds per-tx mint cap {MAX_MINT_PER_TX_BCT}. HELD for manual review.")
                self._set_status(bridge_id, "HELD", f"Amount exceeds per-transaction mint cap ({MAX_MINT_PER_TX_BCT} BCT); manual approval required.")
                continue
            if self._minted_last_24h() + net_amt_dec > DAILY_MINT_LIMIT_BCT:
                logger.warning(f"Bridge {bridge_id}: rolling 24h mint cap {DAILY_MINT_LIMIT_BCT} BCT reached. Deferring.")
                continue

            # L1 Finality Verification: Ensure lock transaction is sealed in an attested/deep block
            # AUD17B-05: Ensure check_conn is safely closed in a finally block
            check_conn = None
            try:
                check_conn = sqlite3.connect(self.db_path, timeout=10.0)
                check_conn.row_factory = sqlite3.Row
                tx_row = check_conn.execute("SELECT block_index FROM tx_lookup WHERE tx_hash = ?", (l1_hash,)).fetchone()
                if not tx_row:
                    age = time.time() - float(r["created_at"] or 0)
                    if age > 7200:
                        # N-01: park (do NOT fail) so a late-sealed lock is still minted; re-checked every cycle
                        logger.warning(f"Bridge {bridge_id}: L1 lock tx {clean_l1[:16]} not sealed after {int(age)}s. Parking as STALLED (auto-retry).")
                        self._set_status(bridge_id, "STALLED", "L1 lock not yet sealed; will auto-resume once confirmed.")
                    else:
                        logger.info(f"Bridge {bridge_id}: L1 lock tx {clean_l1[:16]}... not yet sealed in a block. Deferring mint.")
                    continue
                l1_b_idx = tx_row["block_index"]
                att_c = check_conn.execute("SELECT COUNT(*) AS c FROM block_attestations WHERE block_index = ?", (l1_b_idx,)).fetchone()["c"]
                max_row = check_conn.execute("SELECT MAX(block_index) AS tip FROM blocks").fetchone()
                tip_b = max_row["tip"] if max_row and max_row["tip"] is not None else l1_b_idx
                depth = tip_b - l1_b_idx

                # LT-02 Hardening: Strict L1 confirmation depth & validator finality guard
                is_finalized = (att_c >= 2 and depth >= 4) or depth >= 8
                if not is_finalized:
                    logger.info(f"Bridge {bridge_id}: Block #{l1_b_idx} awaiting full L1 finality (attestations: {att_c}/2, depth: {depth}/8). Deferring mint.")
                    continue
            except Exception as _f_err:
                logger.warning(f"Could not verify L1 finality for {bridge_id}: {_f_err}. Deferring mint.")
                continue
            finally:
                if check_conn:
                    try:
                        check_conn.close()
                    except Exception:
                        pass

            # Validate destination
            if not Web3.is_address(evm_dest) or evm_dest.lower() == WBCT_CONTRACT.lower():
                logger.warning(f"Rejecting bridge {bridge_id}: invalid destination or token contract address ({evm_dest})")
                self._mark_failed(bridge_id, "Geçersiz EVM adresi veya kontrat adresine gönderim yapılamaz.")
                continue

            logger.info(f"Minting {net_amt_dec} wBCT to {evm_dest} (L1 Hash: {l1_hash})...")
            tx_evm = self._mint_on_base(evm_dest, amt_wei, l1_hash)

            if tx_evm:
                if tx_evm == "ALREADY_PROCESSED_ON_CHAIN":
                    self._mark_completed(bridge_id, "PREVIOUSLY_MINTED_ON_BASE")
                else:
                    self._mark_completed(bridge_id, tx_evm)
                processed += 1
                logger.info(f"Bridge {bridge_id} SUCCESS! Base Tx: {tx_evm}")

        return processed

    def _mint_on_base(self, to_address: str, amount_wei: int, l1_tx_hash: str) -> Optional[str]:
        try:
            # AUD18-04: Nonce & gas protection against non-positive amount
            if amount_wei <= 0:
                logger.error(f"Invalid amount_wei ({amount_wei}) for mint on Base. Aborting broadcast.")
                return None

            dest = Web3.to_checksum_address(to_address)
            clean_l1_hash = str(l1_tx_hash or "").strip().lower().removeprefix("0x")

            # AUD17B-01: Check if already processed on contract before spending any gas
            try:
                if hasattr(self.contract.functions, "processedL1Transactions"):
                    is_already_processed = self.contract.functions.processedL1Transactions(clean_l1_hash).call()
                    if is_already_processed:
                        logger.warning(f"L1 tx {clean_l1_hash[:16]} already marked processed on WrappedBCT. Skipping mint to avoid revert & gas drain.")
                        return "ALREADY_PROCESSED_ON_CHAIN"
            except Exception as check_err:
                logger.debug(f"Could not check processedL1Transactions on contract: {check_err}")

            fn = self.contract.functions.mintFromBridge(dest, amount_wei, clean_l1_hash)

            # AUD17B-01: Estimate gas to verify transaction will succeed before broadcasting
            try:
                estimated_gas = fn.estimate_gas({"from": self.account.address})
                gas_limit = min(int(estimated_gas * 1.3) + 15_000, 300_000)
            except Exception as est_err:
                logger.error(f"Gas estimation failed for mintFromBridge (revert expected, aborted broadcast): {est_err}")
                return None

            nonce = self.w3.eth.get_transaction_count(self.account.address, "pending")
            
            # Fetch current Base fees (Base uses EIP-1559)
            base_fee = self.w3.eth.get_block("latest")["baseFeePerGas"]
            priority_fee = self.w3.to_wei(0.001, "gwei")  # 0.001 Gwei priority on Base
            max_fee = int(base_fee * 1.5) + priority_fee

            tx = fn.build_transaction({
                "chainId": CHAIN_ID,
                "from": self.account.address,
                "nonce": nonce,
                "maxFeePerGas": max_fee,
                "maxPriorityFeePerGas": priority_fee,
                "gas": gas_limit
            })

            signed = self.account.sign_transaction(tx)
            raw_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            raw_hex = raw_hash.hex()
            # AUD18-04: Canonical 0x prefix enforcement on EVM transaction hash
            tx_hash_hex = raw_hex if raw_hex.startswith("0x") else f"0x{raw_hex}"
            logger.info(f"Submitted Base Tx: https://basescan.org/tx/{tx_hash_hex}")

            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(raw_hash, timeout=30)
            if receipt["status"] == 1:
                return tx_hash_hex
            else:
                logger.error(f"Base transaction failed or reverted: {tx_hash_hex}")
                return None

        except Exception as e:
            logger.error(f"Error executing mint on Base: {e}")
            return None

    def _set_status(self, bridge_id: str, status: str, note: str = ""):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            with conn:
                conn.execute(
                    "UPDATE bridge_transactions SET status = ?, error_message = ?, updated_at = ? WHERE bridge_id = ?",
                    (status, str(note)[:255] or None, time.time(), bridge_id))
        finally:
            conn.close()

    def _minted_last_24h(self) -> Decimal:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            rows = conn.execute(
                "SELECT net_amount FROM bridge_transactions WHERE direction = 'L1_TO_EVM' "
                "AND status = 'COMPLETED' AND updated_at >= ?", (time.time() - 86400,)).fetchall()
            return sum((Decimal(str(r[0] or 0)) for r in rows), Decimal("0"))
        finally:
            conn.close()

    def _recheck_stalled_locks(self):
        """N-01: resume STALLED orders once their L1 lock tx has been sealed in a block."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            rows = conn.execute(
                "SELECT bridge_id, tx_hash_l1 FROM bridge_transactions WHERE status = 'STALLED' "
                "AND direction = 'L1_TO_EVM' AND tx_hash_l1 IS NOT NULL ORDER BY created_at ASC LIMIT 50").fetchall()
            for bid, h in rows:
                if conn.execute("SELECT 1 FROM tx_lookup WHERE tx_hash = ?", (h,)).fetchone():
                    with conn:
                        conn.execute(
                            "UPDATE bridge_transactions SET status = 'LOCKED', error_message = NULL, updated_at = ? "
                            "WHERE bridge_id = ?", (time.time(), bid))
                    logger.info(f"Bridge {bid}: stalled lock now sealed on L1. Re-queued for mint.")
        except Exception as e:
            logger.warning(f"Stalled lock recheck failed: {e}")
        finally:
            conn.close()

    def _mark_completed(self, bridge_id: str, tx_hash_evm: str):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            with conn:
                conn.execute("""
                    UPDATE bridge_transactions
                    SET status = 'COMPLETED', tx_hash_evm = ?, updated_at = ?
                    WHERE bridge_id = ?
                """, (tx_hash_evm, time.time(), bridge_id))
        finally:
            conn.close()

    def _mark_failed(self, bridge_id: str, error_message: str):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            with conn:
                conn.execute("""
                    UPDATE bridge_transactions
                    SET status = 'FAILED', error_message = ?, updated_at = ?
                    WHERE bridge_id = ?
                """, (str(error_message)[:255], time.time(), bridge_id))
        finally:
            conn.close()

    def process_pending_burns(self) -> int:
        """Finds EVM_TO_L1 bridge orders that need L1 unlock."""
        if not os.path.exists(self.db_path):
            return 0

        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT bridge_id, direction, status, bct_address, evm_address,
                       amount_bct, net_amount, tx_hash_evm
                FROM bridge_transactions
                WHERE status IN ('BURNED', 'PENDING')
                  AND direction = 'EVM_TO_L1'
                  AND tx_hash_evm IS NOT NULL AND tx_hash_evm != ''
                ORDER BY created_at ASC
                LIMIT 10
            """).fetchall()
        finally:
            conn.close()

        if not rows:
            return 0

        logger.info(f"Processing up to {len(rows)} pending EVM burn(s) for LockTrace L1 unlock.")
        processed = 0

        import urllib.request
        for r in rows:
            bridge_id = r["bridge_id"]
            bct_dest = str(r["bct_address"] or "").strip()
            if bct_dest.upper().startswith("BCT") and len(bct_dest) == 43:
                bct_dest = "BCT" + bct_dest[3:].lower()

            # AUD19-02: Precise Decimal parsing without float IEEE-754 precision loss or zero fallback bugs
            raw_net = r["net_amount"]
            raw_gross = r["amount_bct"]
            val_to_parse = raw_net if (raw_net is not None and str(raw_net).strip() != "") else raw_gross
            try:
                amt_dec = Decimal(str(val_to_parse).strip())
            except Exception:
                amt_dec = Decimal("0")

            if amt_dec <= Decimal("0"):
                logger.error(f"Bridge {bridge_id}: Invalid or zero burn net amount ({amt_dec}). Marking FAILED to unblock queue.")
                self._mark_failed(bridge_id, "Geçersiz veya sıfır köprü çekim tutarı.")
                continue

            amt = float(amt_dec)
            evm_hash = r["tx_hash_evm"]
            evm_sender = r["evm_address"]

            # Defense-in-depth: Reject malformed or zero burn address on L1 unlock
            if not re.match(r"^BCT[0-9a-fA-F]{40}$", bct_dest) or re.match(r"^BCT0{40}$", bct_dest, re.IGNORECASE):
                logger.error(f"Bridge {bridge_id}: Invalid or reserved BCT destination address ({bct_dest}). Aborting automatic unlock.")
                self._mark_failed(bridge_id, "FAILED_INVALID_RECIPIENT: Recipient BCT address is invalid or reserved burn address. Manual admin review required.")
                continue

            try:
                # AUD18-04: Configurable API URL for bridge claim calls
                api_base = os.environ.get("LOCKTRACE_API_URL", "http://127.0.0.1:5000").rstrip("/")
                req_data = json.dumps({
                    "evm_tx_hash": evm_hash,
                    "bct_address": bct_dest,
                    "amount": amt,
                    "evm_sender": evm_sender
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"{api_base}/api/v1/bridge/claim_burn",
                    data=req_data,
                    headers={"Content-Type": "application/json"}
                )
                import urllib.error
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        resp_json = json.loads(resp.read().decode("utf-8"))
                        if resp_json.get("success"):
                            self._mark_completed(bridge_id, evm_hash)
                            processed += 1
                            logger.info(f"Bridge {bridge_id} EVM->L1 unlock SUCCESS: {amt} BCT to {bct_dest}")
                        else:
                            msg = str(resp_json.get("message", ""))
                            if "daha önce" in msg or "already" in msg:
                                self._mark_completed(bridge_id, evm_hash)
                                logger.info(f"Bridge {bridge_id} was already processed on L1. Marked COMPLETED.")
                            elif is_transient_bridge_error(msg):
                                # AUD18-02: Do NOT mark FAILED if awaiting EVM confirmation depth
                                logger.info(f"Bridge {bridge_id}: Awaiting confirmations ({msg[:120]}). Deferring.")
                            else:
                                self._mark_failed(bridge_id, msg)
                                logger.warning(f"Bridge {bridge_id} unlock rejected: {msg}")
                except urllib.error.HTTPError as http_err:
                    err_body = ""
                    try:
                        err_body = http_err.read().decode("utf-8")
                    except Exception:
                        pass
                    logger.error(f"Bridge {bridge_id} claim_burn HTTP {http_err.code}: {err_body}")
                    msg = err_body
                    try:
                        err_json = json.loads(err_body)
                        msg = err_json.get("message", err_body)
                    except Exception:
                        pass
                    if "daha önce" in msg or "already" in msg:
                        self._mark_completed(bridge_id, evm_hash)
                    elif http_err.code in (400, 422):
                        # AUD18-02: Do NOT mark FAILED if transaction is waiting for EVM confirmations or temporary network/reorg state
                        is_pending_conf = is_transient_bridge_error(msg)
                        if is_pending_conf:
                            logger.info(f"Bridge {bridge_id}: EVM tx {evm_hash[:16]} awaiting required confirmations ({msg[:120]}). Deferring.")
                        else:
                            # AUD17B-04: Mark genuinely unrecoverable HTTP 400/422 requests as FAILED to prevent queue blockage
                            self._mark_failed(bridge_id, f"HTTP_{http_err.code}: {msg[:200]}")
                    time.sleep(1.0)
                except Exception as e:
                    logger.error(f"Failed to process EVM burn {bridge_id}: {e}")
                    time.sleep(2.0)
            except Exception as e:
                logger.error(f"Error preparing EVM burn payload for {bridge_id}: {e}")

        return processed


def run_daemon(interval_seconds: int = 10):
    relayer = BridgeRelayer()
    status = relayer.get_status()
    print("=========================================================")
    print(" LOCKTRACE AUTOMATED BRIDGE RELAYER (BASE MAINNET)")
    print("=========================================================")
    print(f" Relayer Address   : {status.get('relayer_address')}")
    print(f" ETH Balance       : {status.get('eth_balance', 0):.6f} ETH")
    print(f" Is Authorized     : {status.get('is_authorized')}")
    print(f" Contract Address  : {status.get('contract_address')}")
    print("=========================================================")

    if not status.get("is_authorized"):
        print("\n [!] ACTION REQUIRED: The relayer wallet is NOT authorized yet!")
        print(f" Please run `setBridgeRelayer('{status.get('relayer_address')}', true)` in Remix from Owner.")

    while True:
        try:
            relayer.process_pending_locks()
            relayer.process_pending_burns()
        except Exception as ex:
            logger.error(f"Relayer loop error: {ex}")
        time.sleep(interval_seconds)



if __name__ == "__main__":
    run_daemon()

