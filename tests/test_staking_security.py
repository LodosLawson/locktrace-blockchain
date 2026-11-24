import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.blockchain import (
    ATOMIC_UNIT,
    MAX_OBSERVER_STAKE,
    MIN_OBSERVER_STAKE,
    TREASURY_ADDRESS,
    VALIDATOR_STAKE_VAULT_ADDRESS,
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
        signature=f"TEST_FUND_STK_{w.address}_{amount}",
        tx_type="reward",
    )
    bc.pending_transactions.append(tx)
    bc.mine_pending_block(TREASURY_ADDRESS)
    return w


class TestStakingSecurityHardening(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.bc = Blockchain(data_dir=self.tmp_dir.name)
        self.staker = _make_funded_wallet(self.bc, 150_000.0)
        self.miner = _make_funded_wallet(self.bc, 100.0)
        self.user = _make_funded_wallet(self.bc, 100.0)

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

    def _stake(self, w: Wallet, amt: float):
        nonce = self.bc.get_account_nonce(w.address)
        payload = f"VALIDATOR_STAKE:{w.address}:{amt}:{nonce}"
        return self.bc.execute_validator_stake(w.address, amt, w.sign(payload), w.pub_hex, payload)

    def _unstake(self, w: Wallet, amt: float):
        nonce = self.bc.get_account_nonce(w.address)
        payload = f"VALIDATOR_UNSTAKE:{w.address}:{amt}:{nonce}"
        return self.bc.execute_validator_unstake(w.address, amt, w.sign(payload), w.pub_hex, payload)

    def test_observer_pool_no_double_spend_and_miner_never_zeroed_on_payout(self):
        """Fix #1: Proposer must NEVER steal the 10% Observer slice AND must still earn 50%+ on batched payout blocks."""
        ok, msg, _ = self._stake(self.staker, 1000.0)
        self.assertTrue(ok, msg)
        self.bc.mine_pending_block(TREASURY_ADDRESS)

        # Create a genuine fee-paying user tx (space_post: 0.10 BCT -> 0.02 miner fee + 0.05 subsidy = 0.07 total pool)
        p_tx = Transaction(
            sender=self.user.address,
            receiver=TREASURY_ADDRESS,
            amount=0.10,
            fee=0.02,
            signature=self.user.sign(f"post:{self.user.address}:1"),
            tx_type="space_post",
            extra_data={"post_id": "p_test_1", "content": "test"},
        )
        # Normal accrual block (accrued < 0.25 BCT): observer gets 0.007 accrued, proposer gets 0.063 (90%), NOT 0.07 (100%)
        reward_txs, bd = self.bc._build_reward_transactions([p_tx], self.miner.address, block_index=len(self.bc.chain))
        self.assertAlmostEqual(bd["total_reward"], 0.07, places=8)
        self.assertAlmostEqual(bd["proposer_reward"], 0.063, places=8)
        self.assertEqual(bd["observer_pool_reward"], 0.0)
        self.assertEqual(bd["observer_pending_after"].get(self.staker.address), int(round(0.007 * ATOMIC_UNIT)))

        # Batched payout block: pre-load pending to 0.245 BCT so this block triggers 0.252 BCT payout (> 0.07 total_pool!)
        self.bc.observer_pending_units[self.staker.address] = int(round(0.245 * ATOMIC_UNIT))
        reward_txs2, bd2 = self.bc._build_reward_transactions([p_tx], self.miner.address, block_index=len(self.bc.chain))
        # Proposer MUST still receive exact 0.063 BCT (NOT 0.0 BCT!)
        self.assertAlmostEqual(bd2["proposer_reward"], 0.063, places=8)
        self.assertAlmostEqual(bd2["observer_pool_reward"], 0.252, places=8)
        self._assert_zero_drift()

    def test_cumulative_max_cap_topup_lockup_dust_guard_and_burn_protection(self):
        """Fixes #2, #3, #4, #5, #7: cumulative 100k cap, top-up, 1h lockup, dust guard, burn protection, slashed display."""
        # 1. Stake 60,000 BCT
        ok, msg, _ = self._stake(self.staker, 60_000.0)
        self.assertTrue(ok, msg)
        self.bc.mine_pending_block(TREASURY_ADDRESS)

        # 2. Cumulative cap: trying to add 50,000 BCT (total 110,000 > 100,000) MUST FAIL
        ok, msg, _ = self._stake(self.staker, 50_000.0)
        self.assertFalse(ok)
        self.assertIn("100,000", msg)

        # 3. Top-up below 100 BCT (e.g. +25 BCT) works once >= 100 BCT is already staked
        ok, msg, _ = self._stake(self.staker, 25.0)
        self.assertTrue(ok, msg)
        self.bc.mine_pending_block(TREASURY_ADDRESS)
        self.assertAlmostEqual(self.bc.get_validator_stake(self.staker.address), 60_025.0, places=6)

        # 4. Burn protection: burning a wallet with active stake MUST BE REJECTED
        burn_payload = f"WALLET_BURN:{self.staker.address}:PERMANENT_IRREVERSIBLE_DESTROY"
        ok, msg, _ = self.bc.burn_wallet(self.staker.address, self.staker.sign(burn_payload), self.staker.pub_hex, burn_payload)
        self.assertFalse(ok)
        self.assertIn("Staking Vault", msg)

        # 5. Anti-flash-staking lockup: immediate unstake within 1-hour lockup MUST BE REJECTED
        ok, msg, _ = self._unstake(self.staker, 1000.0)
        self.assertFalse(ok)
        self.assertIn("kilit", msg.lower())

        # 6. Simulate lockup expiry -> partial unstake leaving < 100 BCT dust MUST BE REJECTED
        self.bc.stake_lockup_seconds = 0
        ok, msg, _ = self._unstake(self.staker, 59_975.0)  # leaves 50 BCT (< 100 BCT)
        self.assertFalse(ok)
        self.assertIn("100.00", msg)

        # 7. Full unstake succeeds cleanly
        ok, msg, _ = self._unstake(self.staker, 60_025.0)
        self.assertTrue(ok, msg)
        self.bc.mine_pending_block(TREASURY_ADDRESS)
        self.assertEqual(self.bc.get_validator_stake(self.staker.address), 0.0)

        # 8. Now burning succeeds cleanly and burned wallet cannot stake again
        burn_payload2 = f"WALLET_BURN:{self.staker.address}:PERMANENT_IRREVERSIBLE_DESTROY"
        ok, msg, _ = self.bc.burn_wallet(self.staker.address, self.staker.sign(burn_payload2), self.staker.pub_hex, burn_payload2)
        self.assertTrue(ok, msg)
        ok, _, _ = self._stake(self.staker, 100.0)
        self.assertFalse(ok)

        self._assert_zero_drift()


if __name__ == "__main__":
    unittest.main()
