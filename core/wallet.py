"""
BlockChainT - Wallet Management (BIP-39 Mnemonic Supported)
=========================================================
ECDSA SECP256k1 key pairs + BIP-39 12-word recovery phrase system.
"""

import hashlib
import binascii
from ecdsa import SigningKey, VerifyingKey, SECP256k1, BadSignatureError
from ecdsa.util import sigencode_string, sigdecode_string
from core.mnemonic import generate_mnemonic, mnemonic_to_private_key, validate_mnemonic


class Wallet:
    """ECDSA + BIP-39 Seed based blockchain wallet."""

    def __init__(self, mnemonic: str = None, private_key_hex: str = None):
        if mnemonic:
            self.mnemonic = " ".join(mnemonic.strip().lower().split())
            pk_hex = mnemonic_to_private_key(self.mnemonic)
            self.private_key = SigningKey.from_string(
                binascii.unhexlify(pk_hex), curve=SECP256k1
            )
        elif private_key_hex:
            self.mnemonic = ""
            self.private_key = SigningKey.from_string(
                binascii.unhexlify(private_key_hex), curve=SECP256k1
            )
        else:
            # New wallet: generate 12-word mnemonic and derive key
            self.mnemonic = generate_mnemonic()
            pk_hex = mnemonic_to_private_key(self.mnemonic)
            self.private_key = SigningKey.from_string(
                binascii.unhexlify(pk_hex), curve=SECP256k1
            )

        self.public_key = self.private_key.get_verifying_key()
        self.address = self._generate_address()

    def _generate_address(self) -> str:
        """Derive unique address from public key (double SHA-256, first 40 hex chars)."""
        pub_bytes = self.public_key.to_string()
        first_hash = hashlib.sha256(pub_bytes).hexdigest()
        second_hash = hashlib.sha256(first_hash.encode()).hexdigest()
        return f"BCT{second_hash[:40]}"

    def sign(self, data: str) -> str:
        """Deterministically sign data with private key using SHA-256 ECDSA (SECP256k1)."""
        signature = self.private_key.sign_deterministic(
            data.encode("utf-8"),
            hashfunc=hashlib.sha256,
            sigencode=sigencode_string,
        )
        return binascii.hexlify(signature).decode()

    def get_public_key_hex(self) -> str:
        return binascii.hexlify(self.public_key.to_string()).decode()

    def get_private_key_hex(self) -> str:
        return binascii.hexlify(self.private_key.to_string()).decode()

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
        # Verify valid point on SECP256k1 curve
        VerifyingKey.from_string(pub_bytes, curve=SECP256k1)
        first_hash = hashlib.sha256(pub_bytes).hexdigest()
        second_hash = hashlib.sha256(first_hash.encode()).hexdigest()
        return f"BCT{second_hash[:40]}"
    except Exception:
        return ""


def verify_signature(public_key_hex: str, data: str, signature_hex: str) -> bool:
    """Verify SECP256k1 ECDSA signature (SHA-256)."""
    try:
        pub_bytes = _normalize_uncompressed_pubkey_bytes(public_key_hex)
        if len(pub_bytes) != 64:
            return False
        pub_key = VerifyingKey.from_string(pub_bytes, curve=SECP256k1)
        clean_sig = (signature_hex or "").strip()
        if clean_sig.startswith("0x") or clean_sig.startswith("0X"):
            clean_sig = clean_sig[2:]
        sig_bytes = binascii.unhexlify(clean_sig)
        # SECP256k1 grup mertebesi ve sıfır/aşım kontrolü (0 < r < n, 0 < s < n)
        if len(sig_bytes) == 64:
            r_val = int.from_bytes(sig_bytes[:32], "big")
            s_val = int.from_bytes(sig_bytes[32:64], "big")
            SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
            if r_val <= 0 or r_val >= SECP256K1_N or s_val <= 0 or s_val >= SECP256K1_N:
                return False
        msg_bytes = data.encode("utf-8")

        # Güvenli SHA-256 ECDSA doğrulaması
        return pub_key.verify(sig_bytes, msg_bytes, hashfunc=hashlib.sha256, sigdecode=sigdecode_string)
    except (BadSignatureError, Exception):
        return False
