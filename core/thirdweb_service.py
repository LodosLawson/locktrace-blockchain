"""
LockTrace - Thirdweb Service Bridge (Python)
=============================================
Provides clean interface to Thirdweb v5 SDK & Thirdweb Engine for backend
transaction execution, ERC1155 / ERC721 claiming, and server wallet management.
"""

import os
import sys
import json
import logging
import re
import subprocess
from typing import Dict, Any, Optional

logger = logging.getLogger("LockTrace.Thirdweb")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_SCRIPT = os.path.join(BASE_DIR, "thirdweb_engine.mjs")
TX_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{8,128}$")
EVM_ADDR_REGEX = re.compile(r"^0x[a-fA-F0-9]{40}$")
CHAIN_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{2,32}$")


def _mask_text(text: str, secrets: Optional[list] = None) -> str:
    """Masks secret keys, private keys, and sensitive bearer tokens in logs and errors."""
    if not text:
        return ""
    masked = str(text)
    if secrets:
        for s in secrets:
            if s and len(str(s)) >= 6:
                masked = masked.replace(str(s), "***REDACTED***")
    masked = re.sub(r"(bearer\s+)[a-zA-Z0-9_\-\.]+", r"\1***REDACTED***", masked, flags=re.IGNORECASE)
    # AUD12-02: Automatically redact raw EVM private keys (0x + 64 hex characters)
    masked = re.sub(r"\b0x[a-fA-F0-9]{64}\b", "0x***REDACTED_PRIVKEY***", masked)
    return masked


