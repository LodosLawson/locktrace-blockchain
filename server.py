"""
BlockChainT - Production API Server v1
========================================
Güvenli, rate-limited, versiyonlu REST API.
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

# Config
sys.path.insert(0, os.path.dirname(__file__))
from config import Config
from core.blockchain import Blockchain, TREASURY_ADDRESS, TOTAL_SUPPLY
from core.wallet import Wallet, restore_wallet

# ══════════════════════════════════════════════════════════
#  UYGULAMA OLUŞTURMA
# ══════════════════════════════════════════════════════════

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.from_object(Config)

# CORS
CORS(app, resources={r"/api/*": {"origins": Config.CORS_ORIGINS}})

# Rate Limiter (flask-limiter opsiyonel — yoksa devam et)
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
    HAS_LIMITER = False
    class FakeLimiter:
        def limit(self, *a, **kw):
            def decorator(f): return f
            return decorator
    limiter = FakeLimiter()

# Loglama
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Config.LOG_FILE, encoding="utf-8"),
    ]
)
logger = logging.getLogger("BlockChainT")

# Blockchain başlat
blockchain = Blockchain(auto_mine=Config.AUTO_MINE)
logger.info(f"Blockchain başlatıldı: {len(blockchain.chain)} blok, {len(blockchain.wallets)} cüzdan")

# Admin API anahtarını logla (ilk çalıştırma)
logger.info(f"Admin API Key: {Config.ADMIN_API_KEY}")


# ══════════════════════════════════════════════════════════
#  MIDDLEWARE / YARDIMCILAR
# ══════════════════════════════════════════════════════════

@app.before_request
def before_request():
    g.start_time = time.time()
    # Basit request ID
    g.request_id = secrets.token_hex(8)

@app.after_request
def after_request(response):
    # İşlem süresi
    duration = time.time() - getattr(g, 'start_time', time.time())
    response.headers["X-Request-ID"] = getattr(g, 'request_id', 'unknown')
    response.headers["X-Response-Time"] = f"{duration:.4f}s"
    response.headers["X-Powered-By"] = "BlockChainT/1.0"

    # Güvenlik başlıkları
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"

    # Log
    if request.path.startswith("/api/"):
        logger.info(
            f"[{g.request_id}] {request.method} {request.path} "
            f"→ {response.status_code} ({duration:.3f}s) "
            f"IP:{request.remote_addr}"
        )
    return response


def require_admin_key(f):
    """Admin API key gerektiren endpoint'ler için dekoratör."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if not api_key or api_key != Config.ADMIN_API_KEY:
            logger.warning(f"Yetkisiz admin erişim denemesi: {request.remote_addr}")
            return jsonify({
                "success": False,
                "error": "unauthorized",
                "message": "Geçersiz veya eksik API anahtarı"
            }), 401
        return f(*args, **kwargs)
    return decorated


def api_response(success: bool, data=None, message=None, status=200, **extra):
    """Standart API yanıt formatı."""
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
    """BCT adres formatını doğrula."""
    if not addr or not isinstance(addr, str):
        return False
    if addr == TREASURY_ADDRESS:
        return True
    return addr.startswith("BCT") and len(addr) == 43 and all(c in "0123456789abcdef" for c in addr[3:])


def validate_amount(amount) -> tuple:
    """Miktar doğrulama."""
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return None, "Geçersiz miktar formatı"
    if amount < Config.MIN_TRANSACTION:
        return None, f"Minimum transfer: {Config.MIN_TRANSACTION} BCT"
    if amount > Config.MAX_TRANSACTION:
        return None, f"Maksimum transfer: {Config.MAX_TRANSACTION:,.0f} BCT"
    return amount, None


# ══════════════════════════════════════════════════════════
#  HATA İŞLEYİCİLER
# ══════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    return api_response(False, message="Endpoint bulunamadı", status=404)

@app.errorhandler(405)
def method_not_allowed(e):
    return api_response(False, message="HTTP metodu desteklenmiyor", status=405)

@app.errorhandler(429)
def rate_limited(e):
    return api_response(False, message="Çok fazla istek. Lütfen bekleyin.", status=429)

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Sunucu hatası: {e}")
    return api_response(False, message="Sunucu hatası", status=500)


# ══════════════════════════════════════════════════════════
#  WEB ARAYÜZÜ
# ══════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ══════════════════════════════════════════════════════════
#  API v1 — SAĞLIK / İSTATİSTİK
# ══════════════════════════════════════════════════════════

