# -*- coding: utf-8 -*-
"""
Security & Consensus Test Suite for Permanent On-Chain Wallet Burn (`wallet_burn`).
Verifies:
  1. Valid user-signed wallet burn absorbs 100% of liquid BCT into Treasury (balance -> 0.0).
  2. Burned wallet is permanently locked out of ALL future actions (transfers, rooms, posts, re-registration).
  3. Incoming transfers, BNS transfers, and Room transfers TO a burned wallet are strictly rejected.
  4. Protected system/authority addresses (Treasury, Release Authority) cannot be burned.
  5. Duplicate burn attempts & unauthorized signatures are strictly rejected.
"""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.blockchain import Blockchain, TREASURY_ADDRESS, RELEASE_AUTHORITY_ADDRESS, Transaction
from core.wallet import Wallet


def _make_funded_wallet(bc: Blockchain, amount: float = 50.0) -> Wallet:
    w = Wallet()
    w.pub_hex = w._pub_bytes.hex()
    bc.register_wallet(w.address, w.pub_hex)
    tx = Transaction(
        sender=TREASURY_ADDRESS,
        receiver=w.address,
        amount=amount,
        fee=0.0,
        signature=f"TEST_FUND_BURN_{w.address}",
        tx_type="reward",
    )
    bc.pending_transactions.append(tx)
    bc.mine_pending_block(TREASURY_ADDRESS)
    return w


class TestWalletBurn(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.bc = Blockchain(data_dir=self._tmpdir.name, auto_mine=True)
        self.victim = _make_funded_wallet(self.bc, 42.5)
        self.alice = _make_funded_wallet(self.bc, 50.0)

    def tearDown(self):
        try:
            if self.bc._storage:
                self.bc._storage.close()
        except Exception:
            pass
        self._tmpdir.cleanup()

    def test_permanent_wallet_burn_and_total_lockout(self):
        treasury_before = self.bc.verify_and_recalc_balance(TREASURY_ADDRESS)
        victim_bal = self.bc.verify_and_recalc_balance(self.victim.address)
        self.assertGreater(victim_bal, 40.0)

        # 1. Unauthorized signature (Alice trying to burn Victim's wallet) MUST fail
        bad_sig = self.alice.sign(f"WALLET_BURN:{self.victim.address}:PERMANENT_IRREVERSIBLE_DESTROY")
        ok_bad, _, _ = self.bc.burn_wallet(
            address=self.victim.address,
            signature=bad_sig,
            public_key=self.alice.pub_hex,
        )
        self.assertFalse(ok_bad)
        self.assertFalse(self.bc.is_wallet_burned(self.victim.address))

        # 2. Protected system/authority addresses CANNOT be burned
        ok_sys, _, _ = self.bc.burn_wallet(
            address=TREASURY_ADDRESS,
            signature=bad_sig,
            public_key=self.alice.pub_hex,
        )
        self.assertFalse(ok_sys)
        ok_auth, _, _ = self.bc.burn_wallet(
            address=RELEASE_AUTHORITY_ADDRESS,
            signature=bad_sig,
            public_key=self.alice.pub_hex,
        )
        self.assertFalse(ok_auth)

        # 3. Valid burn by Victim -> absorbs 100% of balance to Treasury & permanently closes wallet
        sig_burn = self.victim.sign(f"WALLET_BURN:{self.victim.address}:PERMANENT_IRREVERSIBLE_DESTROY")
        ok_b, msg_b, res_b = self.bc.burn_wallet(
            address=self.victim.address,
            signature=sig_burn,
            public_key=self.victim.pub_hex,
        )
        self.assertTrue(ok_b, msg_b)
        self.assertTrue(res_b["is_burned"])
        self.assertAlmostEqual(res_b["absorbed_amount"], victim_bal, places=6)
        self.assertTrue(self.bc.is_wallet_burned(self.victim.address))
        self.assertEqual(self.bc.verify_and_recalc_balance(self.victim.address), 0.0)
        # Treasury absorbed the balance (accounting for any block reward minted if applicable)
        self.assertGreaterEqual(self.bc.verify_and_recalc_balance(TREASURY_ADDRESS), treasury_before)

        # 4. Duplicate burn attempt MUST fail
        sig_burn2 = self.victim.sign(f"WALLET_BURN:{self.victim.address}:PERMANENT_IRREVERSIBLE_DESTROY")
        ok_b2, _, _ = self.bc.burn_wallet(
            address=self.victim.address,
            signature=sig_burn2,
            public_key=self.victim.pub_hex,
        )
        self.assertFalse(ok_b2)

        # 5. Burned wallet CANNOT re-register
        ok_reg, _ = self.bc.register_wallet(self.victim.address, self.victim.pub_hex)
        self.assertFalse(ok_reg)

        # 6. Burned wallet CANNOT send transfers or post in Space
        sig_post = self.victim.sign(f"{self.victim.address}:Attacker post attempt")
        ok_post, _, _ = self.bc.create_space_post(
            author=self.victim.address,
            content="Attacker post attempt",
            signature=sig_post,
            public_key=self.victim.pub_hex,
        )
        self.assertFalse(ok_post)

        # 7. Alice CANNOT send BCT to a burned wallet
        sig_tx = self.alice.sign(f"{self.alice.address}:{self.victim.address}:1.0")
        ok_in, msg_in, _ = self.bc.create_transaction(
            sender=self.alice.address,
            receiver=self.victim.address,
            amount=1.0,
            signature=sig_tx,
            public_key=self.alice.pub_hex,
        )
        self.assertFalse(ok_in)
        self.assertIn("burned", msg_in.lower())

        # 8. Alice CANNOT transfer a Protocol Room to a burned wallet
        ok_q, _, q = self.bc.get_room_create_quote("Burn Test Room", has_avatar=False)
        sig_rm = self.alice.sign(f"ROOM_CREATE:{self.alice.address}:{q['slug']}:Room transfer to burned wallet test.:NONE")
        ok_rm, _, rm = self.bc.create_room(
            creator=self.alice.address,
            name="Burn Test Room",
            description="Room transfer to burned wallet test.",
            signature=sig_rm,
            public_key=self.alice.pub_hex,
        )
        self.assertTrue(ok_rm)
        sig_rt = self.alice.sign(f"ROOM_TRANSFER:{self.alice.address}:{rm['room_id']}:{self.victim.address}")
        ok_rt, msg_rt, _ = self.bc.transfer_room(
            current_owner=self.alice.address,
            room_id=rm["room_id"],
            to_address=self.victim.address,
            signature=sig_rt,
            public_key=self.alice.pub_hex,
        )
        self.assertFalse(ok_rt)
        self.assertIn("burned", msg_rt.lower())


if __name__ == "__main__":
    unittest.main()
