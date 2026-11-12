"""
LockTrace Native Acceleration Bridge (Python <-> Rust / PyO3)
==============================================================
Dual-Engine Architecture:
- If `locktrace_rs` (compiled Rust native extension) is present:
    routes cryptographic, Merkle, and PoW calculations directly to native Rust.
- If `locktrace_rs` is not compiled/available:
    seamlessly falls back to optimized Python OpenSSL implementations with zero downtime.
"""

import re
import json
import secrets
import hashlib
import threading
from typing import Tuple, List, Optional

_HAS_NATIVE_RUST = False
_RUST_CORE = None

try:
    import locktrace_rs
    _HAS_NATIVE_RUST = True
    _RUST_CORE = locktrace_rs
except Exception:
    _HAS_NATIVE_RUST = False
    _RUST_CORE = None


def is_rust_accelerated() -> bool:
    """Returns True if the native Rust engine is loaded and active."""
    return _HAS_NATIVE_RUST and _RUST_CORE is not None


def get_engine_status() -> dict:
    """Returns real-time status of the cryptographic execution engine."""
    if is_rust_accelerated():
        return {
            "engine": "Rust Native (PyO3 / SIMD Accelerated)",
            "version": getattr(_RUST_CORE, "__version__", "2.8.0"),
            "accelerated": True,
        }
    return {
        "engine": "Python OpenSSL (Constant-Time SECP256k1 Fallback)",
        "version": "Standard",
        "accelerated": False,
    }


# ── Cryptography Bridge ───────────────────────────────────────────
def fast_public_key_to_address(public_key_hex: str) -> Optional[str]:
    """Derives BCT address using Rust native engine or Python OpenSSL fallback."""
    if is_rust_accelerated():
        try:
            # If Rust engine returns None/empty, key is invalid; do NOT fall back to Python!
            res = _RUST_CORE.public_key_to_address(public_key_hex)
            return res if res else None
        except Exception:
            return None

    # Python Fallback
    try:
        from core.wallet import public_key_to_address as py_addr
        res = py_addr(public_key_hex)
        return res if res else None
    except Exception:
        return None


def fast_verify_signature(public_key_hex: str, message: str, signature_hex: str) -> bool:
    """Verifies SECP256k1 Low-S signature using Rust native engine or Python OpenSSL fallback."""
    if is_rust_accelerated():
        try:
            return bool(_RUST_CORE.verify_signature(public_key_hex, message, signature_hex))
        except Exception:
            pass

    from core.wallet import verify_signature as py_verify
    return py_verify(public_key_hex, message, signature_hex)


def fast_batch_verify_signatures(items: List[Tuple[str, str, str]]) -> List[bool]:
    """
    Batch verifies multiple SECP256k1 signatures in parallel across all CPU cores.
    Uses native Rust Rayon parallel iterator if available, or Python OpenSSL fallback.
    """
    if is_rust_accelerated():
        try:
            return list(_RUST_CORE.batch_verify_signatures(items))
        except Exception:
            pass

    from core.wallet import verify_signature as py_verify
    return [py_verify(pub, data, sig) for (pub, data, sig) in items]


HEX_64_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
MAX_SPV_DEPTH = 32


def fast_verify_spv_proof(target_hash: str, merkle_root: str, proof_steps: List[Tuple[str, str]]) -> bool:
    """Verifies SPV Merkle inclusion proof in microseconds using Rust engine or Python fallback."""
    t_clean = (target_hash or "").strip().lower()
    r_clean = (merkle_root or "").strip().lower()

    if not HEX_64_PATTERN.match(t_clean) or not HEX_64_PATTERN.match(r_clean):
        return False

    # Empty blocks have a root of 64 zeros and contain no transactions.
    # An all-zero hash is also not a valid transaction hash.
    empty_sentinel = "0" * 64
    if r_clean == empty_sentinel or t_clean == empty_sentinel:
        return False

    if not proof_steps:
        # In single-transaction blocks, leaf == root (proof path is empty)
        return t_clean == r_clean

    # DoS protection: prevent unbounded proof steps
    if len(proof_steps) > MAX_SPV_DEPTH:
        return False

    for direction, sibling in proof_steps:
        d = str(direction).strip().lower()
        s = str(sibling).strip().lower()
        if d not in ("left", "right") or not HEX_64_PATTERN.match(s):
            return False

    if is_rust_accelerated():
        try:
            return bool(_RUST_CORE.verify_spv_proof(t_clean, r_clean, proof_steps))
        except Exception:
            pass

    current = t_clean
    for direction, sibling in proof_steps:
        sib = str(sibling).strip().lower()
        d = str(direction).strip().lower()
        # Enforce solitary leaf direction: duplicated odd leaf must be on the right
        if sib == current and d != "right":
            return False
        if d == "left":
            combined = (sib + current).encode("utf-8")
        else:
            combined = (current + sib).encode("utf-8")
        current = hashlib.sha256(combined).hexdigest()

    return current == r_clean


