with open('frontend/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = None
end_idx = None

for i, line in enumerate(lines):
    if 'function formatSpaceBodyHtml(rawText) {' in line:
        start_idx = i
    if start_idx is not None and i > start_idx and line.strip() == '}' and 'function generateSpacePostEmbedHtml' in lines[i+2]:
        end_idx = i + 1
        break

print(f"formatSpaceBodyHtml found from line {start_idx+1} to {end_idx}")

new_code = '''    function formatSpaceBodyHtml(rawText) {
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
    }
'''

new_lines = lines[:start_idx] + [new_code] + lines[end_idx:]
with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("formatSpaceBodyHtml replaced successfully!")

