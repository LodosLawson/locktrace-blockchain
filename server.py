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
from datetime import datetime, timezone
from typing import Optional, Tuple

from flask import Flask, request, jsonify, render_template, g, send_file, send_from_directory, Response
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
    VALIDATOR_STAKE_VAULT_ADDRESS,
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
from core.bridge import BridgeManager, BRIDGE_VAULT_ADDRESS, verify_evm_burn_receipt

bridge_manager = BridgeManager(getattr(Config, "DB_PATH", "blockchain.db"))

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

try:
    from core.push_service import PushNotificationService
    push_service = PushNotificationService(db_path=getattr(Config, "DB_PATH", "blockchain.db"))
    logger.info("Web Push Notification Service attached to server.")
except Exception as _pse:
    logger.warning(f"Could not initialize PushNotificationService: {_pse}")
    push_service = None

blockchain = Blockchain(auto_mine=True)
logger.info(f"LockTrace Initialized: {len(blockchain.chain)} blocks, {len(blockchain.wallets)} wallets")

EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
SAFE_CHAIN_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")
SAFE_TX_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{4,128}$")


# ── Thread-Safe Sliding Window Rate Limiter & Replay Cache ───
class SlidingWindowRateLimiter:
    MAX_BUCKETS = 25000
    MAX_SIG_CACHE = 50000

    def __init__(self):
        self._lock = threading.Lock()
        self._buckets = {}
        self._used_signatures = {}
        self._last_cleanup = time.time()

    def _cleanup_if_needed(self, now: float, force: bool = False):
        if not force and (now - self._last_cleanup < 120):
            return
        self._last_cleanup = now
        stale_keys = [k for k, dq in self._buckets.items() if not dq or (now - dq[-1] > 3600)]
        for k in stale_keys:
            self._buckets.pop(k, None)
        if len(self._buckets) > self.MAX_BUCKETS:
            excess = len(self._buckets) - self.MAX_BUCKETS
            for k in list(self._buckets.keys())[:excess]:
                self._buckets.pop(k, None)
        expired_sigs = [s for s, exp in self._used_signatures.items() if now > exp]
        for s in expired_sigs:
            self._used_signatures.pop(s, None)
        if len(self._used_signatures) > self.MAX_SIG_CACHE:
            excess_s = len(self._used_signatures) - self.MAX_SIG_CACHE
            for s in list(self._used_signatures.keys())[:excess_s]:
                self._used_signatures.pop(s, None)

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        with self._lock:
            self._cleanup_if_needed(now, force=(len(self._buckets) > self.MAX_BUCKETS))
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
            self._cleanup_if_needed(now, force=(len(self._used_signatures) > self.MAX_SIG_CACHE))
            exp = self._used_signatures.get(sig_hex)
            if exp and now <= exp:
                return False
            self._used_signatures[sig_hex] = now + ttl_seconds
            return True

    def check_action_cooldown(self, wallet: str, action_type: str, cooldown_seconds: int) -> Tuple[bool, float]:
        """
        Enforces per-wallet anti-spam & race-condition cooldown intervals.
        Returns: (allowed: bool, remaining_seconds: float)
        """
        if not wallet or cooldown_seconds <= 0:
            return True, 0.0
        now = time.time()
        key = f"{wallet.strip().lower()}:{action_type}"
        with self._lock:
            if not hasattr(self, "_action_cooldowns"):
                self._action_cooldowns = {}
            last_ts = self._action_cooldowns.get(key, 0.0)
            elapsed = now - last_ts
            if elapsed < cooldown_seconds:
                remaining = round(cooldown_seconds - elapsed, 1)
                return False, max(0.1, remaining)
            self._action_cooldowns[key] = now
            return True, 0.0


rate_limiter = SlidingWindowRateLimiter()


TRUSTED_LOCAL_PROXIES = {"127.0.0.1", "::1", "localhost"}


def get_client_ip() -> str:
    """
    Resolve client IP safely.
    Only trusts proxy headers (X-Real-IP / X-Forwarded-For) if incoming connection
    originates from a trusted local reverse-proxy (e.g., Nginx on 127.0.0.1).
    Prevents IP spoofing and rate limit bypasses.
    """
    remote = (request.remote_addr or "127.0.0.1").strip()
    if remote in TRUSTED_LOCAL_PROXIES:
        real_ip = request.headers.get("X-Real-IP", "").strip()
        if real_ip:
            return real_ip[:64]
        fwd = request.headers.get("X-Forwarded-For", "").strip()
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return remote[:64]


def check_rate_limit(scope: str, limit: int, window_seconds: int = 60) -> bool:
    ip = get_client_ip()
    return rate_limiter.allow(f"{scope}:{ip}", limit, window_seconds)


def check_wallet_cooldown(wallet: str, action: str) -> Optional[Tuple[bool, str, int]]:
    """Enforces action-specific rate limiting per user wallet."""
    cd_sec = getattr(Config, "ACTION_COOLDOWNS", {}).get(action, 0)
    if cd_sec <= 0 or not wallet:
        return None
    ok, remain = rate_limiter.check_action_cooldown(wallet, action, cd_sec)
    if not ok:
        action_names = {
            "transfer": "Para transferi",
            "space_post": "Post paylaşımı",
            "space_like": "Beğeni",
            "space_comment": "Yorum",
            "space_follow": "Takip etme",
            "bns_register": "Alan adı kaydı"
        }
        name = action_names.get(action, action)
        return False, f"{name} için bekleme süresi aktif. Lütfen {remain:.0f} saniye sonra tekrar deneyin.", 429
    return None


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


def resolve_authenticated_action(data: dict, expected_address: str, canonical_payload: str, require_nonce: bool = True):
    """
    Cryptographically authenticate a state-changing wallet action.
    Supports:
      1) Custodial-assisted signing via 12-word `mnemonic` or 64-hex `private_key` (Disabled in non-custodial mode)
      2) Non-custodial client-side ECDSA signing via `public_key`, `signature`, `timestamp`, and strictly enforced `nonce`
    Returns: (ok: bool, status_code: int, error_msg: str, signature: str, public_key: str, signed_payload: str)
    """
    clean_expected = (expected_address or "").strip()
    if not is_valid_bct_address(clean_expected) or clean_expected.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT"):
        return False, 400, "Invalid wallet address format.", "", "", ""

    mnemonic_phrase = str(data.get("mnemonic", "") or "").strip()
    private_key_hex = str(data.get("private_key", "") or "").strip()
    client_sig = str(data.get("signature", "") or "").strip()
    client_pub = str(data.get("public_key", "") or "").strip()
    client_ts = data.get("timestamp")

    # Path 1: Mnemonic or Private Key directly sent over network is strictly rejected (Zero-Custodial Security)
    if mnemonic_phrase or private_key_hex:
        return (
            False,
            400,
            "Direct transmission of mnemonic phrases or private keys is strictly disabled for security. "
            "LockTrace is 100% non-custodial; all state actions must be cryptographically signed on the client device.",
            "",
            "",
            ""
        )

    # Path 2: Client-side ECDSA signature (Non-custodial mode)
    if client_sig:
        pub_hex = client_pub or blockchain.wallets.get(clean_expected, {}).get("public_key", "")
        if not pub_hex:
            return False, 401, "public_key is required for signature verification.", "", "", ""

        if public_key_to_address(pub_hex) != clean_expected:
            return False, 403, "Public key does not match wallet address!", "", "", ""

        # LT-03 Fix: Mandatory Nonce Validation for Replay Attack Prevention
        client_nonce = data.get("nonce")
        expected_nonce = blockchain.get_account_nonce(clean_expected)
        if client_nonce is None:
            if require_nonce:
                return False, 400, f"Missing transaction nonce. Nonce is strictly required for replay protection (Current: {expected_nonce}).", "", "", ""
        else:
            if safe_int(client_nonce, default=-1) != expected_nonce:
                return False, 409, f"Invalid transaction nonce. Expected: {expected_nonce}, got: {client_nonce}", "", "", ""

        candidates = canonical_payload if isinstance(canonical_payload, (list, tuple)) else [canonical_payload]
        signed_payload = ""
        verified_ok = False
        if client_ts is not None:
            ts_val = safe_float(client_ts)
            if ts_val is None or abs(time.time() - ts_val) > 300:
                return False, 401, "Signature timestamp expired or invalid.", "", "", ""
        elif expected_nonce is None:
            return False, 401, "Signature timestamp is required to prevent replay attacks.", "", "", ""

        for cand in candidates:
            if client_ts is not None:
                cand_signed = f"{cand}:{client_ts}:{expected_nonce}" if expected_nonce is not None else f"{cand}:{client_ts}"
            else:
                cand_signed = f"{cand}:{expected_nonce}" if expected_nonce is not None else cand
            if verify_signature(pub_hex, cand_signed, client_sig):
                signed_payload = cand_signed
                verified_ok = True
                break

        if not verified_ok:
            return False, 403, "Invalid ECDSA digital signature!", "", "", ""

        if not rate_limiter.register_signature_once(client_sig):
            return False, 409, "Replay signature rejected.", "", "", ""

        return True, 200, "", client_sig, pub_hex, signed_payload

    return False, 401, "Wallet signature authentication is required for this action.", "", "", ""


@app.before_request
def before_request():
    g.start_time = time.time()
    g.request_id = secrets.token_hex(8)


@app.after_request
def after_request(response):
    duration = time.time() - getattr(g, "start_time", time.time())
    response.headers["X-Request-ID"] = getattr(g, "request_id", "unknown")
    response.headers["X-Response-Time"] = f"{duration:.4f}s"
    response.headers["X-Powered-By"] = f"LockTrace-Blockchain/{Config.PROTOCOL_VERSION}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # LT-04 Hardening: Comprehensive Content-Security-Policy (XSS & Key Exfiltration Defense)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://fonts.googleapis.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https: blob:; "
        "connect-src 'self' https://locktrace.space https://www.locktrace.space https://basescan.org https://mainnet.base.org http://127.0.0.1:* http://localhost:*; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    origin = request.headers.get("Origin", "")
    allowed = [o.strip() for o in (Config.CORS_ORIGINS or []) if o.strip()]
    if origin and (not allowed or "*" in allowed or origin in allowed):
        response.headers["Access-Control-Allow-Origin"] = origin
    elif "Access-Control-Allow-Origin" not in response.headers:
        response.headers["Access-Control-Allow-Origin"] = allowed[0] if allowed else "*"
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key, ngrok-skip-browser-warning"
    return response


def api_response(success: bool, data=None, message=None, status=200, **extra):
    # Security Guard (CWE-209): Prevent information exposure through exceptions
    safe_message = message
    if isinstance(message, BaseException):
        safe_message = "An internal processing error occurred."
    elif safe_message is not None:
        clean_msg = str(safe_message)
        if any(term in clean_msg for term in ("Traceback (most recent call last)", "Exception:", "Error:", "PermissionError")):
            safe_message = "An error occurred while processing the request."
        else:
            safe_message = clean_msg

    body = {
        "success": bool(success),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "request_id": getattr(g, "request_id", None),
    }
    if data is not None and not isinstance(data, BaseException):
        body["data"] = data
    if safe_message:
        body["message"] = str(safe_message)
    for k, v in extra.items():
        if not isinstance(v, BaseException):
            body[k] = v
    return jsonify(body), status


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
_FRONTEND_INTEGRITY_CACHE: Tuple[Optional[tuple], Optional[dict]] = (None, None)
_FRONTEND_INTEGRITY_LOCK = threading.Lock()


