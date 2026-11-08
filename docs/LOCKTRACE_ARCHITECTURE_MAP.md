# 🗺️ LockTrace (BCT) — Yazılım Haritası, Sınıflar, Fonksiyonlar ve İletişim Mimarisi

> 💡 **Bu Sayfanın Amacı:**  
> LockTrace Layer-1 blokzincirinin tüm kaynak kod haritasını sunar. Hangi dosyanın ne işe yaradığını, içindeki sınıfları (`Classes`), bu sınıfların fonksiyonlarını (`Functions`), fonksiyonların parametrelerini ve birbirleriyle olan veri alışverişini (Call Graph & Inter-Service Data Flow) detaylandırır.

---

## 🏛️ 1. Mimari Katmanlar ve Uçtan Uca İletişim Akışı (Architecture Data Flow)

Bir kullanıcı arayüzden herhangi bir işlem (Örn: BCT Transferi, .bct Alan Adı Alımı, Sosyal Gönderi Paylaşımı veya Teklif Verme) yaptığında sistem şu sıra ile haberleşir:

```
[İstemci / Tarayıcı (Web3 PWA)]
    │  1. BIP-39 ile 12 kelimeden Private Key türetilir (mnemonic.py mantığı JS'de çalışır)
    │  2. İşlem verisi oluşturulur ve SECP256k1 ile istemcide imzalanır (Non-Custodial)
    ▼
[API Sunucusu (server.py)]
    │  3. Rate Limiter (SlidingWindowRateLimiter) ile IP ve imza kontrolü yapılır
    │  4. ECDSA İmzası ve adres formatı doğrulanır (_verify_actor_signature / verify_signature)
    │  5. İşlem doğrulanırsa Blockchain mempool havuzuna eklenir
    ▼
[Çekirdek Motor (core/blockchain.py)]
    │  6. Bakiye kontrolü, Hazine payı (%50 veya %80) ve Madenci payı (%50 veya %20) hesaplanır
    │  7. Batching Sequencer (Zaman veya Kota dolunca) PoW madenciliğini tetikler
    │  8. Merkle Tree kökü (compute_merkle_root) ve blok hash'i hesaplanır (Block.mine)
    ▼
[Kalıcı Depolama (core/storage.py)]
    │  9. SQLiteStorage motoru WAL modunda blokları, işlemleri ve durum (state) tablolarını günceller
    ▼
[P2P Dağıtım & Doğrulayıcı Ağı (node_runner.py)]
    │ 10. Yeni blok P2P eşlerine duyurulur, LockTraceNode eşleri bloğu bağımsız doğrular
    │ 11. BFT Quorum eşiği (%30) sağlandığında blok kesinleşir (Finality)
    ▼
[Bildirim Servisi (core/push_service.py)]
    │ 12. Alıcı cüzdana veya etiketlenen (#handle.bct) kişiye VAPID Web Push bildirimi yollanır
```

---

## 📦 2. Sınıf ve Fonksiyon Detay Haritası (Class & Function Index)

### 🔹 Modül 1: `core/blockchain.py` (Blokzincir Çekirdeği)
Sistemin en büyük ve en kritik modülüdür. Blok üretimi, madencilik, deflasyonist ekonomi, BNS alan adları, Escrow teklifleri ve sosyal ağ kuralları burada tanımlıdır.

#### Sınıf: `Transaction`
- `__init__(sender, recipient, amount, fee, signature, tx_type, payload)`: Yeni bir işlem nesnesi başlatır.
- `to_dict()`: İşlemi JSON/sözlük formatına çevirir (Hash hesaplaması için standart sıra).
- `hash()`: SHA-256 ile benzersiz işlem kimliği üretir.

#### Sınıf: `Block`
- `__init__(index, timestamp, transactions, previous_hash, nonce, difficulty, merkle_root, quorum_signatures)`: Blok yapısını başlatır.
- `calculate_hash()`: Blok başlıklarını (Header) SHA-256 ile hash'ler.
- `mine(target_difficulty)`: PoW döngüsünü çalıştırır; hash belirlenen sıfır adediyle (`0000...`) başlayana kadar `nonce` artırır.
- `to_dict()`: Blok verilerini sözlük olarak döndürür.

