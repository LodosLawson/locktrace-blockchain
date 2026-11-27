"""
LockTrace wBCT Live Market Maker & Multi-Asset Basket Engine (Base Mainnet)
===========================================================================
v2.1 — Anti-Barcode Histerezis + Doğal Trend Dalgaları + Çoklu Sepet Endeksi:
- Havuz: wBCT / USDC (%0.9 Fee, TickSpacing 90)
- PoolId: 0xf38d2770459e2c4b5fa14af657c8726f1e96242af36d75ba4db1e57a911a9139
- Uniswap V4 Universal Router: 0xd6145b2D3F379919E8CdEda7B97e37c4b2Ca9c40
- Sepet Endeksi: (ΔBTC% + ΔETH% + ΔXRP%) / 3 (Binance birincil, Coinbase yedek)
- Kümülatif Hedef + Kontrollü Beta (2.5x ±%22 asimetrik jitter): Doğal altcoin gövdesi
- Barkod Kırıcı Histerezis & Yön Kilidi (%0.9 havuz makasında ping-pong engeli):
    * Aynı yön devam eşiği : %0.20 (doğal trend merdivenleri)
    * Ters yön dönüş eşiği : %0.55 + 20–40 dk rastgele yön kilidi (şok override: >= %1.25)
    * Değişken pencere     : 6–22 dk arası rastgele değerlendirme aralığı
- Dinamik 1-3 Asimetrik Parçalı Bölme (farklı büyüklüklerde doğal mum gövdeleri)
- Güvenlik Kalkanları:
    * DRY_RUN gerçek koruması, MAX_GAS_GWEI tavanı, MAX_SINGLE_TRADE_USD & MAX_DAILY_TXS devre kesici
    * Toz işlem (sub-dust) engeli, otomatik .env yükleyici, private key log koruması
- Bakiye Sorgulama: `python scripts/wbct_market_maker.py --balances`
"""

import argparse
import json
import logging
import os
import random
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

try:
    from eth_abi import encode
    from eth_account import Account
    from web3 import Web3
    HAS_WEB3 = True
except ImportError:
    Web3 = None
    Account = None
    encode = None
    HAS_WEB3 = False


