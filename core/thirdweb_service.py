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
import subprocess
from typing import Dict, Any, Optional

logger = logging.getLogger("LockTrace.Thirdweb")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_SCRIPT = os.path.join(BASE_DIR, "thirdweb_engine.mjs")


class ThirdwebService:
    def __init__(self, secret_key: Optional[str] = None, client_id: Optional[str] = None):
        self.secret_key = secret_key or os.environ.get("THIRDWEB_SECRET_KEY", "")
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
        if self.client_id:
            env["THIRDWEB_CLIENT_ID"] = self.client_id
        if self.server_wallet:
            env["THIRDWEB_SERVER_WALLET_ADDRESS"] = self.server_wallet
        if self.engine_url:
            env["THIRDWEB_ENGINE_URL"] = self.engine_url

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
                logger.error(f"Thirdweb CLI error ({proc.returncode}): {stderr or stdout}")
                try:
                    return json.loads(stdout)
                except Exception:
                    return {"success": False, "error": stderr or stdout or f"Exited with code {proc.returncode}"}

            try:
                return json.loads(stdout)
            except Exception:
                return {"success": True, "raw": stdout}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Thirdweb operation timed out (45s)"}
        except Exception as e:
            logger.exception(f"Error executing Thirdweb CLI runner: {e}")
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
        """
        payload = {
            "contractAddress": contract_address,
            "to": to_address,
            "tokenId": token_id,
            "quantity": quantity,
            "chain": chain,
        }
        if server_wallet_address or self.server_wallet:
            payload["serverWalletAddress"] = server_wallet_address or self.server_wallet

        return self._call_engine_cli("claim1155", json.dumps(payload))

    def get_transaction_status(self, transaction_id: str) -> Dict[str, Any]:
        """Gets execution status of an enqueued transaction via Engine."""
        return self._call_engine_cli("status", transaction_id)

    def wait_for_transaction_hash(self, transaction_id: str) -> Dict[str, Any]:
        """Polls Engine until onchain transaction hash is mined."""
        return self._call_engine_cli("wait-hash", transaction_id)


# Global singleton
thirdweb_service = ThirdwebService()

