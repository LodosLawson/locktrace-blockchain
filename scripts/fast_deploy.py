# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import tarfile

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_KEY = os.path.join(WORKSPACE_DIR, ".keys", "vps.key")
DEFAULT_KEY = os.path.join(os.path.expanduser("~"), "Downloads", "ssh-key-2026-11-02.key")

if os.path.exists(WORKSPACE_KEY):
    SSH_KEY = os.environ.get("LOCKTRACE_SSH_KEY", WORKSPACE_KEY)
elif os.path.exists(DEFAULT_KEY):
    SSH_KEY = os.environ.get("LOCKTRACE_SSH_KEY", DEFAULT_KEY)
else:
    SSH_KEY = os.environ.get("LOCKTRACE_SSH_KEY", "deploy/id_rsa")

VPS_HOST = os.environ.get("LOCKTRACE_SSH_HOST", "ubuntu@129.151.205.219")

def run_cmd(cmd_list, timeout=120):
    print(f"[*] Running: {' '.join(cmd_list[:6])}...")
    sys.stdout.flush()
    res = subprocess.run(cmd_list, timeout=timeout)
    return res.returncode == 0

def sync_local_templates():
    pairs = [
        ("frontend/index.html", "templates/index.html"),
        ("frontend/sw.js", "templates/sw.js"),
    ]
    if os.path.isdir("frontend/simple-mode"):
        os.makedirs("templates/simple-mode", exist_ok=True)
        for fname in os.listdir("frontend/simple-mode"):
            src = os.path.join("frontend/simple-mode", fname)
            dst = os.path.join("templates/simple-mode", fname)
            if os.path.isfile(src):
                pairs.append((src, dst))
    for src, dst in pairs:
        if os.path.exists(src):
            with open(src, "rb") as f:
                data = f.read().replace(b"\r\n", b"\n")
            with open(src, "wb") as f:
                f.write(data)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(data)