class ThirdwebService:
    def __init__(self, secret_key: Optional[str] = None, client_id: Optional[str] = None):
        self.secret_key = secret_key or os.environ.get("THIRDWEB_SECRET_KEY", "")
        self.server_private_key = os.environ.get("THIRDWEB_SERVER_PRIVATE_KEY", "")
        self.client_id = client_id or os.environ.get("THIRDWEB_CLIENT_ID", "")
        self.server_wallet = os.environ.get("THIRDWEB_SERVER_WALLET_ADDRESS", "")
        self.engine_url = os.environ.get("THIRDWEB_ENGINE_URL", "")

    def get_info(self) -> Dict[str, Any]:
        """Returns non-sensitive configuration state."""
        return {
            "configured": bool(self.secret_key),
            "client_id": self.client_id,
            "has_server_wallet": bool(self.server_wallet),
            "server_wallet": self.server_wallet if self.server_wallet else None,
            "has_engine_url": bool(self.engine_url),
            "engine_url": self.engine_url if self.engine_url else None,
            "supported_actions": ["claim_erc1155", "transaction_status", "wait_for_hash"]
        }

    def _call_engine_cli(self, command: str, *args) -> Dict[str, Any]:
        """Calls the Node.js Thirdweb Engine CLI helper."""
        if not os.path.exists(ENGINE_SCRIPT):
            return {"success": False, "error": f"Engine runner not found at {ENGINE_SCRIPT}"}

        cmd = ["node", ENGINE_SCRIPT, command] + list(args)
        env = os.environ.copy()
        if self.secret_key:
            env["THIRDWEB_SECRET_KEY"] = self.secret_key
        if self.server_private_key:
            env["THIRDWEB_SERVER_PRIVATE_KEY"] = self.server_private_key
        if self.client_id:
            env["THIRDWEB_CLIENT_ID"] = self.client_id
        if self.server_wallet:
            env["THIRDWEB_SERVER_WALLET_ADDRESS"] = self.server_wallet
        if self.engine_url:
            env["THIRDWEB_ENGINE_URL"] = self.engine_url

        # AUD12-02: Protect private keys; do not mask public client_id
        known_secrets = [
            self.secret_key,
            self.server_private_key,
            os.environ.get("THIRDWEB_SECRET_KEY", ""),
            os.environ.get("THIRDWEB_SERVER_PRIVATE_KEY", ""),
        ]

        try:
            proc = subprocess.run(
                cmd,
                cwd=BASE_DIR,
                capture_output=True,
                text=True,
                timeout=45,
                env=env
            )
            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()

            if proc.returncode != 0:
                safe_log_msg = _mask_text(stderr or stdout, known_secrets)
                logger.error(f"Thirdweb CLI error ({proc.returncode}): {safe_log_msg}")
                try:
                    parsed = json.loads(stdout)
                    # Sanitize error message to prevent secret or system leakage
                    err_msg = _mask_text(str(parsed.get("error", "") or "Execution failed"), known_secrets)
                    return {"success": False, "error": err_msg}
                except Exception:
                    return {"success": False, "error": "Thirdweb engine operation failed"}

            try:
                return json.loads(stdout)
            except Exception:
                return {"success": True, "raw": stdout}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Thirdweb operation timed out (45s)"}
        except Exception as e:
            safe_err = _mask_text(str(e), known_secrets)
            logger.error(f"Error executing Thirdweb CLI runner: {safe_err}")
            return {"success": False, "error": "Thirdweb CLI execution failed"}

    def claim_erc1155(
        self,
        contract_address: str,
        to_address: str,
        token_id: int = 0,
        quantity: int = 1,
        chain: str = "base-sepolia",
        server_wallet_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Mints/Claims ERC1155 token to recipient using Engine server wallet.
        Validates addresses, bounds, and chain identifier to protect against DoS and invalid inputs.
        """
        contract_addr = (contract_address or "").strip()
        to_addr = (to_address or "").strip()
        chain_name = (chain or "").strip()

        if not EVM_ADDR_REGEX.match(contract_addr):
            return {"success": False, "error": "Invalid contract address format (must be 0x hex 40 chars)"}

        if not EVM_ADDR_REGEX.match(to_addr):
            return {"success": False, "error": "Invalid recipient address format (must be 0x hex 40 chars)"}

        try:
            tok_id = int(token_id)
            if tok_id < 0 or tok_id >= 2**256:
                return {"success": False, "error": "Token ID out of valid range (0 <= token_id < 2^256)"}
        except (ValueError, TypeError):
            return {"success": False, "error": "Token ID must be a valid integer"}

        try:
            qty = int(quantity)
            if qty <= 0 or qty > 1_000_000:
                return {"success": False, "error": "Quantity must be between 1 and 1,000,000"}
        except (ValueError, TypeError):
            return {"success": False, "error": "Quantity must be a valid integer"}

        if not CHAIN_REGEX.match(chain_name):
            return {"success": False, "error": "Invalid chain identifier"}

        payload = {
            "contractAddress": contract_addr,
            "to": to_addr,
            "tokenId": tok_id,
            "quantity": qty,
            "chain": chain_name,
        }

        target_server_wallet = server_wallet_address or self.server_wallet
        if target_server_wallet:
            target_wallet_str = str(target_server_wallet).strip()
            if not EVM_ADDR_REGEX.match(target_wallet_str):
                return {"success": False, "error": "Invalid server wallet address format"}
            payload["serverWalletAddress"] = target_wallet_str

        return self._call_engine_cli("claim1155", json.dumps(payload))

    def get_transaction_status(self, transaction_id: str) -> Dict[str, Any]:
        """Gets execution status of an enqueued transaction via Engine."""
        clean_id = (transaction_id or "").strip()
        if not TX_ID_REGEX.match(clean_id):
            return {"success": False, "error": "Invalid transaction ID format"}
        return self._call_engine_cli("status", clean_id)

    def wait_for_transaction_hash(self, transaction_id: str) -> Dict[str, Any]:
        """Polls Engine until onchain transaction hash is mined."""
        clean_id = (transaction_id or "").strip()
        if not TX_ID_REGEX.match(clean_id):
            return {"success": False, "error": "Invalid transaction ID format"}
        return self._call_engine_cli("wait-hash", clean_id)


# Global singleton
thirdweb_service = ThirdwebService()

