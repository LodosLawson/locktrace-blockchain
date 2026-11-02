"""
BlockChainT - Cüzdan Yönetimi (BIP-39 Mnemonic Destekli)
=========================================================
ECDSA SECP256k1 anahtar çifti + BIP-39 12-kelimelik Mnemonic Kurtarma Sistemi.
"""

import hashlib
import binascii
from ecdsa import SigningKey, VerifyingKey, SECP256k1, BadSignatureError
from ecdsa.util import sigencode_string, sigdecode_string
from core.mnemonic import generate_mnemonic, mnemonic_to_private_key, validate_mnemonic


class Wallet:
    """ECDSA + BIP-39 Seed tabanlı blockchain cüzdanı."""

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
            # Yeni cüzdan: 12 kelimelik mnemonic üret ve anahtarı türet
            self.mnemonic = generate_mnemonic()
            pk_hex = mnemonic_to_private_key(self.mnemonic)
            self.private_key = SigningKey.from_string(
                binascii.unhexlify(pk_hex), curve=SECP256k1
            )

        self.public_key = self.private_key.get_verifying_key()
        self.address = self._generate_address()

    def _generate_address(self) -> str:
        """Public key'den benzersiz adres üret (çift SHA-256, ilk 40 karakter)."""
        pub_bytes = self.public_key.to_string()
        first_hash = hashlib.sha256(pub_bytes).hexdigest()
        second_hash = hashlib.sha256(first_hash.encode()).hexdigest()
        return f"BCT{second_hash[:40]}"

    def sign(self, data: str) -> str:
        """Veriyi private key ile deterministik SHA-256 ECDSA (SECP256k1) olarak imzala."""
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
    """Private key'den cüzdan geri yükle."""
    return Wallet(private_key_hex=private_key_hex)


def restore_wallet_from_mnemonic(mnemonic: str) -> Wallet:
    """12 kelimelik mnemonic kurtarma ifadesinden cüzdan geri yükle."""
    return Wallet(mnemonic=mnemonic)


def _normalize_uncompressed_pubkey_bytes(public_key_hex: str) -> bytes:
    """64-bayt ham (x||y) veya 65-bayt (04||x||y) açık anahtarı 64 bayta normalize et."""
    clean = (public_key_hex or "").strip()
    if clean.startswith("0x") or clean.startswith("0X"):
        clean = clean[2:]
    raw = binascii.unhexlify(clean)
    if len(raw) == 65 and raw[0] == 0x04:
        return raw[1:]
    return raw


def public_key_to_address(public_key_hex: str) -> str:
    """Public key hex dizgesinden deterministik BCT cüzdan adresi üret ve doğrula."""
    try:
        pub_bytes = _normalize_uncompressed_pubkey_bytes(public_key_hex)
        if len(pub_bytes) != 64:
            return ""
        # SECP256k1 eğrisi üzerinde geçerli bir nokta olduğunu doğrula
        VerifyingKey.from_string(pub_bytes, curve=SECP256k1)
        first_hash = hashlib.sha256(pub_bytes).hexdigest()
        second_hash = hashlib.sha256(first_hash.encode()).hexdigest()
        return f"BCT{second_hash[:40]}"
    except Exception:
        return ""


def verify_signature(public_key_hex: str, data: str, signature_hex: str) -> bool:
    """SECP256k1 ECDSA imzasını doğrula (SHA-256 birincil, eski SHA-1 geriye dönük uyumlu)."""
    try:
        pub_bytes = _normalize_uncompressed_pubkey_bytes(public_key_hex)
        if len(pub_bytes) != 64:
            return False
        pub_key = VerifyingKey.from_string(pub_bytes, curve=SECP256k1)
        clean_sig = (signature_hex or "").strip()
        if clean_sig.startswith("0x") or clean_sig.startswith("0X"):
            clean_sig = clean_sig[2:]
        sig_bytes = binascii.unhexlify(clean_sig)
        msg_bytes = data.encode("utf-8")

        # 1) Modern SHA-256 ECDSA (Tarayıcı Non-Custodial & v1.3+ Sunucu İmzaları)
        try:
            if pub_key.verify(sig_bytes, msg_bytes, hashfunc=hashlib.sha256, sigdecode=sigdecode_string):
                return True
        except BadSignatureError:
            pass

        # 2) Geriye dönük uyumluluk: Eski ecdsa varsayılanı (SHA-1)
        return pub_key.verify(sig_bytes, msg_bytes, sigdecode=sigdecode_string)
    except (BadSignatureError, Exception):
        return False
