import shutil
import os

target_dir = r"C:\Users\mehem\Documents\testndoe"
if os.path.exists(target_dir):
    files_to_sync = [
        ('server.py', os.path.join(target_dir, 'server.py')),
        ('node_runner.py', os.path.join(target_dir, 'node_runner.py')),
        ('frontend/index.html', os.path.join(target_dir, 'frontend', 'index.html')),
        ('frontend/sw.js', os.path.join(target_dir, 'frontend', 'sw.js')),
        ('frontend/integrity.json', os.path.join(target_dir, 'frontend', 'integrity.json')),
        ('templates/index.html', os.path.join(target_dir, 'templates', 'index.html')),
        ('templates/sw.js', os.path.join(target_dir, 'templates', 'sw.js')),
        ('templates/integrity.json', os.path.join(target_dir, 'templates', 'integrity.json')),
        ('core/blockchain.py', os.path.join(target_dir, 'core', 'blockchain.py')),
        ('core/bridge.py', os.path.join(target_dir, 'core', 'bridge.py')),
        ('core/storage.py', os.path.join(target_dir, 'core', 'storage.py')),
    ]
    for src, dst in files_to_sync:
        if os.path.exists(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            print(f"Synced {src} -> {dst}")
    print("Local testndoe sync complete!")
else:
    print("testndoe directory not found.")