@app.route("/api/v1/health", methods=["GET"])
@limiter.limit("60/minute")
def api_health():
    """Sunucu sağlık kontrolü."""
    return api_response(True, data={
        "status": "healthy",
        "version": "1.0.0",
        "network": "mainnet",
        "uptime": time.time(),
        "chain_valid": blockchain.is_chain_valid()
    })


@app.route("/api/v1/stats", methods=["GET"])
@limiter.limit(Config.RATE_LIMIT_QUERY)
def api_stats():
    """Blockchain istatistikleri."""
    return api_response(True, data=blockchain.get_stats())


@app.route("/api/v1/network", methods=["GET"])
@limiter.limit(Config.RATE_LIMIT_QUERY)
def api_network():
    """Ağ bilgileri."""
    stats = blockchain.get_stats()
    return api_response(True, data={
        "network": "mainnet",
        "version": "1.0.0",
        "coin": "BCT",
        "total_supply": TOTAL_SUPPLY,
        "fee_percent": 1,
        "difficulty": blockchain.difficulty,
        "total_blocks": stats["total_blocks"],
        "total_wallets": stats["total_wallets"],
        "total_transactions": stats["total_transactions"],
    })


# ══════════════════════════════════════════════════════════
#  API v1 — CÜZDAN
# ══════════════════════════════════════════════════════════

@app.route("/api/v1/wallet/create", methods=["POST"])
@limiter.limit(Config.RATE_LIMIT_WALLET_CREATE)
def api_create_wallet():
    """Yeni cüzdan oluştur."""
    try:
        wallet = Wallet()
        success, message = blockchain.register_wallet(
            wallet.address, wallet.get_public_key_hex()
        )
        if success:
            logger.info(f"Yeni cüzdan: {wallet.address}")
            return api_response(True, message=message, data={
                "address": wallet.address,
                "public_key": wallet.get_public_key_hex(),
                "private_key": wallet.get_private_key_hex(),
                "balance": blockchain.get_balance(wallet.address)
            }, status=201)
        return api_response(False, message=message, status=400)
    except Exception as e:
        logger.error(f"Cüzdan oluşturma hatası: {e}")
        return api_response(False, message="Cüzdan oluşturulamadı", status=500)


@app.route("/api/v1/wallet/import", methods=["POST"])
@limiter.limit(Config.RATE_LIMIT_WALLET_CREATE)
def api_import_wallet():
    """Private key ile cüzdan içe aktar."""
    data = request.get_json(silent=True)
    if not data or "private_key" not in data:
        return api_response(False, message="private_key alanı gerekli", status=400)

    pk = data["private_key"].strip()
    if not pk or len(pk) != 64 or not all(c in "0123456789abcdef" for c in pk):
        return api_response(False, message="Geçersiz private key formatı (64 hex karakter)", status=400)

    try:
        wallet = restore_wallet(pk)
        if wallet.address in blockchain.wallets:
            return api_response(True, message="Cüzdan geri yüklendi (zaten kayıtlı)", data={
                "address": wallet.address,
                "public_key": wallet.get_public_key_hex(),
                "private_key": wallet.get_private_key_hex(),
                "balance": blockchain.get_balance(wallet.address)
            })
        success, message = blockchain.register_wallet(
            wallet.address, wallet.get_public_key_hex()
        )
        return api_response(True, message=message, data={
            "address": wallet.address,
            "public_key": wallet.get_public_key_hex(),
            "private_key": wallet.get_private_key_hex(),
            "balance": blockchain.get_balance(wallet.address)
        }, status=201)
    except Exception as e:
        logger.error(f"Cüzdan import hatası: {e}")
        return api_response(False, message=f"Geçersiz private key: {str(e)}", status=400)


@app.route("/api/v1/wallet/list", methods=["GET"])
@limiter.limit(Config.RATE_LIMIT_QUERY)
def api_wallet_list():
    """Tüm cüzdanları listele."""
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 100)

    wallets = blockchain.get_wallet_list()
    total = len(wallets)
    start = (page - 1) * per_page
    end = start + per_page

    return api_response(True, data={
        "wallets": wallets[start:end],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page
        }
    })


# ══════════════════════════════════════════════════════════
#  API v1 — BAKİYE
# ══════════════════════════════════════════════════════════

@app.route("/api/v1/balance/<address>", methods=["GET"])
@limiter.limit(Config.RATE_LIMIT_QUERY)
def api_balance(address):
    """Cüzdan bakiyesi sorgula."""
    if not validate_address(address):
        return api_response(False, message="Geçersiz adres formatı", status=400)

    return api_response(True, data={
        "address": address,
        "balance": blockchain.get_balance(address),
        "exists": address in blockchain.wallets or address == TREASURY_ADDRESS
    })


