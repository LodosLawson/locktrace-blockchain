"""
BlockChainT - Production API Server v1 (Mnemonic & Ledger-Hardened)
===================================================================
12-Word Mnemonic Recovery Phrase Support & On-Chain Balance Guarantee.
"""

import os
import sys
import time
import logging
import secrets
from functools import wraps
from datetime import datetime

from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(__file__))
from config import Config
from core.blockchain import Blockchain, TREASURY_ADDRESS, TOTAL_SUPPLY
from core.wallet import Wallet, restore_wallet, restore_wallet_from_mnemonic
from core.mnemonic import validate_mnemonic

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.from_object(Config)

# CORS
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Rate Limiter
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[Config.RATE_LIMIT_DEFAULT],
        storage_uri="memory://",
    )
    HAS_LIMITER = True
except ImportError:
    class FakeLimiter:
        def limit(self, *a, **kw):
            def decorator(f): return f
            return decorator
    limiter = FakeLimiter()

# Logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Config.LOG_FILE, encoding="utf-8"),
    ]
)
logger = logging.getLogger("LockTrace")

# Blockchain instance
blockchain = Blockchain(auto_mine=True)
logger.info(f"LockTrace Blockchain Initialized: {len(blockchain.chain)} blocks, {len(blockchain.wallets)} wallets")


@app.before_request
def before_request():
    g.start_time = time.time()
    g.request_id = secrets.token_hex(8)

@app.after_request
def after_request(response):
    duration = time.time() - getattr(g, 'start_time', time.time())
    response.headers["X-Request-ID"] = getattr(g, 'request_id', 'unknown')
    response.headers["X-Response-Time"] = f"{duration:.4f}s"
    response.headers["X-Powered-By"] = "LockTrace-Blockchain/1.0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key"
    return response


def api_response(success: bool, data=None, message=None, status=200, **extra):
    body = {
        "success": success,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "request_id": getattr(g, 'request_id', None),
    }
    if data is not None:
        body["data"] = data
    if message:
        body["message"] = message
    body.update(extra)
    return jsonify(body), status


def validate_address(addr: str) -> bool:
    if not addr or not isinstance(addr, str):
        return False
    if addr == TREASURY_ADDRESS:
        return True
    return addr.startswith("BCT") and len(addr) == 43


# ── Health & Stats ───────────────────────────────────────────
@app.route("/api/v1/health", methods=["GET"])
def api_health():
    return api_response(True, data={
        "status": "healthy",
        "version": "1.1.0",
        "network": "mainnet",
        "chain_valid": blockchain.is_chain_valid()
    })


@app.route("/api/v1/stats", methods=["GET"])
def api_stats():
    return api_response(True, data=blockchain.get_stats())


# ── Wallet Creation (12-Word Mnemonic + 1 BCT Bonus) ─────────
@app.route("/api/v1/wallet/create", methods=["POST"])
@limiter.limit("20/minute")
def api_create_wallet():
    try:
        # Generates 12 words seed phrase + ECDSA keys
        wallet = Wallet()
        success, message = blockchain.register_wallet(
            wallet.address, wallet.get_public_key_hex()
        )
        if success:
            logger.info(f"Account Registered: {wallet.address} with 1.00 BCT bonus")
            return api_response(True, message=message, data={
                "address": wallet.address,
                "mnemonic": wallet.mnemonic,
                "public_key": wallet.get_public_key_hex(),
                "private_key": wallet.get_private_key_hex(),
                "balance": blockchain.get_balance(wallet.address)
            }, status=201)
        return api_response(False, message=message, status=400)
    except Exception as e:
        logger.error(f"Wallet creation error: {e}")
        return api_response(False, message=str(e), status=500)


