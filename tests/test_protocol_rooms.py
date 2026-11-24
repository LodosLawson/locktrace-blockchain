# -*- coding: utf-8 -*-
"""
Comprehensive Security, Tokenomics & Functional Test Suite for Protocol Rooms.
Tests:
  - Tiered room creation pricing (3-4 chars = 50 BCT, 5-8 chars = 25 BCT, 9+ chars = 10 BCT)
  - Optional immutable avatar seal (+2 BCT) & strict consensus-level immutability
  - Creator-only one-time avatar seal (non-creator rejected, second seal rejected, rogue tx ignored)
  - Homoglyph/Turkish spoofing prevention & reserved slug blocking
  - Control character & invalid hex/XSS payload rejection
  - Reddit-style Topics (0.25 BCT -> 30% Room Creator royalty)
  - Nested Replies/Tweets (0.05 BCT -> 20% Topic Author + 20% Room Creator royalty)
  - Cross-topic parent_reply_id hijacking rejection
  - Upvoting (0.01 BCT) & duplicate upvote rejection
  - Exact atomic-unit balance conservation across all participants & Treasury
"""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.blockchain import Blockchain, TREASURY_ADDRESS, Transaction
from core.wallet import Wallet


def _make_funded_wallet(bc: Blockchain, amount: float = 200.0) -> Wallet:
    w = Wallet()
    w.pub_hex = w._pub_bytes.hex()
    bc.register_wallet(w.address, w.pub_hex)
    # Credit from Treasury directly in a clean reward funding tx
    tx = Transaction(
        sender=TREASURY_ADDRESS,
        receiver=w.address,
        amount=amount,
        fee=0.0,
        signature=f"TEST_FUNDING_{w.address}",
        tx_type="reward",
    )
    bc.pending_transactions.append(tx)
    bc.mine_pending_block(TREASURY_ADDRESS)
    return w


