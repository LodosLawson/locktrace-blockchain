"""
BlockChainT - Hardened & Transparent API Server
===============================================
Universal Explorer Endpoints & High-Resiliency Transaction Processing.
"""

import os
import sys
import time
import logging
import secrets
from datetime import datetime

from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(__file__))
from config import Config
from core.blockchain import Blockchain, TREASURY_ADDRESS, TOTAL_SUPPLY, is_valid_bct_address
from core.wallet import Wallet, restore_wallet, restore_wallet_from_mnemonic
from core.mnemonic import validate_mnemonic

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.from_object(Config)

CORS(app, resources={r"/api/*": {"origins": "*"}})

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

blockchain = Blockchain(auto_mine=True)
logger.info(f"LockTrace Initialized: {len(blockchain.chain)} blocks, {len(blockchain.wallets)} wallets")


@app.before_request
def before_request():
    g.start_time = time.time()
    g.request_id = secrets.token_hex(8)

@app.after_request
def after_request(response):
    duration = time.time() - getattr(g, 'start_time', time.time())
    response.headers["X-Request-ID"] = getattr(g, 'request_id', 'unknown')
    response.headers["X-Response-Time"] = f"{duration:.4f}s"
    response.headers["X-Powered-By"] = "LockTrace-Blockchain/1.1"
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


# ── Health & Stats ───────────────────────────────────────────
@app.route("/api/v1/health", methods=["GET"])
def api_health():
    return api_response(True, data={
        "status": "healthy",
        "version": "1.2.0",
        "network": "mainnet",
        "chain_valid": blockchain.is_chain_valid()
    })


@app.route("/api/v1/stats", methods=["GET"])
def api_stats():
    return api_response(True, data=blockchain.get_stats())


# ── Wallet Creation ──────────────────────────────────────────
@app.route("/api/v1/wallet/create", methods=["POST"])
def api_create_wallet():
    try:
        wallet = Wallet()
        success, message = blockchain.register_wallet(
            wallet.address, wallet.get_public_key_hex()
        )
        if success:
            logger.info(f"Account Created: {wallet.address} with 1.00 BCT")
            return api_response(True, message=message, data={
                "address": wallet.address,
                "mnemonic": wallet.mnemonic,
                "public_key": wallet.get_public_key_hex(),
                "private_key": wallet.get_private_key_hex(),
                "balance": blockchain.get_balance(wallet.address)
            }, status=201)
        return api_response(False, message=message, status=400)
    except Exception as e:
        logger.error(f"Account creation exception: {e}")
        return api_response(False, message=str(e), status=500)


# ── Wallet Import ────────────────────────────────────────────
@app.route("/api/v1/wallet/import", methods=["POST"])
def api_import_wallet():
    data = request.get_json(silent=True) or {}
    mnemonic_phrase = data.get("mnemonic", "").strip()
    private_key_hex = data.get("private_key", "").strip()

    try:
        if mnemonic_phrase:
            words = mnemonic_phrase.split()
            if len(words) < 12:
                return api_response(False, message="Mnemonic must contain 12 words", status=400)
            wallet = restore_wallet_from_mnemonic(" ".join(words))
        elif private_key_hex:
            clean_pk = private_key_hex.strip()
            if len(clean_pk) != 64:
                return api_response(False, message="Private key must be 64 hex characters", status=400)
            wallet = restore_wallet(clean_pk)
        else:
            return api_response(False, message="Provide 12 words mnemonic or private key", status=400)

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
        logger.warning(f"Wallet restoration failed: {e}")
        return api_response(False, message=f"Restoration failed: {str(e)}", status=400)


# ── Balance ──────────────────────────────────────────────────
@app.route("/api/v1/balance/<address>", methods=["GET"])
def api_balance(address):
    clean_addr = address.strip()
    if not is_valid_bct_address(clean_addr):
        return api_response(False, message="Invalid address syntax", status=400)

    bal = blockchain.get_balance(clean_addr)
    return api_response(True, data={
        "address": clean_addr,
        "balance": bal,
        "exists": clean_addr in blockchain.wallets or clean_addr == TREASURY_ADDRESS
    })


