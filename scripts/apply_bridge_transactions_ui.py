#!/usr/bin/env python3
"""
apply_bridge_transactions_ui.py
Adds bridge transactions feed to the bridge page (tab-kopru), matching the Explorer style.
"""
import sys

def run():
    with open('frontend/index.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. HTML Insertion in tab-kopru
    # Insert right after the bridge card container (around line 5908)
    card_end_marker = '''            <!-- Order Status Banner (hidden by default) -->
            <div id="bridgeStatusBox"
              class="hidden flex flex-col gap-2 p-4 rounded-2xl bg-surface-container-high border border-outline-variant/20">
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <span class="w-2.5 h-2.5 rounded-full bg-secondary animate-ping"></span>
                  <span class="font-semibold text-xs text-on-surface" id="bridgeStatusTitle">Processing Bridge
                    Order...</span>
                </div>
                <span
                  class="font-mono text-[11px] px-2 py-0.5 rounded-full bg-surface-container-lowest text-on-surface-variant"
                  id="bridgeStatusOrderId">#ORDER-ID</span>
              </div>
              <p class="text-[11px] text-on-surface-variant leading-relaxed" id="bridgeStatusMessage">
                Waiting for on-chain block confirmation...
              </p>
              <div class="flex items-center gap-2 pt-1">
                <a id="bridgeStatusL1TxLink" href="#" target="_blank"
                  class="hidden text-[11px] text-primary hover:underline flex items-center gap-1">
                  <span>View L1 Tx</span>
                  <span class="material-symbols-outlined notranslate text-[13px]" translate="no">open_in_new</span>
                </a>
                <a id="bridgeStatusEvmTxLink" href="#" target="_blank"
                  class="hidden text-[11px] text-secondary hover:underline flex items-center gap-1">
                  <span>View BaseScan</span>
                  <span class="material-symbols-outlined notranslate text-[13px]" translate="no">open_in_new</span>
                </a>
              </div>
            </div>

          </div>'''

    bridge_txs_html = '''          <!-- Bridge Transactions Feed (Same Style & Real-Time Sync as Explorer) -->
          <div class="flex flex-col gap-3.5 p-4 sm:p-5 rounded-3xl bg-surface-container-low border border-outline-variant/20 mt-4 shadow-sm" id="bridgeUserHistoryContainer">
            <!-- Header Row with Title, Filter Tabs (My Activity vs All Bridge), and Refresh Button -->
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-outline-variant/15">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-2xl bg-secondary/15 text-secondary flex items-center justify-center shrink-0">
                  <span class="material-symbols-outlined notranslate text-[20px]" translate="no">history</span>
                </div>
                <div>
                  <div class="flex items-center gap-2">
                    <h3 class="font-bold text-sm text-on-surface">Bridge Activity &amp; History</h3>
                    <span class="px-2 py-0.5 rounded-full bg-secondary/10 text-secondary font-mono text-[10px] font-semibold border border-secondary/20">Base &harr; L1</span>
                  </div>
                  <p class="text-xs text-on-surface-variant mt-0.5">Track your cross-chain lock, burn, mint and unlock records in real-time.</p>
                </div>
              </div>
              <div class="flex items-center gap-2 self-end sm:self-auto">
                <!-- Filter Toggle: My Activity vs All Bridge -->
                <div class="flex items-center p-1 rounded-xl bg-surface-container border border-outline-variant/20 text-xs">
                  <button type="button" id="btnBridgeFilterMy" onclick="setBridgeHistoryFilter('my')"
                    class="py-1 px-3 rounded-lg font-semibold transition-all bg-primary text-on-primary shadow-xs cursor-pointer">
                    My Activity
                  </button>
                  <button type="button" id="btnBridgeFilterAll" onclick="setBridgeHistoryFilter('all')"
                    class="py-1 px-3 rounded-lg font-medium transition-all text-on-surface-variant hover:text-on-surface cursor-pointer">
                    All Bridge
                  </button>
                </div>
                <button type="button" onclick="loadBridgePageTransactions(true)"
                  class="p-2 rounded-xl bg-surface-container hover:bg-surface-container-high text-on-surface-variant hover:text-primary transition-all border border-outline-variant/20 cursor-pointer"
                  title="Refresh Bridge History">
                  <span class="material-symbols-outlined notranslate text-[18px]" translate="no">sync</span>
                </button>
              </div>
            </div>

            <!-- Transaction Feed List -->
            <div class="flex flex-col gap-2" id="bridgePageTxsList">
              <div class="p-5 text-center font-body-sm text-on-surface-variant bg-surface-container rounded-2xl">
                Loading bridge transactions...
              </div>
            </div>

            <!-- Pagination Bar for Bridge Txs -->
            <div id="bridgePageTxsPaginationBar" class="hidden items-center justify-between pt-2.5 border-t border-outline-variant/10 text-xs">
              <span class="text-on-surface-variant font-mono text-[11px]" id="bridgePageTxsCountLabel">Showing 0 transactions</span>
              <div class="flex items-center gap-1.5">
                <button type="button" id="btnBridgePageTxsPrev" onclick="changeBridgePageTxsPage(-1)"
                  class="p-1.5 rounded-lg bg-surface-container hover:bg-surface-container-high text-on-surface disabled:opacity-30 disabled:pointer-events-none cursor-pointer border border-outline-variant/20">
                  <span class="material-symbols-outlined notranslate text-[16px]" translate="no">chevron_left</span>
                </button>
                <span class="px-2.5 py-0.5 font-mono text-[11px] text-on-surface font-semibold" id="bridgePageTxsPageLabel">1 / 1</span>
                <button type="button" id="btnBridgePageTxsNext" onclick="changeBridgePageTxsPage(1)"
                  class="p-1.5 rounded-lg bg-surface-container hover:bg-surface-container-high text-on-surface disabled:opacity-30 disabled:pointer-events-none cursor-pointer border border-outline-variant/20">
                  <span class="material-symbols-outlined notranslate text-[16px]" translate="no">chevron_right</span>
                </button>
              </div>
            </div>
          </div>\n\n'''

    assert card_end_marker in content, 'card_end_marker not found'
    if 'id="bridgeUserHistoryContainer"' not in content:
        content = content.replace(card_end_marker, card_end_marker + '\n\n' + bridge_txs_html, 1)

    # 2. Hook switchTab('kopru')
    switch_hook_marker = '''      if (target === 'ag-ve-explorer' || target === 'dugum-paneli') {
        if (typeof loadStakingParticipantsUI === 'function') loadStakingParticipantsUI();
      }'''

    switch_hook_replacement = '''      if (target === 'ag-ve-explorer' || target === 'dugum-paneli') {
        if (typeof loadStakingParticipantsUI === 'function') loadStakingParticipantsUI();
      }
      if (target === 'kopru') {
        if (typeof loadBridgePageTransactions === 'function') loadBridgePageTransactions();
      }'''

    assert switch_hook_marker in content, 'switch_hook_marker not found'
    if "if (target === 'kopru')" not in content:
        content = content.replace(switch_hook_marker, switch_hook_replacement, 1)

    # 3. JavaScript Logic for Bridge Page Activity
    # Insert right before function loadBridgeConfig()
    js_marker = '    async function loadBridgeConfig() {'

    js_code = '''    // ── Bridge Page Transaction Feed & Activity (Explorer Style) ──────────────
    let bridgeHistoryFilter = 'my';
    let allBridgePageTxs = [];
    let currentBridgePageTxsPage = 1;
    const bridgePageTxsPageSize = 8;

    function setBridgeHistoryFilter(filter) {
      bridgeHistoryFilter = filter;
      currentBridgePageTxsPage = 1;
      const btnMy = document.getElementById('btnBridgeFilterMy');
      const btnAll = document.getElementById('btnBridgeFilterAll');
      if (filter === 'my') {
        if (btnMy) btnMy.className = 'py-1 px-3 rounded-lg font-semibold transition-all bg-primary text-on-primary shadow-xs cursor-pointer';
        if (btnAll) btnAll.className = 'py-1 px-3 rounded-lg font-medium transition-all text-on-surface-variant hover:text-on-surface cursor-pointer';
      } else {
        if (btnAll) btnAll.className = 'py-1 px-3 rounded-lg font-semibold transition-all bg-primary text-on-primary shadow-xs cursor-pointer';
        if (btnMy) btnMy.className = 'py-1 px-3 rounded-lg font-medium transition-all text-on-surface-variant hover:text-on-surface cursor-pointer';
      }
      renderBridgePageTransactions();
    }

    async function loadBridgePageTransactions(forceToast = false) {
      const list = document.getElementById('bridgePageTxsList');
      try {
        const res = await apiFetch('/bridge/base-transactions?limit=100');
        let txs = null;
        if (res && res.body && res.body.data && Array.isArray(res.body.data.transactions)) {
          txs = res.body.data.transactions;
        } else if (res && res.data && Array.isArray(res.data.transactions)) {
          txs = res.data.transactions;
        }

        if (txs) {
          allBridgePageTxs = txs;
          renderBridgePageTransactions();
          if (forceToast) showToast('Bridge activity refreshed', 'info');
        } else {
          allBridgePageTxs = [];
          if (list) list.innerHTML = '<div class="p-5 text-center font-body-sm text-on-surface-variant bg-surface-container rounded-2xl">No bridge transactions found on network.</div>';
          updateBridgePageTxsPaginationUI(0);
        }
      } catch (err) {
        console.warn('Could not load bridge transactions for bridge page:', err);
        if (list && !allBridgePageTxs.length) {
          list.innerHTML = `<div class="p-5 text-center font-body-sm text-rose-400 bg-surface-container rounded-2xl">Could not load bridge transactions: ${escapeHtml(err.message || 'Error')}</div>`;
        }
      }
    }

    function renderBridgePageTransactions() {
      const list = document.getElementById('bridgePageTxsList');
      if (!list) return;

      const myL1 = currentAccount && currentAccount.address ? String(currentAccount.address).trim().toLowerCase() : null;
      const myEvm = userMetaMaskAddress ? String(userMetaMaskAddress).trim().toLowerCase() : null;

      let filtered = allBridgePageTxs;
      if (bridgeHistoryFilter === 'my') {
        if (!myL1 && !myEvm) {
          list.innerHTML = `
            <div class="p-6 text-center rounded-2xl bg-surface-container border border-outline-variant/15 flex flex-col items-center justify-center gap-2.5">
              <span class="material-symbols-outlined notranslate text-outline text-[32px]" translate="no">account_balance_wallet</span>
              <p class="font-body-sm text-xs text-on-surface-variant max-w-sm leading-relaxed">
                Connect your LockTrace L1 or Web3 EVM wallet to view your personal cross-chain transfer records.
              </p>
              <div class="flex items-center gap-2 mt-1">
                <button type="button" onclick="handleConnectEvmWalletClick()" class="px-3.5 py-1.5 rounded-xl bg-primary/10 hover:bg-primary/20 text-primary font-semibold text-xs transition-all cursor-pointer">Connect EVM Wallet</button>
                <button type="button" onclick="setBridgeHistoryFilter('all')" class="px-3.5 py-1.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-semibold text-xs transition-all cursor-pointer">View All Bridge Txs</button>
              </div>
            </div>
          `;
          updateBridgePageTxsPaginationUI(0);
          return;
        }

        filtered = allBridgePageTxs.filter(t => {
          const tL1 = t.bct_address ? String(t.bct_address).toLowerCase() : '';
          const tEvm = t.evm_address ? String(t.evm_address).toLowerCase() : '';
          return (myL1 && tL1 === myL1) || (myEvm && tEvm === myEvm);
        });

        if (!filtered.length) {
          list.innerHTML = `
            <div class="p-6 text-center rounded-2xl bg-surface-container border border-outline-variant/15 flex flex-col items-center justify-center gap-2">
              <span class="material-symbols-outlined notranslate text-outline text-[32px]" translate="no">history_toggle_off</span>
              <p class="font-body-sm text-xs text-on-surface-variant">
                No bridge transactions recorded yet for your connected wallet.
              </p>
              <button type="button" onclick="setBridgeHistoryFilter('all')" class="px-3.5 py-1.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-primary font-semibold text-xs transition-all cursor-pointer">
                Browse All Network Bridge Txs
              </button>
            </div>
          `;
          updateBridgePageTxsPaginationUI(0);
          return;
        }
      }

      const totalPages = Math.ceil(filtered.length / bridgePageTxsPageSize) || 1;
      if (currentBridgePageTxsPage > totalPages) currentBridgePageTxsPage = totalPages;
      if (currentBridgePageTxsPage < 1) currentBridgePageTxsPage = 1;

      const start = (currentBridgePageTxsPage - 1) * bridgePageTxsPageSize;
      const pageTxs = filtered.slice(start, start + bridgePageTxsPageSize);

      try {
        list.innerHTML = pageTxs.map(t => {
          const isMint = t.direction === 'L1_TO_EVM';
          const typeBadge = isMint
            ? '<span class="px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 text-[10.5px] font-semibold font-mono flex items-center gap-1 shrink-0"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>Base Mint</span>'
            : '<span class="px-2 py-0.5 rounded-full bg-secondary/15 text-secondary border border-secondary/30 text-[10.5px] font-semibold font-mono flex items-center gap-1 shrink-0"><span class="w-1.5 h-1.5 rounded-full bg-secondary"></span>Base Burn</span>';

          const statusColor = t.status === 'COMPLETED' ? 'text-emerald-400' : (t.status === 'LOCKED' ? 'text-secondary' : (t.status === 'FAILED' ? 'text-rose-400' : 'text-amber-400'));
          const displayEvm = t.tx_hash_evm ? (t.tx_hash_evm.slice(0, 8) + '...' + t.tx_hash_evm.slice(-6)) : 'Pending (L2)';
          const evmLink = t.basescan_tx_url
            ? `<a href="${escapeHtml(t.basescan_tx_url)}" target="_blank" rel="noopener noreferrer" class="font-mono text-xs font-semibold text-secondary hover:underline flex items-center gap-0.5" title="View on BaseScan">${escapeHtml(displayEvm)}<span class="material-symbols-outlined notranslate text-[12px]" translate="no">open_in_new</span></a>`
            : `<span class="font-mono text-xs text-on-surface-variant">${escapeHtml(displayEvm)}</span>`;

          const bctDisplay = t.bct_address ? (t.bct_address.slice(0, 8) + '...' + t.bct_address.slice(-6)) : '--';
          const evmRecipientDisplay = t.evm_address ? (t.evm_address.slice(0, 8) + '...' + t.evm_address.slice(-6)) : '--';
          const timeAgo = t.created_at ? formatTimeAgo(t.created_at) : 'recently';
          const amountStr = typeof formatBct === 'function' ? formatBct(t.amount, 4) : Number(t.amount || 0).toFixed(4);

          const l1TxBtn = t.tx_hash_l1
            ? `<button type="button" onclick="inspectExplorerTx('${sanitizeJsAttr(t.tx_hash_l1)}')" class="text-primary hover:underline font-mono font-semibold" title="${escapeHtml(t.tx_hash_l1)}">${escapeHtml(t.tx_hash_l1.slice(0, 8))}...${escapeHtml(t.tx_hash_l1.slice(-6))}</button>`
            : '<span class="text-on-surface-variant">--</span>';

          return `
            <div class="p-3 sm:p-3.5 rounded-2xl bg-surface-container hover:bg-surface-container-high/80 border border-outline-variant/15 flex flex-col gap-2 transition-all">
              <div class="flex items-center justify-between gap-2 flex-wrap">
                <div class="flex items-center gap-2 flex-wrap">
                  ${typeBadge}
                  ${evmLink}
                </div>
                <div class="flex items-center gap-2 ml-auto">
                  <span class="font-mono text-xs sm:text-sm font-bold text-on-surface">${amountStr} wBCT</span>
                  <span class="text-[10px] font-mono uppercase font-semibold px-2 py-0.5 rounded-full bg-surface-container-lowest border border-outline-variant/20 ${statusColor}">${escapeHtml(t.status)}</span>
                </div>
              </div>
              <div class="flex items-center justify-between gap-2 text-[11px] text-on-surface-variant flex-wrap pt-1.5 border-t border-outline-variant/10">
                <div class="flex items-center gap-1.5 font-mono flex-wrap">
                  <span>L1: <button type="button" onclick="openUserProfile('${sanitizeJsAttr(t.bct_address)}')" class="text-primary hover:underline font-semibold" title="${escapeHtml(t.bct_address)}">${escapeHtml(bctDisplay)}</button></span>
                  <span>&bull;</span>
                  <span>Base EVM: <a href="https://basescan.org/address/${escapeHtml(t.evm_address)}" target="_blank" rel="noopener noreferrer" class="text-secondary hover:underline" title="${escapeHtml(t.evm_address)}">${escapeHtml(evmRecipientDisplay)}</a></span>
                  <span>&bull;</span>
                  <span>L1 Tx: ${l1TxBtn}</span>
                </div>
                <span class="text-[10.5px] font-sans text-on-surface-variant/80 ml-auto">${timeAgo}</span>
              </div>
            </div>
          `;
        }).join('');
      } catch (e) {
        console.error('Error rendering bridge page transactions:', e);
      }

      updateBridgePageTxsPaginationUI(filtered.length);
    }

    function changeBridgePageTxsPage(delta) {
      const myL1 = currentAccount && currentAccount.address ? String(currentAccount.address).trim().toLowerCase() : null;
      const myEvm = userMetaMaskAddress ? String(userMetaMaskAddress).trim().toLowerCase() : null;
      let filtered = allBridgePageTxs;
      if (bridgeHistoryFilter === 'my') {
        filtered = allBridgePageTxs.filter(t => {
          const tL1 = t.bct_address ? String(t.bct_address).toLowerCase() : '';
          const tEvm = t.evm_address ? String(t.evm_address).toLowerCase() : '';
          return (myL1 && tL1 === myL1) || (myEvm && tEvm === myEvm);
        });
      }
      const totalPages = Math.ceil(filtered.length / bridgePageTxsPageSize) || 1;
      const targetPage = currentBridgePageTxsPage + delta;
      if (targetPage < 1 || targetPage > totalPages) return;
      currentBridgePageTxsPage = targetPage;
      renderBridgePageTransactions();
    }

    function updateBridgePageTxsPaginationUI(totalCount) {
      const pBar = document.getElementById('bridgePageTxsPaginationBar');
      const lblPage = document.getElementById('bridgePageTxsPageLabel');
      const lblCount = document.getElementById('bridgePageTxsCountLabel');
      const btnPrev = document.getElementById('btnBridgePageTxsPrev');
      const btnNext = document.getElementById('btnBridgePageTxsNext');

      if (!totalCount) {
        if (pBar) pBar.classList.add('hidden');
        if (pBar) pBar.classList.remove('flex');
        return;
      }
      if (pBar) {
        pBar.classList.remove('hidden');
        pBar.classList.add('flex');
      }

      const totalPages = Math.ceil(totalCount / bridgePageTxsPageSize) || 1;
      if (lblPage) lblPage.textContent = `${currentBridgePageTxsPage} / ${totalPages}`;
      if (lblCount) {
        const start = (currentBridgePageTxsPage - 1) * bridgePageTxsPageSize + 1;
        const end = Math.min(start + bridgePageTxsPageSize - 1, totalCount);
        lblCount.textContent = `Showing ${start}-${end} of ${totalCount} transactions`;
      }
      if (btnPrev) btnPrev.disabled = currentBridgePageTxsPage <= 1;
      if (btnNext) btnNext.disabled = currentBridgePageTxsPage >= totalPages;
    }

    function inspectExplorerTx(hash) {
      if (!hash) return;
      switchTab('ag-ve-explorer');
      const input = document.getElementById('explorerSearchInput');
      if (input) {
        input.value = hash;
        triggerExplorerSearch();
      }
    }\n\n'''

    assert js_marker in content, 'js_marker not found'
    if 'function loadBridgePageTransactions' not in content:
        content = content.replace(js_marker, js_code + js_marker, 1)

    # 4. Trigger loadBridgePageTransactions after bridge order creation/completion
    order_create_marker = "displayBridgeStatusBox(bridgeId, l1TxHash);"
    if order_create_marker in content and "loadBridgePageTransactions();" not in content[content.find(order_create_marker):content.find(order_create_marker)+100]:
        content = content.replace(order_create_marker, order_create_marker + "\n          loadBridgePageTransactions();", 1)

    claim_done_marker = "displayBridgeStatusBox(claimBody.data.bridge_id || 'burn_' + evmTxHash.substring(2, 10), l1Hash);"
    if claim_done_marker in content and "loadBridgePageTransactions();" not in content[content.find(claim_done_marker):content.find(claim_done_marker)+150]:
        content = content.replace(claim_done_marker, claim_done_marker + "\n          loadBridgePageTransactions();", 1)

    # Write files
    with open('frontend/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(content)

    print('SUCCESS: Bridge page transaction list applied to frontend/index.html and templates/index.html!')

if __name__ == '__main__':
    run()
