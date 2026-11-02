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

from flask import Flask, request, jsonify, render_template, g, send_file
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(__file__))
from config import Config
from core.blockchain import Blockchain, TREASURY_ADDRESS, TOTAL_SUPPLY, is_valid_bct_address
from core.wallet import Wallet, restore_wallet, restore_wallet_from_mnemonic
from core.mnemonic import validate_mnemonic
from core.thirdweb_service import thirdweb_service

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
        # Enrich block data with validator node metadata
        node_meta = None
        miner_addr = block.get("miner", "")
        for n_id, n in blockchain.nodes.items():
            if n.get("miner_address") == miner_addr or n.get("endpoint") == miner_addr or n.get("node_id") == miner_addr:
                node_meta = {
                    "node_id": n.get("node_id"),
                    "name": n.get("name"),
                    "location": n.get("location"),
                    "role": n.get("role"),
                    "version": n.get("version"),
                    "status": n.get("status", "online")
                }
                break
        if not node_meta:
            node_meta = {
                "node_id": "node-stockholm-validator-01",
                "name": "LockTrace Genesis Validator #1",
                "location": "Stockholm, Sweden (Oracle Cloud)",
                "role": "Core PoW Archival Validator",
                "version": "1.2.0",
                "status": "online"
            }
        block["validator_node"] = node_meta
        return api_response(True, data=block)
    return api_response(False, message="Block not found", status=404)


@app.route("/api/v1/nodes/download", methods=["GET"])
@app.route("/node_runner.py", methods=["GET"])
def api_download_node():
    """Serves the node_runner.py daemon for direct download via curl/wget/browser."""
    script_path = os.path.join(os.path.dirname(__file__), "node_runner.py")
    if os.path.exists(script_path):
        return send_file(script_path, mimetype="text/x-python", as_attachment=False)
    return api_response(False, message="Node runner script not found", status=404)


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


# ══════════════════════════════════════════════════════
# 🪐 LockTrace Space (On-Chain Decentralized Social Feed)
# ══════════════════════════════════════════════════════

@app.route("/api/v1/space/feed", methods=["GET"])
def api_space_feed():
    """Returns on-chain space thoughts feed with likes and comments."""
    limit = min(request.args.get("limit", 50, type=int), 100)
    feed = blockchain.get_space_feed(limit)
    return api_response(True, data={"posts": feed, "count": len(feed)})


@app.route("/api/v1/space/post/<post_id>", methods=["GET"])
def api_space_get_post(post_id):
    post = blockchain.get_space_post(post_id)
    if post:
        return api_response(True, data=post)
    return api_response(False, message="Gönderi bulunamadı", status=404)


@app.route("/api/v1/space/post", methods=["POST"])
def api_space_create_post():
    """
    Publishes an immutable on-chain thought.
    Cost: 0.10 BCT (80% returns to Treasury Vault, 20% to block validator).
    """
    data = request.get_json(silent=True) or {}
    author = str(data.get("author", "")).strip()
    content = str(data.get("content", "")).strip()

    if not author:
        return api_response(False, message="Yazar cüzdan adresi gereklidir", status=400)
    if not content:
        return api_response(False, message="Düşünce metni boş olamaz", status=400)

    mnemonic_phrase = str(data.get("mnemonic", "")).strip()
    private_key_hex = str(data.get("private_key", "")).strip()
    signature = str(data.get("signature", "")).strip()

    if not signature:
        try:
            if mnemonic_phrase and len(mnemonic_phrase.split()) >= 12:
                wallet = restore_wallet_from_mnemonic(mnemonic_phrase)
                if wallet.address == author:
                    signature = wallet.sign(f"{author}:{content}")
            elif private_key_hex and len(private_key_hex) == 64:
                wallet = restore_wallet(private_key_hex)
                if wallet.address == author:
                    signature = wallet.sign(f"{author}:{content}")
        except Exception:
            pass

    success, message, result = blockchain.create_space_post(
        author=author,
        content=content,
        signature=signature
    )
    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"Space Post Created: by {author[:8]}... (0.10 BCT)")
    return api_response(True, message=message, data=result, status=201)


@app.route("/api/v1/space/like", methods=["POST"])
def api_space_like():
    """
    Likes an on-chain thought.
    Cost: 0.01 BCT (20% to tweet author, 70% to Treasury, 10% validator fee).
    """
    data = request.get_json(silent=True) or {}
    liker = str(data.get("liker", "")).strip()
    post_id = str(data.get("post_id", "")).strip()

    if not liker or not post_id:
        return api_response(False, message="liker adresi ve post_id gereklidir", status=400)

    mnemonic_phrase = str(data.get("mnemonic", "")).strip()
    private_key_hex = str(data.get("private_key", "")).strip()
    signature = str(data.get("signature", "")).strip()

    if not signature:
        try:
            if mnemonic_phrase and len(mnemonic_phrase.split()) >= 12:
                wallet = restore_wallet_from_mnemonic(mnemonic_phrase)
                if wallet.address == liker:
                    signature = wallet.sign(f"{liker}:{post_id}")
            elif private_key_hex and len(private_key_hex) == 64:
                wallet = restore_wallet(private_key_hex)
                if wallet.address == liker:
                    signature = wallet.sign(f"{liker}:{post_id}")
        except Exception:
            pass

    success, message, result = blockchain.like_space_post(
        liker=liker,
        post_id=post_id,
        signature=signature
    )
    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"Space Post Liked: {post_id} by {liker[:8]}...")
    return api_response(True, message=message, data=result, status=200)


