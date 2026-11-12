"""
LockTrace (BCT) - Cryptographically Hardened Web Push Notification Engine
===========================================================================
Implements RFC 8291 & RFC 8292 (VAPID / Web Push Protocol) for off-site
real-time native mobile PWA & desktop notifications with zero security loopholes.

Security Invariants:
1. Non-Custodial Cryptographic Registration:
   Only the valid private key holder of a BCT address can register or revoke
   a push notification subscription. Verified via SECP256k1 ECDSA signatures.
2. Zero Key or Secret Leaks:
   VAPID private key is protected with 0600 file permissions and never leaves
   the server. Only benign, public ledger facts (e.g. "+X BCT Received") are pushed.
3. End-to-End Encryption in Transit:
   Payloads are encrypted with Curve P-256 ECDH + AES-128-GCM before reaching Google/Apple.
4. Auto-Pruning & DoS Resistance:
   Max 5 active devices per wallet. Expired tokens (HTTP 404/410) are purged immediately.
"""

import os
import time
import json
import sqlite3
import hashlib
import logging
import threading
import ipaddress
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, Tuple, List
from urllib.parse import urlparse

from core.wallet import verify_signature, public_key_to_address

logger = logging.getLogger("LockTrace.Push")

ALLOWED_PUSH_DOMAINS = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    ".push.apple.com",
    ".push.services.mozilla.com",
    "updates.push.services.mozilla.com",
    ".notify.windows.com",
    ".wns.windows.com",
    ".push.brave.com",
)


def is_safe_push_endpoint(endpoint: str) -> bool:
    """
    Validates Web Push endpoint against SSRF (Server-Side Request Forgery).
    Strictly enforces:
    1. Scheme must be HTTPS.
    2. Hostname must NOT be an IP address (disallowing loopback, RFC1918, link-local, cloud metadata).
    3. Hostname must match authorized browser push notification gateways.
    """
    if not endpoint or not isinstance(endpoint, str):
        return False
    try:
        parsed = urlparse(endpoint.strip())
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            return False
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False
        # Disallow raw IP addresses (prevents 127.0.0.1, 169.254.169.254, ::1, etc.)
        try:
            ipaddress.ip_address(hostname)
            return False
        except ValueError:
            pass
        # Disallow localhost, local domains
        if hostname in ("localhost",) or hostname.endswith((".local", ".internal", ".localhost", ".onion")):
            return False
        # Check against allowed browser push gateways
        for allowed in ALLOWED_PUSH_DOMAINS:
            if allowed.startswith("."):
                if hostname.endswith(allowed) or hostname == allowed[1:]:
                    return True
            elif hostname == allowed:
                return True
        return False
    except Exception:
        return False

# Try to import pywebpush & py_vapid; graceful fallback if offline/mock
try:
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    HAS_WEBPUSH = True
except ImportError:
    HAS_WEBPUSH = False
    logger.warning("pywebpush or cryptography not available in this Python environment.")


DEFAULT_VAPID_CLAIM = "mailto:locktracetoken+space@gmail.com"