# ── Merkle Tree Bridge ────────────────────────────────────────────
def fast_compute_merkle_root(tx_hashes: List[str]) -> str:
    """Computes SHA-256 Merkle root using Rust native engine or Python fallback (CVE-2012-2459 protected)."""
    if not tx_hashes:
        return "0" * 64

    clean_hashes = [str(h).strip().lower() for h in tx_hashes]
    if any(not HEX_64_PATTERN.match(h) for h in clean_hashes):
        raise ValueError("Invalid transaction hash format in Merkle tree")

    # CVE-2012-2459: Block must not contain duplicate transaction hashes
    if len(clean_hashes) != len(set(clean_hashes)):
        raise ValueError("CVE-2012-2459: Duplicate transaction hashes in block")

    if is_rust_accelerated():
        try:
            return _RUST_CORE.compute_merkle_root(clean_hashes)
        except ValueError:
            raise
        except Exception:
            pass

    level = clean_hashes
    while len(level) > 1:
        next_level = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else level[i]
            combined = (left + right).encode("utf-8")
            next_level.append(hashlib.sha256(combined).hexdigest())
        level = next_level

    return level[0]


# ── PoW Mining Bridge ─────────────────────────────────────────────
def fast_solve_pow(
    candidate: dict,
    target_difficulty: int,
    max_nonces: int = 1_000_000,
    start_nonce: int = 0
) -> Tuple[bool, int, str, float]:
    """
    Parallel PoW mining using Rust native multi-threaded engine or CPU/GPU fallback.
    Immune to magic nonce splitting DoS (LT-POW-01) and redundant chunk re-computation (BUG-01).
    Supports start_nonce parameter to avoid re-scanning identical nonce ranges (AUD14-03).
    """
    try:
        target_diff = int(target_difficulty)
        if target_diff < 1 or target_diff > 64:
            return False, 0, "", 0.0
    except Exception:
        return False, 0, "", 0.0
    max_n = max(1, int(max_nonces))
    s_nonce = max(0, int(start_nonce))
    if is_rust_accelerated():
        try:
            dummy = dict(candidate)
            sentinel = f"__BCT_NONCE_{secrets.token_hex(16)}__"
            dummy["nonce"] = sentinel
            serialized = json.dumps(dummy, sort_keys=True)
            target_token = f'"nonce": "{sentinel}"'
            token_pos = serialized.find(target_token)
            if token_pos != -1:
                prefix = serialized[:token_pos + len('"nonce": ')]
                suffix = serialized[token_pos + len(target_token):]
                ok, nonce, h, hr = _RUST_CORE.solve_pow(prefix, suffix, target_diff, max_n, s_nonce)
                # Rust successfully scanned s_nonce..(s_nonce + max_n). Return result directly without redundant re-runs.
                return bool(ok), int(nonce), str(h), float(hr)
        except Exception:
            pass

    # AUD12-07 & AUD14-03: Use singleton shared miner engine with start_nonce support
    miner = get_shared_miner_engine()
    return miner.solve_pow(candidate, target_diff, max_n, start_nonce=s_nonce)


_SHARED_MINER = None
_SHARED_MINER_LOCK = threading.Lock()


def get_shared_miner_engine():
    """Returns singleton instance of LockTraceMinerEngine, eliminating driver re-init overhead."""
    global _SHARED_MINER
    if _SHARED_MINER is None:
        with _SHARED_MINER_LOCK:
            if _SHARED_MINER is None:
                from core.gpu_miner import LockTraceMinerEngine
                _SHARED_MINER = LockTraceMinerEngine(preferred_engine="auto")
    return _SHARED_MINER