# ══════════════════════════════════════════════════════════
#  API v1 — İŞLEM (TRANSFER)
# ══════════════════════════════════════════════════════════

@app.route("/api/v1/transaction", methods=["POST"])
@limiter.limit(Config.RATE_LIMIT_TRANSACTION)
def api_transaction():
    """Coin transfer et."""
    data = request.get_json(silent=True)
    if not data:
        return api_response(False, message="JSON body gerekli", status=400)

    # Alan doğrulama
    required = ["sender", "receiver", "amount", "private_key"]
    missing = [f for f in required if f not in data]
    if missing:
        return api_response(False, message=f"Eksik alanlar: {', '.join(missing)}", status=400)

    # Adres doğrulama
    if not validate_address(data["sender"]):
        return api_response(False, message="Geçersiz gönderen adresi", status=400)
    if not validate_address(data["receiver"]):
        return api_response(False, message="Geçersiz alıcı adresi", status=400)
    if data["sender"] == data["receiver"]:
        return api_response(False, message="Kendinize transfer yapamazsınız", status=400)

    # Miktar doğrulama
    amount, err = validate_amount(data["amount"])
    if err:
        return api_response(False, message=err, status=400)

    # Private key doğrulama
    pk = str(data["private_key"]).strip()
    if not pk or len(pk) != 64:
        return api_response(False, message="Geçersiz private key", status=400)

    try:
        wallet = restore_wallet(pk)
        if wallet.address != data["sender"]:
            logger.warning(f"Key mismatch: {data['sender']} IP:{request.remote_addr}")
            return api_response(False, message="Private key gönderen adresle eşleşmiyor", status=403)
    except Exception:
        return api_response(False, message="Geçersiz private key", status=400)

    # İşlem imzası
    tx_data = f"{data['sender']}{data['receiver']}{amount}"
    signature = wallet.sign(tx_data)

    # Transfer
    success, message, tx_info = blockchain.create_transaction(
        sender=data["sender"],
        receiver=data["receiver"],
        amount=amount,
        signature=signature
    )

    if success:
        logger.info(f"Transfer: {data['sender'][:12]}→{data['receiver'][:12]} {amount} BCT")
        return api_response(True, message=message, data=tx_info, status=201)

    return api_response(False, message=message, status=400)


# ══════════════════════════════════════════════════════════
#  API v1 — ZİNCİR / BLOKLAR / İŞLEM GEÇMİŞİ
# ══════════════════════════════════════════════════════════

@app.route("/api/v1/chain", methods=["GET"])
@limiter.limit(Config.RATE_LIMIT_QUERY)
def api_chain():
    """Tüm blockchain (sayfalı)."""
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 50)

    chain = blockchain.get_chain_data()
    total = len(chain)
    start = (page - 1) * per_page
    end = start + per_page

    return api_response(True, data={
        "chain": chain[start:end],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page
        }
    })


@app.route("/api/v1/blocks/latest", methods=["GET"])
@limiter.limit(Config.RATE_LIMIT_QUERY)
def api_latest_blocks():
    """Son N blok."""
    count = min(request.args.get("count", 10, type=int), 50)
    return api_response(True, data={"blocks": blockchain.get_latest_blocks(count)})


@app.route("/api/v1/blocks/<int:index>", methods=["GET"])
@limiter.limit(Config.RATE_LIMIT_QUERY)
def api_block_by_index(index):
    """Blok numarasına göre sorgula."""
    if index < 0 or index >= len(blockchain.chain):
        return api_response(False, message="Blok bulunamadı", status=404)
    return api_response(True, data=blockchain.chain[index].to_dict())


@app.route("/api/v1/transactions/latest", methods=["GET"])
@limiter.limit(Config.RATE_LIMIT_QUERY)
def api_latest_transactions():
    """Son işlemler."""
    limit = min(request.args.get("limit", 50, type=int), 200)
    txs = blockchain.get_all_transactions()
    return api_response(True, data={
        "transactions": txs[:limit],
        "total": len(txs)
    })


@app.route("/api/v1/transactions/<address>", methods=["GET"])
@limiter.limit(Config.RATE_LIMIT_QUERY)
def api_wallet_transactions(address):
    """Bir cüzdanın işlem geçmişi."""
    if not validate_address(address):
        return api_response(False, message="Geçersiz adres formatı", status=400)

    txs = blockchain.get_wallet_transactions(address)
    return api_response(True, data={
        "address": address,
        "transactions": txs,
        "total": len(txs)
    })


