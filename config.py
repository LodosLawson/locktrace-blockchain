"""
BlockChainT - Master Protocol Configuration (SSOT)
==================================================
Single Source of Truth (SSOT) for all protocol constants, tokenomics,
fees, rate limits, consensus parameters, and validator thresholds.

All subsystems (core/blockchain.py, server.py, scripts, and documentation)
reference this canonical specification.
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
    # ── Protokol & Versiyon ───────────────────────────
    PROTOCOL_VERSION = "2.8.2"
    NETWORK_NAME = os.environ.get("BCT_NETWORK", "mainnet")

    # ── Anti-Stall & Resilience Parameters (v2.5.0) ───
    EMERGENCY_STALL_TIMEOUT = 120.0       # 6x blok süresi boyunca blok çıkmazsa acil zorluk düşürme aktifleşir
    MEMPOOL_EVICTION_ENABLED = True       # Mempool dolduğunda düşük ücretli işlemlerin yerini yüksek ücretliler alır (RBF)
    ACTIVE_RAM_BLOCK_WINDOW = 2000        # RAM'de tutulan aktif blok penceresi (eski bloklar SQLite'tan sorgulanır)

    # ── Compact Block & State Snapshot Parameters (v2.6.0 & v2.7.0) ──
    COMPACT_BLOCKS_ENABLED = True         # P2P Compact Block Relay (~90% bant genişliği tasarrufu)
    STATE_SNAPSHOT_WINDOW = 1000          # Hızlı senkronizasyonda doğrulanacak son blok penceresi
    GPU_MINING_ENABLED = True             # OpenCL / CUDA GPU madenciliği hızlandırması

    # ── Güvenlik ──────────────────────────────────────
    SECRET_KEY = os.environ.get("BCT_SECRET_KEY", secrets.token_hex(32))
    ADMIN_API_KEY = os.environ.get("BCT_ADMIN_KEY", secrets.token_hex(24))

    # ── Thirdweb Yapılandırması ───────────────────────
    THIRDWEB_CLIENT_ID = os.environ.get("THIRDWEB_CLIENT_ID", "")
    THIRDWEB_SECRET_KEY = os.environ.get("THIRDWEB_SECRET_KEY", "")
    THIRDWEB_SERVER_WALLET_ADDRESS = os.environ.get("THIRDWEB_SERVER_WALLET_ADDRESS", "")
    THIRDWEB_ENGINE_URL = os.environ.get("THIRDWEB_ENGINE_URL", "")
    THIRDWEB_DEFAULT_CHAIN = os.environ.get("THIRDWEB_DEFAULT_CHAIN", "base-sepolia")

    # ── Tokenomik & SocialFi Ücretleri (BCT) ───────────
    SPACE_POST_FEE = 0.10       # 100% Burn to BURN_ADDRESS
    SPACE_LIKE_FEE = 0.01       # 80% Creator, 20% Burn
    SPACE_COMMENT_FEE = 0.02    # 50% Creator, 50% Burn
    SPACE_FOLLOW_FEE = 1.00     # 80% Creator, 20% Burn

    # ── BNS Alan Adı Kayıt Ücretleri (100% Burn) ──────
    BNS_FEES = {
        3: 100.0,   # 3 karakter (örn: abc.bct)
        4: 50.0,    # 4 karakter (örn: lock.bct)
        5: 10.0     # 5+ karakter (örn: trace.bct)
    }

    # ── Konsensüs & Blok Ödülü Dağılımı ───────────────
    REWARD_MINER_PERCENT = 70       # %70 PoW madencisine
    REWARD_VALIDATOR_PERCENT = 30   # %30 aktif tasdikleyici (validator) havuzuna
    BASE_BLOCK_REWARD = 50.0        # Başlangıç blok ödülü

    # ── Sybil Koruması & Validator Teminatı (Stake) ───
    MIN_VALIDATOR_STAKE = 1000.0    # Validator olmak ve %30 ödülden pay almak için min bakiye/stake
    EQUIVOCATION_SLASH_PERCENT = 100 # Çift imza / çelişkili blok tasdikinde %100 slashing

    # ── Dinamik Zorluk (LWMA) & Hedef Blok Süresi ─────
    TARGET_BLOCK_TIME = 20.0        # Hedeflenen blok üretim süresi (saniye)
    LWMA_WINDOW = 20                # Zorluk ayarlaması için incelenen geçmiş blok sayısı
    INITIAL_DIFFICULTY = 3          # Başlangıç PoW zorluğu (hex sıfır sayısı)
    FINALITY_QUORUM_RATIO = 2.0 / 3.0  # Finalized checkpoint için gereken validator onay oranı (%66.7)

    # ── Anti-Spam & İşlem Tipi Bekleme Süreleri (Saniye)
    ACTION_COOLDOWNS = {
        "space_like": 0,        # Beğeni: Anlık (0s) - Mempool çift beğeni & IP limitleri devrede
        "space_comment": 5,     # Yorum: 5 saniye
        "transfer": 3,          # Para Transferi: 3 saniye
        "space_post": 10,       # Post Paylaşımı: 10 saniye
        "bns_register": 10,     # İsim Alma: 10 saniye
        "space_follow": 3       # Takip Etme: 3 saniye
    }

    # ── Cross-Chain Bridge Güvenliği ──────────────────
    MIN_EVM_CONFIRMATIONS = 12   # Base Mainnet reorg koruması için gereken min onay sayısı
    WBCT_CONTRACT_ADDRESS = os.environ.get("WBCT_CONTRACT_ADDRESS", "0xA3C743113a41cFd0146917065d4578337Bb77254")
    BASE_RPC_URL = os.environ.get("BASE_RPC_URL", "https://mainnet.base.org")

    # ── Fiyat ve Ticaret Oranları ─────────────────────
    BCT_PER_USD = float(os.environ.get("BCT_PER_USD", "100.0"))       # 1 USD = 100 BCT
    BCT_PRICE_USD = float(os.environ.get("BCT_PRICE_USD", "0.01"))    # 1 BCT = $0.01
    MIN_BUY_USD = 1.0
    MAX_BUY_USD = 10_000.0

    # ── Rate Limiting (Genel HTTP) ────────────────────
    RATE_LIMIT_DEFAULT = "120/minute"
    RATE_LIMIT_WALLET_CREATE = "10/minute;50/hour"
    RATE_LIMIT_TRANSACTION = "60/minute;500/hour"
    RATE_LIMIT_QUERY = "300/minute"

    # ── CORS ──────────────────────────────────────────
    CORS_ORIGINS = os.environ.get(
        "BCT_CORS_ORIGINS",
        "https://locktrace.space,https://www.locktrace.space,https://spectacular-brioche-aafb73.netlify.app,http://localhost:3000,http://localhost:5000,http://127.0.0.1:5000"
    ).split(",")

    # ── Sunucu & Veritabanı ───────────────────────────
    DB_PATH = os.environ.get("BCT_DB_PATH", "blockchain.db")
    HOST = os.environ.get("BCT_HOST", "0.0.0.0")
    PORT = int(os.environ.get("BCT_PORT", "5000"))
    DEBUG = os.environ.get("BCT_DEBUG", "false").lower() == "true"
    DEV_MODE = os.environ.get("BCT_DEV_MODE", "true").lower() == "true"

    # ── Blockchain Mempool & Limitler ─────────────────
    MIN_TRANSACTION = 0.00000001   # Minimum transfer miktarı
    MAX_TRANSACTION = 1_000_000    # Maksimum tek seferde transfer
    MAX_PENDING_TX = 5000          # Maksimum bekleyen işlem
    AUTO_MINE = True               # Otomatik madencilik

    # ── Loglama ───────────────────────────────────────
    LOG_LEVEL = os.environ.get("BCT_LOG_LEVEL", "INFO")
    LOG_FILE = os.environ.get("BCT_LOG_FILE", "logs/blockchain.log")
