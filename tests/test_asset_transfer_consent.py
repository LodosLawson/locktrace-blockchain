import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.blockchain import (
    ATOMIC_UNIT,
    TREASURY_ADDRESS,
    Blockchain,
    Transaction,
)
from core.wallet import Wallet

INITIAL_SUPPLY = 1_000_000_000_000


def _make_funded_wallet(bc: Blockchain, amount: float) -> Wallet:
    w = Wallet()
    w.pub_hex = w._pub_bytes.hex()
    bc.register_wallet(w.address, w.pub_hex)
    tx = Transaction(
        sender=TREASURY_ADDRESS,
        receiver=w.address,
        amount=amount,
        fee=0.0,
        signature=f"TEST_FUND_CONSENT_{w.address}_{amount}",
        tx_type="reward",
    )
    bc.pending_transactions.append(tx)
    bc.mine_pending_block(TREASURY_ADDRESS)
    return w


class TestTwoStepAssetTransferConsent(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.bc = Blockchain(data_dir=self.tmp_dir.name)
        self.alice = _make_funded_wallet(self.bc, 3000.0)
        self.bob = _make_funded_wallet(self.bc, 200.0)
        self.charlie = _make_funded_wallet(self.bc, 200.0)

    def tearDown(self):
        try:
            if hasattr(self.bc, "storage") and hasattr(self.bc.storage, "close"):
                self.bc.storage.close()
        except Exception:
            pass
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def _assert_zero_drift(self):
        self.bc._ensure_ledger_index()
        total_non_genesis = sum(
            u for k, u in self.bc._unit_balances_map.items()
            if k not in ("GENESIS", "GENESIS_VAULT")
        )
        expected = int(round(INITIAL_SUPPLY * ATOMIC_UNIT))
        self.assertEqual(total_non_genesis, expected)

    def test_room_propose_reject_and_unauthorized_accept_blocked(self):
        """Recipient can reject unwanted rooms with 0 fee; 3rd party & sender cannot accept."""
        # Alice creates a room
        r_pl = f"ROOM_CREATE:{self.alice.address}:CryptoHub:Test desc"
        ok, msg, room_res = self.bc.create_room(
            creator=self.alice.address,
            name="CryptoHub",
            description="Test desc",
            signature=self.alice.sign(r_pl),
            public_key=self.alice.pub_hex,
            signed_payload=r_pl,
        )
        self.assertTrue(ok, msg)
        rid = room_res["room_id"]
        self.bc.mine_pending_block(TREASURY_ADDRESS)

        alice_bal_before = self.bc.verify_and_recalc_units(self.alice.address)

        # Alice proposes transferring room to Bob
        t_pl = f"ROOM_TRANSFER:{self.alice.address}:{rid}:{self.bob.address}"
        ok, msg, prop = self.bc.propose_asset_transfer(
            asset_type="room",
            asset_id=rid,
            from_address=self.alice.address,
            to_address=self.bob.address,
            signature=self.alice.sign(t_pl),
            public_key=self.alice.pub_hex,
            signed_payload=t_pl,
        )
        self.assertTrue(ok, msg)
        prop_id = prop["proposal_id"]

        # Ownership has NOT changed yet and NO fee was charged!
        self.assertEqual(self.bc.rooms[rid]["creator"], self.alice.address)
        self.assertEqual(self.bc.verify_and_recalc_units(self.alice.address), alice_bal_before)

        # Duplicate pending proposal for same room MUST be rejected
        t_pl2 = f"ROOM_TRANSFER:{self.alice.address}:{rid}:{self.charlie.address}"
        ok_dup, _, _ = self.bc.propose_asset_transfer(
            "room", rid, self.alice.address, self.charlie.address, self.alice.sign(t_pl2), self.alice.pub_hex, t_pl2
        )
        self.assertFalse(ok_dup)

        # Charlie (unauthorized 3rd party) cannot accept Bob's proposal
        c_pl = f"ASSET_TRANSFER_ACCEPT:{self.charlie.address}:{prop_id}"
        ok_c, _, _ = self.bc.accept_asset_transfer(prop_id, self.charlie.address, self.charlie.sign(c_pl), self.charlie.pub_hex, c_pl)
        self.assertFalse(ok_c)

        # Alice (sender) cannot accept her own proposal
        a_pl = f"ASSET_TRANSFER_ACCEPT:{self.alice.address}:{prop_id}"
        ok_a, _, _ = self.bc.accept_asset_transfer(prop_id, self.alice.address, self.alice.sign(a_pl), self.alice.pub_hex, a_pl)
        self.assertFalse(ok_a)

        # Bob rejects the unwanted room -> 0 fee charged, room stays with Alice
        rej_pl = f"ASSET_TRANSFER_REJECT:{self.bob.address}:{prop_id}"
        ok_rej, msg_rej, _ = self.bc.reject_asset_transfer(prop_id, self.bob.address, self.bob.sign(rej_pl), self.bob.pub_hex, rej_pl)
        self.assertTrue(ok_rej, msg_rej)
        self.assertEqual(self.bc.rooms[rid]["creator"], self.alice.address)
        self.assertEqual(self.bc.verify_and_recalc_units(self.alice.address), alice_bal_before)

        # Bob cannot later accept an already-rejected proposal
        acc_pl = f"ASSET_TRANSFER_ACCEPT:{self.bob.address}:{prop_id}"
        ok_late, _, _ = self.bc.accept_asset_transfer(prop_id, self.bob.address, self.bob.sign(acc_pl), self.bob.pub_hex, acc_pl)
        self.assertFalse(ok_late)

        self._assert_zero_drift()

    def test_post_royalty_and_bulk_propose_cancel_and_accept_with_persistence(self):
        """Tests Space Post Royalty (single + bulk 1,000 BCT) propose, SQLite reload persistence, cancel, and accept."""
        # Alice creates 2 posts
        p1_pl = f"{self.alice.address}:Post One"
        ok, _, r1 = self.bc.create_space_post(self.alice.address, "Post One", self.alice.sign(p1_pl), self.alice.pub_hex, p1_pl)
        self.assertTrue(ok)
        pid1 = r1["post_id"]
        p2_pl = f"{self.alice.address}:Post Two"
        ok, _, r2 = self.bc.create_space_post(self.alice.address, "Post Two", self.alice.sign(p2_pl), self.alice.pub_hex, p2_pl)
        self.assertTrue(ok)
        pid2 = r2["post_id"]
        self.bc.mine_pending_block(TREASURY_ADDRESS)

        # Propose single post royalty transfer -> then sender cancels
        s_pl = f"POST_ROYALTY_TRANSFER:{self.alice.address}:{pid1}:{self.bob.address}"
        ok, msg, prop1 = self.bc.propose_asset_transfer(
            "post_royalty", pid1, self.alice.address, self.bob.address, self.alice.sign(s_pl), self.alice.pub_hex, s_pl
        )
        self.assertTrue(ok, msg)
        c_pl = f"ASSET_TRANSFER_CANCEL:{self.alice.address}:{prop1['proposal_id']}"
        ok_can, _, _ = self.bc.cancel_asset_transfer(prop1["proposal_id"], self.alice.address, self.alice.sign(c_pl), self.alice.pub_hex, c_pl)
        self.assertTrue(ok_can)

        # Propose Bulk All Royalty Transfer (1,000 BCT) -> verify durable SQLite persistence across reload!
        b_pl = f"POST_ROYALTY_TRANSFER_ALL:{self.alice.address}:{self.bob.address}"
        ok, msg, prop_bulk = self.bc.propose_asset_transfer(
            "post_royalty_all", "ALL", self.alice.address, self.bob.address, self.alice.sign(b_pl), self.alice.pub_hex, b_pl
        )
        self.assertTrue(ok, msg)
        bulk_id = prop_bulk["proposal_id"]

        # Reload Blockchain fresh from SQLite to confirm proposal survived restart
        bc_reloaded = Blockchain(data_dir=self.tmp_dir.name)
        pend = bc_reloaded.get_pending_asset_transfers(self.bob.address)
        self.assertEqual(pend["pending_incoming_count"], 1)
        self.assertEqual(pend["incoming"][0]["proposal_id"], bulk_id)

        # Bob accepts the bulk royalty transfer!
        alice_pre = bc_reloaded.verify_and_recalc_units(self.alice.address)
        acc_pl = f"ASSET_TRANSFER_ACCEPT:{self.bob.address}:{bulk_id}"
        ok_acc, msg_acc, res_acc = bc_reloaded.accept_asset_transfer(
            bulk_id, self.bob.address, self.bob.sign(acc_pl), self.bob.pub_hex, acc_pl
        )
        self.assertTrue(ok_acc, msg_acc)
        self.assertEqual(res_acc["execution"]["transferred_count"], 2)
        self.assertEqual(alice_pre - bc_reloaded.verify_and_recalc_units(self.alice.address), int(round(1000.0 * ATOMIC_UNIT)))

        # Verify Bob is now the royalty_owner of both posts
        self.assertEqual(bc_reloaded.get_space_post(pid1)["royalty_owner"], self.bob.address)
        self.assertEqual(bc_reloaded.get_space_post(pid2)["royalty_owner"], self.bob.address)

        try:
            bc_reloaded.storage.close()
        except Exception:
            pass
        self._assert_zero_drift()


if __name__ == "__main__":
    unittest.main()