#### Sınıf: `Blockchain` (Ana Yönetici - 80 Metot)
1. **Çekirdek & Blok Yönetimi:**
   - `_create_genesis_block()`: 1 Trilyon BCT sabit arzlı Blok #0'ı üretir.
   - `add_block(block)`: Yeni kazılmış bloğu zincire ekler, bakiyeleri ve state tablolarını günceller.
   - `mine_pending_transactions(miner_address)`: Mempool'daki işlemleri toplayıp yeni blok kazar.
   - `is_chain_valid()`: Zincirin baştan sona SHA-256 ve Merkle bütünlüğünü doğrular.
   - `resolve_conflicts(neighbors)`: En uzun geçerli zincir (Longest Valid Chain) kuralını uygular.
2. **Ekonomik Kurallar & Bakiyeler:**
   - `get_balance(address)`: Cüzdanın harcanabilir net BCT bakiyesini döndürür.
   - `verify_and_recalc_balance(address)`: Tüm geçmiş işlemleri toplayarak bakiyeyi kesin doğrular.
   - `get_welcome_grant(address)`: Yeni cüzdana Hazine'den 1 BCT hibe tanımlar (Sybil korumalı).
   - `_calculate_tx_fees(amount, tx_type)`: %1 işlem ücretini hesaplar; %50'sini Hazine kasasına kilitler, %50'sini madenci/doğrulayıcıya ayırır.
3. **BNS (.bct Alan Adı Sistemi & Pazar Yeri):**
   - `register_bns_handle(handle, owner, signature)`: Yeni alan adı kaydı açar; ödenen tutarın **%80'ini Hazineye geri döndürür, %20'sini madencilere** verir.
   - `list_bns_for_sale(handle, price, seller_sig)`: Alan adını pazar yerinde sabit fiyata satışa çıkarır.
   - `buy_bns_handle(handle, buyer, signature)`: Pazar yerinden alan adını satın alır (%2 protokol komisyonu).
   - `create_bns_offer(handle, buyer, offer_amount, signature)`: Satışta olsun/olmasın isme **Non-Custodial Escrow teklifi** verir; para kilitlenir.
   - `accept_bns_offer(handle, offer_id, owner_sig)`: Teklifi kabul eder; kilitli para satıcıya, isim alıcıya geçer.
   - `cancel_bns_offer(handle, offer_id, buyer_sig)`: Teklifi iptal eder; kilitli BCT teklif sahibine anında iade edilir.
   - `get_bns_sales_history()` & `get_bns_analytics()`: Tüm el değiştirmelerin geçmiş kaydını ve fiyat grafiğini sunar.
4. **LockTrace Space (Sosyal Ağ Modülü):**
   - `create_space_post(author, content, signature)`: 0.05 BCT karşılığı kalıcı on-chain gönderi yazar.
   - `like_space_post(post_id, sender_address, signature)`: 0.003 BCT'lik beğeninin **+0.002 BCT'sini içerik sahibine telif olarak öder**.
   - `comment_space_post(post_id, author, text, signature)`: 0.02 BCT'lik yorumun **+0.005 BCT'sini içerik sahibine telif olarak aktarır**.
   - `tip_space_author(post_id, sender, amount, signature)`: %0 komisyonla doğrudan bahşiş transferi yapar.

---

### 🔹 Modül 2: `core/storage.py` (Kalıcı Veritabanı Katmanı)
Blokzincir durumunu JSON dosyaları yerine atomik, yüksek hızlı SQLite Write-Ahead Logging (WAL) ile saklar.

#### Sınıf: `SQLiteStorage`
- `_init_schema()`: `blocks`, `transactions`, `bns_handles`, `bns_offers`, `space_posts`, `space_likes` tablolarını ve indekslerini oluşturur.
- `save_state(blocks, mempool, bns_state, space_state)`: Tüm durumu tek bir SQLite transaction (commit/rollback) içinde diske kaydeder.
- `load_full_state()`: Sunucu yeniden başladığında en son blok ve durum bilgilerini diske hızla yükler.
- `get_block_count()`: Zincir boyunu mikrosaniyede sorgular.

---

### 🔹 Modül 3: `core/wallet.py` & `core/mnemonic.py` (Kriptografi & Anahtar Yönetimi)

#### Sınıf: `Wallet`
- `__init__(private_key)`: SECP256k1 eğrisi üzerinde anahtar çifti oluşturur.
- `_generate_address()`: Public key'i SHA-256 + RIPEMD-160 ile hash'leyip `BCT...` adresine dönüştürür.
- `sign(message_bytes)`: İşlem verisini SECP256k1 ECDSA ile imzalar.
- `verify_signature(public_key, signature, message)`: İmzayı matematiksel olarak doğrular.

