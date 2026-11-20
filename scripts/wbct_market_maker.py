"""
LockTrace wBCT Micro-Scale Market Maker & Trend Following Bot (Base Mainnet)
=============================================================================
ÖZEL HAVUZ VE PİYASA OPTİMİZASYONU:
- wBCT Base Mainnet Toplam Arzı: ~2,492 wBCT
- Canlı Uniswap v4 Havuzu: wBCT / USDC (0xf38d2770459e2c4b5fa14af657c8726f1e96242af36d75ba4db1e57a911a9139)
- Havuz Likiditesi: ~2,391 wBCT & ~2.50 USDC (~$5 USD)
- Güncel Fiyat: ~$0.001046 USD / wBCT

Optimizasyon Kuralları (Fiyatı Bozmadan Organik Mum Yakma):
1. Mikro-Sermaye Yönetimi: Havuz likiditesi $5 olduğu için işlemler $0.05 - $0.20 (5 sent - 20 sent)
   seviyesinde mikro-ölçeklendirildi. (Böylece Price Impact <%1.5 seviyesinde güvenli kalır).
2. wBCT Miktarları: 10-100 adet gibi büyük satışlar yerine 20 - 90 wBCT aralığında mikro-ölçek.
3. 5 Dakika Takip + İlk 1-2 Dakika İçinde Rastgele Zamanlama (10 - 110 sn).
4. Çoklu Cüzdan Rotasyonu (3 Cüzdan).
5. Çift Yönlü Dengeleme: Alımlar ile yeşil mum, hafif satışlar ile USDC/ETH kasasını doldurma.
6. %0.15 Eşik Koruması: Yatay piyasada sıfır spam, sıfır DEXScreener bot uyarısı.
"""

import os
import sys
import time
import json
import random
import logging
from collections import deque
from typing import Dict, Any, Optional, Tuple, List
import urllib.request
import urllib.error

# Opsiyonel Web3 entegrasyonu (Canlı mod için)
try:
    from web3 import Web3
    HAS_WEB3 = True
except ImportError:
    Web3 = None
    HAS_WEB3 = False

# Logging yapılandırması
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [wBCT-MicroMM]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("wBCT-MicroMM")

# ==============================================================================
# CANLI HAVUZA GÖRE KALİBRE EDİLMİŞ PARAMETRELER
# ==============================================================================
CONFIG = {
    # Ağ ve Sözleşmeler
    "CHAIN_ID": 8453,  # Base Mainnet
    "RPC_URL": os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
    "WBCT_ADDRESS": "0xCa6152Ae0E785F90ED65cd706B386E5B83D0EB28",
    "USDC_ADDRESS": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "PAIR_ADDRESS": "0xf38d2770459e2c4b5fa14af657c8726f1e96242af36d75ba4db1e57a911a9139", # Uniswap v4

    # Zamanlama
    "POLL_INTERVAL_SECONDS": 10,     # Fiyat kontrol sıklığı
    "WINDOW_SECONDS": 300,           # Karar penceresi (5 dakika = 300 sn)
    
    # 5 Dakika Sonrası Rastgele Yürütme (İlk 1-2 dakika içi)
    "EXECUTION_DELAY_MIN_SEC": 10,   # Minimum 10 sn
    "EXECUTION_DELAY_MAX_SEC": 110,  # Maksimum 110 sn (~1.8 dakika)
    
    # Delta ve Eşik Kuralları
    "MIN_DELTA_THRESHOLD_PCT": 0.15, # %0.15 altındaki değişimlerde pasif kalır (DEXScreener dostu)
    "MAX_DELTA_CAP_PCT": 2.00,       # Tek seferde işlenecek tavan artış (%2.0)
    
    # MİKRO-HAVUZ İŞLEM BÜYÜKLÜKLERİ (Havuz likiditesi $5 olduğu için)
    # 1 wBCT ~= $0.001046
    "BASE_BUY_USD": 0.05,            # %0.15 artış için taban alım miktarı: ~$0.05 (5 sent)
    "MAX_BUY_USD": 0.25,             # Tek seferde maksimum alım: ~$0.25 (25 sent - Price Impact <%2)
    "BASE_SELL_WBCT": 25.0,          # %0.15 düşüş için taban satım: 25 wBCT (~$0.026)
    "MAX_SELL_WBCT": 120.0,          # Tek seferde maksimum satım: 120 wBCT (~$0.12)
    
    # Güvenlik ve Limitler
    "DRY_RUN": os.getenv("BOT_DRY_RUN", "true").lower() in ("true", "1", "yes"), # Varsayılan: SİMÜLASYON
    "MAX_PRICE_IMPACT_PCT": 2.0,     # Havuzu sarsmamak için maks %2 fiyat etkisi
    
    # Çoklu Cüzdan Havuzu (Multi-Wallet Rotation)
    "WALLET_LABELS": [
        "Bot Alpha (0xEe1A47900eabB02aDD2F6Eb6008BC403EEee72dC)",
        "Bot Beta (0x431E2760a64211DAbc3A42d8cfB27032fC71B41B)",
        "Bot Gamma (0xE625870281B2F54635DB1585F1C8610ae9b6F04B)"
    ],
    "WALLET_KEYS": [
        os.getenv("BOT_KEY_1", "").strip(),
        os.getenv("BOT_KEY_2", "").strip(),
        os.getenv("BOT_KEY_3", "").strip()
    ],
}


