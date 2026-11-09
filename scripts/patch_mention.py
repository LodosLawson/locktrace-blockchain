# -*- coding: utf-8 -*-
with open('frontend/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_mention = """      // 2. Mentions: @handle.bct or @username or @BCT...
      safe = safe.replace(/@([a-zA-Z0-9_\\-\\.]+)/g, (match, handle) => {
        return `<span class=\"mention-tag inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded-md bg-primary/10 text-primary font-medium hover:bg-primary/20 hover:underline cursor-pointer transition-colors\" onclick=\"event.stopPropagation(); filterSpaceByEntity('@${handle}')\" title=\"Filter posts mentioning @${handle}\">@${handle}</span>`;
      });"""

new_mention = """      // 2. Mentions & Replies: Clickable to view author profile directly
      safe = safe.replace(/@([a-zA-Z0-9_\\-\\.]+)/g, (match, handle) => {
        return `<span class=\"mention-tag inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded-md bg-primary/10 text-primary font-medium hover:bg-primary/20 hover:underline cursor-pointer transition-colors\" onclick=\"event.stopPropagation(); openUserProfile('${handle}')\" title=\"Profilini Gör: @${handle}\">@${handle}</span>`;
      });"""

if old_mention in text:
    text = text.replace(old_mention, new_mention, 1)
    print('Mentions updated to link directly to openUserProfile!')
    with open('frontend/index.html', 'w', encoding='utf-8') as f:
        f.write(text)
else:
    print('Mention target not found.')