#### Fonksiyonlar (`core/mnemonic.py`):
- `generate_mnemonic(strength=128)`: BIP-39 kelime listesinden 12 kelimelik rastgele tohum cümlesi üretir.
- `mnemonic_to_private_key(mnemonic, passphrase)`: PBKDF2-HMAC-SHA512 ile 256-bit deterministik özel anahtar üretir.
- `validate_mnemonic(mnemonic)`: Kelimelerin geçerliliğini ve sağlama toplamını (checksum) test eder.

---

### 🔹 Modül 4: `core/bridge.py` & `core/bridge_relayer.py` (Base L2 Çapraz Zincir Köprüsü)

#### Sınıf: `BridgeManager`
- `create_bridge_order(l1_sender, evm_recipient, amount)`: L1 -> Base köprü emri oluşturur.
- `confirm_l1_lock(order_id)`: BCT'lerin `BCT_BRIDGE_VAULT` kasasına kilitlendiğini doğrular.

#### Sınıf: `BridgeRelayer` (7/24 Arka Plan Servisi)
- `process_pending_locks()`: Kilitlenen emirleri okur ve Base Mainnet üzerindeki `wBCT` ERC-20 kontratında (`0xA3C743...`) `mint()` işlemini çağırır.
- `process_pending_burns()`: Base üzerinde yakılan wBCT fişlerini doğrular ve L1 kasasından BCT'leri serbest bırakır (`unlock`).

---

### 🔹 Modül 5: `core/push_service.py` (VAPID Web Push Bildirim Motoru)

#### Sınıf: `PushNotificationService`
- `_init_vapid_keys()`: RFC-8292 standardında VAPID ECDSA anahtarlarını yönetir.
- `subscribe(wallet_address, subscription_info)`: iOS/Android/Masaüstü PWA tarayıcı abonelik token'larını SQLite veritabanına kaydeder.
- `send_push_to_wallet(wallet_address, title, body, url)`: Kullanıcı sitede olmasa bile telefonuna kilit ekranı bildirimi gönderir.

---

### 🔹 Modül 6: `server.py` (Flask REST API & Hibrit Batching Sequencer)

#### Sınıf: `SlidingWindowRateLimiter`
- `allow(client_ip, limit, window_seconds)`: DDoS ve spam saldırılarına karşı IP bazlı kayan pencere sınırlandırması uygular.
- `register_signature_once(sig)`: Tekrar oynatma saldırılarını (Replay Attack) engellemek için aynı imzanın iki kez işlenmesini önler.

#### Temel API Rotaları ve Çağrı Haritası:
- `POST /api/v1/transaction/new` ➔ `Blockchain.add_transaction()` ➔ Mempool
- `POST /api/v1/bns/register` ➔ `Blockchain.register_bns_handle()` ➔ %80 Hazine, %20 Madenci
- `POST /api/v1/bns/offer` ➔ `Blockchain.create_bns_offer()` ➔ Escrow Kilit
- `POST /api/v1/space/post` ➔ `Blockchain.create_space_post()` ➔ On-chain Kayıt
- `POST /api/v1/space/like` ➔ `Blockchain.like_space_post()` ➔ Telif + Batching Havuzu
- `GET /api/v1/chain` & `/api/v1/block/<id>` ➔ SQLiteStorage Blok Sorgusu
- `GET /api/v1/frontend/integrity` ➔ Kriptografik SHA-256 on-chain mühür kontrolü

---

### 🔹 Modül 7: `node_runner.py` (Bağımsız Doğrulayıcı & Madenci Node)

#### Sınıf: `LockTraceNode`
- `__init__(port, miner_wallet, public_endpoint)`: Düğüm kimliğini ve RPC sunucusunu başlatır.
- `_sync_chain()`: Ana ağdan (`locktrace.space`) yeni blokları indirir ve yerel SQLite'a işler.
- `start_mining()`: Boş işlemcide PoW hash döngüsü çalıştırır; blok bulursa ana ağa duyurur.
- `sign_quorum_block(block_hash)`: Yeni bloklar için BFT Quorum imzasını üretip ağa iletir (%30 ödül payı kazanır).
