"""
BlockChainT - Hardened & Transparent API Server
===============================================
Universal Explorer Endpoints, Cryptographic Signature Verification,
Thread-Safe Rate Limiting & High-Resiliency Transaction Processing.
"""

import os
import re
import sys
import json
import math
import time
import hashlib
import logging
import secrets
import threading
from collections import deque
from datetime import datetime
from typing import Optional

from flask import Flask, request, jsonify, render_template, g, send_file, Response
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(__file__))
from config import Config
from core.blockchain import (
    Blockchain,
    TREASURY_ADDRESS,
    TOTAL_SUPPLY,
    BLOCK_REWARD,
    MINER_FEE_SHARE,
    RELEASE_AUTHORITY_ADDRESS,
    RELEASE_AUTHORITY_PUBKEY,
    is_valid_bct_address,
    verify_frontend_manifest,
)
from core.wallet import (
    Wallet,
    restore_wallet,
    restore_wallet_from_mnemonic,
    public_key_to_address,
    verify_signature,
)
from core.mnemonic import generate_mnemonic, validate_mnemonic
from core.thirdweb_service import thirdweb_service

app = Flask(__name__, template_folder="templates", static_folder="frontend", static_url_path="")
app.config.from_object(Config)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB strict JSON body cap

CORS(app, resources={r"/api/*": {"origins": Config.CORS_ORIGINS or "*"}})

# Logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Config.LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("LockTrace")

blockchain = Blockchain(auto_mine=True)
logger.info(f"LockTrace Initialized: {len(blockchain.chain)} blocks, {len(blockchain.wallets)} wallets")

EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
SAFE_CHAIN_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")
SAFE_TX_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{4,128}$")


# ── Thread-Safe Sliding Window Rate Limiter & Replay Cache ───
class SlidingWindowRateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._buckets = {}
        self._used_signatures = {}
        self._last_cleanup = time.time()

    def _cleanup_if_needed(self, now: float):
        if now - self._last_cleanup < 120:
            return
        self._last_cleanup = now
        stale_keys = [k for k, dq in self._buckets.items() if not dq or (now - dq[-1] > 3600)]
        for k in stale_keys:
            self._buckets.pop(k, None)
        expired_sigs = [s for s, exp in self._used_signatures.items() if now > exp]
        for s in expired_sigs:
            self._used_signatures.pop(s, None)

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        with self._lock:
            self._cleanup_if_needed(now)
            dq = self._buckets.get(key)
            if dq is None:
                dq = deque()
                self._buckets[key] = dq
            cutoff = now - window_seconds
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(now)
            return True

    def register_signature_once(self, sig_hex: str, ttl_seconds: int = 600) -> bool:
        """Returns True if signature has not been seen inside replay window."""
        now = time.time()
        with self._lock:
            self._cleanup_if_needed(now)
            exp = self._used_signatures.get(sig_hex)
            if exp and now <= exp:
                return False
            self._used_signatures[sig_hex] = now + ttl_seconds
            return True


rate_limiter = SlidingWindowRateLimiter()


def get_client_ip() -> str:
    """Resolve client IP safely (prefers Nginx X-Real-IP over spoofable headers)."""
    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        return real_ip[:64]
    return (request.remote_addr or "127.0.0.1")[:64]


def check_rate_limit(scope: str, limit: int, window_seconds: int = 60) -> bool:
    ip = get_client_ip()
    return rate_limiter.allow(f"{scope}:{ip}", limit, window_seconds)


def safe_float(val, default: Optional[float] = None) -> Optional[float]:
    try:
        num = float(val)
        if not math.isfinite(num):
            return default
        return num
    except (ValueError, TypeError):
        return default


