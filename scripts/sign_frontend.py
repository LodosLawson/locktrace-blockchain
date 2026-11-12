#!/usr/bin/env python3
"""
LockTrace Official Frontend Checksum & ECDSA Release Signer (v2.8.4)
====================================================================
Generates canonical SHA-256 checksums, IPFS CIDv1 content identifiers,
and SECP256k1 ECDSA release signatures for `frontend/index.html` and `frontend/sw.js`.

Usage:
  Sign new release (requires ~/.locktrace/release_signing_key.json):
      python scripts/sign_frontend.py --version 2.8.4

  Verify existing local frontend integrity (public-key only, zero secrets needed):
      python scripts/sign_frontend.py --verify-only
"""

import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from core.wallet import Wallet, verify_signature, public_key_to_address

RELEASE_AUTHORITY_ADDRESS = "BCT885bc383a03ebed0aa11cedfbfac0d52be3d4080"
RELEASE_AUTHORITY_PUBKEY = (
    "5e3686d4e64119cc049dd966e57150a04db4160a335610c8740748ba618c0023"
    "21a5882ed90bfd5597bc144a7c4926369aec9b89070d3d337819d6626c67a150"
)


def canonical_file_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        raw = f.read()
    return raw.replace(b"\r\n", b"\n")


def compute_ipfs_cid_v1(sha256_hex: str) -> str:
    """Computes RFC-compliant IPFS CIDv1 (multibase base32 lowercase, raw codec 0x55, sha2-256 0x12 0x20)."""
    digest = bytes.fromhex(sha256_hex)
    cid_bytes = b"\x01\x55\x12\x20" + digest
    b32 = base64.b32encode(cid_bytes).decode("ascii").lower().rstrip("=")
    return f"b{b32}"


def verify_local_frontend() -> bool:
    index_path = os.path.join(ROOT_DIR, "frontend", "index.html")
    sw_path = os.path.join(ROOT_DIR, "frontend", "sw.js")
    manifest_path = os.path.join(ROOT_DIR, "frontend", "integrity.json")

    if not os.path.exists(index_path) or not os.path.exists(manifest_path):
        print("⛔ UYARI: Frontend veya integrity.json dosyası bulunamadı!")
        return False

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    actual_index_sha = hashlib.sha256(canonical_file_bytes(index_path)).hexdigest()
    actual_sw_sha = hashlib.sha256(canonical_file_bytes(sw_path)).hexdigest() if os.path.exists(sw_path) else ""

    pub = manifest.get("authority_public_key", "")
    sig = manifest.get("signature", "")
    ver = manifest.get("version", "")
    expected_index_sha = manifest.get("index_html_sha256") or manifest.get("index_sha256", "")
    expected_sw_sha = manifest.get("sw_js_sha256") or manifest.get("sw_sha256", "")
    expected_cid = manifest.get("ipfs_cid_v1", "")

    if pub != RELEASE_AUTHORITY_PUBKEY or public_key_to_address(pub) != RELEASE_AUTHORITY_ADDRESS:
        print("⛔ UYARI: İmza yetkili açık anahtarı (Release Authority) geçersiz!")
        return False

    canonical_msg = f"LOCKTRACE_FRONTEND_RELEASE:{ver}:{expected_index_sha}:{expected_sw_sha}:{expected_cid}"
    if not verify_signature(RELEASE_AUTHORITY_PUBKEY, canonical_msg, sig):
        print("⛔ UYARI: ECDSA sürüm imzası geçersiz! integrity.json manipüle edilmiş!")
        return False

    if actual_index_sha != expected_index_sha:
        print("⛔ UYARI: Bu frontend dosyası değiştirilmiş veya manipüle edilmiş! Çalıştırılamaz.")
        print(f"   Beklenen SHA-256 : {expected_index_sha}")
        print(f"   Mevcut SHA-256   : {actual_index_sha}")
        return False

    if expected_sw_sha and actual_sw_sha and actual_sw_sha != expected_sw_sha:
        print("⛔ UYARI: Service Worker (sw.js) dosyası değiştirilmiş veya manipüle edilmiş! Çalıştırılamaz.")
        return False

    print("✅ [DOĞRULANDI] LockTrace Frontend SHA-256 Checksum & ECDSA İmzası Geçerli!")
    print(f"   Sürüm            : v{ver}")
    print(f"   index.html SHA256: {actual_index_sha}")
    print(f"   IPFS CIDv1       : ipfs://{expected_cid}")
    print(f"   İmza Yetkilisi   : {RELEASE_AUTHORITY_ADDRESS}")
    return True


