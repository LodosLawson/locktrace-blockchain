# 🛡️ LockTrace: Decentralized Layer-1 Blockchain & Sovereign Asset Protocol

<p align="center">
  <img src="frontend/icons/icon-192.png" width="128" height="128" alt="LockTrace Official Logo" />
</p>

[![Mainnet Status](https://img.shields.io/badge/Mainnet-Online%20%28Stockholm%29-10b981?style=for-the-badge&logo=oracle)](https://locktrace.space)
[![Total Supply](https://img.shields.io/badge/Total%20Supply-1%20Trillion%20BCT-2563eb?style=for-the-badge)](https://locktrace.space)
[![Base Mainnet wBCT](https://img.shields.io/badge/Base%20L2-wBCT%20Bridge-0052ff?style=for-the-badge&logo=coinbase)](https://basescan.org/token/0xA3C743113a41cFd0146917065d4578337Bb77254)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-181717?style=for-the-badge&logo=github)](https://github.com/LodosLawson/locktrace-blockchain)
[![Telegram](https://img.shields.io/badge/Telegram-Channel-229ED9?style=for-the-badge&logo=telegram)](https://t.me/+zsaG1qkAHZllZGIy)
[![X / Twitter](https://img.shields.io/badge/X-@LockTraceSpace-000000?style=for-the-badge&logo=x)](https://x.com/LockTraceSpace)
[![Instagram](https://img.shields.io/badge/Instagram-@locktracespace-E4405F?style=for-the-badge&logo=instagram)](https://www.instagram.com/locktracespace)
[![Official Email](https://img.shields.io/badge/Email-locktracetoken%2Bspace%40gmail.com-EA4335?style=for-the-badge&logo=gmail)](mailto:locktracetoken+space@gmail.com)

LockTrace is an independent, high-performance Layer-1 decentralized blockchain ledger built for sovereign asset custody, instantaneous peer-to-peer settlement, censorship-resistant on-chain social networking, and cross-chain liquidity. Engineered with deterministic macro-monetary rules, BIP-39 mnemonic key derivation, SECP256k1 ECDSA cryptography, hybrid 70% PoW + 30% BFT Quorum consensus, native Name Service (BNS `.bct`), and cryptographically signed on-chain frontend releases.

---

## 🌐 Official Channels & Community Links

- **Official Web Portal & Web3 DApp:** [https://locktrace.space](https://locktrace.space)
- **Official Contact & Inquiries:** [`locktracetoken@gmail.com`](mailto:locktracetoken@gmail.com) / [`locktracetoken+space@gmail.com`](mailto:locktracetoken+space@gmail.com)
- **Telegram Channel:** [https://t.me/+zsaG1qkAHZllZGIy](https://t.me/+zsaG1qkAHZllZGIy)
- **X (Twitter):** [@LockTraceSpace](https://x.com/LockTraceSpace)
- **Instagram:** [@locktracespace](https://www.instagram.com/locktracespace)
- **GitHub Repository:** [LodosLawson/locktrace-blockchain](https://github.com/LodosLawson/locktrace-blockchain)
- **Base L2 Contract:** [`0xA3C743113a41cFd0146917065d4578337Bb77254`](https://basescan.org/token/0xA3C743113a41cFd0146917065d4578337Bb77254)

---

## 🏛️ Monetary Policy & Core Tokenomics

| Metric | Specification | Verification Rule |
| :--- | :--- | :--- |
| **Asset Symbol** | **BCT** (BlockChain Trace) | Native Layer-1 cryptographic ledger unit |
| **Total Supply** | **1,000,000,000,000.00 BCT** (1 Trillion) | Fixed in Genesis Block #0. Mathematically hard-capped; zero future minting or inflation. |
| **Genesis Treasury Vault** | `BCT_HAZINE_0000000000000000000000000000000000000000` | Holds uncirculated reserves, genesis subsidies, and welcome grants. |
| **Cross-Chain Bridge Vault** | `BCT_BRIDGE_VAULT_000000000000000000000000000000000` | Holds 1:1 escrowed L1 collateral backing EVM wrapped tokens (43 chars). |
| **Validator Staking Vault** | `BCT_STAKE_VAULT_00000000000000000000000000000000` | Holds 1,000.00 BCT PoS validator collateral qualifying for 30% Quorum Pool. |
| **Provable Burn Address** | `BCT0000000000000000000000000000000000000000` | Deflationary burn address (effectively provable lost key sink). |
| **Welcome Grant** | **1.00 BCT** automated protocol grant | Granted directly from Treasury Vault to every newly generated wallet address. |
| **Transaction Fee** | **1.0%** automated protocol fee | **50% permanently locked to Treasury** (deflationary supply reduction). Remaining 50% split **70% to Block Proposer/Miner** and **30% to Validator Quorum**. |
| **Key Derivation** | **BIP-39 Mnemonic** + ECDSA SECP256k1 | 12-word seed phrase + 256-bit private key. |
| **Consensus Engine** | **Hybrid 70% PoW + 30% BFT Quorum** | Dynamic SHA-256 target difficulty + validator multi-signature confirmation. |
| **EVM Bridge (Base L2)**| **Wrapped BCT (wBCT)** | ERC-20 token on Base Mainnet (`0xA3C743113a41cFd0146917065d4578337Bb77254`), 1:1 backed. |

---

## 🌌 LockTrace Space: Censorship-Resistant Social Economy

LockTrace Space embeds social interactions directly into the Layer-1 transaction graph. Thoughts, likes, and comments are decentralized financial interactions where creators receive direct micro-royalties without intermediaries:

- **Publish Post (`space_post`):** Cost is **0.10 BCT** to prevent spam and ensure content permanence. Content is permanently stored across blockchain blocks (80% Treasury pool, 20% fee pool).
- **Like Royalty (`space_like`):** Cost is **0.01 BCT**. **+0.002 BCT is instantly paid on-chain to the post creator's wallet** as creator royalty (70% Treasury, 10% fee pool).
- **Comment Royalty (`space_comment`):** Cost is **0.02 BCT**. **+0.004 BCT is transferred directly to the thread author's wallet** (70% Treasury, 10% fee pool).
- **Follow Creator (`space_follow`):** Cost is **1.00 BCT**. **+0.50 BCT is transferred directly to the creator's wallet** (30% miner/quorum pool, 20% Treasury).
- **Anti-Spam Action Cooldowns:** Enforced per-wallet cooldowns to prevent spam and double-spend race conditions (Transfer: 3s, Post: 10s, Like: 0s Instant, Comment: 5s, Follow: 3s, BNS Register: 10s).
- **Tip Royalty (`space_tip`):** Readers can tip creators directly in any custom amount of BCT with 0% intermediary commission.
- **Creator Identity:** Verified via on-chain BNS `.bct` handles or verified public ECDSA wallet addresses.

### ⚡ Hybrid Batching & Sequencer Architecture (Time + Quota)
To maintain ultra-lean blockchain storage, eliminate micro-block bloat, and protect network validator bandwidth while delivering instantaneous Web3 social responsiveness, LockTrace implements an intelligent **Time + Quota Hybrid Batching Sequencer**:

$$\text{Block Trigger} = (\Delta t \ge T_{\text{window}}) \quad \mathbf{OR} \quad (N_{\text{tx}} \ge Q_{\text{quota}})$$

- **Likes Batching Window (`space_like`):**
  - **Time Window ($T_{\text{window}}$):** Max **20 seconds**. All likes across the global network within 20s are pooled in mempool and sealed together into a single PoW block.
  - **Quota Threshold ($Q_{\text{quota}}$):** **15 Likes**. If 15 likes arrive before 20s, the batch block seals **immediately**.
- **Comments Batching Window (`space_comment`):**
  - **Time Window ($T_{\text{window}}$):** Max **50 seconds**.
  - **Quota Threshold ($Q_{\text{quota}}$):** **10 Comments**. If 10 comments accumulate, the batch block seals immediately.
- **Security & Cryptographic Integrity:**
  - **Mempool Double-Action Prevention:** Rejects duplicate likes or duplicate comments in real-time before block packaging.
  - **Sequential Nonce Preservation:** Supports multiple actions from the same user within the same batch window with strictly incremented sequential nonces ($n, n+1, n+2$).
  - **Optimistic Web3 UI Responsiveness:** Client feeds reflect social interactions and creator balances instantly while the cryptographic PoW block seals in the background.

---

## 🏷️ LockTrace Name Service (BNS - `.bct` Handles)

LockTrace features a native on-chain domain and identity protocol that maps human-readable names (`@handle.bct`) to 43-character hex addresses (`BCT...`).

### 💰 Tiered Pricing & 80/20 Protocol Treasury Pool Tokenomics
- **3-Letter Handles (Premium Tier):** `100.0 BCT` (e.g. `btc.bct`, `eth.bct`, `ceo.bct`)
- **4-Letter Handles (Standard Tier):** `50.0 BCT` (e.g. `alex.bct`, `moon.bct`, `lock.bct`)
- **5+ Character Handles (General Tier):** `10.0 BCT` (e.g. `satoshi.bct`, `locktrace.bct`)

**Tokenomics Breakdown:**
- **🏦 80% Returns to Protocol Treasury Pool:** 80% of paid registration fees return directly into the Protocol Treasury Vault pool (Hazine havuzuna geri aktarım, yakım değil), replenishing the ecosystem reserves.
- **⚡ 20% Returned to Active Participants:** 20% flows to active PoW miners (70%) and Quorum validators (30%) as transaction fee rewards.
- **Peer-to-Peer Marketplace & Bidding System:** Handles can be transferred, listed for sale, or bid on via decentralized non-custodial offers in BCT coins.

---

## 🥩 Non-Custodial Validator Staking & Yield Model (v2.4.0)

LockTrace v2.4.0 features an on-chain **Validator Staking Vault** that empowers participants to stake collateral, attest block headers, participate in the $2/3$ Quorum Finality checkpoint mechanism, and earn automated protocol rewards without trusting any third party or centralized custodian.

### 🏛️ Staking Vault Specifications
* **Vault Address:** `BCT_STAKE_VAULT_00000000000000000000000000000000`
* **Collateral Threshold:** Exactly **$1{,}000.00\text{ BCT}$** locked per validator address.
* **Non-Custodial Cryptographic Security:** Staking operations are executed entirely client-side using deterministic SECP256k1 ECDSA signatures (`VALIDATOR_STAKE:<sender>:<amount>:<nonce>`).
* **Consensus Split:** Every 20-second block rewards are divided into **70% to winning PoW Miner / Block Proposer** and **30% pro-rata to Active Staked Quorum Validators**.

### 📈 Emission Math & APR Economic Projections
1. **Cadence:** Block interval $T = 20.0\text{s} \implies 4{,}320\text{ blocks/day} \implies 1{,}576{,}800\text{ blocks/year}$.
2. **Subsidy per Block:** Fixed treasury subsidy of $0.05\text{ BCT}$ per block $\times 30\% = \mathbf{0.015\text{ BCT / block}}$ for validators.
3. **Daily Validator Pool:** $4{,}320 \times 0.015\text{ BCT} = \mathbf{64.80\text{ BCT / day}}$ ($+ 30\%$ of all network transaction fees).
4. **Yearly Validator Pool:** $1{,}576{,}800 \times 0.015\text{ BCT} = \mathbf{23{,}652.00\text{ BCT / year}}$ ($+ 30\%$ of all network transaction fees).
5. **Yield Schedule Table:**

| Active Quorum Validators | Total Staked Collateral | Daily Reward / Validator | Yearly Reward / Validator | Estimated APR |
|:---|:---|:---|:---|:---|
| **1 Validator (Genesis Boot)** | $1{,}000\text{ BCT}$ | $64.80\text{ BCT}$ | $23{,}652.00\text{ BCT}$ | **$\sim 2{,}365.2\%$** |
| **3 Validators** | $3{,}000\text{ BCT}$ | $21.60\text{ BCT}$ | $7{,}884.00\text{ BCT}$ | **$\sim 788.4\%$** |
| **5 Validators** | $5{,}000\text{ BCT}$ | $12.96\text{ BCT}$ | $4{,}730.40\text{ BCT}$ | **$\sim 473.0\%$** |
| **10 Validators (Max Soft Quorum)** | $10{,}000\text{ BCT}$ | $6.48\text{ BCT}$ | $2{,}365.20\text{ BCT}$ | **$\sim 236.5\%$** |
| **25 Validators** | $25{,}000\text{ BCT}$ | $2.59\text{ BCT}$ | $946.08\text{ BCT}$ | **$\sim 94.6\%$** |
| **50 Validators** | $50{,}000\text{ BCT}$ | $1.30\text{ BCT}$ | $473.04\text{ BCT}$ | **$\sim 47.3\%$** |
| **100 Validators** | $100{,}000\text{ BCT}$ | $0.65\text{ BCT}$ | $236.52\text{ BCT}$ | **$\sim 23.7\%$** |

---

## 📊 Financial Analytics Dashboard & Sovereign Portfolio Management (v2.4.0)

Built directly into the **My Wallet** interface, the v2.4.0 **Financial Analytics View** provides non-custodial asset auditing and real-time ledger intelligence:
* **Interactive Donut Breakdown:** Visualizes liquid balance vs. active locked collateral (PoS Staking Vault).
* **Live Area Sparkline:** Tracks dynamic balance trajectories derived directly from cryptographic transaction graph history.
* **Cashflow Inflow vs. Outflow:** Categorizes mining payouts, validator quorum distributions, creator royalties, BNS investments, and peer transfers.
* **One-Click Gateway:** Seamless transition to the Validator Hub with telemetry tracking for remote cloud nodes and local miners.

---

---

## 🌉 Cross-Chain Bridge Architecture (wBCT on Base)

LockTrace features a native, non-custodial cross-chain bridge architecture linking the native Layer-1 network with Ethereum Layer-2 (Base Mainnet):

- **Wrapped BCT Contract (Base):** [`0xA3C743113a41cFd0146917065d4578337Bb77254`](https://basescan.org/token/0xA3C743113a41cFd0146917065d4578337Bb77254)
- **Collateral Vault (L1):** `BCT_BRIDGE_VAULT_0000000000000000000000000000000`
- **Bridge-In (L1 &rarr; Base L2):** Native BCT is locked into the verifiable L1 bridge vault. The bridge relayer oracles verify finality and mint the exact 1:1 equivalent wBCT on Base.
- **Bridge-Out (Base L2 &rarr; L1):** User calls `burn()` on the wBCT ERC-20 contract. The relayer verifies the burn transaction on Base and releases the equivalent native BCT from the L1 bridge vault.
- **DEX Liquidity Pool:** Integrated with **Uniswap v4** on Base Mainnet for decentralized trading pairs (wBCT / ETH, wBCT / USDC).

---

## 🖥️ Cross-Platform Node Setup Guide

You can run an independent node on your local computer or cloud VPS to sync the entire ledger, verify blocks locally, participate in consensus, and announce your node live to the global web explorer.

### 🐧 1. Linux Setup (Ubuntu / Debian / CentOS / Arch)

```bash
# Step 1: Clone the repository
git clone https://github.com/LodosLawson/locktrace-blockchain.git
cd locktrace-blockchain

# Step 2: Install Python dependencies
sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Step 3: Run the node runner daemon
python3 node_runner.py --name "My-Linux-Node" --location "Stockholm, Sweden"
```

#### Run as a Background Systemd Service (Linux Production)
```ini
# Create /etc/systemd/system/locktrace-node.service
[Unit]
Description=LockTrace Blockchain Community Node
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/locktrace-blockchain
ExecStart=/home/ubuntu/locktrace-blockchain/venv/bin/python3 node_runner.py --name "Stockholm-Peer" --location "Stockholm, SE"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now locktrace-node.service
sudo systemctl status locktrace-node.service
```

---

### 🪟 2. Windows Setup (PowerShell / Command Prompt)

```powershell
# Step 1: Clone the repository
git clone https://github.com/LodosLawson/locktrace-blockchain.git
cd locktrace-blockchain

# Step 2: Set up virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Step 3: Launch Local Node & Web Wallet
python node_runner.py --local --open
```

---

### 🍎 3. macOS Setup (Terminal)

```bash
git clone https://github.com/LodosLawson/locktrace-blockchain.git
cd locktrace-blockchain
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 node_runner.py --name "Mac-Community-Node" --location "Oslo, Norway"
```

---

## 📡 Live Interactive REST API Reference

All endpoints return standardized JSON payloads with `success: true/false`, `data`, and unique `request_id`.

### 1. Network Health & Consensus State
```http
GET /api/v1/health
```
```bash
curl -s "https://locktrace.space/api/v1/health"
```
**Response:**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "network": "mainnet",
    "version": "2.3.0",
    "chain_valid": true,
    "consensus": "pow-v2-merkle-quorum",
    "storage_engine": "sqlite-wal",
    "non_custodial_signing": true
  }
}
```

### 2. Frontend Integrity & Release Authority Verification
```http
GET /api/v1/frontend/integrity
```
```bash
curl -s "https://locktrace.space/api/v1/frontend/integrity"
```

### 3. Network Statistics & Macro Tokenomics
```http
GET /api/v1/stats
```
```bash
curl -s "https://locktrace.space/api/v1/stats"
```

### 4. Account Profile & Portfolio Resolution
```http
GET /api/v1/profile/<address_or_bns_handle>
```
```bash
curl -s "https://locktrace.space/api/v1/profile/locktrace.bct"
```

### 5. BNS Handle Availability & Pricing
```http
GET /api/v1/bns/available/<name>
```
```bash
curl -s "https://locktrace.space/api/v1/bns/available/satoshi"
```

### 6. BNS Handle Lookup (Direct & Reverse Resolution)
```http
GET /api/v1/bns/lookup/<query>
```
```bash
curl -s "https://locktrace.space/api/v1/bns/lookup/locktrace.bct"
```

### 7. Validator Telemetry & Remote Node Status
```http
GET /api/v1/validator/telemetry/<address_or_bns>
```
```bash
curl -s "https://locktrace.space/api/v1/validator/telemetry/BCT3fec00e39c728050c1f1cef4cbe78fcc85881572"
```
**Response:**
```json
{
  "success": true,
  "data": {
    "wallet_address": "BCT3fec00e39c728050c1f1cef4cbe78fcc85881572",
    "staked_amount": 1000.0,
    "min_required_stake": 1000.0,
    "is_eligible_validator": true,
    "node_connected": true,
    "node_telemetry": {
      "name": "Community Validator",
      "masked_endpoint": "P2P Node (192.***.***.105:5050)",
      "block_height": 550,
      "last_seen_seconds_ago": 0,
      "is_online": true,
      "hashrate_hs": 59369.73,
      "version": "2.3.0"
    },
    "blocks_produced": 139,
    "rewards_earned": 157.6394503
  }
}
```

### 8. Space Social & Royalty Feed
```http
GET /api/v1/space/feed?limit=50&page=1
```
```bash
curl -s "https://locktrace.space/api/v1/space/feed?limit=10"
```

### 9. Submit Cryptographically Signed Transaction
```http
POST /api/v1/transaction
Content-Type: application/json
```
```json
{
  "sender": "BCT3fec00e39c728050c1f1cef4cbe78fcc85881572",
  "receiver": "BCT885bc383a03ebed0aa11cedfbfac0d52be3d4080",
  "amount": 10.0,
  "fee": 0.1,
  "signature": "<SECP256k1_ECDSA_HEX>",
  "public_key": "<64_BYTE_PUBKEY_HEX>",
  "nonce": 4
}
```

### 10. Active Peer Nodes Directory
```http
GET /api/v1/nodes
```
```bash
curl -s "https://locktrace.space/api/v1/nodes"
```

---

## 🔒 Security Architecture & Cryptographic Verification

1. **Sovereign Client-Side Custody:** Private keys are generated and held strictly in client devices using pure WebCrypto BIP-39 / SECP256k1 algorithms. No user keys or credentials are ever sent to, processed by, or stored on remote nodes.
2. **Deterministic State Resolution:** Account balances and BNS ownerships are dynamically derived through verified transaction graph evaluation across immutable blocks, eliminating mutable state tampering.
3. **Replay & Double-Spend Protection:** Every transaction enforces sequential integer `nonce` validation and cryptographic SECP256k1 signature verification.
4. **Comprehensive Security & Audit Hardening Suite (v2.4.0):**
   - **[LT-01] Quorum Proof-of-Attestation & Anti-Fake-Uptime:** Strictly enforces active cryptographic attestation within the last 3 blocks + 1,000 BCT stake in vault for 30% consensus reward participation.
   - **[LT-02] Cross-Chain Bridge Reorg & Double-Spend Defense:** 8-10 L1 confirmation depth, fail-closed 12-block Base EVM confirmation depth verification, SQLite unique index, and atomic in-flight mutex locks.
   - **[LT-03] Local Node Daemon Host & Origin CSRF Isolation:** Rigorous Host header and Origin/Sec-Fetch-Site checking on `node_runner.py` rejecting unauthorized third-party cross-origin RPC executions.
   - **[LT-04] SECP256k1 Low-S Signature Malleability Immunity:** Full compliance with BIP-62 / BIP-146 / EIP-2 rejecting $s > \lfloor N/2 \rfloor$, coupled with deterministic canonical signatures.
   - **[LT-05] DOM Injection Neutralization & Attribute XSS Guard:** Complete linkify URL attribute escaping and strict Content-Security-Policy (CSP) headers protecting BIP-39 recovery phrases.
   - **[LT-06] P2P Header-First Pre-PoW, Median-Time-Past (MTP) & Drift Defense:** Immediate PoW difficulty validation before JSON parsing, +120s max future drift cap, and 11-block Median-Time-Past (MTP).
   - **[LT-07] Zero-Disk TOCTOU-Free Atomic In-Memory Serving:** Direct serving of web assets from verified in-memory byte buffers eliminating Time-of-Check to Time-of-Use tampering risks.
5. **ACID Storage with O(1) Delta SQLite WAL & 3-Phase CAS Engine (v2.4.0):** Ledger records are committed incrementally using SQLite Write-Ahead Logging (WAL), non-blocking 3-phase Compare-And-Swap (CAS) PoW block sealing, per-wallet Anti-DDoS mempool quotas, and IPv4 `/24` Sybil subnet deduplication.
6. **Cryptographic Frontend Integrity Seal (v2.4.0):**
   - Canonical SHA-256 Checksums and ECDSA SECP256k1 release signatures (`frontend/integrity.json`).
   - Every node independently validates `index.html` and `sw.js` against the on-chain release block before serving. Any unauthorized file tampering triggers an immediate `HTTP 403` lockout.
7. **Anti-Stall Consensus & High-Throughput Resilience Engine (v2.5.0):**
   - **Emergency LWMA Stall Failsafe:** Automatic difficulty relaxation when block intervals exceed 120 seconds, preventing network freezes during severe miner drop-offs.
   - **Priority Replace-By-Fee (RBF) & Mempool Eviction:** Dynamic mempool admission that evicts the lowest-fee transaction in saturated mempools (5,000 txs) for higher-fee priority inclusion.
   - **Constant-Time SECP256k1 Cryptography:** Full migration to OpenSSL C-backed constant-time cryptography eliminating Minerva side-channel timing attacks (CVE-2024-23342).
   - **O(1) Reverse-Cursor Transaction Indexing:** High-speed paginated queries and indexed SQLite lookups eliminating linear memory/CPU degradation.
8. **P2P Compact Block Relay, State Snapshot Fast Sync & GPU Mining Acceleration (v2.7.0):**
   - **P2P Compact Block Relay (v2.6.0):** Transmits block headers, prefilled coinbase transactions, and 16-hex short transaction IDs, cutting block propagation bandwidth by ~90-95% while strictly enforcing cryptographic Merkle root and PoW verification.
   - **Decentralized State Snapshot Sync (v2.7.0):** Enables warp sync for newly joining nodes by providing deterministically hashed state roots over sorted account balances and BNS registries, requiring nodes to fully replay only the rolling window of recent 1,000 blocks to tip without compromising decentralization.
   - **Hybrid OpenCL GPU & Multi-Worker CPU Miner:** Integrated OpenCL C kernel acceleration for NVIDIA, AMD, and Intel GPUs alongside multi-worker CPU fallback in `node_runner.py` with zero required external pip packages.
9. **Native Rust Acceleration Core, Multi-Layer Bridge Hardening & Security Audit Fixes (v2.8.0):**
   - **Native Rust Acceleration Core (`crates/locktrace_core`):** High-speed cryptographic validation, lazy parallel Rayon PoW mining with accurate atomic hashrate telemetry, zero heap allocation chunking, and deterministic serialization.
   - **Multi-Layer Cross-Chain Bridge Hardening (LT-SOL-01):** Hex-character enforcement (`[0-9a-fA-F]`) on 43-character BCT addresses and zero burn address rejection across Solidity smart contract (`WrappedBCT.sol`), frontend Web3 client, and backend bridge relayer daemon.
   - **ECDSA Space Cast Authentication (LT-WEB-01):** Enforces cryptographic secp256k1 canonical signature verification on quick compose casts, eliminating unauthorized impersonation.
   - **DOM XSS Sanitization (LT-WEB-02):** Strict regex attribute sanitation and entity escaping on mentions, hashtags, and cashtags in rich social threads.
   - **Nginx HTTPS Enforcement & Tight CSP (LT-NGX-01):** Unconditional port 80 HTTP-to-HTTPS 301 redirection and tightened Content-Security-Policy removing `unsafe-eval` and whitelisting trusted RPC origins.
   - **Thirdweb Engine EVM Address & BigInt Validation (LT-TWB-01):** Defensive validation against negative numbers, non-integers, and invalid EVM address formats.
10. **Comprehensive Security Audit Hardening & Testnet Resilience (v2.8.1):**
   - **Cryptographic Sentinel Nonce Serialization (LT-POW-01):** Replaced static split tokens with 128-bit random runtime sentinels (`secrets.token_hex(16)`) and exact byte-offset splicing across `core/gpu_miner.py` and `core/native_bridge.py`, immunizing the PoW engine against transaction-content mining split DoS attacks.
   - **Strict SPV Merkle Proof Validation (LT-MRK-01):** Enforced 64-character lowercase hex format validation on target hashes and Merkle roots, prohibited empty proof arrays, and strictly checked directional proof paths (`"left"` vs `"right"`) in both Python and Rust (`crates/locktrace_core/src/merkle.rs`).
   - **SECP256k1 Curve Point Validation & 33-Byte Compressed Parity (LT-CRY-01):** Added strict SEC1 curve verification in Rust (`k256::AffinePoint::from_encoded_point`) and Python fallback, rejecting off-curve public keys ($y^2 \ne x^3 + 7$) and providing full address parity for 33-byte compressed public keys.
   - **Merkle Duplicate Leaf Collision Defense (LT-MRK-02 / CVE-2012-2459):** Implemented strict duplicate leaf transaction detection returning a poisoned zero-hash root (`"0"*64`) and block invalidation on mutated transaction duplicates.
   - **Cross-Chain Canonical Address Ingress Normalization (LT-SOL-02):** Enforced case-insensitive canonical address mapping (`BCT` + lowercase hex) across `core/bridge.py`, `server.py`, and `core/bridge_relayer.py`, preventing stuck or unclaimable bridged assets.
   - **Multi-Core Parallel Thread Mining & Honest Telemetry (LT-GPU-01):** Integrated `ThreadPoolExecutor` parallel worker pool and first-priority delegation to Rust Rayon in `core/gpu_miner.py` with accurate engine telemetry.
   - **100k Bot Army & Sybil Testnet Benchmark:** 100% test passage across Sybil faucet exhaustion, zero-stake validator quorums, mempool flood limits, concurrent race condition double-spends, and validator equivocation slashing.
11. **Critical Cryptographic & SPV Logic Hardening (v2.8.2):**
   - **Zero-Bypass Public Key Address Derivation:** Fixed fallback bypass in `fast_public_key_to_address` (`core/native_bridge.py`); invalid or off-curve public keys return `None` immediately, eliminating fake address generation via unauthenticated double-SHA256 fallback.
   - **Strict Exception-Based Merkle Duplicate Rejection (CVE-2012-2459):** Replaced poisoned `"0"*64` return with explicit `ValueError("CVE-2012-2459: Duplicate transaction hashes in block")` across `core/blockchain.py`, `core/native_bridge.py`, `crates/locktrace_core/src/merkle.rs`, and `node_runner.py`, preventing attackers from creating valid blocks with `"0"*64` Merkle roots.
   - **Single-Transaction Block SPV Proof Parity:** Fixed `fast_verify_spv_proof` to correctly verify single-transaction blocks (`proof_steps = []`) where the transaction hash equals the block Merkle root, establishing 100% interoperability with lightweight SPV clients.
12. **Creator Follow Royalty History, WrappedBCT Double-Mint Immunity & Mining Pipeline Hardening (v2.8.3):**
   - **Creator Follow Royalty History Indexing:** Fixed transaction history lookup (`extra_json LIKE '%"target": "..."%'`) and UI classification in `core/storage.py`, `core/blockchain.py`, and `frontend/index.html`, ensuring 0.50 BCT follow rewards appear seamlessly in creator transaction history and analytics.
   - **WrappedBCT Canonical Double-Mint Immunity (BUG-02):** Hardened `contracts/WrappedBCT.sol` with `mapping(bytes32 => bool) public processedL1TxHashes` and `_canonicalizeTxHash`, immunizing the bridge against casing and `0x` prefix duplicate minting.
   - **PoW Multi-Pass & Worker Thread Loop Elimination (BUG-01 & BUG-05):** Eliminated redundant 3-pass nonce recalculations when `ok == False` in `core/native_bridge.py` and `core/gpu_miner.py`, replaced blocking sequential `f.result()` with atomic event synchronization, and clamped non-positive target difficulty.
   - **Explorer Search DoS & Quick Compose Fee Parity (BUG-03 & BUG-04):** Enforced 50-item search history pagination to prevent server/browser freezes on treasury/miner addresses, fixed `JSON.stringify` quote breaking in transaction modals, and synchronized Space post fee validation at 0.10 BCT.
13. **Systemd Security Hardening, Multi-Thread Race Elimination & EVM Event Parity (v2.8.4):**
   - **Systemd Secret Key Hardening (LT-SRV-01):** Replaced hardcoded default secrets with `EnvironmentFile=-/opt/blockchaint/.env`, implemented automated 256-bit secret provisioning in `setup.sh` (`chmod 600`), and added defense-in-depth in `config.py` automatically invalidating insecure defaults.
   - **DOM Integrity & Safe URL Regex Isolation (NEW-01):** Introduced private Unicode sentinel placeholders isolating URLs during mention/hashtag/cashtag regex parsing, eliminating HTML tag attribute corruption and XSS risks.
   - **Coinbase Spot Price Feed CSP & Nginx Security Header Inheritance (NEW-02 & NEW-03):** Whitelisted `https://api.coinbase.com` in `connect-src` and preserved HSTS/X-Frame-Options/nosniff headers across `/sw.js`, `.json`, and image location blocks.
   - **Anti-Spoofing Plaintext Quote Guard (NEW-04):** Eliminated unverified 'verified' checkmarks from arbitrary text quotes, ensuring verified badges reflect only cryptographic on-chain consensus.
   - **WrappedBCT Un-Indexed Event Log Parity (NEW-05):** Converted `locktraceTxHash` to un-indexed string in `MintedFromBridge`, preserving plaintext L1 hash strings in EVM transaction logs for indexers and BaseScan.
   - **Atomic State Index Pointer Swaps (NEW-06):** Replaced in-place dictionary wipes with atomic reference swaps in `_load_in_memory_bns_index` and `_load_in_memory_space_index`, eliminating race conditions across Gunicorn's 8 worker threads.
   - **Comment Reply Hyphen Support & .env Inline Comment Parsing (NEW-07):** Added hyphen support in handle removal regex and stripped inline comments in `.env` parsing across Python and Node.js.
14. **Deep Security Audit Hardening & Zero-Defect Parity (v2.8.5):**
   - **Nginx /health Proxy Hardening (REV11-01):** Applied `limit_req zone=api burst=20 nodelay;` and forwarded `X-Real-IP`, `X-Forwarded-For`, and `X-Forwarded-Proto` headers to prevent IP masking and rate-limit bypass on the `/health` endpoint.
   - **WrappedBCT Processed Transaction Mapping Parity (REV11-02):** Synchronized `processedL1Transactions` alongside `processedL1TxHashes` during `mintFromBridge`, ensuring public getter lookups accurately reflect processed L1 transaction states.
   - **Thirdweb Service Log Masking & Input Hardening (REV11-03):** Implemented pre-log sensitive credential masking (`_mask_text`) for stdout/stderr/exceptions and enforced strict regex and boundary validation for addresses, token IDs, quantities, and chains in `claim_erc1155`.
   - **SPV Proof Depth Bounds & Solitary Leaf Direction Enforcement (REV11-04):** Bounded SPV Merkle verification to `MAX_SPV_DEPTH = 32` in Rust and Python to eliminate CPU exhaustion DoS, and enforced canonical `"right"` direction validation for duplicated solitary leaves (`sib == current`).
   - **WrappedBCT Two-Step Governance Ownership (REV11-05):** Upgraded `WrappedBCT.sol` ownership architecture to `Ownable2Step` (`pendingOwner()`, `transferOwnership`, `acceptOwnership()`), eliminating irreversible ownership loss from accidental zero/mistyped address transfers.
   - **OpenCL Hardware Bounds & URL Request Timeout Guards (REV11-06):** Replaced fixed OpenCL device querying with dynamic device count allocation and clamped indices to eliminate `IndexError`, and added explicit network timeouts across all `urllib.request.urlopen` calls in utility scripts.
15. **Consensus Optimization, Cryptographic Normalization & Resource Hardening (v2.8.6):**
   - **PoW Zero-Allocation Inner Loop & Cancellation Signal (AUD12-01):** Replaced per-nonce `hex::encode` with zero-allocation raw `[u8; 32]` leading byte checks, implemented prefix SHA-256 mid-state cloning, and added bounded batch iteration honoring `stop_event` cancellation signals.
   - **Thirdweb Private Key Secret Redaction (AUD12-02):** Added `THIRDWEB_SERVER_PRIVATE_KEY` and raw 64-hex private key patterns to sanitization masking, and removed public `client_id` from secret masking.
   - **WrappedBCT SSTORE Gas Optimization & Canonical Getter (AUD12-03):** Converted `processedL1Transactions` to an external view function querying `processedL1TxHashes`, eliminating duplicate string SSTORE writes (~22,100 gas saved per mint) and immunizing lookups against casing/prefix variances.
   - **Web Push DoS Length Bounds & Thread Pool Bounding (AUD12-04):** Bounded `endpoint` (512 chars), `p256dh` (128 chars), and `auth` (64 chars) to prevent database bloat, and replaced unbounded `threading.Thread` spawning with a bounded `ThreadPoolExecutor(max_workers=4)`.
   - **Mnemonic Validation & BIP-39 NFKD Normalization (AUD12-05):** Strictly rejected empty and corrupt mnemonic phrases with `ValueError` (preventing deterministic empty-key sweep exploits) and applied BIP-39 standard Unicode NFKD normalization.
   - **Compact Block Invariant & Difficulty Validation (AUD12-06):** Enforced `difficulty` (1..64) range, verified `prefilled.len() + short_ids.len() == total_transactions`, and enforced out-of-bounds and duplicate index rejection on prefilled transactions.
   - **Shared GPU/CPU Miner Engine Singleton (AUD12-07):** Replaced per-call `LockTraceMinerEngine` instantiation with a thread-safe singleton, eliminating repeated OpenCL Ctypes driver initialization overhead.
   - **Nginx HTTP Fallback CSP & Certbot Hardening (AUD12-08):** Configured full modern Web3 CSP headers, rate-limited API proxies, and removed obsolete `X-XSS-Protection` across port 80 HTTP configurations.
16. **Production Engine, Runtime Decompression & Web3 Client Hardening (v2.8.7):**
   - **Thirdweb CLI Clean Process Termination (AUD14-01):** Enforced explicit `process.exit(0)` across all CLI execution branches to immediately release active RPC/WebSocket listeners and prevent 45-second subprocess hangs.
   - **SECP256k1 Curve Point Single-Pass Decompression (AUD14-02):** Refactored `crates/locktrace_core/src/crypto.rs` to parse `VerifyingKey` once per signature verification, halving cryptographic curve decompression overhead.
   - **PoW Nonce Offset & SHA-256 Midstate Stream Cloning (AUD14-03):** Introduced `start_nonce` support across mining engines to prevent redundant 0..2M nonce scans, and implemented Python-side `hashlib.sha256.copy()` prefix mid-state reuse.
   - **Frontend DOM XSS Prevention & Escaped Market Feeds (AUD14-04):** Replaced unescaped attribute interpolation with `sanitizeJsAttr` for post identifiers (`pid`) and strictly sanitized market price change badges (`m.change`) via `escapeHtml`.
   - **Production Rust Compilation & Systemd Resource Limits (AUD14-05):** Automated Rust native acceleration building via `maturin` in `setup.sh` and configured `LimitNOFILE=65535` / `LimitNPROC=65535` in `blockchain.service`.
   - **Nginx Wallet Endpoint Request Body & Timeout Bounds (AUD14-06):** Enforced `client_max_body_size 1m;` alongside strict connect/read/send proxy timeouts on `/api/v1/wallet/create`.
   - **SSH Log Inspector Timeout & Secret Masking (AUD14-07):** Hardened `scripts/test_base_logs.py` with 30s timeout guards and regex-based credential masking.
   - **Mnemonic Case Normalization (AUD13-01):** Applied BIP-39 case-insensitive lowercasing in `mnemonic_to_private_key` prior to NFKD normalization.
17. **Integer Overflow Hardening, Nginx CSP Inheritance & Engine Option Defense (v2.8.8):**
   - **Frontend Embedding Text Slicing Bug Fix (AUD15-01):** Sliced directly from `f_idx2` preserving `window.liveMarketPrices =` in `scripts/replace_embed.py` to prevent frontend JS execution breaks.
   - **Secret Masking Regex Callable & Dual DB Fallback (AUD15-02):** Fixed `scripts/test_base_logs.py` backreference leak using group match callables and multi-path sqlite database discovery.
   - **Checked Arithmetic Integer Overflow Immunization (AUD15-03):** Immunized `crates/locktrace_core/src/pow.rs` against `u64` arithmetic overflows via `checked_mul`, `checked_add`, and `saturating_add`.
   - **Nginx Child Location CSP Inheritance & /integrity.json Parity (AUD15-04):** Re-declared Content-Security-Policy across all sub-locations with custom `add_header` and added explicit `/integrity.json` caching guards in `nginx.conf`.
   - **Full BIP-39 NFKD Normalization Prior to Validation (AUD15-05):** Enforced Unicode NFKD normalization in both `validate_mnemonic` and `mnemonic_to_private_key` before wordlist verification.
   - **P2P Compact Block Version, Raw JSON & Short ID Verification (AUD15-06):** Enforced `compact_version == 1`, 64KB raw JSON bounds, and 16-hex character formatting in `crates/locktrace_core/src/compact.rs`.
   - **Thirdweb 0x Key Normalization & CLI Flag Injection Defense (AUD15-07):** Normalized raw 64-hex server private keys with `0x` prefix and prohibited leading hyphens in transaction ID and chain name regexes.
   - **Audit Bundle Privacy Filters & Dynamic Protocol SSOT (AUD15-08):** Configured strict exclusions for `.env`, keys, certificates, and bound protocol version dynamically to `Config.PROTOCOL_VERSION`.
18. **Rayon Clamping, DOM Sanitization & Protocol SSOT Alignment (v2.8.9):**
   - **High Start-Nonce Rayon Clamping (AUD16-01):** Clamped `max_nonces` in `crates/locktrace_core/src/pow.rs` and bounded 64-bit integer ranges to eliminate empty chunk Rayon iterations and 100% CPU thread exhaustion.
   - **Prioritized Non-Empty Database Discovery (AUD16-02):** Reordered candidate database paths in `scripts/test_base_logs.py` to prioritize active `/opt/blockchaint/data/blockchain.db` over stale 0-byte databases.
   - **DOM XSS Attribute Sanitization (AUD16-03):** Replaced `escapeHtml` with `sanitizeJsAttr` across all inline `onclick` event attributes in `scripts/replace_embed.py`, `frontend/index.html`, and `templates/index.html`.
   - **P2P Compact Block Header & Duplicate ID Defense (AUD16-04):** Enforced non-empty string validation on `CompactHeader` fields (`hash`, `previous_hash`, `merkle_root`, `miner`) and eliminated duplicate transaction IDs via `HashSet` in `crates/locktrace_core/src/compact.rs`.
   - **Thirdweb 64-Hex Validation & Dual-Prefix Key Redaction (AUD16-05):** Strictly validated 64-hex private keys, ensured lowercase `0x` formatting in `thirdweb_engine.mjs`, and masked both raw 64-hex and `0x`/`0X` prefixed keys in Python log redaction.
   - **BIP-39 Pre-Split NFKD Unicode Normalization (AUD16-06):** Applied NFKD normalization directly to raw mnemonic strings in `core/mnemonic.py` prior to whitespace splitting, fully conforming to BIP-39 specification.
   - **Audit Bundle Privacy Filters & Output XML Parity (AUD16-07):** Filtered `"wallet"` and `".bak"` artifacts from security packages and ensured dynamic `repomix-output_16.xml` bundling.
   - **Universal Protocol SSOT Version Synchronization (AUD16-08):** Harmonized all deployment scripts, launchers, whitepapers, and core packages to v2.8.9.
19. **Responsible Disclosure Policy:** Security vulnerabilities should be responsibly disclosed directly to [`locktracetoken+space@gmail.com`](mailto:locktracetoken+space@gmail.com) or through [GitHub Security Advisories](https://github.com/LodosLawson/locktrace-blockchain/security).

---

## 📄 License
MIT License. Built for decentralization, transparency, and sovereign peer-to-peer finance.
