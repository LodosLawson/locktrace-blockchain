import sys
import time
import secrets
sys.path.insert(0, '.')
from core.blockchain import Blockchain, Transaction, normalize_bct_address
from config import Config

print("=== 1. Testing BNS Reserved Namespace Protection ===")
bc = Blockchain()
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
# Even if staked >= 1000, if not auth_verified, is_active_validator must return False!
bc._confirmed_stakes_map[test_addr] = 1000 * 100_000_000
bc._confirmed_units_map["BCT9999999999999999999999999999999999999999"] = 10000 * 100_000_000
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

print("\nALL SECURITY AUDIT VERIFICATIONS PASSED SUCCESSFULLY!")
