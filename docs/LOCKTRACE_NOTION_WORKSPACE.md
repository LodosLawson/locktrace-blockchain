# 🛡️ LockTrace (BCT) — Master Proje Çalışma Alanı, Teknik Dokümantasyon & Pazarlama Referans Rehberi

> 💡 **Bu Dokümanın Amacı:**  
> Bu çalışma alanı; **LockTrace Layer-1 Blokzincir Ekosisteminin** bugüne kadar tamamlanan tüm teknik altyapısını, mimari haritasını, güncel ilerleme durumunu, gelecekte yapılması gereken geliştirmeleri (Roadmap) ve **reklam/pazarlama çalışmalarında doğrudan kaynak olarak kullanılacak** içerik stratejilerini tek bir merkezde toplamak için hazırlanmıştır.
>
> **Notion'a Tek Tıkla Aktarım:** Notion sol menüsünden **`Import` -> `Text & Markdown`** seçeneğine tıklayıp bu dosyayı (`docs/LOCKTRACE_NOTION_WORKSPACE.md`) seçerek tüm tabloları, görev listelerini ve başlıkları doğrudan Notion sayfanıza aktarabilirsiniz.

---

## 📌 1. Proje Kimliği & Resmi Kanallar (Quick Links)

| Kategori | Detay / Bağlantı | Durum |
| :--- | :--- | :--- |
| **Proje Adı** | **BlocTag: Decentralized Layer-1 Blockchain (Developed by LockTrace)** | 🟢 Aktif |
| **Geliştirici / R&D** | **Developed by LockTrace** | 🟢 Aktif |
| **Yerel Coin Sembolü** | **BCT** (BlockChain Trace / BlocTag) | 🟢 Mainnet |
| **Maksimum Arz** | **1,000,000,000,000.00 BCT** (1 Trilyon - Genesis'te Sabitlenmiş, Sıfır Enflasyon) | 🔒 Kilitli |
| **Canlı Web3 Portalı & DApp** | [https://locktrace.space](https://locktrace.space) | 🟢 Online (Stockholm VPS) |
| **Base L2 (EVM) Kontratı (wBCT)** | [`0xA3C743113a41cFd0146917065d4578337Bb77254`](https://basescan.org/token/0xA3C743113a41cFd0146917065d4578337Bb77254) | 🟢 Doğrulanmış (BaseScan) |
| **Resmi X (Twitter)** | [@bloctag](https://x.com/bloctag) | 🟢 Aktif |
| **Resmi Telegram Duyuru Kanalı** | [@LOCKTRACESPACE](https://t.me/LOCKTRACESPACE) | 🟢 Aktif |
| **Resmi Telegram Topluluk Grubu** | [https://t.me/+boFrw-gPj0g5ODEy](https://t.me/+boFrw-gPj0g5ODEy) | 🟢 Aktif |
| **Resmi Instagram** | [@bloctag](https://www.instagram.com/bloctag) | 🟢 Aktif |
| **GitHub Kaynak Kodu** | [LodosLawson/locktrace-blockchain](https://github.com/LodosLawson/locktrace-blockchain) | 🟢 Açık Kaynak |
| **Resmi İletişim E-Posta** | `locktracetoken@gmail.com` / `locktracetoken+space@gmail.com` | 🟢 Aktif |

---

## 📊 2. Neredeyiz? Neleri Tamamladık? (Tamamlanan Geliştirmeler Raporu)

Aşağıdaki modüllerin tamamı sıfırdan geliştirilmiş, güvenlik testlerinden geçirilmiş ve canlı ana ağda (**Mainnet**) aktif olarak çalışmaktadır:

### ✅ A. Layer-1 Blokzincir Çekirdeği & Ekonomik Kurallar
- [x] **1 Trilyon Sabit Arz:** Genesis Blok (`Blok #0`) ile üretildi. Sonradan coin basımı (minting) matematiksel olarak imkansızdır.
- [x] **Hibrit Konsensüs (%70 PoW + %30 BFT Quorum):** Hem SHA-256 Proof-of-Work madenciliği hem de doğrulayıcı düğümlerin (Validator Nodes) ECDSA imzalı oylaması ile bloklar mühürlenir.
- [x] **Otomatik İşlem Ücreti & Arz Daraltma (%1 Fee):**
  - Her transferdeki %1 kesintinin **%50'si Hazine Kasasına (`BCT_HAZINE_...`) geri dönerek** dolaşımdaki arzı daraltır.
  - Kalan **%50'si ise %70 Blok Madencisine, %30 Doğrulayıcı Quorum Düğümlerine** ödül olarak dağıtılır.
- [x] **Hoş Geldin Hibe Sistemi (1.00 BCT):** Yeni oluşturulan her cüzdana ağ kullanımını başlatabilmesi için Hazine'den otomatik 1 BCT tanımlanır (Sybil ve bot korumalı).
- [x] **SQLite WAL & SPV Merkle Kanıtı:** Yüksek hızlı `sqlite-wal` depolama motoru ve her işlemin blok içinde kriptografik olarak doğrulanmasını sağlayan Merkle Tree (SPV Proof) yapısı.

### ✅ B. Non-Custodial Cüzdan & Kriptografi
- [x] **BIP-39 12 Kelime Kurtarma İfadesi (Mnemonic):** Standart 12 kelimelik tohum cümlesi ile deterministik özel anahtar üretimi.
- [x] **SECP256k1 ECDSA İmzalar:** Hiçbir özel anahtar (private key) sunucuya gönderilmez. Tüm transfer, beğeni, yorum, alan adı alımı ve teklif işlemleri **kullanıcının tarayıcısında (client-side)** imzalanır.

### ✅ C. BlocTag (Sansürsüz On-Chain Sosyal Medya & İçerik Ekonomisi)
- [x] **Zincir Üstü Gönderi Paylaşımı (`space_post` - 0.05 BCT):** Düşünceler doğrudan blokzincir bloklarına yazılır, silinemez ve sansürlenemez.
- [x] **Doğrudan İçerik Üretici Telifi (Creator Royalties):**
  - **Beğeni (`space_like` - 0.003 BCT):** Beğeni ücretinin **+0.002 BCT'si anında içerik sahibinin cüzdanına** yatar.
  - **Yorum (`space_comment` - 0.02 BCT):** Yorum ücretinin **+0.005 BCT'si doğrudan içerik sahibine** ödenir.
  - **Bahşiş (`space_tip`):** %0 komisyonla içerik üreticisine doğrudan BCT gönderimi.
- [x] **Hibrit Batching Sequencer (Zaman + Kota):** Beğeniler 20 saniye veya 15 adet kotasıyla, yorumlar 15 saniye veya 5 adet kotasıyla tek blokta birleştirilerek zincir şişmesi (bloat) önlenir.
- [x] **Akıllı `#` Etiketleme & Bahsetme (Mention) Sistemi:** Gönderi veya yorumlarda `#BCT...` cüzdan adresi ya da `#isim.bct` alan adı etiketlendiğinde, ilgili cüzdan veya alan adı sahibine anında bildirim gönderilir.
- [x] **Gelişmiş Kullanıcı Profili Modalı:** Kullanıcının `@handle.bct` kimliği, rol rozeti (Validator / Community Member), cüzdan bakiyesi, kazandığı telif gelirleri, gönderileri, sahip olduğu `.bct` alan adları ve zincir üstü işlem geçmişi tek ekranda sunulur.

### ✅ D. BNS (`.bct` Blokzincir Alan Adı Sistemi & İkincil Pazar Yeri)
- [x] **Kademeli Alan Adı Fiyatlandırması:** 3 karakter (500 BCT), 4 karakter (150 BCT), 5+ karakter (25 BCT).
- [x] **%80 Hazine Havuzu Dönüşü & %20 Madenci Ödülü:** Yeni alınan her `.bct` alan adı ücretinin **%80'i Hazine Kasasına (`Treasury Vault`) geri dönerek dolaşımdaki arzı azaltır**, **%20'si ise aktif PoW madencilerine ve doğrulayıcı düğümlere** dağıtılır.
- [x] **İkincil Pazar Yeri (Sabit Fiyatlı Satış):** Alan adı sahipleri `.bct` isimlerini istedikleri fiyattan satışa çıkarabilir; alıcı tek işlemle ödemeyi yapar ve mülkiyet atomik olarak devredilir.
- [x] **Non-Custodial Teklif Verme (Make Offer / Escrow) Sistemi:**
  - Satışta olmayan veya fiyatı yüksek bulunan herhangi bir `xxx.bct` alan adına kullanıcılar BCT teklifi (`bns_offer`) verebilir.
  - Teklif tutarı zincir üstü güvenli emanet (Escrow) hesabında kilitlenir.
  - İsim sahibi teklifi kabul ederse (`bns_accept_offer`) para satıcıya (%2 protokol kesintisiyle), isim alıcıya anında geçer. İptal edilirse (`bns_cancel_offer`) kilitli BCT anında teklif sahibine iade edilir.
- [x] **Tam Satış Geçmişi & Analitik (Sales History Tape):** Bir alan adı kaç kez el değiştirirse değiştirsin (ister doğrudan pazar yeri satışı, ister kabul edilen teklif olsun) tüm geçmiş satışları, hacmi ve fiyat grafiği kaydedilir.

### ✅ E. Base L2 Köprüsü (`wBCT` Cross-Chain Bridge)
- [x] **1:1 Teminatlı Köprü:** LockTrace L1 üzerindeki BCT'ler `BCT_BRIDGE_VAULT` kasasında kilitlenerek Base Mainnet (EVM) üzerinde 1:1 oranında **Wrapped BCT (`wBCT`)** olarak basılır veya ters yönde yakılarak L1'e geri çekilir.
- [x] **Otomatik Relayer Servisi (`blockchaint-relayer.service`):** Zincirler arası transferleri 7/24 dinleyen ve doğrulayan otonom köprü servisi.

### ✅ F. Gerçek Zamanlı Bildirim & PWA Altyapısı
- [x] **VAPID Web Push Bildirimleri:** Kullanıcı sitede veya uygulamada olmasa bile (iOS Safari PWA, Android Chrome, Masaüstü) cüzdanına BCT geldiğinde, gönderisine beğeni/yorum/bahşiş geldiğinde, `#` ile etiketlendiğinde veya alan adına teklif geldiğinde telefonuna/bilgisayarına anında bildirim düşer.
- [x] **Uygulama İçi Bildirim Kutusu (Notification Bell):** Hem uygulama açıkken hem arka planda gelen tüm bildirimler senkronize olarak bildirim kutusunda saklanır ve okundu olarak işaretlenebilir.

### ✅ G. Kriptografik Arayüz Güvenliği & Denetim (Security Hardening)
- [x] **Comprehensive Audit Hardening & On-Chain Integrity (`v2.8.4`):** LT-01..07, LT-WEB-01..02, LT-SOL-01..02, LT-NGX-01, LT-RST-01, LT-OPS-01, LT-TWB-01, LT-POW-01, LT-MRK-01..02, LT-CRY-01, LT-GPU-01, BUG-01..05, LT-SRV-01, NEW-01..07 kapatmaları: Systemd gizli anahtar güvenliği, URL regex placeholder izolasyonu, Coinbase CSP ve Nginx miras koruması, sahte verified alıntı engeli, WrappedBCT un-indexed event logu, atomik indeks referans takası ve .env inline yorum desteği.
- [x] **On-Chain Frontend Sealing (`v2.8.4`):** `index.html` ve `sw.js` dosyalarının SHA-256 özetleri ve IPFS CIDv1 adresleri resmi otorite anahtarıyla imzalanıp doğrudan blokzincir bloğuna mühürlenir. Kullanıcı tarayıcısı arayüzün değiştirilmediğini (`verified: true`) kriptografik olarak doğrular.
- [x] **P2P Compact Block Relay & State Snapshot Fast Sync (`v2.7.0`):** BIP-152 %90+ bant genişliği tasarrufu, deterministik durum özeti (state root) ile saniyeler içinde düğüm kurulumu ve OpenCL GPU donanım madencilik motoru.
- [x] **Derinlemesine Güvenlik Taraması:** Sybil saldırı engelleri, kendi kendine sahte hacim (wash-trading) engeli, SQLite WAL kilit koruması, XSS temizliği ve hız sınırlandırma (Rate Limiting) tamamlandı.

---

## 🗺️ 3. Sistem Mimarisi: Neyin Nerede Olduğu (Kod ve Sunucu Haritası)

Projenin teknik yapısını hızlıca anlamak ve referans almak için dosya haritası:

```
BlockChainT/
├── core/
│   ├── blockchain.py        # L1 Blokzincir kalbi: Blok üretimi, PoW, BFT Quorum, BNS (.bct), Space, Compact Block, State Snapshot
│   ├── storage.py           # SQLite-WAL veritabanı motoru: Blokları, işlemleri ve durum (state) verilerini kalıcı saklar
│   ├── wallet.py            # SECP256k1 ECDSA anahtar çifti üretimi, adres türetimi (BCT...) ve imza doğrulama
│   ├── mnemonic.py          # BIP-39 12 kelimelik kurtarma cümlesi (Seed Phrase) motoru
│   ├── gpu_miner.py         # OpenCL C kernel ile GPU donanım hızlandırmalı PoW madencilik motoru (v2.7.0)
│   ├── native_bridge.py     # Rust (crates/locktrace_core) ve OpenSSL çift motorlu köprü (Dual-Engine)
│   ├── bridge.py            # Base L2 <-> LockTrace L1 köprü doğrulama ve kilit mantığı
│   ├── bridge_relayer.py    # Base Mainnet kontratını dinleyen ve transferleri tamamlayan arka plan servisi
│   ├── push_service.py      # VAPID tabanlı Web Push (iOS/Android/Web) bildirim gönderim motoru
│   └── thirdweb_service.py  # EVM / Base L2 kontrat etkileşim yardımcı servisi
├── crates/
│   └── locktrace_core/      # Rust native performans modülleri (crypto, merkle, pow, compact)
├── frontend/
│   ├── index.html           # Tüm Web3 Cüzdan, Explorer, Space Sosyal Ağ, BNS Pazar Yeri ve Dokümantasyon arayüzü (Tek Sayfa PWA)
│   ├── sw.js                # PWA Çevrimdışı Önbellek (Service Worker v34) ve Arka Plan Push Bildirim Dinleyicisi
│   ├── manifest.json        # Mobil uygulama kurulum (Add to Home Screen) tanım dosyası
│   └── integrity.json       # Arayüzün SHA-256 ve ECDSA kriptografik imza mühürü
├── scripts/
│   ├── sign_frontend.py     # Frontend dosyalarını imzalayıp integrity.json üreten güvenlik aracı
│   └── deploy_bns.py        # Canlı Oracle VPS sunucusuna otomatik yükleme, imzalama ve on-chain mühürleme scripti
├── server.py                # Ana Flask REST API Sunucusu, P2P Senkronizasyon ve Hybrid Batching Sequencer
└── node_runner.py           # Bağımsız Madenci (Miner) ve Doğrulayıcı (Validator) Node çalıştırma programı
```

### 🖥️ Sunucu ve Düğüm (Node) Topolojisi
1. **Ana Üretim Sunucusu (Mainnet Genesis & Seed Node):**
   - **Konum:** Oracle Cloud Stockholm (`129.151.205.219` / `https://locktrace.space`)
   - **Servisler:** `nginx` (SSL + Statik hızlandırma), `blockchaint.service` (Gunicorn/Flask L1 Node), `blockchaint-relayer.service` (Base L2 Köprü Relayer).
2. **Harici Doğrulayıcı & Madenci Düğümler (Validator Nodes):**
   - Yerel veya bulut tabanlı `node_runner.py` çalıştıran düğümler (Örn: `LockTrace-Ngrok-Validator` port `5050`). Ana ağa P2P bağlanır, blokları doğrular ve %30 Quorum ödülü + %20 BNS ödülü kazanır.

---

## 🚀 4. Gelecek Yol Haritası (Roadmap): Neler Yapmalıyız?

Elimizdeki mevcut altyapı tam fonksiyonel bir Layer-1 seviyesindedir. Bundan sonraki büyüme ve geliştirme adımları:

### 📌 Faz 1: Kısa Vadeli Hedefler (Topluluk & Likidite Büyümesi)
- [ ] **Base L2 (Uniswap / Aerodrome) Likidite Havuzu (DEX Pool):**
  - Base ağındaki `wBCT` (`0xA3C743...7254`) için USDC veya ETH paritesinde ilk merkeziyetsiz borsa (DEX) likidite havuzunun açılması ve canlı piyasa fiyatının oluşması.
- [ ] **Telegram & X Topluluk Botu Entegrasyonu:**
  - Yeni bir `.bct` alan adı alındığında, büyük bir BCT transferi yapıldığında veya yeni bir blok kazıldığında resmi Telegram kanalına (`https://t.me/+zsaG1qkAHZllZGIy`) otomatik bildirim atan **LockTrace Whale & BNS Bot** kurulması.
- [ ] **BlocTag Görsel & Medya Desteği (IPFS):**
  - Gönderilerde sadece metin değil, IPFS/Arweave üzerinden merkeziyetsiz görsel ve NFT paylaşımı.
- [ ] **Çoklu Dil Desteği (TR / EN Dil Seçici):**
  - Arayüzde tek tıkla İngilizce / Türkçe dil geçiş anahtarı.

### 📌 Faz 2: Orta Vadeli Hedefler (Ekosistem Genişlemesi)
- [ ] **Tarayıcı Eklentisi Cüzdanı (Chrome / Brave Extension):**
  - MetaMask benzeri, `window.locktrace` API'si sunan bağımsız tarayıcı eklentisi.
- [ ] **BNS `.bct` Alt Alan Adları (Subdomains) & Web3 Profil Sayfaları:**
  - Örneğin `kullanici.bct` sahibinin `pay.kullanici.bct` adresini oluşturabilmesi ve `locktrace.space/@kullanici.bct` şeklinde doğrudan paylaşılabilir kişisel Web3 kartvizit URL'leri.
- [ ] **Staking & Delegasyon Paneli:**
  - Kendi bilgisayarında node kuramayan kullanıcıların BCT'lerini aktif Validator düğümlerine delege ederek pasif gelir (ödül payı) kazanması.

### 📌 Faz 3: Uzun Vadeli Hedefler (Kurumsal & Küresel Ölçek)
- [ ] **CoinGecko & CoinMarketCap Başvuruları:**
  - Base DEX havuzu ve Explorer API uç noktaları (`/api/v1/stats`, `/api/v1/supply`) kullanılarak resmi listeleme başvurularının yapılması.
- [ ] **Akıllı Kontrat Sanal Makinesi (Light-VM / Token Factory):**
  - Kullanıcıların LockTrace L1 üzerinde kendi alt tokenlarını (BCT-20 standardı) tek tıkla üretebilmesi.
- [ ] **Mobil App Store & Google Play Yayını (TWA / Capacitor):**
  - Mevcut PWA yapısının imzalı APK/AAB ve iOS paketi olarak uygulama mağazalarına yüklenmesi.

---

## 📢 5. Reklam, Pazarlama ve Tanıtım Rehberi (Marketing Playbook)

Reklam çalışmalarında, sosyal medya gönderilerinde, influencer işbirliklerinde ve tanıtım videolarında referans alınacak **핵심 (Core) Değer Önerileri ve Hazır Metinler**:

### 🔥 Bizi Rakiplerden Ayıran 7 Güçlü Fark (Unique Selling Points - USP)
1. **Sadece Token Değil, Kendi Bağımsız Layer-1 Blokzinciri:** LockTrace başka bir ağın üzerinde sıradan bir token değildir; kendi PoW+BFT konsensüsü, kendi gezgini (Explorer), kendi cüzdanı ve kendi sosyal ağı olan bağımsız bir Layer-1 protokolüdür.
2. **İçerik Üreticisine Anında Kripto Kazandıran Sosyal Ağ (BlocTag):** Klasik sosyal medyada beğeni ve yorumlardan platformlar para kazanır. BlocTag'te gönderinize gelen **her beğeni ve yorumda anında cüzdanınıza BCT telifi (royalty) yatar.**
3. **Gerçek Deflasyonist Mekanizma (Arz Azaltma):**
  - Her transfer ücretinin **%50'si** Hazine Kasasına kilitlenir.
  - Her `.bct` alan adı kaydının **%80'i** Hazine Kasasına geri döner.
  - Ağ kullanıldıkça dolaşımdaki BCT miktarı sürekli daralır.
4. **Web3 Kimliği ve `.bct` Alan Adı Borsası (BNS):** Uzun ve karmaşık `BCT3fec...` adresleri yerine `@isim.bct` kullanıcı adınızla para alın, gönderin, etiketlenin ve alan adlarını açık artırma / teklif usulüyle alıp satın.
5. **Yeni Başlayanlara 1 BCT Anında Hediye (Zero-Friction Onboarding):** Kripto dünyasına yeni giren bir kullanıcı 10 saniyede cüzdanını oluşturur ve **anında 1.00 BCT hoş geldin hibesi** alarak hemen gönderi paylaşmaya veya transfer yapmaya başlayabilir.
6. **Hem Kendi L1 Ağı Hem Base L2 (EVM) Köprüsü:** İsteyen ultra düşük ücretli LockTrace L1 ağında işlem yapar, isteyen 1:1 köprü ile Base Mainnet (`wBCT`) ekosistemine geçer.
7. **Askeri Düzeyde Non-Custodial Güvenlik:** Özel anahtarlarınız asla sunucuya gitmez. Arayüz kodu bile her güncellemede blokzincire kriptografik olarak mühürlenir (`On-Chain Integrity Sealed`).

---

### 📱 Reklam Kampanyaları İçin Hazır Metin Şablonları (Copywriting)

#### 🎯 Kampanya 1: "Paylaştıkça Kazan" (Sosyal Medya / Viral Odaklı)
> **Başlık:** Beğenileriniz Sadece Kalp Değil, Kripto Kazandırsın! ⚡  
> **Metin:**  
> Klasik sosyal medyada saatlerinizi harcıyorsunuz ama tüm geliri platformlar alıyor.  
> **BlocTag** ile tanışın: Kendi Layer-1 blokzinciri üzerinde çalışan sansürsüz sosyal ağ!  
> ✅ Cüzdanını 10 saniyede aç, **1.00 BCT hoş geldin hediyeni** anında al.  
> ✅ Düşüncelerini paylaş, aldığın her beğeni ve yorumdan **anında cüzdanına BCT telifi** yatsın!  
> ✅ Kendi `.bct` Web3 alan adını tescille, teklif al, ticaret yap.  
> 🌐 Hemen Dene: https://locktrace.space  
> 💬 Telegram: https://t.me/+zsaG1qkAHZllZGIy

#### 🎯 Kampanya 2: `.bct` Alan Adı & Yatırımcı Odaklı (BNS Domain Rush)
> **Başlık:** Web3 Kimliğini Erken Kap: `.bct` Alan Adları ve Teklif Pazarı Canlıda! 🌐🔥  
> **Metin:**  
> `.eth` ve `.sol` alan adlarını ilk alanlar dijital kimliğin öncüleri oldu. Şimdi **LockTrace Name Service (`.bct`)** zamanı!  
> 🔹 Kısa ve değerli `.bct` isimlerini tescille.  
> 🔹 Ödenen BCT'nin **%80'i Hazine Havuzuna geri dönerek** dolaşımdaki arzı daraltır, **%20'si madencilere** dağıtılır!  
> 🔹 İster sabit fiyatla satışa koy, ister başkalarının alan adlarına **Non-Custodial Escrow** ile teklif ver.  
> 🔗 Cüzdanını Oluştur & İsmini Kap: https://locktrace.space

#### 🎯 Kampanya 3: Madenci & Doğrulayıcı (Validator Node) Odaklı
> **Başlık:** Kendi Bilgisayarını Bir Blokzincir Düğümüne (Node) Dönüştür! 🖥️⛏️  
> **Metin:**  
> Pahalı ASIC cihazlara gerek yok! LockTrace'in **Hibrit %70 PoW + %30 BFT Quorum** mimarisiyle kendi doğrulayıcı düğümünü çalıştır:  
> ⚡ Blok üretim ödüllerinden **%30 Quorum payı** kazan.  
> ⚡ Satılan her `.bct` alan adından **%20 madenci/doğrulayıcı havuzu payı** al.  
> ⚡ Ağın merkeziyetsizliğine güç kat, gerçek zamanlı Explorer'da kendi düğümünü izle!  
> 📖 Dokümantasyon & Kurulum: https://locktrace.space

---

### 🎬 Kısa Video / Reels / TikTok / Shorts Senaryo Akışı (30 Saniye)
1. **0-5 sn (Kanca / Hook):** *"Telefonunuzdan 10 saniyede kendi kripto cüzdanınızı açıp, ilk 1 BCT coininizi ücretsiz alabileceğinizi biliyor muydunuz?"* (Ekranda `locktrace.space` cüzdan oluşturma ve +1.00 BCT bildirim sesi gösterilir).
2. **5-15 sn (Özellik 1 - Sosyal Ekonomi):** *"Üstelik BlocTag'de yazdığınız her gönderiye gelen beğeni ve yorumlar size anında kripto telif geliri kazandırıyor."* (Ekranda bir gönderiye beğeni atılması ve telif sayacının artması gösterilir).
3. **15-23 sn (Özellik 2 - .bct Alan Adları):** *"Uzun cüzdan adresleriyle uğraşmayın; kendi `@isminiz.bct` alan adınızı alın, teklif verin ve alım-satım yapın."* (BNS Marketplace ve profil ekranı gösterilir).
4. **23-30 sn (Harekete Geçirici Mesaj / CTA):** *"Bağımsız Layer-1 blokzinciri LockTrace şu an canlıda! Profildeki linkten `locktrace.space`'e girin ve Telegram topluluğumuza katılın!"*

---

## 📋 6. Teknik Referans Özeti (Hızlı Bakış Tablosu)

| Parametre | Değer | Açıklama |
| :--- | :--- | :--- |
| **Ağ Sürümü** | `v2.9.4` | Rust Core Acceleration, Multi-Layer Bridge Hardening, Compact Relay, State Snapshot Fast Sync, GPU Mining |
| **Konsensüs** | `pow-v2-merkle-quorum` | %70 SHA-256 PoW + %30 ECDSA Validator Quorum |
| **Validator Teminatı** | `1.000,0 BCT` | %30 Quorum ve Blok Tasdikleme Havuzu için kilitli stake |
| **Transfer Ücreti** | `%1.0` | %50 Hazine Havuzu Kilidi, %35 Madenci, %15 Doğrulayıcılar |
| **BNS Kayıt Dağılımı** | `%80 / %20` | %80 Hazine Havuzuna Dönüş (Arz Azaltma), %20 Madenci & Validator |
| **BNS Pazar Yeri Komisyonu** | `%2.0` | İkincil satışlarda ve kabul edilen tekliflerde %2 protokol ücreti |
| **Gönderi / Beğeni / Yorum** | `0.10` / `0.01` / `0.02 BCT` | Yaratıcıya anında +0.002 BCT (beğeni) ve +0.004 BCT (yorum) telif |
| **Hazine Adresi** | `BCT_HAZINE_0000000000000000000000000000000000000000` | Rezerv, Hibe ve Arz Daraltma Havuzu |
| **Staking Kasası** | `BCT_STAKE_VAULT_00000000000000000000000000000000` | PoS Doğrulayıcı Teminat Kasası |
| **Köprü Kasası Adresi** | `BCT_BRIDGE_VAULT_0000000000000000000000000000000` | Base L2 `wBCT` 1:1 Karşılık Kasası |

---

## 🛡️ 7. LockTrace v2.5.0: Yüksek Verimlilik, Donma/Kilitlenme Koruması ve Dayanıklılık Mimarisi (Resilience Engine)

Yapılan stres testleri ve geleceğe yönelik çökme/darboğaz simülasyonları doğrultusunda geliştirilen v2.5.0 dayanıklılık paketi:

1. **Acil Durum LWMA Zorluk Gevşetme (Emergency Stall Recovery - Anti-Freeze):**
   - **Sorun:** Ağdaki madencilerin %90'ı aniden koptuğunda, 20 blokluk LWMA zorluk ayarı penceresi nedeniyle ağ yaklaşık 66 dakika boyunca blok üretememekte ve fiilen donmaktaydı.
   - **Çözüm:** Bloklar arası süre 120 saniyeyi (hedefin 6 katını) aştığında, geçen her 60 saniye için PoW zorluğu otomatik olarak 1 kademe gevşetilir. Ağdaki CPU madencileri hemen blok üretir ve zincir asla kilitlenmez. Yeni blok çıktığında standart LWMA mekanizması sorunsuz devralır.

2. **Dinamik Ücret Önceliklendirmesi & Spam Tahliyesi (Replace-By-Fee / Mempool Eviction):**
   - **Sorun:** Mempool 5,000 işleme ulaştığında yeni işlemlerin reddedilmesi, bir saldırganın minimum ücretli işlemlerle ağı kilitlemesine yol açabiliyordu.
   - **Çözüm:** Mempool dolduğunda gelen yeni işlem, havuzdaki en düşük ücretli işlemi tahliye eder (evict). Böylece gerçek transferler hiçbir zaman spam saldırılarıyla engellenemez.

3. **Sabit-Zamanlı Kriptografi Motoru (Constant-Time SECP256k1 & Minerva Koruması):**
   - **Sorun:** Eski `python-ecdsa` kütüphanesindeki Minerva zamanlama analizi zafiyeti (CVE-2024-23342), yan kanal ataklarına karşı risk oluşturmaktaydı.
   - **Çözüm:** Endüstri standardı OpenSSL C-çekirdekli `cryptography` motoruna geçildi. İmzalama ve doğrulama işlemleri sabit zamanlı (constant-time) ve ~2,200 TPS hızında çalışır hale getirildi.

4. **Ters İmleç (Reverse-Cursor) O(1) İşlem İndeksleme & Bellek Optimizasyonu:**
   - **Sorun:** Blok sayısı 100,000'i aştığında tüm zincirin RAM'de tutulması ve her sayfa isteğinde blokların baştan sona taranması OOM çökmesine (Out-Of-Memory) yol açıyordu.
   - **Çözüm:** Gezgin ve bakiye sorgularında O(1) sayaçlar ve SQLite `tx_lookup` indeksleri devreye alındı. Blok sorgulama performansı CPU yükü getirmeden 10 kat hızlandırıldı.

5. **Yerel Düğüm (`node_runner.py`) Senkronizasyonu:**
   - Yerel düğüm çalıştırıcısı v2.5.0 çekirdeği ile eşitlendi; dinamik zorluk geçişleri, P2P yedek tohum bağlantı dayanıklılığı ve bağlantı kopmalarında üstel geri çekilme (exponential backoff) eklendi.

---

## ⚡ 8. LockTrace v2.7.0: P2P Compact Block Relay, State Snapshot Fast Sync & GPU Hızlandırma Mimarisi

Merkeziyetsizlikten ve güvenlikten asla ödün vermeden hayata geçirilen üç dev yenilik:

1. **P2P Compact Block Relay (v2.6.0 - %90+ Bant Genişliği Tasarrufu):**
   - **Çalışma Mantığı:** Madenciler ve doğrulayıcı düğümler blok yayarken işlemlerin tamamını tekrar tekrar göndermez. Blok başlığı, prefilled coinbase işlemi ve mempool eşleştirmesi için 16 karakterlik kısa işlem kimlikleri (`short_ids`) iletilir.
   - **Merkeziyetsiz Güvenlik Koruması:** Düğüm, mempoolundaki işlemlerle bloğu yeniden birleştirir ve anında **Merkle Kökü (`merkle_root`)** kontrolü yapar. Eğer bir tek bayt bile uyuşmazsa veya eksik işlem varsa blok derhal reddedilir. Böylece ağdaki blok yayılma gecikmesi sıfıra yaklaşırken sıfır-güven (zero-trust) güvenliği %100 korunur.

2. **Merkeziyetsiz State Snapshot Warp Sync (v2.7.0 - Hızlı Kurulum):**
   - **Çalışma Mantığı:** Yeni bir doğrulayıcı düğüm kurulurken Genesis #0'dan itibaren yüz binlerce bloğu tek tek indirip saatlerce beklemek yerine, ağın anlık durum özeti (bakiye, nonce ve BNS kayıtları) indirilir.
   - **Merkeziyetsiz Güvenlik Koruması:** Snapshot körü körüne kabul edilmez! Snapshot'ın kanonik SHA-256 durum kökü (`state_root`) düğüm tarafından bağımsızca hesaplanır ve doğrulanır. Ardından düğüm son **1.000 bloğu (rolling window)** indirerek her bir işlemin imzasını, bakiyesini ve Quorum tasdiklerini eksiksiz doğrular. Sahte bakiye veya manipüle edilmiş snapshot enjekte edilmesi matematiksel olarak imkansızdır.

3. **GPU Madencilik Desteği (OpenCL Accelerated - NVIDIA / AMD / Intel):**
   - **Çalışma Mantığı:** `node_runner.py` içine standart Python `ctypes` kütüphanesi üzerinden çalışan sıfır bağımlılıklı yerel OpenCL C-bağlantısı eklendi.
   - **Donanım Uyumluluğu:** Bilgisayarda bulunan NVIDIA (Örn: GeForce RTX 3050), AMD Radeon veya Intel Arc GPU'ları otomatik algılanır. GPU mevcutsa paralel nonce taraması GPU üzerinden yüz binlerce H/s ile koşturulur; GPU bulunmayan cihazlarda ise çok çekirdekli CPU madenciliği kesintisiz devam eder.
   - **Kullanım Seçenekleri:** `--miner-engine {auto,gpu,cpu}` ve `--sync-mode {snapshot,full}` parametreleriyle tam kullanıcı denetimi sunulur.

---

## 🦀 9. LockTrace v2.8.0: Rust Core Hızlandırma, Çok Katmanlı Köprü & Tam Güvenlik Denetim Paketi

LockTrace v2.8.0 sürümü ile birlikte hayata geçirilen kritik performans ve güvenlik geliştirmeleri:

1. **Rust Native Hızlandırma Motoru (`crates/locktrace_core`):**
   - **Kriptografik Doğrulama:** SECP256k1 imza doğrulaması ve Merkle kök hesaplamalarında yüksek hızlı Rust çekirdeği.
   - **Lazy Chunking PoW:** Rayon iş parçacıklarında sıfır bellek ayırma (zero-heap allocation) ve `AtomicU64` ile hassas kümülatif hashrate telemetrisi.
   - **Çift Motorlu Mimari (Dual-Engine):** Rust modülü yüklü ise doğrudan native `.pyd` / `.so` çalışır; derleme olmayan ortamlarda Python OpenSSL motoru kesintisiz çalışır.

2. **Çok Katmanlı Köprü Güvenliği (LT-SOL-01):**
   - **Solidity Seviyesi (`contracts/WrappedBCT.sol`):** `burnToBridge` fonksiyonunda 43 karakterlik hedef BCT adresinin karakter karakter `[0-9a-fA-F]` hex kontrolü ve `BCT0000...` sıfır yakım adresine transfer engeli.
   - **Web3 Arayüz Koruması:** Kullanıcı Base'den L1'e çekim yaparken arayüz regex doğrulamasıyla hatalı veya sıfır adres girişini cüzdan onayına göndermeden engeller.
   - **Relayer Failsafe (`core/bridge_relayer.py`):** Doğrulanamayan veya hatalı adresli yakımlar `FAILED_INVALID_RECIPIENT` durumuna alınarak admin incelemesi için güvenceye alınır.

3. **Kriptografik Sosyal Gönderi İmzası (LT-WEB-01):**
   - Hızlı gönderi (`submitQuickComposePost`) fonksiyonuna `buildSignedAuthPayload` ve kanonik ECDSA imza doğrulaması eklendi; yetkisiz kimlik taklidi riski tamamen kapatıldı.

4. **DOM XSS Sanitizasyonu (LT-WEB-02):**
   - Sosyal akıştaki mention (`@`), hashtag (`#`) ve cashtag (`$`) girdileri `sanitizeJsAttr` ve `escapeHtml` ile katı sanitizasyondan geçirilerek XSS açıkları kapatıldı.

5. **Nginx HTTPS Zorunluluğu & Sıkılaştırılmış CSP (LT-NGX-01):**
   - Port 80 HTTP üzerinden `/api/` proxy kaldırıldı ve tüm trafik koşulsuz olarak 301 ile HTTPS'e yönlendirildi. CSP'den `unsafe-eval` temizlendi ve RPC çıkışları sınırlandırıldı.

6. **Thirdweb Engine EVM Adres & BigInt Güvenliği (LT-TWB-01):**
   - Pozitif tamsayı ve EVM adres format kontrolleri ile motor sağlamlaştırıldı.

---

## 🛡️ 10. LockTrace v2.8.1: Kapsamlı Güvenlik Açığı Denetimi, Testnet & 100k Bot Dayanıklılık Paketi

LockTrace v2.8.1 sürümü ile birlikte hayata geçirilen 6 kritik güvenlik açığı kapatması ve testnet doğrulamaları:

1. **Kriptografik Nöbetçi Nonce Ayrıştırması (LT-POW-01):**
   - `core/gpu_miner.py` ve `core/native_bridge.py` içindeki statik split değerleri yerine 128-bit kriptografik rastgele nöbetçi (`secrets.token_hex(16)`) ve kesin bayt ofset dilimlemesi kullanılarak işlem içeriğiyle madencilik durdurma (split DoS) saldırıları %100 engellendi.

2. **Katı SPV Merkle Kanıtı Doğrulaması (LT-MRK-01):**
   - Hedef hash ve Merkle root üzerinde 64 karakterli onaltılık (hex) doğrulaması getirildi, boş kanıt listeleri engellendi ve kardeş yönleri (`"left"` / `"right"`) hem Python hem Rust modülünde zorunlu kılındı.

3. **SECP256k1 Eğri Doğrulaması ve Sıkıştırılmış Anahtar Uyumu (LT-CRY-01):**
   - Rust (`crates/locktrace_core/src/crypto.rs`) tarafında SEC1 eğri noktası doğrulaması (`VerifyingKey::from_sec1_bytes`) eklenerek eğri dışı ($y^2 \ne x^3 + 7$) geçersiz anahtarlar reddedildi. Python cüzdanına 33-bayt sıkıştırılmış anahtar desteği eklenerek Rust ile %100 tam adres türetme eşitliği sağlandı.

4. **Merkle Tek Sayılı Yaprak Çakışma Savunması (LT-MRK-02 / CVE-2012-2459):**
   - Blok içindeki yinelenen sahte işlemler tespit edildiğinde zehirli sıfır kökü (`"0"*64`) döndürülerek blok zincirden geçersiz kılınır.

5. **EVM/L1 Köprü Adres Büyük/Küçük Harf Kanonikleştirmesi (LT-SOL-02):**
   - EVM yakım olaylarından gelen büyük harfli hex adresler L1 tarafında (`bridge.py`, `server.py`, `bridge_relayer.py`) otomatik küçük harfe dönüştürülerek fon kilitlenmesi önlendi.

6. **Çok İş Parçacıklı Madencilik Motoru & Doğru Telemetri (LT-GPU-01):**
   - `core/gpu_miner.py` içine `ThreadPoolExecutor` paralel işçi havuzu ve Rust Rayon öncelikli delegasyon entegre edildi, dürüst motor telemetrisi sağlandı.

7. **100.000 Aktif Kullanıcı Bot Ordusu & Sybil Testnet Benchmark:**
   - 100k bot cüzdanı, 5.000 işlem/blok mühürleme, Sybil musluk sömürüsü, çift harcama yarış koşulu ve doğrulayıcı stake kesintisi (slashing) testlerinin tamamından %100 başarıyla geçti.

---

## 🛡️ 11. LockTrace v2.8.2: Kritik Kriptografik & SPV Mantık Sertleştirmesi

LockTrace v2.8.2 sürümü ile hayata geçirilen 3 kritik mantık düzeltmesi:

1. **Sıfır-Baypas Açık Anahtar Adres Türetimi (`core/native_bridge.py`):**
   - Rust motorundan `None` dönen veya Python OpenSSL eğri doğrulamasına uymayan geçersiz/eğri dışı ($y^2 \ne x^3 + 7$) açık anahtarlar için ham SHA-256 fallback'i tamamen kaldırıldı. Geçersiz anahtarlarda anında `None` dönülerek sahte `BCT...` adresi üretimi engellendi.

2. **İstisna Tabanlı Merkle Kopya İşlem Engeli (CVE-2012-2459):**
   - Kopya veya yinelenen işlem içeren bloklarda `"0"*64` zehirli kök döndürme mantığı yerine açık `ValueError("CVE-2012-2459: Duplicate transaction hashes in block")` fırlatılması sağlandı. Kötü niyetli madencilerin blok başlığına `"0"*64` yazarak kopya işlemleri geçerli kılması riski tamamen ortadan kaldırıldı.

3. **Tek İşlemli Bloklar İçin SPV Kök Eşitlik Doğrulaması (`core/native_bridge.py`, `crates/locktrace_core/src/merkle.rs`):**
   - Tek işlemli bloklarda (yaprak == kök) Merkle kardeş adımları olmadığı için `proof_steps = []` boş gelir. Boş liste geldiğinde hedef işlem özeti ile Merkle kökü eşitse (`target_hash == merkle_root`) SPV doğrulaması `True` dönecek şekilde düzeltildi; tek işlemli blokların reddedilmesi hatası çözüldü.

---

## 🛡️ 12. LockTrace v2.8.3: Takipçi Telif Geçmişi, WrappedBCT Çift Basım Koruması & Madencilik Sertleştirmesi

LockTrace v2.8.3 sürümü ile hayata geçirilen 5 kritik düzeltme:

1. **Yaratıcı Takipçi Telifi İşlem Geçmişi (0.50 BCT Telif İndekslemesi):**
   - Bir kullanıcı bir yaratıcıyı takip ettiğinde ödenen 1.00 BCT'nin 0.50 BCT'si doğrudan takip edilen yaratıcıya aktarılır. İşlemin alıcısı teknik olarak `BCT_TREASURY_SYSTEM_REWARD_POOL` olduğu için arama sorgularında ve işlem geçmişinde yaratıcı adresi gözükmüyordu. `core/storage.py` içindeki `get_transactions_for_address` sorgusuna `extra_json LIKE '%"target": "..."%'` eklendi, `core/blockchain.py` ve arayüzde (frontend) `is_creator_follow_reward` bayrağı ile yaratıcının işlem geçmişinde yeşil `+ 0.5000 BCT` telif kazancı olarak listelenmesi sağlandı.

2. **WrappedBCT Kanonik Hash Çift Basım Koruması (BUG-02):**
   - `contracts/WrappedBCT.sol` içinde `mintFromBridge` fonksiyonuna `mapping(bytes32 => bool) public processedL1TxHashes;` haritası ve `_canonicalizeTxHash` dahili dönüştürücüsü eklendi. `locktraceTxHash` parametresinin büyük/küçük harf veya `0x` önekiyle değiştirilerek aynı L1 işleminin iki kez basılması (double-mint) riski matematiksel olarak engellendi.

3. **Madenci Tek Geçiş Döngüsü & İş Parçacığı Senkronizasyonu (BUG-01 & BUG-05):**
   - `core/native_bridge.py` ve `core/gpu_miner.py` içinde çözüm bulunamadığında (`ok == False`) aynı nonce aralığının 3 kez üst üste hesaplanması engellendi; Rust Rayon motorundan dönen sonuç doğrudan kabul edildi. Çoklu iş parçacıklı CPU madenciliğinde `f.result()` ardışık bloklama döngüsü yerine olay tabanlı bekleme (`found_flag.wait`) uygulandı ve geçersiz/negatif zorluklar sınırlandırıldı.

4. **Blok Gezgini Arama DoS Engeli (BUG-03):**
   - `server.py` `/api/v1/explorer/search` uç noktasında hazine veya madenci gibi on binlerce işlemi olan adresler arandığında tüm geçmişin tek seferde döndürülmesi sunucuyu ve tarayıcıyı kilitliyordu (`DoS`). Arama sonucu `history[:50]` ile 50 işlemle sınırlandırıldı; toplam işlem sayısı `transaction_count` olarak korundu.

5. **Hızlı Gönderi Ücret Eşitlemesi & JSON Hata Düzeltmesi (BUG-04):**
   - `frontend/index.html` işlem listesinde `onclick="openTxDetail(${JSON.stringify(tx)...})"` kullanımının tırnak ve satır sonlarında kırılması engellenerek `window._profileTxStore` nesnesi üzerinden güvenli çağrı sağlandı. Hızlı gönderi (`submitQuickComposePost`) için 0.10 BCT bakiye kontrolü ve `node_runner.py` doğrulaması tam mutabakata bağlandı.

---

## 🛡️ 13. LockTrace v2.8.4: Systemd Güvenliği, Çoklu İş Parçacığı & EVM Event Sertleştirmesi

LockTrace v2.8.4 sürümü ile hayata geçirilen 8 kritik düzeltme:

1. **Systemd Ortam Değişkeni İzolasyonu & Otomatik Gizli Anahtar Üretimi (LT-SRV-01):**
   - `deploy/blockchain.service` içindeki sabit `CHANGE_ME_IN_PRODUCTION` tanımları kaldırıldı ve `EnvironmentFile=-/opt/blockchaint/.env` direktifine geçildi. `deploy/setup.sh` içine otomatik 256-bit kriptografik anahtar üretimi eklendi (`chmod 600`). `config.py` içinde güvensiz varsayılan metinler (`CHANGE_ME_IN_PRODUCTION` vb.) algılandığında bellekte anında rastgele anahtarla ezilmesi sağlandı.

2. **DOM Bütünlüğü & URL Regex İzolasyonu (NEW-01):**
   - `formatSpaceBodyHtml` içinde URL'lerin sonradan gelen `@`, `#` ve `$` etiketleri tarafından HTML `href` özniteliklerinin ezilmesi (DOM kırılması) önlendi. URL'ler özel Unicode sentinel belirteçleriyle (`\uE000BCT_URL_x\uE000`) geçici olarak ayrıştırıldı ve etiketlemeler tamamlandıktan sonra güvenli biçimde geri yerleştirildi.

3. **Coinbase Canlı Fiyat CSP İzni & Nginx Güvenlik Başlıkları Mirası (NEW-02 & NEW-03):**
   - `deploy/nginx_ssl.conf` `connect-src` direktifine `https://api.coinbase.com` eklendi. Nginx `add_header` kuralı gereği `/sw.js`, `.json` ve görsel dosyalarında düşen `Strict-Transport-Security`, `X-Content-Type-Options: nosniff` ve `X-Frame-Options` başlıkları ilgili konumlarda korunarak güçlendirildi.

4. **Metin Alıntısı Sahte "Doğrulanmış Hesap" Rozeti Engeli (NEW-04):**
   - `formatSpaceBodyHtml` içindeki düz metin alıntılarında koşulsuz olarak basılan "Doğrulanmış Hesap (verified)" rozeti kaldırıldı; yanıltıcı onay işareti yerine standart `format_quote` ikonu yerleştirildi.

5. **WrappedBCT Un-Indexed Event Log Okunabilirliği (NEW-05):**
   - `contracts/WrappedBCT.sol` içinde `MintedFromBridge` olayında `string indexed locktraceTxHash` yerine `string locktraceTxHash` tanımına geçildi. Böylece L1 işlem özeti 32-baytlık Keccak-256 özetine dönüşmeden açık metin olarak EVM log verisinde saklanır; BaseScan ve relayer tarafından doğrudan okunabilir.

6. **Atomik Referans Değişimi ile Çoklu İş Parçacığı (8-Thread) Yarış Koruması (NEW-06):**
   - `_load_in_memory_bns_index` ve `_load_in_memory_space_index` fonksiyonlarındaki yerinde sözlük temizliği (`self.bns_records = {}`) kaldırıldı. Veriler yerel kapsamda (`new_bns_records`) inşa edilip tamamlandığında atomik referans ataması (`STORE_ATTR`) ile tek adımda takas edilir; eşzamanlı isteklerde boş/yarım veri veya `RuntimeError` riski sıfırlandı.

7. **Yorum Yanıtında Tire (-) Karakter Desteği & .env Satır İçi Yorum Desteği (NEW-07):**
   - `cancelCommentReply` içindeki regex `^@[a-zA-Z0-9_\-\.]+` olarak genişletildi. Python ve Node.js `.env` ayrıştırıcılarında `KEY=value # comment` şeklindeki satır içi yorumlar temizlenerek yapılandırma kirliliği giderildi.

---

## 🛡️ 14. LockTrace v2.8.5: Derinlemesine Denetim & Tam Mutabakat Güvenliği (REV11)

LockTrace v2.8.5 sürümü ile tespit edilen 6 kritik bulgunun tamamı çözüme kavuşturuldu:

1. **Nginx /health Proxy Güvenliği & IP Maskeleme Engeli (REV11-01):**
   - `deploy/nginx_ssl.conf` `/health` konumuna `limit_req zone=api burst=20 nodelay;` ve `proxy_set_header X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto` başlıkları eklendi. Rate-limit atlatma ve istemci IP adresini gizleme açığı kapatıldı.

2. **WrappedBCT processedL1Transactions Eşitlemesi (REV11-02):**
   - `contracts/WrappedBCT.sol` kontratında `mintFromBridge` çağrısında `processedL1TxHashes` ile birlikte `processedL1Transactions[locktraceTxHash] = true;` haritası da güncellendi. Dış sorgularda dönen `false` hatası giderildi.

3. **Thirdweb CLI Hassas Veri Maskeleme & Girdi Doğrulaması (REV11-03):**
   - `core/thirdweb_service.py` içinde hata loglarına yazılmadan önce `_mask_text` ile gizli anahtarlar, API anahtarları ve token'lar disk loglarından maskelendi. `claim_erc1155` fonksiyonunda adres, token_id, quantity ve chain parametrelerine katı doğrulama kuralları eklendi.

4. **SPV Kanıt Derinlik Sınırı (MAX_SPV_DEPTH) & Tekil Yaprak Yön Kontrolü (REV11-04):**
   - `core/native_bridge.py` ve `crates/locktrace_core/src/merkle.rs` modüllerinde SPV kanıt adımı sınırı `MAX_SPV_DEPTH = 32` olarak belirlendi. Tekil yaprakların kendisiyle eşleştiği durumlarda yönün zorunlu olarak `"right"` olması kuralı getirilerek DoS açığı engellendi.

5. **WrappedBCT İki Adımlı Mülkiyet Devri (Ownable2Step) (REV11-05):**
   - `contracts/WrappedBCT.sol` kontratı `Ownable2Step` mimarisine yükseltildi (`pendingOwner()`, `transferOwnership`, `acceptOwnership()`). Yanlış veya sıfır adrese tek adımda geri dönülemez yetki devri riski ortadan kaldırıldı.

6. **OpenCL Donanım Dizi Sınır Güvenliği & URL Zaman Aşımı Koruması (REV11-06):**
   - `core/gpu_miner.py` içinde OpenCL aygıt sayısı dinamik olarak sorgulanıp tahsis edildi, indeks sınırlandırıldı (`IndexError` engeli). `scripts/*.py` altındaki tüm `urllib.request.urlopen` çağrılarına açık `timeout` parametresi eklendi.

---

## 🛡️ 15. LockTrace v2.8.6: Konsensüs Optimizasyonu, Kriptografik Normalizasyon & Kaynak Sertleştirmesi (AUD12)

LockTrace v2.8.6 sürümü ile çözülen 8 kritik optimizasyon ve güvenlik bulgusu:

1. **PoW Sıfır Tahsisli İç Döngü & İptal Sinyali Entegrasyonu (AUD12-01):**
   - `crates/locktrace_core/src/pow.rs` içinde her nonce döngüsündeki `hex::encode` heap tahsisi kaldırıldı; doğrudan `[u8; 32]` bayt seviyesinde sıfır maliyetli kontrol sağlandı. Başlık öneki mid-state olarak önceden hash'lenip klonlandı. `core/gpu_miner.py` içinde `stop_event` sinyali dilimlenmiş batch döngüsüyle Rust motoruna bağlandı.

2. **Thirdweb Sunucu Özel Anahtarı Maskelemesi (AUD12-02):**
   - `core/thirdweb_service.py` içinde `THIRDWEB_SERVER_PRIVATE_KEY` ve ham 64-hex özel anahtar desenleri maskeleme listesine alındı; genel `client_id` değeri maskelemeden çıkarılarak arayüz şeffaflığı korundu.

3. **WrappedBCT SSTORE Gaz Optimizasyonu & Kanonik Getter (AUD12-03):**
   - `contracts/WrappedBCT.sol` kontratında fazladan ~22.100 gaz tüketen dinamik string `processedL1Transactions` state haritası kaldırıldı; yerine `processedL1TxHashes` haritasını okuyan ve 0x/büyük-küçük harfe duyarsız kanonik bir getter fonksiyonu tanımlandı.

4. **Web Push DoS Uzunluk Sınırları & Bounded Thread Pool (AUD12-04):**
   - `core/push_service.py` içinde `endpoint` (512 karakter), `p256dh` (128 karakter) ve `auth` (64 karakter) uzunluk sınırları getirildi. Sınırsız iş parçacığı (`threading.Thread`) açılması yerine 4 işçili `ThreadPoolExecutor` motoruna geçildi.

5. **Mnemonic Doğrulaması & BIP-39 NFKD Normalizasyonu (AUD12-05):**
   - `core/mnemonic.py` modülünde boş veya geçersiz kurtarma kelimeleri verildiğinde sabit anahtar üretilmesi engellendi (`ValueError`); BIP-39 standardına uygun UTF-8 NFKD normalizasyonu zorunlu kılındı.

6. **Kompakt Blok Değişmezleri & Zorluk Kontrolü (AUD12-06):**
   - `crates/locktrace_core/src/compact.rs` içinde `difficulty` (1..64) aralığı denetlendi; `prefilled.len() + short_ids.len() == total_transactions` eşitliği ve `prefilled.index` sınır ve tekillik kontrolleri eklendi.

7. **Paylaşımlı Madenci Motoru Tekili (Singleton) (AUD12-07):**
   - `core/native_bridge.py` içinde her PoW yedek çağrısında OpenCL Ctypes sürücüsünün sıfırdan yüklenmesi engellendi; iş parçacığı güvenli `get_shared_miner_engine()` tekil nesnesi kuruldu.

8. **Nginx HTTP Fallback CSP & Dağıtım Sertleştirmesi (AUD12-08):**
   - `deploy/nginx.conf` dosyasına tam özellikli Web3 Content-Security-Policy başlıkları, API proxy ve rate limiting eklendi; eski `X-XSS-Protection` başlığı kaldırıldı.

---

## 🛡️ 16. LockTrace v2.8.7: Üretim Motoru, Çalışma Zamanı Ayrıştırma & Web3 İstemci Güvenliği (AUD14)

LockTrace v2.8.7 sürümü ile çözülen 7 yeni güvenlik açığı, mantık hatası ve optimizasyon:

1. **Thirdweb CLI Temiz Süreç Sonlandırması (AUD14-01):**
   - `thirdweb_engine.mjs` içinde tüm başarılı komut dönüşlerinde açık kalan RPC/WebSocket soketlerinin Node.js sürecini 45 saniye boyunca askıda bırakmasını önlemek amacıyla `process.exit(0)` çağrısı eklendi.

2. **SECP256k1 Eğri Noktası Tekil Ayrıştırma Optimizasyonu (AUD14-02):**
   - `crates/locktrace_core/src/crypto.rs` modülünde `parse_verifying_key` fonksiyonu kurularak her imza doğrulamasında `VerifyingKey::from_sec1_bytes` çağrısının iki kez yapılması engellendi, kriptografik CPU yükü yarıya indirildi.

3. **PoW Nonce Ofseti & SHA-256 Durum Klonlama (AUD14-03):**
   - `core/gpu_miner.py` ve `core/native_bridge.py` içinde `start_nonce` parametresi desteği getirilerek aynı saniyede yinelenen 0..2M taramaları ortadan kaldırıldı; Python fallback'te blok başlığı öneki `hashlib.sha256.copy()` ile klonlanarak her nonce için sıfırdan özetleme engellendi.

4. **Frontend DOM XSS Savunması & Piyasa Verisi Kaçışı (AUD14-04):**
   - `frontend/index.html` ve `scripts/replace_embed.py` içinde `onclick` özniteliklerine aktarılan gönderi kimlikleri (`pid`) `sanitizeJsAttr` ile arındırıldı; canlı piyasa kartlarında `m.change` verisi `escapeHtml` ile sarmalanarak DOM XSS açığı kapatıldı.

5. **Otomatik Rust Derlemesi & Systemd Dosya Sınırları (AUD14-05):**
   - `deploy/setup.sh` içine `cargo rustc` ve `maturin develop --release` adımları eklenerek VPS sunucusunun saf Python'a düşmesi önlendi; `deploy/blockchain.service` içine `LimitNOFILE=65535` ve `LimitNPROC=65535` direktifleri yerleştirildi.

6. **Nginx Cüzdan Uç Noktası Gövde Sınırı & Zaman Aşımı (AUD14-06):**
   - `deploy/nginx.conf` ve `deploy/nginx_ssl.conf` içindeki `/api/v1/wallet/create` bloğuna `client_max_body_size 1m;` ve proxy zaman aşımı sınırları (`proxy_connect_timeout 10s; proxy_read_timeout 30s; proxy_send_timeout 30s;`) eklendi.

7. **SSH Günlük Denetleyicisi Zaman Aşımı & Gizli Veri Maskelemesi (AUD14-07):**
   - `scripts/test_base_logs.py` içine 30 saniye zaman aşımı denetimi (`TimeoutExpired`), özel anahtar ve gizli belirteç maskeleme fonksiyonu (`mask_output`) entegre edildi.

8. **Mnemonic Küçük Harf Normalizasyonu (AUD13-01):**
   - `core/mnemonic.py` içindeki `mnemonic_to_private_key` fonksiyonunda BIP-39 standartlarına uygun olarak NFKD normalizasyonu öncesi `cleaned_mnemonic = " ".join(mnemonic.strip().lower().split())` uygulanarak büyük/küçük harf duyarsızlığı güvenceye alındı.

---

## 🛡️ 17. LockTrace v2.8.8: Tamsayı Taşması Savunması, Nginx CSP Kalıtımı & Engine Seçenek Koruması (AUD15)

LockTrace v2.8.8 sürümü ile çözülen 8 kritik bulgu ve optimizasyon:

1. **Frontend Canlı Piyasa Dilimleme Hatası Onarımı (AUD15-01):**
   - `scripts/replace_embed.py` içinde `f_idx2` başlangıcı doğrudan referans alınarak `window.liveMarketPrices =` tanımının silinmesi önlendi; frontend JS sözdizimi kırılması engellendi.

2. **Gizli Anahtar Maskeleme Geri Başvuru Hatası & Çoklu DB Yolu (AUD15-02):**
   - `scripts/test_base_logs.py` içinde `r'\1'` yerine grup eşleşmesi fonksiyonu (`_mask_match`) kullanılarak 64-hex anahtarların ekrana iki kez basılması engellendi; hem `/opt/blockchaint/blockchain.db` hem de `/opt/blockchaint/data/blockchain.db` yollarını otomatik tespit eden yapı kuruldu.

3. **Rust Çekirdeği u64 Tamsayı Taşması (Integer Overflow) Koruması (AUD15-03):**
   - `crates/locktrace_core/src/pow.rs` içinde yüksek `start_nonce` ve `max_nonces` değerlerinde panik veya taşma yaşanmaması için `checked_mul`, `checked_add` ve `saturating_add` güvenli aritmetik kontrolleri uygulandı.

4. **Nginx Alt Konum CSP Kalıtımı & /integrity.json Eşitlemesi (AUD15-04):**
   - Nginx'in `add_header` direktifini alt konumlara devretmeme kuralı nedeniyle `/sw.js`, `/integrity.json`, `/node_runner.py` gibi tüm alt bloklara Content-Security-Policy ve güvenlik başlıkları açıkça eklendi; `deploy/nginx.conf` içine eksik `/integrity.json` bloğu yerleştirildi.

5. **BIP-39 Doğrulama Öncesi Tam Unicode NFKD Normalizasyonu (AUD15-05):**
   - `core/mnemonic.py` içinde hem `validate_mnemonic` hem de `mnemonic_to_private_key` fonksiyonlarında kelime listesi doğrulanmadan önce `unicodedata.normalize("NFKD", ...)` çalıştırılması zorunlu kılındı.

6. **P2P Kompakt Blok Sürüm, Ham JSON ve Kısa Kimlik Denetimi (AUD15-06):**
   - `crates/locktrace_core/src/compact.rs` içinde `compact_version == 1` kontrolü, 64 KB prefilled `raw_json` bellek sınırı ve 16-hex kısa kimlik (short_id) format doğrulaması uygulandı.

7. **Thirdweb 0x Önek Normalizasyonu & CLI Komut Enjeksiyon Savunması (AUD15-07):**
   - `thirdweb_engine.mjs` içinde sunucu özel anahtarına otomatik `0x` öneki eklendi; `core/thirdweb_service.py` ve `thirdweb_engine.mjs` içinde işlem kimliği ve zincir adı regex'lerinin tire (`-`) ile başlaması engellenerek CLI parametre enjeksiyonu kapatıldı.

8. **Güvenlik Paketi Gizlilik Filtreleri & Dinamik Protokol SSOT (AUD15-08):**
   - `scripts/create_audit_bundle.py` içindeki zip paketleyicisine `.env*`, `*key*`, `*rsa*` ve sertifikaları dışlayan katı gizlilik filtreleri eklendi; protokol sürümü doğrudan `Config.PROTOCOL_VERSION` değişkenine bağlandı.

---

## 🛡️ 18. LockTrace v2.8.9: Rayon Sınırlandırması, DOM Sanitizasyonu & Protokol SSOT Senkronizasyonu (AUD16)

LockTrace v2.8.9 sürümü ile çözülen 8 kritik bulgu ve optimizasyon:

1. **Yüksek Start-Nonce Rayon Sonsuz Döngü Koruması (AUD16-01):**
   - `crates/locktrace_core/src/pow.rs` içinde `max_nonces`, `u64::MAX - start_nonce` aralığına sınırlandırılarak Rayon'un boş chunk'lar üretmesi ve CPU'nun %100'e kilitlenmesi engellendi.

2. **Öncelikli ve Boyut Kontrollü Veritabanı Tespiti (AUD16-02):**
   - `scripts/test_base_logs.py` içinde `/opt/blockchaint/data/blockchain.db` ilk sıraya alındı ve `os.path.getsize(p) > 0` şartı eklenerek 0-byte boş dosyaların seçilmesi önlendi.

3. **DOM XSS inline Olay Sanitizasyonu (AUD16-03):**
   - `scripts/replace_embed.py`, `frontend/index.html` ve `templates/index.html` içindeki `onclick` özniteliklerinde `escapeHtml` yerine HTML entity çözümleme bypass'ını engelleyen `sanitizeJsAttr` kullanıldı.

4. **Kompakt Blok Başlık ve Tekil Kısa Kimlik Denetimi (AUD16-04):**
   - `crates/locktrace_core/src/compact.rs` içinde `hash`, `previous_hash`, `merkle_root`, `miner` alanlarına `!is_empty()` denetimi ve `short_ids` listesine `HashSet` ile mükerrer kimlik engellemesi getirildi.

5. **Thirdweb 64-Hex Format Doğrulaması & Çift Önek Maskeleme (AUD16-05):**
   - `thirdweb_engine.mjs` içinde büyük harf `0X` önekleri temizlenip küçük harf `0x` formatına zorlandı; Python `_mask_text` fonksiyonunda hem yalın 64-hex hem de `0x`/`0X` önekli anahtarlar maskelendi.

6. **BIP-39 Bölme Öncesi NFKD Normalizasyonu (AUD16-06):**
   - `core/mnemonic.py` içinde Unicode boşluk ve birleştirici karakterlerin ayrıştırma hatasına yol açmaması için `unicodedata.normalize("NFKD", ...)` işlemi `.split()` çağrısından önceye alındı.

7. **Güvenlik Denetim Paketi Filtre ve Dinamik XML Güncellemesi (AUD16-07):**
   - `scripts/create_audit_bundle.py` hariç tutma kurallarına `"wallet"` ve `".bak"` filtreleri eklendi; çıktı XML adı `repomix-output_16.xml` olarak güncellendi.

8. **Evrensel Protokol SSOT Sürüm Uyumlaştırması (AUD16-08):**
   - `scripts/sign_frontend.py`, `scripts/build_whitepaper_pdf.py`, `scripts/fast_deploy.py`, `scripts/run_node.*` ve tüm dokümantasyon v2.8.9 olarak senkronize edildi.



---

## 🛡️ 19. LockTrace v2.9.0: P2P Amplifikasyon Koruması, Snapshot Önbelleği & SSRF Yönlendirme Savunması (AUD17)

1. **P2P getblocktxn Hız Sınırı & İndeks Amplifikasyon Savunması (AUD17-01):** `indices` listesi 200 elemanla sınırlandırıldı, mükerrer indeksler tekilleştirildi ve tip dönüşümü güvenli hale getirildi.
2. **State Snapshot Önbellekleme & Hız Sınırı (AUD17-02):** `/api/v1/snapshot/latest` uç noktasına hız sınırı ve `get_state_snapshot()` içine 15 saniyelik blok yüksekliği bazlı önbellek eklendi.
3. **P2P HTTP Yönlendirme (Redirect) SSRF Koruması (AUD17-03):** `_broadcast_block_to_peers` içinde HTTP 301/302 yönlendirmelerini engelleyen `_NoRedirectHandler` devreye alındı.
4. **Kompakt Blok Madenci İmza İletimi (AUD17-04):** `/p2p/gossip/compact_block` içinde `public_key` ve `signature` alanları konsensüs motoruna aktarıldı.
5. **Nginx /p2p/ Proxy Yönlendirmesi (AUD17-05):** `nginx_ssl.conf` ve `nginx.conf` dosyalarına `location /p2p/` bloğu eklendi.
6. **Validator Stake/Unstake Hız Sınırı (AUD17-06):** `/api/v1/validator/stake` ve `/api/v1/validator/unstake` uç noktalarına IP bazlı hız sınırı eklendi.
7. **Yetkilendirilmiş Web Push İptali (AUD17-07):** `/api/v1/notifications/unsubscribe` için ECDSA cüzdan imzası veya cihaz `auth` sırrı doğrulaması zorunlu kılındı.

---

## 🛡️ 20. LockTrace v2.9.1: Köprü Gas Drenajı Savunması, Rust Tamsayı Bölme Koruması & SECP256k1 Mertebe Denetimi (AUD17B)

1. **Köprü Gas Drenajı Savunması & Kontrat Mükerrerlik Denetimi (AUD17B-01):** `_mint_on_base` içinde `processedL1Transactions` kontrolü ve dinamik `estimate_gas` eklendi; revert eden işlemlerin Base ETH bakiyesini tüketmesi engellendi.
2. **Rust PoW u64 Taşmasız Yukarı Yuvarlama Bölmesi (AUD17B-02):** `crates/locktrace_core/src/pow.rs` içinde `(effective_max + chunk_size - 1)` taşma riski taşmasız bölme formülüyle giderildi.
3. **Cüzdan 64-Hex & SECP256k1 Eğri Mertebesi Sınır Denetimi (AUD17B-03):** `core/wallet.py` içinde 64-hex format ve `1 <= k < SECP256K1_ORDER` sınır kontrolü uygulandı.
4. **Köprü Kuyruk Blokajı HTTP 400/422 Drenaj Savunması (AUD17B-04):** `process_pending_burns` içinde `urllib.error.HTTPError` yakalanarak hatalı emirlerin `FAILED` işaretlenmesi ve kuyruğu tıkamaması sağlandı.
5. **Relayer NoneType & Veritabanı Bağlantı Sızıntısı Koruması (AUD17B-05):** `get_status()` içinde `NoneType` kontrolleri eklendi; `check_conn` bağlantısı `finally` bloğu ile kapatıldı.
6. **Öncelikli Veritabanı Yolu & Doğrudan Decimal Dönüşümü (AUD17B-06):** `core/bridge_relayer.py` varsayılan DB yolu `data/blockchain.db` olarak güncellendi ve ara `float()` dönüşümü kaldırıldı.
7. **Netlify /p2p/* Yönlendirme Kuralı (AUD17B-07):** `frontend/netlify.toml` içine `/p2p/*` yönlendirme kuralı eklendi.

---

## 🛡️ 21. LockTrace v2.9.2: Web3 v6 Uyumluluğu, Köprü Onay Ertelemesi & Kapsayıcı PoW Aralığı (AUD18)

1. **Web3 v6+ Uyumluluğu & POA Middleware Temizliği (AUD18-01):** `core/bridge_relayer.py` içindeki kullanılmayan ve `web3` v6+ sürümlerinde bulunmayan `ExtraDataToPOAMiddleware` içe aktarımı kaldırılarak relayer çalışma hatası giderildi.
2. **Köprü Onay Derinliği Ertelemesi (AUD18-02):** `process_pending_burns` içinde 12 EVM onayını bekleyen işlemlerin HTTP 400 ile erken `FAILED` işaretlenmesi engellendi; işlem onaylar tamamlanana kadar ertelendi.
3. **Rust PoW Kapsayıcı Aralık & u64::MAX Sınır Desteği (AUD18-03):** `crates/locktrace_core/src/pow.rs` içinde chunk yinelemesi `chunk_start..=chunk_end_inclusive` biçimine dönüştürülerek `u64::MAX` sınırının taranması güvenceye alındı.
4. **Köprü Relayer 0x Kanonik Önek & Gas Hijyeni (AUD18-04):** Base üzerinde yayınlanan işlemlere `0x` öneki zorunlu kılındı, pozitif `amount_wei` denetimi yapıldı, ölü kod kaldırıldı ve `LOCKTRACE_API_URL` yapılandırılabilir kılındı.
5. **BIP-39 NFKD Unicode Normalizasyonu & Eğri Mertebesi Birleştirmesi (AUD18-05):** `core/wallet.py` içinde `self.mnemonic` için `unicodedata.normalize("NFKD", ...)` uygulandı ve `SECP256K1_ORDER` tekilleştirildi.
6. **Nginx Permissions-Policy Alt Konum Mirası (AUD18-06):** `nginx.conf` ve `nginx_ssl.conf` içerisindeki tüm alt `location` bloklarına `Permissions-Policy` başlığı eklenerek tarayıcı güvenlik başlığı korundu.
7. **Denetim Paketi & SSOT Protokol Senkronizasyonu (AUD18-07):** Protokol `v2.9.2` sürümüne yükseltildi, `repomix-output_19.xml` ve `test_aud18_fixes.py` güvenlik paketine dahil edildi.

---

## 🛡️ 22. LockTrace v2.9.4: Köprü Kuyruk Kilit Çözümü, Toz Yakım Sınırı & Repomix Varlık Filtresi (AUD19)

1. **Köprü Kuyruk Blokajı ve Kilit Çözümü (AUD19-01):** `process_pending_locks` içinde geçersiz 64-hex hash formatı, sıfır/negatif tutarlar ve 2 saat boyunca blokta onaylanmayan kilit işlemleri `FAILED` işaretlenerek `LIMIT 10` baş-sıra tıkanması giderildi.
2. **Köprü Çekim Decimal Hassasiyeti & 1 wBCT Minimum Yakım (AUD19-02):** `process_pending_burns` içinde `float()` kaldırılarak hassas `Decimal` hesaplamaya geçildi; `WrappedBCT.sol` kontratına `MIN_BURN_AMOUNT = 1 wBCT` anti-toz yakım koruması eklendi.
3. **Nginx Tekil Content-Type Yapılandırması (AUD19-03):** `deploy/nginx.conf` ve `deploy/nginx_ssl.conf` içindeki `/node_runner.py` bloğunda `add_header Content-Type` yerine `default_type text/x-python;` kullanılarak çift başlık sorunu giderildi.
4. **Whitepaper PDF Üreteci Genel Başlık Filtresi (AUD19-04):** `scripts/build_whitepaper_pdf.py` markdown filtre satırı `*Version ` olarak genişletilerek PDF kapağında mükerrer sürüm yazımı engellendi.
5. **Yerel Test Düğüm Senkronizasyon Listesi Genişletmesi (AUD19-05):** `scripts/sync_local_node.py` dosyasına `config.py`, `core/wallet.py`, `core/mnemonic.py` ve `core/bridge_relayer.py` eklendi.
6. **Çift SHA-256 ve Kontrat Parametre Dokümantasyon Uyumu (AUD19-06):** Cüzdan adres türetiminin Double SHA-256 olduğu dokümanlarda netleştirildi ve `docs/LIQUIDITY_AND_BRIDGE_GUIDE.md` içindeki kurucu parametresi `initialRelayer` ile eşitlendi.
7. **Repomix Base64 Varlık Filtresi & Paket Hafifletmesi (AUD19-07):** `.repomixignore` ve `repomix.config.json` ile ağır SVG/görsel dosyaları XML denetim çıktısından hariç tutuldu; repomix token tüketimi ~84.200 token hafifletildi.

---

## 🛡️ 23. LockTrace v2.9.4: Cüzdan Kasası, Kalıcı Slashing, Sybil-Güvenli Quorum & Köprü Korumaları (F-01 – F-10, N-01)

1. **F-01 Cüzdan Kasası:** `sha256Bytes` dışa aktarıldı; sıfır anahtar akışı (düz metin) yerine fail-closed şifreleme; eski kayıtlar otomatik göç eder.
2. **F-03 Kalıcı Slashing:** Çifte imza defteri ve slashed validator listesi SQLite'ta saklanır; restart'ta sıfırlanmaz.
3. **F-04 Sybil Quorum:** Attestation sayımı `node_id` yerine validator cüzdanına göre yapılır.
4. **F-05 Tam Tutar Eşleşmesi:** 0.0001 BCT toleransı kaldırıldı (8 hane / wei).
5. **F-06 Mint Limitleri:** Relayer işlem/24 saat limitleri ve kontratta `maxMintPerTx`, `dailyMintLimit`, 2 gün timelock.
6. **F-07 CSP:** `script-src`'ten `unsafe-inline` ve CDN'ler kaldırıldı; inline scriptler SHA-256 ile sabitlendi; kütüphaneler self-host (SRI).
7. **F-08 Geçici Durumlar:** pending/mempool/RPC/rezerv hataları artık FAILED yapmaz.
8. **F-10 İmzalı Emir:** Köprü emri oluşturma cüzdan imzası gerektirir; başkasının emri iade edilmez.
9. **N-01 Otomatik Devam:** 2 saatte bloğa girmeyen kilitler `STALLED` olur ve onaylanınca otomatik mint edilir.