@app.route("/api/v1/space/comment", methods=["POST"])
def api_space_comment():
    """
    Comments on an on-chain thought.
    Cost: 0.02 BCT (20% to tweet author, 70% to Treasury, 10% validator fee).
    """
    data = request.get_json(silent=True) or {}
    commenter = str(data.get("commenter", "")).strip()
    post_id = str(data.get("post_id", "")).strip()
    content = str(data.get("content", "")).strip()

    if not commenter or not post_id or not content:
        return api_response(False, message="commenter, post_id ve content gereklidir", status=400)

    mnemonic_phrase = str(data.get("mnemonic", "")).strip()
    private_key_hex = str(data.get("private_key", "")).strip()
    signature = str(data.get("signature", "")).strip()

    if not signature:
        try:
            if mnemonic_phrase and len(mnemonic_phrase.split()) >= 12:
                wallet = restore_wallet_from_mnemonic(mnemonic_phrase)
                if wallet.address == commenter:
                    signature = wallet.sign(f"{commenter}:{post_id}:{content}")
            elif private_key_hex and len(private_key_hex) == 64:
                wallet = restore_wallet(private_key_hex)
                if wallet.address == commenter:
                    signature = wallet.sign(f"{commenter}:{post_id}:{content}")
        except Exception:
            pass

    success, message, result = blockchain.comment_space_post(
        commenter=commenter,
        post_id=post_id,
        content=content,
        signature=signature
    )
    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"Space Comment Added: {post_id} by {commenter[:8]}...")
    return api_response(True, message=message, data=result, status=201)


# ══════════════════════════════════════════════════════
# 💱 Fiat On-Ramp & Buy/Sell Coin Trading (Thirdweb Protected)
# ══════════════════════════════════════════════════════

@app.route("/api/v1/trade/config", methods=["GET"])
def api_trade_config():
    """
    Returns public trade parameters and public Thirdweb Client ID.
    CRITICAL: Secret keys are strictly protected on the backend and never exposed.
    """
    rates = {
        "USD": Config.BCT_PER_USD,
        "EUR": round(Config.BCT_PER_USD * 1.08, 4),
        "TRY": round(Config.BCT_PER_USD / 34.0, 4)
    }
    return api_response(True, data={
        "thirdweb_client_id": Config.THIRDWEB_CLIENT_ID,
        "bct_per_usd": Config.BCT_PER_USD,
        "bct_price_usd": Config.BCT_PRICE_USD,
        "min_buy_usd": Config.MIN_BUY_USD,
        "max_buy_usd": Config.MAX_BUY_USD,
        "supported_currencies": ["USD", "EUR", "TRY"],
        "rates": rates
    })


@app.route("/api/v1/trade/buy", methods=["POST"])
def api_trade_buy():
    """
    Executes a fiat purchase of BCT tokens via Thirdweb Pay or direct payment.
    Debits Treasury reserves and delivers BCT directly into buyer's address with PoW block settlement.
    """
    data = request.get_json(silent=True) or {}
    buyer_address = str(data.get("buyer_address", "")).strip()
    fiat_amount = float(data.get("fiat_amount", 0.0))
    currency = str(data.get("currency", "USD")).strip().upper()
    payment_method = str(data.get("payment_method", "credit_card")).strip()
    session_token = str(data.get("session_token", "")).strip()

    if not buyer_address:
        return api_response(False, message="Buyer wallet address is required", status=400)

    if not is_valid_bct_address(buyer_address):
        return api_response(False, message=f"Invalid buyer address: '{buyer_address}'", status=400)

    if fiat_amount < Config.MIN_BUY_USD:
        return api_response(False, message=f"Minimum purchase amount is ${Config.MIN_BUY_USD:.2f}", status=400)

    if fiat_amount > Config.MAX_BUY_USD:
        return api_response(False, message=f"Maximum purchase amount is ${Config.MAX_BUY_USD:,.2f}", status=400)

    success, message, receipt = blockchain.execute_fiat_purchase(
        buyer_address=buyer_address,
        fiat_amount=fiat_amount,
        currency=currency,
        payment_ref=session_token,
        bct_per_usd=Config.BCT_PER_USD
    )

    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"Token Purchase: {buyer_address[:10]} bought {receipt['bct_amount']} BCT with {fiat_amount} {currency}")
    return api_response(True, message=message, data=receipt, status=201)


