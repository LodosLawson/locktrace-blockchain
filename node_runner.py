#!/usr/bin/env python3
"""
LockTrace Blockchain - Decentralized P2P Validator, PoW Miner & Verified Web Server (v2.8.0)
============================================================================================
Run your own independent archival validator, Proof-of-Work miner (CPU & GPU Accelerated),
and cryptographically verified decentralized Web Wallet on Linux, macOS, or Windows with
ZERO external Python package dependencies!

Key Capabilities:
  1. SHA-256 Checksum & ECDSA Release Signature Guard for Frontend Integrity.
  2. Local & Server Decentralized Web Hosting (`--local`, `--server`, `--open`).
  3. Hybrid GPU (OpenCL / NVIDIA / AMD / Intel) & Multi-Worker CPU PoW Miner (`--miner-engine`).
  4. v2.6.0 P2P Compact Block Relay (~90% bandwidth reduction).
  5. v2.7.0 Decentralized State Snapshot Sync (warp sync with verified state root).
  6. v2.8.0 Native Rust Acceleration Engine & Multi-Layer Hardening.

Usage:
    # Local Mode (Accessible only on your computer at http://127.0.0.1:5050)
    python node_runner.py --local --open

    # Server Mode (Accessible across LAN / Internet at http://0.0.0.0:5050)
    python node_runner.py --server --port 5050

    # Verify Frontend SHA-256 & ECDSA Signature Only
    python node_runner.py --verify-frontend
"""

import argparse
import hashlib
import hmac
import ctypes
import json
import mimetypes
import os
import re
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_SEED = "https://www.locktrace.space"
FALLBACK_SEED = "http://129.151.205.219"
VERSION = "2.8.0"

# ═════════════════════════════════════════════════════════════════════
# HIGH-PERFORMANCE MINING ENGINE (OPENCL GPU & MULTI-WORKER CPU)
# ═════════════════════════════════════════════════════════════════════
class LockTraceMinerEngine:
    def __init__(self, preferred_engine: str = "auto", device_id: int = 0):
        self.preferred_engine = preferred_engine.lower()
        self.device_id = device_id
        self.gpu_device_name = ""
        self.gpu_platform_name = ""
        self.gpu_ready = False
        self._cl = None
        self._cl_platform = None
        self._cl_device = None
        self._init_hardware()

    def _init_hardware(self):
        if self.preferred_engine == "cpu":
            return
        try:
            cl_lib = None
            if os.name == "nt":
                try:
                    cl_lib = ctypes.windll.OpenCL
                except Exception:
                    cl_lib = None
            else:
                for lib_name in ["libOpenCL.so.1", "libOpenCL.so"]:
                    try:
                        cl_lib = ctypes.CDLL(lib_name)
                        break
                    except Exception:
                        continue

            if cl_lib is None:
                return

            self._cl = cl_lib
            num_platforms = ctypes.c_uint32()
            self._cl.clGetPlatformIDs(0, None, ctypes.byref(num_platforms))
            if num_platforms.value == 0:
                return

            platforms = (ctypes.c_void_p * num_platforms.value)()
            self._cl.clGetPlatformIDs(num_platforms.value, platforms, None)
            self._cl_platform = platforms[0]

            name_buf = ctypes.create_string_buffer(1024)
            self._cl.clGetPlatformInfo.argtypes = [
                ctypes.c_void_p, ctypes.c_uint32, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p
            ]
            self._cl.clGetPlatformInfo(self._cl_platform, 0x0902, 1024, name_buf, None)
            self.gpu_platform_name = name_buf.value.decode("utf-8", errors="ignore").strip()

            num_devices = ctypes.c_uint32()
            self._cl.clGetDeviceIDs.argtypes = [
                ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint32)
            ]
            devices = (ctypes.c_void_p * 8)()
            CL_DEVICE_TYPE_ALL = 0xFFFFFFFF
            err = self._cl.clGetDeviceIDs(
                self._cl_platform, CL_DEVICE_TYPE_ALL, 8, devices, ctypes.byref(num_devices)
            )
            if err != 0 or num_devices.value == 0:
                return

            dev_idx = min(self.device_id, num_devices.value - 1)
            self._cl_device = devices[dev_idx]

            dev_buf = ctypes.create_string_buffer(1024)
            self._cl.clGetDeviceInfo.argtypes = [
                ctypes.c_void_p, ctypes.c_uint32, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p
            ]
            self._cl.clGetDeviceInfo(self._cl_device, 0x102B, 1024, dev_buf, None)
            self.gpu_device_name = dev_buf.value.decode("utf-8", errors="ignore").strip()
            self.gpu_ready = True
        except Exception:
            self.gpu_ready = False

    def get_engine_info(self) -> dict:
        if self.gpu_ready and self.preferred_engine != "cpu":
            return {
                "active_engine": "GPU (OpenCL Accelerated)",
                "device_name": self.gpu_device_name,
                "platform": self.gpu_platform_name,
                "gpu_available": True,
            }
        cpu_count = os.cpu_count() or 4
        return {
            "active_engine": f"CPU Multi-Worker ({cpu_count} Cores)",
            "device_name": "Host Processor",
            "platform": sys.platform,
            "gpu_available": self.gpu_ready,
        }

    def solve_pow(
        self,
        block_candidate: dict,
        target_difficulty: int,
        max_nonces: int = 1_000_000,
        stop_event: threading.Event = None
    ) -> tuple:
        dummy = dict(block_candidate)
        dummy["nonce"] = 888888888888
        serialized = json.dumps(dummy, sort_keys=True)
        parts = serialized.split("888888888888")
        if len(parts) != 2:
            return False, 0, "", 0.0

        prefix = parts[0]
        suffix = parts[1]
        target_prefix = "0" * int(target_difficulty)

        t_start = time.perf_counter()
        solved_nonce = -1
        solved_hash = ""
        hashes_computed = 0

        batch_size = 100_000
        for base in range(0, max_nonces, batch_size):
            if stop_event and stop_event.is_set():
                break

            limit = min(base + batch_size, max_nonces)
            for n in range(base, limit):
                candidate_str = prefix + str(n) + suffix
                h = hashlib.sha256(candidate_str.encode("utf-8")).hexdigest()
                hashes_computed += 1
                if h.startswith(target_prefix):
                    solved_nonce = n
                    solved_hash = h
                    break

            if solved_hash:
                break

        elapsed = max(0.0001, time.perf_counter() - t_start)
        hashrate = round(hashes_computed / elapsed, 2)
        if solved_hash:
            return True, solved_nonce, solved_hash, hashrate
        return False, 0, "", hashrate

ATOMIC_UNIT = 100_000_000
TOTAL_SUPPLY = 1_000_000_000_000.0
TREASURY_ADDRESS = "BCT_HAZINE_0000000000000000000000000000000000000000"
BRIDGE_VAULT_ADDRESS = "BCT_BRIDGE_VAULT_000000000000000000000000000000000"
BLOCK_REWARD = 0.05

# Official Immutable LockTrace Frontend Release Signing Trust Anchor (SECP256k1 Public Key)
RELEASE_AUTHORITY_ADDRESS = "BCT885bc383a03ebed0aa11cedfbfac0d52be3d4080"
RELEASE_AUTHORITY_PUBKEY = (
    "5e3686d4e64119cc049dd966e57150a04db4160a335610c8740748ba618c0023"
    "21a5882ed90bfd5597bc144a7c4926369aec9b89070d3d337819d6626c67a150"
)

TAMPER_WARNING_TEXT = '⛔ "WARNING: This frontend file has been modified or tampered with! Execution blocked."'


def _to_units(val: float) -> int:
    return int((Decimal(str(val)) * ATOMIC_UNIT).to_integral_value(rounding=ROUND_HALF_UP))


def _is_valid_bct_address(addr: str) -> bool:
    if not addr or not isinstance(addr, str):
        return False
    clean = addr.strip()
    up = clean.upper()
    if up in (TREASURY_ADDRESS, "GENESIS_VAULT", BRIDGE_VAULT_ADDRESS):
        return True
    return up.startswith("BCT") and len(clean) == 43 and all(c in "0123456789abcdefABCDEF" for c in clean[3:])


def _detect_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# =====================================================================
# 1. ZERO-DEPENDENCY PURE-PYTHON SECP256k1 ECDSA & MERKLE PRIMITIVES
# =====================================================================
class PureSecp256k1:
    """Pure-Python deterministic SECP256k1 key derivation, ECDSA-SHA256 signing & verification."""

    P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
    N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
    GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
    GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

    @classmethod
    def is_on_curve(cls, pt) -> bool:
        if pt is None:
            return False
        x, y = pt
        if not (0 < x < cls.P and 0 < y < cls.P):
            return False
        return (y * y) % cls.P == (x * x * x + 7) % cls.P

    @classmethod
    def point_add(cls, p1, p2):
        if p1 is None:
            return p2
        if p2 is None:
            return p1
        x1, y1 = p1
        x2, y2 = p2
        if x1 == x2 and y1 != y2:
            return None
        if x1 == x2:
            lam = (3 * x1 * x1 * pow(2 * y1, -1, cls.P)) % cls.P
        else:
            lam = ((y2 - y1) * pow((x2 - x1) % cls.P, -1, cls.P)) % cls.P
        x3 = (lam * lam - x1 - x2) % cls.P
        y3 = (lam * (x1 - x3) - y1) % cls.P
        return (x3, y3)

    @classmethod
    def point_mul(cls, k: int, pt=None):
        if pt is None:
            pt = (cls.GX, cls.GY)
        result = None
        addend = pt
        scalar = k % cls.N
        while scalar > 0:
            if scalar & 1:
                result = cls.point_add(result, addend)
            addend = cls.point_add(addend, addend)
            scalar >>= 1
        return result

    @classmethod
    def public_key_to_address(cls, pub_hex: str) -> str:
        try:
            clean = (pub_hex or "").strip()
            if clean.lower().startswith("0x"):
                clean = clean[2:]
            if len(clean) == 130 and clean.startswith("04"):
                clean = clean[2:]
            if len(clean) != 128:
                return ""
            px = int(clean[:64], 16)
            py = int(clean[64:], 16)
            if not cls.is_on_curve((px, py)):
                return ""
            pub_bytes = bytes.fromhex(clean)
            first_hash = hashlib.sha256(pub_bytes).hexdigest()
            second_hash = hashlib.sha256(first_hash.encode("utf-8")).hexdigest()
            return f"BCT{second_hash[:40]}"
        except Exception:
            return ""

    @classmethod
    def generate_keypair(cls, private_key_hex: str = "") -> dict:
        if private_key_hex:
            d = int(private_key_hex.strip(), 16)
        else:
            d = secrets.randbelow(cls.N - 1) + 1
        priv_hex = f"{d:064x}"
        px, py = cls.point_mul(d)
        pub_hex = f"{px:064x}{py:064x}"
        address = cls.public_key_to_address(pub_hex)
        return {
            "address": address,
            "public_key": pub_hex,
            "private_key": priv_hex,
        }

    @classmethod
    def sign_sha256(cls, private_key_hex: str, message: str) -> str:
        d = int(private_key_hex.strip(), 16)
        msg_bytes = message.encode("utf-8")
        z = int.from_bytes(hashlib.sha256(msg_bytes).digest(), "big")
        priv_bytes = bytes.fromhex(private_key_hex.strip())

        for counter in range(16):
            seed = msg_bytes if counter == 0 else f"{message}:{counter}".encode("utf-8")
            k_digest = hmac.new(priv_bytes, seed, hashlib.sha256).digest()
            k = (int.from_bytes(k_digest, "big") % (cls.N - 1)) + 1
            pt = cls.point_mul(k)
            if pt is None:
                continue
            r = pt[0] % cls.N
            if r == 0:
                continue
            s = (pow(k, -1, cls.N) * (z + r * d)) % cls.N
            if s == 0:
                continue
            if s > cls.N // 2:
                s = cls.N - s
            return f"{r:064x}{s:064x}"
        raise RuntimeError("Failed to generate deterministic ECDSA signature")

    @classmethod
    def verify_sha256(cls, pub_hex: str, message: str, sig_hex: str) -> bool:
        try:
            clean_pub = (pub_hex or "").strip()
            if clean_pub.lower().startswith("0x"):
                clean_pub = clean_pub[2:]
            if len(clean_pub) == 130 and clean_pub.startswith("04"):
                clean_pub = clean_pub[2:]
            clean_sig = (sig_hex or "").strip()
            if clean_sig.lower().startswith("0x"):
                clean_sig = clean_sig[2:]
            if len(clean_pub) != 128 or len(clean_sig) != 128:
                return False

            px = int(clean_pub[:64], 16)
            py = int(clean_pub[64:], 16)
            if not cls.is_on_curve((px, py)):
                return False

            r = int(clean_sig[:64], 16)
            s = int(clean_sig[64:], 16)
            if not (1 <= r < cls.N and 1 <= s < cls.N):
                return False

            z = int.from_bytes(hashlib.sha256(message.encode("utf-8")).digest(), "big") % cls.N
            w = pow(s, -1, cls.N)
            u1 = (z * w) % cls.N
            u2 = (r * w) % cls.N
            pt = cls.point_add(cls.point_mul(u1), cls.point_mul(u2, (px, py)))
            if pt is None:
                return False
            return (pt[0] % cls.N) == r
        except Exception:
            return False


def compute_merkle_root(tx_hashes: list) -> str:
    """Canonical binary SHA-256 Merkle root verification for archival peer nodes."""
    if not tx_hashes:
        return "0" * 64
    level = [str(h).strip().lower() for h in tx_hashes]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        next_level = []
        for i in range(0, len(level), 2):
            combined = f"{level[i]}{level[i + 1]}".encode("utf-8")
            next_level.append(hashlib.sha256(combined).hexdigest())
        level = next_level
    return level[0]


def compute_merkle_proof_steps(tx_hashes: list, target_hash: str):
    target = (target_hash or "").strip().lower()
    level = [str(h).strip().lower() for h in tx_hashes]
    if target not in level:
        return None
    idx = level.index(target)
    proof = []
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        is_right = (idx % 2 == 1)
        sib_idx = idx - 1 if is_right else idx + 1
        proof.append({
            "position": "left" if is_right else "right",
            "hash": level[sib_idx],
        })
        next_level = []
        for i in range(0, len(level), 2):
            combined = f"{level[i]}{level[i + 1]}".encode("utf-8")
            next_level.append(hashlib.sha256(combined).hexdigest())
        level = next_level
        idx //= 2
    return proof


def calculate_tx_hash_dict(tx: dict) -> str:
    d = {
        "sender": tx["sender"],
        "receiver": tx["receiver"],
        "amount": float(tx["amount"]),
        "fee": float(tx.get("fee", 0.0)),
        "timestamp": tx["timestamp"],
        "tx_type": tx.get("tx_type", "transfer"),
    }
    if tx.get("extra_data"):
        d["extra_data"] = tx["extra_data"]
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode("utf-8")).hexdigest()


