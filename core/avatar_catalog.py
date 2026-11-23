# -*- coding: utf-8 -*-
"""
LockTrace On-Chain Profile Avatar Catalog & Bonding Curve Pricing Engine (SSOT)
===============================================================================
Extensible architecture for Soulbound (non-transferable / non-sellable) profile avatars.
Each base artwork has an immutable default ID (e.g. ANM-001).
Combining `base_id` + normalized `#RRGGBB` background color creates a unique Variant ID:
  e.g. `ANM-001-FFFFFF` (White background) or `ANM-001-10B981` (Emerald background).

Pricing & Tokenomics:
  - Any brand-new Variant ID (mint_count == 0) opens at 0.10 BCT.
  - Each subsequent purchase of that exact Variant ID increases its price by +25%:
      price(n) = 0.10 * (1.25 ** n)
  - Switching background color generates a distinct Variant ID; if unminted, it opens at 0.10 BCT.
  - Revenue split (atomic unit precision, zero drift):
      * 30% -> Genesis Treasury Vault
      * 70% -> Block Reward Pool (50% PoW Miner, 40% Active Validator Nodes, 10% Observer Stakers)
  - Soulbound policy: Purchased avatars cannot be transferred or sold; owners may freely
    equip or unequip any owned avatar on their profile via signed on-chain transactions.
"""

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple

ATOMIC_UNIT = 100_000_000  # 1 BCT = 10^8 atomic units

AVATAR_BASE_PRICE = Decimal("0.10")
AVATAR_PRICE_MULTIPLIER = Decimal("1.25")
AVATAR_EQUIP_FEE = Decimal("0.20")       # 0.20 BCT per on-chain equip or unequip action
AVATAR_SWAP_FEE = Decimal("0.40")        # 0.40 BCT to replace an already-equipped avatar (0.20 remove + 0.20 equip)
AVATAR_TREASURY_RATIO = Decimal("0.30")
AVATAR_POOL_RATIO = Decimal("0.70")
DEFAULT_BG_COLOR = "#FFFFFF"
MAX_MINT_EXPONENT = 80

_HEX_COLOR_RE = re.compile(r"^#[0-9A-F]{6}$")
_VARIANT_ID_RE = re.compile(r"^([A-Z]{2,6}-\d{3,5})-([0-9A-F]{6})$")

# Curated background palette for quick selection (users can also pick any valid #RRGGBB hex)
CURATED_BG_COLORS: List[Dict[str, str]] = [
    {"hex": "#FFFFFF", "name": "Pure White", "name_tr": "Beyaz"},
    {"hex": "#0F172A", "name": "Obsidian", "name_tr": "Obsidyen"},
    {"hex": "#10B981", "name": "LockTrace Emerald", "name_tr": "Zümrüt"},
    {"hex": "#3B82F6", "name": "Cobalt Blue", "name_tr": "Kobalt Mavi"},
    {"hex": "#8B5CF6", "name": "Neon Violet", "name_tr": "Mor"},
    {"hex": "#EC4899", "name": "Cyber Pink", "name_tr": "Pembe"},
    {"hex": "#F59E0B", "name": "Solar Gold", "name_tr": "Altın Sarısı"},
    {"hex": "#EF4444", "name": "Crimson", "name_tr": "Kırmızı"},
    {"hex": "#14B8A6", "name": "Ocean Teal", "name_tr": "Turkuaz"},
    {"hex": "#FDE68A", "name": "Warm Cream", "name_tr": "Krem"},
    {"hex": "#BAE6FD", "name": "Sky Pastel", "name_tr": "Gökyüzü"},
    {"hex": "#FECDD3", "name": "Blush Rose", "name_tr": "Gül Kurusu"},
]

# Extensible Collections Registry (add future collections here)
AVATAR_COLLECTIONS: Dict[str, Dict[str, str]] = {
    "animals": {
        "id": "animals",
        "name": "Animals",
        "name_tr": "Hayvanlar",
        "description": "Genesis pixel-art animal companions wearing the LockTrace badge.",
        "description_tr": "LockTrace rozetli Genesis piksel sanat hayvan koleksiyonu.",
    },
}

