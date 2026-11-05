# 🛡️ LockTrace: Decentralized Layer-1 Blockchain & Sovereign Asset Protocol

[![Mainnet Status](https://img.shields.io/badge/Mainnet-Online%20%28Stockholm%29-10b981?style=for-the-badge&logo=oracle)](https://locktrace.space)
[![Total Supply](https://img.shields.io/badge/Total%20Supply-1%20Trillion%20BCT-2563eb?style=for-the-badge)](https://locktrace.space)
[![Base Mainnet wBCT](https://img.shields.io/badge/Base%20L2-wBCT%20Bridge-0052ff?style=for-the-badge&logo=coinbase)](https://basescan.org/token/0xA3C743113a41cFd0146917065d4578337Bb77254)
[![PWA Ready](https://img.shields.io/badge/PWA-Desktop%20%26%20Mobile-f59e0b?style=for-the-badge&logo=pwa)](https://locktrace.space)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-181717?style=for-the-badge&logo=github)](https://github.com/LodosLawson/locktrace-blockchain)

LockTrace is an independent, high-performance Layer-1 decentralized blockchain ledger built for sovereign asset custody, instantaneous peer-to-peer settlement, and cross-chain liquidity. Engineered with deterministic macro-monetary rules, BIP-39 mnemonic key derivation, SECP256k1 ECDSA cryptography, hybrid PoW + BFT quorum consensus, and cryptographically signed on-chain frontend releases.

---

## 🏛️ Monetary Policy & Tokenomics

| Metric | Specification | Verification Rule |
| :--- | :--- | :--- |
| **Asset Symbol** | **BCT** (BlockChain Trace) | Native Layer-1 cryptographic ledger unit |
| **Total Supply** | **1,000,000,000,000.00 BCT** (1 Trillion) | Fixed in Genesis Block #0. Mathematically hard-capped; zero inflation. |
| **Genesis Vault** | `BCT_HAZINE_0000000000000000000000000000000000000000` | Holds uncirculated reserves. |
| **Cross-Chain Vault** | `BCT_BRIDGE_VAULT_0000000000000000000000000000000` | Holds 1:1 escrowed L1 collateral backing EVM tokens. |
| **Welcome Grant** | **1.00 BCT** automated protocol grant | Granted directly from Treasury Vault to every newly generated wallet. |
| **Transaction Fee** | **1.0%** automated protocol fee | **50% permanently locked to Treasury** (deflationary supply reduction). Remaining 50% split **70% to Block Proposer/Miner** and **30% to Validator Quorum**. |
| **Key Derivation** | **BIP-39 Mnemonic** + ECDSA SECP256k1 | 12-word seed phrase + 256-bit private key. |
| **Consensus Engine** | **Hybrid PoW + BFT Quorum** | Dynamic SHA-256 target difficulty (scales to 4 when $\ge 8$ miners online) + validator multi-signature confirmation. |
| **EVM Bridge (Base L2)**| **Wrapped BCT (wBCT)** | ERC-20 token on Base Mainnet (`0xA3C743113a41cFd0146917065d4578337Bb77254`), 1:1 backed. |

---

## 🌉 Cross-Chain Bridge Architecture (wBCT on Base)

LockTrace features a native, non-custodial cross-chain bridge architecture linking the native Layer-1 network with Ethereum Layer-2 (Base Mainnet):

- **Wrapped BCT Contract (Base):** [`0xA3C743113a41cFd0146917065d4578337Bb77254`](https://basescan.org/token/0xA3C743113a41cFd0146917065d4578337Bb77254)
- **Collateral Vault (L1):** `BCT_BRIDGE_VAULT_0000000000000000000000000000000`
- **Bridge-In (L1 &rarr; Base L2):** Native BCT is locked into the verifiable L1 bridge vault. The bridge relayer oracles verify finality and mint the exact 1:1 equivalent wBCT on Base.
- **Bridge-Out (Base L2 &rarr; L1):** User calls `burn()` on the wBCT ERC-20 contract. The relayer verifies the burn transaction on Base and releases the equivalent native BCT from the L1 bridge vault.
- **DEX Liquidity Pool:** Integrated with **Uniswap v4** on Base Mainnet for decentralized trading pairs (wBCT / ETH, wBCT / USDC).

---

## 🏷️ LockTrace Name Service (BNS - `.bct` Handle Protocol)

LockTrace features a native on-chain naming system that maps human-readable handles (`@handle.bct`) to 43-character hex addresses (`BCT...`). BNS handles replace complex addresses for transfers, Space social posts, comments, and rich list explorer profiles.

### 💰 Tiered Pricing & 80/20 Deflationary Tokenomics
Handle registration fees are determined by character length and enforce an automated **80/20 deflationary split**:
- **3-Letter Handles (Premium Tier):** `100.0 BCT` (e.g. `btc.bct`, `eth.bct`, `ceo.bct`)
- **4-Letter Handles (Standard Tier):** `50.0 BCT` (e.g. `alex.bct`, `moon.bct`, `lock.bct`)
- **5+ Character Handles (General Tier):** `10.0 BCT` (e.g. `satoshi.bct`, `locktrace.bct`)

**Tokenomics Breakdown:**
- **🔥 80% Permanently Burned / Treasury Locked:** 80% of paid registration BCT is permanently escrowed into the Treasury Vault, removing it from circulating supply and inducing continuous supply deflation.
- **⚡ 20% Returned to Circulating Rewards:** 20% of paid BCT flows directly to active PoW miners (70%) and BFT validator quorum nodes (30%) as transaction fee rewards.

### 🔄 Ownership Transfer & Decentralized Secondary Marketplace
- **Non-Custodial Transfers:** Handle owners can transfer `.bct` domains to any valid recipient address on-chain at any time for a 0.50 BCT network fee.
- **Secondary Marketplace:** Any owner can list their `.bct` handle for sale in BCT coins (`POST /api/v1/bns/market/list`). Community members can browse listed handles and purchase them peer-to-peer (`POST /api/v1/bns/market/buy`), with automated 1% network trade fee distribution.
- **Bi-Directional Handle Resolution:** Resolves `.bct` handle &rarr; address and address &rarr; primary `.bct` handle across Send Crypto, Space Feed, Comments, and the Rich List.

---

## 🖥️ Cross-Platform Node Setup Guide

You can run an independent node on your local computer or cloud VPS to sync the entire ledger, verify blocks locally, participate in consensus, and announce your node live to the global web explorer.

### 🐧 1. Linux Setup (Ubuntu / Debian / CentOS / Arch)

Open your terminal and run:

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
```

---

### 🍎 2. macOS Setup

```bash
# Step 1: Open Terminal and clone repository
git clone https://github.com/LodosLawson/locktrace-blockchain.git
cd locktrace-blockchain

# Step 2: Make launcher executable and run
chmod +x scripts/run_node.sh
./scripts/run_node.sh
```
Or run directly with Python:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 node_runner.py --name "MacBook-Node" --location "London, UK"
```

---

### 🪟 3. Windows Setup (PowerShell & Command Prompt)

1. Make sure **Python 3.10+** is installed from [python.org](https://www.python.org/) (ensure **"Add Python to PATH"** is checked).
2. Open **PowerShell** and run:

```powershell
# Step 1: Clone repository
git clone https://github.com/LodosLawson/locktrace-blockchain.git
cd locktrace-blockchain

# Step 2: Launch automated setup script
.\scripts\run_node.ps1
```
Or execute manual commands:
```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
py node_runner.py --name "Windows-Node" --location "Frankfurt, Germany"
```

---

## 🌐 Live Web Explorer & PWA App

- **Official Web Domain:** [https://locktrace.space](https://locktrace.space)
- **Genesis Validator Node (Stockholm, SE):** `http://129.151.205.219:5000`
- **PWA Capabilities:** Standalone mobile app installation, Android maskable icons with safe zones, iOS home screen support, offline cache resilience via Service Worker v14.

### Platform Features:
- **Sovereign Non-Custodial Wallet:** 12-word BIP-39 mnemonic seed phrase generator, secure local storage, raw private key export.
- **Instant Peer-to-Peer Transfers:** Real-time transfer settlement with deterministic 1% protocol fee calculation.
- **Decentralized Rich List & Holder Distribution:** Interactive paginated view of top addresses, balance rankings, and circulating supply percentages.
- **Universal Explorer:** Real-time block search, transaction hash inspection, mempool monitoring, and address analytics.
- **Space Social Layer:** Decentralized, censorship-resistant micro-messages recorded directly onto the immutable ledger.
- **Cross-Chain Bridge Dashboard:** Lock & Mint / Burn & Release UI for native BCT &harr; Base wBCT.
- **Interactive REST API Console:** Test endpoints directly from the browser with live responses.

---

## 🔌 REST API Specification (v1)

Base URL:
- Production: `https://locktrace.space/api/v1`
- Direct Genesis Node: `http://129.151.205.219/api/v1`

---

### 1. Network Health
```http
GET /api/v1/health
```
```bash
curl -X GET "https://locktrace.space/api/v1/health"
```
**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "version": "1.6.4",
    "network": "mainnet",
    "chain_valid": true
  }
}
```

---

### 2. Macro Network Stats & Proof-of-Reserve
```http
GET /api/v1/stats
```
```bash
curl -X GET "https://locktrace.space/api/v1/stats"
```
**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "total_supply": 1000000000000.0,
    "total_supply_formatted": "1,000,000,000,000",
    "treasury_balance": 999999999984.046,
    "circulating_supply": 15.954,
    "total_blocks": 321,
    "total_wallets": 127,
    "total_transactions": 348,
    "chain_valid": true
  }
}
```

---

### 3. Generate Non-Custodial Wallet (BIP-39 Seed + 1.00 BCT Protocol Grant)
```http
POST /api/v1/wallet/create
```
```bash
curl -X POST "https://locktrace.space/api/v1/wallet/create"
```
**Response (201 Created):**
```json
{
  "success": true,
  "message": "Wallet registered successfully! Available balance: 1.0 BCT",
  "data": {
    "address": "BCT2db88f4a46871844cfcde4b8ecfa02644af88836",
    "mnemonic": "step dignity loyal retreat field cluster talk divorce industry local urge area",
    "public_key": "78414a8e7466a70a6cd4466a05fc446395d4debcc21fc5dfa391ce0304dea33561...",
    "private_key": "51e8af23166d6fc06b1c9ad067276d0970f705e8f57254e09b4cc7e759e591a4",
    "balance": 1.0
  }
}
```

---

### 4. Import / Restore Wallet via Mnemonic or Private Key
```http
POST /api/v1/wallet/import
Content-Type: application/json
```
```json
{
  "mnemonic": "step dignity loyal retreat field cluster talk divorce industry local urge area"
}
```

---

### 5. Check Balance
```http
GET /api/v1/balance/{address}
```
```bash
curl -X GET "https://locktrace.space/api/v1/balance/BCT2db88f4a46871844cfcde4b8ecfa02644af88836"
```

---

### 6. Sign & Broadcast Peer-to-Peer Transfer
```http
POST /api/v1/transaction
Content-Type: application/json
```
```json
{
  "sender": "BCT2db88f4a46871844cfcde4b8ecfa02644af88836",
  "receiver": "BCT7404325cf37316e3c6396ff1eef80c4ef381c27b",
  "amount": 0.2,
  "mnemonic": "step dignity loyal retreat field cluster talk divorce industry local urge area"
}
```

---

### 7. Rich List & Top Holders
```http
GET /api/v1/explorer/holders?page=1&limit=25
```
```bash
curl -X GET "https://locktrace.space/api/v1/explorer/holders?page=1&limit=25"
```
**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "holders": [
      {
        "rank": 1,
        "address": "BCT_HAZINE_0000000000000000000000000000000000000000",
        "tag": "Genesis Treasury",
        "role": "treasury",
        "balance": 999999999800.0,
        "tx_count": 12,
        "percentage": 99.99999998
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 25,
      "total_holders": 127,
      "total_pages": 6
    }
  }
}
```

---

### 8. List Network Peer Nodes
```http
GET /api/v1/nodes
```
```bash
curl -X GET "https://locktrace.space/api/v1/nodes"
```

---

### 9. Announce Community Node
```http
POST /api/v1/nodes/register
Content-Type: application/json
```
```json
{
  "name": "My-Community-Node",
  "location": "Frankfurt, Germany",
  "role": "Community Peer Node",
  "endpoint": "http://my-ip:5000"
}
```

---

## 🔒 Security Architecture & Protocol Verification

1. **Sovereign Client-Side Custody:** Private keys are generated and held strictly on the client side via PBKDF2 HMAC-SHA512 seed derivation. No user keys or credentials are ever sent to, processed by, or stored on remote nodes.
2. **Deterministic Balance Resolution:** Account balances are dynamically derived through verified transaction graph evaluation across immutable blocks, eliminating mutable state tampering.
3. **Replay & Double-Spend Protection:** Every transaction enforces sequential integer `nonce` validation and cryptographic SECP256k1 signature verification.
4. **Thread-Safe Atomic Ledger Synchronization:** Memory state is protected by a process-wide `RLock` and written via atomic file swaps (`blockchain.json.tmp` -> `blockchain.json`).
5. **Cryptographic Frontend Integrity Seal (v1.6.7+):**
   - Canonical SHA-256 Checksums and ECDSA SECP256k1 release signatures (`frontend/integrity.json`).
   - `frontend/index.html` SHA-256: `4f362ac1c587befbbe7113fb7ba0982ecb30e6e4ff54c0e92304f57932b379f3`
   - IPFS CIDv1: `ipfs://bafkreicpgyvmdrmhx35344it7n52bgbozmyonzh7ktaosiye6v4tfm3z6m`
   - Release Authority Address: `BCT885bc383a03ebed0aa11cedfbfac0d52be3d4080`
   - Every node independently validates `index.html` and `sw.js` against the on-chain release block before serving. Any unauthorized file tampering triggers an immediate `HTTP 403` lockout.
6. **Responsible Disclosure Policy:** Security vulnerabilities should be responsibly disclosed directly to `security@locktrace.space` or through [GitHub Security Advisories](https://github.com/LodosLawson/locktrace-blockchain/security).

---

## 📄 License
MIT License. Built for decentralization, transparency, and sovereign peer-to-peer finance.
