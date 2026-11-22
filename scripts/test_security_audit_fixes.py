import sys
import time
import secrets
import tempfile
import shutil
sys.path.insert(0, '.')
from core.blockchain import Blockchain, Transaction, normalize_bct_address
from config import Config

_test_temp_dir = tempfile.mkdtemp(prefix="locktrace_audit_test_")
print(f"Running tests in isolated directory: {_test_temp_dir}")
print("=== 1. Testing BNS Reserved Namespace Protection ===")
bc = Blockchain(auto_mine=False, data_dir=_test_temp_dir)
for name in ["treasury", "genesis", "bridge", "vault", "admin", "system", "bct", "foundation"]:
    pricing = bc.get_bns_pricing(name)
    avail = bc.bns_check_available(name)
    print(f"Testing '{name}.bct': valid={pricing['valid']}, avail={avail['available']}, reason='{avail['reason']}'")
    assert not pricing["valid"], f"Expected {name} to be invalid"
    assert not avail["available"], f"Expected {name} to be unavailable"

# Normal handle should be available (if not registered)
normal_pricing = bc.get_bns_pricing("mycrypto123")
assert normal_pricing["valid"], "Expected normal handle to be valid"
print("Normal handle 'mycrypto123.bct': valid=True (Passed)")

print("\n=== 2. Testing is_active_validator Auth Verification ===")
# Create dummy node without auth_verified
test_addr = "BCT1111111111111111111111111111111111111111"
bc.nodes["test-unauth-node"] = {
    "node_id": "test-unauth-node",
    "miner_address": test_addr,
    "auth_verified": False,
    "is_genesis": False,
}
from core.blockchain import VALIDATOR_STAKE_VAULT_ADDRESS
bc._ensure_ledger_index()
bc._confirmed_stakes_map[test_addr] = 1000 * 100_000_000
bc._confirmed_units_map[VALIDATOR_STAKE_VAULT_ADDRESS] = 10000 * 100_000_000
is_val_unauth = bc.is_active_validator(test_addr)
print(f"Unauthenticated node is_active_validator: {is_val_unauth} (Expected: False)")
assert not is_val_unauth, "Unauthenticated peer node should NOT be an active validator!"

# Now set auth_verified = True
bc.nodes["test-unauth-node"]["auth_verified"] = True
is_val_auth = bc.is_active_validator(test_addr)
print(f"Authenticated node is_active_validator: {is_val_auth} (Expected: True)")
assert is_val_auth, "Authenticated staked node should be an active validator!"

# Clean up test node
del bc.nodes["test-unauth-node"]
del bc._confirmed_stakes_map[test_addr]

print("\n=== 3. Testing Slashed Addresses Consensus Disqualification ===")
for s in Config.SLASHED_MALICIOUS_VALIDATORS:
    assert not bc.is_active_validator(s), f"{s} should NOT be active validator"
    can_stake, msg, _ = bc.execute_validator_stake(s, 1000.0, "sig")
    assert not can_stake, f"{s} should be barred from staking"
print("All slashed validators barred from staking and consensus roles! (Passed)")

print("\n=== 4. Testing Chain Validity ===")
valid = bc.is_chain_valid()
print(f"Blockchain is_chain_valid(): {valid} (Chain length: {len(bc.chain)})")
assert valid, "Blockchain integrity must be valid!"

print("\n=== 5. Testing Case-Insensitive Slashing Enforcement Across All Consensus Endpoints ===")
test_slashed = Config.SLASHED_MALICIOUS_VALIDATORS[0]
test_slashed_lower = test_slashed.lower()
test_slashed_upper = "BCT" + test_slashed[3:].upper()

for variant in [test_slashed, test_slashed_lower, test_slashed_upper]:
    assert not bc.is_active_validator(variant), f"{variant} must NOT be active validator"
    # build_mining_template must reject
    ok, msg, _ = bc.build_mining_template(variant)
    assert not ok and "Slashed" in msg, f"build_mining_template should reject slashed address {variant}: {msg}"
    # submit_mined_block must reject
    dummy_block = {"miner": variant, "hash": "0000", "index": 1, "nonce": 1, "version": 2}
    ok, msg, _ = bc.submit_mined_block(dummy_block, "sig", "pub")
    assert not ok and "Slashed" in msg, f"submit_mined_block should reject slashed address {variant}: {msg}"
    # attest_block must reject
    ok, msg, _ = bc.attest_block("node-test", variant, 1, "0000", "pub", "sig", 1000)
    assert not ok and ("Slashed" in msg or "slashed" in msg), f"attest_block should reject slashed address {variant}: {msg}"
    # get_user_profile tag must be slashed
    details = bc.get_user_profile(variant)
    assert details["is_slashed"] and details["tag_type"] == "slashed", f"get_user_profile failed for {variant}"