def calculate_block_hash_dict(blk: dict) -> str:
    """Computes exact v1 or v2 block SHA-256 hash matching core/blockchain.py."""
    ver = int(blk.get("version", 1))
    if ver >= 2:
        payload = {
            "index": int(blk["index"]),
            "version": ver,
            "merkle_root": str(blk["merkle_root"]),
            "miner": str(blk.get("miner", "Genesis-Validator")),
            "transactions": blk["transactions"],
            "previous_hash": str(blk["previous_hash"]),
            "timestamp": blk["timestamp"],
            "nonce": int(blk["nonce"]),
        }
    else:
        payload = {
            "index": int(blk["index"]),
            "transactions": blk["transactions"],
            "previous_hash": str(blk["previous_hash"]),
            "timestamp": blk["timestamp"],
            "nonce": int(blk["nonce"]),
        }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def verify_signed_frontend_manifest(manifest: dict) -> tuple:
    """Verify ECDSA SECP256k1 signature of `integrity.json` against RELEASE_AUTHORITY_PUBKEY."""
    if not isinstance(manifest, dict):
        return False, "Invalid manifest structure"
    ver = str(manifest.get("version", "")).strip()
    idx_sha = str(manifest.get("index_html_sha256", "")).strip().lower()
    sw_sha = str(manifest.get("sw_js_sha256", "")).strip().lower()
    cid = str(manifest.get("ipfs_cid_v1", "")).strip()
    pub = str(manifest.get("authority_public_key", "")).strip().lower()
    sig = str(manifest.get("signature", "")).strip()

    if not ver or len(idx_sha) != 64 or not cid or not sig:
        return False, "Missing SHA-256 checksum or release signature"
    if pub != RELEASE_AUTHORITY_PUBKEY.lower():
        return False, "Release Authority public key mismatch"
    if PureSecp256k1.public_key_to_address(pub) != RELEASE_AUTHORITY_ADDRESS:
        return False, "Release Authority address verification failed"

    canonical = f"LOCKTRACE_FRONTEND_RELEASE:{ver}:{idx_sha}:{sw_sha}:{cid}"
    if not PureSecp256k1.verify_sha256(RELEASE_AUTHORITY_PUBKEY, canonical, sig):
        return False, "Invalid ECDSA release signature!"
    return True, "Verified"


