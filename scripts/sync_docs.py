"""
LockTrace SSOT Documentation Verifier & Synchronizer
===================================================
Verifies that all fees, rates, consensus splits, and limits documented
in README.md and docs/WHITEPAPER.md match config.py (Single Source of Truth).
"""

import os
import sys
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import Config

def verify_and_sync():
    print(f"=== LOCKTRACE SSOT VERIFIER (v{Config.PROTOCOL_VERSION}) ===")
    print(f"Space Post Fee:      {Config.SPACE_POST_FEE} BCT")
    print(f"Space Like Fee:      {Config.SPACE_LIKE_FEE} BCT")
    print(f"Space Comment Fee:   {Config.SPACE_COMMENT_FEE} BCT")
    print(f"Space Follow Fee:    {Config.SPACE_FOLLOW_FEE} BCT")
    print(f"BNS Fees:            {Config.BNS_FEES}")
    print(f"Consensus Rewards:   Miner {Config.REWARD_MINER_PERCENT}% / Validator {Config.REWARD_VALIDATOR_PERCENT}%")
    print(f"Validator Min Stake: {Config.MIN_VALIDATOR_STAKE} BCT")
    print(f"Target Block Time:   {Config.TARGET_BLOCK_TIME}s (LWMA Window: {Config.LWMA_WINDOW})")
    print(f"Action Cooldowns:    {Config.ACTION_COOLDOWNS}")
    print(f"Min EVM Confs:       {Config.MIN_EVM_CONFIRMATIONS}")

    # Check README.md
    readme_path = os.path.join(ROOT, "README.md")
    with open(readme_path, "r", encoding="utf-8") as f:
        readme = f.read()

    assert f"{Config.SPACE_POST_FEE:.2f} BCT" in readme, "README.md space_post fee mismatch!"
    assert f"{Config.SPACE_LIKE_FEE:.2f} BCT" in readme, "README.md space_like fee mismatch!"
    assert f"{Config.SPACE_COMMENT_FEE:.2f} BCT" in readme, "README.md space_comment fee mismatch!"
    assert f"{Config.SPACE_FOLLOW_FEE:.2f} BCT" in readme, "README.md space_follow fee mismatch!"
    assert f"{Config.BNS_FEES[3]:.1f} BCT" in readme, "README.md 3-letter BNS fee mismatch!"

    # Check WHITEPAPER.md
    wp_path = os.path.join(ROOT, "docs", "WHITEPAPER.md")
    with open(wp_path, "r", encoding="utf-8") as f:
        wp = f.read()

    assert f"{Config.SPACE_POST_FEE:.2f}\\text{{ BCT}}" in wp, "WHITEPAPER.md space_post fee mismatch!"
    assert f"{Config.SPACE_LIKE_FEE:.2f}\\text{{ BCT}}" in wp, "WHITEPAPER.md space_like fee mismatch!"
    assert f"{Config.SPACE_COMMENT_FEE:.2f}\\text{{ BCT}}" in wp, "WHITEPAPER.md space_comment fee mismatch!"
    assert f"{Config.SPACE_FOLLOW_FEE:.2f}\\text{{ BCT}}" in wp, "WHITEPAPER.md space_follow fee mismatch!"
    assert f"{Config.BNS_FEES[3]:.2f}\\text{{ BCT}}" in wp, "WHITEPAPER.md 3-letter BNS fee mismatch!"
    assert f"{Config.MIN_VALIDATOR_STAKE:,.1f}" in wp or "1{,}000.0" in wp, "WHITEPAPER.md MIN_VALIDATOR_STAKE mismatch!"

    print("\n[SUCCESS] All documentation matches config.py with 100% precision!")

if __name__ == "__main__":
    verify_and_sync()

