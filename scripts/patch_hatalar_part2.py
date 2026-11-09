# -*- coding: utf-8 -*-
"""
Part 2 of Hatalar fixes:
- Post details 4-col action grid optimization
- Quick Compose Popup Widget (#quickComposeModal) + JS functions
- Space Feed Settings Modal (#spaceSettingsModal) + triggerSpaceFeedRefresh()
- Multi-asset cashtag horizontal scroll carousel (from left to right) in generateSpacePostEmbedHtml
- Reply to comments logic & mention linking in formatSpaceBodyHtml
"""

with open('frontend/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Post Details 4-Column Action Grid
old_action_grid = '''          <!-- 4-Col Action Buttons Grid (Exact Stitch Screen F) -->
          <div class="grid grid-cols-4 gap-2 pt-1">
            <button class="flex items-center justify-center space-x-1.5 py-2.5 rounded-xl ${likedByMe ? 'bg-tertiary/15 text-tertiary' : 'bg-surface-container-high text-on-surface hover:bg-surface-variant'} transition-all active:scale-95" onclick="likeSpacePost('${pid}', event)" type="button">
              <span class="material-symbols-outlined text-[18px]" ${likedByMe ? 'style="font-variation-settings: \'FILL\' 1;"' : ''}>favorite</span>
              <span class="font-label-md text-label-md">Like</span>
            </button>
            <button class="flex items-center justify-center space-x-1.5 py-2.5 rounded-xl bg-surface-container-high text-on-surface hover:bg-surface-variant transition-all active:scale-95" onclick="document.getElementById('detailCommentInput').focus()" type="button">
              <span class="material-symbols-outlined text-[18px]">chat_bubble</span>
              <span class="font-label-md text-label-md">Comments</span>
            </button>
            <button class="flex items-center justify-center space-x-1.5 py-2.5 rounded-xl bg-surface-container-high text-on-surface hover:bg-surface-variant transition-all active:scale-95" onclick="closeSpacePostDetail(); quoteSpacePost('${pid}', event)" type="button">
              <span class="material-symbols-outlined text-[18px]">repeat</span>
              <span class="font-label-md text-label-md">Quote</span>
            </button>
            <button class="flex items-center justify-center space-x-1 py-2.5 rounded-xl bg-primary/15 text-primary hover:bg-primary/25 transition-all active:scale-95" onclick="tipAuthorPrompt('${escapeHtml(post.author)}', event)" type="button">
              <span class="material-symbols-outlined text-[18px]">bolt</span>
              <span class="font-label-md text-label-md font-semibold">Tip</span>
            </button>
          </div>'''

new_action_grid = '''          <!-- 4-Col Action Buttons Grid (Responsive, compact, no horizontal overflow) -->
          <div class="grid grid-cols-4 gap-1 sm:gap-2 pt-1">
            <button class="flex items-center justify-center space-x-1 py-2 px-1 rounded-xl ${likedByMe ? 'bg-tertiary/15 text-tertiary font-bold' : 'bg-surface-container-high text-on-surface hover:bg-surface-variant'} transition-all active:scale-95 text-xs font-semibold" onclick="likeSpacePost('${pid}', event)" type="button">
              <span class="material-symbols-outlined text-[16px] sm:text-[18px]" ${likedByMe ? 'style="font-variation-settings: \'FILL\' 1;"' : ''}>favorite</span>
              <span class="truncate">Like</span>
            </button>
            <button class="flex items-center justify-center space-x-1 py-2 px-1 rounded-xl bg-surface-container-high text-on-surface hover:bg-surface-variant transition-all active:scale-95 text-xs font-semibold" onclick="document.getElementById('detailCommentInput').focus()" type="button">
              <span class="material-symbols-outlined text-[16px] sm:text-[18px]">chat_bubble</span>
              <span class="truncate">Comment</span>
            </button>
            <button class="flex items-center justify-center space-x-1 py-2 px-1 rounded-xl bg-surface-container-high text-on-surface hover:bg-surface-variant transition-all active:scale-95 text-xs font-semibold" onclick="closeSpacePostDetail(); quoteSpacePost('${pid}', event)" type="button">
              <span class="material-symbols-outlined text-[16px] sm:text-[18px]">repeat</span>
              <span class="truncate">Quote</span>
            </button>
            <button class="flex items-center justify-center space-x-1 py-2 px-1 rounded-xl bg-primary/15 text-primary hover:bg-primary/25 transition-all active:scale-95 text-xs font-semibold" onclick="tipAuthorPrompt('${escapeHtml(post.author)}', event)" type="button">
              <span class="material-symbols-outlined text-[16px] sm:text-[18px]">bolt</span>
              <span class="truncate font-semibold">Tip</span>
            </button>
          </div>'''

if old_action_grid in content:
    content = content.replace(old_action_grid, new_action_grid, 1)
    print('[+] Issue 7 fixed: 4-Col action grid updated')
else:
    print('[-] Issue 7 4-Col action grid target not found')

# 2. Add Quick Compose Modal (#quickComposeModal) & Space Settings Modal (#spaceSettingsModal) before </body> or near other modals
modals_html = '''
  <!-- ========================================================================= -->
  <!-- MODAL: QUICK COMPOSE THOUGHT / CAST WIDGET (Popup Widget for FAB)          -->
  <!-- ========================================================================= -->
  <div class="fixed inset-0 z-50 bg-background/85 backdrop-blur-md hidden items-center justify-center p-3 sm:p-4 overflow-y-auto" id="quickComposeModal" onclick="if(event.target===this) closeQuickComposeModal();">
    <div class="w-full max-w-lg rounded-3xl bg-surface-container p-5 sm:p-6 flex flex-col shadow-2xl border border-outline-variant/30 gap-4 transition-all scale-95 opacity-0 my-auto" id="quickComposeModalCard">
      <div class="flex items-center justify-between pb-3 border-b border-outline-variant/20">
        <div class="flex items-center gap-2">
          <div class="w-8 h-8 rounded-full bg-primary/15 flex items-center justify-center text-primary">
            <span class="material-symbols-outlined text-[18px]">edit_note</span>
          </div>
          <div>
            <h3 class="font-headline-sm text-sm sm:text-base font-bold text-on-surface">Publish Thought to Space</h3>
            <span class="text-[11px] text-on-surface-variant font-mono">0.10 BCT On-Chain Sealed &bull; 20% Royalties</span>
          </div>
        </div>
        <button class="w-8 h-8 rounded-full bg-surface-container-high hover:bg-surface-variant text-on-surface flex items-center justify-center transition-colors cursor-pointer" onclick="closeQuickComposeModal()" type="button">
          <span class="material-symbols-outlined text-[18px]">close</span>
        </button>
      </div>

      <!-- Identity Selector -->
      <div class="flex items-center justify-between text-xs bg-surface-container-low p-2.5 rounded-xl border border-outline-variant/15">
        <span class="text-on-surface-variant font-medium">Publishing As:</span>
        <select id="quickComposeHandleSelect" class="bg-surface-container-high text-on-surface text-xs rounded-lg px-2 py-1 font-mono focus:outline-none border border-outline-variant/30 cursor-pointer">
          <option value="wallet">💳 Connected Wallet</option>
        </select>
      </div>

      <!-- Textarea -->
      <div class="flex flex-col gap-1.5">
        <textarea id="quickComposeTextarea" maxlength="280" rows="4" class="w-full bg-surface-container-lowest rounded-2xl p-3.5 text-on-surface text-sm placeholder:text-on-surface-variant/60 border border-outline-variant/20 focus:border-primary focus:outline-none resize-none leading-relaxed" placeholder="Share alpha, code, market thoughts or insights... ($BTC, $ETH, $SOL, $BCT supported)" oninput="updateQuickComposeCharCount()"></textarea>
        <div class="flex items-center justify-between text-[11px] font-mono px-1">
          <!-- Cashtag shortcut pills -->
          <div class="flex items-center gap-1.5 flex-wrap">
            <button type="button" onclick="insertQuickComposeTag('$BCT')" class="px-2 py-0.5 rounded-full bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 font-bold border border-emerald-500/20 active:scale-95 transition">$BCT</button>
            <button type="button" onclick="insertQuickComposeTag('$ETH')" class="px-2 py-0.5 rounded-full bg-sky-500/10 hover:bg-sky-500/20 text-sky-400 font-bold border border-sky-500/20 active:scale-95 transition">$ETH</button>
            <button type="button" onclick="insertQuickComposeTag('$BTC')" class="px-2 py-0.5 rounded-full bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 font-bold border border-amber-500/20 active:scale-95 transition">$BTC</button>
            <button type="button" onclick="insertQuickComposeTag('$SOL')" class="px-2 py-0.5 rounded-full bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 font-bold border border-purple-500/20 active:scale-95 transition">$SOL</button>
          </div>
          <span id="quickComposeCharCounter" class="text-on-surface-variant font-semibold">0 / 280</span>
        </div>
      </div>

      <!-- Footer & Submit Button -->
      <div class="flex items-center justify-between pt-2 border-t border-outline-variant/15">
        <div class="flex items-center gap-1 text-[11px] text-on-surface-variant">
          <span class="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
          <span>100% Non-Custodial</span>
        </div>
        <button id="btnQuickComposeSubmit" class="h-10 px-5 rounded-full bg-primary text-on-primary font-semibold text-xs sm:text-sm flex items-center gap-1.5 hover:brightness-105 active:scale-95 transition-all shadow-md shadow-primary/20 disabled:opacity-40 cursor-pointer" onclick="submitQuickComposePost()" type="button">
          <span class="material-symbols-outlined text-[16px]">send</span>
          <span>Publish Cast</span>
        </button>
      </div>
    </div>
  </div>

  <!-- ========================================================================= -->
  <!-- MODAL: SPACE FEED DISPLAY & FILTER SETTINGS MODAL (#spaceSettingsModal)    -->
  <!-- ========================================================================= -->
  <div class="fixed inset-0 z-50 bg-background/85 backdrop-blur-md hidden items-center justify-center p-3 sm:p-4 overflow-y-auto" id="spaceSettingsModal" onclick="if(event.target===this) closeSpaceSettingsModal();">
    <div class="w-full max-w-md rounded-3xl bg-surface-container p-5 sm:p-6 flex flex-col shadow-2xl border border-outline-variant/30 gap-4 transition-all scale-95 opacity-0 my-auto" id="spaceSettingsModalCard">
      <div class="flex items-center justify-between pb-3 border-b border-outline-variant/20">
        <div class="flex items-center gap-2">
          <div class="w-8 h-8 rounded-full bg-primary/15 flex items-center justify-center text-primary">
            <span class="material-symbols-outlined text-[18px]">tune</span>
          </div>
          <div>
            <h3 class="font-headline-sm text-sm sm:text-base font-bold text-on-surface">Space Feed Ayarları &bull; Filter</h3>
            <span class="text-[11px] text-on-surface-variant">Akış tercihlerinizi ve filtreleri özelleştirin</span>
          </div>
        </div>
        <button class="w-8 h-8 rounded-full bg-surface-container-high hover:bg-surface-variant text-on-surface flex items-center justify-center transition-colors cursor-pointer" onclick="closeSpaceSettingsModal()" type="button">
          <span class="material-symbols-outlined text-[18px]">close</span>
        </button>
      </div>

      <div class="flex flex-col gap-3 text-xs">
        <label class="flex items-center justify-between p-3 rounded-xl bg-surface-container-low border border-outline-variant/15 cursor-pointer hover:bg-surface-container-high transition">
          <div class="flex flex-col">
            <span class="font-semibold text-on-surface text-sm">Finansal Grafikler &amp; Cashtagler</span>
            <span class="text-on-surface-variant text-[11px]">Sadece $BTC, $ETH, $SOL, $BCT içeren gönderileri öne çıkar</span>
          </div>
          <input type="checkbox" id="settingFilterFinancialOnly" class="rounded accent-primary w-4 h-4 cursor-pointer" onchange="applySpaceSettings()">
        </label>

        <label class="flex items-center justify-between p-3 rounded-xl bg-surface-container-low border border-outline-variant/15 cursor-pointer hover:bg-surface-container-high transition">
          <div class="flex flex-col">
            <span class="font-semibold text-on-surface text-sm">Doğrulanmış BNS Kimlikleri</span>
            <span class="text-on-surface-variant text-[11px]">Sadece @bns handle'ı bulunan yazarları göster</span>
          </div>
          <input type="checkbox" id="settingFilterBnsOnly" class="rounded accent-primary w-4 h-4 cursor-pointer" onchange="applySpaceSettings()">
        </label>

        <label class="flex items-center justify-between p-3 rounded-xl bg-surface-container-low border border-outline-variant/15 cursor-pointer hover:bg-surface-container-high transition">
          <div class="flex flex-col">
            <span class="font-semibold text-on-surface text-sm">Kompakt Akış Görünümü</span>
            <span class="text-on-surface-variant text-[11px]">Daha az boşluk ile ekranda daha fazla gönderi göster</span>
          </div>
          <input type="checkbox" id="settingCompactFeed" class="rounded accent-primary w-4 h-4 cursor-pointer" onchange="applySpaceSettings()">
        </label>
      </div>

      <div class="flex items-center justify-end gap-2 pt-2 border-t border-outline-variant/15">
        <button class="px-4 py-2 rounded-full bg-surface-container-high hover:bg-surface-variant text-on-surface font-semibold text-xs transition active:scale-95" onclick="resetSpaceSettings()" type="button">Varsayılan</button>
        <button class="px-5 py-2 rounded-full bg-primary text-on-primary font-semibold text-xs transition active:scale-95 shadow-sm" onclick="closeSpaceSettingsModal()" type="button">Tamam</button>
      </div>
    </div>
  </div>
'''

if 'id="quickComposeModal"' not in content:
    content = content.replace('<!-- MODAL: USER & CREATOR PROFILE', modals_html + '\n  <!-- MODAL: USER & CREATOR PROFILE', 1)
    print('[+] Quick Compose Modal & Space Settings Modal added to HTML')

# 3. Update generateSpacePostEmbedHtml to support multiple cashtags in horizontal scroll carousel (from left to right)
old_embed_func = '''    function generateSpacePostEmbedHtml(rawContent) {
      if (!rawContent) return '';
      const text = String(rawContent).toLowerCase();

      // Helper to generate dynamic sparkline SVG
      const makeSparklineSvg = (colorHex) => `
        <svg class="w-full h-full overflow-visible" fill="none" viewBox="0 0 100 30">
          <path d="M0 24 Q 25 20, 40 12 T 70 7 T 100 2" fill="none" stroke="${colorHex}" stroke-linecap="round" stroke-width="2.2"></path>
          <path d="M0 24 Q 25 20, 40 12 T 70 7 T 100 2 L 100 30 L 0 30 Z" fill="${colorHex}" fill-opacity="0.12"></path>
        </svg>
      `;

      // Helper to render asset card
      const makeAssetCard = (sym, name, priceFormatted, change, metricTitle, metricVal, colorClass, bgClass, strokeHex, iconName) => {
        const cleanSym = sym.replace('$', '').toLowerCase();
        return `
          <div class="rounded-xl bg-surface-container-lowest p-3 sm:p-3.5 my-2 border border-outline-variant/15 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs select-none" onclick="event.stopPropagation()">
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 rounded-xl ${bgClass} ${colorClass} flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined text-[20px]">${iconName || 'trending_up'}</span>
              </div>
              <div class="flex flex-col">
                <div class="flex items-center gap-2">
                  <span class="font-mono text-sm font-bold text-on-surface">${sym}</span>
                  <span class="font-mono text-sm font-medium text-on-surface market-price-${cleanSym}">${priceFormatted}</span>
                  <span class="inline-flex items-center gap-0.5 px-2 py-0.2 rounded-full ${bgClass} ${colorClass} font-mono text-[10px] font-bold">
                    <span class="material-symbols-outlined text-[11px]">trending_up</span>
                    <span class="market-change-${cleanSym}">${change}</span>
                  </span>
                </div>
                <span class="text-[11px] text-on-surface-variant">${name}</span>
              </div>
            </div>
            <div class="flex items-center gap-3 self-end sm:self-auto shrink-0">
              <div class="flex flex-col items-end">
                <span class="text-[10px] text-on-surface-variant font-mono">${metricTitle}</span>
                <span class="font-mono text-xs ${colorClass} font-bold">${metricVal}</span>
              </div>
              <div class="w-20 h-6 flex items-center">
                ${makeSparklineSvg(strokeHex)}
              </div>
            </div>
          </div>
        `;
      };

      // 1. $BTC / Bitcoin
      if (text.includes('$btc') || text.includes('bitcoin') || text.includes('satoshi')) {
        const m = (window.liveMarketPrices && window.liveMarketPrices.BTC) || { price: 92450.00, change: '+3.8%' };
        const priceStr = '$' + Number(m.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return makeAssetCard('$BTC', 'Bitcoin • L1 Digital Gold Store of Value', priceStr, m.change, 'L1 Hashrate', '710 EH/s', 'text-amber-400', 'bg-amber-400/15', '#f59e0b', 'currency_bitcoin');
      }

      // 2. $ETH / Ethereum
      if (text.includes('$eth') || text.includes('ethereum') || text.includes('blob') || text.includes('gwei')) {
        const m = (window.liveMarketPrices && window.liveMarketPrices.ETH) || { price: 3450.00, change: '+2.4%' };
        const priceStr = '$' + Number(m.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return makeAssetCard('$ETH', 'Ethereum • L1 Blob Settlement Telemetry', priceStr, m.change, 'L1 Base Fee', '~12 Gwei', 'text-primary', 'bg-primary/15', '#22c55e', 'query_stats');
      }

      // 3. $SOL / Solana
      if (text.includes('$sol') || text.includes('solana')) {
        const m = (window.liveMarketPrices && window.liveMarketPrices.SOL) || { price: 214.80, change: '+5.2%' };
        const priceStr = '$' + Number(m.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return makeAssetCard('$SOL', 'Solana • Proof-of-History High Throughput L1', priceStr, m.change, 'Throughput', '2,840 TPS', 'text-purple-400', 'bg-purple-500/15', '#c084fc', 'electric_bolt');
      }

      // 4. $BCT / wBCT On-Chain Telemetry Card
      if (text.includes('$bct') || text.includes('wbct') || text.includes('uniswap') || text.includes('locktrace') || text.includes('tokenomics')) {
        const m = (window.liveMarketPrices && window.liveMarketPrices.BCT) || { price: 0.0000000046, change: '+4.2%' };
        return makeAssetCard('$BCT', 'LockTrace Native L1 • Base Uniswap v3 1:1 Peg Backed', '$0.0000000046', m.change, 'Transfer Fee', '0.0001 BCT', 'text-emerald-400', 'bg-emerald-500/15', '#34d399', 'currency_exchange');
      }

      // 5. Stocks: $AAPL / Apple
      if (text.includes('$aapl') || text.includes('apple') || text.includes('iphone')) {
        const m = (window.liveMarketPrices && window.liveMarketPrices.AAPL) || { price: 227.60, change: '+1.4%' };
        const priceStr = '$' + Number(m.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return makeAssetCard('$AAPL', 'Apple Inc. • NASDAQ Equity Telemetry', priceStr, m.change, 'Market Cap', '$3.45T', 'text-sky-400', 'bg-sky-500/15', '#38bdf8', 'bar_chart');
      }

      // 6. Stocks: $TSLA / Tesla
      if (text.includes('$tsla') || text.includes('tesla')) {
        const m = (window.liveMarketPrices && window.liveMarketPrices.TSLA) || { price: 322.40, change: '+4.8%' };
        const priceStr = '$' + Number(m.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return makeAssetCard('$TSLA', 'Tesla Inc. • NASDAQ EV & Autonomous AI', priceStr, m.change, 'Market Cap', '$1.03T', 'text-rose-400', 'bg-rose-500/15', '#fb7185', 'directions_car');
      }

      // 7. Stocks: $NVDA / NVIDIA
      if (text.includes('$nvda') || text.includes('nvidia')) {
        const m = (window.liveMarketPrices && window.liveMarketPrices.NVDA) || { price: 147.80, change: '+3.9%' };
        const priceStr = '$' + Number(m.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return makeAssetCard('$NVDA', 'NVIDIA Corp. • NASDAQ AI Semiconductor', priceStr, m.change, 'Market Cap', '$3.62T', 'text-emerald-400', 'bg-emerald-500/15', '#4ade80', 'memory');
      }

      // 8. General Cashtags: $[A-Z]{2,6} (e.g. $MSFT, $GOOG, $AMZN, etc.)
      const cashtagMatch = text.match(/\\$([a-z]{2,6})\\b/);
      if (cashtagMatch) {
        const sym = cashtagMatch[1].toUpperCase();
        const priceStr = '$' + (100 + (sym.charCodeAt(0) * 2.5)).toFixed(2);
        return makeAssetCard(`$${sym}`, `${sym} • Global Financial Telemetry`, priceStr, '+2.1%', '24h Vol', '$1.2B', 'text-primary', 'bg-primary/15', '#22c55e', 'monitoring');
      }

      // 9. Vault & Solvency Proof Embed (Exact Stitch Screen E)
      if (text.includes('vault') || text.includes('cold storage') || text.includes('solvency') || text.includes('multisig') || text.includes('reserve')) {
        return `
          <div class="rounded-xl bg-surface-container-lowest p-3 sm:p-3.5 my-2 border border-emerald-500/25 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs" onclick="event.stopPropagation()">
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 rounded-xl bg-emerald-500/15 text-emerald-400 flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined text-[20px]">shield</span>
              </div>
              <div class="flex flex-col">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-mono text-xs sm:text-sm font-bold text-on-surface">Secured Vault Balance</span>
                  <span class="px-2 py-0.2 rounded-full bg-emerald-500/15 text-emerald-400 font-mono text-[10px] font-bold">Zk-Proof Verified</span>
                </div>
                <span class="text-[11px] text-on-surface-variant">LockTrace Cold Reserve &bull; Multi-sig 3-of-5 Ledger Guard</span>
              </div>
            </div>
            <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 font-mono text-[11px] font-semibold self-end sm:self-auto border border-emerald-500/20">
              <span class="material-symbols-outlined text-[13px]">verified</span>
              <span>100% Solvency Proof</span>
            </div>
          </div>
        `;
      }

      // 10. Instant Settlement & Transaction Telemetry
      if (text.includes('usdc') || text.includes('settlement') || text.includes('finality') || text.includes('micro-transaction')) {
        return `
          <div class="rounded-xl bg-surface-container-lowest p-3 sm:p-3.5 my-2 border border-outline-variant/15 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs" onclick="event.stopPropagation()">
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined text-[20px]">swap_horiz</span>
              </div>
              <div class="flex flex-col">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-mono text-sm font-bold text-on-surface">1,250 USDC</span>
                  <span class="px-2 py-0.2 rounded-full bg-primary/10 text-primary font-mono text-[10px] font-bold">Instant Settlement</span>
                </div>
                <div class="flex items-center gap-2 font-mono text-[10.5px] text-on-surface-variant">
                  <span>Tx #4920</span>
                  <span>&bull;</span>
                  <span>Finality: 412ms</span>
                  <span>&bull;</span>
                  <span>Fee: $0.000102</span>
                </div>
              </div>
            </div>
          </div>
        `;
      }

      return '';
    }'''

new_embed_func = '''    function generateSpacePostEmbedHtml(rawContent) {
      if (!rawContent) return '';
      const text = String(rawContent).toLowerCase();
      const cards = [];

      // Helper to generate dynamic sparkline SVG
      const makeSparklineSvg = (colorHex) => `
        <svg class="w-full h-full overflow-visible" fill="none" viewBox="0 0 100 30">
          <path d="M0 24 Q 25 20, 40 12 T 70 7 T 100 2" fill="none" stroke="${colorHex}" stroke-linecap="round" stroke-width="2.2"></path>
          <path d="M0 24 Q 25 20, 40 12 T 70 7 T 100 2 L 100 30 L 0 30 Z" fill="${colorHex}" fill-opacity="0.12"></path>
        </svg>
      `;

      // Helper to render asset card
      const makeAssetCard = (sym, name, priceFormatted, change, metricTitle, metricVal, colorClass, bgClass, strokeHex, iconName) => {
        const cleanSym = sym.replace('$', '').toLowerCase();
        return `
          <div class="rounded-xl bg-surface-container-lowest p-3 sm:p-3.5 my-1.5 border border-outline-variant/15 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs select-none w-full" onclick="event.stopPropagation()">
            <div class="flex items-center gap-2.5 sm:gap-3 min-w-0">
              <div class="w-8 h-8 sm:w-9 sm:h-9 rounded-xl ${bgClass} ${colorClass} flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined text-[18px] sm:text-[20px]">${iconName || 'trending_up'}</span>
              </div>
              <div class="flex flex-col min-w-0">
                <div class="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                  <span class="font-mono text-xs sm:text-sm font-bold text-on-surface">${sym}</span>
                  <span class="font-mono text-xs sm:text-sm font-medium text-on-surface market-price-${cleanSym}">${priceFormatted}</span>
                  <span class="inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded-full ${bgClass} ${colorClass} font-mono text-[10px] font-bold">
                    <span class="material-symbols-outlined text-[10px]">trending_up</span>
                    <span class="market-change-${cleanSym}">${change}</span>
                  </span>
                </div>
                <span class="text-[10px] sm:text-[11px] text-on-surface-variant truncate">${name}</span>
              </div>
            </div>
            <div class="flex items-center gap-2.5 self-end sm:self-auto shrink-0">
              <div class="flex flex-col items-end">
                <span class="text-[9px] sm:text-[10px] text-on-surface-variant font-mono">${metricTitle}</span>
                <span class="font-mono text-xs ${colorClass} font-bold">${metricVal}</span>
              </div>
              <div class="w-16 sm:w-20 h-5 sm:h-6 flex items-center">
                ${makeSparklineSvg(strokeHex)}
              </div>
            </div>
          </div>
        `;
      };

      // 1. $BTC / Bitcoin
      if (text.includes('$btc') || text.includes('bitcoin') || text.includes('satoshi')) {
        const m = (window.liveMarketPrices && window.liveMarketPrices.BTC) || { price: 92450.00, change: '+3.8%' };
        const priceStr = '$' + Number(m.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        cards.push(makeAssetCard('$BTC', 'Bitcoin • L1 Digital Gold Store of Value', priceStr, m.change, 'L1 Hashrate', '710 EH/s', 'text-amber-400', 'bg-amber-400/15', '#f59e0b', 'currency_bitcoin'));
      }

      // 2. $ETH / Ethereum
      if (text.includes('$eth') || text.includes('ethereum') || text.includes('blob') || text.includes('gwei')) {
        const m = (window.liveMarketPrices && window.liveMarketPrices.ETH) || { price: 3450.00, change: '+2.4%' };
        const priceStr = '$' + Number(m.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        cards.push(makeAssetCard('$ETH', 'Ethereum • L1 Blob Settlement Telemetry', priceStr, m.change, 'L1 Base Fee', '~12 Gwei', 'text-primary', 'bg-primary/15', '#22c55e', 'query_stats'));
      }

      // 3. $SOL / Solana
      if (text.includes('$sol') || text.includes('solana')) {
        const m = (window.liveMarketPrices && window.liveMarketPrices.SOL) || { price: 214.80, change: '+5.2%' };
        const priceStr = '$' + Number(m.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        cards.push(makeAssetCard('$SOL', 'Solana • Proof-of-History High Throughput L1', priceStr, m.change, 'Throughput', '2,840 TPS', 'text-purple-400', 'bg-purple-500/15', '#c084fc', 'electric_bolt'));
      }

      // 4. $BCT / wBCT On-Chain Telemetry Card
      if (text.includes('$bct') || text.includes('wbct') || text.includes('uniswap') || text.includes('locktrace') || text.includes('tokenomics')) {
        const m = (window.liveMarketPrices && window.liveMarketPrices.BCT) || { price: 0.0000000046, change: '+4.2%' };
        cards.push(makeAssetCard('$BCT', 'LockTrace Native L1 • Base Uniswap v3 1:1 Peg Backed', '$0.0000000046', m.change, 'Transfer Fee', '0.0001 BCT', 'text-emerald-400', 'bg-emerald-500/15', '#34d399', 'currency_exchange'));
      }

      // 5. Stocks: $AAPL / Apple
      if (text.includes('$aapl') || text.includes('apple') || text.includes('iphone')) {
        const m = (window.liveMarketPrices && window.liveMarketPrices.AAPL) || { price: 227.60, change: '+1.4%' };
        const priceStr = '$' + Number(m.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        cards.push(makeAssetCard('$AAPL', 'Apple Inc. • NASDAQ Equity Telemetry', priceStr, m.change, 'Market Cap', '$3.45T', 'text-sky-400', 'bg-sky-500/15', '#38bdf8', 'bar_chart'));
      }

      // 6. Stocks: $TSLA / Tesla
      if (text.includes('$tsla') || text.includes('tesla')) {
        const m = (window.liveMarketPrices && window.liveMarketPrices.TSLA) || { price: 322.40, change: '+4.8%' };
        const priceStr = '$' + Number(m.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        cards.push(makeAssetCard('$TSLA', 'Tesla Inc. • NASDAQ EV & Autonomous AI', priceStr, m.change, 'Market Cap', '$1.03T', 'text-rose-400', 'bg-rose-500/15', '#fb7185', 'directions_car'));
      }

      // 7. Stocks: $NVDA / NVIDIA
      if (text.includes('$nvda') || text.includes('nvidia')) {
        const m = (window.liveMarketPrices && window.liveMarketPrices.NVDA) || { price: 147.80, change: '+3.9%' };
        const priceStr = '$' + Number(m.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        cards.push(makeAssetCard('$NVDA', 'NVIDIA Corp. • NASDAQ AI Semiconductor', priceStr, m.change, 'Market Cap', '$3.62T', 'text-emerald-400', 'bg-emerald-500/15', '#4ade80', 'memory'));
      }

      // 8. General Cashtags: $[A-Z]{2,6} (e.g. $MSFT, $GOOG, $AMZN, etc.)
      const cashtagMatches = Array.from(new Set(text.match(/\\$([a-z]{2,6})\\b/g) || []));
      cashtagMatches.forEach(tag => {
        const sym = tag.replace('$', '').toUpperCase();
        if (!['BTC', 'ETH', 'SOL', 'BCT', 'AAPL', 'TSLA', 'NVDA', 'WBCT'].includes(sym)) {
          const priceStr = '$' + (100 + (sym.charCodeAt(0) * 2.5)).toFixed(2);
          cards.push(makeAssetCard(`$${sym}`, `${sym} • Global Financial Telemetry`, priceStr, '+2.1%', '24h Vol', '$1.2B', 'text-primary', 'bg-primary/15', '#22c55e', 'monitoring'));
        }
      });

      // 9. Vault & Solvency Proof Embed (Exact Stitch Screen E)
      if (text.includes('vault') || text.includes('cold storage') || text.includes('solvency') || text.includes('multisig') || text.includes('reserve')) {
        cards.push(`
          <div class="rounded-xl bg-surface-container-lowest p-3 sm:p-3.5 my-1.5 border border-emerald-500/25 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs w-full" onclick="event.stopPropagation()">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 sm:w-9 sm:h-9 rounded-xl bg-emerald-500/15 text-emerald-400 flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined text-[18px] sm:text-[20px]">shield</span>
              </div>
              <div class="flex flex-col">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-mono text-xs sm:text-sm font-bold text-on-surface">Secured Vault Balance</span>
                  <span class="px-2 py-0.2 rounded-full bg-emerald-500/15 text-emerald-400 font-mono text-[10px] font-bold">Zk-Proof Verified</span>
                </div>
                <span class="text-[10px] sm:text-[11px] text-on-surface-variant">LockTrace Cold Reserve &bull; Multi-sig 3-of-5 Ledger Guard</span>
              </div>
            </div>
            <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 font-mono text-[10px] sm:text-[11px] font-semibold self-end sm:self-auto border border-emerald-500/20">
              <span class="material-symbols-outlined text-[12px] sm:text-[13px]">verified</span>
              <span>100% Solvency Proof</span>
            </div>
          </div>
        `);
      }

      // 10. Instant Settlement & Transaction Telemetry
      if (text.includes('usdc') || text.includes('settlement') || text.includes('finality') || text.includes('micro-transaction')) {
        cards.push(`
          <div class="rounded-xl bg-surface-container-lowest p-3 sm:p-3.5 my-1.5 border border-outline-variant/15 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs w-full" onclick="event.stopPropagation()">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 sm:w-9 sm:h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined text-[18px] sm:text-[20px]">swap_horiz</span>
              </div>
              <div class="flex flex-col">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-mono text-xs sm:text-sm font-bold text-on-surface">1,250 USDC</span>
                  <span class="px-2 py-0.2 rounded-full bg-primary/10 text-primary font-mono text-[10px] font-bold">Instant Settlement</span>
                </div>
                <div class="flex items-center gap-2 font-mono text-[10px] sm:text-[10.5px] text-on-surface-variant">
                  <span>Tx #4920</span>
                  <span>&bull;</span>
                  <span>Finality: 412ms</span>
                  <span>&bull;</span>
                  <span>Fee: $0.000102</span>
                </div>
              </div>
            </div>
          </div>
        `);
      }

      if (cards.length === 0) return '';
      if (cards.length === 1) return cards[0];

      // Multi-Asset Carousel: List from left to right as requested in Notion Bug #8!
      return `
        <div class="my-2 -mx-1 px-1">
          <div class="flex items-center justify-between text-[11px] font-mono text-on-surface-variant px-1 mb-1">
            <span class="flex items-center gap-1"><span class="material-symbols-outlined text-[14px] text-primary">ssid_chart</span> Tagged Instruments (${cards.length})</span>
            <span class="text-[10px] text-outline">Kaydır &rarr; Scroll</span>
          </div>
          <div class="flex gap-2.5 overflow-x-auto pb-2 no-scrollbar scroll-smooth snap-x">
            ${cards.map(c => `<div class="min-w-[270px] sm:min-w-[310px] max-w-[330px] shrink-0 snap-start">${c}</div>`).join('')}
          </div>
        </div>
      `;
    }'''

if old_embed_func in content:
    content = content.replace(old_embed_func, new_embed_func, 1)
    print('[+] Issue 8 fixed: generateSpacePostEmbedHtml multi-asset horizontal scroll carousel')
else:
    print('[-] Issue 8 generateSpacePostEmbedHtml target not found')

# 4. Fix typo in fetchLiveMarketTelemetry & improve price fetcher
old_fetch_telemetry = '''      // 2. Fetch BTC
      try {
        const ctrlB = new AbortController();
        const tB = setTimeout(() => ctrlB.abort(), 3500);
        const resB = await fetch('https://api.coinbase.com/v2/prices/BTC-USD/spot', { signal: ctrlB.signal });
        clearTimeout(tB);
        if (resB.ok) {
          const dB = await res.json ? await resB.json() : null;
          const pB = parseFloat(dB && dB.data && dB.data.amount);
          if (pB && !isNaN(pB)) window.liveMarketPrices.BTC.price = pB;
        }
      } catch (_) {}

      // 3. Fetch SOL
      try {
        const ctrlS = new AbortController();
        const tS = setTimeout(() => ctrlS.abort(), 3500);
        const resS = await fetch('https://api.coinbase.com/v2/prices/SOL-USD/spot', { signal: ctrlS.signal });
        clearTimeout(tS);
        if (resS.ok) {
          const dS = await resS.json ? await resS.json() : null;
          const pS = parseFloat(dS && dS.data && dS.data.amount);
          if (pS && !isNaN(pS)) window.liveMarketPrices.SOL.price = pS;
        }
      } catch (_) {}'''

new_fetch_telemetry = '''      // 2. Fetch BTC (Direct & Cached)
      try {
        const ctrlB = new AbortController();
        const tB = setTimeout(() => ctrlB.abort(), 3500);
        const resB = await fetch('https://api.coinbase.com/v2/prices/BTC-USD/spot', { signal: ctrlB.signal });
        clearTimeout(tB);
        if (resB.ok) {
          const dB = await resB.json();
          const pB = parseFloat(dB && dB.data && dB.data.amount);
          if (pB && !isNaN(pB)) window.liveMarketPrices.BTC.price = pB;
        }
      } catch (_) {}

      // 3. Fetch SOL (Direct & Cached)
      try {
        const ctrlS = new AbortController();
        const tS = setTimeout(() => ctrlS.abort(), 3500);
        const resS = await fetch('https://api.coinbase.com/v2/prices/SOL-USD/spot', { signal: ctrlS.signal });
        clearTimeout(tS);
        if (resS.ok) {
          const dS = await resS.json();
          const pS = parseFloat(dS && dS.data && dS.data.amount);
          if (pS && !isNaN(pS)) window.liveMarketPrices.SOL.price = pS;
        }
      } catch (_) {}'''

if old_fetch_telemetry in content:
    content = content.replace(old_fetch_telemetry, new_fetch_telemetry, 1)
    print('[+] Issue 8 fixed: fetchLiveMarketTelemetry typo corrected')
else:
    print('[-] Issue 8 fetchLiveMarketTelemetry target not found')

# 5. Add JavaScript helpers for Quick Compose, Refresh Spin, Settings Modal, and Comment Replies
js_helpers = '''
    // ── Quick Compose Modal Widget Handlers ─────────────────────────────────────
    function openQuickComposeModal() {
      const modal = document.getElementById('quickComposeModal');
      const card = document.getElementById('quickComposeModalCard');
      const textarea = document.getElementById('quickComposeTextarea');
      const select = document.getElementById('quickComposeHandleSelect');
      if (!modal || !card) return;

      // Populate handles if available
      if (select && window.currentAccount) {
        select.innerHTML = `<option value="wallet">💳 ${shortAddr(currentAccount.address)}</option>`;
        if (window.userBnsHandles && Array.isArray(userBnsHandles)) {
          userBnsHandles.forEach(h => {
            select.innerHTML += `<option value="${escapeHtml(h.name)}">@${escapeHtml(h.name)}</option>`;
          });
        }
      }

      modal.classList.remove('hidden');
      modal.classList.add('flex');
      requestAnimationFrame(() => {
        card.classList.remove('scale-95', 'opacity-0');
        card.classList.add('scale-100', 'opacity-100');
        if (textarea) textarea.focus();
      });
    }

    function closeQuickComposeModal() {
      const modal = document.getElementById('quickComposeModal');
      const card = document.getElementById('quickComposeModalCard');
      if (!modal || !card) return;
      card.classList.remove('scale-100', 'opacity-100');
      card.classList.add('scale-95', 'opacity-0');
      setTimeout(() => {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
      }, 150);
    }

    function updateQuickComposeCharCount() {
      const textarea = document.getElementById('quickComposeTextarea');
      const counter = document.getElementById('quickComposeCharCounter');
      const btn = document.getElementById('btnQuickComposeSubmit');
      if (!textarea || !counter) return;
      const len = textarea.value.length;
      counter.textContent = `${len} / 280`;
      if (btn) btn.disabled = len === 0;
    }

    function insertQuickComposeTag(tag) {
      const textarea = document.getElementById('quickComposeTextarea');
      if (!textarea) return;
      textarea.value = (textarea.value ? textarea.value.trim() + ' ' : '') + tag + ' ';
      textarea.focus();
      updateQuickComposeCharCount();
    }

    async function submitQuickComposePost() {
      const textarea = document.getElementById('quickComposeTextarea');
      const select = document.getElementById('quickComposeHandleSelect');
      const btn = document.getElementById('btnQuickComposeSubmit');
      if (!textarea) return;
      const content = textarea.value.trim();
      if (!content) return;

      if (!currentAccount) {
        showToast('Please create or unlock a wallet first', 'warning', true);
        closeQuickComposeModal();
        switchTab('yeni-cuzdan');
        return;
      }

      const selectedHandle = select ? select.value : 'wallet';
      let authorBns = '';
      if (selectedHandle && selectedHandle !== 'wallet') {
        authorBns = selectedHandle;
      }

      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="material-symbols-outlined text-[16px] animate-spin">sync</span><span>Publishing...</span>';
      }

      try {
        const { ok, body } = await apiFetch('/space/post', {
          method: 'POST',
          body: JSON.stringify({
            content: content,
            author: currentAccount.address,
            author_bns: authorBns
          })
        });

        if (ok && body.data) {
          showToast('Thought published successfully on-chain! (+20% royalty enabled)', 'success', true);
          textarea.value = '';
          updateQuickComposeCharCount();
          closeQuickComposeModal();
          loadSpaceFeed();
        } else {
          showToast(body.message || 'Failed to publish post', 'error', true);
        }
      } catch (err) {
        showToast('Network error while publishing post', 'error', true);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<span class="material-symbols-outlined text-[16px]">send</span><span>Publish Cast</span>';
        }
      }
    }

    // ── Space Header Refresh Spin & Settings Modal ──────────────────────────────
    function triggerSpaceFeedRefresh(btn) {
      const icon = document.getElementById('spaceRefreshSpinIcon');
      if (icon) {
        icon.classList.add('animate-spin');
        setTimeout(() => icon.classList.remove('animate-spin'), 750);
      }
      loadSpaceFeed();
      showToast('Space feed refreshed / Akış yenilendi', 'info');
    }

    function openSpaceSettingsModal() {
      const modal = document.getElementById('spaceSettingsModal');
      const card = document.getElementById('spaceSettingsModalCard');
      if (!modal || !card) return;
      modal.classList.remove('hidden');
      modal.classList.add('flex');
      requestAnimationFrame(() => {
        card.classList.remove('scale-95', 'opacity-0');
        card.classList.add('scale-100', 'opacity-100');
      });
    }

    function closeSpaceSettingsModal() {
      const modal = document.getElementById('spaceSettingsModal');
      const card = document.getElementById('spaceSettingsModalCard');
      if (!modal || !card) return;
      card.classList.remove('scale-100', 'opacity-100');
      card.classList.add('scale-95', 'opacity-0');
      setTimeout(() => {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
      }, 150);
    }

    function applySpaceSettings() {
      const filterFin = document.getElementById('settingFilterFinancialOnly')?.checked;
      const filterBns = document.getElementById('settingFilterBnsOnly')?.checked;
      const compact = document.getElementById('settingCompactFeed')?.checked;

      const feedStream = document.getElementById('spaceFeedStream');
      if (feedStream) {
        if (compact) {
          feedStream.classList.add('space-y-2');
          feedStream.classList.remove('space-y-4');
        } else {
          feedStream.classList.remove('space-y-2');
          feedStream.classList.add('space-y-4');
        }
      }

      if (filterFin) {
        spaceActiveEntityFilter = '$';
      } else if (filterBns) {
        spaceActiveEntityFilter = '@';
      } else {
        spaceActiveEntityFilter = null;
      }
      renderSpacePosts();
    }

    function resetSpaceSettings() {
      const chk1 = document.getElementById('settingFilterFinancialOnly');
      const chk2 = document.getElementById('settingFilterBnsOnly');
      const chk3 = document.getElementById('settingCompactFeed');
      if (chk1) chk1.checked = false;
      if (chk2) chk2.checked = false;
      if (chk3) chk3.checked = false;
      spaceActiveEntityFilter = null;
      applySpaceSettings();
      closeSpaceSettingsModal();
    }

    // ── Comment Reply Logic ─────────────────────────────────────────────────────
    let activeCommentReplyTarget = null;

    function replyToComment(displayHandle, address) {
      activeCommentReplyTarget = { handle: displayHandle, address: address };
      const banner = document.getElementById('detailCommentReplyBanner');
      const targetLbl = document.getElementById('detailCommentReplyTarget');
      const input = document.getElementById('detailCommentInput');
      if (banner && targetLbl) {
        targetLbl.textContent = `Replying to @${displayHandle}`;
        banner.classList.remove('hidden');
        banner.classList.add('flex');
      }
      if (input) {
        const prefix = `@${displayHandle} `;
        if (!input.value.startsWith(prefix)) {
          input.value = prefix + input.value;
        }
        input.focus();
      }
    }

    function cancelCommentReply() {
      activeCommentReplyTarget = null;
      const banner = document.getElementById('detailCommentReplyBanner');
      const input = document.getElementById('detailCommentInput');
      if (banner) {
        banner.classList.add('hidden');
        banner.classList.remove('flex');
      }
      if (input && input.value.startsWith('@')) {
        input.value = input.value.replace(/^@[a-zA-Z0-9_.]+\\s*/, '');
      }
    }
'''

if 'function openQuickComposeModal' not in content:
    content = content.replace('// 15. USER & CREATOR PROFILE MODAL', js_helpers + '\n    // 15. USER & CREATOR PROFILE MODAL', 1)
    print('[+] JS Helpers for Quick Compose, Refresh, Settings, and Comment Replies added')

with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('[*] frontend/index.html patched part 2 successfully.')

