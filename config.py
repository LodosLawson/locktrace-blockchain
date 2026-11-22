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
                    v = v.strip()
                    # Strip inline comments (e.g. KEY=val # comment) while preserving quotes
                    if not (v.startswith('"') or v.startswith("'")):
                        v = v.split("#")[0].strip()
                    else:
                        q = v[0]
                        end_idx = v.find(q, 1)
                        if end_idx != -1:
                            v = v[1:end_idx]
                        else:
                            v = v.strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass


class Config:
    # ── Protokol & Versiyon ───────────────────────────
    PROTOCOL_VERSION = "2.12.1"
    NETWORK_NAME = os.environ.get("BCT_NETWORK", "mainnet")

    # ── Anti-Stall & Resilience Parameters (v2.5.0) ───
    EMERGENCY_STALL_TIMEOUT = 120.0       # 6x blok süresi boyunca blok çıkmazsa acil zorluk düşürme aktifleşir
    MEMPOOL_EVICTION_ENABLED = True       # Mempool dolduğunda düşük ücretli işlemlerin yerini yüksek ücretliler alır (RBF)
    ACTIVE_RAM_BLOCK_WINDOW = 2000        # RAM'de tutulan aktif blok penceresi (eski bloklar SQLite'tan sorgulanır)

    # ── Compact Block & State Snapshot Parameters (v2.6.0 & v2.7.0) ──
    COMPACT_BLOCKS_ENABLED = True         # P2P Compact Block Relay (~90% bant genişliği tasarrufu)
    STATE_SNAPSHOT_WINDOW = 1000          # Hızlı senkronizasyonda doğrulanacak son blok penceresi
    GPU_MINING_ENABLED = True             # OpenCL / CUDA GPU madenciliği hızlandırması

    # ── Güvenlik (LT-SRV-01 Defense-In-Depth Koruması) ──
    _insecure_defaults = {"change_me_in_production", "change_me", "admin", "123456", "secret", "password"}
    _raw_secret = os.environ.get("BCT_SECRET_KEY", "").strip()
    _raw_admin = os.environ.get("BCT_ADMIN_KEY", "").strip()

    SECRET_KEY = secrets.token_hex(32) if (not _raw_secret or _raw_secret.lower() in _insecure_defaults) else _raw_secret
    ADMIN_API_KEY = secrets.token_hex(32) if (not _raw_admin or _raw_admin.lower() in _insecure_defaults) else _raw_admin

    # ── Thirdweb Yapılandırması ───────────────────────
    THIRDWEB_CLIENT_ID = os.environ.get("THIRDWEB_CLIENT_ID", "")
    THIRDWEB_SECRET_KEY = os.environ.get("THIRDWEB_SECRET_KEY", "")
    THIRDWEB_SERVER_WALLET_ADDRESS = os.environ.get("THIRDWEB_SERVER_WALLET_ADDRESS", "")
    THIRDWEB_ENGINE_URL = os.environ.get("THIRDWEB_ENGINE_URL", "")
    THIRDWEB_DEFAULT_CHAIN = os.environ.get("THIRDWEB_DEFAULT_CHAIN", "base-sepolia")

    # ── Tokenomik & SocialFi Ücretleri (BCT) ───────────
    SPACE_POST_FEE = 0.10       # 80% Treasury reserve, 20% Validator/Miner fee
    SPACE_LIKE_FEE = 0.01       # 20% Creator royalty, 70% Treasury reserve, 10% Validator fee
    SPACE_COMMENT_FEE = 0.02    # 20% Creator royalty, 70% Treasury reserve, 10% Validator fee
    SPACE_FOLLOW_FEE = 1.00     # 50% Creator, 30% Miner/Validator pool, 20% Treasury reserve

    # ── BNS Alan Adı Kayıt Ücretleri (100% Burn) ──────
    BNS_FEES = {
        3: 100.0,   # 3 karakter (örn: abc.bct)
        4: 50.0,    # 4 karakter (örn: lock.bct)
        5: 10.0     # 5+ karakter (örn: trace.bct)
    }

    # ── Konsensüs & Blok Ödülü Dağılımı (3 Kademeli Model) ──
    REWARD_MINER_PERCENT = 50       # %50 PoW bloğunu bulan madenciye (Proposer)
    REWARD_VALIDATOR_PERCENT = 40   # %40 aktif doğrulayıcı düğüm havuzuna (Düğüm çalıştıran Validator Quorum)
    REWARD_OBSERVER_PERCENT = 10    # %10 pasif teminat kitleyen gözlemcilere (Observer Staking Pool)
    BASE_BLOCK_REWARD = 50.0        # Başlangıç blok ödülü

    # ── Sybil Koruması & Staking Kademeleri (Stake Limits) ───
    MIN_OBSERVER_STAKE = 100.0      # Pasif gözlemci staking alt limiti (Min 100 BCT)
    MAX_OBSERVER_STAKE = 100_000.0  # Pasif gözlemci staking üst limiti (Max 100.000 BCT)
    MIN_VALIDATOR_STAKE = 1000.0    # Aktif Validator Düğümü olmak için gereken min bakiye/stake
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
    _DEPRECATED_WBCT_CONTRACTS = {
        "0xa3c743113a41cfd0146917065d4578337bb77254",
        "0x5e5d957b240c9e4a51613f58c6c242b710519b41",
    }
    _env_wbct = os.environ.get("WBCT_CONTRACT_ADDRESS", "").strip()
    WBCT_CONTRACT_ADDRESS = (
        "0xCa6152Ae0E785F90ED65cd706B386E5B83D0EB28"
        if (not _env_wbct or _env_wbct.lower() in _DEPRECATED_WBCT_CONTRACTS)
        else _env_wbct
    )
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
        "https://bloctag.space,https://www.bloctag.space,https://locktrace.space,https://www.locktrace.space,https://spectacular-brioche-aafb73.netlify.app,http://localhost:3000,http://localhost:5000,http://127.0.0.1:5000"
    ).split(",")

    # ── Sunucu & Veritabanı ───────────────────────────
    DB_PATH = os.environ.get("BCT_DB_PATH", "blockchain.db")
    HOST = os.environ.get("BCT_HOST", "0.0.0.0")
    PORT = int(os.environ.get("BCT_PORT", "5000"))
    DEBUG = os.environ.get("BCT_DEBUG", "false").lower() == "true"
    DEV_MODE = os.environ.get("BCT_DEV_MODE", "false").lower() == "true"

    # ── Blockchain Mempool & Limitler ─────────────────
    MIN_TRANSACTION = 0.01          # Minimum transfer miktarı (dust-spam engelleme)
    MIN_TRANSFER_FEE = 0.001        # Minimum transfer işlem ücreti (sıfır-ücret sömürü koruması)
    MAX_TRANSACTION = 1_000_000    # Maksimum tek seferde transfer
    MAX_PENDING_TX = 5000          # Maksimum bekleyen işlem
    AUTO_MINE = True               # Otomatik madencilik

    # ── Cezalandırılmış / Yasaklı Zararlı Hesaplar (Slashing) ──
    SLASHED_MALICIOUS_VALIDATORS = [
        "BCT3a5f3ce88254c92f1daa43caa96c3bb0e2ca163b",
        "BCT35d240a88e37513fdd4f07e93363adb7f24c5b39",
        "BCTdc88fceb46881c318efa5e6ffc333eee931a8fbd",
        "BCTa482e0a97003f22f15afddb234cc8deb93bb1e0a",
        "BCT4a9207a5be60786264cc0653aba1a8568c91f5a0",
    ]

    # SEC-BNS: Reserved protocol namespaces barred from arbitrary public registration
    RESERVED_BNS_HANDLES = {
        "treasury", "genesis", "bridge", "vault", "admin", "system",
        "support", "official", "null", "burn", "validator", "security",
        "bct", "foundation"
    }

    # ── Loglama ───────────────────────────────────────
    LOG_LEVEL = os.environ.get("BCT_LOG_LEVEL", "INFO")
    LOG_FILE = os.environ.get("BCT_LOG_FILE", "logs/blockchain.log")
