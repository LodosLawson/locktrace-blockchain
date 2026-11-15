import sys
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

print("\nALL SECURITY AUDIT VERIFICATIONS PASSED SUCCESSFULLY!")
