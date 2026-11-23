# -*- coding: utf-8 -*-
"""
LockTrace Protocol Rooms Engine (SSOT)
======================================
Reddit-style public on-chain discussion spaces ("Protocol Rooms") with:
  - Unique canonical Special ID (`RM-XXXXXXXX`) + normalized unique slug
  - Immutable single Room Avatar (optional at creation or one-time creator lock,
    permanently unchangeable once sealed on-chain)
  - Reddit-style Topics ("Mevzu") and nested Tweets/Replies under each Topic
  - Optimized anti-spam tiered pricing & creator royalty tokenomics with exact
    atomic-unit (10^8) integer arithmetic (zero rounding drift).
"""

import hashlib
import re
import unicodedata
from decimal import Decimal
from typing import Dict, Optional, Tuple

from core.avatar_catalog import (
    ATOMIC_UNIT,
    build_avatar_metadata,
    make_variant_id,
    parse_variant_id,
)

# ── Authoritative Pricing Constants (BCT) ────────────────────────
ROOM_TIER_FEES = {
    "short": Decimal("50.00"),      # 3-4 char normalized slug (anti-squatting premium)
    "medium": Decimal("25.00"),     # 5-8 char normalized slug
    "standard": Decimal("10.00"),   # 9+ char normalized slug
}
ROOM_AVATAR_SEAL_FEE = Decimal("2.00")   # One-time immutable room avatar seal fee
ROOM_TRANSFER_FEE = Decimal("0.50")      # On-chain room ownership transfer fee
ROOM_TOPIC_FEE = Decimal("0.25")         # Open a Topic ("Mevzu") inside a Room
ROOM_REPLY_FEE = Decimal("0.05")         # Post a tweet/reply under a Topic
ROOM_UPVOTE_FEE = Decimal("0.01")        # Upvote a Topic

# ── Strict Length & Validation Bounds ────────────────────────────
ROOM_NAME_MIN = 3
ROOM_NAME_MAX = 48
ROOM_DESC_MIN = 5
ROOM_DESC_MAX = 240
TOPIC_TITLE_MIN = 3
TOPIC_TITLE_MAX = 120
TOPIC_BODY_MIN = 3
TOPIC_BODY_MAX = 500
REPLY_BODY_MIN = 1
REPLY_BODY_MAX = 280

# Control characters & invisible Unicode spoofing characters
_FORBIDDEN_CHARS_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]"
)
_SLUG_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_ROOM_ID_RE = re.compile(r"^RM-[0-9A-F]{8}$")

# Turkish & common diacritic transliteration map to prevent homoglyph spoofing
_TRANSLITERATION_MAP = str.maketrans({
    "ç": "c", "Ç": "c",
    "ğ": "g", "Ğ": "g",
    "ı": "i", "İ": "i", "I": "i",
    "ö": "o", "Ö": "o",
    "ş": "s", "Ş": "s",
    "ü": "u", "Ü": "u",
})

# Reserved protocol room slugs barred from public squatting
RESERVED_ROOM_SLUGS = {
    "admin", "administrator", "system", "official", "locktrace", "bloctag",
    "bct", "treasury", "genesis", "bridge", "vault", "validator", "validators",
    "security", "support", "help", "mod", "moderator", "foundation", "burn",
    "null", "undefined", "all", "popular", "home", "new", "hot", "top",
    "explore", "rooms", "space", "wallet", "api", "root",
}


def sanitize_text(raw: Optional[str], allow_newlines: bool = False) -> Tuple[bool, str]:
    """
    Validates and normalizes user text.
    Rejects control characters and invisible Unicode spoofing characters.
    """
    if raw is None:
        return False, ""
    text = str(raw)
    if _FORBIDDEN_CHARS_RE.search(text):
        return False, "Text contains forbidden control or invisible characters."
    if allow_newlines:
        # Normalize CRLF -> LF, strip trailing spaces per line, collapse >2 blank lines
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    else:
        text = re.sub(r"\s+", " ", text).strip()
    return True, text


