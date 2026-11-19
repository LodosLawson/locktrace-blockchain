#!/usr/bin/env python3
"""
patch_web3_flow.py
Implements seamless Web3 wallet connection, MetaMask direct signing,
EIP-6963 discovery, Coinbase & Trust deep linking, and automated on-chain
transaction recovery for LockTrace Bridge.
"""
import sys

def apply_patches():
    with open('frontend/index.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Action Banner insertion
    banner_html = '''  <!-- ========================================================================= -->
  <!-- FLOATING ACTION BANNER: METAMASK SIGNING / CONFIRMATION                   -->
  <!-- ========================================================================= -->
  <div id="metaMaskActionBanner"
    class="fixed bottom-6 left-4 right-4 sm:left-auto sm:right-6 sm:w-96 z-[10001] p-4 rounded-3xl bg-surface-container-high/95 backdrop-blur-xl border-2 border-amber-500/50 shadow-2xl hidden items-center justify-between gap-3 animate-pulse">
    <div class="flex items-center gap-3 min-w-0">
      <div class="w-10 h-10 rounded-2xl bg-amber-500/20 text-amber-400 border border-amber-500/30 flex items-center justify-center shrink-0">
        <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none">
          <path d="M21.1 2.3l-8.6 6.3 1.6-3.8-1-1.3-4.3 3.1 1.6 3.8L1.8 2.3c-.6-.4-1.4.1-1.3.8l2.6 13.9c.1.6.6 1.1 1.2 1.2l6.8 1.4v-4.1l-4.1-.9 1.4-1.3-3.6-1.5 5.5-2 1.3 4.8 1.3-4.8 5.5 2-3.6 1.5 1.4 1.3-4.1.9v4.1l6.8-1.4c.6-.1 1.1-.6 1.2-1.2L22.4 3.1c.1-.7-.7-1.2-1.3-.8z" fill="#E2761B"/>
        </svg>
      </div>
      <div class="flex flex-col min-w-0">
        <span class="font-bold text-xs text-on-surface truncate" id="mmActionBannerTitle">Confirm in MetaMask</span>
        <span class="text-[11px] text-on-surface-variant truncate" id="mmActionBannerSubtitle">Tap if MetaMask did not open</span>
      </div>
    </div>
    <div class="flex items-center gap-1.5 shrink-0">
      <button type="button" id="mmActionBannerBtn"
        class="py-2 px-3.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs shadow-md transition-all active:scale-95 cursor-pointer flex items-center gap-1">
        <span>Open</span>
        <span class="material-symbols-outlined notranslate text-[16px]" translate="no">arrow_outward</span>
      </button>
      <button type="button" onclick="hideMetaMaskActionBanner()"
        class="w-7 h-7 rounded-full bg-surface-container hover:bg-surface-variant text-on-surface-variant flex items-center justify-center transition-colors cursor-pointer">
        <span class="material-symbols-outlined notranslate text-[14px]" translate="no">close</span>
      </button>
    </div>
  </div>\n\n'''

    target_marker = '  <!-- ========================================================================= -->\n  <!-- MODAL: MOBILE & DESKTOP WEB3 WALLET CONNECTOR'
    if target_marker in content and 'id="metaMaskActionBanner"' not in content:
        content = content.replace(target_marker, banner_html + target_marker, 1)

    # 2. Add alternative buttons inside modal
    mm_button_end = 'id="mmStatusSubtitle">Direct Connect &amp; Sign (Stay in Browser)</span>\n            </div>\n          </div>\n          <span class="material-symbols-outlined notranslate text-on-surface-variant group-hover:text-amber-400 text-[18px] transition-transform group-hover:translate-x-0.5" translate="no">chevron_right</span>\n        </button>'

    mm_alt_html = '''        <!-- MetaMask In-App Browser Option (1-Tap Web3 Browser Fallback) -->
        <a id="btnMetaMaskInAppBrowser" href="https://metamask.app.link/dapp/locktrace.space?tab=kopru&dir=EVM_TO_L1" target="_blank"
          class="group flex items-center justify-between p-3 rounded-2xl bg-surface-container-lowest hover:bg-surface-container-high border border-outline-variant/15 hover:border-amber-500/30 transition-all text-left shadow-sm">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
              <span class="material-symbols-outlined notranslate text-amber-400 text-[20px]" translate="no">open_in_browser</span>
            </div>
            <div class="flex flex-col">
              <div class="flex items-center gap-1.5">
                <span class="font-bold text-xs text-on-surface group-hover:text-amber-400 transition-colors">MetaMask DApp Browser</span>
                <span class="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-amber-500/10 text-amber-300">In-App</span>
              </div>
              <span class="text-[11px] text-on-surface-variant">Launch inside MetaMask\'s built-in Web3 browser</span>
            </div>
          </div>
          <span class="material-symbols-outlined notranslate text-on-surface-variant group-hover:text-amber-400 text-[18px]" translate="no">open_in_new</span>
        </a>'''

    if mm_button_end in content and 'id="btnMetaMaskInAppBrowser"' not in content:
        content = content.replace(mm_button_end, mm_button_end + '\n\n' + mm_alt_html, 1)

    # 3. Add Coinbase Wallet button
    trust_button_end = '<!-- Trust Wallet Option -->\n        <button type="button" onclick="connectOrLaunchWeb3Wallet(\'trust\')"'
    cb_option_html = '''<!-- Coinbase Wallet Option -->
        <button type="button" onclick="connectOrLaunchWeb3Wallet(\'coinbase\')"
          class="group flex items-center justify-between p-3.5 rounded-2xl bg-surface-container-lowest hover:bg-surface-container-high border border-outline-variant/20 hover:border-blue-600/40 transition-all text-left cursor-pointer shadow-sm">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-blue-600/10 border border-blue-600/20 flex items-center justify-center shrink-0">
              <svg class="w-5 h-5" viewBox="0 0 24 24" fill="#0052FF">
                <path d="M12 24C18.6274 24 24 18.6274 24 12C24 5.37258 18.6274 0 12 0C5.37258 0 0 5.37258 0 12C0 18.6274 5.37258 24 12 24ZM12 4.5C16.1421 4.5 19.5 7.85786 19.5 12C19.5 16.1421 16.1421 19.5 12 19.5C7.85786 19.5 4.5 16.1421 4.5 12C4.5 7.85786 7.85786 4.5 12 4.5ZM10.5 8.5C9.39543 8.5 8.5 9.39543 8.5 10.5V13.5C8.5 14.6046 9.39543 15.5 10.5 15.5H13.5C14.6046 15.5 15.5 14.6046 15.5 13.5V10.5C15.5 9.39543 14.6046 8.5 13.5 8.5H10.5Z"/>
              </svg>
            </div>
            <div class="flex flex-col">
              <span class="font-bold text-xs text-on-surface group-hover:text-blue-500 transition-colors">Coinbase Wallet</span>
              <span class="text-[11px] text-on-surface-variant">Web3 Extension / Mobile App</span>
            </div>
          </div>
          <span class="material-symbols-outlined notranslate text-on-surface-variant group-hover:text-blue-500 text-[18px] transition-transform group-hover:translate-x-0.5" translate="no">chevron_right</span>
        </button>\n\n        '''

    if trust_button_end in content and 'connectOrLaunchWeb3Wallet(\'coinbase\')' not in content:
        content = content.replace(trust_button_end, cb_option_html + trust_button_end, 1)

    # 4. JavaScript helpers and SDK enhancements
    # Target from 'function getOrInitMetaMaskSDK()' to 'function isChainIdBase('
    old_sdk_init = '''    function getOrInitMetaMaskSDK() {
      if (mmSdkInstance) return mmSdkInstance;
      const SdkCtor = (typeof window !== 'undefined' && window.MetaMaskSDK)
        ? (window.MetaMaskSDK.MetaMaskSDK || window.MetaMaskSDK.default || (typeof window.MetaMaskSDK === 'function' ? window.MetaMaskSDK : null))
        : null;
      if (!SdkCtor) return null;
      try {
        mmSdkInstance = new SdkCtor({
          dappMetadata: {
            name: 'LockTrace Bridge (BlocTag)',
            url: window.location.origin,
            iconUrl: `${window.location.origin}/icons/icon-192.png`
          },
          defaultReadOnlyChainId: '0x2105',
          readonlyRPCMap: {
            '0x2105': 'https://mainnet.base.org'
          },
          preferDesktop: false,
          useDeeplink: true,
          openDeeplink: (link) => {
            if (link && typeof window !== 'undefined') {
              window.location.href = link;
            }
          },
          injectProvider: false,
          shouldShimWeb3: false,
          enableAnalytics: false,
          checkInstallationImmediately: false,
          logging: { developerMode: false, sdk: false }
        });
        return mmSdkInstance;
      } catch (err) {
        console.warn('MetaMaskSDK init error:', err);
        return null;
      }
    }'''

    new_sdk_init = '''    let latestMetaMaskDeeplink = null;
    let latestMetaMaskUniversalLink = null;
    let activeSigningActionDismissTimer = null;

    function getMetaMaskDeeplinkVariants(link) {
      if (!link || typeof link !== 'string') return { deep: null, universal: null };
      let deep = link;
      let universal = link;
      if (link.startsWith('metamask://')) {
        universal = link.replace(/^metamask:\\/\\//, 'https://metamask.app.link/');
      } else if (link.startsWith('https://metamask.app.link/')) {
        deep = link.replace(/^https:\\/\\/metamask\\.app\\.link\\//, 'metamask://');
      }
      return { deep, universal };
    }

    function showMetaMaskActionBanner(title, subtitle, targetLink) {
      const banner = document.getElementById('metaMaskActionBanner');
      if (!banner) return;
      const tEl = document.getElementById('mmActionBannerTitle');
      const sEl = document.getElementById('mmActionBannerSubtitle');
      const btn = document.getElementById('mmActionBannerBtn');

      if (tEl) tEl.textContent = title || 'Confirm in MetaMask';
      if (sEl) sEl.textContent = subtitle || 'Tap to open the MetaMask signing sheet';
      if (btn && targetLink) {
        btn.onclick = () => {
          openMetaMaskDirectly(targetLink);
        };
      }
      banner.classList.remove('hidden');
      banner.classList.add('flex');
      if (activeSigningActionDismissTimer) clearTimeout(activeSigningActionDismissTimer);
    }

    function hideMetaMaskActionBanner() {
      const banner = document.getElementById('metaMaskActionBanner');
      if (!banner) return;
      banner.classList.add('hidden');
      banner.classList.remove('flex');
      if (activeSigningActionDismissTimer) {
        clearTimeout(activeSigningActionDismissTimer);
        activeSigningActionDismissTimer = null;
      }
    }

    function openMetaMaskDirectly(overrideLink = null) {
      const link = overrideLink || latestMetaMaskDeeplink || latestMetaMaskUniversalLink || 'metamask://';
      try {
        window.location.href = link;
      } catch (_e) { }
      setTimeout(() => {
        if (latestMetaMaskUniversalLink && latestMetaMaskUniversalLink !== link) {
          try { window.location.href = latestMetaMaskUniversalLink; } catch (_e) { }
        }
      }, 500);
    }

    async function checkForRecentOnChainBurn(userAddress, contractAddress) {
      try {
        if (!userAddress || !contractAddress) return null;
        const burnedTopic = ethers.id("BurnedToBridge(address,uint256,string)");
        const cleanSender = String(userAddress).trim().toLowerCase();
        const paddedSender = ethers.zeroPadValue(cleanSender, 32);

        const latestBlockHex = await callBaseJsonRpc('eth_blockNumber', []);
        if (!latestBlockHex) return null;
        const latestBlock = parseInt(latestBlockHex, 16);
        const fromBlockHex = '0x' + Math.max(0, latestBlock - 30).toString(16);

        const logs = await callBaseJsonRpc('eth_getLogs', [{
          fromBlock: fromBlockHex,
          toBlock: 'latest',
          address: contractAddress,
          topics: [burnedTopic, paddedSender]
        }]);

        if (Array.isArray(logs) && logs.length > 0) {
          const lastLog = logs[logs.length - 1];
          if (lastLog && lastLog.transactionHash) {
            return lastLog.transactionHash;
          }
        }
      } catch (err) {
        console.warn('Could not query recent on-chain burn events:', err);
      }
      return null;
    }

    function getOrInitMetaMaskSDK() {
      if (mmSdkInstance) return mmSdkInstance;
      const SdkCtor = (typeof window !== 'undefined' && window.MetaMaskSDK)
        ? (window.MetaMaskSDK.MetaMaskSDK || window.MetaMaskSDK.default || (typeof window.MetaMaskSDK === 'function' ? window.MetaMaskSDK : null))
        : null;
      if (!SdkCtor) return null;
      try {
        mmSdkInstance = new SdkCtor({
          dappMetadata: {
            name: 'LockTrace Bridge (BlocTag)',
            url: window.location.origin,
            iconUrl: `${window.location.origin}/icons/icon-192.png`
          },
          defaultReadOnlyChainId: '0x2105',
          readonlyRPCMap: {
            '0x2105': 'https://mainnet.base.org'
          },
          preferDesktop: false,
          useDeeplink: true,
          openDeeplink: (link) => {
            if (link && typeof window !== 'undefined') {
              const { deep, universal } = getMetaMaskDeeplinkVariants(link);
              latestMetaMaskDeeplink = deep;
              latestMetaMaskUniversalLink = universal;

              try {
                window.location.href = isMobileUser() ? (deep || link) : link;
              } catch (_e) { }

              if (isMobileUser()) {
                showMetaMaskActionBanner(
                  'MetaMask Request Ready',
                  'Tap below if MetaMask did not open automatically:',
                  deep || link
                );
              }
            }
          },
          injectProvider: false,
          shouldShimWeb3: false,
          enableAnalytics: false,
          checkInstallationImmediately: false,
          logging: { developerMode: false, sdk: false }
        });
        return mmSdkInstance;
      } catch (err) {
        console.warn('MetaMaskSDK init error:', err);
        return null;
      }
    }'''

    assert old_sdk_init in content, 'old_sdk_init block not found'
    content = content.replace(old_sdk_init, new_sdk_init, 1)

    # 5. Add visibility & focus listeners for seamless mobile resumption
    vis_target = '''    // EIP-6963: Multi-Injected Provider Discovery (MetaMask, Coinbase, Trust, Rainbow, OKX, Phantom, Rabby)
    if (typeof window !== 'undefined') {'''

    vis_replacement = '''    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
          if (mmSdkInstance && typeof mmSdkInstance.resume === 'function') {
            try { mmSdkInstance.resume(); } catch (_e) { }
          }
          if (userMetaMaskAddress) {
            checkMetaMaskWbctBalance();
          }
        }
      });
      window.addEventListener('focus', () => {
        if (mmSdkInstance && typeof mmSdkInstance.resume === 'function') {
          try { mmSdkInstance.resume(); } catch (_e) { }
        }
      });
    }

    // EIP-6963: Multi-Injected Provider Discovery (MetaMask, Coinbase, Trust, Rainbow, OKX, Phantom, Rabby)
    if (typeof window !== 'undefined') {'''

    assert vis_target in content, 'vis_target not found'
    content = content.replace(vis_target, vis_replacement, 1)

    # 6. Update connectOrLaunchWeb3Wallet to handle 'coinbase' and clean 'metamask'
    wallet_switch_target = '''    async function connectOrLaunchWeb3Wallet(walletType = 'metamask') {
      closeMobileWalletModal();

      if (walletType === 'metamask') {
        // 1. If MetaMask extension or in-app browser is injected, use it directly
        const mmEip6963 = announcedEip6963Providers.find(p => p.info && (p.info.rdns === 'io.metamask' || /metamask/i.test(p.info.name || '')));
        if (mmEip6963 && mmEip6963.provider) {
          await connectEvmWalletDirect(mmEip6963.provider, 'MetaMask');
          return;
        }
        const injected = getInjectedEvmProvider(true);
        if (injected && injected.isMetaMask) {
          await connectEvmWalletDirect(injected, 'MetaMask');
          return;
        }

        // 2. Otherwise use MetaMask SDK: opens native MetaMask Connect/Sign sheet directly
        //    WITHOUT redirecting to MetaMask's in-app browser! (Also supports Desktop QR!)
        await connectViaMetaMaskSDK();
        return;
      }

      if (walletType === 'trust') {
        const trustEip = announcedEip6963Providers.find(p => p.info && /trust/i.test(p.info.name || p.info.rdns || ''));
        if (trustEip && trustEip.provider) {
          await connectEvmWalletDirect(trustEip.provider, 'Trust Wallet');
          return;
        }
        if (window.trustwallet || (window.ethereum && window.ethereum.isTrust)) {
          await connectEvmWalletDirect(window.trustwallet || window.ethereum, 'Trust Wallet');
          return;
        }
        const injected = getInjectedEvmProvider(false);
        if (injected) {
          await connectEvmWalletDirect(injected, 'Web3 Wallet');
          return;
        }
        if (isMobileUser()) {
          showToast('Opening Trust Wallet...', 'info');
          const rawUrl = `${window.location.origin}${window.location.pathname}?tab=kopru&dir=${encodeURIComponent(currentBridgeDirection)}`;
          window.location.href = `https://link.trustwallet.com/open_url?coin_id=60&url=${encodeURIComponent(rawUrl)}`;
          return;
        }
        window.open('https://trustwallet.com/browser-extension', '_blank');
        return;
      }

      const fallbackProvider = getEvmProvider();
      if (fallbackProvider) {
        await connectEvmWalletDirect(fallbackProvider);
      } else {
        await connectViaMetaMaskSDK();
      }
    }'''

    wallet_switch_replacement = '''    async function connectOrLaunchWeb3Wallet(walletType = 'metamask') {
      closeMobileWalletModal();

      if (walletType === 'metamask') {
        // 1. If MetaMask extension or in-app browser is injected, use it directly
        const mmEip6963 = announcedEip6963Providers.find(p => p.info && (p.info.rdns === 'io.metamask' || /metamask/i.test(p.info.name || '')));
        if (mmEip6963 && mmEip6963.provider) {
          await connectEvmWalletDirect(mmEip6963.provider, 'MetaMask');
          return;
        }
        const injected = getInjectedEvmProvider(true);
        if (injected && (injected.isMetaMask || /MetaMaskMobile/i.test(navigator.userAgent || ''))) {
          await connectEvmWalletDirect(injected, 'MetaMask');
          return;
        }

        // 2. Otherwise use MetaMask SDK: opens native MetaMask Connect/Sign sheet directly
        await connectViaMetaMaskSDK();
        return;
      }

      if (walletType === 'trust') {
        const trustEip = announcedEip6963Providers.find(p => p.info && /trust/i.test(p.info.name || p.info.rdns || ''));
        if (trustEip && trustEip.provider) {
          await connectEvmWalletDirect(trustEip.provider, 'Trust Wallet');
          return;
        }
        if (window.trustwallet || (window.ethereum && window.ethereum.isTrust)) {
          await connectEvmWalletDirect(window.trustwallet || window.ethereum, 'Trust Wallet');
          return;
        }
        const injected = getInjectedEvmProvider(false);
        if (injected) {
          await connectEvmWalletDirect(injected, 'Trust Wallet');
          return;
        }
        if (isMobileUser()) {
          showToast('Opening Trust Wallet...', 'info');
          const rawUrl = `${window.location.origin}${window.location.pathname}?tab=kopru&dir=${encodeURIComponent(currentBridgeDirection)}`;
          window.location.href = `https://link.trustwallet.com/open_url?coin_id=60&url=${encodeURIComponent(rawUrl)}`;
          return;
        }
        window.open('https://trustwallet.com/browser-extension', '_blank');
        return;
      }

      if (walletType === 'coinbase') {
        const cbEip = announcedEip6963Providers.find(p => p.info && /coinbase/i.test(p.info.name || p.info.rdns || ''));
        if (cbEip && cbEip.provider) {
          await connectEvmWalletDirect(cbEip.provider, 'Coinbase Wallet');
          return;
        }
        if (window.coinbaseWalletExtension || (window.ethereum && window.ethereum.isCoinbaseWallet)) {
          await connectEvmWalletDirect(window.coinbaseWalletExtension || window.ethereum, 'Coinbase Wallet');
          return;
        }
        const injected = getInjectedEvmProvider(false);
        if (injected) {
          await connectEvmWalletDirect(injected, 'Coinbase Wallet');
          return;
        }
        if (isMobileUser()) {
          showToast('Opening Coinbase Wallet...', 'info');
          const rawUrl = `${window.location.origin}${window.location.pathname}?tab=kopru&dir=${encodeURIComponent(currentBridgeDirection)}`;
          window.location.href = `https://go.cb-w.com/dapp?cb_url=${encodeURIComponent(rawUrl)}`;
          return;
        }
        window.open('https://www.coinbase.com/wallet', '_blank');
        return;
      }

      const fallbackProvider = getEvmProvider();
      if (fallbackProvider) {
        await connectEvmWalletDirect(fallbackProvider);
      } else {
        await connectViaMetaMaskSDK();
      }
    }'''

    assert wallet_switch_target in content, 'wallet_switch_target not found'
    content = content.replace(wallet_switch_target, wallet_switch_replacement, 1)

    # 7. Update handleBridgeSubmit to include On-Chain Recovery and Action Banner
    burn_target = '''          const wbctIface = new ethers.Interface([
            "function burnToBridge(uint256 amount, string calldata locktraceRecipient) external"
          ]);
          const encodedData = wbctIface.encodeFunctionData("burnToBridge", [amountWei, cleanDest]);

          if (btnText) btnText.textContent = 'Confirm in Wallet...';
          showToast(`Opening MetaMask to sign ${formatBct(amount, 2)} wBCT burn transaction...`, 'info');

          const evmTxHash = await evmProvider.request({
            method: 'eth_sendTransaction',
            params: [{
              from: userEvm,
              to: contractAddr,
              data: encodedData,
              value: '0x0'
            }]
          });

          if (!evmTxHash || typeof evmTxHash !== 'string') {
            throw new Error('Could not obtain EVM transaction hash.');
          }'''

    burn_replacement = '''          const wbctIface = new ethers.Interface([
            "function burnToBridge(uint256 amount, string calldata locktraceRecipient) external"
          ]);
          const encodedData = wbctIface.encodeFunctionData("burnToBridge", [amountWei, cleanDest]);

          if (btnText) btnText.textContent = 'Confirm in Wallet...';
          showToast(`Opening MetaMask to sign ${formatBct(amount, 2)} wBCT burn transaction...`, 'info');

          let evmTxHash = null;
          let fallbackRecoveryInterval = null;
          let recoveryFoundHash = null;

          // Background on-chain event watcher for mobile users:
          // If MetaMask app signs and user returns but websocket dropped,
          // this automatically recovers the mined tx hash!
          if (isMobileUser() || isMmSdk) {
            fallbackRecoveryInterval = setInterval(async () => {
              if (evmTxHash || recoveryFoundHash) return;
              try {
                const found = await checkForRecentOnChainBurn(userEvm, contractAddr);
                if (found && !evmTxHash) {
                  recoveryFoundHash = found;
                  console.log('Auto-recovered recent Base burn transaction:', found);
                }
              } catch (_e) { }
            }, 3500);
          }

          try {
            const sendPromise = evmProvider.request({
              method: 'eth_sendTransaction',
              params: [{
                from: userEvm,
                to: contractAddr,
                data: encodedData,
                value: '0x0'
              }]
            });

            // Race the RPC response against on-chain detection
            const recoveryWatcher = new Promise((resolve) => {
              const checkTimer = setInterval(() => {
                if (recoveryFoundHash) {
                  clearInterval(checkTimer);
                  resolve(recoveryFoundHash);
                }
                if (!isExecutingBridge) {
                  clearInterval(checkTimer);
                }
              }, 1000);
            });

            evmTxHash = await Promise.race([sendPromise, recoveryWatcher]);
          } finally {
            if (fallbackRecoveryInterval) clearInterval(fallbackRecoveryInterval);
            hideMetaMaskActionBanner();
          }

          if (!evmTxHash || typeof evmTxHash !== 'string') {
            throw new Error('Could not obtain EVM transaction hash.');
          }'''

    assert burn_target in content, 'burn_target not found'
    content = content.replace(burn_target, burn_replacement, 1)

    # 8. Ensure hideMetaMaskActionBanner is called in error/finally blocks
    content = content.replace(
        "showToast('Transaction signature was cancelled by user.', 'info', true);",
        "hideMetaMaskActionBanner(); showToast('Transaction signature was cancelled by user.', 'info', true);"
    )

    # Write patched files
    with open('frontend/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(content)

    print('SUCCESS: frontend/index.html and templates/index.html patched with flawless Web3 wallet flow!')

if __name__ == '__main__':
    apply_patches()