# Master Avatar Catalog (immutable base_id per artwork)
AVATAR_CATALOG: List[Dict[str, str]] = [
    {
        "base_id": "ANM-001",
        "collection": "animals",
        "slug": "octopus",
        "name": "Octopus",
        "name_tr": "Ahtapot",
        "image_url": "/avatars/animals/octopus.png",
    },
    {
        "base_id": "ANM-002",
        "collection": "animals",
        "slug": "bee",
        "name": "Bee",
        "name_tr": "Arı",
        "image_url": "/avatars/animals/bee.png",
    },
    {
        "base_id": "ANM-003",
        "collection": "animals",
        "slug": "flamingo",
        "name": "Flamingo",
        "name_tr": "Flamingo",
        "image_url": "/avatars/animals/flamingo.png",
    },
    {
        "base_id": "ANM-004",
        "collection": "animals",
        "slug": "weasel",
        "name": "Weasel",
        "name_tr": "Gelincik",
        "image_url": "/avatars/animals/weasel.png",
    },
    {
        "base_id": "ANM-005",
        "collection": "animals",
        "slug": "turtle",
        "name": "Turtle",
        "name_tr": "Kaplumbağa",
        "image_url": "/avatars/animals/turtle.png",
    },
    {
        "base_id": "ANM-006",
        "collection": "animals",
        "slug": "ant",
        "name": "Ant",
        "name_tr": "Karınca",
        "image_url": "/avatars/animals/ant.png",
    },
    {
        "base_id": "ANM-007",
        "collection": "animals",
        "slug": "eagle",
        "name": "Eagle",
        "name_tr": "Kartal",
        "image_url": "/avatars/animals/eagle.png",
    },
    {
        "base_id": "ANM-008",
        "collection": "animals",
        "slug": "platypus",
        "name": "Platypus",
        "name_tr": "Ornitorenk",
        "image_url": "/avatars/animals/platypus.png",
    },
    {
        "base_id": "ANM-009",
        "collection": "animals",
        "slug": "raccoon",
        "name": "Raccoon",
        "name_tr": "Rakun",
        "image_url": "/avatars/animals/raccoon.png",
    },
    {
        "base_id": "ANM-010",
        "collection": "animals",
        "slug": "shark",
        "name": "Shark",
        "name_tr": "Köpekbalığı",
        "image_url": "/avatars/animals/shark.png",
    },
    {
        "base_id": "ANM-011",
        "collection": "animals",
        "slug": "snake",
        "name": "Snake",
        "name_tr": "Yılan",
        "image_url": "/avatars/animals/snake.png",
    },
    {
        "base_id": "ANM-012",
        "collection": "animals",
        "slug": "zebra",
        "name": "Zebra",
        "name_tr": "Zebra",
        "image_url": "/avatars/animals/zebra.png",
    },
    {
        "base_id": "ANM-013",
        "collection": "animals",
        "slug": "giraffe",
        "name": "Giraffe",
        "name_tr": "Zürafa",
        "image_url": "/avatars/animals/giraffe.png",
    },
]

AVATAR_CATALOG_BY_ID: Dict[str, Dict[str, str]] = {
    item["base_id"]: item for item in AVATAR_CATALOG
}


def normalize_hex_color(raw: Optional[str]) -> Optional[str]:
    """
    Strictly validates and canonicalizes a hex background color to `#RRGGBB` uppercase.
    Rejects any non-hex input to prevent XSS / CSS injection.
    """
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if not s:
        return None
    if not s.startswith("#"):
        s = "#" + s
    if not _HEX_COLOR_RE.match(s):
        return None
    return s


def get_base_avatar(base_id: Optional[str]) -> Optional[Dict[str, str]]:
    if not base_id:
        return None
    return AVATAR_CATALOG_BY_ID.get(str(base_id).strip().upper())


def make_variant_id(base_id: str, bg_color: str) -> Optional[str]:
    item = get_base_avatar(base_id)
    color = normalize_hex_color(bg_color)
    if not item or not color:
        return None
    return f"{item['base_id']}-{color[1:]}"


def parse_variant_id(variant_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not variant_id:
        return None, None
    s = str(variant_id).strip().upper()
    m = _VARIANT_ID_RE.match(s)
    if not m:
        return None, None
    base_id = m.group(1)
    bg_color = f"#{m.group(2)}"
    if base_id not in AVATAR_CATALOG_BY_ID:
        return None, None
    return base_id, bg_color


def compute_variant_price(mint_count: int) -> float:
    """
    Bonding curve pricing for a specific Variant ID:
      n = 0 -> 0.10 BCT
      n = 1 -> 0.125 BCT (+25%)
      n = 2 -> 0.15625 BCT (+25%)
      ...
    """
    n = max(0, min(int(mint_count or 0), MAX_MINT_EXPONENT))
    price_dec = (AVATAR_BASE_PRICE * (AVATAR_PRICE_MULTIPLIER ** n)).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    return float(price_dec)


def compute_revenue_split(price: float) -> Dict[str, float]:
    """
    Computes exact atomic-unit revenue split with zero rounding drift:
      - 30% Treasury Vault
      - 70% Block Reward Pool (split 50% PoW Miner, 40% Active Validators, 10% Observer Stakers)
    """
    price_u = int(round(float(price) * ATOMIC_UNIT))
    treasury_u = (price_u * 30) // 100
    pool_u = price_u - treasury_u  # Guarantees treasury_u + pool_u == price_u exactly

    miner_u = (pool_u * 50) // 100
    validator_u = (pool_u * 40) // 100
    observer_u = pool_u - miner_u - validator_u

    return {
        "price": float(Decimal(price_u) / Decimal(ATOMIC_UNIT)),
        "treasury_cut": float(Decimal(treasury_u) / Decimal(ATOMIC_UNIT)),
        "pool_cut": float(Decimal(pool_u) / Decimal(ATOMIC_UNIT)),
        "miner_share": float(Decimal(miner_u) / Decimal(ATOMIC_UNIT)),
        "validator_share": float(Decimal(validator_u) / Decimal(ATOMIC_UNIT)),
        "observer_share": float(Decimal(observer_u) / Decimal(ATOMIC_UNIT)),
    }


def build_avatar_metadata(base_id: str, bg_color: str, mint_count: int = 0) -> Optional[Dict]:
    item = get_base_avatar(base_id)
    color = normalize_hex_color(bg_color)
    if not item or not color:
        return None
    variant_id = f"{item['base_id']}-{color[1:]}"
    return {
        "variant_id": variant_id,
        "base_id": item["base_id"],
        "collection": item["collection"],
        "slug": item["slug"],
        "name": item["name"],
        "name_tr": item["name_tr"],
        "image_url": item["image_url"],
        "bg_color": color,
        "mint_count": int(mint_count),
        "soulbound": True,
        "transferable": False,
        "sellable": False,
    }