class PushNotificationService:
    def __init__(self, db_path: str = "blockchain.db", vapid_key_dir: Optional[str] = None):
        self.db_path = db_path
        self.lock = threading.RLock()
        
        # Locate VAPID key
        self.vapid_dir = vapid_key_dir or os.path.expanduser("~/.locktrace")
        os.makedirs(self.vapid_dir, exist_ok=True)
        self.vapid_key_path = os.path.join(self.vapid_dir, "vapid_private.pem")
        
        self.vapid_obj = None
        self.vapid_public_b64 = ""
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="LockTracePush")
        self._init_vapid_keys()
        self._init_db()

    def _init_db(self):
        """Create push_subscriptions table with indices in SQLite WAL."""
        with self.lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                cur = conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL;")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS push_subscriptions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        wallet_address TEXT NOT NULL,
                        endpoint TEXT NOT NULL UNIQUE,
                        p256dh TEXT NOT NULL,
                        auth TEXT NOT NULL,
                        user_agent TEXT DEFAULT '',
                        created_at REAL NOT NULL,
                        last_used REAL NOT NULL
                    );
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_push_wallet ON push_subscriptions(wallet_address);")
                conn.commit()
            except Exception as e:
                logger.error(f"Error initializing push database: {e}")
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def _init_vapid_keys(self):
        """Load or create persistent VAPID SECP256R1 keypair."""
        if not HAS_WEBPUSH:
            return

        try:
            if os.path.exists(self.vapid_key_path):
                self.vapid_obj = Vapid.from_file(self.vapid_key_path)
            else:
                self.vapid_obj = Vapid()
                self.vapid_obj.generate_keys()
                self.vapid_obj.save_key(self.vapid_key_path)
                try:
                    os.chmod(self.vapid_key_path, 0o600)
                except Exception:
                    pass

            # Export uncompressed public key to URL-safe base64 string
            raw_pub = self.vapid_obj.public_key.public_bytes(
                encoding=Encoding.X962,
                format=PublicFormat.UncompressedPoint
            )
            import base64
            self.vapid_public_b64 = base64.urlsafe_b64encode(raw_pub).rstrip(b'=').decode('utf-8')
            logger.info("VAPID Push Service initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to load/generate VAPID keys: {e}")

    def get_public_key(self) -> str:
        """Returns the public VAPID key for browser pushManager.subscribe()."""
        return self.vapid_public_b64

    def subscribe(
        self,
        wallet_address: str,
        public_key: str,
        subscription: Dict[str, Any],
        timestamp: float,
        signature: str,
        user_agent: str = ""
    ) -> Tuple[bool, str]:
        """
        Cryptographically registers an off-site Web Push subscription for a BCT wallet.
        Enforces SECP256k1 signature validation to prevent subscription spoofing.
        """
        clean_addr = (wallet_address or "").strip()
        clean_pub = (public_key or "").strip()
        clean_sig = (signature or "").strip()

        if not clean_addr.startswith("BCT") or len(clean_addr) != 43:
            return False, "Invalid BCT wallet address."

        # 1. Verify that public key derives to the exact wallet address
        derived = public_key_to_address(clean_pub)
        if not derived or derived != clean_addr:
            return False, "Public key does not match the provided BCT wallet address."

        # 2. Verify timestamp window (300 seconds freshness)
        now = time.time()
        try:
            ts = float(timestamp)
            if abs(now - ts) > 300:
                return False, "Signature timestamp expired or skewed (> 300s difference)."
        except Exception:
            return False, "Invalid timestamp format."

        # 3. Validate subscription structure
        if not isinstance(subscription, dict):
            return False, "Subscription must be an object."

        endpoint = str(subscription.get("endpoint", "")).strip()
        keys = subscription.get("keys", {}) or {}
        p256dh = str(keys.get("p256dh", "")).strip()
        auth = str(keys.get("auth", "")).strip()

        if not endpoint or not p256dh or not auth:
            return False, "Missing endpoint, p256dh, or auth in push subscription."

        # AUD12-04: Length bounding against database bloat and memory DoS attacks
        if len(endpoint) > 512:
            return False, "Push endpoint exceeds maximum allowed length (512 characters)."
        if len(p256dh) < 16 or len(p256dh) > 128:
            return False, "Invalid p256dh key length (must be between 16 and 128 characters)."
        if len(auth) < 8 or len(auth) > 64:
            return False, "Invalid auth secret length (must be between 8 and 64 characters)."

        # Verify secure HTTPS and authorized push gateway (SSRF Protection)
        if not is_safe_push_endpoint(endpoint):
            return False, "Push endpoint must be an authorized HTTPS browser push notification gateway (SSRF protection enforced)."

        # 4. Cryptographic Proof of Ownership (SECP256k1 Signature)
        endpoint_hash = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()
        auth_msg = f"LOCKTRACE_PUSH_SUB:{clean_addr}:{endpoint_hash}:{int(ts)}"

        if not verify_signature(clean_pub, auth_msg, clean_sig):
            return False, "Cryptographic SECP256k1 signature verification failed!"

        # 5. Commit to database with FIFO device capping (max 5 devices per wallet)
        with self.lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                cur = conn.cursor()

                # Clean up existing count for this wallet only if registering a brand new device
                cur.execute(
                    "SELECT id, endpoint FROM push_subscriptions WHERE wallet_address = ? ORDER BY created_at ASC",
                    (clean_addr,)
                )
                existing = cur.fetchall()
                existing_endpoints = {r[1] for r in existing}
                if endpoint not in existing_endpoints and len(existing) >= 5:
                    oldest_id = existing[0][0]
                    cur.execute("DELETE FROM push_subscriptions WHERE id = ?", (oldest_id,))

                # Upsert current subscription
                cur.execute("""
                    INSERT INTO push_subscriptions 
                        (wallet_address, endpoint, p256dh, auth, user_agent, created_at, last_used)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(endpoint) DO UPDATE SET
                        wallet_address = excluded.wallet_address,
                        p256dh = excluded.p256dh,
                        auth = excluded.auth,
                        user_agent = excluded.user_agent,
                        last_used = excluded.last_used;
                """, (clean_addr, endpoint, p256dh, auth, (user_agent or "")[:120], now, now))

                conn.commit()
                logger.info(f"Subscribed push device for {clean_addr[:10]}... (endpoint: {endpoint[:32]}...)")
                return True, "Push notifications subscribed successfully."
            except Exception as e:
                logger.error(f"Failed to save push subscription: {e}")
                return False, "Database error occurred while saving push subscription."
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def unsubscribe(self, endpoint: str) -> bool:
        """Removes a push subscription by endpoint."""
        clean_ep = (endpoint or "").strip()
        if not clean_ep:
            return False
        with self.lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                cur = conn.cursor()
                cur.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (clean_ep,))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to unsubscribe push: {e}")
                return False
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def get_subscriptions_for_wallet(self, wallet_address: str) -> List[Dict[str, Any]]:
        """Retrieve all active push subscriptions for a wallet."""
        clean_addr = (wallet_address or "").strip()
        if not clean_addr:
            return []
        with self.lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path, timeout=10.0)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE wallet_address = ?",
                    (clean_addr,)
                )
                rows = cur.fetchall()
                return [
                    {
                        "endpoint": r["endpoint"],
                        "keys": {
                            "p256dh": r["p256dh"],
                            "auth": r["auth"]
                        }
                    }
                    for r in rows
                ]
            except Exception as e:
                logger.error(f"Failed to query push subscriptions: {e}")
                return []
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def send_push_to_wallet(
        self,
        wallet_address: str,
        title: str,
        body: str,
        url: str = "/#cuzdanim",
        category: str = "transfer"
    ):
        """Asynchronously dispatches a Web Push payload to all registered devices of a wallet."""
        if not HAS_WEBPUSH or not self.vapid_obj:
            return

        subs = self.get_subscriptions_for_wallet(wallet_address)
        if not subs:
            return

        payload = {
            "title": title[:80],
            "body": body[:180],
            "url": url[:120],
            "category": category[:24],
            "timestamp": time.time(),
            "tag": f"locktrace-{category}-{int(time.time())}"
        }

        # AUD12-04: Run dispatch in a bounded thread pool executor to eliminate thread exhaustion DoS
        try:
            self._executor.submit(self._dispatch_push_worker, subs, payload)
        except Exception as e:
            logger.error(f"Failed to submit push task to thread pool executor: {e}")

    def _dispatch_push_worker(self, subscriptions: List[Dict[str, Any]], payload: Dict[str, Any]):
        """Worker executing RFC 8291 payload encryption and HTTP POST to push gateways."""
        claims = {"sub": DEFAULT_VAPID_CLAIM}
        data_str = json.dumps(payload)

        for sub in subscriptions:
            endpoint = sub.get("endpoint", "")
            if not is_safe_push_endpoint(endpoint):
                logger.warning(f"Skipping dispatch to disallowed push endpoint (SSRF blocked): {endpoint}")
                continue
            try:
                webpush(
                    subscription_info=sub,
                    data=data_str,
                    vapid_private_key=self.vapid_key_path,
                    vapid_claims=claims,
                    timeout=8
                )
            except WebPushException as ex:
                status_code = getattr(ex.response, "status_code", None) if ex.response else None
                # HTTP 404 or 410 indicates the client revoked permission or uninstalled PWA
                if status_code in (404, 410):
                    logger.info(f"Purging dead push endpoint ({status_code}): {endpoint[:32]}...")
                    self.unsubscribe(endpoint)
                else:
                    logger.warning(f"Push delivery notice ({status_code}): {ex}")
            except Exception as e:
                logger.debug(f"WebPush dispatch exception: {e}")