print("Case-insensitive slashing correctly enforced across all consensus methods! (Passed)")

print("\n=== 6. Testing Node Impersonation Defense (Public Key vs Miner Address Binding) ===")
from core.wallet import Wallet
wallet_a = Wallet() # Genuine validator
wallet_b = Wallet() # Malicious attacker attempting to impersonate wallet_a

ts = time.time()
clean_id = f"test-impersonate-{secrets.token_hex(4)}"
msg = f"NODE:{clean_id}:{wallet_a.address}:{ts}"
# Attacker signs the message with their own private key for wallet_b, but claims wallet_a.address!
fake_sig = wallet_b.sign(msg)

node_res = bc.register_or_ping_node(
    node_id=clean_id,
    miner_address=wallet_a.address,
    public_key=wallet_b.get_public_key_hex(),
    signature=fake_sig,
    timestamp=ts
)
print(f"Impersonation attempt auth_verified: {node_res.get('auth_verified')} (Expected: False)")
assert not node_res.get("auth_verified"), "Impersonation MUST NOT be authenticated!"

# Clean up test node
bc.nodes.pop(clean_id, None)

# Legitimate node signing with matching key MUST authenticate
legit_sig = wallet_a.sign(msg)
legit_res = bc.register_or_ping_node(
    node_id=clean_id,
    miner_address=wallet_a.address,
    public_key=wallet_a.get_public_key_hex(),
    signature=legit_sig,
    timestamp=ts
)
print(f"Legitimate node auth_verified: {legit_res.get('auth_verified')} (Expected: True)")
assert legit_res.get("auth_verified"), "Legitimate owner MUST be authenticated!"
bc.nodes.pop(clean_id, None)
print("Node identity impersonation defense verified! (Passed)")

print("\n=== 7. Testing node_runner.py P2P SSRF Protection ===")
from node_runner import LockTraceNode
assert not LockTraceNode._is_safe_peer_endpoint("http://169.254.169.254/latest/meta-data"), "Must block cloud metadata"
assert not LockTraceNode._is_safe_peer_endpoint("http://127.0.0.1:8080"), "Must block loopback"
assert not LockTraceNode._is_safe_peer_endpoint("http://10.0.0.1:5000"), "Must block private 10.x"
assert not LockTraceNode._is_safe_peer_endpoint("http://192.168.1.1:5000"), "Must block private 192.168.x"
assert not LockTraceNode._is_safe_peer_endpoint("http://224.0.0.1"), "Must block multicast"
assert LockTraceNode._is_safe_peer_endpoint("http://8.8.8.8:5000"), "Must allow valid public IP endpoint"
print("node_runner.py SSRF defenses verified! (Passed)")

print("\n=== 8. Testing BNS Accept Offer Accounting Inversion Guard ===")
# Verify that a malformed bns_accept_offer without seller extra_data never credits the recipient
units_map = {"BCT1111111111111111111111111111111111111111": 1000, "BCT2222222222222222222222222222222222222222": 500}
nonces = {}
tx_counts = {}
used_sigs = set()
rewarded = set()
malformed_tx = Transaction(
    sender="BCT1111111111111111111111111111111111111111",
    receiver="BCT2222222222222222222222222222222222222222",
    amount=100.0,
    fee=1.0,
    signature="test_sig",
    tx_type="bns_accept_offer",
    extra_data=None # Missing seller!
)
bc._apply_tx_to_ledger_maps(malformed_tx, units_map, nonces, tx_counts, used_sigs, rewarded)
# Balances must NOT have changed due to fail-closed guard
assert units_map["BCT1111111111111111111111111111111111111111"] == 1000
assert units_map["BCT2222222222222222222222222222222222222222"] == 500
print("BNS accept offer fail-closed accounting guard verified! (Passed)")

print("\n=== 9. Testing Anti-Whale MAX_TRANSACTION & MIN_TRANSACTION Enforcement ===")
w_sender = Wallet()
w_rec = Wallet()
bc.register_wallet(w_sender.address, w_sender.get_public_key_hex(), grant_welcome_bonus=False)
bc.register_wallet(w_rec.address, w_rec.get_public_key_hex(), grant_welcome_bonus=False)
# Give sender enough balance for testing
bc.balances[w_sender.address] = 5_000_000.0
bc._confirmed_units_map[w_sender.address] = 5_000_000 * 100_000_000