def normalize_room_slug(name: str) -> str:
    """
    Derives a deterministic, homoglyph-resistant lowercase ASCII slug from a room name.
    Example: 'Kripto Analiz TR!' -> 'kripto-analiz-tr'
    """
    s = str(name or "").translate(_TRANSLITERATION_MAP)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = _SLUG_NON_ALNUM_RE.sub("-", s).strip("-")
    if len(s) > 40:
        s = s[:40].rstrip("-")
    return s


def make_room_special_id(slug: str) -> str:
    """
    Generates a deterministic canonical Special ID (`RM-XXXXXXXX`) from a room slug.
    Because `slug` is unique on-chain, `RM-XXXXXXXX` is clean, compact, and verifiable.
    """
    digest = hashlib.sha256(f"LOCKTRACE_ROOM_V1:{slug}".encode("utf-8")).hexdigest()[:8].upper()
    return f"RM-{digest}"


def is_valid_room_id(room_id: Optional[str]) -> bool:
    return bool(room_id and _ROOM_ID_RE.match(str(room_id).strip().upper()))


def validate_room_name(raw_name: Optional[str]) -> Tuple[bool, str, str, str]:
    """
    Validates a room name and returns (ok, clean_name_or_error, slug, special_room_id).
    """
    ok, clean = sanitize_text(raw_name, allow_newlines=False)
    if not ok:
        return False, clean or "Invalid room name.", "", ""
    if len(clean) < ROOM_NAME_MIN:
        return False, f"Room name must be at least {ROOM_NAME_MIN} characters.", "", ""
    if len(clean) > ROOM_NAME_MAX:
        return False, f"Room name can be at most {ROOM_NAME_MAX} characters.", "", ""

    slug = normalize_room_slug(clean)
    compact_len = len(slug.replace("-", ""))
    if compact_len < 3:
        return False, "Room name must contain at least 3 alphanumeric characters.", "", ""
    if slug in RESERVED_ROOM_SLUGS:
        return False, f"Room name '{clean}' is reserved by the protocol.", "", ""

    room_id = make_room_special_id(slug)
    return True, clean, slug, room_id


def validate_room_description(raw_desc: Optional[str]) -> Tuple[bool, str]:
    ok, clean = sanitize_text(raw_desc, allow_newlines=True)
    if not ok:
        return False, clean or "Invalid room description."
    if len(clean) < ROOM_DESC_MIN:
        return False, f"Room description must be at least {ROOM_DESC_MIN} characters."
    if len(clean) > ROOM_DESC_MAX:
        return False, f"Room description can be at most {ROOM_DESC_MAX} characters."
    return True, clean


def validate_topic_fields(raw_title: Optional[str], raw_body: Optional[str]) -> Tuple[bool, str, str]:
    ok_t, title = sanitize_text(raw_title, allow_newlines=False)
    if not ok_t:
        return False, title or "Invalid topic title.", ""
    if len(title) < TOPIC_TITLE_MIN or len(title) > TOPIC_TITLE_MAX:
        return False, f"Topic title must be between {TOPIC_TITLE_MIN} and {TOPIC_TITLE_MAX} characters.", ""

    ok_b, body = sanitize_text(raw_body, allow_newlines=True)
    if not ok_b:
        return False, body or "Invalid topic content.", ""
    if len(body) < TOPIC_BODY_MIN or len(body) > TOPIC_BODY_MAX:
        return False, f"Topic content must be between {TOPIC_BODY_MIN} and {TOPIC_BODY_MAX} characters.", ""

    return True, title, body


def validate_reply_content(raw_content: Optional[str]) -> Tuple[bool, str]:
    ok, content = sanitize_text(raw_content, allow_newlines=True)
    if not ok:
        return False, content or "Invalid reply content."
    if len(content) < REPLY_BODY_MIN or len(content) > REPLY_BODY_MAX:
        return False, f"Reply must be between {REPLY_BODY_MIN} and {REPLY_BODY_MAX} characters."
    return True, content