def safe_int(val, default: int = 0, min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
    try:
        num = int(val)
    except (ValueError, TypeError):
        num = default
    if min_val is not None:
        num = max(min_val, num)
    if max_val is not None:
        num = min(max_val, num)
    return num


def resolve_authenticated_action(data: dict, expected_address: str, canonical_payload: str):
    """
    Cryptographically authenticate a state-changing wallet action.
    Supports:
      1) Custodial-assisted signing via 12-word `mnemonic` or 64-hex `private_key`
      2) Non-custodial client-side ECDSA signing via `public_key`, `signature`, and `timestamp`
    Returns: (ok: bool, status_code: int, error_msg: str, signature: str, public_key: str, signed_payload: str)
    """
    clean_expected = (expected_address or "").strip()
    if not is_valid_bct_address(clean_expected) or clean_expected.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT"):
        return False, 400, "Geçersiz cüzdan adresi formatı.", "", "", ""

    mnemonic_phrase = str(data.get("mnemonic", "") or "").strip()
    private_key_hex = str(data.get("private_key", "") or "").strip()
    client_sig = str(data.get("signature", "") or "").strip()
    client_pub = str(data.get("public_key", "") or "").strip()
    client_ts = data.get("timestamp")

    # Path 1: Mnemonic or Private Key provided
    if mnemonic_phrase or private_key_hex:
        try:
            if mnemonic_phrase and len(mnemonic_phrase.split()) >= 12:
                wallet = restore_wallet_from_mnemonic(mnemonic_phrase)
            elif private_key_hex and len(private_key_hex) == 64:
                wallet = restore_wallet(private_key_hex)
            else:
                return False, 400, "Geçersiz imza anahtarı (12 kelime kurtarma ifadesi veya 64 karakter özel anahtar gerekli).", "", "", ""

            if wallet.address != clean_expected:
                logger.warning(f"Auth mismatch: key {wallet.address[:10]}... attempted action as {clean_expected[:10]}...")
                return False, 403, "İmza anahtarı belirtilen cüzdan adresiyle eşleşmiyor!", "", "", ""

            cand_primary = canonical_payload[0] if isinstance(canonical_payload, (list, tuple)) else canonical_payload
            nonce_ts = f"{int(time.time() * 1000)}:{secrets.token_hex(4)}"
            signed_payload = f"{cand_primary}:{nonce_ts}"
            sig = wallet.sign(signed_payload)
            return True, 200, "", sig, wallet.get_public_key_hex(), signed_payload
        except Exception:
            return False, 400, "Cüzdan anahtarı doğrulanamadı.", "", "", ""

    # Path 2: Client-side ECDSA signature (Non-custodial mode)
    if client_sig:
        pub_hex = client_pub or blockchain.wallets.get(clean_expected, {}).get("public_key", "")
        if not pub_hex:
            return False, 401, "İmza doğrulaması için public_key gereklidir.", "", "", ""

        if public_key_to_address(pub_hex) != clean_expected:
            return False, 403, "Açık anahtar (public_key) cüzdan adresiyle uyuşmuyor!", "", "", ""

        client_nonce = data.get("nonce")
        expected_nonce = None
        if client_nonce is not None:
            expected_nonce = blockchain.get_account_nonce(clean_expected)
            if safe_int(client_nonce, default=-1) != expected_nonce:
                return False, 409, f"Geçersiz işlem sırası (nonce). Beklenen: {expected_nonce}", "", "", ""

        candidates = canonical_payload if isinstance(canonical_payload, (list, tuple)) else [canonical_payload]
        signed_payload = ""
        verified_ok = False
        for cand in candidates:
            if client_ts is not None:
                ts_val = safe_float(client_ts)
                if ts_val is None or abs(time.time() - ts_val) > 300:
                    return False, 401, "İmza zaman damgası (timestamp) süresi dolmuş veya geçersiz.", "", "", ""
                cand_signed = f"{cand}:{client_ts}:{expected_nonce}" if expected_nonce is not None else f"{cand}:{client_ts}"
            else:
                cand_signed = f"{cand}:{expected_nonce}" if expected_nonce is not None else cand
            if verify_signature(pub_hex, cand_signed, client_sig):
                signed_payload = cand_signed
                verified_ok = True
                break

        if not verified_ok:
            return False, 403, "Geçersiz ECDSA dijital imza!", "", "", ""

        if not rate_limiter.register_signature_once(client_sig):
            return False, 409, "Tekrarlanan (replay) imza reddedildi.", "", "", ""

        return True, 200, "", client_sig, pub_hex, signed_payload

    return False, 401, "Bu işlem için cüzdan imzası (kimlik doğrulaması) zorunludur.", "", "", ""


@app.before_request
def before_request():
    g.start_time = time.time()
    g.request_id = secrets.token_hex(8)


@app.after_request
def after_request(response):
    duration = time.time() - getattr(g, "start_time", time.time())
    response.headers["X-Request-ID"] = getattr(g, "request_id", "unknown")
    response.headers["X-Response-Time"] = f"{duration:.4f}s"
    response.headers["X-Powered-By"] = "LockTrace-Blockchain/1.4"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    origin = request.headers.get("Origin", "")
    allowed = [o.strip() for o in (Config.CORS_ORIGINS or []) if o.strip()]
    if origin and (not allowed or "*" in allowed or origin in allowed):
        response.headers["Access-Control-Allow-Origin"] = origin
    elif "Access-Control-Allow-Origin" not in response.headers:
        response.headers["Access-Control-Allow-Origin"] = allowed[0] if allowed else "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key"
    return response


def api_response(success: bool, data=None, message=None, status=200, **extra):
    body = {
        "success": success,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "request_id": getattr(g, "request_id", None),
    }
    if data is not None:
        body["data"] = data
    if message:
        body["message"] = message
    body.update(extra)
    return jsonify(body), status


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def _inspect_local_frontend_integrity() -> dict:
    """Verify local frontend/index.html & sw.js SHA-256 checksums + ECDSA Release Authority signature."""
    index_path = os.path.join(ROOT_DIR, "frontend", "index.html")
    sw_path = os.path.join(ROOT_DIR, "frontend", "sw.js")
    manifest_path = os.path.join(ROOT_DIR, "frontend", "integrity.json")

    if not os.path.exists(index_path) or not os.path.exists(manifest_path):
        return {
            "verified": False,
            "reason": "⛔ UYARI: Bu frontend dosyası değiştirilmiş veya manipüle edilmiş! Çalıştırılamaz. (integrity.json eksik)",
        }

    try:
        with open(manifest_path, "r", encoding="utf-8") as mf:
            manifest = json.load(mf)
        with open(index_path, "rb") as ix:
            index_bytes = ix.read().replace(b"\r\n", b"\n")
        actual_index_sha = hashlib.sha256(index_bytes).hexdigest()

        actual_sw_sha = ""
        if os.path.exists(sw_path):
            with open(sw_path, "rb") as sf:
                actual_sw_sha = hashlib.sha256(sf.read().replace(b"\r\n", b"\n")).hexdigest()

        sig_ok, sig_msg = verify_frontend_manifest(manifest)
        if not sig_ok:
            return {
                "verified": False,
                "reason": f"⛔ UYARI: Bu frontend dosyası değiştirilmiş veya manipüle edilmiş! Çalıştırılamaz. ({sig_msg})",
                "actual_index_sha256": actual_index_sha,
            }

        expected_index_sha = str(manifest.get("index_html_sha256", "")).lower()
        expected_sw_sha = str(manifest.get("sw_js_sha256", "")).lower()
        if actual_index_sha != expected_index_sha:
            return {
                "verified": False,
                "reason": "⛔ UYARI: Bu frontend dosyası değiştirilmiş veya manipüle edilmiş! Çalıştırılamaz.",
                "expected_index_sha256": expected_index_sha,
                "actual_index_sha256": actual_index_sha,
            }
        if expected_sw_sha and actual_sw_sha and actual_sw_sha != expected_sw_sha:
            return {
                "verified": False,
                "reason": "⛔ UYARI: Service Worker (sw.js) değiştirilmiş veya manipüle edilmiş! Çalıştırılamaz.",
                "expected_sw_sha256": expected_sw_sha,
                "actual_sw_sha256": actual_sw_sha,
            }

        return {
            "verified": True,
            "manifest": manifest,
            "index_bytes": index_bytes,
            "actual_index_sha256": actual_index_sha,
            "actual_sw_sha256": actual_sw_sha,
        }
    except Exception as exc:
        return {
            "verified": False,
            "reason": f"⛔ UYARI: Bu frontend dosyası değiştirilmiş veya manipüle edilmiş! Çalıştırılamaz. ({exc})",
        }


def _bootstrap_onchain_frontend_seal():
    check = _inspect_local_frontend_integrity()
    if check.get("verified") and check.get("manifest"):
        ok, msg, sealed = blockchain.seal_frontend_release(check["manifest"])
        if ok and sealed:
            logger.info(
                f"Frontend Integrity Sealed On-Chain: v{sealed.get('version')} "
                f"SHA256={sealed.get('index_html_sha256', '')[:16]}... Block=#{sealed.get('block_index')}"
            )
    else:
        logger.warning(f"Frontend Integrity Check Alert: {check.get('reason')}")


_bootstrap_onchain_frontend_seal()


def _serve_verified_frontend_response():
    check = _inspect_local_frontend_integrity()
    if not check.get("verified"):
        warn_html = f"""<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8"><title>Güvenlik Kilidi - LockTrace</title>
        <style>body{{background:#131315;color:#ffb4ab;font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:24px;}}
        .card{{max-width:620px;background:#1f1f21;border:1px solid #93000a;border-radius:16px;padding:32px;box-shadow:0 20px 50px rgba(0,0,0,0.6);}}
        code{{display:block;background:#0e0e10;color:#e5e1e4;padding:12px;border-radius:8px;margin-top:12px;word-break:break-all;font-size:12px;}}</style></head>
        <body><div class="card"><h2>⛔ UYARI: Bu frontend dosyası değiştirilmiş veya manipüle edilmiş! Çalıştırılamaz.</h2>
        <p style="color:#e5e1e4;line-height:1.6;">LockTrace SHA-256 Sağlama Toplamı ve ECDSA Sürüm İmzası doğrulaması başarısız oldu. Cüzdan güvenliğiniz için arayüz yüklenmesi engellendi.</p>
        <code>Beklenen SHA-256: {check.get('expected_index_sha256', 'Bilinmiyor')}<br>Mevcut SHA-256: {check.get('actual_index_sha256', 'Geçersiz')}</code></div></body></html>"""
        return Response(warn_html, status=403, mimetype="text/html")

    resp = Response(check["index_bytes"], status=200, mimetype="text/html; charset=utf-8")
    resp.headers["X-Frontend-SHA256"] = check["actual_index_sha256"]
    resp.headers["X-Frontend-IPFS-CID"] = check["manifest"].get("ipfs_cid_v1", "")
    resp.headers["X-Frontend-Signature"] = check["manifest"].get("signature", "")
    return resp


@app.errorhandler(404)
def handle_404(_err):
    if request.path.startswith("/api/"):
        return api_response(False, message="API uç noktası bulunamadı.", status=404)
    return _serve_verified_frontend_response()


@app.errorhandler(405)
def handle_405(_err):
    return api_response(False, message="Bu uç nokta için HTTP metodu desteklenmiyor.", status=405)


@app.errorhandler(413)
def handle_413(_err):
    return api_response(False, message="İstek boyutu çok büyük (Maksimum 1 MB).", status=413)


@app.errorhandler(500)
def handle_500(err):
    logger.error(f"Unhandled server error [{getattr(g, 'request_id', '-')}]: {err}")
    return api_response(False, message="Sunucu tarafında beklenmeyen bir hata oluştu.", status=500)


# ── Web Shell Entrypoint (Cryptographically Verified) ────────
@app.route("/", methods=["GET"])
@app.route("/index.html", methods=["GET"])
def index_page():
    return _serve_verified_frontend_response()


@app.route("/api/v1/frontend/integrity", methods=["GET"])
def api_frontend_integrity():
    check = _inspect_local_frontend_integrity()
    onchain = blockchain.get_latest_frontend_release()
    manifest = check.get("manifest") or onchain or {}
    return api_response(True, data={
        "verified": bool(check.get("verified")),
        "version": manifest.get("version", "1.5.0"),
        "released_at": manifest.get("released_at", ""),
        "authority_address": RELEASE_AUTHORITY_ADDRESS,
        "authority_public_key": RELEASE_AUTHORITY_PUBKEY,
        "index_html_sha256": check.get("actual_index_sha256") or manifest.get("index_html_sha256", ""),
        "expected_index_sha256": manifest.get("index_html_sha256", ""),
        "sw_js_sha256": check.get("actual_sw_sha256") or manifest.get("sw_js_sha256", ""),
        "ipfs_cid_v1": manifest.get("ipfs_cid_v1", ""),
        "signature": manifest.get("signature", ""),
        "onchain_anchor": onchain,
        "warning": None if check.get("verified") else check.get("reason"),
    })


# ── Health & Stats ───────────────────────────────────────────
@app.route("/api/v1/health", methods=["GET"])
def api_health():
    check = _inspect_local_frontend_integrity()
    return api_response(True, data={
        "status": "healthy",
        "version": "1.5.0",
        "network": "mainnet",
        "storage_engine": "sqlite-wal",
        "consensus": "pow-v2-merkle-quorum",
        "merkle_enabled": True,
        "non_custodial_signing": True,
        "multi_node_p2p": True,
        "frontend_verified": bool(check.get("verified")),
        "frontend_sha256": check.get("actual_index_sha256", ""),
        "chain_valid": blockchain.is_chain_valid(),
    })


@app.route("/api/v1/stats", methods=["GET"])
def api_stats():
    return api_response(True, data=blockchain.get_stats())


# ── Wallet Mnemonic Preview & Creation ───────────────────────
@app.route("/api/v1/wallet/mnemonic-preview", methods=["GET"])
def api_mnemonic_preview():
    """Generates a 12-word BIP-39 phrase in memory without minting a block or spending Treasury funds."""
    if not check_rate_limit("mnemonic_preview", limit=20, window_seconds=60):
        return api_response(False, message="Çok fazla kelime üretme isteği gönderildi. Lütfen 1 dakika bekleyin.", status=429)
    phrase = generate_mnemonic()
    return api_response(True, data={"mnemonic": phrase})


@app.route("/api/v1/wallet/create", methods=["POST"])
def api_create_wallet():
    if not check_rate_limit("wallet_create_min", limit=5, window_seconds=60) or not check_rate_limit("wallet_create_hr", limit=15, window_seconds=3600):
        return api_response(False, message="Cüzdan oluşturma sınırına ulaştınız. Lütfen daha sonra tekrar deneyin.", status=429)

    data = request.get_json(silent=True) or {}
    client_address = str(data.get("address", "") or "").strip()
    client_pubkey = str(data.get("public_key", "") or "").strip()
    provided_mnemonic = str(data.get("mnemonic", "") or "").strip()

    try:
        # Path A: 100% Zero-Knowledge Client-Side Keygen (mnemonic & private_key never leave browser!)
        if client_address and client_pubkey and not provided_mnemonic:
            if public_key_to_address(client_pubkey) != client_address:
                return api_response(False, message="Açık anahtar (public_key) ile cüzdan adresi uyuşmuyor.", status=400)
            success, message = blockchain.register_wallet(client_address, client_pubkey)
            if success:
                logger.info(f"Non-Custodial Account Registered: {client_address} (ip={get_client_ip()})")
                return api_response(True, message=message, data={
                    "address": client_address,
                    "public_key": client_pubkey,
                    "balance": blockchain.get_balance(client_address),
                    "nonce": blockchain.get_account_nonce(client_address),
                }, status=201)
            return api_response(False, message=message, status=400)

        # Path B: Legacy / API Mnemonic Keygen
        if provided_mnemonic:
            cleaned = " ".join(provided_mnemonic.lower().split())
            if not validate_mnemonic(cleaned):
                return api_response(False, message="Geçersiz 12 kelimelik BIP-39 kurtarma ifadesi.", status=400)
            wallet = Wallet(mnemonic=cleaned)
        else:
            wallet = Wallet()

        success, message = blockchain.register_wallet(
            wallet.address, wallet.get_public_key_hex()
        )
        if success:
            logger.info(f"Account Created: {wallet.address} (ip={get_client_ip()})")
            return api_response(True, message=message, data={
                "address": wallet.address,
                "mnemonic": wallet.mnemonic,
                "public_key": wallet.get_public_key_hex(),
                "private_key": wallet.get_private_key_hex(),
                "balance": blockchain.get_balance(wallet.address),
                "nonce": blockchain.get_account_nonce(wallet.address),
            }, status=201)
        return api_response(False, message=message, status=400)
    except Exception as e:
        logger.error(f"Account creation exception: {e}")
        return api_response(False, message="Cüzdan oluşturulurken bir hata oluştu.", status=500)


# ── Wallet Import ────────────────────────────────────────────
@app.route("/api/v1/wallet/import", methods=["POST"])
def api_import_wallet():
    if not check_rate_limit("wallet_import", limit=15, window_seconds=60):
        return api_response(False, message="Çok fazla içe aktarma denemesi. Lütfen 1 dakika bekleyin.", status=429)

    data = request.get_json(silent=True) or {}
    client_address = str(data.get("address", "") or "").strip()
    client_pubkey = str(data.get("public_key", "") or "").strip()
    mnemonic_phrase = str(data.get("mnemonic", "") or "").strip()
    private_key_hex = str(data.get("private_key", "") or "").strip()

    try:
        # Path A: 100% Zero-Knowledge Client-Side Import (secrets stay in browser!)
        if client_address and client_pubkey and not mnemonic_phrase and not private_key_hex:
            if public_key_to_address(client_pubkey) != client_address:
                return api_response(False, message="Açık anahtar ile cüzdan adresi uyuşmuyor.", status=400)
            ok, msg = blockchain.register_wallet(client_address, client_pubkey)
            if not ok:
                return api_response(False, message=msg, status=400)
            return api_response(True, message="Cüzdan başarıyla doğrulandı ve bağlandı!", data={
                "address": client_address,
                "public_key": client_pubkey,
                "balance": blockchain.get_balance(client_address),
                "nonce": blockchain.get_account_nonce(client_address),
            })

        # Path B: Legacy / API Import
        if mnemonic_phrase:
            words = mnemonic_phrase.lower().split()
            if len(words) != 12:
                return api_response(False, message="Kurtarma ifadesi tam 12 kelimeden oluşmalıdır.", status=400)
            wallet = restore_wallet_from_mnemonic(" ".join(words))
        elif private_key_hex:
            clean_pk = private_key_hex.strip()
            if len(clean_pk) != 64 or not all(c in "0123456789abcdefABCDEF" for c in clean_pk):
                return api_response(False, message="Özel anahtar 64 karakterlik hex formatında olmalıdır.", status=400)
            wallet = restore_wallet(clean_pk)
        else:
            return api_response(False, message="12 kelimelik kurtarma ifadesi veya özel anahtar girin.", status=400)

        ok, msg = blockchain.register_wallet(wallet.address, wallet.get_public_key_hex())
        if not ok:
            return api_response(False, message=msg, status=400)
        bal = blockchain.get_balance(wallet.address)

        return api_response(True, message="Cüzdan başarıyla geri yüklendi!", data={
            "address": wallet.address,
            "mnemonic": getattr(wallet, "mnemonic", ""),
            "public_key": wallet.get_public_key_hex(),
            "private_key": wallet.get_private_key_hex(),
            "balance": bal,
            "nonce": blockchain.get_account_nonce(wallet.address),
        })
    except Exception as e:
        logger.warning(f"Wallet restoration failed: {e}")
        return api_response(False, message="Cüzdan geri yüklenemedi. Anahtarınızı kontrol edin.", status=400)


# ── Balance ──────────────────────────────────────────────────
@app.route("/api/v1/balance/<address>", methods=["GET"])
def api_balance(address):
    clean_addr = address.strip()
    if not is_valid_bct_address(clean_addr):
        return api_response(False, message="Invalid address syntax", status=400)

    bal = blockchain.get_balance(clean_addr)
    nonce = blockchain.get_account_nonce(clean_addr)
    return api_response(True, data={
        "address": clean_addr,
        "balance": bal,
        "nonce": nonce,
        "exists": clean_addr in blockchain.wallets or clean_addr == TREASURY_ADDRESS,
    })


# ── Wire Transfer (Cryptographically Verified) ───────────────
@app.route("/api/v1/transaction", methods=["POST"])
def api_transaction():
    if not check_rate_limit("tx_submit", limit=30, window_seconds=60):
        return api_response(False, message="Çok sık transfer isteği gönderildi. Lütfen kısa süre bekleyin.", status=429)

    data = request.get_json(silent=True) or {}
    sender = str(data.get("sender", "") or "").strip()
    receiver = str(data.get("receiver", "") or "").strip()
    amount_raw = data.get("amount")

    if not sender or not receiver or amount_raw is None:
        return api_response(False, message="Missing required fields: sender, receiver, amount", status=400)

    amount = safe_float(amount_raw)
    if amount is None or amount <= 0:
        return api_response(False, message="Geçerli ve pozitif bir tutar girilmelidir.", status=400)

    if amount > Config.MAX_TRANSACTION:
        return api_response(False, message=f"Tek seferde maksimum transfer sınırı {Config.MAX_TRANSACTION:,.0f} BCT'dir.", status=400)

    amount = round(amount, 8)
    amt_str_trim = f"{amount:.8f}".rstrip("0").rstrip(".") or "0"
    canonical_variants = list(dict.fromkeys([
        f"{sender}{receiver}{amount}",
        f"{sender}{receiver}{amt_str_trim}",
        f"{sender}{receiver}{amount:.8f}",
        f"{sender}{receiver}{amount_raw}",
    ]))
    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, sender, canonical_variants
    )
    if not auth_ok:
        return api_response(False, message=auth_err, status=auth_status)

    success, message, tx_info = blockchain.create_transaction(
        sender=sender,
        receiver=receiver,
        amount=amount,
        signature=signature,
        public_key=pub_key,
        signed_payload=signed_payload,
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
    q = request.args.get("q", "").strip()[:128]
    if not q:
        return api_response(False, message="Search query cannot be empty", status=400)

    block = blockchain.get_block_by_index_or_hash(q)
    if block:
        return api_response(True, data={"type": "block", "result": block})

    tx = blockchain.get_tx_by_hash(q)
    if tx:
        return api_response(True, data={"type": "transaction", "result": tx})

    if is_valid_bct_address(q):
        bal = blockchain.get_balance(q)
        history = blockchain.get_wallet_transactions(q)
        return api_response(True, data={
            "type": "address",
            "result": {
                "address": q,
                "balance": bal,
                "transaction_count": len(history),
                "transactions": history[:50],
            },
        })

    return api_response(False, message="Aranan kriterlere uygun blok, işlem veya cüzdan bulunamadı.", status=404)


@app.route("/api/v1/explorer/block/<query>", methods=["GET"])
def api_explorer_block(query):
    clean_q = (query or "").strip()[:128]
    block = blockchain.get_block_by_index_or_hash(clean_q)
    if block:
        node_meta = None
        miner_addr = block.get("miner", "")
        for _n_id, n in blockchain.nodes.items():
            if miner_addr and (n.get("miner_address") == miner_addr or n.get("endpoint") == miner_addr or n.get("node_id") == miner_addr):
                node_meta = {
                    "node_id": n.get("node_id"),
                    "name": n.get("name"),
                    "location": n.get("location"),
                    "role": n.get("role"),
                    "version": n.get("version"),
                    "status": n.get("status", "online"),
                }
                break
        if not node_meta:
            node_meta = {
                "node_id": "node-stockholm-validator-01",
                "name": "LockTrace Genesis Validator #1",
                "location": "Stockholm, Sweden (Oracle Cloud)",
                "role": "Core PoW Archival Validator",
                "version": "1.2.1",
                "status": "online",
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
    tx = blockchain.get_tx_by_hash((tx_hash or "").strip()[:128])
    if tx:
        return api_response(True, data=tx)
    return api_response(False, message="Transaction not found", status=404)


@app.route("/api/v1/explorer/merkle-proof/<tx_hash>", methods=["GET"])
def api_explorer_merkle_proof(tx_hash):
    """Generates and cryptographically verifies SPV Merkle proof for a confirmed transaction."""
    proof_data = blockchain.get_merkle_proof((tx_hash or "").strip()[:128])
    if proof_data:
        return api_response(True, data=proof_data)
    return api_response(False, message="İşlem veya Merkle kanıtı bulunamadı.", status=404)


@app.route("/api/v1/transactions/latest", methods=["GET"])
def api_latest_transactions():
    limit = safe_int(request.args.get("limit", 20), default=20, min_val=1, max_val=100)
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
    count = safe_int(request.args.get("count", 15), default=15, min_val=1, max_val=50)
    return api_response(True, data={"blocks": blockchain.get_latest_blocks(count)})


@app.route("/api/v1/chain/range", methods=["GET"])
def api_chain_range():
    """Incremental archival chain sync endpoint for decentralized peer nodes."""
    start = safe_int(request.args.get("start", 0), default=0, min_val=0)
    limit = safe_int(request.args.get("limit", 100), default=100, min_val=1, max_val=200)
    return api_response(True, data=blockchain.get_chain_range(start=start, limit=limit))


# ── Decentralized Network Nodes & P2P Consensus Endpoints ─────
@app.route("/api/v1/nodes", methods=["GET"])
def api_get_nodes():
    """List all registered network nodes with uptime, attestations, rewards, and health."""
    nodes = blockchain.get_nodes()
    online_count = sum(1 for n in nodes if n.get("status") == "online")
    verified_count = sum(1 for n in nodes if n.get("status") == "online" and (n.get("auth_verified") or n.get("is_genesis")))
    return api_response(True, data={
        "total_nodes": len(nodes),
        "online_nodes": online_count,
        "verified_nodes": verified_count,
        "reward_model": {"proposer_share": 0.70, "validator_pool_share": 0.30},
        "nodes": nodes,
    })


@app.route("/api/v1/peers", methods=["GET"])
def api_get_peers():
    """Returns active P2P peer endpoints for node-to-node mesh discovery."""
    nodes = blockchain.get_nodes()
    peers = [
        {
            "node_id": n.get("node_id"),
            "name": n.get("name"),
            "endpoint": n.get("endpoint"),
            "location": n.get("location"),
            "block_height": n.get("block_height", 0),
            "attested_height": n.get("attested_height", -1),
            "auth_verified": bool(n.get("auth_verified") or n.get("is_genesis")),
            "is_genesis": bool(n.get("is_genesis")),
        }
        for n in nodes
        if n.get("status") == "online" and str(n.get("endpoint", "")).startswith("http")
    ]
    return api_response(True, data={"peers": peers, "count": len(peers)})


@app.route("/api/v1/nodes/register", methods=["POST"])
def api_register_node():
    """Register or announce a community node into the decentralized network (with optional ECDSA ownership proof)."""
    if not check_rate_limit("node_register", limit=25, window_seconds=60):
        return api_response(False, message="Çok sık düğüm kayıt isteği gönderildi.", status=429)

    data = request.get_json(silent=True) or {}
    node_id = str(data.get("node_id", "") or "").strip()
    name = str(data.get("name", "") or "").strip()
    endpoint = str(data.get("endpoint", "") or "").strip()
    role = str(data.get("role", "Community Validator Peer") or "Community Validator Peer").strip()
    location = str(data.get("location", "Decentralized") or "Decentralized").strip()
    miner_address = str(data.get("miner_address", "") or "").strip()
    block_height = safe_int(data.get("block_height", 0), default=0, min_val=0)
    version = str(data.get("version", "1.4.0") or "1.4.0").strip()
    pub_key = str(data.get("public_key", "") or "").strip()
    sig = str(data.get("signature", "") or "").strip()
    raw_ts = data.get("timestamp")
    ts_val = safe_float(raw_ts) if raw_ts is not None else None
    ts_exact = str(raw_ts).strip() if ts_val is not None else None
    hashrate_hs = safe_float(data.get("hashrate_hs", 0.0), default=0.0) or 0.0

    if miner_address and not is_valid_bct_address(miner_address):
        return api_response(False, message="Geçersiz madenci cüzdan adresi formatı.", status=400)

    if not node_id:
        node_id = f"node-{secrets.token_hex(4)}"

    try:
        node_info = blockchain.register_or_ping_node(
            node_id=node_id,
            name=name,
            endpoint=endpoint,
            role=role,
            location=location,
            miner_address=miner_address,
            block_height=block_height,
            version=version,
            public_key=pub_key,
            signature=sig,
            timestamp=ts_exact,
            hashrate_hs=hashrate_hs,
        )
    except PermissionError as pe:
        return api_response(False, message=str(pe), status=403)
    logger.info(f"Node Registered / Heartbeat: {node_info['name']} [{node_info['node_id']}] (verified={node_info.get('auth_verified')})")
    return api_response(True, message="Node registered successfully in LockTrace network", data=node_info, status=201)


@app.route("/api/v1/nodes/ping", methods=["POST"])
def api_ping_node():
    """Authenticated heartbeat endpoint for connected peer nodes."""
    if not check_rate_limit("node_ping", limit=45, window_seconds=60):
        return api_response(False, message="Rate limit exceeded", status=429)

    data = request.get_json(silent=True) or {}
    node_id = str(data.get("node_id", "") or "").strip()
    if not node_id:
        return api_response(False, message="Node ID required", status=400)

    miner_addr = str(data.get("miner_address", "") or "").strip()
    if miner_addr and not is_valid_bct_address(miner_addr):
        miner_addr = ""

    pub_key = str(data.get("public_key", "") or "").strip()
    sig = str(data.get("signature", "") or "").strip()
    raw_ts = data.get("timestamp")
    ts_val = safe_float(raw_ts) if raw_ts is not None else None
    ts_exact = str(raw_ts).strip() if ts_val is not None else None
    hashrate_hs = safe_float(data.get("hashrate_hs", 0.0), default=0.0) or 0.0

    try:
        blockchain.register_or_ping_node(
            node_id=node_id,
            block_height=safe_int(data.get("block_height", len(blockchain.chain)), default=len(blockchain.chain), min_val=0),
            miner_address=miner_addr,
            public_key=pub_key,
            signature=sig,
            timestamp=ts_exact,
            hashrate_hs=hashrate_hs,
        )
    except PermissionError as pe:
        return api_response(False, message=str(pe), status=403)
    return api_response(True, message="Pong", data={
        "node_id": node_id[:64],
        "status": "online",
        "network_height": len(blockchain.chain),
        "pending_mempool": len(blockchain.pending_transactions),
    })


@app.route("/api/v1/nodes/attest", methods=["POST"])
def api_attest_block():
    """Cryptographic ECDSA block attestation from peer validator nodes (unlocks 30% Validator Reward Pool)."""
    if not check_rate_limit("node_attest", limit=60, window_seconds=60):
        return api_response(False, message="Attestation rate limit exceeded", status=429)

    data = request.get_json(silent=True) or {}
    node_id = str(data.get("node_id", "") or "").strip()
    miner_address = str(data.get("miner_address", "") or "").strip()
    block_index = safe_int(data.get("block_index", -1), default=-1)
    block_hash = str(data.get("block_hash", "") or "").strip()
    pub_key = str(data.get("public_key", "") or "").strip()
    sig = str(data.get("signature", "") or "").strip()
    raw_ts = data.get("timestamp")
    ts = safe_float(raw_ts)

    if ts is None:
        return api_response(False, message="Geçerli timestamp gereklidir.", status=400)
    ts_exact = str(raw_ts).strip()
    if sig and not rate_limiter.register_signature_once(sig):
        return api_response(False, message="Tekrarlanan (replay) doğrulama imzası reddedildi.", status=409)

    ok, msg, res = blockchain.attest_block(
        node_id=node_id,
        miner_address=miner_address,
        block_index=block_index,
        block_hash=block_hash,
        public_key=pub_key,
        signature=sig,
        timestamp=ts_exact,
    )
    if not ok:
        return api_response(False, message=msg, status=400)
    return api_response(True, message=msg, data=res, status=200)


# ── Mining, PoW Block Templates & Multi-Node Reward Endpoints ─
@app.route("/api/v1/mining/job", methods=["GET"])
def api_mining_job():
    """Provides current mining difficulty, pending fees, and 70/30 reward pool metrics."""
    with blockchain.lock:
        blockchain._load_state(sweep_overdue=False)
        pending_count = len(blockchain.pending_transactions)
        pending_fees = sum(tx.fee for tx in blockchain.pending_transactions if tx.tx_type == "transfer")
        space_fees = sum(tx.fee for tx in blockchain.pending_transactions if tx.tx_type in ("space_post", "space_like", "space_comment"))
        miner_cut = round(pending_fees * MINER_FEE_SHARE + space_fees, 8)
        block_index = len(blockchain.chain)
        prev_hash = blockchain.chain[-1].hash if blockchain.chain else "0" * 64
        difficulty = blockchain.get_current_difficulty()
        active_vals = len(blockchain.get_eligible_validators("", block_index))

    total_pool = round(BLOCK_REWARD + miner_cut, 8) if pending_count > 0 else 0.0
    return api_response(True, data={
        "block_index": block_index,
        "previous_hash": prev_hash,
        "difficulty": difficulty,
        "pending_transactions": pending_count,
        "block_subsidy": BLOCK_REWARD if pending_count > 0 else 0.0,
        "pending_fees": round(pending_fees + space_fees, 8),
        "potential_reward_pool": total_pool,
        "proposer_share_pct": 70 if active_vals > 0 else 100,
        "validator_pool_share_pct": 30 if active_vals > 0 else 0,
        "eligible_validators": active_vals,
    })


@app.route("/api/v1/mining/template", methods=["GET"])
def api_mining_template():
    """Returns a deterministic v2 PoW block template (`getblocktemplate`) for external CPU/GPU miners."""
    if not check_rate_limit("mining_template", limit=60, window_seconds=60):
        return api_response(False, message="Şablon istek sınırı aşıldı.", status=429)

    miner_address = str(request.args.get("miner_address", "") or "").strip()
    node_id = str(request.args.get("node_id", "") or "").strip()
    ok, msg, tpl = blockchain.build_mining_template(miner_address=miner_address, node_id=node_id)
    if not ok and (tpl is None or not tpl.get("empty")):
        return api_response(False, message=msg, status=400)
    return api_response(True, message=msg, data=tpl)


@app.route("/api/v1/mining/submit", methods=["POST"])
def api_mining_submit():
    """Verifies and appends an externally mined Proof-of-Work block (`submitblock`) and distributes 70/30 rewards."""
    if not check_rate_limit("mining_submit", limit=30, window_seconds=60):
        return api_response(False, message="Blok gönderim sınırı aşıldı.", status=429)

    data = request.get_json(silent=True) or {}
    block_data = data.get("block") or {}
    node_id = str(data.get("node_id", "") or "").strip()
    pub_key = str(data.get("public_key", "") or "").strip()
    sig = str(data.get("signature", "") or "").strip()
    hashrate_hs = safe_float(data.get("hashrate_hs", 0.0), default=0.0) or 0.0

    if sig and not rate_limiter.register_signature_once(sig):
        return api_response(False, message="Tekrarlanan (replay) blok imzası reddedildi.", status=409)

    ok, msg, receipt = blockchain.submit_mined_block(
        block_data=block_data,
        node_id=node_id,
        public_key=pub_key,
        signature=sig,
        reported_hashrate=hashrate_hs,
    )
    if not ok:
        status_code = 409 if (receipt and receipt.get("stale")) else 400
        return api_response(False, message=msg, data=receipt, status=status_code)

    logger.info(
        f"External PoW Block #{receipt['block_index']} sealed by {receipt['miner_address'][:10]}... "
        f"(Proposer: +{receipt['miner_reward']} BCT | Validator Pool: +{receipt['validator_pool_reward']} BCT)"
    )
    return api_response(True, message=msg, data=receipt, status=201)


@app.route("/api/v1/mine", methods=["POST"])
def api_mine_block():
    """Backward-compatible mining trigger when pending transactions exist in the mempool."""
    if not check_rate_limit("mine_block", limit=15, window_seconds=60):
        return api_response(False, message="Madencilik istek sınırına ulaşıldı. Lütfen bekleyin.", status=429)

    data = request.get_json(silent=True) or {}
    miner_address = str(data.get("miner_address", "") or "").strip()

    if not miner_address:
        return api_response(False, message="Miner address is required to receive block rewards", status=400)

    if not is_valid_bct_address(miner_address) or miner_address.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT"):
        return api_response(False, message="Invalid miner address format", status=400)

    block = blockchain.mine_pending_block(miner_address=miner_address)
    if not block:
        return api_response(False, message="Havuzda bekleyen işlem yok. Boş blok üretimi ve karşılıksız ödül dağıtımı kapalıdır.", status=400)

    coinbase = next((t for t in block.transactions if t.tx_type == "mining_reward"), None)
    val_rewards = sum(t.amount for t in block.transactions if t.tx_type == "validator_reward")
    reward_val = coinbase.amount if coinbase else 0.0

    logger.info(f"Block #{block.index} mined by {miner_address[:10]}... Reward: {reward_val} BCT (+{val_rewards} BCT validator pool)")

    return api_response(True, message=f"Block #{block.index} successfully mined! Deposited {reward_val:.8f} BCT reward.", data={
        "block_index": block.index,
        "block_hash": block.hash,
        "merkle_root": block.merkle_root,
        "nonce": block.nonce,
        "transactions_packaged": len(block.transactions),
        "miner_address": miner_address,
        "miner_reward": reward_val,
        "validator_pool_reward": round(val_rewards, 8),
        "miner_balance": blockchain.get_balance(miner_address),
        "timestamp": block.timestamp,
    }, status=201)


# ══════════════════════════════════════════════════════
# 🪐 LockTrace Space (On-Chain Decentralized Social Feed)
# ══════════════════════════════════════════════════════

@app.route("/api/v1/space/feed", methods=["GET"])
def api_space_feed():
    """Returns on-chain space thoughts feed with likes and comments."""
    limit = safe_int(request.args.get("limit", 50), default=50, min_val=1, max_val=100)
    feed = blockchain.get_space_feed(limit)
    return api_response(True, data={"posts": feed, "count": len(feed)})


@app.route("/api/v1/space/post/<post_id>", methods=["GET"])
def api_space_get_post(post_id):
    post = blockchain.get_space_post((post_id or "")[:64])
    if post:
        return api_response(True, data=post)
    return api_response(False, message="Gönderi bulunamadı", status=404)


@app.route("/api/v1/space/post", methods=["POST"])
def api_space_create_post():
    """
    Publishes an immutable on-chain thought (Requires cryptographic wallet authentication).
    Cost: 0.10 BCT (80% returns to Treasury Vault, 20% validator fee).
    """
    if not check_rate_limit("space_post", limit=15, window_seconds=60):
        return api_response(False, message="Çok hızlı paylaşım yapıyorsunuz. Lütfen kısa süre bekleyin.", status=429)

    data = request.get_json(silent=True) or {}
    author = str(data.get("author", "") or "").strip()
    content = str(data.get("content", "") or "").strip()

    if not author:
        return api_response(False, message="Yazar cüzdan adresi gereklidir", status=400)
    if not content:
        return api_response(False, message="Düşünce metni boş olamaz", status=400)

    canonical = f"{author}:{content}"
    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, author, canonical
    )
    if not auth_ok:
        return api_response(False, message=auth_err, status=auth_status)

    success, message, result = blockchain.create_space_post(
        author=author,
        content=content,
        signature=signature,
        public_key=pub_key,
        signed_payload=signed_payload,
    )
    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"Space Post Created: by {author[:8]}... (0.10 BCT)")
    return api_response(True, message=message, data=result, status=201)


