# 🛡️ LockTrace: Decentralized Layer-1 Blockchain & Sovereign Asset Protocol

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
| **Cross-Chain Bridge Vault** | `BCT_BRIDGE_VAULT_0000000000000000000000000000000` | Holds 1:1 escrowed L1 collateral backing EVM wrapped tokens. |
| **Welcome Grant** | **1.00 BCT** automated protocol grant | Granted directly from Treasury Vault to every newly generated wallet address. |
| **Transaction Fee** | **1.0%** automated protocol fee | **50% permanently locked to Treasury** (deflationary supply reduction). Remaining 50% split **70% to Block Proposer/Miner** and **30% to Validator Quorum**. |
| **Key Derivation** | **BIP-39 Mnemonic** + ECDSA SECP256k1 | 12-word seed phrase + 256-bit private key. |
| **Consensus Engine** | **Hybrid 70% PoW + 30% BFT Quorum** | Dynamic SHA-256 target difficulty + validator multi-signature confirmation. |
| **EVM Bridge (Base L2)**| **Wrapped BCT (wBCT)** | ERC-20 token on Base Mainnet (`0xA3C743113a41cFd0146917065d4578337Bb77254`), 1:1 backed. |

---

## 🌌 LockTrace Space: Censorship-Resistant Social Economy

LockTrace Space embeds social interactions directly into the Layer-1 transaction graph. Thoughts, likes, and comments are decentralized financial interactions where creators receive direct micro-royalties without intermediaries:

- **Publish Post (`space_post`):** Cost is **0.05 BCT** to prevent spam and ensure content permanence. Content is permanently stored across blockchain blocks.
- **Like Royalty (`space_like`):** Cost is **0.003 BCT**. **+0.002 BCT is instantly paid on-chain to the post creator's wallet**, and 0.001 BCT goes to Treasury.
- **Comment Royalty (`space_comment`):** Cost is **0.02 BCT**. **+0.005 BCT is transferred directly to the original author's wallet**.
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
    "version": "2.0.0",
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

### 7. Space Social & Royalty Feed
```http
GET /api/v1/space/feed?limit=50&page=1
```
```bash
curl -s "https://locktrace.space/api/v1/space/feed?limit=10"
```

### 8. Submit Cryptographically Signed Transaction
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

### 9. Active Peer Nodes Directory
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
4. **ACID Storage with O(1) Delta SQLite WAL & 3-Phase CAS Engine (v2.0.0):** Ledger records are committed incrementally using SQLite Write-Ahead Logging (WAL), non-blocking 3-phase Compare-And-Swap (CAS) PoW block sealing, per-wallet Anti-DDoS mempool quotas, and IPv4 `/24` Sybil subnet deduplication.
5. **Cryptographic Frontend Integrity Seal (v2.0.0):**
   - Canonical SHA-256 Checksums and ECDSA SECP256k1 release signatures (`frontend/integrity.json`).
   - Every node independently validates `index.html` and `sw.js` against the on-chain release block before serving. Any unauthorized file tampering triggers an immediate `HTTP 403` lockout.
6. **Responsible Disclosure Policy:** Security vulnerabilities should be responsibly disclosed directly to [`locktracetoken+space@gmail.com`](mailto:locktracetoken+space@gmail.com) or through [GitHub Security Advisories](https://github.com/LodosLawson/locktrace-blockchain/security).

---

## 📄 License
MIT License. Built for decentralization, transparency, and sovereign peer-to-peer finance.