def validate_room_avatar_spec(
    base_id: Optional[str], bg_color: Optional[str] = "#FFFFFF"
) -> Tuple[bool, str, Optional[str], Optional[dict]]:
    """
    Validates an optional immutable room avatar against the canonical Avatar Catalog.
    Returns (ok, error_msg, variant_id, metadata_dict).
    """
    raw_base = str(base_id or "").strip().upper()
    if not raw_base:
        return True, "", None, None
    vid = make_variant_id(raw_base, bg_color or "#FFFFFF")
    if not vid:
        return False, "Invalid avatar base ID or hex background color (#RRGGBB).", None, None
    b_id, color = parse_variant_id(vid)
    meta = build_avatar_metadata(b_id, color)
    return True, "", vid, meta


def compute_room_create_pricing(slug: str, has_avatar: bool = False) -> Dict[str, object]:
    """
    Computes exact tiered creation fee & atomic-unit revenue split (50% Treasury / 50% Miner-Validator Pool).
    """
    compact_len = len(str(slug or "").replace("-", ""))
    if compact_len <= 4:
        tier = "short"
        tier_label = "Premium (3-4 chars)"
        tier_label_tr = "Premium (3-4 karakter)"
        base_dec = ROOM_TIER_FEES["short"]
    elif compact_len <= 8:
        tier = "medium"
        tier_label = "Standard (5-8 chars)"
        tier_label_tr = "Standart (5-8 karakter)"
        base_dec = ROOM_TIER_FEES["medium"]
    else:
        tier = "standard"
        tier_label = "Community (9+ chars)"
        tier_label_tr = "Topluluk (9+ karakter)"
        base_dec = ROOM_TIER_FEES["standard"]

    avatar_dec = ROOM_AVATAR_SEAL_FEE if has_avatar else Decimal("0.00")
    total_dec = base_dec + avatar_dec

    total_u = int(total_dec * ATOMIC_UNIT)
    pool_u = total_u // 2
    treasury_u = total_u - pool_u  # Exact conservation: treasury_u + pool_u == total_u

    return {
        "tier": tier,
        "tier_label": tier_label,
        "tier_label_tr": tier_label_tr,
        "base_fee": float(base_dec),
        "avatar_fee": float(avatar_dec),
        "total_cost": round(total_u / ATOMIC_UNIT, 8),
        "treasury_cut": round(treasury_u / ATOMIC_UNIT, 8),
        "pool_cut": round(pool_u / ATOMIC_UNIT, 8),
    }


def compute_room_avatar_seal_pricing() -> Dict[str, float]:
    total_u = int(ROOM_AVATAR_SEAL_FEE * ATOMIC_UNIT)
    pool_u = total_u // 2
    treasury_u = total_u - pool_u
    return {
        "total_cost": round(total_u / ATOMIC_UNIT, 8),
        "treasury_cut": round(treasury_u / ATOMIC_UNIT, 8),
        "pool_cut": round(pool_u / ATOMIC_UNIT, 8),
    }


def compute_room_transfer_pricing() -> Dict[str, float]:
    """
    Room Ownership Transfer (0.50 BCT):
      - 50% (0.25 BCT) -> Treasury Reserve
      - 50% (0.25 BCT) -> Miner / Validator Pool
    """
    total_u = int(ROOM_TRANSFER_FEE * ATOMIC_UNIT)
    pool_u = total_u // 2
    treasury_u = total_u - pool_u
    return {
        "total_cost": round(total_u / ATOMIC_UNIT, 8),
        "treasury_cut": round(treasury_u / ATOMIC_UNIT, 8),
        "pool_cut": round(pool_u / ATOMIC_UNIT, 8),
    }


