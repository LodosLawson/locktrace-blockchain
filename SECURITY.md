# Security Policy — LockTrace Blockchain (BCT)

## Supported Versions

The following versions of LockTrace are actively supported with security patches and consensus updates:

| Version | Supported          | Status |
| ------- | ------------------ | ------ |
| 2.9.x (v2.9.8+) | :white_check_mark: | **Current Active Mainnet Release** (Wallet Balance & Mempool Dedup Hardened) |
| 2.9.0 - 2.9.7  | :white_check_mark: | Supported (Upgrade Recommended to v2.9.8) |
| 2.8.x   | :white_check_mark: | Legacy Consensus Supported |
| < 2.8.0 | :x:                | Deprecated (Upgrade Mandatory) |

## Security Architecture & Core Guarantees

1. **Zero-Custodial Security Model:**
   - Private keys and 12-word BIP-39 recovery phrases are strictly generated and stored on the user's client device.
   - Server endpoints `/api/v1/wallet/create` and `/api/v1/wallet/import` unconditionally reject private keys or recovery phrases over the network.
   - Client device storage is encrypted using per-encryption random 16-byte IVs with CSPRNG (`window.crypto.getRandomValues`) and user-configured AES-256-GCM PIN Vaults.

2. **Consensus & PoW Integrity:**
   - Proof-of-Work headers enforce strict timestamp monotonicity (`cur_ts > prev_ts`) and future drift bounds (`cur_ts <= now + 120s`).
   - Constant-time SECP256k1 signature verification with BIP-62/146 Low-S enforcement (`s <= N/2`) in Rust Native Core and OpenSSL fallback.
   - Immunity to CVE-2012-2459 duplicate transaction Merkle tree collision attacks.

3. **Cross-Chain Bridge Defense:**
   - Base L2 `WrappedBCT` ERC-20 (`0xA3C743113a41cFd0146917065d4578337Bb77254`) enforces `maxMintPerTx` (1M wBCT) and `dailyMintLimit` (5M wBCT) with timelocked governance changes.
   - Two-step ownership transfer (`Ownable2Step`) prevents accidental irreversible owner transfers.
   - Proof-of-Reserve validation requires at least 12 EVM confirmations on Base Mainnet and 4-8 block confirmation depth on Layer-1 to defend against chain reorgs.

4. **P2P Network & SSRF Defenses:**
   - P2P gossip peer endpoints are strictly validated against SSRF attacks; private, loopback, link-local, and multicast IP ranges are blocked, and HTTP 3xx redirects are rejected.

## Reporting a Vulnerability

The LockTrace team takes the security of the decentralized Layer-1 blockchain, cross-chain bridge, and non-custodial wallet infrastructure seriously.

If you believe you have discovered a vulnerability, architectural exploit, or consensus discrepancy:

1. **Do NOT open a public GitHub issue.**
2. Send an encrypted email or detailed report directly to:
   - **Primary Security Contact:** [`locktracetoken+space@gmail.com`](mailto:locktracetoken+space@gmail.com)
   - **GitHub Security Advisories:** [Submit a Private Advisory](https://github.com/LodosLawson/locktrace-blockchain/security/advisories/new)

### What to Include
* Detailed description of the vulnerability and attack vector (e.g. Consensus, Bridge, Cryptography, P2P, Web UI).
* Step-by-step reproduction instructions or test case scenario.
* Potential impact and proposed remediation, if available.

### Response Timeline
* **Initial Acknowledgement:** Within 24 hours.
* **Triage & Assessment:** Within 48 hours.
* **Remediation & Patch Deployment:** Critical vulnerabilities are hotfixed and deployed to mainnet nodes via emergency consensus updates.