# ══════════════════════════════════════════════════════════
#  API v1 — MADENCİLİK
# ══════════════════════════════════════════════════════════

@app.route("/api/v1/mine", methods=["POST"])
@limiter.limit("10/minute")
def api_mine():
    """Bekleyen işlemleri madencilikle bloka ekle."""
    block_data, message = blockchain.mine_pending()
    if block_data:
        logger.info(f"Blok #{block_data['index']} kazıldı")
        return api_response(True, message=message, data=block_data, status=201)
    return api_response(False, message=message)


# ══════════════════════════════════════════════════════════
#  API v1 — DOĞRULAMA
# ══════════════════════════════════════════════════════════

@app.route("/api/v1/validate", methods=["GET"])
@limiter.limit("10/minute")
def api_validate():
    """Zincir bütünlüğünü doğrula."""
    valid = blockchain.is_chain_valid()
    return api_response(True, data={
        "valid": valid,
        "total_blocks": len(blockchain.chain),
        "message": "Zincir geçerli ✓" if valid else "Zincir BOZUK ✗"
    })


# ══════════════════════════════════════════════════════════
#  API v1 — ADMIN (API Key gerekli)
# ══════════════════════════════════════════════════════════

@app.route("/api/v1/admin/reset", methods=["POST"])
@require_admin_key
def api_reset():
    """Blockchain'i sıfırla (DİKKAT!)."""
    logger.warning(f"Blockchain sıfırlama! IP:{request.remote_addr}")
    success, message = blockchain.reset()
    return api_response(success, message=message)


@app.route("/api/v1/admin/config", methods=["GET"])
@require_admin_key
def api_admin_config():
    """Sunucu yapılandırma bilgileri."""
    return api_response(True, data={
        "rate_limiter": HAS_LIMITER,
        "cors_origins": Config.CORS_ORIGINS,
        "debug": Config.DEBUG,
        "auto_mine": Config.AUTO_MINE,
        "min_transaction": Config.MIN_TRANSACTION,
        "max_transaction": Config.MAX_TRANSACTION,
        "difficulty": blockchain.difficulty,
    })


# ══════════════════════════════════════════════════════════
#  ESKİ API UYUMU (/api/stats → /api/v1/stats)
# ══════════════════════════════════════════════════════════

@app.route("/api/stats", methods=["GET"])
def api_stats_compat():
    return api_response(True, data=blockchain.get_stats())

@app.route("/api/wallet/create", methods=["POST"])
def api_create_wallet_compat():
    return api_create_wallet()

@app.route("/api/wallet/import", methods=["POST"])
def api_import_wallet_compat():
    return api_import_wallet()

@app.route("/api/wallet/list", methods=["GET"])
def api_wallet_list_compat():
    return api_wallet_list()

@app.route("/api/balance/<address>", methods=["GET"])
def api_balance_compat(address):
    return api_balance(address)

@app.route("/api/transaction", methods=["POST"])
def api_transaction_compat():
    return api_transaction()

@app.route("/api/chain", methods=["GET"])
def api_chain_compat():
    return api_chain()

@app.route("/api/blocks/latest", methods=["GET"])
def api_latest_blocks_compat():
    return api_latest_blocks()

@app.route("/api/transactions/latest", methods=["GET"])
def api_latest_transactions_compat():
    return api_latest_transactions()

@app.route("/api/transactions/<address>", methods=["GET"])
def api_wallet_transactions_compat(address):
    return api_wallet_transactions(address)

@app.route("/api/mine", methods=["POST"])
def api_mine_compat():
    return api_mine()

@app.route("/api/validate", methods=["GET"])
def api_validate_compat():
    return api_validate()

@app.route("/api/reset", methods=["POST"])
def api_reset_compat():
    return api_reset()


# ══════════════════════════════════════════════════════════
#  BAŞLAT
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"""
    ╔══════════════════════════════════════════╗
    ║        🔗 BlockChainT v1.0              ║
    ║   Kompakt Blockchain - 1 Trilyon BCT    ║
    ║                                         ║
    ║   API:  http://localhost:{Config.PORT}/api/v1/stats
    ║   Web:  http://localhost:{Config.PORT}            
    ║   Admin Key: {Config.ADMIN_API_KEY[:8]}...       
    ╚══════════════════════════════════════════╝
    """)
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