@app.route("/api/v1/trade/sell", methods=["POST"])
def api_trade_sell():
    """
    Executes a sale of BCT tokens for fiat payout.
    Transfers BCT back to Treasury vault and initiates off-ramp payout.
    """
    data = request.get_json(silent=True) or {}
    seller_address = str(data.get("seller_address", "")).strip()
    bct_amount = float(data.get("bct_amount", 0.0))
    currency = str(data.get("currency", "USD")).strip().upper()
    payout_info = str(data.get("payout_info", "")).strip()

    if not seller_address:
        return api_response(False, message="Seller wallet address is required", status=400)

    if not is_valid_bct_address(seller_address):
        return api_response(False, message=f"Invalid seller address: '{seller_address}'", status=400)

    if bct_amount <= 0:
        return api_response(False, message="Sell amount must be greater than zero", status=400)

    success, message, receipt = blockchain.execute_fiat_sale(
        seller_address=seller_address,
        bct_amount=bct_amount,
        payout_info=payout_info,
        currency=currency,
        bct_per_usd=Config.BCT_PER_USD
    )

    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"Token Sale: {seller_address[:10]} sold {bct_amount} BCT for {receipt['fiat_payout']} {currency}")
    return api_response(True, message=message, data=receipt, status=201)


@app.route("/api/v1/trade/orders/<address>", methods=["GET"])
def api_trade_orders(address: str):
    """Returns buy & sell order history for a specific wallet address."""
    clean_addr = address.strip()
    orders = []
    with blockchain.lock:
        blockchain._load_state()
        for b in blockchain.chain:
            for tx in b.transactions:
                if (tx.sender == clean_addr or tx.receiver == clean_addr) and tx.tx_type in ("fiat_buy", "token_sell"):
                    orders.append({
                        "tx_hash": tx.tx_hash,
                        "block_index": b.index,
                        "type": tx.tx_type,
                        "amount": tx.amount,
                        "fee": tx.fee,
                        "timestamp": tx.timestamp,
                        "signature": tx.signature
                    })
    return api_response(True, data={"address": clean_addr, "orders": orders})


# ══════════════════════════════════════════════════════
# 🌐 Thirdweb Engine & Server Wallet Endpoints
# ══════════════════════════════════════════════════════

@app.route("/api/v1/thirdweb/info", methods=["GET"])
def api_thirdweb_info():
    """Returns Thirdweb backend status and configuration info."""
    return api_response(True, data=thirdweb_service.get_info())


@app.route("/api/v1/thirdweb/claim-erc1155", methods=["POST"])
def api_thirdweb_claim_erc1155():
    """
    Mints / Claims ERC1155 NFT to a recipient address using Thirdweb SDK / Engine Server Wallet.
    """
    data = request.get_json(silent=True) or {}
    contract_address = str(data.get("contract_address", "")).strip()
    to_address = str(data.get("to", data.get("to_address", ""))).strip()
    token_id = int(data.get("token_id", 0))
    quantity = int(data.get("quantity", 1))
    chain = str(data.get("chain", Config.THIRDWEB_DEFAULT_CHAIN)).strip()
    server_wallet = str(data.get("server_wallet", "")).strip() or None

    if not contract_address:
        return api_response(False, message="contract_address is required", status=400)
    if not to_address:
        return api_response(False, message="recipient 'to' address is required", status=400)

    result = thirdweb_service.claim_erc1155(
        contract_address=contract_address,
        to_address=to_address,
        token_id=token_id,
        quantity=quantity,
        chain=chain,
        server_wallet_address=server_wallet
    )

    if not result.get("success", False):
        err = result.get("error", "Failed to enqueue Thirdweb transaction")
        return api_response(False, message=err, status=400)

    logger.info(f"Thirdweb Claim Enqueued/Executed: to={to_address} contract={contract_address} token={token_id}")
    return api_response(True, message="Thirdweb transaction successfully processed", data=result.get("data", {}), status=201)


@app.route("/api/v1/thirdweb/status/<transaction_id>", methods=["GET"])
def api_thirdweb_status(transaction_id: str):
    """Checks the execution status of an enqueued Engine transaction."""
    clean_tx_id = transaction_id.strip()
    if not clean_tx_id:
        return api_response(False, message="transaction_id is required", status=400)

    result = thirdweb_service.get_transaction_status(clean_tx_id)
    if not result.get("success", False):
        return api_response(False, message=result.get("error", "Failed to retrieve transaction status"), status=400)

    return api_response(True, data=result.get("data", {}))


@app.route("/api/v1/thirdweb/wait-hash/<transaction_id>", methods=["GET"])
def api_thirdweb_wait_hash(transaction_id: str):
    """Waits for and returns onchain transaction hash."""
    clean_tx_id = transaction_id.strip()
    if not clean_tx_id:
        return api_response(False, message="transaction_id is required", status=400)

    result = thirdweb_service.wait_for_transaction_hash(clean_tx_id)
    if not result.get("success", False):
        return api_response(False, message=result.get("error", "Failed to get transaction hash"), status=400)

    return api_response(True, data=result.get("data", {}))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
