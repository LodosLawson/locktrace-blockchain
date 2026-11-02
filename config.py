"""
BlockChainT - Yapılandırma
===========================
Ortam değişkenleri veya varsayılan değerler ile yapılandırma.
Hassas API anahtarları .env üzerinden okunur ve asla istemciye açık edilmez.
"""

import os
import secrets

# ── Otomatik .env yükleyici ─────────────────────────
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass


class Config:
    # ── Güvenlik ──────────────────────────────────────
    SECRET_KEY = os.environ.get("BCT_SECRET_KEY", secrets.token_hex(32))
    ADMIN_API_KEY = os.environ.get("BCT_ADMIN_KEY", secrets.token_hex(24))

    # ── Thirdweb Yapılandırması (Gizli Anahtarlar Backend'de Saklanır) ──
    THIRDWEB_CLIENT_ID = os.environ.get("THIRDWEB_CLIENT_ID", "a1fca74604210a59de7fe189ae76f156")
    THIRDWEB_SECRET_KEY = os.environ.get(
        "THIRDWEB_SECRET_KEY",
        "gGarsHl3rFMziwML_BqvptsdOsvUT34Tzdl8YkwUsj3ecrgj-tyKDpjiPGUpQWv5idnRYD2KwrV7RE641E1Zow"
    )
    THIRDWEB_SERVER_WALLET_ADDRESS = os.environ.get("THIRDWEB_SERVER_WALLET_ADDRESS", "")
    THIRDWEB_ENGINE_URL = os.environ.get("THIRDWEB_ENGINE_URL", "")
    THIRDWEB_DEFAULT_CHAIN = os.environ.get("THIRDWEB_DEFAULT_CHAIN", "base-sepolia")

    # ── Fiyat ve Ticaret Oranları ─────────────────────
    BCT_PER_USD = float(os.environ.get("BCT_PER_USD", "100.0"))       # 1 USD = 100 BCT
    BCT_PRICE_USD = float(os.environ.get("BCT_PRICE_USD", "0.01"))    # 1 BCT = $0.01
    MIN_BUY_USD = 1.0
    MAX_BUY_USD = 10_000.0

    # ── Rate Limiting ─────────────────────────────────
    RATE_LIMIT_DEFAULT = "120/minute"
    RATE_LIMIT_WALLET_CREATE = "10/minute;50/hour"
    RATE_LIMIT_TRANSACTION = "60/minute;500/hour"
    RATE_LIMIT_QUERY = "300/minute"

    # ── CORS ──────────────────────────────────────────
    CORS_ORIGINS = os.environ.get(
        "BCT_CORS_ORIGINS",
        "https://locktrace.space,https://www.locktrace.space,https://spectacular-brioche-aafb73.netlify.app,http://localhost:3000,http://localhost:5000,http://127.0.0.1:5000"
    ).split(",")

    # ── Sunucu ────────────────────────────────────────
    HOST = os.environ.get("BCT_HOST", "0.0.0.0")
    PORT = int(os.environ.get("BCT_PORT", "5000"))
    DEBUG = os.environ.get("BCT_DEBUG", "false").lower() == "true"

    # ── Blockchain ────────────────────────────────────
    MIN_TRANSACTION = 0.00000001   # Minimum transfer miktarı
    MAX_TRANSACTION = 1_000_000    # Maksimum tek seferde transfer
    MAX_PENDING_TX = 5000          # Maksimum bekleyen işlem
    AUTO_MINE = True               # Otomatik madencilik

    # ── Loglama ───────────────────────────────────────
    LOG_LEVEL = os.environ.get("BCT_LOG_LEVEL", "INFO")
    LOG_FILE = os.environ.get("BCT_LOG_FILE", "logs/blockchain.log")
