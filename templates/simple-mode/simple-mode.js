/**
 * ============================================================================
 * BLOCTAG & SPACE — STITCH SIMPLIFIED MOBILE UI ENGINE (v2.12.2)
 * ============================================================================
 * Modular, self-contained Simple Mode implementation based on the Stitch
 * "Kinetic Minimalist Crypto" mobile design system:
 *   - SCR-ONB-01: BlocTag - Hoş Geldiniz & Giriş (/onboarding/welcome)
 *   - SCR-WLT-02: Cüzdan Aç - Anahtar Kelimeler (/wallet/seed-phrase)
 *   - SCR-WLT-HOME: Cüzdanım ve Geçmiş (Mobil) (/wallet/home)
 *   - SCR-WLT-SEND: Para Gönder (Mobil) (/wallet/send)
 *   - SCR-SPC-03: Space - Sade Sosyal Akış (/space/feed - Default)
 *   - SCR-SPC-04: Space - Gönderi Detayı (/space/post/:id)
 *   - SCR-PRF-05: Space - Kullanıcı Profili (/space/profile/:handle)
 *   - SCR-NTF-06: Space - Bildirimler (/notifications)
 *
 * Security & Architecture Guarantees:
 *   - 100% Non-Custodial: Delegates all key generation, AES-256-GCM PIN Vault,
 *     and SECP256k1 ECDSA signing to the core LockTraceCrypto & app engine.
 *   - Strict XSS Defense: All dynamic values pass through escapeHtml() and
 *     sanitizeJsAttr() before rendering.
 *   - Zero Destructive Coupling: Leaves the Pro Mode DOM untouched so the user
 *     can switch between Pro and Simple Mode with an animated transition at any
 *     time, or remove `/simple-mode/` cleanly in the future.
 * ============================================================================
 */
(function () {
  'use strict';

  const SIMPLE_MODE_STORAGE_KEY = 'locktrace_ui_simple_mode_v1';
  const WEB3_ONBOARDING_STORAGE_KEY = 'locktrace_web3_onboarding_choice_v1';
  const PWA_INSTALLED_STORAGE_KEY = 'locktrace_pwa_installed_v1';
  const PWA_BACK_BTN_STORAGE_KEY = 'locktrace_pwa_back_btn_enabled_v1';
  const GATE_LANG_STORAGE_KEY = 'locktrace_gate_lang_v1';

  let _capturedPwaPrompt = null;
  let _mobileGateStep = null; // 'web3' | 'pwa' | 'pwa-installed' | null
  let _pwaManualGuideOpen = false;
  let _pwaInstallWaiting = false;
  let _pwaAutoTriggerPending = false;
  let _iosInstallSheetOpen = false;

  // Eagerly register Service Worker so Chromium fires beforeinstallprompt as fast as possible
  try {
    if ('serviceWorker' in navigator && !navigator.serviceWorker.controller) {
      navigator.serviceWorker.register('/sw.js').catch(() => { });
    }
  } catch (_e) { }

  function isMobileDevice() {
    try {
      const ua = navigator.userAgent || '';
      const mobileUa = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(ua);
      const coarseSmall = Boolean(
        window.matchMedia &&
        window.matchMedia('(pointer: coarse)').matches &&
        window.innerWidth <= 900
      );
      return mobileUa || coarseSmall;
    } catch (_e) {
      return false;
    }
  }

  function isStandalonePwaApp() {
    try {
      return Boolean(
        (window.matchMedia && (
          window.matchMedia('(display-mode: standalone)').matches ||
          window.matchMedia('(display-mode: fullscreen)').matches ||
          window.matchMedia('(display-mode: minimal-ui)').matches
        )) ||
        (window.navigator && window.navigator.standalone === true)
      );
    } catch (_e) {
      return false;
    }
  }

  function isIosDeviceLocal() {
    try {
      const ua = navigator.userAgent || '';
      return /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    } catch (_e) {
      return false;
    }
  }

  function isIosChrome() {
    try {
      return isIosDeviceLocal() && /CriOS/i.test(navigator.userAgent || '');
    } catch (_e) {
      return false;
    }
  }

  function isIosInAppBrowser() {
    try {
      if (!isIosDeviceLocal()) return false;
      const ua = navigator.userAgent || '';
      return /Instagram|FBAN|FBAV|WhatsApp|Telegram|Line\/|TikTok|Snapchat|Twitter|MicroMessenger/i.test(ua);
    } catch (_e) {
      return false;
    }
  }

  function getAvailablePwaPrompt() {
    if (window.__bloctagPwaPrompt) return window.__bloctagPwaPrompt;
    if (_capturedPwaPrompt) return _capturedPwaPrompt;
    try {
      if (typeof deferredPwaPrompt !== 'undefined' && deferredPwaPrompt) {
        return deferredPwaPrompt;
      }
    } catch (_e) { }
    return null;
  }

  // Capture native PWA install prompt & appinstalled event early
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    _capturedPwaPrompt = e;
    window.__bloctagPwaPrompt = e;
    try {
      if (typeof deferredPwaPrompt !== 'undefined') {
        deferredPwaPrompt = e;
      }
    } catch (_err) { }
    _pwaInstallWaiting = false;
    _pwaAutoTriggerPending = false;
    if (_mobileGateStep === 'pwa') {
      renderMobileOnboardingGate('pwa');
    }
  });

  window.addEventListener('appinstalled', () => {
    _capturedPwaPrompt = null;
    window.__bloctagPwaPrompt = null;
    window.__bloctagPwaInstalled = true;
    try {
      localStorage.setItem(PWA_INSTALLED_STORAGE_KEY, 'true');
    } catch (_e) { }
    if (isMobileDevice() && !isStandalonePwaApp()) {
      renderMobileOnboardingGate('pwa-installed');
    }
  });

  let _savedFeedLayout = 'snap';
  try {
    _savedFeedLayout = localStorage.getItem('bloctag_simple_feed_layout') || 'snap';
  } catch (_e) { }

  const simpleState = {
    enabled: false,
    activeScreen: 'SCR-SPC-03', // Default launch screen per Stitch MCP manifest
    screenHistory: ['SCR-SPC-03'],
    feedLayout: _savedFeedLayout, // 'snap' (TikTok/Instagram Reels centered snap) | 'classic' (list)
    feedFilter: 'all',          // 'all' | 'following'
    txFilter: 'all',            // 'all' | 'incoming' | 'outgoing'
    notifFilter: 'all',         // 'all' | 'tips' | 'mentions' | 'likes'
    profileTab: 'posts',        // 'posts' | 'replies' | 'likes' | 'tips'
    profileTarget: '',          // '' means current user
    activePostId: null,
    seedSavedConfirmed: false,
    seedMnemonic: '',
    importModeOpen: false,
    searchBarOpen: false,
    searchQuery: '',
    sendPrefillRecipient: '',
    sendPrefillAmount: '',
    followTab: 'followers',      // 'followers' | 'following'
    followFilter: 'all',         // 'all' | 'mutual' | 'verified'
    followSearch: '',
    followTargetAddr: ''
  };

  // Safe HTML & Attribute Escaping (Defense-in-Depth)
  function esc(str) {
    if (typeof window.escapeHtml === 'function') {
      return window.escapeHtml(str);
    }
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function escAttr(val) {
    if (typeof window.sanitizeJsAttr === 'function') {
      return window.sanitizeJsAttr(val);
    }
    if (val === null || val === undefined) return '';
    return String(val).replace(/[^a-zA-Z0-9._\-@]/g, '');
  }

  function getActiveWallet() {
    try {
      if (typeof currentAccount !== 'undefined' && currentAccount && currentAccount.address) {
        return currentAccount;
      }
    } catch (_e) { }
    return null;
  }

  function getMyPrimaryHandle() {
    try {
      const stored = localStorage.getItem('locktrace_primary_bns');
      if (stored) return stored.replace(/^@/, '');
      if (typeof currentBnsHandle === 'string' && currentBnsHandle) {
        return currentBnsHandle.replace(/^@/, '');
      }
      if (typeof bnsMyHandlesCache !== 'undefined' && Array.isArray(bnsMyHandlesCache) && bnsMyHandlesCache.length > 0) {
        const first = bnsMyHandlesCache[0];
        const h = typeof first === 'string' ? first : (first && first.name ? first.name : '');
        if (h) return h.replace(/^@/, '');
      }
      const acc = getActiveWallet();
      if (acc && acc.bns_name) return String(acc.bns_name).replace(/^@/, '');
    } catch (_e) { }
    return '';
  }

  function getMyOwnedBnsHandles() {
    const list = new Set();
    try {
      const stored = localStorage.getItem('locktrace_primary_bns');
      if (stored) list.add(stored.replace(/^@/, ''));
      const primary = getMyPrimaryHandle();
      if (primary) list.add(primary.replace(/^@/, ''));
      if (typeof currentBnsHandle !== 'undefined' && currentBnsHandle) {
        list.add(String(currentBnsHandle).replace(/^@/, ''));
      }
      const acc = getActiveWallet();
      if (acc && acc.bns_name) {
        list.add(String(acc.bns_name).replace(/^@/, ''));
      }
      if (typeof bnsMyHandlesCache !== 'undefined' && Array.isArray(bnsMyHandlesCache)) {
        bnsMyHandlesCache.forEach(x => {
          const h = typeof x === 'string' ? x : (x && x.name ? x.name : '');
          if (h) list.add(String(h).replace(/^@/, ''));
        });
      }
      if (typeof window.myBnsNames !== 'undefined' && Array.isArray(window.myBnsNames)) {
        window.myBnsNames.forEach(x => {
          if (x) list.add(String(x).replace(/^@/, ''));
        });
      }
    } catch (_e) { }
    return Array.from(list).filter(Boolean);
  }

  function getDisplayHandleOrAddr(addr, bns) {
    if (bns && bns !== 'anonymous') {
      const clean = String(bns).replace(/^@/, '');
      return '@' + clean;
    }
    if (!addr) return '@kullanici';
    const s = String(addr).trim();
    if (s.length <= 14) return s;
    return s.slice(0, 6) + '...' + s.slice(-4);
  }

  function getUnreadNotificationsCount() {
    try {
      const raw = localStorage.getItem('locktrace_notifications_v1');
      if (!raw) return 0;
      const list = JSON.parse(raw);
      if (!Array.isArray(list)) return 0;
      return list.filter(n => n && !n.read).length;
    } catch (_e) {
      return 0;
    }
  }

  function getStoredNotifications() {
    try {
      const raw = localStorage.getItem('locktrace_notifications_v1');
      if (!raw) return [];
      const list = JSON.parse(raw);
      return Array.isArray(list) ? list : [];
    } catch (_e) {
      return [];
    }
  }

  // ==========================================================================
  // 1. PERSISTENCE & MODE TOGGLE CONTROLLER
  // ==========================================================================
  function isSimpleModeEnabled() {
    try {
      const v = localStorage.getItem(SIMPLE_MODE_STORAGE_KEY);
      return v === 'true' || v === '1';
    } catch (_e) {
      return false;
    }
  }

  function syncModeToggleControls(enabled) {
    const checkboxes = [
      document.getElementById('settingSimpleModeToggle'),
      document.getElementById('settingSimpleModeVault'),
      document.getElementById('settingSimpleModeFeed')
    ];
    checkboxes.forEach(cb => {
      if (cb) cb.checked = Boolean(enabled);
    });

    const pillSwitches = document.querySelectorAll('.bloctag-mode-pill-switch');
    pillSwitches.forEach(sw => {
      sw.classList.toggle('is-simple', Boolean(enabled));
      const proOpt = sw.querySelector('[data-mode-opt="pro"]');
      const simpleOpt = sw.querySelector('[data-mode-opt="simple"]');
      if (proOpt) {
        proOpt.className = 'bloctag-mode-pill-option ' + (!enabled ? 'active-pro' : 'text-on-surface-variant');
      }
      if (simpleOpt) {
        simpleOpt.className = 'bloctag-mode-pill-option ' + (enabled ? 'active-simple' : 'text-on-surface-variant');
      }
    });

    const badgeEls = document.querySelectorAll('.bloctag-active-mode-badge');
    badgeEls.forEach(b => {
      b.textContent = enabled ? 'SIMPLE MODE' : 'PRO MODE';
      b.className = 'bloctag-active-mode-badge px-2 py-0.5 rounded-full font-mono text-[9.5px] font-bold transition-all ' +
        (enabled ? 'bg-primary text-on-primary shadow-xs' : 'bg-surface-container-highest text-on-surface-variant');
    });
  }

  function ensureSimpleModeShell() {
    let shell = document.getElementById('bloctag-simple-mode-shell');
    if (!shell) {
      shell = document.createElement('div');
      shell.id = 'bloctag-simple-mode-shell';
      shell.setAttribute('aria-label', 'BlocTag Simple Mode Interface');
      document.body.appendChild(shell);
    }
    let navPortal = document.getElementById('bloctag-simple-bottom-nav-portal');
    if (!navPortal) {
      navPortal = document.createElement('div');
      navPortal.id = 'bloctag-simple-bottom-nav-portal';
      document.body.appendChild(navPortal);
    }
    return shell;
  }

  // Pro Mode Switch Confirmation Modal (shown when navigating to Pro pages from Simple Mode)
  let _pendingProTargetTab = null;
  const PRO_TAB_LABELS = {
    'ana-sayfa': 'Ana Sayfa (Pro Genel Bakış)',
    'ag-ve-explorer': 'Ağ & Blok Explorer',
    'dugum-paneli': 'Node & Validator Paneli',
    'system-wallets': 'Sistem Cüzdanları & Hazine',
    'kopru': 'Base Köprü (Bridge)',
    'bns': 'BNS İsim Pazarı (.bct)',
    'api-docs': 'Geliştirici API & Dokümantasyon',
    'guvenlik': 'Güvenlik & Kriptografi'
  };

  function requestSwitchToProMode(targetTab = null) {
    _pendingProTargetTab = targetTab || null;

    // Close mobile menu drawer if open so the confirmation modal is clearly visible
    try {
      const mobMenu = document.getElementById('mobileMenuModal');
      if (mobMenu && !mobMenu.classList.contains('hidden') && typeof window.closeMobileMenuModal === 'function') {
        window.closeMobileMenuModal();
      }
    } catch (_e) { }

    let modal = document.getElementById('bloctag-pro-confirm-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'bloctag-pro-confirm-modal';
      modal.className = 'hidden fixed inset-0 z-[95] bg-black/75 backdrop-blur-md items-center justify-center p-4';
      document.body.appendChild(modal);
    }

    const pageName = targetTab && PRO_TAB_LABELS[targetTab] ? PRO_TAB_LABELS[targetTab] : '';
    const descHtml = pageName
      ? `<strong class="text-primary">${esc(pageName)}</strong> sayfası Pro Mod arayüzünde yer almaktadır. Pro Moda geçmek istediğinizden emin misiniz?`
      : 'Tam protokol araçlarına erişmek için <strong class="text-primary">Pro Mod</strong> arayüzüne geçmek istediğinizden emin misiniz?';

    modal.innerHTML = `
      <div class="w-full max-w-[360px] rounded-3xl bg-surface-container border border-outline-variant/25 shadow-2xl p-5 flex flex-col gap-4 animate-fade-in" onclick="event.stopPropagation()">
        <div class="flex items-center gap-3">
          <div class="w-11 h-11 rounded-2xl bg-primary/15 border border-primary/30 text-primary flex items-center justify-center shrink-0">
            <span class="material-symbols-outlined notranslate text-[24px]" translate="no">bolt</span>
          </div>
          <div class="flex flex-col min-w-0">
            <h3 class="text-base font-bold text-on-surface leading-tight">Pro Moda Geçilsin mi?</h3>
            <span class="text-[11px] font-mono text-on-surface-variant">Simple Mod → Pro Mod</span>
          </div>
        </div>
        <p class="text-xs text-on-surface-variant leading-relaxed">
          ${descHtml}
        </p>
        <div class="grid grid-cols-2 gap-2.5 pt-1">
          <button type="button" onclick="window.BlocTagSimpleMode.cancelProSwitch()"
            class="h-11 rounded-2xl bg-surface-container-high hover:bg-surface-bright text-on-surface text-xs font-semibold transition-all active:scale-95 cursor-pointer">
            Vazgeç
          </button>
          <button type="button" onclick="window.BlocTagSimpleMode.confirmProSwitch()"
            class="h-11 rounded-2xl bg-primary text-on-primary text-xs font-bold flex items-center justify-center gap-1.5 hover:brightness-95 transition-all active:scale-95 shadow-sm cursor-pointer">
            <span class="material-symbols-outlined notranslate text-[16px]" translate="no">bolt</span>
            <span>Pro Moda Geç</span>
          </button>
        </div>
      </div>
    `;
    modal.onclick = () => cancelSwitchToProMode();
    modal.classList.remove('hidden');
    modal.classList.add('flex');
  }

  function cancelSwitchToProMode() {
    _pendingProTargetTab = null;
    const modal = document.getElementById('bloctag-pro-confirm-modal');
    if (modal) {
      modal.classList.add('hidden');
      modal.classList.remove('flex');
    }
  }

  function confirmSwitchToProMode() {
    const targetTab = _pendingProTargetTab;
    cancelSwitchToProMode();
    toggleSimpleModeSetting(false);
    if (targetTab && typeof window._origSwitchTab === 'function') {
      setTimeout(() => {
        window._origSwitchTab(targetTab, true, true);
      }, 40);
    }
  }

  // ── Language Selector Modal & Preferences (SCR-MNU-07) ───────────────────────
  const SIMPLE_LANGUAGES = [
    { code: 'en', flag: '🌐', name: 'English (Default)', desc: 'Official international interface' },
    { code: 'tr', flag: '🇹🇷', name: 'Türkçe', desc: 'Türkçe kullanıcı arayüzü' },
    { code: 'az', flag: '🇦🇿', name: 'Azərbaycanca', desc: 'Azərbaycan dili interfeysi' },
    { code: 'ru', flag: '🇷🇺', name: 'Русский', desc: 'Русскоязычный интерфейс' },
    { code: 'de', flag: '🇩🇪', name: 'Deutsch', desc: 'Deutsche Benutzeroberfläche' },
    { code: 'es', flag: '🇪🇸', name: 'Español', desc: 'Interfaz en español' },
    { code: 'fr', flag: '🇫🇷', name: 'Français', desc: 'Interface en français' },
    { code: 'ar', flag: '🇸🇦', name: 'العربية', desc: 'الواجهة العربية (RTL)' },
  ];

  const SIMPLE_I18N = {
    tr: {
      nav_space: 'Space',
      nav_wallet: 'Cüzdan',
      nav_profile: 'Profil',
      nav_menu: 'Menü',
      top_welcome: 'BlocTag',
      top_recovery: 'Kurtarma Anahtarı',
      top_wallet: 'Cüzdanım',
      top_send: 'Kripto Gönder',
      top_space: 'BlocTag Space',
      top_post_detail: 'Gönderi Detayı',
      top_profile: 'Profil',
      top_notifications: 'Bildirimler',
      top_menu: 'Menü',
      onb_title_1: 'Kripto ve Topluluk',
      onb_title_2: 'Tek Bir Yerde.',
      onb_sub: 'Karmaşık terimler yok. Tek tıkla cüzdan oluşturun, varlıklarınızı yönetin ve Space ile Web3 topluluklarına katılın.',
      onb_feat1_title: 'Kolay & Güvenli',
      onb_feat1_desc: 'Kendi anahtarınız, tam kontrolünüz. Aracı kurum veya riskli sunucular olmadan doğrudan cihazınızda saklanır.',
      onb_feat2_title: 'BlocTag Kimliği',
      onb_feat2_badge: 'Yeni',
      onb_feat2_desc: 'Uzun, karmaşık 42 karakterlik adresler yerine sade kullanıcı adınızı kullanın (örn. @kullanici.bct).',
      onb_feat3_title: 'Space Topluluğu',
      onb_feat3_desc: 'Doğrulanmış token sahipleriyle fikir paylaşın, projeleri keşfedin ve içerik üreticilerini tek tıkla ödüllendirin.',
      onb_import_title: '12 Kelime veya Özel Anahtar ile Bağlan',
      onb_import_ph: '12 kurtarma kelimenizi veya 64 haneli özel anahtarınızı girin...',
      onb_import_btn: 'Cüzdanı Geri Yükle ve Bağlan',
      onb_create_btn: 'Cüzdan Aç (+1.00 BCT Bonus)',
      onb_existing_btn: 'Mevcut Cüzdanla Bağlan',
      onb_footer: 'Uçtan Uca Şifreli • Non-Custodial Güvenlik',
      seed_hero_title: 'Cüzdan Anahtarlarınız',
      seed_hero_sub: 'Bu 12 kelime cüzdanınızın tek şifresidir. Güvenli bir yere not edin ve kimseyle paylaşmayın.',
      seed_tip: 'Etrafınızda kimsenin izlemediğinden emin olun',
      seed_private: 'Gizli',
      seed_copy_btn: 'Kelimeleri Kopyala',
      seed_copied_toast: '12 kurtarma kelimesi kopyalandı!',
      seed_rec_title: 'Tavsiye Edilen Yöntem',
      seed_rec_desc: 'Kelimeleri tercihen fiziksel bir kağıda yazın ve güvenli bir yerde saklayın. Ekran görüntüsü almaktan kaçının.',
      seed_saved_label: 'Kelimelerimi güvenli bir yere kaydettim',
      seed_saved_sub: 'Kurtarma kelimelerim olmadan hesabıma erişemem',
      seed_launch_btn: "Cüzdanı Başlat & Space'e Git (+1.00 BCT)",
      seed_footer: 'Merkeziyetsiz ve bağımsız mülkiyet protokolü',
      seed_refresh_title: 'Yeni Kelime Üret',
      wlt_net_worth: 'Net Portföy Değeri',
      wlt_balance_title: 'Toplam Varlık',
      wlt_send_btn: 'Gönder',
      wlt_receive_btn: 'Al (QR)',
      wlt_vault_btn: 'PIN Kasası',
      wlt_switch_wallet: 'Cüzdan Değiştir',
      wlt_audit_btn: 'Ağ Güvenliği',
      wlt_txs_title: 'İşlem Geçmişi',
      wlt_filter_all: 'Tümü',
      wlt_filter_in: 'Gelenler',
      wlt_filter_out: 'Gidenler',
      wlt_empty_txs: 'Bu filtrede henüz işlem bulunmuyor.',
      wlt_tx_pending: 'Mempool',
      wlt_tx_confirmed: 'Onaylandı',
      send_badge: 'İşlem',
      send_title: 'BCT Gönder',
      send_fast_mode: 'Hızlı Mod',
      send_active_asset: 'Aktif Varlık',
      send_recipient: 'Alıcı Adresi veya .bct İsmi',
      send_recipient_label: 'Alıcı Adresi veya @isim.bct',
      send_recipient_ph: 'BCT... veya kullanici.bct',
      send_paste: 'Yapıştır',
      send_qr_scan: 'QR Tara',
      send_amount: 'Gönderilecek Miktar',
      send_available: 'Kullanılabilir:',
      send_net_received: 'Net Alıcıya Geçen:',
      send_pct_all: 'Tümü',
      send_network_fee: 'Ağ Ücreti (%1 Protokol):',
      send_zero_fee: 'Ağ Ücreti: 0.00 BCT (Sıfır Komisyon)',
      send_instant_conf: 'Anlık Onay',
      send_submit: 'Devam Et ve İmzala',
      send_submit_btn: 'Devam Et ve İmzala',
      send_ecdsa_signed: 'Uçtan Uca ECDSA İmzalı',
      send_instant_block: 'Anlık Blok Kaydı',
      space_ph: 'Bir şeyler paylaş... (0.10 BCT)',
      space_composer_ph: 'Bir şeyler paylaş... (0.10 BCT)',
      space_publish: 'Paylaş',
      space_filter_all: 'Hepsi',
      space_filter_following: 'Doğrulanmış & Takip',
      space_empty: 'Henüz zincir üstü gönderi paylaşılmamış.',
      space_empty_posts: 'Gönderiler yükleniyor veya bu filtrede gönderi yok...',
      space_like: 'Beğen',
      space_liked: 'Beğenildi',
      space_reply: 'Yorum',
      space_share: 'Paylaş',
      space_tip: 'Bahşiş',
      space_follow: 'Takip Et',
      space_active_l1: 'Aktif L1',
      space_compose_fab: 'Yaz',
      space_create_wallet_hint: 'Cüzdan oluşturun (+1.00 BCT bonus)',
      space_search_ph: 'Gönderi, #etiket veya @kullanici ara...',
      space_search_btn: 'Arama',
      space_share_btn: 'Paylaş',
      post_not_found: 'Gönderi bulunamadı veya yükleniyor.',
      post_back_to_feed: 'Space Akışına Dön',
      post_block_label: 'Blok',
      post_likes_label: 'Beğeni',
      post_comments_label: 'Yorum',
      post_royalties_label: 'Telif',
      post_comments_title: 'Yorumlar',
      post_author_royalty_hint: '+0.004 BCT Yazar Telifi',
      post_be_first_comment: 'İlk zincir üstü yorumu aşağıdan siz yazın!',
      post_comment_ph: 'Düşünceni yaz... (0.02 BCT)',
      post_comment_send: 'Gönder',
      profile_security_btn: 'Güvenlik',
      profile_follow_btn: 'Takip Et',
      profile_tip_btn: 'Bahşiş',
      profile_bns_title: 'Kayıtlı BNS İsimleriniz (.bct)',
      profile_bns_count: 'isim',
      profile_bns_hint: 'Profilinizde ve paylaşımlarınızda görünecek aktif kimliğinizi seçin:',
      profile_bns_active: '(Aktif)',
      profile_bns_none: 'Henüz bir .bct alan adı almadınız. Cüzdan adresiniz yerine havalı bir isim kullanın.',
      profile_bns_claim: 'İsim Al',
      profile_bio: 'Doğrulanmış BlocTag Space üreticisi ✦ Sansüre dayanıklı Layer-1 blokzincir üzerinde içerik paylaşıyor ve anlık telif kazanıyor.',
      profile_stat_posts: 'Gönderi',
      profile_stat_likes: 'Beğeni',
      profile_stat_followers: 'Takipçi',
      profile_stat_following: 'Takip',
      profile_tab_posts: 'Gönderiler',
      profile_tab_popular: 'Popüler',
      profile_empty_posts: 'Henüz zincir üstü gönderi paylaşılmamış.',
      profile_view_followers: 'Takipçileri Görüntüle',
      profile_view_following: 'Takip Edilenleri Görüntüle',
      connections_title: 'Bağlantılı Hesaplar',
      live_network_community: 'Canlı Ağ • Topluluk',
      filter_all: 'Tümü',
      filter_mutual: 'Karşılıklı Takip',
      filter_verified: 'Doğrulanmış',
      follows_you: 'Seni takip ediyor',
      follow_back: 'Geri Takip',
      btn_following: 'Takip Ediliyor',
      btn_follow: 'Takip Et',
      no_users_found: 'Sonuç bulunamadı',
      no_users_found_desc: 'Aradığınız kriterlere uygun kullanıcı bulunamadı. Filtreleri sıfırlayabilirsiniz.',
      search_users_placeholder: 'Kullanıcı adı veya cüzdan ara...',
      user_self_tag: 'Sen',
      followers_empty_title: 'Henüz takipçi yok',
      followers_empty_desc: 'Space üzerinde düşüncelerinizi paylaşarak zincir üstü takipçi kitlenizi oluşturun.',
      following_empty_title: 'Henüz kimse takip edilmiyor',
      following_empty_desc: 'Space akışındaki üreticileri keşfedip takip ederek gönderilerini kaçırmayın.',
      loading_connections: 'Zincir üstü bağlantılar yükleniyor...',
      querying_ledger: 'Kriptografik defter ve merkeziyetsiz ağ sorgulanıyor...',
      switch_to_main_feed: 'Ana Space Akışına Geç',
      switched_to_main_feed_toast: 'Ana Space akışına geçildi',
      feed_layout_snap: 'Reels / TikTok Görünümü',
      feed_layout_list: 'Liste Görünümü',
      swipe_up_hint: 'Sonraki için yukarı kaydır',
      feed_reached_end: 'Tüm gönderileri gördünüz',
      notif_new_badge: 'yeni',
      notif_mark_all: 'Okundu Say',
      notif_all: 'Tümü',
      notif_tips: 'Transfer & Bahşiş',
      notif_mentions: 'Space & Yanıtlar',
      notif_system: 'Sistem',
      notif_empty_title: 'Henüz bildirim yok',
      notif_empty_desc: 'Gönderilerinize etkileşim geldiğinde veya token transferi olduğunda burada görünecektir.',
      menu_not_connected: 'Cüzdan bağlı değil',
      menu_wallet: 'Cüzdanım',
      menu_profile: 'Profilim',
      menu_validator: 'VALİDATOR',
      menu_pro_title: 'Pro Mod (Tam Görünüm)',
      menu_pro_desc: 'Ağ Explorer, Düğümler ve Geliştirici Araçları',
      menu_pro_switch: 'Geçiş Yap',
      menu_services: 'İşlemler & Hizmetler',
      menu_send: 'Kripto Gönder',
      menu_send_desc: 'Sıfır komisyonlu anında BCT transferi',
      menu_bns: 'BNS Kullanıcı Adı (.bct)',
      menu_bns_desc: 'Kimlik ve Web3 profilinizi yönetin',
      menu_sec: 'Güvenlik & Kurtarma Anahtarı',
      menu_sec_desc: '12 kelimelik gizli kurtarma ifadesi (Seed Phrase)',
      menu_notif: 'Bildirimler & Uyarılar',
      menu_notif_desc: 'İşlem ve Space güncellemeleri',
      menu_lang: 'Dil Seçimi (Language)',
      menu_lang_desc: 'Uygulama arayüz dili',
      menu_wp: 'LockTrace Whitepaper',
      menu_wp_desc: 'Protokol mimarisi ve teknik dokümantasyon',
      lang_modal_title: 'Dil Seçimi (Language)',
      lang_modal_sub: 'Uygulama dilinizi belirleyin',
      lang_modal_hint: 'Tarayıcınızın Çevir (Translate) özelliği ve çok dilli PWA desteği ile tam uyumludur.'
    },
    az: {
      nav_space: 'Space',
      nav_wallet: 'Cüzdan',
      nav_profile: 'Profil',
      nav_menu: 'Menyu',
      top_welcome: 'BlocTag',
      top_recovery: 'Bərpa Açarı',
      top_wallet: 'Cüzdanım',
      top_send: 'Kripto Göndər',
      top_space: 'BlocTag Space',
      top_post_detail: 'Paylaşım Detalı',
      top_profile: 'Profil',
      top_notifications: 'Bildirişlər',
      top_menu: 'Menyu',
      onb_title_1: 'Kripto və İcma',
      onb_title_2: 'Tək Bir Yerdə.',
      onb_sub: 'Mürəkkəb terminlər yoxdur. Bir kliklə cüzdan yaradın, aktivlərinizi idarə edin və Space ilə Web3 icmalarına qoşulun.',
      onb_feat1_title: 'Asan və Təhlükəsiz',
      onb_feat1_desc: 'Öz açarınız, tam nəzarətiniz. Vasitəçilər olmadan birbaşa cihazınızda saxlanılır.',
      onb_feat2_title: 'BlocTag Kimliyi',
      onb_feat2_badge: 'Yeni',
      onb_feat2_desc: 'Uzun 42 simvollu ünvanlar yerinə sadə istifadəçi adınızı istifadə edin (məs. @istifadeci.bct).',
      onb_feat3_title: 'Space İcması',
      onb_feat3_desc: 'Təsdiqlənmiş istifadəçilərlə fikir paylaşın, layihələri kəşf edin və müəlliflərə bəxşiş göndərin.',
      onb_import_title: '12 Söz və ya Şəxsi Açar ilə Bərpa',
      onb_import_ph: '12 bərpa sözünüzü və ya şəxsi açarınızı daxil edin...',
      onb_import_btn: 'Cüzdanı Bərpa Et və Daxil Ol',
      onb_create_btn: 'Cüzdan Yarat (+1.00 BCT Bonus)',
      onb_existing_btn: 'Mövcud Cüzdanla Daxil Ol',
      onb_footer: 'Ucdan-Uca Şifrələnmiş • Non-Custodial Təhlükəsizlik',
      seed_hero_title: 'Cüzdan Açarlarınız',
      seed_hero_sub: 'Bu 12 söz cüzdanınızın tək şifrəsidir. Təhlükəsiz yerdə saxlayın və heç kimlə bölüşməyin.',
      seed_tip: 'Ətrafınızda heç kimin baxmadığından əmin olun',
      seed_private: 'Məxfi',
      seed_copy_btn: 'Sözləri Kopyala',
      seed_copied_toast: '12 bərpa sözü kopyalandı!',
      seed_rec_title: 'Tövsiyə Edilən Metod',
      seed_rec_desc: 'Sözləri kağıza yazın və etibarlı yerdə saxlayın. Ekran görüntüsü çəkməkdən çəkinin.',
      seed_saved_label: 'Sözlərimi təhlükəsiz yerdə saxladım',
      seed_saved_sub: 'Bərpa sözlərim olmadan cüzdanıma daxil ola bilmərəm',
      seed_launch_btn: "Cüzdanı Başlat & Space-ə Get (+1.00 BCT)",
      seed_footer: 'Mərkəzsiz və müstəqil mülkiyyət protokolu',
      seed_refresh_title: 'Yeni Sözlər Yarat',
      wlt_net_worth: 'Net Portfel Dəyəri',
      wlt_balance_title: 'Ümumi Balans',
      wlt_send_btn: 'Göndər',
      wlt_receive_btn: 'Qəbul Et (QR)',
      wlt_vault_btn: 'PIN Kassası',
      wlt_switch_wallet: 'Cüzdanı Dəyiş',
      wlt_audit_btn: 'Şəbəkə Təhlükəsizliyi',
      wlt_txs_title: 'Əməliyyat Tarixçəsi',
      wlt_filter_all: 'Hamısı',
      wlt_filter_in: 'Gələnlər',
      wlt_filter_out: 'Gedənlər',
      wlt_empty_txs: 'Bu filtrdə hələ ki əməliyyat qeydi yoxdur.',
      wlt_tx_pending: 'Mempool',
      wlt_tx_confirmed: 'Təsdiqləndi',
      send_badge: 'Əməliyyat',
      send_title: 'BCT Göndər',
      send_fast_mode: 'Sürətli Rejim',
      send_active_asset: 'Aktiv Varlıq',
      send_recipient: 'Qəbuledici Ünvanı və ya .bct Adı',
      send_recipient_label: 'Qəbuledici Ünvanı və ya @ad.bct',
      send_recipient_ph: 'BCT... və ya istifadeci.bct',
      send_paste: 'Yapışdır',
      send_qr_scan: 'QR Skan',
      send_amount: 'Göndəriləcək Məbləğ',
      send_available: 'Mövcud:',
      send_net_received: 'Qəbulediciyə Çatan Xalis:',
      send_pct_all: 'Hamısı',
      send_network_fee: 'Şəbəkə Haqqı (%1 Protokol):',
      send_zero_fee: 'Şəbəkə Haqqı: 0.00 BCT (Komissiyasız)',
      send_instant_conf: 'Ani Təsdiq',
      send_submit: 'Davam Et və İmzala',
      send_submit_btn: 'Davam Et və İmzala',
      send_ecdsa_signed: 'Ucdan-Uca ECDSA İmzalı',
      send_instant_block: 'Ani Blok Qeydiyyatı',
      space_ph: 'Bir şeylər paylaşın... (0.10 BCT)',
      space_composer_ph: 'Bir şeylər paylaşın... (0.10 BCT)',
      space_publish: 'Paylaş',
      space_filter_all: 'Hamısı',
      space_filter_following: 'Təsdiqlənmiş & İzlənilən',
      space_empty: 'Hələ zəncir üzərində paylaşım edilməyib.',
      space_empty_posts: 'Paylaşımlar yüklənir və ya bu filtrdə paylaşım yoxdur...',
      space_like: 'Bəyən',
      space_liked: 'Bəyənildi',
      space_reply: 'Şərh',
      space_share: 'Paylaş',
      space_tip: 'Bəxşiş',
      space_follow: 'İzlə',
      space_active_l1: 'Aktiv L1',
      space_compose_fab: 'Yaz',
      space_create_wallet_hint: 'Cüzdan yaradın (+1.00 BCT bonus)',
      space_search_ph: 'Paylaşım, #teq və ya @istifadəçi axtar...',
      space_search_btn: 'Axtarış',
      space_share_btn: 'Paylaş',
      post_not_found: 'Paylaşım tapılmadı və ya yüklənir.',
      post_back_to_feed: 'Space Axınına Qayıt',
      post_block_label: 'Blok',
      post_likes_label: 'Bəyənmə',
      post_comments_label: 'Şərh',
      post_royalties_label: 'Qonorar',
      post_comments_title: 'Şərhlər',
      post_author_royalty_hint: '+0.004 BCT Müəllif Qonorarı',
      post_be_first_comment: 'İlk zəncir üzərində şərhi aşağıdan siz yazın!',
      post_comment_ph: 'Fikrinizi yazın... (0.02 BCT)',
      post_comment_send: 'Göndər',
      profile_security_btn: 'Təhlükəsizlik',
      profile_follow_btn: 'İzlə',
      profile_tip_btn: 'Bəxşiş',
      profile_bns_title: 'Qeydiyyatdan Keçmiş BNS Adlarınız (.bct)',
      profile_bns_count: 'ad',
      profile_bns_hint: 'Profilinizdə və Space paylaşımlarınızda görünəcək aktiv kimliyinizi seçin:',
      profile_bns_active: '(Aktiv)',
      profile_bns_none: 'Hələ .bct adı almamısınız. Cüzdan ünvanı yerinə gözəl bir ad istifadə edin.',
      profile_bns_claim: 'Ad Al',
      profile_bio: 'Təsdiqlənmiş BlocTag Space müəllifi ✦ Senzuraya davamlı Layer-1 blokçeynində məzmun paylaşır və ani qonorar qazanır.',
      profile_stat_posts: 'Paylaşım',
      profile_stat_likes: 'Bəyənmə',
      profile_stat_followers: 'İzləyici',
      profile_stat_following: 'İzlənilən',
      profile_tab_posts: 'Paylaşımlar',
      profile_tab_popular: 'Populyar',
      profile_empty_posts: 'Hələ zəncir üzərində paylaşım edilməyib.',
      profile_view_followers: 'İzləyicilərə Bax',
      profile_view_following: 'İzlənilənlərə Bax',
      connections_title: 'Əlaqəli Hesablar',
      live_network_community: 'Canlı Şəbəkə • İcma',
      filter_all: 'Hamısı',
      filter_mutual: 'Qarşılıqlı İzləmə',
      filter_verified: 'Təsdiqlənmiş',
      follows_you: 'Sizi izləyir',
      follow_back: 'Geri İzlə',
      btn_following: 'İzlənilir',
      btn_follow: 'İzlə',
      no_users_found: 'İstifadəçi tapılmadı',
      no_users_found_desc: 'Axtarış meyarlarına uyğun istifadəçi tapılmadı. Filtrləri sıfırlaya bilərsiniz.',
      search_users_placeholder: 'İstifadəçi adı və ya cüzdan axtar...',
      user_self_tag: 'Siz',
      loading_connections: 'Zəncir üzərindəki əlaqələr yüklənir...',
      querying_ledger: 'Kriptoqrafik dəftər və mərkəzsiz şəbəkə sorğulanır...',
      switch_to_main_feed: 'Əsas Space Axınına Keç',
      switched_to_main_feed_toast: 'Əsas Space axınına keçildi',
      feed_layout_snap: 'Reels / TikTok Görünüşü',
      feed_layout_list: 'Siyahı Görünüşü',
      swipe_up_hint: 'Növbəti üçün yuxarı sürüşdürün',
      feed_reached_end: 'Bütün paylaşımları gördünüz',
      notif_new_badge: 'yeni',
      notif_mark_all: 'Oxunmuş Say',
      notif_all: 'Hamısı',
      notif_tips: 'Köçürmə & Bəxşiş',
      notif_mentions: 'Space & Cavablar',
      notif_system: 'Sistem',
      notif_empty_title: 'Hələ bildiriş yoxdur',
      notif_empty_desc: 'Paylaşımlarınıza qarşılıqlı əlaqə gəldikdə və ya köçürmə olduqda burada görünəcək.',
      menu_not_connected: 'Cüzdan qoşulmayıb',
      menu_wallet: 'Cüzdanım',
      menu_profile: 'Profilim',
      menu_validator: 'VALİDATOR',
      menu_pro_title: 'Pro Rejim (Tam Görünüş)',
      menu_pro_desc: 'Blok Explorer, Node və Tərtibatçı Alətləri',
      menu_pro_switch: 'Keçid Et',
      menu_services: 'Əməliyyatlar & Xidmətlər',
      menu_send: 'Kripto Göndər',
      menu_send_desc: 'Komissiyasız ani BCT köçürməsi',
      menu_bns: 'BNS İstifadəçi Adı (.bct)',
      menu_bns_desc: 'Kimlik və Web3 profilinizi idarə edin',
      menu_sec: 'Təhlükəsizlik & Bərpa Açarı',
      menu_sec_desc: '12 sözlük gizli bərpa ifadəsi (Seed Phrase)',
      menu_notif: 'Bildirişlər & Xəbərdarlıqlar',
      menu_notif_desc: 'Əməliyyat və Space yenilikləri',
      menu_lang: 'Dil Seçimi (Language)',
      menu_lang_desc: 'Tətbiq interfeys dili',
      menu_wp: 'LockTrace Whitepaper',
      menu_wp_desc: 'Protokol arxitekturası və texniki sənədlər',
      lang_modal_title: 'Dil Seçimi (Language)',
      lang_modal_sub: 'Tətbiq dilinizi seçin',
      lang_modal_hint: 'Brauzerinizin tərcümə funksiyası və çoxdilli PWA ilə tam uyğundur.'
    },
    ru: {
      nav_space: 'Space',
      nav_wallet: 'Кошелек',
      nav_profile: 'Профиль',
      nav_menu: 'Меню',
      top_welcome: 'BlocTag',
      top_recovery: 'Ключи восстановления',
      top_wallet: 'Мой кошелек',
      top_send: 'Отправить крипту',
      top_space: 'BlocTag Space',
      top_post_detail: 'Детали публикации',
      top_profile: 'Профиль',
      top_notifications: 'Уведомления',
      top_menu: 'Меню',
      onb_title_1: 'Криптовалюта и сообщество',
      onb_title_2: 'В одном месте.',
      onb_sub: 'Без сложных терминов. Создайте кошелек в один клик, управляйте активами и присоединяйтесь к Web3-сообществам Space.',
      onb_feat1_title: 'Просто и безопасно',
      onb_feat1_desc: 'Ваши ключи — ваш полный контроль. Хранятся прямо на вашем устройстве без посредников.',
      onb_feat2_title: 'Имя BlocTag',
      onb_feat2_badge: 'Новое',
      onb_feat2_desc: 'Используйте простое имя вместо 42-значных адресов (например, @user.bct).',
      onb_feat3_title: 'Сообщество Space',
      onb_feat3_desc: 'Делитесь мыслями, открывайте децентрализованные проекты и отправляйте чаевые создателям.',
      onb_import_title: 'Восстановление по 12 словам или ключу',
      onb_import_ph: 'Введите 12 слов восстановления или приватный ключ...',
      onb_import_btn: 'Восстановить кошелек и войти',
      onb_create_btn: 'Создать кошелек (+1.00 BCT Бонус)',
      onb_existing_btn: 'Войти с существующим кошельком',
      onb_footer: 'Сквозное шифрование • Полный контроль (Non-Custodial)',
      seed_hero_title: 'Ключи вашего кошелька',
      seed_hero_sub: 'Эти 12 слов — единственный пароль к вашему кошельку. Запишите их и никому не показывайте.',
      seed_tip: 'Убедитесь, что никто не смотрит на экран',
      seed_private: 'Секретно',
      seed_copy_btn: 'Скопировать слова',
      seed_copied_toast: '12 слов восстановления скопированы!',
      seed_rec_title: 'Рекомендуемый способ',
      seed_rec_desc: 'Запишите слова на бумаге и храните в надежном месте. Избегайте скриншотов.',
      seed_saved_label: 'Я сохранил слова в надежном месте',
      seed_saved_sub: 'Без этих слов восстановить доступ к кошельку невозможно',
      seed_launch_btn: 'Запустить кошелек и перейти в Space (+1.00 BCT)',
      seed_footer: 'Децентрализованный протокол суверенного владения',
      seed_refresh_title: 'Сгенерировать новые слова',
      wlt_net_worth: 'Чистая стоимость портфеля',
      wlt_balance_title: 'Общий баланс',
      wlt_send_btn: 'Отправить',
      wlt_receive_btn: 'Получить (QR)',
      wlt_vault_btn: 'Сейф PIN',
      wlt_switch_wallet: 'Сменить кошелек',
      wlt_audit_btn: 'Безопасность сети',
      wlt_txs_title: 'История транзакций',
      wlt_filter_all: 'Все',
      wlt_filter_in: 'Входящие',
      wlt_filter_out: 'Исходящие',
      wlt_empty_txs: 'В этом фильтре транзакций пока нет.',
      wlt_tx_pending: 'В мемпуле',
      wlt_tx_confirmed: 'Подтверждено',
      send_badge: 'Транзакция',
      send_title: 'Отправить BCT',
      send_fast_mode: 'Быстрый режим',
      send_active_asset: 'Активный актив',
      send_recipient: 'Адрес получателя или имя .bct',
      send_recipient_label: 'Адрес получателя или @имя.bct',
      send_recipient_ph: 'BCT... или user.bct',
      send_paste: 'Вставить',
      send_qr_scan: 'Сканировать QR',
      send_amount: 'Сумма перевода',
      send_available: 'Доступно:',
      send_net_received: 'Чистая сумма получателю:',
      send_pct_all: 'Все',
      send_network_fee: 'Комиссия сети (1% Протокол):',
      send_zero_fee: 'Комиссия сети: 0.00 BCT (Без комиссии)',
      send_instant_conf: 'Мгновенное подтверждение',
      send_submit: 'Продолжить и подписать',
      send_submit_btn: 'Продолжить и подписать',
      send_ecdsa_signed: 'Подписано сквозным ECDSA',
      send_instant_block: 'Мгновенная запись в блок',
      space_ph: 'Поделитесь мыслями... (0.10 BCT)',
      space_composer_ph: 'Поделитесь мыслями... (0.10 BCT)',
      space_publish: 'Опубликовать',
      space_filter_all: 'Все',
      space_filter_following: 'Проверенные и подписки',
      space_empty: 'В блокчейне пока нет публикаций.',
      space_empty_posts: 'Посты загружаются или отсутствуют в этом фильтре...',
      space_like: 'Нравится',
      space_liked: 'Понравилось',
      space_reply: 'Комментарий',
      space_share: 'Поделиться',
      space_tip: 'Чаевые',
      space_follow: 'Читать',
      space_active_l1: 'Активен L1',
      space_compose_fab: 'Написать',
      space_create_wallet_hint: 'Создайте кошелек (+1.00 BCT бонус)',
      space_search_ph: 'Поиск постов, #тегов или @пользователей...',
      space_search_btn: 'Поиск',
      space_share_btn: 'Поделиться',
      post_not_found: 'Публикация не найдена или загружается.',
      post_back_to_feed: 'Вернуться в ленту Space',
      post_block_label: 'Блок',
      post_likes_label: 'Лайки',
      post_comments_label: 'Комментарии',
      post_royalties_label: 'Роялти',
      post_comments_title: 'Комментарии',
      post_author_royalty_hint: '+0.004 BCT Роялти автору',
      post_be_first_comment: 'Напишите первый ончейн-комментарий ниже!',
      post_comment_ph: 'Напишите комментарий... (0.02 BCT)',
      post_comment_send: 'Отправить',
      profile_security_btn: 'Безопасность',
      profile_follow_btn: 'Читать',
      profile_tip_btn: 'Чаевые',
      profile_bns_title: 'Ваши имена BNS (.bct)',
      profile_bns_count: 'имен',
      profile_bns_hint: 'Выберите имя, которое будет отображаться в профиле и ленте Space:',
      profile_bns_active: '(Активно)',
      profile_bns_none: 'У вас пока нет имени .bct. Зарегистрируйте красивое имя вместо адреса кошелька.',
      profile_bns_claim: 'Получить имя',
      profile_bio: 'Верифицированный автор BlocTag Space ✦ Публикует контент и зарабатывает мгновенные роялти на Layer-1 блокчейне.',
      profile_stat_posts: 'Посты',
      profile_stat_likes: 'Лайки',
      profile_stat_followers: 'Подписчики',
      profile_stat_following: 'Подписки',
      profile_tab_posts: 'Посты',
      profile_tab_popular: 'Популярное',
      profile_empty_posts: 'В блокчейне пока нет публикаций.',
      profile_view_followers: 'Смотреть подписчиков',
      profile_view_following: 'Смотреть подписки',
      connections_title: 'Связанные аккаунты',
      live_network_community: 'Живая сеть • Сообщество',
      filter_all: 'Все',
      filter_mutual: 'Взаимные',
      filter_verified: 'Верифицированные',
      follows_you: 'Подписан на вас',
      follow_back: 'В ответ',
      btn_following: 'Вы подписаны',
      btn_follow: 'Подписаться',
      no_users_found: 'Пользователи не найдены',
      no_users_found_desc: 'По вашему запросу ничего не найдено. Попробуйте сбросить фильтры.',
      search_users_placeholder: 'Поиск по имени или адресу...',
      user_self_tag: 'Вы',
      loading_connections: 'Загрузка ончейн связей...',
      querying_ledger: 'Опрос криптографического реестра и сети...',
      switch_to_main_feed: 'Перейти к основной ленте Space',
      switched_to_main_feed_toast: 'Переключено на основную ленту Space',
      feed_layout_snap: 'Режим Reels / TikTok',
      feed_layout_list: 'Режим списка',
      swipe_up_hint: 'Смахните вверх для следующего',
      feed_reached_end: 'Вы просмотрели все посты',
      notif_new_badge: 'новых',
      notif_mark_all: 'Прочитать все',
      notif_all: 'Все',
      notif_tips: 'Переводы и чаевые',
      notif_mentions: 'Space и ответы',
      notif_system: 'Система',
      notif_empty_title: 'Пока нет уведомлений',
      notif_empty_desc: 'Здесь появятся уведомления о реакциях на ваши посты и поступлениях токенов.',
      menu_not_connected: 'Кошелек не подключен',
      menu_wallet: 'Мой кошелек',
      menu_profile: 'Мой профиль',
      menu_validator: 'ВАЛИДАТОР',
      menu_pro_title: 'Pro Mode (Полный интерфейс)',
      menu_pro_desc: 'Обозреватель сети, узлы и инструменты разработчика',
      menu_pro_switch: 'Переключить',
      menu_services: 'Операции и сервисы',
      menu_send: 'Отправить крипту',
      menu_send_desc: 'Мгновенные переводы BCT без комиссии',
      menu_bns: 'Имя BNS (.bct)',
      menu_bns_desc: 'Управление Web3-именем и профилем',
      menu_sec: 'Безопасность и ключи',
      menu_sec_desc: 'Секретная фраза из 12 слов (Seed Phrase)',
      menu_notif: 'Уведомления и оповещения',
      menu_notif_desc: 'Обновления транзакций и ленты Space',
      menu_lang: 'Выбор языка (Language)',
      menu_lang_desc: 'Язык интерфейса приложения',
      menu_wp: 'LockTrace Whitepaper',
      menu_wp_desc: 'Архитектура протокола и документация',
      lang_modal_title: 'Выбор языка (Language)',
      lang_modal_sub: 'Выберите язык интерфейса',
      lang_modal_hint: 'Полная совместимость со встроенным переводом браузера и PWA.'
    },
    de: {
      nav_space: 'Space',
      nav_wallet: 'Wallet',
      nav_profile: 'Profil',
      nav_menu: 'Menü',
      top_welcome: 'BlocTag',
      top_recovery: 'Wiederherstellungsschlüssel',
      top_wallet: 'Meine Wallet',
      top_send: 'Krypto senden',
      top_space: 'BlocTag Space',
      top_post_detail: 'Beitragsdetails',
      top_profile: 'Profil',
      top_notifications: 'Benachrichtigungen',
      top_menu: 'Menü',
      onb_title_1: 'Krypto und Community',
      onb_title_2: 'An einem Ort.',
      onb_sub: 'Kein Fachchinesisch. Erstellen Sie mit einem Klick eine Wallet, verwalten Sie Guthaben und treten Sie Space-Communities bei.',
      onb_feat1_title: 'Einfach & Sicher',
      onb_feat1_desc: 'Ihre Schlüssel, Ihre volle Kontrolle. Sicher direkt auf Ihrem Gerät ohne Zwischenhändler gespeichert.',
      onb_feat2_title: 'BlocTag-Identität',
      onb_feat2_badge: 'Neu',
      onb_feat2_desc: 'Verwenden Sie Ihren einfachen Benutzernamen anstelle von 42-Zeichen-Adressen (z. B. @user.bct).',
      onb_feat3_title: 'Space-Community',
      onb_feat3_desc: 'Teilen Sie Gedanken, entdecken Sie Web3-Projekte und senden Sie Trinkgelder an Autoren.',
      onb_import_title: 'Wiederherstellung mit 12 Wörtern oder Key',
      onb_import_ph: 'Geben Sie 12 Wiederherstellungswörter oder den Private Key ein...',
      onb_import_btn: 'Wallet wiederherstellen & verbinden',
      onb_create_btn: 'Wallet erstellen (+1.00 BCT Bonus)',
      onb_existing_btn: 'Mit bestehender Wallet anmelden',
      onb_footer: 'Ende-zu-Ende verschlüsselt • Non-Custodial Sicherheit',
      seed_hero_title: 'Ihre Wallet-Schlüssel',
      seed_hero_sub: 'Diese 12 Wörter sind das einzige Passwort zu Ihrer Wallet. Notieren Sie sie sicher und teilen Sie sie niemals.',
      seed_tip: 'Stellen Sie sicher, dass niemand auf Ihren Bildschirm schaut',
      seed_private: 'Vertraulich',
      seed_copy_btn: 'Wörter kopieren',
      seed_copied_toast: '12 Wiederherstellungswörter in die Zwischenablage kopiert!',
      seed_rec_title: 'Empfohlene Methode',
      seed_rec_desc: 'Schreiben Sie die Wörter auf Papier und verwahren Sie sie sicher. Vermeiden Sie Screenshots.',
      seed_saved_label: 'Ich habe meine Wörter sicher gespeichert',
      seed_saved_sub: 'Ohne Wiederherstellungswörter verliere ich den Zugriff auf mein Konto',
      seed_launch_btn: 'Wallet starten & zu Space gehen (+1.00 BCT)',
      seed_footer: 'Dezentrales Protokoll für souveränes Eigentum',
      seed_refresh_title: 'Neue Wörter generieren',
      wlt_net_worth: 'Netto-Portfoliowert',
      wlt_balance_title: 'Gesamtsaldo',
      wlt_send_btn: 'Senden',
      wlt_receive_btn: 'Empfangen (QR)',
      wlt_vault_btn: 'PIN-Tresor',
      wlt_switch_wallet: 'Wallet wechseln',
      wlt_audit_btn: 'Netzwerksicherheit',
      wlt_txs_title: 'Transaktionsverlauf',
      wlt_filter_all: 'Alle',
      wlt_filter_in: 'Eingehend',
      wlt_filter_out: 'Ausgehend',
      wlt_empty_txs: 'Keine Transaktionen in diesem Filter gefunden.',
      wlt_tx_pending: 'Mempool',
      wlt_tx_confirmed: 'Bestätigt',
      send_badge: 'Transaktion',
      send_title: 'BCT senden',
      send_fast_mode: 'Schnellmodus',
      send_active_asset: 'Aktiver Vermögenswert',
      send_recipient: 'Empfängeradresse oder .bct-Name',
      send_recipient_label: 'Empfängeradresse oder @name.bct',
      send_recipient_ph: 'BCT... oder user.bct',
      send_paste: 'Einfügen',
      send_qr_scan: 'QR scannen',
      send_amount: 'Betrag',
      send_available: 'Verfügbar:',
      send_net_received: 'Netto beim Empfänger:',
      send_pct_all: 'Alle',
      send_network_fee: 'Netzwerkgebühr (1% Protokoll):',
      send_zero_fee: 'Netzwerkgebühr: 0.00 BCT (Gebührenfrei)',
      send_instant_conf: 'Sofortige Bestätigung',
      send_submit: 'Fortfahren und signieren',
      send_submit_btn: 'Fortfahren und signieren',
      send_ecdsa_signed: 'Ende-zu-Ende ECDSA-signiert',
      send_instant_block: 'Sofortige Blockversiegelung',
      space_ph: 'Teile etwas im Netzwerk... (0.10 BCT)',
      space_composer_ph: 'Teile etwas im Netzwerk... (0.10 BCT)',
      space_publish: 'Veröffentlichen',
      space_filter_all: 'Alle',
      space_filter_following: 'Verifiziert & Gefolgt',
      space_empty: 'Noch keine On-Chain-Beiträge vorhanden.',
      space_empty_posts: 'Beiträge werden geladen oder keine vorhanden...',
      space_like: 'Gefällt mir',
      space_liked: 'Gefällt mir',
      space_reply: 'Kommentar',
      space_share: 'Teilen',
      space_tip: 'Trinkgeld',
      space_follow: 'Folgen',
      space_active_l1: 'Aktiv L1',
      space_compose_fab: 'Schreiben',
      space_create_wallet_hint: 'Wallet erstellen (+1.00 BCT Bonus)',
      space_search_ph: 'Beiträge, #Tags oder @Nutzer suchen...',
      space_search_btn: 'Suchen',
      space_share_btn: 'Teilen',
      post_not_found: 'Beitrag nicht gefunden oder lädt.',
      post_back_to_feed: 'Zurück zum Space-Feed',
      post_block_label: 'Block',
      post_likes_label: 'Gefällt mir',
      post_comments_label: 'Kommentare',
      post_royalties_label: 'Tantiemen',
      post_comments_title: 'Kommentare',
      post_author_royalty_hint: '+0.004 BCT Autorentantieme',
      post_be_first_comment: 'Schreibe den ersten On-Chain-Kommentar!',
      post_comment_ph: 'Schreibe deine Gedanken... (0.02 BCT)',
      post_comment_send: 'Senden',
      profile_security_btn: 'Sicherheit',
      profile_follow_btn: 'Folgen',
      profile_tip_btn: 'Trinkgeld',
      profile_bns_title: 'Ihre registrierten BNS-Namen (.bct)',
      profile_bns_count: 'Namen',
      profile_bns_hint: 'Wählen Sie Ihre aktive Identität für Profil und Beiträge:',
      profile_bns_active: '(Aktiv)',
      profile_bns_none: 'Sie haben noch keinen .bct-Namen. Sichern Sie sich einen einprägsamen Namen.',
      profile_bns_claim: 'Namen holen',
      profile_bio: 'Verifizierter BlocTag Space Creator ✦ Veröffentlicht Inhalte auf der zensurresistenten Layer-1-Blockchain mit Echtzeit-Tantiemen.',
      profile_stat_posts: 'Beiträge',
      profile_stat_likes: 'Likes',
      profile_stat_followers: 'Follower',
      profile_stat_following: 'Folge ich',
      profile_tab_posts: 'Beiträge',
      profile_tab_popular: 'Beliebt',
      profile_empty_posts: 'Noch keine On-Chain-Beiträge veröffentlicht.',
      profile_view_followers: 'Follower anzeigen',
      profile_view_following: 'Gefolgte anzeigen',
      connections_title: 'Verbundene Konten',
      live_network_community: 'Live-Netzwerk • Community',
      filter_all: 'Alle',
      filter_mutual: 'Gegenseitig',
      filter_verified: 'Verifiziert',
      follows_you: 'Folgt dir',
      follow_back: 'Zurückfolgen',
      btn_following: 'Gefolgt',
      btn_follow: 'Folgen',
      no_users_found: 'Keine Benutzer gefunden',
      no_users_found_desc: 'Keine Benutzer entsprechen Ihren Suchkriterien. Sie können Filter zurücksetzen.',
      search_users_placeholder: 'Benutzername oder Adresse suchen...',
      user_self_tag: 'Du',
      loading_connections: 'On-Chain-Verbindungen werden geladen...',
      querying_ledger: 'Abfrage des dezentralen Ledgers...',
      switch_to_main_feed: 'Zum Haupt-Feed wechseln',
      switched_to_main_feed_toast: 'Zum Haupt-Space-Feed gewechselt',
      feed_layout_snap: 'Reels / TikTok-Modus',
      feed_layout_list: 'Listenansicht',
      swipe_up_hint: 'Nach oben wischen für nächsten',
      feed_reached_end: 'Alle Beiträge gesehen',
      notif_new_badge: 'neu',
      notif_mark_all: 'Als gelesen markieren',
      notif_all: 'Alle',
      notif_tips: 'Überweisungen & Trinkgelder',
      notif_mentions: 'Space & Antworten',
      notif_system: 'System',
      notif_empty_title: 'Noch keine Benachrichtigungen',
      notif_empty_desc: 'Interaktionen mit Ihren Beiträgen oder Token-Transfers werden hier in Echtzeit angezeigt.',
      menu_not_connected: 'Wallet nicht verbunden',
      menu_wallet: 'Meine Wallet',
      menu_profile: 'Mein Profil',
      menu_validator: 'VALIDATOR',
      menu_pro_title: 'Pro Mode (Vollansicht)',
      menu_pro_desc: 'Netzwerk-Explorer, Nodes und Entwickler-Tools',
      menu_pro_switch: 'Modus wechseln',
      menu_services: 'Operationen & Dienste',
      menu_send: 'Krypto senden',
      menu_send_desc: 'Sofortige gebührenfreie BCT-Transfers',
      menu_bns: 'BNS-Benutzername (.bct)',
      menu_bns_desc: 'Verwalten Sie Ihre Web3-Identität und Ihr Profil',
      menu_sec: 'Sicherheit & Wiederherstellung',
      menu_sec_desc: 'Geheime 12-Wörter-Wiederherstellungsphrase (Seed Phrase)',
      menu_notif: 'Benachrichtigungen & Hinweise',
      menu_notif_desc: 'Transaktions- und Space-Updates',
      menu_lang: 'Sprachauswahl (Language)',
      menu_lang_desc: 'Sprache der Benutzeroberfläche',
      menu_wp: 'LockTrace Whitepaper',
      menu_wp_desc: 'Protokollarchitektur und technische Dokumentation',
      lang_modal_title: 'Sprachauswahl (Language)',
      lang_modal_sub: 'Wählen Sie Ihre Anwendungssprache',
      lang_modal_hint: 'Voll kompatibel mit integrierter Browser-Übersetzung und PWA.'
    },
    es: {
      nav_space: 'Space',
      nav_wallet: 'Billetera',
      nav_profile: 'Perfil',
      nav_menu: 'Menú',
      top_welcome: 'BlocTag',
      top_recovery: 'Clave de Recuperación',
      top_wallet: 'Mi Billetera',
      top_send: 'Enviar Cripto',
      top_space: 'BlocTag Space',
      top_post_detail: 'Detalle de Publicación',
      top_profile: 'Perfil',
      top_notifications: 'Notificaciones',
      top_menu: 'Menú',
      onb_title_1: 'Cripto y Comunidad',
      onb_title_2: 'En un Solo Lugar.',
      onb_sub: 'Sin términos complejos. Crea una billetera con un clic, gestiona activos y únete a las comunidades de Space en Web3.',
      onb_feat1_title: 'Fácil y Seguro',
      onb_feat1_desc: 'Tus claves, tu control total. Guardadas directamente en tu dispositivo sin intermediarios.',
      onb_feat2_title: 'Identidad BlocTag',
      onb_feat2_badge: 'Nuevo',
      onb_feat2_desc: 'Usa tu nombre de usuario simple en lugar de direcciones de 42 caracteres (ej. @usuario.bct).',
      onb_feat3_title: 'Comunidad Space',
      onb_feat3_desc: 'Comparte ideas, descubre proyectos Web3 y envía propinas directas a los creadores.',
      onb_import_title: 'Recuperar con 12 Palabras o Clave Privada',
      onb_import_ph: 'Introduce tus 12 palabras o clave privada...',
      onb_import_btn: 'Recuperar Billetera e Ingresar',
      onb_create_btn: 'Crear Billetera (+1.00 BCT Bono)',
      onb_existing_btn: 'Ingresar con Billetera Existente',
      onb_footer: 'Cifrado de Extremo a Extremo • Seguridad Non-Custodial',
      seed_hero_title: 'Claves de tu Billetera',
      seed_hero_sub: 'Estas 12 palabras son la única contraseña de tu billetera. Anótalas en un lugar seguro y no las compartas con nadie.',
      seed_tip: 'Asegúrate de que nadie esté mirando tu pantalla',
      seed_private: 'Confidencial',
      seed_copy_btn: 'Copiar Palabras',
      seed_copied_toast: '¡12 palabras de recuperación copiadas al portapapeles!',
      seed_rec_title: 'Método Recomendado',
      seed_rec_desc: 'Escribe las palabras en papel físico y guárdalas en un lugar seguro. Evita capturas de pantalla.',
      seed_saved_label: 'He guardado mis palabras en un lugar seguro',
      seed_saved_sub: 'Sin mis palabras de recuperación no podré acceder a mi cuenta',
      seed_launch_btn: 'Iniciar Billetera e ir a Space (+1.00 BCT)',
      seed_footer: 'Protocolo descentralizado de propiedad soberana',
      seed_refresh_title: 'Generar Nuevas Palabras',
      wlt_net_worth: 'Valor Neto del Portafolio',
      wlt_balance_title: 'Saldo Total',
      wlt_send_btn: 'Enviar',
      wlt_receive_btn: 'Recibir (QR)',
      wlt_vault_btn: 'Bóveda PIN',
      wlt_switch_wallet: 'Cambiar Billetera',
      wlt_audit_btn: 'Seguridad de Red',
      wlt_txs_title: 'Historial de Transacciones',
      wlt_filter_all: 'Todas',
      wlt_filter_in: 'Entrantes',
      wlt_filter_out: 'Salientes',
      wlt_empty_txs: 'No se encontraron transacciones en este filtro.',
      wlt_tx_pending: 'Mempool',
      wlt_tx_confirmed: 'Confirmado',
      send_badge: 'Transacción',
      send_title: 'Enviar BCT',
      send_fast_mode: 'Modo Rápido',
      send_active_asset: 'Activo Seleccionado',
      send_recipient: 'Dirección de Destino o Nombre .bct',
      send_recipient_label: 'Dirección o @nombre.bct',
      send_recipient_ph: 'BCT... o usuario.bct',
      send_paste: 'Pegar',
      send_qr_scan: 'Escanear QR',
      send_amount: 'Monto a Enviar',
      send_available: 'Disponible:',
      send_net_received: 'Neto a Recibir:',
      send_pct_all: 'Todo',
      send_network_fee: 'Tarifa de Red (1% Protocolo):',
      send_zero_fee: 'Tarifa de Red: 0.00 BCT (Sin Comisión)',
      send_instant_conf: 'Confirmación Instantánea',
      send_submit: 'Continuar y Firmar',
      send_submit_btn: 'Continuar y Firmar',
      send_ecdsa_signed: 'Firmado de Extremo a Extremo con ECDSA',
      send_instant_block: 'Sellado Instantáneo en Bloque',
      space_ph: 'Comparte algo en la red... (0.10 BCT)',
      space_composer_ph: 'Comparte algo en la red... (0.10 BCT)',
      space_publish: 'Publicar',
      space_filter_all: 'Todo',
      space_filter_following: 'Verificados y Seguidos',
      space_empty: 'Aún no hay publicaciones en la red.',
      space_empty_posts: 'Cargando publicaciones o no hay en este filtro...',
      space_like: 'Me gusta',
      space_liked: 'Te gusta',
      space_reply: 'Comentar',
      space_share: 'Compartir',
      space_tip: 'Propina',
      space_follow: 'Seguir',
      space_active_l1: 'Activo L1',
      space_compose_fab: 'Publicar',
      space_create_wallet_hint: 'Crea una billetera (+1.00 BCT bono)',
      space_search_ph: 'Buscar publicaciones, #etiquetas o @usuarios...',
      space_search_btn: 'Buscar',
      space_share_btn: 'Compartir',
      post_not_found: 'Publicación no encontrada o cargando.',
      post_back_to_feed: 'Volver a la лента de Space',
      post_block_label: 'Bloque',
      post_likes_label: 'Me gusta',
      post_comments_label: 'Comentarios',
      post_royalties_label: 'Regalías',
      post_comments_title: 'Comentarios',
      post_author_royalty_hint: '+0.004 BCT Regalía al Autor',
      post_be_first_comment: '¡Sé el primero en dejar un comentario on-chain abajo!',
      post_comment_ph: 'Escribe tu opinión... (0.02 BCT)',
      post_comment_send: 'Enviar',
      profile_security_btn: 'Seguridad',
      profile_follow_btn: 'Seguir',
      profile_tip_btn: 'Propina',
      profile_bns_title: 'Tus Nombres BNS Registrados (.bct)',
      profile_bns_count: 'nombres',
      profile_bns_hint: 'Elige tu identidad activa para tu perfil y publicaciones:',
      profile_bns_active: '(Activo)',
      profile_bns_none: 'Aún no tienes un nombre .bct. Consigue un nombre fácil de recordar.',
      profile_bns_claim: 'Obtener Nombre',
      profile_bio: 'Creador verificado de BlocTag Space ✦ Publica en la blockchain Layer-1 resistente a la censura con regalías instantáneas.',
      profile_stat_posts: 'Publicaciones',
      profile_stat_likes: 'Me gusta',
      profile_stat_followers: 'Seguidores',
      profile_stat_following: 'Siguiendo',
      profile_tab_posts: 'Publicaciones',
      profile_tab_popular: 'Populares',
      profile_empty_posts: 'Aún no se han publicado mensajes en la red.',
      profile_view_followers: 'Ver Seguidores',
      profile_view_following: 'Ver Seguidos',
      connections_title: 'Cuentas Conectadas',
      live_network_community: 'Red en Vivo • Comunidad',
      filter_all: 'Todos',
      filter_mutual: 'Mutuo',
      filter_verified: 'Verificado',
      follows_you: 'Te sigue',
      follow_back: 'Seguir de vuelta',
      btn_following: 'Siguiendo',
      btn_follow: 'Seguir',
      no_users_found: 'No se encontraron usuarios',
      no_users_found_desc: 'No se encontraron usuarios que coincidan con sus criterios de búsqueda. Puede restablecer los filtros.',
      search_users_placeholder: 'Buscar nombre de usuario o dirección...',
      user_self_tag: 'Tú',
      loading_connections: 'Cargando conexiones on-chain...',
      querying_ledger: 'Consultando el registro criptográfico...',
      switch_to_main_feed: 'Cambiar al Feed Principal de Space',
      switched_to_main_feed_toast: 'Cambiado al feed principal de Space',
      feed_layout_snap: 'Modo Reels / TikTok',
      feed_layout_list: 'Vista de lista',
      swipe_up_hint: 'Desliza hacia arriba para el siguiente',
      feed_reached_end: 'Has visto todas las publicaciones',
      notif_new_badge: 'nuevas',
      notif_mark_all: 'Marcar como Leídas',
      notif_all: 'Todas',
      notif_tips: 'Transferencias y Propinas',
      notif_mentions: 'Space y Respuestas',
      notif_system: 'Sistema',
      notif_empty_title: 'Aún no hay notificaciones',
      notif_empty_desc: 'Las interacciones con tus publicaciones y transferencias de tokens aparecerán aquí en tiempo real.',
      menu_not_connected: 'Billetera no conectada',
      menu_wallet: 'Mi Billetera',
      menu_profile: 'Mi Perfil',
      menu_validator: 'VALIDADOR',
      menu_pro_title: 'Modo Pro (Vista Completa)',
      menu_pro_desc: 'Explorador de red, nodos y herramientas de desarrollo',
      menu_pro_switch: 'Cambiar Modo',
      menu_services: 'Operaciones y Servicios',
      menu_send: 'Enviar Cripto',
      menu_send_desc: 'Transferencias BCT instantáneas sin comisión',
      menu_bns: 'Nombre de Usuario BNS (.bct)',
      menu_bns_desc: 'Gestiona tu identidad Web3 y perfil',
      menu_sec: 'Seguridad y Clave de Recuperación',
      menu_sec_desc: 'Frase secreta de 12 palabras (Seed Phrase)',
      menu_notif: 'Notificaciones y Alertas',
      menu_notif_desc: 'Actualizaciones de transacciones y Space',
      menu_lang: 'Selección de Idioma (Language)',
      menu_lang_desc: 'Idioma de la interfaz de la aplicación',
      menu_wp: 'LockTrace Whitepaper',
      menu_wp_desc: 'Arquitectura del protocolo y documentación técnica',
      lang_modal_title: 'Selección de Idioma (Language)',
      lang_modal_sub: 'Elige el idioma de tu aplicación',
      lang_modal_hint: 'Totalmente compatible con la función de traducción del navegador y PWA.'
    },
    fr: {
      nav_space: 'Space',
      nav_wallet: 'Portefeuille',
      nav_profile: 'Profil',
      nav_menu: 'Menu',
      top_welcome: 'BlocTag',
      top_recovery: 'Clé de Récupération',
      top_wallet: 'Mon Portefeuille',
      top_send: 'Envoyer Crypto',
      top_space: 'BlocTag Space',
      top_post_detail: 'Détail de la Publication',
      top_profile: 'Profil',
      top_notifications: 'Notifications',
      top_menu: 'Menu',
      onb_title_1: 'Crypto et Communauté',
      onb_title_2: 'En Un Seul Lieu.',
      onb_sub: 'Sans jargon complexe. Créez un portefeuille en un clic, gérez vos actifs et rejoignez les communautés Web3 de Space.',
      onb_feat1_title: 'Simple et Sécurisé',
      onb_feat1_desc: 'Vos clés, votre contrôle total. Conservées directement sur votre appareil sans intermédiaire.',
      onb_feat2_title: 'Identité BlocTag',
      onb_feat2_badge: 'Nouveau',
      onb_feat2_desc: 'Utilisez un nom simple au lieu d\'adresses de 42 caractères (ex. @utilisateur.bct).',
      onb_feat3_title: 'Communauté Space',
      onb_feat3_desc: 'Partagez des idées, découvrez des projets Web3 et envoyez des pourboires aux créateurs.',
      onb_import_title: 'Restaurer avec 12 Mots ou Clé Privée',
      onb_import_ph: 'Entrez vos 12 mots ou votre clé privée...',
      onb_import_btn: 'Restaurer le Portefeuille & Se Connecter',
      onb_create_btn: 'Créer un Portefeuille (+1.00 BCT Bonus)',
      onb_existing_btn: 'Se Connecter avec un Portefeuille Existant',
      onb_footer: 'Chiffré de Bout en Bout • Sécurité Non-Custodial',
      seed_hero_title: 'Vos Clés de Portefeuille',
      seed_hero_sub: 'Ces 12 mots sont le mot de passe unique de votre portefeuille. Notez-les en lieu sûr et ne les partagez jamais.',
      seed_tip: 'Assurez-vous que personne ne regarde votre écran',
      seed_private: 'Confidentiel',
      seed_copy_btn: 'Copier les Mots',
      seed_copied_toast: '12 mots de récupération copiés dans le presse-papiers !',
      seed_rec_title: 'Méthode Recommandée',
      seed_rec_desc: 'Écrivez les mots sur un papier et conservez-le en sécurité. Évitez les captures d\'écran.',
      seed_saved_label: 'J\'ai enregistré mes mots en lieu sûr',
      seed_saved_sub: 'Sans mes mots de récupération, je ne pourrai pas accéder à mon compte',
      seed_launch_btn: 'Lancer le Portefeuille & Aller à Space (+1.00 BCT)',
      seed_footer: 'Protocole décentralisé de propriété souveraine',
      seed_refresh_title: 'Générer de Nouveaux Mots',
      wlt_net_worth: 'Valeur Nette du Portefeuille',
      wlt_balance_title: 'Solde Total',
      wlt_send_btn: 'Envoyer',
      wlt_receive_btn: 'Recevoir (QR)',
      wlt_vault_btn: 'Coffre-fort PIN',
      wlt_switch_wallet: 'Changer de Portefeuille',
      wlt_audit_btn: 'Sécurité Réseau',
      wlt_txs_title: 'Historique des Transactions',
      wlt_filter_all: 'Toutes',
      wlt_filter_in: 'Entrantes',
      wlt_filter_out: 'Sortantes',
      wlt_empty_txs: 'Aucune transaction trouvée dans ce filtre.',
      wlt_tx_pending: 'Mempool',
      wlt_tx_confirmed: 'Confirmé',
      send_badge: 'Transaction',
      send_title: 'Envoyer BCT',
      send_fast_mode: 'Mode Rapide',
      send_active_asset: 'Actif Sélectionné',
      send_recipient: 'Adresse du Destinataire ou Nom .bct',
      send_recipient_label: 'Adresse ou @nom.bct',
      send_recipient_ph: 'BCT... ou utilisateur.bct',
      send_paste: 'Coller',
      send_qr_scan: 'Scanner QR',
      send_amount: 'Montant à Envoyer',
      send_available: 'Disponible :',
      send_net_received: 'Net Reçu par le Destinataire :',
      send_pct_all: 'Tout',
      send_network_fee: 'Frais de Réseau (1 % Protocole) :',
      send_zero_fee: 'Frais de Réseau : 0.00 BCT (Sans Commission)',
      send_instant_conf: 'Confirmation Instantanée',
      send_submit: 'Continuer et Signer',
      send_submit_btn: 'Continuer et Signer',
      send_ecdsa_signed: 'Signé ECDSA de Bout en Bout',
      send_instant_block: 'Sceau de Bloc Instantané',
      space_ph: 'Partagez quelque chose... (0.10 BCT)',
      space_composer_ph: 'Partagez quelque chose... (0.10 BCT)',
      space_publish: 'Publier',
      space_filter_all: 'Tout',
      space_filter_following: 'Vérifiés & Suivis',
      space_empty: 'Aucune publication on-chain pour le moment.',
      space_empty_posts: 'Chargement des publications ou aucune trouvée...',
      space_like: 'J\'aime',
      space_liked: 'Aimé',
      space_reply: 'Commenter',
      space_share: 'Partager',
      space_tip: 'Pourboire',
      space_follow: 'Suivre',
      space_active_l1: 'Actif L1',
      space_compose_fab: 'Écrire',
      space_create_wallet_hint: 'Créer un portefeuille (+1.00 BCT bonus)',
      space_search_ph: 'Rechercher publications, #tags ou @utilisateurs...',
      space_search_btn: 'Rechercher',
      space_share_btn: 'Partager',
      post_not_found: 'Publication introuvable ou en cours de chargement.',
      post_back_to_feed: 'Retour au flux Space',
      post_block_label: 'Bloc',
      post_likes_label: 'J\'aime',
      post_comments_label: 'Commentaires',
      post_royalties_label: 'Redevances',
      post_comments_title: 'Commentaires',
      post_author_royalty_hint: '+0.004 BCT Redevance Auteur',
      post_be_first_comment: 'Soyez le premier à commenter on-chain ci-dessous !',
      post_comment_ph: 'Partagez votre avis... (0.02 BCT)',
      post_comment_send: 'Envoyer',
      profile_security_btn: 'Sécurité',
      profile_follow_btn: 'Suivre',
      profile_tip_btn: 'Pourboire',
      profile_bns_title: 'Vos Noms BNS Enregistrés (.bct)',
      profile_bns_count: 'noms',
      profile_bns_hint: 'Choisissez votre identité active pour votre profil et vos posts :',
      profile_bns_active: '(Actif)',
      profile_bns_none: 'Vous n\'avez pas encore de nom .bct. Obtenez un nom facile à retenir.',
      profile_bns_claim: 'Obtenir un Nom',
      profile_bio: 'Créateur vérifié BlocTag Space ✦ Publie sur la blockchain Layer-1 résistante à la censure avec redevances en direct.',
      profile_stat_posts: 'Publications',
      profile_stat_likes: 'J\'aime',
      profile_stat_followers: 'Abonnés',
      profile_stat_following: 'Abonnements',
      profile_tab_posts: 'Publications',
      profile_tab_popular: 'Populaires',
      profile_empty_posts: 'Aucune publication on-chain pour le moment.',
      profile_view_followers: 'Voir les Abonnés',
      profile_view_following: 'Voir les Abonnements',
      connections_title: 'Comptes Connectés',
      live_network_community: 'Réseau en Direct • Communauté',
      filter_all: 'Tous',
      filter_mutual: 'Mutuel',
      filter_verified: 'Vérifié',
      follows_you: 'Vous suit',
      follow_back: 'Suivre en retour',
      btn_following: 'Abonné',
      btn_follow: 'Suivre',
      no_users_found: 'Aucun utilisateur trouvé',
      no_users_found_desc: 'Aucun utilisateur ne correspond à vos critères. Vous pouvez réinitialiser les filtres.',
      search_users_placeholder: 'Rechercher un nom d\'utilisateur ou une adresse...',
      user_self_tag: 'Vous',
      loading_connections: 'Chargement des connexions on-chain...',
      querying_ledger: 'Interrogation du registre décentralisé...',
      switch_to_main_feed: 'Passer au fil principal Space',
      switched_to_main_feed_toast: 'Basculé vers le fil principal Space',
      feed_layout_snap: 'Mode Reels / TikTok',
      feed_layout_list: 'Vue en liste',
      swipe_up_hint: 'Glissez vers le haut pour le suivant',
      feed_reached_end: 'Vous avez tout vu',
      notif_new_badge: 'nouveaux',
      notif_mark_all: 'Tout Marquer comme Lu',
      notif_all: 'Tous',
      notif_tips: 'Transferts & Pourboires',
      notif_mentions: 'Space & Réponses',
      notif_system: 'Système',
      notif_empty_title: 'Aucune notification pour l\'instant',
      notif_empty_desc: 'Les interactions avec vos publications et les réceptions de jetons apparaîtront ici en temps réel.',
      menu_not_connected: 'Portefeuille non connecté',
      menu_wallet: 'Mon Portefeuille',
      menu_profile: 'Mon Profil',
      menu_validator: 'VALIDATEUR',
      menu_pro_title: 'Mode Pro (Vue Complète)',
      menu_pro_desc: 'Explorateur de réseau, nœuds et outils pour développeurs',
      menu_pro_switch: 'Changer de Mode',
      menu_services: 'Opérations & Services',
      menu_send: 'Envoyer Crypto',
      menu_send_desc: 'Transferts BCT instantanés sans commission',
      menu_bns: 'Nom d\'Utilisateur BNS (.bct)',
      menu_bns_desc: 'Gérez votre identité Web3 et votre profil',
      menu_sec: 'Sécurité & Clé de Récupération',
      menu_sec_desc: 'Phrase secrète de 12 mots (Seed Phrase)',
      menu_notif: 'Notifications & Alertes',
      menu_notif_desc: 'Mises à jour des transactions et de Space',
      menu_lang: 'Sélection de la Langue (Language)',
      menu_lang_desc: 'Langue de l\'interface de l\'application',
      menu_wp: 'LockTrace Whitepaper',
      menu_wp_desc: 'Architecture du protocole et documentation technique',
      lang_modal_title: 'Sélection de la Langue (Language)',
      lang_modal_sub: 'Choisissez la langue de votre application',
      lang_modal_hint: 'Entièrement compatible avec la traduction native du navigateur et la PWA.'
    },
    ar: {
      nav_space: 'Space',
      nav_wallet: 'المحفظة',
      nav_profile: 'الملف الشخصي',
      nav_menu: 'القائمة',
      top_welcome: 'BlocTag',
      top_recovery: 'مفتاح الاسترداد',
      top_wallet: 'محفظتي',
      top_send: 'إرسال العملات',
      top_space: 'BlocTag Space',
      top_post_detail: 'تفاصيل المنشور',
      top_profile: 'الملف الشخصي',
      top_notifications: 'الإشعارات',
      top_menu: 'القائمة',
      onb_title_1: 'العملات الرقمية والمجتمع',
      onb_title_2: 'في مكان واحد.',
      onb_sub: 'دون مصطلحات معقدة. أنشئ محفظتك بنقرة واحدة، وأدر أصولك وانضم إلى مجتمعات Space اللامركزية.',
      onb_feat1_title: 'سهل وآمن',
      onb_feat1_desc: 'مفاتيحك تحت سيطرتك الكاملة. مخزنة مباشرة على جهازك دون وسطاء أو خوادم وسيطة.',
      onb_feat2_title: 'هوية BlocTag',
      onb_feat2_badge: 'جديد',
      onb_feat2_desc: 'استخدم اسماً بسيطاً بدلاً من العناوين الطويلة المكونة من 42 حرفاً (مثل @user.bct).',
      onb_feat3_title: 'مجتمع Space',
      onb_feat3_desc: 'شارك أفكارك مع الموثقين واكتشف مشاريع Web3 وقدم إكراميات مباشرة للمبدعين.',
      onb_import_title: 'استرداد بواسطة 12 كلمة أو مفتاح خاص',
      onb_import_ph: 'أدخل كلمات الاسترداد الـ 12 أو المفتاح الخاص...',
      onb_import_btn: 'استرداد المحفظة وتسجيل الدخول',
      onb_create_btn: 'إنشاء محفظة (+1.00 BCT مكافأة)',
      onb_existing_btn: 'تسجيل الدخول بمحفظة موجودة',
      onb_footer: 'مشفر من طرف لطرف • أمان بدون وسيط (Non-Custodial)',
      seed_hero_title: 'مفاتيح محفظتك',
      seed_hero_sub: 'هذه الكلمات الـ 12 هي كلمة المرور الوحيدة لمحفظتك. احفظها في مكان آمن ولا تشاركها مع أحد.',
      seed_tip: 'تأكد من عدم وجود أحد يراقب شاشتك',
      seed_private: 'سري',
      seed_copy_btn: 'نسخ الكلمات',
      seed_copied_toast: 'تم نسخ كلمات الاسترداد الـ 12 إلى الحافظة!',
      seed_rec_title: 'الطريقة الموصى بها',
      seed_rec_desc: 'اكتب الكلمات على ورقة واحتفظ بها في مكان آمن. تجنب أخذ لقطات شاشة.',
      seed_saved_label: 'لقد حفظت كلماتي في مكان آمن',
      seed_saved_sub: 'بدون كلمات الاسترداد لن أتمكن من الوصول إلى حسابي',
      seed_launch_btn: 'بدء تشغيل المحفظة والانتقال إلى Space (+1.00 BCT)',
      seed_footer: 'بروتوكول ملكية سيادي ولامركزي',
      seed_refresh_title: 'توليد كلمات جديدة',
      wlt_net_worth: 'صافي قيمة المحفظة',
      wlt_balance_title: 'إجمالي الرصيد',
      wlt_send_btn: 'إرسال',
      wlt_receive_btn: 'استلام (QR)',
      wlt_vault_btn: 'خزنة PIN',
      wlt_switch_wallet: 'تبديل المحفظة',
      wlt_audit_btn: 'أمان الشبكة',
      wlt_txs_title: 'سجل المعاملات',
      wlt_filter_all: 'الكل',
      wlt_filter_in: 'الواردة',
      wlt_filter_out: 'الصادرة',
      wlt_empty_txs: 'لا توجد معاملات في هذا التصفية.',
      wlt_tx_pending: 'في قائمة الانتظار',
      wlt_tx_confirmed: 'مؤكد',
      send_badge: 'معاملة',
      send_title: 'إرسال BCT',
      send_fast_mode: 'الوضع السريع',
      send_active_asset: 'الأصل النشط',
      send_recipient: 'عنوان المستلم أو اسم .bct',
      send_recipient_label: 'عنوان المستلم أو @اسم.bct',
      send_recipient_ph: 'BCT... أو user.bct',
      send_paste: 'لصق',
      send_qr_scan: 'مسح QR',
      send_amount: 'المبلغ المراد إرساله',
      send_available: 'المتاح:',
      send_net_received: 'صافي المستلم:',
      send_pct_all: 'الكل',
      send_network_fee: 'رسوم الشبكة (1% بروتوكول):',
      send_zero_fee: 'رسوم الشبكة: 0.00 BCT (بدون عمولة)',
      send_instant_conf: 'تأكيد فوري',
      send_submit: 'متابعة وتوقيع',
      send_submit_btn: 'متابعة وتوقيع',
      send_ecdsa_signed: 'موقّع بتقنية ECDSA من طرف لطرف',
      send_instant_block: 'تسجيل فوري على البلوك',
      space_ph: 'شارك شيئاً على الشبكة... (0.10 BCT)',
      space_composer_ph: 'شارك شيئاً على الشبكة... (0.10 BCT)',
      space_publish: 'نشر',
      space_filter_all: 'الكل',
      space_filter_following: 'الموثقون والمتابعون',
      space_empty: 'لا توجد منشورات على السلسلة بعد.',
      space_empty_posts: 'جارٍ تحميل المنشورات أو لا توجد منشورات...',
      space_like: 'إعجاب',
      space_liked: 'تم الإعجاب',
      space_reply: 'تعليق',
      space_share: 'مشاركة',
      space_tip: 'إكرامية',
      space_follow: 'متابعة',
      space_active_l1: 'نشط L1',
      space_compose_fab: 'كتابة',
      space_create_wallet_hint: 'أنشئ محفظة (+1.00 BCT مكافأة)',
      space_search_ph: 'بحث في المنشورات، #الوسوم أو @المستخدمين...',
      space_search_btn: 'بحث',
      space_share_btn: 'مشاركة',
      post_not_found: 'المنشور غير موجود أو قيد التحميل.',
      post_back_to_feed: 'العودة إلى موجز Space',
      post_block_label: 'كتلة',
      post_likes_label: 'إعجابات',
      post_comments_label: 'تعليقات',
      post_royalties_label: 'عوائد',
      post_comments_title: 'التعليقات',
      post_author_royalty_hint: '+0.004 BCT عوائد الكاتب',
      post_be_first_comment: 'كن أول من يكتب تعليقاً على السلسلة بالأسفل!',
      post_comment_ph: 'اكتب رأيك... (0.02 BCT)',
      post_comment_send: 'إرسال',
      profile_security_btn: 'الأمان',
      profile_follow_btn: 'متابعة',
      profile_tip_btn: 'إكرامية',
      profile_bns_title: 'أسماء BNS المسجلة الخاصة بك (.bct)',
      profile_bns_count: 'أسماء',
      profile_bns_hint: 'اختر هويتك النشطة لتظهر في ملفك الشخصي ومنشوراتك:',
      profile_bns_active: '(نشط)',
      profile_bns_none: 'لم تسجل اسم .bct بعد. احصل على اسم مميز بدلاً من عنوان محفظتك.',
      profile_bns_claim: 'تسجيل اسم',
      profile_bio: 'صانع محتوى موثق على BlocTag Space ✦ ينشر على بلوكشين Layer-1 المقاوم للرقابة مع أرباح فورية.',
      profile_stat_posts: 'منشورات',
      profile_stat_likes: 'إعجابات',
      profile_stat_followers: 'متابعون',
      profile_stat_following: 'متابَعون',
      profile_tab_posts: 'المنشورات',
      profile_tab_popular: 'الشائع',
      profile_empty_posts: 'لم يتم نشر أي منشورات على السلسلة بعد.',
      profile_view_followers: 'عرض المتابعين',
      profile_view_following: 'عرض المتابَعين',
      connections_title: 'الحسابات المتصلة',
      live_network_community: 'شبكة مباشرة • المجتمع',
      filter_all: 'الكل',
      filter_mutual: 'متابعة متبادلة',
      filter_verified: 'موثق',
      follows_you: 'يتابعك',
      follow_back: 'رد المتابعة',
      btn_following: 'تتابعه',
      btn_follow: 'متابعة',
      no_users_found: 'لم يتم العثور على مستخدمين',
      no_users_found_desc: 'لا توجد نتائج مطابقة لبحثك. يمكنك إعادة تعيين التصفية.',
      search_users_placeholder: 'ابحث عن اسم المستخدم أو العنوان...',
      user_self_tag: 'أنت',
      loading_connections: 'جارٍ تحميل الروابط على السلسلة...',
      querying_ledger: 'استعلام عن دفتر الأستاذ التشفيري والشبكة اللامركزية...',
      switch_to_main_feed: 'التبديل إلى موجز Space الرئيسي',
      switched_to_main_feed_toast: 'تم الانتقال إلى موجز Space الرئيسي',
      feed_layout_snap: 'وضع Reels / TikTok',
      feed_layout_list: 'عرض القائمة',
      swipe_up_hint: 'اسحب لأعلى للمنشور التالي',
      feed_reached_end: 'لقد شاهدت جميع المنشورات',
      notif_new_badge: 'جديد',
      notif_mark_all: 'تحديد الكل كمقروء',
      notif_all: 'الكل',
      notif_tips: 'التحويلات والإكراميات',
      notif_mentions: 'Space والردود',
      notif_system: 'النظام',
      notif_empty_title: 'لا توجد إشعارات بعد',
      notif_empty_desc: 'ستظهر هنا التفاعلات مع منشوراتك وتحويلات العملات في الوقت الفعلي.',
      menu_not_connected: 'المحفظة غير متصلة',
      menu_wallet: 'محفظتي',
      menu_profile: 'ملفي الشخصي',
      menu_validator: 'المدقق',
      menu_pro_title: 'وضع المحترفين Pro (عرض كامل)',
      menu_pro_desc: 'مستكشف الشبكة والعقد وأدوات المطورين',
      menu_pro_switch: 'تبديل الوضع',
      menu_services: 'العمليات والخدمات',
      menu_send: 'إرسال العملات',
      menu_send_desc: 'تحويلات BCT فورية وبدون عمولة',
      menu_bns: 'اسم مستخدم BNS (.bct)',
      menu_bns_desc: 'إدارة هويتك وملفك في Web3',
      menu_sec: 'الأمان ومفتاح الاسترداد',
      menu_sec_desc: 'عبارة الاسترداد السرية المكونة من 12 كلمة (Seed Phrase)',
      menu_notif: 'الإشعارات والتنبيهات',
      menu_notif_desc: 'تحديثات المعاملات وموجز Space',
      menu_lang: 'اختيار اللغة (Language)',
      menu_lang_desc: 'لغة واجهة التطبيق',
      menu_wp: 'LockTrace Whitepaper',
      menu_wp_desc: 'بنية البروتوكول والوثائق الفنية',
      lang_modal_title: 'اختيار اللغة (Language)',
      lang_modal_sub: 'حدد لغة التطبيق الخاصة بك',
      lang_modal_hint: 'متوافق تماماً مع ميزة الترجمة التلقائية للمتصفح وتطبيق PWA.'
    }
  };

  function getActiveLanguageCode() {
    try {
      const saved = localStorage.getItem('bloctag_lang') || localStorage.getItem(GATE_LANG_STORAGE_KEY);
      if (saved && SIMPLE_LANGUAGES.some(l => l.code === saved)) return saved;
    } catch (_e) { }
    const htmlLang = (document.documentElement.lang || '').slice(0, 2).toLowerCase();
    if (htmlLang && SIMPLE_LANGUAGES.some(l => l.code === htmlLang)) return htmlLang;
    return 'en';
  }

  function t(key, defaultEn) {
    const lang = getActiveLanguageCode();
    if (lang === 'en') return defaultEn;
    if (typeof SIMPLE_I18N !== 'undefined' && SIMPLE_I18N[lang] && SIMPLE_I18N[lang][key]) {
      return SIMPLE_I18N[lang][key];
    }
    return defaultEn;
  }

  function openSimpleLanguageModal() {
    let modal = document.getElementById('bloctag-language-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'bloctag-language-modal';
      modal.className = 'hidden fixed inset-0 z-[96] bg-black/75 backdrop-blur-md items-end sm:items-center justify-center p-0 sm:p-4';
      document.body.appendChild(modal);
    }

    const current = getActiveLanguageCode();

    modal.innerHTML = `
      <div class="w-full max-w-[420px] rounded-t-3xl sm:rounded-3xl bg-surface-container border border-outline-variant/25 shadow-2xl p-5 flex flex-col gap-3.5 animate-slide-up sm:animate-fade-in" onclick="event.stopPropagation()">
        <!-- Header -->
        <div class="flex items-center justify-between pb-1 border-b border-outline-variant/10">
          <div class="flex items-center gap-2.5">
            <div class="w-9 h-9 rounded-xl bg-primary/15 text-primary flex items-center justify-center">
              <span class="material-symbols-outlined notranslate text-[20px]" translate="no">language</span>
            </div>
            <div class="flex flex-col">
              <h3 class="text-base font-bold text-on-surface">${t('lang_modal_title', 'Language Selection')}</h3>
              <p class="text-[11px] text-on-surface-variant">${t('lang_modal_sub', 'Choose your application language')}</p>
            </div>
          </div>
          <button type="button" onclick="window.BlocTagSimpleMode.closeLanguageModal()"
            class="w-8 h-8 rounded-full bg-surface-container-high hover:bg-surface-bright text-on-surface-variant hover:text-on-surface flex items-center justify-center active:scale-95 transition-all cursor-pointer">
            <span class="material-symbols-outlined notranslate text-[18px]" translate="no">close</span>
          </button>
        </div>

        <!-- Language Items -->
        <div class="flex flex-col gap-1.5 max-h-[58vh] overflow-y-auto no-scrollbar py-1">
          ${SIMPLE_LANGUAGES.map(item => {
            const isSelected = item.code === current;
            return `
              <button type="button" onclick="window.BlocTagSimpleMode.selectLanguage('${item.code}')"
                class="w-full p-3 rounded-2xl flex items-center justify-between transition-all active:scale-[0.98] cursor-pointer ${isSelected ? 'bg-primary/15 border border-primary/30 text-on-surface ring-1 ring-primary/40' : 'bg-surface-container-low hover:bg-surface-container-high border border-outline-variant/15 text-on-surface'}">
                <div class="flex items-center gap-3">
                  <span class="text-2xl notranslate leading-none" translate="no">${item.flag}</span>
                  <div class="flex flex-col text-left">
                    <span class="text-xs font-bold leading-snug">${esc(item.name)}</span>
                    <span class="text-[10.5px] text-on-surface-variant leading-snug">${esc(item.desc)}</span>
                  </div>
                </div>
                ${isSelected ? `
                  <div class="w-6 h-6 rounded-full bg-primary text-on-primary flex items-center justify-center shadow-xs">
                    <span class="material-symbols-outlined notranslate text-[16px]" translate="no">check</span>
                  </div>
                ` : `
                  <span class="text-[11px] font-mono text-on-surface-variant/60 uppercase">${item.code}</span>
                `}
              </button>
            `;
          }).join('')}
        </div>

        <!-- Browser Translate Tip -->
        <div class="p-3 rounded-xl bg-surface-container-lowest border border-outline-variant/10 flex items-center gap-2.5 text-on-surface-variant text-[11px]">
          <span class="material-symbols-outlined notranslate text-primary text-[17px] shrink-0" translate="no">translate</span>
          <span>${t('lang_modal_hint', 'Fully compatible with browser Translate features and multilingual PWA support.')}</span>
        </div>
      </div>
    `;

    modal.onclick = () => closeSimpleLanguageModal();
    modal.classList.remove('hidden');
    modal.classList.add('flex');
  }

  function closeSimpleLanguageModal() {
    const modal = document.getElementById('bloctag-language-modal');
    if (modal) {
      modal.classList.add('hidden');
      modal.classList.remove('flex');
    }
  }

  function setLanguagePreference(code) {
    if (!code) return;
    try {
      localStorage.setItem('bloctag_lang', code);
      localStorage.setItem(GATE_LANG_STORAGE_KEY, code);
      document.cookie = `googtrans=/auto/${code}; path=/;`;
      if (window.location.hostname) {
        document.cookie = `googtrans=/auto/${code}; domain=${window.location.hostname}; path=/;`;
      }
    } catch (_e) { }
    document.documentElement.lang = code;
    document.documentElement.dir = (code === 'ar') ? 'rtl' : 'ltr';

    closeSimpleLanguageModal();
    renderSimpleMode(false);

    const langObj = SIMPLE_LANGUAGES.find(l => l.code === code);
    const langLabel = langObj ? `${langObj.flag} ${langObj.name}` : code.toUpperCase();
    if (typeof window.showToast === 'function') {
      window.showToast(`${langLabel} ${t('lang_selected_toast', 'selected as active language.')}`, 'translate');
    }
  }

  function applySimpleModeState(enabled, withAnimation = true) {
    simpleState.enabled = Boolean(enabled);
    const html = document.documentElement;
    ensureSimpleModeShell();

    if (withAnimation) {
      html.classList.add('bloctag-mode-switching');
      setTimeout(() => html.classList.remove('bloctag-mode-switching'), 420);
    }

    if (simpleState.enabled) {
      html.classList.add('bloctag-simple-mode');
      const acc = getActiveWallet();
      if (!acc && (simpleState.activeScreen === 'SCR-WLT-HOME' || simpleState.activeScreen === 'SCR-SPC-03')) {
        simpleState.activeScreen = 'SCR-ONB-01';
      }
      renderSimpleMode();
      try {
        const hasPosts = typeof spacePostsCache !== 'undefined' && Array.isArray(spacePostsCache) && spacePostsCache.length > 0;
        if (!hasPosts && typeof window.loadSpaceFeed === 'function') {
          window.loadSpaceFeed().then(() => {
            if (simpleState.enabled) renderSimpleMode(false);
          }).catch(() => { });
        }
      } catch (_e) { }
    } else {
      html.classList.remove('bloctag-simple-mode');
    }

    syncModeToggleControls(simpleState.enabled);
  }

  function toggleSimpleModeSetting(forceState) {
    const nextState = typeof forceState === 'boolean' ? forceState : !simpleState.enabled;
    try {
      localStorage.setItem(SIMPLE_MODE_STORAGE_KEY, nextState ? 'true' : 'false');
    } catch (_e) { }

    // Close menu drawer smoothly if open so the user sees the animated design update immediately
    try {
      const mobMenu = document.getElementById('mobileMenuModal');
      if (mobMenu && !mobMenu.classList.contains('hidden') && typeof window.closeMobileMenuModal === 'function') {
        window.closeMobileMenuModal();
      }
    } catch (_e) { }

    applySimpleModeState(nextState, true);

    if (typeof window.showToast === 'function') {
      window.showToast(
        nextState
          ? '✨ Simple Mod aktif edildi (Stitch Sade Mobil Tasarım)'
          : '⚡ Pro Mod aktif edildi (Tam Protokol Arayüzü)',
        nextState ? 'auto_awesome' : 'bolt'
      );
    }
  }

  // ── Profile Cache & Asynchronous Fetcher for Simple Mode ──
  const _simpleProfileCache = window._simpleProfileCache || {};
  window._simpleProfileCache = _simpleProfileCache;
  const _simpleProfileFetching = window._simpleProfileFetching || {};
  window._simpleProfileFetching = _simpleProfileFetching;

  function fetchSimpleProfile(target) {
    if (!target) return Promise.resolve(null);
    const key = String(target).trim().toLowerCase().replace(/^@/, '');
    if (!key) return Promise.resolve(null);

    const cached = _simpleProfileCache[key];
    if (cached && (Date.now() - (cached._cachedAt || 0) < 45000)) {
      return Promise.resolve(cached);
    }

    if (_simpleProfileFetching[key]) {
      return _simpleProfileFetching[key];
    }

    const fetcher = (typeof window.apiFetch === 'function')
      ? window.apiFetch('/profile/' + encodeURIComponent(key))
      : fetch('/api/v1/profile/' + encodeURIComponent(key)).then(r => r.json().then(b => ({ ok: r.ok, body: b })));

    const p = fetcher.then(({ ok, body }) => {
      delete _simpleProfileFetching[key];
      if (ok && body && body.data) {
        const data = body.data;
        data._cachedAt = Date.now();
        const addr = String(data.address || '').toLowerCase();
        if (addr) _simpleProfileCache[addr] = data;
        if (data.bns_name) {
          _simpleProfileCache[String(data.bns_name).toLowerCase().replace(/^@/, '')] = data;
        }
        if (data.primary_bns) {
          _simpleProfileCache[String(data.primary_bns).toLowerCase().replace(/^@/, '')] = data;
        }
        if (data.primary_handle) {
          _simpleProfileCache[String(data.primary_handle).toLowerCase().replace(/^@/, '')] = data;
        }
        _simpleProfileCache[key] = data;

        window.currentProfileData = data;
        try {
          if (typeof currentProfileData !== 'undefined') {
            currentProfileData = data;
          }
        } catch (_e) { }

        if (simpleState.enabled) {
          const act = simpleState.activeScreen;
          if (act === 'SCR-PRF-05' || act === 'SCR-PRF-FOLLOW' || act === 'SCR-PRF-FOLLOWERS' || act === 'SCR-PRF-FOLLOWING') {
            renderSimpleMode(false);
          }
        }
        return data;
      }
      return null;
    }).catch(err => {
      delete _simpleProfileFetching[key];
      console.warn('[SimpleMode] fetchSimpleProfile failed:', err);
      return null;
    });

    _simpleProfileFetching[key] = p;
    return p;
  }

  function getSimpleProfileData(target) {
    if (!target) return null;
    const key = String(target).trim().toLowerCase().replace(/^@/, '');
    if (_simpleProfileCache[key]) return _simpleProfileCache[key];
    if (window.currentProfileData) {
      const c = window.currentProfileData;
      const cAddr = String(c.address || '').toLowerCase();
      const cBns = String(c.bns_name || c.primary_bns || c.primary_handle || '').toLowerCase().replace(/^@/, '');
      if (cAddr === key || cBns === key) return c;
    }
    try {
      if (typeof currentProfileData !== 'undefined' && currentProfileData) {
        const c = currentProfileData;
        const cAddr = String(c.address || '').toLowerCase();
        const cBns = String(c.bns_name || c.primary_bns || c.primary_handle || '').toLowerCase().replace(/^@/, '');
        if (cAddr === key || cBns === key) return c;
      }
    } catch (_e) { }
    return null;
  }

  // ==========================================================================
  // 2. NAVIGATION ROUTER FOR STITCH SIMPLE MODE SCREENS
  // ==========================================================================
  function navigateToSimpleScreen(screenCode, opts = {}) {
    const valid = [
      'SCR-ONB-01',
      'SCR-WLT-02',
      'SCR-WLT-HOME',
      'SCR-WLT-SEND',
      'SCR-SPC-03',
      'SCR-SPC-04',
      'SCR-PRF-05',
      'SCR-PRF-FOLLOW',
      'SCR-PRF-FOLLOWERS',
      'SCR-PRF-FOLLOWING',
      'SCR-NTF-06',
      'SCR-MNU-07'
    ];
    const target = valid.includes(screenCode) ? screenCode : 'SCR-SPC-03';

    if (opts.postId !== undefined) {
      simpleState.activePostId = opts.postId;
    }
    if (opts.profileTarget !== undefined) {
      simpleState.profileTarget = opts.profileTarget;
      if (!opts.profileTarget && opts.followTargetAddr === undefined) {
        simpleState.followTargetAddr = '';
      }
    }
    if (opts.followTab !== undefined) {
      simpleState.followTab = opts.followTab;
    }
    if (opts.followTargetAddr !== undefined) {
      simpleState.followTargetAddr = opts.followTargetAddr;
    }
    if (opts.recipient !== undefined) {
      simpleState.sendPrefillRecipient = opts.recipient;
    }
    if (opts.amount !== undefined) {
      simpleState.sendPrefillAmount = opts.amount;
    }

    if (target === 'SCR-WLT-02' && !simpleState.seedMnemonic) {
      generateSimpleSeedPreview();
    }

    if (opts.pushHistory !== false) {
      const last = simpleState.screenHistory[simpleState.screenHistory.length - 1];
      if (last !== target) {
        simpleState.screenHistory.push(target);
        if (simpleState.screenHistory.length > 25) simpleState.screenHistory.shift();
      }
    }

    simpleState.activeScreen = target;
    renderSimpleMode();
    window.scrollTo({ top: 0, behavior: 'smooth' });

    // Trigger background data sync on screen entry
    try {
      if (target === 'SCR-SPC-03') {
        if (typeof window.loadSpaceFeed === 'function') {
          window.loadSpaceFeed().then(() => {
            if (simpleState.enabled) renderSimpleMode(false);
          }).catch(() => { });
        }
      } else if (target === 'SCR-SPC-04') {
        const activePid = simpleState.activePostId;
        if (activePid && typeof window.apiFetch === 'function') {
          window.apiFetch('/space/post/' + encodeURIComponent(activePid) + '?_nc=' + Date.now()).then(({ ok, body }) => {
            if (ok && body && body.data && typeof spacePostsCache !== 'undefined' && Array.isArray(spacePostsCache)) {
              const idx = spacePostsCache.findIndex(p => String(p.post_id || p.id) === String(activePid));
              if (idx >= 0) spacePostsCache[idx] = body.data;
              else spacePostsCache.unshift(body.data);
              if (simpleState.enabled && simpleState.activeScreen === 'SCR-SPC-04') {
                renderSimpleMode(false);
              }
            }
          }).catch(() => { });
        } else if (typeof window.loadSpaceFeed === 'function') {
          window.loadSpaceFeed().then(() => {
            if (simpleState.enabled) renderSimpleMode(false);
          }).catch(() => { });
        }
      } else if (target === 'SCR-WLT-HOME' || target === 'SCR-WLT-SEND') {
        if (typeof window.refreshCurrentAccountBalance === 'function') {
          window.refreshCurrentAccountBalance().then(() => {
            if (simpleState.enabled) renderSimpleMode(false);
          }).catch(() => { });
        }
        if (typeof window.refreshPersonalTransactions === 'function') {
          window.refreshPersonalTransactions().then(() => {
            if (simpleState.enabled) renderSimpleMode(false);
          }).catch(() => { });
        }
      } else if (target === 'SCR-PRF-05' || target === 'SCR-PRF-FOLLOW' || target === 'SCR-PRF-FOLLOWERS' || target === 'SCR-PRF-FOLLOWING') {
        if (typeof window.fetchAndSyncMyBnsHandles === 'function') {
          window.fetchAndSyncMyBnsHandles().then(() => {
            if (simpleState.enabled) renderSimpleMode(false);
          }).catch(() => { });
        }
        const pTarget = (target === 'SCR-PRF-FOLLOW' || target === 'SCR-PRF-FOLLOWERS' || target === 'SCR-PRF-FOLLOWING')
          ? (simpleState.followTargetAddr || simpleState.profileTarget || (getActiveWallet() ? getActiveWallet().address : ''))
          : (simpleState.profileTarget || (getActiveWallet() ? getActiveWallet().address : ''));
        if (pTarget) {
          fetchSimpleProfile(pTarget);
        }
        const myAcc = getActiveWallet();
        if (myAcc && myAcc.address && myAcc.address.toLowerCase() !== String(pTarget).toLowerCase()) {
          fetchSimpleProfile(myAcc.address);
        }
      }
    } catch (_e) { }
  }

  function navigateSimpleBack() {
    if (simpleState.screenHistory.length > 1) {
      simpleState.screenHistory.pop();
      const prev = simpleState.screenHistory[simpleState.screenHistory.length - 1];
      navigateToSimpleScreen(prev, { pushHistory: false });
    } else {
      navigateToSimpleScreen('SCR-SPC-03', { pushHistory: false });
    }
  }

  function generateSimpleSeedPreview() {
    try {
      if (typeof previewMnemonicPhrase === 'string' && previewMnemonicPhrase.trim().split(/\s+/).length === 12) {
        simpleState.seedMnemonic = previewMnemonicPhrase.trim();
      } else if (typeof LockTraceCrypto !== 'undefined' && typeof LockTraceCrypto.generateMnemonic12 === 'function') {
        simpleState.seedMnemonic = LockTraceCrypto.generateMnemonic12();
        try { previewMnemonicPhrase = simpleState.seedMnemonic; } catch (_e) { }
      }
      simpleState.seedSavedConfirmed = false;
    } catch (_e) { }
  }

  // ==========================================================================
  // 3. STITCH SCREEN RENDERERS (EXACT STITCH MOBILE DESIGNS)
  // ==========================================================================

  // ── Shared Top Header & Bottom Navigation ──────────────────────────────────
  function renderTopBar(title, showBack = false, rightActionHtml = '') {
    const acc = getActiveWallet();
    const myHandle = getMyPrimaryHandle();
    const avatarChar = myHandle ? myHandle[0].toUpperCase() : (acc && acc.address ? acc.address.slice(3, 4).toUpperCase() : '');
    const unread = getUnreadNotificationsCount();

    return `
      <header class="simple-top-header">
        <div class="h-14 px-4 flex items-center justify-between gap-2">
          <div class="flex items-center gap-2.5 min-w-0">
            ${showBack ? `
              <button type="button" aria-label="${t('common_back', 'Back')}" onclick="window.BlocTagSimpleMode.back()"
                class="w-9 h-9 -ml-1.5 rounded-full flex items-center justify-center text-on-surface hover:text-primary active:scale-95 transition-all cursor-pointer">
                <span class="material-symbols-outlined notranslate text-[21px]" translate="no">arrow_back_ios_new</span>
              </button>
            ` : `
              <span class="w-2.5 h-2.5 rounded-full bg-primary animate-pulse shrink-0"></span>
            `}
            <span class="font-headline-sm text-[18px] font-semibold tracking-tight text-on-surface truncate">${esc(title)}</span>
          </div>

          <div class="flex items-center gap-1.5 shrink-0">
            ${rightActionHtml}

            <!-- Notification Bell Icon -->
            <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-NTF-06')"
              title="${t('top_notifications', 'Notifications')}" aria-label="${t('top_notifications', 'Notifications')}"
              class="relative w-8 h-8 rounded-full bg-surface-container-high hover:bg-surface-variant text-on-surface-variant hover:text-primary flex items-center justify-center active:scale-90 transition-all cursor-pointer shrink-0">
              <span class="material-symbols-outlined notranslate text-[18px]" translate="no">notifications</span>
              ${unread > 0 ? `<span class="absolute -top-1 -right-1 min-w-[15px] h-[15px] px-1 rounded-full bg-rose-500 text-white font-mono text-[9px] font-bold flex items-center justify-center ring-2 ring-surface">${unread}</span>` : ''}
            </button>

            <!-- Profile Avatar Pill (Shown on non-profile screens) -->
            ${(simpleState.activeScreen !== 'SCR-PRF-05' && simpleState.activeScreen !== 'SCR-PRF-FOLLOW' && simpleState.activeScreen !== 'SCR-PRF-FOLLOWERS' && simpleState.activeScreen !== 'SCR-PRF-FOLLOWING') ? `
              <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-PRF-05', { profileTarget: '' })"
                title="${t('top_my_profile', 'My Profile')}"
                class="w-8 h-8 rounded-full bg-primary text-on-primary flex items-center justify-center font-mono font-bold text-xs shadow-sm active:scale-95 transition-transform cursor-pointer shrink-0">
                ${avatarChar ? esc(avatarChar) : '<span class="material-symbols-outlined notranslate text-[17px]" translate="no">person</span>'}
              </button>
            ` : ''}
          </div>
        </div>
      </header>
    `;
  }

  function renderBottomNav() {
    const active = simpleState.activeScreen;
    const isSpace = active === 'SCR-SPC-03' || active === 'SCR-SPC-04';
    const isWallet = active === 'SCR-WLT-HOME' || active === 'SCR-WLT-SEND' || active === 'SCR-ONB-01' || active === 'SCR-WLT-02';
    const isProfile = active === 'SCR-PRF-05' || active === 'SCR-PRF-FOLLOW' || active === 'SCR-PRF-FOLLOWERS' || active === 'SCR-PRF-FOLLOWING';
    const isMenu = active === 'SCR-MNU-07';

    return `
      <nav class="simple-bottom-nav" aria-label="Simple Mode Navigation">
        <div class="flex justify-around items-center h-14 px-1.5">
          <!-- 1. Space -->
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-SPC-03')"
            class="flex flex-col items-center justify-center gap-0.5 flex-1 h-12 transition-colors cursor-pointer ${isSpace ? 'text-primary font-semibold' : 'text-on-surface-variant hover:text-on-surface'}">
            <span class="material-symbols-outlined notranslate text-[22px]" translate="no">tag</span>
            <span class="font-label-sm text-[10px] leading-none">${t('nav_space', 'Space')}</span>
          </button>

          <!-- 2. Wallet -->
          <button type="button" onclick="window.BlocTagSimpleMode.openWalletTab()"
            class="flex flex-col items-center justify-center gap-0.5 flex-1 h-12 transition-colors cursor-pointer ${isWallet ? 'text-primary font-semibold' : 'text-on-surface-variant hover:text-on-surface'}">
            <span class="material-symbols-outlined notranslate text-[21px]" translate="no">account_balance_wallet</span>
            <span class="font-label-sm text-[10px] leading-none">${t('nav_wallet', 'Wallet')}</span>
          </button>

          <!-- 3. Profile -->
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-PRF-05', { profileTarget: '' })"
            class="flex flex-col items-center justify-center gap-0.5 flex-1 h-12 transition-colors cursor-pointer ${isProfile ? 'text-primary font-semibold' : 'text-on-surface-variant hover:text-on-surface'}">
            <span class="material-symbols-outlined notranslate text-[21px]" translate="no">person</span>
            <span class="font-label-sm text-[10px] leading-none">${t('nav_profile', 'Profile')}</span>
          </button>

          <!-- 4. Menu -->
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-MNU-07')"
            class="flex flex-col items-center justify-center gap-0.5 flex-1 h-12 transition-colors cursor-pointer ${isMenu ? 'text-primary font-semibold' : 'text-on-surface-variant hover:text-on-surface'}">
            <span class="material-symbols-outlined notranslate text-[21px]" translate="no">widgets</span>
            <span class="font-label-sm text-[10px] leading-none font-semibold">${t('nav_menu', 'Menu')}</span>
          </button>
        </div>
      </nav>
    `;
  }

  // ── SCR-ONB-01: BlocTag - Hoş Geldiniz & Giriş ──────────────────────────────
  function renderScreenOnboardingWelcome() {
    const acc = getActiveWallet();
    const myHandle = getMyPrimaryHandle();

    return `
      ${renderTopBar('BlocTag', false)}
      <main class="flex-1 flex flex-col w-full px-5 pt-3 pb-24 simple-screen-animate select-none">
        <!-- Top Visual & Identity Cluster (Exact Stitch SCR-ONB-01) -->
        <div class="flex flex-col items-center justify-center pt-3 relative mb-3">
          <div class="absolute w-36 h-36 rounded-full bg-primary-container/20 blur-3xl -z-10 pointer-events-none transform -translate-y-2"></div>
          <div class="relative flex items-center justify-center w-20 h-20 rounded-full bg-surface-container-high shadow-lg border border-outline-variant/20">
            <div class="w-12 h-12 rounded-full bg-surface-container flex items-center justify-center relative overflow-hidden">
              <svg class="w-8 h-8 text-primary" fill="none" viewBox="0 0 36 36">
                <path class="opacity-90" d="M18 4L30 11V25L18 32L6 25V11L18 4Z" stroke="currentColor" stroke-linejoin="round" stroke-width="2.2"></path>
                <path d="M18 12L24 15.5V22.5L18 26L12 22.5V15.5L18 12Z" fill="currentColor" fill-opacity="0.25"></path>
                <circle cx="18" cy="19" fill="currentColor" r="3"></circle>
              </svg>
            </div>
            <span class="absolute bottom-1 right-1 w-3.5 h-3.5 rounded-full bg-primary ring-2 ring-surface"></span>
          </div>
          <div class="mt-2.5 inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-container-high text-on-surface-variant font-label-sm text-[11px]">
            <span class="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></span>
            <span>BlocTag Mainnet v2.12.2</span>
          </div>
        </div>

        <!-- Editorial Headline Section -->
        <div class="flex flex-col items-center text-center px-2 mb-4">
          <h1 class="text-[30px] leading-[36px] font-bold text-on-surface tracking-tight mb-1.5">
            ${t('onb_title_1', 'Crypto & Community')} <br/>
            <span class="text-primary">${t('onb_title_2', 'All in One Place.')}</span>
          </h1>
          <p class="text-sm text-on-surface-variant max-w-sm leading-relaxed">
            ${t('onb_sub', 'No complex jargon. Create a non-custodial wallet in one click, manage your assets, and connect with Web3 communities on Space.')}
          </p>
        </div>

        <!-- Feature Highlights (Card Stack) -->
        <div class="flex flex-col gap-2.5 mb-4">
          <div class="flex items-start gap-3.5 p-3.5 rounded-2xl bg-surface-container hover:bg-surface-container-high transition-colors">
            <div class="w-10 h-10 rounded-full bg-surface-container-high flex items-center justify-center text-primary shrink-0">
              <span class="material-symbols-outlined notranslate text-[20px]" style="font-variation-settings: 'FILL' 1;" translate="no">lock_open</span>
            </div>
            <div class="flex flex-col min-w-0">
              <h3 class="text-xs font-semibold text-on-surface">${t('onb_feat1_title', 'Easy & Secure')}</h3>
              <p class="text-xs text-on-surface-variant mt-0.5 leading-relaxed">
                ${t('onb_feat1_desc', 'Your keys, your complete control. Stored directly on your device with no intermediaries or custody risk.')}
              </p>
            </div>
          </div>

          <div class="flex items-start gap-3.5 p-3.5 rounded-2xl bg-surface-container hover:bg-surface-container-high transition-colors cursor-pointer"
               onclick="window.BlocTagSimpleMode.requestProMode('bns')">
            <div class="w-10 h-10 rounded-full bg-surface-container-high flex items-center justify-center text-secondary shrink-0">
              <span class="material-symbols-outlined notranslate text-[20px]" style="font-variation-settings: 'FILL' 1;" translate="no">alternate_email</span>
            </div>
            <div class="flex flex-col min-w-0">
              <div class="flex items-center gap-2">
                <h3 class="text-xs font-semibold text-on-surface">${t('onb_feat2_title', 'BlocTag Identity')}</h3>
                <span class="px-1.5 py-0.5 rounded-full bg-secondary-container text-on-secondary-container text-[10px] font-bold">${t('onb_feat2_badge', 'New')}</span>
              </div>
              <p class="text-xs text-on-surface-variant mt-0.5 leading-relaxed">
                ${t('onb_feat2_desc', 'Use a clean username instead of raw hex addresses (e.g. @user.bct).')}
              </p>
            </div>
          </div>

          <div class="flex items-start gap-3.5 p-3.5 rounded-2xl bg-surface-container hover:bg-surface-container-high transition-colors cursor-pointer"
               onclick="window.BlocTagSimpleMode.go('SCR-SPC-03')">
            <div class="w-10 h-10 rounded-full bg-surface-container-high flex items-center justify-center text-primary-fixed shrink-0">
              <span class="material-symbols-outlined notranslate text-[20px]" style="font-variation-settings: 'FILL' 1;" translate="no">groups</span>
            </div>
            <div class="flex flex-col min-w-0">
              <h3 class="text-xs font-semibold text-on-surface">${t('onb_feat3_title', 'Space Community')}</h3>
              <p class="text-xs text-on-surface-variant mt-0.5 leading-relaxed">
                ${t('onb_feat3_desc', 'Share on-chain thoughts with peers, explore decentralized projects, and tip creators in one click.')}
              </p>
            </div>
          </div>
        </div>

        <!-- Interactive Tag Preview Badge -->
        <div class="flex items-center justify-center mb-4">
          <div class="inline-flex items-center gap-2 py-1.5 px-3.5 rounded-full bg-surface-container-low text-on-surface-variant text-xs border border-outline-variant/15 shadow-sm">
            <span class="text-primary font-semibold font-mono">${myHandle ? '@' + esc(myHandle) : '@yourname.bct'}</span>
            <span class="opacity-40">•</span>
            <span class="text-on-surface">${myHandle ? (t('onb_active_id', 'active on-chain identity')) : (acc ? t('onb_connected_active', 'wallet connected & active') : t('onb_bonus_ready', '+1.00 BCT welcome bonus ready'))}</span>
          </div>
        </div>

        <!-- Inline Import Box (Toggled by 'BlocTag Bağlan') -->
        ${simpleState.importModeOpen ? `
          <div class="mb-4 p-4 rounded-2xl bg-surface-container-low border border-primary/30 flex flex-col gap-2.5 animate-fadeIn">
            <div class="flex items-center justify-between">
              <span class="text-xs font-semibold text-on-surface flex items-center gap-1.5">
                <span class="material-symbols-outlined notranslate text-primary text-[16px]" translate="no">vpn_key</span>
                <span>${t('onb_import_title', 'Restore with 12 Words or Private Key')}</span>
              </span>
              <button type="button" onclick="window.BlocTagSimpleMode.toggleImport(false)" class="text-on-surface-variant hover:text-on-surface">
                <span class="material-symbols-outlined notranslate text-[16px]" translate="no">close</span>
              </button>
            </div>
            <textarea id="simpleImportInput" rows="3"
              placeholder="${t('onb_import_ph', 'Enter your 12 recovery words or 64-char private key...')}"
              class="w-full bg-surface-container rounded-xl p-3 text-xs font-mono text-on-surface placeholder:text-outline/60 border border-outline-variant/20 focus:border-primary focus:outline-none resize-none"></textarea>
            <button type="button" onclick="window.BlocTagSimpleMode.submitImport()"
              class="w-full h-11 rounded-full bg-primary text-on-primary text-xs font-semibold flex items-center justify-center gap-1.5 shadow-md active:scale-98 transition-all cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[17px]" translate="no">login</span>
              <span>${t('onb_import_btn', 'Restore Wallet & Connect')}</span>
            </button>
          </div>
        ` : ''}

        <!-- Action CTA Area -->
        <div class="flex flex-col gap-2.5 w-full mt-auto">
          <button type="button" onclick="window.BlocTagSimpleMode.startCreateWallet()"
            class="w-full h-[50px] rounded-full bg-primary-container text-on-primary-container text-sm font-semibold flex items-center justify-center gap-2 shadow-md active:scale-[0.98] transition-all cursor-pointer">
            <span>${t('onb_create_btn', 'Create Wallet (+1.00 BCT Bonus)')}</span>
            <span class="material-symbols-outlined notranslate text-[18px]" translate="no">arrow_forward</span>
          </button>

          <button type="button" onclick="window.BlocTagSimpleMode.toggleImport()"
            class="w-full h-[50px] rounded-full bg-surface-container-high hover:bg-surface-bright text-on-surface text-sm font-medium flex items-center justify-center gap-2 active:scale-[0.98] transition-all cursor-pointer">
            <span class="material-symbols-outlined notranslate text-[18px] text-primary" translate="no">wallet</span>
            <span>${acc ? (t('onb_existing_btn', 'Connect with Existing Wallet') + ' (' + esc(getDisplayHandleOrAddr(acc.address, myHandle)) + ')') : t('onb_existing_btn', 'Connect with Existing Wallet')}</span>
          </button>
        </div>

        <!-- Bottom Trust & Security Footnote -->
        <div class="flex items-center justify-center gap-1.5 pt-3 text-on-surface-variant/70 mt-2">
          <span class="material-symbols-outlined notranslate text-[14px] text-primary" translate="no">verified_user</span>
          <span class="text-[11px] tracking-wide">${t('onb_footer', 'End-to-End Encrypted • Non-Custodial Security')}</span>
        </div>
      </main>
    `;
  }

  // ── SCR-WLT-02: Cüzdan Aç - Anahtar Kelimeler ──────────────────────────────
  function renderScreenSeedPhrase() {
    if (!simpleState.seedMnemonic) {
      generateSimpleSeedPreview();
    }
    const words = String(simpleState.seedMnemonic || '').trim().split(/\s+/).filter(Boolean);
    const isSaved = Boolean(simpleState.seedSavedConfirmed);

    return `
      ${renderTopBar(t('top_recovery', 'Recovery Key'), true)}
      <main class="flex-1 flex flex-col w-full px-5 pt-3 pb-24 simple-screen-animate">
        <div class="flex flex-col w-full gap-3.5">
          <!-- Warm Visual Illustration & Human Context (Exact Stitch SCR-WLT-02) -->
          <div class="flex items-center gap-3.5 p-3.5 rounded-2xl bg-surface-container-low border border-outline-variant/15 shadow-sm">
            <div class="relative w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
              <span class="material-symbols-outlined notranslate text-primary text-[24px]" style="font-variation-settings: 'FILL' 1;" translate="no">shield_with_heart</span>
              <div class="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-primary flex items-center justify-center">
                <span class="material-symbols-outlined notranslate text-on-primary text-[10px]" translate="no">check</span>
              </div>
            </div>
            <div class="flex flex-col">
              <h2 class="text-base font-semibold text-on-surface">${t('seed_hero_title', 'Your Wallet Keys')}</h2>
              <p class="text-xs text-on-surface-variant leading-snug">
                ${t('seed_hero_sub', 'These 12 words are the sole password to your wallet. Write them down securely and never share them.')}
              </p>
            </div>
          </div>

          <!-- Security Tip Pill -->
          <div class="flex items-center justify-between px-3.5 py-2 rounded-full bg-surface-container text-on-surface-variant text-xs">
            <div class="flex items-center gap-1.5">
              <span class="material-symbols-outlined notranslate text-primary text-[16px]" translate="no">visibility_off</span>
              <span>${t('seed_tip', 'Make sure no one is watching your screen')}</span>
            </div>
            <span class="text-primary text-[10px] font-bold uppercase tracking-wider">${t('seed_private', 'Confidential')}</span>
          </div>

          <!-- 12-Word Grid Container (2 Symmetrical Columns) -->
          <div class="relative rounded-2xl bg-surface-container-low p-3.5 shadow-md border border-outline-variant/15 flex flex-col gap-3">
            <div class="grid grid-cols-2 gap-2" id="simple-seed-grid">
              ${words.map((w, idx) => `
                <div class="flex items-center gap-2 px-3 py-2 rounded-xl bg-surface-container hover:bg-surface-container-high transition-colors">
                  <span class="font-mono text-[11px] text-on-surface-variant/60 w-5">${String(idx + 1).padStart(2, '0')}</span>
                  <span class="font-mono text-sm text-on-surface font-medium select-all">${esc(w)}</span>
                </div>
              `).join('')}
            </div>

            <!-- Quick Copy & Refresh Action Bar -->
            <div class="flex items-center justify-between pt-1">
              <div class="flex items-center gap-1.5">
                <button type="button" onclick="window.BlocTagSimpleMode.copySeed()"
                  class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-surface-container-highest hover:bg-surface-bright text-on-surface active:scale-95 transition-all cursor-pointer">
                  <span class="material-symbols-outlined notranslate text-[16px] text-primary" id="simple-copy-seed-icon" translate="no">content_copy</span>
                  <span class="text-xs font-medium" id="simple-copy-seed-text">${t('seed_copy_btn', 'Copy Words')}</span>
                </button>
                <button type="button" onclick="window.BlocTagSimpleMode.refreshSeed()" title="${t('seed_refresh_title', 'Generate New Words')}"
                  class="w-8 h-8 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-on-surface flex items-center justify-center active:scale-95 transition-all cursor-pointer">
                  <span class="material-symbols-outlined notranslate text-[16px]" translate="no">refresh</span>
                </button>
              </div>
              <span class="text-[11px] font-mono text-on-surface-variant/70 flex items-center gap-1">
                <span class="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></span>
                <span>128-bit BIP39</span>
              </span>
            </div>
          </div>

          <!-- Friendly Physical Backup Tips Badge -->
          <div class="flex items-start gap-2.5 p-3.5 rounded-2xl bg-surface-container-lowest border border-outline-variant/10">
            <span class="material-symbols-outlined notranslate text-secondary text-[20px] shrink-0 mt-0.5" translate="no">draw</span>
            <div class="flex flex-col gap-0.5">
              <span class="text-xs font-semibold text-on-surface">${t('seed_rec_title', 'Recommended Method')}</span>
              <span class="text-xs text-on-surface-variant leading-relaxed">
                ${t('seed_rec_desc', 'Write down the words on physical paper and store in a safe place. Avoid taking screenshots.')}
              </span>
            </div>
          </div>

          <!-- Custom Animated Switch Confirmation -->
          <div class="flex items-center justify-between p-3.5 rounded-2xl bg-surface-container-low border border-outline-variant/15 select-none cursor-pointer"
               onclick="window.BlocTagSimpleMode.toggleSeedSaved()">
            <div class="flex flex-col pr-3">
              <span class="text-xs font-semibold text-on-surface">${t('seed_saved_label', 'I have safely saved my recovery words')}</span>
              <span class="text-[11px] text-on-surface-variant/80">${t('seed_saved_sub', 'Without recovery words I cannot access my wallet')}</span>
            </div>
            <div class="relative w-12 h-7 rounded-full transition-colors duration-200 shrink-0 ${isSaved ? 'bg-primary-container' : 'bg-surface-container-highest'}">
              <div class="absolute top-1 left-1 w-5 h-5 rounded-full transition-transform duration-200 flex items-center justify-center ${isSaved ? 'translate-x-5 bg-on-primary-container' : 'bg-outline'}">
                <span class="material-symbols-outlined notranslate text-[14px] text-primary transition-opacity ${isSaved ? 'opacity-100' : 'opacity-0'}" translate="no">check</span>
              </div>
            </div>
          </div>

          <!-- Primary CTA Button -->
          <div class="pt-1 flex flex-col gap-2">
            <button type="button" id="simple-finalize-wallet-btn"
              ${isSaved ? '' : 'disabled'}
              onclick="window.BlocTagSimpleMode.finalizeCreateWallet()"
              class="w-full h-[52px] rounded-full text-sm font-semibold flex items-center justify-center gap-2 transition-all duration-200 ${isSaved ? 'bg-primary text-on-primary shadow-md active:scale-[0.98] hover:brightness-95 cursor-pointer' : 'bg-surface-container-highest text-on-surface/40 cursor-not-allowed'}">
              <span>${t('seed_launch_btn', "Launch Wallet & Go to Space (+1.00 BCT)")}</span>
              <span class="material-symbols-outlined notranslate text-[20px]" translate="no">arrow_forward</span>
            </button>
            <p class="text-center text-[11px] text-on-surface-variant/60">
              ${t('seed_footer', 'Decentralized and sovereign ownership protocol')}
            </p>
          </div>
        </div>
      </main>
    `;
  }

  // ── SCR-WLT-HOME: Cüzdanım ve Geçmiş (Mobil) ───────────────────────────────
  function renderScreenWalletHome() {
    const acc = getActiveWallet();
    if (!acc) {
      return renderScreenOnboardingWelcome();
    }

    const myHandle = getMyPrimaryHandle();
    const bal = Number(acc.balance || 0);
    const price = (typeof window.currentWbctPriceUsd === 'number' && window.currentWbctPriceUsd > 0)
      ? window.currentWbctPriceUsd
      : 0.01;
    const usdVal = bal * price;
    const hidden = typeof isBalanceHidden !== 'undefined' && isBalanceHidden;
    const balFormatted = hidden ? '••••••' : (typeof window.formatBct === 'function' ? window.formatBct(bal, 4) : bal.toFixed(4));
    const usdFormatted = hidden ? '••••' : (typeof window.formatUsdValue === 'function' ? window.formatUsdValue(usdVal) : ('$' + usdVal.toFixed(2)));
    const shortAddress = typeof window.shortAddr === 'function' ? window.shortAddr(acc.address) : (acc.address.slice(0, 6) + '...' + acc.address.slice(-4));

    const allTxs = (typeof personalTxCache !== 'undefined' && Array.isArray(personalTxCache)) ? personalTxCache : [];
    const filteredTxs = allTxs.filter(tx => {
      if (typeof window.classifyPersonalTx !== 'function') return true;
      const meta = window.classifyPersonalTx(tx, acc.address);
      if (simpleState.txFilter === 'incoming') return meta.isIncoming;
      if (simpleState.txFilter === 'outgoing') return !meta.isIncoming;
      return true;
    });

    const addressPillHtml = `
      <button type="button" onclick="if(typeof copyCurrentAddress==='function') copyCurrentAddress();"
        class="flex items-center gap-1 bg-surface-container px-2.5 py-1 rounded-full text-on-surface hover:bg-surface-container-high transition-colors text-xs font-mono cursor-pointer max-w-[132px]">
        <span class="truncate">${esc(myHandle ? '@' + myHandle : shortAddress)}</span>
        <span class="material-symbols-outlined notranslate text-[14px] text-on-surface-variant shrink-0" translate="no">content_copy</span>
      </button>
    `;

    return `
      ${renderTopBar(t('top_wallet', 'My Wallet'), false, addressPillHtml)}
      <main class="flex-1 flex flex-col w-full px-5 pt-3 pb-24 simple-screen-animate">
        <!-- Net Portfolio Hero (Exact Stitch Cüzdanım ve Geçmiş Mobil) -->
        <div class="flex flex-col items-center justify-center pt-4 pb-5 text-center">
          <div class="flex items-center gap-1.5 mb-1">
            <span class="text-[11px] font-semibold text-on-surface-variant uppercase tracking-wider">${t('wlt_net_worth', 'Net Portfolio Value')}</span>
            <button type="button" onclick="if(typeof toggleBalanceVisibility==='function'){ toggleBalanceVisibility(); window.BlocTagSimpleMode.refresh(); }"
              class="text-on-surface-variant hover:text-on-surface flex items-center cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[15px]" translate="no">${hidden ? 'visibility_off' : 'visibility'}</span>
            </button>
          </div>
          <div class="flex items-baseline justify-center gap-1.5">
            <span id="simple-wallet-balance-val" class="text-[36px] leading-[42px] text-on-surface tracking-tight font-bold font-mono">${esc(balFormatted)}</span>
            <span class="text-lg font-bold text-primary">BCT</span>
          </div>
          <div class="inline-flex items-center gap-1.5 mt-2 px-3 py-1 rounded-full bg-surface-container text-primary text-xs font-mono">
            <span class="material-symbols-outlined notranslate text-[14px]" translate="no">trending_up</span>
            <span id="simple-wallet-usd-val" class="font-semibold">≈ ${esc(usdFormatted)}</span>
            <span id="simple-wallet-nonce-val" class="text-on-surface-variant ml-0.5">• Nonce #${Number(acc.nonce || 0)}</span>
          </div>
        </div>

        <!-- Primary 2-Button Action Row (Gönder & Al) -->
        <div class="grid grid-cols-2 gap-2.5 mb-6">
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-WLT-SEND')"
            class="flex items-center justify-center gap-2 h-[50px] bg-primary-container text-on-primary-container rounded-full text-sm font-semibold active:scale-[0.98] transition-all shadow-sm cursor-pointer">
            <span class="material-symbols-outlined notranslate text-[20px]" translate="no">arrow_upward</span>
            <span>${t('wlt_send_btn', 'Send')}</span>
          </button>
          <button type="button" onclick="if(typeof openReceiveModal==='function') openReceiveModal();"
            class="flex items-center justify-center gap-2 h-[50px] bg-surface-container-high hover:bg-surface-bright text-on-surface rounded-full text-sm font-semibold active:scale-[0.98] transition-all cursor-pointer">
            <span class="material-symbols-outlined notranslate text-[20px]" translate="no">arrow_downward</span>
            <span>${t('wlt_receive_btn', 'Receive (QR)')}</span>
          </button>
        </div>

        <!-- Quick Utility Chips (PIN Vault, Yeni Cüzdan, BNS) -->
        <div class="grid grid-cols-3 gap-2 mb-5">
          <button type="button" onclick="if(typeof openWalletVaultModal==='function') openWalletVaultModal();"
            class="p-2.5 rounded-2xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/15 flex flex-col items-center gap-1 text-center transition-colors cursor-pointer">
            <span class="material-symbols-outlined notranslate text-primary text-[18px]" translate="no">shield_lock</span>
            <span class="text-[11px] font-medium text-on-surface">${t('wlt_vault_btn', 'PIN Vault')}</span>
          </button>
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-ONB-01')"
            class="p-2.5 rounded-2xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/15 flex flex-col items-center gap-1 text-center transition-colors cursor-pointer">
            <span class="material-symbols-outlined notranslate text-secondary text-[18px]" translate="no">add_circle</span>
            <span class="text-[11px] font-medium text-on-surface">${t('wlt_switch_wallet', 'Switch Wallet')}</span>
          </button>
          <button type="button" onclick="if(typeof openNetworkSecurityModal==='function') openNetworkSecurityModal();"
            class="p-2.5 rounded-2xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/15 flex flex-col items-center gap-1 text-center transition-colors cursor-pointer">
            <span class="material-symbols-outlined notranslate text-emerald-400 text-[18px]" translate="no">verified_user</span>
            <span class="text-[11px] font-medium text-on-surface">${t('wlt_audit_btn', 'Network Security')}</span>
          </button>
        </div>

        <!-- İşlem Geçmişi Section -->
        <div class="flex flex-col w-full">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-base font-semibold text-on-surface">${t('wlt_txs_title', 'Transaction History')}</h2>
            <button type="button" onclick="if(typeof refreshCurrentAccountBalance==='function') refreshCurrentAccountBalance(); if(typeof refreshPersonalTransactions==='function') refreshPersonalTransactions().then(()=>window.BlocTagSimpleMode.refresh());"
              class="w-8 h-8 rounded-full bg-surface-container-low flex items-center justify-center text-on-surface-variant hover:text-primary transition-colors cursor-pointer" title="Refresh">
              <span class="material-symbols-outlined notranslate text-[18px]" translate="no">sync</span>
            </button>
          </div>

          <!-- Filter Pills (All, Incoming, Outgoing) -->
          <div class="flex items-center gap-1 p-1 bg-surface-container-low rounded-full mb-3.5">
            <button type="button" onclick="window.BlocTagSimpleMode.setTxFilter('all')"
              class="flex-1 py-1.5 px-3 rounded-full text-center text-xs transition-all cursor-pointer ${simpleState.txFilter === 'all' ? 'bg-surface-container-high text-on-surface font-semibold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}">
              ${t('wlt_filter_all', 'All')}
            </button>
            <button type="button" onclick="window.BlocTagSimpleMode.setTxFilter('incoming')"
              class="flex-1 py-1.5 px-3 rounded-full text-center text-xs transition-all cursor-pointer ${simpleState.txFilter === 'incoming' ? 'bg-surface-container-high text-on-surface font-semibold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}">
              ${t('wlt_filter_in', 'Incoming')}
            </button>
            <button type="button" onclick="window.BlocTagSimpleMode.setTxFilter('outgoing')"
              class="flex-1 py-1.5 px-3 rounded-full text-center text-xs transition-all cursor-pointer ${simpleState.txFilter === 'outgoing' ? 'bg-surface-container-high text-on-surface font-semibold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}">
              ${t('wlt_filter_out', 'Outgoing')}
            </button>
          </div>

          <!-- Transactions Stream -->
          <div class="flex flex-col gap-2 w-full">
            ${filteredTxs.length === 0 ? `
              <div class="p-6 rounded-2xl bg-surface-container-low text-center text-xs text-on-surface-variant">
                ${t('wlt_empty_txs', 'No transactions found in this filter.')}
              </div>
            ` : filteredTxs.slice(0, 25).map((tx) => {
      const meta = typeof window.classifyPersonalTx === 'function'
        ? window.classifyPersonalTx(tx, acc.address)
        : { title: 'BCT Transfer', icon: 'swap_horiz', iconColor: 'text-primary', isIncoming: true, sign: '+', displayAmount: Number(tx.amount || 0), counterparty: tx.receiver || '--' };
      const amtStr = typeof window.formatBct === 'function' ? window.formatBct(Math.abs(meta.displayAmount), 4) : Number(meta.displayAmount || 0).toFixed(4);
      const timeStr = typeof window.formatTimeAgo === 'function' ? window.formatTimeAgo(tx.timestamp) : '';
      const cpShort = typeof window.shortAddr === 'function' ? window.shortAddr(meta.counterparty) : String(meta.counterparty || '');
      const txHashAttr = escAttr(tx.tx_hash || tx.hash || '');

      return `
                <div onclick="window.BlocTagSimpleMode.openTxByHash('${txHashAttr}')"
                  class="flex items-center justify-between p-3 rounded-2xl bg-surface-container-low hover:bg-surface-container transition-colors cursor-pointer">
                  <div class="flex items-center gap-3 min-w-0">
                    <div class="w-10 h-10 rounded-full bg-surface-container-high flex items-center justify-center shrink-0 ${esc(meta.iconColor)}">
                      <span class="material-symbols-outlined notranslate text-[20px]" translate="no">${esc(meta.icon)}</span>
                    </div>
                    <div class="flex flex-col min-w-0">
                      <span class="text-xs font-semibold text-on-surface truncate">${esc(meta.title)}</span>
                      <div class="flex items-center gap-1.5 text-[11px] text-on-surface-variant truncate font-mono">
                        <span>${esc(cpShort)}</span>
                        <span class="opacity-40">•</span>
                        <span class="font-sans">${esc(timeStr)}</span>
                      </div>
                    </div>
                  </div>
                  <div class="flex flex-col items-end shrink-0 pl-2">
                    <span class="text-xs font-mono font-semibold ${meta.isIncoming ? 'text-primary' : 'text-on-surface'}">${meta.displayAmount > 0 ? esc(meta.sign) : ''}${esc(amtStr)} BCT</span>
                    <div class="flex items-center gap-1">
                      <span class="text-[10px] text-on-surface-variant">${tx.status === 'mempool' ? t('wlt_tx_pending', 'Pending') : t('wlt_tx_confirmed', 'Confirmed')}</span>
                      <span class="w-1.5 h-1.5 rounded-full ${tx.status === 'mempool' ? 'bg-secondary animate-pulse' : 'bg-primary'}"></span>
                    </div>
                  </div>
                </div>
              `;
    }).join('')}
          </div>
        </div>
      </main>
    `;
  }

  // ── SCR-WLT-SEND: Para Gönder (Mobil) ──────────────────────────────────────
  function renderScreenWalletSend() {
    const acc = getActiveWallet();
    if (!acc) return renderScreenOnboardingWelcome();

    const bal = Number(acc.balance || 0);
    const balStr = typeof window.formatBct === 'function' ? window.formatBct(bal, 4) : bal.toFixed(4);
    const preAmt = simpleState.sendPrefillAmount || '';
    const preRec = simpleState.sendPrefillRecipient || '';

    return `
      ${renderTopBar(t('top_send', 'Send Crypto'), true)}
      <main class="flex-1 flex flex-col w-full px-5 pt-2 pb-24 simple-screen-animate">
        <div class="flex items-center justify-between py-2">
          <div class="flex flex-col">
            <span class="text-[10px] text-outline uppercase tracking-wider font-mono">${t('send_badge', 'Transaction')}</span>
            <h1 class="text-xl font-semibold text-on-surface">${t('send_title', 'Send BCT')}</h1>
          </div>
          <div class="flex items-center gap-1.5 bg-surface-container-high px-2.5 py-1 rounded-full text-on-surface-variant text-[11px]">
            <span class="w-1.5 h-1.5 rounded-full bg-primary animate-ping"></span>
            <span>${t('send_fast_mode', 'Fast Mode')}</span>
          </div>
        </div>

        <!-- Asset Selector Chip -->
        <section class="flex flex-col gap-1.5 mt-1">
          <div class="flex items-center justify-between px-1">
            <span class="text-xs text-on-surface-variant font-medium">${t('send_active_asset', 'Active Asset')}</span>
            <span class="text-xs text-primary font-mono">${t('send_available', 'Available:')} ${esc(balStr)} BCT</span>
          </div>
          <div class="flex gap-2 py-1">
            <div class="flex items-center gap-2.5 px-4 py-2.5 rounded-2xl bg-surface-container-high text-on-surface border border-primary/25">
              <div class="w-8 h-8 rounded-full bg-primary-container/20 flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined notranslate text-primary text-[20px]" translate="no">currency_exchange</span>
              </div>
              <div class="flex flex-col text-left">
                <span class="text-xs font-semibold text-on-surface leading-tight">BCT (BlocTag L1)</span>
                <span class="text-[11px] font-mono text-on-surface-variant leading-tight">${esc(balStr)} BCT</span>
              </div>
            </div>
          </div>
        </section>

        <!-- Hero Amount Card (Exact Stitch Para Gönder Mobil) -->
        <section class="flex flex-col items-center justify-center my-4 bg-surface-container-low/70 rounded-2xl py-6 px-4 shadow-sm relative overflow-hidden border border-outline-variant/15">
          <div class="absolute -right-8 -top-8 w-28 h-28 rounded-full bg-primary/5 blur-2xl pointer-events-none"></div>
          <div class="flex items-baseline justify-center gap-1.5 w-full">
            <span class="text-2xl font-bold text-outline">BCT</span>
            <input id="simple-send-amount" type="text" inputmode="decimal" placeholder="0"
              value="${esc(preAmt)}"
              oninput="window.BlocTagSimpleMode.updateSendPreview()"
              class="bg-transparent text-[38px] leading-[42px] font-bold text-on-surface text-center focus:outline-none w-52 caret-primary tracking-tight font-mono" />
          </div>
          <div class="flex items-center gap-1 mt-1.5 text-on-surface-variant text-xs font-mono">
            <span>${t('send_net_received', 'Net Received by Recipient:')}</span>
            <strong class="text-primary" id="simple-send-net-preview">0.00 BCT</strong>
          </div>
          <div class="grid grid-cols-4 gap-2 w-full max-w-xs mt-5">
            <button type="button" onclick="window.BlocTagSimpleMode.setSendPct(0.25)"
              class="py-2 rounded-full bg-surface-container-high hover:bg-surface-container-highest text-on-surface text-xs font-medium active:scale-95 transition-all cursor-pointer">%25</button>
            <button type="button" onclick="window.BlocTagSimpleMode.setSendPct(0.50)"
              class="py-2 rounded-full bg-surface-container-high hover:bg-surface-container-highest text-on-surface text-xs font-medium active:scale-95 transition-all cursor-pointer">%50</button>
            <button type="button" onclick="window.BlocTagSimpleMode.setSendPct(0.75)"
              class="py-2 rounded-full bg-surface-container-high hover:bg-surface-container-highest text-on-surface text-xs font-medium active:scale-95 transition-all cursor-pointer">%75</button>
            <button type="button" onclick="window.BlocTagSimpleMode.setSendPct(1.00)"
              class="py-2 rounded-full bg-surface-container-highest text-primary text-xs font-semibold active:scale-95 transition-all cursor-pointer">${t('send_pct_all', 'All')}</button>
          </div>
        </section>

        <!-- Recipient Input -->
        <section class="flex flex-col gap-1.5 mb-3">
          <label class="text-xs text-on-surface-variant font-medium px-1" for="simple-send-recipient">${t('send_recipient_label', 'Recipient Address or @name.bct')}</label>
          <div class="flex items-center bg-surface-container-low rounded-2xl px-3.5 py-3 border border-outline-variant/15 focus-within:border-primary transition-colors">
            <span class="material-symbols-outlined notranslate text-outline text-[20px] mr-2" translate="no">alternate_email</span>
            <input id="simple-send-recipient" type="text" autocomplete="off" spellcheck="false"
              value="${esc(preRec)}"
              placeholder="${t('send_recipient_ph', 'BCT... or user.bct')}"
              class="bg-transparent flex-1 text-xs font-mono text-on-surface placeholder:text-outline/60 focus:outline-none min-w-0" />
            <div class="flex items-center gap-1.5 shrink-0 ml-2">
              <button type="button" onclick="window.BlocTagSimpleMode.pasteRecipient()"
                class="flex items-center gap-1 bg-surface-container-highest px-2.5 py-1 rounded-full text-on-surface text-[11px] font-medium hover:brightness-110 active:scale-95 transition-all cursor-pointer">
                <span class="material-symbols-outlined notranslate text-[13px]" translate="no">content_paste</span>
                <span>${t('send_paste', 'Paste')}</span>
              </button>
              <button type="button" onclick="if(typeof openQrScannerModal==='function') openQrScannerModal();"
                class="w-8 h-8 rounded-full bg-surface-container-highest flex items-center justify-center text-on-surface hover:brightness-110 active:scale-95 transition-all cursor-pointer" title="Scan QR">
                <span class="material-symbols-outlined notranslate text-[17px]" translate="no">qr_code_scanner</span>
              </button>
            </div>
          </div>
        </section>

        <!-- Fee Info -->
        <div class="flex items-center justify-between bg-surface-container-low/50 px-4 py-2.5 rounded-2xl mb-5 text-on-surface-variant text-xs">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined notranslate text-[17px] text-primary" translate="no">local_gas_station</span>
            <span>${t('send_network_fee', 'Network Fee (1% Protocol):')}</span>
            <span class="text-on-surface font-mono font-medium" id="simple-send-fee-preview">0.00 BCT</span>
          </div>
          <div class="flex items-center gap-1">
            <span class="w-1.5 h-1.5 rounded-full bg-primary"></span>
            <span class="text-[11px]">${t('send_instant_conf', 'Instant Confirmation')}</span>
          </div>
        </div>

        <!-- Submit Button -->
        <div class="flex flex-col gap-2 mt-auto">
          <button type="button" id="simple-send-submit-btn" onclick="window.BlocTagSimpleMode.executeSend()"
            class="w-full h-[52px] rounded-full bg-primary text-on-primary text-base font-semibold flex items-center justify-center gap-2 shadow-lg active:scale-[0.98] transition-transform cursor-pointer">
            <span>${t('send_submit_btn', 'Continue and Sign')}</span>
            <span class="material-symbols-outlined notranslate text-[20px]" translate="no">arrow_forward</span>
          </button>
          <div class="flex items-center justify-center gap-3 py-1 text-outline text-[11px]">
            <span class="flex items-center gap-1">
              <span class="material-symbols-outlined notranslate text-[14px] text-primary" translate="no">verified_user</span>
              <span>${t('send_ecdsa_signed', 'End-to-End ECDSA Signed')}</span>
            </span>
            <span>•</span>
            <span class="flex items-center gap-1">
              <span class="material-symbols-outlined notranslate text-[14px] text-primary" translate="no">timer</span>
              <span>${t('send_instant_block', 'Instant On-Chain Seal')}</span>
            </span>
          </div>
        </div>
      </main>
    `;
  }

  // ── ON-CHAIN AVATAR RENDER HELPER (Strict XSS & Color Sanitization) ───────
  function renderAvatarCircleHtml(avatarObj, fallbackHtml) {
    if (avatarObj && typeof avatarObj === 'object' && typeof avatarObj.image_url === 'string') {
      const url = avatarObj.image_url.trim();
      if (url.startsWith('/avatars/') && !url.includes('..') && !url.includes('"') && !url.includes("'")) {
        const rawBg = String(avatarObj.bg_color || '#FFFFFF').trim().toUpperCase();
        const safeBg = /^#[0-9A-F]{6}$/.test(rawBg) ? rawBg : '#FFFFFF';
        const altName = esc(avatarObj.name || 'Avatar');
        return `<div class="w-full h-full rounded-full overflow-hidden flex items-center justify-center" style="background-color:${safeBg};"><img src="${url}" alt="${altName}" class="w-full h-full object-contain p-0.5 select-none pointer-events-none" loading="lazy" /></div>`;
      }
    }
    return fallbackHtml;
  }

  // ── SCR-SPC-REEL: TikTok / Instagram Style Vertical Snap Card ──────────────
  function renderSimpleReelCard(post, acc, index, total) {
    if (!post || typeof post !== 'object') return '';
    const pid = escAttr(post.post_id || post.id || '');
    const authorAddr = String(post.author || '');
    const authorBns = (post.author_bns && post.author_bns !== 'anonymous') ? String(post.author_bns).replace(/^@/, '') : '';
    const displayName = authorBns ? ('@' + authorBns) : (typeof window.shortAddr === 'function' ? window.shortAddr(authorAddr) : authorAddr.slice(0, 10));
    const subHandle = authorBns ? (typeof window.shortAddr === 'function' ? window.shortAddr(authorAddr) : '') : '@onchain';
    const timeAgo = typeof window.formatTimeAgo === 'function' ? window.formatTimeAgo(post.timestamp) : '';
    const myAddr = acc ? String(acc.address || '').toLowerCase() : '';
    const isLiked = Boolean(myAddr && Array.isArray(post.likes) && post.likes.includes(myAddr));
    const likesCount = Number(post.likes_count || (Array.isArray(post.likes) ? post.likes.length : 0));
    const commentsCount = Number(post.comments_count || (Array.isArray(post.comments) ? post.comments.length : 0));
    const bodyHtml = safeFormatSimpleBody(post.content || '');
    const profileTargetAttr = escAttr(authorBns || authorAddr);
    const avatarChar = (authorBns || authorAddr || 'B').replace(/^@/, '')[0].toUpperCase();
    const authorAvatarHtml = renderAvatarCircleHtml(post.author_avatar, avatarChar);

    return `
      <section class="simple-reel-slide w-full h-full min-h-full max-h-full snap-start snap-always flex flex-col items-center justify-center p-3 relative shrink-0 select-none" data-post-index="${index}">
        <!-- Centered Card (Fixed Viewport • Single Post Focus) -->
        <article class="w-full max-w-[430px] rounded-3xl bg-surface-container-low border border-outline-variant/15 shadow-2xl p-5 flex flex-col justify-between relative h-[86%] max-h-[540px] overflow-hidden"
                 onclick="window.BlocTagSimpleMode.go('SCR-SPC-04', { postId: '${pid}' })">

          <!-- Top Author Cluster -->
          <div class="flex items-center justify-between gap-2 shrink-0 pb-3 border-b border-outline-variant/10">
            <div class="flex items-center gap-2.5 min-w-0 cursor-pointer"
                 onclick="event.stopPropagation(); window.BlocTagSimpleMode.go('SCR-PRF-05', { profileTarget: '${profileTargetAttr}' })">
              <div class="w-10 h-10 rounded-full bg-surface-container-high overflow-hidden flex items-center justify-center text-primary font-bold font-mono text-sm shrink-0 ring-1 ring-primary/25">
                ${authorAvatarHtml}
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1 min-w-0">
                  <span class="text-xs font-bold text-on-surface truncate">${esc(displayName)}</span>
                  <span class="material-symbols-outlined notranslate text-primary text-[15px] shrink-0" style="font-variation-settings: 'FILL' 1;" translate="no">verified</span>
                </div>
                <div class="flex items-center gap-1.5 text-[10.5px] text-on-surface-variant">
                  <span class="font-mono truncate">${esc(subHandle)}</span>
                  <span>•</span>
                  <span>${esc(timeAgo)}</span>
                </div>
              </div>
            </div>

            <!-- Slide Counter Badge & Options -->
            <div class="flex items-center gap-1 shrink-0">
              <span class="px-2 py-0.5 rounded-full bg-surface-container text-primary text-[10.5px] font-mono font-bold">
                ${index + 1}/${total}
              </span>
              <button type="button" aria-label="${t('space_share_btn', 'Share')}"
                onclick="event.stopPropagation(); if(typeof openPostShareModal==='function') openPostShareModal('${pid}', event);"
                class="w-8 h-8 rounded-full flex items-center justify-center text-on-surface-variant hover:text-on-surface cursor-pointer">
                <span class="material-symbols-outlined notranslate text-[18px]" translate="no">more_horiz</span>
              </button>
            </div>
          </div>

          <!-- Middle Tweet Content (Centered, Large, Immersive) -->
          <div class="simple-post-body flex-1 flex flex-col justify-center py-4 my-auto text-base sm:text-lg text-on-surface font-normal leading-relaxed overflow-y-auto no-scrollbar">
            ${bodyHtml}
          </div>

          <!-- Bottom Action Bar & Status Strip -->
          <div class="shrink-0 pt-3 border-t border-outline-variant/10 flex items-center justify-between text-on-surface-variant">
            <!-- Left Meta Stats -->
            <div class="flex items-center gap-2">
              <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-primary/10 text-primary text-[11px] font-mono font-semibold">
                <span class="material-symbols-outlined notranslate text-[13px]" translate="no">monetization_on</span>
                <span>+0.004 BCT</span>
              </span>
              <span class="text-[10px] text-outline font-mono">#${post.block_index || 'L1'}</span>
            </div>

            <!-- Right Interactive Actions (TikTok / Instagram style) -->
            <div class="flex items-center gap-2">
              <!-- Like Button -->
              <button type="button"
                onclick="event.stopPropagation(); window.BlocTagSimpleMode.likePost('${pid}', event)"
                class="flex items-center gap-1 py-1 px-2 rounded-full hover:bg-surface-container transition-all group cursor-pointer ${isLiked ? 'text-tertiary font-bold' : 'text-on-surface-variant hover:text-tertiary'}">
                <span class="material-symbols-outlined notranslate text-[20px] group-hover:scale-125 active:scale-95 transition-transform"
                  ${isLiked ? 'style="font-variation-settings: \'FILL\' 1;"' : ''} translate="no">favorite</span>
                <span class="text-xs font-mono tabular-nums">${likesCount}</span>
              </button>

              <!-- Comment Button -->
              <button type="button"
                onclick="event.stopPropagation(); window.BlocTagSimpleMode.go('SCR-SPC-04', { postId: '${pid}' })"
                class="flex items-center gap-1 py-1 px-2 rounded-full hover:bg-surface-container text-on-surface-variant hover:text-primary transition-all group cursor-pointer">
                <span class="material-symbols-outlined notranslate text-[20px] group-hover:scale-110 active:scale-95 transition-transform" translate="no">chat_bubble</span>
                <span class="text-xs font-mono tabular-nums">${commentsCount}</span>
              </button>

              <!-- Tip Button -->
              <button type="button"
                onclick="event.stopPropagation(); window.BlocTagSimpleMode.tipAuthor('${escAttr(authorAddr)}')"
                class="w-8 h-8 rounded-full bg-primary/15 text-primary hover:bg-primary hover:text-on-primary transition-all flex items-center justify-center active:scale-90 cursor-pointer"
                title="${t('space_tip', 'Tip')}">
                <span class="material-symbols-outlined notranslate text-[16px]" translate="no">volunteer_activism</span>
              </button>
            </div>
          </div>
        </article>

        <!-- Subtle Animated Swipe-Up Indicator (TikTok style) -->
        <div class="flex items-center justify-center gap-1 text-[11px] text-outline/80 font-medium animate-pulse mt-2 cursor-pointer"
             onclick="window.BlocTagSimpleMode.reelNext()">
          <span class="material-symbols-outlined notranslate text-[16px]" translate="no">keyboard_arrow_up</span>
          <span>${index < total - 1 ? t('swipe_up_hint', 'Swipe up for next') : t('feed_reached_end', 'You are all caught up')}</span>
        </div>
      </section>
    `;
  }

  // ── SCR-SPC-03: Space - Sade Sosyal Akış (Default Simple Screen) ───────────
  function renderScreenSpaceFeed() {
    const acc = getActiveWallet();
    const myHandle = getMyPrimaryHandle();
    const displayTag = getDisplayHandleOrAddr(acc ? acc.address : '', myHandle);

    const posts = (typeof spacePostsCache !== 'undefined' && Array.isArray(spacePostsCache)) ? spacePostsCache : [];
    const q = String(simpleState.searchQuery || '').trim().toLowerCase();

    const filteredPosts = posts.filter(p => {
      if (!p) return false;
      if (simpleState.feedFilter === 'following' && acc && acc.address) {
        // Show user's own posts or posts from verified BNS handles
        const isMine = String(p.author || '').toLowerCase() === acc.address.toLowerCase();
        const hasBns = Boolean(p.author_bns && p.author_bns !== 'anonymous');
        if (!isMine && !hasBns) return false;
      }
      if (q) {
        const content = String(p.content || '').toLowerCase();
        const author = String(p.author || '').toLowerCase();
        const bns = String(p.author_bns || '').toLowerCase();
        return content.includes(q) || author.includes(q) || bns.includes(q);
      }
      return true;
    });

    const myProfileForHeader = acc ? getSimpleProfileData(acc.address) : null;
    if (!myProfileForHeader && acc && acc.address) {
      fetchSimpleProfile(acc.address);
    }
    const myMiniAvatarHtml = renderAvatarCircleHtml(
      myProfileForHeader?.avatar,
      '<span class="material-symbols-outlined notranslate text-primary text-[20px]" translate="no">account_circle</span>'
    );

    const isSnap = (simpleState.feedLayout !== 'classic');

    if (isSnap) {
      return `
        ${renderTopBar('Space', false)}
        <main class="flex-1 flex flex-col w-full h-[calc(100dvh-120px)] max-h-[calc(100dvh-120px)] overflow-hidden relative simple-screen-animate">
          <!-- Minimal Sub-Header Strip -->
          <div class="flex items-center justify-between px-4 py-2 shrink-0 border-b border-outline-variant/10 bg-surface/90 backdrop-blur-md z-10">
            <div class="flex items-center gap-2.5 min-w-0 cursor-pointer"
                 onclick="window.BlocTagSimpleMode.go('${acc ? 'SCR-PRF-05' : 'SCR-ONB-01'}', { profileTarget: '' })">
              <div class="relative shrink-0">
                <div class="w-9 h-9 rounded-full bg-surface-container-high flex items-center justify-center overflow-hidden">
                  ${myMiniAvatarHtml}
                </div>
                <span class="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-primary ring-2 ring-surface"></span>
              </div>
              <div class="flex flex-col min-w-0">
                <span class="px-2.5 py-0.5 rounded-full bg-surface-container-high text-primary font-mono text-xs font-semibold truncate max-w-[170px]">
                  ${esc(displayTag)}
                </span>
                <span id="simple-space-bal-subtitle" class="text-[10.5px] text-on-surface-variant truncate">
                  ${acc ? (typeof window.formatBct === 'function' ? window.formatBct(acc.balance || 0, 2) + ' BCT • ' + t('space_active_l1', 'Active L1') : t('space_active_l1', 'Active L1')) : t('space_create_wallet_hint', 'Create wallet (+1.00 BCT bonus)')}
                </span>
              </div>
            </div>

            <!-- Top Control Actions -->
            <div class="flex items-center gap-1.5 shrink-0">
              <!-- Feed Filter Pill (All / Following) -->
              <button type="button"
                onclick="window.BlocTagSimpleMode.setFeedFilter('${simpleState.feedFilter === 'following' ? 'all' : 'following'}')"
                class="px-2.5 py-1 rounded-full text-[11px] font-semibold transition-all cursor-pointer flex items-center gap-1 ${simpleState.feedFilter === 'following' ? 'bg-primary text-on-primary' : 'bg-surface-container-low text-on-surface-variant hover:text-on-surface'}">
                <span class="material-symbols-outlined notranslate text-[13px]" translate="no">${simpleState.feedFilter === 'following' ? 'verified' : 'public'}</span>
                <span>${simpleState.feedFilter === 'following' ? t('space_filter_following', 'Following') : t('space_filter_all', 'All')}</span>
              </button>

              <!-- Toggle between TikTok/Reels Snap and Classic List View -->
              <button type="button" aria-label="${t('feed_layout_list', 'Switch to List View')}"
                title="${t('feed_layout_list', 'Switch to List View')}"
                onclick="window.BlocTagSimpleMode.toggleFeedLayout()"
                class="w-9 h-9 rounded-full bg-surface-container-low flex items-center justify-center text-on-surface-variant hover:text-primary transition-colors active:scale-95 cursor-pointer">
                <span class="material-symbols-outlined notranslate text-[20px]" translate="no">view_agenda</span>
              </button>

              <!-- Search Toggle -->
              <button type="button" aria-label="${t('space_search_btn', 'Search')}" onclick="window.BlocTagSimpleMode.toggleSearch()"
                class="w-9 h-9 rounded-full bg-surface-container-low flex items-center justify-center text-on-surface-variant hover:text-primary transition-colors active:scale-95 cursor-pointer">
                <span class="material-symbols-outlined notranslate text-[20px]" translate="no">search</span>
              </button>
            </div>
          </div>

          ${simpleState.searchBarOpen ? `
            <div class="px-4 py-2 bg-surface shrink-0 border-b border-outline-variant/10 z-10">
              <div class="flex items-center bg-surface-container-low rounded-full px-3.5 py-1.5 border border-outline-variant/25">
                <span class="material-symbols-outlined notranslate text-[17px] text-outline mr-2" translate="no">search</span>
                <input id="simple-space-search-input" type="search" value="${esc(simpleState.searchQuery)}"
                  oninput="window.BlocTagSimpleMode.setSearchQuery(this.value)"
                  placeholder="${t('space_search_ph', 'Search posts, #tags or @users...')}"
                  class="w-full bg-transparent text-xs text-on-surface placeholder:text-outline focus:outline-none" />
              </div>
            </div>
          ` : ''}

          <!-- Vertical Snap Reel (TikTok / Reels Immersion Container) -->
          <div id="simple-reel-container" class="simple-reel-viewport flex-1 w-full overflow-y-scroll snap-y snap-mandatory no-scrollbar">
            ${filteredPosts.length === 0 ? `
              <div class="h-full flex flex-col items-center justify-center p-8 text-center text-on-surface-variant">
                <span class="material-symbols-outlined notranslate text-[36px] text-primary mb-2" translate="no">forum</span>
                <span class="text-xs font-semibold">${t('space_empty_posts', 'Posts are loading or none found in this filter...')}</span>
              </div>
            ` : filteredPosts.map((post, idx) => renderSimpleReelCard(post, acc, idx, filteredPosts.length)).join('')}
          </div>

          <!-- Floating Action Button (+ Post Compose) -->
          <div class="fixed z-40" style="bottom: calc(var(--simple-bottom-nav-h, 64px) + 14px); right: max(16px, calc(50% - 224px));">
            <button type="button" onclick="window.BlocTagSimpleMode.focusComposer()"
              class="h-11 px-4 rounded-full bg-primary text-on-primary text-xs font-semibold flex items-center gap-1.5 shadow-[0_8px_20px_rgba(16,185,129,0.35)] hover:scale-105 active:scale-95 transition-all cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[18px]" translate="no">edit</span>
              <span>${t('space_compose_fab', 'Post')}</span>
            </button>
          </div>
        </main>
      `;
    }

    return `
      ${renderTopBar('Space', false)}
      <main class="flex-1 flex flex-col w-full px-4 pt-2 pb-24 simple-screen-animate">
        <!-- Community Space Sub-Header & Live Status (Exact Stitch SCR-SPC-03) -->
        <div class="flex items-center justify-between py-2">
          <div class="flex items-center gap-2.5 min-w-0 cursor-pointer"
               onclick="window.BlocTagSimpleMode.go('${acc ? 'SCR-PRF-05' : 'SCR-ONB-01'}', { profileTarget: '' })">
            <div class="relative shrink-0">
              <div class="w-10 h-10 rounded-full bg-surface-container-high flex items-center justify-center overflow-hidden">
                ${myMiniAvatarHtml}
              </div>
              <span class="absolute bottom-0 right-0 w-3 h-3 rounded-full bg-primary ring-2 ring-surface"></span>
            </div>
            <div class="flex flex-col min-w-0">
              <div class="flex items-center gap-1.5">
                <span class="px-2.5 py-0.5 rounded-full bg-surface-container-high text-primary font-mono text-xs font-semibold truncate max-w-[190px]">
                  ${esc(displayTag)}
                </span>
              </div>
              <span id="simple-space-bal-subtitle" class="text-[11px] text-on-surface-variant truncate mt-0.5">
                ${acc ? (typeof window.formatBct === 'function' ? window.formatBct(acc.balance || 0, 2) + ' BCT • ' + t('space_active_l1', 'Active L1') : t('space_active_l1', 'Active L1')) : t('space_create_wallet_hint', 'Create wallet (+1.00 BCT bonus)')}
              </span>
            </div>
          </div>

          <div class="flex items-center gap-1.5 shrink-0">
            <button type="button" aria-label="${t('feed_layout_snap', 'Switch to TikTok / Reels View')}"
              title="${t('feed_layout_snap', 'Switch to TikTok / Reels View')}"
              onclick="window.BlocTagSimpleMode.toggleFeedLayout()"
              class="w-9 h-9 rounded-full bg-surface-container-low flex items-center justify-center text-on-surface-variant hover:text-primary transition-colors active:scale-95 cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[20px]" translate="no">movie</span>
            </button>
            <button type="button" aria-label="${t('space_search_btn', 'Search')}" onclick="window.BlocTagSimpleMode.toggleSearch()"
              class="w-9 h-9 rounded-full bg-surface-container-low flex items-center justify-center text-on-surface-variant hover:text-primary transition-colors active:scale-95 cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[20px]" translate="no">search</span>
            </button>
          </div>
        </div>

        ${simpleState.searchBarOpen ? `
          <div class="mb-2.5 flex items-center bg-surface-container-low rounded-full px-3.5 py-2 border border-outline-variant/25">
            <span class="material-symbols-outlined notranslate text-[17px] text-outline mr-2" translate="no">search</span>
            <input id="simple-space-search-input" type="search" value="${esc(simpleState.searchQuery)}"
              oninput="window.BlocTagSimpleMode.setSearchQuery(this.value)"
              placeholder="${t('space_search_ph', 'Search posts, #tags or @users...')}"
              class="w-full bg-transparent text-xs text-on-surface placeholder:text-outline focus:outline-none" />
          </div>
        ` : ''}

        <!-- Share Quick Composer Card (Exact Stitch SCR-SPC-03) -->
        <div class="mt-1 bg-surface-container-low rounded-2xl shadow-sm p-3.5 border border-outline-variant/15">
          <div class="flex items-start gap-2.5">
            <div class="w-9 h-9 rounded-full bg-surface-container-high overflow-hidden shrink-0 flex items-center justify-center text-primary">
              <span class="material-symbols-outlined notranslate text-[20px]" translate="no">person</span>
            </div>
            <div class="flex-1 min-w-0">
              <textarea id="simple-composer-input" rows="2" maxlength="280"
                placeholder="${t('space_composer_ph', 'Share something on-chain... (0.10 BCT)')}"
                class="w-full bg-transparent text-sm text-on-surface placeholder:text-outline resize-none focus:outline-none leading-relaxed"></textarea>
              <div class="flex items-center justify-between pt-1.5 border-t border-outline-variant/10">
                <div class="flex items-center gap-1 text-on-surface-variant">
                  <button type="button" onclick="window.BlocTagSimpleMode.insertComposerTag('$BCT ')"
                    class="px-2 py-1 rounded-full hover:bg-surface-container-high text-primary font-mono text-[11px] font-semibold transition-colors active:scale-95 cursor-pointer">
                    $BCT
                  </button>
                  <button type="button" onclick="window.BlocTagSimpleMode.insertComposerTag('🔥 ')"
                    class="w-8 h-8 rounded-full flex items-center justify-center hover:bg-surface-container-high hover:text-primary transition-colors active:scale-95 cursor-pointer">
                    <span class="material-symbols-outlined notranslate text-[18px]" translate="no">sentiment_satisfied</span>
                  </button>
                  <button type="button" onclick="window.BlocTagSimpleMode.insertComposerTag('@')"
                    class="w-8 h-8 rounded-full flex items-center justify-center hover:bg-surface-container-high hover:text-primary transition-colors active:scale-95 cursor-pointer">
                    <span class="material-symbols-outlined notranslate text-[18px]" translate="no">alternate_email</span>
                  </button>
                </div>
                <button type="button" id="simple-post-submit-btn" onclick="window.BlocTagSimpleMode.submitPost()"
                  class="h-9 px-4 bg-primary text-on-primary text-xs rounded-full flex items-center justify-center font-semibold hover:brightness-95 active:scale-95 transition-all shadow-sm cursor-pointer">
                  ${t('space_publish', 'Publish')}
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Segmented Feed Switcher (All / Verified & Following) -->
        <div class="flex p-1 bg-surface-container-low rounded-full mt-3 border border-outline-variant/10">
          <button type="button" onclick="window.BlocTagSimpleMode.setFeedFilter('all')"
            class="flex-1 text-center rounded-full text-xs font-medium transition-all py-1.5 cursor-pointer ${simpleState.feedFilter === 'all' ? 'bg-surface-container text-on-surface font-semibold shadow-xs' : 'text-on-surface-variant hover:text-on-surface'}">
            ${t('space_filter_all', 'All')}
          </button>
          <button type="button" onclick="window.BlocTagSimpleMode.setFeedFilter('following')"
            class="flex-1 text-center rounded-full text-xs font-medium transition-all py-1.5 cursor-pointer ${simpleState.feedFilter === 'following' ? 'bg-surface-container text-on-surface font-semibold shadow-xs' : 'text-on-surface-variant hover:text-on-surface'}">
            ${t('space_filter_following', 'Verified & Following')}
          </button>
        </div>

        <!-- Feed List Stream (Exact Stitch Post Cards) -->
        <div class="flex flex-col gap-2.5 mt-3 w-full min-w-0" id="simple-feed-container">
          ${filteredPosts.length === 0 ? `
            <div class="p-8 rounded-2xl bg-surface-container-low text-center flex flex-col items-center gap-2 text-on-surface-variant">
              <span class="material-symbols-outlined notranslate text-[28px] text-primary" translate="no">forum</span>
              <span class="text-xs">${t('space_empty_posts', 'Posts are loading or none found in this filter...')}</span>
            </div>
          ` : filteredPosts.slice(0, 35).map(post => renderSimplePostCard(post, acc)).join('')}
        </div>

        <!-- Floating Action Button (+ Post) -->
        <div class="fixed z-40" style="bottom: calc(var(--simple-bottom-nav-h, 64px) + 14px); right: max(16px, calc(50% - 224px));">
          <button type="button" onclick="window.BlocTagSimpleMode.focusComposer()"
            class="h-11 px-4 rounded-full bg-primary text-on-primary text-xs font-semibold flex items-center gap-1.5 shadow-[0_8px_20px_rgba(16,185,129,0.35)] hover:scale-105 active:scale-95 transition-all cursor-pointer">
            <span class="material-symbols-outlined notranslate text-[18px]" translate="no">edit</span>
            <span>${t('space_compose_fab', 'Post')}</span>
          </button>
        </div>
      </main>
    `;
  }

  function safeFormatSimpleBody(rawContent) {
    try {
      const str = String(rawContent ?? '');
      if (!str.trim()) return '';
      if (typeof window.formatSpaceBodyHtml === 'function') {
        const formatted = window.formatSpaceBodyHtml(str);
        if (typeof formatted === 'string' && formatted.length > 0) return formatted;
      }
      return esc(str).replace(/\n/g, '<br/>');
    } catch (_e) {
      return esc(String(rawContent ?? '')).replace(/\n/g, '<br/>');
    }
  }

  function renderSimplePostCard(post, acc) {
    if (!post || typeof post !== 'object') return '';
    const pid = escAttr(post.post_id || post.id || '');
    const authorAddr = String(post.author || '');
    const authorBns = (post.author_bns && post.author_bns !== 'anonymous') ? String(post.author_bns).replace(/^@/, '') : '';
    const displayName = authorBns ? ('@' + authorBns) : (typeof window.shortAddr === 'function' ? window.shortAddr(authorAddr) : authorAddr.slice(0, 10));
    const subHandle = authorBns ? (typeof window.shortAddr === 'function' ? window.shortAddr(authorAddr) : '') : '@onchain';
    const timeAgo = typeof window.formatTimeAgo === 'function' ? window.formatTimeAgo(post.timestamp) : '';
    const myAddr = acc ? acc.address : '';
    const isLiked = Boolean(myAddr && Array.isArray(post.likes) && post.likes.includes(myAddr));
    const likesCount = Number(post.likes_count || (Array.isArray(post.likes) ? post.likes.length : 0));
    const commentsCount = Number(post.comments_count || (Array.isArray(post.comments) ? post.comments.length : 0));
    const bodyHtml = safeFormatSimpleBody(post.content || '');
    const profileTargetAttr = escAttr(authorBns || authorAddr);
    const postAvatarHtml = renderAvatarCircleHtml(
      post.author_avatar,
      '<span class="material-symbols-outlined notranslate text-[21px]" translate="no">person</span>'
    );

    return `
      <article onclick="window.BlocTagSimpleMode.go('SCR-SPC-04', { postId: '${pid}' })"
        class="simple-post-card bg-surface-container-low rounded-2xl shadow-sm transition-all hover:bg-surface-container p-3.5 border border-outline-variant/10 cursor-pointer">
        <div class="flex items-center justify-between gap-2 min-w-0">
          <div class="flex items-center gap-2.5 min-w-0 flex-1"
               onclick="event.stopPropagation(); window.BlocTagSimpleMode.go('SCR-PRF-05', { profileTarget: '${profileTargetAttr}' })">
            <div class="w-10 h-10 rounded-full bg-surface-container-high overflow-hidden flex items-center justify-center text-primary shrink-0">
              ${postAvatarHtml}
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-1 min-w-0">
                <span class="text-xs font-semibold text-on-surface truncate">${esc(displayName)}</span>
                <span class="material-symbols-outlined notranslate text-primary text-[15px] shrink-0" style="font-variation-settings: 'FILL' 1;" translate="no">verified</span>
              </div>
              <span class="text-[11px] text-on-surface-variant truncate block">${esc(subHandle)} • ${esc(timeAgo)}</span>
            </div>
          </div>
          <button type="button" aria-label="${t('space_share_btn', 'Share')}"
            onclick="event.stopPropagation(); if(typeof openPostShareModal==='function') openPostShareModal('${pid}', event);"
            class="w-8 h-8 rounded-full flex items-center justify-center text-on-surface-variant hover:text-on-surface cursor-pointer shrink-0">
            <span class="material-symbols-outlined notranslate text-[18px]" translate="no">more_horiz</span>
          </button>
        </div>

        <div class="simple-post-body mt-2.5 text-sm text-on-surface">
          ${bodyHtml}
        </div>

        <div class="mt-3.5 flex items-center justify-between pt-2 border-t border-outline-variant/10 text-on-surface-variant">
          <div class="flex items-center gap-4">
            <button type="button"
              onclick="event.stopPropagation(); window.BlocTagSimpleMode.likePost('${pid}', event)"
              class="flex items-center gap-1.5 ${isLiked ? 'text-tertiary font-semibold' : 'hover:text-tertiary'} transition-colors group cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[19px] group-hover:scale-110 transition-transform"
                ${isLiked ? 'style="font-variation-settings: \'FILL\' 1;"' : ''} translate="no">favorite</span>
              <span class="text-xs tabular-nums">${likesCount}</span>
            </button>
            <button type="button"
              onclick="event.stopPropagation(); window.BlocTagSimpleMode.go('SCR-SPC-04', { postId: '${pid}' })"
              class="flex items-center gap-1.5 hover:text-primary transition-colors cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[19px]" translate="no">chat_bubble</span>
              <span class="text-xs tabular-nums">${commentsCount}</span>
            </button>
          </div>
          <button type="button"
            onclick="event.stopPropagation(); window.BlocTagSimpleMode.tipAuthor('${escAttr(authorAddr)}')"
            class="px-3 py-1.5 rounded-full bg-surface-container-high hover:bg-primary hover:text-on-primary text-primary transition-all flex items-center gap-1.5 active:scale-95 cursor-pointer">
            <span class="material-symbols-outlined notranslate text-[15px]" translate="no">volunteer_activism</span>
            <span class="text-[11px] font-semibold">${t('space_tip', 'Tip')}</span>
          </button>
        </div>
      </article>
    `;
  }

  // ── SCR-SPC-04: Space - Gönderi Detayı ─────────────────────────────────────
  function renderScreenPostDetail() {
    const acc = getActiveWallet();
    const posts = (typeof spacePostsCache !== 'undefined' && Array.isArray(spacePostsCache)) ? spacePostsCache : [];
    const post = posts.find(p => String(p.post_id || p.id) === String(simpleState.activePostId)) || posts[0];

    if (!post) {
      return `
        ${renderTopBar(t('top_post_detail', 'Post Details'), true)}
        <main class="flex-1 flex flex-col items-center justify-center p-6 text-center simple-screen-animate">
          <p class="text-xs text-on-surface-variant mb-3">${t('post_not_found', 'Post not found or loading.')}</p>
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-SPC-03')"
            class="px-4 py-2 rounded-full bg-primary text-on-primary text-xs font-semibold cursor-pointer">
            ${t('post_back_to_feed', 'Return to Space Feed')}
          </button>
        </main>
      `;
    }

    const pid = escAttr(post.post_id || post.id || '');
    const authorAddr = String(post.author || '');
    const authorBns = (post.author_bns && post.author_bns !== 'anonymous') ? String(post.author_bns).replace(/^@/, '') : '';
    const displayName = authorBns ? ('@' + authorBns) : (typeof window.shortAddr === 'function' ? window.shortAddr(authorAddr) : authorAddr);
    const myAddr = acc ? acc.address : '';
    const isLiked = Boolean(myAddr && Array.isArray(post.likes) && post.likes.includes(myAddr));
    const likesCount = Number(post.likes_count || (Array.isArray(post.likes) ? post.likes.length : 0));
    const comments = Array.isArray(post.comments) ? post.comments : [];
    const earned = Number(post.author_earnings || 0);
    const fullDate = typeof window.formatFullDate === 'function' ? window.formatFullDate(post.timestamp) : '';
    const bodyHtml = safeFormatSimpleBody(post.content || '');
    const profileTargetAttr = escAttr(authorBns || authorAddr);

    return `
      ${renderTopBar(t('top_post_detail', 'Post Details'), true)}
      <main class="flex-1 flex flex-col w-full min-w-0 px-4 pt-3 pb-36 simple-screen-animate">
        <!-- Main Post Card (Exact Stitch SCR-SPC-04) -->
        <section class="simple-post-card bg-surface-container rounded-2xl flex flex-col shadow-sm p-4 gap-3 border border-outline-variant/15">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2.5 min-w-0 cursor-pointer"
                 onclick="window.BlocTagSimpleMode.go('SCR-PRF-05', { profileTarget: '${profileTargetAttr}' })">
              <div class="w-11 h-11 rounded-full bg-surface-container-high flex items-center justify-center text-primary shrink-0">
                <span class="material-symbols-outlined notranslate text-[24px]" translate="no">person</span>
              </div>
              <div class="flex flex-col min-w-0">
                <div class="flex items-center gap-1">
                  <span class="text-sm font-semibold text-on-surface truncate">${esc(displayName)}</span>
                  <span class="material-symbols-outlined notranslate text-[16px] text-primary" style="font-variation-settings: 'FILL' 1;" translate="no">verified</span>
                </div>
                <span class="text-[11px] font-mono text-on-surface-variant truncate">${esc(typeof window.shortAddr === 'function' ? window.shortAddr(authorAddr) : authorAddr)}</span>
              </div>
            </div>
            <button type="button" onclick="if(typeof openPostShareModal==='function') openPostShareModal('${pid}', event);"
              class="w-9 h-9 flex items-center justify-center rounded-full text-on-surface-variant hover:text-on-surface cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[20px]" translate="no">ios_share</span>
            </button>
          </div>

          <div class="simple-post-body text-base text-on-surface pt-1">
            ${bodyHtml}
          </div>

          <div class="flex items-center justify-between pt-1 text-xs">
            <span class="text-on-surface-variant">${esc(fullDate)}</span>
            <div class="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-surface-container-high">
              <span class="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></span>
              <span class="text-[11px] text-on-surface-variant font-medium">${t('post_block_label', 'Block')} #${esc(post.block_index ?? '--')}</span>
            </div>
          </div>

          <!-- Metrics Strip -->
          <div class="flex items-center justify-between py-2.5 px-3.5 rounded-xl bg-surface-container-low text-xs">
            <div class="flex items-center gap-1.5">
              <span class="font-semibold text-on-surface tabular-nums">${likesCount}</span>
              <span class="text-on-surface-variant">${t('post_likes_label', 'Likes')}</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="font-semibold text-on-surface tabular-nums">${comments.length}</span>
              <span class="text-on-surface-variant">${t('post_comments_label', 'Comments')}</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="font-semibold text-primary font-mono tabular-nums">+${typeof window.formatBct === 'function' ? window.formatBct(earned, 3) : earned.toFixed(3)} BCT</span>
              <span class="text-on-surface-variant">${t('post_royalties_label', 'Royalties')}</span>
            </div>
          </div>

          <!-- 4-Action Cluster -->
          <div class="grid grid-cols-4 gap-1.5 pt-1">
            <button type="button" onclick="window.BlocTagSimpleMode.likePost('${pid}', event)"
              class="flex flex-col items-center justify-center gap-1 py-2 rounded-xl bg-surface-container-high hover:bg-surface-container-highest transition-all active:scale-95 cursor-pointer ${isLiked ? 'text-tertiary font-semibold' : 'text-on-surface-variant'}">
              <span class="material-symbols-outlined notranslate text-[19px]" ${isLiked ? 'style="font-variation-settings: \'FILL\' 1;"' : ''} translate="no">favorite</span>
              <span class="text-[10.5px]">${t('space_like', 'Like')}</span>
            </button>
            <button type="button" onclick="document.getElementById('simple-comment-input')?.focus()"
              class="flex flex-col items-center justify-center gap-1 py-2 rounded-xl bg-surface-container-high hover:bg-surface-container-highest text-on-surface-variant hover:text-primary transition-all active:scale-95 cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[19px]" translate="no">chat_bubble</span>
              <span class="text-[10.5px]">${t('space_reply', 'Comment')}</span>
            </button>
            <button type="button" onclick="if(typeof openPostShareModal==='function') openPostShareModal('${pid}', event);"
              class="flex flex-col items-center justify-center gap-1 py-2 rounded-xl bg-surface-container-high hover:bg-surface-container-highest text-on-surface-variant hover:text-primary transition-all active:scale-95 cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[19px]" translate="no">repeat</span>
              <span class="text-[10.5px]">${t('space_share', 'Share')}</span>
            </button>
            <button type="button" onclick="window.BlocTagSimpleMode.tipAuthor('${escAttr(authorAddr)}')"
              class="flex flex-col items-center justify-center gap-1 py-2 rounded-xl bg-surface-container-high hover:bg-surface-container-highest text-primary transition-all active:scale-95 cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[19px]" style="font-variation-settings: 'FILL' 1;" translate="no">payments</span>
              <span class="text-[10.5px] font-semibold">${t('space_tip', 'Tip')}</span>
            </button>
          </div>
        </section>

        <!-- Comments Section Header -->
        <div class="flex items-center justify-between pt-4 pb-2 px-1">
          <div class="flex items-center gap-2">
            <h2 class="text-sm font-semibold text-on-surface">${t('post_comments_title', 'Comments')}</h2>
            <span class="px-2 py-0.5 rounded-full bg-surface-container text-on-surface-variant text-xs font-semibold">${comments.length}</span>
          </div>
          <span class="text-[11px] text-primary">${t('post_author_royalty_hint', '+0.004 BCT Author Royalty')}</span>
        </div>

        <!-- Comments List -->
        <section class="flex flex-col gap-2">
          ${comments.length === 0 ? `
            <div class="p-6 rounded-2xl bg-surface-container-low text-center text-xs text-on-surface-variant">
              ${t('post_be_first_comment', 'Be the first to leave an on-chain comment below!')}
            </div>
          ` : comments.slice().reverse().map(c => {
      const cAddr = String(c.commenter || '');
      const cBns = (c.commenter_bns && c.commenter_bns !== 'anonymous') ? String(c.commenter_bns).replace(/^@/, '') : '';
      const cName = cBns ? ('@' + cBns) : (typeof window.shortAddr === 'function' ? window.shortAddr(cAddr) : cAddr);
      const cTime = typeof window.formatTimeAgo === 'function' ? window.formatTimeAgo(c.timestamp) : '';
      const cBody = safeFormatSimpleBody(c.content || '');
      return `
              <article class="simple-post-card bg-surface-container rounded-2xl px-3.5 py-3 flex flex-col gap-1.5 border border-outline-variant/10">
                <div class="flex items-center justify-between gap-2 min-w-0">
                  <div class="flex items-center gap-2 min-w-0 cursor-pointer flex-1"
                       onclick="window.BlocTagSimpleMode.go('SCR-PRF-05', { profileTarget: '${escAttr(cBns || cAddr)}' })">
                    <div class="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center text-secondary shrink-0">
                      <span class="material-symbols-outlined notranslate text-[17px]" translate="no">person</span>
                    </div>
                    <div class="flex items-center gap-1.5 min-w-0">
                      <span class="text-xs font-semibold text-on-surface truncate">${esc(cName)}</span>
                      <span class="material-symbols-outlined notranslate text-[13px] text-primary shrink-0" style="font-variation-settings: 'FILL' 1;" translate="no">verified</span>
                      <span class="text-[11px] text-on-surface-variant shrink-0">· ${esc(cTime)}</span>
                    </div>
                  </div>
                  <button type="button" onclick="window.BlocTagSimpleMode.tipAuthor('${escAttr(cAddr)}')"
                    class="text-[11px] text-primary hover:underline font-medium cursor-pointer shrink-0">${t('space_tip', 'Tip')}</button>
                </div>
                <div class="simple-post-body text-xs text-on-surface pl-10">
                  ${cBody}
                </div>
              </article>
            `;
    }).join('')}
        </section>

        <!-- Sticky Bottom Reply Bar (Above bottom nav) -->
        <div class="fixed left-1/2 -translate-x-1/2 w-full max-w-[480px] z-50 bg-surface-dim/95 backdrop-blur-xl px-4 py-2.5 border-t border-outline-variant/15" style="bottom: var(--simple-bottom-nav-h, 60px);">
          <form class="flex items-center gap-2 bg-surface-container rounded-full p-1.5 shadow-md border border-outline-variant/20"
                onsubmit="event.preventDefault(); window.BlocTagSimpleMode.submitComment('${pid}');">
            <div class="w-8 h-8 rounded-full bg-surface-container-high ml-1 flex items-center justify-center text-primary shrink-0">
              <span class="material-symbols-outlined notranslate text-[17px]" translate="no">person</span>
            </div>
            <input id="simple-comment-input" type="text" maxlength="140" autocomplete="off"
              placeholder="${t('post_comment_ph', 'Write your comment... (0.02 BCT)')}"
              class="flex-1 bg-transparent text-xs text-on-surface placeholder:text-outline focus:outline-none px-1.5 min-w-0" />
            <button type="submit" id="simple-comment-submit-btn"
              class="h-8 px-3.5 rounded-full bg-primary-container text-on-primary text-xs font-semibold flex items-center justify-center gap-1 hover:brightness-95 active:scale-95 transition-all shrink-0 cursor-pointer">
              <span>${t('post_comment_send', 'Send')}</span>
              <span class="material-symbols-outlined notranslate text-[15px]" translate="no">arrow_upward</span>
            </button>
          </form>
        </div>
      </main>
    `;
  }

  // ── SCR-PRF-05: Space - Kullanıcı Profili ──────────────────────────────────
  function renderScreenProfile() {
    const acc = getActiveWallet();
    const myHandle = getMyPrimaryHandle();
    const targetRaw = String(simpleState.profileTarget || '').trim();
    const isMyProfile = !targetRaw ||
      (acc && targetRaw.toLowerCase() === acc.address.toLowerCase()) ||
      (myHandle && targetRaw.toLowerCase() === myHandle.toLowerCase());

    if (isMyProfile && !acc) {
      return renderScreenOnboardingWelcome();
    }

    const posts = (typeof spacePostsCache !== 'undefined' && Array.isArray(spacePostsCache)) ? spacePostsCache : [];
    const lookupKey = isMyProfile ? (acc ? acc.address : '') : targetRaw;
    let pData = getSimpleProfileData(lookupKey);
    if (!pData && lookupKey) {
      fetchSimpleProfile(lookupKey);
    }
    const myProfileData = acc ? getSimpleProfileData(acc.address) : null;
    if (!myProfileData && acc && acc.address) {
      fetchSimpleProfile(acc.address);
    }

    const targetAddr = isMyProfile ? (acc ? acc.address : '') : (pData?.address || targetRaw);
    const userPosts = posts.filter(p => {
      if (!p) return false;
      const pAddr = String(p.author || '').toLowerCase();
      const pBns = String(p.author_bns || '').toLowerCase().replace(/^@/, '');
      const tLow = targetAddr.toLowerCase().replace(/^@/, '');
      if (isMyProfile && acc) {
        return pAddr === acc.address.toLowerCase() || (myHandle && pBns === myHandle.toLowerCase());
      }
      return pAddr === tLow || pBns === tLow;
    });

    const resolvedBns = isMyProfile
      ? myHandle
      : (pData?.bns_name || pData?.primary_bns || pData?.primary_handle || userPosts.find(p => p.author_bns && p.author_bns !== 'anonymous')?.author_bns || (targetRaw.endsWith('.bct') ? targetRaw : ''));
    const resolvedAddress = isMyProfile
      ? (acc ? acc.address : '')
      : (pData?.address || userPosts[0]?.author || targetRaw);

    const resolvedTitleHandle = resolvedBns ? ('@' + resolvedBns.replace(/^@/, '')) : (typeof window.shortAddr === 'function' ? window.shortAddr(resolvedAddress) : resolvedAddress);
    const displayTitle = resolvedTitleHandle;
    const shortWallet = typeof window.shortAddr === 'function' ? window.shortAddr(resolvedAddress) : resolvedAddress;
    const totalLikesReceived = userPosts.reduce((accSum, p) => accSum + Number(p.likes_count || (p.likes ? p.likes.length : 0)), 0);
    const totalRoyalties = userPosts.reduce((accSum, p) => accSum + Number(p.author_earnings || 0), 0);

    // Follower & Following metrics strictly from live on-chain profile data
    let followersCount = 0;
    let followingCount = 0;
    if (pData) {
      followersCount = Number(pData.followers_count ?? (Array.isArray(pData.followers) ? pData.followers.length : 0));
      followingCount = Number(pData.following_count ?? (Array.isArray(pData.following) ? pData.following.length : 0));
    }

    const amIFollowing = Boolean(myProfileData && Array.isArray(myProfileData.following) && myProfileData.following.some(f => {
      const fAddr = typeof f === 'string' ? f : (f && f.address ? f.address : '');
      return fAddr.toLowerCase() === resolvedAddress.toLowerCase();
    }));

    // Owned BNS handles for current user
    const myOwnedHandles = isMyProfile ? getMyOwnedBnsHandles() : [];

    return `
      ${renderTopBar(t('top_profile', 'Profile'), !isMyProfile)}
      <main class="flex-1 flex flex-col w-full pb-24 simple-screen-animate">
        <!-- Minimalist Cover Scrim (Exact Stitch SCR-PRF-05) -->
        <div class="relative w-full h-32 bg-gradient-to-b from-surface-container to-surface overflow-hidden">
          <div class="absolute inset-0 opacity-30 bg-[radial-gradient(circle_at_top,_var(--tw-gradient-stops))] from-primary/40 via-transparent to-transparent"></div>
          <div class="absolute top-3.5 right-4 flex items-center gap-2">
            <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-container-high/85 backdrop-blur-md text-primary text-[11px] font-semibold shadow-sm">
              <span class="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></span>
              <span>Mainnet</span>
            </span>
          </div>
        </div>

        <!-- Profile Identity Cluster -->
        <div class="px-5 -mt-10 flex flex-col relative z-10">
          <div class="flex items-end justify-between gap-3">
            <!-- Avatar -->
            <div class="relative shrink-0 ${isMyProfile ? 'cursor-pointer group' : ''}"
                 ${isMyProfile ? 'onclick="window.BlocTagSimpleMode.openAvatarStudio()"' : ''}>
              <div class="w-20 h-20 rounded-full p-1 bg-surface shadow-xl ring-2 ring-surface ${isMyProfile ? 'group-hover:ring-primary/50 transition-all' : ''}">
                <div class="w-full h-full rounded-full overflow-hidden bg-surface-container-high flex items-center justify-center text-primary font-mono font-bold text-2xl">
                  ${renderAvatarCircleHtml(
                    pData?.avatar,
                    resolvedBns ? esc(resolvedBns.replace(/^@/, '')[0].toUpperCase()) : '<span class="material-symbols-outlined notranslate text-[36px]" translate="no">person</span>'
                  )}
                </div>
              </div>
              ${isMyProfile ? `
                <div class="absolute bottom-0 right-0 w-7 h-7 rounded-full bg-primary text-on-primary shadow-md ring-2 ring-surface flex items-center justify-center group-hover:scale-110 transition-transform"
                     title="${t('avatar_studio_title', 'Avatar Studio')}">
                  <span class="material-symbols-outlined notranslate text-[15px]" translate="no">photo_camera</span>
                </div>
              ` : `
                <div class="absolute bottom-1 right-1 w-4 h-4 rounded-full bg-surface p-0.5 flex items-center justify-center">
                  <div class="w-full h-full rounded-full bg-primary"></div>
                </div>
              `}
            </div>

            <!-- Profile Action Buttons -->
            <div class="flex items-center gap-1.5 pb-1 flex-wrap justify-end">
              ${isMyProfile ? `
                <button type="button" onclick="window.BlocTagSimpleMode.openAvatarStudio()"
                  class="h-8.5 px-3 rounded-full bg-primary/15 hover:bg-primary/25 text-primary text-xs font-semibold transition-all active:scale-95 flex items-center gap-1 cursor-pointer border border-primary/25">
                  <span class="material-symbols-outlined notranslate text-[15px]" translate="no">palette</span>
                  <span>${t('profile_avatar_btn', 'Avatar')}</span>
                </button>
                <button type="button" onclick="if(typeof openWalletVaultModal==='function') openWalletVaultModal();"
                  class="h-8.5 px-3 rounded-full bg-surface-container-high hover:bg-surface-container-highest text-on-surface text-xs font-medium transition-all active:scale-95 flex items-center gap-1 cursor-pointer">
                  <span class="material-symbols-outlined notranslate text-[15px]" translate="no">tune</span>
                  <span>${t('profile_security_btn', 'Security')}</span>
                </button>
              ` : `
                <!-- Follow Button (For Other Profiles) -->
                ${amIFollowing ? `
                  <button type="button" id="simple-profile-follow-btn"
                    onclick="window.BlocTagSimpleMode.followProfileAuthor('${escAttr(resolvedAddress)}', '${escAttr(resolvedBns)}', this)"
                    class="h-8.5 px-3 rounded-full bg-surface-container-high hover:bg-surface-variant text-on-surface text-xs font-medium flex items-center gap-1 transition-all active:scale-95 shadow-xs cursor-pointer">
                    <span class="material-symbols-outlined notranslate text-[15px] text-primary" translate="no">check</span>
                    <span>${t('btn_following', 'Following')}</span>
                  </button>
                ` : `
                  <button type="button" id="simple-profile-follow-btn"
                    onclick="window.BlocTagSimpleMode.followProfileAuthor('${escAttr(resolvedAddress)}', '${escAttr(resolvedBns)}', this)"
                    class="h-8.5 px-3 rounded-full bg-primary text-on-primary text-xs font-bold transition-all active:scale-95 flex items-center gap-1 shadow-sm cursor-pointer hover:brightness-95">
                    <span class="material-symbols-outlined notranslate text-[15px]" translate="no">person_add</span>
                    <span>${t('profile_follow_btn', 'Follow')}</span>
                  </button>
                `}

                <button type="button" onclick="window.BlocTagSimpleMode.tipAuthor('${escAttr(resolvedAddress)}')"
                  class="h-8.5 px-2.5 rounded-full bg-surface-container-high hover:bg-surface-container-highest text-on-surface text-xs font-medium transition-all active:scale-95 flex items-center gap-1 cursor-pointer">
                  <span class="material-symbols-outlined notranslate text-[15px] text-primary" translate="no">volunteer_activism</span>
                  <span>${t('profile_tip_btn', 'Tip')}</span>
                </button>
              `}
            </div>
          </div>

          <!-- User Meta Info -->
          <div class="flex flex-col mt-3">
            <div class="flex items-center gap-1.5">
              <h1 class="text-xl font-bold text-on-surface tracking-tight truncate">${esc(displayTitle)}</h1>
              <span class="inline-flex items-center justify-center w-5 h-5 rounded-full bg-primary/10 text-primary">
                <span class="material-symbols-outlined notranslate text-[14px]" style="font-variation-settings: 'FILL' 1;" translate="no">verified</span>
              </span>
            </div>

            <!-- Handle & Status Badge -->
            <div class="flex items-center gap-2 mt-1.5 flex-wrap">
              ${resolvedBns ? `
                <button type="button" onclick="if(typeof copyText==='function') copyText('@${escAttr(resolvedBns.replace(/^@/, ''))}', 'Identity copied!');"
                  class="group flex items-center gap-1 text-on-surface-variant hover:text-on-surface transition-colors cursor-pointer">
                  <span class="text-xs text-primary font-mono font-medium">@${esc(resolvedBns.replace(/^@/, ''))}</span>
                  <span class="material-symbols-outlined notranslate text-[14px] text-outline group-hover:text-primary" translate="no">content_copy</span>
                </button>
                <span class="w-1 h-1 rounded-full bg-outline-variant"></span>
              ` : ''}
              <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface-container text-primary text-[10.5px] font-medium">
                <span class="w-1.5 h-1.5 rounded-full bg-primary"></span>
                <span>${t('space_active_l1', 'Active L1')}</span>
              </span>
              ${totalRoyalties > 0 ? `
                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary/10 text-primary text-[10.5px] font-mono font-semibold">
                  <span class="material-symbols-outlined notranslate text-[12px]" translate="no">monetization_on</span>
                  <span>+${typeof window.formatBct === 'function' ? window.formatBct(totalRoyalties, 3) : totalRoyalties.toFixed(3)} BCT</span>
                </span>
              ` : ''}
            </div>

            <!-- Compact Wallet Strip -->
            <div class="mt-2.5 flex items-center gap-2 flex-wrap">
              <button type="button" onclick="if(typeof copyText==='function') copyText('${escAttr(resolvedAddress)}', 'Wallet address copied!');"
                class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-surface-container-low hover:bg-surface-container text-on-surface-variant transition-all active:scale-95 cursor-pointer border border-outline-variant/15">
                <span class="material-symbols-outlined notranslate text-[15px] text-primary" translate="no">account_balance_wallet</span>
                <span class="text-xs tracking-wider font-mono">${esc(shortWallet)}</span>
                <span class="material-symbols-outlined notranslate text-[13px]" translate="no">file_copy</span>
              </button>
            </div>

            <!-- BNS Handle Selector & Switcher -->
            ${isMyProfile ? `
              <div class="mt-3.5 p-3 rounded-2xl bg-surface-container-low border border-outline-variant/15 shadow-sm">
                <div class="flex items-center justify-between mb-2">
                  <div class="flex items-center gap-1.5">
                    <span class="material-symbols-outlined notranslate text-primary text-[17px]" translate="no">badge</span>
                    <span class="text-xs font-bold text-on-surface">${t('profile_bns_title', 'Your Registered BNS Names (.bct)')}</span>
                  </div>
                  <span class="text-[10px] text-on-surface-variant font-mono">${myOwnedHandles.length} ${t('profile_bns_count', 'names')}</span>
                </div>

                ${myOwnedHandles.length > 0 ? `
                  <p class="text-[11px] text-on-surface-variant mb-2 leading-relaxed">
                    ${t('profile_bns_hint', 'Select your active identity to display across your profile and Space posts:')}
                  </p>
                  <div class="flex flex-wrap gap-1.5">
                    ${myOwnedHandles.map(h => {
                      const clean = String(h).replace(/^@/, '');
                      const isCurrent = clean.toLowerCase() === (resolvedBns || '').toLowerCase().replace(/^@/, '');
                      return `
                        <button type="button" onclick="window.BlocTagSimpleMode.setPrimaryHandle('${escAttr(clean)}')"
                          class="px-2.5 py-1 rounded-full text-[11px] font-mono font-medium transition-all cursor-pointer flex items-center gap-1 active:scale-95 ${isCurrent ? 'bg-primary text-on-primary font-bold shadow-xs ring-1 ring-primary' : 'bg-surface-container text-on-surface hover:bg-surface-container-high border border-outline-variant/20'}">
                          ${isCurrent ? '<span class="material-symbols-outlined notranslate text-[12px]" translate="no">check</span>' : ''}
                          <span>@${esc(clean)}</span>
                          ${isCurrent ? `<span class="text-[9px] opacity-90 font-sans font-normal">${t('profile_bns_active', '(Active)')}</span>` : ''}
                        </button>
                      `;
                    }).join('')}
                  </div>
                ` : `
                  <div class="flex items-center justify-between gap-3 pt-0.5">
                    <p class="text-[11px] text-on-surface-variant leading-relaxed">
                      ${t('profile_bns_none', "You haven't claimed a .bct domain yet. Use a memorable name instead of your wallet address.")}
                    </p>
                    <button type="button" onclick="if(typeof openBnsRegisterModal==='function') openBnsRegisterModal(); else window.BlocTagSimpleMode.requestProMode('bns');"
                      class="px-3 py-1 rounded-full bg-primary/15 hover:bg-primary/25 border border-primary/30 text-primary text-[11px] font-semibold shrink-0 cursor-pointer active:scale-95 transition-all">
                      ${t('profile_bns_claim', 'Get Name')}
                    </button>
                  </div>
                `}
              </div>
            ` : ''}

            <!-- Bio Statement -->
            <p class="text-xs text-on-surface/90 leading-relaxed mt-2.5">
              ${t('profile_bio', 'Verified BlocTag Space creator ✦ Publishing content on censorship-resistant Layer-1 blockchain with instant royalties.')}
            </p>

            <!-- Metrics 4-Col Grid (Posts, Likes, Followers, Following) -->
            <div class="grid grid-cols-4 gap-2 mt-3.5">
              <div class="flex flex-col items-center justify-center py-2 px-1 rounded-xl bg-surface-container-low border border-outline-variant/10 text-center">
                <span class="font-bold text-on-surface font-mono text-sm">${userPosts.length}</span>
                <span class="text-[10.5px] text-on-surface-variant mt-0.5">${t('profile_stat_posts', 'Posts')}</span>
              </div>
              <div class="flex flex-col items-center justify-center py-2 px-1 rounded-xl bg-surface-container-low border border-outline-variant/10 text-center">
                <span class="font-bold text-on-surface font-mono text-sm">${totalLikesReceived}</span>
                <span class="text-[10.5px] text-on-surface-variant mt-0.5">${t('profile_stat_likes', 'Likes')}</span>
              </div>
              <div class="flex flex-col items-center justify-center py-2 px-1 rounded-xl bg-surface-container-low border border-outline-variant/10 text-center cursor-pointer group active:scale-95 transition-transform"
                   onclick="window.BlocTagSimpleMode.openFollowersList('${escAttr(resolvedAddress)}', 'followers')"
                   title="${t('profile_view_followers', 'View Followers')}">
                <span class="font-bold text-emerald-400 font-mono text-sm group-hover:underline" id="simple-profile-followers-count">${followersCount}</span>
                <span class="text-[10.5px] text-on-surface-variant group-hover:text-emerald-400 transition-colors mt-0.5">${t('profile_stat_followers', 'Followers')}</span>
              </div>
              <div class="flex flex-col items-center justify-center py-2 px-1 rounded-xl bg-surface-container-low border border-outline-variant/10 text-center cursor-pointer group active:scale-95 transition-transform"
                   onclick="window.BlocTagSimpleMode.openFollowersList('${escAttr(resolvedAddress)}', 'following')"
                   title="${t('profile_view_following', 'View Following')}">
                <span class="font-bold text-on-surface font-mono text-sm group-hover:underline" id="simple-profile-following-count">${followingCount}</span>
                <span class="text-[10.5px] text-on-surface-variant group-hover:text-on-surface transition-colors mt-0.5">${t('profile_stat_following', 'Following')}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Space Minimal Segmented Nav -->
        <div class="px-5 mt-4">
          <div class="w-full flex items-center justify-between bg-surface-container-lowest rounded-full p-1 border border-outline-variant/15">
            <button type="button" onclick="window.BlocTagSimpleMode.setProfileTab('posts')"
              class="flex-1 py-1.5 text-center rounded-full text-xs transition-all cursor-pointer ${simpleState.profileTab === 'posts' ? 'bg-surface-container text-primary font-semibold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}">
              ${t('profile_tab_posts', 'Posts')}
            </button>
            <button type="button" onclick="window.BlocTagSimpleMode.setProfileTab('likes')"
              class="flex-1 py-1.5 text-center rounded-full text-xs transition-all cursor-pointer ${simpleState.profileTab === 'likes' ? 'bg-surface-container text-primary font-semibold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}">
              ${t('profile_tab_popular', 'Popular')}
            </button>
          </div>
        </div>

        <!-- User Content Stream -->
        <div class="px-5 flex flex-col mt-3 gap-2.5">
          ${userPosts.length === 0 ? `
            <div class="p-6 rounded-2xl bg-surface-container-low text-center text-xs text-on-surface-variant">
              ${t('profile_empty_posts', 'No on-chain posts published yet.')}
            </div>
          ` : (simpleState.profileTab === 'likes'
        ? [...userPosts].sort((a, b) => Number(b.likes_count || 0) - Number(a.likes_count || 0))
        : userPosts
      ).map(p => renderSimplePostCard(p, acc)).join('')}
        </div>
      </main>
    `;
  }

  // ── SCR-PRF-FOLLOW: Space - Takipçiler & Takip Edilenler (Stitch Modern Crypto Wallet App) ──
  function renderScreenFollowList() {
    const acc = getActiveWallet();
    const myHandle = getMyPrimaryHandle();
    const targetRaw = String(simpleState.followTargetAddr || simpleState.profileTarget || '').trim();
    const isMyList = !targetRaw ||
      (acc && targetRaw.toLowerCase() === acc.address.toLowerCase()) ||
      (myHandle && targetRaw.toLowerCase() === myHandle.toLowerCase());

    const targetAddr = isMyList ? (acc ? acc.address : '') : targetRaw;
    const currentTab = (simpleState.followTab === 'following') ? 'following' : 'followers';
    const currentFilter = simpleState.followFilter || 'all';
    const searchQuery = String(simpleState.followSearch || '').trim().toLowerCase();

    // 1. Get Live Profile Data strictly from on-chain state (NO mock/curated data)
    let pData = getSimpleProfileData(targetAddr);
    const isLoading = !pData && Boolean(targetAddr);
    if (!pData && targetAddr) {
      fetchSimpleProfile(targetAddr);
    }
    const myProfileData = acc ? getSimpleProfileData(acc.address) : null;
    if (!myProfileData && acc && acc.address) {
      fetchSimpleProfile(acc.address);
    }

    const liveFollowers = (pData && Array.isArray(pData.followers)) ? pData.followers : [];
    const liveFollowing = (pData && Array.isArray(pData.following)) ? pData.following : [];

    function normalizeUser(item, defaultType) {
      const addr = typeof item === 'string' ? item.trim() : String(item.address || '').trim();
      const bns = typeof item === 'object' ? String(item.bns_name || '').replace(/^@/, '') : '';
      const dName = (typeof item === 'object' && item.display_name)
        ? item.display_name
        : (bns ? ('@' + bns) : (typeof window.shortAddr === 'function' ? window.shortAddr(addr) : addr));
      const myAddr = acc ? String(acc.address || '').toLowerCase() : '';
      const isSelf = Boolean(myAddr && addr.toLowerCase() === myAddr);

      let isFollowing = false;
      let followsYou = false;

      if (isMyList) {
        if (defaultType === 'following') {
          isFollowing = true;
          followsYou = liveFollowers.some(f => (typeof f === 'string' ? f : (f && f.address ? f.address : '')).toLowerCase() === addr.toLowerCase());
        } else {
          followsYou = true;
          isFollowing = liveFollowing.some(f => (typeof f === 'string' ? f : (f && f.address ? f.address : '')).toLowerCase() === addr.toLowerCase());
        }
      } else {
        if (myProfileData) {
          const myFollowing = Array.isArray(myProfileData.following) ? myProfileData.following : [];
          const myFollowers = Array.isArray(myProfileData.followers) ? myProfileData.followers : [];
          isFollowing = myFollowing.some(f => (typeof f === 'string' ? f : (f && f.address ? f.address : '')).toLowerCase() === addr.toLowerCase());
          followsYou = myFollowers.some(f => (typeof f === 'string' ? f : (f && f.address ? f.address : '')).toLowerCase() === addr.toLowerCase());
        }
      }

      const isMutual = Boolean(isFollowing && followsYou);

      return {
        address: addr,
        bns_name: bns,
        display_name: dName,
        bio: (typeof item === 'object' && item.bio) ? item.bio : ((typeof item === 'object' && item.is_validator) ? 'Verified Validator Node' : 'BlocTag On-Chain Account'),
        is_verified: Boolean(typeof item === 'object' && (item.is_verified || item.is_validator)),
        is_validator: Boolean(typeof item === 'object' && item.is_validator),
        is_self: isSelf,
        is_following: isFollowing,
        follows_you: followsYou,
        is_mutual: isMutual
      };
    }

    const followersList = liveFollowers.map(u => normalizeUser(u, 'followers'));
    const followingList = liveFollowing.map(u => normalizeUser(u, 'following'));

    const activeList = currentTab === 'followers' ? followersList : followingList;
    const mutualCount = activeList.filter(u => u.is_mutual).length;
    const verifiedCount = activeList.filter(u => u.is_verified).length;

    const filteredList = activeList.filter(u => {
      if (currentFilter === 'mutual' && !u.is_mutual) return false;
      if (currentFilter === 'verified' && !u.is_verified) return false;
      if (searchQuery) {
        const text = `${u.display_name} ${u.bns_name} ${u.address} ${u.bio}`.toLowerCase();
        if (!text.includes(searchQuery)) return false;
      }
      return true;
    });

    const pageTitle = currentTab === 'following' ? t('profile_stat_following', 'Following') : t('profile_stat_followers', 'Followers');

    return `
      ${renderTopBar(pageTitle, true)}
      <main class="flex-1 flex flex-col w-full px-5 pt-3 pb-24 simple-screen-animate">
        <!-- Dynamic Stats & Network Sub-Bar (Stitch Modern Crypto Wallet App) -->
        <div class="flex items-center justify-between py-1.5">
          <div class="flex items-center gap-1.5">
            <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-container text-on-surface-variant font-label-sm text-[11px]">
              <span class="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></span>
              <span>${t('live_network_community', 'Live Network • Community')}</span>
            </span>
            <span class="px-2 py-0.5 rounded-full bg-primary/10 text-primary font-label-md text-[11px] font-mono">
              ${activeList.length} ${pageTitle}
            </span>
          </div>
          <span class="text-[11px] font-mono text-outline">${activeList.length} total</span>
        </div>

        <!-- Segmented Control Pill Bar (Interactive Stitch Tab Switching) -->
        <div class="w-full p-1 rounded-full bg-surface-container-lowest flex items-center gap-1 mt-2.5 border border-outline-variant/15 shadow-sm">
          <button type="button" onclick="window.BlocTagSimpleMode.setFollowTab('followers')"
            class="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-full transition-all duration-200 cursor-pointer ${currentTab === 'followers' ? 'bg-surface-container-high text-primary font-bold shadow-xs' : 'text-on-surface-variant hover:text-on-surface'}">
            <span class="text-xs ${currentTab === 'followers' ? 'text-primary font-bold' : ''}">${t('profile_stat_followers', 'Followers')}</span>
            <span class="px-2 py-0.5 rounded-full ${currentTab === 'followers' ? 'bg-primary/15 text-primary font-bold' : 'bg-surface-container text-on-surface-variant'} text-[10px] font-mono">${followersList.length}</span>
          </button>
          <button type="button" onclick="window.BlocTagSimpleMode.setFollowTab('following')"
            class="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-full transition-all duration-200 cursor-pointer ${currentTab === 'following' ? 'bg-surface-container-high text-primary font-bold shadow-xs' : 'text-on-surface-variant hover:text-on-surface'}">
            <span class="text-xs ${currentTab === 'following' ? 'text-primary font-bold' : ''}">${t('profile_stat_following', 'Following')}</span>
            <span class="px-2 py-0.5 rounded-full ${currentTab === 'following' ? 'bg-primary/15 text-primary font-bold' : 'bg-surface-container text-on-surface-variant'} text-[10px] font-mono">${followingList.length}</span>
          </button>
        </div>

        <!-- Search Input Field -->
        <div class="relative w-full mt-3">
          <div class="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-on-surface-variant">
            <span class="material-symbols-outlined notranslate text-[18px]" translate="no">search</span>
          </div>
          <input type="text"
            value="${escAttr(simpleState.followSearch || '')}"
            oninput="window.BlocTagSimpleMode.onFollowSearchInput(this.value)"
            placeholder="${t('search_users_placeholder', 'Search username or address...')}"
            class="w-full h-11 pl-10 pr-9 rounded-xl bg-surface-container text-on-surface placeholder:text-outline text-xs focus:outline-none focus:bg-surface-container-high transition-colors shadow-inner" />
          ${(simpleState.followSearch || '').length > 0 ? `
            <button type="button" onclick="window.BlocTagSimpleMode.clearFollowSearch()"
              class="absolute inset-y-0 right-0 pr-3 flex items-center text-outline hover:text-on-surface cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[17px]" translate="no">cancel</span>
            </button>
          ` : ''}
        </div>

        <!-- Quick Pill Filter Carousel -->
        <div class="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-2 mt-1 -mx-1 px-1">
          <button type="button" onclick="window.BlocTagSimpleMode.setFollowFilter('all')"
            class="shrink-0 px-3 py-1.5 rounded-full text-xs font-medium flex items-center gap-1 transition-all cursor-pointer ${currentFilter === 'all' ? 'bg-surface-container-high text-primary font-semibold shadow-xs' : 'bg-surface-container-low text-on-surface-variant hover:text-on-surface'}">
            <span>${t('filter_all', 'All')}</span>
            <span class="text-[10px] opacity-75 font-mono">(${activeList.length})</span>
          </button>
          <button type="button" onclick="window.BlocTagSimpleMode.setFollowFilter('mutual')"
            class="shrink-0 px-3 py-1.5 rounded-full text-xs font-medium flex items-center gap-1 transition-all cursor-pointer ${currentFilter === 'mutual' ? 'bg-surface-container-high text-primary font-semibold shadow-xs' : 'bg-surface-container-low text-on-surface-variant hover:text-on-surface'}">
            <span class="material-symbols-outlined notranslate text-[14px]" translate="no">swap_horiz</span>
            <span>${t('filter_mutual', 'Mutual')}</span>
            <span class="text-[10px] opacity-75 font-mono">(${mutualCount})</span>
          </button>
          <button type="button" onclick="window.BlocTagSimpleMode.setFollowFilter('verified')"
            class="shrink-0 px-3 py-1.5 rounded-full text-xs font-medium flex items-center gap-1 transition-all cursor-pointer ${currentFilter === 'verified' ? 'bg-surface-container-high text-primary font-semibold shadow-xs' : 'bg-surface-container-low text-on-surface-variant hover:text-on-surface'}">
            <span class="material-symbols-outlined notranslate text-[14px] text-primary" style="font-variation-settings: 'FILL' 1;" translate="no">verified</span>
            <span>${t('filter_verified', 'Verified')}</span>
            <span class="text-[10px] opacity-75 font-mono">(${verifiedCount})</span>
          </button>
        </div>

        <!-- Users Stream Container -->
        <div class="flex flex-col gap-2 mt-2">
          ${isLoading ? `
            <div class="flex flex-col items-center justify-center py-16 px-4 text-center">
              <div class="w-9 h-9 rounded-full border-2 border-primary border-t-transparent animate-spin mb-3"></div>
              <span class="font-headline-sm text-xs font-semibold text-on-surface">
                ${t('loading_connections', 'Loading on-chain connections...')}
              </span>
              <p class="text-[11px] text-on-surface-variant mt-1.5 max-w-xs leading-relaxed">
                ${t('querying_ledger', 'Querying cryptographic ledger & decentralized network...')}
              </p>
            </div>
          ` : (filteredList.length === 0 ? `
            <div class="flex flex-col items-center justify-center py-16 px-4 text-center">
              <div class="w-14 h-14 rounded-full bg-surface-container flex items-center justify-center mb-3">
                <span class="material-symbols-outlined notranslate text-outline text-[28px]" translate="no">
                  ${searchQuery ? 'person_search' : (currentTab === 'following' ? 'person_add' : 'group')}
                </span>
              </div>
              <span class="font-headline-sm text-sm font-semibold text-on-surface">
                ${searchQuery
                  ? t('no_users_found', 'No users found')
                  : (currentTab === 'following' ? t('following_empty_title', 'Not following anyone yet') : t('followers_empty_title', 'No followers yet'))}
              </span>
              <p class="text-xs text-on-surface-variant mt-1.5 max-w-xs leading-relaxed">
                ${searchQuery
                  ? t('no_users_found_desc', 'No users matching your search criteria. You can reset filters.')
                  : (currentTab === 'following' ? t('following_empty_desc', 'Explore creators on Space and follow them to see their latest updates.') : t('followers_empty_desc', 'Share your thoughts on Space to build your on-chain audience.'))}
              </p>
              ${searchQuery ? `
                <button type="button" onclick="window.BlocTagSimpleMode.clearFollowSearch(); window.BlocTagSimpleMode.setFollowFilter('all');"
                  class="mt-3 px-3.5 py-1.5 rounded-full bg-surface-container-high hover:bg-surface-variant text-primary text-xs font-semibold transition-all cursor-pointer">
                  Reset
                </button>
              ` : `
                <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-SPC-03')"
                  class="mt-4 px-4 py-2 rounded-full bg-primary text-on-primary text-xs font-semibold shadow-xs active:scale-95 transition-all cursor-pointer">
                  ${t('nav_space', 'Go to Space')}
                </button>
              `}
            </div>
          ` : filteredList.map(u => `
            <div class="flex items-center justify-between p-3 rounded-2xl bg-surface-container-low hover:bg-surface-container transition-colors group">
              <div class="flex items-center gap-3 min-w-0 pr-2 cursor-pointer flex-1"
                onclick="window.BlocTagSimpleMode.go('SCR-PRF-05', { profileTarget: '${escAttr(u.bns_name || u.address)}' })">
                <div class="relative shrink-0 w-11 h-11 rounded-full bg-surface-container-highest flex items-center justify-center font-bold text-sm text-primary ring-1 ring-primary/20">
                  ${renderAvatarCircleHtml(
                    u.avatar,
                    u.bns_name ? esc(u.bns_name[0].toUpperCase()) : '<span class="material-symbols-outlined notranslate text-[20px]" translate="no">person</span>'
                  )}
                  <span class="absolute bottom-0 right-0 w-3 h-3 rounded-full bg-primary ring-2 ring-surface-container-low"></span>
                </div>
                <div class="flex flex-col min-w-0">
                  <div class="flex items-center gap-1.5 truncate">
                    <span class="font-semibold text-xs text-on-surface truncate">${esc(u.display_name)}</span>
                    ${u.is_verified ? `<span class="material-symbols-outlined notranslate text-primary text-[14px] shrink-0" style="font-variation-settings: 'FILL' 1;" translate="no">verified</span>` : ''}
                    ${u.follows_you ? `<span class="px-1.5 py-0.2 rounded bg-surface-container-highest text-primary text-[10px] shrink-0 font-medium">${t('follows_you', 'Follows you')}</span>` : ''}
                  </div>
                  <span class="text-[11px] font-mono text-outline truncate">${u.bns_name ? '@' + esc(u.bns_name) : esc(typeof window.shortAddr === 'function' ? window.shortAddr(u.address) : u.address)}</span>
                  <p class="text-[11px] text-on-surface-variant truncate mt-0.5">${esc(u.bio)}</p>
                </div>
              </div>
              ${u.is_self ? `
                <span class="shrink-0 px-3 py-1 rounded-full bg-surface-container-high text-on-surface-variant text-[11px] font-semibold">${t('user_self_tag', 'You')}</span>
              ` : (u.is_following ? `
                <button type="button" onclick="window.BlocTagSimpleMode.followProfileAuthor('${escAttr(u.address)}', '${escAttr(u.bns_name)}', this)"
                  class="shrink-0 h-8.5 px-3 rounded-full bg-surface-container-high hover:bg-surface-variant text-on-surface text-xs font-medium flex items-center gap-1 transition-all active:scale-95 shadow-xs cursor-pointer">
                  <span class="material-symbols-outlined notranslate text-[15px] text-primary" translate="no">check</span>
                  <span>${t('btn_following', 'Following')}</span>
                </button>
              ` : (u.follows_you ? `
                <button type="button" onclick="window.BlocTagSimpleMode.followProfileAuthor('${escAttr(u.address)}', '${escAttr(u.bns_name)}', this)"
                  class="shrink-0 h-8.5 px-3 rounded-full bg-primary hover:bg-primary-fixed text-on-primary text-xs font-semibold flex items-center gap-1 transition-all active:scale-95 shadow-xs cursor-pointer">
                  <span class="material-symbols-outlined notranslate text-[15px]" translate="no">add</span>
                  <span>${t('follow_back', 'Follow Back')}</span>
                </button>
              ` : `
                <button type="button" onclick="window.BlocTagSimpleMode.followProfileAuthor('${escAttr(u.address)}', '${escAttr(u.bns_name)}', this)"
                  class="shrink-0 h-8.5 px-3 rounded-full bg-primary hover:bg-primary-fixed text-on-primary text-xs font-semibold flex items-center gap-1 transition-all active:scale-95 shadow-xs cursor-pointer">
                  <span class="material-symbols-outlined notranslate text-[15px]" translate="no">add</span>
                  <span>${t('btn_follow', 'Follow')}</span>
                </button>
              `))}
            </div>
          `).join(''))}
        </div>
      </main>
    `;
  }

  // ── SCR-NTF-06: Space - Bildirimler ────────────────────────────────────────
  function renderScreenNotifications() {
    const stored = getStoredNotifications();
    const unreadCount = stored.filter(n => n && !n.read).length;

    const filtered = stored.filter(n => {
      if (!n) return false;
      const cat = String(n.category || 'system').toLowerCase();
      if (simpleState.notifFilter === 'tips') return cat === 'transfer' || cat === 'tips';
      if (simpleState.notifFilter === 'mentions') return cat === 'space' || cat === 'mentions';
      if (simpleState.notifFilter === 'system') return cat === 'system' || cat === 'bns_offer';
      return true;
    });

    return `
      ${renderTopBar(t('top_notifications', 'Notifications'), false)}
      <main class="flex-1 flex flex-col w-full px-5 pt-2 pb-24 simple-screen-animate">
        <!-- Header & Actions (Exact Stitch SCR-NTF-06) -->
        <div class="flex items-center justify-between pt-1 pb-3">
          <div class="flex items-center gap-2">
            <h1 class="text-xl font-bold text-on-surface">${t('top_notifications', 'Notifications')}</h1>
            <span class="px-2 py-0.5 rounded-full bg-primary-container/20 text-primary text-[11px] font-semibold">
              ${unreadCount} ${t('notif_new_badge', 'new')}
            </span>
          </div>
          <button type="button" onclick="window.BlocTagSimpleMode.markAllNotifsRead()"
            class="flex items-center gap-1 px-3 py-1.5 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-on-surface text-xs active:scale-95 transition-all cursor-pointer">
            <span class="material-symbols-outlined notranslate text-[16px]" translate="no">done_all</span>
            <span>${t('notif_mark_all', 'Mark All Read')}</span>
          </button>
        </div>

        <!-- Filter Chips -->
        <div class="flex items-center gap-2 overflow-x-auto no-scrollbar py-1 mb-3">
          <button type="button" onclick="window.BlocTagSimpleMode.setNotifFilter('all')"
            class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors cursor-pointer ${simpleState.notifFilter === 'all' ? 'bg-surface-container-high text-on-surface font-semibold' : 'bg-surface-container text-on-surface-variant'}">
            <span>${t('notif_all', 'All')}</span>
            <span class="w-1.5 h-1.5 rounded-full bg-primary"></span>
          </button>
          <button type="button" onclick="window.BlocTagSimpleMode.setNotifFilter('tips')"
            class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors cursor-pointer ${simpleState.notifFilter === 'tips' ? 'bg-surface-container-high text-on-surface font-semibold' : 'bg-surface-container text-on-surface-variant'}">
            <span class="material-symbols-outlined notranslate text-[15px] text-primary" translate="no">volunteer_activism</span>
            <span>${t('notif_tips', 'Transfers & Tips')}</span>
          </button>
          <button type="button" onclick="window.BlocTagSimpleMode.setNotifFilter('mentions')"
            class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors cursor-pointer ${simpleState.notifFilter === 'mentions' ? 'bg-surface-container-high text-on-surface font-semibold' : 'bg-surface-container text-on-surface-variant'}">
            <span class="material-symbols-outlined notranslate text-[15px]" translate="no">chat_bubble</span>
            <span>${t('notif_mentions', 'Space & Replies')}</span>
          </button>
          <button type="button" onclick="window.BlocTagSimpleMode.setNotifFilter('system')"
            class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors cursor-pointer ${simpleState.notifFilter === 'system' ? 'bg-surface-container-high text-on-surface font-semibold' : 'bg-surface-container text-on-surface-variant'}">
            <span class="material-symbols-outlined notranslate text-[15px] text-secondary" translate="no">verified_user</span>
            <span>${t('notif_system', 'System')}</span>
          </button>
        </div>

        <!-- Notifications List -->
        <div class="flex flex-col gap-2.5">
          ${filtered.length === 0 ? `
            <div class="flex flex-col items-center justify-center text-center py-12 px-4 rounded-2xl bg-surface-container-low">
              <div class="w-14 h-14 rounded-full bg-surface-container flex items-center justify-center text-primary mb-3">
                <span class="material-symbols-outlined notranslate text-[28px]" translate="no">mark_chat_read</span>
              </div>
              <h3 class="text-sm font-semibold text-on-surface mb-1">${t('notif_empty_title', 'No notifications yet')}</h3>
              <p class="text-xs text-on-surface-variant max-w-xs">
                ${t('notif_empty_desc', 'Incoming transfers, Space likes, comments and tips will appear here in real time.')}
              </p>
            </div>
          ` : filtered.slice(0, 30).map(item => {
      const timeSec = Number(item.time || Date.now()) / 1000;
      const timeStr = typeof window.formatTimeAgo === 'function' ? window.formatTimeAgo(timeSec) : '';
      const icon = item.icon || (item.category === 'transfer' ? 'payments' : (item.category === 'space' ? 'forum' : 'verified_user'));
      return `
              <div class="relative flex items-start gap-3 p-3.5 rounded-2xl bg-surface-container hover:bg-surface-container-high transition-all">
                ${!item.read ? '<span class="absolute left-2 top-5 w-1.5 h-1.5 rounded-full bg-primary ring-4 ring-primary/10"></span>' : ''}
                <div class="shrink-0 w-10 h-10 rounded-full bg-primary/15 flex items-center justify-center text-primary ml-1">
                  <span class="material-symbols-outlined notranslate text-[20px]" translate="no">${esc(icon)}</span>
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center justify-between gap-2 mb-0.5">
                    <span class="text-xs font-semibold text-on-surface truncate">${esc(item.title || 'BlocTag Notification')}</span>
                    <span class="shrink-0 text-[10.5px] text-on-surface-variant/80">${esc(timeStr)}</span>
                  </div>
                  <p class="text-xs text-on-surface-variant leading-relaxed break-words">${esc(item.body || '')}</p>
                </div>
              </div>
            `;
    }).join('')}
        </div>
      </main>
    `;
  }

  // ── SCR-MNU-07: Simple Mode Menu & Settings Screen ─────────────────────────
  function renderScreenMenu() {
    const acc = getActiveWallet();
    const myHandle = getMyPrimaryHandle();
    const displayTag = getDisplayHandleOrAddr(acc ? acc.address : '', myHandle);
    const balanceStr = acc ? (typeof window.formatBct === 'function' ? window.formatBct(acc.balance || 0, 2) + ' BCT' : '0.00 BCT') : '0.00 BCT';
    const isValidator = acc && Array.isArray(window.knownValidators) && window.knownValidators.includes(acc.address);
    const activeLangCode = getActiveLanguageCode();
    const activeLangObj = SIMPLE_LANGUAGES.find(l => l.code === activeLangCode) || SIMPLE_LANGUAGES[0];

    return `
      ${renderTopBar(t('top_menu', 'Menu'), false)}
      <main class="flex-1 flex flex-col w-full px-4 pt-3 pb-24 simple-screen-animate">
        <!-- Account Summary Card -->
        <div class="bg-surface-container-low rounded-2xl p-4 border border-outline-variant/15 shadow-sm mb-3.5">
          <div class="flex items-center gap-3">
            <div class="w-12 h-12 rounded-full bg-primary/20 text-primary flex items-center justify-center font-mono font-bold text-base shrink-0">
              ${myHandle ? esc(myHandle[0].toUpperCase()) : '<span class="material-symbols-outlined notranslate text-[24px]" translate="no">person</span>'}
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-1.5">
                <span class="font-bold text-on-surface text-sm truncate">${esc(displayTag)}</span>
                ${isValidator ? '<span class="px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-mono text-[9px] font-bold">VALİDATOR</span>' : ''}
              </div>
              <span class="text-xs font-mono text-primary font-semibold">${balanceStr}</span>
              <p class="text-[10.5px] text-on-surface-variant font-mono truncate mt-0.5">${acc ? esc(acc.address) : t('menu_not_connected', 'Wallet not connected')}</p>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-2 mt-3 pt-3 border-t border-outline-variant/10">
            <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-WLT-HOME')"
              class="h-9 rounded-xl bg-surface-container hover:bg-surface-container-high text-xs font-semibold text-on-surface flex items-center justify-center gap-1.5 transition-colors cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[16px] text-primary" translate="no">account_balance_wallet</span>
              <span>${t('menu_wallet', 'My Wallet')}</span>
            </button>
            <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-PRF-05', { profileTarget: '' })"
              class="h-9 rounded-xl bg-surface-container hover:bg-surface-container-high text-xs font-semibold text-on-surface flex items-center justify-center gap-1.5 transition-colors cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[16px] text-primary" translate="no">person</span>
              <span>${t('menu_profile', 'My Profile')}</span>
            </button>
          </div>
        </div>

        <!-- Mode Switch Banner (Pro Mode Switch) -->
        <div class="bg-gradient-to-r from-primary/15 via-surface-container-low to-secondary/15 rounded-2xl p-4 border border-primary/25 shadow-sm mb-3.5">
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-2.5 min-w-0">
              <div class="w-9 h-9 rounded-xl bg-primary/20 text-primary flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined notranslate text-[20px]" translate="no">bolt</span>
              </div>
              <div class="flex flex-col min-w-0">
                <span class="text-xs font-bold text-on-surface">${t('menu_pro_title', 'Pro Mode (Full View)')}</span>
                <span class="text-[10px] text-on-surface-variant">${t('menu_pro_desc', 'Network Explorer, Nodes, and Developer Tools')}</span>
              </div>
            </div>
            <button type="button" onclick="window.BlocTagSimpleMode.requestProMode()"
              class="px-3 py-1.5 rounded-full bg-primary text-on-primary text-[11px] font-bold hover:brightness-95 active:scale-95 transition-all shadow-sm shrink-0 cursor-pointer">
              ${t('menu_pro_switch', 'Switch Mode')}
            </button>
          </div>
        </div>

        <!-- Quick Simple Features List -->
        <div class="flex flex-col gap-2">
          <span class="text-[11px] font-mono uppercase font-bold text-on-surface-variant/70 px-1">${t('menu_services', 'Operations & Services')}</span>

          <!-- Send Crypto -->
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-WLT-SEND')"
            class="w-full p-3 rounded-2xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/15 flex items-center justify-between text-left transition-all active:scale-[0.99] cursor-pointer">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-xl bg-primary/15 text-primary flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined notranslate text-[18px]" translate="no">send</span>
              </div>
              <div class="flex flex-col">
                <span class="text-xs font-bold text-on-surface">${t('menu_send', 'Send Crypto')}</span>
                <span class="text-[10px] text-on-surface-variant">${t('menu_send_desc', 'Zero-commission instant BCT transfers')}</span>
              </div>
            </div>
            <span class="material-symbols-outlined notranslate text-[18px] text-on-surface-variant" translate="no">chevron_right</span>
          </button>

          <!-- BNS Name (.bct) -->
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-PRF-05', { profileTarget: '' })"
            class="w-full p-3 rounded-2xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/15 flex items-center justify-between text-left transition-all active:scale-[0.99] cursor-pointer">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-xl bg-emerald-500/15 text-emerald-400 flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined notranslate text-[18px]" translate="no">badge</span>
              </div>
              <div class="flex flex-col">
                <span class="text-xs font-bold text-on-surface">${t('menu_bns', 'BNS Username (.bct)')}</span>
                <span class="text-[10px] text-on-surface-variant">${t('menu_bns_desc', 'Manage your Web3 identity and profile')}</span>
              </div>
            </div>
            <span class="material-symbols-outlined notranslate text-[18px] text-on-surface-variant" translate="no">chevron_right</span>
          </button>

          <!-- Backup / Seed Phrase -->
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-WLT-02')"
            class="w-full p-3 rounded-2xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/15 flex items-center justify-between text-left transition-all active:scale-[0.99] cursor-pointer">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-xl bg-amber-500/15 text-amber-400 flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined notranslate text-[18px]" translate="no">key</span>
              </div>
              <div class="flex flex-col">
                <span class="text-xs font-bold text-on-surface">${t('menu_sec', 'Security & Recovery Key')}</span>
                <span class="text-[10px] text-on-surface-variant">${t('menu_sec_desc', '12-word secret recovery phrase (Seed Phrase)')}</span>
              </div>
            </div>
            <span class="material-symbols-outlined notranslate text-[18px] text-on-surface-variant" translate="no">chevron_right</span>
          </button>

          <!-- Notifications -->
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-NTF-06')"
            class="w-full p-3 rounded-2xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/15 flex items-center justify-between text-left transition-all active:scale-[0.99] cursor-pointer">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-xl bg-secondary/15 text-secondary flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined notranslate text-[18px]" translate="no">notifications</span>
              </div>
              <div class="flex flex-col">
                <span class="text-xs font-bold text-on-surface">${t('menu_notif', 'Notifications & Alerts')}</span>
                <span class="text-[10px] text-on-surface-variant">${t('menu_notif_desc', 'Transaction and Space updates')}</span>
              </div>
            </div>
            <span class="material-symbols-outlined notranslate text-[18px] text-on-surface-variant" translate="no">chevron_right</span>
          </button>

          <!-- Language Selector -->
          <button type="button" onclick="window.BlocTagSimpleMode.openLanguageModal()"
            class="w-full p-3 rounded-2xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/15 flex items-center justify-between text-left transition-all active:scale-[0.99] cursor-pointer">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-xl bg-surface-container text-on-surface flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined notranslate text-[18px]" translate="no">language</span>
              </div>
              <div class="flex flex-col">
                <span class="text-xs font-bold text-on-surface">${t('menu_lang', 'Language Selection')}</span>
                <span class="text-[10px] text-on-surface-variant">${t('menu_lang_desc', 'Application interface language')}</span>
              </div>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="text-xs font-bold text-primary font-mono">${activeLangObj.flag} ${esc(activeLangObj.name)}</span>
              <span class="material-symbols-outlined notranslate text-[18px] text-on-surface-variant" translate="no">chevron_right</span>
            </div>
          </button>

          <!-- Whitepaper Link -->
          <a href="/docs/WHITEPAPER.md" target="_blank" rel="noopener noreferrer"
            class="w-full p-3 rounded-2xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/15 flex items-center justify-between text-left transition-all active:scale-[0.99] cursor-pointer">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-xl bg-surface-container text-on-surface flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined notranslate text-[18px]" translate="no">description</span>
              </div>
              <div class="flex flex-col">
                <span class="text-xs font-bold text-on-surface">${t('menu_wp', 'LockTrace Whitepaper')}</span>
                <span class="text-[10px] text-on-surface-variant">${t('menu_wp_desc', 'Protocol architecture and technical documentation')}</span>
              </div>
            </div>
            <span class="material-symbols-outlined notranslate text-[18px] text-on-surface-variant" translate="no">open_in_new</span>
          </a>
        </div>

        <!-- Network Info Pill Footer -->
        <div class="mt-4 p-3 rounded-2xl bg-surface-container-low/60 border border-outline-variant/10 flex items-center justify-between text-[11px] text-on-surface-variant">
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span class="font-mono">LockTrace Mainnet v2.12.2</span>
          </div>
          <span class="font-mono text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-bold">Simple Mode</span>
        </div>
      </main>
    `;
  }

  // ==========================================================================
  // 4. MASTER RENDER DISPATCHER (ZERO-FLICKER DIFF & SILENT BACKGROUND SYNC)
  // ==========================================================================
  let _lastRenderedScreen = null;
  let _lastRenderedFingerprint = '';
  let _lastNavHtml = '';
  let _lastKnownWalletAddr = '';

  function isUserTypingInSimpleMode() {
    const ae = document.activeElement;
    if (!ae) return false;
    const tag = (ae.tagName || '').toUpperCase();
    if (tag !== 'INPUT' && tag !== 'TEXTAREA' && tag !== 'SELECT') return false;
    const shell = document.getElementById('bloctag-simple-mode-shell');
    return Boolean(shell && shell.contains(ae));
  }

  function computeSimpleScreenFingerprint() {
    const acc = getActiveWallet();
    const addr = acc ? String(acc.address || '') : '';
    const bal = acc ? Number(acc.balance || 0).toFixed(6) : '0';
    const nonce = acc ? Number(acc.nonce || 0) : 0;
    const hidden = typeof isBalanceHidden !== 'undefined' && isBalanceHidden ? '1' : '0';
    const unread = getUnreadNotificationsCount();
    const posts = (typeof spacePostsCache !== 'undefined' && Array.isArray(spacePostsCache)) ? spacePostsCache : [];
    const txs = (typeof personalTxCache !== 'undefined' && Array.isArray(personalTxCache)) ? personalTxCache : [];

    const myProfSnap = addr ? getSimpleProfileData(addr) : null;
    const myAvVid = (myProfSnap && myProfSnap.avatar && myProfSnap.avatar.variant_id) ? myProfSnap.avatar.variant_id : '';
    const targetProfSnap = simpleState.profileTarget ? getSimpleProfileData(simpleState.profileTarget) : myProfSnap;
    const targetAvVid = (targetProfSnap && targetProfSnap.avatar && targetProfSnap.avatar.variant_id) ? targetProfSnap.avatar.variant_id : '';

    if (simpleState.activeScreen === 'SCR-SPC-03') {
      const feedSig = posts.slice(0, 35).map(p => `${p.post_id || p.id}:${p.likes_count || (p.likes ? p.likes.length : 0)}:${p.comments_count || (p.comments ? p.comments.length : 0)}:${p.author_avatar ? p.author_avatar.variant_id : ''}`).join(',');
      return `SPC03|${addr}|${myAvVid}|${bal}|${unread}|${simpleState.feedFilter}|${simpleState.feedLayout}|${simpleState.searchBarOpen}|${simpleState.searchQuery}|${feedSig}`;
    }
    if (simpleState.activeScreen === 'SCR-SPC-04') {
      const post = posts.find(p => String(p.post_id || p.id) === String(simpleState.activePostId)) || posts[0];
      const cmts = post && Array.isArray(post.comments) ? post.comments : [];
      const cmtSig = cmts.map(c => c.comment_id || c.tx_hash || c.timestamp).join(',');
      return `SPC04|${addr}|${simpleState.activePostId}|${post ? (post.likes_count || 0) : 0}|${cmts.length}|${cmtSig}|${unread}`;
    }
    if (simpleState.activeScreen === 'SCR-WLT-HOME') {
      const txSig = txs.slice(0, 20).map(t => `${t.tx_hash || t.hash}:${t.status || ''}`).join(',');
      return `WLTHOME|${addr}|${bal}|${nonce}|${hidden}|${simpleState.txFilter}|${txSig}|${unread}`;
    }
    if (simpleState.activeScreen === 'SCR-PRF-FOLLOW' || simpleState.activeScreen === 'SCR-PRF-FOLLOWERS' || simpleState.activeScreen === 'SCR-PRF-FOLLOWING') {
      return `PRFFOLLOW|${addr}|${simpleState.followTargetAddr}|${simpleState.followTab}|${simpleState.followFilter}|${simpleState.followSearch}|${unread}`;
    }
    return `${simpleState.activeScreen}|${addr}|${myAvVid}|${targetAvVid}|${bal}|${nonce}|${hidden}|${unread}|${simpleState.profileTarget}|${simpleState.profileTab}|${simpleState.notifFilter}|${simpleState.importModeOpen}|${simpleState.seedSavedConfirmed}`;
  }

  function patchSimpleLiveValuesInPlace() {
    if (!simpleState.enabled) return;
    const acc = getActiveWallet();
    const bal = acc ? Number(acc.balance || 0) : 0;
    const price = (typeof window.currentWbctPriceUsd === 'number' && window.currentWbctPriceUsd > 0)
      ? window.currentWbctPriceUsd
      : 0.01;
    const hidden = typeof isBalanceHidden !== 'undefined' && isBalanceHidden;
    const balFormatted = hidden ? '••••••' : (typeof window.formatBct === 'function' ? window.formatBct(bal, 4) : bal.toFixed(4));
    const usdFormatted = hidden ? '••••' : (typeof window.formatUsdValue === 'function' ? window.formatUsdValue(bal * price) : ('$' + (bal * price).toFixed(2)));

    const balEl = document.getElementById('simple-wallet-balance-val');
    if (balEl && balEl.textContent !== balFormatted) balEl.textContent = balFormatted;

    const usdEl = document.getElementById('simple-wallet-usd-val');
    if (usdEl && usdEl.textContent !== ('≈ ' + usdFormatted)) usdEl.textContent = '≈ ' + usdFormatted;

    const nonceEl = document.getElementById('simple-wallet-nonce-val');
    const nonceTxt = '• Nonce #' + Number(acc ? (acc.nonce || 0) : 0);
    if (nonceEl && nonceEl.textContent !== nonceTxt) nonceEl.textContent = nonceTxt;

    const spaceSubEl = document.getElementById('simple-space-bal-subtitle');
    if (spaceSubEl) {
      const nextSub = acc
        ? (typeof window.formatBct === 'function' ? window.formatBct(bal, 2) + ' BCT • Zincir Üstü Aktif' : 'Zincir Üstü Aktif')
        : 'Cüzdan oluşturun (+1.00 BCT bonus)';
      if (spaceSubEl.textContent.trim() !== nextSub) spaceSubEl.textContent = nextSub;
    }

    const navPortal = document.getElementById('bloctag-simple-bottom-nav-portal');
    if (navPortal) {
      const nextNavHtml = renderBottomNav();
      if (nextNavHtml !== _lastNavHtml) {
        navPortal.innerHTML = nextNavHtml;
        _lastNavHtml = nextNavHtml;
      }
    }
  }

  function renderSimpleMode(animate = true) {
    if (!simpleState.enabled) return;
    const shell = ensureSimpleModeShell();
    const isSameScreen = (_lastRenderedScreen === simpleState.activeScreen);
    const shouldAnimate = Boolean(animate && !isSameScreen);
    const currentFp = computeSimpleScreenFingerprint();

    // Background sync optimization: if nothing changed, do ZERO DOM work (no flicker!)
    if (!animate && isSameScreen && currentFp === _lastRenderedFingerprint) {
      return;
    }

    // Never tear down DOM while user is actively typing in an input/textarea
    if (!animate && isSameScreen && isUserTypingInSimpleMode()) {
      patchSimpleLiveValuesInPlace();
      return;
    }

    // Targeted in-place feed patch on SCR-SPC-03 (preserves composer text, scroll position, and zero flicker)
    if (!animate && isSameScreen && simpleState.activeScreen === 'SCR-SPC-03') {
      const reelContainer = document.getElementById('simple-reel-container');
      const feedContainer = document.getElementById('simple-feed-container');
      if (reelContainer || feedContainer) {
        const acc = getActiveWallet();
        const posts = (typeof spacePostsCache !== 'undefined' && Array.isArray(spacePostsCache)) ? spacePostsCache : [];
        const q = String(simpleState.searchQuery || '').trim().toLowerCase();
        const filteredPosts = posts.filter(p => {
          if (!p) return false;
          if (simpleState.feedFilter === 'following' && acc && acc.address) {
            const isMine = String(p.author || '').toLowerCase() === acc.address.toLowerCase();
            const hasBns = Boolean(p.author_bns && p.author_bns !== 'anonymous');
            if (!isMine && !hasBns) return false;
          }
          if (q) {
            const content = String(p.content || '').toLowerCase();
            const author = String(p.author || '').toLowerCase();
            const bns = String(p.author_bns || '').toLowerCase();
            return content.includes(q) || author.includes(q) || bns.includes(q);
          }
          return true;
        });
        if (reelContainer) {
          reelContainer.innerHTML = filteredPosts.length === 0 ? `
            <div class="h-full flex flex-col items-center justify-center p-8 text-center text-on-surface-variant">
              <span class="material-symbols-outlined notranslate text-[36px] text-primary mb-2" translate="no">forum</span>
              <span class="text-xs font-semibold">${t('space_empty_posts', 'Posts are loading or none found in this filter...')}</span>
            </div>
          ` : filteredPosts.map((post, idx) => renderSimpleReelCard(post, acc, idx, filteredPosts.length)).join('');
        } else if (feedContainer) {
          feedContainer.innerHTML = filteredPosts.length === 0 ? `
            <div class="p-8 rounded-2xl bg-surface-container-low text-center flex flex-col items-center gap-2 text-on-surface-variant">
              <span class="material-symbols-outlined notranslate text-[28px] text-primary" translate="no">forum</span>
              <span class="text-xs">${t('space_empty_posts', 'Posts are loading or none found in this filter...')}</span>
            </div>
          ` : filteredPosts.slice(0, 35).map(post => renderSimplePostCard(post, acc)).join('');
        }
        patchSimpleLiveValuesInPlace();
        _lastRenderedFingerprint = currentFp;
        return;
      }
    }

    let screenHtml = '';
    switch (simpleState.activeScreen) {
      case 'SCR-ONB-01':
        screenHtml = renderScreenOnboardingWelcome();
        break;
      case 'SCR-WLT-02':
        screenHtml = renderScreenSeedPhrase();
        break;
      case 'SCR-WLT-HOME':
        screenHtml = renderScreenWalletHome();
        break;
      case 'SCR-WLT-SEND':
        screenHtml = renderScreenWalletSend();
        break;
      case 'SCR-SPC-04':
        screenHtml = renderScreenPostDetail();
        break;
      case 'SCR-PRF-05':
        screenHtml = renderScreenProfile();
        break;
      case 'SCR-PRF-FOLLOW':
      case 'SCR-PRF-FOLLOWERS':
      case 'SCR-PRF-FOLLOWING':
        screenHtml = renderScreenFollowList();
        break;
      case 'SCR-NTF-06':
        screenHtml = renderScreenNotifications();
        break;
      case 'SCR-MNU-07':
        screenHtml = renderScreenMenu();
        break;
      case 'SCR-SPC-03':
      default:
        screenHtml = renderScreenSpaceFeed();
        break;
    }

    if (!shouldAnimate) {
      screenHtml = screenHtml.replace(/\bsimple-screen-animate\b/g, '');
    }

    shell.innerHTML = `
      <div class="simple-app-frame">
        ${screenHtml}
      </div>
    `;

    const navPortal = document.getElementById('bloctag-simple-bottom-nav-portal');
    if (navPortal) {
      const nextNavHtml = renderBottomNav();
      if (nextNavHtml !== _lastNavHtml) {
        navPortal.innerHTML = nextNavHtml;
        _lastNavHtml = nextNavHtml;
      }
    }

    _lastRenderedScreen = simpleState.activeScreen;
    _lastRenderedFingerprint = currentFp;
    const accNow = getActiveWallet();
    _lastKnownWalletAddr = accNow ? String(accNow.address || '') : '';

    if (simpleState.activeScreen === 'SCR-WLT-SEND') {
      updateSimpleSendPreview();
    }
  }

  // ==========================================================================
  // 5. NON-CUSTODIAL ACTIONS & EVENT HANDLERS
  // ==========================================================================
  function updateSimpleSendPreview() {
    const inp = document.getElementById('simple-send-amount');
    const netEl = document.getElementById('simple-send-net-preview');
    const feeEl = document.getElementById('simple-send-fee-preview');
    if (!inp) return;
    const raw = String(inp.value || '').replace(',', '.').replace(/[^0-9.]/g, '');
    const amt = parseFloat(raw) || 0;
    const fee = amt > 0 ? Math.max(0.001, Number((amt * 0.01).toFixed(8))) : 0;
    const net = Math.max(0, Number((amt - fee).toFixed(8)));
    if (netEl) netEl.textContent = (typeof window.formatBct === 'function' ? window.formatBct(net, 4) : net.toFixed(4)) + ' BCT';
    if (feeEl) feeEl.textContent = (typeof window.formatBct === 'function' ? window.formatBct(fee, 4) : fee.toFixed(4)) + ' BCT';
  }

  const BlocTagSimpleMode = {
    go: (screen, opts) => navigateToSimpleScreen(screen, opts),
    back: () => navigateSimpleBack(),
    refresh: () => renderSimpleMode(),
    requestProMode: (targetTab) => requestSwitchToProMode(targetTab),
    confirmProSwitch: () => confirmSwitchToProMode(),
    cancelProSwitch: () => cancelSwitchToProMode(),

    switchToMainFeed: () => {
      toggleSimpleModeSetting(false);
      if (typeof window.switchTab === 'function') {
        window.switchTab('space');
      }
      if (typeof window.showToast === 'function') {
        window.showToast(t('switched_to_main_feed_toast', 'Switched to Main Space Feed'), 'auto_awesome');
      }
    },

    toggleFeedLayout: () => {
      simpleState.feedLayout = (simpleState.feedLayout === 'classic') ? 'snap' : 'classic';
      try {
        localStorage.setItem('bloctag_simple_feed_layout', simpleState.feedLayout);
      } catch (_e) { }
      _lastRenderedFingerprint = '';
      renderSimpleMode(true);
      if (typeof window.showToast === 'function') {
        window.showToast(
          simpleState.feedLayout === 'snap'
            ? t('feed_layout_snap', 'Reels / TikTok View active')
            : t('feed_layout_list', 'List View active'),
          'auto_awesome'
        );
      }
    },

    reelNext: () => {
      const container = document.getElementById('simple-reel-container');
      if (container) {
        container.scrollBy({ top: container.clientHeight || 450, behavior: 'smooth' });
      }
    },

    reelPrev: () => {
      const container = document.getElementById('simple-reel-container');
      if (container) {
        container.scrollBy({ top: -(container.clientHeight || 450), behavior: 'smooth' });
      }
    },

    openWalletTab: () => {
      const acc = getActiveWallet();
      navigateToSimpleScreen(acc ? 'SCR-WLT-HOME' : 'SCR-ONB-01');
    },

    startCreateWallet: () => {
      generateSimpleSeedPreview();
      navigateToSimpleScreen('SCR-WLT-02');
    },

    refreshSeed: () => {
      try {
        if (typeof LockTraceCrypto !== 'undefined' && typeof LockTraceCrypto.generateMnemonic12 === 'function') {
          simpleState.seedMnemonic = LockTraceCrypto.generateMnemonic12();
          try { previewMnemonicPhrase = simpleState.seedMnemonic; } catch (_e) { }
          simpleState.seedSavedConfirmed = false;
          renderSimpleMode();
        }
      } catch (_e) { }
    },

    copySeed: () => {
      const phrase = simpleState.seedMnemonic;
      if (!phrase) return;
      if (typeof window.copyText === 'function') {
        window.copyText(phrase, 'Kurtarma kelimeleri panoya kopyalandı!');
      } else if (navigator.clipboard) {
        navigator.clipboard.writeText(phrase).catch(() => { });
      }
      const ic = document.getElementById('simple-copy-seed-icon');
      const tx = document.getElementById('simple-copy-seed-text');
      if (ic) ic.textContent = 'check';
      if (tx) tx.textContent = 'Kopyalandı!';
    },

    toggleSeedSaved: () => {
      simpleState.seedSavedConfirmed = !simpleState.seedSavedConfirmed;
      renderSimpleMode();
    },

    finalizeCreateWallet: async () => {
      if (!simpleState.seedSavedConfirmed || !simpleState.seedMnemonic) return;
      const btn = document.getElementById('simple-finalize-wallet-btn');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="material-symbols-outlined notranslate animate-spin text-[18px]" translate="no">progress_activity</span><span>${t('seed_prep_wallet', 'Preparing Wallet...')}</span>`;
      }
      try {
        try {
          previewMnemonicPhrase = simpleState.seedMnemonic;
          isTermsAccepted = true;
        } catch (_e) { }

        if (typeof window.requestNewWallet === 'function') {
          await window.requestNewWallet();
          navigateToSimpleScreen('SCR-SPC-03');
        }
      } catch (err) {
        if (typeof window.showToast === 'function') {
          window.showToast(err.message || t('wallet_create_failed', 'Could not create wallet'), 'error', true);
        }
        renderSimpleMode();
      }
    },

    toggleImport: (force) => {
      const acc = getActiveWallet();
      if (force === undefined && acc && !simpleState.importModeOpen) {
        navigateToSimpleScreen('SCR-WLT-HOME');
        return;
      }
      simpleState.importModeOpen = typeof force === 'boolean' ? force : !simpleState.importModeOpen;
      renderSimpleMode();
    },

    submitImport: async () => {
      const inp = document.getElementById('simpleImportInput');
      const val = String(inp ? inp.value : '').trim();
      if (!val) {
        if (typeof window.showToast === 'function') window.showToast(t('import_key_required', 'Please enter 12 words or private key'), 'warning', true);
        return;
      }
      const proInput = document.getElementById('importInputKey');
      if (proInput && typeof window.executeImportWallet === 'function') {
        const words = val.split(/\s+/).filter(Boolean);
        if (typeof window.setImportTab === 'function') {
          window.setImportTab(words.length === 12 ? 'words' : 'key');
        }
        proInput.value = val;
        if (typeof window.handleImportInputLive === 'function') {
          await window.handleImportInputLive(val);
        }
        await window.executeImportWallet();
        if (getActiveWallet()) {
          simpleState.importModeOpen = false;
          navigateToSimpleScreen('SCR-WLT-HOME');
        }
      }
    },

    setTxFilter: (f) => {
      simpleState.txFilter = f;
      renderSimpleMode();
    },

    openTxByHash: (hash) => {
      if (!hash) return;
      const txs = (typeof personalTxCache !== 'undefined' && Array.isArray(personalTxCache)) ? personalTxCache : [];
      const found = txs.find(t => String(t.tx_hash || t.hash) === String(hash));
      if (found && typeof window.openTxDetail === 'function') {
        window.openTxDetail(found);
      }
    },

    updateSendPreview: () => updateSimpleSendPreview(),

    setSendPct: (pct) => {
      const acc = getActiveWallet();
      const bal = acc ? Number(acc.balance || 0) : 0;
      const inp = document.getElementById('simple-send-amount');
      if (inp) {
        const val = Math.max(0, bal * Number(pct || 0));
        inp.value = val > 0 ? val.toFixed(4).replace(/\.?0+$/, '') : '0';
        updateSimpleSendPreview();
      }
    },

    pasteRecipient: async () => {
      try {
        if (navigator.clipboard && navigator.clipboard.readText) {
          const text = (await navigator.clipboard.readText() || '').trim();
          const inp = document.getElementById('simple-send-recipient');
          if (inp && text) inp.value = text;
        }
      } catch (_e) { }
    },

    executeSend: async () => {
      const amtInp = document.getElementById('simple-send-amount');
      const recInp = document.getElementById('simple-send-recipient');
      const amt = String(amtInp ? amtInp.value : '').trim();
      const rec = String(recInp ? recInp.value : '').trim();
      if (!amt || !rec) {
        if (typeof window.showToast === 'function') window.showToast(t('send_fields_required', 'Please enter amount and recipient address'), 'warning', true);
        return;
      }
      const proAmt = document.getElementById('sendAmountInput');
      const proRec = document.getElementById('sendRecipientInput');
      if (proAmt && proRec && typeof window.executeSendTransaction === 'function') {
        proAmt.value = amt;
        proRec.value = rec;
        if (typeof window.sanitizeAndPreviewSendAmount === 'function') window.sanitizeAndPreviewSendAmount(proAmt);
        if (typeof window.validateRecipientInput === 'function') await window.validateRecipientInput();
        await window.executeSendTransaction();
        simpleState.sendPrefillAmount = '';
        simpleState.sendPrefillRecipient = '';
        navigateToSimpleScreen('SCR-WLT-HOME');
      }
    },

    setFeedFilter: (f) => {
      simpleState.feedFilter = f;
      renderSimpleMode();
    },

    toggleSearch: () => {
      simpleState.searchBarOpen = !simpleState.searchBarOpen;
      if (!simpleState.searchBarOpen) simpleState.searchQuery = '';
      renderSimpleMode();
      if (simpleState.searchBarOpen) {
        setTimeout(() => document.getElementById('simple-space-search-input')?.focus(), 50);
      }
    },

    setSearchQuery: (q) => {
      simpleState.searchQuery = String(q || '');
      renderSimpleMode();
      const inp = document.getElementById('simple-space-search-input');
      if (inp) {
        inp.focus();
        inp.setSelectionRange(inp.value.length, inp.value.length);
      }
    },

    focusComposer: () => {
      const inp = document.getElementById('simple-composer-input');
      if (inp) {
        inp.focus();
        inp.scrollIntoView({ behavior: 'smooth', block: 'center' });
      } else {
        window.BlocTagSimpleMode.openComposerModal();
      }
    },

    openComposerModal: () => {
      let modal = document.getElementById('simple-composer-modal');
      if (!modal) {
        modal = document.createElement('div');
        modal.id = 'simple-composer-modal';
        document.body.appendChild(modal);
      }
      modal.className = 'fixed inset-0 z-[90] bg-black/75 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4 transition-all duration-200';
      modal.innerHTML = `
        <div class="w-full sm:max-w-lg bg-surface-container-high rounded-t-2xl sm:rounded-2xl border border-outline-variant/30 shadow-2xl p-5 flex flex-col gap-3">
          <div class="flex items-center justify-between pb-2 border-b border-outline-variant/15">
            <div class="flex items-center gap-2">
              <span class="material-symbols-outlined notranslate text-primary text-[20px]" translate="no">edit_square</span>
              <span class="text-sm font-semibold text-on-surface">${t('space_compose_title', 'New Post')}</span>
            </div>
            <button type="button" onclick="window.BlocTagSimpleMode.closeComposerModal()" class="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center text-on-surface-variant hover:text-on-surface cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[18px]" translate="no">close</span>
            </button>
          </div>
          <textarea id="simple-modal-composer-input" rows="4" placeholder="${t('space_whats_happening', "What's happening on LockTrace?")}"
            class="w-full bg-surface-container-lowest rounded-xl p-3 text-sm text-on-surface placeholder:text-outline border border-outline-variant/20 focus:outline-none focus:border-primary resize-none"></textarea>
          <div class="flex items-center justify-between pt-1">
            <div class="flex items-center gap-1.5 flex-wrap">
              <button type="button" onclick="window.BlocTagSimpleMode.insertModalComposerTag('#locktrace')" class="px-2 py-0.5 rounded-full bg-surface-container text-[11px] font-mono text-primary border border-primary/20 hover:bg-primary/10">#locktrace</button>
              <button type="button" onclick="window.BlocTagSimpleMode.insertModalComposerTag('#crypto')" class="px-2 py-0.5 rounded-full bg-surface-container text-[11px] font-mono text-primary border border-primary/20 hover:bg-primary/10">#crypto</button>
              <button type="button" onclick="window.BlocTagSimpleMode.insertModalComposerTag('#web3')" class="px-2 py-0.5 rounded-full bg-surface-container text-[11px] font-mono text-primary border border-primary/20 hover:bg-primary/10">#web3</button>
            </div>
            <button type="button" onclick="window.BlocTagSimpleMode.submitModalPost()" class="h-9 px-5 rounded-full bg-primary text-on-primary text-xs font-semibold flex items-center gap-1 shadow-md hover:scale-105 active:scale-95 transition-all cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[16px]" translate="no">send</span>
              <span>${t('space_btn_post', 'Post')}</span>
            </button>
          </div>
        </div>
      `;
      setTimeout(() => document.getElementById('simple-modal-composer-input')?.focus(), 50);
    },

    closeComposerModal: () => {
      const modal = document.getElementById('simple-composer-modal');
      if (modal) modal.remove();
    },

    // ── ON-CHAIN PROFILE AVATAR STUDIO (Bonding Curve + Color Variants) ─────
    _avatarStudioState: {
      tab: 'catalog',       // 'catalog' | 'owned'
      collection: 'animals',
      catalogData: null,
      selectedBaseId: 'ANM-001',
      selectedColor: '#FFFFFF',
      quote: null,
      loadingQuote: false,
      busy: false,
    },

    openAvatarStudio: async () => {
      const acc = getActiveWallet();
      if (!acc || !acc.address) {
        navigateToSimpleScreen('SCR-ONB-01');
        return;
      }
      const st = window.BlocTagSimpleMode._avatarStudioState;
      st.tab = 'catalog';
      st.busy = false;
      window.BlocTagSimpleMode._renderAvatarStudioModal(true);

      try {
        const apiUrl = '/avatars/catalog?address=' + encodeURIComponent(acc.address);
        const res = (typeof window.apiFetch === 'function')
          ? await window.apiFetch(apiUrl)
          : await fetch('/api/v1' + apiUrl).then(r => r.json().then(b => ({ ok: r.ok, body: b })));
        if (res.ok && res.body && res.body.data) {
          st.catalogData = res.body.data;
          if (!st.selectedBaseId && st.catalogData.catalog && st.catalogData.catalog.length > 0) {
            st.selectedBaseId = st.catalogData.catalog[0].base_id;
          }
          window.BlocTagSimpleMode._renderAvatarStudioModal(false);
          await window.BlocTagSimpleMode._fetchAvatarQuote();
        }
      } catch (err) {
        console.error('Avatar catalog load error:', err);
        if (typeof window.showToast === 'function') window.showToast('Failed to load avatar catalog.', 'error');
      }
    },

    closeAvatarStudio: () => {
      const modal = document.getElementById('simple-avatar-studio-modal');
      if (modal) modal.remove();
    },

    setAvatarStudioTab: (tab) => {
      const st = window.BlocTagSimpleMode._avatarStudioState;
      st.tab = (tab === 'owned') ? 'owned' : 'catalog';
      window.BlocTagSimpleMode._renderAvatarStudioModal(false);
    },

    selectAvatarItem: async (baseId) => {
      const st = window.BlocTagSimpleMode._avatarStudioState;
      st.selectedBaseId = String(baseId || 'ANM-001').toUpperCase();
      window.BlocTagSimpleMode._renderAvatarStudioModal(false);
      await window.BlocTagSimpleMode._fetchAvatarQuote();
    },

    selectAvatarColor: async (hexColor) => {
      const st = window.BlocTagSimpleMode._avatarStudioState;
      let c = String(hexColor || '#FFFFFF').trim().toUpperCase();
      if (!c.startsWith('#')) c = '#' + c;
      if (!/^#[0-9A-F]{6}$/.test(c)) return;
      st.selectedColor = c;
      window.BlocTagSimpleMode._renderAvatarStudioModal(false);
      await window.BlocTagSimpleMode._fetchAvatarQuote();
    },

    _fetchAvatarQuote: async () => {
      const acc = getActiveWallet();
      const st = window.BlocTagSimpleMode._avatarStudioState;
      st.loadingQuote = true;
      window.BlocTagSimpleMode._renderAvatarStudioModal(false);
      try {
        const qUrl = '/avatars/price?base_id=' + encodeURIComponent(st.selectedBaseId)
          + '&bg_color=' + encodeURIComponent(st.selectedColor)
          + (acc && acc.address ? '&address=' + encodeURIComponent(acc.address) : '');
        const res = (typeof window.apiFetch === 'function')
          ? await window.apiFetch(qUrl)
          : await fetch('/api/v1' + qUrl).then(r => r.json().then(b => ({ ok: r.ok, body: b })));
        if (res.ok && res.body && res.body.data) {
          st.quote = res.body.data;
        }
      } catch (err) {
        console.error('Avatar quote error:', err);
      } finally {
        st.loadingQuote = false;
        window.BlocTagSimpleMode._renderAvatarStudioModal(false);
      }
    },

    mintSelectedAvatar: async () => {
      const acc = getActiveWallet();
      const st = window.BlocTagSimpleMode._avatarStudioState;
      if (!acc || !acc.address || st.busy) return;
      if (typeof window.buildSignedAuthPayload !== 'function') {
        if (typeof window.showToast === 'function') window.showToast('Wallet signing engine unavailable.', 'error');
        return;
      }

      const baseId = st.selectedBaseId;
      const bgColor = st.selectedColor;
      const variantId = `${baseId}-${bgColor.slice(1)}`;
      const maxPrice = st.quote ? Number(st.quote.price) : 0.10;

      st.busy = true;
      window.BlocTagSimpleMode._renderAvatarStudioModal(false);
      try {
        const canonical = `AVATAR_MINT:${acc.address}:${variantId}`;
        const authFields = await window.buildSignedAuthPayload(canonical);
        const resp = await window.apiFetch('/avatars/mint', {
          method: 'POST',
          body: JSON.stringify({
            buyer: acc.address,
            base_id: baseId,
            bg_color: bgColor,
            max_price: maxPrice,
            auto_equip: true,
            ...authFields
          })
        });
        if (!resp.ok || !resp.body || !resp.body.success) {
          throw new Error((resp.body && resp.body.message) || 'Avatar mint failed');
        }
        const d = resp.body.data || {};
        // Update local wallet balance & profile cache immediately
        if (typeof d.new_balance === 'number') {
          acc.balance = d.new_balance;
          if (typeof window.saveWalletState === 'function') window.saveWalletState(acc);
        }
        const addrKey = acc.address.toLowerCase();
        if (_simpleProfileCache[addrKey]) {
          _simpleProfileCache[addrKey].avatar = d.equipped_avatar || d.avatar || null;
          _simpleProfileCache[addrKey].owned_avatars = d.owned_avatars || [];
          _simpleProfileCache[addrKey]._cachedAt = 0;
        }
        if (typeof window.showToast === 'function') {
          window.showToast(resp.body.message || `Avatar ${variantId} minted & equipped!`, 'verified');
        }
        // Refresh catalog, quote, profile, and space feed
        await window.BlocTagSimpleMode.openAvatarStudio();
        fetchSimpleProfile(acc.address);
        if (typeof window.loadSpaceFeed === 'function') window.loadSpaceFeed();
        renderSimpleMode();
      } catch (err) {
        if (typeof window.showToast === 'function') {
          window.showToast(err.message || 'Avatar purchase canceled or failed.', 'error');
        }
      } finally {
        st.busy = false;
        window.BlocTagSimpleMode._renderAvatarStudioModal(false);
      }
    },

    confirmEquipAvatar: (variantId) => {
      const st = window.BlocTagSimpleMode._avatarStudioState;
      if (st.busy) return;
      const cleanVid = String(variantId || '').trim().toUpperCase();
      const cat = st.catalogData || {};
      const currentEq = cat.equipped_avatar || null;
      const hasEquipped = Boolean(currentEq && currentEq.variant_id);
      const isTr = (typeof getSimpleLang === 'function' ? getSimpleLang() : 'en') === 'tr';

      let title = '';
      let desc = '';
      let feeLabel = '0.20 BCT';
      let confirmBtnText = '';

      if (!cleanVid) {
        // Unequip / Remove warning (explicitly informs user about 0.20 remove + 0.20 re-equip = 0.40 total)
        feeLabel = '0.20 BCT';
        title = isTr ? 'Profil Fotoğrafını Kaldır (0.20 BCT)' : 'Remove Profile Photo (0.20 BCT)';
        desc = isTr
          ? 'Bu işlem blokzincirde bir hareket olduğu için fotoğrafı kaldırma ücreti <b>0.20 BCT</b>\'dir. Daha sonra yeni bir fotoğraf takmak istediğinizde tekrar <b>0.20 BCT</b> ödersiniz — yani fotoğraf değiştirmenin toplam maliyeti <b>0.40 BCT</b>\'dir.'
          : 'Because this is an on-chain blockchain transaction, removing your photo costs <b>0.20 BCT</b>. Equipping another photo afterwards also costs <b>0.20 BCT</b> — for a total of <b>0.40 BCT</b> to change your profile photo.';
        confirmBtnText = isTr ? 'Onayla ve Kaldır (0.20 BCT)' : 'Confirm & Remove (0.20 BCT)';
      } else if (hasEquipped) {
        // Direct Swap (0.20 remove old + 0.20 equip new = 0.40 BCT)
        feeLabel = '0.40 BCT';
        title = isTr ? 'Profil Fotoğrafını Değiştir (0.40 BCT)' : 'Change Profile Photo (0.40 BCT)';
        desc = isTr
          ? `Mevcut fotoğrafı kaldırıp <b>${esc(cleanVid)}</b> avatarını takmak toplam <b>0.40 BCT</b> (0.20 BCT çıkarma + 0.20 BCT takma) on-chain işlem ücreti gerektirir.`
          : `Removing your current photo and equipping <b>${esc(cleanVid)}</b> costs <b>0.40 BCT</b> total (0.20 BCT unequip + 0.20 BCT equip) on-chain.`;
        confirmBtnText = isTr ? 'Onayla ve Değiştir (0.40 BCT)' : 'Confirm & Change (0.40 BCT)';
      } else {
        // Fresh Equip (0.20 BCT)
        feeLabel = '0.20 BCT';
        title = isTr ? 'Profil Fotoğrafını Tak (0.20 BCT)' : 'Equip Profile Photo (0.20 BCT)';
        desc = isTr
          ? `<b>${esc(cleanVid)}</b> avatarını profilinize takmak blokzincir işlemi olduğu için <b>0.20 BCT</b> ücretlidir. (İleride kaldırmak isterseniz kaldırma da 0.20 BCT, toplam değişim 0.40 BCT\'dir.)`
          : `Equipping <b>${esc(cleanVid)}</b> to your profile is an on-chain transaction costing <b>0.20 BCT</b>. (Removing later also costs 0.20 BCT; total photo change is 0.40 BCT.)`;
        confirmBtnText = isTr ? 'Onayla ve Tak (0.20 BCT)' : 'Confirm & Equip (0.20 BCT)';
      }

      let dlg = document.getElementById('simple-avatar-fee-confirm-modal');
      if (!dlg) {
        dlg = document.createElement('div');
        dlg.id = 'simple-avatar-fee-confirm-modal';
        document.body.appendChild(dlg);
      }
      dlg.className = 'fixed inset-0 z-[105] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4';
      dlg.innerHTML = `
        <div class="w-full max-w-sm bg-surface-container-high rounded-3xl border border-outline-variant/30 shadow-2xl p-5 space-y-4">
          <div class="flex items-start gap-3">
            <div class="w-10 h-10 rounded-full bg-amber-500/15 text-amber-400 flex items-center justify-center shrink-0">
              <span class="material-symbols-outlined notranslate text-[22px]" translate="no">info</span>
            </div>
            <div class="min-w-0">
              <h4 class="text-sm font-bold text-on-surface">${title}</h4>
              <p class="text-xs text-on-surface-variant mt-1.5 leading-relaxed">${desc}</p>
            </div>
          </div>
          <div class="px-3 py-2 rounded-xl bg-surface-container text-[10.5px] text-on-surface-variant flex items-center justify-between">
            <span>${isTr ? 'On-Chain İşlem Ücreti:' : 'On-Chain Tx Fee:'}</span>
            <span class="font-mono font-bold text-primary">${feeLabel}</span>
          </div>
          <div class="flex items-center gap-2 pt-1">
            <button type="button" onclick="window.BlocTagSimpleMode.closeAvatarFeeConfirm()"
              class="flex-1 h-10 rounded-full bg-surface-container text-on-surface text-xs font-semibold hover:bg-surface-container-highest transition-colors cursor-pointer">
              ${isTr ? 'Vazgeç' : 'Cancel'}
            </button>
            <button type="button" onclick="window.BlocTagSimpleMode.closeAvatarFeeConfirm(); window.BlocTagSimpleMode.equipAvatarVariant('${escAttr(cleanVid)}');"
              class="flex-1 h-10 rounded-full bg-primary text-on-primary text-xs font-bold shadow-md hover:brightness-95 transition-all cursor-pointer">
              ${confirmBtnText}
            </button>
          </div>
        </div>
      `;
    },

    closeAvatarFeeConfirm: () => {
      const dlg = document.getElementById('simple-avatar-fee-confirm-modal');
      if (dlg) dlg.remove();
    },

    equipAvatarVariant: async (variantId) => {
      const acc = getActiveWallet();
      const st = window.BlocTagSimpleMode._avatarStudioState;
      if (!acc || !acc.address || st.busy) return;
      if (typeof window.buildSignedAuthPayload !== 'function') {
        if (typeof window.showToast === 'function') window.showToast('Wallet signing engine unavailable.', 'error');
        return;
      }

      const cleanVid = String(variantId || '').trim().toUpperCase();
      st.busy = true;
      window.BlocTagSimpleMode._renderAvatarStudioModal(false);
      try {
        const canonical = `AVATAR_EQUIP:${acc.address}:${cleanVid}`;
        const authFields = await window.buildSignedAuthPayload(canonical);
        const resp = await window.apiFetch('/avatars/equip', {
          method: 'POST',
          body: JSON.stringify({
            owner: acc.address,
            variant_id: cleanVid,
            ...authFields
          })
        });
        if (!resp.ok || !resp.body || !resp.body.success) {
          throw new Error((resp.body && resp.body.message) || 'Avatar update failed');
        }
        const d = resp.body.data || {};
        if (typeof d.new_balance === 'number') {
          acc.balance = d.new_balance;
          if (typeof window.saveWalletState === 'function') window.saveWalletState(acc);
        }
        const addrKey = acc.address.toLowerCase();
        if (_simpleProfileCache[addrKey]) {
          _simpleProfileCache[addrKey].avatar = d.equipped_avatar || null;
          _simpleProfileCache[addrKey].owned_avatars = d.owned_avatars || [];
          _simpleProfileCache[addrKey]._cachedAt = 0;
        }
        if (typeof window.showToast === 'function') {
          window.showToast(resp.body.message || (cleanVid ? 'Avatar equipped!' : 'Avatar removed from profile.'), 'check_circle');
        }
        await window.BlocTagSimpleMode.openAvatarStudio();
        fetchSimpleProfile(acc.address);
        if (typeof window.loadSpaceFeed === 'function') window.loadSpaceFeed();
        renderSimpleMode();
      } catch (err) {
        if (typeof window.showToast === 'function') {
          window.showToast(err.message || 'Avatar equip failed.', 'error');
        }
      } finally {
        st.busy = false;
        window.BlocTagSimpleMode._renderAvatarStudioModal(false);
      }
    },

    _renderAvatarStudioModal: (isInitialLoading) => {
      let modal = document.getElementById('simple-avatar-studio-modal');
      if (!modal) {
        modal = document.createElement('div');
        modal.id = 'simple-avatar-studio-modal';
        document.body.appendChild(modal);
      }
      const st = window.BlocTagSimpleMode._avatarStudioState;
      const isTr = (typeof getSimpleLang === 'function' ? getSimpleLang() : 'en') === 'tr';
      const cat = st.catalogData;
      const catalogItems = (cat && Array.isArray(cat.catalog)) ? cat.catalog : [];
      const curatedColors = (cat && Array.isArray(cat.curated_colors)) ? cat.curated_colors : [
        { hex: '#FFFFFF', name: 'White', name_tr: 'Beyaz' },
        { hex: '#0F172A', name: 'Obsidian', name_tr: 'Obsidyen' },
        { hex: '#10B981', name: 'Emerald', name_tr: 'Zümrüt' },
        { hex: '#3B82F6', name: 'Blue', name_tr: 'Mavi' },
        { hex: '#8B5CF6', name: 'Violet', name_tr: 'Mor' },
        { hex: '#EC4899', name: 'Pink', name_tr: 'Pembe' },
        { hex: '#F59E0B', name: 'Gold', name_tr: 'Altın' },
        { hex: '#EF4444', name: 'Red', name_tr: 'Kırmızı' },
      ];
      const ownedAvatars = (cat && Array.isArray(cat.owned_avatars)) ? cat.owned_avatars : [];
      const equippedAvatar = (cat && cat.equipped_avatar) ? cat.equipped_avatar : null;

      const selectedItem = catalogItems.find(i => i.base_id === st.selectedBaseId) || catalogItems[0] || null;
      const liveVariantId = selectedItem ? `${selectedItem.base_id}-${st.selectedColor.slice(1)}` : '';
      const q = (st.quote && st.quote.variant_id === liveVariantId) ? st.quote : null;

      const priceDisplay = q ? Number(q.price).toFixed(q.price >= 1 ? 4 : (q.price === 0.1 ? 2 : 5)).replace(/0+$/, '').replace(/\.$/, '') : '0.10';
      const nextPriceDisplay = q ? Number(q.next_price).toFixed(5).replace(/0+$/, '').replace(/\.$/, '') : '0.125';
      const mintCount = q ? Number(q.mint_count || 0) : 0;
      const alreadyOwned = Boolean(q ? q.already_owned : ownedAvatars.some(o => o.variant_id === liveVariantId));
      const isEquipped = Boolean(q ? q.is_equipped : (equippedAvatar && equippedAvatar.variant_id === liveVariantId));

      modal.className = 'fixed inset-0 z-[95] bg-black/80 backdrop-blur-md flex items-end sm:items-center justify-center p-0 sm:p-4';
      modal.innerHTML = `
        <div class="w-full sm:max-w-lg max-h-[92dvh] bg-surface-container-high rounded-t-3xl sm:rounded-3xl border border-outline-variant/25 shadow-2xl flex flex-col overflow-hidden">
          <!-- Studio Header -->
          <div class="flex items-center justify-between px-5 py-4 border-b border-outline-variant/15 shrink-0">
            <div class="flex items-center gap-2.5 min-w-0">
              <div class="w-9 h-9 rounded-full bg-primary/15 text-primary flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined notranslate text-[20px]" translate="no">palette</span>
              </div>
              <div class="min-w-0">
                <h3 class="text-sm font-bold text-on-surface truncate">${isTr ? 'On-Chain Avatar Stüdyosu' : 'On-Chain Avatar Studio'}</h3>
                <p class="text-[11px] text-on-surface-variant truncate">${isTr ? 'Soulbound (Satılamaz / Gönderilemez) • Hayvanlar Koleksiyonu' : 'Soulbound (Non-transferable) • Animals Collection'}</p>
              </div>
            </div>
            <button type="button" onclick="window.BlocTagSimpleMode.closeAvatarStudio()"
              class="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center text-on-surface-variant hover:text-on-surface cursor-pointer shrink-0">
              <span class="material-symbols-outlined notranslate text-[18px]" translate="no">close</span>
            </button>
          </div>

          <!-- Tabs (Catalog / My Avatars) -->
          <div class="px-5 pt-3 pb-2 flex items-center gap-2 shrink-0">
            <button type="button" onclick="window.BlocTagSimpleMode.setAvatarStudioTab('catalog')"
              class="flex-1 h-9 rounded-full text-xs font-semibold transition-all cursor-pointer ${st.tab === 'catalog' ? 'bg-primary text-on-primary shadow-sm' : 'bg-surface-container text-on-surface-variant hover:text-on-surface'}">
              ${isTr ? 'Hayvanlar (' + catalogItems.length + ')' : 'Animals (' + catalogItems.length + ')'}
            </button>
            <button type="button" onclick="window.BlocTagSimpleMode.setAvatarStudioTab('owned')"
              class="flex-1 h-9 rounded-full text-xs font-semibold transition-all cursor-pointer ${st.tab === 'owned' ? 'bg-primary text-on-primary shadow-sm' : 'bg-surface-container text-on-surface-variant hover:text-on-surface'}">
              ${isTr ? 'Avatarlarım (' + ownedAvatars.length + ')' : 'My Avatars (' + ownedAvatars.length + ')'}
            </button>
          </div>

          <!-- Scrollable Body -->
          <div class="flex-1 overflow-y-auto px-5 pb-5 pt-2 space-y-4">
            ${isInitialLoading ? `
              <div class="py-12 flex flex-col items-center justify-center gap-2 text-on-surface-variant">
                <span class="material-symbols-outlined notranslate text-[32px] text-primary animate-spin" translate="no">progress_activity</span>
                <span class="text-xs font-medium">${isTr ? 'Koleksiyon yükleniyor...' : 'Loading on-chain collection...'}</span>
              </div>
            ` : (st.tab === 'owned' ? `
              <!-- MY OWNED AVATARS TAB -->
              ${equippedAvatar ? `
                <div class="p-3.5 rounded-2xl bg-primary/10 border border-primary/25 flex items-center justify-between gap-3">
                  <div class="flex items-center gap-3 min-w-0">
                    <div class="w-12 h-12 rounded-full overflow-hidden shrink-0 ring-2 ring-primary">
                      ${renderAvatarCircleHtml(equippedAvatar, '')}
                    </div>
                    <div class="min-w-0">
                      <span class="text-[10px] font-bold uppercase tracking-wider text-primary block">${isTr ? 'Profilde Aktif' : 'Equipped on Profile'}</span>
                      <span class="text-xs font-bold text-on-surface truncate block">${esc(isTr ? (equippedAvatar.name_tr || equippedAvatar.name) : equippedAvatar.name)}</span>
                      <span class="text-[10.5px] font-mono text-on-surface-variant">${esc(equippedAvatar.variant_id)}</span>
                    </div>
                  </div>
                  <button type="button" ${st.busy ? 'disabled' : ''} onclick="window.BlocTagSimpleMode.confirmEquipAvatar('')"
                    class="h-8 px-3 rounded-full bg-surface-container-highest text-on-surface text-[11px] font-semibold hover:bg-error/20 hover:text-error transition-colors cursor-pointer shrink-0">
                    ${isTr ? 'Kaldır (0.20 BCT)' : 'Remove (0.20 BCT)'}
                  </button>
                </div>
              ` : ''}

              ${ownedAvatars.length === 0 ? `
                <div class="py-10 text-center flex flex-col items-center gap-2 text-on-surface-variant">
                  <span class="material-symbols-outlined notranslate text-[36px] text-outline" translate="no">collections</span>
                  <p class="text-xs font-semibold text-on-surface">${isTr ? 'Henüz bir avatarınız yok' : 'No avatars owned yet'}</p>
                  <p class="text-[11px] max-w-xs">${isTr ? 'Hayvanlar sekmesinden 0.10 BCT açılış fiyatıyla kendi arka plan renginizde benzersiz bir ID oluşturabilirsiniz.' : 'Pick an animal and background color from the catalog starting at 0.10 BCT.'}</p>
                </div>
              ` : `
                <div class="grid grid-cols-2 gap-3">
                  ${ownedAvatars.map(av => {
                    const isEq = Boolean(equippedAvatar && equippedAvatar.variant_id === av.variant_id);
                    return `
                      <div class="p-3 rounded-2xl bg-surface-container-low border ${isEq ? 'border-primary ring-1 ring-primary/40' : 'border-outline-variant/15'} flex flex-col items-center gap-2">
                        <div class="w-16 h-16 rounded-full overflow-hidden ring-2 ring-surface shadow-md">
                          ${renderAvatarCircleHtml(av, '')}
                        </div>
                        <div class="text-center min-w-0 w-full">
                          <div class="text-xs font-bold text-on-surface truncate">${esc(isTr ? (av.name_tr || av.name) : av.name)}</div>
                          <div class="text-[10px] font-mono text-primary truncate">${esc(av.variant_id)}</div>
                          <div class="text-[9.5px] text-outline mt-0.5">${isTr ? 'Soulbound • Kişiye Özel' : 'Soulbound • Non-transferable'}</div>
                        </div>
                        ${isEq ? `
                          <button type="button" ${st.busy ? 'disabled' : ''} onclick="window.BlocTagSimpleMode.confirmEquipAvatar('')"
                            class="w-full h-8 rounded-full bg-surface-container-highest text-on-surface text-[11px] font-semibold hover:bg-error/20 hover:text-error transition-colors cursor-pointer">
                            ${isTr ? 'Kaldır (0.20 BCT)' : 'Unequip (0.20 BCT)'}
                          </button>
                        ` : `
                          <button type="button" ${st.busy ? 'disabled' : ''} onclick="window.BlocTagSimpleMode.confirmEquipAvatar('${escAttr(av.variant_id)}')"
                            class="w-full h-8 rounded-full bg-primary text-on-primary text-[11px] font-semibold hover:brightness-95 transition-all cursor-pointer">
                            ${equippedAvatar
                              ? (isTr ? 'Değiştir (0.40 BCT)' : 'Swap (0.40 BCT)')
                              : (isTr ? 'Profile Tak (0.20 BCT)' : 'Equip (0.20 BCT)')}
                          </button>
                        `}
                      </div>
                    `;
                  }).join('')}
                </div>
              `}
            ` : `
              <!-- LIVE CUSTOMIZER PREVIEW CARD -->
              ${selectedItem ? `
                <div class="p-4 rounded-2xl bg-surface-container-low border border-outline-variant/20 space-y-3.5">
                  <div class="flex items-center gap-4">
                    <!-- Live Circular Preview -->
                    <div class="w-24 h-24 rounded-full overflow-hidden shrink-0 shadow-xl ring-4 ring-surface" style="background-color:${st.selectedColor};">
                      <img src="${selectedItem.image_url}" alt="${esc(selectedItem.name)}" class="w-full h-full object-contain p-1 select-none pointer-events-none" />
                    </div>
                    <div class="flex-1 min-w-0 space-y-1">
                      <div class="flex items-center gap-1.5 flex-wrap">
                        <span class="text-base font-bold text-on-surface">${esc(isTr ? selectedItem.name_tr : selectedItem.name)}</span>
                        <span class="px-2 py-0.5 rounded-full bg-surface-container text-[10px] font-mono text-on-surface-variant">${esc(selectedItem.base_id)}</span>
                      </div>
                      <div class="flex items-center gap-1.5">
                        <span class="text-[10.5px] font-mono font-bold text-primary bg-primary/10 px-2 py-0.5 rounded-md">ID: ${esc(liveVariantId)}</span>
                      </div>
                      <div class="text-[11px] ${mintCount === 0 ? 'text-primary' : 'text-amber-400'} font-medium">
                        ${st.loadingQuote ? (isTr ? 'Fiyat hesaplanıyor...' : 'Calculating live price...') : (
                          mintCount === 0
                            ? (isTr ? '✨ Yeni renk ID! Açılış fiyatı: 0.10 BCT' : '✨ Fresh Variant ID! Opens at 0.10 BCT')
                            : (isTr
                                ? `🔥 ${mintCount} kez alındı (+%25) • Renk değiştirerek 0.10 BCT ile yeni ID açabilirsin!`
                                : `🔥 ${mintCount} minted (+25% curve) • Pick another color for a fresh 0.10 BCT ID!`)
                        )}
                      </div>
                    </div>
                  </div>

                  <!-- Background Color Selector -->
                  <div class="space-y-2">
                    <div class="flex items-center justify-between">
                      <span class="text-[11px] font-semibold text-on-surface-variant">${isTr ? 'Arka Plan Rengi (Yeni ID & Fiyat)' : 'Background Color (Creates Unique ID)'}</span>
                      <span class="text-[10.5px] font-mono text-primary">${st.selectedColor}</span>
                    </div>
                    <div class="flex items-center gap-2 flex-wrap">
                      ${curatedColors.map(c => {
                        const active = c.hex.toUpperCase() === st.selectedColor;
                        return `
                          <button type="button" title="${esc(isTr ? (c.name_tr || c.name) : c.name)} (${c.hex})"
                            onclick="window.BlocTagSimpleMode.selectAvatarColor('${c.hex}')"
                            class="w-7 h-7 rounded-full cursor-pointer transition-transform ${active ? 'scale-115 ring-2 ring-primary ring-offset-2 ring-offset-surface-container-low' : 'ring-1 ring-outline-variant/40 hover:scale-105'}"
                            style="background-color:${c.hex};"></button>
                        `;
                      }).join('')}
                      <!-- Custom Any-Color Picker -->
                      <label title="${isTr ? 'Özel Renk Seç' : 'Pick Custom Hex Color'}"
                        class="w-7 h-7 rounded-full bg-gradient-to-tr from-rose-500 via-amber-400 to-emerald-400 flex items-center justify-center cursor-pointer ring-1 ring-outline-variant/40 hover:scale-105 transition-transform relative overflow-hidden">
                        <span class="material-symbols-outlined notranslate text-[14px] text-white drop-shadow" translate="no">colorize</span>
                        <input type="color" value="${st.selectedColor}"
                          onchange="window.BlocTagSimpleMode.selectAvatarColor(this.value)"
                          class="absolute inset-0 opacity-0 cursor-pointer w-full h-full" />
                      </label>
                    </div>
                  </div>

                  <!-- Tokenomics & Soulbound Info -->
                  <div class="px-3 py-2 rounded-xl bg-surface-container text-[10.5px] text-on-surface-variant flex flex-col gap-1">
                    <div class="flex items-center justify-between">
                      <span>${isTr ? 'Dağıtım:' : 'Revenue Split:'}</span>
                      <span class="font-mono text-on-surface">${isTr ? '%30 Hazine • %70 Miner/Node/Stake' : '30% Treasury • 70% Miner/Nodes/Stakers'}</span>
                    </div>
                    <div class="flex items-center justify-between">
                      <span>${isTr ? 'Sonraki Alım Fiyatı (+%25):' : 'Next Mint Price (+25%):'}</span>
                      <span class="font-mono text-amber-400">${nextPriceDisplay} BCT</span>
                    </div>
                    <div class="flex items-center justify-between">
                      <span>${isTr ? 'Takma / Çıkarma (On-Chain):' : 'Equip / Remove (On-Chain):'}</span>
                      <span class="font-mono text-on-surface">${isTr ? '0.20 BCT (Değişim: 0.40 BCT)' : '0.20 BCT (Swap: 0.40 BCT)'}</span>
                    </div>
                  </div>

                  <!-- Primary Action CTA -->
                  ${isEquipped ? `
                    <button type="button" ${st.busy ? 'disabled' : ''} onclick="window.BlocTagSimpleMode.confirmEquipAvatar('')"
                      class="w-full h-11 rounded-full bg-surface-container-highest text-on-surface text-xs font-bold flex items-center justify-center gap-1.5 hover:bg-error/20 hover:text-error transition-all cursor-pointer">
                      <span class="material-symbols-outlined notranslate text-[17px]" translate="no">hide_image</span>
                      <span>${st.busy ? (isTr ? 'İşleniyor...' : 'Processing...') : (isTr ? 'Profilde Takılı — Kaldır (0.20 BCT)' : 'Equipped — Remove (0.20 BCT)')}</span>
                    </button>
                  ` : (alreadyOwned ? `
                    <button type="button" ${st.busy ? 'disabled' : ''} onclick="window.BlocTagSimpleMode.confirmEquipAvatar('${escAttr(liveVariantId)}')"
                      class="w-full h-11 rounded-full bg-primary text-on-primary text-xs font-bold flex items-center justify-center gap-1.5 shadow-md hover:brightness-95 transition-all cursor-pointer">
                      <span class="material-symbols-outlined notranslate text-[17px]" translate="no">check_circle</span>
                      <span>${st.busy ? (isTr ? 'İşleniyor...' : 'Processing...') : (equippedAvatar
                        ? (isTr ? 'Sende Var — Fotoğrafı Değiştir (0.40 BCT)' : 'Owned — Change Photo (0.40 BCT)')
                        : (isTr ? 'Sende Var — Profile Tak (0.20 BCT)' : 'Owned — Equip to Profile (0.20 BCT)'))}</span>
                    </button>
                  ` : `
                    <button type="button" ${(st.busy || st.loadingQuote) ? 'disabled' : ''} onclick="window.BlocTagSimpleMode.mintSelectedAvatar()"
                      class="w-full h-11 rounded-full bg-primary text-on-primary text-xs font-bold flex items-center justify-center gap-1.5 shadow-md hover:brightness-95 active:scale-[0.99] transition-all cursor-pointer disabled:opacity-60">
                      <span class="material-symbols-outlined notranslate text-[17px]" translate="no">verified</span>
                      <span>${st.busy ? (isTr ? 'İmzalanıyor & Alınıyor...' : 'Signing & Minting...') : (isTr ? `Satın Al ve Profile Tak (${priceDisplay} BCT)` : `Mint & Equip (${priceDisplay} BCT)`)}</span>
                    </button>
                  `)}
                </div>
              ` : ''}

              <!-- ANIMAL COLLECTION GRID -->
              <div>
                <div class="flex items-center justify-between mb-2">
                  <span class="text-xs font-bold text-on-surface">${isTr ? 'Hayvan Seç' : 'Select Animal'}</span>
                  <span class="text-[10.5px] text-outline">${isTr ? 'Her hayvanın özel default ID’si vardır' : 'Each animal has a unique base ID'}</span>
                </div>
                <div class="grid grid-cols-3 sm:grid-cols-4 gap-2.5">
                  ${catalogItems.map(item => {
                    const isSel = item.base_id === st.selectedBaseId;
                    const defP = Number(item.default_price || 0.10).toFixed(item.default_price === 0.1 ? 2 : 3);
                    return `
                      <button type="button" onclick="window.BlocTagSimpleMode.selectAvatarItem('${escAttr(item.base_id)}')"
                        class="p-2 rounded-2xl bg-surface-container-low border ${isSel ? 'border-primary ring-2 ring-primary/35 bg-primary/5' : 'border-outline-variant/15 hover:border-outline-variant/40'} flex flex-col items-center gap-1.5 transition-all cursor-pointer active:scale-95">
                        <div class="w-14 h-14 rounded-full overflow-hidden shadow-sm ring-1 ring-outline-variant/20" style="background-color:${isSel ? st.selectedColor : '#FFFFFF'};">
                          <img src="${item.image_url}" alt="${esc(item.name)}" class="w-full h-full object-contain p-0.5 select-none pointer-events-none" loading="lazy" />
                        </div>
                        <span class="text-[11px] font-semibold text-on-surface truncate w-full text-center">${esc(isTr ? item.name_tr : item.name)}</span>
                        <span class="text-[9.5px] font-mono text-outline">${esc(item.base_id)} • ${defP}</span>
                      </button>
                    `;
                  }).join('')}
                </div>
              </div>
            `)}
          </div>
        </div>
      `;
    },

    insertModalComposerTag: (tag) => {
      const inp = document.getElementById('simple-modal-composer-input');
      if (!inp) return;
      inp.value = (inp.value ? inp.value + ' ' : '') + tag;
      inp.focus();
    },

    submitModalPost: async () => {
      const acc = getActiveWallet();
      if (!acc) {
        window.BlocTagSimpleMode.closeComposerModal();
        navigateToSimpleScreen('SCR-ONB-01');
        return;
      }
      const inp = document.getElementById('simple-modal-composer-input');
      const text = String(inp ? inp.value : '').trim();
      if (!text) {
        if (inp) inp.focus();
        return;
      }
      const proInput = document.getElementById('spacePostInput');
      if (proInput && typeof window.publishSpacePost === 'function') {
        proInput.value = text;
        if (typeof window.updateSpaceCharCount === 'function') window.updateSpaceCharCount();
        window.BlocTagSimpleMode.closeComposerModal();
        await window.publishSpacePost();
        renderSimpleMode();
      }
    },

    insertComposerTag: (tag) => {
      const inp = document.getElementById('simple-composer-input');
      if (!inp) return;
      inp.value = (inp.value ? inp.value + ' ' : '') + tag;
      inp.focus();
    },

    submitPost: async () => {
      const acc = getActiveWallet();
      if (!acc) {
        navigateToSimpleScreen('SCR-ONB-01');
        return;
      }
      const inp = document.getElementById('simple-composer-input');
      const text = String(inp ? inp.value : '').trim();
      if (!text) {
        if (inp) inp.focus();
        return;
      }
      const proInput = document.getElementById('spacePostInput');
      if (proInput && typeof window.publishSpacePost === 'function') {
        proInput.value = text;
        if (typeof window.updateSpaceCharCount === 'function') window.updateSpaceCharCount();
        await window.publishSpacePost();
        renderSimpleMode();
      }
    },

    likePost: async (postId, ev) => {
      if (ev) ev.stopPropagation();
      const acc = getActiveWallet();
      if (!acc) {
        navigateToSimpleScreen('SCR-ONB-01');
        return;
      }
      if (typeof window.likeSpacePost === 'function') {
        await window.likeSpacePost(postId, ev);
        renderSimpleMode();
      }
    },

    submitComment: async (postId) => {
      const acc = getActiveWallet();
      if (!acc) {
        navigateToSimpleScreen('SCR-ONB-01');
        return;
      }
      const inp = document.getElementById('simple-comment-input');
      const text = String(inp ? inp.value : '').trim();
      if (!text) return;
      try {
        activeDetailPostId = postId;
      } catch (_e) { }
      const proCommentInput = document.getElementById('detailCommentInput');
      if (proCommentInput && typeof window.submitDetailSpaceComment === 'function') {
        proCommentInput.value = text;
        await window.submitDetailSpaceComment();
        renderSimpleMode();
      }
    },

    tipAuthor: (authorAddress) => {
      if (!authorAddress) return;
      const acc = getActiveWallet();
      if (!acc) {
        navigateToSimpleScreen('SCR-ONB-01');
        return;
      }
      if (acc.address && acc.address.toLowerCase() === String(authorAddress).toLowerCase()) {
        if (typeof window.showToast === 'function') window.showToast(t('tip_self_error', 'You cannot tip your own post'), 'warning', true);
        return;
      }
      navigateToSimpleScreen('SCR-WLT-SEND', {
        recipient: authorAddress,
        amount: '0.25'
      });
      if (typeof window.showToast === 'function') {
        window.showToast(t('tip_ready_toast', 'Tip recipient prepared (0.25 BCT)'), 'volunteer_activism');
      }
    },

    setProfileTab: (tab) => {
      simpleState.profileTab = tab;
      renderSimpleMode();
    },

    openDetailedProProfile: (target) => {
      applySimpleModeState(false, true);
      toggleSimpleModeSetting(false);
      setTimeout(() => {
        if (typeof window.openUserProfile === 'function') {
          window.openUserProfile(target);
        } else if (typeof window.openMyUserProfile === 'function') {
          window.openMyUserProfile();
        }
      }, 80);
    },

    setPrimaryHandle: async (cleanName) => {
      if (!cleanName) return;
      try {
        try {
          localStorage.setItem('locktrace_primary_bns', cleanName);
        } catch (_e) { }
        if (typeof currentBnsHandle !== 'undefined') {
          currentBnsHandle = cleanName;
        }
        const acc = getActiveWallet();
        if (acc) {
          acc.bns_name = cleanName;
        }
        if (typeof window.setPrimaryBnsHandle === 'function') {
          await window.setPrimaryBnsHandle(cleanName);
        } else if (typeof window.apiFetch === 'function') {
          if (acc && acc.address) {
            await window.apiFetch('/bns/set-primary', {
              method: 'POST',
              body: JSON.stringify({ name: cleanName, owner: acc.address })
            });
          }
        }
        if (typeof window.fetchAndSyncMyBnsHandles === 'function') {
          await window.fetchAndSyncMyBnsHandles();
        }
        renderSimpleMode(false);
        if (typeof window.showToast === 'function') {
          window.showToast(`⭐ '@${cleanName}' ${t('bns_set_primary_toast', 'set as active identity!')}`, 'verified');
        }
      } catch (err) {
        console.error('setPrimaryHandle error:', err);
        renderSimpleMode(false);
        if (typeof window.showToast === 'function') {
          window.showToast(`⭐ '@${cleanName}' ${t('bns_selected_toast', 'selected as active identity')}`, 'info');
        }
      }
    },

    followProfileAuthor: async (targetAddress, bnsName, btnEl) => {
      if (!targetAddress) return;
      const btn = btnEl || (window.event && window.event.currentTarget) || document.getElementById('simple-profile-follow-btn') || document.createElement('button');
      if (typeof window.followVoiceOnChain === 'function') {
        await window.followVoiceOnChain(btn, targetAddress, bnsName);
        delete _simpleProfileCache[targetAddress.toLowerCase()];
        if (bnsName) delete _simpleProfileCache[String(bnsName).toLowerCase().replace(/^@/, '')];
        const acc = getActiveWallet();
        if (acc) delete _simpleProfileCache[acc.address.toLowerCase()];
        fetchSimpleProfile(targetAddress);
        if (acc) fetchSimpleProfile(acc.address);
        renderSimpleMode(false);
      } else {
        if (typeof window.showToast === 'function') {
          window.showToast(t('follow_loading_toast', 'Follow service loading...'), 'info');
        }
      }
    },

    openFollowersList: (addr, type) => {
      const target = addr || (getActiveWallet() ? getActiveWallet().address : '');
      simpleState.followTargetAddr = target;
      simpleState.profileTarget = target;
      simpleState.followTab = (type === 'following') ? 'following' : 'followers';
      simpleState.followFilter = 'all';
      simpleState.followSearch = '';
      _lastRenderedFingerprint = '';
      navigateToSimpleScreen('SCR-PRF-FOLLOW', { profileTarget: target, followTargetAddr: target, followTab: simpleState.followTab });
    },

    setFollowTab: (tab) => {
      simpleState.followTab = (tab === 'following') ? 'following' : 'followers';
      simpleState.followSearch = '';
      _lastRenderedFingerprint = '';
      renderSimpleMode(true);
    },

    setFollowFilter: (f) => {
      simpleState.followFilter = f || 'all';
      _lastRenderedFingerprint = '';
      renderSimpleMode(true);
    },

    onFollowSearchInput: (val) => {
      simpleState.followSearch = val || '';
      renderSimpleMode(false);
    },

    clearFollowSearch: () => {
      simpleState.followSearch = '';
      _lastRenderedFingerprint = '';
      renderSimpleMode(true);
    },

    setNotifFilter: (f) => {
      simpleState.notifFilter = f;
      renderSimpleMode();
    },

    markAllNotifsRead: () => {
      if (typeof window.markAllNotificationsRead === 'function') {
        window.markAllNotificationsRead();
      }
      renderSimpleMode();
    },

    openLanguageModal: () => openSimpleLanguageModal(),
    closeLanguageModal: () => closeSimpleLanguageModal(),
    selectLanguage: (code) => setLanguagePreference(code),
    selectWeb3Experience: (choice) => handleSelectWeb3Experience(choice),
    setGateLanguage: (langCode) => handleSetGateLanguage(langCode),
    triggerMandatoryPwaInstall: () => handleTriggerMandatoryPwaInstall(),
    openIosInstallSheet: () => handleToggleIosInstallSheet(true),
    closeIosInstallSheet: () => handleToggleIosInstallSheet(false),
    copySiteLinkForSafari: () => handleCopySiteLinkForSafari(),
    markManualPwaInstalled: () => handleMarkManualPwaInstalled(),
    showPwaInstallStepsAgain: () => handleShowPwaInstallStepsAgain(),
    openInstalledAppHint: (ev) => handleOpenInstalledAppHint(ev)
  };

  // Global helper fallback
  window.openLanguageModal = () => openSimpleLanguageModal();

  // ==========================================================================
  // 6. MOBILE FIRST-VISIT WEB3 ONBOARDING & MANDATORY PWA INSTALL GATE
  //    (Mobile Only — Default English for Native Browser Translator Support)
  // ==========================================================================
  const GATE_I18N = {
    en: {
      welcomeBadge: 'BlocTag • Welcome',
      web3TitlePre: 'Do you know what ',
      web3TitleHighlight: 'Web3 is?',
      web3Sub: 'Choose the interface that fits you best. You can switch between <strong class="text-on-surface">Simple</strong> and <strong class="text-on-surface">Pro</strong> mode anytime from the menu.',
      simpleTitle: 'No, Keep It Simple',
      simpleBadge: 'Simple Mode',
      simpleDesc: 'No complex jargon. Start with an easy wallet, fast transfers, and a clean Space feed.',
      proTitle: 'Yes, I Know Web3',
      proBadge: 'Pro Mode',
      proDesc: 'Continue with Block Explorer, Node Panel, Bridge, BNS, and all advanced protocol tools.',
      nonCustodialFooter: '100% Non-Custodial • Keys Stay Only on Your Device',
      pwaBadge: 'Mobile App Installation Required',
      pwaTitlePre: 'Add BlocTag App to ',
      pwaTitleHighlight: 'Home Screen',
      pwaSub: 'For fullscreen performance, instant notifications, and secure local non-custodial storage on mobile, please install the BlocTag app.',
      chipVault: 'Secure Vault',
      chipSpeed: 'Instant Speed',
      chipFull: 'Fullscreen',
      iosInAppTitle: 'Open in Safari Browser',
      iosInAppDesc: 'On iPhone, in-app browsers (Instagram, WhatsApp, Telegram) cannot add apps to the Home Screen. Copy the link and open it in <strong class="text-on-surface">Safari</strong>.',
      iosInAppBtn: 'Copy Link & Open in Safari',
      iosCta: 'Add App to Home Screen',
      iosAlready: 'Already Added to Home Screen',
      iosSheetTitle: 'Add to Home Screen',
      iosStep1Chrome: 'Tap the <strong class="text-primary">Share</strong> icon in the <strong>top right</strong> corner of Chrome.',
      iosStep1Safari: 'Tap the <strong class="text-primary">Share</strong> icon at the <strong>bottom center</strong> of Safari.',
      iosStep2: 'Scroll down and tap <strong class="text-primary">"Add to Home Screen"</strong> → then tap <strong class="text-primary">"Add"</strong>.',
      iosAddedBtn: 'I Added It to Home Screen',
      iosPointerSafari: 'Safari Share (↑) icon is right below',
      iosPointerChrome: 'Chrome Share (↑) icon is at top right',
      androidStarting: 'Starting Auto-Install...',
      androidReadyCta: 'Install & Add to Home Screen',
      androidAutoCta: 'Install BlocTag App Automatically',
      androidManualTitle: 'Browser Does Not Support Auto-Prompt',
      androidManualDesc: 'Tap <strong class="text-on-surface">Menu (⋮)</strong> in the top right corner and select <strong class="text-primary">"Install App"</strong> or <strong class="text-primary">"Add to Home screen"</strong>.',
      androidManualDone: 'I Installed the App',
      androidHint: 'Tap the button to open your device install prompt; confirm to add <strong class="text-on-surface">BlocTag</strong> directly to your home screen.',
      doneBadge: 'Installation Complete',
      doneTitlePre: 'You Can ',
      doneTitleHighlight: 'Open the App!',
      doneSub: '<strong class="text-on-surface">BlocTag</strong> has been added to your home screen. You are still in your mobile browser — close it and tap the <strong class="text-primary">BlocTag</strong> icon on your home screen.',
      doneCardTitle: 'BlocTag App Ready',
      doneCardSub: 'Launch the app from your home screen',
      doneOpenBtn: 'Open App',
      doneRetryBtn: "Didn't appear on home screen? Install again",
      browserTranslateHint: 'Use your browser Translate menu (⋮ → Translate or aA → Translate) for any language.'
    },
    tr: {
      welcomeBadge: 'BlocTag • Hoş Geldiniz',
      web3TitlePre: 'Web3 nedir, ',
      web3TitleHighlight: 'biliyor musun?',
      web3Sub: 'Deneyimine en uygun arayüzü seç. Dilediğin zaman menüden <strong class="text-on-surface">Simple</strong> ve <strong class="text-on-surface">Pro</strong> modları arasında geçiş yapabilirsin.',
      simpleTitle: 'Hayır, Sade Olsun',
      simpleBadge: 'Simple Mod',
      simpleDesc: 'Karmaşık teknik terimler yok. Hızlı cüzdan, kolay transfer ve sade Space akışı ile başla.',
      proTitle: "Evet, Web3'ü Biliyorum",
      proBadge: 'Pro Mod',
      proDesc: 'Blok Explorer, Node Paneli, Köprü (Bridge), BNS ve tüm gelişmiş protokol araçlarıyla devam et.',
      nonCustodialFooter: '%100 Non-Custodial • Anahtarlar Yalnızca Cihazınızda',
      pwaBadge: 'Mobil Uygulama Kurulumu Zorunludur',
      pwaTitlePre: 'BlocTag Uygulamasını ',
      pwaTitleHighlight: 'Ana Ekrana Ekle',
      pwaSub: 'Mobil cihazlarda tam ekran performans, anlık bildirimler ve güvenli yerel kasa deneyimi için BlocTag PWA uygulamasını cihazınıza indirmeniz gerekmektedir.',
      chipVault: 'Güvenli Kasa',
      chipSpeed: 'Anlık Hız',
      chipFull: 'Tam Ekran',
      iosInAppTitle: 'Safari Tarayıcısında Açın',
      iosInAppDesc: "iPhone'da uygulama içi tarayıcılardan (Instagram, WhatsApp, Telegram) ana ekrana ekleme yapılamaz. Linki kopyalayıp <strong class=\"text-on-surface\">Safari</strong>'de açın.",
      iosInAppBtn: "Linki Kopyala ve Safari'de Aç",
      iosCta: 'Uygulamayı Ana Ekrana Ekle',
      iosAlready: 'Zaten Ana Ekrana Ekledim',
      iosSheetTitle: 'Ana Ekrana Ekle',
      iosStep1Chrome: 'Sağ üst çubuktaki <strong class="text-primary">Paylaş</strong> simgesine dokunun.',
      iosStep1Safari: 'Ekranın <strong>en alt ortasındaki</strong> <strong class="text-primary">Paylaş</strong> simgesine dokunun.',
      iosStep2: 'Listede <strong class="text-primary">"Ana Ekrana Ekle"</strong> → sağ üstten <strong class="text-primary">"Ekle"</strong> butonuna basın.',
      iosAddedBtn: 'Ana Ekrana Ekledim',
      iosPointerSafari: 'Safari Paylaş (↑) simgesi tam burada',
      iosPointerChrome: 'Chrome Paylaş (↑) simgesi sağ üstte',
      androidStarting: 'Otomatik Kurulum Başlatılıyor...',
      androidReadyCta: 'Uygulamayı İndir & Ana Ekrana Ekle',
      androidAutoCta: 'BlocTag Uygulamasını Otomatik İndir',
      androidManualTitle: 'Tarayıcı Otomatik Onayı Desteklemiyor',
      androidManualDesc: 'Sağ üst köşedeki <strong class="text-on-surface">Menü (⋮)</strong> → <strong class="text-primary">"Uygulamayı Yükle"</strong> veya <strong class="text-primary">"Ana ekrana ekle"</strong> seçeneğine dokunun.',
      androidManualDone: 'Uygulamayı Yükledim',
      androidHint: 'Butona bastığınızda cihazınızda kurulum onayı otomatik açılır; onayladığınızda <strong class="text-on-surface">BlocTag</strong> ana ekranınıza eklenir.',
      doneBadge: 'Kurulum Tamamlandı',
      doneTitlePre: 'Uygulamayı ',
      doneTitleHighlight: 'Açabilirsiniz!',
      doneSub: '<strong class="text-on-surface">BlocTag</strong> ana ekranınıza eklendi. Şu anda hâlâ mobil tarayıcı üzerindesiniz — tarayıcıyı kapatıp telefonunuzun ana ekranındaki <strong class="text-primary">BlocTag</strong> simgesine dokunun.',
      doneCardTitle: 'BlocTag Uygulaması Hazır',
      doneCardSub: 'Ana ekranınızdan uygulamayı başlatın',
      doneOpenBtn: 'Uygulamayı Aç',
      doneRetryBtn: 'Uygulama ekrana düşmediyse tekrar yükle',
      browserTranslateHint: 'Tarayıcınızın Çeviri eklentisi (⋮ → Çevir) ile tüm dilleri kullanabilirsiniz.'
    },
    az: {
      welcomeBadge: 'BlocTag • Xoş Gəldiniz',
      web3TitlePre: 'Web3 nədir, ',
      web3TitleHighlight: 'bilirsinizmi?',
      web3Sub: 'Sizə ən uyğun interfeysi seçin. İstədiyiniz zaman menyudan <strong class="text-on-surface">Simple</strong> və <strong class="text-on-surface">Pro</strong> rejimi dəyişə bilərsiniz.',
      simpleTitle: 'Xeyr, Sadə Olsun',
      simpleBadge: 'Simple Rejim',
      simpleDesc: 'Mürəkkəb terminlər yoxdur. Asan cüzdan, sürətli köçürmə və sadə Space axını ilə başlayın.',
      proTitle: 'Bəli, Web3-ü Bilirəm',
      proBadge: 'Pro Rejim',
      proDesc: 'Blok Explorer, Node Paneli, Körpü (Bridge), BNS və bütün protokol alətləri ilə davam edin.',
      nonCustodialFooter: '100% Non-Custodial • Açarlar Yalnız Cihazınızda Saxlanır',
      pwaBadge: 'Mobil Tətbiq Quraşdırılması Məcburidir',
      pwaTitlePre: 'BlocTag Tətbiqini ',
      pwaTitleHighlight: 'Ana Ekrana Əlavə Et',
      pwaSub: 'Mobil cihazlarda tam ekran performans, ani bildirişlər və təhlükəsiz yerli saxlama üçün BlocTag tətbiqini quraşdırın.',
      chipVault: 'Təhlükəsiz Kassa',
      chipSpeed: 'Ani Sürət',
      chipFull: 'Tam Ekran',
      iosInAppTitle: 'Safari Brauzerində Açın',
      iosInAppDesc: 'iPhone-da tətbiqdaxili brauzerlərdən ana ekrana əlavə etmək olmur. Linki kopyalayıb <strong class="text-on-surface">Safari</strong>-də açın.',
      iosInAppBtn: 'Linki Kopyala və Safari-də Aç',
      iosCta: 'Tətbiqi Ana Ekrana Əlavə Et',
      iosAlready: 'Artıq Ana Ekrana Əlavə Etdim',
      iosSheetTitle: 'Ana Ekrana Əlavə Et',
      iosStep1Chrome: 'Sağ yuxarıdakı <strong class="text-primary">Paylaş</strong> işarəsinə toxunun.',
      iosStep1Safari: 'Ekranın <strong>aşağı ortasındakı</strong> <strong class="text-primary">Paylaş</strong> işarəsinə toxunun.',
      iosStep2: 'Siyahıda <strong class="text-primary">"Ana Ekrana Əlavə Et"</strong> → <strong class="text-primary">"Əlavə Et"</strong> seçin.',
      iosAddedBtn: 'Ana Ekrana Əlavə Etdim',
      iosPointerSafari: 'Safari Paylaş (↑) işarəsi aşağıdadır',
      iosPointerChrome: 'Chrome Paylaş (↑) işarəsi sağ yuxarıdadır',
      androidStarting: 'Avtomatik Quraşdırma Başladılır...',
      androidReadyCta: 'Tətbiqi Yüklə & Ana Ekrana Əlavə Et',
      androidAutoCta: 'BlocTag Tətbiqini Avtomatik Yüklə',
      androidManualTitle: 'Brauzer Avtomatik Quraşdırmanı Dəstəkləmir',
      androidManualDesc: 'Sağ yuxarıdakı <strong class="text-on-surface">Menyu (⋮)</strong> → <strong class="text-primary">"Tətbiqi Quraşdır"</strong> seçin.',
      androidManualDone: 'Tətbiqi Quraşdırdım',
      androidHint: 'Düyməyə basdıqda cihazınızda quraşdırma təsdiqi açılacaq; təsdiqlədikdə <strong class="text-on-surface">BlocTag</strong> ana ekranınıza düşəcək.',
      doneBadge: 'Quraşdırma Tamamlandı',
      doneTitlePre: 'Tətbiqi ',
      doneTitleHighlight: 'Aça Bilərsiniz!',
      doneSub: '<strong class="text-on-surface">BlocTag</strong> ana ekranınıza əlavə edildi. Brauzeri bağlayıb ana ekrandakı <strong class="text-primary">BlocTag</strong> ikonuna toxunun.',
      doneCardTitle: 'BlocTag Tətbiqi Hazırdır',
      doneCardSub: 'Ana ekranınızdan tətbiqi açın',
      doneOpenBtn: 'Tətbiqi Aç',
      doneRetryBtn: 'Ekrana düşmədisə yenidən yüklə',
      browserTranslateHint: 'İstənilən dil üçün brauzerinizin tərcümə menyusundan istifadə edə bilərsiniz.'
    },
    ru: {
      welcomeBadge: 'BlocTag • Добро пожаловать',
      web3TitlePre: 'Вы знаете, что такое ',
      web3TitleHighlight: 'Web3?',
      web3Sub: 'Выберите удобный режим. Вы всегда сможете переключиться между <strong class="text-on-surface">Simple</strong> и <strong class="text-on-surface">Pro</strong> в меню.',
      simpleTitle: 'Нет, мне нужен простой режим',
      simpleBadge: 'Simple Mode',
      simpleDesc: 'Без сложных терминов. Простой кошелёк, быстрые переводы и чистая лента Space.',
      proTitle: 'Да, я знаю Web3',
      proBadge: 'Pro Mode',
      proDesc: 'Block Explorer, панель узла, мост (Bridge), BNS и все инструменты протокола.',
      nonCustodialFooter: '100% Non-Custodial • Ключи хранятся только на вашем устройстве',
      pwaBadge: 'Требуется установка приложения',
      pwaTitlePre: 'Добавьте BlocTag на ',
      pwaTitleHighlight: 'главный экран',
      pwaSub: 'Для полноэкранного режима, уведомлений и безопасного локального хранилища установите приложение BlocTag.',
      chipVault: 'Безопасный сейф',
      chipSpeed: 'Мгновенно',
      chipFull: 'Полный экран',
      iosInAppTitle: 'Откройте в Safari',
      iosInAppDesc: 'Встроенные браузеры на iPhone не поддерживают установку. Скопируйте ссылку и откройте её в <strong class="text-on-surface">Safari</strong>.',
      iosInAppBtn: 'Скопировать ссылку для Safari',
      iosCta: 'Добавить на экран «Домой»',
      iosAlready: 'Уже добавлено на экран',
      iosSheetTitle: 'На экран «Домой»',
      iosStep1Chrome: 'Нажмите <strong class="text-primary">Поделиться</strong> в <strong>правом верхнем</strong> углу Chrome.',
      iosStep1Safari: 'Нажмите <strong class="text-primary">Поделиться</strong> в <strong>нижней части</strong> Safari.',
      iosStep2: 'Выберите <strong class="text-primary">«На экран Домой»</strong> → <strong class="text-primary">«Добавить»</strong>.',
      iosAddedBtn: 'Я добавил на экран',
      iosPointerSafari: 'Кнопка «Поделиться» (↑) внизу',
      iosPointerChrome: 'Кнопка «Поделиться» (↑) вверху справа',
      androidStarting: 'Запуск установки...',
      androidReadyCta: 'Установить на главный экран',
      androidAutoCta: 'Установить BlocTag автоматически',
      androidManualTitle: 'Браузер не поддерживает автоустановку',
      androidManualDesc: 'Нажмите <strong class="text-on-surface">Меню (⋮)</strong> → <strong class="text-primary">«Установить приложение»</strong>.',
      androidManualDone: 'Приложение установлено',
      androidHint: 'Нажмите кнопку, чтобы открыть системное окно установки <strong class="text-on-surface">BlocTag</strong>.',
      doneBadge: 'Установка завершена',
      doneTitlePre: 'Можно ',
      doneTitleHighlight: 'открыть приложение!',
      doneSub: '<strong class="text-on-surface">BlocTag</strong> добавлен на главный экран. Закройте браузер и откройте иконку <strong class="text-primary">BlocTag</strong>.',
      doneCardTitle: 'BlocTag готов к работе',
      doneCardSub: 'Запустите приложение с главного экрана',
      doneOpenBtn: 'Открыть приложение',
      doneRetryBtn: 'Не появилось на экране? Установить снова',
      browserTranslateHint: 'Вы можете использовать встроенный переводчик браузера для любого языка.'
    },
    de: {
      welcomeBadge: 'BlocTag • Willkommen',
      web3TitlePre: 'Weißt du, was ',
      web3TitleHighlight: 'Web3 ist?',
      web3Sub: 'Wähle die passende Ansicht. Du kannst jederzeit im Menü zwischen <strong class="text-on-surface">Simple</strong> und <strong class="text-on-surface">Pro</strong> wechseln.',
      simpleTitle: 'Nein, bitte einfach',
      simpleBadge: 'Simple Mode',
      simpleDesc: 'Keine Fachbegriffe. Starte mit einfacher Wallet, schnellen Transfers und Space.',
      proTitle: 'Ja, ich kenne Web3',
      proBadge: 'Pro Mode',
      proDesc: 'Block Explorer, Node-Panel, Bridge, BNS und alle Protokoll-Tools.',
      nonCustodialFooter: '100% Non-Custodial • Schlüssel bleiben nur auf deinem Gerät',
      pwaBadge: 'App-Installation erforderlich',
      pwaTitlePre: 'BlocTag App zum ',
      pwaTitleHighlight: 'Startbildschirm hinzufügen',
      pwaSub: 'Für Vollbild, Benachrichtigungen und sicheren lokalen Speicher installiere bitte die BlocTag App.',
      chipVault: 'Sicherer Tresor',
      chipSpeed: 'Sofort schnell',
      chipFull: 'Vollbild',
      iosInAppTitle: 'In Safari öffnen',
      iosInAppDesc: 'In-App-Browser auf dem iPhone unterstützen keine Installation. Kopiere den Link und öffne ihn in <strong class="text-on-surface">Safari</strong>.',
      iosInAppBtn: 'Link kopieren & in Safari öffnen',
      iosCta: 'Zum Home-Bildschirm hinzufügen',
      iosAlready: 'Bereits hinzugefügt',
      iosSheetTitle: 'Zum Home-Bildschirm',
      iosStep1Chrome: 'Tippe oben rechts auf das <strong class="text-primary">Teilen</strong>-Symbol.',
      iosStep1Safari: 'Tippe unten in der Mitte auf das <strong class="text-primary">Teilen</strong>-Symbol.',
      iosStep2: 'Wähle <strong class="text-primary">„Zum Home-Bildschirm“</strong> → <strong class="text-primary">„Hinzufügen“</strong>.',
      iosAddedBtn: 'Ich habe es hinzugefügt',
      iosPointerSafari: 'Safari Teilen-Symbol (↑) unten',
      iosPointerChrome: 'Chrome Teilen-Symbol (↑) oben rechts',
      androidStarting: 'Installation wird gestartet...',
      androidReadyCta: 'App installieren & hinzufügen',
      androidAutoCta: 'BlocTag App automatisch installieren',
      androidManualTitle: 'Auto-Installation nicht unterstützt',
      androidManualDesc: 'Tippe oben rechts auf <strong class="text-on-surface">Menü (⋮)</strong> → <strong class="text-primary">„App installieren“</strong>.',
      androidManualDone: 'App wurde installiert',
      androidHint: 'Tippe auf den Button und bestätige, um <strong class="text-on-surface">BlocTag</strong> hinzuzufügen.',
      doneBadge: 'Installation abgeschlossen',
      doneTitlePre: 'Du kannst die ',
      doneTitleHighlight: 'App öffnen!',
      doneSub: '<strong class="text-on-surface">BlocTag</strong> wurde hinzugefügt. Schließe den Browser und öffne das <strong class="text-primary">BlocTag</strong>-Symbol auf deinem Startbildschirm.',
      doneCardTitle: 'BlocTag App bereit',
      doneCardSub: 'Starte die App vom Startbildschirm',
      doneOpenBtn: 'App öffnen',
      doneRetryBtn: 'Nicht erschienen? Erneut installieren',
      browserTranslateHint: 'Nutze die Browser-Übersetzung für weitere Sprachen.'
    },
    es: {
      welcomeBadge: 'BlocTag • Bienvenido',
      web3TitlePre: '¿Sabes qué es ',
      web3TitleHighlight: 'Web3?',
      web3Sub: 'Elige tu modo ideal. Puedes cambiar entre <strong class="text-on-surface">Simple</strong> y <strong class="text-on-surface">Pro</strong> en cualquier momento.',
      simpleTitle: 'No, hazlo simple',
      simpleBadge: 'Modo Simple',
      simpleDesc: 'Sin términos complejos. Billetera fácil, envíos rápidos y Space limpio.',
      proTitle: 'Sí, conozco Web3',
      proBadge: 'Modo Pro',
      proDesc: 'Block Explorer, Panel de Nodo, Bridge, BNS y todas las herramientas.',
      nonCustodialFooter: '100% Non-Custodial • Tus llaves solo en tu dispositivo',
      pwaBadge: 'Instalación de App Obligatoria',
      pwaTitlePre: 'Añadir BlocTag a la ',
      pwaTitleHighlight: 'Pantalla de Inicio',
      pwaSub: 'Para pantalla completa, notificaciones y bóveda local segura, instala la aplicación BlocTag.',
      chipVault: 'Bóveda Segura',
      chipSpeed: 'Velocidad',
      chipFull: 'Pantalla Completa',
      iosInAppTitle: 'Abrir en Safari',
      iosInAppDesc: 'Los navegadores integrados en iPhone no permiten instalar. Copia el enlace y ábrelo en <strong class="text-on-surface">Safari</strong>.',
      iosInAppBtn: 'Copiar enlace y abrir en Safari',
      iosCta: 'Añadir a pantalla de inicio',
      iosAlready: 'Ya la añadí',
      iosSheetTitle: 'Añadir a inicio',
      iosStep1Chrome: 'Toca el icono <strong class="text-primary">Compartir</strong> arriba a la derecha.',
      iosStep1Safari: 'Toca el icono <strong class="text-primary">Compartir</strong> abajo en el centro de Safari.',
      iosStep2: 'Pulsa <strong class="text-primary">«Añadir a pantalla de inicio»</strong> → <strong class="text-primary">«Añadir»</strong>.',
      iosAddedBtn: 'Ya la añadí a inicio',
      iosPointerSafari: 'El icono Compartir (↑) está justo abajo',
      iosPointerChrome: 'El icono Compartir (↑) está arriba a la derecha',
      androidStarting: 'Iniciando instalación...',
      androidReadyCta: 'Instalar y añadir a inicio',
      androidAutoCta: 'Instalar BlocTag automáticamente',
      androidManualTitle: 'Instalación automática no disponible',
      androidManualDesc: 'Toca <strong class="text-on-surface">Menú (⋮)</strong> → <strong class="text-primary">«Instalar aplicación»</strong>.',
      androidManualDone: 'App instalada',
      androidHint: 'Toca el botón y confirma para añadir <strong class="text-on-surface">BlocTag</strong> a tu pantalla.',
      doneBadge: 'Instalación completa',
      doneTitlePre: '¡Ya puedes ',
      doneTitleHighlight: 'abrir la App!',
      doneSub: '<strong class="text-on-surface">BlocTag</strong> está en tu pantalla de inicio. Cierra el navegador y abre el icono <strong class="text-primary">BlocTag</strong>.',
      doneCardTitle: 'App BlocTag lista',
      doneCardSub: 'Ábrela desde tu pantalla de inicio',
      doneOpenBtn: 'Abrir App',
      doneRetryBtn: '¿No apareció? Instalar de nuevo',
      browserTranslateHint: 'Usa el traductor de tu navegador para otros idiomas.'
    },
    fr: {
      welcomeBadge: 'BlocTag • Bienvenue',
      web3TitlePre: 'Savez-vous ce qu’est le ',
      web3TitleHighlight: 'Web3 ?',
      web3Sub: 'Choisissez l’interface adaptée. Vous pouvez basculer entre <strong class="text-on-surface">Simple</strong> et <strong class="text-on-surface">Pro</strong> dans le menu.',
      simpleTitle: 'Non, restons simple',
      simpleBadge: 'Mode Simple',
      simpleDesc: 'Sans jargon technique. Portefeuille facile, transferts rapides et fil Space.',
      proTitle: 'Oui, je connais le Web3',
      proBadge: 'Mode Pro',
      proDesc: 'Block Explorer, Node Panel, Bridge, BNS et tous les outils avancés.',
      nonCustodialFooter: '100% Non-Custodial • Clés stockées uniquement sur votre appareil',
      pwaBadge: 'Installation de l’application requise',
      pwaTitlePre: 'Ajouter BlocTag à ',
      pwaTitleHighlight: 'l’écran d’accueil',
      pwaSub: 'Pour le plein écran, les notifications et le coffre sécurisé sur mobile, installez l’application BlocTag.',
      chipVault: 'Coffre Sécurisé',
      chipSpeed: 'Instantané',
      chipFull: 'Plein Écran',
      iosInAppTitle: 'Ouvrir dans Safari',
      iosInAppDesc: 'Les navigateurs intégrés sur iPhone bloquent l’installation. Copiez le lien et ouvrez-le dans <strong class="text-on-surface">Safari</strong>.',
      iosInAppBtn: 'Copier le lien pour Safari',
      iosCta: 'Ajouter à l’écran d’accueil',
      iosAlready: 'Déjà ajouté',
      iosSheetTitle: 'Sur l’écran d’accueil',
      iosStep1Chrome: 'Touchez <strong class="text-primary">Partager</strong> en haut à droite.',
      iosStep1Safari: 'Touchez <strong class="text-primary">Partager</strong> en bas au centre de Safari.',
      iosStep2: 'Sélectionnez <strong class="text-primary">« Sur l’écran d’accueil »</strong> → <strong class="text-primary">« Ajouter »</strong>.',
      iosAddedBtn: 'Ajouté à l’écran d’accueil',
      iosPointerSafari: 'Icône Partager (↑) juste en dessous',
      iosPointerChrome: 'Icône Partager (↑) en haut à droite',
      androidStarting: 'Lancement de l’installation...',
      androidReadyCta: 'Installer et ajouter à l’écran',
      androidAutoCta: 'Installer BlocTag automatiquement',
      androidManualTitle: 'Installation auto non prise en charge',
      androidManualDesc: 'Touchez <strong class="text-on-surface">Menu (⋮)</strong> → <strong class="text-primary">« Installer l’application »</strong>.',
      androidManualDone: 'Application installée',
      androidHint: 'Touchez le bouton et confirmez pour ajouter <strong class="text-on-surface">BlocTag</strong>.',
      doneBadge: 'Installation terminée',
      doneTitlePre: 'Vous pouvez ',
      doneTitleHighlight: 'ouvrir l’app !',
      doneSub: '<strong class="text-on-surface">BlocTag</strong> est sur votre écran d’accueil. Fermez le navigateur et touchez l’icône <strong class="text-primary">BlocTag</strong>.',
      doneCardTitle: 'BlocTag est prêt',
      doneCardSub: 'Lancez l’app depuis votre écran d’accueil',
      doneOpenBtn: 'Ouvrir l’application',
      doneRetryBtn: 'Pas sur l’écran ? Réinstaller',
      browserTranslateHint: 'Utilisez le traducteur du navigateur pour toute autre langue.'
    },
    ar: {
      welcomeBadge: 'BlocTag • مرحباً بك',
      web3TitlePre: 'هل تعرف ما هو ',
      web3TitleHighlight: 'Web3؟',
      web3Sub: 'اختر الواجهة المناسبة لك. يمكنك التبديل بين <strong class="text-on-surface">Simple</strong> و <strong class="text-on-surface">Pro</strong> في أي وقت.',
      simpleTitle: 'لا، أريد الوضع البسيط',
      simpleBadge: 'الوضع البسيط',
      simpleDesc: 'بدون مصطلحات معقدة. محفظة سهلة وتحويلات سريعة وخلاصة Space بسيطة.',
      proTitle: 'نعم، أعرف Web3',
      proBadge: 'وضع Pro',
      proDesc: 'مستكشف الكتل، لوحة العقدة، الجسر، BNS وجميع أدوات البروتوكول المتقدمة.',
      nonCustodialFooter: '100% غير وصائي • المفاتيح تبقى على جهازك فقط',
      pwaBadge: 'تثبيت تطبيق الجوال مطلوب',
      pwaTitlePre: 'أضف تطبيق BlocTag إلى ',
      pwaTitleHighlight: 'الشاشة الرئيسية',
      pwaSub: 'للحصول على تجربة ملء الشاشة والإشعارات الفورية والتخزين الآمن، يرجى تثبيت تطبيق BlocTag.',
      chipVault: 'خزنة آمنة',
      chipSpeed: 'سرعة فائقة',
      chipFull: 'ملء الشاشة',
      iosInAppTitle: 'افتح في متصفح Safari',
      iosInAppDesc: 'لا تسمح المتصفحات الداخلية على iPhone بالتثبيت. انسخ الرابط وافتحه في <strong class="text-on-surface">Safari</strong>.',
      iosInAppBtn: 'نسخ الرابط وفتحه في Safari',
      iosCta: 'إضافة إلى الشاشة الرئيسية',
      iosAlready: 'تمت الإضافة بالفعل',
      iosSheetTitle: 'إضافة للشاشة الرئيسية',
      iosStep1Chrome: 'اضغط على أيقونة <strong class="text-primary">المشاركة</strong> في الأعلى.',
      iosStep1Safari: 'اضغط على أيقونة <strong class="text-primary">المشاركة</strong> في أسفل Safari.',
      iosStep2: 'اختر <strong class="text-primary">"إضافة إلى الشاشة الرئيسية"</strong> ثم <strong class="text-primary">"إضافة"</strong>.',
      iosAddedBtn: 'تمت الإضافة للشاشة الرئيسية',
      iosPointerSafari: 'أيقونة المشاركة (↑) بالأسفل',
      iosPointerChrome: 'أيقونة المشاركة (↑) بالأعلى',
      androidStarting: 'جاري بدء التثبيت...',
      androidReadyCta: 'تثبيت وإضافة للشاشة الرئيسية',
      androidAutoCta: 'تثبيت BlocTag تلقائياً',
      androidManualTitle: 'التثبيت التلقائي غير مدعوم',
      androidManualDesc: 'اضغط على <strong class="text-on-surface">القائمة (⋮)</strong> ثم <strong class="text-primary">"تثبيت التطبيق"</strong>.',
      androidManualDone: 'تم تثبيت التطبيق',
      androidHint: 'اضغط على الزر ووافق لإضافة <strong class="text-on-surface">BlocTag</strong> مباشرة لشاشتك الرئيسية.',
      doneBadge: 'اكتمل التثبيت',
      doneTitlePre: 'يمكنك الآن ',
      doneTitleHighlight: 'فتح التطبيق!',
      doneSub: 'تمت إضافة <strong class="text-on-surface">BlocTag</strong> إلى شاشتك الرئيسية. أغلق المتصفح واضغط على أيقونة <strong class="text-primary">BlocTag</strong>.',
      doneCardTitle: 'تطبيق BlocTag جاهز',
      doneCardSub: 'افتح التطبيق من الشاشة الرئيسية',
      doneOpenBtn: 'فتح التطبيق',
      doneRetryBtn: 'لم يظهر التطبيق؟ أعد التثبيت',
      browserTranslateHint: 'يمكنك استخدام مترجم المتصفح لأي لغة أخرى.'
    }
  };

  function getGateLanguage() {
    try {
      const saved = localStorage.getItem(GATE_LANG_STORAGE_KEY);
      if (saved && GATE_I18N[saved]) return saved;
    } catch (_e) { }
    return 'en'; // Default English so browser translator plugins translate cleanly
  }

  function handleSetGateLanguage(langCode) {
    if (langCode === 'browser') {
      try { localStorage.setItem(GATE_LANG_STORAGE_KEY, 'en'); } catch (_e) { }
      document.documentElement.lang = 'en';
      document.documentElement.dir = 'ltr';
      if (_mobileGateStep) renderMobileOnboardingGate(_mobileGateStep);
      if (typeof window.showToast === 'function') {
        window.showToast(GATE_I18N.en.browserTranslateHint, 'translate');
      }
      return;
    }
    const clean = GATE_I18N[langCode] ? langCode : 'en';
    try {
      localStorage.setItem(GATE_LANG_STORAGE_KEY, clean);
    } catch (_e) { }
    document.documentElement.lang = clean;
    document.documentElement.dir = (clean === 'ar') ? 'rtl' : 'ltr';
    if (_mobileGateStep) {
      renderMobileOnboardingGate(_mobileGateStep);
    }
  }

  function renderGateLanguageBar(activeLang) {
    const opts = [
      ['en', '🌐 English (Default)'],
      ['tr', '🇹🇷 Türkçe'],
      ['az', '🇦🇿 Azərbaycanca'],
      ['ru', '🇷🇺 Русский'],
      ['de', '🇩🇪 Deutsch'],
      ['es', '🇪🇸 Español'],
      ['fr', '🇫🇷 Français'],
      ['ar', '🇸🇦 العربية'],
      ['browser', '✨ Browser Translate']
    ];
    return `
      <div class="w-full flex items-center justify-end -mb-1 notranslate" translate="no">
        <label class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-surface-container-high border border-outline-variant/25 text-[11px] font-medium text-on-surface cursor-pointer shadow-sm">
          <span class="material-symbols-outlined text-[15px] text-primary">translate</span>
          <select aria-label="Language" onchange="window.BlocTagSimpleMode.setGateLanguage(this.value)"
            class="bg-transparent text-on-surface text-[11px] font-semibold focus:outline-none cursor-pointer pr-1">
            ${opts.map(([code, label]) => `<option value="${code}" class="bg-[#1b1b1e] text-[#e5e1e4]" ${activeLang === code ? 'selected' : ''}>${label}</option>`).join('')}
          </select>
        </label>
      </div>
    `;
  }

  function ensureMobileGateOverlay() {
    let el = document.getElementById('bloctag-mobile-gate-overlay');
    if (!el) {
      el = document.createElement('div');
      el.id = 'bloctag-mobile-gate-overlay';
      el.setAttribute('role', 'dialog');
      el.setAttribute('aria-modal', 'true');
      el.setAttribute('translate', 'yes');
      document.body.appendChild(el);
    }
    return el;
  }

  function closeMobileOnboardingGate() {
    _mobileGateStep = null;
    document.documentElement.classList.remove('bloctag-mobile-gate-open');
    document.documentElement.dir = 'ltr';
    const el = document.getElementById('bloctag-mobile-gate-overlay');
    if (el) {
      el.classList.remove('is-visible');
      el.innerHTML = '';
    }
  }

  function renderMobileOnboardingGate(step) {
    if (!isMobileDevice()) {
      closeMobileOnboardingGate();
      return;
    }

    _mobileGateStep = step;
    const lang = getGateLanguage();
    const t = GATE_I18N[lang] || GATE_I18N.en;
    document.documentElement.lang = lang;
    document.documentElement.dir = (lang === 'ar') ? 'rtl' : 'ltr';

    const overlay = ensureMobileGateOverlay();
    document.documentElement.classList.add('bloctag-mobile-gate-open');
    const langBarHtml = renderGateLanguageBar(lang);

    if (step === 'web3') {
      overlay.innerHTML = `
        <div class="w-full max-w-[400px] flex flex-col gap-5" translate="yes">
          ${langBarHtml}
          <!-- Brand Header -->
          <div class="flex flex-col items-center text-center gap-3">
            <div class="relative flex items-center justify-center w-20 h-20 rounded-full bg-surface-container-high shadow-xl border border-primary/25">
              <svg class="w-10 h-10 text-primary" fill="none" viewBox="0 0 36 36">
                <path class="opacity-95" d="M18 4L30 11V25L18 32L6 25V11L18 4Z" stroke="currentColor" stroke-linejoin="round" stroke-width="2.2"></path>
                <path d="M18 12L24 15.5V22.5L18 26L12 22.5V15.5L18 12Z" fill="currentColor" fill-opacity="0.25"></path>
                <circle cx="18" cy="19" fill="currentColor" r="3"></circle>
              </svg>
              <span class="absolute bottom-1 right-1 w-3.5 h-3.5 rounded-full bg-primary ring-2 ring-[#131315]"></span>
            </div>
            <div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-container-high border border-outline-variant/20 text-[11px] font-mono text-primary">
              <span class="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></span>
              <span>${t.welcomeBadge}</span>
            </div>
            <h1 class="text-[26px] leading-[32px] font-bold text-on-surface tracking-tight">
              ${t.web3TitlePre}<span class="text-primary">${t.web3TitleHighlight}</span>
            </h1>
            <p class="text-xs text-on-surface-variant leading-relaxed max-w-[330px]">
              ${t.web3Sub}
            </p>
          </div>

          <!-- Experience Choice Cards -->
          <div class="flex flex-col gap-3">
            <button type="button" onclick="window.BlocTagSimpleMode.selectWeb3Experience('simple')"
              class="w-full text-left p-4 rounded-3xl bg-primary/12 hover:bg-primary/18 border border-primary/40 shadow-lg active:scale-[0.98] transition-all cursor-pointer flex items-start gap-3.5">
              <div class="w-12 h-12 rounded-2xl bg-primary text-on-primary flex items-center justify-center shrink-0 shadow-md">
                <span class="material-symbols-outlined notranslate text-[24px]" translate="no">auto_awesome</span>
              </div>
              <div class="flex flex-col flex-1 min-w-0">
                <div class="flex items-center justify-between gap-2">
                  <span class="text-sm font-bold text-on-surface">${t.simpleTitle}</span>
                  <span class="px-2 py-0.5 rounded-full bg-primary text-on-primary font-mono text-[10px] font-bold shrink-0">${t.simpleBadge}</span>
                </div>
                <p class="text-xs text-on-surface-variant mt-1 leading-relaxed">
                  ${t.simpleDesc}
                </p>
              </div>
            </button>

            <button type="button" onclick="window.BlocTagSimpleMode.selectWeb3Experience('pro')"
              class="w-full text-left p-4 rounded-3xl bg-surface-container hover:bg-surface-container-high border border-outline-variant/25 shadow-md active:scale-[0.98] transition-all cursor-pointer flex items-start gap-3.5">
              <div class="w-12 h-12 rounded-2xl bg-surface-container-highest text-primary flex items-center justify-center shrink-0 border border-outline-variant/20">
                <span class="material-symbols-outlined notranslate text-[24px]" translate="no">bolt</span>
              </div>
              <div class="flex flex-col flex-1 min-w-0">
                <div class="flex items-center justify-between gap-2">
                  <span class="text-sm font-bold text-on-surface">${t.proTitle}</span>
                  <span class="px-2 py-0.5 rounded-full bg-surface-container-highest text-on-surface-variant font-mono text-[10px] font-bold shrink-0">${t.proBadge}</span>
                </div>
                <p class="text-xs text-on-surface-variant mt-1 leading-relaxed">
                  ${t.proDesc}
                </p>
              </div>
            </button>
          </div>

          <div class="flex items-center justify-center gap-1.5 text-[11px] text-on-surface-variant/70 pt-1">
            <span class="material-symbols-outlined notranslate text-[14px] text-primary" translate="no">verified_user</span>
            <span>${t.nonCustodialFooter}</span>
          </div>
        </div>
      `;
    } else if (step === 'pwa') {
      const isIos = isIosDeviceLocal();
      const hasNativePrompt = Boolean(getAvailablePwaPrompt());

      overlay.innerHTML = `
        <div class="w-full max-w-[400px] flex flex-col gap-5" translate="yes">
          ${langBarHtml}
          <div class="flex flex-col items-center text-center gap-3">
            <div class="relative flex items-center justify-center w-20 h-20 rounded-3xl bg-surface-container-high shadow-xl border border-primary/30">
              <span class="material-symbols-outlined notranslate text-primary text-[38px]" translate="no">install_mobile</span>
              <span class="absolute -bottom-1.5 -right-1.5 w-7 h-7 rounded-full bg-primary text-on-primary flex items-center justify-center shadow-md">
                <span class="material-symbols-outlined notranslate text-[16px]" translate="no">download</span>
              </span>
            </div>

            <div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/15 border border-primary/30 text-[11px] font-mono text-primary font-semibold">
              <span class="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></span>
              <span>${t.pwaBadge}</span>
            </div>

            <h1 class="text-[24px] leading-[30px] font-bold text-on-surface tracking-tight">
              ${t.pwaTitlePre}<span class="text-primary">${t.pwaTitleHighlight}</span>
            </h1>
            <p class="text-xs text-on-surface-variant leading-relaxed max-w-[340px]">
              ${t.pwaSub}
            </p>
          </div>

          <!-- Feature Mini-Strip -->
          <div class="grid grid-cols-3 gap-2">
            <div class="p-3 rounded-2xl bg-surface-container/90 border border-outline-variant/15 flex flex-col items-center text-center gap-1">
              <span class="material-symbols-outlined notranslate text-primary text-[20px]" translate="no">shield_lock</span>
              <span class="text-[11px] font-semibold text-on-surface">${t.chipVault}</span>
            </div>
            <div class="p-3 rounded-2xl bg-surface-container/90 border border-outline-variant/15 flex flex-col items-center text-center gap-1">
              <span class="material-symbols-outlined notranslate text-primary text-[20px]" translate="no">bolt</span>
              <span class="text-[11px] font-semibold text-on-surface">${t.chipSpeed}</span>
            </div>
            <div class="p-3 rounded-2xl bg-surface-container/90 border border-outline-variant/15 flex flex-col items-center text-center gap-1">
              <span class="material-symbols-outlined notranslate text-primary text-[20px]" translate="no">fullscreen</span>
              <span class="text-[11px] font-semibold text-on-surface">${t.chipFull}</span>
            </div>
          </div>

          ${isIos ? `
            ${isIosInAppBrowser() ? `
              <!-- iOS In-App Browser Redirect to Safari -->
              <div class="p-4 rounded-3xl bg-surface-container border border-amber-400/35 flex flex-col gap-3">
                <div class="flex items-center gap-2 text-xs font-bold text-amber-300">
                  <span class="material-symbols-outlined notranslate text-[18px]" translate="no">open_in_browser</span>
                  <span>${t.iosInAppTitle}</span>
                </div>
                <p class="text-xs text-on-surface-variant leading-relaxed">
                  ${t.iosInAppDesc}
                </p>
                <button type="button" onclick="window.BlocTagSimpleMode.copySiteLinkForSafari()"
                  class="w-full h-12 rounded-full bg-primary text-on-primary text-sm font-bold flex items-center justify-center gap-2 shadow-lg active:scale-[0.98] transition-all cursor-pointer">
                  <span class="material-symbols-outlined notranslate text-[19px]" translate="no">content_copy</span>
                  <span>${t.iosInAppBtn}</span>
                </button>
              </div>
            ` : `
              <!-- iOS Safari / Chrome Primary CTA + Animated Bottom-Sheet Spotlight Guide -->
              <div class="flex flex-col gap-3">
                <button type="button" onclick="window.BlocTagSimpleMode.openIosInstallSheet()"
                  class="w-full h-[54px] rounded-full bg-primary text-on-primary text-sm font-bold flex items-center justify-center gap-2 shadow-[0_8px_24px_rgba(78,222,163,0.3)] hover:brightness-95 active:scale-[0.98] transition-all cursor-pointer">
                  <span class="material-symbols-outlined notranslate text-[20px]" translate="no">add_to_home_screen</span>
                  <span>${t.iosCta}</span>
                </button>

                <button type="button" onclick="window.BlocTagSimpleMode.markManualPwaInstalled()"
                  class="w-full h-11 rounded-full bg-surface-container-high hover:bg-surface-bright text-on-surface text-xs font-semibold flex items-center justify-center gap-1.5 active:scale-[0.98] transition-all cursor-pointer">
                  <span class="material-symbols-outlined notranslate text-[17px] text-primary" translate="no">check_circle</span>
                  <span>${t.iosAlready}</span>
                </button>
              </div>

              ${_iosInstallSheetOpen ? `
                <!-- Bottom-Docked Visual Spotlight Sheet Pointing Directly to Safari/Chrome Share Icon -->
                <div class="fixed inset-0 z-[135] bg-black/75 backdrop-blur-sm flex flex-col justify-end items-center p-3 pb-[max(16px,env(safe-area-inset-bottom,12px))]"
                     onclick="window.BlocTagSimpleMode.closeIosInstallSheet()">
                  <div class="w-full max-w-[400px] rounded-3xl bg-[#1b1b1e] border border-primary/40 shadow-2xl p-5 flex flex-col gap-4 animate-fade-in"
                       onclick="event.stopPropagation()">
                    <div class="flex items-center justify-between">
                      <div class="flex items-center gap-2.5">
                        <div class="w-10 h-10 rounded-2xl bg-primary/15 border border-primary/30 text-primary flex items-center justify-center shrink-0">
                          <span class="material-symbols-outlined notranslate text-[22px]" translate="no">add_to_home_screen</span>
                        </div>
                        <div class="flex flex-col">
                          <span class="text-sm font-bold text-on-surface">${t.iosSheetTitle}</span>
                          <span class="text-[11px] font-mono text-primary notranslate" translate="no">${isIosChrome() ? 'Chrome iOS' : 'Safari'}</span>
                        </div>
                      </div>
                      <button type="button" onclick="window.BlocTagSimpleMode.closeIosInstallSheet()"
                        class="w-8 h-8 rounded-full bg-surface-container-high text-on-surface-variant hover:text-on-surface flex items-center justify-center cursor-pointer">
                        <span class="material-symbols-outlined notranslate text-[18px]" translate="no">close</span>
                      </button>
                    </div>

                    <div class="flex flex-col gap-2.5">
                      <div class="flex items-center gap-3 p-3 rounded-2xl bg-surface-container border border-outline-variant/15">
                        <span class="w-6 h-6 rounded-full bg-primary text-on-primary font-mono font-bold text-xs flex items-center justify-center shrink-0">1</span>
                        <span class="text-xs text-on-surface leading-snug">
                          ${isIosChrome() ? t.iosStep1Chrome : t.iosStep1Safari} (<span class="material-symbols-outlined notranslate text-[16px] align-middle text-primary" translate="no">ios_share</span>)
                        </span>
                      </div>
                      <div class="flex items-center gap-3 p-3 rounded-2xl bg-surface-container border border-outline-variant/15">
                        <span class="w-6 h-6 rounded-full bg-primary text-on-primary font-mono font-bold text-xs flex items-center justify-center shrink-0">2</span>
                        <span class="text-xs text-on-surface leading-snug">
                          ${t.iosStep2} (<span class="material-symbols-outlined notranslate text-[15px] align-middle text-primary" translate="no">add_box</span>)
                        </span>
                      </div>
                    </div>

                    <button type="button" onclick="window.BlocTagSimpleMode.markManualPwaInstalled()"
                      class="w-full h-12 rounded-full bg-primary text-on-primary text-sm font-bold flex items-center justify-center gap-2 shadow-lg active:scale-[0.98] transition-all cursor-pointer">
                      <span class="material-symbols-outlined notranslate text-[19px]" translate="no">check_circle</span>
                      <span>${t.iosAddedBtn}</span>
                    </button>
                  </div>

                  ${!isIosChrome() ? `
                    <div class="flex flex-col items-center gap-0.5 pt-2.5 text-primary animate-bounce pointer-events-none">
                      <span class="text-[11px] font-bold">${t.iosPointerSafari}</span>
                      <span class="material-symbols-outlined notranslate text-[26px]" translate="no">keyboard_double_arrow_down</span>
                    </div>
                  ` : `
                    <div class="flex items-center justify-center gap-1.5 pt-2.5 text-primary text-[11px] font-bold pointer-events-none">
                      <span class="material-symbols-outlined notranslate text-[18px]" translate="no">north_east</span>
                      <span>${t.iosPointerChrome}</span>
                    </div>
                  `}
                </div>
              ` : ''}
            `}
          ` : `
            <!-- Android / Chromium One-Tap Auto-Install CTA -->
            <div class="flex flex-col gap-3">
              <button type="button" id="bloctag-mandatory-pwa-btn" onclick="window.BlocTagSimpleMode.triggerMandatoryPwaInstall()"
                ${_pwaInstallWaiting ? 'disabled' : ''}
                class="w-full h-[54px] rounded-full bg-primary text-on-primary text-sm font-bold flex items-center justify-center gap-2 shadow-[0_8px_24px_rgba(78,222,163,0.3)] hover:brightness-95 active:scale-[0.98] transition-all cursor-pointer disabled:opacity-85">
                ${_pwaInstallWaiting ? `
                  <span class="material-symbols-outlined notranslate text-[21px] animate-spin" translate="no">progress_activity</span>
                  <span>${t.androidStarting}</span>
                ` : `
                  <span class="material-symbols-outlined notranslate text-[21px]" translate="no">download</span>
                  <span>${hasNativePrompt ? t.androidReadyCta : t.androidAutoCta}</span>
                `}
              </button>

              ${_pwaManualGuideOpen ? `
                <div class="p-3.5 rounded-2xl bg-surface-container border border-outline-variant/25 flex flex-col gap-2 text-xs text-on-surface-variant">
                  <div class="font-semibold text-on-surface flex items-center gap-1.5">
                    <span class="material-symbols-outlined notranslate text-primary text-[16px]" translate="no">info</span>
                    <span>${t.androidManualTitle}</span>
                  </div>
                  <p class="leading-relaxed">
                    ${t.androidManualDesc}
                  </p>
                  <button type="button" onclick="window.BlocTagSimpleMode.markManualPwaInstalled()"
                    class="mt-1 h-9 px-3 rounded-full bg-surface-container-high hover:bg-surface-bright text-primary text-xs font-semibold cursor-pointer">
                    ${t.androidManualDone}
                  </button>
                </div>
              ` : `
                <p class="text-center text-[11px] text-on-surface-variant/80 leading-relaxed">
                  ${t.androidHint}
                </p>
              `}
            </div>
          `}
        </div>
      `;
    } else if (step === 'pwa-installed') {
      overlay.innerHTML = `
        <div class="w-full max-w-[400px] flex flex-col items-center text-center gap-5" translate="yes">
          ${langBarHtml}
          <div class="relative flex items-center justify-center w-22 h-22 rounded-full bg-primary/15 border border-primary/40 shadow-[0_0_40px_rgba(78,222,163,0.22)]">
            <span class="material-symbols-outlined notranslate text-primary text-[44px]" style="font-variation-settings: 'FILL' 1;" translate="no">task_alt</span>
          </div>

          <div class="flex flex-col gap-2">
            <div class="inline-flex items-center justify-center gap-1.5 px-3 py-1 rounded-full bg-primary/15 border border-primary/30 text-[11px] font-mono text-primary font-semibold mx-auto">
              <span class="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></span>
              <span>${t.doneBadge}</span>
            </div>
            <h1 class="text-[24px] leading-[30px] font-bold text-on-surface tracking-tight">
              ${t.doneTitlePre}<span class="text-primary">${t.doneTitleHighlight}</span>
            </h1>
            <p class="text-xs text-on-surface-variant leading-relaxed max-w-[330px] mx-auto">
              ${t.doneSub}
            </p>
          </div>

          <div class="w-full p-4 rounded-3xl bg-surface-container border border-outline-variant/20 flex items-center gap-3 text-left">
            <div class="w-12 h-12 rounded-2xl bg-[#131315] border border-primary/35 flex items-center justify-center shrink-0">
              <svg class="w-7 h-7 text-primary" fill="none" viewBox="0 0 36 36">
                <path d="M18 4L30 11V25L18 32L6 25V11L18 4Z" stroke="currentColor" stroke-linejoin="round" stroke-width="2.2"></path>
                <circle cx="18" cy="19" fill="currentColor" r="3"></circle>
              </svg>
            </div>
            <div class="flex flex-col min-w-0">
              <span class="text-xs font-bold text-on-surface">${t.doneCardTitle}</span>
              <span class="text-[11px] text-on-surface-variant">${t.doneCardSub}</span>
            </div>
          </div>

          <div class="w-full flex flex-col gap-2.5">
            <a href="${esc(window.location.origin + '/?pwa_launch=1')}" target="_blank" rel="noopener"
              onclick="window.BlocTagSimpleMode.openInstalledAppHint(event)"
              class="w-full h-[52px] rounded-full bg-primary text-on-primary text-sm font-bold flex items-center justify-center gap-2 shadow-lg active:scale-[0.98] transition-all cursor-pointer no-underline">
              <span class="material-symbols-outlined notranslate text-[20px]" translate="no">open_in_new</span>
              <span>${t.doneOpenBtn}</span>
            </a>
            <button type="button" onclick="window.BlocTagSimpleMode.showPwaInstallStepsAgain()"
              class="w-full h-10 rounded-full bg-transparent hover:bg-surface-container text-on-surface-variant text-xs font-medium transition-colors cursor-pointer">
              ${t.doneRetryBtn}
            </button>
          </div>
        </div>
      `;
    }

    overlay.classList.add('is-visible');
  }

  function handleSelectWeb3Experience(choice) {
    const isSimple = choice === 'simple';
    try {
      localStorage.setItem(WEB3_ONBOARDING_STORAGE_KEY, isSimple ? 'simple' : 'pro');
      localStorage.setItem(SIMPLE_MODE_STORAGE_KEY, isSimple ? 'true' : 'false');
      if (isSimple) {
        // Simple Mode default: Back button OFF
        localStorage.setItem(PWA_BACK_BTN_STORAGE_KEY, 'false');
        if (typeof window.applyPwaBackButtonUI === 'function') {
          window.applyPwaBackButtonUI(false);
        }
      }
    } catch (_e) { }

    if (isSimple) {
      if (!getActiveWallet()) {
        simpleState.activeScreen = 'SCR-ONB-01';
      }
      applySimpleModeState(true, true);
    } else {
      applySimpleModeState(false, false);
    }

    // Next step: if on mobile browser (not standalone PWA), show mandatory PWA install gate
    if (isMobileDevice() && !isStandalonePwaApp()) {
      const alreadyInstalled = localStorage.getItem(PWA_INSTALLED_STORAGE_KEY) === 'true';
      renderMobileOnboardingGate(alreadyInstalled ? 'pwa-installed' : 'pwa');
    } else {
      closeMobileOnboardingGate();
    }
  }

  async function handleTriggerMandatoryPwaInstall() {
    // 1. MUST call prompt() synchronously inside the user click gesture (Chrome security requirement!)
    const promptEv = getAvailablePwaPrompt();
    if (promptEv) {
      _pwaInstallWaiting = false;
      _pwaAutoTriggerPending = false;
      try {
        const promptPromise = promptEv.prompt();
        if (promptPromise && typeof promptPromise.then === 'function') {
          await promptPromise;
        }
        const choice = await promptEv.userChoice;
        _capturedPwaPrompt = null;
        window.__bloctagPwaPrompt = null;
        try {
          if (typeof deferredPwaPrompt !== 'undefined') deferredPwaPrompt = null;
        } catch (_e) { }
        if (choice && choice.outcome === 'accepted') {
          try {
            localStorage.setItem(PWA_INSTALLED_STORAGE_KEY, 'true');
          } catch (_e) { }
          renderMobileOnboardingGate('pwa-installed');
          if (typeof window.showToast === 'function') {
            window.showToast('BlocTag ana ekranınıza eklendi! Uygulamayı açabilirsiniz.', 'check_circle');
          }
          return;
        }
        renderMobileOnboardingGate('pwa');
        return;
      } catch (_e) { }
    }

    // 2. Check if the PWA is ALREADY installed on this Android device
    try {
      if (navigator.getInstalledRelatedApps) {
        const related = await navigator.getInstalledRelatedApps();
        if (Array.isArray(related) && related.length > 0) {
          localStorage.setItem(PWA_INSTALLED_STORAGE_KEY, 'true');
          renderMobileOnboardingGate('pwa-installed');
          return;
        }
      }
    } catch (_e) { }

    // 3. Ensure SW is registered and wait briefly for beforeinstallprompt so user can tap once it's ready
    _pwaInstallWaiting = true;
    renderMobileOnboardingGate('pwa');

    try {
      if ('serviceWorker' in navigator) {
        await navigator.serviceWorker.register('/sw.js').catch(() => { });
      }
    } catch (_e) { }

    const deadline = Date.now() + 3000;
    while (Date.now() < deadline) {
      if (getAvailablePwaPrompt()) {
        _pwaInstallWaiting = false;
        renderMobileOnboardingGate('pwa');
        if (typeof window.showToast === 'function') {
          window.showToast('Kurulum hazır! Yüklemek için butona tekrar dokunun.', 'download');
        }
        return;
      }
      await new Promise(r => setTimeout(r, 200));
    }

    // 4. Fallback only if browser doesn't support beforeinstallprompt (e.g. Firefox, In-App WebView, or already installed)
    _pwaInstallWaiting = false;
    _pwaManualGuideOpen = true;
    renderMobileOnboardingGate('pwa');
  }

  function handleToggleIosInstallSheet(open) {
    _iosInstallSheetOpen = Boolean(open);
    if (_mobileGateStep === 'pwa') {
      renderMobileOnboardingGate('pwa');
    }
  }

  function handleCopySiteLinkForSafari() {
    const url = 'https://www.locktrace.space/';
    if (typeof window.copyText === 'function') {
      window.copyText(url, 'Link kopyalandı! Safari\'yi açıp adres çubuğuna yapıştırın.');
    } else if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).catch(() => { });
      if (typeof window.showToast === 'function') {
        window.showToast('Link kopyalandı! Safari\'de açın.', 'content_copy');
      }
    }
  }

  function handleMarkManualPwaInstalled() {
    _iosInstallSheetOpen = false;
    try {
      localStorage.setItem(PWA_INSTALLED_STORAGE_KEY, 'true');
    } catch (_e) { }
    renderMobileOnboardingGate('pwa-installed');
  }

  function handleShowPwaInstallStepsAgain() {
    try {
      localStorage.removeItem(PWA_INSTALLED_STORAGE_KEY);
    } catch (_e) { }
    _pwaManualGuideOpen = false;
    _pwaInstallWaiting = false;
    _pwaAutoTriggerPending = false;
    renderMobileOnboardingGate('pwa');
  }

  function handleOpenInstalledAppHint(ev) {
    // On iOS Safari, browsers cannot programmatically launch a Home Screen WebClip
    if (isIosDeviceLocal()) {
      if (ev) ev.preventDefault();
      if (typeof window.showToast === 'function') {
        window.showToast('Safari\'yi kapatıp telefonunuzun ana ekranındaki BlocTag ikonuna dokunun.', 'install_mobile');
      }
      return;
    }
    // On Android/Chromium, let the native <a href="/?pwa_launch=1" target="_blank"> link trigger WebAPK / launch_handler!
    if (typeof window.showToast === 'function') {
      window.showToast('BlocTag uygulaması başlatılıyor... Açılmazsa ana ekranınızdan dokunun.', 'open_in_new');
    }
  }

  function evaluateMobileGates() {
    // Desktop / PC: do NOT show Web3 gate or mandatory PWA gate
    if (!isMobileDevice()) {
      closeMobileOnboardingGate();
      return;
    }

    let onboardingChoice = null;
    try {
      onboardingChoice = localStorage.getItem(WEB3_ONBOARDING_STORAGE_KEY);
    } catch (_e) { }

    if (!onboardingChoice) {
      renderMobileOnboardingGate('web3');
      return;
    }

    if (!isStandalonePwaApp()) {
      let alreadyInstalled = Boolean(window.__bloctagPwaInstalled);
      try {
        if (localStorage.getItem(PWA_INSTALLED_STORAGE_KEY) === 'true') alreadyInstalled = true;
      } catch (_e) { }
      renderMobileOnboardingGate(alreadyInstalled ? 'pwa-installed' : 'pwa');
      // Async check if Android Chrome already has the PWA installed
      if (!alreadyInstalled && navigator.getInstalledRelatedApps) {
        navigator.getInstalledRelatedApps().then((related) => {
          if (Array.isArray(related) && related.length > 0 && _mobileGateStep === 'pwa') {
            try { localStorage.setItem(PWA_INSTALLED_STORAGE_KEY, 'true'); } catch (_e) { }
            renderMobileOnboardingGate('pwa-installed');
          }
        }).catch(() => { });
      }
      return;
    }

    // Running inside Standalone PWA! Close gate and ensure welcome screen if no wallet exists
    closeMobileOnboardingGate();
    if (simpleState.enabled && !getActiveWallet()) {
      simpleState.activeScreen = 'SCR-ONB-01';
      renderSimpleMode(false);
    }
  }

  // Expose globally for inline handlers & menu toggles
  window.BlocTagSimpleMode = BlocTagSimpleMode;
  window.isSimpleModeEnabled = isSimpleModeEnabled;
  window.toggleSimpleModeSetting = toggleSimpleModeSetting;
  window.applySimpleModeState = applySimpleModeState;

  // Boot & Hook into Core App Lifecycle
  function initSimpleModeModule() {
    const mobile = isMobileDevice();
    const saved = mobile ? isSimpleModeEnabled() : false;
    syncModeToggleControls(saved);
    if (saved) {
      if (!getActiveWallet()) {
        simpleState.activeScreen = 'SCR-ONB-01';
      }
      applySimpleModeState(true, false);
    }
    evaluateMobileGates();

    // Wrap wallet state updates so 15s background balance polls patch in-place with zero flicker
    const origSaveWalletState = window.saveWalletState;
    if (typeof origSaveWalletState === 'function' && !origSaveWalletState._simpleHooked) {
      const wrappedSave = function (acc) {
        const res = origSaveWalletState.apply(this, arguments);
        if (simpleState.enabled) {
          const nextAddr = acc ? String(acc.address || '') : '';
          if (nextAddr !== _lastKnownWalletAddr) {
            _lastKnownWalletAddr = nextAddr;
            renderSimpleMode(false);
          } else {
            patchSimpleLiveValuesInPlace();
          }
        }
        return res;
      };
      wrappedSave._simpleHooked = true;
      window.saveWalletState = wrappedSave;
    }

    const origRenderSpacePosts = window.renderSpacePosts;
    if (typeof origRenderSpacePosts === 'function' && !origRenderSpacePosts._simpleHooked) {
      const wrappedRenderSpace = function () {
        const res = origRenderSpacePosts.apply(this, arguments);
        if (simpleState.enabled && (simpleState.activeScreen === 'SCR-SPC-03' || simpleState.activeScreen === 'SCR-SPC-04' || simpleState.activeScreen === 'SCR-PRF-05')) {
          renderSimpleMode(false);
        }
        return res;
      };
      wrappedRenderSpace._simpleHooked = true;
      window.renderSpacePosts = wrappedRenderSpace;
    }

    const origOpenSpacePostDetail = window.openSpacePostDetail;
    if (typeof origOpenSpacePostDetail === 'function' && !origOpenSpacePostDetail._simpleHooked) {
      const wrappedOpenPostDetail = function (postId) {
        if (simpleState.enabled && postId) {
          navigateToSimpleScreen('SCR-SPC-04', { postId: postId });
          return;
        }
        return origOpenSpacePostDetail.apply(this, arguments);
      };
      wrappedOpenPostDetail._simpleHooked = true;
      window.openSpacePostDetail = wrappedOpenPostDetail;
    }

    // Sync Simple Mode bottom nav immediately when PWA Back Button setting is toggled
    const origToggleBackBtn = window.togglePwaBackButtonSetting;
    if (typeof origToggleBackBtn === 'function' && !origToggleBackBtn._simpleHooked) {
      const wrappedToggleBackBtn = function () {
        const res = origToggleBackBtn.apply(this, arguments);
        if (simpleState.enabled) {
          patchSimpleLiveValuesInPlace();
        }
        return res;
      };
      wrappedToggleBackBtn._simpleHooked = true;
      window.togglePwaBackButtonSetting = wrappedToggleBackBtn;
    }

    // Route hashtag / cashtag / mention clicks inside tweets to Simple Mode search/feed
    const origFilterSpaceByEntity = window.filterSpaceByEntity;
    if (typeof origFilterSpaceByEntity === 'function' && !origFilterSpaceByEntity._simpleHooked) {
      const wrappedFilterEntity = function (entity) {
        if (simpleState.enabled && entity) {
          simpleState.searchBarOpen = true;
          simpleState.searchQuery = String(entity).trim();
          navigateToSimpleScreen('SCR-SPC-03');
          return;
        }
        return origFilterSpaceByEntity.apply(this, arguments);
      };
      wrappedFilterEntity._simpleHooked = true;
      window.filterSpaceByEntity = wrappedFilterEntity;
    }

    // Intercept Pro Mode tab navigation while in Simple Mode and ask for user confirmation
    const origSwitchTab = window.switchTab;
    if (typeof origSwitchTab === 'function' && !origSwitchTab._simpleHooked) {
      window._origSwitchTab = origSwitchTab;
      const wrappedSwitchTab = function (tabId) {
        if (simpleState.enabled && tabId) {
          const cleanTab = String(tabId).trim();
          if (cleanTab === 'cuzdanim') {
            BlocTagSimpleMode.openWalletTab();
            return;
          }
          if (cleanTab === 'para-gonder') {
            navigateToSimpleScreen('SCR-WLT-SEND');
            return;
          }
          if (cleanTab === 'space') {
            navigateToSimpleScreen('SCR-SPC-03');
            return;
          }
          if (cleanTab === 'yeni-cuzdan') {
            BlocTagSimpleMode.startCreateWallet();
            return;
          }
          // Any other Pro Mode page -> ask user before switching out of Simple Mode
          requestSwitchToProMode(cleanTab);
          return;
        }
        return origSwitchTab.apply(this, arguments);
      };
      wrappedSwitchTab._simpleHooked = true;
      window.switchTab = wrappedSwitchTab;
    }

    // Intercept Mobile Menu open in Simple Mode and route to Simple Menu Screen
    const origOpenMobileMenuModal = window.openMobileMenuModal;
    if (typeof origOpenMobileMenuModal === 'function' && !origOpenMobileMenuModal._simpleHooked) {
      const wrappedOpenMobileMenu = function () {
        if (simpleState.enabled) {
          navigateToSimpleScreen('SCR-MNU-07');
          return;
        }
        return origOpenMobileMenuModal.apply(this, arguments);
      };
      wrappedOpenMobileMenu._simpleHooked = true;
      window.openMobileMenuModal = wrappedOpenMobileMenu;
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(initSimpleModeModule, 60));
  } else {
    setTimeout(initSimpleModeModule, 60);
  }
})();
