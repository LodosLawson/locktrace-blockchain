import subprocess
import json

KEY_PATH = r"C:\Users\mehem\Downloads\ssh-key-2026-11-02.key"
HOST = "ubuntu@129.151.205.219"

cmd = """python3 -c "
import sqlite3, json
conn = sqlite3.connect('/opt/blockchaint/blockchain.db')
c = conn.cursor()
try:
    c.execute('SELECT bridge_id, direction, status, bct_address, evm_address, amount_bct, tx_hash_l1, tx_hash_evm, created_at FROM bridge_transactions ORDER BY created_at DESC LIMIT 50')
    rows = c.fetchall()
    print('BRIDGE_ROWS:', json.dumps(rows))
except Exception as e:
    print('ERROR:', e)
" """

full_cmd = ["ssh", "-i", KEY_PATH, "-o", "StrictHostKeyChecking=no", HOST, cmd]
res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=30)
print(res.stdout)
if res.stderr:
    print("STDERR:", res.stderr)