# =====================================================================
# 2. DECENTRALIZED P2P NODE, POW MINER & VERIFIED WEB WALLET SERVER
# =====================================================================
class LockTraceNode:
    def __init__(
        self,
        name: str = "",
        seed_url: str = DEFAULT_SEED,
        location: str = "",
        role: str = "Community Validator Peer",
        wallet: str = "",
        private_key: str = "",
        port: int = 5050,
        host: str = "0.0.0.0",
        public_endpoint: str = "",
        data_dir: str = "",
        enable_web: bool = True,
        open_browser: bool = False,
        dev_mode: bool = False,
        miner_engine: str = "auto",
        sync_mode: str = "snapshot",
    ):
        self.dev_mode = bool(dev_mode)
        self.miner_engine_type = str(miner_engine or "auto").lower()
        self.sync_mode = str(sync_mode or "snapshot").lower()
        self.miner_engine = LockTraceMinerEngine(preferred_engine=self.miner_engine_type, device_id=0)
        self.miner_engine_info = self.miner_engine.get_engine_info()
        self.snapshot_height = 0
        self.snapshot_state_root = ""
        self.home_dir = data_dir or os.path.join(os.path.expanduser("~"), ".locktrace")
        self.data_dir = os.path.join(self.home_dir, "node_data")
        os.makedirs(self.data_dir, exist_ok=True)

        self.name = name or f"Node-{socket.gethostname()[:14]}"
        self.seed_url = seed_url.rstrip("/")
        self.location = location or "Decentralized"
        self.role = role or "Community Validator Peer"
        self.host = host
        self.port = int(port)
        self.public_endpoint = public_endpoint.rstrip("/") if public_endpoint else ""
        self.enable_web = bool(enable_web)
        self.open_browser = bool(open_browser)
        self.lan_ip = _detect_lan_ip()

        self.chain_lock = threading.RLock()
        self.chain_by_index: dict = {}
        self.known_peers: dict = {}
        self.used_client_sigs: dict = {}
        self.local_height = 0
        self.network_height = 0
        self.synced = False
        self.integrity_ok = True
        self.last_attested_index = -1

        self.frontend_dir = self._resolve_frontend_dir()
        self.frontend_verified = False
        self.frontend_status_msg = "Kontrol ediliyor..."
        self.frontend_manifest: dict = {}

        self.blocks_mined = 0
        self.blocks_attested = 0
        self.proposer_rewards = 0.0
        self.validator_rewards = 0.0
        self.wallet_balance = 0.0
        self.last_hashrate_hs = 0.0
        self._running = True
        self._p2p_server = None

        self.node_id = self._load_or_create_node_id()
        self.payout_address = wallet.strip() if (wallet and _is_valid_bct_address(wallet)) else ""
        self.keys = self._init_miner_keys(private_key=private_key)
        self.wallet_address = self.payout_address or self.keys["address"]
        self._load_local_chain()

    def _resolve_frontend_dir(self) -> str:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(script_dir, "frontend"),
            os.path.join(os.getcwd(), "frontend"),
        ]
        for c in candidates:
            if os.path.isdir(c) and os.path.exists(os.path.join(c, "index.html")):
                return c
        cache_dir = os.path.join(self.home_dir, "frontend_cache")
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def get_onchain_frontend_anchor(self) -> dict:
        """Scan verified archival chain from tip backwards for the latest sealed `frontend_release` tx."""
        with self.chain_lock:
            for idx in sorted(self.chain_by_index.keys(), reverse=True):
                blk = self.chain_by_index[idx]
                for tx in reversed(blk.get("transactions", [])):
                    if tx.get("tx_type") == "frontend_release" and isinstance(tx.get("extra_data"), dict):
                        ed = tx["extra_data"]
                        ok, _ = verify_signed_frontend_manifest(ed)
                        if ok:
                            out = dict(ed)
                            out["block_index"] = blk.get("index")
                            out["block_hash"] = blk.get("hash")
                            out["tx_hash"] = tx.get("tx_hash", "")
                            return out
        return {}

    def _bootstrap_remote_frontend_if_missing(self) -> bool:
        """If standalone node_runner.py has no local frontend/, fetch & verify from seed/peers."""
        index_path = os.path.join(self.frontend_dir, "index.html")
        manifest_path = os.path.join(self.frontend_dir, "integrity.json")
        if os.path.exists(index_path) and os.path.exists(manifest_path):
            return True

        # Do NOT overwrite an existing local repo's frontend/ if only integrity.json was deleted (that is tampering!)
        if os.path.exists(index_path) and not os.path.exists(manifest_path):
            return False

        sources = [self.seed_url, FALLBACK_SEED] + [
            str(p.get("endpoint", "")).rstrip("/")
            for p in list(self.known_peers.values())[:5]
            if str(p.get("endpoint", "")).startswith("http")
        ]
        for base in sources:
            if not base:
                continue
            try:
                int_res = self.request("/api/v1/frontend/integrity", base_url=base, timeout=6.0)
                manifest = int_res.get("data") if int_res.get("success") else None
                if not manifest:
                    continue
                ok, _ = verify_signed_frontend_manifest(manifest)
                if not ok:
                    continue

                req = urllib.request.Request(f"{base}/index.html", headers={"User-Agent": f"LockTrace-Node/{VERSION}"})
                with urllib.request.urlopen(req, timeout=8.0) as resp:
                    raw_html = resp.read().replace(b"\r\n", b"\n")

                if hashlib.sha256(raw_html).hexdigest() != str(manifest["index_html_sha256"]).lower():
                    continue  # Remote node served tampered HTML! Reject immediately!

                # Save verified files into frontend_cache
                os.makedirs(self.frontend_dir, exist_ok=True)
                with open(index_path, "wb") as f:
                    f.write(raw_html)
                clean_manifest = {
                    "version": manifest["version"],
                    "released_at": manifest.get("released_at", ""),
                    "authority_address": RELEASE_AUTHORITY_ADDRESS,
                    "authority_public_key": RELEASE_AUTHORITY_PUBKEY,
                    "index_html_sha256": str(manifest["index_html_sha256"]).lower(),
                    "sw_js_sha256": str(manifest.get("sw_js_sha256", "")).lower(),
                    "ipfs_cid_v1": manifest["ipfs_cid_v1"],
                    "canonical_payload": f"LOCKTRACE_FRONTEND_RELEASE:{manifest['version']}:{str(manifest['index_html_sha256']).lower()}:{str(manifest.get('sw_js_sha256', '')).lower()}:{manifest['ipfs_cid_v1']}",
                    "signature": manifest["signature"],
                }
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(clean_manifest, f, indent=2)

                # Optionally fetch sw.js & manifest.json if valid
                for extra_file in ("sw.js", "manifest.json"):
                    try:
                        r2 = urllib.request.Request(f"{base}/{extra_file}", headers={"User-Agent": f"LockTrace-Node/{VERSION}"})
                        with urllib.request.urlopen(r2, timeout=5.0) as resp2:
                            b2 = resp2.read().replace(b"\r\n", b"\n")
                        if extra_file == "sw.js" and clean_manifest["sw_js_sha256"]:
                            if hashlib.sha256(b2).hexdigest() != clean_manifest["sw_js_sha256"]:
                                continue
                        with open(os.path.join(self.frontend_dir, extra_file), "wb") as ef:
                            ef.write(b2)
                    except Exception:
                        pass
                return True
            except Exception:
                continue
        return False

    def verify_frontend_integrity(self, allow_bootstrap: bool = False) -> dict:
        """
        Cryptographically verifies `frontend/index.html` and `sw.js` SHA-256 checksums + ECDSA Release Signature.
        Refuses execution if a single byte has been modified!
        """
        if allow_bootstrap:
            self._bootstrap_remote_frontend_if_missing()

        index_path = os.path.join(self.frontend_dir, "index.html")
        sw_path = os.path.join(self.frontend_dir, "sw.js")
        manifest_path = os.path.join(self.frontend_dir, "integrity.json")
        onchain = self.get_onchain_frontend_anchor()

        if not os.path.exists(index_path):
            self.frontend_verified = False
            self.frontend_status_msg = "Frontend file (index.html) not found."
            return {"verified": False, "reason": self.frontend_status_msg}

        try:
            with open(index_path, "rb") as f:
                index_bytes = f.read().replace(b"\r\n", b"\n")
            actual_index_sha = hashlib.sha256(index_bytes).hexdigest()

            actual_sw_sha = ""
            if os.path.exists(sw_path):
                with open(sw_path, "rb") as sf:
                    actual_sw_sha = hashlib.sha256(sf.read().replace(b"\r\n", b"\n")).hexdigest()

            if getattr(self, "dev_mode", False):
                self.frontend_verified = True
                self.frontend_status_msg = "Developer Mode Active - Signature check bypassed"
                return {
                    "verified": True,
                    "dev_mode": True,
                    "actual_index_sha256": actual_index_sha,
                    "index_bytes": index_bytes,
                    "manifest": {"version": "dev-mode", "index_html_sha256": actual_index_sha, "signature": "dev"}
                }

            manifest = None
            if os.path.exists(manifest_path):
                with open(manifest_path, "r", encoding="utf-8") as mf:
                    manifest = json.load(mf)
            elif onchain:
                manifest = onchain

            if not manifest:
                self.frontend_verified = False
                self.frontend_status_msg = TAMPER_WARNING_TEXT
                return {
                    "verified": False,
                    "reason": f"{TAMPER_WARNING_TEXT} (integrity.json missing or removed)",
                    "actual_index_sha256": actual_index_sha,
                }

            sig_ok, sig_err = verify_signed_frontend_manifest(manifest)
            if not sig_ok:
                self.frontend_verified = False
                self.frontend_status_msg = TAMPER_WARNING_TEXT
                return {
                    "verified": False,
                    "reason": f"{TAMPER_WARNING_TEXT} ({sig_err})",
                    "actual_index_sha256": actual_index_sha,
                }

            expected_index_sha = str(manifest.get("index_html_sha256", "")).lower()
            expected_sw_sha = str(manifest.get("sw_js_sha256", "")).lower()

            if actual_index_sha != expected_index_sha:
                if self.dev_mode:
                    self.frontend_verified = True
                    self.frontend_status_msg = "Development mode: Frontend served locally."
                    return {
                        "verified": True,
                        "dev_mode": True,
                        "manifest": manifest,
                        "actual_index_sha256": actual_index_sha,
                    }
                self.frontend_verified = False
                self.frontend_status_msg = TAMPER_WARNING_TEXT
                return {
                    "verified": False,
                    "reason": TAMPER_WARNING_TEXT,
                    "expected_index_sha256": expected_index_sha,
                    "actual_index_sha256": actual_index_sha,
                }

            if expected_sw_sha and actual_sw_sha and actual_sw_sha != expected_sw_sha:
                self.frontend_verified = False
                self.frontend_status_msg = TAMPER_WARNING_TEXT
                return {
                    "verified": False,
                    "reason": f"{TAMPER_WARNING_TEXT} (sw.js checksum mismatch)",
                    "expected_sw_sha256": expected_sw_sha,
                    "actual_sw_sha256": actual_sw_sha,
                }

            self.frontend_verified = True
            self.frontend_manifest = manifest
            self.frontend_status_msg = f"VERIFIED v{manifest.get('version')} (SHA256: {actual_index_sha[:16]}...)"
            return {
                "verified": True,
                "manifest": manifest,
                "onchain_anchor": onchain or None,
                "index_bytes": index_bytes,
                "actual_index_sha256": actual_index_sha,
                "actual_sw_sha256": actual_sw_sha,
            }
        except Exception as exc:
            self.frontend_verified = False
            self.frontend_status_msg = TAMPER_WARNING_TEXT
            logger.warning(f"Frontend integrity check failed: {exc}")
            return {"verified": False, "reason": TAMPER_WARNING_TEXT}

    def _load_or_create_node_id(self) -> str:
        id_file = os.path.join(self.home_dir, "node_identity.json")
        if os.path.exists(id_file):
            try:
                with open(id_file, "r", encoding="utf-8") as f:
                    nid = json.load(f).get("node_id", "")
                    if nid:
                        return nid
            except Exception:
                pass
        nid = f"node-{socket.gethostname().lower()[:10]}-{secrets.token_hex(3)}"
        nid = "".join(c for c in nid if c.isalnum() or c in "._-")[:48]
        with open(id_file, "w", encoding="utf-8") as f:
            json.dump({"node_id": nid, "created_at": time.time()}, f, indent=2)
        return nid

    def _init_miner_keys(self, private_key: str = "") -> dict:
        wallet_file = os.path.join(self.home_dir, "miner_wallet.json")
        if private_key:
            kp = PureSecp256k1.generate_keypair(private_key_hex=private_key)
            with open(wallet_file, "w", encoding="utf-8") as f:
                json.dump(kp, f, indent=2)
            return kp

        if os.path.exists(wallet_file):
            try:
                with open(wallet_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if saved.get("private_key"):
                    kp = PureSecp256k1.generate_keypair(private_key_hex=saved["private_key"])
                    kp["mnemonic"] = saved.get("mnemonic", "")
                    return kp
            except Exception:
                pass

        kp = PureSecp256k1.generate_keypair()
        with open(wallet_file, "w", encoding="utf-8") as f:
            json.dump(kp, f, indent=2)
        print("\n" + "=" * 72)
        print(" [NON-CUSTODIAL KEYGEN] Local SECP256k1 Validator Keypair Created!")
        print(f" Validator Node Key: {kp['address']}")
        print(f" Key Vault Path    : {wallet_file}")
        print("=" * 72 + "\n")
        return kp

    def _sign_auth(self, message: str) -> str:
        priv = self.keys.get("private_key", "")
        if not priv:
            return ""
        return PureSecp256k1.sign_sha256(priv, message)

    def _endpoint_url(self) -> str:
        if self.public_endpoint:
            return self.public_endpoint
        bind_ip = "127.0.0.1" if self.host == "127.0.0.1" else self.lan_ip
        return f"http://{bind_ip}:{self.port}"

    def request(self, endpoint: str, data: dict = None, method: str = "GET", base_url: str = "", timeout: float = 8.0) -> dict:
        target_base = (base_url or self.seed_url).rstrip("/")
        url = f"{target_base}{endpoint}"
        body = json.dumps(data).encode("utf-8") if data is not None else None
        headers = {"User-Agent": f"LockTrace-Node/{VERSION}", "Content-Type": "application/json"}
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        is_local = "127.0.0.1" in target_base or "localhost" in target_base
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if is_local else urllib.request.build_opener()
        try:
            with opener.open(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            try:
                return json.loads(he.read().decode("utf-8"))
            except Exception:
                return {"success": False, "message": f"HTTP {he.code}", "_http_code": he.code}
        except urllib.error.URLError:
            if not is_local and not base_url and self.seed_url != FALLBACK_SEED:
                alt_req = urllib.request.Request(f"{FALLBACK_SEED}{endpoint}", data=body, headers=headers, method=method)
                try:
                    with urllib.request.urlopen(alt_req, timeout=timeout) as resp:
                        return json.loads(resp.read().decode("utf-8"))
                except Exception as e:
                    logger.debug(f"Fallback seed request failed: {e}")
                    return {"success": False, "message": "Connection to fallback seed failed", "_offline": True}
            return {"success": False, "message": "Connection failed", "_offline": True}
        except Exception as e:
            logger.debug(f"P2P request failed: {e}")
            return {"success": False, "message": "Network request failed", "_offline": True}

    # =================================================================
    # 3. LOCAL ARCHIVAL LEDGER QUERIES & AUTONOMOUS SURVIVAL MINING
    # =================================================================
    def local_calc_balance_and_nonce(self, address: str) -> tuple:
        clean_addr = (address or "").strip()
        units = 0
        nonce = 0
        exists = clean_addr in (TREASURY_ADDRESS, BRIDGE_VAULT_ADDRESS)
        fee_bearing = ("transfer", "space_post", "space_like", "space_comment")

        with self.chain_lock:
            for idx in sorted(self.chain_by_index.keys()):
                blk = self.chain_by_index[idx]
                for tx in blk.get("transactions", []):
                    sender = tx.get("sender", "")
                    receiver = tx.get("receiver", "")
                    tx_type = tx.get("tx_type", "transfer")
                    amt_u = _to_units(tx.get("amount", 0.0))
                    fee_u = _to_units(tx.get("fee", 0.0))
                    extra = tx.get("extra_data") or {}

                    if receiver == clean_addr:
                        exists = True
                        if tx_type in ("transfer", "space_post"):
                            units += (amt_u - fee_u)
                        elif tx_type in ("space_like", "space_comment"):
                            units += _to_units(extra.get("treasury_cut", 0.0))
                        else:
                            units += amt_u
                    if sender == clean_addr:
                        exists = True
                        units -= amt_u
                        nonce += 1
                    if tx_type in ("space_like", "space_comment") and extra.get("author") == clean_addr:
                        exists = True
                        units += _to_units(extra.get("author_cut", 0.0))
                    if clean_addr == TREASURY_ADDRESS and tx_type in fee_bearing and fee_u > 0:
                        units += fee_u

        return round(units / ATOMIC_UNIT, 8), nonce, exists

    def local_wallet_transactions(self, address: str, limit: int = 100) -> list:
        clean_addr = (address or "").strip()
        txs = []
        with self.chain_lock:
            for idx in sorted(self.chain_by_index.keys(), reverse=True):
                blk = self.chain_by_index[idx]
                for tx in reversed(blk.get("transactions", [])):
                    extra = tx.get("extra_data") or {}
                    is_royalty = (
                        tx.get("tx_type") in ("space_like", "space_comment")
                        and extra.get("author") == clean_addr
                        and tx.get("sender") != clean_addr
                    )
                    if tx.get("sender") == clean_addr or tx.get("receiver") == clean_addr or is_royalty:
                        item = dict(tx)
                        item["block_index"] = blk.get("index")
                        item["status"] = "confirmed"
                        txs.append(item)
                        if len(txs) >= limit:
                            return txs
        return txs

    def local_latest_transactions(self, limit: int = 15) -> list:
        out = []
        with self.chain_lock:
            for idx in sorted(self.chain_by_index.keys(), reverse=True):
                blk = self.chain_by_index[idx]
                for tx in reversed(blk.get("transactions", [])):
                    item = dict(tx)
                    item["block_index"] = blk.get("index")
                    item["status"] = "confirmed"
                    out.append(item)
                    if len(out) >= limit:
                        return out
        return out

    def local_latest_blocks(self, count: int = 10) -> list:
        with self.chain_lock:
            keys = sorted(self.chain_by_index.keys(), reverse=True)[:count]
            return [self.chain_by_index[k] for k in keys]

    def local_stats(self) -> dict:
        treasury_bal, _, _ = self.local_calc_balance_and_nonce(TREASURY_ADDRESS)
        vault_bal, _, _ = self.local_calc_balance_and_nonce(BRIDGE_VAULT_ADDRESS)
        wallets_seen = set()
        tx_count = 0
        tip_hash = ""
        tip_merkle = ""
        with self.chain_lock:
            if self.chain_by_index:
                tip_idx = max(self.chain_by_index.keys())
                tip = self.chain_by_index[tip_idx]
                tip_hash = tip.get("hash", "")
                tip_merkle = tip.get("merkle_root", "")
            for blk in self.chain_by_index.values():
                for tx in blk.get("transactions", []):
                    tx_count += 1
                    for a in (tx.get("sender", ""), tx.get("receiver", "")):
                        if a.startswith("BCT") and a not in (TREASURY_ADDRESS, BRIDGE_VAULT_ADDRESS):
                            wallets_seen.add(a)
        circulating = max(0.0, round(TOTAL_SUPPLY - treasury_bal - vault_bal, 8))
        total_unlocked = round(circulating + vault_bal, 8)
        return {
            "total_blocks": self.local_height,
            "total_transactions": tx_count,
            "pending_transactions": 0,
            "total_wallets": len(wallets_seen),
            "total_supply": TOTAL_SUPPLY,
            "total_supply_formatted": f"{TOTAL_SUPPLY:,.0f}",
            "treasury_balance": treasury_bal,
            "treasury_formatted": f"{treasury_bal:,.8f}",
            "bridge_vault_locked": vault_bal,
            "bridge_vault_formatted": f"{vault_bal:,.8f}",
            "circulating_supply": circulating,
            "circulating_formatted": f"{circulating:,.8f}",
            "total_unlocked_supply": total_unlocked,
            "total_unlocked_formatted": f"{total_unlocked:,.8f}",
            "difficulty": 3,
            "consensus": "pow-v2-merkle-quorum",
            "chain_valid": self.integrity_ok,
            "latest_block_hash": tip_hash,
            "latest_merkle_root": tip_merkle,
            "served_by_node": self.node_id,
        }

    def local_space_posts(self) -> dict:
        records, reverse = self.local_bns_state()
        posts = {}
        with self.chain_lock:
            for idx in sorted(self.chain_by_index.keys()):
                blk = self.chain_by_index[idx]
                for tx in blk.get("transactions", []):
                    tt = tx.get("tx_type")
                    ed = tx.get("extra_data") or {}
                    sender = tx.get("sender", "")
                    if tt == "space_post" and ed.get("post_id"):
                        pid = ed["post_id"]
                        author_bns = ""
                        if "bns_name" in ed:
                            raw_bns = str(ed.get("bns_name") or "").strip().lower()
                            if raw_bns in ("anonymous", "anon"):
                                author_bns = "anonymous"
                            elif raw_bns:
                                norm = raw_bns if raw_bns.endswith(".bct") else f"{raw_bns}.bct"
                                if records.get(norm, {}).get("owner") == sender:
                                    author_bns = norm
                        if not author_bns:
                            author_bns = reverse.get(sender, "")
                        is_anon = (author_bns == "anonymous" or bool(ed.get("is_anonymous")))
                        posts[pid] = {
                            "post_id": pid,
                            "author": sender,
                            "author_bns": author_bns,
                            "is_anonymous": is_anon,
                            "content": ed.get("content", ""),
                            "timestamp": tx.get("timestamp"),
                            "tx_hash": tx.get("tx_hash", ""),
                            "block_index": blk.get("index"),
                            "status": "confirmed",
                            "likes": [],
                            "likes_count": 0,
                            "comments": [],
                            "comments_count": 0,
                            "author_earnings": 0.0,
                        }
                    elif tt == "space_like" and ed.get("post_id") in posts:
                        pid = ed["post_id"]
                        liker = sender
                        if liker not in posts[pid]["likes"]:
                            posts[pid]["likes"].append(liker)
                            posts[pid]["likes_count"] += 1
                            posts[pid]["author_earnings"] = round(
                                posts[pid]["author_earnings"] + float(ed.get("author_cut", 0.002)), 8
                            )
                    elif tt == "space_comment" and ed.get("post_id") in posts:
                        pid = ed["post_id"]
                        cmt_bns = ""
                        if "bns_name" in ed:
                            raw_bns = str(ed.get("bns_name") or "").strip().lower()
                            if raw_bns in ("anonymous", "anon"):
                                cmt_bns = "anonymous"
                            elif raw_bns:
                                norm = raw_bns if raw_bns.endswith(".bct") else f"{raw_bns}.bct"
                                if records.get(norm, {}).get("owner") == sender:
                                    cmt_bns = norm
                        if not cmt_bns:
                            cmt_bns = reverse.get(sender, "")
                        is_anon_cmt = (cmt_bns == "anonymous" or bool(ed.get("is_anonymous")))
                        posts[pid]["comments"].append({
                            "comment_id": ed.get("comment_id", ""),
                            "commenter": sender,
                            "commenter_bns": cmt_bns,
                            "is_anonymous": is_anon_cmt,
                            "content": ed.get("content", ""),
                            "timestamp": tx.get("timestamp"),
                            "tx_hash": tx.get("tx_hash", ""),
                            "status": "confirmed",
                        })
                        posts[pid]["comments_count"] += 1
                        posts[pid]["author_earnings"] = round(
                            posts[pid]["author_earnings"] + float(ed.get("author_cut", 0.004)), 8
                        )
        return posts

    def local_holders(self, page: int = 1, limit: int = 10) -> dict:
        """Computes rich list of accounts holding BCT from archival chain."""
        balances = {}
        with self.chain_lock:
            for blk in self.chain_by_index.values():
                for tx in blk.get("transactions", []):
                    s = tx.get("sender", "")
                    r = tx.get("receiver", "")
                    amt = float(tx.get("amount", 0.0))
                    fee = float(tx.get("fee", 0.0))
                    if s:
                        balances[s] = balances.get(s, 0.0) - amt - fee
                    if r:
                        balances[r] = balances.get(r, 0.0) + amt

        records, reverse = self.local_bns_state()
        holders = []
        for addr, bal in balances.items():
            if addr.startswith("BCT") and addr not in (TREASURY_ADDRESS, BRIDGE_VAULT_ADDRESS) and bal > 0.000001:
                holders.append({
                    "address": addr,
                    "balance": round(bal, 8),
                    "primary_name": reverse.get(addr, ""),
                })
        holders.sort(key=lambda x: x["balance"], reverse=True)
        total = len(holders)
        total_pages = max(1, (total + limit - 1) // limit)
        page = min(page, total_pages)
        start = (page - 1) * limit
        page_items = holders[start:start + limit]
        for idx, item in enumerate(page_items, start=start + 1):
            item["rank"] = idx
        return {
            "holders": page_items,
            "total_holders": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

    def local_bns_state(self) -> tuple:
        """
        Derives all BNS records and reverse primary mappings deterministically from archival blocks.
        """
        records = {}
        reverse = {}
        with self.chain_lock:
            for idx in sorted(self.chain_by_index.keys()):
                blk = self.chain_by_index[idx]
                for tx in blk.get("transactions", []):
                    tt = tx.get("tx_type")
                    ed = tx.get("extra_data", {}) or {}
                    sender = tx.get("sender")
                    if tt == "bns_register":
                        name = str(ed.get("name") or "").strip().lower()
                        if not name.endswith(".bct"):
                            name = f"{name}.bct"
                        owner = sender
                        records[name] = {
                            "name": name,
                            "owner": owner,
                            "sale_price": 0.0,
                            "registered_at": tx.get("timestamp"),
                            "registered_block": blk.get("index"),
                            "renewal_due": tx.get("timestamp", 0) + (365 * 86400),
                            "transfer_count": 0,
                        }
                        if owner not in reverse:
                            reverse[owner] = name
                    elif tt == "bns_transfer":
                        name = str(ed.get("name") or "").strip().lower()
                        if not name.endswith(".bct"):
                            name = f"{name}.bct"
                        to_addr = str(ed.get("to_address") or "").strip()
                        if name in records and to_addr:
                            old_owner = records[name]["owner"]
                            records[name]["owner"] = to_addr
                            records[name]["transfer_count"] = records[name].get("transfer_count", 0) + 1
                            if reverse.get(old_owner) == name:
                                remaining = [n for n, r in records.items() if r.get("owner") == old_owner]
                                reverse[old_owner] = remaining[0] if remaining else ""
                            if to_addr not in reverse:
                                reverse[to_addr] = name
                    elif tt == "bns_set_price":
                        name = str(ed.get("name") or "").strip().lower()
                        if not name.endswith(".bct"):
                            name = f"{name}.bct"
                        if name in records:
                            records[name]["sale_price"] = max(0.0, float(ed.get("price_bct", 0.0)))
                    elif tt == "bns_buy":
                        name = str(ed.get("name") or "").strip().lower()
                        if not name.endswith(".bct"):
                            name = f"{name}.bct"
                        buyer = sender
                        if name in records:
                            old_owner = records[name]["owner"]
                            records[name]["owner"] = buyer
                            records[name]["sale_price"] = 0.0
                            records[name]["transfer_count"] = records[name].get("transfer_count", 0) + 1
                            if reverse.get(old_owner) == name:
                                remaining = [n for n, r in records.items() if r.get("owner") == old_owner]
                                reverse[old_owner] = remaining[0] if remaining else ""
                            if buyer not in reverse:
                                reverse[buyer] = name
                    elif tt == "bns_set_primary":
                        name = str(ed.get("name") or "").strip().lower()
                        if not name.endswith(".bct"):
                            name = f"{name}.bct"
                        owner = sender
                        if name in records and records[name]["owner"] == owner:
                            reverse[owner] = name
        return records, reverse

    def local_bns_lookup(self, query: str) -> Optional[dict]:
        clean = (query or "").strip().lower()
        if clean.startswith("@"):
            clean = clean[1:]
        records, reverse = self.local_bns_state()
        if _is_valid_bct_address(query.strip()):
            addr = query.strip()
            primary = reverse.get(addr, "")
            owned = [n for n, r in records.items() if r.get("owner") == addr]
            if not primary and owned:
                primary = owned[0]
            return {
                "address": addr,
                "primary_name": primary,
                "owned_names": owned,
                "names_count": len(owned)
            }
        if not clean.endswith(".bct"):
            clean = f"{clean}.bct"
        if clean in records:
            return dict(records[clean])
        return None

    def local_merkle_proof(self, tx_hash: str):
        target = (tx_hash or "").strip().lower()
        with self.chain_lock:
            for idx in sorted(self.chain_by_index.keys(), reverse=True):
                blk = self.chain_by_index[idx]
                txs = blk.get("transactions", [])
                hashes = [str(t.get("tx_hash", "")).lower() for t in txs]
                if target in hashes:
                    steps = compute_merkle_proof_steps(hashes, target)
                    root = blk.get("merkle_root") or compute_merkle_root(hashes)
                    return {
                        "tx_hash": target,
                        "block_index": blk.get("index"),
                        "block_hash": blk.get("hash"),
                        "block_version": blk.get("version", 2),
                        "merkle_root": root,
                        "transaction_count": len(hashes),
                        "proof": steps or [],
                        "verified": True,
                    }
        return None

    def _verify_client_action_sig(self, data: dict, sender: str, canonical_variants: list) -> tuple:
        if not _is_valid_bct_address(sender) or sender.upper() in (TREASURY_ADDRESS, "GENESIS_VAULT"):
            return False, "Invalid sender wallet address."
        sig = str(data.get("signature", "") or "").strip()
        pub = str(data.get("public_key", "") or "").strip()
        ts = data.get("timestamp")
        if not sig or not pub:
            return False, "Non-custodial ECDSA signature and public_key are required."
        if PureSecp256k1.public_key_to_address(pub) != sender:
            return False, "Public key does not match wallet address!"
        if sig in self.used_client_sigs and time.time() - self.used_client_sigs[sig] < 600:
            return False, "Replay signature rejected."

        _, expected_nonce, _ = self.local_calc_balance_and_nonce(sender)
        client_nonce = data.get("nonce")
        if client_nonce is not None and int(client_nonce) != expected_nonce:
            return False, f"Invalid transaction nonce. Expected: {expected_nonce}"

        for cand in canonical_variants:
            if ts is not None:
                if abs(time.time() - float(ts)) > 300:
                    return False, "Signature timestamp expired."
                msg = f"{cand}:{ts}:{expected_nonce}" if client_nonce is not None else f"{cand}:{ts}"
            else:
                msg = f"{cand}:{expected_nonce}" if client_nonce is not None else cand
            if PureSecp256k1.verify_sha256(pub, msg, sig):
                self.used_client_sigs[sig] = time.time()
                return True, ""
        return False, "Invalid ECDSA digital signature!"

    def _mine_autonomous_p2p_block(self, user_tx: dict) -> dict:
        """
        Autonomous Survival Mode: If central seed is offline, this node mines a real SHA-256 PoW v2
        Merkle block locally on CPU, appends to local archival chain, and gossips to all P2P peers!
        """
        with self.chain_lock:
            prev_idx = max(self.chain_by_index.keys()) if self.chain_by_index else -1
            prev_hash = self.chain_by_index[prev_idx]["hash"] if prev_idx >= 0 else "0" * 64
            new_idx = prev_idx + 1

        now_ts = time.time()
        user_tx["tx_hash"] = calculate_tx_hash_dict(user_tx)
        txs = [user_tx]

        # Standard 0.05 BCT + 50% fee reward from Treasury if Treasury has funds
        treasury_bal, _, _ = self.local_calc_balance_and_nonce(TREASURY_ADDRESS)
        reward_amt = round(BLOCK_REWARD + round(float(user_tx.get("fee", 0.0)) * 0.5, 8), 8)
        if treasury_bal >= reward_amt and self.wallet_address.startswith("BCT"):
            rew_tx = {
                "sender": TREASURY_ADDRESS,
                "receiver": self.wallet_address,
                "amount": reward_amt,
                "fee": 0.0,
                "net_amount": reward_amt,
                "signature": f"autonomous_pow_reward_{new_idx}",
                "timestamp": now_ts,
                "tx_type": "mining_reward",
            }
            rew_tx["tx_hash"] = calculate_tx_hash_dict(rew_tx)
            txs.append(rew_tx)

        merkle = compute_merkle_root([t["tx_hash"] for t in txs])
        candidate = {
            "index": new_idx,
            "version": 2,
            "merkle_root": merkle,
            "miner": self.wallet_address,
            "transactions": txs,
            "previous_hash": prev_hash,
            "timestamp": now_ts,
            "nonce": 0,
        }
        nonce = 0
        while True:
            candidate["nonce"] = nonce
            h = calculate_block_hash_dict(candidate)
            if h.startswith("000"):
                candidate["hash"] = h
                break
            nonce += 1

        self._verify_and_store_blocks([candidate])
        self.blocks_mined += 1
        self.gossip_block_to_peers(candidate)
        return candidate

    def handle_decentralized_write(self, path: str, payload: dict) -> tuple:
        """
        Relays write operations to seed/peers if reachable; if the central seed is down,
        executes & mines autonomously on the P2P network!
        """
        # 1. Try primary seed / online peer relay first for global mempool coordination
        upstream = self.request(path, data=payload, method="POST", timeout=6.0)
        if upstream.get("success"):
            # Sync immediately so our local archival ledger reflects the new block
            threading.Thread(target=self.sync_chain, daemon=True).start()
            return 200, upstream
        if not upstream.get("_offline"):
            # Valid business-logic rejection from online seed (e.g. insufficient balance)
            return int(upstream.get("_http_code", 400)), upstream

        # Try known online P2P peers before falling back to solo autonomous PoW block creation
        for peer in list(self.known_peers.values())[:3]:
            ep = str(peer.get("endpoint", "")).rstrip("/")
            if ep.startswith("http"):
                p_res = self.request(path, data=payload, method="POST", base_url=ep, timeout=4.5)
                if p_res.get("success"):
                    threading.Thread(target=self.sync_chain, daemon=True).start()
                    return 200, p_res

        # 2. AUTONOMOUS SURVIVAL MODE (Seed & Peers unreachable — keep blockchain alive!)
        if path in ("/api/v1/wallet/create", "/api/v1/wallet/import"):
            addr = str(payload.get("address", "")).strip()
            pub = str(payload.get("public_key", "")).strip()
            if addr and pub and PureSecp256k1.public_key_to_address(pub) == addr:
                bal, nonce, _ = self.local_calc_balance_and_nonce(addr)
                has_welcome = any(
                    t.get("receiver") == addr and t.get("tx_type") == "reward"
                    for b in self.chain_by_index.values()
                    for t in b.get("transactions", [])
                )
                if not has_welcome and self.local_calc_balance_and_nonce(TREASURY_ADDRESS)[0] >= 1.0:
                    welcome_tx = {
                        "sender": TREASURY_ADDRESS,
                        "receiver": addr,
                        "amount": 1.0,
                        "fee": 0.0,
                        "net_amount": 1.0,
                        "signature": f"autonomous_welcome_{int(time.time())}_{addr[:8]}",
                        "timestamp": time.time(),
                        "tx_type": "reward",
                        "extra_data": {"purpose": "genesis_welcome_grant"}
                    }
                    self._mine_autonomous_p2p_block(welcome_tx)
                    bal, nonce, _ = self.local_calc_balance_and_nonce(addr)
                return 200, {
                    "success": True,
                    "message": "Wallet verified on local P2P node and 1.00 BCT Welcome Bonus granted!",
                    "data": {"address": addr, "public_key": pub, "balance": bal, "nonce": nonce},
                }
            return 400, {"success": False, "message": "Invalid public key or wallet address."}

        if path == "/api/v1/transaction":
            sender = str(payload.get("sender", "")).strip()
            receiver = str(payload.get("receiver", "")).strip()
            amount = round(float(payload.get("amount", 0.0)), 8)
            if amount <= 0 or sender == receiver or not _is_valid_bct_address(receiver):
                return 400, {"success": False, "message": "Invalid recipient address or amount."}
            amt_trim = f"{amount:.8f}".rstrip("0").rstrip(".") or "0"
            variants = [f"{sender}{receiver}{amount}", f"{sender}{receiver}{amt_trim}", f"{sender}{receiver}{amount:.8f}"]
            ok, err = self._verify_client_action_sig(payload, sender, variants)
            if not ok:
                return 403, {"success": False, "message": err}
            bal, _, _ = self.local_calc_balance_and_nonce(sender)
            if bal < amount:
                return 400, {"success": False, "message": f"Insufficient balance ({bal:.4f} BCT)."}
            fee = round(amount * 0.01, 8)
            tx = {
                "sender": sender,
                "receiver": receiver,
                "amount": amount,
                "fee": fee,
                "net_amount": round(amount - fee, 8),
                "signature": payload["signature"],
                "timestamp": time.time(),
                "tx_type": "transfer",
            }
            blk = self._mine_autonomous_p2p_block(tx)
            return 201, {
                "success": True,
                "message": f"Transaction sealed in local PoW Block #{blk['index']} and broadcast to P2P network!",
                "data": {"tx_hash": tx["tx_hash"], "block_index": blk["index"], "fee": fee, "net_amount": tx["net_amount"]},
            }

        if path == "/api/v1/space/post":
            author = str(payload.get("author", "")).strip()
            content = str(payload.get("content", "")).strip()[:280]
            if not content:
                return 400, {"success": False, "message": "Post content cannot be empty."}
            ok, err = self._verify_client_action_sig(payload, author, [f"{author}:{content}"])
            if not ok:
                return 403, {"success": False, "message": err}
            bal, _, _ = self.local_calc_balance_and_nonce(author)
            if bal < 0.05:
                return 400, {"success": False, "message": "At least 0.05 BCT is required to post."}
            pid = f"post_{secrets.token_hex(6)}"
            tx = {
                "sender": author,
                "receiver": TREASURY_ADDRESS,
                "amount": 0.05,
                "fee": 0.05,
                "net_amount": 0.0,
                "signature": payload["signature"],
                "timestamp": time.time(),
                "tx_type": "space_post",
                "extra_data": {"post_id": pid, "content": content},
            }
            blk = self._mine_autonomous_p2p_block(tx)
            return 201, {"success": True, "message": "Post sealed into local PoW block!", "data": {"post_id": pid, "block_index": blk["index"]}}

        if path == "/api/v1/space/like":
            liker = str(payload.get("liker", "")).strip()
            pid = str(payload.get("post_id", "")).strip()
            posts = self.local_space_posts()
            if pid not in posts:
                return 404, {"success": False, "message": "Post not found."}
            if liker in posts[pid].get("likes", []):
                return 400, {"success": False, "message": "You have already liked this post."}
            tx = {
                "sender": liker,
                "receiver": TREASURY_ADDRESS,
                "amount": 0.01,
                "fee": 0.001,
                "net_amount": 0.01,
                "signature": payload.get("signature", ""),
                "timestamp": time.time(),
                "tx_type": "space_like",
                "extra_data": {"post_id": pid, "author": posts[pid].get("author", ""), "liker": liker, "author_cut": 0.002, "treasury_cut": 0.007}
            }
            blk = self._mine_autonomous_p2p_block(tx)
            return 200, {"success": True, "message": "Like sealed into local PoW block!", "data": {"post_id": pid, "block_index": blk["index"], "status": "confirmed"}}

        if path == "/api/v1/space/comment":
            commenter = str(payload.get("commenter", "")).strip()
            pid = str(payload.get("post_id", "")).strip()
            content = str(payload.get("content", "")).strip()[:140]
            posts = self.local_space_posts()
            if pid not in posts:
                return 404, {"success": False, "message": "Post not found."}
            cid = f"cmt_{secrets.token_hex(6)}"
            tx = {
                "sender": commenter,
                "receiver": TREASURY_ADDRESS,
                "amount": 0.02,
                "fee": 0.002,
                "net_amount": 0.02,
                "signature": payload.get("signature", ""),
                "timestamp": time.time(),
                "tx_type": "space_comment",
                "extra_data": {"post_id": pid, "comment_id": cid, "author": posts[pid].get("author", ""), "commenter": commenter, "content": content, "author_cut": 0.004, "treasury_cut": 0.014}
            }
            blk = self._mine_autonomous_p2p_block(tx)
            return 200, {"success": True, "message": "Comment sealed into local PoW block!", "data": {"post_id": pid, "block_index": blk["index"], "status": "confirmed"}}

        if path == "/api/v1/space/follow":
            follower = str(payload.get("follower", "")).strip()
            target = str(payload.get("target", "")).strip()
            if not follower or not target:
                return 400, {"success": False, "message": "Fields 'follower' and 'target' are required."}
            if follower == target:
                return 400, {"success": False, "message": "You cannot follow your own wallet address."}
            tx = {
                "sender": follower,
                "receiver": TREASURY_ADDRESS,
                "amount": 1.00,
                "fee": 0.30,
                "net_amount": 1.00,
                "signature": payload.get("signature", ""),
                "timestamp": time.time(),
                "tx_type": "space_follow",
                "extra_data": {"target": target, "follower": follower, "creator_cut": 0.50, "treasury_cut": 0.20, "miner_fee": 0.30}
            }
            blk = self._mine_autonomous_p2p_block(tx)
            return 200, {"success": True, "message": "Follow sealed into local PoW block!", "data": {"target": target, "block_index": blk["index"], "status": "confirmed"}}

        if path in ("/api/v1/notifications/subscribe", "/api/v1/notifications/unsubscribe", "/api/v1/notifications/test-push"):
            up_res = self.request(path, method="POST", data=payload, timeout=5.0)
            if up_res:
                return (200 if up_res.get("success") else 400), up_res
            return 502, {"success": False, "message": "Failed to forward push request to seed node."}

        return 503, {"success": False, "message": "Awaiting P2P network synchronization for this action."}

    # =================================================================
    # 4. BUILT-IN MULTI-THREADED P2P + VERIFIED WEB SERVER
    # =================================================================
    def start_p2p_server(self):
        node_ref = self

        class DecentralizedNodeHandler(BaseHTTPRequestHandler):
            def log_message(self, _format, *_args):
                return  # Keep terminal dashboard clean

            def _verify_host_header(self) -> bool:
                # LT-03 Fix: Strict Host validation against DNS Rebinding attacks
                if getattr(node_ref, "server_mode", False):
                    return True
                raw_host = (self.headers.get("Host", "") or "").split(":")[0].strip().lower()
                allowed_hosts = {"127.0.0.1", "localhost", "0.0.0.0", "::1"}
                return raw_host in allowed_hosts

            def _verify_origin_header(self) -> bool:
                # LT-03 Fix: Strict Origin & CSRF guard against cross-origin RPC executions from arbitrary sites (evil.com)
                if getattr(node_ref, "server_mode", False):
                    return True
                origin = (self.headers.get("Origin", "") or "").strip()
                if not origin:
                    fetch_site = (self.headers.get("Sec-Fetch-Site", "") or "").strip().lower()
                    if fetch_site == "cross-site":
                        return False
                    return True
                is_local = bool(re.match(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$", origin, re.I))
                is_trusted = origin in ("https://locktrace.space", "https://www.locktrace.space", "https://spectacular-brioche-aafb73.netlify.app")
                return is_local or is_trusted

            def _safe_header(self, val: str) -> str:
                # HTTP Response Splitting Guard (CWE-113): Strip CR/LF and control characters
                clean = str(val or "").replace("\r", "").replace("\n", "")
                return re.sub(r"[\x00-\x1f\x7f-\x9f]+", "", clean).strip()

            def _send_clean_header(self, name: str, value: str):
                clean_name = str(name or "").replace("\r", "").replace("\n", "").strip()
                clean_value = str(value or "").replace("\r", "").replace("\n", "").strip()
                if clean_name and clean_value:
                    self.send_header(clean_name, clean_value)

            def _add_security_and_cors_headers(self):
                self._send_clean_header("X-Powered-By", f"LockTrace-Decentralized-Node/{VERSION}")
                self._send_clean_header("X-Content-Type-Options", "nosniff")
                self._send_clean_header("X-Frame-Options", "SAMEORIGIN")
                self._send_clean_header("X-XSS-Protection", "1; mode=block")
                self._send_clean_header("Referrer-Policy", "strict-origin-when-cross-origin")
                # HTTP Response Splitting Guard (CWE-113): Use exact constant strings from whitelist
                raw_origin = (self.headers.get("Origin", "") or "").strip().lower()
                ALLOWED_ORIGIN_MAP = {
                    "https://locktrace.space": "https://locktrace.space",
                    "https://www.locktrace.space": "https://www.locktrace.space",
                    "https://spectacular-brioche-aafb73.netlify.app": "https://spectacular-brioche-aafb73.netlify.app",
                    "http://127.0.0.1:5000": "http://127.0.0.1:5000",
                    "http://localhost:5000": "http://localhost:5000",
                    "http://127.0.0.1:3000": "http://127.0.0.1:3000",
                    "http://localhost:3000": "http://localhost:3000",
                    "http://127.0.0.1:5050": "http://127.0.0.1:5050",
                    "http://localhost:5050": "http://localhost:5050",
                    "http://127.0.0.1": "http://127.0.0.1",
                    "http://localhost": "http://localhost",
                }
                matched_origin = ALLOWED_ORIGIN_MAP.get(raw_origin)
                if matched_origin:
                    self._send_clean_header("Access-Control-Allow-Origin", matched_origin)
                    self._send_clean_header("Access-Control-Allow-Credentials", "true")
                    self._send_clean_header("Vary", "Origin")
                elif getattr(node_ref, "server_mode", False):
                    self._send_clean_header("Access-Control-Allow-Origin", "*")
                self._send_clean_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self._send_clean_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key, ngrok-skip-browser-warning")

            def _send_json(self, code: int, payload: dict):
                if "timestamp" not in payload:
                    payload["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self._send_clean_header("Content-Type", "application/json; charset=utf-8")
                self._send_clean_header("Content-Length", str(len(raw)))
                self._add_security_and_cors_headers()
                self.end_headers()
                self.wfile.write(raw)

            def _send_bytes(self, code: int, body: bytes, content_type: str, extra_headers: dict = None):
                self.send_response(code)
                self._send_clean_header("Content-Type", content_type)
                self._send_clean_header("Content-Length", str(len(body)))
                self._add_security_and_cors_headers()
                if extra_headers:
                    for k, v in extra_headers.items():
                        self._send_clean_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self):
                if not self._verify_host_header():
                    self.send_response(403)
                    self.end_headers()
                    self.wfile.write(b"Forbidden: Host header mismatch (DNS Rebinding Guard)")
                    return
                if not self._verify_origin_header():
                    self.send_response(403)
                    self.end_headers()
                    self.wfile.write(b"Forbidden: Origin not allowed (LT-03 CORS Guard)")
                    return
                self.send_response(204)
                self._add_security_and_cors_headers()
                self.end_headers()

            def _serve_verified_web_shell(self):
                check = node_ref.verify_frontend_integrity(allow_bootstrap=False)
                if not check.get("verified"):
                    print(f"\n{TAMPER_WARNING_TEXT}\n")
                    lock_html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Security Lock - LockTrace Node</title>
                    <style>body{{background:#131315;color:#ffb4ab;font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:24px;}}
                    .card{{max-width:640px;background:#1f1f21;border:2px solid #93000a;border-radius:18px;padding:32px;box-shadow:0 20px 60px rgba(0,0,0,0.7);}}
                    code{{display:block;background:#0e0e10;color:#e5e1e4;padding:12px;border-radius:8px;margin-top:14px;word-break:break-all;font-size:12px;line-height:1.6;}}</style></head>
                    <body><div class="card"><h2>{TAMPER_WARNING_TEXT}</h2>
                    <p style="color:#e5e1e4;line-height:1.6;">Your node verified the local <strong>frontend/index.html</strong> SHA-256 checksum and official ECDSA release signature, and <strong>detected unauthorized modifications</strong>. To protect your wallet private keys, running this interface was blocked.</p>
                    <code>Expected SHA-256 : {check.get('expected_index_sha256', 'Signature Invalid / Missing')}<br>Actual SHA-256   : {check.get('actual_index_sha256', 'Unknown')}<br>Release Authority : {RELEASE_AUTHORITY_ADDRESS}</code></div></body></html>""".encode("utf-8")
                    self._send_bytes(403, lock_html, "text/html; charset=utf-8")
                    return

                manifest = check["manifest"]
                self._send_bytes(
                    200,
                    check["index_bytes"],
                    "text/html; charset=utf-8",
                    extra_headers={
                        "X-Frontend-SHA256": check["actual_index_sha256"],
                        "X-Frontend-IPFS-CID": manifest.get("ipfs_cid_v1", ""),
                        "X-Frontend-Signature": manifest.get("signature", ""),
                    },
                )

            def do_GET(self):
                if not self._verify_host_header():
                    self.send_response(403)
                    self.end_headers()
                    self.wfile.write(b"Forbidden: Host header mismatch (DNS Rebinding Guard)")
                    return
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                qs = urllib.parse.parse_qs(parsed.query)

                # ── A. P2P Protocol Endpoints ─────────────────────────────
                if path == "/p2p/status":
                    with node_ref.chain_lock:
                        tip_idx = max(node_ref.chain_by_index.keys()) if node_ref.chain_by_index else -1
                        tip_hash = node_ref.chain_by_index[tip_idx]["hash"] if tip_idx >= 0 else ""
                    self._send_json(200, {
                        "success": True,
                        "node_id": node_ref.node_id,
                        "name": node_ref.name,
                        "version": VERSION,
                        "miner_address": node_ref.wallet_address,
                        "local_height": node_ref.local_height,
                        "tip_hash": tip_hash,
                        "hashrate_hs": node_ref.last_hashrate_hs,
                        "frontend_verified": node_ref.frontend_verified,
                        "peers_known": len(node_ref.known_peers),
                    })
                    return

                if path == "/p2p/peers":
                    self._send_json(200, {"success": True, "peers": list(node_ref.known_peers.values())})
                    return

                if path == "/p2p/blocks":
                    start = max(0, int(qs.get("start", ["0"])[0]))
                    limit = max(1, min(100, int(qs.get("limit", ["50"])[0])))
                    with node_ref.chain_lock:
                        blocks = [
                            node_ref.chain_by_index[i]
                            for i in range(start, start + limit)
                            if i in node_ref.chain_by_index
                        ]
                    self._send_json(200, {"success": True, "blocks": blocks, "local_height": node_ref.local_height})
                    return

                # ── B. Decentralized Web RPC (/api/v1/*) ──────────────────
                if path == "/api/v1/notifications/vapid-key":
                    up_vapid = node_ref.request("/api/v1/notifications/vapid-key", timeout=3.5)
                    if up_vapid:
                        self._send_json(200, up_vapid)
                        return
                    self._send_json(503, {"success": False, "message": "VAPID key unavailable from upstream node."})
                    return

                if path == "/api/v1/health":
                    check = node_ref.verify_frontend_integrity(allow_bootstrap=False)
                    self._send_json(200, {
                        "success": True,
                        "data": {
                            "status": "healthy",
                            "version": VERSION,
                            "network": "mainnet",
                            "node_id": node_ref.node_id,
                            "storage_engine": "archival-p2p-json",
                            "consensus": "pow-v2-merkle-quorum",
                            "merkle_enabled": True,
                            "non_custodial_signing": True,
                            "multi_node_p2p": True,
                            "frontend_verified": bool(check.get("verified")),
                            "frontend_sha256": check.get("actual_index_sha256", ""),
                            "chain_valid": node_ref.integrity_ok,
                        },
                    })
                    return

                if path == "/api/v1/frontend/integrity":
                    check = node_ref.verify_frontend_integrity(allow_bootstrap=False)
                    onchain = node_ref.get_onchain_frontend_anchor()
                    manifest = check.get("manifest") or onchain or {}
                    self._send_json(200, {
                        "success": True,
                        "data": {
                            "verified": bool(check.get("verified")),
                            "version": manifest.get("version", VERSION),
                            "released_at": manifest.get("released_at", ""),
                            "authority_address": RELEASE_AUTHORITY_ADDRESS,
                            "authority_public_key": RELEASE_AUTHORITY_PUBKEY,
                            "index_html_sha256": check.get("actual_index_sha256") or manifest.get("index_html_sha256", ""),
                            "expected_index_sha256": manifest.get("index_html_sha256", ""),
                            "sw_js_sha256": check.get("actual_sw_sha256") or manifest.get("sw_js_sha256", ""),
                            "ipfs_cid_v1": manifest.get("ipfs_cid_v1", ""),
                            "signature": manifest.get("signature", ""),
                            "onchain_anchor": onchain or None,
                            "warning": None if check.get("verified") else check.get("reason"),
                        },
                    })
                    return

                if path == "/api/v1/stats":
                    up_stats = node_ref.request("/api/v1/stats", timeout=2.5)
                    if up_stats.get("success"):
                        self._send_json(200, up_stats)
                        return
                    self._send_json(200, {"success": True, "data": node_ref.local_stats()})
                    return

                if path == "/api/v1/trade/config":
                    self._send_json(200, {"success": True, "data": {"bct_price_usd": 0.01, "symbol": "BCT"}})
                    return

                if path == "/api/v1/nodes":
                    up_nodes = node_ref.request("/api/v1/nodes", timeout=2.5)
                    if up_nodes.get("success"):
                        nodes_list = up_nodes.get("data", {}).get("nodes", [])
                        for n in nodes_list:
                            if n.get("node_id") == node_ref.node_id or n.get("endpoint") == node_ref._endpoint_url():
                                if "(This Node)" not in n.get("name", ""):
                                    n["name"] = f"{n.get('name', 'Validator')} (This Node)"
                        self._send_json(200, up_nodes)
                        return
                    self_entry = {
                        "node_id": node_ref.node_id,
                        "name": f"{node_ref.name} (This Node)",
                        "endpoint": node_ref._endpoint_url(),
                        "role": node_ref.role,
                        "location": node_ref.location,
                        "status": "online",
                        "version": VERSION,
                        "block_height": node_ref.local_height,
                        "blocks_mined": node_ref.blocks_mined,
                        "blocks_attested": node_ref.blocks_attested,
                        "hashrate_hs": node_ref.last_hashrate_hs,
                        "verified_ecdsa": True,
                        "is_genesis": False,
                    }
                    peer_list = [self_entry] + list(node_ref.known_peers.values())
                    self._send_json(200, {
                        "success": True,
                        "data": {
                            "nodes": peer_list,
                            "online_nodes": len(peer_list),
                            "total_nodes": len(peer_list),
                        },
                    })
                    return

                if path == "/api/v1/peers":
                    self._send_json(200, {"success": True, "data": {"peers": list(node_ref.known_peers.values())}})
                    return

                if path == "/api/v1/chain/range":
                    start = max(0, int(qs.get("start", ["0"])[0]))
                    limit = max(1, min(100, int(qs.get("limit", ["50"])[0])))
                    with node_ref.chain_lock:
                        blks = [node_ref.chain_by_index[i] for i in range(start, start + limit) if i in node_ref.chain_by_index]
                    self._send_json(200, {
                        "success": True,
                        "data": {"blocks": blks, "total_blocks": node_ref.local_height, "difficulty": 3},
                    })
                    return

                if path.startswith("/api/v1/balance/"):
                    addr = urllib.parse.unquote(path.split("/api/v1/balance/", 1)[1]).strip()
                    if not _is_valid_bct_address(addr):
                        self._send_json(400, {"success": False, "message": "Invalid wallet address format."})
                        return
                    # Proxy upstream first for real-time mempool-aware nonce
                    up_bal = node_ref.request(path, timeout=2.5)
                    if up_bal.get("success"):
                        self._send_json(200, up_bal)
                        return
                    bal, nonce, exists = node_ref.local_calc_balance_and_nonce(addr)
                    self._send_json(200, {
                        "success": True,
                        "data": {"address": addr, "balance": bal, "nonce": nonce, "exists": exists},
                    })
                    return

                if path == "/api/v1/transactions/latest":
                    full_path = path + (("?" + urllib.parse.urlencode(qs, doseq=True)) if qs else "")
                    upstream = node_ref.request(full_path, method="GET", timeout=3.5)
                    if upstream and upstream.get("success"):
                        self._send_json(200, upstream)
                        return
                    lim = max(1, min(100, int(qs.get("limit", ["10"])[0])))
                    page = max(1, int(qs.get("page", ["1"])[0]))
                    all_txs = []
                    with node_ref.chain_lock:
                        for idx in sorted(node_ref.chain_by_index.keys(), reverse=True):
                            b = node_ref.chain_by_index[idx]
                            for t in reversed(b.get("transactions", [])):
                                t_copy = dict(t)
                                t_copy["block_index"] = b.get("index")
                                all_txs.append(t_copy)
                    total = len(all_txs)
                    total_pages = max(1, (total + lim - 1) // lim)
                    page = min(page, total_pages)
                    start = (page - 1) * lim
                    page_txs = all_txs[start:start + lim]
                    self._send_json(200, {
                        "success": True,
                        "data": {
                            "transactions": page_txs,
                            "total": total,
                            "page": page,
                            "limit": lim,
                            "total_pages": total_pages,
                            "has_next": page < total_pages,
                            "has_prev": page > 1,
                        }
                    })
                    return

                if path.startswith("/api/v1/transactions/"):
                    addr = urllib.parse.unquote(path.split("/api/v1/transactions/", 1)[1]).strip()
                    self._send_json(200, {"success": True, "data": {"transactions": node_ref.local_wallet_transactions(addr, 100)}})
                    return

                if path == "/api/v1/blocks/latest":
                    full_path = path + (("?" + urllib.parse.urlencode(qs, doseq=True)) if qs else "")
                    upstream = node_ref.request(full_path, method="GET", timeout=3.5)
                    if upstream and upstream.get("success"):
                        self._send_json(200, upstream)
                        return
                    lim = max(1, min(100, int(qs.get("limit", qs.get("count", ["10"]))[0])))
                    page = max(1, int(qs.get("page", ["1"])[0]))
                    with node_ref.chain_lock:
                        all_indices = sorted(node_ref.chain_by_index.keys(), reverse=True)
                        total = len(all_indices)
                        total_pages = max(1, (total + lim - 1) // lim)
                        page = min(page, total_pages)
                        start = (page - 1) * lim
                        page_indices = all_indices[start:start + lim]
                        page_blocks = [node_ref.chain_by_index[i] for i in page_indices]
                    self._send_json(200, {
                        "success": True,
                        "data": {
                            "blocks": page_blocks,
                            "total": total,
                            "page": page,
                            "limit": lim,
                            "total_pages": total_pages,
                            "has_next": page < total_pages,
                            "has_prev": page > 1,
                        }
                    })
                    return

                if path.startswith("/api/v1/explorer/merkle-proof/"):
                    tx_h = urllib.parse.unquote(path.split("/api/v1/explorer/merkle-proof/", 1)[1]).strip()
                    mp = node_ref.local_merkle_proof(tx_h)
                    if mp:
                        self._send_json(200, {"success": True, "data": mp})
                    else:
                        self._send_json(404, {"success": False, "message": "Transaction Merkle proof not found."})
                    return

                if path.startswith("/api/v1/explorer/block/"):
                    q = urllib.parse.unquote(path.split("/api/v1/explorer/block/", 1)[1]).strip()
                    found = None
                    with node_ref.chain_lock:
                        if q.isdigit() and int(q) in node_ref.chain_by_index:
                            found = node_ref.chain_by_index[int(q)]
                        else:
                            ql = q.lower()
                            for b in node_ref.chain_by_index.values():
                                if str(b.get("hash", "")).lower() == ql:
                                    found = b
                                    break
                    if found:
                        self._send_json(200, {"success": True, "data": found})
                    else:
                        self._send_json(404, {"success": False, "message": "Block not found."})
                    return

                if path == "/api/v1/explorer/search":
                    full_path = path + (("?" + urllib.parse.urlencode(qs, doseq=True)) if qs else "")
                    upstream = node_ref.request(full_path, method="GET", timeout=3.5)
                    if upstream and upstream.get("success"):
                        self._send_json(200, upstream)
                        return
                    q = (qs.get("q", [""])[0] or "").strip()
                    with node_ref.chain_lock:
                        if q.isdigit() and int(q) in node_ref.chain_by_index:
                            self._send_json(200, {"success": True, "data": {"type": "block", "result": node_ref.chain_by_index[int(q)]}})
                            return
                        ql = q.lower()
                        for b in node_ref.chain_by_index.values():
                            if str(b.get("hash", "")).lower() == ql:
                                self._send_json(200, {"success": True, "data": {"type": "block", "result": b}})
                                return
                            for t in b.get("transactions", []):
                                if str(t.get("tx_hash", "")).lower() == ql:
                                    t_copy = dict(t)
                                    t_copy["block_index"] = b.get("index")
                                    self._send_json(200, {"success": True, "data": {"type": "transaction", "result": t_copy}})
                                    return
                    if _is_valid_bct_address(q):
                        bal, _, _ = node_ref.local_calc_balance_and_nonce(q)
                        hist = node_ref.local_wallet_transactions(q, 50)
                        self._send_json(200, {
                            "success": True,
                            "data": {"type": "address", "result": {"address": q, "balance": bal, "transaction_count": len(hist), "transactions": hist}},
                        })
                        return
                    self._send_json(404, {"success": False, "message": "Record not found."})
                    return

                if path == "/api/v1/explorer/holders":
                    full_path = path + (("?" + urllib.parse.urlencode(qs, doseq=True)) if qs else "")
                    upstream = node_ref.request(full_path, method="GET", timeout=3.5)
                    if upstream and upstream.get("success"):
                        self._send_json(200, upstream)
                        return
                    lim = max(1, min(50, int(qs.get("limit", ["10"])[0])))
                    page = max(1, int(qs.get("page", ["1"])[0]))
                    self._send_json(200, {"success": True, "data": node_ref.local_holders(page, lim)})
                    return

                if path == "/api/v1/space/feed":
                    full_path = path + (("?" + urllib.parse.urlencode(qs, doseq=True)) if qs else "")
                    upstream = node_ref.request(full_path, method="GET", timeout=3.5)
                    if upstream and upstream.get("success"):
                        self._send_json(200, upstream)
                        return
                    lim = max(1, min(100, int(qs.get("limit", ["50"])[0])))
                    posts_map = node_ref.local_space_posts()
                    ordered = sorted(posts_map.values(), key=lambda x: float(x.get("timestamp", 0)), reverse=True)[:lim]
                    self._send_json(200, {"success": True, "data": {"posts": ordered}})
                    return

                if path == "/api/v1/space/trending_tags":
                    full_path = path + (("?" + urllib.parse.urlencode(qs, doseq=True)) if qs else "")
                    upstream = node_ref.request(full_path, method="GET", timeout=3.5)
                    if upstream and upstream.get("success"):
                        self._send_json(200, upstream)
                        return
                    posts_map = node_ref.local_space_posts()
                    tag_counts = {}
                    for p in posts_map.values():
                        raw = p.get("content", "")
                        for h in re.findall(r"#([a-zA-Z0-9_ğüşıöçĞÜŞİÖÇ\-]+)", raw):
                            tag_counts[f"#{h}"] = tag_counts.get(f"#{h}", 0) + 1
                        for c in re.findall(r"\$([a-zA-Z0-9_]{2,10})\b", raw):
                            tag_counts[f"${c.upper()}"] = tag_counts.get(f"${c.upper()}", 0) + 1
                    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:15]
                    self._send_json(200, {"success": True, "data": {"tags": [{"tag": t[0], "count": t[1], "type": "cashtag" if t[0].startswith("$") else "hashtag"} for t in sorted_tags]}})
                    return

                if path == "/api/v1/space/suggested-voices":
                    full_path = path + (("?" + urllib.parse.urlencode(qs, doseq=True)) if qs else "")
                    upstream = node_ref.request(full_path, method="GET", timeout=3.5)
                    if upstream and upstream.get("success"):
                        self._send_json(200, upstream)
                        return
                    lim = max(1, min(20, int(qs.get("limit", ["5"])[0])))
                    posts_map = node_ref.local_space_posts()
                    authors = {p.get("author") for p in posts_map.values() if p.get("author")}
                    bns_map = node_ref.local_bns_records()
                    voices = []
                    for a in authors:
                        if a and a != TREASURY_ADDRESS:
                            bns = next((k for k, v in bns_map.items() if v.get("owner") == a), "")
                            voices.append({
                                "address": a,
                                "bns_name": bns,
                                "display_name": f"@{bns}" if bns else f"{a[:6]}...{a[-4:]}",
                                "bio": f"@{bns} • Core Voice" if bns else "BCT Active Creator",
                                "followers_count": 0,
                                "is_following": False,
                                "posts_count": sum(1 for p in posts_map.values() if p.get("author") == a)
                            })
                    self._send_json(200, {"success": True, "data": {"voices": voices[:lim]}})
                    return

                if path.startswith("/api/v1/space/post/"):
                    upstream = node_ref.request(path, method="GET", timeout=3.5)
                    if upstream and upstream.get("success"):
                        self._send_json(200, upstream)
                        return
                    pid = urllib.parse.unquote(path.split("/api/v1/space/post/", 1)[1]).strip()
                    posts_map = node_ref.local_space_posts()
                    if pid in posts_map:
                        self._send_json(200, {"success": True, "data": posts_map[pid]})
                    else:
                        self._send_json(404, {"success": False, "message": "Post not found."})
                    return

                # ── BNS & Profile Endpoints (Proxy to seed + offline fallback) ──
                if path.startswith("/api/v1/bns/lookup/"):
                    q = urllib.parse.unquote(path.split("/api/v1/bns/lookup/", 1)[1]).strip()
                    upstream = node_ref.request(path, method="GET", timeout=3.5)
                    if upstream and upstream.get("success"):
                        self._send_json(200, upstream)
                        return
                    rec = node_ref.local_bns_lookup(q)
                    if rec:
                        self._send_json(200, {"success": True, "data": rec})
                    else:
                        self._send_json(404, {"success": False, "message": f"BNS record not found: '{q}'"})
                    return

                if path.startswith("/api/v1/profile/"):
                    upstream = node_ref.request(path, method="GET", timeout=3.5)
                    if upstream and upstream.get("success"):
                        self._send_json(200, upstream)
                        return
                    q = urllib.parse.unquote(path.split("/api/v1/profile/", 1)[1]).strip()
                    addr = q
                    bns_info = node_ref.local_bns_lookup(q)
                    if bns_info and bns_info.get("owner"):
                        addr = bns_info["owner"]
                    bal, nonce, _ = node_ref.local_calc_balance_and_nonce(addr)
                    rev_info = node_ref.local_bns_lookup(addr) or {}
                    posts_map = node_ref.local_space_posts()
                    user_posts = [p for p in posts_map.values() if p.get("author") == addr]
                    self._send_json(200, {
                        "success": True,
                        "data": {
                            "address": addr,
                            "balance": bal,
                            "nonce": nonce,
                            "primary_name": rev_info.get("primary_name", ""),
                            "owned_names": rev_info.get("owned_names", []),
                            "followers": [],
                            "following": [],
                            "followers_count": 0,
                            "following_count": 0,
                            "posts_count": len(user_posts),
                            "posts": sorted(user_posts, key=lambda x: float(x.get("timestamp", 0)), reverse=True)[:25]
                        }
                    })
                    return

                if path == "/api/v1/bns/names":
                    upstream = node_ref.request(path + (("?" + urllib.parse.urlencode(qs, doseq=True)) if qs else ""), method="GET", timeout=3.5)
                    if upstream and upstream.get("success"):
                        self._send_json(200, upstream)
                        return
                    records, _ = node_ref.local_bns_state()
                    self._send_json(200, {"success": True, "data": {"names": list(records.values()), "total": len(records)}})
                    return

                if path.startswith("/api/v1/bns/available/"):
                    q = urllib.parse.unquote(path.split("/api/v1/bns/available/", 1)[1]).strip().lower()
                    upstream = node_ref.request(path, method="GET", timeout=3.5)
                    if upstream and upstream.get("success"):
                        self._send_json(200, upstream)
                        return
                    records, _ = node_ref.local_bns_state()
                    clean = q if q.endswith(".bct") else f"{q}.bct"
                    is_avail = clean not in records
                    self._send_json(200, {"success": True, "data": {"name": clean, "available": is_avail}})
                    return

                # Upstream transparent proxy for any unhandled /api/v1/* GET route
                if path.startswith("/api/v1/"):
                    full_path = path + (("?" + urllib.parse.urlencode(qs, doseq=True)) if qs else "")
                    upstream = node_ref.request(full_path, method="GET", timeout=4.0)
                    if upstream and not upstream.get("_offline") and upstream.get("success") is not None:
                        code = int(upstream.get("_http_code", 200)) if upstream.get("_http_code") else 200
                        self._send_json(code, upstream)
                        return

                # ── C. Verified Web Frontend Static Routes ────────────────
                if not node_ref.enable_web:
                    self._send_json(404, {"success": False, "message": "Web UI disabled (--no-web active)."})
                    return

                if path in ("/", "/index.html"):
                    self._serve_verified_web_shell()
                    return

                if path == "/node_runner.py":
                    with open(os.path.abspath(__file__), "rb") as nf:
                        self._send_bytes(200, nf.read(), "text/x-python; charset=utf-8")
                    return

                # Serve static PWA assets safely from frontend_dir (sw.js, manifest.json, integrity.json, icons/*)
                rel = path.lstrip("/")
                safe_base = os.path.abspath(node_ref.frontend_dir)
                candidate_file = os.path.abspath(os.path.join(safe_base, rel))
                if candidate_file.startswith(safe_base + os.sep) and os.path.isfile(candidate_file):
                    if rel == "sw.js":
                        check = node_ref.verify_frontend_integrity(allow_bootstrap=False)
                        if not check.get("verified"):
                            self._send_bytes(403, b"// Blocked by LockTrace SHA-256 Guard", "application/javascript")
                            return
                    STATIC_MIME_MAP = {
                        ".js": "application/javascript; charset=utf-8",
                        ".json": "application/json; charset=utf-8",
                        ".svg": "image/svg+xml",
                        ".png": "image/png",
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".ico": "image/x-icon",
                        ".html": "text/html; charset=utf-8",
                        ".css": "text/css; charset=utf-8",
                        ".txt": "text/plain; charset=utf-8",
                    }
                    ext = os.path.splitext(candidate_file)[1].lower()
                    ctype = STATIC_MIME_MAP.get(ext, "application/octet-stream")
                    with open(candidate_file, "rb") as sf:
                        self._send_bytes(200, sf.read(), ctype)
                    return

                # SPA Fallback -> Verified Web Shell
                if not path.startswith("/api/") and not path.startswith("/p2p/"):
                    self._serve_verified_web_shell()
                    return

                self._send_json(404, {"success": False, "message": "Endpoint not found."})

            def do_POST(self):
                if not self._verify_host_header():
                    self.send_response(403)
                    self.end_headers()
                    self.wfile.write(b"Forbidden: Host header mismatch (DNS Rebinding Guard)")
                    return
                if not self._verify_origin_header():
                    self.send_response(403)
                    self.end_headers()
                    self.wfile.write(b"Forbidden: Cross-Origin RPC execution rejected (LT-03 CSRF/Origin Guard)")
                    return
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                length = int(self.headers.get("Content-Length", "0"))
                # LT-05 Fix: Enforce strict 512 KB payload limit (DoS & Memory Exhaustion Guard)
                if length < 0 or length > 524_288:
                    self._send_json(400, {"success": False, "message": "Payload exceeds strict 512 KB limit"})
                    return
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
                except Exception:
                    self._send_json(400, {"success": False, "message": "Invalid JSON"})
                    return

                if path == "/p2p/gossip/block":
                    blk = payload.get("block") or {}
                    # LT-05 Fix: Header-First Pre-PoW Validation before heavy processing
                    if not isinstance(blk, dict) or "hash" not in blk or "index" not in blk or "nonce" not in blk:
                        self._send_json(400, {"success": False, "message": "Malformed block payload"})
                        return
                    accepted = node_ref.ingest_gossiped_block(blk)
                    self._send_json(200 if accepted else 400, {"success": accepted})
                    return

                if path == "/p2p/gossip/compact_block":
                    compact_data = payload.get("compact_block") or {}
                    accepted = node_ref.ingest_compact_block(compact_data)
                    self._send_json(200 if accepted else 400, {"success": accepted})
                    return

                if path.startswith("/api/v1/"):
                    code, resp = node_ref.handle_decentralized_write(path, payload)
                    self._send_json(code, resp)
                    return

                self._send_json(404, {"success": False, "message": "Unknown POST route"})

        for candidate_port in [self.port, 0]:
            try:
                srv = ThreadingHTTPServer((self.host, candidate_port), DecentralizedNodeHandler)
                self.port = srv.server_address[1]
                self._p2p_server = srv
                threading.Thread(target=srv.serve_forever, daemon=True).start()
                return
            except OSError:
                continue

    def stop(self):
        self._running = False
        if self._p2p_server:
            try:
                self._p2p_server.shutdown()
                self._p2p_server.server_close()
            except Exception:
                pass

    # ── Local Archival Storage & Block Verification ───────────────
    def _load_local_chain(self):
        chain_file = os.path.join(self.data_dir, "archival_chain.json")
        if not os.path.exists(chain_file):
            return
        try:
            with open(chain_file, "r", encoding="utf-8") as f:
                blocks = json.load(f)
            if isinstance(blocks, list):
                self._verify_and_store_blocks(blocks, persist=False)
        except Exception:
            pass

    def _persist_local_chain(self):
        chain_file = os.path.join(self.data_dir, "archival_chain.json")
        tmp_file = chain_file + ".tmp"
        with self.chain_lock:
            ordered = [self.chain_by_index[k] for k in sorted(self.chain_by_index.keys())]
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(ordered, f)
        os.replace(tmp_file, chain_file)

    def verify_single_block(self, blk: dict, base_difficulty: int = 3) -> bool:
        if not isinstance(blk, dict):
            return False
        b_idx = int(blk.get("index", -1))
        b_hash = str(blk.get("hash", "")).lower()
        if b_idx < 0 or not b_hash:
            return False

        if calculate_block_hash_dict(blk) != b_hash:
            return False

        target_diff = int(blk.get("difficulty", base_difficulty) or base_difficulty)
        if b_idx > 0 and not b_hash.startswith("0" * max(1, target_diff)):
            return False

        txs = blk.get("transactions", [])
        if not isinstance(txs, list) or not txs:
            return False

        reward_total_u = 0
        fee_total_u = 0
        computed_tx_hashes = []
        for t in txs:
            if not isinstance(t, dict):
                return False
            th = str(t.get("tx_hash", "")).strip().lower()
            if th and calculate_tx_hash_dict(t) != th:
                return False
            computed_tx_hashes.append(th or calculate_tx_hash_dict(t))

            ttype = str(t.get("tx_type", "transfer"))
            amt_u = _to_units(float(t.get("amount", 0.0)))
            fee_u = _to_units(float(t.get("fee", 0.0)))
            if amt_u < 0 or fee_u < 0:
                return False
            if b_idx > 0 and ttype == "genesis":
                return False
            if ttype in ("mining_reward", "validator_reward"):
                if str(t.get("sender", "")) != TREASURY_ADDRESS:
                    return False
                reward_total_u += amt_u
            else:
                fee_total_u += fee_u

        max_allowed_reward_u = _to_units(BLOCK_REWARD) + fee_total_u + 100
        if b_idx > 0 and reward_total_u > max_allowed_reward_u:
            return False

        if computed_tx_hashes and blk.get("merkle_root"):
            if compute_merkle_root(computed_tx_hashes) != str(blk["merkle_root"]).lower():
                return False

        with self.chain_lock:
            if b_idx > 0 and (b_idx - 1) in self.chain_by_index:
                prev_blk = self.chain_by_index[b_idx - 1]
                if str(blk.get("previous_hash", "")).lower() != str(prev_blk["hash"]).lower():
                    return False
        return True

    def _verify_and_store_blocks(self, blocks: list, difficulty: int = 3, persist: bool = True) -> bool:
        ordered = sorted(blocks, key=lambda b: int(b.get("index", 0)))
        added = False
        with self.chain_lock:
            for blk in ordered:
                if not self.verify_single_block(blk, base_difficulty=3):
                    self.integrity_ok = False
                    return False
                idx = int(blk["index"])
                if idx not in self.chain_by_index or self.chain_by_index[idx]["hash"] != blk["hash"]:
                    self.chain_by_index[idx] = blk
                    added = True
            if self.chain_by_index:
                self.local_height = max(self.chain_by_index.keys()) + 1
            self.integrity_ok = True

        if added and persist:
            self._persist_local_chain()
        return True

    def ingest_compact_block(self, compact_data: dict) -> bool:
        """
        v2.6.0 P2P Compact Block Handler.
        Validates compact block header and reconstructs full block without retransmitting transactions.
        """
        header = compact_data.get("header") or {}
        if not isinstance(header, dict) or "hash" not in header or "merkle_root" not in header:
            return False

        target_diff = int(header.get("difficulty", 3))
        if not str(header.get("hash", "")).startswith("0" * target_diff):
            return False

        prefilled = {item["index"]: item["tx"] for item in compact_data.get("prefilled_transactions", []) if "index" in item}
        short_ids = compact_data.get("short_ids", [])
        total_txs = int(compact_data.get("total_transactions", len(short_ids) + len(prefilled)))

        assembled = []
        for i in range(total_txs):
            if i in prefilled:
                assembled.append(prefilled[i])
            else:
                return False  # Missing tx, node will receive full block via regular gossip

        calc_merkle = compute_merkle_root([t.get("tx_hash", "") for t in assembled])
        if calc_merkle != header.get("merkle_root", "").lower():
            return False

        full_block = dict(header)
        full_block["transactions"] = assembled
        return self.ingest_gossiped_block(full_block)

    def ingest_gossiped_block(self, blk: dict) -> bool:
        if not self.verify_single_block(blk, base_difficulty=3):
            return False
        with self.chain_lock:
            idx = int(blk["index"])
            # Prevent malicious fork injection: Do not overwrite an existing block at the same index
            if idx in self.chain_by_index:
                if self.chain_by_index[idx].get("hash") == blk.get("hash"):
                    return True
                return False

            # Ensure cryptographic chain continuity with predecessor
            if idx > 0:
                prev_idx = idx - 1
                if prev_idx not in self.chain_by_index:
                    threading.Thread(target=self.sync_chain, daemon=True).start()
                    return False  # Missing predecessor, full sync triggered
                if str(blk.get("previous_hash", "")).lower() != str(self.chain_by_index[prev_idx].get("hash", "")).lower():
                    return False

            self.chain_by_index[idx] = blk
            self.local_height = max(self.local_height, idx + 1)
            self.network_height = max(self.network_height, self.local_height)
        self._persist_local_chain()
        self.gossip_block_to_peers(blk)
        threading.Thread(target=self.submit_latest_attestation, daemon=True).start()
        return True

    # ── P2P Registration, Peer Discovery, Sync & Attestations ────
    def register(self) -> bool:
        if self.host == "127.0.0.1" and not self.public_endpoint:
            ep = f"http://local-only:{self.port}"
        else:
            ep = self._endpoint_url()
        ts = round(time.time(), 3)
        sig = self._sign_auth(f"NODE:{self.node_id}:{self.wallet_address}:{ts}")
        payload = {
            "node_id": self.node_id,
            "name": self.name,
            "endpoint": ep,
            "role": self.role,
            "location": self.location,
            "miner_address": self.wallet_address,
            "block_height": self.local_height,
            "version": VERSION,
            "public_key": self.keys.get("public_key", ""),
            "signature": sig,
            "timestamp": ts,
            "hashrate_hs": self.last_hashrate_hs,
        }
        res = self.request("/api/v1/nodes/register", data=payload, method="POST")
        if not res.get("success") and ("başka bir" in str(res.get("message", "")).lower() or "another" in str(res.get("message", "")).lower()):
            # Node ID collision with another key -> generate new unique node_id and re-sign
            self.node_id = f"node-{socket.gethostname().lower()[:10]}-{secrets.token_hex(4)}"
            self.node_id = "".join(c for c in self.node_id if c.isalnum() or c in "._-")[:48]
            id_file = os.path.join(self.home_dir, "node_identity.json")
            try:
                with open(id_file, "w", encoding="utf-8") as f:
                    json.dump({"node_id": self.node_id, "created_at": time.time()}, f, indent=2)
            except Exception:
                pass
            payload["node_id"] = self.node_id
            payload["signature"] = self._sign_auth(f"NODE:{self.node_id}:{self.wallet_address}:{ts}")
            res = self.request("/api/v1/nodes/register", data=payload, method="POST")
        return bool(res.get("success", False))

    def heartbeat(self):
        ts = round(time.time(), 3)
        sig = self._sign_auth(f"NODE:{self.node_id}:{self.wallet_address}:{ts}")
        payload = {
            "node_id": self.node_id,
            "block_height": self.local_height,
            "miner_address": self.wallet_address,
            "public_key": self.keys.get("public_key", ""),
            "signature": sig,
            "timestamp": ts,
            "hashrate_hs": self.last_hashrate_hs,
        }
        self.request("/api/v1/nodes/ping", data=payload, method="POST")

    def discover_peers(self):
        res = self.request("/api/v1/peers")
        if res.get("success"):
            for p in res.get("data", {}).get("peers", []):
                nid = p.get("node_id")
                ep = str(p.get("endpoint", "") or "").rstrip("/")
                if nid and nid != self.node_id and ep.startswith("http") and "local-only" not in ep:
                    self.known_peers[nid] = p

    def sync_state_snapshot(self) -> bool:
        """
        v2.7.0 Decentralized State Snapshot Sync.
        Fetches snapshot, verifies canonical state root, and initializes base ledger state.
        Allows fast-syncing nodes to sync recent 1,000 blocks instead of entire history.
        """
        res = self.request("/api/v1/snapshot/latest")
        if not res.get("success"):
            return False
        snap = res.get("data") or {}
        declared_root = str(snap.get("state_root", "")).strip().lower()
        height = int(snap.get("snapshot_height", 0))
        if not declared_root or height <= 0:
            return False

        balances = snap.get("balances", {})
        wallets = snap.get("wallets", {})
        bns = snap.get("bns_records", snap.get("bns_domains", {}))

        sorted_balances = sorted((k, round(float(v), 8)) for k, v in balances.items())
        sorted_wallets = sorted((k, int(w.get("nonce", 0))) for k, w in wallets.items() if isinstance(w, dict))
        sorted_bns = sorted((k, str(v.get("owner", ""))) for k, v in bns.items() if isinstance(v, dict))

        payload = {"balances": sorted_balances, "wallets": sorted_wallets, "bns": sorted_bns}
        calc_root = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

        if calc_root != declared_root:
            print(f" [WARN] State snapshot root mismatch! Falling back to archival genesis sync.")
            return False

        with self.chain_lock:
            self.snapshot_height = height
            self.snapshot_state_root = declared_root
            self.network_height = height
            # Sync rolling window of latest 1,000 blocks
            self.local_height = max(0, height - 1000)

        print(f"\n [FAST SYNC v2.7.0] Verified Decentralized State Root @ Height #{height} ({declared_root[:12]}...). Syncing recent 1,000 blocks...")
        return True

    def sync_chain(self):
        if self.sync_mode == "snapshot" and self.local_height == 0:
            self.sync_state_snapshot()
        cursor = self.local_height
        while True:
            res = self.request(f"/api/v1/chain/range?start={cursor}&limit=100")
            if not res.get("success"):
                for peer in list(self.known_peers.values())[:3]:
                    ep = str(peer.get("endpoint", "")).rstrip("/")
                    p_res = self.request(f"/p2p/blocks?start={cursor}&limit=50", base_url=ep, timeout=4.0)
                    if p_res.get("success") and p_res.get("blocks"):
                        self._verify_and_store_blocks(p_res["blocks"])
                        break
                break

            data = res.get("data", {})
            self.network_height = int(data.get("total_blocks", self.network_height))
            blocks = data.get("blocks", [])
            if not blocks:
                break
            if not self._verify_and_store_blocks(blocks, difficulty=int(data.get("difficulty", 3))):
                break
            cursor = self.local_height
            if len(blocks) < 100 or self.local_height >= self.network_height:
                break

        self.synced = self.local_height >= max(1, self.network_height) and self.integrity_ok

        if self.synced and self.local_height > 0:
            self.submit_latest_attestation()

        if self.wallet_address.startswith("BCT"):
            bal_res = self.request(f"/api/v1/balance/{self.wallet_address}")
            if bal_res.get("success"):
                self.wallet_balance = float(bal_res.get("data", {}).get("balance", 0.0))
            else:
                local_bal, _, _ = self.local_calc_balance_and_nonce(self.wallet_address)
                self.wallet_balance = local_bal

    def submit_latest_attestation(self):
        if not self.keys.get("private_key"):
            return
        with self.chain_lock:
            if not self.chain_by_index:
                return
            tip_idx = max(self.chain_by_index.keys())
            if tip_idx <= self.last_attested_index:
                return
            tip_hash = str(self.chain_by_index[tip_idx]["hash"]).lower()

        ts = round(time.time(), 3)
        msg = f"ATTEST:{self.node_id}:{tip_idx}:{tip_hash}:{ts}"
        sig = self._sign_auth(msg)
        res = self.request(
            "/api/v1/nodes/attest",
            data={
                "node_id": self.node_id,
                "miner_address": self.wallet_address,
                "block_index": tip_idx,
                "block_hash": tip_hash,
                "public_key": self.keys["public_key"],
                "signature": sig,
                "timestamp": ts,
            },
            method="POST",
        )
        if res.get("success"):
            self.last_attested_index = tip_idx
            self.blocks_attested = int(res.get("data", {}).get("blocks_attested", self.blocks_attested + 1))

    # ── Real Local CPU Proof-of-Work Miner ───────────────────────
    def mine_template_locally(self) -> bool:
        if not self.keys.get("private_key"):
            return False

        qs = urllib.parse.urlencode({"miner_address": self.wallet_address, "node_id": self.node_id})
        tpl_res = self.request(f"/api/v1/mining/template?{qs}")
        if not tpl_res.get("success"):
            return False

        tpl = tpl_res.get("data") or {}
        if tpl.get("empty") or not tpl.get("transactions"):
            return False

        txs = tpl["transactions"]
        computed_merkle = compute_merkle_root([t["tx_hash"] for t in txs])
        if computed_merkle != str(tpl["merkle_root"]).lower():
            return False

        difficulty = int(tpl.get("difficulty", 3))
        target_prefix = "0" * difficulty
        candidate = {
            "index": int(tpl["index"]),
            "version": int(tpl.get("version", 2)),
            "merkle_root": computed_merkle,
            "miner": self.wallet_address,
            "transactions": txs,
            "previous_hash": str(tpl["previous_hash"]),
            "timestamp": tpl["timestamp"],
            "nonce": 0,
        }

        # High-Performance PoW Engine (GPU OpenCL / Multi-Worker CPU)
        ok, winning_nonce, solved_hash, hr = self.miner_engine.solve_pow(
            candidate, target_difficulty=difficulty, max_nonces=1_000_000
        )
        self.last_hashrate_hs = hr

        if not ok or not solved_hash:
            return False

        candidate["nonce"] = winning_nonce
        candidate["hash"] = solved_hash
        sig_msg = f"SUBMIT_BLOCK:{candidate['index']}:{solved_hash}:{candidate['nonce']}:{self.wallet_address}"
        sig = self._sign_auth(sig_msg)

        submit_res = self.request(
            "/api/v1/mining/submit",
            data={
                "node_id": self.node_id,
                "public_key": self.keys["public_key"],
                "signature": sig,
                "hashrate_hs": self.last_hashrate_hs,
                "block": candidate,
            },
            method="POST",
        )
        if submit_res.get("success"):
            receipt = submit_res.get("data", {})
            reward = float(receipt.get("miner_reward", 0.0))
            val_pool = float(receipt.get("validator_pool_reward", 0.0))
            self.blocks_mined += 1
            self.proposer_rewards = round(self.proposer_rewards + reward, 8)
            self.wallet_balance = float(receipt.get("miner_balance", self.wallet_balance + reward))
            self._verify_and_store_blocks([candidate])
            self.gossip_block_to_peers(candidate)
            print(
                f"\n >>> [POW BLOCK #{candidate['index']} SEALED] "
                f"Proposer: +{reward:.6f} BCT | Validator Pool: +{val_pool:.6f} BCT "
                f"({self.last_hashrate_hs:,.0f} H/s) <<< \n"
            )
            return True
        return False

    def _build_compact_block(self, block_dict: dict) -> dict:
        txs = block_dict.get("transactions", [])
        prefilled = []
        short_ids = []
        if txs:
            prefilled.append({"index": 0, "tx": txs[0]})
            for tx in txs[1:]:
                tx_hash = tx.get("tx_hash", "") or ""
                short_ids.append(tx_hash[:16])

        return {
            "compact_version": 1,
            "header": {
                "index": int(block_dict.get("index", 0)),
                "version": int(block_dict.get("version", 2)),
                "merkle_root": str(block_dict.get("merkle_root", "")),
                "miner": str(block_dict.get("miner", "")),
                "previous_hash": str(block_dict.get("previous_hash", "")),
                "timestamp": block_dict.get("timestamp", 0.0),
                "nonce": int(block_dict.get("nonce", 0)),
                "difficulty": int(block_dict.get("difficulty", 3)),
                "hash": str(block_dict.get("hash", "")),
                "validator_quorum": block_dict.get("validator_quorum", []),
            },
            "prefilled_transactions": prefilled,
            "short_ids": short_ids,
            "total_transactions": len(txs),
        }

    def gossip_block_to_peers(self, block_dict: dict):
        compact_data = self._build_compact_block(block_dict)
        for _nid, peer in list(self.known_peers.items())[:15]:
            if peer.get("is_genesis"):
                continue
            ep = str(peer.get("endpoint", "")).rstrip("/")
            if ep.startswith("http"):
                # v2.6.0 Compact Block Relay (~90% bandwidth reduction)
                threading.Thread(
                    target=self.request,
                    kwargs={
                        "endpoint": "/p2p/gossip/compact_block",
                        "data": {"compact_block": compact_data, "node_id": self.node_id},
                        "method": "POST",
                        "base_url": ep,
                        "timeout": 2.5,
                    },
                    daemon=True,
                ).start()
                # Full Block Gossip Fallback
                threading.Thread(
                    target=self.request,
                    kwargs={
                        "endpoint": "/p2p/gossip/block",
                        "data": {"block": block_dict},
                        "method": "POST",
                        "base_url": ep,
                        "timeout": 2.5,
                    },
                    daemon=True,
                ).start()

    def print_status(self):
        os.system("cls" if os.name == "nt" else "clear")
        print("=" * 74)
        print(f"   LOCKTRACE DECENTRALIZED VALIDATOR, POW MINER & WEB SERVER (v{VERSION})")
        print("=" * 74)
        print(f" Node ID          : {self.node_id}")
        print(f" Node Name        : {self.name} ({self.location})")
        if self.enable_web:
            print(f" Local Web Wallet : http://127.0.0.1:{self.port}")
            if self.host == "0.0.0.0":
                print(f" Server / LAN URL : http://{self.lan_ip}:{self.port} (Public/LAN RPC & Web)")
            print(f" Frontend Guard   : {self.frontend_status_msg}")
        else:
            print(f" Local P2P Server : http://{self.host}:{self.port}/p2p/status (--no-web)")
        print(f" Known P2P Peers  : {len(self.known_peers)} active peers")
        print("-" * 74)
        if self.payout_address and self.payout_address != self.keys["address"]:
            print(f" Payout Wallet    : {self.payout_address} (Mining & Quorum Rewards Destination)")
            print(f" Node Signing Key : {self.keys['address']}")
        else:
            print(f" Validator Wallet : {self.wallet_address}")
        print(f" Wallet Vault     : {os.path.join(self.home_dir, 'miner_wallet.json')}")
        print(f" Wallet Balance   : {self.wallet_balance:.8f} BCT")
        print(f" PoW Blocks Mined : {self.blocks_mined} (70% Proposer Share: +{self.proposer_rewards:.6f} BCT)")
        print(f" Blocks Attested  : {self.blocks_attested} (Eligible for 30% Validator Quorum Pool)")
        print(f" Local Hashrate   : {self.last_hashrate_hs:,.0f} H/s (SHA-256 v2 Merkle)")
        print(f" Mining Engine    : {self.miner_engine_info.get('active_engine')}")
        if self.miner_engine_info.get("gpu_available"):
            print(f" GPU Model        : {self.miner_engine_info.get('device_name')}")
        try:
            from core.native_bridge import get_engine_status
            c_eng = get_engine_status()
            print(f" Crypto Engine    : {c_eng.get('engine')}")
        except Exception:
            pass
        print(f" Sync Engine      : {self.sync_mode.upper()} (v2.7.0 State Snapshot & Compact Relay)")
        print("-" * 74)
        status_txt = "SYNCHRONIZED & ATTESTING" if self.synced else "AUTONOMOUS P2P / SYNCING"
        print(f" Consensus Status : {status_txt}")
        print(f" Archival Chain   : {self.local_height} / {max(self.local_height, self.network_height)} Verified Blocks")
        print(f" Last Heartbeat   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 74)
        if self.enable_web and not self.frontend_verified:
            print(f" {TAMPER_WARNING_TEXT}")
            print("=" * 74)
        print(" Active: Verified Web UI + P2P Gossip + Quorum (30%) + CPU PoW (70%). Ctrl+C to stop.")

    def run(self):
        print(f"[INIT] Syncing archival chain & peers from {self.seed_url}...")
        self.discover_peers()
        self.sync_chain()

        if self.enable_web:
            check = self.verify_frontend_integrity(allow_bootstrap=True)
            if not check.get("verified"):
                print("\n" + "!" * 74)
                print(f" {TAMPER_WARNING_TEXT}")
                print(f" Detay: {check.get('reason')}")
                if check.get("expected_index_sha256"):
                    print(f" Beklenen SHA-256 : {check.get('expected_index_sha256')}")
                    print(f" Mevcut SHA-256   : {check.get('actual_index_sha256')}")
                print("!" * 74 + "\n")
            else:
                print(f"[OK] Frontend SHA-256 & ECDSA Signature Verified: {check['actual_index_sha256'][:24]}...")

        mode_lbl = "LOCAL-ONLY (127.0.0.1)" if self.host == "127.0.0.1" else "PUBLIC/LAN SERVER (0.0.0.0)"
        print(f"[INIT] Starting HTTP Web + P2P Listener [{mode_lbl}] on {self.host}:{self.port}...")
        self.start_p2p_server()

        if self.enable_web and self.open_browser:
            if self.frontend_verified:
                url = f"http://127.0.0.1:{self.port}"
                print(f"[WEB] Opening verified LockTrace Web Wallet at {url} ...")
                threading.Thread(target=lambda: (time.sleep(0.8), webbrowser.open(url)), daemon=True).start()
            else:
                print(f"[BLOCKED] Browser launch aborted -> {TAMPER_WARNING_TEXT}")

        if self.register():
            print("[OK] Authenticated ECDSA Validator Node registered on LockTrace Mainnet!")
        else:
            print("[WARN] Running in Autonomous Decentralized P2P Mode.")

        tick = 0
        try:
            while self._running:
                self.sync_chain()
                if self.enable_web:
                    self.verify_frontend_integrity(allow_bootstrap=False)
                self.mine_template_locally()
                if tick % 2 == 0:
                    self.heartbeat()
                if tick % 5 == 0:
                    self.discover_peers()
                self.print_status()
                tick += 1
                time.sleep(5)
        except KeyboardInterrupt:
            self.stop()
            print("\n[INFO] LockTrace Decentralized Node stopped cleanly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LockTrace Decentralized P2P Validator, PoW Miner & Verified Web Server")
    parser.add_argument("--name", default="", help="Custom display name for your node")
    parser.add_argument("--seed", default=DEFAULT_SEED, help="Primary seed node endpoint")
    parser.add_argument("--location", default="", help="City / Country or cloud region")
    parser.add_argument("--wallet", default="", help="Optional payout BCT wallet address")
    parser.add_argument("--private-key", "--key", "-k", default="", help="Optional 64-hex SECP256k1 private key for node signing")
    parser.add_argument("--role", default="Community Validator Peer", help="Network role")
    parser.add_argument("--port", type=int, default=5050, help="HTTP Web & P2P listening port (default: 5050)")
    parser.add_argument("--host", default="", help="Bind IP (127.0.0.1 for local-only, 0.0.0.0 for server mode)")
    parser.add_argument("--local", action="store_true", help="Run Web Frontend locally only on 127.0.0.1 (private to your PC)")
    parser.add_argument("--server", action="store_true", help="Run Web Frontend & RPC as a LAN/Public server on 0.0.0.0")
    parser.add_argument("--open", action="store_true", help="Automatically open verified Web Wallet in your default browser")
    parser.add_argument("--no-web", action="store_true", help="Disable Web Frontend hosting (headless P2P validator only)")
    parser.add_argument("--verify-frontend", action="store_true", help="Verify local frontend SHA-256 & ECDSA signature and exit")
    parser.add_argument("--public-endpoint", default="", help="Public URL (http://ip:port) for inbound P2P gossip")
    parser.add_argument("--data-dir", default="", help="Custom node storage directory")
    parser.add_argument("--miner-engine", choices=["auto", "gpu", "cpu"], default="auto", help="PoW mining acceleration engine (default: auto)")
    parser.add_argument("--sync-mode", choices=["snapshot", "full"], default="snapshot", help="Sync mode: 'snapshot' for fast warp sync (last 1,000 blocks + state root), 'full' for archival sync from Genesis #0 (default: snapshot)")
    parser.add_argument("--dev", action="store_true", help="Development mode (bypasses frontend release signing check)")
    args = parser.parse_args()

    if args.local:
        bind_host = "127.0.0.1"
    elif args.server:
        bind_host = "0.0.0.0"
    elif args.host:
        bind_host = args.host
    else:
        bind_host = "0.0.0.0"

    daemon = LockTraceNode(
        name=args.name,
        seed_url=args.seed,
        location=args.location,
        role=args.role,
        wallet=args.wallet,
        private_key=args.private_key,
        port=args.port,
        host=bind_host,
        public_endpoint=args.public_endpoint,
        data_dir=args.data_dir,
        enable_web=not args.no_web,
        open_browser=args.open,
        dev_mode=args.dev,
        miner_engine=args.miner_engine,
        sync_mode=args.sync_mode,
    )

    if args.verify_frontend:
        res = daemon.verify_frontend_integrity(allow_bootstrap=False)
        if res.get("verified"):
            m = res["manifest"]
            print("✅ [VERIFIED] LockTrace Frontend SHA-256 Checksum & ECDSA Release Signature Valid!")
            print(f"   Version          : v{m.get('version')}")
            print(f"   index.html SHA256: {res['actual_index_sha256']}")
            print(f"   IPFS CIDv1       : ipfs://{m.get('ipfs_cid_v1')}")
            print(f"   Signing Authority: {RELEASE_AUTHORITY_ADDRESS}")
            sys.exit(0)
        else:
            print(res.get("reason", TAMPER_WARNING_TEXT))
            if res.get("expected_index_sha256"):
                print(f"   Expected SHA-256 : {res.get('expected_index_sha256')}")
                print(f"   Actual SHA-256   : {res.get('actual_index_sha256')}")
            sys.exit(1)

    daemon.run()