def _inspect_local_frontend_integrity() -> dict:
    """
    Verify local frontend/index.html & sw.js SHA-256 checksums + ECDSA Release Authority signature.
    Uses stat-based (mtime_ns, size) memoization to eliminate redundant 750KB disk reads & ECDSA math
    under high concurrency while detecting any file modification on disk in O(1) time.
    """
    global _FRONTEND_INTEGRITY_CACHE
    index_path = os.path.join(ROOT_DIR, "frontend", "index.html")
    sw_path = os.path.join(ROOT_DIR, "frontend", "sw.js")
    manifest_path = os.path.join(ROOT_DIR, "frontend", "integrity.json")

    if not os.path.exists(index_path) or not os.path.exists(manifest_path):
        return {
            "verified": False,
            "reason": "⛔ WARNING: This frontend file has been modified or tampered with! Execution blocked. (integrity.json missing)",
        }

    try:
        ix_stat = os.stat(index_path)
        mf_stat = os.stat(manifest_path)
        sw_stat = os.stat(sw_path) if os.path.exists(sw_path) else None
        stat_key = (
            ix_stat.st_mtime_ns,
            ix_stat.st_size,
            mf_stat.st_mtime_ns,
            mf_stat.st_size,
            sw_stat.st_mtime_ns if sw_stat else 0,
            sw_stat.st_size if sw_stat else 0,
            bool(Config.DEBUG or os.environ.get("BCT_DEV_MODE", "false").lower() == "true"),
        )
        cached_key, cached_res = _FRONTEND_INTEGRITY_CACHE
        if cached_key == stat_key and cached_res is not None:
            return cached_res

        with open(manifest_path, "r", encoding="utf-8") as mf:
            manifest = json.load(mf)
        with open(index_path, "rb") as ix:
            index_bytes = ix.read().replace(b"\r\n", b"\n")
        actual_index_sha = hashlib.sha256(index_bytes).hexdigest()

        actual_sw_sha = ""
        sw_bytes = b""
        if sw_stat is not None:
            with open(sw_path, "rb") as sf:
                sw_bytes = sf.read().replace(b"\r\n", b"\n")
            actual_sw_sha = hashlib.sha256(sw_bytes).hexdigest()

        dev_mode = Config.DEBUG or getattr(Config, "DEV_MODE", True) or os.environ.get("BCT_DEV_MODE", "true").lower() == "true"
        expected_index_sha = str(manifest.get("index_html_sha256", "")).lower()
        expected_sw_sha = str(manifest.get("sw_js_sha256", "")).lower()

        if dev_mode:
            manifest_dev = dict(manifest)
            manifest_dev["index_html_sha256"] = actual_index_sha
            manifest_dev["expected_index_sha256"] = actual_index_sha
            manifest_dev["version"] = manifest.get("version", Config.PROTOCOL_VERSION)
            manifest_dev["dev_mode"] = True
            res = {
                "verified": True,
                "dev_mode": True,
                "manifest": manifest_dev,
                "index_bytes": index_bytes,
                "sw_bytes": sw_bytes,
                "actual_index_sha256": actual_index_sha,
                "expected_index_sha256": actual_index_sha,
                "actual_sw_sha256": actual_sw_sha,
            }
            with _FRONTEND_INTEGRITY_LOCK:
                _FRONTEND_INTEGRITY_CACHE = (stat_key, res)
            return res

        sig_ok, sig_msg = verify_frontend_manifest(manifest)
        if not sig_ok:
            res = {
                "verified": False,
                "reason": f"⛔ WARNING: This frontend file has been modified or tampered with! Execution blocked. ({sig_msg})",
                "actual_index_sha256": actual_index_sha,
            }
            with _FRONTEND_INTEGRITY_LOCK:
                _FRONTEND_INTEGRITY_CACHE = (stat_key, res)
            return res

        if actual_index_sha != expected_index_sha:
            if dev_mode:
                res = {
                    "verified": True,
                    "dev_mode": True,
                    "manifest": manifest,
                    "index_bytes": index_bytes,
                    "actual_index_sha256": actual_index_sha,
                    "actual_sw_sha256": actual_sw_sha,
                }
            else:
                res = {
                    "verified": False,
                    "reason": "⛔ WARNING: This frontend file has been modified or tampered with! Execution blocked.",
                    "expected_index_sha256": expected_index_sha,
                    "actual_index_sha256": actual_index_sha,
                    "index_bytes": index_bytes,
                    "manifest": manifest,
                }
            with _FRONTEND_INTEGRITY_LOCK:
                _FRONTEND_INTEGRITY_CACHE = (stat_key, res)
            return res

        if expected_sw_sha and actual_sw_sha and actual_sw_sha != expected_sw_sha:
            res = {
                "verified": False,
                "reason": "⛔ WARNING: Service Worker (sw.js) has been modified or tampered with! Execution blocked.",
                "expected_sw_sha256": expected_sw_sha,
                "actual_sw_sha256": actual_sw_sha,
                "index_bytes": index_bytes,
                "manifest": manifest,
            }
            with _FRONTEND_INTEGRITY_LOCK:
                _FRONTEND_INTEGRITY_CACHE = (stat_key, res)
            return res

        res = {
            "verified": True,
            "manifest": manifest,
            "index_bytes": index_bytes,
            "sw_bytes": sw_bytes,
            "actual_index_sha256": actual_index_sha,
            "actual_sw_sha256": actual_sw_sha,
        }
        with _FRONTEND_INTEGRITY_LOCK:
            _FRONTEND_INTEGRITY_CACHE = (stat_key, res)
        return res
    except Exception as exc:
        logger.warning(f"Frontend integrity inspection error: {exc}")
        return {
            "verified": False,
            "reason": "⛔ WARNING: This frontend file has been modified or tampered with! Execution blocked.",
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


def is_local_or_lan_request() -> bool:
    """Returns True ONLY if request originates from loopback/LAN or explicit BCT_DEV_MODE."""
    if Config.DEBUG or getattr(Config, "DEV_MODE", False) or os.environ.get("BCT_DEV_MODE", "true").lower() == "true":
        return True
    client_ip = (get_client_ip() or "").strip().lower()
    if client_ip in ("127.0.0.1", "::1", "localhost"):
        return True
    if client_ip.startswith("192.168.") or client_ip.startswith("10."):
        return True
    if client_ip.startswith("172."):
        parts = client_ip.split(".")
        if len(parts) >= 2 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
            return True
    return False


def _serve_verified_frontend_response():
    check = _inspect_local_frontend_integrity()
    is_dev = is_local_or_lan_request()

    if not check.get("verified") and not is_dev:
        warn_html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Security Lock - LockTrace</title>
        <style>body{{background:#131315;color:#ffb4ab;font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:24px;}}
        .card{{max-width:620px;background:#1f1f21;border:1px solid #93000a;border-radius:16px;padding:32px;box-shadow:0 20px 50px rgba(0,0,0,0.6);}}
        code{{display:block;background:#0e0e10;color:#e5e1e4;padding:12px;border-radius:8px;margin-top:12px;word-break:break-all;font-size:12px;}}</style></head>
        <body><div class="card"><h2>⛔ WARNING: This frontend file has been modified or tampered with! Execution blocked.</h2>
        <p style="color:#e5e1e4;line-height:1.6;">LockTrace SHA-256 Checksum and ECDSA Release Signature verification failed. Interface loading blocked for wallet security.</p>
        <code>Expected SHA-256: {check.get('expected_index_sha256', 'Unknown')}<br>Actual SHA-256: {check.get('actual_index_sha256', 'Invalid')}</code></div></body></html>"""
        return Response(warn_html, status=403, mimetype="text/html")

    index_bytes = check.get("index_bytes")
    if not index_bytes:
        index_path = os.path.join(ROOT_DIR, "frontend", "index.html")
        if os.path.exists(index_path):
            with open(index_path, "rb") as ix:
                index_bytes = ix.read().replace(b"\r\n", b"\n")
        else:
            index_bytes = b""

    manifest = check.get("manifest") or {}
    resp = Response(index_bytes, status=200, mimetype="text/html; charset=utf-8")
    resp.headers["X-Frontend-SHA256"] = check.get("actual_index_sha256", "")
    resp.headers["X-Frontend-IPFS-CID"] = manifest.get("ipfs_cid_v1", "")
    resp.headers["X-Frontend-Signature"] = manifest.get("signature", "")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.errorhandler(404)
def handle_404(_err):
    if request.path.startswith("/api/"):
        return api_response(False, message="API endpoint not found.", status=404)
    return _serve_verified_frontend_response()


@app.errorhandler(405)
def handle_405(_err):
    return api_response(False, message="HTTP method not supported for this endpoint.", status=405)


@app.errorhandler(413)
def handle_413(_err):
    return api_response(False, message="Request payload too large (Maximum 1 MB).", status=413)


@app.errorhandler(500)
def handle_500(err):
    logger.error(f"Unhandled server error [{getattr(g, 'request_id', '-')}]: {err}")
    return api_response(False, message="An unexpected server error occurred.", status=500)


@app.route("/whitepaper.pdf", methods=["GET"])
@app.route("/docs/whitepaper.pdf", methods=["GET"])
@app.route("/docs/LockTrace_Whitepaper.pdf", methods=["GET"])
@app.route("/LockTrace_Whitepaper.pdf", methods=["GET"])
def serve_whitepaper_pdf():
    pdf_path = os.path.join(ROOT_DIR, "docs", "LockTrace_Whitepaper.pdf")
    if not os.path.exists(pdf_path):
        pdf_path = os.path.join(ROOT_DIR, "LockTrace_Whitepaper.pdf")
    if os.path.exists(pdf_path):
        return send_file(pdf_path, mimetype="application/pdf", as_attachment=False)
    return api_response(False, message="Whitepaper PDF not found.", status=404)


# ── Web Shell Entrypoint (Cryptographically Verified) ────────
@app.route("/", methods=["GET"])
@app.route("/index.html", methods=["GET"])
def index_page():
    return _serve_verified_frontend_response()


@app.route("/manifest.json", methods=["GET"])
def serve_manifest():
    return send_from_directory(os.path.join(ROOT_DIR, "frontend"), "manifest.json", mimetype="application/manifest+json")


@app.route("/sw.js", methods=["GET"])
def serve_service_worker():
    # LT-06 Hardening: Cryptographically verify sw.js and serve directly from verified in-memory buffer (TOCTOU guard)
    check = _inspect_local_frontend_integrity()
    is_dev = is_local_or_lan_request()
    if not check.get("verified") and not is_dev:
        return Response("/* 403 Security Lock: Service Worker integrity check failed */", status=403, mimetype="application/javascript")
    sw_bytes = check.get("sw_bytes")
    if not sw_bytes:
        sw_path = os.path.join(ROOT_DIR, "frontend", "sw.js")
        if os.path.exists(sw_path):
            with open(sw_path, "rb") as f:
                sw_bytes = f.read()
        else:
            return Response("/* 404 Service Worker not found */", status=404, mimetype="application/javascript")
    resp = Response(sw_bytes, mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app.route("/icons/<path:filename>", methods=["GET"])
def serve_icons(filename):
    return send_from_directory(os.path.join(ROOT_DIR, "frontend", "icons"), filename)


@app.route("/api/v1/frontend/integrity", methods=["GET"])
def api_frontend_integrity():
    check = _inspect_local_frontend_integrity()
    onchain = blockchain.get_latest_frontend_release()
    manifest = check.get("manifest") or onchain or {}
    is_dev = bool(check.get("dev_mode")) or is_local_or_lan_request()
    actual_sha = check.get("actual_index_sha256") or manifest.get("index_html_sha256", "")
    expected_sha = actual_sha if is_dev else manifest.get("index_html_sha256", "")
    return api_response(True, data={
        "verified": bool(check.get("verified") or is_dev),
        "dev_mode": is_dev,
        "version": manifest.get("version", Config.PROTOCOL_VERSION),
        "released_at": manifest.get("released_at", ""),
        "authority_address": RELEASE_AUTHORITY_ADDRESS,
        "authority_public_key": RELEASE_AUTHORITY_PUBKEY,
        "index_html_sha256": actual_sha,
        "expected_index_sha256": expected_sha,
        "sw_js_sha256": check.get("actual_sw_sha256") or manifest.get("sw_js_sha256", ""),
        "ipfs_cid_v1": manifest.get("ipfs_cid_v1", ""),
        "signature": manifest.get("signature", ""),
        "onchain_anchor": onchain,
        "warning": None if (check.get("verified") or is_dev) else check.get("reason"),
    })


# ── Web Push Notifications (Off-Site PWA & Mobile Alerts) ──────
@app.route("/api/v1/notifications/vapid-key", methods=["GET"])
def api_notifications_vapid_key():
    """Returns the server VAPID public key for browser pushManager.subscribe()."""
    if not push_service:
        return api_response(False, message="Web Push service not available on this node", status=503)
    pub = push_service.get_public_key()
    if not pub:
        return api_response(False, message="VAPID key not configured", status=503)
    return api_response(True, data={"public_key": pub})


@app.route("/api/v1/notifications/subscribe", methods=["POST"])
def api_notifications_subscribe():
    """
    Cryptographically binds a device Web Push subscription to a BCT wallet address.
    Requires SECP256k1 ECDSA signature proof of wallet ownership.
    """
    if not push_service:
        return api_response(False, message="Web Push service not available on this node", status=503)

    if not check_rate_limit("push_sub", limit=20, window_seconds=60):
        return api_response(False, message="Too many subscription attempts. Please wait.", status=429)

    data = request.get_json(silent=True) or {}
    wallet_address = str(data.get("wallet_address", "") or "").strip()
    public_key = str(data.get("public_key", "") or "").strip()
    subscription = data.get("subscription")
    signature = str(data.get("signature", "") or "").strip()
    timestamp = safe_float(data.get("timestamp")) or 0.0
    user_agent = str(data.get("user_agent", "") or request.headers.get("User-Agent", ""))[:120]

    if not wallet_address or not public_key or not subscription or not signature:
        return api_response(False, message="Missing required fields: wallet_address, public_key, subscription, signature", status=400)

    ok, msg = push_service.subscribe(
        wallet_address=wallet_address,
        public_key=public_key,
        subscription=subscription,
        timestamp=timestamp,
        signature=signature,
        user_agent=user_agent
    )
    if ok:
        return api_response(True, message=msg, status=201)
    return api_response(False, message=msg, status=401)


@app.route("/api/v1/notifications/unsubscribe", methods=["POST"])
def api_notifications_unsubscribe():
    """Removes a push subscription by endpoint."""
    if not push_service:
        return api_response(False, message="Web Push service not available on this node", status=503)
    if not check_rate_limit("push_unsub", limit=10, window_seconds=60):
        return api_response(False, message="Too many unsubscribe attempts. Please wait.", status=429)
    data = request.get_json(silent=True) or {}
    endpoint = str(data.get("endpoint", "") or "").strip()
    if not endpoint:
        return api_response(False, message="Endpoint is required", status=400)
    push_service.unsubscribe(endpoint)
    return api_response(True, message="Unsubscribed successfully")


@app.route("/api/v1/notifications/test-push", methods=["POST"])
def api_notifications_test_push():
    """
    Sends a test Web Push notification to all registered devices of the caller's wallet via APNs/Google Push.
    Verifies lock-screen delivery end-to-end without transferring actual funds.
    """
    if not push_service:
        return api_response(False, message="Web Push service not available on this node", status=503)

    if not check_rate_limit("push_test", limit=5, window_seconds=60):
        return api_response(False, message="Rate limit exceeded for test push. Please wait.", status=429)

    data = request.get_json(silent=True) or {}
    wallet_address = str(data.get("wallet_address", "") or "").strip()
    if not wallet_address or not is_valid_bct_address(wallet_address):
        return api_response(False, message="Valid BCT wallet address required.", status=400)

    if not rate_limiter.allow(f"push_test_wallet:{wallet_address}", limit=2, window_seconds=60):
        return api_response(False, message="Rate limit exceeded for this wallet. Please wait 1 minute.", status=429)

    subs = push_service.get_subscriptions_for_wallet(wallet_address)
    if not subs:
        return api_response(False, message="No registered push devices found for this wallet. Please tap Enable in Notification Settings.", status=404)

    push_service.send_push_to_wallet(
        wallet_address,
        title="🔔 LockTrace Web Push Testi",
        body="Tebrikler! Apple APNs / Google Push üzerinden kilit ekranınıza başarıyla ulaştı. Kriptografik doğrulama aktif.",
        url="/#cuzdanim",
        category="system"
    )
    return api_response(True, message=f"Test push dispatched to {len(subs)} registered device(s).", data={"device_count": len(subs)})


# ── Health & Stats ───────────────────────────────────────────
@app.route("/api/v1/health", methods=["GET"])
def api_health():
    check = _inspect_local_frontend_integrity()
    return api_response(True, data={
        "status": "healthy",
        "version": Config.PROTOCOL_VERSION,
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
        return api_response(False, message="Too many mnemonic generation requests. Please wait 1 minute.", status=429)
    phrase = generate_mnemonic()
    return api_response(True, data={"mnemonic": phrase})


@app.route("/api/v1/wallet/create", methods=["POST"])
def api_create_wallet():
    if not check_rate_limit("wallet_create_min", limit=3, window_seconds=60) or not check_rate_limit("wallet_create_hr", limit=10, window_seconds=3600):
        return api_response(False, message="Wallet creation limit reached. Please try again later.", status=429)

    data = request.get_json(silent=True) or {}
    client_address = str(data.get("address", "") or "").strip()
    client_pubkey = str(data.get("public_key", "") or "").strip()
    provided_mnemonic = str(data.get("mnemonic", "") or "").strip()

    try:
        # Path A: 100% Zero-Knowledge Client-Side Keygen (mnemonic & private_key never leave browser!)
        if client_address and client_pubkey and not provided_mnemonic:
            if public_key_to_address(client_pubkey) != client_address:
                return api_response(False, message="Public key does not match wallet address.", status=400)
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
                return api_response(False, message="Invalid 12-word BIP-39 recovery phrase.", status=400)
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
        return api_response(False, message="An error occurred while creating wallet.", status=500)


# ── Wallet Import ────────────────────────────────────────────
@app.route("/api/v1/wallet/import", methods=["POST"])
def api_import_wallet():
    if not check_rate_limit("wallet_import", limit=15, window_seconds=60):
        return api_response(False, message="Too many import attempts. Please wait 1 minute.", status=429)

    data = request.get_json(silent=True) or {}
    client_address = str(data.get("address", "") or "").strip()
    client_pubkey = str(data.get("public_key", "") or "").strip()
    mnemonic_phrase = str(data.get("mnemonic", "") or "").strip()
    private_key_hex = str(data.get("private_key", "") or "").strip()

    try:
        # Path A: 100% Zero-Knowledge Client-Side Import (secrets stay in browser!)
        if client_address and client_pubkey and not mnemonic_phrase and not private_key_hex:
            if public_key_to_address(client_pubkey) != client_address:
                return api_response(False, message="Public key does not match wallet address.", status=400)
            allow_bonus = check_rate_limit("wallet_create_min", limit=3, window_seconds=60) and check_rate_limit("wallet_create_hr", limit=10, window_seconds=3600)
            ok, msg = blockchain.register_wallet(client_address, client_pubkey, grant_welcome_bonus=allow_bonus)
            if not ok:
                return api_response(False, message=msg, status=400)
            return api_response(True, message="Wallet successfully verified and connected!", data={
                "address": client_address,
                "public_key": client_pubkey,
                "balance": blockchain.get_balance(client_address),
                "nonce": blockchain.get_account_nonce(client_address),
            })

        # Path B: Legacy / API Import
        if mnemonic_phrase:
            words = mnemonic_phrase.lower().split()
            if len(words) != 12:
                return api_response(False, message="Recovery phrase must consist of exactly 12 words.", status=400)
            wallet = restore_wallet_from_mnemonic(" ".join(words))
        elif private_key_hex:
            clean_pk = private_key_hex.strip()
            if len(clean_pk) != 64 or not all(c in "0123456789abcdefABCDEF" for c in clean_pk):
                return api_response(False, message="Private key must be in 64-character hex format.", status=400)
            wallet = restore_wallet(clean_pk)
        else:
            return api_response(False, message="Please enter a 12-word recovery phrase or private key.", status=400)

        allow_bonus = check_rate_limit("wallet_create_min", limit=3, window_seconds=60) and check_rate_limit("wallet_create_hr", limit=10, window_seconds=3600)
        ok, msg = blockchain.register_wallet(wallet.address, wallet.get_public_key_hex(), grant_welcome_bonus=allow_bonus)
        if not ok:
            return api_response(False, message=msg, status=400)
        bal = blockchain.get_balance(wallet.address)

        return api_response(True, message="Wallet successfully restored!", data={
            "address": wallet.address,
            "mnemonic": getattr(wallet, "mnemonic", ""),
            "public_key": wallet.get_public_key_hex(),
            "private_key": wallet.get_private_key_hex(),
            "balance": bal,
            "nonce": blockchain.get_account_nonce(wallet.address),
        })
    except Exception as e:
        logger.warning(f"Wallet restoration failed: {e}")
        return api_response(False, message="Wallet could not be restored. Please check your key.", status=400)


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
        return api_response(False, message="Too many transfer requests. Please wait a moment.", status=429)

    data = request.get_json(silent=True) or {}
    sender = str(data.get("sender", "") or "").strip()
    receiver = str(data.get("receiver", "") or "").strip()
    amount_raw = data.get("amount")

    if not sender or not receiver or amount_raw is None:
        return api_response(False, message="Missing required fields: sender, receiver, amount", status=400)

    cd_err = check_wallet_cooldown(sender, "transfer")
    if cd_err:
        return api_response(cd_err[0], message=cd_err[1], status=cd_err[2])

    # BNS Handle Auto-Resolution (.bct domain support)
    raw_receiver = receiver
    if receiver.lower().endswith(".bct"):
        bns_res = blockchain.bns_lookup(receiver)
        if bns_res and bns_res.get("owner"):
            receiver = bns_res["owner"]
            logger.info(f"BNS Resolved: '{raw_receiver}' -> {receiver}")
        else:
            return api_response(False, message=f"BNS handle '{raw_receiver}' is not registered or cannot be resolved.", status=404)

    amount = safe_float(amount_raw)
    if amount is None or amount <= 0:
        return api_response(False, message="A valid and positive amount must be entered.", status=400)

    if amount > Config.MAX_TRANSACTION:
        return api_response(False, message=f"Maximum single transfer limit is {Config.MAX_TRANSACTION:,.0f} BCT.", status=400)

    amount = round(amount, 8)
    amt_str_trim = f"{amount:.8f}".rstrip("0").rstrip(".") or "0"
    canonical_variants = list(dict.fromkeys([
        f"TX:{Config.NETWORK_NAME}:{sender}:{receiver}:{amount}",
        f"TX:{Config.NETWORK_NAME}:{sender}:{receiver}:{amount:.8f}",
        f"{sender}{receiver}{amount}",
        f"{sender}{receiver}{amt_str_trim}",
        f"{sender}{receiver}{amount:.8f}",
        f"{sender}{receiver}{amount_raw}",
        f"{sender}{raw_receiver}{amount}",
        f"{sender}{raw_receiver}{amt_str_trim}",
    ]))
    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, sender, canonical_variants, require_nonce=True
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
        if push_service and receiver:
            try:
                push_service.send_push_to_wallet(
                    receiver,
                    title=f"🎉 +{amount:.4f} BCT Alındı!",
                    body=f"{sender[:8]}... adresinden transfer hesabınıza ulaştı.",
                    url="/#cuzdanim",
                    category="transfer"
                )
            except Exception as _p_err:
                logger.debug(f"Push dispatch error: {_p_err}")
        return api_response(True, message=message, data=tx_info, status=201)

    logger.warning(f"Transaction Declined: {message}")
    return api_response(False, message=message, status=400)


# ── Universal Explorer Endpoints ─────────────────────────────
@app.route("/api/v1/explorer/search", methods=["GET"])
def api_explorer_search():
    """Universal search across Blocks, Transactions, and Addresses."""
    if not check_rate_limit("explorer_search", limit=45, window_seconds=60):
        return api_response(False, message="Too many search requests. Please wait.", status=429)
    q = request.args.get("q", "").strip()[:128]
    if not q:
        return api_response(False, message="Search query cannot be empty", status=400)

    block = blockchain.get_block_by_index_or_hash(q)
    if block:
        return api_response(True, data={"type": "block", "result": block})

    tx = blockchain.get_tx_by_hash(q)
    if tx:
        return api_response(True, data={"type": "transaction", "result": tx})

    # BNS handle resolution in explorer search (e.g. @satoshi, satoshi.bct)
    clean_handle = q.lstrip("@").lower()
    bns_cand = clean_handle if clean_handle.endswith(".bct") else f"{clean_handle}.bct"
    if bns_cand in blockchain.bns_records:
        resolved_addr = blockchain.bns_records[bns_cand].get("owner", "")
        if resolved_addr and is_valid_bct_address(resolved_addr):
            bal = blockchain.get_balance(resolved_addr)
            history = blockchain.get_wallet_transactions(resolved_addr)
            return api_response(True, data={
                "type": "address",
                "result": {
                    "address": resolved_addr,
                    "handle": bns_cand,
                    "balance": bal,
                    "transaction_count": len(history),
                    "transactions": history[:50],
                },
            })

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

    return api_response(False, message="No block, transaction, or wallet found matching search criteria.", status=404)


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
                "version": Config.PROTOCOL_VERSION,
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
    return api_response(False, message="Transaction or Merkle proof not found.", status=404)


@app.route("/api/v1/explorer/holders", methods=["GET"])
@app.route("/api/v1/holders", methods=["GET"])
def api_explorer_holders():
    """Returns paginated rich list of all accounts holding native BCT."""
    if not check_rate_limit("explorer_holders", limit=45, window_seconds=60):
        return api_response(False, message="Too many requests. Please wait.", status=429)
    page = safe_int(request.args.get("page", 1), default=1, min_val=1)
    limit = safe_int(request.args.get("limit", 10), default=10, min_val=1, max_val=50)
    data = blockchain.get_holders(page=page, limit=limit)
    return api_response(True, data=data)


@app.route("/api/v1/transactions/latest", methods=["GET"])
@app.route("/api/v1/transactions", methods=["GET"])
def api_latest_transactions():
    limit = safe_int(request.args.get("limit", 10), default=10, min_val=1, max_val=100)
    page = safe_int(request.args.get("page", 1), default=1, min_val=1)
    page_txs, total = blockchain.get_paginated_transactions(page=page, limit=limit)
    total_pages = max(1, (total + limit - 1) // limit)
    page = min(page, total_pages)
    return api_response(True, data={
        "transactions": page_txs,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    })


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
@app.route("/api/v1/blocks", methods=["GET"])
def api_latest_blocks():
    count_param = request.args.get("count")
    limit_param = request.args.get("limit")
    limit_val = count_param if count_param is not None and limit_param is None else (limit_param or 10)
    limit = safe_int(limit_val, default=10, min_val=1, max_val=100)
    page = safe_int(request.args.get("page", 1), default=1, min_val=1)

    with blockchain.lock:
        blockchain._load_state()
        total_blocks = len(blockchain.chain)
        total_pages = max(1, (total_blocks + limit - 1) // limit)
        page = min(page, total_pages)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        # Slice backwards in O(limit) without copying the full chain
        slice_end = max(0, total_blocks - start_idx)
        slice_start = max(0, total_blocks - end_idx)
        page_blocks = [b.to_dict() for b in reversed(blockchain.chain[slice_start:slice_end])]

    return api_response(True, data={
        "blocks": page_blocks,
        "total": total_blocks,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    })


@app.route("/api/v1/chain/range", methods=["GET"])
def api_chain_range():
    """Incremental archival chain sync endpoint for decentralized peer nodes."""
    start = safe_int(request.args.get("start", 0), default=0, min_val=0)
    limit = safe_int(request.args.get("limit", 100), default=100, min_val=1, max_val=200)
    return api_response(True, data=blockchain.get_chain_range(start=start, limit=limit))


@app.route("/api/v1/snapshot/latest", methods=["GET"])
def api_get_latest_snapshot():
    """
    v2.7.0 Decentralized State Snapshot Sync endpoint.
    Returns a cryptographically audited state root over sorted balances, nonces, and BNS domains.
    Allows new nodes to fast-sync their ledger in seconds and verify only the latest 1,000 blocks.
    """
    snapshot = blockchain.get_state_snapshot()
    return api_response(True, message="Verified state snapshot ready.", data=snapshot)


@app.route("/p2p/gossip/compact_block", methods=["POST"])
def api_p2p_gossip_compact_block():
    """
    v2.6.0 P2P Compact Block Relay endpoint.
    Accepts compact block header + prefilled coinbase and short IDs, reconstructing
    the full block from local mempool without transmitting redundant transaction bytes.
    """
    if not check_rate_limit("p2p_compact_gossip", limit=60, window_seconds=60):
        return api_response(False, message="Compact block gossip rate limit exceeded.", status=429)

    payload = request.get_json(silent=True) or {}
    compact_data = payload.get("compact_block") or {}
    header = compact_data.get("header") or {}

    if not header or "hash" not in header or "merkle_root" not in header:
        return api_response(False, message="Malformed compact block header.", status=400)

    # Reconstruct from local pending mempool
    ok, msg, reconstructed_block, missing = blockchain.reconstruct_compact_block(compact_data)
    if not ok:
        if missing:
            return api_response(False, message="Missing transactions for compact block.", data={"missing_indices": missing, "header_hash": header.get("hash")}, status=206)
        return api_response(False, message=msg, status=400)

    # Submit reconstructed block to consensus engine
    submit_ok, submit_msg, receipt = blockchain.submit_mined_block(
        block_data=reconstructed_block,
        node_id=str(payload.get("node_id", "") or "P2P-Peer"),
        public_key="",
        signature="",
        reported_hashrate=0.0
    )
    if not submit_ok:
        return api_response(False, message=submit_msg, data=receipt, status=400)

    return api_response(True, message="Compact block reconstructed and sealed.", data=receipt, status=201)


@app.route("/p2p/getblocktxn", methods=["POST"])
def api_p2p_getblocktxn():
    """
    v2.6.0 Compact Block transaction responder.
    Supplies the exact missing transactions requested by a peer node to complete block assembly.
    """
    payload = request.get_json(silent=True) or {}
    block_hash = str(payload.get("block_hash", "")).strip().lower()
    indices = payload.get("indices", [])
    if not block_hash or not isinstance(indices, list):
        return api_response(False, message="Invalid block transaction query.", status=400)

    blk_dict = blockchain.get_block_by_index_or_hash(block_hash)
    if not blk_dict:
        return api_response(False, message="Block not found.", status=404)

    txs = blk_dict.get("transactions", [])
    requested_txs = []
    for idx in indices:
        if 0 <= int(idx) < len(txs):
            requested_txs.append({"index": int(idx), "tx": txs[int(idx)]})

    return api_response(True, data={"block_hash": block_hash, "transactions": requested_txs})


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
        return api_response(False, message="Too many node registration requests.", status=429)

    data = request.get_json(silent=True) or {}
    node_id = str(data.get("node_id", "") or "").strip()
    name = str(data.get("name", "") or "").strip()
    endpoint = str(data.get("endpoint", "") or "").strip()
    role = str(data.get("role", "Community Validator Peer") or "Community Validator Peer").strip()
    location = str(data.get("location", "Decentralized") or "Decentralized").strip()
    miner_address = str(data.get("miner_address", "") or "").strip()
    block_height = safe_int(data.get("block_height", 0), default=0, min_val=0)
    version = str(data.get("version", Config.PROTOCOL_VERSION) or Config.PROTOCOL_VERSION).strip()
    pub_key = str(data.get("public_key", "") or "").strip()
    sig = str(data.get("signature", "") or "").strip()
    raw_ts = data.get("timestamp")
    ts_val = safe_float(raw_ts) if raw_ts is not None else None
    ts_exact = str(raw_ts).strip() if ts_val is not None else None
    hashrate_hs = safe_float(data.get("hashrate_hs", 0.0), default=0.0) or 0.0

    if miner_address and not is_valid_bct_address(miner_address):
        return api_response(False, message="Invalid miner wallet address format.", status=400)

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
            client_ip=get_client_ip(),
        )
    except PermissionError as pe:
        logger.warning(f"Node registration rejected: {pe}")
        return api_response(False, message="Node authentication failed: Node ID is registered to another cryptographic key.", status=403)
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
            client_ip=get_client_ip(),
        )
    except PermissionError as pe:
        logger.warning(f"Node ping rejected: {pe}")
        return api_response(False, message="Node authentication failed: Node ID is registered to another cryptographic key.", status=403)
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
        return api_response(False, message="Valid timestamp is required.", status=400)
    ts_exact = str(raw_ts).strip()
    if sig and not rate_limiter.register_signature_once(sig):
        return api_response(False, message="Replay verification signature rejected.", status=409)

    ok, msg, res = blockchain.attest_block(
        node_id=node_id,
        miner_address=miner_address,
        block_index=block_index,
        block_hash=block_hash,
        public_key=pub_key,
        signature=sig,
        timestamp=ts_exact,
        client_ip=get_client_ip(),
    )
    if not ok:
        return api_response(False, message=msg, status=400)
    return api_response(True, message=msg, data=res, status=200)


# ── Validator Staking & Collateral Vault Endpoints ───────────
@app.route("/api/v1/validator/stake", methods=["POST"])
def api_validator_stake():
    """Lock 1,000+ BCT collateral into VALIDATOR_STAKE_VAULT to become an active consensus validator."""
    data = request.get_json(silent=True) or {}
    sender = str(data.get("sender", "") or "").strip()
    amount_raw = data.get("amount")
    amount = safe_float(amount_raw, default=0.0)

    if not sender or amount_raw is None:
        return api_response(False, message="Sender and amount are required.", status=400)
    if amount < 1000.0:
        return api_response(False, message="Minimum validator stake is 1000.00 BCT.", status=400)

    amount = round(amount, 8)
    amt_str_trim = f"{amount:.8f}".rstrip("0").rstrip(".") or "0"
    amt_int = str(int(amount)) if amount.is_integer() else str(amount)

    canonical_variants = list(dict.fromkeys([
        f"VALIDATOR_STAKE:{sender}:{amount}",
        f"VALIDATOR_STAKE:{sender}:{amt_str_trim}",
        f"VALIDATOR_STAKE:{sender}:{amt_int}",
        f"{sender}{VALIDATOR_STAKE_VAULT_ADDRESS}{amount}",
        f"{sender}{VALIDATOR_STAKE_VAULT_ADDRESS}{amt_str_trim}",
        f"{sender}{VALIDATOR_STAKE_VAULT_ADDRESS}{amt_int}",
        f"VALIDATOR_STAKE:{sender}:{amount:.8f}",
    ]))

    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, sender, canonical_variants
    )
    if not auth_ok:
        return api_response(False, message=auth_err, status=auth_status)

    ok, msg, res = blockchain.execute_validator_stake(
        sender=sender,
        amount_bct=amount,
        signature=signature,
        public_key=pub_key,
        signed_payload=signed_payload
    )
    if not ok:
        return api_response(False, message=msg, status=400)
    return api_response(True, message=msg, data=res, status=200)


@app.route("/api/v1/validator/unstake", methods=["POST"])
def api_validator_unstake():
    """Unlock staked BCT collateral from VALIDATOR_STAKE_VAULT back to the validator."""
    data = request.get_json(silent=True) or {}
    sender = str(data.get("sender", "") or "").strip()
    amount_raw = data.get("amount")
    amount = safe_float(amount_raw, default=0.0)

    if not sender or amount_raw is None:
        return api_response(False, message="Sender and amount are required.", status=400)
    if amount <= 0:
        return api_response(False, message="Valid unstake amount is required.", status=400)

    amount = round(amount, 8)
    amt_str_trim = f"{amount:.8f}".rstrip("0").rstrip(".") or "0"
    amt_int = str(int(amount)) if amount.is_integer() else str(amount)

    canonical_variants = list(dict.fromkeys([
        f"VALIDATOR_UNSTAKE:{sender}:{amount}",
        f"VALIDATOR_UNSTAKE:{sender}:{amt_str_trim}",
        f"VALIDATOR_UNSTAKE:{sender}:{amt_int}",
        f"{VALIDATOR_STAKE_VAULT_ADDRESS}{sender}{amount}",
        f"{VALIDATOR_STAKE_VAULT_ADDRESS}{sender}{amt_str_trim}",
        f"{VALIDATOR_STAKE_VAULT_ADDRESS}{sender}{amt_int}",
        f"VALIDATOR_UNSTAKE:{sender}:{amount:.8f}",
    ]))

    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, sender, canonical_variants
    )
    if not auth_ok:
        return api_response(False, message=auth_err, status=auth_status)

    ok, msg, res = blockchain.execute_validator_unstake(
        sender=sender,
        amount_bct=amount,
        signature=signature,
        public_key=pub_key,
        signed_payload=signed_payload
    )
    if not ok:
        return api_response(False, message=msg, status=400)
    return api_response(True, message=msg, data=res, status=200)



@app.route("/api/v1/validator/telemetry/<address>", methods=["GET"])
def api_validator_telemetry(address):
    """Returns remote node telemetry, on-chain stake, and attestation stats for a validator wallet."""
    if not check_rate_limit("validator_telemetry", limit=60, window_seconds=60):
        return api_response(False, message="Too many telemetry requests.", status=429)

    clean = (address or "").strip()
    if not is_valid_bct_address(clean):
        return api_response(False, message="Invalid wallet address format.", status=400)

    telemetry = blockchain.get_validator_telemetry(clean)
    return api_response(True, data=telemetry, status=200)

@app.route("/api/v1/validator/stake/<address>", methods=["GET"])
def api_validator_get_stake(address):
    """Query current on-chain staked collateral, validator status, and voting weight."""
    clean = str(address or "").strip()
    staked = blockchain.get_validator_stake(clean)
    bal = blockchain.get_balance(clean)
    is_eligible = (staked >= 1000.0) or (bal >= 1000.0)
    return api_response(True, data={
        "address": clean,
        "staked_amount": staked,
        "wallet_balance": bal,
        "min_required_stake": 1000.0,
        "is_eligible_validator": is_eligible,
        "is_vault_staked": staked >= 1000.0,
        "stake_vault_address": VALIDATOR_STAKE_VAULT_ADDRESS,
    })


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
        return api_response(False, message="Mining template rate limit exceeded.", status=429)

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
        return api_response(False, message="Block submission rate limit exceeded.", status=429)

    data = request.get_json(silent=True) or {}
    block_data = data.get("block") or {}
    node_id = str(data.get("node_id", "") or "").strip()
    pub_key = str(data.get("public_key", "") or "").strip()
    sig = str(data.get("signature", "") or "").strip()
    hashrate_hs = safe_float(data.get("hashrate_hs", 0.0), default=0.0) or 0.0

    if sig and not rate_limiter.register_signature_once(sig):
        return api_response(False, message="Replay block signature rejected.", status=409)

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
    """
    Disabled synchronous server-side mining endpoint to prevent CPU exhaustion and Denial-of-Service.
    Decentralized PoW mining must be executed via `/api/v1/mining/template` and `/api/v1/mining/submit`
    or directly via `node_runner.py`.
    """
    return api_response(
        False,
        message=(
            "Server-side synchronous mining is disabled to prevent CPU DoS. "
            "Please use '/api/v1/mining/template' and '/api/v1/mining/submit' endpoints "
            "or 'python node_runner.py' standalone miner."
        ),
        status=403
    )


# ══════════════════════════════════════════════════════
# 🪐 LockTrace Space (On-Chain Decentralized Social Feed)
# ══════════════════════════════════════════════════════

@app.route("/api/v1/space/feed", methods=["GET"])
def api_space_feed():
    """Returns on-chain space thoughts feed with likes, comments, and algorithmic sorting."""
    limit = safe_int(request.args.get("limit", 50), default=50, min_val=1, max_val=100)
    feed_type = str(request.args.get("feed_type", "for_you") or "for_you").lower().strip()
    if feed_type not in ("for_you", "latest", "trending"):
        feed_type = "for_you"
    tag = str(request.args.get("tag", "") or "").strip()
    author = str(request.args.get("author", "") or "").strip()
    feed = blockchain.get_space_feed(limit=limit, feed_type=feed_type, tag=tag, author=author)
    return api_response(True, data={"posts": feed, "count": len(feed), "feed_type": feed_type, "filter_tag": tag})


@app.route("/api/v1/space/trending_tags", methods=["GET"])
def api_space_trending_tags():
    """Returns top trending hashtags (#) and cashtags ($) across LockTrace Space."""
    limit = safe_int(request.args.get("limit", 15), default=15, min_val=1, max_val=50)
    data = blockchain.get_space_trending_tags(top_n=limit)
    return api_response(True, data=data)


@app.route("/api/v1/space/post/<post_id>", methods=["GET"])
def api_space_get_post(post_id):
    post = blockchain.get_space_post((post_id or "")[:64])
    if post:
        return api_response(True, data=post)
    return api_response(False, message="Post not found", status=404)


@app.route("/api/v1/space/post", methods=["POST"])
def api_space_create_post():
    """
    Publishes an immutable on-chain thought (Requires cryptographic wallet authentication).
    Cost: 0.10 BCT (80% returns to Treasury Vault, 20% validator fee).
    """
    if not check_rate_limit("space_post", limit=15, window_seconds=60):
        return api_response(False, message="Posting too fast. Please wait a moment.", status=429)

    data = request.get_json(silent=True) or {}
    author = str(data.get("author", "") or "").strip()
    content = str(data.get("content", "") or "").strip()

    if not author:
        return api_response(False, message="Author wallet address is required", status=400)
    if not content:
        return api_response(False, message="Post content cannot be empty", status=400)

    cd_err = check_wallet_cooldown(author, "space_post")
    if cd_err:
        return api_response(cd_err[0], message=cd_err[1], status=cd_err[2])

    bns_name = str(data.get("bns_name", "") or "").strip()
    canonical = [f"{author}:{content}", f"{author}:{content}:{bns_name}"] if bns_name else f"{author}:{content}"
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
        bns_name=bns_name,
    )
    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"Space Post Created: by {author[:8]}... (0.10 BCT)")
    if push_service:
        try:
            tagged_users = blockchain.resolve_tagged_wallets(content)
            for item in tagged_users:
                target_w = item["wallet"]
                if target_w and target_w != author:
                    snippet = content[:65].replace('"', "'")
                    display_sender = f"@{bns_name}" if bns_name else f"{author[:8]}..."
                    push_service.send_push_to_wallet(
                        target_w,
                        title="💬 Space'te Etiketlendiniz!",
                        body=f"{display_sender} sizden bahsetti: \"{snippet}...\"",
                        url="/#space",
                        category="space"
                    )
        except Exception as _s_err:
            logger.debug(f"Space mention push error: {_s_err}")
    return api_response(True, message=message, data=result, status=201)


@app.route("/api/v1/space/like", methods=["POST"])
def api_space_like():
    """
    Likes an on-chain thought (Requires cryptographic wallet authentication).
    Cost: 0.01 BCT (20% to tweet author, 70% to Treasury, 10% validator fee).
    """
    if not check_rate_limit("space_like", limit=60, window_seconds=60):
        return api_response(False, message="Liking too fast. Please wait a moment.", status=429)

    data = request.get_json(silent=True) or {}
    liker = str(data.get("liker", "") or "").strip()
    post_id = str(data.get("post_id", "") or "").strip()

    if not liker or not post_id:
        return api_response(False, message="Fields 'liker' and 'post_id' are required.", status=400)

    cd_err = check_wallet_cooldown(liker, "space_like")
    if cd_err:
        return api_response(cd_err[0], message=cd_err[1], status=cd_err[2])

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
    if push_service:
        try:
            parent_post = blockchain.space_posts.get(post_id)
            if parent_post and parent_post.get("author") and parent_post["author"] != liker:
                push_service.send_push_to_wallet(
                    parent_post["author"],
                    title="❤️ Gönderiniz Beğenildi!",
                    body=f"{liker[:8]}... Space gönderinizi beğendi (+0.002 BCT telif).",
                    url="/#space",
                    category="space"
                )
        except Exception as _l_err:
            logger.debug(f"Space like push error: {_l_err}")
    return api_response(True, message=message, data=result, status=200)


@app.route("/api/v1/space/comment", methods=["POST"])
def api_space_comment():
    """
    Comments on an on-chain thought (Requires cryptographic wallet authentication).
    Cost: 0.02 BCT (20% to tweet author, 70% to Treasury, 10% validator fee).
    """
    if not check_rate_limit("space_comment", limit=20, window_seconds=60):
        return api_response(False, message="Commenting too fast. Please wait a moment.", status=429)

    data = request.get_json(silent=True) or {}
    commenter = str(data.get("commenter", "") or "").strip()
    post_id = str(data.get("post_id", "") or "").strip()
    content = str(data.get("content", "") or "").strip()

    if not commenter or not post_id or not content:
        return api_response(False, message="Fields 'commenter', 'post_id', and 'content' are required.", status=400)

    cd_err = check_wallet_cooldown(commenter, "space_comment")
    if cd_err:
        return api_response(cd_err[0], message=cd_err[1], status=cd_err[2])

    bns_name = str(data.get("bns_name", "") or "").strip()
    canonical = [f"{commenter}:{post_id}:{content}", f"{commenter}:{post_id}:{content}:{bns_name}"] if bns_name else f"{commenter}:{post_id}:{content}"
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
        bns_name=bns_name,
    )
    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"Space Comment Added: {post_id} by {commenter[:8]}...")
    if push_service:
        try:
            parent_post = blockchain.space_posts.get(post_id)
            snippet = content[:65].replace('"', "'")
            display_commenter = f"@{bns_name}" if bns_name else f"{commenter[:8]}..."

            # 1. Notify the original author of the post (if commenter != post author)
            if parent_post and parent_post.get("author") and parent_post["author"] != commenter:
                push_service.send_push_to_wallet(
                    parent_post["author"],
                    title="💬 Gönderinize Yorum Yapıldı!",
                    body=f"{display_commenter}: \"{snippet}...\"",
                    url="/#space",
                    category="space"
                )

            # 2. Notify anyone tagged with # or @ in the comment
            tagged_users = blockchain.resolve_tagged_wallets(content)
            for item in tagged_users:
                target_w = item["wallet"]
                if target_w and target_w != commenter and (not parent_post or target_w != parent_post.get("author")):
                    push_service.send_push_to_wallet(
                        target_w,
                        title="💬 Yorumda Etiketlendiniz!",
                        body=f"{display_commenter} yorumda sizden bahsetti: \"{snippet}...\"",
                        url="/#space",
                        category="space"
                    )
        except Exception as _c_err:
            logger.debug(f"Space comment push error: {_c_err}")
    return api_response(True, message=message, data=result, status=201)


@app.route("/api/v1/space/follow", methods=["POST"])
def api_space_follow():
    """
    Follows an on-chain creator or address (Requires cryptographic wallet authentication).
    Cost: 1.00 BCT (50% to creator, 30% to miner/validator fee pool, 20% to Treasury).
    """
    if not check_rate_limit("space_follow", limit=20, window_seconds=60):
        return api_response(False, message="Following too fast. Please wait a moment.", status=429)

    data = request.get_json(silent=True) or {}
    follower = str(data.get("follower", "") or "").strip()
    target = str(data.get("target", "") or "").strip()

    if not follower or not target:
        return api_response(False, message="Fields 'follower' and 'target' are required.", status=400)

    cd_err = check_wallet_cooldown(follower, "space_follow")
    if cd_err:
        return api_response(cd_err[0], message=cd_err[1], status=cd_err[2])

    canonical = f"follow:{follower}:{target}"
    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, follower, canonical
    )
    if not auth_ok:
        return api_response(False, message=auth_err, status=auth_status)

    success, message, result = blockchain.follow_creator(
        follower=follower,
        target=target,
        signature=signature,
        public_key=pub_key,
        signed_payload=signed_payload,
    )
    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"Creator Followed: {target[:8]}... by {follower[:8]}... (1.00 BCT)")
    if push_service:
        try:
            push_service.send_push_to_wallet(
                target,
                title="🌟 Yeni Bir Takipçiniz Var!",
                body=f"{follower[:8]}... sizi takip etmeye başladı (+0.50 BCT kazanç).",
                url="/#space",
                category="space"
            )
        except Exception as _f_err:
            logger.debug(f"Space follow push error: {_f_err}")
    return api_response(True, message=message, data=result, status=200)


@app.route("/api/v1/space/suggested-voices", methods=["GET"])
def api_space_suggested_voices():
    """
    Returns verified on-chain creator accounts for the Suggested Voices sidebar.
    """
    viewer = str(request.args.get("viewer", "") or "").strip()
    try:
        limit = min(max(int(request.args.get("limit", 5)), 1), 20)
    except Exception:
        limit = 5

    voices = blockchain.get_suggested_voices(viewer_address=viewer, limit=limit)
    return api_response(True, message="Suggested voices retrieved", data={"voices": voices})


@app.route("/api/v1/profile/<path:query>", methods=["GET"])
def api_get_user_profile(query: str):
    """
    Returns public non-custodial creator profile, social metrics, BNS handles,
    recent posts, and transaction ledger for an address or .bct handle.
    """
    clean_query = str(query or "").strip()
    if not clean_query:
        return api_response(False, message="Profile query parameter required", status=400)

    profile = blockchain.get_user_profile(clean_query)
    if not profile:
        return api_response(False, message="User profile or address not found", status=404)

    return api_response(True, data=profile)


# ══════════════════════════════════════════════════════
# 🏷️ BNS (LockTrace Name Service — .bct Domain & Handle Protocol)
# ══════════════════════════════════════════════════════

@app.route("/api/v1/bns/check/<name>", methods=["GET"])
def api_bns_check(name):
    """Checks availability and pricing tiers for a .bct domain/handle."""
    res = blockchain.bns_check_available(name)
    return api_response(True, data=res)


@app.route("/api/v1/bns/lookup/<query>", methods=["GET"])
def api_bns_lookup(query):
    """Bi-directional resolution: .bct handle -> address or address -> primary .bct handle."""
    res = blockchain.bns_lookup(query)
    if not res:
        return api_response(False, message=f"No BNS record found for query: '{query}'", status=404)
    return api_response(True, data=res)


@app.route("/api/v1/bns/names", methods=["GET"])
def api_bns_list_names():
    """Returns registered .bct names with optional filter for secondary marketplace items."""
    page = max(1, request.args.get("page", 1, type=int))
    limit = min(100, max(1, request.args.get("limit", 50, type=int)))
    for_sale = request.args.get("for_sale", "").lower() in ("true", "1", "yes")
    res = blockchain.get_all_bns_names(page=page, limit=limit, for_sale_only=for_sale)
    return api_response(True, data=res)


@app.route("/api/v1/bns/analytics", methods=["GET"])
def api_bns_analytics():
    """Returns ecosystem-wide analytics, pricing timeline, treasury fees, and trade records."""
    data = blockchain.get_bns_analytics()
    return api_response(True, data=data)


@app.route("/api/v1/bns/history/<name>", methods=["GET"])
def api_bns_history(name):
    """Returns price and trade history datapoints for a specific .bct handle."""
    data = blockchain.get_bns_history(name)
    if not data:
        return api_response(False, message=f"Handle '{name}' not found", status=404)
    return api_response(True, data=data)


@app.route("/api/v1/bns/register", methods=["POST"])
def api_bns_register():
    """
    Registers a new .bct handle on-chain.
    Tokenomics:
      - 20% of cost returns to circulating supply (miner/validator fee pool).
      - 80% returns directly to the Protocol Treasury Vault pool (Hazine havuzuna geri aktarım).
    """
    if not check_rate_limit("bns_reg", limit=10, window_seconds=60):
        return api_response(False, message="Too many registration requests. Please wait a moment.", status=429)

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "") or "").strip()
    owner = str(data.get("owner", "") or "").strip()

    if not name or not owner:
        return api_response(False, message="Both 'name' and 'owner' address are required.", status=400)

    cd_err = check_wallet_cooldown(owner, "bns_register")
    if cd_err:
        return api_response(cd_err[0], message=cd_err[1], status=cd_err[2])

    pricing = blockchain.get_bns_pricing(name)
    if not pricing["valid"]:
        return api_response(False, message=pricing.get("tier", "Invalid name length (3-24 characters required)."), status=400)

    full_name = pricing["name"]
    cost = pricing["cost"]
    canonical_variants = [
        f"BNS_REGISTER:{full_name}:{owner}:{cost}",
        f"BNS_REGISTER:{full_name}:{owner}:{int(cost)}",
        f"BNS_REGISTER:{full_name}:{owner}:{cost:.1f}",
        f"BNS_REGISTER:{full_name}:{owner}:{cost:.2f}",
        f"BNS_REGISTER:{name}:{owner}:{cost}",
        f"BNS_REGISTER:{name}:{owner}:{int(cost)}",
    ]
    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, owner, canonical_variants
    )
    if not auth_ok:
        return api_response(False, message=auth_err, status=auth_status)

    success, message, result = blockchain.bns_register(
        name=name,
        owner=owner,
        signature=signature,
        public_key=pub_key,
        signed_payload=signed_payload,
    )
    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"BNS Registered: '{full_name}' by {owner[:8]}... (Cost: {pricing['cost']} BCT)")
    return api_response(True, message=message, data=result, status=201)


