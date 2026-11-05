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
from decimal import Decimal
from typing import Dict, Any, Optional
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

logger = logging.getLogger("LockTrace.Relayer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

BASE_RPC_URL = os.environ.get("BASE_RPC_URL", "https://mainnet.base.org")
WBCT_CONTRACT = os.environ.get("WBCT_CONTRACT_ADDRESS", "0xA3C743113a41cFd0146917065d4578337Bb77254")
DB_PATH = os.environ.get("BCT_DB_PATH", "/opt/blockchaint/blockchain.db")
RELAYER_KEY_PATH = os.environ.get("RELAYER_KEY_PATH", "/opt/blockchaint/relayer_wallet.json")
CHAIN_ID = 8453  # Base Mainnet

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
        self.w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL, request_kwargs={"headers": {"User-Agent": "Mozilla/5.0"}}))
        self.contract = self.w3.eth.contract(address=Web3.to_checksum_address(WBCT_CONTRACT), abi=WBCT_ABI)
        self.account = self._load_or_create_wallet()

    def _load_or_create_wallet(self):
        from eth_account import Account
        if os.path.exists(self.key_path):
            with open(self.key_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Account.from_key(data["private_key"])
        else:
            acct = Account.create()
            data = {"address": acct.address, "private_key": acct.key.hex()}
            os.makedirs(os.path.dirname(os.path.abspath(self.key_path)), exist_ok=True)
            with open(self.key_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            try:
                os.chmod(self.key_path, 0o600)
            except Exception:
                pass
            logger.info(f"Generated new Bridge Relayer wallet: {acct.address}")
            return acct

    def get_status(self) -> Dict[str, Any]:
        """Returns relayer health, balance, and authorization status."""
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
            return {"error": str(e), "relayer_address": self.account.address}

    def process_pending_locks(self) -> int:
        """Finds all verified L1 locked orders that haven't been minted on EVM yet."""
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

        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        
        try:
            rows = conn.execute("""
                SELECT bridge_id, direction, status, bct_address, evm_address,
                       net_amount, tx_hash_l1
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
            net_amt = float(r["net_amount"])
            l1_hash = r["tx_hash_l1"]

            # Validate destination
            if not Web3.is_address(evm_dest) or evm_dest.lower() == WBCT_CONTRACT.lower():
                logger.warning(f"Rejecting bridge {bridge_id}: invalid destination or token contract address ({evm_dest})")
                self._mark_failed(bridge_id, "Geçersiz EVM adresi veya kontrat adresine gönderim yapılamaz.")
                continue

            # Exact amount in 18 decimals (immune to float64 IEEE-754 drift)
            amt_wei = int((Decimal(str(net_amt)) * Decimal(10 ** 18)).to_integral_value())

            logger.info(f"Minting {net_amt} wBCT to {evm_dest} (L1 Hash: {l1_hash})...")
            tx_evm = self._mint_on_base(evm_dest, amt_wei, l1_hash)

            if tx_evm:
                self._mark_completed(bridge_id, tx_evm)
                processed += 1
                logger.info(f"Bridge {bridge_id} SUCCESS! Base Tx: {tx_evm}")

        return processed

    def _mint_on_base(self, to_address: str, amount_wei: int, l1_tx_hash: str) -> Optional[str]:
        try:
            nonce = self.w3.eth.get_transaction_count(self.account.address, "pending")
            dest = Web3.to_checksum_address(to_address)
            
            # Estimate gas
            fn = self.contract.functions.mintFromBridge(dest, amount_wei, l1_tx_hash)
            
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
                "gas": 120_000
            })

            signed = self.account.sign_transaction(tx)
            raw_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            tx_hash_hex = raw_hash.hex()
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
            bct_dest = r["bct_address"]
            amt = float(r["net_amount"] or r["amount_bct"])
            evm_hash = r["tx_hash_evm"]
            evm_sender = r["evm_address"]

            try:
                req_data = json.dumps({
                    "evm_tx_hash": evm_hash,
                    "bct_address": bct_dest,
                    "amount": amt,
                    "evm_sender": evm_sender
                }).encode("utf-8")
                req = urllib.request.Request(
                    "http://127.0.0.1:5000/api/v1/bridge/claim_burn",
                    data=req_data,
                    headers={"Content-Type": "application/json"}
                )
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
                        else:
                            self._mark_failed(bridge_id, msg)
                            logger.warning(f"Bridge {bridge_id} unlock rejected: {msg}")
                time.sleep(1.0)
            except Exception as e:
                logger.error(f"Failed to process EVM burn {bridge_id}: {e}")
                time.sleep(2.0)

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

