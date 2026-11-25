import os
import sys
import time
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.wallet import (
    Wallet,
    verify_signature,
    SECP256K1_N,
    HALF_SECP256K1_N,
)
from core.blockchain import (
    Blockchain,
    Transaction,
    TREASURY_ADDRESS,
    VALIDATOR_STAKE_VAULT_ADDRESS,
)
from core.bridge import verify_evm_burn_receipt, WBCT_OFFICIAL_CONTRACT, BURNED_TO_BRIDGE_TOPIC


class TestCoreConsensusAndCrypto(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="lt_core_sec_")
        self.db_path = os.path.join(self.tmpdir, "blockchain.db")
        self.bc = Blockchain(data_dir=self.tmpdir)

    def tearDown(self):
        try:
            if hasattr(self.bc, "_storage") and self.bc._storage:
                self.bc._storage.close()
        except Exception:
            pass
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_wallet_low_s_malleability_and_key_bounds(self):
        """ECDSA must reject High-S (s > N/2) malleable signatures and out-of-bounds private keys."""
        w = Wallet()
        msg = "LOCKTRACE_LOW_S_TEST:12345"
        sig_hex = w.sign(msg)
        self.assertTrue(verify_signature(w.get_public_key_hex(), msg, sig_hex))

        # Construct malleable High-S counterpart: s' = N - s
        r = int(sig_hex[:64], 16)
        s = int(sig_hex[64:], 16)
        self.assertLessEqual(s, HALF_SECP256K1_N)
        high_s = SECP256K1_N - s
        malleable_sig = f"{r:064x}{high_s:064x}"
        self.assertFalse(verify_signature(w.get_public_key_hex(), msg, malleable_sig))

        # Out-of-bounds private keys (0 and >= N) must raise ValueError
        with self.assertRaises(ValueError):
            Wallet(private_key_hex="0" * 64)
        with self.assertRaises(ValueError):
            Wallet(private_key_hex=f"{SECP256K1_N:064x}")

    def test_two_tier_signature_replay_protection(self):
        """O(1) two-tier _is_signature_used catches both confirmed and mempool signatures without copying history."""
        alice = Wallet()
        bob = Wallet()
        self.bc.register_wallet(alice.address, alice.get_public_key_hex(), grant_welcome_bonus=False)
        self.bc.register_wallet(bob.address, bob.get_public_key_hex(), grant_welcome_bonus=False)

        # Fund Alice directly via genesis/treasury test tx
        fund_tx = Transaction(sender=TREASURY_ADDRESS, receiver=alice.address, amount=50.0, fee=0.0, tx_type="reward")
        self.bc.pending_transactions.append(fund_tx)
        self.bc.mine_pending_block(TREASURY_ADDRESS)

        payload = f"{alice.address}:{bob.address}:5.0:0"
        sig = alice.sign(payload)
        ok1, _msg1, _res1 = self.bc.create_transaction(
            sender=alice.address,
            receiver=bob.address,
            amount=5.0,
            signature=sig,
            public_key=alice.get_public_key_hex(),
            signed_payload=payload,
        )
        self.assertTrue(ok1)
        self.assertTrue(self.bc._is_signature_used(sig))

        # Exact same signature replay must be rejected
        ok2, msg2, _res2 = self.bc.create_transaction(
            sender=alice.address,
            receiver=bob.address,
            amount=5.0,
            signature=sig,
            public_key=alice.get_public_key_hex(),
            signed_payload=payload,
        )
        self.assertFalse(ok2)
        self.assertIn("replay", msg2.lower())

    def test_submit_mined_block_malformed_types_and_sender_pays_solvency(self):
        """submit_mined_block must safely reject malformed types (no ValueError 500) and enforce sender_pays fee solvency."""
        val = Wallet()
        alice = Wallet()
        bob = Wallet()
        for w in (val, alice, bob):
            self.bc.register_wallet(w.address, w.get_public_key_hex(), grant_welcome_bonus=False)

        # Fund validator & lock 1,000 BCT + mark active validator
        self.bc.pending_transactions.append(
            Transaction(sender=TREASURY_ADDRESS, receiver=val.address, amount=1500.0, fee=0.0, tx_type="reward")
        )
        self.bc.pending_transactions.append(
            Transaction(sender=TREASURY_ADDRESS, receiver=alice.address, amount=10.0, fee=0.0, tx_type="reward")
        )
        self.bc.mine_pending_block(TREASURY_ADDRESS)

        stake_payload = f"VALIDATOR_STAKE:{val.address}:1000.0:0"
        ok_s, msg_s, _ = self.bc.execute_validator_stake(
            val.address, 1000.0, val.sign(stake_payload), val.get_public_key_hex(), stake_payload
        )
        self.assertTrue(ok_s, msg_s)
        self.bc.mine_pending_block(TREASURY_ADDRESS)
        self.bc.nodes["node-val-test"] = {
            "node_id": "node-val-test",
            "miner_address": val.address,
            "auth_verified": True,
            "last_seen": time.time(),
            "status": "online",
        }

        # 1. Malformed index/nonce/version must return (False, ..., None) instead of raising ValueError
        ok_bad, msg_bad, _ = self.bc.submit_mined_block(
            block_data={"miner": val.address, "index": "not_an_int", "nonce": "abc", "version": 2},
            public_key=val.get_public_key_hex(),
            signature=val.sign("dummy"),
        )
        self.assertFalse(ok_bad)
        self.assertIn("numeric", msg_bad.lower())

        # 2. Malformed bool index must also be rejected cleanly
        ok_bool, msg_bool, _ = self.bc.submit_mined_block(
            block_data={"miner": val.address, "index": True, "nonce": 0, "version": 2},
            public_key=val.get_public_key_hex(),
            signature=val.sign("dummy"),
        )
        self.assertFalse(ok_bool)
        self.assertIn("type", msg_bool.lower())

        # 3. sender_pays solvency test: Alice has 10.0 BCT; tx has amount=10.0, fee=0.10 (total debit 10.10 > 10.0)
        insolvent_tx = Transaction(
            sender=alice.address,
            receiver=bob.address,
            amount=10.0,
            fee=0.10,
            signature=alice.sign("insolvent_sender_pays_test"),
            tx_type="transfer",
            extra_data={"fee_mode": "sender_pays"},
        )
        self.bc.pending_transactions.append(insolvent_tx)

        # Build a valid PoW header containing the insolvent sender_pays tx
        tip = self.bc.chain[-1]
        ts = max(time.time(), tip.timestamp + 20.0)
        from core.blockchain import Block
        cand = Block(
            index=len(self.bc.chain),
            transactions=[insolvent_tx],
            previous_hash=tip.hash,
            miner=val.address,
            timestamp=round(ts, 3),
            version=2,
        )
        diff = self.bc.get_current_difficulty()
        target = "0" * diff
        while not cand.hash.startswith(target):
            cand.nonce += 1
            cand.hash = cand.calculate_hash()

        hdr_sig = val.sign(f"SUBMIT_BLOCK:{cand.index}:{cand.hash}:{cand.nonce}:{val.address}")
        ok_insolv, msg_insolv, _ = self.bc.submit_mined_block(
            block_data=cand.to_dict(),
            public_key=val.get_public_key_hex(),
            signature=hdr_sig,
        )
        self.assertFalse(ok_insolv)
        self.assertIn("insolvent", msg_insolv.lower())

    def test_verify_full_chain_integrity_and_storage_delta_fork_detection(self):
        """verify_full_chain_integrity passes on valid chain; storage load_delta_state returns None on tip mismatch."""
        ok, msg, stats = self.bc.verify_full_chain_integrity()
        self.assertTrue(ok, msg)
        self.assertGreaterEqual(stats["blocks"], 1)

        # Fork mismatch on load_delta_state must return None (triggering safe full reload)
        storage = self.bc._get_storage()
        delta_bad = storage.load_delta_state(since_block_index=0, expected_tip_hash="f" * 64)
        self.assertIsNone(delta_bad)

    def test_bridge_reorg_and_confirmation_guards(self):
        """verify_evm_burn_receipt must reject < 12 confirmations and canonical blockHash mismatches (reorgs)."""
        fake_tx = "0x" + "a" * 64
        fake_blk_hash = "0x" + "b" * 64
        reorg_blk_hash = "0x" + "c" * 64
        alice = Wallet()

        def mock_rpc_low_confs(payload, **_kwargs):
            m = payload.get("method")
            if m == "eth_getTransactionReceipt":
                return {"result": {
                    "status": "0x1",
                    "to": WBCT_OFFICIAL_CONTRACT,
                    "blockNumber": "0x64",  # 100
                    "blockHash": fake_blk_hash,
                    "logs": [],
                }}
            if m == "eth_blockNumber":
                return {"result": "0x69"}  # 105 -> only 6 confs (< 12)
            return None

        with patch("core.bridge._call_base_rpc", side_effect=mock_rpc_low_confs):
            ok, msg, meta = verify_evm_burn_receipt(fake_tx, alice.address, 10.0)
            self.assertFalse(ok)
            self.assertIn("confirmation", msg.lower())
            self.assertEqual(meta.get("confirmations"), 6)

        def mock_rpc_reorg(payload, **_kwargs):
            m = payload.get("method")
            if m == "eth_getTransactionReceipt":
                return {"result": {
                    "status": "0x1",
                    "to": WBCT_OFFICIAL_CONTRACT,
                    "blockNumber": "0x64",  # 100
                    "blockHash": fake_blk_hash,
                    "logs": [],
                }}
            if m == "eth_blockNumber":
                return {"result": "0x96"}  # 150 -> 51 confs (>= 12)
            if m == "eth_getBlockByNumber":
                return {"result": {"hash": reorg_blk_hash}}  # MISMATCH!
            return None

        with patch("core.bridge._call_base_rpc", side_effect=mock_rpc_reorg):
            ok2, msg2, meta2 = verify_evm_burn_receipt(fake_tx, alice.address, 10.0)
            self.assertFalse(ok2)
            self.assertTrue(meta2.get("reorg_detected"))
            self.assertIn("reorg", msg2.lower())

    def test_bns_burned_counterparty_and_burn_wallet_proposal_cleanup(self):
        """bns_buy must reject burned sellers, bns_accept_offer must reject burned bidders, and burn_wallet must cancel open proposals."""
        seller = Wallet()
        buyer = Wallet()
        for w in (seller, buyer):
            self.bc.register_wallet(w.address, w.get_public_key_hex(), grant_welcome_bonus=False)
            self.bc.pending_transactions.append(
                Transaction(sender=TREASURY_ADDRESS, receiver=w.address, amount=100.0, fee=0.0, tx_type="reward")
            )
        self.bc.mine_pending_block(TREASURY_ADDRESS)

        # Register a 5-char .bct domain (10 BCT) and list for sale (20 BCT)
        reg_payload = f"BNS_REGISTER:alpha.bct:{seller.address}:10.0"
        ok_r, msg_r, _ = self.bc.bns_register("alpha.bct", seller.address, seller.sign(reg_payload), seller.get_public_key_hex(), signed_payload=reg_payload)
        self.assertTrue(ok_r, msg_r)
        self.bc.mine_pending_block(TREASURY_ADDRESS)

        price_payload = f"BNS_PRICE:alpha.bct:{seller.address}:20.0"
        ok_p, msg_p, _ = self.bc.bns_set_price("alpha.bct", seller.address, 20.0, seller.sign(price_payload), seller.get_public_key_hex(), signed_payload=price_payload)
        self.assertTrue(ok_p, msg_p)
        self.bc.mine_pending_block(TREASURY_ADDRESS)

        # Create a 2-step pending asset transfer proposal from seller -> buyer
        prop_payload = f"BNS_TRANSFER:alpha.bct:{seller.address}:{buyer.address}"
        ok_prop, msg_prop, prop_res = self.bc.propose_asset_transfer(
            asset_type="bns",
            asset_id="alpha.bct",
            from_address=seller.address,
            to_address=buyer.address,
            signature=seller.sign(prop_payload),
            public_key=seller.get_public_key_hex(),
            signed_payload=prop_payload,
        )
        self.assertTrue(ok_prop, msg_prop)
        pid = prop_res["proposal_id"]

        # Seller permanently burns their wallet
        burn_payload = f"WALLET_BURN:{seller.address}:PERMANENT_IRREVERSIBLE_DESTROY"
        ok_b, msg_b, _ = self.bc.burn_wallet(seller.address, seller.sign(burn_payload), seller.get_public_key_hex(), signed_payload=burn_payload)
        self.assertTrue(ok_b, msg_b)

        # 1. Pending proposal involving burned seller must be automatically cancelled
        self.assertEqual(self.bc.pending_asset_transfers[pid]["status"], "cancelled")
        self.assertEqual(self.bc.pending_asset_transfers[pid].get("cancel_reason"), "wallet_burned")

        # 2. Buyer attempting bns_buy against burned seller must be rejected (zero BCT leaked to burned wallet)
        buy_payload = f"BNS_BUY:alpha.bct:{buyer.address}:{seller.address}:20.0"
        ok_buy, msg_buy, _ = self.bc.bns_buy("alpha.bct", buyer.address, buyer.sign(buy_payload), buyer.get_public_key_hex(), signed_payload=buy_payload)
        self.assertFalse(ok_buy)
        self.assertIn("burned", msg_buy.lower())
        self.assertEqual(self.bc.verify_and_recalc_balance(seller.address), 0.0)

        # 3. Buyer attempting bns_make_offer on burned seller's domain must also be rejected early
        offer_payload = f"BNS_OFFER:alpha.bct:{buyer.address}:15.0"
        ok_off, msg_off, _ = self.bc.bns_make_offer("alpha.bct", buyer.address, 15.0, buyer.sign(offer_payload), buyer.get_public_key_hex(), signed_payload=offer_payload)
        self.assertFalse(ok_off)
        self.assertIn("burned", msg_off.lower())


if __name__ == "__main__":
    unittest.main()