def _load_dotenv():
    """Load workspace .env safely without overwriting existing env vars."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(root_dir, ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if not (v.startswith('"') or v.startswith("'")):
                    v = v.split("#")[0].strip()
                else:
                    q = v[0]
                    end_idx = v.find(q, 1)
                    v = v[1:end_idx] if end_idx != -1 else v.strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


_load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [wBCT-AMM]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("wBCT-AMM")


def _checksum(addr: str) -> str:
    return Web3.to_checksum_address(addr) if HAS_WEB3 and Web3 else addr


CONFIG: Dict[str, Any] = {
    "CHAIN_ID": 8453,
    "RPC_URL": os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),

    # Sözleşme Adresleri (Base Mainnet)
    "WBCT_ADDRESS": _checksum("0xCa6152Ae0E785F90ED65cd706B386E5B83D0EB28"),
    "USDC_ADDRESS": _checksum("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
    "UNIVERSAL_ROUTER": _checksum("0xd6145b2D3F379919E8CdEda7B97e37c4b2Ca9c40"),
    "POOL_ID": "0xf38d2770459e2c4b5fa14af657c8726f1e96242af36d75ba4db1e57a911a9139",

    # Havuz Rezerv Parametreleri
    "POOL_WBCT_RESERVE": float(os.getenv("BOT_POOL_WBCT_RESERVE", "2391.0")),
    "WBCT_UNIT_PRICE_USD": float(os.getenv("BOT_WBCT_PRICE_USD", "0.001048")),

    # Sepet & Beta Parametreleri (BTC + ETH + XRP)
    "BASKET_SYMBOLS": ("BTC", "ETH", "XRP"),
    "BETA_MULTIPLIER": float(os.getenv("BOT_BETA_MULTIPLIER", "2.5")),
    "JITTER_MIN": 0.78,
    "JITTER_MAX": 1.24,

    # Zamanlama (Doğal 2–10 dakikalık rastgele değerlendirme penceresi)
    "POLL_INTERVAL_SECONDS": 10,
    "WINDOW_MIN_SECONDS": int(os.getenv("BOT_WINDOW_MIN_SECONDS", "120")),   # 2 dk
    "WINDOW_MAX_SECONDS": int(os.getenv("BOT_WINDOW_MAX_SECONDS", "600")),   # 10 dk
    "WINDOW_SECONDS": 360,  # Parça yayılımı için ortalama pencere referansı (6 dk)

    # Dengeli Anti-Barkod Histerezis & Yön Kilidi (BTC+ETH+XRP Senkron)
    "MIN_DELTA_THRESHOLD_PCT": 0.08,          # Aynı yönde devam eşiği (%0.08)
    "REVERSE_DELTA_THRESHOLD_PCT": 0.22,      # Ters yöne dönüş eşiği (%0.22 - dengeli anti-barkod)
    "SHOCK_OVERRIDE_PCT": 0.65,               # %0.65+ sert piyasa hareketinde yön kilidini kır
    "DIRECTION_LOCK_MIN_SECONDS": int(os.getenv("BOT_DIR_LOCK_MIN_SECONDS", "360")),   # 6 dk
    "DIRECTION_LOCK_MAX_SECONDS": int(os.getenv("BOT_DIR_LOCK_MAX_SECONDS", "720")),   # 12 dk

    # Dinamik 1-3 Parçalı Çoklu Cüzdan Bölme Eşikleri (Ham Sepet % Değişimi)
    "SPLIT_2_THRESHOLD_PCT": 0.14,            # %0.14 - %0.30 -> 2 farklı cüzdan
    "SPLIT_3_THRESHOLD_PCT": 0.30,            # >= %0.30      -> 3 farklı cüzdan (Alpha, Beta, Gamma)
    "MAX_IMPACT_CAP_PCT": 4.00,               # Tek pencerede maksimum fiyat etkisi tavanı

    # Güvenlik & Devre Kesiciler
    "MAX_GAS_GWEI": float(os.getenv("BOT_MAX_GAS_GWEI", "0.5")),
    "MAX_SINGLE_TRADE_USD": float(os.getenv("BOT_MAX_SINGLE_TRADE_USD", "0.50")),
    "MIN_SLICE_WBCT": 0.50,            # 0.50 wBCT altı toz işlemleri tek parçada topla
    "MIN_SLICE_USD": 0.0005,           # $0.0005 altı toz işlemleri tek parçada topla
    "MIN_WALLET_ETH_GAS": 0.000003,    # Cüzdan başına minimum gas tamponu
    "MAX_DAILY_TXS": int(os.getenv("BOT_MAX_DAILY_TXS", "240")),

    # Simülasyon / Canlı Mod
    "DRY_RUN": os.getenv("BOT_DRY_RUN", "false").lower() in ("true", "1", "yes"),
}

ERC20_BALANCE_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    }
]


class PriceFeed:
    """BTC + ETH + XRP fiyat sağlayıcı (Binance birincil, Coinbase yedek)."""

    @staticmethod
    def _http_json(url: str, timeout: int = 5) -> Optional[Any]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        return None

    @classmethod
    def get_basket_prices(cls, symbols: Tuple[str, ...] = ("BTC", "ETH", "XRP")) -> Optional[Dict[str, float]]:
        # 1. Binance toplu sorgu (tek HTTP isteği)
        binance_syms = json.dumps([f"{s}USDT" for s in symbols], separators=(",", ":"))
        url = f"https://api.binance.com/api/v3/ticker/price?symbols={urllib.request.quote(binance_syms)}"
        data = cls._http_json(url)
        if isinstance(data, list):
            prices: Dict[str, float] = {}
            for item in data:
                sym = str(item.get("symbol", ""))
                for s in symbols:
                    if sym == f"{s}USDT":
                        prices[s] = float(item["price"])
            if len(prices) == len(symbols):
                return prices

        # 2. Coinbase yedek (tek tek spot fiyat)
        fallback: Dict[str, float] = {}
        for s in symbols:
            cb = cls._http_json(f"https://api.coinbase.com/v2/prices/{s}-USD/spot")
            if isinstance(cb, dict) and isinstance(cb.get("data"), dict) and "amount" in cb["data"]:
                fallback[s] = float(cb["data"]["amount"])
        if len(fallback) == len(symbols):
            return fallback

        return None

    @classmethod
    def get_eth_price(cls) -> Optional[float]:
        prices = cls.get_basket_prices(("ETH",))
        return prices.get("ETH") if prices else None


class BasketImpactEngine:
    """
    BTC + ETH + XRP Kümülatif Sepet Endeksi + Kontrollü Beta + Dinamik 1-3 Parçalı Zamanlayıcı.
    - Fiyatı başlangıç referansına göre kümülatif sepet endeksine bağlar (uzun vadede drift/kayma yapmaz).
    - Hareket büyüklüğüne göre 5 dakikalık pencere içine yayılmış 1, 2 veya 3 rastgele parçalı emir planlar.
    """

    def __init__(self, config: Dict[str, Any], wallet_count: int = 3):
        self.config = config
        self.wallet_count = max(1, wallet_count)
        self.initial_prices: Optional[Dict[str, float]] = None
        self.last_eval_time: float = 0.0
        self.next_eval_at: float = 0.0
        self.cumulative_executed_pct: float = 0.0
        self.pending_slices: List[Dict[str, Any]] = []
        self.last_direction: Optional[str] = None
        self.direction_lock_until: float = 0.0

    def _roll_next_window(self, now: float) -> float:
        w_min = int(self.config.get("WINDOW_MIN_SECONDS", 360))
        w_max = int(self.config.get("WINDOW_MAX_SECONDS", 1320))
        span = random.uniform(w_min, max(w_min + 60, w_max))
        self.next_eval_at = now + span
        return span

    @staticmethod
    def _random_weights(n: int) -> List[float]:
        if n <= 1:
            return [1.0]
        # Asimetrik (kuadratik) ağırlıklar: mum boylarının tekdüze barkod olmasını önler
        raw = [random.uniform(0.20, 1.0) ** 1.8 for _ in range(n)]
        total = sum(raw)
        return [r / total for r in raw]

    def _choose_slice_count(self, abs_raw_delta_pct: float, total_wbct: float, total_usd: float) -> int:
        if abs_raw_delta_pct >= self.config["SPLIT_3_THRESHOLD_PCT"]:
            n = 3
        elif abs_raw_delta_pct >= self.config["SPLIT_2_THRESHOLD_PCT"]:
            n = 2
        else:
            n = 1
        n = min(n, self.wallet_count)

        # Toz (sub-dust) koruması: parça başına minimum eşik sağlanmıyorsa parça sayısını düşür
        while n > 1:
            if (total_wbct / n) >= self.config["MIN_SLICE_WBCT"] and (total_usd / n) >= self.config["MIN_SLICE_USD"]:
                break
            n -= 1
        return n

    def compute_cumulative_basket_pct(self, prices: Dict[str, float]) -> float:
        assert self.initial_prices is not None
        deltas = []
        for sym in self.config["BASKET_SYMBOLS"]:
            p0 = self.initial_prices[sym]
            pt = prices[sym]
            deltas.append(((pt - p0) / p0) * 100.0)
        return sum(deltas) / len(deltas)

    def evaluate_market(self, prices: Dict[str, float], current_time: float) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Dönüş:
          ("EXECUTE_SLICE", slice_dict) -> Zamanı gelmiş parçayı yürüt
          ("PENDING_WAIT", None)        -> Kuyrukta zamanı bekleyen parçalar var
          ("HOLD", None)                -> Pasif / eşik altı
        """
        # 1. Kuyrukta bekleyen parça varsa bayat olanları temizle, zamanı geleni çıkar
        if self.pending_slices:
            self.pending_slices = [
                s for s in self.pending_slices
                if (current_time - s["execute_at"]) <= 600.0
            ]
        if self.pending_slices:
            self.pending_slices.sort(key=lambda s: s["execute_at"])
            if current_time >= self.pending_slices[0]["execute_at"]:
                return "EXECUTE_SLICE", self.pending_slices.pop(0)
            return "PENDING_WAIT", None

        # 2. İlk referans sepet fiyatlarını sabitle
        if self.initial_prices is None:
            self.initial_prices = dict(prices)
            self.last_eval_time = current_time
            span = self._roll_next_window(current_time)
            summary = " | ".join(f"{k}=${v:.4f}" if v < 10 else f"{k}=${v:.2f}" for k, v in prices.items())
            logger.info(f"[REFERANS SEPET] Başlangıç endeksi sabitlendi: {summary} (İlk kontrol: {span/60:.1f} dk sonra)")
            return "HOLD", None

        # 3. Değişken değerlendirme penceresi dolmadan yeni plan yapma
        if current_time < self.next_eval_at:
            return "HOLD", None

        self.last_eval_time = current_time
        next_span = self._roll_next_window(current_time)

        # 4. Kümülatif sepet değişimi & drift-free hedef etki hesabı
        cum_basket_pct = self.compute_cumulative_basket_pct(prices)
        target_cum_impact = cum_basket_pct * self.config["BETA_MULTIPLIER"]
        needed_impact = target_cum_impact - self.cumulative_executed_pct
        proposed_action = "BUY" if needed_impact > 0 else "SELL"

        # Eşdeğer ham sepet hareketi (asimetrik histerezis & barkod kırıcı kontrol)
        equiv_raw_delta = abs(needed_impact) / max(0.1, self.config["BETA_MULTIPLIER"])
        is_reversal = (self.last_direction is not None and proposed_action != self.last_direction)
        required_threshold = (
            self.config.get("REVERSE_DELTA_THRESHOLD_PCT", 0.55)
            if is_reversal
            else self.config["MIN_DELTA_THRESHOLD_PCT"]
        )

        # Yön kilidi aktifken ters yönde küçük salınımları yoksay (barkod / ping-pong engeli)
        if is_reversal and current_time < self.direction_lock_until:
            shock_pct = self.config.get("SHOCK_OVERRIDE_PCT", 1.25)
            if equiv_raw_delta < shock_pct:
                rem_min = max(0.1, (self.direction_lock_until - current_time) / 60.0)
                logger.info(
                    f"[YÖN KİLİDİ / ANTI-BARKOD] {self.last_direction} -> {proposed_action} bekletiliyor "
                    f"(Kalan: {rem_min:.1f} dk | Fark={equiv_raw_delta:.3f}% < Şok %{shock_pct} | Sonraki: {next_span/60:.1f} dk)"
                )
                return "HOLD", None

        if equiv_raw_delta < required_threshold:
            logger.info(
                f"[PASIF] Kontrol ({'Ters Yön' if is_reversal else 'Aynı Yön'}): Sepet={cum_basket_pct:+.3f}% | "
                f"Hedef={target_cum_impact:+.3f}% | Uygulanan={self.cumulative_executed_pct:+.3f}% | "
                f"Fark={equiv_raw_delta:.3f}% (<%{required_threshold}) | Sonraki: {next_span/60:.1f} dk"
            )
            return "HOLD", None

        # Kontrollü küçük jitter (±%12) + tavan koruması
        jitter = random.uniform(self.config["JITTER_MIN"], self.config["JITTER_MAX"])
        capped_impact = min(abs(needed_impact) * jitter, self.config["MAX_IMPACT_CAP_PCT"])
        signed_impact = capped_impact if needed_impact > 0 else -capped_impact

        # AMM Fiyat Etkisi Formülü: Delta_wBCT = (Impact% / 100) / 2 * Pool_wBCT_Reserve
        total_wbct = round((capped_impact / 100.0) / 2.0 * self.config["POOL_WBCT_RESERVE"], 2)
        total_usd = round(total_wbct * self.config["WBCT_UNIT_PRICE_USD"], 4)

        # Güvenlik: Tek pencere üst harcama sınırı
        max_usd = self.config["MAX_SINGLE_TRADE_USD"]
        if total_usd > max_usd:
            scale = max_usd / total_usd
            total_usd = round(max_usd, 4)
            total_wbct = round(total_wbct * scale, 2)
            signed_impact = signed_impact * scale

        if total_wbct < self.config["MIN_SLICE_WBCT"] or total_usd < self.config["MIN_SLICE_USD"]:
            return "HOLD", None

        action = "BUY" if signed_impact > 0 else "SELL"
        n_slices = self._choose_slice_count(equiv_raw_delta, total_wbct, total_usd)
        weights = self._random_weights(n_slices)
        # Her ağırlıklı parçanın gerçekte MIN_SLICE_WBCT ve MIN_SLICE_USD üstünde kalmasını garanti et
        while n_slices > 1 and any(
            round(total_wbct * w, 2) < self.config["MIN_SLICE_WBCT"]
            or round(total_usd * w, 4) < self.config["MIN_SLICE_USD"]
            for w in weights
        ):
            # Eşit bölme geçiyorsa eşit ağırlığa dön, geçmiyorsa parça sayısını 1 azalt
            eq_w = [1.0 / n_slices] * n_slices
            if all(
                round(total_wbct * w, 2) >= self.config["MIN_SLICE_WBCT"]
                and round(total_usd * w, 4) >= self.config["MIN_SLICE_USD"]
                for w in eq_w
            ):
                weights = eq_w
                break
            n_slices -= 1
            weights = self._random_weights(n_slices)

        # Pencere içine yayılmış rastgele yürütme zamanları (15s .. next_span-20s)
        window_span = max(90, min(int(next_span) - 15, self.config["WINDOW_SECONDS"]))
        slot_width = window_span / n_slices
        wallet_order = list(range(self.wallet_count))
        random.shuffle(wallet_order)

        self.pending_slices = []
        for i in range(n_slices):
            w = weights[i]
            s_wbct = round(total_wbct * w, 2)
            s_usd = round(total_usd * w, 4)
            s_impact = signed_impact * w
            low_delay = 10.0 + i * slot_width
            high_delay = min(float(window_span), (i + 1) * slot_width - 5.0)
            delay = random.uniform(low_delay, max(low_delay + 5.0, high_delay))
            self.pending_slices.append({
                "action": action,
                "wbct_amount": s_wbct,
                "usd_amount": s_usd,
                "signed_impact": s_impact,
                "preferred_wallet_idx": wallet_order[i % len(wallet_order)],
                "execute_at": current_time + delay,
                "delay": delay,
                "slice_no": i + 1,
                "slice_total": n_slices,
            })

        self.pending_slices.sort(key=lambda s: s["execute_at"])
        delays_str = ", ".join(f"#{s['slice_no']}:{s['delay']:.0f}s(${s['usd_amount']:.4f})" for s in self.pending_slices)
        logger.info(
            f"[PLANLANDI] Sepet={cum_basket_pct:+.2f}% (Beta {self.config['BETA_MULTIPLIER']}x) -> "
            f"{action} {total_wbct:.2f} wBCT (${total_usd:.4f}) | {n_slices} parça: [{delays_str}]"
        )
        return "PENDING_WAIT", None

    def commit_slice(self, slice_info: Dict[str, Any]):
        self.cumulative_executed_pct += float(slice_info["signed_impact"])
        action = str(slice_info.get("action") or "").upper()
        if action in ("BUY", "SELL"):
            now = time.time()
            lock_min = int(self.config.get("DIRECTION_LOCK_MIN_SECONDS", 1200))
            lock_max = int(self.config.get("DIRECTION_LOCK_MAX_SECONDS", 2400))
            if self.last_direction != action or now >= self.direction_lock_until:
                self.direction_lock_until = now + random.uniform(lock_min, max(lock_min + 60, lock_max))
            self.last_direction = action