@app.route("/api/v1/space/like", methods=["POST"])
def api_space_like():
    """
    Likes an on-chain thought (Requires cryptographic wallet authentication).
    Cost: 0.01 BCT (20% to tweet author, 70% to Treasury, 10% validator fee).
    """
    if not check_rate_limit("space_like", limit=30, window_seconds=60):
        return api_response(False, message="Çok hızlı beğeni işlemi gönderildi. Lütfen kısa süre bekleyin.", status=429)

    data = request.get_json(silent=True) or {}
    liker = str(data.get("liker", "") or "").strip()
    post_id = str(data.get("post_id", "") or "").strip()

    if not liker or not post_id:
        return api_response(False, message="liker adresi ve post_id gereklidir", status=400)

    canonical = f"{liker}:{post_id}"
    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, liker, canonical
    )
    if not auth_ok:
        return api_response(False, message=auth_err, status=auth_status)

    success, message, result = blockchain.like_space_post(
        liker=liker,
        post_id=post_id,
        signature=signature,
        public_key=pub_key,
        signed_payload=signed_payload,
    )
    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"Space Post Liked: {post_id} by {liker[:8]}...")
    return api_response(True, message=message, data=result, status=200)


@app.route("/api/v1/space/comment", methods=["POST"])
def api_space_comment():
    """
    Comments on an on-chain thought (Requires cryptographic wallet authentication).
    Cost: 0.02 BCT (20% to tweet author, 70% to Treasury, 10% validator fee).
    """
    if not check_rate_limit("space_comment", limit=20, window_seconds=60):
        return api_response(False, message="Çok hızlı yorum gönderildi. Lütfen kısa süre bekleyin.", status=429)

    data = request.get_json(silent=True) or {}
    commenter = str(data.get("commenter", "") or "").strip()
    post_id = str(data.get("post_id", "") or "").strip()
    content = str(data.get("content", "") or "").strip()

    if not commenter or not post_id or not content:
        return api_response(False, message="commenter, post_id ve content gereklidir", status=400)

    canonical = f"{commenter}:{post_id}:{content}"
    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, commenter, canonical
    )
    if not auth_ok:
        return api_response(False, message=auth_err, status=auth_status)

    success, message, result = blockchain.comment_space_post(
        commenter=commenter,
        post_id=post_id,
        content=content,
        signature=signature,
        public_key=pub_key,
        signed_payload=signed_payload,
    )
    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"Space Comment Added: {post_id} by {commenter[:8]}...")
    return api_response(True, message=message, data=result, status=201)


