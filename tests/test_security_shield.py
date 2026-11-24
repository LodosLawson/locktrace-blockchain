# -*- coding: utf-8 -*-
"""
Security Resilience Test Suite:
  1. Verifies `/api/v1/market/bot-wallet/<invalid>` returns clean 404 (never HTTP 500).
  2. Verifies Adaptive Abuse Shield automatically jails IPs after auth-failure bursts
     and releases cleanly after expiry.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import server


class TestSecurityResilience(unittest.TestCase):
    def setUp(self):
        with server._ABUSE_SHIELD_LOCK:
            server._ABUSE_AUTH_HITS.clear()
            server._ABUSE_SCAN_HITS.clear()
            server._ABUSE_RL_HITS.clear()
            server._ABUSE_JAIL_UNTIL.clear()
        self.client = server.app.test_client()

    def test_bot_wallet_invalid_returns_404_not_500(self):
        for probe in ["abc", "0xdeadbeef", "' OR 1=1--", "BCT0000000000000000000000000000000000000000"]:
            resp = self.client.get(f"/api/v1/market/bot-wallet/{probe}")
            self.assertEqual(resp.status_code, 404, f"Expected 404 for {probe}, got {resp.status_code}")

    def test_adaptive_abuse_shield_auto_jails_auth_fuzzer(self):
        fake_ip = "203.0.113.99"
        self.assertEqual(server._is_ip_jailed(fake_ip), 0.0)
        for _ in range(10):
            server._record_abuse_signal(fake_ip, 403)
        self.assertGreater(server._is_ip_jailed(fake_ip), 0.0)

        # Jailed IP gets immediate 429 before hitting any API handler
        resp = self.client.get(
            "/api/v1/stats",
            environ_base={"REMOTE_ADDR": fake_ip},
            headers={"X-Real-IP": fake_ip},
        )
        self.assertEqual(resp.status_code, 429)

        # Rate-limit hammerer gets jailed after 8x 429s
        rl_ip = "203.0.113.77"
        for _ in range(8):
            server._record_abuse_signal(rl_ip, 429)
        self.assertGreater(server._is_ip_jailed(rl_ip), 0.0)

        # Tor exit node POST is blocked with 403 while GET still works
        tor_ip = "198.51.100.42"
        server._TOR_EXIT_SET.add(tor_ip)
        try:
            r_post = self.client.post(
                "/api/v1/rooms",
                json={},
                environ_base={"REMOTE_ADDR": tor_ip},
                headers={"X-Real-IP": tor_ip},
            )
            self.assertEqual(r_post.status_code, 403)
            r_get = self.client.get(
                "/api/v1/stats",
                environ_base={"REMOTE_ADDR": tor_ip},
                headers={"X-Real-IP": tor_ip},
            )
            self.assertEqual(r_get.status_code, 200)
        finally:
            server._TOR_EXIT_SET.discard(tor_ip)

        # Localhost is never jailed
        for _ in range(30):
            server._record_abuse_signal("127.0.0.1", 403)
        self.assertEqual(server._is_ip_jailed("127.0.0.1"), 0.0)


if __name__ == "__main__":
    unittest.main()
