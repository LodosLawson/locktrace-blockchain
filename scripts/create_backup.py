#!/usr/bin/env python3
"""
LockTrace Full Version Backup Generator
Creates a full local archive (Source Zip + Git Repo Bundle) with SHA-256 integrity verification.
"""

import os
import sys
import zipfile
import subprocess
import hashlib
from datetime import datetime

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_ROOT = os.path.join(os.path.dirname(WORKSPACE), "BlockChainT_Backups", "v2.12.2")

def main():
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    print(f"[*] Target backup directory: {BACKUP_ROOT}")

    # 1. Create Git Bundle
    bundle_path = os.path.join(BACKUP_ROOT, "locktrace_v2.12.2_repo.bundle")
    print(f"[*] Creating Git repository bundle...")
    subprocess.run(["git", "bundle", "create", bundle_path, "--all"], cwd=WORKSPACE, check=True)

    # 2. Create full source zip snapshot
    zip_path = os.path.join(BACKUP_ROOT, "locktrace_v2.12.2_full_source.zip")
    print(f"[*] Creating source code ZIP snapshot...")
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

    bundle_size_mb = os.path.getsize(bundle_path) / (1024 * 1024)
    zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)

    # 3. Compute SHA256 checksums
    def get_sha256(filepath):
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    bundle_sha = get_sha256(bundle_path)
    zip_sha = get_sha256(zip_path)

    # 4. Write Manifest
    manifest_path = os.path.join(BACKUP_ROOT, "BACKUP_MANIFEST.txt")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write("LOCKTRACE / BLOCTAG VERSION BACKUP MANIFEST\n")
        f.write("============================================\n")
        f.write("Version        : v2.12.2\n")
        f.write(f"Created At     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("Git Commit     : 9800ea60f7914decc3bcf4fb61bb06e3e8750815\n")
        f.write("GitHub Tag     : v2.12.2\n")
        f.write("GitHub Branch  : backup/v2.12.2\n")
        f.write("GitHub Repo    : https://github.com/LodosLawson/locktrace-blockchain\n")
        f.write("--------------------------------------------\n")
        f.write(f"Git Bundle     : locktrace_v2.12.2_repo.bundle ({bundle_size_mb:.2f} MB)\n")
        f.write(f"  SHA-256      : {bundle_sha}\n\n")
        f.write(f"Source Zip     : locktrace_v2.12.2_full_source.zip ({zip_size_mb:.2f} MB)\n")
        f.write(f"  SHA-256      : {zip_sha}\n")

    print(f"\n[SUCCESS] Local Backup Created Successfully!")
    print(f" Directory  : {BACKUP_ROOT}")
    print(f" Git Bundle : {bundle_path} ({bundle_size_mb:.2f} MB)")
    print(f" Source Zip : {zip_path} ({zip_size_mb:.2f} MB)")
    print(f" Manifest   : {manifest_path}")

if __name__ == "__main__":
    main()