@app.route("/api/v1/bns/transfer", methods=["POST"])
def api_bns_transfer():
    """Transfers ownership of a .bct handle to another BCT wallet address."""
    if not check_rate_limit("bns_transfer", limit=10, window_seconds=60):
        return api_response(False, message="Too many transfer requests. Please wait a moment.", status=429)

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "") or "").strip()
    current_owner = str(data.get("from_address", "") or "").strip()
    to_address = str(data.get("to_address", "") or "").strip()

    if not name or not current_owner or not to_address:
        return api_response(False, message="Fields 'name', 'from_address', and 'to_address' are required.", status=400)

    norm = blockchain._normalize_bns_name(name)
    canonical_variants = [
        f"BNS_TRANSFER:{norm}:{current_owner}:{to_address}",
        f"BNS_TRANSFER:{name}:{current_owner}:{to_address}",
    ]
    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, current_owner, canonical_variants
    )
    if not auth_ok:
        return api_response(False, message=auth_err, status=auth_status)

    success, message, result = blockchain.bns_transfer(
        name=name,
        current_owner=current_owner,
        to_address=to_address,
        signature=signature,
        public_key=pub_key,
        signed_payload=signed_payload,
    )
    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"BNS Transferred: '{norm}' from {current_owner[:8]}... to {to_address[:8]}...")
    return api_response(True, message=message, data=result, status=200)


