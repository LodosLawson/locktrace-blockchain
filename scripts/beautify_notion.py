import os
import sys
import re
import json
import time
import urllib.request
import urllib.error

NOTION_VERSION = "2022-06-28"
MASTER_PAGE_ID = "41234084-c76e-80de-b266-f1c404ba05d8"
MAP_PAGE_ID = "41234084-c76e-81db-91fd-f919ab899012"

def get_notion_token():
    token = os.environ.get("NOTION_TOKEN")
    if token:
        return token
    cfg_paths = [
        os.path.expanduser("~/.gemini/config/mcp_config.json"),
        os.path.expanduser("~/.gemini/config/plugins/notion/mcp_config.json")
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
        print("[!] Error: NOTION_TOKEN not found.")
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

def clear_page_children(page_id):
    print(f"[*] Clearing existing blocks from page {page_id}...", flush=True)
    deleted_count = 0
    while True:
        res = notion_api(f"blocks/{page_id}/children?page_size=100")
        if not res:
            break
        results = [b for b in res.get("results", []) if not b.get("archived")]
        if not results:
            break
        print(f"[*] Found {len(results)} active blocks to remove...", flush=True)
        for b in results:
            bid = b["id"]
            notion_api(f"blocks/{bid}", method="DELETE")
            deleted_count += 1
            time.sleep(0.03)
        if len(results) < 100:
            break
    print(f"[+] Page {page_id} cleared: {deleted_count} blocks removed.", flush=True)

def rich_text(text):
    if not text:
        return []
    # Tokenize bold (**...**), code (`...`), link ([...](...))
    tokens = []
    pattern = re.compile(r'(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))')
    parts = pattern.split(text)
    for p in parts:
        if not p:
            continue
        if p.startswith("**") and p.endswith("**") and len(p) >= 4:
            tokens.append({
                "type": "text",
                "text": {"content": p[2:-2]},
                "annotations": {"bold": True}
            })
        elif p.startswith("`") and p.endswith("`") and len(p) >= 2:
            tokens.append({
                "type": "text",
                "text": {"content": p[1:-1]},
                "annotations": {"code": True, "color": "green"}
            })
        elif p.startswith("[") and "](" in p and p.endswith(")"):
            label = p[1:p.index("](")]
            url = p[p.index("](") + 2:-1]
            tokens.append({
                "type": "text",
                "text": {"content": label, "link": {"url": url}},
                "annotations": {"bold": True, "color": "blue"}
            })
        else:
            tokens.append({
                "type": "text",
                "text": {"content": p}
            })
    return tokens

def paragraph_block(text, color="default"):
    return {
        "type": "paragraph",
        "paragraph": {
            "rich_text": rich_text(text),
            "color": color
        }
    }

def heading_block(level, text, color="default"):
    h_type = f"heading_{level}"
    return {
        "type": h_type,
        h_type: {
            "rich_text": rich_text(text),
            "color": color
        }
    }

def callout_block(text, emoji="💡", color="default"):
    return {
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": emoji},
            "rich_text": rich_text(text),
            "color": color
        }
    }

def divider_block():
    return {"type": "divider", "divider": {}}

def toc_block(color="gray"):
    return {"type": "table_of_contents", "table_of_contents": {"color": color}}

def code_block(code_text, language="plain text"):
    return {
        "type": "code",
        "code": {
            "language": language,
            "rich_text": [{"type": "text", "text": {"content": code_text[:1950]}}]
        }
    }

def create_child_page(parent_page_id, title, icon_emoji="🗺️"):
    data = {
        "parent": {"page_id": parent_page_id},
        "icon": {"type": "emoji", "emoji": icon_emoji},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        }
    }
    res = notion_api("pages", method="POST", data=data)
    if res and "id" in res:
        print(f"[+] Created new child page '{title}' with ID: {res['id']}", flush=True)
        return res["id"]
    print(f"[!] Failed to create child page: {res}", flush=True)
    return None

def bullet_block(text):
    return {
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": rich_text(text)
        }
    }

