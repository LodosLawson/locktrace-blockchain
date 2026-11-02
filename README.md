# 🛡️ LockTrace Blockchain & Decentralized Banking

[![Mainnet Status](https://img.shields.io/badge/Mainnet-Online%20%28Stockholm%29-10b981?style=for-the-badge&logo=oracle)](https://locktrace.space)
[![Total Supply](https://img.shields.io/badge/Total%20Supply-1%20Trillion%20BCT-2563eb?style=for-the-badge)](https://locktrace.space)
[![PWA Ready](https://img.shields.io/badge/PWA-Desktop%20%26%20Mobile-f59e0b?style=for-the-badge&logo=pwa)](https://locktrace.space)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-181717?style=for-the-badge&logo=github)](https://github.com/LodosLawson/locktrace-blockchain)

LockTrace is an enterprise-grade, high-performance decentralized blockchain ledger coupled with a premium Neobank / Obsidian Fintech UI. It features deterministic macro-monetary policy, BIP-39 mnemonic key derivation, ECDSA SECP256k1 transaction signatures, Proof-of-Work consensus, and real-time P2P node telemetry.

---

## 🏛️ Monetary Policy & Tokenomics

| Metric | Specification | Verification Rule |
| :--- | :--- | :--- |
| **Asset Symbol** | **BCT** (BlockChain Token) | Cryptographic ledger unit |
| **Total Supply** | **1,000,000,000,000.00 BCT** (1 Trillion) | Fixed in Genesis Block #0. No inflation or extra minting. |
| **Genesis Vault** | `BCT_HAZINE_0000000000000000000000000000000000000000` | Holds uncirculated tokens. |
| **Welcome Grant** | **1.00 BCT** automated welcome grant | Deposited from Treasury Vault to every new unique wallet. |
| **Transaction Fee** | **1.0%** strictly automated | 100% of fees cycle directly back into the Treasury Vault pool. |
| **Key Derivation** | **BIP-39 Mnemonic** + ECDSA SECP256k1 | 12-word secret seed phrase + 64-hex private key. |
| **Consensus Engine** | **Proof-of-Work (SHA-256)** | Target difficulty with atomic persistence. |

---

## 🖥️ Cross-Platform Node Setup Guide

You can run an independent node on your local computer or VPS to sync the entire ledger, verify blocks locally, and announce your node live to the global web explorer.

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
python3 node_runner.py --name "My-Linux-Node" --location "Istanbul, Turkey"
```

#### Optional: Run as a Background Systemd Service (Linux)
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
py node_runner.py --name "Windows-Node" --location "Berlin, Germany"
```

---

## 🌐 Live Web Explorer & PWA App

- **Official Web Domain:** [https://locktrace.space](https://locktrace.space)
- **Netlify Mirror:** [https://spectacular-brioche-aafb73.netlify.app](https://spectacular-brioche-aafb73.netlify.app)
- **Genesis Validator Node (Stockholm, SE):** `http://129.151.205.219:5000`

### Interactive Features Available in Web UI:
- **Obsidian Titanium Debit Card:** Real-time display of verified balance and truncated account number.
- **Instant Wire Transfer:** Fast transfer with automated 1% fee calculation.
- **Account Vault:** 12-word seed phrase generator and backup view, 64-hex private key reveal, and wallet switcher.
- **Personal Statement:** Chronological inbound/outbound transfer history with green `(+)` and red `(-)` badges.
- **Universal Explorer:** Real-time search across Block Numbers, Transaction Hashes, and Addresses.
- **Active Network Nodes:** Live status cards of all validator peers and community nodes.
- **Interactive REST API Docs:** Embedded test harness enabling live endpoint execution directly in browser.

---

## 🔌 REST API Specification (v1)

Base URL:
- Production: `https://locktrace.space/api/v1`
- Mirror: `https://spectacular-brioche-aafb73.netlify.app/api/v1`
- Direct Genesis Node: `http://129.151.205.219/api/v1`

---

### 1. Network Health
```http
GET /api/v1/health
```
**cURL:**
```bash
curl -X GET "https://locktrace.space/api/v1/health"
```
**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "version": "1.2.0",
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
**cURL:**
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
    "treasury_formatted": "999,999,999,984.04600000",
    "circulating_supply": 15.954,
    "circulating_formatted": "15.95400000",
    "total_blocks": 23,
    "total_wallets": 3,
    "total_transactions": 22,
    "total_fees_collected": 0.046,
    "chain_valid": true,
    "latest_block_hash": "0006e1cc6607d2a0db2983688d6ea5997d7f30034238bd98335000cf49caa14a"
  }
}
```

---

### 3. Open Account (12-Word BIP-39 Seed & 1.00 BCT Bonus)
```http
POST /api/v1/wallet/create
```
**cURL:**
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

### 4. Restore Account via 12 Words or Private Key
```http
POST /api/v1/wallet/import
Content-Type: application/json
```
**Request Body:**
```json
{
  "mnemonic": "step dignity loyal retreat field cluster talk divorce industry local urge area"
}
```
*Or with private key:*
```json
{
  "private_key": "51e8af23166d6fc06b1c9ad067276d0970f705e8f57254e09b4cc7e759e591a4"
}
```

---

### 5. Check Balance
```http
GET /api/v1/balance/{address}
```
**cURL:**
```bash
curl -X GET "https://locktrace.space/api/v1/balance/BCT2db88f4a46871844cfcde4b8ecfa02644af88836"
```
**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "address": "BCT2db88f4a46871844cfcde4b8ecfa02644af88836",
    "balance": 0.8,
    "exists": true
  }
}
```

---

### 6. Authorize Wire Transfer (1% Treasury Fee)
```http
POST /api/v1/transaction
Content-Type: application/json
```
**Request Body:**
```json
{
  "sender": "BCT2db88f4a46871844cfcde4b8ecfa02644af88836",
  "receiver": "BCT7404325cf37316e3c6396ff1eef80c4ef381c27b",
  "amount": 0.2,
  "mnemonic": "step dignity loyal retreat field cluster talk divorce industry local urge area"
}
```
**Response (201 Created):**
```json
{
  "success": true,
  "message": "Transfer confirmed! Sent: 0.198 BCT, 1% Fee (0.002 BCT) returned to treasury vault.",
  "data": {
    "tx_hash": "fbe40b7dcae0c3a1522bace1316c76bfd832f4c4b2b9a18f1baaa9c3e5004b84",
    "sender": "BCT2db88f4a46871844cfcde4b8ecfa02644af88836",
    "receiver": "BCT7404325cf37316e3c6396ff1eef80c4ef381c27b",
    "amount": 0.2,
    "fee": 0.002,
    "net_amount": 0.198
  }
}
```

---

### 7. Account Statement
```http
GET /api/v1/transactions/{address}
```
Returns personal transaction records for `{address}`.

---

### 8. List Network Peer Nodes
```http
GET /api/v1/nodes
```
**cURL:**
```bash
curl -X GET "https://locktrace.space/api/v1/nodes"
```
**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "total_nodes": 2,
    "online_nodes": 2,
    "nodes": [
      {
        "node_id": "node-stockholm-validator-01",
        "name": "LockTrace Genesis Validator #1",
        "endpoint": "http://129.151.205.219:5000",
        "location": "Stockholm, Sweden (Oracle Cloud)",
        "role": "Genesis Validator / Archival Seed",
        "status": "online",
        "block_height": 23,
        "is_genesis": true
      }
    ]
  }
}
```

---

### 9. Announce Community Node
```http
POST /api/v1/nodes/register
Content-Type: application/json
```
**Request Body:**
```json
{
  "name": "My-Community-Node",
  "location": "Berlin, Germany",
  "role": "Community Peer Node",
  "endpoint": "http://my-ip:5000"
}
```

---

## 🔒 Security & Verification Model

1. **Cryptographic Identity:** Wallets are secured with BIP-39 mnemonic seed phrases derived via PBKDF2 HMAC-SHA512. Private keys remain exclusively on the user side.
2. **Immutable On-Chain Balance Resolution:** Balances are not stored in mutable single registers; instead, every balance inquiry computes the exact sum of verified genesis, reward, and transfer transactions across the Proof-of-Work blockchain.
3. **Double-Spend Prevention:** Automatic nonces and signature verifications prevent replay and double-spending attempts.
4. **Thread-Safe Atomic Persistence:** State synchronization is protected by a process-wide `RLock` and written via atomic file swaps (`blockchain.json.tmp` -> `blockchain.json`).

---

## 📄 License
MIT License. Built for decentralization, transparency, and accessible sovereign finance.
