# 🛡️ LockTrace (BCT) — Master Proje Çalışma Alanı, Teknik Dokümantasyon & Pazarlama Referans Rehberi

> 💡 **Bu Dokümanın Amacı:**  
> Bu çalışma alanı; **LockTrace Layer-1 Blokzincir Ekosisteminin** bugüne kadar tamamlanan tüm teknik altyapısını, mimari haritasını, güncel ilerleme durumunu, gelecekte yapılması gereken geliştirmeleri (Roadmap) ve **reklam/pazarlama çalışmalarında doğrudan kaynak olarak kullanılacak** içerik stratejilerini tek bir merkezde toplamak için hazırlanmıştır.
>
> **Notion'a Tek Tıkla Aktarım:** Notion sol menüsünden **`Import` -> `Text & Markdown`** seçeneğine tıklayıp bu dosyayı (`docs/LOCKTRACE_NOTION_WORKSPACE.md`) seçerek tüm tabloları, görev listelerini ve başlıkları doğrudan Notion sayfanıza aktarabilirsiniz.

---

## 📌 1. Proje Kimliği & Resmi Kanallar (Quick Links)

| Kategori | Detay / Bağlantı | Durum |
| :--- | :--- | :--- |
| **Proje Adı** | **LockTrace: Decentralized Layer-1 Blockchain & Sovereign Asset Protocol** | 🟢 Aktif |
| **Yerel Coin Sembolü** | **BCT** (BlockChain Trace) | 🟢 Mainnet |
| **Maksimum Arz** | **1,000,000,000,000.00 BCT** (1 Trilyon - Genesis'te Sabitlenmiş, Sıfır Enflasyon) | 🔒 Kilitli |
| **Canlı Web3 Portalı & DApp** | [https://locktrace.space](https://locktrace.space) | 🟢 Online (Stockholm VPS) |
| **Base L2 (EVM) Kontratı (wBCT)** | [`0xA3C743113a41cFd0146917065d4578337Bb77254`](https://basescan.org/token/0xA3C743113a41cFd0146917065d4578337Bb77254) | 🟢 Doğrulanmış (BaseScan) |
| **Resmi Telegram Kanalı** | [https://t.me/+zsaG1qkAHZllZGIy](https://t.me/+zsaG1qkAHZllZGIy) | 🟢 Aktif |
| **Resmi X (Twitter)** | [@LockTraceSpace](https://x.com/LockTraceSpace) | 🟢 Aktif |
| **Resmi Instagram** | [@locktracespace](https://www.instagram.com/locktracespace) | 🟢 Aktif |
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

### ✅ C. LockTrace Space (Sansürsüz On-Chain Sosyal Medya & İçerik Ekonomisi)
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
- [x] **Comprehensive Audit Hardening & On-Chain Integrity (`v2.8.1`):** LT-01'den LT-07'ye, LT-WEB-01..02, LT-SOL-01, LT-NGX-01, LT-RST-01, LT-OPS-01, LT-TWB-01 ve v2.8.1 ile LT-POW-01, LT-MRK-01, LT-CRY-01, LT-MRK-02, LT-SOL-02, LT-GPU-01 kapatmaları: Kriptografik rastgele nöbetçi nonce ayrımı ile madenci DoS koruması, 64-karakter hex SPV Merkle doğrulaması, Rust/Python SECP256k1 eğri doğrulaması ve sıkıştırılmış anahtar uyumu, çift yapraklı Merkle çakışma koruması (CVE-2012-2459) ve büyük/küçük harf köprü adres kanonikleştirilmesi.
- [x] **On-Chain Frontend Sealing (`v2.8.1`):** `index.html` ve `sw.js` dosyalarının SHA-256 özetleri ve IPFS CIDv1 adresleri resmi otorite anahtarıyla imzalanıp doğrudan blokzincir bloğuna mühürlenir. Kullanıcı tarayıcısı arayüzün değiştirilmediğini (`verified: true`) kriptografik olarak doğrular.
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
- [ ] **LockTrace Space Görsel & Medya Desteği (IPFS):**
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
2. **İçerik Üreticisine Anında Kripto Kazandıran Sosyal Ağ (LockTrace Space):** Klasik sosyal medyada beğeni ve yorumlardan platformlar para kazanır. LockTrace Space'te gönderinize gelen **her beğeni ve yorumda anında cüzdanınıza BCT telifi (royalty) yatar.**
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
> **LockTrace Space** ile tanışın: Kendi Layer-1 blokzinciri üzerinde çalışan sansürsüz sosyal ağ!  
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
2. **5-15 sn (Özellik 1 - Sosyal Ekonomi):** *"Üstelik LockTrace Space'te yazdığınız her gönderiye gelen beğeni ve yorumlar size anında kripto telif geliri kazandırıyor."* (Ekranda bir gönderiye beğeni atılması ve telif sayacının artması gösterilir).
3. **15-23 sn (Özellik 2 - .bct Alan Adları):** *"Uzun cüzdan adresleriyle uğraşmayın; kendi `@isminiz.bct` alan adınızı alın, teklif verin ve alım-satım yapın."* (BNS Marketplace ve profil ekranı gösterilir).
4. **23-30 sn (Harekete Geçirici Mesaj / CTA):** *"Bağımsız Layer-1 blokzinciri LockTrace şu an canlıda! Profildeki linkten `locktrace.space`'e girin ve Telegram topluluğumuza katılın!"*

---

## 📋 6. Teknik Referans Özeti (Hızlı Bakış Tablosu)

| Parametre | Değer | Açıklama |
| :--- | :--- | :--- |
| **Ağ Sürümü** | `v2.8.1` | Rust Core Acceleration, Multi-Layer Bridge Hardening, Compact Relay, State Snapshot Fast Sync, GPU Mining |
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