def todo_block(text, checked=False):
    return {
        "type": "to_do",
        "to_do": {
            "rich_text": rich_text(text),
            "checked": checked
        }
    }

def quote_block(text, color="default"):
    return {
        "type": "quote",
        "quote": {
            "rich_text": rich_text(text),
            "color": color
        }
    }

def table_block(headers, rows):
    width = len(headers)
    table_children = []
    
    header_cells = [rich_text(f"**{h}**") for h in headers]
    table_children.append({
        "type": "table_row",
        "table_row": {"cells": header_cells}
    })
    
    for r in rows:
        row_cells = [rich_text(str(cell)) for cell in r]
        # Pad row cells if needed
        while len(row_cells) < width:
            row_cells.append([])
        table_children.append({
            "type": "table_row",
            "table_row": {"cells": row_cells[:width]}
        })
    
    return {
        "type": "table",
        "table": {
            "table_width": width,
            "has_column_header": True,
            "has_row_header": False,
            "children": table_children
        }
    }

def toggle_block(title, children, color="default"):
    return {
        "type": "toggle",
        "toggle": {
            "rich_text": rich_text(title),
            "color": color,
            "children": children
        }
    }

def upload_blocks(parent_id, blocks, chunk_size=35):
    total = len(blocks)
    uploaded = 0
    for i in range(0, total, chunk_size):
        chunk = blocks[i:i + chunk_size]
        res = notion_api(f"blocks/{parent_id}/children", method="PATCH", data={"children": chunk})
        if res and res.get("results"):
            uploaded += len(chunk)
            print(f"[*] Uploaded {uploaded}/{total} blocks to Notion...", flush=True)
        else:
            print(f"[!] Error uploading chunk starting at index {i}: {res}", flush=True)
            break
        time.sleep(0.4)
    return uploaded

def update_page_header(page_id, title_text, icon_emoji=None, cover_url=None):
    data = {
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title_text}}]
            }
        }
    }
    if icon_emoji:
        data["icon"] = {"type": "emoji", "emoji": icon_emoji}
    if cover_url:
        data["cover"] = {"type": "external", "external": {"url": cover_url}}
    notion_api(f"pages/{page_id}", method="PATCH", data=data)

