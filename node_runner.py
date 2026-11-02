#!/usr/bin/env python3
"""
LockTrace Blockchain - Decentralized P2P Validator & Real PoW Mining Daemon (v1.4.0)
====================================================================================
Run your own independent archival validator & Proof-of-Work miner on Linux, macOS, or Windows
with ZERO external Python package dependencies!

Key Capabilities:
  1. Non-Custodial Local SECP256k1 Keypair & ECDSA Authentication (Private key stays on your node).
  2. Built-in Multi-Threaded P2P HTTP Server (/p2p/status, /p2p/peers, /p2p/blocks, /p2p/gossip/block).
  3. Full Incremental Archival Chain Sync (Genesis #0 -> Tip) with SHA-256 + Merkle Root Verification.
  4. Cryptographic Block Attestations (Earns from the 30% Active Validator Quorum Reward Pool).
  5. Real Local CPU SHA-256 Proof-of-Work Mining (Earns 70% Proposer Share + 50% Fees + 0.05 BCT Subsidy).

Usage:
    python node_runner.py
    python node_runner.py --name "Istanbul-Validator-01" --location "Istanbul, TR" --port 5050
"""

import argparse
import hashlib
import hmac
import json
import os
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_SEED = "https://www.locktrace.space"
FALLBACK_SEED = "http://129.151.205.219"
VERSION = "1.4.0"


# =====================================================================
# 1. ZERO-DEPENDENCY PURE-PYTHON SECP256k1 ECDSA & MERKLE PRIMITIVES
# =====================================================================
class PureSecp256k1:
    """Pure-Python deterministic SECP256k1 key derivation & ECDSA-SHA256 signing."""

    P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
    N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
    GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
    GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

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
            lam = ((y2 - y1) * pow(x2 - x1, -1, cls.P)) % cls.P
        x3 = (lam * lam - x1 - x2) % cls.P
        y3 = (lam * (x1 - x3) - y1) % cls.P
        return (x3, y3)

    @classmethod
    def point_mul(cls, k: int, pt=None):
        if pt is None:
            pt = (cls.GX, cls.GY)
        result = None
        addend = pt
        scalar = k
        while scalar > 0:
            if scalar & 1:
                result = cls.point_add(result, addend)
            addend = cls.point_add(addend, addend)
            scalar >>= 1
        return result

    @classmethod
    def generate_keypair(cls, private_key_hex: str = "") -> dict:
        if private_key_hex:
            d = int(private_key_hex.strip(), 16)
        else:
            d = secrets.randbelow(cls.N - 1) + 1
        priv_hex = f"{d:064x}"
        px, py = cls.point_mul(d)
        pub_hex = f"{px:064x}{py:064x}"
        pub_bytes = bytes.fromhex(pub_hex)
        first_hash = hashlib.sha256(pub_bytes).hexdigest()
        second_hash = hashlib.sha256(first_hash.encode("utf-8")).hexdigest()
        address = f"BCT{second_hash[:40]}"
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