# 9.1 Dust transfer (< 0.01) must fail
sig_dust = w_sender.sign(f"{w_sender.address}{w_rec.address}0.005")
ok_dust, msg_dust, _ = bc.create_transaction(w_sender.address, w_rec.address, 0.005, sig_dust, w_sender.get_public_key_hex())
assert not ok_dust and "Minimum transfer" in msg_dust, f"Dust transfer should fail: {msg_dust}"
print("Core MIN_TRANSACTION dust rejection verified! (Passed)")

# 9.2 Whale transfer exceeding MAX_TRANSACTION (1,000,000 BCT, ~6.7% of circulating supply) must fail
sig_whale = w_sender.sign(f"{w_sender.address}{w_rec.address}1000001.0")
ok_whale, msg_whale, _ = bc.create_transaction(w_sender.address, w_rec.address, 1_000_001.0, sig_whale, w_sender.get_public_key_hex())
assert not ok_whale and "Maximum single transfer limit" in msg_whale, f"Whale transfer should fail: {msg_whale}"
print("Core MAX_TRANSACTION anti-whale limit verified! (Passed)")

# Clean up test balances
del bc.balances[w_sender.address]
del bc._confirmed_units_map[w_sender.address]

print("\n=== 10. Testing Validator Concurrent Unstake Mutex & Zero-Amount Rejection ===")
w_val = Wallet()
bc.register_wallet(w_val.address, w_val.get_public_key_hex(), grant_welcome_bonus=False)
bc._ensure_ledger_index()
bc._confirmed_stakes_map[w_val.address] = 2000 * 100_000_000
bc._confirmed_units_map[VALIDATOR_STAKE_VAULT_ADDRESS] = 10000 * 100_000_000

# 10.1 Zero unstake must fail
ok_zero, msg_zero, _ = bc.execute_validator_unstake(w_val.address, 0.0, "sig", w_val.get_public_key_hex())
assert not ok_zero and "greater than zero" in msg_zero, f"Zero unstake should fail: {msg_zero}"
print("Zero-amount unstake rejected! (Passed)")

# 10.2 First valid unstake queues in pending_transactions
sig_un1 = w_val.sign(f"VALIDATOR_UNSTAKE:{w_val.address}:500.0")
ok_un1, msg_un1, _ = bc.execute_validator_unstake(w_val.address, 500.0, sig_un1, w_val.get_public_key_hex())
assert ok_un1, f"First unstake should succeed: {msg_un1}"

# 10.3 Second concurrent unstake while first is pending MUST be rejected
sig_un2 = w_val.sign(f"VALIDATOR_UNSTAKE:{w_val.address}:500.0")
ok_un2, msg_un2, _ = bc.execute_validator_unstake(w_val.address, 500.0, sig_un2, w_val.get_public_key_hex())
assert not ok_un2 and "Bekleyen" in msg_un2, f"Concurrent unstake should fail: {msg_un2}"
print("Concurrent validator unstake mutex verified! (Passed)")

# Clean up pending
bc.pending_transactions = [tx for tx in bc.pending_transactions if tx.extra_data.get("staker") != w_val.address]
del bc._confirmed_stakes_map[w_val.address]

print("\n=== 11. Testing node_runner.py BNS Accept Offer Parity ===")
from node_runner import LockTraceNode
import os
test_data_dir = os.path.abspath("./test_node_data")
os.makedirs(test_data_dir, exist_ok=True)
lnode = LockTraceNode(miner_engine="python", enable_web=False, data_dir=test_data_dir)
# Construct a fake block with a malformed bns_accept_offer (missing seller)
fake_blk = {
    "index": 999999,
    "transactions": [{
        "sender": "BCT1111111111111111111111111111111111111111",
        "receiver": "BCT2222222222222222222222222222222222222222",
        "amount": 100.0,
        "fee": 1.0,
        "tx_type": "bns_accept_offer",
        "extra_data": {} # Missing seller!
    }]
}
lnode.chain_by_index[999999] = fake_blk
bal_rec, _, _ = lnode.local_calc_balance_and_nonce("BCT2222222222222222222222222222222222222222")
assert bal_rec == 0.0, f"Malformed bns_accept_offer must NOT credit receiver in node_runner! Got: {bal_rec}"
del lnode.chain_by_index[999999]
print("node_runner bns_accept_offer parity verified! (Passed)")