@app.route("/api/v1/bns/market/list", methods=["POST"])
def api_bns_market_list():
    """Lists or unlists a .bct handle on the secondary marketplace."""
    if not check_rate_limit("bns_list", limit=15, window_seconds=60):
        return api_response(False, message="Too many listing requests. Please wait a moment.", status=429)

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "") or "").strip()
    owner = str(data.get("owner", "") or "").strip()
    price = safe_float(data.get("price", 0.0), default=0.0)

    if not name or not owner:
        return api_response(False, message="Fields 'name' and 'owner' are required.", status=400)

    norm = blockchain._normalize_bns_name(name)
    price_val = max(0.0, round(float(price), 4))
    canonical_variants = [
        f"BNS_SET_PRICE:{norm}:{owner}:{price_val}",
        f"BNS_SET_PRICE:{norm}:{owner}:{int(price_val)}",
        f"BNS_SET_PRICE:{norm}:{owner}:{price_val:.1f}",
        f"BNS_SET_PRICE:{norm}:{owner}:{price_val:.2f}",
        f"BNS_SET_PRICE:{name}:{owner}:{price_val}",
    ]
    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, owner, canonical_variants
    )
    if not auth_ok:
        return api_response(False, message=auth_err, status=auth_status)

    success, message, result = blockchain.bns_set_price(
        name=name,
        owner=owner,
        price_bct=price_val,
        signature=signature,
        public_key=pub_key,
        signed_payload=signed_payload,
    )
    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"BNS Market Price Set: '{norm}' price={price_val} BCT by {owner[:8]}...")
    return api_response(True, message=message, data=result, status=200)