# =====================================================================
# 2. DECENTRALIZED P2P NODE & REAL CPU PROOF-OF-WORK MINER
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
    ):
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

        self.chain_lock = threading.RLock()
        self.chain_by_index: dict = {}
        self.known_peers: dict = {}
        self.local_height = 0
        self.network_height = 0
        self.synced = False
        self.integrity_ok = True
        self.last_attested_index = -1

        self.blocks_mined = 0
        self.blocks_attested = 0
        self.proposer_rewards = 0.0
        self.validator_rewards = 0.0
        self.wallet_balance = 0.0
        self.last_hashrate_hs = 0.0
        self._running = True
        self._p2p_server = None

        self.node_id = self._load_or_create_node_id()
        self.keys = self._init_miner_keys(wallet=wallet, private_key=private_key)
        self.wallet_address = self.keys["address"]
        self._load_local_chain()

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

    def _init_miner_keys(self, wallet: str = "", private_key: str = "") -> dict:
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
                    if not wallet or wallet.strip() == kp["address"]:
                        return kp
            except Exception:
                pass

        if wallet and wallet.strip().startswith("BCT") and len(wallet.strip()) == 43:
            # Read-only payout address without private key (observer mode)
            return {"address": wallet.strip(), "public_key": "", "private_key": ""}

        # Generate 100% local non-custodial SECP256k1 keypair!
        kp = PureSecp256k1.generate_keypair()
        with open(wallet_file, "w", encoding="utf-8") as f:
            json.dump(kp, f, indent=2)
        print("\n" + "=" * 68)
        print(" [NON-CUSTODIAL KEYGEN] Local SECP256k1 Validator Keypair Created!")
        print(f" Validator Wallet : {kp['address']}")
        print(f" Key Vault Path   : {wallet_file}")
        print("=" * 68 + "\n")
        return kp

    def _sign_auth(self, message: str) -> str:
        priv = self.keys.get("private_key", "")
        if not priv:
            return ""
        return PureSecp256k1.sign_sha256(priv, message)

    def _endpoint_url(self) -> str:
        if self.public_endpoint:
            return self.public_endpoint
        return f"http://{socket.gethostname()}:{self.port}"

    def request(self, endpoint: str, data: dict = None, method: str = "GET", base_url: str = "", timeout: float = 10.0) -> dict:
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
                return {"success": False, "message": f"HTTP {he.code}"}
        except urllib.error.URLError as ue:
            if not is_local and not base_url and self.seed_url != FALLBACK_SEED:
                alt_req = urllib.request.Request(f"{FALLBACK_SEED}{endpoint}", data=body, headers=headers, method=method)
                try:
                    with urllib.request.urlopen(alt_req, timeout=timeout) as resp:
                        return json.loads(resp.read().decode("utf-8"))
                except Exception as e:
                    return {"success": False, "message": str(e)}
            return {"success": False, "message": "Connection failed"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Local P2P HTTP Server ─────────────────────────────────────
    def start_p2p_server(self):
        node_ref = self

        class P2PHandler(BaseHTTPRequestHandler):
            def log_message(self, _format, *_args):
                return  # Silent clean TUI

            def _send_json(self, code: int, payload: dict):
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/p2p/status":
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
                        "peers_known": len(node_ref.known_peers),
                    })
                elif parsed.path == "/p2p/peers":
                    self._send_json(200, {
                        "success": True,
                        "peers": list(node_ref.known_peers.values()),
                    })
                elif parsed.path == "/p2p/blocks":
                    qs = urllib.parse.parse_qs(parsed.query)
                    start = max(0, int(qs.get("start", ["0"])[0]))
                    limit = max(1, min(100, int(qs.get("limit", ["50"])[0])))
                    with node_ref.chain_lock:
                        blocks = [
                            node_ref.chain_by_index[i]
                            for i in range(start, start + limit)
                            if i in node_ref.chain_by_index
                        ]
                    self._send_json(200, {"success": True, "blocks": blocks, "local_height": node_ref.local_height})
                else:
                    self._send_json(404, {"success": False, "message": "Unknown P2P route"})

            def do_POST(self):
                parsed = urllib.parse.urlparse(self.path)
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 2_000_000:
                    self._send_json(400, {"success": False, "message": "Invalid payload size"})
                    return
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except Exception:
                    self._send_json(400, {"success": False, "message": "Invalid JSON"})
                    return

                if parsed.path == "/p2p/gossip/block":
                    blk = payload.get("block")
                    accepted = node_ref.ingest_gossiped_block(blk)
                    self._send_json(200 if accepted else 400, {"success": accepted})
                else:
                    self._send_json(404, {"success": False, "message": "Unknown P2P POST route"})

        for candidate_port in [self.port, 0]:
            try:
                srv = ThreadingHTTPServer((self.host, candidate_port), P2PHandler)
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
            if isinstance(blocks, list) and self._verify_and_store_blocks(blocks, persist=False):
                pass
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

        # Recompute SHA-256 header hash
        if calculate_block_hash_dict(blk) != b_hash:
            return False

        if b_idx > 0 and not b_hash.startswith("0" * max(1, base_difficulty)):
            return False

        txs = blk.get("transactions", [])
        tx_hashes = [t.get("tx_hash", "") for t in txs if t.get("tx_hash")]
        if tx_hashes and blk.get("merkle_root"):
            if compute_merkle_root(tx_hashes) != str(blk["merkle_root"]).lower():
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

    def ingest_gossiped_block(self, blk: dict) -> bool:
        """Handles a newly mined block pushed directly over P2P gossip from another node."""
        if not self.verify_single_block(blk, base_difficulty=3):
            return False
        with self.chain_lock:
            idx = int(blk["index"])
            self.chain_by_index[idx] = blk
            self.local_height = max(self.local_height, idx + 1)
            self.network_height = max(self.network_height, self.local_height)
        self._persist_local_chain()
        # Submit validator attestation asynchronously so we earn from the 30% Validator Pool!
        threading.Thread(target=self.submit_latest_attestation, daemon=True).start()
        return True

    # ── P2P Registration, Peer Discovery, Sync & Attestations ────
    def register(self) -> bool:
        ts = round(time.time(), 3)
        sig = self._sign_auth(f"NODE:{self.node_id}:{self.wallet_address}:{ts}")
        payload = {
            "node_id": self.node_id,
            "name": self.name,
            "endpoint": self._endpoint_url(),
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
                if nid and nid != self.node_id and ep.startswith("http"):
                    self.known_peers[nid] = p

    def sync_chain(self):
        """Incremental archival sync from local_height up to tip (falls back to P2P peers if seed fails)."""
        cursor = self.local_height
        while True:
            res = self.request(f"/api/v1/chain/range?start={cursor}&limit=100")
            if not res.get("success"):
                # Peer fallback sync if primary seed is temporarily unreachable
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

        self.synced = self.local_height >= self.network_height and self.integrity_ok

        # Submit cryptographic block attestation for latest verified block
        if self.synced and self.local_height > 0:
            self.submit_latest_attestation()

        # Refresh wallet balance & node reward stats
        if self.wallet_address.startswith("BCT"):
            bal_res = self.request(f"/api/v1/balance/{self.wallet_address}")
            if bal_res.get("success"):
                self.wallet_balance = float(bal_res.get("data", {}).get("balance", 0.0))

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
        """Fetches mempool candidate template, computes real SHA-256 PoW locally, signs & submits block!"""
        if not self.keys.get("private_key"):
            return False

        qs = urllib.parse.urlencode({"miner_address": self.wallet_address, "node_id": self.node_id})
        tpl_res = self.request(f"/api/v1/mining/template?{qs}")
        if not tpl_res.get("success"):
            return False

        tpl = tpl_res.get("data") or {}
        if tpl.get("empty") or not tpl.get("transactions"):
            return False

        # Independently verify Merkle root before investing CPU cycles
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

        t0 = time.perf_counter()
        hashes_tried = 0
        solved_hash = ""

        # Mine up to 500,000 nonces per round (~3-5 seconds max) so node stays responsive to new blocks
        for nonce in range(500_000):
            if not self._running:
                return False
            candidate["nonce"] = nonce
            h = calculate_block_hash_dict(candidate)
            hashes_tried += 1
            if h.startswith(target_prefix):
                solved_hash = h
                break

        elapsed = max(0.001, time.perf_counter() - t0)
        self.last_hashrate_hs = round(hashes_tried / elapsed, 2)

        if not solved_hash:
            return False

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

    def gossip_block_to_peers(self, block_dict: dict):
        for nid, peer in list(self.known_peers.items())[:15]:
            if peer.get("is_genesis"):
                continue
            ep = str(peer.get("endpoint", "")).rstrip("/")
            if ep.startswith("http"):
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
        print("=" * 70)
        print(f"   LOCKTRACE P2P ARCHIVAL VALIDATOR & POW MINER (v{VERSION})")
        print("=" * 70)
        print(f" Node ID          : {self.node_id}")
        print(f" Node Name        : {self.name} ({self.location})")
        print(f" Local P2P Server : http://{self.host}:{self.port}/p2p/status")
        print(f" Known P2P Peers  : {len(self.known_peers)} active peers")
        print("-" * 70)
        print(f" Validator Wallet : {self.wallet_address}")
        print(f" Wallet Balance   : {self.wallet_balance:.8f} BCT")
        print(f" PoW Blocks Mined : {self.blocks_mined} (70% Proposer Share: +{self.proposer_rewards:.6f} BCT)")
        print(f" Blocks Attested  : {self.blocks_attested} (Eligible for 30% Validator Quorum Pool)")
        print(f" Local Hashrate   : {self.last_hashrate_hs:,.0f} H/s (SHA-256 v2 Merkle)")
        print("-" * 70)
        status_txt = "SYNCHRONIZED & ATTESTING" if self.synced else "SYNCING ARCHIVAL LEDGER"
        print(f" Consensus Status : {status_txt}")
        print(f" Archival Chain   : {self.local_height} / {self.network_height} Verified Blocks")
        print(f" Last Heartbeat   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        print(" Active: P2P Gossip + Block Attestation (30%) + CPU PoW Mining (70%). Ctrl+C to stop.")

    def run(self):
        print(f"[INIT] Starting P2P HTTP Listener on {self.host}:{self.port}...")
        self.start_p2p_server()
        print(f"[INIT] Syncing archival chain from {self.seed_url}...")
        self.discover_peers()
        self.sync_chain()
        if self.register():
            print("[OK] Authenticated ECDSA Validator Node registered on LockTrace Mainnet!")
        else:
            print("[WARN] Running in P2P peer-sync mode.")

        tick = 0
        try:
            while self._running:
                self.sync_chain()
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
            print("\n[INFO] LockTrace P2P Validator stopped cleanly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LockTrace Decentralized P2P Validator & PoW Miner")
    parser.add_argument("--name", default="", help="Custom display name for your node")
    parser.add_argument("--seed", default=DEFAULT_SEED, help="Primary seed node endpoint")
    parser.add_argument("--location", default="", help="City / Country or cloud region")
    parser.add_argument("--wallet", default="", help="Optional read-only BCT address")
    parser.add_argument("--private-key", default="", help="Optional 64-hex SECP256k1 private key for node signing")
    parser.add_argument("--role", default="Community Validator Peer", help="Network role")
    parser.add_argument("--port", type=int, default=5050, help="Local P2P HTTP listening port")
    parser.add_argument("--host", default="0.0.0.0", help="Local P2P bind address")
    parser.add_argument("--public-endpoint", default="", help="Public URL (http://ip:port) for inbound P2P gossip")
    parser.add_argument("--data-dir", default="", help="Custom node storage directory")
    args = parser.parse_args()

    daemon = LockTraceNode(
        name=args.name,
        seed_url=args.seed,
        location=args.location,
        role=args.role,
        wallet=args.wallet,
        private_key=args.private_key,
        port=args.port,
        host=args.host,
        public_endpoint=args.public_endpoint,
        data_dir=args.data_dir,
    )
    daemon.run()
