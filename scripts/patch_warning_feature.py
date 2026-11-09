with open('frontend/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Patch Mobile Header (next to mobileNetLabel Mainnet button)
old_mobile_hdr = """        <button class="flex items-center gap-1 bg-surface-container-low hover:bg-surface-container px-2 py-0.5 rounded-full border border-outline-variant/30 transition-colors active:scale-95 shrink-0" onclick="openNetworkSecurityModal()" title="Network &amp; SHA-256 Verification" type="button">
          <span class="w-2 h-2 rounded-full bg-primary animate-pulse shrink-0" id="mobileNetDot"></span>
          <span class="font-label-sm text-[10.5px] sm:text-[11px] text-on-surface tracking-wide uppercase font-semibold shrink-0" id="mobileNetLabel">Mainnet</span>
          <span class="material-symbols-outlined text-[12px] text-primary shrink-0 hidden xs:inline">shield_lock</span>
        </button>
      </div>"""

new_mobile_hdr = """        <button class="flex items-center gap-1 bg-surface-container-low hover:bg-surface-container px-2 py-0.5 rounded-full border border-outline-variant/30 transition-colors active:scale-95 shrink-0" onclick="openNetworkSecurityModal()" title="Network &amp; SHA-256 Verification" type="button">
          <span class="w-2 h-2 rounded-full bg-primary animate-pulse shrink-0" id="mobileNetDot"></span>
          <span class="font-label-sm text-[10.5px] sm:text-[11px] text-on-surface tracking-wide uppercase font-semibold shrink-0" id="mobileNetLabel">Mainnet</span>
          <span class="material-symbols-outlined text-[12px] text-primary shrink-0 hidden xs:inline">shield_lock</span>
        </button>
        <button id="mobileNetWarningBtn" class="hidden items-center gap-1 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold animate-pulse cursor-pointer shrink-0 shadow-xs" onclick="openNetworkSecurityModal('warning')" title="⚠️ Security &amp; Integrity Discrepancy Alert" type="button">
          <span class="material-symbols-outlined text-[13px] text-rose-400">warning</span>
          <span>Alert</span>
        </button>
      </div>"""

if old_mobile_hdr in content:
    content = content.replace(old_mobile_hdr, new_mobile_hdr, 1)
    print("1. Mobile header patched!")
else:
    print("1. Mobile header NOT found!")

# 2. Patch Desktop Header (next to desktopNetLabel Mainnet button)
old_desktop_hdr = """      <button class="flex items-center gap-space-xs bg-surface-container-low hover:bg-surface-container px-3 py-1.5 rounded-full border border-outline-variant/30 transition-colors cursor-pointer" onclick="openNetworkSecurityModal()" title="SHA-256 Integrity Shield &amp; RPC Selector" type="button">
        <span class="w-2 h-2 rounded-full bg-primary animate-pulse" id="desktopNetDot"></span>
        <span class="font-label-sm text-label-sm text-on-surface tracking-wide uppercase font-semibold" id="desktopNetLabel">LockTrace Mainnet</span>
        <span class="material-symbols-outlined text-[14px] text-primary">shield_lock</span>
      </button>"""

new_desktop_hdr = """      <button class="flex items-center gap-space-xs bg-surface-container-low hover:bg-surface-container px-3 py-1.5 rounded-full border border-outline-variant/30 transition-colors cursor-pointer" onclick="openNetworkSecurityModal()" title="SHA-256 Integrity Shield &amp; RPC Selector" type="button">
        <span class="w-2 h-2 rounded-full bg-primary animate-pulse" id="desktopNetDot"></span>
        <span class="font-label-sm text-label-sm text-on-surface tracking-wide uppercase font-semibold" id="desktopNetLabel">LockTrace Mainnet</span>
        <span class="material-symbols-outlined text-[14px] text-primary">shield_lock</span>
      </button>
      <button id="desktopNetWarningBtn" class="hidden items-center gap-1.5 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40 px-2.5 py-1 rounded-full text-xs font-mono font-bold animate-pulse cursor-pointer shrink-0 shadow-xs" onclick="openNetworkSecurityModal('warning')" title="⚠️ Security &amp; Integrity Discrepancy Alert" type="button">
        <span class="material-symbols-outlined text-[15px] text-rose-400">warning</span>
        <span>Security Discrepancy Alert</span>
      </button>"""

if old_desktop_hdr in content:
    content = content.replace(old_desktop_hdr, new_desktop_hdr, 1)
    print("2. Desktop header patched!")
else:
    print("2. Desktop header NOT found!")

# 3. Patch Sidebar button
old_sidebar_btn = """        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-primary animate-pulse" id="sidebarIntegrityDot"></span>
          <div class="flex flex-col">
            <span class="font-label-sm text-label-sm text-on-surface" id="sidebarIntegrityLabel">SHA-256 + Quorum</span>
            <span class="text-[10px] font-mono text-on-surface-variant" id="sidebarActiveRpcLabel">Non-Custodial ECDSA</span>
          </div>
        </div>
        <span class="material-symbols-outlined text-primary text-[16px]">verified_user</span>
      </button>"""

new_sidebar_btn = """        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-primary animate-pulse" id="sidebarIntegrityDot"></span>
          <div class="flex flex-col">
            <span class="font-label-sm text-label-sm text-on-surface" id="sidebarIntegrityLabel">SHA-256 + Quorum</span>
            <span class="text-[10px] font-mono text-on-surface-variant" id="sidebarActiveRpcLabel">Non-Custodial ECDSA</span>
          </div>
        </div>
        <div class="flex items-center gap-1.5 shrink-0">
          <span id="sidebarWarningBadge" class="hidden px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 font-mono text-[9px] font-bold">Alert</span>
          <span class="material-symbols-outlined text-primary text-[16px]">verified_user</span>
        </div>
      </button>"""

if old_sidebar_btn in content:
    content = content.replace(old_sidebar_btn, new_sidebar_btn, 1)
    print("3. Sidebar button patched!")
else:
    print("3. Sidebar button NOT found!")

# 4. Patch network-security-modal with #secModalSecurityAlertBox
old_modal_header = """        <button class="w-8 h-8 rounded-full bg-surface-container-high hover:bg-surface-variant text-on-surface flex items-center justify-center transition-colors shrink-0" onclick="closeNetworkSecurityModal()" type="button">
          <span class="material-symbols-outlined text-[18px]">close</span>
        </button>
      </div>

      <!-- 1. SHA-256 & ECDSA Integrity Box -->"""

new_modal_header = """        <button class="w-8 h-8 rounded-full bg-surface-container-high hover:bg-surface-variant text-on-surface flex items-center justify-center transition-colors shrink-0 cursor-pointer" onclick="closeNetworkSecurityModal()" type="button">
          <span class="material-symbols-outlined text-[18px]">close</span>
        </button>
      </div>

      <!-- 0. Dynamic Security Discrepancy & Vulnerability Analysis Card -->
      <div id="secModalSecurityAlertBox" class="hidden p-4 rounded-2xl bg-rose-500/10 border border-rose-500/35 flex flex-col gap-2.5 text-xs text-rose-200 shadow-lg shadow-rose-950/20">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <div class="w-7 h-7 rounded-lg bg-rose-500/25 text-rose-400 flex items-center justify-center shrink-0">
              <span class="material-symbols-outlined text-[18px]">warning</span>
            </div>
            <span class="font-bold text-sm text-rose-300 font-sans tracking-tight">Güvenlik &amp; Bütünlük Uyuşmazlığı Uyarısı</span>
          </div>
          <span class="px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-400 font-mono text-[10px] font-bold uppercase tracking-wider">Kritik Uyarı</span>
        </div>

        <div class="space-y-2 text-on-surface leading-relaxed text-[12px]">
          <div class="flex items-start gap-1.5 text-rose-200">
            <span class="font-bold text-rose-300 shrink-0">Hata Açıklaması:</span>
            <span id="secModalAlertDescription">Tarayıcınızdaki frontend dosyasının SHA-256 özeti, LockTrace L1 Doğrulayıcı Otoritesi tarafından blokzincirde mühürlenen beklenen özet ile eşleşmiyor.</span>
          </div>
          <div class="flex items-start gap-2 text-rose-200/90 bg-surface-container-lowest/80 p-3 rounded-xl border border-rose-500/20">
            <span class="material-symbols-outlined text-rose-400 text-[18px] shrink-0 mt-0.5">security</span>
            <div class="flex flex-col gap-1">
              <span class="font-bold text-rose-300">Güvenlik Açığı &amp; Olası Risk:</span>
              <span id="secModalAlertVulnerability">
                Önbellekte eski bir sürüm veya aradaki bir proxy/CDN tarafından manipüle edilmiş JavaScript script'leri çalışıyor olabilir. 
                Bu durum, kötü niyetli bir araya girme (Man-in-the-Middle) saldırısında transfer alıcı adresinin veya işlem parametrelerinin değiştirilmesine yol açabilir. 
                Cüzdan güvenliğiniz için bu arayüzde işlem yapmadan önce önbelleğinizi temizleyip doğrulanmış sürüme geçmeniz zorunludur.
              </span>
            </div>
          </div>
        </div>

        <!-- Quick Recovery Action Buttons -->
        <div class="flex items-center gap-2 pt-1 flex-wrap">
          <button type="button" onclick="forcePurgeCacheAndReload()" class="px-3.5 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs flex items-center gap-1.5 shadow-sm transition-all active:scale-95 cursor-pointer">
            <span class="material-symbols-outlined text-[14px]">refresh</span>
            <span>Önbelleği Temizle &amp; Yeniden Yükle</span>
          </button>
          <button type="button" onclick="verifyFrontendIntegrityState()" class="px-3 py-1.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-semibold text-xs flex items-center gap-1 transition-all cursor-pointer">
            <span class="material-symbols-outlined text-[14px]">sync</span>
            <span>Yeniden Doğrula</span>
          </button>
        </div>
      </div>

      <!-- 1. SHA-256 & ECDSA Integrity Box -->"""

if old_modal_header in content:
    content = content.replace(old_modal_header, new_modal_header, 1)
    print("4. Modal alert box inserted!")
else:
    print("4. Modal alert box NOT found!")

# 5. Patch JavaScript functions: openNetworkSecurityModal, setIntegrityWarningState, forcePurgeCacheAndReload, verifyFrontendIntegrityState
old_js_block = """    function openNetworkSecurityModal() {
      const m = document.getElementById('network-security-modal');
      if (!m) return;
      m.classList.remove('hidden');
      m.classList.add('flex');
      renderNetworkSecurityModalContent();
      verifyFrontendIntegrityState();
    }"""

new_js_block = """    let isIntegrityWarningActive = false;
    let activeIntegrityWarningDetails = null;

    function setIntegrityWarningState(hasWarning, details) {
      isIntegrityWarningActive = Boolean(hasWarning);
      activeIntegrityWarningDetails = hasWarning ? (details || {}) : null;

      const mobileWarnBtn = document.getElementById('mobileNetWarningBtn');
      const desktopWarnBtn = document.getElementById('desktopNetWarningBtn');
      const sideWarnBadge = document.getElementById('sidebarWarningBadge');
      const mobileDot = document.getElementById('mobileNetDot');
      const desktopDot = document.getElementById('desktopNetDot');
      const sideDot = document.getElementById('sidebarIntegrityDot');
      const sideLbl = document.getElementById('sidebarIntegrityLabel');

      if (isIntegrityWarningActive) {
        if (mobileWarnBtn) {
          mobileWarnBtn.classList.remove('hidden');
          mobileWarnBtn.classList.add('inline-flex');
        }
        if (desktopWarnBtn) {
          desktopWarnBtn.classList.remove('hidden');
          desktopWarnBtn.classList.add('inline-flex');
        }
        if (sideWarnBadge) {
          sideWarnBadge.classList.remove('hidden');
        }
        if (mobileDot) mobileDot.className = 'w-2 h-2 rounded-full bg-rose-500 animate-ping shrink-0';
        if (desktopDot) desktopDot.className = 'w-2 h-2 rounded-full bg-rose-500 animate-ping';
        if (sideDot) sideDot.className = 'w-2 h-2 rounded-full bg-error animate-ping';
        if (sideLbl) sideLbl.textContent = '⛔ INTEGRITY WARNING!';
      } else {
        if (mobileWarnBtn) {
          mobileWarnBtn.classList.add('hidden');
          mobileWarnBtn.classList.remove('inline-flex');
        }
        if (desktopWarnBtn) {
          desktopWarnBtn.classList.add('hidden');
          desktopWarnBtn.classList.remove('inline-flex');
        }
        if (sideWarnBadge) {
          sideWarnBadge.classList.add('hidden');
        }
        if (mobileDot) mobileDot.className = 'w-2 h-2 rounded-full bg-primary animate-pulse shrink-0';
        if (desktopDot) desktopDot.className = 'w-2 h-2 rounded-full bg-primary animate-pulse';
        if (sideDot) sideDot.className = 'w-2 h-2 rounded-full bg-primary animate-pulse';
        if (sideLbl) sideLbl.textContent = 'SHA-256 + ECDSA Verified';
      }

      const alertBox = document.getElementById('secModalSecurityAlertBox');
      const alertDesc = document.getElementById('secModalAlertDescription');
      const alertVuln = document.getElementById('secModalAlertVulnerability');

      if (alertBox) {
        if (isIntegrityWarningActive) {
          alertBox.classList.remove('hidden');
          if (alertDesc && details && details.description) alertDesc.textContent = details.description;
          if (alertVuln && details && details.vulnerability) alertVuln.textContent = details.vulnerability;
        } else {
          alertBox.classList.add('hidden');
        }
      }
    }

    async function forcePurgeCacheAndReload() {
      showToast('Önbellek temizleniyor ve doğrulanmış sürüm yükleniyor...', 'sync');
      try {
        if ('caches' in window) {
          const keys = await caches.keys();
          for (const k of keys) {
            await caches.delete(k);
          }
        }
        if ('serviceWorker' in navigator) {
          const regs = await navigator.serviceWorker.getRegistrations();
          for (const r of regs) {
            await r.unregister();
          }
        }
      } catch (_e) {}
      setTimeout(() => {
        window.location.reload(true);
      }, 350);
    }

    function openNetworkSecurityModal(focusMode) {
      const m = document.getElementById('network-security-modal');
      if (!m) return;
      m.classList.remove('hidden');
      m.classList.add('flex');
      renderNetworkSecurityModalContent();
      verifyFrontendIntegrityState();
      if (focusMode === 'warning') {
        const alertBox = document.getElementById('secModalSecurityAlertBox');
        if (alertBox && !alertBox.classList.contains('hidden')) {
          alertBox.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }
    }"""

if old_js_block in content:
    content = content.replace(old_js_block, new_js_block, 1)
    print("5. JS openNetworkSecurityModal and setIntegrityWarningState patched!")
else:
    print("5. JS openNetworkSecurityModal NOT found!")

# 6. Update verifyFrontendIntegrityState to trigger setIntegrityWarningState
old_verify_tail = """        const sideLbl = document.getElementById('sidebarIntegrityLabel');
        const sideDot = document.getElementById('sidebarIntegrityDot');
        if (allOk) {
          if (sideLbl) sideLbl.textContent = 'SHA-256 + ECDSA Verified';
          if (sideDot) sideDot.className = 'w-2 h-2 rounded-full bg-primary animate-pulse';
        } else if (info.verified === false) {
          if (sideLbl) sideLbl.textContent = '⛔ INTEGRITY WARNING!';
          if (sideDot) sideDot.className = 'w-2 h-2 rounded-full bg-error animate-ping';
          showToast('⛔ WARNING: Frontend release signature or SHA-256 mismatch!', 'error', true);
        }
        renderNetworkSecurityModalContent();"""

new_verify_tail = """        if (allOk) {
          setIntegrityWarningState(false);
        } else {
          const reason = info.warning || (hashMatches ? 'ECDSA Dijital Sürüm İmzası doğrulanamadı.' : `Frontend SHA-256 özeti (${info.index_html_sha256 ? info.index_html_sha256.slice(0, 16) : ''}...) beklenen özetle (${info.expected_index_sha256 ? info.expected_index_sha256.slice(0, 16) : ''}...) eşleşmiyor.`);
          setIntegrityWarningState(true, {
            description: reason,
            vulnerability: 'Önbellekte eski veya manipüle edilmiş JavaScript scriptleri çalışıyor olabilir (Man-in-the-Middle veya eski CDN önbelleği). Kötü niyetli bir saldırıda özel anahtar hırsızlığı veya sahte işlem parametreleri üretilebilir. Güvenliğiniz için derhal önbelleği temizleyip sayfayı yenileyiniz.'
          });
          if (info.verified === false) {
            showToast('⛔ WARNING: Frontend release signature or SHA-256 mismatch!', 'error', true);
          }
        }
        renderNetworkSecurityModalContent();"""

if old_verify_tail in content:
    content = content.replace(old_verify_tail, new_verify_tail, 1)
    print("6. verifyFrontendIntegrityState tail patched!")
else:
    print("6. verifyFrontendIntegrityState tail NOT found!")

# 7. Update runQuorumCrossCheck to also trigger warning state if inconsistency found
old_quorum_discrepancy = """      if (balanceConsistent) {
        lines.push(`\\n✅ QUORUM CONFIRMED (${reports.length} nodes consistent, Highest Block: #${maxBlocks})`);
      } else {
        lines.push(`\\n⛔ WARNING: Balance discrepancy detected between nodes! Select a trusted seed or your local node.`);
      }"""

new_quorum_discrepancy = """      if (balanceConsistent) {
        lines.push(`\\n✅ QUORUM CONFIRMED (${reports.length} nodes consistent, Highest Block: #${maxBlocks})`);
      } else {
        lines.push(`\\n⛔ WARNING: Balance discrepancy detected between nodes! Select a trusted seed or your local node.`);
        setIntegrityWarningState(true, {
          description: 'P2P düğümleri arasında bakiye veya blok yüksekliği mutabakat uyumsuzluğu tespit edildi.',
          vulnerability: 'Bağlı olduğunuz P2P düğümü ana blokzincir ağından kopmuş (fork/desync) olabilir. Yanlış bakiyeler görmemek ve işlem gecikmesi yaşamamak için güvenilir ana tohum düğümüne (Seed Node) geçiş yapmanız önerilir.'
        });
      }"""

if old_quorum_discrepancy in content:
    content = content.replace(old_quorum_discrepancy, new_quorum_discrepancy, 1)
    print("7. runQuorumCrossCheck patched!")
else:
    print("7. runQuorumCrossCheck NOT found!")

with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Saved frontend/index.html successfully!")