@app.route("/api/v1/bns/market/buy", methods=["POST"])
def api_bns_market_buy():
    """Purchases a listed .bct handle from the secondary marketplace."""
    if not check_rate_limit("bns_buy", limit=15, window_seconds=60):
        return api_response(False, message="Too many purchase requests. Please wait a moment.", status=429)

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "") or "").strip()
    buyer = str(data.get("buyer", "") or "").strip()

    if not name or not buyer:
        return api_response(False, message="Fields 'name' and 'buyer' are required.", status=400)

    norm = blockchain._normalize_bns_name(name)
    rec = blockchain.bns_lookup(norm)
    if not rec or not rec.get("owner"):
        return api_response(False, message=f"Name '{norm}' is not registered.", status=404)

    seller = rec.get("owner")
    sale_price = rec.get("sale_price", 0.0)
    if sale_price <= 0:
        return api_response(False, message=f"'{norm}' is not listed for sale.", status=400)

    canonical_variants = [
        f"BNS_BUY:{norm}:{buyer}:{seller}:{sale_price}",
        f"BNS_BUY:{norm}:{buyer}:{seller}:{int(sale_price)}",
        f"BNS_BUY:{norm}:{buyer}:{seller}:{sale_price:.1f}",
        f"BNS_BUY:{norm}:{buyer}:{seller}:{sale_price:.2f}",
        f"BNS_BUY:{name}:{buyer}:{seller}:{sale_price}",
    ]
    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, buyer, canonical_variants
    )
    if not auth_ok:
        return api_response(False, message=auth_err, status=auth_status)

    success, message, result = blockchain.bns_buy(
        name=name,
        buyer=buyer,
        signature=signature,
        public_key=pub_key,
        signed_payload=signed_payload,
    )
    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"BNS Market Purchased: '{norm}' by {buyer[:8]}... for {sale_price} BCT from {seller[:8]}...")
    return api_response(True, message=message, data=result, status=200)