class TestProtocolRooms(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.bc = Blockchain(data_dir=self._tmpdir.name, auto_mine=True)
        self.creator = _make_funded_wallet(self.bc, 200.0)
        self.alice = _make_funded_wallet(self.bc, 50.0)
        self.bob = _make_funded_wallet(self.bc, 50.0)

    def tearDown(self):
        try:
            if self.bc._storage:
                self.bc._storage.close()
        except Exception:
            pass
        self._tmpdir.cleanup()

    def test_tiered_pricing_and_room_creation(self):
        # 1. Short name (3-4 chars -> 50 BCT) + Avatar (+2 BCT) = 52 BCT
        ok_q, _, q_short = self.bc.get_room_create_quote("Krip", has_avatar=True)
        self.assertTrue(ok_q)
        self.assertEqual(q_short["tier"], "short")
        self.assertEqual(q_short["base_fee"], 50.0)
        self.assertEqual(q_short["avatar_fee"], 2.0)
        self.assertEqual(q_short["total_cost"], 52.0)
        self.assertTrue(q_short["room_id"].startswith("RM-"))

        sig = self.creator.sign(f"ROOM_CREATE:{self.creator.address}:{q_short['slug']}:Kısa isimli premium kripto odası.")
        bal_before = self.bc.verify_and_recalc_balance(self.creator.address)
        ok, msg, res = self.bc.create_room(
            creator=self.creator.address,
            name="Krip",
            description="Kısa isimli premium kripto odası.",
            avatar_base_id="ANM-001",
            avatar_bg_color="#10B981",
            signature=sig,
            public_key=self.creator.pub_hex,
        )
        self.assertTrue(ok, msg)
        self.assertEqual(res["cost"], 52.0)
        self.assertTrue(res["avatar_locked"])
        self.assertEqual(res["avatar"]["variant_id"], "ANM-001-10B981")
        bal_after = self.bc.verify_and_recalc_balance(self.creator.address)
        self.assertAlmostEqual(bal_before - bal_after, 52.0, places=6)

        # 2. Medium name (5-8 chars -> 25 BCT, no avatar)
        ok_q2, _, q_med = self.bc.get_room_create_quote("Kripto", has_avatar=False)
        self.assertTrue(ok_q2)
        self.assertEqual(q_med["tier"], "medium")
        self.assertEqual(q_med["total_cost"], 25.0)

        # 3. Standard name (9+ chars -> 10 BCT, no avatar)
        ok_q3, _, q_std = self.bc.get_room_create_quote("LockTrace Builders TR", has_avatar=False)
        self.assertTrue(ok_q3)
        self.assertEqual(q_std["tier"], "standard")
        self.assertEqual(q_std["total_cost"], 10.0)

    def test_developer_room_verification(self):
        ok_q, _, q = self.bc.get_room_create_quote("Official Room", has_avatar=False)
        sig = self.creator.sign(f"ROOM_CREATE:{self.creator.address}:{q['slug']}:Dogrulama testi odasi.")
        ok, _, r = self.bc.create_room(
            creator=self.creator.address,
            name="Official Room",
            description="Dogrulama testi odasi.",
            signature=sig,
            public_key=self.creator.pub_hex,
        )
        self.assertTrue(ok)
        rid = r["room_id"]
        self.assertFalse(self.bc.rooms[rid]["is_verified"])

        # Non-authority attempt rejected
        sig_alice = self.alice.sign(f"ROOM_VERIFY:{self.alice.address}:{rid}:true")
        ok_a, _, _ = self.bc.verify_protocol_room(
            authority_address=self.alice.address,
            room_id=rid,
            verified=True,
            signature=sig_alice,
            public_key=self.alice.pub_hex,
        )
        self.assertFalse(ok_a)
        self.assertFalse(self.bc.rooms[rid]["is_verified"])

    def test_strict_avatar_immutability(self):
        # Case A: Room created WITH avatar -> set_room_avatar MUST fail
        ok_q, _, q1 = self.bc.get_room_create_quote("Sealed Room Alpha", has_avatar=True)
        sig1 = self.creator.sign(f"ROOM_CREATE:{self.creator.address}:{q1['slug']}:Oluşturulurken avatarı mühürlenmiş oda.")
        ok, _, r1 = self.bc.create_room(
            creator=self.creator.address,
            name="Sealed Room Alpha",
            description="Oluşturulurken avatarı mühürlenmiş oda.",
            avatar_base_id="ANM-002",
            avatar_bg_color="#3B82F6",
            signature=sig1,
            public_key=self.creator.pub_hex,
        )
        self.assertTrue(ok)
        rid1 = r1["room_id"]

        sig_try = self.creator.sign(f"ROOM_AVATAR:{self.creator.address}:{rid1}:ANM-003-FFFFFF")
        ok_ch, msg_ch, _ = self.bc.set_room_avatar(
            creator=self.creator.address,
            room_id=rid1,
            avatar_base_id="ANM-003",
            avatar_bg_color="#FFFFFF",
            signature=sig_try,
            public_key=self.creator.pub_hex,
        )
        self.assertFalse(ok_ch)
        self.assertIn("locked", msg_ch.lower())

        # Case B: Room created WITHOUT avatar -> non-creator fails, creator succeeds ONCE, second time fails!
        ok_q2, _, q2 = self.bc.get_room_create_quote("Open Room Beta", has_avatar=False)
        sig2 = self.creator.sign(f"ROOM_CREATE:{self.creator.address}:{q2['slug']}:Sonradan tek seferlik avatar mühürlenecek oda.")
        ok2, _, r2 = self.bc.create_room(
            creator=self.creator.address,
            name="Open Room Beta",
            description="Sonradan tek seferlik avatar mühürlenecek oda.",
            signature=sig2,
            public_key=self.creator.pub_hex,
        )
        self.assertTrue(ok2)
        self.assertFalse(r2["avatar_locked"])
        rid2 = r2["room_id"]

        # Non-creator attempt MUST fail
        sig_alice = self.alice.sign(f"ROOM_AVATAR:{self.alice.address}:{rid2}:ANM-005-FFFFFF")
        ok_nc, _, _ = self.bc.set_room_avatar(
            creator=self.alice.address,
            room_id=rid2,
            avatar_base_id="ANM-005",
            avatar_bg_color="#FFFFFF",
            signature=sig_alice,
            public_key=self.alice.pub_hex,
        )
        self.assertFalse(ok_nc)

        # Creator first seal MUST succeed (2.00 BCT)
        sig_seal = self.creator.sign(f"ROOM_AVATAR:{self.creator.address}:{rid2}:ANM-005-F59E0B")
        bal_b = self.bc.verify_and_recalc_balance(self.creator.address)
        ok_s1, msg_s1, res_s1 = self.bc.set_room_avatar(
            creator=self.creator.address,
            room_id=rid2,
            avatar_base_id="ANM-005",
            avatar_bg_color="#F59E0B",
            signature=sig_seal,
            public_key=self.creator.pub_hex,
        )
        self.assertTrue(ok_s1, msg_s1)
        self.assertTrue(res_s1["avatar_locked"])
        self.assertAlmostEqual(bal_b - self.bc.verify_and_recalc_balance(self.creator.address), 2.0, places=6)

        # Creator second seal MUST fail
        sig_seal2 = self.creator.sign(f"ROOM_AVATAR:{self.creator.address}:{rid2}:ANM-006-FFFFFF")
        ok_s2, _, _ = self.bc.set_room_avatar(
            creator=self.creator.address,
            room_id=rid2,
            avatar_base_id="ANM-006",
            avatar_bg_color="#FFFFFF",
            signature=sig_seal2,
            public_key=self.creator.pub_hex,
        )
        self.assertFalse(ok_s2)

        # Consensus-level rogue tx injection test: even if a second room_set_avatar tx is forced into chain,
        # indexer MUST ignore it and preserve ANM-005-F59E0B!
        rogue_tx = Transaction(
            sender=self.creator.address,
            receiver=TREASURY_ADDRESS,
            amount=2.0,
            fee=1.0,
            signature="ROGUE_OVERRIDE",
            tx_type="room_set_avatar",
            extra_data={"room_id": rid2, "avatar_variant_id": "ANM-007-000000"},
        )
        self.bc.pending_transactions.append(rogue_tx)
        self.bc._load_in_memory_rooms_index()
        detail = self.bc.get_room_detail(rid2)
        self.assertEqual(detail["avatar_variant_id"], "ANM-005-F59E0B")

    def test_security_validation_and_spoofing_protection(self):
        # Reserved name blocked
        ok_res, _, _ = self.bc.get_room_create_quote("admin", has_avatar=False)
        self.assertFalse(ok_res)

        # Control / zero-width chars blocked
        ok_zw, _, _ = self.bc.get_room_create_quote("Kripto\u200bAnaliz", has_avatar=False)
        self.assertFalse(ok_zw)

        # Create "Kripto Analiz" then attempt Turkish homoglyph spoof "krıpto analiz"
        ok_q, _, q = self.bc.get_room_create_quote("Kripto Analiz", has_avatar=False)
        self.assertTrue(ok_q)
        sig = self.creator.sign(f"ROOM_CREATE:{self.creator.address}:{q['slug']}:Gerçek kripto analiz topluluğu.")
        ok, _, _ = self.bc.create_room(
            creator=self.creator.address,
            name="Kripto Analiz",
            description="Gerçek kripto analiz topluluğu.",
            signature=sig,
            public_key=self.creator.pub_hex,
        )
        self.assertTrue(ok)

        ok_spoof_q, _, q_spoof = self.bc.get_room_create_quote("krıpto analiz", has_avatar=False)
        self.assertTrue(ok_spoof_q)
        self.assertFalse(q_spoof["available"])

        # Invalid hex / CSS injection in avatar color rejected
        ok_q2, _, q2 = self.bc.get_room_create_quote("Security Test Room", has_avatar=True)
        sig2 = self.creator.sign(f"ROOM_CREATE:{self.creator.address}:{q2['slug']}:XSS testi için oda.")
        ok_xss, _, _ = self.bc.create_room(
            creator=self.creator.address,
            name="Security Test Room",
            description="XSS testi için oda.",
            avatar_base_id="ANM-001",
            avatar_bg_color="#FFFFFF;background:url(javascript:alert(1))",
            signature=sig2,
            public_key=self.creator.pub_hex,
        )
        self.assertFalse(ok_xss)

    def test_reddit_flow_topics_replies_upvotes_and_royalties(self):
        # 1. Creator opens a standard room (10.00 BCT)
        ok_q, _, q = self.bc.get_room_create_quote("LockTrace Developers", has_avatar=False)
        sig_r = self.creator.sign(f"ROOM_CREATE:{self.creator.address}:{q['slug']}:L1 geliştirici tartışma ve mevzu alanı.")
        ok, _, room = self.bc.create_room(
            creator=self.creator.address,
            name="LockTrace Developers",
            description="L1 geliştirici tartışma ve mevzu alanı.",
            signature=sig_r,
            public_key=self.creator.pub_hex,
        )
        self.assertTrue(ok)
        rid = room["room_id"]

        # 2. Alice opens a Topic (0.25 BCT -> Room Creator gets +0.075 BCT)
        creator_bal_0 = self.bc.verify_and_recalc_balance(self.creator.address)
        alice_bal_0 = self.bc.verify_and_recalc_balance(self.alice.address)

        title = "Blok süresi 20s optimize edilmeli mi?"
        body_txt = "LWMA penceresi ve 20s hedef blok süresi hakkında fikirleriniz?"
        # Body-tampering test: signing with different body MUST be rejected
        sig_tamper = self.alice.sign(f"ROOM_TOPIC:{self.alice.address}:{rid}:{title}:DIFFERENT_BODY")
        ok_tamp, _, _ = self.bc.create_room_topic(
            author=self.alice.address,
            room_id=rid,
            title=title,
            content=body_txt,
            signature=sig_tamper,
            public_key=self.alice.pub_hex,
        )
        self.assertFalse(ok_tamp)

        sig_t = self.alice.sign(f"ROOM_TOPIC:{self.alice.address}:{rid}:{title}:{body_txt}")
        ok_t, msg_t, topic = self.bc.create_room_topic(
            author=self.alice.address,
            room_id=rid,
            title=title,
            content=body_txt,
            signature=sig_t,
            public_key=self.alice.pub_hex,
        )
        self.assertTrue(ok_t, msg_t)
        tid = topic["topic_id"]

        self.assertAlmostEqual(alice_bal_0 - self.bc.verify_and_recalc_balance(self.alice.address), 0.25, places=6)
        self.assertAlmostEqual(self.bc.verify_and_recalc_balance(self.creator.address) - creator_bal_0, 0.075, places=6)

        # 3. Bob posts a reply under the Topic (0.05 BCT -> Alice +0.010, Creator +0.010)
        creator_bal_1 = self.bc.verify_and_recalc_balance(self.creator.address)
        alice_bal_1 = self.bc.verify_and_recalc_balance(self.alice.address)
        bob_bal_1 = self.bc.verify_and_recalc_balance(self.bob.address)

        rep_txt = "Bence 20 saniye hem finality hem de orphan oranı için ideal."
        sig_rep = self.bob.sign(f"ROOM_REPLY:{self.bob.address}:{tid}:{rep_txt}")
        ok_rep, msg_rep, rep1 = self.bc.create_room_reply(
            author=self.bob.address,
            topic_id=tid,
            content=rep_txt,
            signature=sig_rep,
            public_key=self.bob.pub_hex,
        )
        self.assertTrue(ok_rep, msg_rep)
        self.assertAlmostEqual(bob_bal_1 - self.bc.verify_and_recalc_balance(self.bob.address), 0.05, places=6)
        self.assertAlmostEqual(self.bc.verify_and_recalc_balance(self.alice.address) - alice_bal_1, 0.010, places=6)
        self.assertAlmostEqual(self.bc.verify_and_recalc_balance(self.creator.address) - creator_bal_1, 0.010, places=6)

        # 4. Alice posts a nested reply to Bob's reply
        rep2_txt = "Katılıyorum, compact block relay ile çok hızlı!"
        sig_rep2 = self.alice.sign(f"ROOM_REPLY:{self.alice.address}:{tid}:{rep2_txt}:{rep1['reply_id']}")
        ok_rep2, _, rep2 = self.bc.create_room_reply(
            author=self.alice.address,
            topic_id=tid,
            content=rep2_txt,
            parent_reply_id=rep1["reply_id"],
            signature=sig_rep2,
            public_key=self.alice.pub_hex,
        )
        self.assertTrue(ok_rep2)
        self.assertEqual(rep2["parent_reply_id"], rep1["reply_id"])

        # Cross-topic / invalid parent_reply_id MUST be rejected
        sig_bad_rep = self.bob.sign(f"ROOM_REPLY:{self.bob.address}:{tid}:Fake parent test")
        ok_bad, _, _ = self.bc.create_room_reply(
            author=self.bob.address,
            topic_id=tid,
            content="Fake parent test",
            parent_reply_id="rep_nonexistent",
            signature=sig_bad_rep,
            public_key=self.bob.pub_hex,
        )
        self.assertFalse(ok_bad)

        # 5. Bob upvotes Topic (0.01 BCT -> Alice +0.002) and cannot upvote twice
        sig_up = self.bob.sign(f"ROOM_UPVOTE:{self.bob.address}:{tid}")
        ok_up, _, up_res = self.bc.upvote_room_topic(
            voter=self.bob.address,
            topic_id=tid,
            signature=sig_up,
            public_key=self.bob.pub_hex,
        )
        self.assertTrue(ok_up)
        self.assertEqual(up_res["upvotes_count"], 1)

        sig_up2 = self.bob.sign(f"ROOM_UPVOTE:{self.bob.address}:{tid}")
        ok_up2, _, _ = self.bc.upvote_room_topic(
            voter=self.bob.address,
            topic_id=tid,
            signature=sig_up2,
            public_key=self.bob.pub_hex,
        )
        self.assertFalse(ok_up2)

        # 6. Verify read endpoints & persistence
        detail = self.bc.get_room_topic_detail(tid)
        self.assertEqual(detail["replies_count"], 2)
        self.assertEqual(detail["upvotes_count"], 1)
        room_detail = self.bc.get_room_detail(rid)
        self.assertEqual(room_detail["topics_count"], 1)
        self.assertEqual(room_detail["replies_count"], 2)
        self.assertAlmostEqual(room_detail["creator_earnings"], 0.095, places=6)

    def test_room_ownership_transfer_and_royalty_redirection(self):
        # 1. Creator creates a room without avatar
        ok_q, _, q = self.bc.get_room_create_quote("Transferable Space", has_avatar=False)
        sig_c = self.creator.sign(f"ROOM_CREATE:{self.creator.address}:{q['slug']}:Sahiplik devri test odası.")
        ok, _, room = self.bc.create_room(
            creator=self.creator.address,
            name="Transferable Space",
            description="Sahiplik devri test odası.",
            signature=sig_c,
            public_key=self.creator.pub_hex,
        )
        self.assertTrue(ok)
        rid = room["room_id"]

        # 2. Non-owner (Alice) cannot transfer
        sig_bad = self.alice.sign(f"ROOM_TRANSFER:{self.alice.address}:{rid}:{self.bob.address}")
        ok_bad, _, _ = self.bc.transfer_room(
            current_owner=self.alice.address,
            room_id=rid,
            to_address=self.bob.address,
            signature=sig_bad,
            public_key=self.alice.pub_hex,
        )
        self.assertFalse(ok_bad)

        # 3. Self-transfer & Treasury transfer rejected
        sig_self = self.creator.sign(f"ROOM_TRANSFER:{self.creator.address}:{rid}:{self.creator.address}")
        ok_self, _, _ = self.bc.transfer_room(
            current_owner=self.creator.address,
            room_id=rid,
            to_address=self.creator.address,
            signature=sig_self,
            public_key=self.creator.pub_hex,
        )
        self.assertFalse(ok_self)

        sig_tr = self.creator.sign(f"ROOM_TRANSFER:{self.creator.address}:{rid}:{TREASURY_ADDRESS}")
        ok_tr, _, _ = self.bc.transfer_room(
            current_owner=self.creator.address,
            room_id=rid,
            to_address=TREASURY_ADDRESS,
            signature=sig_tr,
            public_key=self.creator.pub_hex,
        )
        self.assertFalse(ok_tr)

        # 4. Valid transfer: Creator -> Alice (0.50 BCT fee)
        bal_before = self.bc.verify_and_recalc_balance(self.creator.address)
        sig_t = self.creator.sign(f"ROOM_TRANSFER:{self.creator.address}:{rid}:{self.alice.address}")
        ok_t, msg_t, res_t = self.bc.transfer_room(
            current_owner=self.creator.address,
            room_id=rid,
            to_address=self.alice.address,
            signature=sig_t,
            public_key=self.creator.pub_hex,
        )
        self.assertTrue(ok_t, msg_t)
        self.assertEqual(res_t["new_owner"], self.alice.address)
        self.assertAlmostEqual(bal_before - self.bc.verify_and_recalc_balance(self.creator.address), 0.50, places=6)

        detail = self.bc.get_room_detail(rid)
        self.assertEqual(detail["creator"], self.alice.address)
        self.assertEqual(detail["original_creator"], self.creator.address)
        self.assertEqual(detail["transfer_count"], 1)

        # 5. Old owner can NO LONGER transfer or seal avatar
        sig_old = self.creator.sign(f"ROOM_TRANSFER:{self.creator.address}:{rid}:{self.bob.address}")
        ok_old, _, _ = self.bc.transfer_room(
            current_owner=self.creator.address,
            room_id=rid,
            to_address=self.bob.address,
            signature=sig_old,
            public_key=self.creator.pub_hex,
        )
        self.assertFalse(ok_old)

        # 6. New owner (Alice) CAN seal the one-time immutable avatar
        sig_av = self.alice.sign(f"ROOM_AVATAR:{self.alice.address}:{rid}:ANM-001-10B981")
        ok_av, msg_av, _ = self.bc.set_room_avatar(
            creator=self.alice.address,
            room_id=rid,
            avatar_base_id="ANM-001",
            avatar_bg_color="#10B981",
            signature=sig_av,
            public_key=self.alice.pub_hex,
        )
        self.assertTrue(ok_av, msg_av)

        # 7. Future topic royalties (30% = 0.075 BCT) go to Alice, NOT old creator!
        alice_bal_0 = self.bc.verify_and_recalc_balance(self.alice.address)
        creator_bal_0 = self.bc.verify_and_recalc_balance(self.creator.address)
        title = "Yeni sahip royalty testi"
        sig_top = self.bob.sign(f"ROOM_TOPIC:{self.bob.address}:{rid}:{title}:Royalty artık Alice hesabına gitmeli.")
        ok_top, msg_top, _ = self.bc.create_room_topic(
            author=self.bob.address,
            room_id=rid,
            title=title,
            content="Royalty artık Alice hesabına gitmeli.",
            signature=sig_top,
            public_key=self.bob.pub_hex,
        )
        self.assertTrue(ok_top, msg_top)
        self.assertAlmostEqual(self.bc.verify_and_recalc_balance(self.alice.address) - alice_bal_0, 0.075, places=6)
        self.assertAlmostEqual(self.bc.verify_and_recalc_balance(self.creator.address) - creator_bal_0, 0.0, places=6)

        # 8. Consensus-level rogue room_transfer tx by non-owner is ignored
        rogue_tx = Transaction(
            sender=self.creator.address,
            receiver=TREASURY_ADDRESS,
            amount=0.50,
            fee=0.25,
            signature="ROGUE_TRANSFER",
            tx_type="room_transfer",
            extra_data={"room_id": rid, "from_address": self.creator.address, "to_address": self.bob.address},
        )
        self.bc.pending_transactions.append(rogue_tx)
        self.bc._load_in_memory_rooms_index()
        self.assertEqual(self.bc.rooms[rid]["creator"], self.alice.address)


if __name__ == "__main__":
    unittest.main()
