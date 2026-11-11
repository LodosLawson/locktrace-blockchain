"""
LockTrace Native Acceleration Bridge (Python <-> Rust / PyO3)
==============================================================
Dual-Engine Architecture:
- If `locktrace_rs` (compiled Rust native extension) is present:
    routes cryptographic, Merkle, and PoW calculations directly to native Rust.
- If `locktrace_rs` is not compiled/available:
    seamlessly falls back to optimized Python OpenSSL implementations with zero downtime.
"""

import json
import hashlib
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
def fast_public_key_to_address(public_key_hex: str) -> str:
    """Derives BCT address using Rust native engine or Python OpenSSL fallback."""
    if is_rust_accelerated():
        try:
            addr = _RUST_CORE.public_key_to_address(public_key_hex)
            if addr:
                return addr
        except Exception:
            pass

    # Python Fallback
    try:
        from core.wallet import public_key_to_address as py_addr
        return py_addr(public_key_hex)
    except Exception:
        clean = (public_key_hex or "").strip().lower()
        if clean.startswith("04") and len(clean) == 130:
            clean = clean[2:]
        b = bytes.fromhex(clean)
        h1 = hashlib.sha256(b).hexdigest()
        h2 = hashlib.sha256(h1.encode()).hexdigest()
        return f"BCT{h2[:40]}"


def fast_verify_signature(public_key_hex: str, message: str, signature_hex: str) -> bool:
    """Verifies SECP256k1 Low-S signature using Rust native engine or Python OpenSSL fallback."""
    if is_rust_accelerated():
        try:
            return bool(_RUST_CORE.verify_signature(public_key_hex, message, signature_hex))
        except Exception:
            pass

    from core.wallet import verify_signature as py_verify
    return py_verify(public_key_hex, message, signature_hex)


# ── Merkle Tree Bridge ────────────────────────────────────────────
def fast_compute_merkle_root(tx_hashes: List[str]) -> str:
    """Computes SHA-256 Merkle root using Rust native engine or Python fallback."""
    if is_rust_accelerated():
        try:
            return _RUST_CORE.compute_merkle_root(tx_hashes)
        except Exception:
            pass

    if not tx_hashes:
        return "0" * 64

    level = [str(h).strip().lower() for h in tx_hashes]
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
    max_nonces: int = 1_000_000
) -> Tuple[bool, int, str, float]:
    """
    Parallel PoW mining using Rust native multi-threaded engine or CPU/GPU fallback.
    """
    if is_rust_accelerated():
        try:
            dummy = dict(candidate)
            dummy["nonce"] = 777777777777
            serialized = json.dumps(dummy, sort_keys=True)
            parts = serialized.split("777777777777")
            if len(parts) == 2:
                ok, nonce, h, hr = _RUST_CORE.solve_pow(parts[0], parts[1], int(target_difficulty), int(max_nonces))
                if ok and h:
                    return True, int(nonce), str(h), float(hr)
        except Exception:
            pass

    from core.gpu_miner import LockTraceMinerEngine
    miner = LockTraceMinerEngine(preferred_engine="auto")
    return miner.solve_pow(candidate, target_difficulty, max_nonces)

