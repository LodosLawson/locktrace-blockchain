import os
import sys
import subprocess
import json

# AUD14-07 Hardened SSH inspection script with timeout protection and credential safety
DEFAULT_KEY = os.path.join(os.path.expanduser("~"), "Downloads", "ssh-key-2026-11-02.key")
KEY_PATH = os.environ.get("LOCKTRACE_SSH_KEY", DEFAULT_KEY if os.path.exists(DEFAULT_KEY) else "deploy/id_rsa")
HOST = os.environ.get("LOCKTRACE_SSH_HOST", "ubuntu@129.151.205.219")

cmd = """python3 -c "
import os, sqlite3, json
try:
    candidates = ['/opt/blockchaint/blockchain.db', '/opt/blockchaint/data/blockchain.db']
    db_path = next((p for p in candidates if os.path.exists(p)), candidates[0])
    conn = sqlite3.connect(db_path, timeout=10)
    c = conn.cursor()
    c.execute('SELECT bridge_id, direction, status, bct_address, evm_address, amount_bct, tx_hash_l1, tx_hash_evm, created_at FROM bridge_transactions ORDER BY created_at DESC LIMIT 50')
    rows = c.fetchall()
    print('BRIDGE_ROWS:', json.dumps(rows))
    conn.close()
except Exception as e:
    print('ERROR:', str(e))
" """

def mask_output(text: str) -> str:
    if not text:
        return ""
    # AUD15-02: Use match callable to strictly mask 64-hex secrets without regex backreference leaks
    import re
    def _mask_match(m):
        val = m.group(1)
        return val[:8] + "..." + val[-8:]
    return re.sub(r'\b([0-9a-fA-F]{64})\b', _mask_match, text)

if __name__ == "__main__":
    if not os.path.exists(KEY_PATH):
        print(f"[!] Warning: SSH Key not found at configured path. Set LOCKTRACE_SSH_KEY env var.")
        sys.exit(1)

    full_cmd = ["ssh", "-i", KEY_PATH, "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10", HOST, cmd]

    try:
        res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=30)
        if res.stdout:
            print(mask_output(res.stdout))
        if res.stderr:
            print("STDERR:", mask_output(res.stderr))
    except subprocess.TimeoutExpired:
        print("[!] Error: SSH command timed out after 30 seconds.")
        sys.exit(1)
    except Exception as e:
        print(f"[!] Execution failed: {e}")
        sys.exit(1)