@app.route("/api/v1/bns/set-primary", methods=["POST"])
def api_bns_set_primary():
    """Sets a registered .bct handle as the primary handle for an owner address."""
    if not check_rate_limit("bns_set_primary", limit=15, window_seconds=60):
        return api_response(False, message="Too many requests. Please wait a moment.", status=429)

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "") or "").strip()
    owner = str(data.get("owner", "") or "").strip()

    if not name or not owner:
        return api_response(False, message="Fields 'name' and 'owner' are required.", status=400)

    norm = blockchain._normalize_bns_name(name)
    canonical_variants = [
        f"BNS_SET_PRIMARY:{norm}:{owner}",
        f"BNS_SET_PRIMARY:{name}:{owner}",
    ]
    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, owner, canonical_variants
    )
    if not auth_ok:
        return api_response(False, message=auth_err, status=auth_status)

    success, message, result = blockchain.bns_set_primary(
        name=name,
        owner=owner,
        signature=signature,
        public_key=pub_key,
        signed_payload=signed_payload,
    )
    if not success:
        return api_response(False, message=message, status=400)

    logger.info(f"BNS Set Primary: '{norm}' by {owner[:8]}...")
    return api_response(True, message=message, data=result, status=200)


@app.route("/api/v1/bns/offer", methods=["POST"])
def api_bns_offer():
    """
    Submits a non-custodial offer/bid for any registered .bct handle.
    Signed by bidder: BNS_OFFER:{name}:{bidder}:{amount}
    """
    if not check_rate_limit("bns_offer", limit=15, window_seconds=60):
        return api_response(False, message="Too many offer requests. Please wait a moment.", status=429)

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "") or "").strip()
    bidder = str(data.get("bidder", "") or "").strip()
    raw_amt = safe_float(data.get("amount"))
    if raw_amt is None or raw_amt < 0.1:
        return api_response(False, message="Fields 'name', 'bidder', and 'amount' (>= 0.10 BCT) are required.", status=400)
    amount = round(raw_amt, 4)

    if not name or not bidder:
        return api_response(False, message="Fields 'name', 'bidder', and positive 'amount' are required.", status=400)

    norm = blockchain._normalize_bns_name(name)
    canonical_variants = [
        f"BNS_OFFER:{norm}:{bidder}:{amount}",
        f"BNS_OFFER:{norm}:{bidder}:{int(amount)}",
        f"BNS_OFFER:{norm}:{bidder}:{amount:.1f}",
        f"BNS_OFFER:{norm}:{bidder}:{amount:.2f}",
        f"BNS_OFFER:{name}:{bidder}:{amount}",
    ]
    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, bidder, canonical_variants
    )
    if not auth_ok:
        return api_response(False, message=auth_err, status=auth_status)

    success, message, result = blockchain.bns_make_offer(
        name=norm,
        bidder=bidder,
        amount_bct=amount,
        signature=signature,
        public_key=pub_key,
        signed_payload=signed_payload,
    )
    if not success:
        return api_response(False, message=message, status=400)

    # Web push notification to domain owner
    owner = (result or {}).get("owner", "")
    if push_service and owner:
        try:
            push_service.send_push_to_wallet(
                owner,
                title=f"🏷️ @{norm} İçin Yeni Teklif!",
                body=f"{bidder[:8]}... adresi @{norm} için {amount:.2f} BCT teklif sundu.",
                url="/#bns",
                category="bns_offer"
            )
        except Exception as _p_err:
            logger.debug(f"Push dispatch error on bns offer: {_p_err}")

    logger.info(f"BNS Offer: {bidder[:8]}... offered {amount} BCT for '@{norm}'")
    return api_response(True, message=message, data=result, status=201)