# ══════════════════════════════════════════════════════
# 💱 Fiat On-Ramp & Buy/Sell Coin Trading (Disabled / Protected)
# ══════════════════════════════════════════════════════

@app.route("/api/v1/trade/config", methods=["GET"])
def api_trade_config():
    """Returns public trade parameters and public Thirdweb Client ID (never secret keys)."""
    rates = {
        "USD": Config.BCT_PER_USD,
        "EUR": round(Config.BCT_PER_USD * 1.08, 4),
        "TRY": round(Config.BCT_PER_USD / 34.0, 4),
    }
    return api_response(True, data={
        "thirdweb_client_id": Config.THIRDWEB_CLIENT_ID,
        "bct_per_usd": Config.BCT_PER_USD,
        "bct_price_usd": Config.BCT_PRICE_USD,
        "min_buy_usd": Config.MIN_BUY_USD,
        "max_buy_usd": Config.MAX_BUY_USD,
        "supported_currencies": ["USD", "EUR", "TRY"],
        "rates": rates,
    })


@app.route("/api/v1/trade/buy", methods=["POST"])
def api_trade_buy():
    data = request.get_json(silent=True) or {}
    buyer_address = str(data.get("buyer_address", "") or "").strip()
    fiat_amount = safe_float(data.get("fiat_amount", 0.0), default=0.0)
    currency = str(data.get("currency", "USD") or "USD").strip().upper()[:8]
    session_token = str(data.get("session_token", "") or "").strip()[:128]

    if not buyer_address or not is_valid_bct_address(buyer_address):
        return api_response(False, message="Geçerli bir alıcı BCT cüzdan adresi gereklidir.", status=400)

    success, message, receipt = blockchain.execute_fiat_purchase(
        buyer_address=buyer_address,
        fiat_amount=fiat_amount,
        currency=currency,
        payment_ref=session_token,
        bct_per_usd=Config.BCT_PER_USD,
    )
    if not success:
        return api_response(False, message=message, status=400)
    return api_response(True, message=message, data=receipt, status=201)