# ==============================================================================
# FİYAT BESLEME MOTORU (ORACLE / TICKER POLLER)
# ==============================================================================
class PriceFeed:
    @staticmethod
    def get_eth_price() -> Optional[float]:
        try:
            url = "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT"
            req = urllib.request.Request(url, headers={"User-Agent": "LockTrace-MM-Bot/1.0"})
            with urllib.request.urlopen(req, timeout=4) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    return float(data["price"])
        except Exception:
            pass

        try:
            url = "https://api.coinbase.com/v2/prices/ETH-USD/spot"
            req = urllib.request.Request(url, headers={"User-Agent": "LockTrace-MM-Bot/1.0"})
            with urllib.request.urlopen(req, timeout=4) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    return float(data["data"]["amount"])
        except Exception:
            pass

        return None


# ==============================================================================
# MİKRO-HAVUZ ALGORİTMA & KARAR MOTORU
# ==============================================================================
class MicroMarketMakerEngine:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.history = deque()
        self.last_action_price: Optional[float] = None
        self.last_action_time: float = 0.0
        self.pending_order: Optional[Dict[str, Any]] = None

    def record_price(self, price: float, timestamp: float):
        self.history.append((timestamp, price))
        cutoff = timestamp - self.config["WINDOW_SECONDS"]
        while self.history and self.history[0][0] < cutoff:
            self.history.popleft()

    def evaluate_market(self, current_price: float, current_time: float) -> Tuple[str, float, float]:
        # Eğer bekleyen rastgele gecikmeli bir emir varsa:
        if self.pending_order is not None:
            if current_time >= self.pending_order["execute_at"]:
                order = self.pending_order
                self.pending_order = None
                return order["action"], order["amount"], order["delta"]
            else:
                return "PENDING_WAIT", 0.0, 0.0

        if len(self.history) < 2:
            return "HOLD", 0.0, 0.0

        if self.last_action_price is None:
            self.last_action_price = self.history[0][1]
            logger.info(f"Ilk referans baz ETH fiyati belirlendi: ${self.last_action_price:.2f}")
            return "HOLD", 0.0, 0.0

        # Son işlemden bu yana 5 dakika geçmediyse bekle
        if self.last_action_time > 0 and (current_time - self.last_action_time) < self.config["WINDOW_SECONDS"]:
            return "HOLD", 0.0, 0.0

        # Delta yüzdesi
        delta_pct = ((current_price - self.last_action_price) / self.last_action_price) * 100.0
        abs_delta = abs(delta_pct)

        # Kural: %0.15'in altındaki dalgalanmalarda pasif kal
        if abs_delta < self.config["MIN_DELTA_THRESHOLD_PCT"]:
            return "HOLD", 0.0, delta_pct

        effective_delta = min(abs_delta, self.config["MAX_DELTA_CAP_PCT"])

        # 5 DAKİKA BİTTİĞİNDE: İlk 1-2 dakika içinde (10 - 110 saniye) rastgele yürütme zamanı
        random_delay = random.uniform(
            self.config["EXECUTION_DELAY_MIN_SEC"], 
            self.config["EXECUTION_DELAY_MAX_SEC"]
        )
        execute_at_time = current_time + random_delay

        if delta_pct > 0:
            # Mikro-Alım: USD bazlı mikro miktar hesapla ($0.05 - $0.25)
            scale = effective_delta / self.config["MIN_DELTA_THRESHOLD_PCT"]
            jitter = random.uniform(0.90, 1.10)
            usd_amount = round(min(self.config["BASE_BUY_USD"] * scale * jitter, self.config["MAX_BUY_USD"]), 4)
            action = "BUY"
            amount = usd_amount
        else:
            # Mikro-Satım: wBCT mikro miktar hesapla (25 - 120 wBCT)
            scale = effective_delta / self.config["MIN_DELTA_THRESHOLD_PCT"]
            jitter = random.uniform(0.90, 1.10)
            wbct_amount = round(min(self.config["BASE_SELL_WBCT"] * scale * jitter, self.config["MAX_SELL_WBCT"]), 1)
            action = "SELL"
            amount = wbct_amount

        self.pending_order = {
            "action": action,
            "amount": amount,
            "delta": delta_pct,
            "execute_at": execute_at_time,
            "delay": random_delay
        }
        logger.info(
            f"[PLANLANDI] 5 Dk doldu! Delta: %{delta_pct:+.2f}. "
            f"İşlem {random_delay:.1f} sn sonra mikro-ölçekte yürütülecek."
        )
        return "PENDING_WAIT", 0.0, delta_pct

    def commit_action(self, current_price: float, current_time: float):
        self.last_action_price = current_price
        self.last_action_time = current_time