print("\n=== 12. Testing node_runner.py Transaction Limit Checks ===")
code_dust, resp_dust = lnode.handle_decentralized_write("/api/v1/transaction", {
    "sender": "BCT1111111111111111111111111111111111111111",
    "receiver": "BCT2222222222222222222222222222222222222222",
    "amount": 0.005,
    "signature": "sig"
})
assert code_dust == 400 and "Minimum transfer limit" in resp_dust.get("message", ""), f"node_runner dust failed: {resp_dust}"

code_whale, resp_whale = lnode.handle_decentralized_write("/api/v1/transaction", {
    "sender": "BCT1111111111111111111111111111111111111111",
    "receiver": "BCT2222222222222222222222222222222222222222",
    "amount": 1_000_001.0,
    "signature": "sig"
})
assert code_whale == 400 and "Maximum single transfer limit" in resp_whale.get("message", ""), f"node_runner whale failed: {resp_whale}"
print("node_runner MIN_TRANSACTION & MAX_TRANSACTION verified! (Passed)")

print("\n=== 13. Testing NaN / Infinity Timestamp Bypass Defenses ===")
ok_nan_att, msg_nan_att, _ = bc.attest_block("node-1", wallet_a.address, 0, "0000", wallet_a.get_public_key_hex(), "sig", float("nan"))
assert not ok_nan_att, f"NaN timestamp in attest_block MUST be rejected: {msg_nan_att}"
from core.push_service import PushNotificationService
ps = PushNotificationService(db_path=os.path.join(_test_temp_dir, "push_test.db"))
ok_nan_push, msg_nan_push = ps.subscribe(wallet_a.address, wallet_a.get_public_key_hex(), {"endpoint": "https://fcm.googleapis.com/fcm/send/123", "keys": {"p256dh": "a"*20, "auth": "b"*16}}, float("nan"), "sig")
assert not ok_nan_push, f"NaN timestamp in push subscribe MUST be rejected: {msg_nan_push}"
print("NaN / Infinity timestamp bypass defenses verified! (Passed)")

print("\n=== 14. Testing Confirmed-Cache Aliasing Isolation (Space & BNS Mempool Overlay) ===")
bc._load_in_memory_space_index()
bc._load_in_memory_bns_index()
confirmed_posts_before = len(bc._confirmed_space_posts)
confirmed_bns_before = len(bc._confirmed_bns_records)
bc.balances[wallet_a.address] = 500.0
bc._confirmed_units_map[wallet_a.address] = 500 * 100_000_000
sig_post = wallet_a.sign(f"{wallet_a.address}:Hello Audit Security Test")
ok_post, msg_post, post_res = bc.create_space_post(wallet_a.address, "Hello Audit Security Test", sig_post, wallet_a.get_public_key_hex())
assert ok_post, f"create_space_post failed: {msg_post}"
assert len(bc._confirmed_space_posts) == confirmed_posts_before, "Mempool post MUST NOT corrupt _confirmed_space_posts!"
assert post_res["post_id"] in bc.space_posts, "Mempool post must be visible in overlay space_posts!"
print("Confirmed-cache aliasing isolation verified! (Passed)")

print("\n=== 15. Testing Atomic Under-Lock Nonce TOCTOU Guard ===")
bc._pending_auth_nonces["stale_nonce_sig"] = 999
sig_toctou = wallet_a.sign(f"{wallet_a.address}:{wallet_b.address}:1.0")
# Inject mismatched pending auth nonce for this signature
bc._pending_auth_nonces[sig_toctou] = 999
ok_toc, msg_toc = bc._verify_actor_signature(wallet_a.address, f"{wallet_a.address}:{wallet_b.address}:1.0", sig_toctou, wallet_a.get_public_key_hex())
assert not ok_toc and "nonce conflict" in msg_toc.lower(), f"TOCTOU nonce mismatch must be rejected under lock: {msg_toc}"
print("Atomic under-lock TOCTOU nonce guard verified! (Passed)")

print("\nALL SECURITY AUDIT VERIFICATIONS PASSED SUCCESSFULLY!")

try:
    shutil.rmtree(_test_temp_dir, ignore_errors=True)
    if os.path.exists("./test_node_data"):
        shutil.rmtree("./test_node_data", ignore_errors=True)
except Exception:
    pass
