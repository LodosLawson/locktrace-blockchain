"""
BlockChainT - High-Performance ACID SQLite WAL Persistence Engine
=================================================================
Replaces full-file JSON re-parsing on every request with indexed SQLite WAL storage,
multi-worker revision tracking, and seamless zero-data-loss migration from blockchain.json.
"""

import json
import os
import sqlite3
import time
from typing import Dict, List, Optional, Tuple


class SQLiteStorage:
    """Thread-safe & multi-process safe SQLite WAL ledger persistence."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=15000;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        return conn

    def _init_schema(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS blocks (
                    block_index INTEGER PRIMARY KEY,
                    hash TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    merkle_root TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    nonce INTEGER NOT NULL,
                    miner TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    transactions_json TEXT NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_blocks_hash ON blocks(hash);")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS wallets (
                    address TEXT PRIMARY KEY,
                    public_key TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    nonce INTEGER NOT NULL DEFAULT 0
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL,
                    last_seen REAL NOT NULL
                );
            """)
            cur = conn.execute("SELECT value FROM meta WHERE key = 'state_revision';")
            if cur.fetchone() is None:
                conn.execute("INSERT INTO meta (key, value) VALUES ('state_revision', '0');")
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def get_state_revision(self) -> int:
        conn = self._connect()
        try:
            cur = conn.execute("SELECT value FROM meta WHERE key = 'state_revision';")
            row = cur.fetchone()
            return int(row["value"]) if row else 0
        except Exception:
            return 0
        finally:
            conn.close()

    def get_block_count(self) -> int:
        conn = self._connect()
        try:
            cur = conn.execute("SELECT COUNT(*) AS cnt FROM blocks;")
            row = cur.fetchone()
            return int(row["cnt"]) if row else 0
        finally:
            conn.close()

    def migrate_from_json_if_empty(self, json_path: str, merkle_fn) -> bool:
        """
        Atomically imports legacy data/blockchain.json into SQLite WAL if blocks table is empty.
        Preserves block version=1 on legacy blocks so historical PoW hashes stay 100% valid.
        """
        if not os.path.exists(json_path):
            return False
        if self.get_block_count() > 0:
            return True

        with open(json_path, "r", encoding="utf-8") as f:
            state = json.load(f)

        chain_data = state.get("chain", [])
        if not chain_data:
            return False

        wallets = state.get("wallets", {})
        nodes = state.get("nodes", {})
        total_txs = int(state.get("total_transactions", 0))
        total_fees = float(state.get("total_fees_collected", 0.0))

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            # Double-check inside exclusive write lock to avoid multi-worker race
            cur = conn.execute("SELECT COUNT(*) AS cnt FROM blocks;")
            if int(cur.fetchone()["cnt"]) > 0:
                conn.execute("COMMIT;")
                return True

            for b_data in chain_data:
                tx_list = b_data.get("transactions", [])
                tx_hashes = [t.get("tx_hash") or "" for t in tx_list]
                m_root = b_data.get("merkle_root") or merkle_fn(tx_hashes)
                b_ver = int(b_data.get("version", 1))
                conn.execute(
                    """
                    INSERT INTO blocks (
                        block_index, hash, previous_hash, merkle_root,
                        timestamp, nonce, miner, version, transactions_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        int(b_data["index"]),
                        str(b_data["hash"]),
                        str(b_data["previous_hash"]),
                        str(m_root),
                        float(b_data["timestamp"]),
                        int(b_data["nonce"]),
                        str(b_data.get("miner", "Genesis-Validator")),
                        b_ver,
                        json.dumps(tx_list, ensure_ascii=False),
                    ),
                )

            for addr, w_info in wallets.items():
                if not isinstance(w_info, dict):
                    w_info = {}
                conn.execute(
                    """
                    INSERT OR REPLACE INTO wallets (address, public_key, created_at, nonce)
                    VALUES (?, ?, ?, ?);
                    """,
                    (
                        str(addr),
                        str(w_info.get("public_key", "")),
                        float(w_info.get("created_at", time.time())),
                        int(w_info.get("nonce", 0)),
                    ),
                )

            for nid, n_info in nodes.items():
                if not isinstance(n_info, dict):
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO nodes (node_id, data_json, last_seen)
                    VALUES (?, ?, ?);
                    """,
                    (
                        str(nid),
                        json.dumps(n_info, ensure_ascii=False),
                        float(n_info.get("last_seen", time.time())),
                    ),
                )

            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('total_transactions', ?);", (str(total_txs),))
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('total_fees_collected', ?);", (str(total_fees),))
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('state_revision', '1');")
            conn.execute("COMMIT;")
            return True
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def load_full_state(self) -> Optional[Tuple[int, dict]]:
        """Loads full ledger state and current revision from SQLite WAL."""
        conn = self._connect()
        try:
            cur = conn.execute("SELECT block_index, hash, previous_hash, merkle_root, timestamp, nonce, miner, version, transactions_json FROM blocks ORDER BY block_index ASC;")
            block_rows = cur.fetchall()
            if not block_rows:
                return None

            meta_rows = conn.execute("SELECT key, value FROM meta;").fetchall()
            meta = {r["key"]: r["value"] for r in meta_rows}
            revision = int(meta.get("state_revision", "1"))

            wallet_rows = conn.execute("SELECT address, public_key, created_at, nonce FROM wallets;").fetchall()
            wallets: Dict[str, dict] = {
                r["address"]: {
                    "public_key": r["public_key"],
                    "created_at": r["created_at"],
                    "nonce": r["nonce"],
                }
                for r in wallet_rows
            }

            node_rows = conn.execute("SELECT node_id, data_json FROM nodes;").fetchall()
            nodes: Dict[str, dict] = {}
            for r in node_rows:
                try:
                    nodes[r["node_id"]] = json.loads(r["data_json"])
                except Exception:
                    pass

            chain_dicts: List[dict] = []
            for r in block_rows:
                chain_dicts.append({
                    "index": r["block_index"],
                    "hash": r["hash"],
                    "previous_hash": r["previous_hash"],
                    "merkle_root": r["merkle_root"],
                    "timestamp": r["timestamp"],
                    "nonce": r["nonce"],
                    "miner": r["miner"],
                    "version": r["version"],
                    "transactions": json.loads(r["transactions_json"]),
                })

            return revision, {
                "chain": chain_dicts,
                "wallets": wallets,
                "nodes": nodes,
                "total_transactions": int(meta.get("total_transactions", "0")),
                "total_fees_collected": float(meta.get("total_fees_collected", "0.0")),
            }
        finally:
            conn.close()

    def save_state(self, blocks_dicts: List[dict], wallets: Dict[str, dict],
                   nodes: Dict[str, dict], total_transactions: int,
                   total_fees_collected: float) -> int:
        """
        Persists new blocks incrementally and upserts wallets/nodes inside a single ACID WAL transaction.
        Returns the new state_revision.
        """
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.execute("SELECT COALESCE(MAX(block_index), -1) AS max_idx FROM blocks;")
            max_idx = int(cur.fetchone()["max_idx"])

            for b in blocks_dicts:
                if int(b["index"]) > max_idx:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO blocks (
                            block_index, hash, previous_hash, merkle_root,
                            timestamp, nonce, miner, version, transactions_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            int(b["index"]),
                            str(b["hash"]),
                            str(b["previous_hash"]),
                            str(b.get("merkle_root", "")),
                            float(b["timestamp"]),
                            int(b["nonce"]),
                            str(b.get("miner", "Genesis-Validator")),
                            int(b.get("version", 2)),
                            json.dumps(b["transactions"], ensure_ascii=False),
                        ),
                    )

            for addr, w_info in wallets.items():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO wallets (address, public_key, created_at, nonce)
                    VALUES (?, ?, ?, ?);
                    """,
                    (
                        str(addr),
                        str(w_info.get("public_key", "")),
                        float(w_info.get("created_at", time.time())),
                        int(w_info.get("nonce", 0)),
                    ),
                )

            # Sync node registry cleanly
            existing_ids = {r["node_id"] for r in conn.execute("SELECT node_id FROM nodes;").fetchall()}
            removed_ids = existing_ids - set(nodes.keys())
            for rid in removed_ids:
                conn.execute("DELETE FROM nodes WHERE node_id = ?;", (rid,))

            for nid, n_info in nodes.items():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO nodes (node_id, data_json, last_seen)
                    VALUES (?, ?, ?);
                    """,
                    (
                        str(nid),
                        json.dumps(n_info, ensure_ascii=False),
                        float(n_info.get("last_seen", time.time())),
                    ),
                )

            rev_row = conn.execute("SELECT value FROM meta WHERE key = 'state_revision';").fetchone()
            next_rev = (int(rev_row["value"]) if rev_row else 0) + 1

            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('total_transactions', ?);", (str(int(total_transactions)),))
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('total_fees_collected', ?);", (str(float(total_fees_collected)),))
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('state_revision', ?);", (str(next_rev),))
            conn.execute("COMMIT;")
            return next_rev
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()