class LiveOnChainExecutor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        if not HAS_WEB3:
            raise RuntimeError("web3 / eth_account / eth_abi paketleri kurulu değil.")

        self.w3 = Web3(
            Web3.HTTPProvider(
                self.config["RPC_URL"],
                request_kwargs={"headers": {"User-Agent": "Mozilla/5.0"}, "timeout": 15},
            )
        )

        raw_wallets = [
            ("Bot Alpha", os.getenv("BOT_KEY_1", "").strip(), os.getenv("BOT_ADDRESS_1", "").strip()),
            ("Bot Beta", os.getenv("BOT_KEY_2", "").strip(), os.getenv("BOT_ADDRESS_2", "").strip()),
            ("Bot Gamma", os.getenv("BOT_KEY_3", "").strip(), os.getenv("BOT_ADDRESS_3", "").strip()),
        ]
        self.wallets: List[Tuple[str, str, str]] = []
        for name, key, addr_hint in raw_wallets:
            if key:
                derived = Account.from_key(key).address
                if addr_hint and derived.lower() != addr_hint.lower():
                    logger.warning(f"[UYARI] {name} için BOT_ADDRESS ile private key türetimi uyuşmuyor; türetilen adres kullanılıyor.")
                self.wallets.append((name, key, derived))
            elif addr_hint:
                # Sadece bakiye okuma modu için salt-okunur adres
                self.wallets.append((name, "", _checksum(addr_hint)))

        self.last_wallet_idx = -1
        self.daily_tx_day = time.strftime("%Y-%m-%d", time.gmtime())
        self.daily_tx_count = 0

        self.pool_key = (
            self.config["USDC_ADDRESS"],
            self.config["WBCT_ADDRESS"],
            9000,
            90,
            _checksum("0x0000000000000000000000000000000000000000"),
        )
        self.usdc_contract = self.w3.eth.contract(address=self.config["USDC_ADDRESS"], abi=ERC20_BALANCE_ABI)
        self.wbct_contract = self.w3.eth.contract(address=self.config["WBCT_ADDRESS"], abi=ERC20_BALANCE_ABI)

    def get_wallet_balances(self) -> List[Dict[str, Any]]:
        eth_usd = PriceFeed.get_eth_price() or 0.0
        wbct_usd = self.config["WBCT_UNIT_PRICE_USD"]
        rows: List[Dict[str, Any]] = []
        for name, _key, address in self.wallets:
            eth_bal = float(self.w3.from_wei(self.w3.eth.get_balance(address), "ether"))
            usdc_bal = self.usdc_contract.functions.balanceOf(address).call() / 1e6
            wbct_bal = self.wbct_contract.functions.balanceOf(address).call() / 1e18
            rows.append({
                "name": name,
                "address": address,
                "eth": eth_bal,
                "eth_usd": eth_bal * eth_usd,
                "usdc": usdc_bal,
                "wbct": wbct_bal,
                "wbct_usd": wbct_bal * wbct_usd,
                "eth_price": eth_usd,
            })
        return rows

    def check_wallet_liquidity(self, address: str, action: str, req_wbct: float, req_usd: float) -> Tuple[bool, str]:
        try:
            eth_bal = float(self.w3.from_wei(self.w3.eth.get_balance(address), "ether"))
            if eth_bal < self.config["MIN_WALLET_ETH_GAS"]:
                return False, f"Yetersiz Gas: {eth_bal:.6f} ETH (Min: {self.config['MIN_WALLET_ETH_GAS']:.6f} ETH)"

            if action == "BUY":
                usdc_bal = self.usdc_contract.functions.balanceOf(address).call() / 1e6
                exact_req_usd = max(0.001, (req_wbct * self.config["WBCT_UNIT_PRICE_USD"]))
                if usdc_bal < exact_req_usd:
                    return False, f"Yetersiz USDC: ${usdc_bal:.4f} (Gereken: ${exact_req_usd:.4f})"
            elif action == "SELL":
                wbct_bal = self.wbct_contract.functions.balanceOf(address).call() / 1e18
                if wbct_bal < req_wbct:
                    return False, f"Yetersiz wBCT: {wbct_bal:.2f} wBCT (Gereken: {req_wbct:.2f} wBCT)"

            return True, "OK"
        except Exception as e:
            return False, f"Bakiye kontrol hatası: {type(e).__name__}"

    def build_v4_swap_calldata(self, action: str, wbct_amount: float, recipient: str) -> bytes:
        deadline = int(time.time()) + 1800

        if action == "BUY":
            usd_val = wbct_amount * self.config["WBCT_UNIT_PRICE_USD"]
            amount_in = max(1000, int(usd_val * 1e6))
            param0 = encode(["address", "uint256", "bool"], [self.config["USDC_ADDRESS"], amount_in, True])
            exact_input_params = (self.pool_key, True, amount_in, 0, 0, b"")
            param1 = encode(["((address,address,uint24,int24,address),bool,uint128,uint128,uint256,bytes)"], [exact_input_params])
            param2 = encode(["address", "address", "uint256"], [self.config["WBCT_ADDRESS"], recipient, 0])
        else:
            amount_in = int(wbct_amount * 1e18)
            param0 = encode(["address", "uint256", "bool"], [self.config["WBCT_ADDRESS"], amount_in, True])
            exact_input_params = (self.pool_key, False, amount_in, 0, 0, b"")
            param1 = encode(["((address,address,uint24,int24,address),bool,uint128,uint128,uint256,bytes)"], [exact_input_params])
            param2 = encode(["address", "address", "uint256"], [self.config["USDC_ADDRESS"], recipient, 0])

        actions = bytes.fromhex("0b060e")
        v4_swap_input = encode(["bytes", "bytes[]"], [actions, [param0, param1, param2]])
        commands = bytes.fromhex("10")
        exec_selector = bytes.fromhex("3593564c")
        exec_args = encode(["bytes", "bytes[]", "uint256"], [commands, [v4_swap_input], deadline])
        return exec_selector + exec_args

    def execute_live_order(self, slice_info: Dict[str, Any]) -> bool:
        action = slice_info["action"]
        wbct_amount = float(slice_info["wbct_amount"])
        usd_amount = float(slice_info["usd_amount"])
        preferred_idx = int(slice_info.get("preferred_wallet_idx", -1))

        # Güvenlik 1: Günlük işlem devre kesici
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if today != self.daily_tx_day:
            self.daily_tx_day = today
            self.daily_tx_count = 0
        if self.daily_tx_count >= self.config["MAX_DAILY_TXS"]:
            logger.warning(f"[DEVRE KESİCİ] Günlük maksimum işlem limitine ({self.config['MAX_DAILY_TXS']}) ulaşıldı.")
            return False

        # Güvenlik 2: Tek işlem USD tavanı
        if usd_amount <= 0 or usd_amount > self.config["MAX_SINGLE_TRADE_USD"]:
            logger.error(f"[GÜVENLİK ENGELİ] İşlem tutarı sınır dışı: ${usd_amount:.4f} (Tavan: ${self.config['MAX_SINGLE_TRADE_USD']})")
            return False

        signable = [(i, w) for i, w in enumerate(self.wallets) if w[1]]
        if not signable:
            logger.error("İmzalanabilir cüzdan anahtarı bulunamadı!")
            return False

        # Önce tercih edilen cüzdan, sonra diğerleri
        candidates: List[int] = []
        if 0 <= preferred_idx < len(self.wallets) and self.wallets[preferred_idx][1]:
            candidates.append(preferred_idx)
        others = [i for i, _ in signable if i not in candidates and i != self.last_wallet_idx]
        random.shuffle(others)
        candidates.extend(others)
        if self.last_wallet_idx >= 0 and self.last_wallet_idx not in candidates and self.wallets[self.last_wallet_idx][1]:
            candidates.append(self.last_wallet_idx)

        # Güvenlik 3: DRY_RUN gerçek koruması
        if self.config["DRY_RUN"]:
            idx = candidates[0]
            name, _k, addr = self.wallets[idx]
            logger.info(
                f"[DRY-RUN] >>> {name} ({addr[:6]}...{addr[-4:]}) | "
                f"Parça {slice_info['slice_no']}/{slice_info['slice_total']} | "
                f"{action} {wbct_amount:.2f} wBCT (${usd_amount:.4f})"
            )
            self.last_wallet_idx = idx
            self.daily_tx_count += 1
            return True

        # Güvenlik 4: Base Gas tavan koruması
        try:
            gas_price = self.w3.eth.gas_price
            gas_gwei = float(self.w3.from_wei(gas_price, "gwei"))
            if gas_gwei > self.config["MAX_GAS_GWEI"]:
                logger.warning(f"[GAS TAVANI] Base gas yüksek ({gas_gwei:.4f} gwei > {self.config['MAX_GAS_GWEI']} gwei); parça atlandı.")
                return False
        except Exception as e:
            logger.error(f"[RPC HATASI] Gas okunamadı: {type(e).__name__}")
            return False

        selected_idx = None
        for cand_idx in candidates:
            name, _key, address = self.wallets[cand_idx]
            has_funds, reason = self.check_wallet_liquidity(address, action, wbct_amount, usd_amount)
            if has_funds:
                selected_idx = cand_idx
                break
            logger.warning(f"[BAKİYE YETERSİZ - YEDEK CÜZDANA GEÇİLİYOR] {name} ({address[:6]}...{address[-4:]}): {reason}")

        if selected_idx is None:
            logger.error(f"[TÜM CÜZDANLAR YETERSİZ] {action} ({wbct_amount:.2f} wBCT / ${usd_amount:.4f}) yürütülemedi!")
            return False

        self.last_wallet_idx = selected_idx
        name, key, address = self.wallets[selected_idx]
        account = Account.from_key(key)

        try:
            calldata = self.build_v4_swap_calldata(action, wbct_amount, address)
            nonce = self.w3.eth.get_transaction_count(address, "pending")
            tx = {
                "from": address,
                "to": self.config["UNIVERSAL_ROUTER"],
                "data": calldata,
                "nonce": nonce,
                "gas": 240000,
                "gasPrice": gas_price,
                "chainId": self.config["CHAIN_ID"],
            }
            signed = account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info(
                f"[ON-CHAIN SWAP SENT] >>> {name} ({address[:6]}...{address[-4:]}) | "
                f"Parça {slice_info['slice_no']}/{slice_info['slice_total']} | "
                f"{action} ({wbct_amount:.2f} wBCT / ${usd_amount:.4f}) | Tx: 0x{tx_hash.hex()}"
            )
            rc = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=45)
            if rc.get("status") == 1:
                self.daily_tx_count += 1
                logger.info(
                    f"[AMM POOL SWAP SUCCESS] Block: {rc['blockNumber']} | Gas: {rc['gasUsed']} | Tx: 0x{tx_hash.hex()}"
                )
                return True
            logger.error(f"[AMM POOL SWAP REVERTED] Tx status 0: 0x{tx_hash.hex()}")
            return False
        except Exception as e:
            # Private key asla loglanmaz
            logger.error(f"[ON-CHAIN ERROR] {name} işlem hatası: {type(e).__name__}: {str(e)[:160]}")
            return False


