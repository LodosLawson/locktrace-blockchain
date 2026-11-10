# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import tarfile

SSH_KEY = r"C:\Users\mehem\Downloads\ssh-key-2026-11-02.key"
VPS_HOST = "ubuntu@129.151.205.219"

def run_cmd(cmd_list, timeout=90):
    print(f"[*] Running: {' '.join(cmd_list[:6])}...")
    res = subprocess.run(cmd_list, capture_output=True, text=True, timeout=timeout)
    if res.stdout:
        print("STDOUT:", res.stdout.strip())
    if res.stderr:
        print("STDERR:", res.stderr.strip())
    return res.returncode == 0

def main():
    tar_path = "pwa_bundle.tar.gz"
    print("[*] Creating compressed tarball...")
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add("frontend/index.html", arcname="frontend/index.html")
        tar.add("frontend/sw.js", arcname="frontend/sw.js")
        tar.add("templates/index.html", arcname="templates/index.html")
        tar.add("templates/sw.js", arcname="templates/sw.js")
        tar.add("core", arcname="core")
        tar.add("docs", arcname="docs")
        tar.add("server.py", arcname="server.py")
        tar.add("node_runner.py", arcname="node_runner.py")
        tar.add("README.md", arcname="README.md")
        tar.add("config.py", arcname="config.py")
        tar.add("scripts/sign_frontend.py", arcname="scripts/sign_frontend.py")

    print("[*] Uploading bundle in single SCP stream...")
    scp_cmd = [
        "scp", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        tar_path, f"{VPS_HOST}:/tmp/pwa_bundle.tar.gz"
    ]
    if not run_cmd(scp_cmd, timeout=60):
        print("[!] SCP bundle failed")
        sys.exit(1)

    print("[*] Installing, signing frontend, sealing on-chain, and restarting services...")
    remote_script = """
set -e
tar -xzf /tmp/pwa_bundle.tar.gz -C /tmp/
sudo cp -r /tmp/core/* /opt/blockchaint/core/
sudo mkdir -p /opt/blockchaint/docs /var/www/locktrace/docs /opt/blockchaint/frontend/docs
sudo cp -r /tmp/docs/* /opt/blockchaint/docs/
sudo cp -r /tmp/docs/* /var/www/locktrace/docs/
sudo cp -r /tmp/docs/* /opt/blockchaint/frontend/docs/
sudo cp /tmp/docs/LockTrace_Whitepaper.pdf /opt/blockchaint/LockTrace_Whitepaper.pdf || true
sudo cp /tmp/docs/LockTrace_Whitepaper.pdf /var/www/locktrace/LockTrace_Whitepaper.pdf || true
sudo cp /tmp/docs/LockTrace_Whitepaper.pdf /opt/blockchaint/frontend/LockTrace_Whitepaper.pdf || true
sudo cp /tmp/server.py /opt/blockchaint/server.py
sudo cp /tmp/node_runner.py /opt/blockchaint/node_runner.py
sudo cp /tmp/README.md /opt/blockchaint/README.md
sudo cp /tmp/config.py /opt/blockchaint/config.py
sudo cp /tmp/frontend/index.html /opt/blockchaint/frontend/index.html
sudo cp /tmp/frontend/sw.js /opt/blockchaint/frontend/sw.js
sudo cp /tmp/templates/index.html /opt/blockchaint/templates/index.html
sudo cp /tmp/templates/sw.js /opt/blockchaint/templates/sw.js
sudo cp /tmp/scripts/sign_frontend.py /opt/blockchaint/scripts/sign_frontend.py

# 1. Sign Frontend with official Release Key
cd /opt/blockchaint
sudo /opt/blockchaint/venv/bin/python3 scripts/sign_frontend.py --version 2.3.0 --key-file /home/ubuntu/.locktrace/release_signing_key.json

# 2. Publish to Nginx document root
sudo mkdir -p /var/www/locktrace
sudo cp /opt/blockchaint/frontend/index.html /var/www/locktrace/index.html
sudo cp /opt/blockchaint/frontend/sw.js /var/www/locktrace/sw.js
sudo cp /opt/blockchaint/frontend/integrity.json /var/www/locktrace/integrity.json
sudo cp /opt/blockchaint/frontend/integrity.json /opt/blockchaint/templates/integrity.json
sudo chown -R www-data:www-data /var/www/locktrace

# 3. Restart Services
sudo systemctl restart blockchaint.service
sudo systemctl restart blockchaint-relayer.service
sleep 3
sudo systemctl reload nginx

echo "[*] Verifying integrity endpoint..."
curl -s http://127.0.0.1:5000/api/v1/frontend/integrity | head -c 250
echo ""
echo "[*] Checking blockchaint service status..."
systemctl is-active blockchaint.service
systemctl is-active blockchaint-relayer.service
"""
    ssh_cmd = [
        "ssh", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        VPS_HOST, remote_script
    ]
    if not run_cmd(ssh_cmd, timeout=90):
        print("[!] Remote execution failed")
        sys.exit(1)

    # Download updated integrity.json to local frontend & templates
    run_cmd([
        "scp", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        f"{VPS_HOST}:/opt/blockchaint/frontend/integrity.json", "frontend/integrity.json"
    ], timeout=30)
    run_cmd([
        "scp", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        f"{VPS_HOST}:/opt/blockchaint/frontend/integrity.json", "templates/integrity.json"
    ], timeout=30)

    print("[+] Fast deploy and on-chain seal completed successfully!")

if __name__ == "__main__":
    main()