def build_master_workspace_blocks():
    blocks = [
        callout_block(
            "🛡️ **LockTrace (BCT) — Sovereign Layer-1 Blockchain & Decentralized Asset Ecosystem**\n"
            "Bu çalışma alanı, LockTrace L1 blokzincirinin mimarisini, deflasyonist ekonomik kurallarını, "
            "Base L2 köprüsünü, BNS alan adı sistemini ve Web3 sosyal protokolünü derleyen resmi teknik yönetim merkezidir.",
            emoji="🏛️",
            color="blue_background"
        ),
        divider_block(),
        heading_block(2, "📑 Hızlı İçindekiler Tablosu (Table of Contents)"),
        toc_block(),
        divider_block(),

        # SECTION 1: PROJE KIMLIGI & CANLI KANALLAR
        heading_block(2, "📌 1. Proje Kimliği & Canlı Resmi Kanallar (Quick Links)"),
        callout_block(
            "LockTrace; SHA-256 Merkle ağacı, PoW madencilik, BFT doğrulayıcı mutabakatı ve Base L2 üzerinde 1:1 wBCT köprüsüyle "
            "çalışan bağımsız, sansürlenemez ve merkeziyetsiz bir Layer-1 blokzinciridir.",
            emoji="⚡",
            color="gray_background"
        ),
        table_block(
            headers=["Kategori / Parametre", "Detay & Resmi Bağlantı", "Ağ Durumu / Not"],
            rows=[
                ["**Proje Adı**", "**LockTrace Network (L1 Protocol)**", "🟢 Mainnet Aktif (Chain ID: 885)"],
                ["**Yerel Coin Sembolü**", "**BCT** (BlockChain Trace)", "⚡ L1 Bağımsız Katman"],
                ["**Maksimum Arz**", "**1,000,000,000,000.00 BCT** (1 Trilyon Capped)", "🔒 Genesis'te Sabitlendi"],
                ["**Canlı Web3 DApp**", "[https://locktrace.space](https://locktrace.space)", "📱 Mobil PWA & Desktop"],
                ["**Base L2 Kontratı (wBCT)**", "[0xA3C743113a41cFd0146917065d4578337Bb77254](https://basescan.org/token/0xA3C743113a41cFd0146917065d4578337Bb77254)", "🔵 Base Mainnet (8453) 1:1 Peg"],
                ["**Base EVM Dead Adresi**", "[0x000000000000000000000000000000000000dEaD](https://basescan.org/address/0x000000000000000000000000000000000000dEaD)", "🔥 Kalıcı EVM Yakım Kasası"],
                ["**L1 Sıfır Yakım Adresi**", "`BCT0000000000000000000000000000000000000000`", "🔥 Matematiksel Sıfır (Key Yok)"],
                ["**GitHub Kaynak Kodu**", "[LodosLawson/locktrace-blockchain](https://github.com/LodosLawson/locktrace-blockchain)", "🐙 Açık Kaynak Repository"],
                ["**Resmi Topluluk & Duyuru**", "[LockTrace Official Telegram](https://t.me/+zsaG1qkAHZllZGIy)", "💬 Canlı P2P Topluluğu"]
            ]
        ),
        divider_block(),

        # SECTION 2: TOKENOMICS & DEFLASYONIST ARZ
        heading_block(2, "💰 2. Tokenomics & Deflasyonist Arz Mimarisi (Circulating & Burned)"),
        callout_block(
            "**Dolaşımdan Düşürülen Arz Modeli:** LockTrace protokolünde Hazine Kilit Rezervi, Base 1:1 wBCT Teminat Kasası, "
            "Protokol Yakım Adresi ve Private Key'i Kayıp Özel Test Adresleri resmi dolaşımdan kalıcı olarak düşürülür.",
            emoji="🔥",
            color="green_background"
        ),
        table_block(
            headers=["Arz Havuzu / Bileşen", "Bakiye / Oran", "İşlev & Güvenlik Kuralı"],
            rows=[
                ["**Toplam Sabit Arz**", "1,000,000,000,000.00 BCT", "Genesis Blok #0'da basılmış değiştirilemez üst limit"],
                ["**Genesis Hazine Rezervi**", "~999,897,899,888 BCT", "Blok ödülleri ve eko-sistem sübvansiyonu için kilitli rezerv"],
                ["**Base 1:1 Köprü Kasası**", "85,091,894.68 BCT", "Base L2'deki wBCT tokenlarının L1'deki %100 nakit teminat karşılığı"],
                ["**Kalıcı Protokol Yakımı**", "`BCT0000...0000`", "Matematiksel sıfır adresi; buraya gelen coinler kalıcı yok edilir"],
                ["**Kayıp Test Cüzdanları**", "17,008.20 BCT", "Ağın ilk testinde üretilmiş ve key'leri kayıp 4 cüzdan (Fiili Yakım)"],
                ["**Transfer Ücreti (%1 Tx Fee)**", "%50 Hazine / %50 Madenci", "Transfer komisyonunun yarısı sonsuza dek kilitlenir, yarısı ödül havuzuna gider"],
                ["**BNS Alan Adı Gelirleri**", "%80 Hazine / %20 Madenci", ".bct isim satışlarının %80'i Hazineye kilitlenir, %20'si madencilere dağıtılır"],
                ["**Space İçerik Telifi**", "%20 Doğrudan Yazara", "Beğeni ve yorum ücretlerinin %20'si anında gönderi sahibine ödenir"]
            ]
        ),
        divider_block(),

        # SECTION 3: TEMEL MODULLER (TOGGLE ACCORDIONS)
        heading_block(2, "🧩 3. Sistem Modülleri & Özellikleri (Interactive Cards)"),
        paragraph_block("Detayları ve alt kuralları incelemek için ilgili kartın solundaki oka tıklayarak genişletebilirsiniz:"),

        toggle_block(
            "💎 **BNS — .bct Merkeziyetsiz Alan Adı Sistemi & Pazar Yeri**",
            [
                callout_block("Uzun ve karmaşık 44 karakterli `BCT...` adresleri yerine insan tarafından okunabilen `@lodos.bct` isimleri tanımlar.", emoji="🏷️", color="purple_background"),
                bullet_block("**Karakter Uzunluğuna Göre Fiyatlandırma:** 3 harfli (50,000 BCT), 4 harfli (10,000 BCT), 5+ harfli (10 BCT)."),
                bullet_block("**Pazar Yeri (Marketplace):** Alan adları istenen fiyattan listelenebilir (%2 protokol komisyonu)."),
                bullet_block("**Non-Custodial Escrow Teklifleri:** Satışta olmayan isimlere bile BCT kilitlenerek teklif verilebilir. İptal edilirse para anında iade edilir."),
                bullet_block("**Birincil Kimlik (Primary Handle):** Kullanıcı cüzdanına ait bir ismi varsayılan seçerek Space'te ve transferlerde bu isimle görünür.")
            ],
            color="purple_background"
        ),

        toggle_block(
            "🚀 **LockTrace Space — Web3 Sosyal Ağ & Telif Motoru**",
            [
                callout_block("Blokzincir üzerinde sansürlenemez düşünce paylaşımı, telemetri kartları ve içerik üreticisi telif modeli sunar.", emoji="📢", color="blue_background"),
                bullet_block("**Gönderi Paylaşımı:** 0.05 BCT karşılığı blokzincirde kalıcı mühürlenir."),
                bullet_block("**Beğeni & Telif Dağıtımı:** 0.003 BCT beğeni ücretinin **+0.002 BCT'si** anında içerik üreticisine telif olarak ödenir."),
                bullet_block("**Yorum & Telif:** 0.02 BCT yorum ücretinin **+0.005 BCT'si** gönderi sahibinin cüzdanına aktarılır."),
                bullet_block("**Telemetri Gömüleri:** $BTC, $ETH, $SOL, $AAPL, $TSLA fiyat grafikleri ve Soğuk Cüzdan ZK Solvency kanıtları otomatik tespit edilip zengin kartlara dönüştürülür."),
                bullet_block("**Takipçi Sistemi (On-Chain Paid Follow):** 1.00 BCT karşılığı MetaMask tarzı Web3 onay modalı ile içerik üreticileri takip edilir (%50 içerik üreticisine, %30 madencilere, %20 hazineye gider).")
            ],
            color="blue_background"
        ),

        toggle_block(
            "🌉 **Base L2 Çift Yönlü Köprü (Bridge & Relayer)**",
            [
                callout_block("Layer-1 yerel BCT ile Base Mainnet (EVM) ERC-20 wBCT arasında 1:1 teminatlı çift yönlü takas sağlar.", emoji="🔗", color="yellow_background"),
                bullet_block("**L1 -> Base Minting:** Kullanıcı L1 Bridge Vault kasasına BCT kilitler. ECDSA onaylı Oracle Relayer Base üzerinde eşit miktarda wBCT mint eder."),
                bullet_block("**Base -> L1 Release:** Kullanıcı Base'de wBCT burn eder. Relayer logları yakalar ve L1 kasasından BCT'yi kullanıcının cüzdanına serbest bırakır."),
                bullet_block("**Dahili BaseScan Explorer:** Kullanıcılar arayüzden ayrılmadan BaseScan kontratındaki tüm mint/burn/transfer hareketlerini canlı izleyebilir.")
            ],
            color="yellow_background"
        ),

        toggle_block(
            "🔐 **Kriptografi & Güvenlik Kalkanı (Integrity Shield)**",
            [
                callout_block("LockTrace %100 Non-Custodial (velayetsiz) prensibiyle çalışır. Private key hiçbir zaman sunucuya iletilmez.", emoji="🛡️", color="green_background"),
                bullet_block("**SECP256k1 & BIP-39:** 12 kelimelik standart mnemonic tohumdan istemci tarafında yerel anahtar türetimi."),
                bullet_block("**On-Chain Frontend İmzası:** `index.html` ve `sw.js` dosyalarının SHA-256 hash'i Blokzincir Genesis Yetkilisi tarafından imzalanır ve Blok #509'a mühürlenmiştir."),
                bullet_block("**Sliding Window Rate Limiter:** IP ve cüzdan bazlı DDoS ve Flood koruması."),
                bullet_block("**Merkeziyetsiz Güncelleme Kuralı:** Gelecekte sistem güncellenirken Satoshi/Bitcoin modelinde olduğu gibi kurallar geriye dönük uyumlu (Soft Fork) yürütülür; kurallara uymayan bloklar madenci ve doğrulayıcılar tarafından reddedilir.")
            ],
            color="green_background"
        ),

        divider_block(),

        # SECTION 4: YOL HARITASI & DURUM
        heading_block(2, "🎯 4. Yol Haritası & Proje Durumu (Live Roadmap)"),
        todo_block("Genesis Blok #0 Mühürlendi (1 Trilyon BCT Arz)", checked=True),
        todo_block("Base Mainnet (8453) wBCT Akıllı Sözleşmesi Yayında", checked=True),
        todo_block("Çift Yönlü Köprü (Bridge Relayer & BaseScan Explorer)", checked=True),
        todo_block("BNS (.bct) Merkeziyetsiz Alan Adları & Pazar Yeri", checked=True),
        todo_block("LockTrace Space (Sosyal Ağ, Telif Modeli, Telemetri Gömüleri)", checked=True),
        todo_block("MetaMask Tarzı Web3 İmza Onay Modalı (English)", checked=True),
        todo_block("Kalıcı Yakım ve Kayıp Test Cüzdanları Arz İzolasyonu", checked=True),
        todo_block("Mobil PWA Optimizasyonu (Responsive Adresler & Padding Düzenlemesi)", checked=True),
        todo_block("Topluluk Doğrulayıcı Ağı Genişletme & DApp Ekosistemi", checked=False),
        divider_block(),
        callout_block("💡 **İpucu:** Mimari sınıf haritasını, fonksiyon parametrelerini ve veri akış şemasını incelemek için alt sayfadaki **'Map: Architecture & Codebase Call Graph'** sayfasını ziyaret edebilirsiniz.", emoji="🗺️", color="gray_background")
    ]
    return blocks

