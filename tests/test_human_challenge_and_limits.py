import hashlib
import os
import tempfile
import unittest

import server as srv
from core.bridge import BridgeManager
from core.wallet import Wallet


def _solve_challenge(chal: dict) -> str:
    prefix = f"{chal['challenge_id']}:{chal['salt']}:"
    diff = int(chal["difficulty_bits"])
    for nonce in range(500000):
        digest = hashlib.sha256(f"{prefix}{nonce}".encode("utf-8")).digest()
        if srv._count_leading_zero_bits(digest) >= diff:
            return str(nonce)
    raise AssertionError("Failed to solve PoW challenge")


class TestHumanChallengeAndLimits(unittest.TestCase):
    def setUp(self):
        self.client = srv.app.test_client()
        srv._USED_HUMAN_CHALLENGES.clear()
        srv._WALLET_BONUS_IP_HISTORY.clear()
        srv._WALLET_CREATE_IP_HISTORY.clear()

    def test_wallet_create_blocks_direct_api_bot_without_challenge(self):
        w = Wallet()
        resp = self.client.post(
            "/api/v1/wallet/create",
            json={"address": w.address, "public_key": w.get_public_key_hex()},
            environ_base={"REMOTE_ADDR": "198.51.100.10"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.get_json()["success"])

    def test_wallet_create_allows_unlimited_wallets_but_caps_bonus_to_1_per_ip_24h(self):
        ip = "198.51.100.11"
        # 1st wallet: gets 1.00 BCT welcome bonus
        c1 = self.client.get("/api/v1/auth/human-challenge", environ_base={"REMOTE_ADDR": ip}).get_json()["data"]
        n1 = _solve_challenge(c1)
        w1 = Wallet()
        r1 = self.client.post(
            "/api/v1/wallet/create",
            json={"address": w1.address, "public_key": w1.get_public_key_hex(), "human_challenge": c1, "human_nonce": n1},
            environ_base={"REMOTE_ADDR": ip},
        )
        self.assertEqual(r1.status_code, 201)
        j1 = r1.get_json()
        self.assertTrue(j1["data"]["welcome_bonus_granted"])
        self.assertGreaterEqual(j1["data"]["balance"], 1.0)

        # Replay of c1 MUST fail with 403
        w_rep = Wallet()
        r_rep = self.client.post(
            "/api/v1/wallet/create",
            json={"address": w_rep.address, "public_key": w_rep.get_public_key_hex(), "human_challenge": c1, "human_nonce": n1},
            environ_base={"REMOTE_ADDR": ip},
        )
        self.assertEqual(r_rep.status_code, 403)

        # 2nd wallet from same IP with fresh solved challenge: SUCCEEDS, but 0.00 BCT bonus
        c2 = self.client.get("/api/v1/auth/human-challenge", environ_base={"REMOTE_ADDR": ip}).get_json()["data"]
        n2 = _solve_challenge(c2)
        w2 = Wallet()
        r2 = self.client.post(
            "/api/v1/wallet/create",
            json={"address": w2.address, "public_key": w2.get_public_key_hex(), "human_challenge": c2, "human_nonce": n2},
            environ_base={"REMOTE_ADDR": ip},
        )
        self.assertEqual(r2.status_code, 201)
        j2 = r2.get_json()
        self.assertFalse(j2["data"]["welcome_bonus_granted"])
        self.assertEqual(j2["data"]["balance"], 0.0)

    def test_wallet_import_never_grants_free_bonus(self):
        w = Wallet()
        r = self.client.post(
            "/api/v1/wallet/import",
            json={"address": w.address, "public_key": w.get_public_key_hex()},
            environ_base={"REMOTE_ADDR": "198.51.100.12"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["data"]["balance"], 0.0)

    def test_two_way_bridge_limits_15_to_50_bct(self):
        with tempfile.TemporaryDirectory() as td:
            bm = BridgeManager(os.path.join(td, "bridge_test.db"))
            w = Wallet()
            evm = "0x" + "a" * 40
            for direction in ("L1_TO_EVM", "EVM_TO_L1"):
                low = bm.create_bridge_order(direction, w.address, evm, 14.99)
                self.assertFalse(low["success"])
                high = bm.create_bridge_order(direction, w.address, evm, 50.01)
                self.assertFalse(high["success"])
                ok = bm.create_bridge_order(direction, w.address, evm, 25.0)
                self.assertTrue(ok["success"])


if __name__ == "__main__":
    unittest.main()
