# LockTrace Blockchain v2.12.3 — Mainnet Security Hardening, 1:1 Bridge Proof-of-Reserve & Soulbound Avatars

**Release Tag:** `v2.12.3`
**Live Mainnet:** https://locktrace.space
**Official Base Mainnet wBCT (v2):** [`0xCa6152Ae0E785F90ED65cd706B386E5B83D0EB28`](https://basescan.org/token/0xCa6152Ae0E785F90ED65cd706B386E5B83D0EB28)
**Chain Integrity Status:** `chain_valid: true` (100% verified from Genesis Block `#0`)

---

## Highlights

### 1. Consensus, PoW & BFT Finality Hardening
- **Cumulative Deterministic LWMA Difficulty (`core/blockchain.py`):** Upgraded `get_current_difficulty()` via `compute_lwma_difficulty()` to track effective median leading-zero work across `LWMA_WINDOW = 20` blocks, enabling cumulative scaling across `[2 .. MAX_DIFFICULTY=8]` with emergency stall recovery.
- **v2 Header-Hash Parity & `chain_valid: true` (`core/blockchain.py`):** Aligned `Block.calculate_hash()` with `Block.mine()` canonical v2 header hashing (`_header_hash()`) while maintaining full backwards-compatible verification for historical blocks `#0–#884`, and aligned `is_chain_valid()` LWMA + stall-recovery ordering.
- **Persistent Post-Block 2/3 BFT Finality (`core/storage.py`, `core/blockchain.py`):** Persisted `finalized_height` monotonically in SQLite `meta` and restored `block.finalized` state across restarts and multi-worker delta loads.
- **Zero-Fee Block Subsidy Guard (`core/blockchain.py`):** Restricted the `0.05 BCT` Treasury block subsidy to blocks containing fee-paying third-party transactions (`fee > 0`), preventing zero-fee `frontend_release`, `reward`, `validator_stake`, and `validator_unstake` blocks from draining Treasury.

### 2. Cross-Chain Bridge (Base Mainnet `wBCT`) Security & 1:1 Proof-of-Reserve
- **Canonical `blockHash` Reorg Protection (`core/bridge.py`):** `verify_evm_burn_receipt()` now verifies `status == 0x1`, minimum `12` Base confirmations (`MIN_EVM_CONFIRMATIONS`), AND exact canonical parity via `eth_getBlockByNumber(blockNumber).hash == receipt.blockHash` (fail-closed on reorg/mismatch).
- **Bridge Vault 1:1 Reserve Invariant Fix (`core/blockchain.py`, `core/bridge_relayer.py`):** Exempted `L1_TO_EVM` lock deposits to `BCT_BRIDGE_VAULT` from the 1% L1 transfer fee (`fee = 0.0`) so 100% of locked BCT enters the vault while the 0.2% bridge fee remains as positive reserve surplus. Enforced a hard relayer cap (`mint_amount <= actual_vault_credit`) and verified recipient == `BCT_BRIDGE_VAULT`.
- **Cross-Direction `tx_hash_evm` Protection (`core/bridge.py`, `server.py`):** Blocked `EVM_TO_L1` burn claims from colliding with or overwriting completed `L1_TO_EVM` mint records.

### 3. Storage & Concurrency Hardening
- **Concurrency-Safe SQLite Mempool Merge (`core/storage.py`):** Replaced full `DELETE FROM mempool` wipes inside `save_state()` with incremental `tx_lookup`-pruned + `INSERT OR IGNORE` merging inside `BEGIN IMMEDIATE` WAL transactions, eliminating multi-worker lost updates.

### 4. Transfer Fee UX, Soulbound Avatars & Mobile Polish
- **Sender-Pays Transfer Fee Model (`core/blockchain.py`, `frontend/`):** Backwards-compatible `extra_data={"fee_mode": "sender_pays"}` transfers ensure recipients receive 100% of the entered amount while the 1% network fee is deducted separately from the sender's wallet (preserving 100% historical balance parity).
- **Transfer Signature Confirmation Modal (`frontend/index.html`):** Added an explicit ECDSA signing confirmation dialog showing Recipient, Amount to Recipient, Network Fee, and Total Deducted before signing.
- **On-Chain Soulbound Profile Avatars (`core/avatar_catalog.py`, `frontend/simple-mode/simple-mode.js`):** Bonding-curve avatar minting (`0.10 BCT` opening price, `+25%` per mint per `BASE_ID-HEXCOLOR` variant; `0.20 BCT` equip/unequip, `0.40 BCT` swap; 30% Treasury / 70% Block Reward Pool) with 60fps mobile-safe in-place custom color picker + manual `#HEX` input.
- **Feed Ordering & Pro Mode Mobile Menu Guard (`core/blockchain.py`, `frontend/`):** Removed static MD5 `for_you` jitter, enforced chronological newest-first feed ordering in Simple Mode, and added a 1-second touch/click guard when opening the Pro Mode mobile menu drawer.

### 5. Public Security Disclosures & Documentation Parity
- Added public transparency cards in the live Explorer (**System Addresses / Burn Addresses**) and published [`docs/SECURITY_DISCLOSURES.md`](docs/SECURITY_DISCLOSURES.md) covering the Block `#749` slashed validator note, retired legacy v1 `wBCT` contract (`0xa3c743...7254`), bridge reserve fix, and authorized mainnet red-team probe results.
- Synchronized `README.md`, `docs/WHITEPAPER.md`, `frontend/docs/WHITEPAPER.md`, and `docs/LOCKTRACE_NOTION_WORKSPACE.md`.

---

## Verification & Deployment
- **On-Chain Frontend Sealing:** Signed and sealed on mainnet via `scripts/fast_deploy.py` (`verified: true`).
- **Node Setup:**
  ```bash
  git clone https://github.com/LodosLawson/locktrace-blockchain.git
  cd locktrace-blockchain
  git checkout v2.12.3
  pip install -r requirements.txt
  python3 node_runner.py --name "My-Validator-Node"
  ```