@app.route("/api/v1/trade/sell", methods=["POST"])
def api_trade_sell():
    data = request.get_json(silent=True) or {}
    seller_address = str(data.get("seller_address", "") or "").strip()
    bct_amount = safe_float(data.get("bct_amount", 0.0), default=0.0)
    currency = str(data.get("currency", "USD") or "USD").strip().upper()[:8]
    payout_info = str(data.get("payout_info", "") or "").strip()[:128]

    if not seller_address or not is_valid_bct_address(seller_address):
        return api_response(False, message="Geçerli bir satıcı BCT cüzdan adresi gereklidir.", status=400)

    success, message, receipt = blockchain.execute_fiat_sale(
        seller_address=seller_address,
        bct_amount=bct_amount,
        payout_info=payout_info,
        currency=currency,
        bct_per_usd=Config.BCT_PER_USD,
    )
    if not success:
        return api_response(False, message=message, status=400)
    return api_response(True, message=message, data=receipt, status=201)


@app.route("/api/v1/trade/orders/<address>", methods=["GET"])
def api_trade_orders(address: str):
    """Returns buy & sell order history for a specific wallet address."""
    clean_addr = address.strip()
    if not is_valid_bct_address(clean_addr):
        return api_response(False, message="Invalid address syntax", status=400)
    orders = []
    with blockchain.lock:
        blockchain._load_state()
        for b in blockchain.chain:
            for tx in b.transactions:
                if (tx.sender == clean_addr or tx.receiver == clean_addr) and tx.tx_type in ("fiat_buy", "token_sell"):
                    orders.append({
                        "tx_hash": tx.hash(),
                        "block_index": b.index,
                        "type": tx.tx_type,
                        "amount": tx.amount,
                        "fee": tx.fee,
                        "timestamp": tx.timestamp,
                        "signature": tx.signature,
                    })
    return api_response(True, data={"address": clean_addr, "orders": orders})