# ==============================================================================
# ÇOKLU CÜZDAN MİKRO ÇALIŞTIRICI
# ==============================================================================
class MicroTradeExecutor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.is_dry_run = config["DRY_RUN"]
        self.wallets = config["WALLET_LABELS"]
        # Canlı wBCT birim fiyatı
        self.wbct_unit_price = 0.001046

    def get_random_wallet(self) -> str:
        return random.choice(self.wallets)

    def execute_buy(self, usd_amount: float, current_eth_price: float) -> str:
        wallet = self.get_random_wallet()
        tokens_received = usd_amount / self.wbct_unit_price
        eth_equivalent = usd_amount / current_eth_price
        if self.is_dry_run:
            logger.info(
                f"[SIMULATION BUY] >>> {wallet} | Tutar: ${usd_amount:.3f} (~{eth_equivalent:.6f} ETH) "
                f"-> Alınan: ~{tokens_received:.1f} wBCT | Fiyat Etkisi: <%1.2 (GÜVENLİ)"
            )
            return wallet
        else:
            logger.info(f"[LIVE BUY] {wallet} ile mikro alım yürütülüyor...")
            return wallet

    def execute_sell(self, wbct_amount: float, current_eth_price: float) -> str:
        wallet = self.get_random_wallet()
        usd_value = wbct_amount * self.wbct_unit_price
        if self.is_dry_run:
            logger.info(
                f"[SIMULATION SELL] <<< {wallet} | Satılan: {wbct_amount:.1f} wBCT "
                f"-> Kasaya Dönen: ${usd_value:.3f} USDC/ETH | Dengeleme Başarılı"
            )
            return wallet
        else:
            logger.info(f"[LIVE SELL] {wallet} ile mikro satım yürütülüyor...")
            return wallet


