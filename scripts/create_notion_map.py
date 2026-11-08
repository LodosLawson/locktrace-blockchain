import os
import sys
import json
import urllib.request
import urllib.error

NOTION_VERSION = "2022-06-28"
PARENT_PAGE_ID = "41234084-c76e-80de-b266-f1c404ba05d8"

def get_notion_token():
    token = os.environ.get("NOTION_TOKEN")
    if token:
        return token
    cfg_paths = [
        os.path.expanduser("~/.gemini/config/mcp_config.json"),
        os.path.expanduser("~/.gemini/config/plugins/notion/mcp_config.json"),
        r"C:\Users\mehem\.gemini\config\mcp_config.json"
    ]
    for p in cfg_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    auth = data.get("mcpServers", {}).get("notion", {}).get("headers", {}).get("Authorization", "")
                    if auth.startswith("Bearer "):
                        return auth[7:].strip()
            except Exception:
                pass
    return None

def notion_api(endpoint, method="GET", data=None):
    token = get_notion_token()
    if not token:
        print("[!] Error: NOTION_TOKEN not found in environment or mcp_config.json")
        return None
    url = f"https://api.notion.com/v1/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")
        print(f"[!] Notion API HTTP {e.code} Error: {err}")
        return None
    except Exception as e:
        print(f"[!] Notion API Exception: {e}")
        return None

def text_block(content):
    return {
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": content[:1950]}}]
        }
    }

def heading_block(level, content):
    h_type = f"heading_{level}"
    return {
        "type": h_type,
        h_type: {
            "rich_text": [{"type": "text", "text": {"content": content[:1950]}}]
        }
    }

def code_block(content, language="python"):
    return {
        "type": "code",
        "code": {
            "language": language,
            "rich_text": [{"type": "text", "text": {"content": content[:1950]}}]
        }
    }

def bullet_block(content):
    return {
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {"content": content[:1950]}}]
        }
    }

def callout_block(content, emoji="🗺️"):
    return {
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": emoji},
            "rich_text": [{"type": "text", "text": {"content": content[:1950]}}]
        }
    }

def divider_block():
    return {"type": "divider", "divider": {}}

MAP_MARKDOWN = """# 🗺️ LockTrace (BCT) — Yazılım Haritası, Sınıflar, Fonksiyonlar ve İletişim Mimarisi

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
"""

def parse_markdown_to_blocks(md_content):
    lines = md_content.split("\n")
    blocks = []
    in_code_block = False
    code_lines = []
    
    for line in lines:
        line_str = line.rstrip()
        
        if line_str.startswith("```"):
            if in_code_block:
                in_code_block = False
                blocks.append(code_block("\n".join(code_lines)))
                code_lines = []
            else:
                in_code_block = True
                code_lines = []
            continue
        
        if in_code_block:
            code_lines.append(line_str)
            continue
        
        if not line_str.strip():
            continue
        
        if line_str.startswith("# "):
            blocks.append(heading_block(1, line_str[2:].strip()))
        elif line_str.startswith("## "):
            blocks.append(heading_block(2, line_str[3:].strip()))
        elif line_str.startswith("### "):
            blocks.append(heading_block(3, line_str[4:].strip()))
        elif line_str.startswith("#### "):
            blocks.append(heading_block(3, line_str[5:].strip()))
        elif line_str.startswith("> "):
            blocks.append(callout_block(line_str[2:].strip(), emoji="💡"))
        elif line_str.startswith("---"):
            blocks.append(divider_block())
        elif line_str.strip().startswith("- ") or line_str.strip().startswith("* "):
            blocks.append(bullet_block(line_str.strip()[2:]))
        elif line_str.strip().startswith("1. ") or line_str.strip().startswith("2. ") or line_str.strip().startswith("3. ") or line_str.strip().startswith("4. "):
            blocks.append(bullet_block(line_str.strip()))
        else:
            blocks.append(text_block(line_str))
    
    return blocks

def upload_blocks_in_chunks(parent_id, blocks, chunk_size=90):
    total = len(blocks)
    uploaded = 0
    for i in range(0, total, chunk_size):
        chunk = blocks[i:i + chunk_size]
        res = notion_api(f"blocks/{parent_id}/children", method="PATCH", data={"children": chunk})
        if res:
            uploaded += len(chunk)
            print(f"[*] Uploaded {uploaded}/{total} blocks to Notion...")
        else:
            print(f"[!] Error uploading chunk at index {i}")
            break
    return uploaded

def main():
    print("[*] Creating Notion Child Page: '🗺️ Map: Architecture & Codebase Call Graph'...")
    page_data = {
        "parent": {"page_id": PARENT_PAGE_ID},
        "icon": {"type": "emoji", "emoji": "🗺️"},
        "properties": {
            "title": [
                {"type": "text", "text": {"content": "🗺️ Map: Architecture & Codebase Call Graph"}}
            ]
        }
    }
    
    new_page = notion_api("pages", method="POST", data=page_data)
    if not new_page:
        print("[!] Failed to create child page in Notion.")
        return
    
    new_page_id = new_page.get("id")
    new_page_url = new_page.get("url")
    print(f"[+] Child Page Created! ID: {new_page_id}")
    print(f"[+] URL: {new_page_url}")
    
    # Save markdown locally
    local_path = os.path.join(os.path.dirname(__file__), "..", "docs", "LOCKTRACE_ARCHITECTURE_MAP.md")
    with open(local_path, "w", encoding="utf-8") as f:
        f.write(MAP_MARKDOWN)
    print(f"[+] Local copy saved to: {local_path}")
    
    print("[*] Parsing markdown into Notion blocks...")
    blocks = parse_markdown_to_blocks(MAP_MARKDOWN)
    print(f"[*] Total {len(blocks)} blocks prepared. Uploading to Notion page...")
    
    uploaded = upload_blocks_in_chunks(new_page_id, blocks)
    print(f"\n✅ BAŞARILI! Toplam {uploaded} mimari haritası bloğu Notion alt sayfanıza aktarıldı!")
    print(f"🔗 Notion Map Sayfası URL: {new_page_url}")

if __name__ == "__main__":
    main()
