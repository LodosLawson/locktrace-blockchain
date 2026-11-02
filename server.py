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


# ── Decentralized Network Nodes Endpoints ────────────────────
@app.route("/api/v1/nodes", methods=["GET"])
def api_get_nodes():
    """List all registered network nodes with uptime and health."""
    nodes = blockchain.get_nodes()
    online_count = sum(1 for n in nodes if n.get("status") == "online")
    return api_response(True, data={
        "total_nodes": len(nodes),
        "online_nodes": online_count,
        "nodes": nodes
    })


@app.route("/api/v1/nodes/register", methods=["POST"])
def api_register_node():
    """Register or announce a community node into the decentralized network."""
    data = request.get_json(silent=True) or {}
    node_id = str(data.get("node_id", "")).strip()
    name = str(data.get("name", "")).strip()
    endpoint = str(data.get("endpoint", "")).strip()
    role = str(data.get("role", "Peer Node")).strip()
    location = str(data.get("location", "Decentralized")).strip()
    miner_address = str(data.get("miner_address", "")).strip()
    block_height = int(data.get("block_height", 0))
    version = str(data.get("version", "1.2.0")).strip()

    if not node_id:
        node_id = f"node-{secrets.token_hex(4)}"

    node_info = blockchain.register_or_ping_node(
        node_id=node_id,
        name=name,
        endpoint=endpoint,
        role=role,
        location=location,
        miner_address=miner_address,
        block_height=block_height,
        version=version
    )
    logger.info(f"Node Registered / Heartbeat: {node_info['name']} [{node_info['node_id']}] miner={miner_address[:8]} from {location}")
    return api_response(True, message="Node registered successfully in LockTrace network", data=node_info, status=201)


@app.route("/api/v1/nodes/ping", methods=["POST"])
def api_ping_node():
    """Heartbeat endpoint for connected nodes."""
    data = request.get_json(silent=True) or {}
    node_id = str(data.get("node_id", "")).strip()
    if not node_id:
        return api_response(False, message="Node ID required", status=400)

    node_info = blockchain.register_or_ping_node(
        node_id=node_id,
        block_height=int(data.get("block_height", len(blockchain.chain))),
        miner_address=str(data.get("miner_address", "")).strip()
    )
    return api_response(True, message="Pong", data={"node_id": node_id, "status": "online", "network_height": len(blockchain.chain)})


# ── Mining & Node Reward Endpoints ───────────────────────────
@app.route("/api/v1/mining/job", methods=["GET"])
def api_mining_job():
    """Provides current mining difficulty, pending fees, and block reward metrics."""
    pending_fees = sum(tx.fee for tx in blockchain.pending_transactions if tx.tx_type == "transfer")
    from core.blockchain import BLOCK_REWARD, MINER_FEE_SHARE
    miner_cut = round(pending_fees * MINER_FEE_SHARE, 8)
    return api_response(True, data={
        "block_index": len(blockchain.chain),
        "previous_hash": blockchain.chain[-1].hash if blockchain.chain else "0" * 64,
        "difficulty": blockchain.difficulty,
        "pending_transactions": len(blockchain.pending_transactions),
        "block_subsidy": BLOCK_REWARD,
        "pending_fees": pending_fees,
        "potential_miner_reward": round(BLOCK_REWARD + miner_cut, 8)
    })


@app.route("/api/v1/mine", methods=["POST"])
def api_mine_block():
    """Forge and mine a new Proof-of-Work block, claiming the 50% fee share and 0.05 BCT block reward."""
    data = request.get_json(silent=True) or {}
    miner_address = str(data.get("miner_address", "")).strip()
    node_id = str(data.get("node_id", "")).strip()

    if not miner_address:
        return api_response(False, message="Miner address is required to receive block rewards", status=400)

    if not is_valid_bct_address(miner_address):
        return api_response(False, message=f"Invalid miner address format: '{miner_address}'", status=400)

    # Mine block with the provided miner address
    block = blockchain._mine_block(miner_address=miner_address)
    if not block:
        return api_response(False, message="No pending transactions or mining tasks to package into a block.", status=400)

    # Find coinbase transaction
    coinbase = next((t for t in block.transactions if t.tx_type == "mining_reward"), None)
    reward_val = coinbase.amount if coinbase else 0.0

    logger.info(f"Block #{block.index} successfully mined by {miner_address[:10]}... Reward: {reward_val} BCT")

    return api_response(True, message=f"Block #{block.index} successfully mined! Deposited {reward_val:.8f} BCT reward.", data={
        "block_index": block.index,
        "block_hash": block.hash,
        "nonce": block.nonce,
        "transactions_packaged": len(block.transactions),
        "miner_address": miner_address,
        "miner_reward": reward_val,
        "miner_balance": blockchain.get_balance(miner_address),
        "timestamp": block.timestamp
    }, status=201)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