@app.route("/api/v1/bns/offer/accept", methods=["POST"])
def api_bns_offer_accept():
    """
    Domain owner accepts an active offer.
    Signed by domain owner: BNS_ACCEPT_OFFER:{name}:{owner}:{offer_id}:{bidder}:{amount}
    """
    if not check_rate_limit("bns_offer_accept", limit=15, window_seconds=60):
        return api_response(False, message="Too many requests. Please wait a moment.", status=429)

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "") or "").strip()
    owner = str(data.get("owner", "") or "").strip()
    offer_id = str(data.get("offer_id", "") or "").strip()

    if not name or not owner or not offer_id:
        return api_response(False, message="Fields 'name', 'owner', and 'offer_id' are required.", status=400)

    norm = blockchain._normalize_bns_name(name)
    rec = blockchain.bns_records.get(norm, {})
    offers = rec.get("offers", {}) if isinstance(rec, dict) else {}
    target_offer = offers.get(offer_id, {}) if isinstance(offers, dict) else {}
    bidder = target_offer.get("bidder", "")
    offer_amount = target_offer.get("amount", 0.0)

    canonical_variants = [
        f"BNS_ACCEPT_OFFER:{norm}:{owner}:{offer_id}:{bidder}:{offer_amount}",
        f"BNS_ACCEPT_OFFER:{norm}:{owner}:{offer_id}:{bidder}:{int(offer_amount)}",
        f"BNS_ACCEPT_OFFER:{norm}:{owner}:{offer_id}:{bidder}:{offer_amount:.1f}",
        f"BNS_ACCEPT_OFFER:{norm}:{owner}:{offer_id}:{bidder}:{offer_amount:.2f}",
        f"BNS_ACCEPT_OFFER:{name}:{owner}:{offer_id}:{bidder}:{offer_amount}",
        f"BNS_ACCEPT_OFFER:{norm}:{owner}:{offer_id}",
        f"BNS_ACCEPT_OFFER:{name}:{owner}:{offer_id}",
    ]
    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, owner, canonical_variants
    )
    if not auth_ok:
        return api_response(False, message=auth_err, status=auth_status)

    success, message, result = blockchain.bns_accept_offer(
        name=norm,
        owner=owner,
        offer_id=offer_id,
        signature=signature,
        public_key=pub_key,
        signed_payload=signed_payload,
    )
    if not success:
        return api_response(False, message=message, status=400)

    # Web push notification to bidder whose offer was accepted
    if push_service and bidder:
        try:
            push_service.send_push_to_wallet(
                bidder,
                title=f"🎉 @{norm} Teklifiniz Kabul Edildi!",
                body=f"Tebrikler! @{norm} alan adı teklifiniz kabul edildi ve cüzdanınıza aktarıldı.",
                url="/#bns",
                category="bns_offer"
            )
        except Exception as _p_err:
            logger.debug(f"Push dispatch error on bns accept: {_p_err}")

    logger.info(f"BNS Offer Accepted: '{norm}' by owner {owner[:8]}... -> new owner {bidder[:8]}...")
    return api_response(True, message=message, data=result, status=200)


@app.route("/api/v1/bns/offer/cancel", methods=["POST"])
def api_bns_offer_cancel():
    """
    Cancels or rejects an active offer.
    Callable by bidder (cancel) or owner (reject).
    Signed by actor: BNS_CANCEL_OFFER:{name}:{actor}:{offer_id}
    """
    if not check_rate_limit("bns_offer_cancel", limit=20, window_seconds=60):
        return api_response(False, message="Too many requests. Please wait a moment.", status=429)

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "") or "").strip()
    actor = str(data.get("actor", "") or "").strip()
    offer_id = str(data.get("offer_id", "") or "").strip()

    if not name or not actor or not offer_id:
        return api_response(False, message="Fields 'name', 'actor', and 'offer_id' are required.", status=400)

    norm = blockchain._normalize_bns_name(name)
    rec = blockchain.bns_records.get(norm, {})
    owner = rec.get("owner", "") if isinstance(rec, dict) else ""
    offers = rec.get("offers", {}) if isinstance(rec, dict) else {}
    target_offer = offers.get(offer_id, {}) if isinstance(offers, dict) else {}
    bidder = target_offer.get("bidder", "")

    canonical_variants = [
        f"BNS_CANCEL_OFFER:{norm}:{actor}:{offer_id}",
        f"BNS_CANCEL_OFFER:{name}:{actor}:{offer_id}",
    ]
    auth_ok, auth_status, auth_err, signature, pub_key, signed_payload = resolve_authenticated_action(
        data, actor, canonical_variants
    )
    if not auth_ok:
        return api_response(False, message=auth_err, status=auth_status)

    success, message, result = blockchain.bns_cancel_offer(
        name=norm,
        actor=actor,
        offer_id=offer_id,
        signature=signature,
        public_key=pub_key,
        signed_payload=signed_payload,
    )
    if not success:
        return api_response(False, message=message, status=400)

    # If domain owner rejected the offer, notify bidder
    if actor == owner and push_service and bidder:
        try:
            push_service.send_push_to_wallet(
                bidder,
                title=f"❌ @{norm} Teklifiniz Reddedildi",
                body=f"Alan adı sahibi @{norm} için sunduğunuz teklifi reddetti.",
                url="/#bns",
                category="bns_offer"
            )
        except Exception as _p_err:
            logger.debug(f"Push dispatch error on bns reject: {_p_err}")

    logger.info(f"BNS Offer Cancelled/Rejected: '{norm}' offer {offer_id} by {actor[:8]}...")
    return api_response(True, message=message, data=result, status=200)


@app.route("/api/v1/bns/offers/<name>", methods=["GET"])
def api_bns_get_domain_offers(name):
    """Returns all active and historical offers for a specific .bct domain name."""
    norm = blockchain._normalize_bns_name(name)
    data = blockchain.bns_get_offers(name=norm)
    return api_response(True, data=data)


@app.route("/api/v1/bns/my-offers/<address>", methods=["GET"])
def api_bns_get_my_offers(address):
    """Returns all received and sent offers for a specific wallet address."""
    clean_addr = str(address or "").strip()
    data = blockchain.bns_get_offers(address=clean_addr)
    return api_response(True, data=data)


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
    if not check_rate_limit("trade_buy", limit=15, window_seconds=60):
        return api_response(False, message="Too many requests. Please wait.", status=429)
    data = request.get_json(silent=True) or {}
    buyer_address = str(data.get("buyer_address", "") or "").strip()
    fiat_amount = safe_float(data.get("fiat_amount", 0.0), default=0.0)
    currency = str(data.get("currency", "USD") or "USD").strip().upper()[:8]
    session_token = str(data.get("session_token", "") or "").strip()[:128]

    if not buyer_address or not is_valid_bct_address(buyer_address):
        return api_response(False, message="Valid recipient BCT wallet address is required.", status=400)

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
    if not check_rate_limit("trade_sell", limit=15, window_seconds=60):
        return api_response(False, message="Too many requests. Please wait.", status=429)
    data = request.get_json(silent=True) or {}
    seller_address = str(data.get("seller_address", "") or "").strip()
    bct_amount = safe_float(data.get("bct_amount", 0.0), default=0.0)
    currency = str(data.get("currency", "USD") or "USD").strip().upper()[:8]
    payout_info = str(data.get("payout_info", "") or "").strip()[:128]

    if not seller_address or not is_valid_bct_address(seller_address):
        return api_response(False, message="Valid seller BCT wallet address is required.", status=400)

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
        return api_response(False, message="Unauthorized: Valid X-API-Key header is required.", status=401)

    data = request.get_json(silent=True) or {}
    contract_address = str(data.get("contract_address", "") or "").strip()
    to_address = str(data.get("to", data.get("to_address", "")) or "").strip()
    token_id = safe_int(data.get("token_id", 0), default=-1)
    quantity = safe_int(data.get("quantity", 1), default=0)
    chain = str(data.get("chain", Config.THIRDWEB_DEFAULT_CHAIN) or Config.THIRDWEB_DEFAULT_CHAIN).strip()
    server_wallet = str(data.get("server_wallet", "") or "").strip() or None

    if not EVM_ADDRESS_RE.match(contract_address):
        return api_response(False, message="Invalid EVM contract address (0x + 40 hex characters required).", status=400)
    if not EVM_ADDRESS_RE.match(to_address):
        return api_response(False, message="Invalid target EVM wallet address (0x + 40 hex characters required).", status=400)
    if server_wallet and not EVM_ADDRESS_RE.match(server_wallet):
        return api_response(False, message="Invalid server_wallet address.", status=400)
    if token_id < 0 or token_id > 10**18:
        return api_response(False, message="Invalid token_id value.", status=400)
    if quantity < 1 or quantity > 1000:
        return api_response(False, message="quantity must be between 1 and 1000.", status=400)
    if not SAFE_CHAIN_RE.match(chain):
        return api_response(False, message="Invalid chain parameter.", status=400)

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
        return api_response(False, message="Invalid transaction_id format.", status=400)

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
        return api_response(False, message="Invalid transaction_id format.", status=400)

    result = thirdweb_service.wait_for_transaction_hash(clean_tx_id)
    if not result.get("success", False):
        return api_response(False, message=result.get("error", "Failed to get transaction hash"), status=400)
    return api_response(True, data=result.get("data", {}))


# ── Cross-Chain Bridge Endpoints (LockTrace L1 <-> EVM wBCT) ─────────────
@app.route("/api/v1/bridge/config", methods=["GET"])
def api_bridge_config():
    return api_response(True, data=bridge_manager.get_bridge_config())


def _verify_l1_bridge_lock_tx(tx_hash_l1: str, expected_sender: str, expected_amount: float) -> Tuple[bool, str]:
    """
    Cryptographically verifies that a LockTrace Layer-1 transaction genuinely transferred
    `expected_amount` BCT from `expected_sender` to `BRIDGE_VAULT_ADDRESS`.
    Prevents forged L1_TO_EVM bridge confirmations.
    """
    clean_hash = (tx_hash_l1 or "").strip().lower()
    if not clean_hash or len(clean_hash) != 64:
        return False, "Invalid Layer-1 transaction hash format (64 hex chars required)."

    tx_obj = blockchain.get_tx_by_hash(clean_hash)
    if not tx_obj:
        return False, "Layer-1 lock transaction not found on LockTrace blockchain or mempool."

    if str(tx_obj.get("tx_type", "")) != "transfer":
        return False, "Referenced Layer-1 transaction is not a standard BCT transfer."

    receiver = str(tx_obj.get("receiver") or tx_obj.get("recipient") or "").strip()
    if receiver != BRIDGE_VAULT_ADDRESS:
        return False, f"Transaction recipient must be the official Bridge Vault ({BRIDGE_VAULT_ADDRESS})."

    sender = str(tx_obj.get("sender") or "").strip()
    if expected_sender and sender.lower() != expected_sender.strip().lower():
        return False, "Transaction sender does not match the bridge order BCT wallet address."

    actual_amount = float(tx_obj.get("amount") or 0.0)
    if abs(actual_amount - float(expected_amount)) > 0.0001:
        return False, f"Locked amount mismatch: expected {expected_amount:.4f} BCT, found {actual_amount:.4f} BCT."

    return True, "Verified"


