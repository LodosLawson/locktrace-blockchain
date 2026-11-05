# LockTrace (BCT) & Wrapped BCT (wBCT)
## Cross-Chain Liquidity & Bridge Operations Manual

> **Official Target:** Base Mainnet (Coinbase Ethereum L2 — Chain ID: 8453)  
> **Native Asset:** Blockchain Trace (BCT)  
> **EVM Token:** Wrapped Blockchain Trace (wBCT)  
> **L1 Bridge Vault:** `BCT_BRIDGE_VAULT_000000000000000000000000000000000`  
> **Ratio & Peg:** 1 BCT = 1 wBCT (100% Verifiable On-Chain Reserve)

---

## 1. Executive Summary & Architecture

LockTrace is an independent, non-custodial Layer-1 blockchain operating a hybrid consensus mechanism (70% CPU PoW Merkle + 30% Validator Quorum). Because LockTrace Layer-1 is an autonomous blockchain (similar to Bitcoin or Kaspa) with its own native cryptographic signature scheme, it connects to EVM decentralized finance (DeFi) via a **Decentralized Lock-and-Mint Cross-Chain Bridge**.

```
+------------------------------------+           +------------------------------------+
|       LockTrace Layer-1            |           |         Base Mainnet (EVM)         |
|                                    |           |                                    |
| [User Wallet]                      |           | [Uniswap v3 Pool: wBCT / USDT]     |
|      |                             |           |                 ^                  |
|      | (1) Lock BCT                |           |                 |                  |
|      v                             |           |                 |                  |
| [BCT_BRIDGE_VAULT...]              |           | [WrappedBCT ERC-20 (wBCT)]         |
|                                    |           |                 ^                  |
+-----------------+------------------+           +-----------------+------------------+
                  |                                                |
                  +-----> [Bridge Relayer / Oracle Quorum] --------+
                             (2) Verifies L1 Block Confirmation
                             (3) Executes mintFromBridge(to, amount)
```

### Key Advantages:
1. **Ultra-Low Gas Fees:** Base L2 transactions cost $< \$0.01$, ensuring maximum trading efficiency.
2. **Deep Liquidity:** Instant integration with Uniswap v3, Aerodrome, and DEX aggregators.
3. **No Dilution:** Total circulating supply across L1 and EVM never exceeds the mathematical cap. Every `wBCT` in existence represents exactly one `BCT` locked in the Layer-1 Vault.

---

## 2. Deploying `WrappedBCT.sol` on Base Mainnet

The verified smart contract is located at [`contracts/WrappedBCT.sol`](../contracts/WrappedBCT.sol).

### Deployment Methods:

#### Method A: Via Remix IDE (Browser - No CLI Needed)
1. Open [Remix Ethereum IDE](https://remix.ethereum.org/).
2. Create a new file in `contracts/` named `WrappedBCT.sol`.
3. Copy and paste the entire code from [`contracts/WrappedBCT.sol`](../contracts/WrappedBCT.sol).
4. Go to the **Solidity Compiler** tab:
   - **Compiler Version:** `0.8.20` (or `0.8.24`)
   - **Enable Optimization:** Yes (200 runs)
   - Click **Compile WrappedBCT.sol**
5. Go to the **Deploy & Run Transactions** tab:
   - **Environment:** Injected Provider - MetaMask
   - Ensure your MetaMask is connected to **Base Mainnet** (Chain ID: `8453`, RPC: `https://mainnet.base.org`).
   - In the contract dropdown, select `WrappedBCT`.
   - Enter constructor parameters:
     - `initialBridgeAuthority`: Your deployer address or the automated bridge operator address (`0x...`).
   - Click **Deploy** (Estimated Base network fee: $\approx \$0.05$).
6. Save the deployed contract address (e.g. `0x1234...abcd`).

#### Method B: Via Thirdweb CLI / Hardhat
```bash
npx thirdweb deploy -k YOUR_THIRDWEB_SECRET_KEY --network base
```

---

## 3. Creating the Liquidity Pool on Uniswap v3 (Base)

Once `WrappedBCT` is deployed, create the primary liquidity pool on Uniswap v3 to establish initial coin valuation and allow anyone worldwide to buy and sell.

### Step-by-Step Pool Creation:

1. **Open Uniswap v3 on Base:**
   - URL: [https://app.uniswap.org/#/pool?chain=base](https://app.uniswap.org/#/pool?chain=base)
   - Ensure your wallet is switched to **Base Network**.

2. **Click "New Position" / "Add Liquidity":**
   - **Token 1:** Click "Select a token" and paste your deployed `WrappedBCT` contract address (`0x...`).
   - **Token 2:** Select **USDT** (or **USDC** / **WETH**).
     - Base USDT Contract: `0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2`
     - Base USDC Contract: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`

3. **Select Fee Tier:**
   - **0.30% Fee Tier** (Recommended for mainstream pairs and standard volatility).

4. **Set Initial Price:**
   - Set the starting ratio based on target launch valuation.
   - *Example:* If establishing an initial price of **\$0.05 per BCT**:
     - 1 wBCT = `0.05 USDT`
     - Price Range: Select **Full Range** (to ensure 24/7 liquidity across any price movement).

5. **Deposit Initial Liquidity:**
   - *Example:* Deposit 10,000 wBCT + 500 USDT.
   - Click **Approve wBCT** & **Approve USDT**.
   - Click **Preview** &rarr; **Create Pool**.
   - Confirm in MetaMask.

🎉 **Your token now has a live, decentralized, market-determined price!**

---

## 4. Indexing on DexScreener & GeckoTerminal

The moment the Uniswap v3 pool is created on Base, decentralized indexers automatically discover the pair:

- **DexScreener:** `https://dexscreener.com/base/<YOUR_POOL_OR_TOKEN_ADDRESS>`
- **GeckoTerminal:** `https://www.geckoterminal.com/base/pools/<YOUR_POOL_ADDRESS>`

### Claiming & Enhancing Your DexScreener Profile:
1. Search your token on [DexScreener](https://dexscreener.com).
2. Click **"Update Token Info"**.
3. Attach:
   - Project Name: **Blockchain Trace (LockTrace)**
   - Symbol: **BCT / wBCT**
   - Website: `https://locktrace.space`
   - Whitepaper: `https://locktrace.space/docs/LockTrace_Whitepaper.pdf`
   - Space Explorer: `https://locktrace.space/#space`

---

## 5. Setting the Contract Address in Server Environment

To connect your deployed EVM contract with the LockTrace web application and bridge endpoints:

1. On your production server (`ubuntu@129.151.205.219`):
   ```bash
   sudo nano /etc/systemd/system/blockchaint.service
   ```
2. Add the environment variable:
   ```ini
   Environment="WBCT_CONTRACT_ADDRESS=0xYourDeployedContractAddressHere"
   ```
3. Reload and restart:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart blockchaint.service
   ```

The web interface will automatically display your verified contract address, link directly to your Uniswap v3 pool, and enable 1-click token addition to MetaMask.

---

## 6. Security Guarantees

| Attack Vector | Protection Mechanism |
| :--- | :--- |
| **Double Minting** | `processedL1Transactions` mapping in `WrappedBCT.sol` prevents replay attacks; each L1 tx can only be minted once. |
| **Fractional Reserve** | wBCT total supply can never exceed total BCT locked in `BCT_BRIDGE_VAULT_000000000000000000000000000000000`. |
| **Unwrap Guarantee** | Anyone can burn wBCT at any time via `burnToBridge()` to unlock native BCT on Layer-1. |
| **Slippage & MEV** | Uniswap v3 concentrated liquidity protects traders from front-running on Base L2. |