def compute_room_topic_pricing() -> Dict[str, float]:
    """
    Topic Creation (0.25 BCT):
      - 30% (0.075 BCT) -> Room Creator Royalty
      - 50% (0.125 BCT) -> Treasury Reserve
      - 20% (0.050 BCT) -> Miner / Validator Pool
    """
    total_u = int(ROOM_TOPIC_FEE * ATOMIC_UNIT)
    creator_u = (total_u * 30) // 100
    pool_u = (total_u * 20) // 100
    treasury_u = total_u - creator_u - pool_u
    return {
        "total_cost": round(total_u / ATOMIC_UNIT, 8),
        "room_creator_cut": round(creator_u / ATOMIC_UNIT, 8),
        "treasury_cut": round(treasury_u / ATOMIC_UNIT, 8),
        "pool_cut": round(pool_u / ATOMIC_UNIT, 8),
    }


def compute_room_reply_pricing() -> Dict[str, float]:
    """
    Topic Reply / Tweet (0.05 BCT):
      - 20% (0.010 BCT) -> Topic Author Royalty
      - 20% (0.010 BCT) -> Room Creator Royalty
      - 40% (0.020 BCT) -> Treasury Reserve
      - 20% (0.010 BCT) -> Miner / Validator Pool
    """
    total_u = int(ROOM_REPLY_FEE * ATOMIC_UNIT)
    topic_author_u = (total_u * 20) // 100
    room_creator_u = (total_u * 20) // 100
    pool_u = (total_u * 20) // 100
    treasury_u = total_u - topic_author_u - room_creator_u - pool_u
    return {
        "total_cost": round(total_u / ATOMIC_UNIT, 8),
        "topic_author_cut": round(topic_author_u / ATOMIC_UNIT, 8),
        "room_creator_cut": round(room_creator_u / ATOMIC_UNIT, 8),
        "treasury_cut": round(treasury_u / ATOMIC_UNIT, 8),
        "pool_cut": round(pool_u / ATOMIC_UNIT, 8),
    }


def compute_room_upvote_pricing() -> Dict[str, float]:
    """
    Topic Upvote (0.01 BCT):
      - 20% (0.002 BCT) -> Topic Author Royalty
      - 70% (0.007 BCT) -> Treasury Reserve
      - 10% (0.001 BCT) -> Miner / Validator Pool
    """
    total_u = int(ROOM_UPVOTE_FEE * ATOMIC_UNIT)
    author_u = (total_u * 20) // 100
    pool_u = (total_u * 10) // 100
    treasury_u = total_u - author_u - pool_u
    return {
        "total_cost": round(total_u / ATOMIC_UNIT, 8),
        "author_cut": round(author_u / ATOMIC_UNIT, 8),
        "treasury_cut": round(treasury_u / ATOMIC_UNIT, 8),
        "pool_cut": round(pool_u / ATOMIC_UNIT, 8),
    }


def get_rooms_tokenomics_summary() -> Dict[str, object]:
    """Returns canonical protocol room pricing & revenue split metadata for UI/API."""
    return {
        "room_create_tiers": {
            "short_3_4": float(ROOM_TIER_FEES["short"]),
            "medium_5_8": float(ROOM_TIER_FEES["medium"]),
            "standard_9_plus": float(ROOM_TIER_FEES["standard"]),
        },
        "room_avatar_seal_fee": float(ROOM_AVATAR_SEAL_FEE),
        "room_transfer_fee": float(ROOM_TRANSFER_FEE),
        "room_topic_fee": float(ROOM_TOPIC_FEE),
        "room_reply_fee": float(ROOM_REPLY_FEE),
        "room_upvote_fee": float(ROOM_UPVOTE_FEE),
        "splits": {
            "room_create": "50% Treasury • 50% Miner/Validators",
            "room_avatar_seal": "50% Treasury • 50% Miner/Validators (1x Immutable)",
            "room_transfer": "50% Treasury • 50% Miner/Validators",
            "room_topic": "30% Room Creator • 50% Treasury • 20% Miner/Validators",
            "room_reply": "20% Topic Author • 20% Room Creator • 40% Treasury • 20% Miner/Validators",
            "room_upvote": "20% Topic Author • 70% Treasury • 10% Miner/Validators",
        },
    }
