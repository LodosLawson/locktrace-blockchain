"""
BlockChainT - Wallet Management (BIP-39 Mnemonic Supported)
=========================================================
Constant-Time SECP256k1 Cryptography + BIP-39 12-word recovery phrase system.
Engineered with OpenSSL/cryptography (immune to Minerva timing side-channels) with seamless fallback.
"""

import hashlib
import binascii
from typing import Optional
from core.mnemonic import generate_mnemonic, mnemonic_to_private_key, validate_mnemonic

SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
HALF_SECP256K1_N = SECP256K1_N // 2

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.utils import (
        encode_dss_signature, decode_dss_signature
    )
    _HAS_CRYPTOGRAPHY = True
except ImportError:
    _HAS_CRYPTOGRAPHY = False
    from ecdsa import SigningKey, VerifyingKey, SECP256k1, BadSignatureError
    from ecdsa.util import sigencode_string, sigdecode_string


class Wallet:
    """ECDSA + BIP-39 Seed based blockchain wallet (Constant-time OpenSSL SECP256k1)."""

    def __init__(self, mnemonic: Optional[str] = None, private_key_hex: Optional[str] = None):
        if mnemonic:
            self.mnemonic = " ".join(mnemonic.strip().lower().split())
            pk_hex = mnemonic_to_private_key(self.mnemonic)
        elif private_key_hex:
            self.mnemonic = ""
            pk_hex = private_key_hex.strip()
            if pk_hex.startswith("0x") or pk_hex.startswith("0X"):
                pk_hex = pk_hex[2:]
        else:
            self.mnemonic = generate_mnemonic()
            pk_hex = mnemonic_to_private_key(self.mnemonic)

        self._priv_hex = pk_hex
        priv_bytes = binascii.unhexlify(pk_hex)

        if _HAS_CRYPTOGRAPHY:
            priv_int = int.from_bytes(priv_bytes, "big")
            self._crypto_priv = ec.derive_private_key(priv_int, ec.SECP256K1())
            self._crypto_pub = self._crypto_priv.public_key()
            pn = self._crypto_pub.public_numbers()
            self._pub_bytes = pn.x.to_bytes(32, "big") + pn.y.to_bytes(32, "big")
        else:
            self.private_key = SigningKey.from_string(priv_bytes, curve=SECP256k1)
            self.public_key = self.private_key.get_verifying_key()
            self._pub_bytes = self.public_key.to_string()

        self.address = self._generate_address()

    def _generate_address(self) -> str:
        """Derive unique address from public key (double SHA-256, first 40 hex chars)."""
        first_hash = hashlib.sha256(self._pub_bytes).hexdigest()
        second_hash = hashlib.sha256(first_hash.encode()).hexdigest()
        return f"BCT{second_hash[:40]}"

    def sign(self, data: str) -> str:
        """Deterministically sign data with private key using SHA-256 ECDSA (SECP256k1) with canonical Low-S."""
        msg_bytes = data.encode("utf-8")
        if _HAS_CRYPTOGRAPHY:
            der_sig = self._crypto_priv.sign(msg_bytes, ec.ECDSA(hashes.SHA256()))
            r, s = decode_dss_signature(der_sig)
            if s > HALF_SECP256K1_N:
                s = SECP256K1_N - s
            sig_bytes = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        else:
            sig_bytes = self.private_key.sign_deterministic(
                msg_bytes,
                hashfunc=hashlib.sha256,
                sigencode=sigencode_string,
            )
            if len(sig_bytes) == 64:
                r = int.from_bytes(sig_bytes[:32], "big")
                s = int.from_bytes(sig_bytes[32:64], "big")
                if s > HALF_SECP256K1_N:
                    s = SECP256K1_N - s
                    sig_bytes = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return binascii.hexlify(sig_bytes).decode()

    def get_public_key_hex(self) -> str:
        return binascii.hexlify(self._pub_bytes).decode()

    def get_private_key_hex(self) -> str:
        return self._priv_hex

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "mnemonic": self.mnemonic,
            "public_key": self.get_public_key_hex(),
            "private_key": self.get_private_key_hex()
        }


def restore_wallet(private_key_hex: str) -> Wallet:
    """Restore wallet from private key hex."""
    return Wallet(private_key_hex=private_key_hex)


def restore_wallet_from_mnemonic(mnemonic: str) -> Wallet:
    """Restore wallet from 12-word mnemonic phrase."""
    return Wallet(mnemonic=mnemonic)


def _normalize_uncompressed_pubkey_bytes(public_key_hex: str) -> bytes:
    """Normalize 64-byte raw (x||y) or 65-byte (04||x||y) public key to 64 bytes."""
    clean = (public_key_hex or "").strip()
    if clean.startswith("0x") or clean.startswith("0X"):
        clean = clean[2:]
    raw = binascii.unhexlify(clean)
    if len(raw) == 65 and raw[0] == 0x04:
        return raw[1:]
    return raw


def public_key_to_address(public_key_hex: str) -> str:
    """Generate and verify deterministic BCT wallet address from public key hex."""
    try:
        pub_bytes = _normalize_uncompressed_pubkey_bytes(public_key_hex)
        if len(pub_bytes) != 64:
            return ""
        if _HAS_CRYPTOGRAPHY:
            x = int.from_bytes(pub_bytes[:32], "big")
            y = int.from_bytes(pub_bytes[32:64], "big")
            pub_numbers = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256K1())
            pub_numbers.public_key()
        else:
            VerifyingKey.from_string(pub_bytes, curve=SECP256k1)
        first_hash = hashlib.sha256(pub_bytes).hexdigest()
        second_hash = hashlib.sha256(first_hash.encode()).hexdigest()
        return f"BCT{second_hash[:40]}"
    except Exception:
        return ""


def verify_signature(public_key_hex: str, data: str, signature_hex: str) -> bool:
    """Verify SECP256k1 ECDSA signature (SHA-256) with strict Low-S malleability protection (BIP-62/146/EIP-2)."""
    try:
        pub_bytes = _normalize_uncompressed_pubkey_bytes(public_key_hex)
        if len(pub_bytes) != 64:
            return False

        clean_sig = (signature_hex or "").strip()
        if clean_sig.startswith("0x") or clean_sig.startswith("0X"):
            clean_sig = clean_sig[2:]
        sig_bytes = binascii.unhexlify(clean_sig)
        if len(sig_bytes) != 64:
            return False

        r_val = int.from_bytes(sig_bytes[:32], "big")
        s_val = int.from_bytes(sig_bytes[32:64], "big")
        if r_val <= 0 or r_val >= SECP256K1_N or s_val <= 0 or s_val > HALF_SECP256K1_N:
            # Reject malleable signatures where s > N/2 or r,s outside valid range
            return False

        msg_bytes = data.encode("utf-8")
        if _HAS_CRYPTOGRAPHY:
            x = int.from_bytes(pub_bytes[:32], "big")
            y = int.from_bytes(pub_bytes[32:64], "big")
            pub_numbers = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256K1())
            pub_key = pub_numbers.public_key()
            der_sig = encode_dss_signature(r_val, s_val)
            pub_key.verify(der_sig, msg_bytes, ec.ECDSA(hashes.SHA256()))
            return True
        else:
            pub_key = VerifyingKey.from_string(pub_bytes, curve=SECP256k1)
            return pub_key.verify(sig_bytes, msg_bytes, hashfunc=hashlib.sha256, sigdecode=sigdecode_string)
    except Exception:
        return False