# ── Wallet Import (12-Word Mnemonic or Private Key) ──────────
@app.route("/api/v1/wallet/import", methods=["POST"])
@limiter.limit("30/minute")
def api_import_wallet():
    data = request.get_json(silent=True) or {}
    mnemonic_phrase = data.get("mnemonic", "").strip()
    private_key_hex = data.get("private_key", "").strip()

    try:
        if mnemonic_phrase:
            # 12-Word Mnemonic restoration
            if not validate_mnemonic(mnemonic_phrase):
                return api_response(False, message="Invalid 12-word recovery phrase", status=400)
            wallet = restore_wallet_from_mnemonic(mnemonic_phrase)
        elif private_key_hex:
            # 64-hex Private Key restoration
            if len(private_key_hex) != 64:
                return api_response(False, message="Private key must be exactly 64 hex characters", status=400)
            wallet = restore_wallet(private_key_hex)
        else:
            return api_response(False, message="Provide either 'mnemonic' (12 words) or 'private_key'", status=400)

        # Register or retrieve
        blockchain.register_wallet(wallet.address, wallet.get_public_key_hex())
        bal = blockchain.get_balance(wallet.address)

        return api_response(True, message="Wallet successfully restored!", data={
            "address": wallet.address,
            "mnemonic": getattr(wallet, 'mnemonic', ''),
            "public_key": wallet.get_public_key_hex(),
            "private_key": wallet.get_private_key_hex(),
            "balance": bal
        })
    except Exception as e:
        logger.error(f"Import error: {e}")
        return api_response(False, message=f"Restoration failed: {str(e)}", status=400)


# ── Balance ──────────────────────────────────────────────────
@app.route("/api/v1/balance/<address>", methods=["GET"])
def api_balance(address):
    if not validate_address(address):
        return api_response(False, message="Invalid address format", status=400)

    bal = blockchain.get_balance(address)
    return api_response(True, data={
        "address": address,
        "balance": bal,
        "exists": address in blockchain.wallets or address == TREASURY_ADDRESS
    })


# ── Wire Transfer ────────────────────────────────────────────
@app.route("/api/v1/transaction", methods=["POST"])
@limiter.limit("60/minute")
def api_transaction():
    data = request.get_json(silent=True) or {}
    required = ["sender", "receiver", "amount"]
    missing = [f for f in required if f not in data]
    if missing:
        return api_response(False, message=f"Missing fields: {', '.join(missing)}", status=400)

    try:
        amount = float(data["amount"])
    except (ValueError, TypeError):
        return api_response(False, message="Invalid amount", status=400)

    # Key derivation from mnemonic or private key
    mnemonic_phrase = data.get("mnemonic", "").strip()
    private_key_hex = data.get("private_key", "").strip()

    try:
        if mnemonic_phrase:
            wallet = restore_wallet_from_mnemonic(mnemonic_phrase)
        elif private_key_hex:
            wallet = restore_wallet(private_key_hex)
        else:
            return api_response(False, message="Transaction signing requires private_key or mnemonic", status=400)

        if wallet.address != data["sender"]:
            return api_response(False, message="Signer key does not match sender address", status=403)
    except Exception:
        return api_response(False, message="Cryptographic signature verification failed", status=400)

    # Sign transaction
    tx_data = f"{data['sender']}{data['receiver']}{amount}"
    signature = wallet.sign(tx_data)

    success, message, tx_info = blockchain.create_transaction(
        sender=data["sender"],
        receiver=data["receiver"],
        amount=amount,
        signature=signature
    )

    if success:
        return api_response(True, message=message, data=tx_info, status=201)
    return api_response(False, message=message, status=400)


# ── Explorer Queries ─────────────────────────────────────────
@app.route("/api/v1/transactions/latest", methods=["GET"])
def api_latest_transactions():
    limit = min(request.args.get("limit", 20, type=int), 100)
    txs = blockchain.get_all_transactions()
    return api_response(True, data={"transactions": txs[:limit], "total": len(txs)})


@app.route("/api/v1/blocks/latest", methods=["GET"])
def api_latest_blocks():
    count = min(request.args.get("count", 10, type=int), 50)
    return api_response(True, data={"blocks": blockchain.get_latest_blocks(count)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