# ══════════════════════════════════════════════════════
# 🌐 Thirdweb Engine & Server Wallet Endpoints (Admin-Protected)
# ══════════════════════════════════════════════════════

def _require_admin_api_key() -> bool:
    provided = request.headers.get("X-API-Key", "").strip()
    if not provided or not Config.ADMIN_API_KEY:
        return False
    return secrets.compare_digest(provided, Config.ADMIN_API_KEY)


@app.route("/api/v1/thirdweb/info", methods=["GET"])
def api_thirdweb_info():
    """Returns non-sensitive Thirdweb backend readiness info."""
    if not check_rate_limit("tw_info", limit=15, window_seconds=60):
        return api_response(False, message="Rate limit exceeded", status=429)
    return api_response(True, data=thirdweb_service.get_info())


@app.route("/api/v1/thirdweb/claim-erc1155", methods=["POST"])
def api_thirdweb_claim_erc1155():
    """
    Mints / Claims ERC1155 NFT via Server Wallet.
    Strictly protected by X-API-Key (ADMIN_API_KEY) to prevent unauthorized server-wallet gas/NFT draining.
    """
    if not check_rate_limit("tw_claim", limit=10, window_seconds=60):
        return api_response(False, message="Rate limit exceeded", status=429)

    if not _require_admin_api_key():
        return api_response(False, message="Yetkisiz erişim: Geçerli X-API-Key başlığı gereklidir.", status=401)

    data = request.get_json(silent=True) or {}
    contract_address = str(data.get("contract_address", "") or "").strip()
    to_address = str(data.get("to", data.get("to_address", "")) or "").strip()
    token_id = safe_int(data.get("token_id", 0), default=-1)
    quantity = safe_int(data.get("quantity", 1), default=0)
    chain = str(data.get("chain", Config.THIRDWEB_DEFAULT_CHAIN) or Config.THIRDWEB_DEFAULT_CHAIN).strip()
    server_wallet = str(data.get("server_wallet", "") or "").strip() or None

    if not EVM_ADDRESS_RE.match(contract_address):
        return api_response(False, message="Geçersiz EVM kontrat adresi (0x + 40 hex karakter olmalı).", status=400)
    if not EVM_ADDRESS_RE.match(to_address):
        return api_response(False, message="Geçersiz hedef EVM cüzdan adresi (0x + 40 hex karakter olmalı).", status=400)
    if server_wallet and not EVM_ADDRESS_RE.match(server_wallet):
        return api_response(False, message="Geçersiz server_wallet adresi.", status=400)
    if token_id < 0 or token_id > 10**18:
        return api_response(False, message="Geçersiz token_id değeri.", status=400)
    if quantity < 1 or quantity > 1000:
        return api_response(False, message="quantity 1 ile 1000 arasında olmalıdır.", status=400)
    if not SAFE_CHAIN_RE.match(chain):
        return api_response(False, message="Geçersiz chain parametresi.", status=400)

    result = thirdweb_service.claim_erc1155(
        contract_address=contract_address,
        to_address=to_address,
        token_id=token_id,
        quantity=quantity,
        chain=chain,
        server_wallet_address=server_wallet,
    )

    if not result.get("success", False):
        err = result.get("error", "Failed to enqueue Thirdweb transaction")
        return api_response(False, message=err, status=400)

    logger.info(f"Thirdweb Claim Executed: to={to_address} contract={contract_address} token={token_id}")
    return api_response(True, message="Thirdweb transaction successfully processed", data=result.get("data", {}), status=201)