def main():
    sync_local_templates()
    # F-07: keep CSP script hashes in lock-step with the inline scripts being shipped
    if subprocess.run([sys.executable, "scripts/sync_csp.py"]).returncode != 0:
        print("[!] CSP hash sync failed")
        sys.exit(1)
    tar_path = "pwa_bundle.tar.gz"
    print("[*] Creating compressed tarball...")
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add("frontend/index.html", arcname="frontend/index.html")
        tar.add("frontend/sw.js", arcname="frontend/sw.js")
        tar.add("frontend/icons", arcname="frontend/icons")
        if os.path.isdir("frontend/avatars"):
            tar.add("frontend/avatars", arcname="frontend/avatars")
        tar.add("frontend/vendor", arcname="frontend/vendor")
        if os.path.isdir("frontend/simple-mode"):
            tar.add("frontend/simple-mode", arcname="frontend/simple-mode")
        if os.path.exists("frontend/favicon.ico"):
            tar.add("frontend/favicon.ico", arcname="frontend/favicon.ico")
        tar.add("templates/index.html", arcname="templates/index.html")
        tar.add("templates/sw.js", arcname="templates/sw.js")
        if os.path.isdir("templates/simple-mode"):
            tar.add("templates/simple-mode", arcname="templates/simple-mode")
        tar.add("core", arcname="core")
        tar.add("docs", arcname="docs")
        tar.add("server.py", arcname="server.py")
        tar.add("node_runner.py", arcname="node_runner.py")
        tar.add("README.md", arcname="README.md")
        tar.add("requirements.txt", arcname="requirements.txt")
        tar.add("config.py", arcname="config.py")
        tar.add("deploy", arcname="deploy")
        tar.add("scripts/sign_frontend.py", arcname="scripts/sign_frontend.py")
        if os.path.isdir("crates"):
            def crates_filter(tarinfo):
                p = tarinfo.name.replace("\\", "/")
                if "/target" in p or p.endswith("/target") or p == "crates/target":
                    return None
                return tarinfo
            tar.add("crates", arcname="crates", filter=crates_filter)

    bundle_mb = round(os.path.getsize(tar_path) / (1024 * 1024), 2)
    print(f"[+] Bundle ready: {bundle_mb} MB (optimized)")

    print("[*] Uploading bundle in single SCP stream...")
    subprocess.run(["ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes", "-o", "ConnectTimeout=30", VPS_HOST, "rm -f /tmp/pwa_bundle.tar.gz"], check=False, timeout=30)
    scp_cmd = [
        "scp", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=30",
        tar_path, f"{VPS_HOST}:/tmp/pwa_bundle.tar.gz"
    ]
    if not run_cmd(scp_cmd, timeout=180):
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
if [ -d /tmp/crates ]; then
    sudo mkdir -p /opt/blockchaint/crates
    sudo cp -r /tmp/crates/* /opt/blockchaint/crates/
fi
sudo cp /tmp/node_runner.py /opt/blockchaint/node_runner.py
sudo cp /tmp/README.md /opt/blockchaint/README.md
sudo cp /tmp/requirements.txt /opt/blockchaint/requirements.txt
sudo cp /tmp/config.py /opt/blockchaint/config.py
sudo cp /tmp/frontend/index.html /opt/blockchaint/frontend/index.html
sudo cp /tmp/frontend/sw.js /opt/blockchaint/frontend/sw.js
sudo cp /tmp/templates/index.html /opt/blockchaint/templates/index.html
sudo cp /tmp/templates/sw.js /opt/blockchaint/templates/sw.js
sudo cp /tmp/scripts/sign_frontend.py /opt/blockchaint/scripts/sign_frontend.py
if [ -f /tmp/deploy/nginx_ssl.conf ]; then
    sudo cp /tmp/deploy/nginx_ssl.conf /etc/nginx/sites-available/blockchaint
    sudo nginx -t && sudo systemctl reload nginx
fi

# Install updated dependencies (cryptography)
sudo /opt/blockchaint/venv/bin/pip install -q -r /opt/blockchaint/requirements.txt

# 1. Sign Frontend with official Release Key
cd /opt/blockchaint
VER=$(sudo /opt/blockchaint/venv/bin/python3 -c "import config; print(config.Config.PROTOCOL_VERSION)")
sudo /opt/blockchaint/venv/bin/python3 scripts/sign_frontend.py --version "$VER" --key-file /home/ubuntu/.locktrace/release_signing_key.json

# 2. Publish to Nginx document root
sudo mkdir -p /var/www/locktrace /var/www/locktrace/icons /opt/blockchaint/frontend/icons
sudo cp -r /tmp/frontend/icons/* /opt/blockchaint/frontend/icons/
sudo cp -r /tmp/frontend/icons/* /var/www/locktrace/icons/
if [ -d /tmp/frontend/avatars ]; then
    sudo mkdir -p /opt/blockchaint/frontend/avatars /var/www/locktrace/avatars
    sudo cp -r /tmp/frontend/avatars/* /opt/blockchaint/frontend/avatars/
    sudo cp -r /tmp/frontend/avatars/* /var/www/locktrace/avatars/
fi
sudo mkdir -p /opt/blockchaint/frontend/vendor /var/www/locktrace/vendor
sudo cp -r /tmp/frontend/vendor/* /opt/blockchaint/frontend/vendor/
sudo cp -r /tmp/frontend/vendor/* /var/www/locktrace/vendor/
if [ -d /tmp/frontend/simple-mode ]; then
    sudo mkdir -p /opt/blockchaint/frontend/simple-mode /opt/blockchaint/templates/simple-mode /var/www/locktrace/simple-mode
    sudo cp -r /tmp/frontend/simple-mode/* /opt/blockchaint/frontend/simple-mode/
    sudo cp -r /tmp/frontend/simple-mode/* /opt/blockchaint/templates/simple-mode/
    sudo cp -r /tmp/frontend/simple-mode/* /var/www/locktrace/simple-mode/
fi
if [ -f /tmp/frontend/favicon.ico ]; then
    sudo cp /tmp/frontend/favicon.ico /opt/blockchaint/frontend/favicon.ico
    sudo cp /tmp/frontend/favicon.ico /var/www/locktrace/favicon.ico
fi
sudo cp /opt/blockchaint/frontend/index.html /var/www/locktrace/index.html
sudo cp /opt/blockchaint/frontend/sw.js /var/www/locktrace/sw.js
sudo cp /opt/blockchaint/frontend/integrity.json /var/www/locktrace/integrity.json
sudo cp /opt/blockchaint/frontend/integrity.json /opt/blockchaint/templates/integrity.json
sudo chown -R www-data:www-data /var/www/locktrace /opt/blockchaint/frontend

# 3. Restart Services
sudo systemctl restart blockchaint.service
sudo systemctl restart blockchaint-relayer.service
sleep 3
sudo systemctl reload nginx

echo "[*] Verifying integrity endpoint..."
curl -s http://127.0.0.1:5000/api/v1/frontend/integrity | head -c 250
echo ""
echo "[*] Checking blockchaint service status..."
sleep 2
systemctl is-active blockchaint.service
systemctl is-active blockchaint-relayer.service
"""
    ssh_cmd = [
        "ssh", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        VPS_HOST, remote_script
    ]
    if not run_cmd(ssh_cmd, timeout=180):
        print("[!] Remote execution failed")
        sys.exit(1)

    # Download updated integrity.json to local frontend & templates
    run_cmd([
        "scp", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        f"{VPS_HOST}:/opt/blockchaint/frontend/integrity.json", "frontend/integrity.json"
    ], timeout=30)
    run_cmd([
        "scp", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        f"{VPS_HOST}:/opt/blockchaint/frontend/integrity.json", "templates/integrity.json"
    ], timeout=30)

    print("[+] Fast deploy and on-chain seal completed successfully!")

if __name__ == "__main__":
    main()
