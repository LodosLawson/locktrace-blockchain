"""
BlockChainT - Yapılandırma
===========================
Ortam değişkenleri veya varsayılan değerler ile yapılandırma.
"""

import os
import secrets


class Config:
    # ── Güvenlik ──────────────────────────────────────
    SECRET_KEY = os.environ.get("BCT_SECRET_KEY", secrets.token_hex(32))
    ADMIN_API_KEY = os.environ.get("BCT_ADMIN_KEY", secrets.token_hex(24))

    # ── Rate Limiting ─────────────────────────────────
    RATE_LIMIT_DEFAULT = "120/minute"
    RATE_LIMIT_WALLET_CREATE = "5/minute;20/hour"
    RATE_LIMIT_TRANSACTION = "30/minute;200/hour"
    RATE_LIMIT_QUERY = "300/minute"

    # ── CORS ──────────────────────────────────────────
    CORS_ORIGINS = os.environ.get(
        "BCT_CORS_ORIGINS",
        "https://locktrace.space,https://www.locktrace.space,http://localhost:3000,http://localhost:5000,http://127.0.0.1:5000"
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

