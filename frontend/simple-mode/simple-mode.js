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

  const simpleState = {
    enabled: false,
    activeScreen: 'SCR-SPC-03', // Default launch screen per Stitch MCP manifest
    screenHistory: ['SCR-SPC-03'],
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
    sendPrefillAmount: ''
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
      'SCR-NTF-06',
      'SCR-MNU-07'
    ];
    const target = valid.includes(screenCode) ? screenCode : 'SCR-SPC-03';

    if (opts.postId !== undefined) {
      simpleState.activePostId = opts.postId;
    }
    if (opts.profileTarget !== undefined) {
      simpleState.profileTarget = opts.profileTarget;
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
      } else if (target === 'SCR-PRF-05') {
        if (typeof window.fetchAndSyncMyBnsHandles === 'function') {
          window.fetchAndSyncMyBnsHandles().then(() => {
            if (simpleState.enabled) renderSimpleMode(false);
          }).catch(() => { });
        }
        const pTarget = simpleState.profileTarget || (getActiveWallet() ? getActiveWallet().address : '');
        if (pTarget && typeof window.apiFetch === 'function') {
          window.apiFetch('/bns/lookup/' + encodeURIComponent(pTarget)).then(({ ok, body }) => {
            if (ok && body && body.data) {
              if (typeof window.currentProfileData !== 'undefined') {
                window.currentProfileData = Object.assign(window.currentProfileData || {}, body.data);
              }
              if (simpleState.enabled) renderSimpleMode(false);
            }
          }).catch(() => { });
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
              <button type="button" aria-label="Geri" onclick="window.BlocTagSimpleMode.back()"
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

            <!-- Notification Bell Icon (Yukarıda Bildirim Butonu) -->
            <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-NTF-06')"
              title="Bildirimler" aria-label="Bildirimler"
              class="relative w-8 h-8 rounded-full bg-surface-container-high hover:bg-surface-variant text-on-surface-variant hover:text-primary flex items-center justify-center active:scale-90 transition-all cursor-pointer shrink-0">
              <span class="material-symbols-outlined notranslate text-[18px]" translate="no">notifications</span>
              ${unread > 0 ? `<span class="absolute -top-1 -right-1 min-w-[15px] h-[15px] px-1 rounded-full bg-rose-500 text-white font-mono text-[9px] font-bold flex items-center justify-center ring-2 ring-surface">${unread}</span>` : ''}
            </button>

            <!-- Compact Icon-Only Simple/Pro Mode Switch Button -->
            <button type="button" onclick="window.BlocTagSimpleMode.requestProMode()"
              title="Pro Moda Geç (Tam Görünüm)" aria-label="Pro Moda Geç"
              class="w-8 h-8 rounded-full bg-primary/15 hover:bg-primary/25 border border-primary/30 text-primary flex items-center justify-center active:scale-90 transition-all cursor-pointer shrink-0">
              <span class="material-symbols-outlined notranslate text-[18px]" translate="no">bolt</span>
            </button>

            <!-- Profile Avatar Pill (Profil dışındaki ekranlarda göster) -->
            ${title !== 'Profil' ? `
              <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-PRF-05', { profileTarget: '' })"
                title="Profilim"
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
    const isProfile = active === 'SCR-PRF-05';
    const isMenu = active === 'SCR-MNU-07';

    return `
      <nav class="simple-bottom-nav" aria-label="Simple Mode Navigation">
        <div class="flex justify-around items-center h-14 px-1.5">
          <!-- 1. Space (Soldan Sağa İlk) -->
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-SPC-03')"
            class="flex flex-col items-center justify-center gap-0.5 flex-1 h-12 transition-colors cursor-pointer ${isSpace ? 'text-primary font-semibold' : 'text-on-surface-variant hover:text-on-surface'}">
            <span class="material-symbols-outlined notranslate text-[22px]" translate="no">tag</span>
            <span class="font-label-sm text-[10px] leading-none">Space</span>
          </button>

          <!-- 2. Cüzdan -->
          <button type="button" onclick="window.BlocTagSimpleMode.openWalletTab()"
            class="flex flex-col items-center justify-center gap-0.5 flex-1 h-12 transition-colors cursor-pointer ${isWallet ? 'text-primary font-semibold' : 'text-on-surface-variant hover:text-on-surface'}">
            <span class="material-symbols-outlined notranslate text-[21px]" translate="no">account_balance_wallet</span>
            <span class="font-label-sm text-[10px] leading-none">Cüzdan</span>
          </button>

          <!-- 3. Profil -->
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-PRF-05', { profileTarget: '' })"
            class="flex flex-col items-center justify-center gap-0.5 flex-1 h-12 transition-colors cursor-pointer ${isProfile ? 'text-primary font-semibold' : 'text-on-surface-variant hover:text-on-surface'}">
            <span class="material-symbols-outlined notranslate text-[21px]" translate="no">person</span>
            <span class="font-label-sm text-[10px] leading-none">Profil</span>
          </button>

          <!-- 4. Menü -->
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-MNU-07')"
            class="flex flex-col items-center justify-center gap-0.5 flex-1 h-12 transition-colors cursor-pointer ${isMenu ? 'text-primary font-semibold' : 'text-on-surface-variant hover:text-on-surface'}">
            <span class="material-symbols-outlined notranslate text-[21px]" translate="no">widgets</span>
            <span class="font-label-sm text-[10px] leading-none font-semibold">Menü</span>
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
            Kripto ve Topluluk <br/>
            <span class="text-primary">Tek Bir Yerde.</span>
          </h1>
          <p class="text-sm text-on-surface-variant max-w-sm leading-relaxed">
            Karmaşık terimler yok. Tek tıkla cüzdan oluşturun, varlıklarınızı yönetin ve Space ile Web3 topluluklarına katılın.
          </p>
        </div>

        <!-- Feature Highlights (Card Stack) -->
        <div class="flex flex-col gap-2.5 mb-4">
          <div class="flex items-start gap-3.5 p-3.5 rounded-2xl bg-surface-container hover:bg-surface-container-high transition-colors">
            <div class="w-10 h-10 rounded-full bg-surface-container-high flex items-center justify-center text-primary shrink-0">
              <span class="material-symbols-outlined notranslate text-[20px]" style="font-variation-settings: 'FILL' 1;" translate="no">lock_open</span>
            </div>
            <div class="flex flex-col min-w-0">
              <h3 class="text-xs font-semibold text-on-surface">Kolay &amp; Güvenli</h3>
              <p class="text-xs text-on-surface-variant mt-0.5 leading-relaxed">
                Kendi anahtarınız, tam kontrolünüz. Aracı kurum veya riskli sunucular olmadan doğrudan cihazınızda saklanır.
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
                <h3 class="text-xs font-semibold text-on-surface">BlocTag Kimliği</h3>
                <span class="px-1.5 py-0.5 rounded-full bg-secondary-container text-on-secondary-container text-[10px] font-bold">Yeni</span>
              </div>
              <p class="text-xs text-on-surface-variant mt-0.5 leading-relaxed">
                Uzun, karmaşık 42 karakterlik adresler yerine sade kullanıcı adınızı kullanın (örn. <span class="text-primary font-medium">@kullanici.bct</span>).
              </p>
            </div>
          </div>

          <div class="flex items-start gap-3.5 p-3.5 rounded-2xl bg-surface-container hover:bg-surface-container-high transition-colors cursor-pointer"
               onclick="window.BlocTagSimpleMode.go('SCR-SPC-03')">
            <div class="w-10 h-10 rounded-full bg-surface-container-high flex items-center justify-center text-primary-fixed shrink-0">
              <span class="material-symbols-outlined notranslate text-[20px]" style="font-variation-settings: 'FILL' 1;" translate="no">groups</span>
            </div>
            <div class="flex flex-col min-w-0">
              <h3 class="text-xs font-semibold text-on-surface">Space Topluluğu</h3>
              <p class="text-xs text-on-surface-variant mt-0.5 leading-relaxed">
                Doğrulanmış token sahipleriyle fikir paylaşın, projeleri keşfedin ve içerik üreticilerini tek tıkla ödüllendirin.
              </p>
            </div>
          </div>
        </div>

        <!-- Interactive Tag Preview Badge -->
        <div class="flex items-center justify-center mb-4">
          <div class="inline-flex items-center gap-2 py-1.5 px-3.5 rounded-full bg-surface-container-low text-on-surface-variant text-xs border border-outline-variant/15 shadow-sm">
            <span class="text-primary font-semibold font-mono">${myHandle ? '@' + esc(myHandle) : '@seninismin.bct'}</span>
            <span class="opacity-40">•</span>
            <span class="text-on-surface">${myHandle ? 'aktif zincir üstü kimliğin' : (acc ? 'cüzdanın bağlı ve aktif' : '+1.00 BCT hoş geldin bonusu hazır')}</span>
          </div>
        </div>

        <!-- Inline Import Box (Toggled by 'BlocTag Bağlan') -->
        ${simpleState.importModeOpen ? `
          <div class="mb-4 p-4 rounded-2xl bg-surface-container-low border border-primary/30 flex flex-col gap-2.5 animate-fadeIn">
            <div class="flex items-center justify-between">
              <span class="text-xs font-semibold text-on-surface flex items-center gap-1.5">
                <span class="material-symbols-outlined notranslate text-primary text-[16px]" translate="no">vpn_key</span>
                <span>12 Kelime veya Özel Anahtar ile Bağlan</span>
              </span>
              <button type="button" onclick="window.BlocTagSimpleMode.toggleImport(false)" class="text-on-surface-variant hover:text-on-surface">
                <span class="material-symbols-outlined notranslate text-[16px]" translate="no">close</span>
              </button>
            </div>
            <textarea id="simpleImportInput" rows="3"
              placeholder="12 kurtarma kelimenizi veya 64 haneli özel anahtarınızı girin..."
              class="w-full bg-surface-container rounded-xl p-3 text-xs font-mono text-on-surface placeholder:text-outline/60 border border-outline-variant/20 focus:border-primary focus:outline-none resize-none"></textarea>
            <button type="button" onclick="window.BlocTagSimpleMode.submitImport()"
              class="w-full h-11 rounded-full bg-primary text-on-primary text-xs font-semibold flex items-center justify-center gap-1.5 shadow-md active:scale-98 transition-all cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[17px]" translate="no">login</span>
              <span>Cüzdanı Geri Yükle ve Bağlan</span>
            </button>
          </div>
        ` : ''}

        <!-- Action CTA Area -->
        <div class="flex flex-col gap-2.5 w-full mt-auto">
          <button type="button" onclick="window.BlocTagSimpleMode.startCreateWallet()"
            class="w-full h-[50px] rounded-full bg-primary-container text-on-primary-container text-sm font-semibold flex items-center justify-center gap-2 shadow-md active:scale-[0.98] transition-all cursor-pointer">
            <span>Cüzdan Aç (+1.00 BCT Bonus)</span>
            <span class="material-symbols-outlined notranslate text-[18px]" translate="no">arrow_forward</span>
          </button>

          <button type="button" onclick="window.BlocTagSimpleMode.toggleImport()"
            class="w-full h-[50px] rounded-full bg-surface-container-high hover:bg-surface-bright text-on-surface text-sm font-medium flex items-center justify-center gap-2 active:scale-[0.98] transition-all cursor-pointer">
            <span class="material-symbols-outlined notranslate text-[18px] text-primary" translate="no">wallet</span>
            <span>${acc ? 'Mevcut Cüzdana Git (' + esc(getDisplayHandleOrAddr(acc.address, myHandle)) + ')' : 'Mevcut Cüzdanla Bağlan'}</span>
          </button>
        </div>

        <!-- Bottom Trust & Security Footnote -->
        <div class="flex items-center justify-center gap-1.5 pt-3 text-on-surface-variant/70 mt-2">
          <span class="material-symbols-outlined notranslate text-[14px] text-primary" translate="no">verified_user</span>
          <span class="text-[11px] tracking-wide">Uçtan Uca Şifreli • Non-Custodial Güvenlik</span>
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
      ${renderTopBar('Kurtarma Anahtarı', true)}
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
              <h2 class="text-base font-semibold text-on-surface">Cüzdan Anahtarlarınız</h2>
              <p class="text-xs text-on-surface-variant leading-snug">
                Bu 12 kelime cüzdanınızın tek şifresidir. Güvenli bir yere not edin ve kimseyle paylaşmayın.
              </p>
            </div>
          </div>

          <!-- Security Tip Pill -->
          <div class="flex items-center justify-between px-3.5 py-2 rounded-full bg-surface-container text-on-surface-variant text-xs">
            <div class="flex items-center gap-1.5">
              <span class="material-symbols-outlined notranslate text-primary text-[16px]" translate="no">visibility_off</span>
              <span>Etrafınızda kimsenin izlemediğinden emin olun</span>
            </div>
            <span class="text-primary text-[10px] font-bold uppercase tracking-wider">Gizli</span>
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
                  <span class="text-xs font-medium" id="simple-copy-seed-text">Kelimeleri Kopyala</span>
                </button>
                <button type="button" onclick="window.BlocTagSimpleMode.refreshSeed()" title="Yeni Kelime Üret"
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
              <span class="text-xs font-semibold text-on-surface">Tavsiye Edilen Yöntem</span>
              <span class="text-xs text-on-surface-variant leading-relaxed">
                Kelimeleri tercihen fiziksel bir kağıda yazın ve güvenli bir yerde saklayın. Ekran görüntüsü almaktan kaçının.
              </span>
            </div>
          </div>

          <!-- Custom Animated Switch Confirmation -->
          <div class="flex items-center justify-between p-3.5 rounded-2xl bg-surface-container-low border border-outline-variant/15 select-none cursor-pointer"
               onclick="window.BlocTagSimpleMode.toggleSeedSaved()">
            <div class="flex flex-col pr-3">
              <span class="text-xs font-semibold text-on-surface">Kelimelerimi güvenli bir yere kaydettim</span>
              <span class="text-[11px] text-on-surface-variant/80">Kurtarma kelimelerim olmadan hesabıma erişemem</span>
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
              <span>Cüzdanı Başlat &amp; Space'e Git (+1.00 BCT)</span>
              <span class="material-symbols-outlined notranslate text-[20px]" translate="no">arrow_forward</span>
            </button>
            <p class="text-center text-[11px] text-on-surface-variant/60">
              Merkeziyetsiz ve bağımsız mülkiyet protokolü
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
      ${renderTopBar('Cüzdanım', false, addressPillHtml)}
      <main class="flex-1 flex flex-col w-full px-5 pt-3 pb-24 simple-screen-animate">
        <!-- Net Portfolio Hero (Exact Stitch Cüzdanım ve Geçmiş Mobil) -->
        <div class="flex flex-col items-center justify-center pt-4 pb-5 text-center">
          <div class="flex items-center gap-1.5 mb-1">
            <span class="text-[11px] font-semibold text-on-surface-variant uppercase tracking-wider">Net Portföy Değeri</span>
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
            <span>Gönder</span>
          </button>
          <button type="button" onclick="if(typeof openReceiveModal==='function') openReceiveModal();"
            class="flex items-center justify-center gap-2 h-[50px] bg-surface-container-high hover:bg-surface-bright text-on-surface rounded-full text-sm font-semibold active:scale-[0.98] transition-all cursor-pointer">
            <span class="material-symbols-outlined notranslate text-[20px]" translate="no">arrow_downward</span>
            <span>Al (QR)</span>
          </button>
        </div>

        <!-- Quick Utility Chips (PIN Vault, Yeni Cüzdan, BNS) -->
        <div class="grid grid-cols-3 gap-2 mb-5">
          <button type="button" onclick="if(typeof openWalletVaultModal==='function') openWalletVaultModal();"
            class="p-2.5 rounded-2xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/15 flex flex-col items-center gap-1 text-center transition-colors cursor-pointer">
            <span class="material-symbols-outlined notranslate text-primary text-[18px]" translate="no">shield_lock</span>
            <span class="text-[11px] font-medium text-on-surface">PIN Kasası</span>
          </button>
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-ONB-01')"
            class="p-2.5 rounded-2xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/15 flex flex-col items-center gap-1 text-center transition-colors cursor-pointer">
            <span class="material-symbols-outlined notranslate text-secondary text-[18px]" translate="no">add_circle</span>
            <span class="text-[11px] font-medium text-on-surface">Cüzdan Değiştir</span>
          </button>
          <button type="button" onclick="if(typeof openNetworkSecurityModal==='function') openNetworkSecurityModal();"
            class="p-2.5 rounded-2xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/15 flex flex-col items-center gap-1 text-center transition-colors cursor-pointer">
            <span class="material-symbols-outlined notranslate text-emerald-400 text-[18px]" translate="no">verified_user</span>
            <span class="text-[11px] font-medium text-on-surface">Ağ Güvenliği</span>
          </button>
        </div>

        <!-- İşlem Geçmişi Section -->
        <div class="flex flex-col w-full">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-base font-semibold text-on-surface">İşlem Geçmişi</h2>
            <button type="button" onclick="if(typeof refreshCurrentAccountBalance==='function') refreshCurrentAccountBalance(); if(typeof refreshPersonalTransactions==='function') refreshPersonalTransactions().then(()=>window.BlocTagSimpleMode.refresh());"
              class="w-8 h-8 rounded-full bg-surface-container-low flex items-center justify-center text-on-surface-variant hover:text-primary transition-colors cursor-pointer" title="Yenile">
              <span class="material-symbols-outlined notranslate text-[18px]" translate="no">sync</span>
            </button>
          </div>

          <!-- Filter Pills (Tümü, Gelenler, Gidenler) -->
          <div class="flex items-center gap-1 p-1 bg-surface-container-low rounded-full mb-3.5">
            <button type="button" onclick="window.BlocTagSimpleMode.setTxFilter('all')"
              class="flex-1 py-1.5 px-3 rounded-full text-center text-xs transition-all cursor-pointer ${simpleState.txFilter === 'all' ? 'bg-surface-container-high text-on-surface font-semibold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}">
              Tümü
            </button>
            <button type="button" onclick="window.BlocTagSimpleMode.setTxFilter('incoming')"
              class="flex-1 py-1.5 px-3 rounded-full text-center text-xs transition-all cursor-pointer ${simpleState.txFilter === 'incoming' ? 'bg-surface-container-high text-on-surface font-semibold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}">
              Gelenler
            </button>
            <button type="button" onclick="window.BlocTagSimpleMode.setTxFilter('outgoing')"
              class="flex-1 py-1.5 px-3 rounded-full text-center text-xs transition-all cursor-pointer ${simpleState.txFilter === 'outgoing' ? 'bg-surface-container-high text-on-surface font-semibold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}">
              Gidenler
            </button>
          </div>

          <!-- Transactions Stream -->
          <div class="flex flex-col gap-2 w-full">
            ${filteredTxs.length === 0 ? `
              <div class="p-6 rounded-2xl bg-surface-container-low text-center text-xs text-on-surface-variant">
                Bu filtrede henüz işlem bulunmuyor.
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
                      <span class="text-[10px] text-on-surface-variant">${tx.status === 'mempool' ? 'Mempool' : 'Onaylandı'}</span>
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
      ${renderTopBar('Kripto Gönder', true)}
      <main class="flex-1 flex flex-col w-full px-5 pt-2 pb-24 simple-screen-animate">
        <div class="flex items-center justify-between py-2">
          <div class="flex flex-col">
            <span class="text-[10px] text-outline uppercase tracking-wider font-mono">İşlem</span>
            <h1 class="text-xl font-semibold text-on-surface">BCT Gönder</h1>
          </div>
          <div class="flex items-center gap-1.5 bg-surface-container-high px-2.5 py-1 rounded-full text-on-surface-variant text-[11px]">
            <span class="w-1.5 h-1.5 rounded-full bg-primary animate-ping"></span>
            <span>Hızlı Mod</span>
          </div>
        </div>

        <!-- Asset Selector Chip -->
        <section class="flex flex-col gap-1.5 mt-1">
          <div class="flex items-center justify-between px-1">
            <span class="text-xs text-on-surface-variant font-medium">Aktif Varlık</span>
            <span class="text-xs text-primary font-mono">Kullanılabilir: ${esc(balStr)} BCT</span>
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
            <span>Net Alıcıya Geçen:</span>
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
              class="py-2 rounded-full bg-surface-container-highest text-primary text-xs font-semibold active:scale-95 transition-all cursor-pointer">Tümü</button>
          </div>
        </section>

        <!-- Recipient Input -->
        <section class="flex flex-col gap-1.5 mb-3">
          <label class="text-xs text-on-surface-variant font-medium px-1" for="simple-send-recipient">Alıcı Adresi veya @isim.bct</label>
          <div class="flex items-center bg-surface-container-low rounded-2xl px-3.5 py-3 border border-outline-variant/15 focus-within:border-primary transition-colors">
            <span class="material-symbols-outlined notranslate text-outline text-[20px] mr-2" translate="no">alternate_email</span>
            <input id="simple-send-recipient" type="text" autocomplete="off" spellcheck="false"
              value="${esc(preRec)}"
              placeholder="BCT... veya kullanici.bct"
              class="bg-transparent flex-1 text-xs font-mono text-on-surface placeholder:text-outline/60 focus:outline-none min-w-0" />
            <div class="flex items-center gap-1.5 shrink-0 ml-2">
              <button type="button" onclick="window.BlocTagSimpleMode.pasteRecipient()"
                class="flex items-center gap-1 bg-surface-container-highest px-2.5 py-1 rounded-full text-on-surface text-[11px] font-medium hover:brightness-110 active:scale-95 transition-all cursor-pointer">
                <span class="material-symbols-outlined notranslate text-[13px]" translate="no">content_paste</span>
                <span>Yapıştır</span>
              </button>
              <button type="button" onclick="if(typeof openQrScannerModal==='function') openQrScannerModal();"
                class="w-8 h-8 rounded-full bg-surface-container-highest flex items-center justify-center text-on-surface hover:brightness-110 active:scale-95 transition-all cursor-pointer" title="QR Tara">
                <span class="material-symbols-outlined notranslate text-[17px]" translate="no">qr_code_scanner</span>
              </button>
            </div>
          </div>
        </section>

        <!-- Fee Info -->
        <div class="flex items-center justify-between bg-surface-container-low/50 px-4 py-2.5 rounded-2xl mb-5 text-on-surface-variant text-xs">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined notranslate text-[17px] text-primary" translate="no">local_gas_station</span>
            <span>Ağ Ücreti (%1 Protokol):</span>
            <span class="text-on-surface font-mono font-medium" id="simple-send-fee-preview">0.00 BCT</span>
          </div>
          <div class="flex items-center gap-1">
            <span class="w-1.5 h-1.5 rounded-full bg-primary"></span>
            <span class="text-[11px]">Anlık Onay</span>
          </div>
        </div>

        <!-- Submit Button -->
        <div class="flex flex-col gap-2 mt-auto">
          <button type="button" id="simple-send-submit-btn" onclick="window.BlocTagSimpleMode.executeSend()"
            class="w-full h-[52px] rounded-full bg-primary text-on-primary text-base font-semibold flex items-center justify-center gap-2 shadow-lg active:scale-[0.98] transition-transform cursor-pointer">
            <span>Devam Et ve İmzala</span>
            <span class="material-symbols-outlined notranslate text-[20px]" translate="no">arrow_forward</span>
          </button>
          <div class="flex items-center justify-center gap-3 py-1 text-outline text-[11px]">
            <span class="flex items-center gap-1">
              <span class="material-symbols-outlined notranslate text-[14px] text-primary" translate="no">verified_user</span>
              <span>Uçtan Uca ECDSA İmzalı</span>
            </span>
            <span>•</span>
            <span class="flex items-center gap-1">
              <span class="material-symbols-outlined notranslate text-[14px] text-primary" translate="no">timer</span>
              <span>Anlık Blok Kaydı</span>
            </span>
          </div>
        </div>
      </main>
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

    return `
      ${renderTopBar('Space', false)}
      <main class="flex-1 flex flex-col w-full px-4 pt-2 pb-24 simple-screen-animate">
        <!-- Community Space Sub-Header & Live Status (Exact Stitch SCR-SPC-03) -->
        <div class="flex items-center justify-between py-2">
          <div class="flex items-center gap-2.5 min-w-0 cursor-pointer"
               onclick="window.BlocTagSimpleMode.go('${acc ? 'SCR-PRF-05' : 'SCR-ONB-01'}', { profileTarget: '' })">
            <div class="relative shrink-0">
              <div class="w-10 h-10 rounded-full bg-surface-container-high flex items-center justify-center overflow-hidden">
                <span class="material-symbols-outlined notranslate text-primary text-[22px]" translate="no">account_circle</span>
              </div>
              <span class="absolute bottom-0 right-0 w-3 h-3 rounded-full bg-primary ring-2 ring-surface"></span>
            </div>
            <div class="flex flex-col min-w-0">
              <div class="flex items-center gap-1.5">
                <span class="text-base font-semibold text-on-surface">Space</span>
                <span class="px-2 py-0.5 rounded-full bg-surface-container-high text-primary font-mono text-[11px] font-semibold truncate max-w-[150px]">
                  ${esc(displayTag)}
                </span>
              </div>
              <span id="simple-space-bal-subtitle" class="text-[11px] text-on-surface-variant truncate">
                ${acc ? (typeof window.formatBct === 'function' ? window.formatBct(acc.balance || 0, 2) + ' BCT • Zincir Üstü Aktif' : 'Zincir Üstü Aktif') : 'Cüzdan oluşturun (+1.00 BCT bonus)'}
              </span>
            </div>
          </div>

          <div class="flex items-center gap-1.5 shrink-0">
            <button type="button" aria-label="Bildirimler" onclick="window.BlocTagSimpleMode.go('SCR-NTF-06')"
              class="w-9 h-9 rounded-full bg-surface-container-low flex items-center justify-center text-on-surface-variant hover:text-primary transition-colors active:scale-95 cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[20px]" translate="no">notifications</span>
            </button>
            <button type="button" aria-label="Arama" onclick="window.BlocTagSimpleMode.toggleSearch()"
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
              placeholder="Gönderi, #etiket veya @kullanici ara..."
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
                placeholder="Bir şeyler paylaş... (0.10 BCT)"
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
                  Paylaş
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Segmented Feed Switcher (Hepsi / Takip Edilenler) -->
        <div class="flex p-1 bg-surface-container-low rounded-full mt-3 border border-outline-variant/10">
          <button type="button" onclick="window.BlocTagSimpleMode.setFeedFilter('all')"
            class="flex-1 text-center rounded-full text-xs font-medium transition-all py-1.5 cursor-pointer ${simpleState.feedFilter === 'all' ? 'bg-surface-container text-on-surface font-semibold shadow-xs' : 'text-on-surface-variant hover:text-on-surface'}">
            Hepsi
          </button>
          <button type="button" onclick="window.BlocTagSimpleMode.setFeedFilter('following')"
            class="flex-1 text-center rounded-full text-xs font-medium transition-all py-1.5 cursor-pointer ${simpleState.feedFilter === 'following' ? 'bg-surface-container text-on-surface font-semibold shadow-xs' : 'text-on-surface-variant hover:text-on-surface'}">
            Doğrulanmış &amp; Takip
          </button>
        </div>

        <!-- Feed List Stream (Exact Stitch Post Cards) -->
        <div class="flex flex-col gap-2.5 mt-3 w-full min-w-0" id="simple-feed-container">
          ${filteredPosts.length === 0 ? `
            <div class="p-8 rounded-2xl bg-surface-container-low text-center flex flex-col items-center gap-2 text-on-surface-variant">
              <span class="material-symbols-outlined notranslate text-[28px] text-primary" translate="no">forum</span>
              <span class="text-xs">Gönderiler yükleniyor veya bu filtrede gönderi yok...</span>
            </div>
          ` : filteredPosts.slice(0, 35).map(post => renderSimplePostCard(post, acc)).join('')}
        </div>

        <!-- Floating Action Button (+ Yaz) -->
        <div class="fixed z-40" style="bottom: calc(var(--simple-bottom-nav-h, 64px) + 14px); right: max(16px, calc(50% - 224px));">
          <button type="button" onclick="window.BlocTagSimpleMode.focusComposer()"
            class="h-11 px-4 rounded-full bg-primary text-on-primary text-xs font-semibold flex items-center gap-1.5 shadow-[0_8px_20px_rgba(16,185,129,0.35)] hover:scale-105 active:scale-95 transition-all cursor-pointer">
            <span class="material-symbols-outlined notranslate text-[18px]" translate="no">edit</span>
            <span>Yaz</span>
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

    return `
      <article onclick="window.BlocTagSimpleMode.go('SCR-SPC-04', { postId: '${pid}' })"
        class="simple-post-card bg-surface-container-low rounded-2xl shadow-sm transition-all hover:bg-surface-container p-3.5 border border-outline-variant/10 cursor-pointer">
        <div class="flex items-center justify-between gap-2 min-w-0">
          <div class="flex items-center gap-2.5 min-w-0 flex-1"
               onclick="event.stopPropagation(); window.BlocTagSimpleMode.go('SCR-PRF-05', { profileTarget: '${profileTargetAttr}' })">
            <div class="w-10 h-10 rounded-full bg-surface-container-high overflow-hidden flex items-center justify-center text-primary shrink-0">
              <span class="material-symbols-outlined notranslate text-[21px]" translate="no">person</span>
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-1 min-w-0">
                <span class="text-xs font-semibold text-on-surface truncate">${esc(displayName)}</span>
                <span class="material-symbols-outlined notranslate text-primary text-[15px] shrink-0" style="font-variation-settings: 'FILL' 1;" translate="no">verified</span>
              </div>
              <span class="text-[11px] text-on-surface-variant truncate block">${esc(subHandle)} • ${esc(timeAgo)}</span>
            </div>
          </div>
          <button type="button" aria-label="Paylaş"
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
            <span class="text-[11px] font-semibold">Bahşiş</span>
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
        ${renderTopBar('Gönderi Detayı', true)}
        <main class="flex-1 flex flex-col items-center justify-center p-6 text-center simple-screen-animate">
          <p class="text-xs text-on-surface-variant mb-3">Gönderi bulunamadı veya yükleniyor.</p>
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-SPC-03')"
            class="px-4 py-2 rounded-full bg-primary text-on-primary text-xs font-semibold cursor-pointer">
            Space Akışına Dön
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
      ${renderTopBar('Gönderi Detayı', true)}
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
              <span class="text-[11px] text-on-surface-variant font-medium">Blok #${esc(post.block_index ?? '--')}</span>
            </div>
          </div>

          <!-- Metrics Strip -->
          <div class="flex items-center justify-between py-2.5 px-3.5 rounded-xl bg-surface-container-low text-xs">
            <div class="flex items-center gap-1.5">
              <span class="font-semibold text-on-surface tabular-nums">${likesCount}</span>
              <span class="text-on-surface-variant">Beğeni</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="font-semibold text-on-surface tabular-nums">${comments.length}</span>
              <span class="text-on-surface-variant">Yorum</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="font-semibold text-primary font-mono tabular-nums">+${typeof window.formatBct === 'function' ? window.formatBct(earned, 3) : earned.toFixed(3)} BCT</span>
              <span class="text-on-surface-variant">Telif</span>
            </div>
          </div>

          <!-- 4-Action Cluster -->
          <div class="grid grid-cols-4 gap-1.5 pt-1">
            <button type="button" onclick="window.BlocTagSimpleMode.likePost('${pid}', event)"
              class="flex flex-col items-center justify-center gap-1 py-2 rounded-xl bg-surface-container-high hover:bg-surface-container-highest transition-all active:scale-95 cursor-pointer ${isLiked ? 'text-tertiary font-semibold' : 'text-on-surface-variant'}">
              <span class="material-symbols-outlined notranslate text-[19px]" ${isLiked ? 'style="font-variation-settings: \'FILL\' 1;"' : ''} translate="no">favorite</span>
              <span class="text-[10.5px]">Beğen</span>
            </button>
            <button type="button" onclick="document.getElementById('simple-comment-input')?.focus()"
              class="flex flex-col items-center justify-center gap-1 py-2 rounded-xl bg-surface-container-high hover:bg-surface-container-highest text-on-surface-variant hover:text-primary transition-all active:scale-95 cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[19px]" translate="no">chat_bubble</span>
              <span class="text-[10.5px]">Yorum</span>
            </button>
            <button type="button" onclick="if(typeof openPostShareModal==='function') openPostShareModal('${pid}', event);"
              class="flex flex-col items-center justify-center gap-1 py-2 rounded-xl bg-surface-container-high hover:bg-surface-container-highest text-on-surface-variant hover:text-primary transition-all active:scale-95 cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[19px]" translate="no">repeat</span>
              <span class="text-[10.5px]">Paylaş</span>
            </button>
            <button type="button" onclick="window.BlocTagSimpleMode.tipAuthor('${escAttr(authorAddr)}')"
              class="flex flex-col items-center justify-center gap-1 py-2 rounded-xl bg-surface-container-high hover:bg-surface-container-highest text-primary transition-all active:scale-95 cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[19px]" style="font-variation-settings: 'FILL' 1;" translate="no">payments</span>
              <span class="text-[10.5px] font-semibold">Bahşiş</span>
            </button>
          </div>
        </section>

        <!-- Comments Section Header -->
        <div class="flex items-center justify-between pt-4 pb-2 px-1">
          <div class="flex items-center gap-2">
            <h2 class="text-sm font-semibold text-on-surface">Yorumlar</h2>
            <span class="px-2 py-0.5 rounded-full bg-surface-container text-on-surface-variant text-xs font-semibold">${comments.length}</span>
          </div>
          <span class="text-[11px] text-primary">+0.004 BCT Yazar Telifi</span>
        </div>

        <!-- Comments List -->
        <section class="flex flex-col gap-2">
          ${comments.length === 0 ? `
            <div class="p-6 rounded-2xl bg-surface-container-low text-center text-xs text-on-surface-variant">
              İlk zincir üstü yorumu aşağıdan siz yazın!
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
                    class="text-[11px] text-primary hover:underline font-medium cursor-pointer shrink-0">Bahşiş</button>
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
              placeholder="Düşünceni yaz... (0.02 BCT)"
              class="flex-1 bg-transparent text-xs text-on-surface placeholder:text-outline focus:outline-none px-1.5 min-w-0" />
            <button type="submit" id="simple-comment-submit-btn"
              class="h-8 px-3.5 rounded-full bg-primary-container text-on-primary text-xs font-semibold flex items-center justify-center gap-1 hover:brightness-95 active:scale-95 transition-all shrink-0 cursor-pointer">
              <span>Gönder</span>
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
    const targetAddr = isMyProfile ? (acc ? acc.address : '') : targetRaw;
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
      : (userPosts.find(p => p.author_bns && p.author_bns !== 'anonymous')?.author_bns || (targetRaw.endsWith('.bct') ? targetRaw : ''));
    const resolvedAddress = isMyProfile
      ? (acc ? acc.address : '')
      : (userPosts[0]?.author || targetRaw);

    const resolvedTitleHandle = resolvedBns ? ('@' + resolvedBns.replace(/^@/, '')) : (typeof window.shortAddr === 'function' ? window.shortAddr(resolvedAddress) : resolvedAddress);
    const displayTitle = resolvedTitleHandle;
    const shortWallet = typeof window.shortAddr === 'function' ? window.shortAddr(resolvedAddress) : resolvedAddress;
    const totalLikesReceived = userPosts.reduce((accSum, p) => accSum + Number(p.likes_count || (p.likes ? p.likes.length : 0)), 0);
    const totalRoyalties = userPosts.reduce((accSum, p) => accSum + Number(p.author_earnings || 0), 0);

    // Follower & Following metrics
    let followersCount = 0;
    let followingCount = 0;
    if (typeof currentProfileData !== 'undefined' && currentProfileData &&
      String(currentProfileData.address || '').toLowerCase() === resolvedAddress.toLowerCase()) {
      followersCount = Number(currentProfileData.followers_count || (Array.isArray(currentProfileData.followers) ? currentProfileData.followers.length : 0));
      followingCount = Number(currentProfileData.following_count || (Array.isArray(currentProfileData.following) ? currentProfileData.following.length : 0));
    }

    // Owned BNS handles for current user
    const myOwnedHandles = isMyProfile ? getMyOwnedBnsHandles() : [];

    const expandTopBarHtml = `
      <button type="button" onclick="window.BlocTagSimpleMode.openDetailedProProfile('${escAttr(resolvedBns || resolvedAddress)}')"
        title="Detaylı Pro Görünüme Geç" aria-label="Genişlet"
        class="w-8 h-8 rounded-full bg-surface-container-high hover:bg-primary/20 text-on-surface hover:text-primary flex items-center justify-center active:scale-90 transition-all cursor-pointer shrink-0">
        <span class="material-symbols-outlined notranslate text-[18px]" translate="no">open_in_full</span>
      </button>
    `;

    return `
      ${renderTopBar('Profil', !isMyProfile, expandTopBarHtml)}
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
            <div class="relative shrink-0">
              <div class="w-20 h-20 rounded-full p-1 bg-surface shadow-xl ring-2 ring-surface">
                <div class="w-full h-full rounded-full overflow-hidden bg-surface-container-high flex items-center justify-center text-primary font-mono font-bold text-2xl">
                  ${resolvedBns ? esc(resolvedBns.replace(/^@/, '')[0].toUpperCase()) : '<span class="material-symbols-outlined notranslate text-[36px]" translate="no">person</span>'}
                </div>
              </div>
              <div class="absolute bottom-1 right-1 w-4 h-4 rounded-full bg-surface p-0.5 flex items-center justify-center">
                <div class="w-full h-full rounded-full bg-primary"></div>
              </div>
            </div>

            <!-- Profile Action Buttons -->
            <div class="flex items-center gap-1.5 pb-1 flex-wrap justify-end">
              ${isMyProfile ? `
                <button type="button" onclick="if(typeof openWalletVaultModal==='function') openWalletVaultModal();"
                  class="h-8.5 px-3 rounded-full bg-surface-container-high hover:bg-surface-container-highest text-on-surface text-xs font-medium transition-all active:scale-95 flex items-center gap-1 cursor-pointer">
                  <span class="material-symbols-outlined notranslate text-[15px]" translate="no">tune</span>
                  <span>Güvenlik</span>
                </button>
              ` : `
                <!-- Takip Et Butonu (Diğer profiller için) -->
                <button type="button" id="simple-profile-follow-btn"
                  onclick="window.BlocTagSimpleMode.followProfileAuthor('${escAttr(resolvedAddress)}', '${escAttr(resolvedBns)}')"
                  class="h-8.5 px-3 rounded-full bg-primary text-on-primary text-xs font-bold transition-all active:scale-95 flex items-center gap-1 shadow-sm cursor-pointer hover:brightness-95">
                  <span class="material-symbols-outlined notranslate text-[15px]" translate="no">person_add</span>
                  <span>Takip Et</span>
                </button>

                <button type="button" onclick="window.BlocTagSimpleMode.tipAuthor('${escAttr(resolvedAddress)}')"
                  class="h-8.5 px-2.5 rounded-full bg-surface-container-high hover:bg-surface-container-highest text-on-surface text-xs font-medium transition-all active:scale-95 flex items-center gap-1 cursor-pointer">
                  <span class="material-symbols-outlined notranslate text-[15px] text-primary" translate="no">volunteer_activism</span>
                  <span>Bahşiş</span>
                </button>
              `}

              <!-- Genişletme İkonu: Tıklandığında Detaylı Pro Moda Geçilir -->
              <button type="button" onclick="window.BlocTagSimpleMode.openDetailedProProfile('${escAttr(resolvedBns || resolvedAddress)}')"
                title="Detaylı Pro Görünüme Geç" aria-label="Genişlet"
                class="w-8.5 h-8.5 rounded-full bg-surface-container-high hover:bg-primary/20 text-on-surface hover:text-primary border border-outline-variant/20 flex items-center justify-center transition-all active:scale-90 cursor-pointer shrink-0">
                <span class="material-symbols-outlined notranslate text-[18px]" translate="no">open_in_full</span>
              </button>
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
              <button type="button" onclick="if(typeof copyText==='function') copyText('${escAttr(resolvedBns ? ('@' + resolvedBns.replace(/^@/, '')) : resolvedAddress)}', 'Kimlik kopyalandı!');"
                class="group flex items-center gap-1 text-on-surface-variant hover:text-on-surface transition-colors cursor-pointer">
                <span class="text-xs text-primary font-mono font-medium">${esc(resolvedBns ? '@' + resolvedBns.replace(/^@/, '') : shortWallet)}</span>
                <span class="material-symbols-outlined notranslate text-[14px] text-outline group-hover:text-primary" translate="no">content_copy</span>
              </button>
              <span class="w-1 h-1 rounded-full bg-outline-variant"></span>
              <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface-container text-primary text-[10.5px] font-medium">
                <span class="w-1.5 h-1.5 rounded-full bg-primary"></span>
                <span>Aktif L1</span>
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
              <button type="button" onclick="if(typeof copyText==='function') copyText('${escAttr(resolvedAddress)}', 'Cüzdan adresi kopyalandı!');"
                class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-surface-container-low hover:bg-surface-container text-on-surface-variant transition-all active:scale-95 cursor-pointer border border-outline-variant/15">
                <span class="material-symbols-outlined notranslate text-[15px] text-primary" translate="no">account_balance_wallet</span>
                <span class="text-xs tracking-wider font-mono">${esc(shortWallet)}</span>
                <span class="material-symbols-outlined notranslate text-[13px]" translate="no">file_copy</span>
              </button>
            </div>

            <!-- BNS Handle Selector & Switcher (Kendi Profilinizdeyken Alınmış İsimleri Seçme ve Değiştirme) -->
            ${isMyProfile ? `
              <div class="mt-3.5 p-3 rounded-2xl bg-surface-container-low border border-outline-variant/15 shadow-sm">
                <div class="flex items-center justify-between mb-2">
                  <div class="flex items-center gap-1.5">
                    <span class="material-symbols-outlined notranslate text-primary text-[17px]" translate="no">badge</span>
                    <span class="text-xs font-bold text-on-surface">Kayıtlı BNS İsimleriniz (.bct)</span>
                  </div>
                  <span class="text-[10px] text-on-surface-variant font-mono">${myOwnedHandles.length} isim</span>
                </div>

                ${myOwnedHandles.length > 0 ? `
                  <p class="text-[11px] text-on-surface-variant mb-2 leading-relaxed">
                    Profilinizde ve paylaşımlarınızda görünecek aktif kimliğinizi seçin:
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
                          ${isCurrent ? '<span class="text-[9px] opacity-90 font-sans font-normal">(Aktif)</span>' : ''}
                        </button>
                      `;
                    }).join('')}
                  </div>
                ` : `
                  <div class="flex items-center justify-between gap-3 pt-0.5">
                    <p class="text-[11px] text-on-surface-variant leading-relaxed">
                      Henüz bir .bct alan adı almadınız. Cüzdan adresiniz yerine havalı bir isim kullanın.
                    </p>
                    <button type="button" onclick="if(typeof openBnsRegisterModal==='function') openBnsRegisterModal(); else window.BlocTagSimpleMode.requestProMode('bns');"
                      class="px-3 py-1 rounded-full bg-primary/15 hover:bg-primary/25 border border-primary/30 text-primary text-[11px] font-semibold shrink-0 cursor-pointer active:scale-95 transition-all">
                      İsim Al
                    </button>
                  </div>
                `}
              </div>
            ` : ''}

            <!-- Bio Statement -->
            <p class="text-xs text-on-surface/90 leading-relaxed mt-2.5">
              Doğrulanmış BlocTag Space üreticisi ✦ Sansüre dayanıklı Layer-1 blokzincir üzerinde içerik paylaşıyor ve anlık telif kazanıyor.
            </p>

            <!-- Metrics 4-Col Grid (Gönderi, Beğeni, Takipçi, Takip) -->
            <div class="grid grid-cols-4 gap-2 mt-3.5">
              <div class="flex flex-col items-center justify-center py-2 px-1 rounded-xl bg-surface-container-low border border-outline-variant/10 text-center">
                <span class="font-bold text-on-surface font-mono text-sm">${userPosts.length}</span>
                <span class="text-[10.5px] text-on-surface-variant mt-0.5">Gönderi</span>
              </div>
              <div class="flex flex-col items-center justify-center py-2 px-1 rounded-xl bg-surface-container-low border border-outline-variant/10 text-center">
                <span class="font-bold text-on-surface font-mono text-sm">${totalLikesReceived}</span>
                <span class="text-[10.5px] text-on-surface-variant mt-0.5">Beğeni</span>
              </div>
              <div class="flex flex-col items-center justify-center py-2 px-1 rounded-xl bg-surface-container-low border border-outline-variant/10 text-center cursor-pointer group active:scale-95 transition-transform"
                   onclick="window.BlocTagSimpleMode.openFollowersList('${escAttr(resolvedAddress)}', 'followers')"
                   title="Takipçileri Görüntüle">
                <span class="font-bold text-emerald-400 font-mono text-sm group-hover:underline" id="simple-profile-followers-count">${followersCount}</span>
                <span class="text-[10.5px] text-on-surface-variant group-hover:text-emerald-400 transition-colors mt-0.5">Takipçi</span>
              </div>
              <div class="flex flex-col items-center justify-center py-2 px-1 rounded-xl bg-surface-container-low border border-outline-variant/10 text-center cursor-pointer group active:scale-95 transition-transform"
                   onclick="window.BlocTagSimpleMode.openFollowersList('${escAttr(resolvedAddress)}', 'following')"
                   title="Takip Edilenleri Görüntüle">
                <span class="font-bold text-on-surface font-mono text-sm group-hover:underline" id="simple-profile-following-count">${followingCount}</span>
                <span class="text-[10.5px] text-on-surface-variant group-hover:text-on-surface transition-colors mt-0.5">Takip</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Space Minimal Segmented Nav -->
        <div class="px-5 mt-4">
          <div class="w-full flex items-center justify-between bg-surface-container-lowest rounded-full p-1 border border-outline-variant/15">
            <button type="button" onclick="window.BlocTagSimpleMode.setProfileTab('posts')"
              class="flex-1 py-1.5 text-center rounded-full text-xs transition-all cursor-pointer ${simpleState.profileTab === 'posts' ? 'bg-surface-container text-primary font-semibold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}">
              Gönderiler
            </button>
            <button type="button" onclick="window.BlocTagSimpleMode.setProfileTab('likes')"
              class="flex-1 py-1.5 text-center rounded-full text-xs transition-all cursor-pointer ${simpleState.profileTab === 'likes' ? 'bg-surface-container text-primary font-semibold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}">
              Popüler
            </button>
          </div>
        </div>

        <!-- User Content Stream -->
        <div class="px-5 flex flex-col mt-3 gap-2.5">
          ${userPosts.length === 0 ? `
            <div class="p-6 rounded-2xl bg-surface-container-low text-center text-xs text-on-surface-variant">
              Henüz zincir üstü gönderi paylaşılmamış.
            </div>
          ` : (simpleState.profileTab === 'likes'
        ? [...userPosts].sort((a, b) => Number(b.likes_count || 0) - Number(a.likes_count || 0))
        : userPosts
      ).map(p => renderSimplePostCard(p, acc)).join('')}
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
      ${renderTopBar('BlocTag Space', false)}
      <main class="flex-1 flex flex-col w-full px-5 pt-2 pb-24 simple-screen-animate">
        <!-- Header & Actions (Exact Stitch SCR-NTF-06) -->
        <div class="flex items-center justify-between pt-1 pb-3">
          <div class="flex items-center gap-2">
            <h1 class="text-xl font-bold text-on-surface">Bildirimler</h1>
            <span class="px-2 py-0.5 rounded-full bg-primary-container/20 text-primary text-[11px] font-semibold">
              ${unreadCount} yeni
            </span>
          </div>
          <button type="button" onclick="window.BlocTagSimpleMode.markAllNotifsRead()"
            class="flex items-center gap-1 px-3 py-1.5 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-on-surface text-xs active:scale-95 transition-all cursor-pointer">
            <span class="material-symbols-outlined notranslate text-[16px]" translate="no">done_all</span>
            <span>Okundu Say</span>
          </button>
        </div>

        <!-- Filter Chips -->
        <div class="flex items-center gap-2 overflow-x-auto no-scrollbar py-1 mb-3">
          <button type="button" onclick="window.BlocTagSimpleMode.setNotifFilter('all')"
            class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors cursor-pointer ${simpleState.notifFilter === 'all' ? 'bg-surface-container-high text-on-surface font-semibold' : 'bg-surface-container text-on-surface-variant'}">
            <span>Tümü</span>
            <span class="w-1.5 h-1.5 rounded-full bg-primary"></span>
          </button>
          <button type="button" onclick="window.BlocTagSimpleMode.setNotifFilter('tips')"
            class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors cursor-pointer ${simpleState.notifFilter === 'tips' ? 'bg-surface-container-high text-on-surface font-semibold' : 'bg-surface-container text-on-surface-variant'}">
            <span class="material-symbols-outlined notranslate text-[15px] text-primary" translate="no">volunteer_activism</span>
            <span>Transfer &amp; Bahşiş</span>
          </button>
          <button type="button" onclick="window.BlocTagSimpleMode.setNotifFilter('mentions')"
            class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors cursor-pointer ${simpleState.notifFilter === 'mentions' ? 'bg-surface-container-high text-on-surface font-semibold' : 'bg-surface-container text-on-surface-variant'}">
            <span class="material-symbols-outlined notranslate text-[15px]" translate="no">chat_bubble</span>
            <span>Space &amp; Yanıtlar</span>
          </button>
          <button type="button" onclick="window.BlocTagSimpleMode.setNotifFilter('system')"
            class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs whitespace-nowrap transition-colors cursor-pointer ${simpleState.notifFilter === 'system' ? 'bg-surface-container-high text-on-surface font-semibold' : 'bg-surface-container text-on-surface-variant'}">
            <span class="material-symbols-outlined notranslate text-[15px] text-secondary" translate="no">verified_user</span>
            <span>Sistem</span>
          </button>
        </div>

        <!-- Notifications List -->
        <div class="flex flex-col gap-2.5">
          ${filtered.length === 0 ? `
            <div class="flex flex-col items-center justify-center text-center py-12 px-4 rounded-2xl bg-surface-container-low">
              <div class="w-14 h-14 rounded-full bg-surface-container flex items-center justify-center text-primary mb-3">
                <span class="material-symbols-outlined notranslate text-[28px]" translate="no">mark_chat_read</span>
              </div>
              <h3 class="text-sm font-semibold text-on-surface mb-1">Henüz bildirim yok</h3>
              <p class="text-xs text-on-surface-variant max-w-xs">
                Cüzdanınıza gelen transferler, Space beğenileri, yorumlar ve bahşişler anlık olarak burada görünür.
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
                    <span class="text-xs font-semibold text-on-surface truncate">${esc(item.title || 'BlocTag Bildirimi')}</span>
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

    return `
      ${renderTopBar('Menü', false)}
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
              <p class="text-[10.5px] text-on-surface-variant font-mono truncate mt-0.5">${acc ? esc(acc.address) : 'Cüzdan bağlı değil'}</p>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-2 mt-3 pt-3 border-t border-outline-variant/10">
            <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-WLT-HOME')"
              class="h-9 rounded-xl bg-surface-container hover:bg-surface-container-high text-xs font-semibold text-on-surface flex items-center justify-center gap-1.5 transition-colors cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[16px] text-primary" translate="no">account_balance_wallet</span>
              <span>Cüzdanım</span>
            </button>
            <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-PRF-05', { profileTarget: '' })"
              class="h-9 rounded-xl bg-surface-container hover:bg-surface-container-high text-xs font-semibold text-on-surface flex items-center justify-center gap-1.5 transition-colors cursor-pointer">
              <span class="material-symbols-outlined notranslate text-[16px] text-primary" translate="no">person</span>
              <span>Profilim</span>
            </button>
          </div>
        </div>

        <!-- Mode Switch Banner (Pro Moda Geçiş) -->
        <div class="bg-gradient-to-r from-primary/15 via-surface-container-low to-secondary/15 rounded-2xl p-4 border border-primary/25 shadow-sm mb-3.5">
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-2.5 min-w-0">
              <div class="w-9 h-9 rounded-xl bg-primary/20 text-primary flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined notranslate text-[20px]" translate="no">bolt</span>
              </div>
              <div class="flex flex-col min-w-0">
                <span class="text-xs font-bold text-on-surface">Pro Mod (Tam Görünüm)</span>
                <span class="text-[10px] text-on-surface-variant">Ağ Explorer, Düğümler ve Geliştirici Araçları</span>
              </div>
            </div>
            <button type="button" onclick="window.BlocTagSimpleMode.requestProMode()"
              class="px-3 py-1.5 rounded-full bg-primary text-on-primary text-[11px] font-bold hover:brightness-95 active:scale-95 transition-all shadow-sm shrink-0 cursor-pointer">
              Geçiş Yap
            </button>
          </div>
        </div>

        <!-- Quick Simple Features List -->
        <div class="flex flex-col gap-2">
          <span class="text-[11px] font-mono uppercase font-bold text-on-surface-variant/70 px-1">İşlemler &amp; Hizmetler</span>

          <!-- Send Crypto -->
          <button type="button" onclick="window.BlocTagSimpleMode.go('SCR-WLT-SEND')"
            class="w-full p-3 rounded-2xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/15 flex items-center justify-between text-left transition-all active:scale-[0.99] cursor-pointer">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-xl bg-primary/15 text-primary flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined notranslate text-[18px]" translate="no">send</span>
              </div>
              <div class="flex flex-col">
                <span class="text-xs font-bold text-on-surface">Kripto Gönder</span>
                <span class="text-[10px] text-on-surface-variant">Sıfır komisyonlu anında BCT transferi</span>
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
                <span class="text-xs font-bold text-on-surface">BNS Kullanıcı Adı (.bct)</span>
                <span class="text-[10px] text-on-surface-variant">Kimlik ve Web3 profilinizi yönetin</span>
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
                <span class="text-xs font-bold text-on-surface">Güvenlik &amp; Kurtarma Anahtarı</span>
                <span class="text-[10px] text-on-surface-variant">12 kelimelik gizli kurtarma ifadesi (Seed Phrase)</span>
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
                <span class="text-xs font-bold text-on-surface">Bildirimler &amp; Uyarılar</span>
                <span class="text-[10px] text-on-surface-variant">İşlem ve Space güncellemeleri</span>
              </div>
            </div>
            <span class="material-symbols-outlined notranslate text-[18px] text-on-surface-variant" translate="no">chevron_right</span>
          </button>

          <!-- Language Selector -->
          <button type="button" onclick="if(typeof openLanguageModal==='function') openLanguageModal();"
            class="w-full p-3 rounded-2xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/15 flex items-center justify-between text-left transition-all active:scale-[0.99] cursor-pointer">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-xl bg-surface-container text-on-surface flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined notranslate text-[18px]" translate="no">language</span>
              </div>
              <div class="flex flex-col">
                <span class="text-xs font-bold text-on-surface">Dil Seçimi (Language)</span>
                <span class="text-[10px] text-on-surface-variant">Türkçe, English &amp; 8 dil desteği</span>
              </div>
            </div>
            <span class="material-symbols-outlined notranslate text-[18px] text-on-surface-variant" translate="no">chevron_right</span>
          </button>

          <!-- Whitepaper Link -->
          <a href="/docs/WHITEPAPER.md" target="_blank" rel="noopener noreferrer"
            class="w-full p-3 rounded-2xl bg-surface-container-low hover:bg-surface-container border border-outline-variant/15 flex items-center justify-between text-left transition-all active:scale-[0.99] cursor-pointer">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-xl bg-surface-container text-on-surface flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined notranslate text-[18px]" translate="no">description</span>
              </div>
              <div class="flex flex-col">
                <span class="text-xs font-bold text-on-surface">LockTrace Whitepaper</span>
                <span class="text-[10px] text-on-surface-variant">Protokol mimarisi ve teknik dokümantasyon</span>
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
          <span class="font-mono text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-bold">Simple Mod</span>
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

    if (simpleState.activeScreen === 'SCR-SPC-03') {
      const feedSig = posts.slice(0, 35).map(p => `${p.post_id || p.id}:${p.likes_count || (p.likes ? p.likes.length : 0)}:${p.comments_count || (p.comments ? p.comments.length : 0)}`).join(',');
      return `SPC03|${addr}|${bal}|${unread}|${simpleState.feedFilter}|${simpleState.searchBarOpen}|${simpleState.searchQuery}|${feedSig}`;
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
    return `${simpleState.activeScreen}|${addr}|${bal}|${nonce}|${hidden}|${unread}|${simpleState.profileTarget}|${simpleState.profileTab}|${simpleState.notifFilter}|${simpleState.importModeOpen}|${simpleState.seedSavedConfirmed}`;
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
      const feedContainer = document.getElementById('simple-feed-container');
      if (feedContainer) {
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
        feedContainer.innerHTML = filteredPosts.length === 0 ? `
          <div class="p-8 rounded-2xl bg-surface-container-low text-center flex flex-col items-center gap-2 text-on-surface-variant">
            <span class="material-symbols-outlined notranslate text-[28px] text-primary" translate="no">forum</span>
            <span class="text-xs">Gönderiler yükleniyor veya bu filtrede gönderi yok...</span>
          </div>
        ` : filteredPosts.slice(0, 35).map(post => renderSimplePostCard(post, acc)).join('');
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
        btn.innerHTML = '<span class="material-symbols-outlined notranslate animate-spin text-[18px]" translate="no">progress_activity</span><span>Cüzdan Hazırlanıyor...</span>';
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
          window.showToast(err.message || 'Cüzdan oluşturulamadı', 'error', true);
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
        if (typeof window.showToast === 'function') window.showToast('Lütfen 12 kelime veya özel anahtar girin', 'warning', true);
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
        if (typeof window.showToast === 'function') window.showToast('Lütfen miktar ve alıcı adresini girin', 'warning', true);
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
        if (typeof window.showToast === 'function') window.showToast('Kendi gönderinize bahşiş gönderemezsiniz', 'warning', true);
        return;
      }
      navigateToSimpleScreen('SCR-WLT-SEND', {
        recipient: authorAddress,
        amount: '0.25'
      });
      if (typeof window.showToast === 'function') {
        window.showToast('Bahşiş alıcısı hazırlandı (0.25 BCT)', 'volunteer_activism');
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
          window.showToast(`⭐ '@${cleanName}' aktif kimliğiniz olarak ayarlandı!`, 'verified');
        }
      } catch (err) {
        console.error('setPrimaryHandle error:', err);
        renderSimpleMode(false);
        if (typeof window.showToast === 'function') {
          window.showToast(`⭐ '@${cleanName}' aktif kimlik olarak seçildi`, 'info');
        }
      }
    },

    followProfileAuthor: async (targetAddress, bnsName) => {
      if (!targetAddress) return;
      const btn = document.getElementById('simple-profile-follow-btn');
      if (typeof window.followVoiceOnChain === 'function') {
        await window.followVoiceOnChain(btn, targetAddress, bnsName);
        renderSimpleMode(false);
      } else {
        if (typeof window.showToast === 'function') {
          window.showToast('Takip servisi yükleniyor...', 'info');
        }
      }
    },

    openFollowersList: (addr, type) => {
      const label = type === 'following' ? 'Takip Edilenler' : 'Takipçiler';
      if (typeof window.showToast === 'function') {
        window.showToast(`${label} listesi sayfası Stitch üzerinden hazırlanıyor...`, 'info');
      }
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
