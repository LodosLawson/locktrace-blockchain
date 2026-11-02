"""
BlockChainT - Cüzdan Yönetimi
==============================
ECDSA SECP256k1 anahtar çifti ile güvenli cüzdan oluşturma.
Bitcoin ile aynı eğriyi kullanır.
"""

import hashlib
import binascii
from ecdsa import SigningKey, VerifyingKey, SECP256k1, BadSignatureError


class Wallet:
    """ECDSA tabanlı blockchain cüzdanı."""

    def __init__(self):
        self.private_key = SigningKey.generate(curve=SECP256k1)
        self.public_key = self.private_key.get_verifying_key()
        self.address = self._generate_address()

    def _generate_address(self) -> str:
        """Public key'den benzersiz adres üret (çift SHA-256, ilk 40 karakter)."""
        pub_bytes = self.public_key.to_string()
        first_hash = hashlib.sha256(pub_bytes).hexdigest()
        second_hash = hashlib.sha256(first_hash.encode()).hexdigest()
        return f"BCT{second_hash[:40]}"

    def sign(self, data: str) -> str:
        """Veriyi private key ile imzala."""
        signature = self.private_key.sign(data.encode())
        return binascii.hexlify(signature).decode()

    def get_public_key_hex(self) -> str:
        return binascii.hexlify(self.public_key.to_string()).decode()

    def get_private_key_hex(self) -> str:
        return binascii.hexlify(self.private_key.to_string()).decode()

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "public_key": self.get_public_key_hex(),
            "private_key": self.get_private_key_hex()
        }


def restore_wallet(private_key_hex: str) -> Wallet:
    """Private key'den cüzdan geri yükle."""
    wallet = Wallet.__new__(Wallet)
    wallet.private_key = SigningKey.from_string(
        binascii.unhexlify(private_key_hex), curve=SECP256k1
    )
    wallet.public_key = wallet.private_key.get_verifying_key()
    wallet.address = wallet._generate_address()
    return wallet


def verify_signature(public_key_hex: str, data: str, signature_hex: str) -> bool:
    """İmzayı doğrula."""
    try:
        pub_bytes = binascii.unhexlify(public_key_hex)
        pub_key = VerifyingKey.from_string(pub_bytes, curve=SECP256k1)
        sig_bytes = binascii.unhexlify(signature_hex)
        return pub_key.verify(sig_bytes, data.encode())
    except (BadSignatureError, Exception):
        return False

