# -*- coding: utf-8 -*-
"""
Patch all 9 visual/layout bugs identified in Notion Hatalar page:
1. Space header: Add dedicated refresh (sync) + settings (tune) buttons
2. Home hero badge: responsive font size & max-w-full to prevent mobile overflow
3. Accounts rich list: table min-w-[680px], whitespace-nowrap on badges to prevent vertical word wrapping
4. EVM Bridge: responsive tab buttons & compact padding for mobile
5. Space FAB button: reposition above mobile bottom nav, open quick compose modal widget
6. Top Header: Add 1-click QR code button in both Web/Desktop and Mobile headers
7. Space Post Details: responsive 4-column action bar, optimized comment input, reply to comment
8. Live BTC prices, multi-cashtag horizontal scroll carousel (from left to right), clickable commenter profiles
9. User profile modal: fix mobile clipping, overflow, and avatar/actions layout
"""

import sys

with open('frontend/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# ----------------------------------------------------------------------
# 1. ISSUE 2: Home Page Hero Badge Overflow
# ----------------------------------------------------------------------
old_badge = '''              <div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-container border border-outline-variant/30 self-start">
                <span class="w-2 h-2 rounded-full bg-primary animate-pulse shrink-0"></span>
                <span class="text-[10px] sm:text-xs text-on-surface uppercase tracking-wider font-semibold font-mono truncate">Web3 On-Chain Social Protocol • 100% Non-Custodial</span>
              </div>'''

new_badge = '''              <div class="inline-flex items-center gap-1.5 px-2.5 sm:px-3 py-1 rounded-full bg-surface-container border border-outline-variant/30 max-w-full self-start overflow-hidden shadow-xs">
                <span class="w-2 h-2 rounded-full bg-primary animate-pulse shrink-0"></span>
                <span class="text-[9px] sm:text-xs text-on-surface uppercase tracking-wider font-semibold font-mono truncate leading-tight">Web3 On-Chain Social Protocol • 100% Non-Custodial</span>
              </div>'''

if old_badge in content:
    content = content.replace(old_badge, new_badge, 1)
    print('[+] Issue 2 fixed: Hero badge overflow')
else:
    print('[-] Issue 2 target not found')

# ----------------------------------------------------------------------
# 2. ISSUE 1: Space Header Buttons (Refresh sync + Settings tune)
# ----------------------------------------------------------------------
old_space_buttons = '''            <div class="flex items-center gap-space-xs">
              <button aria-label="Search Feed" class="w-9 h-9 rounded-full bg-surface-container-low flex items-center justify-center text-on-surface-variant hover:text-on-surface active:scale-95 transition-all border border-outline-variant/20" onclick="toggleSpaceSearchBar()" type="button">
                <span class="material-symbols-outlined text-[19px]">search</span>
              </button>
              <button aria-label="Refresh Feed" class="w-9 h-9 rounded-full bg-surface-container-low flex items-center justify-center text-on-surface-variant hover:text-on-surface active:scale-95 transition-all border border-outline-variant/20" onclick="loadSpaceFeed(); showToast('Space feed refreshed');" title="Refresh Feed" type="button">
                <span class="material-symbols-outlined text-[19px]">tune</span>
              </button>
            </div>'''

new_space_buttons = '''            <div class="flex items-center gap-1.5 sm:gap-2">
              <button aria-label="Search Feed" class="w-8 h-8 sm:w-9 sm:h-9 rounded-full bg-surface-container-low flex items-center justify-center text-on-surface-variant hover:text-on-surface active:scale-95 transition-all border border-outline-variant/20 cursor-pointer" onclick="toggleSpaceSearchBar()" title="Search Feed" type="button">
                <span class="material-symbols-outlined text-[18px]">search</span>
              </button>
              <button id="btnSpaceFeedRefresh" aria-label="Refresh Feed" class="w-8 h-8 sm:w-9 sm:h-9 rounded-full bg-surface-container-low flex items-center justify-center text-on-surface-variant hover:text-primary active:scale-95 transition-all border border-outline-variant/20 cursor-pointer" onclick="triggerSpaceFeedRefresh(this)" title="Yenile / Refresh Feed" type="button">
                <span class="material-symbols-outlined text-[18px] transition-transform duration-500" id="spaceRefreshSpinIcon">sync</span>
              </button>
              <button aria-label="Feed Preferences" class="w-8 h-8 sm:w-9 sm:h-9 rounded-full bg-surface-container-low flex items-center justify-center text-on-surface-variant hover:text-on-surface active:scale-95 transition-all border border-outline-variant/20 cursor-pointer" onclick="openSpaceSettingsModal()" title="Ayarlar / Feed Filter Settings" type="button">
                <span class="material-symbols-outlined text-[18px]">tune</span>
              </button>
            </div>'''

if old_space_buttons in content:
    content = content.replace(old_space_buttons, new_space_buttons, 1)
    print('[+] Issue 1 fixed: Space header buttons (refresh + settings)')
else:
    print('[-] Issue 1 target not found')

# ----------------------------------------------------------------------
# 3. ISSUE 6: Add Quick QR Code Button to Desktop and Mobile Top Headers
# ----------------------------------------------------------------------
# 3A: Desktop Header
old_desktop_qr = '''      <button class="flex items-center gap-space-xs bg-surface-container px-3.5 py-1.5 rounded-full text-on-surface hover:bg-surface-container-high transition-colors active:scale-95 border border-outline-variant/20" onclick="handleHeaderAddressAction()" type="button" title="Adresi Kopyala">
        <span class="font-label-md text-label-md text-on-surface font-mono" id="headerAddress">No Wallet Selected</span>
        <span class="material-symbols-outlined text-[16px] text-on-surface-variant">content_copy</span>
      </button>
      <button aria-label="Wallet Details &amp; QR" class="w-8 h-8 rounded-full bg-primary flex items-center justify-center shrink-0 cursor-pointer hover:opacity-90 transition-opacity shadow-sm" onclick="openReceiveModal()" type="button">
        <span class="material-symbols-outlined text-on-primary text-[18px]" id="desktopVaultAvatarIcon">person</span>
      </button>'''

new_desktop_qr = '''      <button class="flex items-center gap-space-xs bg-surface-container px-3.5 py-1.5 rounded-full text-on-surface hover:bg-surface-container-high transition-colors active:scale-95 border border-outline-variant/20 cursor-pointer" onclick="handleHeaderAddressAction()" type="button" title="Adresi Kopyala">
        <span class="font-label-md text-label-md text-on-surface font-mono" id="headerAddress">No Wallet Selected</span>
        <span class="material-symbols-outlined text-[16px] text-on-surface-variant">content_copy</span>
      </button>
      <!-- Quick QR Code Display Button (Web / Desktop) -->
      <button aria-label="Hızlı QR Kod Göster" class="w-8 h-8 rounded-full bg-surface-container hover:bg-surface-container-high border border-outline-variant/30 flex items-center justify-center shrink-0 cursor-pointer text-primary transition-all active:scale-95 shadow-sm" onclick="openReceiveModal()" title="Hızlı Cüzdan QR Kodu" type="button">
        <span class="material-symbols-outlined text-[18px]">qr_code_2</span>
      </button>
      <button aria-label="Wallet Details &amp; QR" class="w-8 h-8 rounded-full bg-primary flex items-center justify-center shrink-0 cursor-pointer hover:opacity-90 transition-opacity shadow-sm" onclick="openReceiveModal()" type="button">
        <span class="material-symbols-outlined text-on-primary text-[18px]" id="desktopVaultAvatarIcon">person</span>
      </button>'''

if old_desktop_qr in content:
    content = content.replace(old_desktop_qr, new_desktop_qr, 1)
    print('[+] Issue 6 fixed: Desktop top header QR code button')
else:
    print('[-] Issue 6 Desktop target not found')

# 3B: Mobile Header
old_mobile_hdr = '''        <!-- Account / Wallet Badge -->
        <button class="flex items-center gap-1 bg-surface-container hover:bg-surface-container-high px-2 py-0.5 rounded-full text-on-surface transition-colors active:scale-95 border border-outline-variant/20 shrink-0 max-w-[95px] xs:max-w-[120px] sm:max-w-[145px]" onclick="handleHeaderAddressAction()" type="button" title="Wallet Account">
          <span class="material-symbols-outlined text-[13px] text-primary shrink-0">account_balance_wallet</span>
          <span class="text-[10px] sm:text-[11px] font-mono font-medium text-on-surface truncate" id="mobileHeaderAddress">Open Wallet</span>
        </button>

        <!-- Menu Drawer Toggle -->'''

new_mobile_hdr = '''        <!-- Account / Wallet Badge -->
        <button class="flex items-center gap-1 bg-surface-container hover:bg-surface-container-high px-2 py-0.5 rounded-full text-on-surface transition-colors active:scale-95 border border-outline-variant/20 shrink-0 max-w-[95px] xs:max-w-[120px] sm:max-w-[145px]" onclick="handleHeaderAddressAction()" type="button" title="Wallet Account">
          <span class="material-symbols-outlined text-[13px] text-primary shrink-0">account_balance_wallet</span>
          <span class="text-[10px] sm:text-[11px] font-mono font-medium text-on-surface truncate" id="mobileHeaderAddress">Open Wallet</span>
        </button>

        <!-- Quick Receive QR Code Button (Mobile) -->
        <button aria-label="Hızlı QR Kod" class="w-7 h-7 rounded-full bg-surface-container hover:bg-surface-container-high flex items-center justify-center shrink-0 cursor-pointer text-primary active:scale-95 transition-all border border-outline-variant/20" onclick="openReceiveModal()" title="Cüzdan QR Kodu" type="button">
          <span class="material-symbols-outlined text-[16px]">qr_code_2</span>
        </button>

        <!-- Menu Drawer Toggle -->'''

if old_mobile_hdr in content:
    content = content.replace(old_mobile_hdr, new_mobile_hdr, 1)
    print('[+] Issue 6 fixed: Mobile top header QR code button')
else:
    print('[-] Issue 6 Mobile target not found')

# ----------------------------------------------------------------------
# 4. ISSUE 3: Accounts Rich List Table Overflow on Mobile
# ----------------------------------------------------------------------
old_table_wrap = '''            <!-- Holders Table / Card Container -->
            <div class="bg-surface-container-low rounded-2xl border border-outline-variant/15 overflow-hidden">
              <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr class="border-b border-outline-variant/10 bg-surface-container/60 text-on-surface-variant font-medium">
                      <th class="py-3 px-3.5 font-mono text-[11px] w-12 text-center"># Rank</th>
                      <th class="py-3 px-3.5">Wallet / Account Address</th>
                      <th class="py-3 px-3.5">Account Role</th>
                      <th class="py-3 px-3.5 text-center">Tx Count</th>
                      <th class="py-3 px-3.5 text-right">Balance (BCT)</th>
                      <th class="py-3 px-3.5 text-right">Supply Share</th>
                    </tr>
                  </thead>'''

new_table_wrap = '''            <!-- Holders Table / Card Container -->
            <div class="bg-surface-container-low rounded-2xl border border-outline-variant/15 overflow-hidden">
              <div class="overflow-x-auto w-full no-scrollbar">
                <table class="w-full min-w-[680px] text-left border-collapse text-xs">
                  <thead>
                    <tr class="border-b border-outline-variant/10 bg-surface-container/60 text-on-surface-variant font-medium whitespace-nowrap">
                      <th class="py-3 px-3.5 font-mono text-[11px] w-14 text-center"># Rank</th>
                      <th class="py-3 px-3.5">Wallet / Account Address</th>
                      <th class="py-3 px-3.5">Account Role</th>
                      <th class="py-3 px-3.5 text-center">Tx Count</th>
                      <th class="py-3 px-3.5 text-right">Balance (BCT)</th>
                      <th class="py-3 px-3.5 text-right">Supply Share</th>
                    </tr>
                  </thead>'''

if old_table_wrap in content:
    content = content.replace(old_table_wrap, new_table_wrap, 1)
    print('[+] Issue 3 fixed: Table container min-w-[680px]')
else:
    print('[-] Issue 3 table target not found')

# Also in renderExplorerHolders:
old_render_holders = '''        let tagBadge = '<span class="bg-surface-container px-2 py-0.5 rounded text-[11px] text-on-surface-variant font-sans">User Wallet</span>';
        if (h.tag_type === 'treasury') {
          tagBadge = '<span class="bg-primary/10 text-primary border border-primary/20 px-2 py-0.5 rounded text-[11px] font-semibold font-sans">Genesis Treasury (Escrowed)</span>';
        } else if (h.tag_type === 'bridge_vault') {
          tagBadge = '<span class="bg-secondary/10 text-secondary border border-secondary/20 px-2 py-0.5 rounded text-[11px] font-semibold font-sans">Bridge Vault (Base 1:1)</span>';
        } else if (h.tag_type === 'validator') {
          tagBadge = '<span class="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded text-[11px] font-medium font-sans">Validator Node</span>';
        } else if (h.tag_type === 'lost_key_burn') {
          tagBadge = '<span class="bg-rose-500/15 text-rose-300 border border-rose-500/30 px-2 py-0.5 rounded text-[11px] font-semibold font-sans inline-flex items-center gap-1 cursor-help" title="Geliştirici doğruladı: Private key kayıp özel test adresidir (Dolaşım dışı / Kilitli)"><span class="material-symbols-outlined text-[13px] text-rose-400">local_fire_department</span>Kayıp Key (Fiili Yakım)</span>';
        }'''

new_render_holders = '''        let tagBadge = '<span class="bg-surface-container px-2 py-0.5 rounded text-[11px] text-on-surface-variant font-sans whitespace-nowrap">User Wallet</span>';
        if (h.tag_type === 'treasury') {
          tagBadge = '<span class="bg-primary/10 text-primary border border-primary/20 px-2 py-0.5 rounded text-[11px] font-semibold font-sans whitespace-nowrap">Genesis Treasury (Escrowed)</span>';
        } else if (h.tag_type === 'bridge_vault') {
          tagBadge = '<span class="bg-secondary/10 text-secondary border border-secondary/20 px-2 py-0.5 rounded text-[11px] font-semibold font-sans whitespace-nowrap">Bridge Vault (Base 1:1)</span>';
        } else if (h.tag_type === 'validator') {
          tagBadge = '<span class="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded text-[11px] font-medium font-sans whitespace-nowrap">Validator Node</span>';
        } else if (h.tag_type === 'lost_key_burn') {
          tagBadge = '<span class="bg-rose-500/15 text-rose-300 border border-rose-500/30 px-2 py-0.5 rounded text-[11px] font-semibold font-sans whitespace-nowrap inline-flex items-center gap-1 cursor-help" title="Geliştirici doğruladı: Private key kayıp özel test adresidir (Dolaşım dışı / Kilitli)"><span class="material-symbols-outlined text-[13px] text-rose-400">local_fire_department</span>Kayıp Key (Fiili Yakım)</span>';
        }'''

if old_render_holders in content:
    content = content.replace(old_render_holders, new_render_holders, 1)
    print('[+] Issue 3 fixed: Badges whitespace-nowrap in JS')
else:
    print('[-] Issue 3 JS target not found')

# ----------------------------------------------------------------------
# 5. ISSUE 4: EVM Bridge Tab Buttons & Layout
# ----------------------------------------------------------------------
old_bridge_card = '''          <!-- Bridge Card Container -->
          <div class="flex flex-col bg-surface-container rounded-3xl p-5 sm:p-6 border border-outline-variant/20 shadow-lg gap-5">
            
            <!-- Direction Toggle Selector -->
            <div class="flex items-center p-1 rounded-2xl bg-surface-container-low border border-outline-variant/15">
              <button id="bridgeDirL1ToEvm" class="flex-1 py-2 sm:py-2.5 px-1.5 sm:px-3 rounded-xl text-xs sm:text-sm font-semibold transition-all flex items-center justify-center gap-1 sm:gap-1.5 bg-primary text-on-primary shadow-sm" onclick="setBridgeDirection('L1_TO_EVM')" type="button">
                <span class="material-symbols-outlined text-[16px] sm:text-[18px] shrink-0">lock</span>
                <span class="truncate">Lock L1 &rarr; Mint wBCT</span>
              </button>
              <button id="bridgeDirEvmToL1" class="flex-1 py-2 sm:py-2.5 px-1.5 sm:px-3 rounded-xl text-xs sm:text-sm font-semibold transition-all flex items-center justify-center gap-1 sm:gap-1.5 text-on-surface-variant hover:text-on-surface" onclick="setBridgeDirection('EVM_TO_L1')" type="button">
                <span class="material-symbols-outlined text-[16px] sm:text-[18px] shrink-0">local_fire_department</span>
                <span class="truncate">Burn wBCT &rarr; Unlock L1</span>
              </button>
            </div>'''

new_bridge_card = '''          <!-- Bridge Card Container -->
          <div class="flex flex-col bg-surface-container rounded-3xl p-3.5 sm:p-6 border border-outline-variant/20 shadow-lg gap-4 sm:gap-5">
            
            <!-- Direction Toggle Selector -->
            <div class="flex items-center p-1 rounded-2xl bg-surface-container-low border border-outline-variant/15 w-full">
              <button id="bridgeDirL1ToEvm" class="flex-1 min-w-0 py-2 sm:py-2.5 px-1.5 sm:px-3 rounded-xl text-xs sm:text-sm font-semibold transition-all flex items-center justify-center gap-1 sm:gap-1.5 bg-primary text-on-primary shadow-sm" onclick="setBridgeDirection('L1_TO_EVM')" type="button">
                <span class="material-symbols-outlined text-[15px] sm:text-[18px] shrink-0">lock</span>
                <span class="truncate"><span class="sm:hidden">Lock L1 &rarr; wBCT</span><span class="hidden sm:inline">Lock L1 &rarr; Mint wBCT</span></span>
              </button>
              <button id="bridgeDirEvmToL1" class="flex-1 min-w-0 py-2 sm:py-2.5 px-1.5 sm:px-3 rounded-xl text-xs sm:text-sm font-semibold transition-all flex items-center justify-center gap-1 sm:gap-1.5 text-on-surface-variant hover:text-on-surface" onclick="setBridgeDirection('EVM_TO_L1')" type="button">
                <span class="material-symbols-outlined text-[15px] sm:text-[18px] shrink-0">local_fire_department</span>
                <span class="truncate"><span class="sm:hidden">Burn wBCT &rarr; L1</span><span class="hidden sm:inline">Burn wBCT &rarr; Unlock L1</span></span>
              </button>
            </div>'''

if old_bridge_card in content:
    content = content.replace(old_bridge_card, new_bridge_card, 1)
    print('[+] Issue 4 fixed: EVM Bridge card padding and tab buttons')
else:
    print('[-] Issue 4 target not found')

# ----------------------------------------------------------------------
# 6. ISSUE 5: Space FAB Position & Quick Compose Popup Widget
# ----------------------------------------------------------------------
old_fab = '''          <!-- Floating Action Compose Trigger Button (Exact Stitch FAB) -->
          <aside class="fixed bottom-20 md:bottom-8 right-5 md:right-8 z-40">
            <button aria-label="Compose New Post" class="w-13 h-13 p-3.5 rounded-full bg-primary-container text-on-primary-container shadow-xl flex items-center justify-center active:scale-90 transition-transform focus:outline-none cursor-pointer" id="fab-compose" onclick="focusSpaceComposer()" type="button">
              <span class="material-symbols-outlined text-[24px]">edit</span>
            </button>
          </aside>'''

new_fab = '''          <!-- Floating Action Compose Trigger Button (Exact Stitch FAB - Adjusted to avoid bottom bar) -->
          <aside class="fixed bottom-[74px] sm:bottom-24 md:bottom-8 right-4 sm:right-6 md:right-8 z-40">
            <button aria-label="Quick Compose Cast" class="w-12 h-12 sm:w-13 sm:h-13 p-3 sm:p-3.5 rounded-full bg-primary-container text-on-primary-container shadow-2xl flex items-center justify-center active:scale-90 transition-transform focus:outline-none cursor-pointer ring-2 ring-primary/30" id="fab-compose" onclick="openQuickComposeModal()" title="Yeni Düşünce Yaz (Quick Cast)" type="button">
              <span class="material-symbols-outlined text-[22px] sm:text-[24px]">edit</span>
            </button>
          </aside>'''

if old_fab in content:
    content = content.replace(old_fab, new_fab, 1)
    print('[+] Issue 5 fixed: Space FAB position and onclick')
else:
    print('[-] Issue 5 target not found')

# ----------------------------------------------------------------------
# 7. ISSUE 7: Space Post Details 4-Column Action Grid & Comment Composer
# ----------------------------------------------------------------------
old_detail_actions = '''          <!-- 4-Col Action Buttons Grid (Exact Stitch Screen F) -->
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

new_detail_actions = '''          <!-- 4-Col Action Buttons Grid (Responsive, never overflow) -->
          <div class="grid grid-cols-4 gap-1.5 pt-1">
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

if old_detail_actions in content:
    content = content.replace(old_detail_actions, new_detail_actions, 1)
    print('[+] Issue 7 fixed: Post details action buttons grid')
else:
    print('[-] Issue 7 action grid target not found')

# Also in Comment Composer sticky bar:
old_comment_bar = '''          <!-- Sticky Bottom Comment Composer Bar (Exact Stitch Screen F) -->
          <div class="fixed md:sticky bottom-0 left-0 right-0 z-50 bg-surface/95 backdrop-blur-xl px-2 sm:px-3 py-3 pb-safe border-t border-outline-variant/20 shadow-[0_-4px_24px_rgba(0,0,0,0.4)] md:rounded-2xl md:mt-4">
            <div class="max-w-[600px] mx-auto flex flex-col gap-1.5">
              <div class="flex items-center justify-between text-xs px-2 text-on-surface-variant">
                <span class="flex items-center gap-1 font-mono text-[11px]"><span class="material-symbols-outlined text-[13px] text-primary">chat</span> On-Chain Comment</span>
                <div class="flex items-center gap-1.5">
                  <span class="text-[11px]">As:</span>
                  <select id="detailCommentHandleSelect" class="bg-surface-container-high text-on-surface border border-outline-variant/30 text-[11px] rounded-md px-1.5 py-0.5 focus:outline-none focus:border-primary font-mono cursor-pointer" title="Select comment identity">
                    <option value="address">💳 My Wallet</option>
                  </select>
                </div>
              </div>
              <div class="flex items-center space-x-space-sm">
                <div class="w-9 h-9 rounded-full bg-primary flex items-center justify-center shrink-0">
                  <span class="material-symbols-outlined text-on-primary text-[18px]">person</span>
                </div>
                <div class="relative flex-1 flex items-center">
                  <input class="w-full h-11 bg-surface-container-high rounded-full pl-4 pr-10 text-on-surface font-body-sm text-body-sm placeholder:text-on-surface-variant focus:outline-none focus:bg-surface-container-highest transition-colors" id="detailCommentInput" maxlength="140" onkeydown="if(event.key==='Enter'){ event.preventDefault(); submitDetailSpaceComment(); }" placeholder="Write a comment (0.02 BCT)..." type="text"/>
                  <button aria-label="Add emoji tag" class="absolute right-3 text-on-surface-variant hover:text-primary flex items-center justify-center" onclick="appendEmojiToDetailComment()" type="button">
                    <span class="material-symbols-outlined text-[20px]">sentiment_satisfied</span>
                  </button>
                </div>
                <button class="h-11 px-5 rounded-full bg-primary text-on-primary font-label-lg text-label-lg font-semibold flex items-center justify-center space-x-1 hover:brightness-95 active:scale-95 transition-all shrink-0" id="detailSubmitCommentBtn" onclick="submitDetailSpaceComment()" type="button">
                  <span>Send</span>
                </button>
              </div>
            </div>
          </div>'''

new_comment_bar = '''          <!-- Sticky Bottom Comment Composer Bar (Exact Stitch Screen F - Compact & Reply Banner) -->
          <div class="fixed md:sticky bottom-0 left-0 right-0 z-50 bg-surface/95 backdrop-blur-xl px-2 sm:px-3 py-2.5 pb-safe border-t border-outline-variant/20 shadow-[0_-4px_24px_rgba(0,0,0,0.4)] md:rounded-2xl md:mt-4">
            <div class="max-w-[600px] mx-auto flex flex-col gap-1.5">
              <!-- Active Reply Target Banner -->
              <div id="detailCommentReplyBanner" class="hidden items-center justify-between px-2.5 py-1 rounded-lg bg-primary/10 border border-primary/20 text-xs text-primary font-mono">
                <div class="flex items-center gap-1.5 truncate">
                  <span class="material-symbols-outlined text-[14px]">reply</span>
                  <span id="detailCommentReplyTarget">Replying to @...</span>
                </div>
                <button type="button" onclick="cancelCommentReply()" class="text-on-surface-variant hover:text-on-surface p-0.5" title="Cancel Reply">
                  <span class="material-symbols-outlined text-[15px]">close</span>
                </button>
              </div>
              <div class="flex items-center justify-between text-xs px-2 text-on-surface-variant">
                <span class="flex items-center gap-1 font-mono text-[11px]"><span class="material-symbols-outlined text-[13px] text-primary">chat</span> On-Chain Comment (0.02 BCT)</span>
                <div class="flex items-center gap-1.5">
                  <span class="text-[11px]">As:</span>
                  <select id="detailCommentHandleSelect" class="bg-surface-container-high text-on-surface border border-outline-variant/30 text-[11px] rounded-md px-1.5 py-0.5 focus:outline-none focus:border-primary font-mono cursor-pointer" title="Select comment identity">
                    <option value="address">💳 My Wallet</option>
                  </select>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <div class="w-8 h-8 rounded-full bg-primary flex items-center justify-center shrink-0">
                  <span class="material-symbols-outlined text-on-primary text-[16px]">person</span>
                </div>
                <div class="relative flex-1 min-w-0 flex items-center">
                  <input class="w-full h-10 bg-surface-container-high rounded-full pl-3.5 pr-8 text-on-surface font-body-sm text-xs sm:text-sm placeholder:text-on-surface-variant focus:outline-none focus:bg-surface-container-highest transition-colors" id="detailCommentInput" maxlength="140" onkeydown="if(event.key==='Enter'){ event.preventDefault(); submitDetailSpaceComment(); }" placeholder="Write a comment..." type="text"/>
                  <button aria-label="Add emoji tag" class="absolute right-2.5 text-on-surface-variant hover:text-primary flex items-center justify-center" onclick="appendEmojiToDetailComment()" type="button">
                    <span class="material-symbols-outlined text-[18px]">sentiment_satisfied</span>
                  </button>
                </div>
                <button class="h-10 px-4 rounded-full bg-primary text-on-primary font-label-md text-xs sm:text-sm font-semibold flex items-center justify-center space-x-1 hover:brightness-95 active:scale-95 transition-all shrink-0" id="detailSubmitCommentBtn" onclick="submitDetailSpaceComment()" type="button">
                  <span>Send</span>
                </button>
              </div>
            </div>
          </div>'''

if old_comment_bar in content:
    content = content.replace(old_comment_bar, new_comment_bar, 1)
    print('[+] Issue 7 fixed: Comment composer bar')
else:
    print('[-] Issue 7 comment bar target not found')

# Also add reply button inside comment render in JS:
old_cmt_render = '''                <button class="px-2.5 py-1 rounded-full bg-surface-container text-primary font-label-sm text-label-sm" onclick="tipAuthorPrompt('${escapeHtml(c.commenter)}', event)" type="button">Tip</button>
              </div>
              <p class="font-body-md text-body-md text-on-surface pl-10 break-words">
                ${formatSpaceBodyHtml(c.content)}
              </p>'''

new_cmt_render = '''                <div class="flex items-center gap-1.5 shrink-0">
                  <button class="px-2 py-0.5 rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface font-label-sm text-[11px] flex items-center gap-0.5 transition cursor-pointer" onclick="replyToComment('${escapeHtml(c.commenter_bns || shortAddr(c.commenter))}', '${escapeHtml(c.commenter)}')" type="button" title="Reply to comment">
                    <span class="material-symbols-outlined text-[13px]">reply</span>
                    <span>Reply</span>
                  </button>
                  <button class="px-2 py-0.5 rounded-full bg-primary/15 text-primary hover:bg-primary/25 font-label-sm text-[11px] font-semibold flex items-center gap-0.5 transition cursor-pointer" onclick="tipAuthorPrompt('${escapeHtml(c.commenter)}', event)" type="button" title="Tip BCT">
                    <span class="material-symbols-outlined text-[12px]">bolt</span>
                    <span>Tip</span>
                  </button>
                </div>
              </div>
              <p class="font-body-md text-body-md text-on-surface pl-9 break-words">
                ${formatSpaceBodyHtml(c.content)}
              </p>'''

if old_cmt_render in content:
    content = content.replace(old_cmt_render, new_cmt_render, 1)
    print('[+] Issue 7 & 8 fixed: Comment Reply button added to comments')
else:
    print('[-] Issue 7/8 comment reply render target not found')

# ----------------------------------------------------------------------
# 8. ISSUE 9: User Profile Modal Clipping and Shift Fix
# ----------------------------------------------------------------------
old_profile_modal = '''  <div class="fixed inset-0 z-50 bg-background/85 backdrop-blur-md hidden items-center justify-center p-3 sm:p-4" id="userProfileModal" onclick="if(event.target===this) closeUserProfile();">
    <div class="w-full max-w-2xl max-h-[92dvh] overflow-y-auto rounded-3xl bg-surface-container flex flex-col shadow-2xl border border-outline-variant/30 transition-all scale-95 opacity-0" id="userProfileModalCard">
      <!-- Header Banner with Gradient -->
      <div class="h-28 sm:h-32 bg-gradient-to-r from-primary/25 via-surface-container-high to-secondary/25 relative rounded-t-3xl p-4 sm:p-5 flex justify-end items-center gap-2">
        <span class="px-2.5 py-1 rounded-full bg-surface-container/90 backdrop-blur-md text-[11px] font-mono text-on-surface flex items-center gap-1.5 border border-outline-variant/20 shadow-sm">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>LockTrace Identity</span>
        </span>
        <button class="w-8 h-8 rounded-full bg-surface-container/90 backdrop-blur-md hover:bg-surface-variant text-on-surface flex items-center justify-center transition-colors shadow-sm cursor-pointer" onclick="closeUserProfile()" type="button" title="Close Profile">
          <span class="material-symbols-outlined text-[18px]">close</span>
        </button>
      </div>

      <!-- Profile Avatar & Identity Section -->
      <div class="px-5 sm:px-6 pb-6 pt-0 flex flex-col gap-4">
        <!-- Top Row: Avatar Protruding Out + Quick Action Buttons -->
        <div class="flex items-end justify-between gap-3 -mt-12 sm:-mt-14">
          <!-- Avatar protruding half into the banner -->
          <div class="w-20 h-20 sm:w-24 sm:h-24 rounded-2xl bg-surface-container-highest border-4 border-surface-container flex items-center justify-center shadow-2xl text-primary shrink-0 relative overflow-hidden z-10" id="userProfileAvatarBox">
            <span class="material-symbols-outlined text-[44px] sm:text-[48px]" id="userProfileAvatarIcon">person</span>
          </div>

          <!-- Quick Action Buttons -->
          <div class="flex items-center gap-1.5 sm:gap-2 pb-1 shrink-0 flex-wrap justify-end">
            <button id="btnProfileFollow" class="px-3 sm:px-4 py-1.5 sm:py-2 rounded-full bg-primary/20 text-primary hover:bg-primary hover:text-on-primary border border-primary/40 font-semibold text-[11px] sm:text-xs flex items-center justify-center gap-1 transition-all active:scale-95 shadow-sm cursor-pointer" onclick="profileFollowClicked()" type="button">
              <span class="material-symbols-outlined text-[15px]">person_add</span>
              <span id="btnProfileFollowText">Follow (1.00 BCT)</span>
            </button>
            <button class="px-2.5 sm:px-4 py-1.5 sm:py-2 rounded-full bg-primary text-on-primary font-semibold text-[11px] sm:text-xs flex items-center justify-center gap-1 sm:gap-1.5 active:scale-95 transition-all shadow-sm cursor-pointer" onclick="profileSendCrypto()" type="button">
              <span class="material-symbols-outlined text-[14px] sm:text-[15px]">send</span>
              <span>Send BCT</span>
            </button>
            <button class="px-2 sm:px-3.5 py-1.5 sm:py-2 rounded-full bg-primary/15 text-primary hover:bg-primary/25 font-semibold text-[11px] sm:text-xs flex items-center justify-center gap-1 sm:gap-1.5 active:scale-95 transition-all cursor-pointer" onclick="profileTipDirect()" type="button">
              <span class="material-symbols-outlined text-[14px] sm:text-[15px]">bolt</span>
              <span>Tip</span>
            </button>
            <button class="w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-surface-container-high hover:bg-surface-variant text-on-surface font-semibold text-xs flex items-center justify-center transition-all cursor-pointer" onclick="profileInspectExplorer()" type="button" title="Search in Explorer">
              <span class="material-symbols-outlined text-[15px] sm:text-[16px]">search</span>
            </button>
          </div>
        </div>'''

new_profile_modal = '''  <div class="fixed inset-0 z-50 bg-background/85 backdrop-blur-md hidden items-center justify-center p-2 sm:p-4 overflow-y-auto overflow-x-hidden" id="userProfileModal" onclick="if(event.target===this) closeUserProfile();">
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
      </div>

      <!-- Profile Avatar & Identity Section -->
      <div class="px-3.5 sm:px-6 pb-6 pt-0 flex flex-col gap-3.5">
        <!-- Top Row: Avatar Protruding Out + Responsive Quick Actions -->
        <div class="flex flex-wrap items-end justify-between gap-2.5 -mt-10 sm:-mt-12">
          <!-- Avatar protruding half into the banner -->
          <div class="w-16 h-16 sm:w-20 sm:h-20 rounded-2xl bg-surface-container-highest border-4 border-surface-container flex items-center justify-center shadow-xl text-primary shrink-0 relative overflow-hidden z-10" id="userProfileAvatarBox">
            <span class="material-symbols-outlined text-[36px] sm:text-[42px]" id="userProfileAvatarIcon">person</span>
          </div>

          <!-- Quick Action Buttons (Wrap safely, no overflow) -->
          <div class="flex items-center gap-1.5 pb-1 flex-wrap justify-end flex-1 min-w-0">
            <button id="btnProfileFollow" class="px-2.5 sm:px-3.5 py-1.5 rounded-full bg-primary/20 text-primary hover:bg-primary hover:text-on-primary border border-primary/40 font-semibold text-[11px] sm:text-xs flex items-center justify-center gap-1 transition-all active:scale-95 shadow-sm cursor-pointer" onclick="profileFollowClicked()" type="button">
              <span class="material-symbols-outlined text-[14px]">person_add</span>
              <span id="btnProfileFollowText">Follow (1.00 BCT)</span>
            </button>
            <button class="px-2.5 sm:px-3 py-1.5 rounded-full bg-primary text-on-primary font-semibold text-[11px] sm:text-xs flex items-center justify-center gap-1 active:scale-95 transition-all shadow-sm cursor-pointer" onclick="profileSendCrypto()" type="button">
              <span class="material-symbols-outlined text-[13px]">send</span>
              <span>Send BCT</span>
            </button>
            <button class="px-2 py-1.5 rounded-full bg-primary/15 text-primary hover:bg-primary/25 font-semibold text-[11px] sm:text-xs flex items-center justify-center gap-1 active:scale-95 transition-all cursor-pointer" onclick="profileTipDirect()" type="button">
              <span class="material-symbols-outlined text-[13px]">bolt</span>
              <span>Tip</span>
            </button>
            <button class="w-7 h-7 rounded-full bg-surface-container-high hover:bg-surface-variant text-on-surface font-semibold text-xs flex items-center justify-center transition-all cursor-pointer" onclick="profileInspectExplorer()" type="button" title="Search in Explorer">
              <span class="material-symbols-outlined text-[14px]">search</span>
            </button>
          </div>
        </div>'''

if old_profile_modal in content:
    content = content.replace(old_profile_modal, new_profile_modal, 1)
    print('[+] Issue 9 fixed: Profile modal layout, padding & responsive buttons')
else:
    print('[-] Issue 9 target not found')

with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('[*] Frontend/index.html patched part 1.')

