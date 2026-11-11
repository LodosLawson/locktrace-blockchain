"""
BlockChainT - High-Performance ACID SQLite WAL Persistence Engine (v2.3.0)
==========================================================================
Provides multi-worker safe SQLite WAL storage for blocks, shared mempool,
wallets, decentralized P2P nodes, and cryptographic validator block attestations.
"""

import json
import os
import sqlite3
import time
from typing import Dict, List, Optional, Tuple


class SQLiteStorage:
    """Thread-safe & multi-process safe SQLite WAL ledger + mempool persistence."""

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
                CREATE TABLE IF NOT EXISTS mempool (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    tx_hash TEXT UNIQUE NOT NULL,
                    tx_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
            """)
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS block_attestations (
                    block_index INTEGER NOT NULL,
                    node_id TEXT NOT NULL,
                    miner_address TEXT NOT NULL,
                    block_hash TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    PRIMARY KEY (block_index, node_id)
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tx_lookup (
                    tx_hash TEXT PRIMARY KEY,
                    block_index INTEGER NOT NULL,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    amount REAL NOT NULL,
                    fee REAL NOT NULL,
                    tx_type TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    extra_json TEXT NOT NULL DEFAULT '{}'
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_lookup_sender ON tx_lookup(sender);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_lookup_recipient ON tx_lookup(recipient);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_lookup_block ON tx_lookup(block_index);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_lookup_timestamp ON tx_lookup(timestamp);")

            # One-time automated backfill from historical blocks if tx_lookup is empty
            cur_tx_cnt = conn.execute("SELECT COUNT(*) AS cnt FROM tx_lookup;").fetchone()
            if int(cur_tx_cnt["cnt"]) == 0:
                b_cur = conn.execute("SELECT block_index, timestamp, transactions_json FROM blocks ORDER BY block_index ASC;")
                for b_row in b_cur.fetchall():
                    b_idx = int(b_row["block_index"])
                    b_time = float(b_row["timestamp"])
                    try:
                        tx_list = json.loads(b_row["transactions_json"])
                        for tx in tx_list:
                            tx_h = str(tx.get("tx_hash") or tx.get("hash") or "")
                            if not tx_h:
                                continue
                            sender = str(tx.get("sender") or "")
                            recip = str(tx.get("recipient") or tx.get("receiver") or "")
                            amt = float(tx.get("amount") or 0.0)
                            fee = float(tx.get("fee") or 0.0)
                            ttype = str(tx.get("tx_type") or tx.get("type") or "transfer")
                            tstamp = float(tx.get("timestamp") or b_time)
                            extra = json.dumps(tx.get("extra_data") or tx.get("data") or {}, ensure_ascii=False)
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO tx_lookup (
                                    tx_hash, block_index, sender, recipient, amount, fee, tx_type, timestamp, extra_json
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                                """,
                                (tx_h, b_idx, sender, recip, amt, fee, ttype, tstamp, extra),
                            )
                    except Exception:
                        pass

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

    def get_max_block_index(self) -> int:
        conn = self._connect()
        try:
            cur = conn.execute("SELECT COALESCE(MAX(block_index), -1) AS max_idx FROM blocks;")
            row = cur.fetchone()
            return int(row["max_idx"]) if row else -1
        except Exception:
            return -1
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
        """Loads full ledger state, shared mempool, and current revision from SQLite WAL."""
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT block_index, hash, previous_hash, merkle_root, timestamp, nonce, miner, version, transactions_json "
                "FROM blocks ORDER BY block_index ASC;"
            )
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

            mempool_rows = conn.execute("SELECT tx_json FROM mempool ORDER BY seq ASC;").fetchall()
            pending_txs: List[dict] = []
            for r in mempool_rows:
                try:
                    pending_txs.append(json.loads(r["tx_json"]))
                except Exception:
                    pass

            att_rows = conn.execute(
                "SELECT block_index, COUNT(*) AS cnt FROM block_attestations GROUP BY block_index;"
            ).fetchall()
            attestation_counts: Dict[int, int] = {int(r["block_index"]): int(r["cnt"]) for r in att_rows}

            chain_dicts: List[dict] = []
            for r in block_rows:
                b_idx = int(r["block_index"])
                chain_dicts.append({
                    "index": b_idx,
                    "hash": r["hash"],
                    "previous_hash": r["previous_hash"],
                    "merkle_root": r["merkle_root"],
                    "timestamp": r["timestamp"],
                    "nonce": r["nonce"],
                    "miner": r["miner"],
                    "version": r["version"],
                    "attestations_count": attestation_counts.get(b_idx, 0),
                    "transactions": json.loads(r["transactions_json"]),
                })

            return revision, {
                "chain": chain_dicts,
                "pending_transactions": pending_txs,
                "attestation_counts": attestation_counts,
                "wallets": wallets,
                "nodes": nodes,
                "total_transactions": int(meta.get("total_transactions", "0")),
                "total_fees_collected": float(meta.get("total_fees_collected", "0.0")),
            }
        finally:
            conn.close()

    def load_delta_state(self, since_block_index: int, expected_tip_hash: str) -> Optional[Tuple[int, dict]]:
        """
        O(Δ) incremental state loader for multi-worker concurrency.
        Verifies canonical tip hash at since_block_index to prevent fork desynchronization;
        returns None if full reload is required.
        """
        if since_block_index < 0 or not expected_tip_hash:
            return None
        conn = self._connect()
        try:
            anchor = conn.execute(
                "SELECT hash FROM blocks WHERE block_index = ?;",
                (int(since_block_index),),
            ).fetchone()
            if not anchor or str(anchor["hash"]) != str(expected_tip_hash):
                return None

            cur = conn.execute(
                "SELECT block_index, hash, previous_hash, merkle_root, timestamp, nonce, miner, version, transactions_json "
                "FROM blocks WHERE block_index > ? ORDER BY block_index ASC;",
                (int(since_block_index),),
            )
            new_block_rows = cur.fetchall()

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

            mempool_rows = conn.execute("SELECT tx_json FROM mempool ORDER BY seq ASC;").fetchall()
            pending_txs: List[dict] = []
            for r in mempool_rows:
                try:
                    pending_txs.append(json.loads(r["tx_json"]))
                except Exception:
                    pass

            att_rows = conn.execute(
                "SELECT block_index, COUNT(*) AS cnt FROM block_attestations GROUP BY block_index;"
            ).fetchall()
            attestation_counts: Dict[int, int] = {int(r["block_index"]): int(r["cnt"]) for r in att_rows}

            new_chain_dicts: List[dict] = []
            for r in new_block_rows:
                b_idx = int(r["block_index"])
                new_chain_dicts.append({
                    "index": b_idx,
                    "hash": r["hash"],
                    "previous_hash": r["previous_hash"],
                    "merkle_root": r["merkle_root"],
                    "timestamp": r["timestamp"],
                    "nonce": r["nonce"],
                    "miner": r["miner"],
                    "version": r["version"],
                    "attestations_count": attestation_counts.get(b_idx, 0),
                    "transactions": json.loads(r["transactions_json"]),
                })

            return revision, {
                "new_blocks": new_chain_dicts,
                "pending_transactions": pending_txs,
                "attestation_counts": attestation_counts,
                "wallets": wallets,
                "nodes": nodes,
                "total_transactions": int(meta.get("total_transactions", "0")),
                "total_fees_collected": float(meta.get("total_fees_collected", "0.0")),
            }
        except Exception:
            return None
        finally:
            conn.close()

    def save_state(self, blocks_dicts: List[dict], wallets: Dict[str, dict],
                   nodes: Dict[str, dict], total_transactions: int,
                   total_fees_collected: float,
                   pending_dicts: Optional[List[dict]] = None,
                   dirty_wallets: Optional[Dict[str, dict]] = None) -> int:
        """
        Persists new blocks incrementally, synchronizes shared mempool,
        and upserts wallets/nodes inside a single ACID WAL transaction.
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
                    # Index transactions in tx_lookup
                    for tx in b.get("transactions", []):
                        tx_h = str(tx.get("tx_hash") or tx.get("hash") or "")
                        if not tx_h:
                            continue
                        sender = str(tx.get("sender") or "")
                        recip = str(tx.get("recipient") or tx.get("receiver") or "")
                        amt = float(tx.get("amount") or 0.0)
                        fee = float(tx.get("fee") or 0.0)
                        ttype = str(tx.get("tx_type") or tx.get("type") or "transfer")
                        tstamp = float(tx.get("timestamp") or b["timestamp"])
                        extra = json.dumps(tx.get("extra_data") or tx.get("data") or {}, ensure_ascii=False)
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO tx_lookup (
                                tx_hash, block_index, sender, recipient, amount, fee, tx_type, timestamp, extra_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                            """,
                            (tx_h, int(b["index"]), sender, recip, amt, fee, ttype, tstamp, extra),
                        )

            # Synchronize shared multi-worker mempool
            if pending_dicts is not None:
                conn.execute("DELETE FROM mempool;")
                for p_tx in pending_dicts:
                    tx_h = str(p_tx.get("tx_hash") or "")
                    conn.execute(
                        "INSERT OR REPLACE INTO mempool (tx_hash, tx_json, created_at) VALUES (?, ?, ?);",
                        (tx_h, json.dumps(p_tx, ensure_ascii=False), float(p_tx.get("timestamp", time.time()))),
                    )

            wallets_to_upsert = dirty_wallets if dirty_wallets is not None else wallets
            for addr, w_info in wallets_to_upsert.items():
                if not isinstance(w_info, dict):
                    continue
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

    def save_nodes_only(self, nodes: Dict[str, dict]):
        """Fast O(1) persistence for P2P node heartbeats without rewriting blocks or incrementing full chain revision."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
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
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def load_nodes_only(self) -> Dict[str, dict]:
        """Reads the latest P2P node telemetry table directly from SQLite WAL."""
        conn = self._connect()
        try:
            node_rows = conn.execute("SELECT node_id, data_json FROM nodes;").fetchall()
            nodes: Dict[str, dict] = {}
            for r in node_rows:
                try:
                    nodes[r["node_id"]] = json.loads(r["data_json"])
                except Exception:
                    pass
            return nodes
        except Exception:
            return {}
        finally:
            conn.close()

    def record_attestation(self, block_index: int, node_id: str, miner_address: str,
                           block_hash: str, signature: str, timestamp: float) -> Tuple[bool, int]:
        """Records a cryptographic validator block attestation if not already submitted by this node."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            existing = conn.execute(
                "SELECT 1 FROM block_attestations WHERE block_index = ? AND node_id = ?;",
                (int(block_index), str(node_id)),
            ).fetchone()
            inserted = False
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO block_attestations (
                        block_index, node_id, miner_address, block_hash, signature, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (int(block_index), str(node_id), str(miner_address), str(block_hash), str(signature), float(timestamp)),
                )
                rev_row = conn.execute("SELECT value FROM meta WHERE key = 'state_revision';").fetchone()
                next_rev = (int(rev_row["value"]) if rev_row else 0) + 1
                conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('state_revision', ?);", (str(next_rev),))
                inserted = True
            cnt_row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM block_attestations WHERE block_index = ?;",
                (int(block_index),),
            ).fetchone()
            conn.execute("COMMIT;")
            return inserted, int(cnt_row["cnt"]) if cnt_row else 0
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def get_block_attestations(self, block_index: int) -> List[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT block_index, node_id, miner_address, block_hash, signature, timestamp "
                "FROM block_attestations WHERE block_index = ? ORDER BY timestamp ASC;",
                (int(block_index),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_transactions_for_address(self, address: str, limit: int = 100) -> List[dict]:
        """High-speed indexed retrieval of wallet transaction history O(log N)."""
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                SELECT tx_hash, block_index, sender, recipient, amount, fee, tx_type, timestamp, extra_json
                FROM tx_lookup
                WHERE sender = ? OR recipient = ? OR extra_json LIKE ?
                ORDER BY block_index DESC, timestamp DESC
                LIMIT ?;
                """,
                (address, address, f'%"author": "{address}"%', limit),
            )
            rows = cur.fetchall()
            results = []
            for r in rows:
                try:
                    extra = json.loads(r["extra_json"])
                except Exception:
                    extra = {}
                results.append({
                    "tx_hash": r["tx_hash"],
                    "block_index": r["block_index"],
                    "sender": r["sender"],
                    "recipient": r["recipient"],
                    "amount": r["amount"],
                    "fee": r["fee"],
                    "type": r["tx_type"],
                    "tx_type": r["tx_type"],
                    "timestamp": r["timestamp"],
                    "extra_data": extra,
                })
            return results
        finally:
            conn.close()

    def get_transaction_by_hash(self, tx_hash: str) -> Optional[dict]:
        """Instant O(1) indexed lookup of any transaction by tx_hash."""
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                SELECT tx_hash, block_index, sender, recipient, amount, fee, tx_type, timestamp, extra_json
                FROM tx_lookup
                WHERE tx_hash = ?;
                """,
                (tx_hash,),
            )
            r = cur.fetchone()
            if not r:
                return None
            try:
                extra = json.loads(r["extra_json"])
            except Exception:
                extra = {}
            return {
                "tx_hash": r["tx_hash"],
                "block_index": r["block_index"],
                "sender": r["sender"],
                "recipient": r["recipient"],
                "amount": r["amount"],
                "fee": r["fee"],
                "type": r["tx_type"],
                "tx_type": r["tx_type"],
                "timestamp": r["timestamp"],
                "extra_data": extra,
            }
        finally:
            conn.close()

    def get_block_by_index(self, block_index: int) -> Optional[dict]:
        """Instant O(1) indexed lookup of any block by block_index from SQLite."""
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                SELECT block_index, hash, previous_hash, merkle_root, timestamp, nonce, miner, version, transactions_json
                FROM blocks
                WHERE block_index = ?;
                """,
                (block_index,),
            )
            r = cur.fetchone()
            if not r:
                return None
            try:
                txs = json.loads(r["transactions_json"])
            except Exception:
                txs = []
            return {
                "index": int(r["block_index"]),
                "hash": r["hash"],
                "previous_hash": r["previous_hash"],
                "merkle_root": r["merkle_root"],
                "timestamp": r["timestamp"],
                "nonce": r["nonce"],
                "miner": r["miner"],
                "version": r["version"],
                "transactions": txs,
            }
        finally:
            conn.close()

    def get_recent_blocks(self, limit: int = 20, offset: int = 0) -> List[dict]:
        """Fetch range of recent blocks directly from SQLite indexed by block_index DESC."""
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                SELECT block_index, hash, previous_hash, merkle_root, timestamp, nonce, miner, version, transactions_json
                FROM blocks
                ORDER BY block_index DESC
                LIMIT ? OFFSET ?;
                """,
                (max(1, min(limit, 100)), max(0, offset)),
            )
            results = []
            for r in cur.fetchall():
                try:
                    txs = json.loads(r["transactions_json"])
                except Exception:
                    txs = []
                results.append({
                    "index": int(r["block_index"]),
                    "hash": r["hash"],
                    "previous_hash": r["previous_hash"],
                    "merkle_root": r["merkle_root"],
                    "timestamp": r["timestamp"],
                    "nonce": r["nonce"],
                    "miner": r["miner"],
                    "version": r["version"],
                    "transactions": txs,
                })
            return results
        finally:
            conn.close()
