import os
import subprocess
import sys
import json

SSH_KEY = r"C:\Users\mehem\Downloads\ssh-key-2026-11-02.key"
VPS_HOST = "ubuntu@129.151.205.219"

def run_ssh(cmd):
    full_cmd = [
        "ssh", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        VPS_HOST, cmd
    ]
    print(f"[*] Running SSH command: {cmd[:120]}...")
    res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=60)
    print("STDOUT:", res.stdout)
    if res.stderr:
        print("STDERR:", res.stderr)
    return res.returncode == 0

def run_scp(local_path, remote_path):
    full_cmd = [
        "scp", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        local_path, f"{VPS_HOST}:{remote_path}"
    ]
    print(f"[*] Uploading: {local_path} -> {remote_path}")
    res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        print("SCP Error:", res.stderr)
        return False
    return True

def run_download(remote_path, local_path):
    full_cmd = [
        "scp", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        f"{VPS_HOST}:{remote_path}", local_path
    ]
    print(f"[*] Downloading: {remote_path} -> {local_path}")
    res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        print("SCP Download Error:", res.stderr)
        return False
    return True

def main():
    print("[*] Creating remote staging directories...")
    if not run_ssh("mkdir -p /tmp/pwa_deploy/core /tmp/pwa_deploy/frontend /tmp/pwa_deploy/templates /tmp/pwa_deploy/scripts /tmp/pwa_deploy/docs"):
        print("[!] Failed to create remote directories")
        sys.exit(1)

    files_to_upload = [
        ("core/blockchain.py", "/tmp/pwa_deploy/core/blockchain.py"),
        ("core/bridge.py", "/tmp/pwa_deploy/core/bridge.py"),
        ("core/bridge_relayer.py", "/tmp/pwa_deploy/core/bridge_relayer.py"),
        ("core/wallet.py", "/tmp/pwa_deploy/core/wallet.py"),
        ("core/mnemonic.py", "/tmp/pwa_deploy/core/mnemonic.py"),
        ("core/storage.py", "/tmp/pwa_deploy/core/storage.py"),
        ("core/thirdweb_service.py", "/tmp/pwa_deploy/core/thirdweb_service.py"),
        ("core/push_service.py", "/tmp/pwa_deploy/core/push_service.py"),
        ("core/__init__.py", "/tmp/pwa_deploy/core/__init__.py"),
        ("server.py", "/tmp/pwa_deploy/server.py"),
        ("node_runner.py", "/tmp/pwa_deploy/node_runner.py"),
        ("README.md", "/tmp/pwa_deploy/README.md"),
        ("frontend/index.html", "/tmp/pwa_deploy/frontend/index.html"),
        ("frontend/sw.js", "/tmp/pwa_deploy/frontend/sw.js"),
        ("templates/index.html", "/tmp/pwa_deploy/templates/index.html"),
        ("scripts/sign_frontend.py", "/tmp/pwa_deploy/scripts/sign_frontend.py"),
        ("scripts/sync_to_notion.py", "/tmp/pwa_deploy/scripts/sync_to_notion.py"),
        ("scripts/deploy_bns.py", "/tmp/pwa_deploy/scripts/deploy_bns.py"),
        ("scripts/create_notion_map.py", "/tmp/pwa_deploy/scripts/create_notion_map.py"),
        ("scripts/benchmark_simulation.py", "/tmp/pwa_deploy/scripts/benchmark_simulation.py"),
        ("docs/LOCKTRACE_NOTION_WORKSPACE.md", "/tmp/pwa_deploy/docs/LOCKTRACE_NOTION_WORKSPACE.md"),
        ("docs/LOCKTRACE_ARCHITECTURE_MAP.md", "/tmp/pwa_deploy/docs/LOCKTRACE_ARCHITECTURE_MAP.md"),
        ("package.json", "/tmp/pwa_deploy/package.json"),
    ]

    for local, remote in files_to_upload:
        if not run_scp(local, remote):
            print(f"[!] Failed to upload {local}")
            sys.exit(1)

    print("[*] Installing files, signing frontend, sealing on-chain, and restarting...")
    remote_cmds = """
set -e
sudo mkdir -p /opt/blockchaint/docs /opt/blockchaint/scripts
sudo cp -r /tmp/pwa_deploy/core/* /opt/blockchaint/core/
sudo cp /tmp/pwa_deploy/server.py /opt/blockchaint/server.py
sudo cp /tmp/pwa_deploy/node_runner.py /opt/blockchaint/node_runner.py
sudo cp /tmp/pwa_deploy/README.md /opt/blockchaint/README.md
sudo cp /tmp/pwa_deploy/frontend/index.html /opt/blockchaint/frontend/index.html
sudo cp /tmp/pwa_deploy/frontend/sw.js /opt/blockchaint/frontend/sw.js
sudo cp /tmp/pwa_deploy/templates/index.html /opt/blockchaint/templates/index.html
sudo cp /tmp/pwa_deploy/scripts/sign_frontend.py /opt/blockchaint/scripts/sign_frontend.py
sudo cp /tmp/pwa_deploy/scripts/sync_to_notion.py /opt/blockchaint/scripts/sync_to_notion.py
sudo cp /tmp/pwa_deploy/scripts/create_notion_map.py /opt/blockchaint/scripts/create_notion_map.py
sudo cp /tmp/pwa_deploy/scripts/benchmark_simulation.py /opt/blockchaint/scripts/benchmark_simulation.py
sudo cp /tmp/pwa_deploy/scripts/deploy_bns.py /opt/blockchaint/scripts/deploy_bns.py
sudo cp /tmp/pwa_deploy/docs/LOCKTRACE_NOTION_WORKSPACE.md /opt/blockchaint/docs/LOCKTRACE_NOTION_WORKSPACE.md
sudo cp /tmp/pwa_deploy/docs/LOCKTRACE_ARCHITECTURE_MAP.md /opt/blockchaint/docs/LOCKTRACE_ARCHITECTURE_MAP.md
sudo cp /tmp/pwa_deploy/package.json /opt/blockchaint/package.json

# 1. Sign Frontend with official Release Key
cd /opt/blockchaint
sudo /opt/blockchaint/venv/bin/python3 scripts/sign_frontend.py --version 1.9.8 --key-file /home/ubuntu/.locktrace/release_signing_key.json

# 2. Publish to Nginx document root
sudo mkdir -p /var/www/locktrace
sudo cp /opt/blockchaint/frontend/index.html /var/www/locktrace/index.html
sudo cp /opt/blockchaint/frontend/sw.js /var/www/locktrace/sw.js
sudo cp /opt/blockchaint/frontend/integrity.json /var/www/locktrace/integrity.json
sudo chown -R www-data:www-data /var/www/locktrace

# 3. Restart LockTrace Service (auto-seals release on-chain on startup), relayer, and reload Nginx
sudo systemctl restart blockchaint.service
sudo systemctl restart blockchaint-relayer.service
sleep 5
systemctl is-active blockchaint.service
systemctl is-active blockchaint-relayer.service
sudo systemctl reload nginx

# 4. Commit and push to GitHub repository
cd /opt/blockchaint
sudo cp /opt/blockchaint/frontend/integrity.json /opt/blockchaint/templates/integrity.json
git add core frontend templates scripts docs server.py node_runner.py README.md package.json
git commit -m "perf: add dedicated tx_lookup index table and revision-based profile cache" || true
git push origin master
"""
    if not run_ssh(remote_cmds):
        print("[!] Failed to apply remote install commands")
        sys.exit(1)

    print("\n[*] Downloading signed integrity.json back to local repository...")
    run_download("/opt/blockchaint/frontend/integrity.json", "frontend/integrity.json")
    run_download("/opt/blockchaint/frontend/integrity.json", "templates/integrity.json")

    print("\n[*] Testing live BNS, Profile, and Integrity endpoints on VPS...")
    test_cmd = """
curl -s http://127.0.0.1:5000/api/v1/health | head -n 5
echo ""
curl -s http://127.0.0.1:5000/api/v1/frontend/integrity | head -n 20
"""
    run_ssh(test_cmd)
    print("\n✅ DEPLOYMENT, SIGNING & ON-CHAIN SEALING TO ORACLE VPS COMPLETE!")

if __name__ == "__main__":
    main()

