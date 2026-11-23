#!/usr/bin/env python3
"""
LockTrace Full Version & Live Mainnet Backup Generator
Creates a full local archive (Git Repo Bundle + Source Zip + Live Mainnet SQLite Snapshots)
with SHA-256 integrity verification.
"""

import os
import sys
import zipfile
import subprocess
import hashlib
from datetime import datetime

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE)

try:
    from config import Config
    VERSION = f"v{getattr(Config, 'PROTOCOL_VERSION', '2.12.3')}"
except Exception:
    VERSION = "v2.12.3"

STAMP = datetime.now().strftime("%Y-%m-%d_%H%M%S")
BACKUP_ROOT = os.path.join(os.path.dirname(WORKSPACE), "BlockChainT_Backups", f"{VERSION}_{STAMP}")

VPS_HOST = os.environ.get("LOCKTRACE_SSH_HOST", "ubuntu@129.151.205.219")
VPS_KEY = os.environ.get("LOCKTRACE_SSH_KEY", os.path.join(WORKSPACE, ".keys", "vps.key"))


def get_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main():
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    print(f"[*] Target backup directory: {BACKUP_ROOT}")

    git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=WORKSPACE, text=True).strip()
    git_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=WORKSPACE, text=True).strip()

    # 1. Create Git Bundle
    bundle_name = f"locktrace_{VERSION}_repo.bundle"
    bundle_path = os.path.join(BACKUP_ROOT, bundle_name)
    print("[*] Creating Git repository bundle...")
    subprocess.run(["git", "bundle", "create", bundle_path, "--all"], cwd=WORKSPACE, check=True)

    # 2. Create full source zip snapshot
    zip_name = f"locktrace_{VERSION}_full_source.zip"
    zip_path = os.path.join(BACKUP_ROOT, zip_name)
    print("[*] Creating source code ZIP snapshot...")
    exclude_dirs = {".git", "__pycache__", "target", "node_modules", ".venv", "venv", ".idea", ".vscode"}

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(WORKSPACE):
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith(".git")]
            for f in files:
                if f.endswith(".pyc") or f == "pwa_bundle.tar.gz":
                    continue
                full_path = os.path.join(root, f)
                arcname = os.path.relpath(full_path, WORKSPACE)
                zf.write(full_path, arcname)

    # 3. Live Mainnet SQLite Hot Backup (safe SQLite .backup() over SSH + SCP)
    db_artifacts = []
    if os.path.exists(VPS_KEY):
        print("[*] Taking safe hot SQLite snapshots from live mainnet VPS...")
        remote_py = (
            "import os, sqlite3\n"
            "os.makedirs('/tmp/lt_backup', exist_ok=True)\n"
            "for src, dst in [('data/blockchain.db', '/tmp/lt_backup/mainnet_ledger.db'), ('blockchain.db', '/tmp/lt_backup/mainnet_bridge.db')]:\n"
            "  if os.path.exists(src):\n"
            "    s = sqlite3.connect(src); d = sqlite3.connect(dst); s.backup(d); d.close(); s.close(); print('OK', dst)\n"
        )
        res = subprocess.run(
            ["ssh", "-i", VPS_KEY, "-o", "StrictHostKeyChecking=accept-new", VPS_HOST, "cd /opt/blockchaint && sudo /opt/blockchaint/venv/bin/python3 -"],
            input=remote_py, capture_output=True, text=True, timeout=60
        )
        if res.returncode == 0:
            for fname in ("mainnet_ledger.db", "mainnet_bridge.db"):
                local_db = os.path.join(BACKUP_ROOT, fname)
                scp = subprocess.run(
                    ["scp", "-i", VPS_KEY, "-o", "StrictHostKeyChecking=accept-new", f"{VPS_HOST}:/tmp/lt_backup/{fname}", local_db],
                    capture_output=True, text=True, timeout=60
                )
                if scp.returncode == 0 and os.path.exists(local_db):
                    db_artifacts.append((fname, local_db))
            subprocess.run(
                ["ssh", "-i", VPS_KEY, "-o", "StrictHostKeyChecking=accept-new", VPS_HOST, "sudo rm -rf /tmp/lt_backup"],
                capture_output=True, text=True, timeout=30
            )
        else:
            print(f"[!] Mainnet DB snapshot skipped: {res.stderr.strip()}")

    bundle_size_mb = os.path.getsize(bundle_path) / (1024 * 1024)
    zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    bundle_sha = get_sha256(bundle_path)
    zip_sha = get_sha256(zip_path)

    # 4. Write Manifest
    manifest_path = os.path.join(BACKUP_ROOT, "BACKUP_MANIFEST.txt")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write("LOCKTRACE / BLOCTAG FULL BACKUP MANIFEST\n")
        f.write("============================================\n")
        f.write(f"Version        : {VERSION}\n")
        f.write(f"Created At     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Git Branch     : {git_branch}\n")
        f.write(f"Git Commit     : {git_commit}\n")
        f.write("GitHub Repo    : https://github.com/LodosLawson/locktrace-blockchain\n")
        f.write("--------------------------------------------\n")
        f.write(f"Git Bundle     : {bundle_name} ({bundle_size_mb:.2f} MB)\n")
        f.write(f"  SHA-256      : {bundle_sha}\n\n")
        f.write(f"Source Zip     : {zip_name} ({zip_size_mb:.2f} MB)\n")
        f.write(f"  SHA-256      : {zip_sha}\n\n")
        for fname, fpath in db_artifacts:
            sz = os.path.getsize(fpath) / (1024 * 1024)
            f.write(f"Mainnet DB     : {fname} ({sz:.2f} MB)\n")
            f.write(f"  SHA-256      : {get_sha256(fpath)}\n\n")

    print("\n[SUCCESS] Full Backup Created Successfully!")
    print(f" Directory  : {BACKUP_ROOT}")
    print(f" Git Bundle : {bundle_name} ({bundle_size_mb:.2f} MB)")
    print(f" Source Zip : {zip_name} ({zip_size_mb:.2f} MB)")
    for fname, fpath in db_artifacts:
        print(f" Mainnet DB : {fname} ({os.path.getsize(fpath) / (1024 * 1024):.2f} MB)")
    print(f" Manifest   : {manifest_path}")


if __name__ == "__main__":
    main()
