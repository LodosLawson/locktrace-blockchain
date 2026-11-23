# LockTrace Mainnet Security Disclosures & Red-Team Test Log

This public ledger documents known immutable historical artifacts, resolved vulnerabilities, and authorized mainnet security / penetration tests on LockTrace Layer-1 (`https://locktrace.space`) and Base Mainnet (`wBCT`).

## 1. Historical Immutable Ledger Notes

### A. Block #749 Slashed Malicious Validator (`-989.986 BCT`)
- **Address:** `BCTa3cf1fe94acd83ea39b247665ccb8fcee080cb44`
- **What happened:** At Block #749, this validator attempted a double-unstake & dust-mining exploit, leaving a permanent `-989.986 BCT` negative balance artifact on the immutable ledger.
- **Resolution:** The validator was permanently slashed and blacklisted in protocol configuration (`SLASHED_MALICIOUS_VALIDATORS`), and the underlying atomic unstake/nonce vulnerability was permanently patched in protocol v2.9.4/v2.9.5.

### B. Decommissioned Legacy wBCT v1 Contract (`0xa3c743113a41cfd0146917065d4578337bb77254`)
- **BaseScan display:** Still shows `60,175,825.84 wBCT` on Base Mainnet because ERC-20 historical contracts are immutable.
- **Resolution:** Formally decommissioned at **Block #835** (`0xa79_v1_decommission`), permanently blocked in `config.py` (`_DEPRECATED_WBCT_CONTRACTS`), and replaced by the official v2 WrappedBlocTag contract **`0xCa6152Ae0E785F90ED65cd706B386E5B83D0EB28`**.

### C. Bridge Vault 0.8% Fee Mismatch Fix (2026-11-23)
- **Root Cause:** Standard L1 `transfer` transactions to `BCT_BRIDGE_VAULT` deducted the 1.0% L1 transfer fee (crediting only 99.0% to the vault), while the Base bridge minted 99.8% (0.2% bridge fee). A 100,000 BCT round-trip test on Nov 22 (Blocks #921–#922) created an `800.00 BCT` deficit (total `820.5147 BCT` across v2 bridge transactions).
- **Resolution:**
  1. `core/blockchain.py`: Deposits to `BCT_BRIDGE_VAULT` are now exempt from the 1.0% L1 transfer fee (`fee = 0.0`) so 100% of deposited BCT enters the vault while the 0.2% bridge fee remains inside the vault as positive reserve surplus.
  2. `core/bridge_relayer.py`: Enforces a strict Proof-of-Reserve invariant — the relayer verifies the L1 lock recipient is `BCT_BRIDGE_VAULT` and caps any Base `wBCT` mint at `<= actual_vault_credit`.
- **Closing the Existing `820.5147 BCT` Deficit:** Deposit `820.5147 BCT` directly into `BCT_BRIDGE_VAULT_000000000000000000000000000000000` (without creating a bridge mint order) so `L1 BRIDGE_VAULT == Base wBCT totalSupply` (`2,645.27240322 BCT`) with 100% 1:1 backing.

## 2. Authorized Mainnet Security & Red-Team Test Log

| Date (UTC) | Target | Probe / Test Description | Result |
| :--- | :--- | :--- | :--- |
| **2026-11-22 – 2026-11-23** | `EVM_TO_L1` Bridge Claim | Synthetic burn claims with dummy hashes (`0xdeadbeef...`, `0xababab...`, `0x4444...`, `0x3333...`, `0x1111...`, `0x0000...beef`) | **100% Blocked** — 0 BCT unlocked; rejected by fail-closed Base RPC receipt, 12-confirmation, and canonical `blockHash` checks. |
| **2026-11-23** | Consensus / Storage / Bridge | Cumulative LWMA scaling, persisted BFT `finalized_height`, concurrent SQLite mempool merge, and canonical `blockHash` verification tests | **4/4 Passed** — deployed to mainnet (`efa092e`). |