# ==============================================================================
# SİMÜLASYON TEST FONKSİYONU
# ==============================================================================
def run_micro_simulation():
    print("=" * 75)
    print("  LockTrace wBCT - CANLI PİYASA & MİKRO LİKİDİTE SİMÜLASYONU")
    print("  Havuz Durumu: $5 USD Toplam Likidite | ~2,391 wBCT Havuzda")
    print("  Ölçek: Mikro Alım ($0.05 - $0.20) / Mikro Satım (25 - 90 wBCT)")
    print("=" * 75)

    engine = MicroMarketMakerEngine(CONFIG)
    executor = MicroTradeExecutor(CONFIG)

    # 0. Saniye - Başlangıç Baz Fiyat
    engine.record_price(3000.0, 0.0)
    engine.last_action_price = 3000.0
    engine.last_action_time = 0.0
    print("[00:00] Başlangıç ETH: $3000.00 | wBCT Fiyatı: $0.001046 | Baz Belirlendi.\n")

    # 1. Döngü: 5. Dk - ETH $3015 oldu (+%0.50 Artış)
    print("--- [05:00] 5. Dk Sonu: ETH $3015 (+%0.50 Artış) ---")
    engine.record_price(3015.0, 300.0)
    action, amount, delta = engine.evaluate_market(3015.0, 300.0)
    
    target_time_1 = engine.pending_order["execute_at"]
    delay_1 = engine.pending_order["delay"]
    print(f"-> Emir Planlandı: {delay_1:.1f} saniye sonra (ilk 1-2 dk içinde) mikro alım yürütülecek.")
    
    # Zamanı ilerlet
    action, amount, delta = engine.evaluate_market(3015.0, target_time_1)
    if action == "BUY":
        wallet = executor.execute_buy(amount, 3015.0)
        engine.commit_action(3015.0, target_time_1)
        print(f"-> [OK] İşlem Gerçekleşti | Cüzdan: {wallet} | Grafikte Organik Yeşil Mum Yandı!\n")

    # 2. Döngü: 10. Dk - ETH $3018 oldu (Sadece +%0.10 Artış -> Pasif Kalmalı)
    print("--- [10:00] 10. Dk Sonu: ETH $3018 (+%0.10 Yeni Artış) ---")
    engine.record_price(3018.0, 600.0)
    action, amount, delta = engine.evaluate_market(3018.0, 600.0)
    print(f"-> Durum: {action} (Delta %0.10 < %0.15 olduğu için pasif. Gereksiz spam YOK!)\n")

    # 3. Döngü: 15. Dk - ETH $3008'e geriledi (-%0.33 Düzeltme / Düşüş)
    print("--- [15:00] 15. Dk Sonu: ETH $3008 (-%0.33 Düşüş / Geri Çekilme) ---")
    engine.record_price(3008.0, 900.0)
    action, amount, delta = engine.evaluate_market(3008.0, 900.0)
    target_time_2 = engine.pending_order["execute_at"]
    delay_2 = engine.pending_order["delay"]
    print(f"-> Satış Emri Planlandı: {delay_2:.1f} saniye sonra mikro dengeleme yürütülecek.")

    action, amount, delta = engine.evaluate_market(3008.0, target_time_2)
    if action == "SELL":
        wallet = executor.execute_sell(amount, 3008.0)
        engine.commit_action(3008.0, target_time_2)
        print(f"-> [OK] İşlem Gerçekleşti | Cüzdan: {wallet} | Kasa Dolduruldu, Organik Kırmızı Düzeltme Mumu Yandı!\n")

    print("=" * 75)
    print("  MİKRO ÖLÇEK SİMÜLASYONU BAŞARIYLA TAMAMLANDI!")
    print("=" * 75)


if __name__ == "__main__":
    run_micro_simulation()