def _rpc_call(rpc_url: str, method: str, params: list) -> Any:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    req = urllib.request.Request(
        rpc_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("result")


def _get_erc20_balance_rpc(rpc_url: str, token_addr: str, wallet_addr: str, decimals: int) -> float:
    padded = wallet_addr.lower().replace("0x", "").rjust(64, "0")
    call_data = "0x70a08231" + padded  # balanceOf(address)
    res = _rpc_call(rpc_url, "eth_call", [{"to": token_addr, "data": call_data}, "latest"])
    return int(res, 16) / (10 ** decimals) if res and res != "0x" else 0.0


def print_wallet_balances():
    rpc_url = CONFIG["RPC_URL"]
    raw_entries = [
        ("Bot Alpha", os.getenv("BOT_KEY_1", "").strip(), os.getenv("BOT_ADDRESS_1", "").strip()),
        ("Bot Beta", os.getenv("BOT_KEY_2", "").strip(), os.getenv("BOT_ADDRESS_2", "").strip()),
        ("Bot Gamma", os.getenv("BOT_KEY_3", "").strip(), os.getenv("BOT_ADDRESS_3", "").strip()),
    ]
    wallets: List[Tuple[str, str]] = []
    for name, key, addr_hint in raw_entries:
        addr = addr_hint
        if key and HAS_WEB3 and Account is not None:
            addr = Account.from_key(key).address
        if addr:
            wallets.append((name, addr))

    if not wallets:
        print("Hiç bot cüzdanı yapılandırılmamış (.env içinde BOT_ADDRESS_1..3 veya BOT_KEY_1..3 yok).")
        return

    eth_price = PriceFeed.get_eth_price() or 0.0
    print("\n" + "=" * 96)
    print(f"  LOCKTRACE wBCT BOT CÜZDAN BAKİYELERİ (Base Mainnet | ETH = ${eth_price:,.2f})")
    print("=" * 96)
    tot_eth = tot_eth_usd = tot_usdc = tot_wbct = 0.0
    for name, addr in wallets:
        eth_hex = _rpc_call(rpc_url, "eth_getBalance", [addr, "latest"])
        eth_bal = int(eth_hex, 16) / 1e18 if eth_hex else 0.0
        eth_usd = eth_bal * eth_price
        usdc_bal = _get_erc20_balance_rpc(rpc_url, CONFIG["USDC_ADDRESS"], addr, 6)
        wbct_bal = _get_erc20_balance_rpc(rpc_url, CONFIG["WBCT_ADDRESS"], addr, 18)

        tot_eth += eth_bal
        tot_eth_usd += eth_usd
        tot_usdc += usdc_bal
        tot_wbct += wbct_bal
        est_swaps = int(eth_usd / 0.002) if eth_usd > 0 else 0
        print(
            f"  {name:<10} | {addr} | "
            f"ETH: {eth_bal:.6f} (${eth_usd:.2f}, ~{est_swaps} swap) | "
            f"USDC: ${usdc_bal:.4f} | wBCT: {wbct_bal:.2f}"
        )
    print("-" * 96)
    est_days = round((tot_eth_usd / 0.002) / 160.0, 1) if tot_eth_usd > 0 else 0.0
    print(
        f"  {'TOPLAM':<10} | {'3 Cüzdan':<42} | "
        f"ETH: {tot_eth:.6f} (${tot_eth_usd:.2f}, ~{est_days} gün) | "
        f"USDC: ${tot_usdc:.4f} | wBCT: {tot_wbct:.2f}"
    )
    print("=" * 96 + "\n")


def run_live_loop():
    logger.info("=" * 72)
    logger.info("  LockTrace wBCT Market Maker v2.0 (BTC+ETH+XRP Sepet + Dinamik 1-3 Bölme)")
    logger.info(f"  Mod: {'DRY-RUN (Simülasyon)' if CONFIG['DRY_RUN'] else 'CANLI (Base Mainnet)'} | Beta: {CONFIG['BETA_MULTIPLIER']}x | Max Gas: {CONFIG['MAX_GAS_GWEI']} gwei")
    logger.info("=" * 72)

    executor = LiveOnChainExecutor(CONFIG)
    engine = BasketImpactEngine(CONFIG, wallet_count=len(executor.wallets))
    logger.info(f"Aktif bot cüzdanı: {len(executor.wallets)}")

    try:
        while True:
            now = time.time()
            prices = PriceFeed.get_basket_prices(CONFIG["BASKET_SYMBOLS"])
            if prices is not None:
                status, slice_info = engine.evaluate_market(prices, now)
                if status == "EXECUTE_SLICE" and slice_info is not None:
                    ok = executor.execute_live_order(slice_info)
                    if ok:
                        engine.commit_slice(slice_info)
            sleep_time = CONFIG["POLL_INTERVAL_SECONDS"] + random.uniform(-1.0, 2.0)
            time.sleep(max(3.0, sleep_time))
    except KeyboardInterrupt:
        logger.info("Bot durduruldu.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LockTrace wBCT Market Maker v2.0")
    parser.add_argument("--balances", action="store_true", help="Bot cüzdanlarının Base Mainnet bakiyelerini listele")
    args = parser.parse_args()
    if args.balances:
        print_wallet_balances()
    else:
        run_live_loop()
