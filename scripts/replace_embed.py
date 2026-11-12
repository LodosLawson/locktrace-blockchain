# -*- coding: utf-8 -*-
with open('frontend/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Action Grid in Space Post Detail
start_marker = '<!-- 4-Col Action Buttons Grid'
end_marker = '</article>'
idx1 = text.find(start_marker)
idx2 = text.find(end_marker, idx1)

replacement_grid = '''<!-- 4-Col Action Buttons Grid (Responsive, compact, no horizontal overflow) -->
          <div class="grid grid-cols-4 gap-1 sm:gap-2 pt-1">
            <button class="flex items-center justify-center space-x-1 py-2 px-1 rounded-xl ${likedByMe ? 'bg-tertiary/15 text-tertiary font-bold' : 'bg-surface-container-high text-on-surface hover:bg-surface-variant'} transition-all active:scale-95 text-xs font-semibold" onclick="likeSpacePost('${sanitizeJsAttr(pid)}', event)" type="button">
              <span class="material-symbols-outlined text-[16px] sm:text-[18px]" ${likedByMe ? 'style="font-variation-settings: \\'FILL\\' 1;"' : ''}>favorite</span>
              <span class="truncate">Like</span>
            </button>
            <button class="flex items-center justify-center space-x-1 py-2 px-1 rounded-xl bg-surface-container-high text-on-surface hover:bg-surface-variant transition-all active:scale-95 text-xs font-semibold" onclick="document.getElementById('detailCommentInput').focus()" type="button">
              <span class="material-symbols-outlined text-[16px] sm:text-[18px]">chat_bubble</span>
              <span class="truncate">Comment</span>
            </button>
            <button class="flex items-center justify-center space-x-1 py-2 px-1 rounded-xl bg-surface-container-high text-on-surface hover:bg-surface-variant transition-all active:scale-95 text-xs font-semibold" onclick="closeSpacePostDetail(); quoteSpacePost('${sanitizeJsAttr(pid)}', event)" type="button">
              <span class="material-symbols-outlined text-[16px] sm:text-[18px]">repeat</span>
              <span class="truncate">Quote</span>
            </button>
            <button class="flex items-center justify-center space-x-1 py-2 px-1 rounded-xl bg-primary/15 text-primary hover:bg-primary/25 transition-all active:scale-95 text-xs font-semibold" onclick="tipAuthorPrompt('${sanitizeJsAttr(post.author)}', event)" type="button">
              <span class="material-symbols-outlined text-[16px] sm:text-[18px]">bolt</span>
              <span class="truncate font-semibold">Tip</span>
            </button>
          </div>
        '''

if idx1 != -1 and idx2 != -1:
    text = text[:idx1] + replacement_grid + text[idx2:]
    print('Action grid in Space Post Detail replaced successfully!')

# 2. generateSpacePostEmbedHtml replacement
start_fn = 'function generateSpacePostEmbedHtml(rawContent) {'
end_fn = 'window.liveMarketPrices ='
f_idx1 = text.find(start_fn)
f_idx2 = text.find(end_fn)

replacement_fn = '''function generateSpacePostEmbedHtml(rawContent) {
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

      // Helper to render asset card (AUD14-04: Strict HTML escaping on change & telemetry)
      const makeAssetCard = (sym, name, priceFormatted, change, metricTitle, metricVal, colorClass, bgClass, strokeHex, iconName) => {
        const cleanSym = sanitizeJsAttr(sym.replace('$', '').toLowerCase());
        const safeChange = escapeHtml(String(change || ''));
        const safeSym = escapeHtml(String(sym || ''));
        const safeName = escapeHtml(String(name || ''));
        const safePrice = escapeHtml(String(priceFormatted || ''));
        const safeMetricTitle = escapeHtml(String(metricTitle || ''));
        const safeMetricVal = escapeHtml(String(metricVal || ''));
        const safeIcon = escapeHtml(String(iconName || 'trending_up'));
        return `
          <div class="rounded-xl bg-surface-container-lowest p-3 sm:p-3.5 my-1 border border-outline-variant/15 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs select-none w-full" onclick="event.stopPropagation()">
            <div class="flex items-center gap-2.5 sm:gap-3 min-w-0">
              <div class="w-8 h-8 sm:w-9 sm:h-9 rounded-xl ${bgClass} ${colorClass} flex items-center justify-center shrink-0">
                <span class="material-symbols-outlined text-[18px] sm:text-[20px]">${safeIcon}</span>
              </div>
              <div class="flex flex-col min-w-0">
                <div class="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                  <span class="font-mono text-xs sm:text-sm font-bold text-on-surface">${safeSym}</span>
                  <span class="font-mono text-xs sm:text-sm font-medium text-on-surface market-price-${cleanSym}">${safePrice}</span>
                  <span class="inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded-full ${bgClass} ${colorClass} font-mono text-[10px] font-bold">
                    <span class="material-symbols-outlined text-[10px]">trending_up</span>
                    <span class="market-change-${cleanSym}">${safeChange}</span>
                  </span>
                </div>
                <span class="text-[10px] sm:text-[11px] text-on-surface-variant truncate">${safeName}</span>
              </div>
            </div>
            <div class="flex items-center gap-2.5 self-end sm:self-auto shrink-0">
              <div class="flex flex-col items-end">
                <span class="text-[9px] sm:text-[10px] text-on-surface-variant font-mono">${safeMetricTitle}</span>
                <span class="font-mono text-xs ${colorClass} font-bold">${safeMetricVal}</span>
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
          <div class="rounded-xl bg-surface-container-lowest p-3 sm:p-3.5 my-1 border border-emerald-500/25 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs w-full" onclick="event.stopPropagation()">
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
          <div class="rounded-xl bg-surface-container-lowest p-3 sm:p-3.5 my-1 border border-outline-variant/15 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs w-full" onclick="event.stopPropagation()">
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

if f_idx1 != -1 and f_idx2 != -1:
    # AUD15-01: Preserve window.liveMarketPrices = by slicing text from f_idx2 directly
    text = text[:f_idx1] + replacement_fn + '\n\n    // ── Live Multi-Asset Market Telemetry (BTC, ETH, SOL, AAPL, etc.) ─────────────\n    ' + text[f_idx2:]
    print('generateSpacePostEmbedHtml replaced successfully!')

with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.write(text)

print('File updated successfully.')

