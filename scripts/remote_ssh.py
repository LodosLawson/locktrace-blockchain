# -*- coding: utf-8 -*-
"""
Helper script to execute remote commands on LockTrace VPS host and stream stdout/stderr.
Allows Antigravity or local developer to inspect logs and diagnose service status.
"""
import os
import sys
import subprocess

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

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/remote_ssh.py \"<command>\"")
        sys.exit(1)

    remote_cmd = sys.argv[1]
    ssh_cmd = [
        "ssh", "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        VPS_HOST,
        remote_cmd
    ]
    res = subprocess.run(ssh_cmd)
    sys.exit(res.returncode)

if __name__ == "__main__":
    main()