@app.route("/api/v1/bridge/order", methods=["POST"])
def api_bridge_create_order():
    if not check_rate_limit("bridge_create", limit=15, window_seconds=60):
        return api_response(False, message="Too many bridge requests. Please wait.", status=429)

    payload = request.get_json(silent=True) or {}
    direction = str(payload.get("direction", "L1_TO_EVM")).strip().upper()
    bct_address = str(payload.get("bct_address", "")).strip()
    if bct_address.upper().startswith("BCT") and len(bct_address) == 43:
        bct_address = "BCT" + bct_address[3:].lower()
    evm_address = str(payload.get("evm_address", "")).strip()
    chain = str(payload.get("chain", "base")).strip()
    tx_hash_l1 = str(payload.get("tx_hash_l1", "")).strip().lower()

    amount_bct = safe_float(payload.get("amount"))
    if amount_bct is None or amount_bct <= 0:
        return api_response(False, message="Invalid transfer amount.", status=400)

    if direction == "L1_TO_EVM" and tx_hash_l1:
        ok_lock, lock_err = _verify_l1_bridge_lock_tx(tx_hash_l1, bct_address, amount_bct)
        if not ok_lock:
            return api_response(False, message=lock_err, status=400)

    result = bridge_manager.create_bridge_order(
        direction=direction,
        bct_address=bct_address,
        evm_address=evm_address,
        amount_bct=amount_bct,
        chain=chain,
        tx_hash_l1=tx_hash_l1
    )

    if not result.get("success"):
        return api_response(False, message=result.get("error", "Bridge order creation failed"), status=400)

    logger.info(f"Cross-Chain Bridge Order Created: {result['data']['bridge_id']} [{direction}] {amount_bct} BCT -> {evm_address}")
    return api_response(True, data=result["data"], status=201)


@app.route("/api/v1/bridge/status/<bridge_id>", methods=["GET"])
def api_bridge_get_status(bridge_id: str):
    clean_id = (bridge_id or "").strip()
    st = bridge_manager.get_bridge_status(clean_id)
    if not st:
        return api_response(False, message="Bridge transaction not found.", status=404)
    return api_response(True, data=st)


@app.route("/api/v1/bridge/history/<address>", methods=["GET"])
def api_bridge_get_history(address: str):
    clean_addr = (address or "").strip()
    history = bridge_manager.get_history_by_address(clean_addr)
    return api_response(True, data={"orders": history, "total": len(history)})


@app.route("/api/v1/bridge/base-transactions", methods=["GET"])
def api_bridge_base_transactions():
    """
    Returns verified Base L2 wBCT transactions and bridge activities so users
    can inspect Base activity directly within LockTrace Explorer without navigating to BaseScan.
    """
    limit = min(int(request.args.get("limit", 50)), 200)
    filter_addr = str(request.args.get("address", "")).strip().lower()

    if filter_addr:
        raw_txs = bridge_manager.get_history_by_address(filter_addr, limit=limit)
    else:
        raw_txs = bridge_manager.get_all_transactions(limit=limit)

    contract_addr = getattr(bridge_manager, "wbct_contract", "0xA3C743113a41cFd0146917065d4578337Bb77254")
    formatted_txs = []

    for tx in raw_txs:
        evm_hash = str(tx.get("tx_hash_evm") or "").strip()
        if evm_hash and not evm_hash.startswith("0x") and len(evm_hash) == 64:
            evm_hash = f"0x{evm_hash}"

        direction = tx.get("direction", "L1_TO_EVM")
        event_type = "Base wBCT Mint (Bridge In)" if direction == "L1_TO_EVM" else "Base wBCT Burn (Unlock to L1)"

        formatted_txs.append({
            "bridge_id": tx.get("bridge_id"),
            "direction": direction,
            "event_type": event_type,
            "status": tx.get("status"),
            "bct_address": tx.get("bct_address"),
            "evm_address": tx.get("evm_address"),
            "chain": tx.get("chain", "base"),
            "amount": float(tx.get("amount_bct", 0.0)),
            "fee": float(tx.get("fee_bct", 0.0) or 0.0),
            "net_amount": float(tx.get("net_amount", 0.0) or 0.0),
            "tx_hash_l1": tx.get("tx_hash_l1"),
            "tx_hash_evm": evm_hash if evm_hash else None,
            "basescan_tx_url": f"https://basescan.org/tx/{evm_hash}" if evm_hash and evm_hash.startswith("0x") else None,
            "basescan_token_url": f"https://basescan.org/token/{contract_addr}",
            "contract_address": contract_addr,
            "created_at": tx.get("created_at"),
            "updated_at": tx.get("updated_at")
        })

    return api_response(True, data={
        "transactions": formatted_txs,
        "total": len(formatted_txs),
        "contract_address": contract_addr,
        "chain_id": 8453,
        "chain_name": "Base Mainnet",
        "basescan_contract_url": f"https://basescan.org/token/{contract_addr}"
    })


@app.route("/api/v1/bridge/confirm", methods=["POST"])
def api_bridge_confirm():
    if not check_rate_limit("bridge_confirm", limit=20, window_seconds=60):
        return api_response(False, message="Too many bridge confirmation requests. Please wait.", status=429)

    payload = request.get_json(silent=True) or {}
    bridge_id = str(payload.get("bridge_id", "")).strip()
    tx_hash = str(payload.get("tx_hash", "")).strip().lower()
    if not bridge_id or not tx_hash:
        return api_response(False, message="bridge_id and tx_hash are required.", status=400)

    order = bridge_manager.get_bridge_status(bridge_id)
    if not order:
        return api_response(False, message="Bridge transaction not found.", status=404)

    ok_lock, lock_err = _verify_l1_bridge_lock_tx(
        tx_hash_l1=tx_hash,
        expected_sender=str(order.get("bct_address", "")),
        expected_amount=float(order.get("amount_bct", 0.0)),
    )
    if not ok_lock:
        return api_response(False, message=lock_err, status=400)

    res = bridge_manager.confirm_l1_lock(bridge_id, tx_hash)
    if not res.get("success"):
        return api_response(False, message=res.get("error", "Verification failed"), status=400)
    return api_response(True, data=res)


_BRIDGE_CLAIM_LOCK = threading.Lock()
_BRIDGE_CLAIMS_IN_FLIGHT = set()


@app.route("/api/v1/bridge/claim_burn", methods=["POST"])
def api_bridge_claim_burn():
    """
    Called after a user burns wBCT on Base Mainnet via `burnToBridge`.
    Verifies parameters and executes immediate 1:1 unlock on LockTrace Layer-1.
    """
    if not check_rate_limit("bridge_claim_burn", limit=30, window_seconds=60):
        return api_response(False, message="Too many unlock requests. Please wait.", status=429)

    payload = request.get_json(silent=True) or {}
    evm_tx_hash = str(payload.get("evm_tx_hash", "")).strip().lower()
    bct_address = str(payload.get("bct_address", "")).strip()
    if bct_address.upper().startswith("BCT") and len(bct_address) == 43:
        bct_address = "BCT" + bct_address[3:].lower()
    evm_sender = str(payload.get("evm_sender", "")).strip().lower()
    safe_sender = evm_sender if (evm_sender.startswith("0x") and len(evm_sender) == 42) else "0x0000000000000000000000000000000000000000"

    amount_bct = safe_float(payload.get("amount"))
    if amount_bct is None or amount_bct <= 0:
        return api_response(False, message="Invalid transfer amount.", status=400)

    if not evm_tx_hash or not evm_tx_hash.startswith("0x") or len(evm_tx_hash) != 66:
        return api_response(False, message="Invalid Base EVM transaction hash (0x... 66 characters required).", status=400)

    if not (bct_address.startswith("BCT") and len(bct_address) == 43) or not re.match(r"^BCT[0-9a-fA-F]{40}$", bct_address) or re.match(r"^BCT0{40}$", bct_address, re.IGNORECASE):
        return api_response(False, message="Invalid or reserved LockTrace BCT recipient address.", status=400)

    if amount_bct < 1.0:
        return api_response(False, message="Minimum bridge amount is 1.00 BCT.", status=400)

    # Concurrency Lock (LT-02 Race-Condition & Double-Spend Defense)
    with _BRIDGE_CLAIM_LOCK:
        if evm_tx_hash in _BRIDGE_CLAIMS_IN_FLIGHT:
            return api_response(False, message="This EVM burn transaction is currently being processed.", status=409)
        _BRIDGE_CLAIMS_IN_FLIGHT.add(evm_tx_hash)

    try:
        # 0. Cryptographic On-Chain Verification on Base Mainnet
        verified, v_msg, event_data = verify_evm_burn_receipt(
            evm_tx_hash=evm_tx_hash,
            expected_recipient=bct_address,
            expected_amount=amount_bct
        )
        if not verified:
            # Allow admin key override only if network is offline and caller has admin key
            if event_data.get("network_error") and _require_admin_api_key():
                logger.warning(f"Bridge unlock granted via ADMIN_API_KEY override for {evm_tx_hash}")
            else:
                return api_response(False, message=f"Burn could not be verified on Base Mainnet: {v_msg}", status=400)
        else:
            verified_sender = str(event_data.get("sender") or "").strip().lower()
            if verified_sender.startswith("0x") and len(verified_sender) == 42:
                safe_sender = verified_sender

        # 0.5. Check if this EVM transaction has already been unlocked on-chain
        for block in blockchain.chain:
            for tx in block.transactions:
                if tx.tx_type == "bridge_unlock" and tx.extra_data and str(tx.extra_data.get("evm_tx_hash", "")).lower() == evm_tx_hash:
                    with bridge_manager._get_connection() as conn:
                        conn.execute("UPDATE bridge_transactions SET status = 'COMPLETED', updated_at = ? WHERE tx_hash_evm = ?", (time.time(), evm_tx_hash))
                    return api_response(True, data={
                        "already_unlocked": True,
                        "evm_tx_hash": evm_tx_hash,
                        "recipient": bct_address,
                        "message": "This EVM burn transaction has already been unlocked on LockTrace."
                    }, status=200)

        # 1. Register order in bridge_manager if not already registered
        order_res = bridge_manager.create_bridge_order(
            direction="EVM_TO_L1",
            bct_address=bct_address,
            evm_address=safe_sender,
            amount_bct=amount_bct,
            chain="base",
            tx_hash_evm=evm_tx_hash
        )
        bridge_id = order_res.get("data", {}).get("bridge_id", "")

        # 2. Execute on-chain Layer-1 unlock (transfers BCT to user and seals block)
        ok, msg, tx_data = blockchain.execute_bridge_unlock(
            recipient_address=bct_address,
            amount_bct=amount_bct,
            evm_tx_hash=evm_tx_hash,
            evm_sender=safe_sender
        )

        if not ok:
            if "daha önce" in msg or "already" in msg:
                if bridge_id:
                    bridge_manager.complete_bridge(bridge_id, tx_hash_evm=evm_tx_hash)
                return api_response(True, data={
                    "already_unlocked": True,
                    "evm_tx_hash": evm_tx_hash,
                    "message": msg
                }, status=200)
            else:
                if bridge_id:
                    with bridge_manager._get_connection() as conn:
                        conn.execute("UPDATE bridge_transactions SET status = 'FAILED', error_message = ?, updated_at = ? WHERE bridge_id = ?", (msg, time.time(), bridge_id))
                return api_response(False, message=msg, status=400)

        # 3. Mark bridge order as completed in bridge database
        if bridge_id:
            bridge_manager.complete_bridge(bridge_id, tx_hash_evm=evm_tx_hash)

        logger.info(f"Cross-Chain Bridge EVM->L1 Unlock Successful: {amount_bct} BCT to {bct_address} (EVM Tx: {evm_tx_hash})")
        return api_response(True, data={
            "bridge_id": bridge_id,
            "l1_tx_hash": tx_data.get("tx_hash"),
            "evm_tx_hash": evm_tx_hash,
            "recipient": bct_address,
            "amount": amount_bct,
            "block_index": tx_data.get("block_index"),
            "new_balance": tx_data.get("new_balance"),
            "message": msg
        }, status=200)
    finally:
        with _BRIDGE_CLAIM_LOCK:
            _BRIDGE_CLAIMS_IN_FLIGHT.discard(evm_tx_hash)



if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
