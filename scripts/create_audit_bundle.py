"""
LockTrace Security Audit Bundle Packager
========================================
Creates a comprehensive, self-contained zip archive in output/ for third-party
security researchers, bug bounty hunters, and auditors.
"""

import os
import sys
import zipfile
import shutil

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
ZIP_NAME = "locktrace_security_audit_package.zip"
ZIP_PATH = os.path.join(OUTPUT_DIR, ZIP_NAME)

AUDIT_GUIDE_CONTENT = """# 🛡️ LockTrace (BCT) — Third-Party Security Audit & Bug Testing Guide

Welcome to the **LockTrace Layer-1 Blockchain** Security Audit Package.
This bundle contains the complete source code, smart contracts, cryptographic modules,
consensus engines, and automated security test suites for third-party penetration testing
and security bug verification.

---

## 📋 System Architecture Overview

- **Protocol Version:** `v2.8.5` (Production Mainnet: https://locktrace.space)
- **Consensus Architecture:** Hybrid 70% Proof-of-Work (PoW) + 30% BFT Quorum Validator Attestation
- **Native Token:** BCT (Blockchain Trace, 1 Trillion fixed max supply, non-inflationary)
- **Database Engine:** SQLite in WAL mode (`sqlite-wal`) with O(1) reverse cursor indexing
- **Cross-Chain Bridge:** Base Mainnet wBCT ERC-20 (`0xA3C743113a41cFd0146917065d4578337Bb77254`) with Ownable2Step & canonical hash deduplication
- **Cryptographic Engine:** Constant-time SECP256k1 (BIP-62/146 Low-S canonical enforcement)
- **Rust Core:** `crates/locktrace_core` (Rayon parallel PoW, SPV Merkle inclusion proof, compact blocks)

---

## 🚀 How to Run the Automated Security Test Suites

All automated security and fuzz test suites are located in `tests/`:

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Run Comprehensive Security & Exploit Defense Suite (Replay, Race Conditions, Slashing, Fuzzing)
python tests/run_security_tests.py

# 3. Run Sybil & Faucet Exhaustion Attack Suite
python tests/run_sybil_tests.py

# 4. Run Critical Logic & State Indexing Patch Tests
python tests/test_critical_logic_patches.py

# 5. Run Vulnerability & Reentrancy Defenses Suite
python tests/test_new_vulnerabilities_patch.py

# 6. Run Rust vs Python Mathematical Parity Audit
python tests/test_rust_spec_parity.py

# 7. Run Latest Audit (REV11) Verification Suite
python tests/test_rev11_fixes.py
```

---

## 🔍 Key Security Focus Areas for Auditors

1. **Consensus & PoW Solver (`core/blockchain.py`, `core/gpu_miner.py`, `crates/locktrace_core/src/pow.rs`):**
   - Anti-stall LWMA difficulty adjustment (failsafe after 120s inactivity).
   - Random sentinel token byte-splicing protecting against mining nonce DoS.
   - Merkle root calculation hardened against CVE-2012-2459 (duplicate leaf rejection).

2. **Cross-Chain Bridge Security (`contracts/WrappedBCT.sol`, `core/bridge.py`, `core/bridge_relayer.py`):**
   - Deduplication mapping (`processedL1Transactions` & `processedL1TxHashes`) prevents double-minting.
   - Dual-step ownership governance (`Ownable2Step`) prevents accidental owner takeover.
   - Minimum 12-block confirmation depth verification on Base L2 before unlock.

3. **SPV Proof Verification (`core/native_bridge.py`, `crates/locktrace_core/src/merkle.rs`):**
   - Proof depth bounded to `MAX_SPV_DEPTH = 32`.
   - Canonical solitary leaf pairing direction check (`sib == current` requires `"right"`).

4. **Web & API Security (`server.py`, `deploy/nginx_ssl.conf`):**
   - Rate limiting zones (`limit_req zone=api` and `zone=wallet`).
   - Reverse proxy IP forwarding headers (`X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`).
   - Content Security Policy (CSP) without `unsafe-eval` and strict domain allowlisting.

---

## 📬 Responsible Disclosure & Bug Bounty

If you discover a security vulnerability or critical bug:
- **Email:** `locktracetoken+space@gmail.com`
- **GitHub Advisories:** https://github.com/LodosLawson/locktrace-blockchain/security/advisories
"""


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"[*] Packaging security audit bundle to {ZIP_PATH}...")

    # Excluded directories and file patterns
    excluded_dirs = {
        "__pycache__", ".git", "venv", "env", "node_modules", "target",
        ".netlify", "backups", "data", "output"
    }
    excluded_exts = {".pyc", ".pyo", ".pyd", ".db", ".db-wal", ".db-shm", ".key", ".pem"}

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Add audit guide
        zf.writestr("AUDIT_TEST_GUIDE.md", AUDIT_GUIDE_CONTENT)

        # 2. Add repomix-output.xml
        repomix_xml = os.path.join(ROOT_DIR, "repomix-output.xml")
        if os.path.exists(repomix_xml):
            print("[+] Adding repomix-output.xml...")
            zf.write(repomix_xml, arcname="repomix-output.xml")

        # 3. Add root files
        root_files = [
            "server.py", "node_runner.py", "wsgi.py", "config.py",
            "requirements.txt", "package.json", "README.md", "SECURITY.md",
            "AGENTS.md", "thirdweb_engine.mjs"
        ]
        for rf in root_files:
            fp = os.path.join(ROOT_DIR, rf)
            if os.path.exists(fp):
                zf.write(fp, arcname=rf)

        # 4. Add core directories
        core_dirs = ["contracts", "core", "crates", "deploy", "docs", "frontend", "templates", "scripts"]
        for cd in core_dirs:
            base_dir = os.path.join(ROOT_DIR, cd)
            if not os.path.exists(base_dir):
                continue
            for root, dirs, files in os.walk(base_dir):
                dirs[:] = [d for d in dirs if d not in excluded_dirs and not d.endswith(".egg-info")]
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in excluded_exts or f.endswith(".tar.gz") or "release_signing_key" in f:
                        continue
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, ROOT_DIR)
                    zf.write(full_path, arcname=rel_path)

        # 5. Add security test suite to tests/ directory in zip
        test_dir = os.path.join(ROOT_DIR, "scratch", "testnet_suite")
        if os.path.exists(test_dir):
            for f in os.listdir(test_dir):
                if f.endswith(".py"):
                    full_path = os.path.join(test_dir, f)
                    zf.write(full_path, arcname=f"tests/{f}")

        rev11_test = os.path.join(ROOT_DIR, "scratch", "test_rev11_fixes.py")
        if os.path.exists(rev11_test):
            zf.write(rev11_test, arcname="tests/test_rev11_fixes.py")

    zip_size_mb = os.path.getsize(ZIP_PATH) / (1024 * 1024)
    print(f"[SUCCESS] Security Audit Package generated successfully!")
    print(f"  • Path: {ZIP_PATH}")
    print(f"  • Size: {zip_size_mb:.2f} MB")


if __name__ == "__main__":
    main()