def build_map_page_blocks():
    blocks = [
        callout_block(
            "🗺️ **LockTrace (BCT) — Kaynak Kod Haritası, Sınıflar, Fonksiyonlar & Çağrı Mimarisi**\n"
            "Bu doküman, LockTrace Layer-1 blokzincirinin çekirdek sınıflarını (`Classes`), fonksiyonlarını (`Functions`), "
            "servisler arası veri alışverişini ve API uç noktalarını düzenli bir mimari panoda sunar.",
            emoji="📐",
            color="purple_background"
        ),
        divider_block(),
        heading_block(2, "📑 Mimari Dizin (Architecture Directory)"),
        toc_block(),
        divider_block(),

        # SECTION 1: SERVIS TABLOSU
        heading_block(2, "🏛️ 1. Modüller ve Sorumluluk Tablosu (Service Overview)"),
        table_block(
            headers=["Modül Dosyası", "Ana Rol & Sorumluluk", "Haberleştiği Servisler", "Güvenlik Katmanı"],
            rows=[
                ["`core/blockchain.py`", "Blokzincir Çekirdeği, Arz, PoW, BNS, Space, Escrow", "storage.py, server.py, node_runner.py", "SECP256k1 ECDSA, Merkle Tree, Hashrate Target"],
                ["`server.py`", "REST API Ağ Geçidi, Flask/WSGI, CORS, Web3 RPC", "blockchain.py, push_service.py", "SlidingWindowRateLimiter, Non-Custodial Auth Verify"],
                ["`core/bridge.py` & `bridge_relayer.py`", "Base L2 Çift Yönlü Köprü & BaseScan Senkronizasyonu", "blockchain.py, Base EVM RPC, server.py", "Web3.py Kontrat İmzası, Oracle Onay Eşiği"],
                ["`core/storage.py`", "Kalıcı SQLite WAL Veritabanı & İndeksleme Motoru", "blockchain.py, server.py", "ACID İşlem Güvenliği, Atomic Tx Rollback"],
                ["`node_runner.py`", "P2P Eş Doğrulama, BFT Quorum Konsensüsü & Mining", "blockchain.py, Diğer Peer Nodeler", "Quorum İmzaları, En Uzun Zincir Kuralı"],
                ["`core/wallet.py` & `mnemonic.py`", "BIP-39 Mnemonic & SECP256k1 Anahtar Üretimi", "Frontend JS İstemcisi, server.py", "İstemci Tarafı İmzalama, Sıfır Velayet (0 Custody)"],
                ["`core/push_service.py`", "VAPID Web Push Mobil & Masaüstü Bildirimleri", "blockchain.py, server.py, Tarayıcı", "VAPID RFC-8292 Asimetrik İmzalama"],
                ["`frontend/index.html`", "Tek Sayfa Web3 PWA Uygulaması, Cüzdan & Space UI", "server.py RPC API, Service Worker", "SHA-256 On-Chain Anchor & SRI Kontrolü"]
            ]
        ),
        divider_block(),

        # SECTION 2: END-TO-END DATA FLOW
        heading_block(2, "🔄 2. Uçtan Uca İşlem Veri Akışı (End-to-End Pipeline)"),
        code_block(
            "[İstemci / Web3 PWA (Tarayıcı)]\n"
            "   │ 1. BIP-39 ile 12 kelimeden yerel ECDSA anahtarı türetilir\n"
            "   │ 2. İşlem verisi hazırlanır ve istemcide imzalanır (Non-Custodial)\n"
            "   ▼\n"
            "[REST API Sunucusu (server.py)]\n"
            "   │ 3. SlidingWindowRateLimiter ile IP ve cüzdan kota kontrolü yapılır\n"
            "   │ 4. ECDSA imzası doğrulanır (_verify_actor_signature)\n"
            "   │ 5. İşlem mempool havuzuna eklenir (add_transaction)\n"
            "   ▼\n"
            "[Blokzincir Çekirdeği (core/blockchain.py)]\n"
            "   │ 6. İşlem ücreti (%1 fee: %50 hazine, %50 madenci) ve bakiye doğrulanır\n"
            "   │ 7. PoW bloğu kazılır (mine) ve Merkle kökü hesaplanır\n"
            "   ▼\n"
            "[Kalıcı Depolama (core/storage.py)]\n"
            "   │ 8. SQLite WAL modunda blok, işlemler ve state tabloları mühürlenir\n"
            "   ▼\n"
            "[P2P Ağı (node_runner.py)]\n"
            "   │ 9. Eş doğrulayıcılara yayınlanır (%30 BFT Quorum ile kesinleşir)\n"
            "   ▼\n"
            "[Push Servisi (core/push_service.py)]\n"
            "   │ 10. Alıcı cüzdana veya etiketlenen kişiye VAPID bildirimi iletilir",
            language="plain text"
        ),
        divider_block(),

        # SECTION 3: MODULLER DETAYLI AKORDION (TOGGLES)
        heading_block(2, "📦 3. Sınıf ve Fonksiyon Detay Haritası (Class & Function Index)"),

        toggle_block(
            "📂 `core/blockchain.py` (Blokzincir Çekirdeği, Arz & BNS Konsensüsü)",
            [
                callout_block("Blokzincirin omurgasını oluşturur. Blok üretimi, madencilik, deflasyonist kurallar ve sosyal telifler burada yönetilir.", emoji="⚙️", color="blue_background"),
                heading_block(3, "Sınıf: Transaction & Block"),
                bullet_block("`Transaction(sender, recipient, amount, fee, signature, tx_type, payload)`: Standart işlem nesnesi."),
                bullet_block("`Block.calculate_hash()` & `Block.mine(difficulty)`: PoW madencilik döngüsü ve SHA-256 blok hash hesaplama."),
                heading_block(3, "Sınıf: Blockchain — Çekirdek Metotlar"),
                table_block(
                    headers=["Fonksiyon Adı", "Parametreler", "Dönüş & Sorumluluk"],
                    rows=[
                        ["`_create_genesis_block()`", "Yok", "Blok #0'ı üretir; 1 Trilyon BCT'lik arzı hazineye ve köprüye kilitler."],
                        ["`mine_pending_transactions()`", "`miner_address`", "Mempool işlemlerini toplar, PoW bloğunu kazar, ödülü dağıtır."],
                        ["`verify_and_recalc_balance()`", "`address`", "Cüzdanın tüm geçmiş hareketlerini toplayarak kesin bakiye doğrular."],
                        ["`register_bns_handle()`", "`handle, owner, sig`", "Yeni .bct alan adı kaydeder (%80 Hazine, %20 Madenci)."],
                        ["`create_bns_offer()`", "`handle, buyer, amount, sig`", "Non-Custodial Escrow teklifi açar; teklif tutarını kilitler."],
                        ["`accept_bns_offer()`", "`handle, offer_id, sig`", "Escrow teklifini onaylar; para satıcıya, isim alıcıya geçer."],
                        ["`create_space_post()`", "`author, content, sig`", "0.05 BCT karşılığı kalıcı on-chain sosyal gönderi üretir."],
                        ["`like_space_post()`", "`post_id, sender, sig`", "0.003 BCT'nin +0.002 BCT'sini içerik sahibine telif olarak öder."],
                        ["`comment_space_post()`", "`post_id, author, text, sig`", "0.02 BCT'nin +0.005 BCT'sini içerik sahibine aktarır."],
                        ["`get_stats()`", "Yok", "Arz, hazine, köprü, yakım ve kayıp test cüzdanları istatistiklerini hesaplar."]
                    ]
                )
            ],
            color="blue_background"
        ),

        toggle_block(
            "📂 `server.py` (REST API Gateway & Güvenlik Uç Noktaları)",
            [
                callout_block("Tarayıcı ve P2P eşlerin blokzincire güvenli erişimini sağlayan Flask/WSGI API katmanıdır.", emoji="🌐", color="green_background"),
                table_block(
                    headers=["API Uç Noktası", "HTTP Metot", "Açıklama & Yetkilendirme"],
                    rows=[
                        ["`/api/v1/health`", "GET", "Düğüm sağlığı, blok yüksekliği ve frontend SHA-256 doğrulama durumu"],
                        ["`/api/v1/balance/<addr>`", "GET", "Cüzdanın doğrulanmış anlık harcanabilir BCT bakiyesi"],
                        ["`/api/v1/transfer`", "POST", "ECDSA imzalı transfer işlemini mempool'a iletme"],
                        ["`/api/v1/bns/register`", "POST", "Yeni .bct alan adı kaydı oluşturma"],
                        ["`/api/v1/bns/offer/create`", "POST", "Bir alan adına Non-Custodial Escrow teklifi verme"],
                        ["`/api/v1/space/feed`", "GET", "Space akışı (For You gravity algoritması, Latest, Top filtreleri)"],
                        ["`/api/v1/space/post`", "POST", "Yeni sosyal gönderi paylaşımı (0.05 BCT on-chain maliyet)"],
                        ["`/api/v1/bridge/lock`", "POST", "L1 -> Base köprüsü için BCT teminat kasasına kilitleme"],
                        ["`/api/v1/frontend/integrity`", "GET", "index.html ve sw.js SHA-256 bütünlük imzası ve kanıtı"]
                    ]
                )
            ],
            color="green_background"
        ),

        toggle_block(
            "📂 `core/bridge.py` & `bridge_relayer.py` (Base L2 Çift Yönlü Köprü)",
            [
                callout_block("Base Mainnet akıllı sözleşmesi (`0xA3C7...7254`) ile Layer-1 Vault arasında 1:1 teminatlı varlık geçişi sağlar.", emoji="🌉", color="yellow_background"),
                bullet_block("`BridgeService.lock_and_request_mint(sender, amount, l2_dest, sig)`: L1'de teminat kilitler."),
                bullet_block("`BridgeService.verify_and_release(burner, amount, l1_dest, evm_tx_hash)`: Base'deki burn kanıtını doğrular ve L1'de coin serbest bırakır."),
                bullet_block("`BridgeRelayer.run_cycle()`: Base L2 üzerindeki `Transfer` ve `Burn` event loglarını canlı dinleyen arka plan servis döngüsü.")
            ],
            color="yellow_background"
        ),

        toggle_block(
            "📂 `core/storage.py` (Kalıcı SQLite WAL Depolama Motoru)",
            [
                callout_block("Sistemin bellek (RAM) ve disk arasındaki kalıcılığını sağlayan SQLite WAL depolama motorudur.", emoji="💾", color="gray_background"),
                bullet_block("`SQLiteStorage._init_tables()`: `blocks`, `transactions`, `bns_records`, `space_posts`, `wallets` ve `tx_lookup` tablolarını oluşturur."),
                bullet_block("`tx_lookup` tablosu: Cüzdan adreslerinin geçmiş işlemlerine O(1) hızında anında erişim için ayrılmış hızlı dizin tablosudur."),
                bullet_block("`save_blockchain_state()` & `load_blockchain_state()`: Bellek ile diski atomik olarak senkronize eder.")
            ],
            color="gray_background"
        ),

        toggle_block(
            "📂 `node_runner.py` (P2P Dağıtık Konsensüs & Validator Motoru)",
            [
                callout_block("Blokzinciri harici doğrulayıcı ve madencilere açan bağımsız P2P eş yürütücüsüdür.", emoji="⛏️", color="purple_background"),
                bullet_block("`LockTraceNode.start_mining()`: Çok çekirdekli PoW madencilik motorunu başlatır."),
                bullet_block("`LockTraceNode.sync_with_network()`: Ağdaki diğer eşleri sorgular ve en uzun zinciri otomatik senkronize eder."),
                bullet_block("`LockTraceNode.verify_incoming_block()`: Ağdan gelen blokların SHA-256 hash'ini, PoW zorluğunu ve işlemlerin çift harcama (double spend) kontrollerini bağımsız doğrular.")
            ],
            color="purple_background"
        ),

        divider_block(),
        callout_block("✅ **Tamamlandı:** Bu harita LockTrace Layer-1 blokzincirinin üretim seviyesindeki tüm mimari parçalarını yansıtmaktadır.", emoji="✨", color="green_background")
    ]
    return blocks

