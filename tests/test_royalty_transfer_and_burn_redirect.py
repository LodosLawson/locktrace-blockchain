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
    VALIDATOR_STAKE_VAULT_ADDRESS,
    Blockchain,
    Transaction,
)
from core.wallet import Wallet

INITIAL_SUPPLY = 1_000_000_000_000


def _make_funded_wallet(bc: Blockchain, amount: float = 50.0) -> Wallet:
    w = Wallet()
    w.pub_hex = w._pub_bytes.hex()
    bc.register_wallet(w.address, w.pub_hex)
    tx = Transaction(
        sender=TREASURY_ADDRESS,
        receiver=w.address,
        amount=amount,
        fee=0.0,
        signature=f"TEST_FUND_ROYALTY_{w.address}",
        tx_type="reward",
    )
    bc.pending_transactions.append(tx)
    bc.mine_pending_block(TREASURY_ADDRESS)
    return w


class TestRoyaltyTransferAndBurnRedirect(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.bc = Blockchain(data_dir=self.tmp_dir.name)

        self.wa = _make_funded_wallet(self.bc, 50.0)
        self.wb = _make_funded_wallet(self.bc, 50.0)
        self.wc = _make_funded_wallet(self.bc, 50.0)
        self.wx = _make_funded_wallet(self.bc, 50.0)

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
        self.assertEqual(
            total_non_genesis,
            expected,
            f"Supply conservation drift detected: {total_non_genesis - expected} atomic units",
        )

    def _create_post(self, w: Wallet, content: str) -> str:
        payload = f"{w.address}:{content}"
        sig = w.sign(payload)
        ok, msg, res = self.bc.create_space_post(
            author=w.address,
            content=content,
            signature=sig,
            public_key=w.pub_hex,
            signed_payload=payload,
        )
        self.assertTrue(ok, f"Post creation failed: {msg}")
        return res["post_id"]

    def _burn_wallet(self, w: Wallet):
        payload = f"WALLET_BURN:{w.address}:PERMANENT_IRREVERSIBLE_DESTROY"
        sig = w.sign(payload)
        ok, msg, _ = self.bc.burn_wallet(
            address=w.address,
            signature=sig,
            public_key=w.pub_hex,
            signed_payload=payload,
        )
        self.assertTrue(ok, f"Wallet burn failed: {msg}")
        self.assertTrue(self.bc.is_wallet_burned(w.address))

    def test_burned_wallet_royalties_redirect_to_treasury(self):
        """All Space & Follow royalties to a burned wallet MUST go to TREASURY, keeping burned balance at 0.0."""
        pid = self._create_post(self.wa, "Hello LockTrace v2.14.0!")
        self._burn_wallet(self.wa)

        self.assertEqual(self.bc.verify_and_recalc_balance(self.wa.address), 0.0)
        treasury_before = self.bc.verify_and_recalc_units(TREASURY_ADDRESS)

        # Wallet B likes A's post (0.01 BCT: 0.002 author_cut -> redirected to TREASURY + 0.007 treasury + 0.001 fee)
        like_payload = f"like:{self.wb.address}:{pid}"
        ok, msg, res_like = self.bc.like_space_post(
            liker=self.wb.address,
            post_id=pid,
            signature=self.wb.sign(like_payload),
            public_key=self.wb.pub_hex,
            signed_payload=like_payload,
        )
        self.assertTrue(ok, msg)
        self.assertTrue(res_like["royalty_redirected_to_treasury"])
        self.assertEqual(res_like["royalty_recipient"], TREASURY_ADDRESS)

        # Wallet B comments on A's post (0.02 BCT: 0.004 author_cut -> redirected to TREASURY)
        cmt_text = "Comment on burned author post"
        cmt_payload = f"{self.wb.address}:{pid}:{cmt_text}"
        ok, msg, res_cmt = self.bc.comment_space_post(
            commenter=self.wb.address,
            post_id=pid,
            content=cmt_text,
            signature=self.wb.sign(cmt_payload),
            public_key=self.wb.pub_hex,
            signed_payload=cmt_payload,
        )
        self.assertTrue(ok, msg)
        self.assertTrue(res_cmt["royalty_redirected_to_treasury"])
        self.assertEqual(res_cmt["royalty_recipient"], TREASURY_ADDRESS)

        # Wallet B follows burned A (1.00 BCT: 0.50 creator_cut -> redirected to TREASURY)
        fol_payload = f"follow:{self.wb.address}:{self.wa.address}"
        ok, msg, res_fol = self.bc.follow_creator(
            follower=self.wb.address,
            target=self.wa.address,
            signature=self.wb.sign(fol_payload),
            public_key=self.wb.pub_hex,
            signed_payload=fol_payload,
        )
        self.assertTrue(ok, msg)
        self.assertTrue(res_fol["royalty_redirected_to_treasury"])
        self.assertEqual(res_fol["royalty_recipient"], TREASURY_ADDRESS)

        # Burned wallet A must remain strictly 0.00000000 BCT
        self.assertEqual(self.bc.verify_and_recalc_balance(self.wa.address), 0.0)
        treasury_after = self.bc.verify_and_recalc_units(TREASURY_ADDRESS)
        self.assertGreaterEqual(treasury_after - treasury_before, int(round(1.03 * ATOMIC_UNIT)))

        # Enriched post metadata must explicitly report royalty_redirected_to_treasury = True
        post_meta = self.bc.get_space_post(pid)
        self.assertTrue(post_meta["royalty_redirected_to_treasury"])
        self._assert_zero_drift()

    def test_post_royalty_transfer_security_and_3_per_year_limit(self):
        """Tests authorization, anti-spoofing, burned target rejection, payout redirection, and 3/year hard cap."""
        pid = self._create_post(self.wa, "Transferable royalty post #BCT")
        self._burn_wallet(self.wx)

        # 1. Unauthorized transfer attempt by B (not holder) -> REJECT
        p1 = f"POST_ROYALTY_TRANSFER:{self.wb.address}:{pid}:{self.wc.address}"
        ok, _, _ = self.bc.transfer_post_royalty(self.wb.address, pid, self.wc.address, self.wb.sign(p1), self.wb.pub_hex, p1)
        self.assertFalse(ok)

        # 2. Self-transfer -> REJECT
        p2 = f"POST_ROYALTY_TRANSFER:{self.wa.address}:{pid}:{self.wa.address}"
        ok, _, _ = self.bc.transfer_post_royalty(self.wa.address, pid, self.wa.address, self.wa.sign(p2), self.wa.pub_hex, p2)
        self.assertFalse(ok)

        # 3. Transfer to system/vault addresses -> REJECT
        for sys_addr in (TREASURY_ADDRESS, VALIDATOR_STAKE_VAULT_ADDRESS):
            ps = f"POST_ROYALTY_TRANSFER:{self.wa.address}:{pid}:{sys_addr}"
            ok, _, _ = self.bc.transfer_post_royalty(self.wa.address, pid, sys_addr, self.wa.sign(ps), self.wa.pub_hex, ps)
            self.assertFalse(ok)

        # 4. Transfer to burned wallet X -> REJECT
        px = f"POST_ROYALTY_TRANSFER:{self.wa.address}:{pid}:{self.wx.address}"
        ok, _, _ = self.bc.transfer_post_royalty(self.wa.address, pid, self.wx.address, self.wa.sign(px), self.wa.pub_hex, px)
        self.assertFalse(ok)

        # 5. Tampered signature (signed for B, submitted for C) -> REJECT
        pt = f"POST_ROYALTY_TRANSFER:{self.wa.address}:{pid}:{self.wb.address}"
        ok, _, _ = self.bc.transfer_post_royalty(
            self.wa.address,
            pid,
            self.wc.address,
            self.wa.sign(pt),
            self.wa.pub_hex,
            f"POST_ROYALTY_TRANSFER:{self.wa.address}:{pid}:{self.wc.address}",
        )
        self.assertFalse(ok)

        # 6. Valid Transfer #1: A -> B
        t1 = f"POST_ROYALTY_TRANSFER:{self.wa.address}:{pid}:{self.wb.address}"
        ok, msg, r1 = self.bc.transfer_post_royalty(self.wa.address, pid, self.wb.address, self.wa.sign(t1), self.wa.pub_hex, t1)
        self.assertTrue(ok, msg)
        self.assertEqual(r1["new_royalty_owner"], self.wb.address)
        self.assertEqual(r1["transfers_used_year"], 1)
        self.assertEqual(r1["transfers_remaining_year"], 2)

        # 7. Original author A can NO LONGER transfer after handing off to B -> REJECT
        t_rev = f"POST_ROYALTY_TRANSFER:{self.wa.address}:{pid}:{self.wc.address}"
        ok, _, _ = self.bc.transfer_post_royalty(self.wa.address, pid, self.wc.address, self.wa.sign(t_rev), self.wa.pub_hex, t_rev)
        self.assertFalse(ok)

        # 8. Payout check: C likes & comments -> B earns 0.002 + 0.004 = 0.006 BCT, A earns 0
        bal_a_before = self.bc.verify_and_recalc_units(self.wa.address)
        bal_b_before = self.bc.verify_and_recalc_units(self.wb.address)

        lp = f"like:{self.wc.address}:{pid}"
        ok, msg, _ = self.bc.like_space_post(self.wc.address, pid, self.wc.sign(lp), self.wc.pub_hex, lp)
        self.assertTrue(ok, msg)
        cp = f"{self.wc.address}:{pid}:Great post!"
        ok, msg, _ = self.bc.comment_space_post(self.wc.address, pid, "Great post!", self.wc.sign(cp), self.wc.pub_hex, cp)
        self.assertTrue(ok, msg)

        self.assertEqual(self.bc.verify_and_recalc_units(self.wa.address), bal_a_before)
        self.assertEqual(self.bc.verify_and_recalc_units(self.wb.address) - bal_b_before, int(round(0.006 * ATOMIC_UNIT)))

        # 8b. Mempool double-transfer race protection: B cannot queue Transfer #2 before #1 is mined
        t2_race = f"POST_ROYALTY_TRANSFER:{self.wb.address}:{pid}:{self.wc.address}"
        if self.bc.pending_transactions:
            ok_race, msg_race, _ = self.bc.transfer_post_royalty(
                self.wb.address, pid, self.wc.address, self.wb.sign(t2_race), self.wb.pub_hex, t2_race
            )
            self.assertFalse(ok_race)
            self.assertIn("pending", msg_race.lower())
            self.bc.mine_pending_block(TREASURY_ADDRESS)

        # 9. Valid Transfer #2: B -> C (after #1 confirmed)
        t2 = f"POST_ROYALTY_TRANSFER:{self.wb.address}:{pid}:{self.wc.address}"
        ok, msg, r2 = self.bc.transfer_post_royalty(self.wb.address, pid, self.wc.address, self.wb.sign(t2), self.wb.pub_hex, t2)
        self.assertTrue(ok, msg)
        self.assertEqual(r2["transfers_used_year"], 2)
        self.assertEqual(r2["transfers_remaining_year"], 1)
        self.bc.mine_pending_block(TREASURY_ADDRESS)

        # 10. Valid Transfer #3: C -> A (after #2 confirmed)
        t3 = f"POST_ROYALTY_TRANSFER:{self.wc.address}:{pid}:{self.wa.address}"
        ok, msg, r3 = self.bc.transfer_post_royalty(self.wc.address, pid, self.wa.address, self.wc.sign(t3), self.wc.pub_hex, t3)
        self.assertTrue(ok, msg)
        self.assertEqual(r3["transfers_used_year"], 3)
        self.assertEqual(r3["transfers_remaining_year"], 0)
        self.bc.mine_pending_block(TREASURY_ADDRESS)

        # 11. 4th transfer within 365 days: A -> B MUST BE REJECTED!
        t4 = f"POST_ROYALTY_TRANSFER:{self.wa.address}:{pid}:{self.wb.address}"
        ok, msg4, _ = self.bc.transfer_post_royalty(self.wa.address, pid, self.wb.address, self.wa.sign(t4), self.wa.pub_hex, t4)
        self.assertFalse(ok)
        self.assertIn("3/3", msg4)

        self._assert_zero_drift()

    def test_bulk_post_royalty_transfer_all_1000_bct_and_per_post_3_year_rule(self):
        """Tests bulk transfer-all (1,000 BCT), per-post 3/year cap skipping, insufficient balance, and zero-drift conservation."""
        # Fund A with 2,500 BCT so A can afford 1,000 BCT bulk transfer
        rich_a = _make_funded_wallet(self.bc, 2500.0)
        pid1 = self._create_post(rich_a, "Bulk post #1")
        pid2 = self._create_post(rich_a, "Bulk post #2")
        pid3 = self._create_post(rich_a, "Bulk post #3 (will hit 3/3 limit)")
        self.bc.mine_pending_block(TREASURY_ADDRESS)

        # Exhaust pid3's 3/year limit across wallets: rich_a -> wb -> wc -> rich_a
        for frm, to in ((rich_a, self.wb), (self.wb, self.wc), (self.wc, rich_a)):
            pl = f"POST_ROYALTY_TRANSFER:{frm.address}:{pid3}:{to.address}"
            ok, msg, _ = self.bc.transfer_post_royalty(frm.address, pid3, to.address, frm.sign(pl), frm.pub_hex, pl)
            self.assertTrue(ok, msg)
            self.bc.mine_pending_block(TREASURY_ADDRESS)

        # Insufficient balance check: wb only has ~50 BCT (< 1,000 BCT)
        pid_b = self._create_post(self.wb, "B's single post")
        self.bc.mine_pending_block(TREASURY_ADDRESS)
        pb_low = f"POST_ROYALTY_TRANSFER_ALL:{self.wb.address}:{self.wc.address}"
        ok, msg_low, _ = self.bc.transfer_all_post_royalties(
            self.wb.address, self.wc.address, self.wb.sign(pb_low), self.wb.pub_hex, pb_low
        )
        self.assertFalse(ok)
        self.assertIn("1,000.00", msg_low)

        # Security: burned wallet target & system target rejected
        self._burn_wallet(self.wx)
        for bad_to in (self.wx.address, TREASURY_ADDRESS, VALIDATOR_STAKE_VAULT_ADDRESS, rich_a.address):
            p_bad = f"POST_ROYALTY_TRANSFER_ALL:{rich_a.address}:{bad_to}"
            ok, _, _ = self.bc.transfer_all_post_royalties(
                rich_a.address, bad_to, rich_a.sign(p_bad), rich_a.pub_hex, p_bad
            )
            self.assertFalse(ok)

        # Preview check before bulk transfer
        prev = self.bc.get_bulk_royalty_transfer_preview(rich_a.address)
        self.assertEqual(prev["eligible_count"], 2)
        self.assertEqual(prev["skipped_limit_count"], 1)
        self.assertIn(pid3, prev["skipped_post_ids"])

        # Execute Bulk Transfer All: rich_a -> wb (1,000 BCT)
        bal_a_before = self.bc.verify_and_recalc_units(rich_a.address)
        p_bulk = f"POST_ROYALTY_TRANSFER_ALL:{rich_a.address}:{self.wb.address}"
        ok, msg, res = self.bc.transfer_all_post_royalties(
            rich_a.address, self.wb.address, rich_a.sign(p_bulk), rich_a.pub_hex, p_bulk
        )
        self.assertTrue(ok, msg)
        self.assertEqual(res["transferred_count"], 2)
        self.assertEqual(res["skipped_limit_count"], 1)
        self.assertEqual(res["cost"], 1000.0)
        self.assertEqual(bal_a_before - self.bc.verify_and_recalc_units(rich_a.address), int(round(1000.0 * ATOMIC_UNIT)))
        self.bc.mine_pending_block(TREASURY_ADDRESS)

        # Verify pid1 & pid2 now pay royalties to wb, while skipped pid3 still pays rich_a
        b_before = self.bc.verify_and_recalc_units(self.wb.address)
        a_before = self.bc.verify_and_recalc_units(rich_a.address)
        for p_target in (pid1, pid2, pid3):
            lp = f"like:{self.wc.address}:{p_target}"
            ok, msg, _ = self.bc.like_space_post(self.wc.address, p_target, self.wc.sign(lp), self.wc.pub_hex, lp)
            self.assertTrue(ok, msg)
        self.assertEqual(self.bc.verify_and_recalc_units(self.wb.address) - b_before, int(round(0.004 * ATOMIC_UNIT)))
        self.assertEqual(self.bc.verify_and_recalc_units(rich_a.address) - a_before, int(round(0.002 * ATOMIC_UNIT)))

        # Second bulk transfer attempt by rich_a (only pid3 at 3/3 remains) -> REJECTED, NO 1,000 BCT charged!
        a_bal_pre = self.bc.verify_and_recalc_units(rich_a.address)
        p_bulk2 = f"POST_ROYALTY_TRANSFER_ALL:{rich_a.address}:{self.wc.address}"
        ok2, msg2, _ = self.bc.transfer_all_post_royalties(
            rich_a.address, self.wc.address, rich_a.sign(p_bulk2), rich_a.pub_hex, p_bulk2
        )
        self.assertFalse(ok2)
        self.assertIn("3/3", msg2)
        self.assertEqual(self.bc.verify_and_recalc_units(rich_a.address), a_bal_pre)

        self._assert_zero_drift()


if __name__ == "__main__":
    unittest.main()