def sign_release(version: str, key_file: str):
    if not os.path.exists(key_file):
        raise FileNotFoundError(
            f"Release signing key not found at {key_file}. Only official release authority can sign builds."
        )

    with open(key_file, "r", encoding="utf-8") as f:
        key_data = json.load(f)

    signer = Wallet(private_key_hex=key_data["private_key"])
    if signer.get_public_key_hex() != RELEASE_AUTHORITY_PUBKEY or signer.address != RELEASE_AUTHORITY_ADDRESS:
        raise ValueError("Signing key does not match hardcoded RELEASE_AUTHORITY_PUBKEY!")

    index_path = os.path.join(ROOT_DIR, "frontend", "index.html")
    template_path = os.path.join(ROOT_DIR, "templates", "index.html")
    sw_path = os.path.join(ROOT_DIR, "frontend", "sw.js")
    manifest_path = os.path.join(ROOT_DIR, "frontend", "integrity.json")

    # Normalize frontend/index.html & sync templates/index.html to exact LF canonical bytes
    index_bytes = canonical_file_bytes(index_path)
    with open(index_path, "wb") as f:
        f.write(index_bytes)
    os.makedirs(os.path.dirname(template_path), exist_ok=True)
    with open(template_path, "wb") as f:
        f.write(index_bytes)

    sw_bytes = b""
    if os.path.exists(sw_path):
        sw_bytes = canonical_file_bytes(sw_path)
        with open(sw_path, "wb") as f:
            f.write(sw_bytes)
        template_sw_path = os.path.join(ROOT_DIR, "templates", "sw.js")
        with open(template_sw_path, "wb") as f:
            f.write(sw_bytes)

    # Sync frontend/manifest.json to templates/manifest.json
    manifest_pwa_path = os.path.join(ROOT_DIR, "frontend", "manifest.json")
    template_manifest_pwa = os.path.join(ROOT_DIR, "templates", "manifest.json")
    if os.path.exists(manifest_pwa_path):
        with open(manifest_pwa_path, "rb") as f:
            pwa_bytes = f.read()
        os.makedirs(os.path.dirname(template_manifest_pwa), exist_ok=True)
        with open(template_manifest_pwa, "wb") as f:
            f.write(pwa_bytes)

    index_sha256 = hashlib.sha256(index_bytes).hexdigest()
    sw_sha256 = hashlib.sha256(sw_bytes).hexdigest() if sw_bytes else ""
    ipfs_cid = compute_ipfs_cid_v1(index_sha256)

    canonical_payload = f"LOCKTRACE_FRONTEND_RELEASE:{version}:{index_sha256}:{sw_sha256}:{ipfs_cid}"
    signature = signer.sign(canonical_payload)

    assert verify_signature(RELEASE_AUTHORITY_PUBKEY, canonical_payload, signature), "Self-verification failed!"

    manifest = {
        "version": version,
        "released_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "authority_address": RELEASE_AUTHORITY_ADDRESS,
        "authority_public_key": RELEASE_AUTHORITY_PUBKEY,
        "index_html_sha256": index_sha256,
        "index_sha256": index_sha256,
        "sw_js_sha256": sw_sha256,
        "sw_sha256": sw_sha256,
        "ipfs_cid_v1": ipfs_cid,
        "canonical_payload": canonical_payload,
        "signature": signature,
    }

    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    with open(manifest_path, "wb") as f:
        f.write(manifest_bytes)
    template_manifest_path = os.path.join(ROOT_DIR, "templates", "integrity.json")
    os.makedirs(os.path.dirname(template_manifest_path), exist_ok=True)
    with open(template_manifest_path, "wb") as f:
        f.write(manifest_bytes)

    print("=" * 72)
    print(f" LOCKTRACE FRONTEND v{version} SIGNED & SEALED SUCCESSFULLY")
    print("=" * 72)
    print(f" index.html SHA-256 : {index_sha256}")
    print(f" sw.js SHA-256      : {sw_sha256}")
    print(f" IPFS CIDv1         : ipfs://{ipfs_cid}")
    print(f" Authority Address  : {RELEASE_AUTHORITY_ADDRESS}")
    print(f" ECDSA Signature    : {signature[:32]}...{signature[-16:]}")
    print("=" * 72)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LockTrace Frontend SHA-256 & ECDSA Release Signer")
    parser.add_argument("--version", default="2.8.4", help="Frontend release version string")
    parser.add_argument(
        "--key-file",
        default=os.path.expanduser("~/.locktrace/release_signing_key.json"),
        help="Path to Release Authority private key JSON",
    )
    parser.add_argument("--verify-only", action="store_true", help="Verify local frontend without signing")
    args = parser.parse_args()

    if args.verify_only:
        sys.exit(0 if verify_local_frontend() else 1)
    else:
        sign_release(args.version, args.key_file)