def main():
    print("[*] Connecting to Notion API...")
    user = notion_api("users/me")
    if not user:
        print("[!] Cannot connect to Notion.")
        return
    print(f"[+] Connected! Bot: '{user.get('name')}'")

    print("\n" + "="*70)
    print("🎨 STEP 1: MASTER WORKSPACE ALREADY BEAUTIFIED")
    print("="*70)
    # Master page is already beautifully populated with 32 structured blocks!
    # clear_page_children(MASTER_PAGE_ID)
    # master_blocks = build_master_workspace_blocks()
    # upload_blocks(MASTER_PAGE_ID, master_blocks)

    print("\n" + "="*70)
    print("🎨 STEP 2: CREATING & POPULATING CODEBASE MAP SUBPAGE")
    print("="*70)
    map_page_id = create_child_page(
        MASTER_PAGE_ID,
        title="🗺️ LockTrace (BCT) — Kod Haritası, Sınıflar & Servis Mimarisi",
        icon_emoji="🗺️"
    )
    if map_page_id:
        map_blocks = build_map_page_blocks()
        upload_blocks(map_page_id, map_blocks)

    print("\n" + "="*70)
    print("✨ NOTION WORKSPACE BEAUTIFICATION COMPLETE!")
    print("="*70)

if __name__ == "__main__":
    main()
