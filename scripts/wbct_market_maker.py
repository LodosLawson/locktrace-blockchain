"""
LockTrace wBCT Live Market Maker & Trend Following Bot (Base Mainnet)
====================================================================
MATEMATİKSEL FİYAT ETKİSİ VE CANLI UNISWAP V4 AMM ENTEGRASYONU:
- Havuz: wBCT / USDC (%0.9 Fee, TickSpacing 90)
- PoolId: 0xf38d2770459e2c4b5fa14af657c8726f1e96242af36d75ba4db1e57a911a9139
- Uniswap V4 Universal Router: 0xd6145b2D3F379919E8CdEda7B97e37c4b2Ca9c40
- Formül: Delta_wBCT = (abs(Delta_ETH_Pct) / 100) / 2.0 * Pool_wBCT_Reserve
- Multi-Wallet Rotation: Alpha, Beta, Gamma cüzdanları arasında rotasyon.
- Random Jitter: 5 dk dolduktan sonra ilk 1-2 dk (10 - 110s) içinde rastgele yürütme.
- Eşik: %0.15 altındaki değişimlerde pasif (Sıfır spam, DEXScreener dostu).
- DEXScreener / GeckoTerminal üzerinde gerçek yeşil ve kırmızı mumlar oluşturur.
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

try:
    from web3 import Web3
    from eth_account import Account
    from eth_abi import encode
    HAS_WEB3 = True
except ImportError:
    Web3 = None
    Account = None
    encode = None
    HAS_WEB3 = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [wBCT-AMM]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("wBCT-AMM")

CONFIG = {
    "CHAIN_ID": 8453,
    "RPC_URL": os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
    
    # Sözleşme Adresleri
    "WBCT_ADDRESS": Web3.to_checksum_address("0xCa6152Ae0E785F90ED65cd706B386E5B83D0EB28") if Web3 else "0xCa6152Ae0E785F90ED65cd706B386E5B83D0EB28",
    "USDC_ADDRESS": Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913") if Web3 else "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "UNIVERSAL_ROUTER": Web3.to_checksum_address("0xd6145b2D3F379919E8CdEda7B97e37c4b2Ca9c40") if Web3 else "0xd6145b2D3F379919E8CdEda7B97e37c4b2Ca9c40",
    "POOL_ID": "0xf38d2770459e2c4b5fa14af657c8726f1e96242af36d75ba4db1e57a911a9139",
    
    # Canlı Havuz Rezervi Parametresi (wBCT)
    "POOL_WBCT_RESERVE": 2391.0,
    "WBCT_UNIT_PRICE_USD": 0.001048,

    # Zamanlama
    "POLL_INTERVAL_SECONDS": 10,
    "WINDOW_SECONDS": 300,          # 5 Dakika
    "EXECUTION_DELAY_MIN_SEC": 10,  # Minimum 10 sn gecikme
    "EXECUTION_DELAY_MAX_SEC": 110, # Maksimum 110 sn gecikme
    
    # Delta Eşikleri
    "MIN_DELTA_THRESHOLD_PCT": 0.15,# %0.15 altı pasif
    "MAX_DELTA_CAP_PCT": 2.00,      # Tavan: %2.00
    
    # Simülasyon / Canlı Mod
    "DRY_RUN": os.getenv("BOT_DRY_RUN", "false").lower() in ("true", "1", "yes"),
}

class PriceFeed:
    @staticmethod
    def get_eth_price() -> Optional[float]:
        try:
            url = "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    return float(data["price"])
        except Exception:
            pass
        return None

class ExactImpactEngine:
    """
    AMM Havuz Fiyat Etkisi Formülü ile çalışan Karar Motoru.
    ETH faizi/oranı kadar tam wBCT fiyat değişimi hesaplar.
    """
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

    def evaluate_market(self, current_price: float, current_time: float) -> Tuple[str, float, float, float]:
        """
        Dönüş: (ACTION, WBCT_MIKTARI, USD_DEGERI, DELTA_ORANI)
        """
        if self.pending_order is not None:
            if current_time >= self.pending_order["execute_at"]:
                order = self.pending_order
                self.pending_order = None
                return order["action"], order["wbct_amount"], order["usd_amount"], order["delta"]
            else:
                return "PENDING_WAIT", 0.0, 0.0, 0.0

        if len(self.history) < 2:
            return "HOLD", 0.0, 0.0, 0.0

        if self.last_action_price is None:
            self.last_action_price = self.history[0][1]
            logger.info(f"Ilk referans baz ETH fiyati: ${self.last_action_price:.2f}")
            return "HOLD", 0.0, 0.0, 0.0

        if self.last_action_time > 0 and (current_time - self.last_action_time) < self.config["WINDOW_SECONDS"]:
            return "HOLD", 0.0, 0.0, 0.0

        delta_pct = ((current_price - self.last_action_price) / self.last_action_price) * 100.0
        abs_delta = abs(delta_pct)

        # Kural: %0.15 altındaki değişimlerde pasif kal (Spam koruması)
        if abs_delta < self.config["MIN_DELTA_THRESHOLD_PCT"]:
            return "HOLD", 0.0, 0.0, delta_pct

        effective_delta = min(abs_delta, self.config["MAX_DELTA_CAP_PCT"])

        # ======================================================================
        # MATEMATİKSEL NOKTA ATIŞI FİYAT ETKİSİ HESAPLAMASI
        # wBCT Miktarı = (Delta_ETH_% / 100) / 2.0 * Havuz_Rezervi
        # ======================================================================
        target_wbct = round((effective_delta / 100.0) / 2.0 * self.config["POOL_WBCT_RESERVE"], 2)
        target_usd = round(target_wbct * self.config["WBCT_UNIT_PRICE_USD"], 4)

        # 5 Dakika Dolduktan Sonraki İlk 1-2 Dakika İçindeki Rastgele Zamanlama (Jitter)
        random_delay = random.uniform(
            self.config["EXECUTION_DELAY_MIN_SEC"], 
            self.config["EXECUTION_DELAY_MAX_SEC"]
        )
        execute_at_time = current_time + random_delay
        action = "BUY" if delta_pct > 0 else "SELL"

        self.pending_order = {
            "action": action,
            "wbct_amount": target_wbct,
            "usd_amount": target_usd,
            "delta": delta_pct,
            "execute_at": execute_at_time,
            "delay": random_delay
        }

        logger.info(
            f"[PLANLANDI] 5 Dk doldu! ETH: %{delta_pct:+.2f} degisti. "
            f"Havuzda tam %{delta_pct:+.2f} etki icin: {target_wbct:.2f} wBCT (${target_usd:.4f}) "
            f"planlandi. {random_delay:.1f} sn sonra yurutulecek."
        )
        return "PENDING_WAIT", 0.0, 0.0, delta_pct

    def commit_action(self, current_price: float, current_time: float):
        self.last_action_price = current_price
        self.last_action_time = current_time

class LiveOnChainExecutor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.w3 = Web3(Web3.HTTPProvider(self.config["RPC_URL"], request_kwargs={"headers": {"User-Agent": "Mozilla/5.0"}}))
        
        self.wallets = [
            ("Bot Alpha", os.getenv("BOT_KEY_1", "").strip()),
            ("Bot Beta", os.getenv("BOT_KEY_2", "").strip()),
            ("Bot Gamma", os.getenv("BOT_KEY_3", "").strip()),
        ]
        self.wallets = [(name, k) for name, k in self.wallets if k]
        self.last_wallet_idx = -1
        
        self.pool_key = (
            self.config["USDC_ADDRESS"],
            self.config["WBCT_ADDRESS"],
            9000,
            90,
            Web3.to_checksum_address("0x0000000000000000000000000000000000000000")
        )
        logger.info(f"Canli On-Chain Yonetici baslatildi: {len(self.wallets)} bot cuzdani aktif.")

    def build_v4_swap_calldata(self, action: str, wbct_amount: float, recipient: str) -> bytes:
        deadline = int(time.time()) + 1800
        
        if action == "BUY":
            # USDC -> wBCT
            usd_val = wbct_amount * self.config["WBCT_UNIT_PRICE_USD"]
            amount_in = max(1000, int(usd_val * 1e6)) # USDC 6 decimals, min 0.001 USDC
            
            # Action 0x0b (SETTLE): (currency, maxAmount, payerIsUser)
            param0 = encode(['address', 'uint256', 'bool'], [self.config["USDC_ADDRESS"], amount_in, True])
            
            # Action 0x06 (SWAP_EXACT_IN_SINGLE)
            exact_input_params = (
                self.pool_key,
                True,        # zeroForOne: USDC (0) -> wBCT (1)
                amount_in,   # amountIn
                0,           # amountOutMinimum
                0,           # flags
                b""          # hookData
            )
            param1 = encode(['((address,address,uint24,int24,address),bool,uint128,uint128,uint256,bytes)'], [exact_input_params])
            
            # Action 0x0e (TAKE): (currency, recipient, minAmount)
            param2 = encode(['address', 'address', 'uint256'], [self.config["WBCT_ADDRESS"], recipient, 0])
            
        else:
            # SELL: wBCT -> USDC
            amount_in = int(wbct_amount * 1e18) # wBCT 18 decimals
            
            # Action 0x0b (SETTLE): (currency, maxAmount, payerIsUser)
            param0 = encode(['address', 'uint256', 'bool'], [self.config["WBCT_ADDRESS"], amount_in, True])
            
            # Action 0x06 (SWAP_EXACT_IN_SINGLE)
            exact_input_params = (
                self.pool_key,
                False,       # zeroForOne: wBCT (1) -> USDC (0)
                amount_in,   # amountIn
                0,           # amountOutMinimum
                0,           # flags
                b""          # hookData
            )
            param1 = encode(['((address,address,uint24,int24,address),bool,uint128,uint128,uint256,bytes)'], [exact_input_params])
            
            # Action 0x0e (TAKE): (currency, recipient, minAmount)
            param2 = encode(['address', 'address', 'uint256'], [self.config["USDC_ADDRESS"], recipient, 0])

        actions = bytes.fromhex('0b060e')
        params = [param0, param1, param2]
        v4_swap_input = encode(['bytes', 'bytes[]'], [actions, params])
        
        commands = bytes.fromhex('10')
        inputs = [v4_swap_input]
        exec_selector = bytes.fromhex('3593564c') # execute(bytes,bytes[],uint256)
        exec_args = encode(['bytes', 'bytes[]', 'uint256'], [commands, inputs, deadline])
        return exec_selector + exec_args

    def execute_live_order(self, action: str, wbct_amount: float, usd_amount: float, eth_price: float):
        if not self.wallets:
            logger.error("Cüzdan anahtari bulunamadi!")
            return False

        # Multi-wallet rotasyonu: bir önceki cüzdandan farklı olanı seç
        candidates = [i for i in range(len(self.wallets)) if i != self.last_wallet_idx]
        idx = random.choice(candidates) if candidates else 0
        self.last_wallet_idx = idx
        
        name, key = self.wallets[idx]
        account = Account.from_key(key)

        try:
            calldata = self.build_v4_swap_calldata(action, wbct_amount, account.address)
            nonce = self.w3.eth.get_transaction_count(account.address, 'pending')
            gas_price = self.w3.eth.gas_price

            tx = {
                'from': account.address,
                'to': self.config["UNIVERSAL_ROUTER"],
                'data': calldata,
                'nonce': nonce,
                'gas': 240000,
                'gasPrice': gas_price,
                'chainId': self.config["CHAIN_ID"]
            }

            signed = account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info(
                f"[ON-CHAIN SWAP SENT] >>> {name} ({account.address[:6]}...{account.address[-4:]}) "
                f"| Islem: {action} ({wbct_amount:.2f} wBCT / ${usd_amount:.4f}) | Tx: 0x{tx_hash.hex()}"
            )
            
            # Receipt bekle (DEXScreener onayı)
            rc = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=45)
            if rc.get("status") == 1:
                logger.info(
                    f"[AMM POOL SWAP SUCCESS] Block: {rc['blockNumber']} | Gas: {rc['gasUsed']} | "
                    f"DEXScreener Mumu Basildi! Tx: 0x{tx_hash.hex()}"
                )
                return True
            else:
                logger.error(f"[AMM POOL SWAP REVERTED] Tx status 0: 0x{tx_hash.hex()}")
                return False

        except Exception as e:
            logger.error(f"[ON-CHAIN ERROR] {name} islem hatasi: {e}")
            return False

def run_live_loop():
    logger.info("=" * 65)
    logger.info("  LockTrace wBCT Market Maker (CANLI UNISWAP V4 AMM ENTEGRASYONU)")
    logger.info("=" * 65)

    engine = ExactImpactEngine(CONFIG)
    executor = LiveOnChainExecutor(CONFIG)

    try:
        while True:
            now = time.time()
            eth_price = PriceFeed.get_eth_price()

            if eth_price is not None:
                engine.record_price(eth_price, now)
                action, wbct_amt, usd_amt, delta = engine.evaluate_market(eth_price, now)

                if action in ("BUY", "SELL"):
                    logger.info(f"[TETIKLENDI] ETH %{delta:+.2f} degisti! Uniswap V4 havuzunda canli takas yapiliyor...")
                    success = executor.execute_live_order(action, wbct_amt, usd_amt, eth_price)
                    if success:
                        engine.commit_action(eth_price, now)
                elif action == "PENDING_WAIT":
                    pass
                else:
                    ref_p = engine.last_action_price or eth_price
                    logger.debug(f"[PASIF] ETH: ${eth_price:.2f} | Baz: ${ref_p:.2f} | Delta: %{delta:.2f}")

            sleep_time = CONFIG["POLL_INTERVAL_SECONDS"] + random.uniform(-1.0, 2.0)
            time.sleep(max(3.0, sleep_time))

    except KeyboardInterrupt:
        logger.info("Bot durduruldu.")

if __name__ == "__main__":
    run_live_loop()