# ── Wire Transfer (Robust Validation & Logging) ──────────────
@app.route("/api/v1/transaction", methods=["POST"])
def api_transaction():
    data = request.get_json(silent=True) or {}
    logger.info(f"Incoming Transaction Request: sender={data.get('sender')} receiver={data.get('receiver')} amount={data.get('amount')}")

    sender = str(data.get("sender", "")).strip()
    receiver = str(data.get("receiver", "")).strip()
    amount_raw = data.get("amount")

    if not sender or not receiver or amount_raw is None:
        return api_response(False, message="Missing required fields: sender, receiver, amount", status=400)

    try:
        amount = float(amount_raw)
        if amount <= 0:
            return api_response(False, message="Amount must be positive", status=400)
    except (ValueError, TypeError):
        return api_response(False, message="Invalid numeric amount", status=400)

    mnemonic_phrase = str(data.get("mnemonic", "")).strip()
    private_key_hex = str(data.get("private_key", "")).strip()

    try:
        if mnemonic_phrase and len(mnemonic_phrase.split()) >= 12:
            wallet = restore_wallet_from_mnemonic(mnemonic_phrase)
        elif private_key_hex and len(private_key_hex) == 64:
            wallet = restore_wallet(private_key_hex)
        else:
            logger.warning(f"Transfer rejected: missing signature credentials for sender {sender}")
            return api_response(False, message="Signing credentials required (12 words mnemonic or 64-hex private key)", status=400)

        if wallet.address != sender:
            logger.warning(f"Key mismatch: wallet {wallet.address} tried to sign for {sender}")
            return api_response(False, message="Signing key does not match sender address", status=403)
    except Exception as e:
        logger.warning(f"Signature resolution error: {e}")
        return api_response(False, message=f"Key verification error: {str(e)}", status=400)

    # Sign transaction
    tx_data = f"{sender}{receiver}{amount}"
    signature = wallet.sign(tx_data)

    success, message, tx_info = blockchain.create_transaction(
        sender=sender,
        receiver=receiver,
        amount=amount,
        signature=signature
    )

    if success:
        logger.info(f"Transaction Confirmed: {tx_info['tx_hash'][:16]} {sender[:8]}->{receiver[:8]} {amount} BCT")
        return api_response(True, message=message, data=tx_info, status=201)

    logger.warning(f"Transaction Declined: {message}")
    return api_response(False, message=message, status=400)


# ── Universal Explorer Endpoints ─────────────────────────────
@app.route("/api/v1/explorer/search", methods=["GET"])
def api_explorer_search():
    """Universal search across Blocks, Transactions, and Addresses."""
    q = request.args.get("q", "").strip()
    if not q:
        return api_response(False, message="Search query cannot be empty", status=400)

    # 1. Search Block
    block = blockchain.get_block_by_index_or_hash(q)
    if block:
        return api_response(True, data={"type": "block", "result": block})

    # 2. Search Transaction
    tx = blockchain.get_tx_by_hash(q)
    if tx:
        return api_response(True, data={"type": "transaction", "result": tx})

    # 3. Search Wallet Address
    if is_valid_bct_address(q):
        bal = blockchain.get_balance(q)
        history = blockchain.get_wallet_transactions(q)
        return api_response(True, data={
            "type": "address",
            "result": {
                "address": q,
                "balance": bal,
                "transaction_count": len(history),
                "transactions": history
            }
        })

    return api_response(False, message=f"No blockchain records found matching '{q}'", status=404)


@app.route("/api/v1/explorer/block/<query>", methods=["GET"])
def api_explorer_block(query):
    block = blockchain.get_block_by_index_or_hash(query)
    if block:
        return api_response(True, data=block)
    return api_response(False, message="Block not found", status=404)


@app.route("/api/v1/explorer/tx/<tx_hash>", methods=["GET"])
def api_explorer_tx(tx_hash):
    tx = blockchain.get_tx_by_hash(tx_hash)
    if tx:
        return api_response(True, data=tx)
    return api_response(False, message="Transaction not found", status=404)


@app.route("/api/v1/transactions/latest", methods=["GET"])
def api_latest_transactions():
    limit = min(request.args.get("limit", 20, type=int), 100)
    txs = blockchain.get_all_transactions()
    return api_response(True, data={"transactions": txs[:limit], "total": len(txs)})


@app.route("/api/v1/transactions/<address>", methods=["GET"])
def api_wallet_transactions(address):
    clean = address.strip()
    if clean.lower() == "latest":
        return api_latest_transactions()
    if not is_valid_bct_address(clean):
        return api_response(False, message="Invalid address syntax", status=400)
    txs = blockchain.get_wallet_transactions(clean)
    return api_response(True, data={"transactions": txs, "total": len(txs), "address": clean})


@app.route("/api/v1/blocks/latest", methods=["GET"])
def api_latest_blocks():
    count = min(request.args.get("count", 15, type=int), 50)
    return api_response(True, data={"blocks": blockchain.get_latest_blocks(count)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