@app.route("/api/v1/thirdweb/status/<transaction_id>", methods=["GET"])
def api_thirdweb_status(transaction_id: str):
    if not check_rate_limit("tw_status", limit=20, window_seconds=60):
        return api_response(False, message="Rate limit exceeded", status=429)
    clean_tx_id = (transaction_id or "").strip()
    if not SAFE_TX_ID_RE.match(clean_tx_id):
        return api_response(False, message="Geçersiz transaction_id formatı.", status=400)

    result = thirdweb_service.get_transaction_status(clean_tx_id)
    if not result.get("success", False):
        return api_response(False, message=result.get("error", "Failed to retrieve transaction status"), status=400)
    return api_response(True, data=result.get("data", {}))


@app.route("/api/v1/thirdweb/wait-hash/<transaction_id>", methods=["GET"])
def api_thirdweb_wait_hash(transaction_id: str):
    if not check_rate_limit("tw_wait", limit=10, window_seconds=60):
        return api_response(False, message="Rate limit exceeded", status=429)
    clean_tx_id = (transaction_id or "").strip()
    if not SAFE_TX_ID_RE.match(clean_tx_id):
        return api_response(False, message="Geçersiz transaction_id formatı.", status=400)

    result = thirdweb_service.wait_for_transaction_hash(clean_tx_id)
    if not result.get("success", False):
        return api_response(False, message=result.get("error", "Failed to get transaction hash"), status=400)
    return api_response(True, data=result.get("data", {}))


if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
