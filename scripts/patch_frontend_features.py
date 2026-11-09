with open('frontend/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update formatSpaceBodyHtml
old_format = """    function formatSpaceBodyHtml(rawText) {
      let safe = escapeHtml(rawText || '');

      // 1. External URLs (safe links)
      safe = safe.replace(/(https?:\/\/[^\s<]+)/gi, (url) => {
        return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="text-primary hover:underline inline-flex items-center gap-0.5 break-all" onclick="event.stopPropagation();">${url}</a>`;
      });

      // 2. Mentions & Replies: Clickable to view author profile directly
      safe = safe.replace(/@([a-zA-Z0-9_\-\.]+)/g, (match, handle) => {
        return `<span class="mention-tag inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded-md bg-primary/10 text-primary font-medium hover:bg-primary/20 hover:underline cursor-pointer transition-colors" onclick="event.stopPropagation(); openUserProfile('${handle}')" title="Profilini Gör: @${handle}">@${handle}</span>`;
      });

      // 3. Hashtags: #topic (supports Turkish & Unicode letters)
      safe = safe.replace(/#([a-zA-Z0-9_ğüşıöçĞÜŞİÖÇ\-]+)/g, (match, tag) => {
        return `<span class="hashtag-tag inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded-md bg-emerald-500/10 text-emerald-400 font-medium hover:bg-emerald-500/20 hover:underline cursor-pointer transition-colors" onclick="event.stopPropagation(); filterSpaceByEntity('#${tag}')" title="Filter topic #${tag}">#${tag}</span>`;
      });

      // 4. Cashtags: $BCT, $ETH, $BTC, etc.
      safe = safe.replace(/\$([a-zA-Z0-9_]{2,10})\b/g, (match, sym) => {
        const s = sym.toUpperCase();
        return `<span class="cashtag-tag inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded-md bg-secondary/10 text-secondary font-mono font-semibold hover:bg-secondary/20 hover:underline cursor-pointer transition-colors" onclick="event.stopPropagation(); filterSpaceByEntity('$${s}')" title="Filter symbol $${s}">$${s}</span>`;
      });

      // 5. Line breaks
      return safe.replace(/\\n/g, '<br/>');
    }"""

new_format = """    function formatSpaceBodyHtml(rawText) {
      if (!rawText) return '';
      let text = String(rawText);

      // 0. Quoted Post Attribution Card (Exact Twitter/Farcaster Style)
      const quoteRegex = /(?:🔁|🔄)\\s*(?:Alıntı|Quote):\\s*(@?[a-zA-Z0-9_\\-\\.]+)?\\s*(?:\\((BCT[a-fA-F0-9]{36,44})\\))?\\s*\\n?["“]([^"”]+)["”]/i;
      const quoteMatch = text.match(quoteRegex);
      let quoteCardHtml = '';

      if (quoteMatch) {
        const qAuthor = (quoteMatch[1] || 'Anonymous').trim();
        const qWallet = (quoteMatch[2] || '').trim();
        const qContent = (quoteMatch[3] || '').trim();
        const profileTarget = qWallet || (qAuthor.startsWith('@') ? qAuthor.slice(1) : qAuthor);
        const avatarChar = qAuthor.replace(/^[@]/, '').charAt(0).toUpperCase() || 'U';
        const displayAuthor = qAuthor.startsWith('@') ? qAuthor : (qWallet ? shortAddr(qWallet) : qAuthor);

        quoteCardHtml = `
          <div class="my-2.5 p-3 sm:p-3.5 rounded-2xl bg-surface-container-high/70 border border-outline-variant/30 hover:border-primary/40 transition-all select-none cursor-pointer group shadow-xs" onclick="event.stopPropagation(); openUserProfile('${escapeHtml(profileTarget)}');" title="Alıntılanan Kullanıcının Profilini Gör">
            <div class="flex items-center justify-between gap-2 mb-2 pb-1.5 border-b border-outline-variant/15">
              <div class="flex items-center gap-2 min-w-0">
                <div class="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold text-[11px] shrink-0 ring-1 ring-primary/30">
                  ${escapeHtml(avatarChar)}
                </div>
                <div class="flex items-center gap-1.5 min-w-0">
                  <span class="text-xs font-bold text-emerald-400 font-mono truncate hover:underline">${escapeHtml(displayAuthor)}</span>
                  <span class="material-symbols-outlined text-primary text-[14px] shrink-0" style="font-variation-settings: 'FILL' 1;" title="Doğrulanmış Hesap">verified</span>
                  ${qWallet ? `<span class="text-[10px] text-on-surface-variant font-mono truncate hidden sm:inline">(${escapeHtml(shortAddr(qWallet))})</span>` : ''}
                </div>
              </div>
              <span class="px-2 py-0.5 rounded-full bg-primary/10 text-primary font-mono text-[9.5px] font-bold shrink-0 flex items-center gap-0.5 border border-primary/20">
                <span class="material-symbols-outlined text-[11px]">cached</span>
                <span>Alıntı Yapıldı</span>
              </span>
            </div>
            <div class="text-xs sm:text-[13px] text-on-surface-variant italic leading-relaxed pl-1">
              &ldquo;${escapeHtml(qContent)}&rdquo;
            </div>
            ${qWallet ? `
              <div class="mt-2 pt-1.5 border-t border-outline-variant/10 flex items-center justify-between text-[10px] text-on-surface-variant/70 font-mono">
                <span class="truncate flex items-center gap-1">
                  <span class="material-symbols-outlined text-[12px] text-primary">account_balance_wallet</span>
                  <span class="truncate">${escapeHtml(shortAddr(qWallet))}</span>
                </span>
                <span class="text-primary group-hover:underline flex items-center gap-0.5 shrink-0">
                  <span>Profili Gör</span>
                  <span class="material-symbols-outlined text-[11px]">arrow_forward</span>
                </span>
              </div>
            ` : ''}
          </div>
        `;
        text = (text.slice(0, quoteMatch.index) + text.slice(quoteMatch.index + quoteMatch[0].length)).trim();
      }

      let safe = escapeHtml(text || '');

      // 1. External URLs (safe links)
      safe = safe.replace(/(https?:\\/\\/[^\\s<]+)/gi, (url) => {
        return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="text-primary hover:underline inline-flex items-center gap-0.5 break-all" onclick="event.stopPropagation();">${url}</a>`;
      });

      // 2. Mentions & Replies: Clickable to view author profile directly
      safe = safe.replace(/@([a-zA-Z0-9_\\-\\.]+)/g, (match, handle) => {
        return `<span class="mention-tag inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded-md bg-primary/10 text-primary font-medium hover:bg-primary/20 hover:underline cursor-pointer transition-colors" onclick="event.stopPropagation(); openUserProfile('${handle}')" title="Profilini Gör: @${handle}">@${handle}</span>`;
      });

      // 3. Hashtags: #topic (supports Turkish & Unicode letters)
      safe = safe.replace(/#([a-zA-Z0-9_ğüşıöçĞÜŞİÖÇ\\-]+)/g, (match, tag) => {
        return `<span class="hashtag-tag inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded-md bg-emerald-500/10 text-emerald-400 font-medium hover:bg-emerald-500/20 hover:underline cursor-pointer transition-colors" onclick="event.stopPropagation(); filterSpaceByEntity('#${tag}')" title="Filter topic #${tag}">#${tag}</span>`;
      });

      // 4. Cashtags: $BCT, $ETH, $BTC, etc.
      safe = safe.replace(/\\$([a-zA-Z0-9_]{2,10})\\b/g, (match, sym) => {
        const s = sym.toUpperCase();
        return `<span class="cashtag-tag inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded-md bg-secondary/10 text-secondary font-mono font-semibold hover:bg-secondary/20 hover:underline cursor-pointer transition-colors" onclick="event.stopPropagation(); filterSpaceByEntity('$${s}')" title="Filter symbol $${s}">$${s}</span>`;
      });

      // 5. Line breaks
      safe = safe.replace(/\\n/g, '<br/>');

      return safe ? (quoteCardHtml ? `${safe}<br/>${quoteCardHtml}` : safe) : quoteCardHtml;
    }"""

if old_format in content:
    content = content.replace(old_format, new_format, 1)
    print("1. formatSpaceBodyHtml patched successfully!")
else:
    print("1. formatSpaceBodyHtml NOT found!")

# 2. Update quoteSpacePost
old_quote = """    function quoteSpacePost(postId, ev) {
      if (ev) ev.stopPropagation();
      const post = spacePostsCache.find(p => p.post_id === postId);
      if (!post) return;
      const input = document.getElementById('spacePostInput');
      if (input) {
        const snippet = String(post.content || '').slice(0, 80);
        input.value = `"${snippet}${post.content.length > 80 ? '...' : ''}" — ${shortAddr(post.author)} $BCT `;
        updateSpaceCharCount();
        focusSpaceComposer();
      }
    }"""

new_quote = """    function quoteSpacePost(postId, ev) {
      if (ev) ev.stopPropagation();
      const post = spacePostsCache.find(p => p.post_id === postId);
      if (!post) return;
      if (activeDetailPostId) {
        resetSpaceDetailChrome();
      }
      const input = document.getElementById('spacePostInput');
      if (input) {
        const authorHandle = post.author_bns ? `@${post.author_bns}` : shortAddr(post.author);
        const authorAddr = post.author || '';
        const rawContent = String(post.content || '').trim().replace(/\\s+/g, ' ');
        input.value = `🔁 Alıntı: ${authorHandle} (${authorAddr})\\n"${rawContent.slice(0, 140)}${rawContent.length > 140 ? '...' : ''}"\\n\\n`;
        updateSpaceCharCount();
        focusSpaceComposer();
        showToast(`Alıntı hazırlandı (${authorHandle}). Düşüncenizi ekleyip paylaşabilirsiniz.`, 'cached');
      }
    }"""

if old_quote in content:
    content = content.replace(old_quote, new_quote, 1)
    print("2. quoteSpacePost patched successfully!")
else:
    print("2. quoteSpacePost NOT found!")

# 3. Update userProfileModal classes for mobile optimization
old_modal_html = """  <div class="fixed inset-0 z-50 bg-background/85 backdrop-blur-md hidden items-center justify-center p-2 sm:p-4 overflow-y-auto overflow-x-hidden" id="userProfileModal" onclick="if(event.target===this) closeUserProfile();">
    <div class="w-full max-w-2xl max-h-[92dvh] overflow-y-auto overflow-x-hidden rounded-3xl bg-surface-container flex flex-col shadow-2xl border border-outline-variant/30 transition-all scale-95 opacity-0 my-auto mx-auto" id="userProfileModalCard">
      <!-- Header Banner with Gradient -->
      <div class="h-20 sm:h-28 bg-gradient-to-r from-primary/25 via-surface-container-high to-secondary/25 relative rounded-t-3xl p-3 sm:p-4 flex justify-between items-center gap-2">
        <span class="px-2.5 py-1 rounded-full bg-surface-container/90 backdrop-blur-md text-[11px] font-mono text-on-surface flex items-center gap-1.5 border border-outline-variant/20 shadow-sm">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>LockTrace Identity</span>
        </span>
        <button class="w-8 h-8 rounded-full bg-surface-container/90 backdrop-blur-md hover:bg-surface-variant text-on-surface flex items-center justify-center transition-colors shadow-sm cursor-pointer" onclick="closeUserProfile()" type="button" title="Close Profile">
          <span class="material-symbols-outlined text-[18px]">close</span>
        </button>
      </div>"""

new_modal_html = """  <div class="fixed inset-0 z-50 bg-background/85 backdrop-blur-md hidden items-start sm:items-center justify-center p-2 sm:p-4 pt-3 sm:pt-6 pb-24 overflow-y-auto overflow-x-hidden overscroll-contain" id="userProfileModal" onclick="if(event.target===this) closeUserProfile();">
    <div class="w-full max-w-2xl max-h-[88dvh] sm:max-h-[90dvh] overflow-y-auto overflow-x-hidden rounded-3xl bg-surface-container flex flex-col shadow-2xl border border-outline-variant/30 transition-all scale-95 opacity-0 my-0 sm:my-auto mx-auto" id="userProfileModalCard">
      <!-- Header Banner with Gradient -->
      <div class="h-20 sm:h-28 bg-gradient-to-r from-primary/25 via-surface-container-high to-secondary/25 relative rounded-t-3xl p-3 sm:p-4 flex justify-between items-center gap-2">
        <span class="px-2.5 py-1 rounded-full bg-surface-container/90 backdrop-blur-md text-[11px] font-mono text-on-surface flex items-center gap-1.5 border border-outline-variant/20 shadow-sm">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>LockTrace Identity</span>
        </span>
        <button class="w-9 h-9 sm:w-8 sm:h-8 min-w-[36px] min-h-[36px] rounded-full bg-surface-container/90 backdrop-blur-md hover:bg-surface-variant text-on-surface flex items-center justify-center transition-colors shadow-sm cursor-pointer active:scale-90 z-20" onclick="closeUserProfile()" type="button" title="Close Profile">
          <span class="material-symbols-outlined text-[20px] sm:text-[18px]">close</span>
        </button>
      </div>"""

if old_modal_html in content:
    content = content.replace(old_modal_html, new_modal_html, 1)
    print("3. userProfileModal HTML patched successfully!")
else:
    print("3. userProfileModal HTML NOT found!")

# 4. Update triggerExplorerSearch
old_search_fn = """        if (type === 'block') {
          openBlockDetailModal(result.index);
        } else if (type === 'transaction') {
          openTxDetail(result);
        } else if (type === 'address') {
          showToast(`${shortAddr(result.address)} Balance: ${formatBct(result.balance, 4)} BCT (${result.transaction_count} txs)`, 'account_balance_wallet');
        }"""

new_search_fn = """        if (type === 'block') {
          openBlockDetailModal(result.index);
        } else if (type === 'transaction') {
          openTxDetail(result);
        } else if (type === 'address') {
          showToast(`Adres bulundu: ${shortAddr(result.address)} (${result.transaction_count || 0} işlem, ${formatBct(result.balance, 4)} BCT)`, 'account_balance_wallet');
          await openUserProfile(result.address, 'txs');
        }"""

if old_search_fn in content:
    content = content.replace(old_search_fn, new_search_fn, 1)
    print("4. triggerExplorerSearch patched successfully!")
else:
    print("4. triggerExplorerSearch NOT found!")

# 5. Update openUserProfile and renderUserProfileData to accept initialTab and reset scrollTop
old_open_profile = """    async function openUserProfile(addressOrHandle) {
      const modal = document.getElementById('userProfileModal');
      const card = document.getElementById('userProfileModalCard');
      if (!modal || !card) return;

      const raw = String(addressOrHandle || '').trim();
      if (!raw) return;

      // Initial loading state
      const handleEl = document.getElementById('userProfileHandle');
      const addrEl = document.getElementById('userProfileAddress');
      const addrShortEl = document.getElementById('userProfileAddressShort');
      const tagEl = document.getElementById('userProfileTagBadge');
      if (handleEl) handleEl.textContent = raw.startsWith('@') ? raw : (raw.endsWith('.bct') ? '@' + raw : shortAddr(raw));
      if (addrEl) addrEl.textContent = raw;
      if (addrShortEl) addrShortEl.textContent = shortAddr(raw);
      if (tagEl) {
        tagEl.textContent = 'Loading profile...';
        tagEl.className = 'px-2 py-0.5 rounded-full text-[11px] font-semibold bg-surface-container text-on-surface-variant font-sans';
      }
      document.getElementById('userProfileBalance').textContent = '...';
      document.getElementById('userProfilePct').textContent = 'Loading ledger...';
      document.getElementById('userProfileTotalPosts').textContent = '0';
      document.getElementById('userProfileTotalLikes').textContent = '0';
      document.getElementById('userProfileTotalCmts').textContent = '0 comments';
      document.getElementById('userProfileRoyalties').textContent = '0.00 BCT';

      document.getElementById('profileSubViewPosts').innerHTML = '<div class="py-8 text-center text-on-surface-variant text-xs">Loading on-chain thoughts...</div>';
      document.getElementById('profileSubViewHandles').innerHTML = '';
      document.getElementById('profileSubViewTxs').innerHTML = '';

      modal.classList.remove('hidden');
      modal.classList.add('flex');
      requestAnimationFrame(() => {
        card.classList.remove('scale-95', 'opacity-0');
        card.classList.add('scale-100', 'opacity-100');
      });

      try {
        const { ok, body } = await apiFetch(`/profile/${encodeURIComponent(raw)}`);
        if (!ok || !body.data) {
          showToast(body.message || 'Profile not found', 'warning', true);
          closeUserProfile();
          return;
        }

        currentProfileData = body.data;
        renderUserProfileData(currentProfileData);
      } catch (err) {
        showToast('Failed to load profile', 'error', true);
        closeUserProfile();
      }
    }"""

new_open_profile = """    async function openUserProfile(addressOrHandle, initialTab = 'posts') {
      const modal = document.getElementById('userProfileModal');
      const card = document.getElementById('userProfileModalCard');
      if (!modal || !card) return;

      const raw = String(addressOrHandle || '').trim();
      if (!raw) return;

      // Ensure modal and card start scrolled to the top on mobile
      modal.scrollTop = 0;
      card.scrollTop = 0;

      // Initial loading state
      const handleEl = document.getElementById('userProfileHandle');
      const addrEl = document.getElementById('userProfileAddress');
      const addrShortEl = document.getElementById('userProfileAddressShort');
      const tagEl = document.getElementById('userProfileTagBadge');
      if (handleEl) handleEl.textContent = raw.startsWith('@') ? raw : (raw.endsWith('.bct') ? '@' + raw : shortAddr(raw));
      if (addrEl) addrEl.textContent = raw;
      if (addrShortEl) addrShortEl.textContent = shortAddr(raw);
      if (tagEl) {
        tagEl.textContent = 'Loading profile...';
        tagEl.className = 'px-2 py-0.5 rounded-full text-[11px] font-semibold bg-surface-container text-on-surface-variant font-sans';
      }
      document.getElementById('userProfileBalance').textContent = '...';
      document.getElementById('userProfilePct').textContent = 'Loading ledger...';
      document.getElementById('userProfileTotalPosts').textContent = '0';
      document.getElementById('userProfileTotalLikes').textContent = '0';
      document.getElementById('userProfileTotalCmts').textContent = '0 comments';
      document.getElementById('userProfileRoyalties').textContent = '0.00 BCT';

      document.getElementById('profileSubViewPosts').innerHTML = '<div class="py-8 text-center text-on-surface-variant text-xs">Loading on-chain thoughts...</div>';
      document.getElementById('profileSubViewHandles').innerHTML = '';
      document.getElementById('profileSubViewTxs').innerHTML = '<div class="py-8 text-center text-on-surface-variant text-xs">Loading ledger transactions...</div>';

      modal.classList.remove('hidden');
      modal.classList.add('flex');
      modal.scrollTop = 0;
      card.scrollTop = 0;

      requestAnimationFrame(() => {
        card.classList.remove('scale-95', 'opacity-0');
        card.classList.add('scale-100', 'opacity-100');
        modal.scrollTop = 0;
        card.scrollTop = 0;
      });

      try {
        const { ok, body } = await apiFetch(`/profile/${encodeURIComponent(raw)}`);
        if (!ok || !body.data) {
          showToast(body.message || 'Profile not found', 'warning', true);
          closeUserProfile();
          return;
        }

        currentProfileData = body.data;
        renderUserProfileData(currentProfileData, initialTab);
      } catch (err) {
        showToast('Failed to load profile', 'error', true);
        closeUserProfile();
      }
    }"""

if old_open_profile in content:
    content = content.replace(old_open_profile, new_open_profile, 1)
    print("5. openUserProfile patched successfully!")
else:
    print("5. openUserProfile NOT found!")

# 6. Update renderUserProfileData signature and profileSubViewTxs rendering
old_render_profile_head = """    function renderUserProfileData(data) {"""
new_render_profile_head = """    function renderUserProfileData(data, initialTab = 'posts') {"""

if old_render_profile_head in content:
    content = content.replace(old_render_profile_head, new_render_profile_head, 1)
    print("6. renderUserProfileData head patched successfully!")
else:
    print("6. renderUserProfileData head NOT found!")

old_render_profile_tail = """      // 5. Transactions Tab View
      const viewTxs = document.getElementById('profileSubViewTxs');
      if (!txs.length) {
        viewTxs.innerHTML = '<div class="py-8 text-center text-on-surface-variant text-xs bg-surface-container-low rounded-xl border border-outline-variant/10">No on-chain transactions found for this account.</div>';
      } else {
        viewTxs.innerHTML = txs.map(tx => {
          const isSender = tx.sender === data.address;
          const typeLabel = tx.tx_type || 'transfer';
          return `
            <div class="p-2.5 rounded-xl bg-surface-container-low border border-outline-variant/10 flex items-center justify-between text-xs">
              <div class="flex items-center gap-2 min-w-0">
                <span class="material-symbols-outlined text-[16px] ${isSender ? 'text-rose-400' : 'text-emerald-400'}">${isSender ? 'arrow_upward' : 'arrow_downward'}</span>
                <div class="flex flex-col min-w-0">
                  <span class="font-medium text-on-surface truncate capitalize">${escapeHtml(typeLabel.replace(/_/g, ' '))}</span>
                  <span class="font-mono text-[11px] text-on-surface-variant truncate">${isSender ? 'To: ' + shortAddr(tx.receiver) : 'From: ' + shortAddr(tx.sender)}</span>
                </div>
              </div>
              <div class="text-right shrink-0">
                <div class="font-mono font-bold ${isSender ? 'text-on-surface' : 'text-primary'}">${isSender ? '-' : '+'}${formatBct(tx.amount || 0, 4)} BCT</div>
                <span class="text-[10px] text-outline">${escapeHtml(formatTimeAgo(tx.timestamp))}</span>
              </div>
            </div>
          `;
        }).join('');
      }

      switchProfileSubTab('posts');
    }"""

new_render_profile_tail = """      // 5. Transactions Tab View (Full On-Chain Ledger & Explorer Integration)
      const viewTxs = document.getElementById('profileSubViewTxs');
      const renderTxsList = (txList) => {
        if (!txList || !txList.length) {
          viewTxs.innerHTML = '<div class="py-8 text-center text-on-surface-variant text-xs bg-surface-container-low rounded-xl border border-outline-variant/10">No on-chain transactions found for this account.</div>';
          return;
        }
        viewTxs.innerHTML = `
          <div class="mb-2 flex items-center justify-between px-1 text-xs text-on-surface-variant">
            <span class="font-mono font-bold text-on-surface">${txList.length} Transactions Found</span>
            <span class="font-mono text-[11px]">All On-Chain Records</span>
          </div>
          <div class="space-y-2">
            ${txList.map(tx => {
              const isSender = tx.sender === data.address;
              const isRoyalty = Boolean(tx.is_author_royalty || (tx.extra_data && tx.extra_data.author === data.address && tx.sender !== data.address));
              const typeLabel = tx.tx_type || 'transfer';
              const amt = Number(tx.amount || 0);
              const txHash = tx.hash || tx.tx_hash || '';
              return `
                <div class="p-3 rounded-2xl bg-surface-container-low border border-outline-variant/15 hover:border-primary/40 transition-all flex flex-col gap-2 cursor-pointer group shadow-xs" onclick="openTxDetail(${JSON.stringify(tx).replace(/\"/g, '&quot;')})">
                  <div class="flex items-center justify-between gap-2">
                    <div class="flex items-center gap-2 min-w-0">
                      <div class="w-7 h-7 rounded-full ${isRoyalty ? 'bg-amber-400/15 text-amber-300' : (isSender ? 'bg-rose-500/15 text-rose-400' : 'bg-emerald-500/15 text-emerald-400')} flex items-center justify-center shrink-0">
                        <span class="material-symbols-outlined text-[15px]">${isRoyalty ? 'bolt' : (isSender ? 'arrow_upward' : 'arrow_downward')}</span>
                      </div>
                      <div class="flex flex-col min-w-0">
                        <div class="flex items-center gap-1.5 flex-wrap">
                          <span class="font-bold text-xs text-on-surface capitalize">${escapeHtml(typeLabel.replace(/_/g, ' '))}</span>
                          <span class="px-1.5 py-0.2 rounded-full ${tx.status === 'confirmed' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-300'} font-mono text-[9px] uppercase font-bold">${escapeHtml(tx.status || 'confirmed')}</span>
                        </div>
                        <span class="font-mono text-[10.5px] text-on-surface-variant truncate">${isSender ? 'To: ' + (tx.receiver ? shortAddr(tx.receiver) : 'Protocol') : 'From: ' + (tx.sender ? shortAddr(tx.sender) : 'Genesis')}</span>
                      </div>
                    </div>
                    <div class="text-right shrink-0">
                      <div class="font-mono font-bold text-xs sm:text-sm ${isRoyalty ? 'text-amber-300' : (isSender ? 'text-on-surface' : 'text-emerald-400')}">
                        ${isRoyalty ? '+' : (isSender ? '-' : '+')}${formatBct(amt, 4)} BCT
                      </div>
                      <span class="text-[10px] text-on-surface-variant font-mono">${escapeHtml(formatTimeAgo(tx.timestamp))}</span>
                    </div>
                  </div>
                  <div class="flex items-center justify-between pt-1 border-t border-outline-variant/10 text-[10px] font-mono text-on-surface-variant/70">
                    <span class="truncate">Tx: ${escapeHtml(String(txHash).slice(0, 14))}...</span>
                    <span class="text-primary group-hover:underline flex items-center gap-0.5 shrink-0">
                      <span>View Receipt</span>
                      <span class="material-symbols-outlined text-[11px]">arrow_forward</span>
                    </span>
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        `;
      };

      renderTxsList(txs);

      // Asynchronously fetch complete wallet history if needed
      if (data.address) {
        apiFetch(`/transactions/${encodeURIComponent(data.address)}`).then(({ ok, body }) => {
          if (ok && body && body.data && Array.isArray(body.data.transactions)) {
            const allTxs = body.data.transactions;
            if (allTxs.length > txs.length) {
              if (countTxs) countTxs.textContent = String(allTxs.length);
              renderTxsList(allTxs);
            }
          }
        }).catch(() => {});
      }

      switchProfileSubTab(initialTab || 'posts');
    }"""

if old_render_profile_tail in content:
    content = content.replace(old_render_profile_tail, new_render_profile_tail, 1)
    print("7. renderUserProfileData tail patched successfully!")
else:
    print("7. renderUserProfileData tail NOT found!")

with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Saved frontend/index.html successfully!")

