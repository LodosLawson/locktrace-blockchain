import os
import sys
import json
import urllib.request
import urllib.error

NOTION_VERSION = "2022-06-28"

def get_notion_token():
    token = os.environ.get("NOTION_TOKEN")
    if token:
        return token
    cfg_paths = [
        os.path.expanduser("~/.gemini/config/mcp_config.json"),
        os.path.expanduser("~/.gemini/config/plugins/notion/mcp_config.json"),
        r"C:\Users\mehem\.gemini\config\mcp_config.json"
    ]
    for p in cfg_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    auth = data.get("mcpServers", {}).get("notion", {}).get("headers", {}).get("Authorization", "")
                    if auth.startswith("Bearer "):
                        return auth[7:].strip()
            except Exception:
                pass
    return None

def notion_api(endpoint, method="GET", data=None):
    token = get_notion_token()
    if not token:
        print("[!] Error: NOTION_TOKEN not found in environment or mcp_config.json")
        return None
    url = f"https://api.notion.com/v1/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")
        print(f"[!] Notion API HTTP {e.code} Error: {err}")
        return None
    except Exception as e:
        print(f"[!] Notion API Exception: {e}")
        return None

def find_connected_pages():
    res = notion_api("search", method="POST", data={"filter": {"value": "page", "property": "object"}})
    if not res:
        return []
    return res.get("results", [])

def text_block(content):
    return {
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": content[:1950]}}]
        }
    }

def heading_block(level, content):
    h_type = f"heading_{level}"
    return {
        "type": h_type,
        h_type: {
            "rich_text": [{"type": "text", "text": {"content": content[:1950]}}]
        }
    }

def todo_block(content, checked=False):
    return {
        "type": "to_do",
        "to_do": {
            "rich_text": [{"type": "text", "text": {"content": content[:1950]}}],
            "checked": checked
        }
    }

def bullet_block(content):
    return {
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {"content": content[:1950]}}]
        }
    }

def callout_block(content, emoji="🛡️"):
    return {
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": emoji},
            "rich_text": [{"type": "text", "text": {"content": content[:1950]}}]
        }
    }

def divider_block():
    return {"type": "divider", "divider": {}}

def parse_markdown_to_blocks(md_path):
    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    blocks = []
    for line in lines:
        line_str = line.rstrip()
        if not line_str.strip():
            continue
        
        # Check headings
        if line_str.startswith("# "):
            blocks.append(heading_block(1, line_str[2:].strip()))
        elif line_str.startswith("## "):
            blocks.append(heading_block(2, line_str[3:].strip()))
        elif line_str.startswith("### "):
            blocks.append(heading_block(3, line_str[4:].strip()))
        elif line_str.startswith("> "):
            blocks.append(callout_block(line_str[2:].strip(), emoji="💡"))
        elif line_str.startswith("---"):
            blocks.append(divider_block())
        elif line_str.strip().startswith("- [x] "):
            blocks.append(todo_block(line_str.strip()[6:], checked=True))
        elif line_str.strip().startswith("- [ ] "):
            blocks.append(todo_block(line_str.strip()[6:], checked=False))
        elif line_str.strip().startswith("- ") or line_str.strip().startswith("* "):
            blocks.append(bullet_block(line_str.strip()[2:]))
        elif line_str.startswith("|") and line_str.endswith("|"):
            # Table row as mono/formatted text
            blocks.append(text_block(line_str))
        else:
            blocks.append(text_block(line_str))
    
    return blocks

def upload_blocks_in_chunks(parent_id, blocks, chunk_size=90):
    total = len(blocks)
    uploaded = 0
    for i in range(0, total, chunk_size):
        chunk = blocks[i:i + chunk_size]
        res = notion_api(f"blocks/{parent_id}/children", method="PATCH", data={"children": chunk})
        if res:
            uploaded += len(chunk)
            print(f"[*] Uploaded {uploaded}/{total} blocks to Notion...")
        else:
            print(f"[!] Error uploading chunk at index {i}")
            break
    return uploaded

def main():
    print("[*] Checking Notion Workspace connection...")
    user_info = notion_api("users/me")
    if not user_info:
        print("[!] Failed to verify Notion token.")
        return
    
    bot_name = user_info.get("name", "Unknown Bot")
    ws_name = user_info.get("bot", {}).get("workspace_name", "Unknown Workspace")
    print(f"[+] Connected to Notion! Bot: '{bot_name}' | Workspace: '{ws_name}'")
    
    pages = find_connected_pages()
    if not pages:
        print("\n" + "="*70)
        print("[!] HENÜZ PAYLAŞILMIŞ BİR NOTION SAYFASI BULUNAMADI")
        print("="*70)
        print("Notion güvenlik kuralı gereği, botun sayfaya yazabilmesi için:")
        print("1. Notion'da herhangi bir sayfa açın (veya yeni bir sayfa oluşturun).")
        print("2. Sayfanın sağ üstündeki '...' butonuna tıklayın.")
        print(f"3. 'Connections' (Bağlantılar) -> '{bot_name}' botunu ekleyin.")
        print("4. Ardından bu komutu tekrar çalıştırdığınızda tüm doküman otomatik yüklenir!")
        print("="*70 + "\n")
        return
    
    target_page = pages[0]
    page_id = target_page.get("id")
    page_title = "Untitled"
    props = target_page.get("properties", {})
    for p in props.values():
        if p.get("type") == "title":
            t_list = p.get("title", [])
            if t_list:
                page_title = t_list[0].get("plain_text", "Untitled")
    
    print(f"\n[+] Hedef Notion Sayfası Bulundu: '{page_title}' (ID: {page_id})")
    md_file = os.path.join(os.path.dirname(__file__), "..", "docs", "LOCKTRACE_NOTION_WORKSPACE.md")
    if not os.path.exists(md_file):
        print(f"[!] Dosya bulunamadı: {md_file}")
        return
    
    print(f"[*] Doküman okunuyor: {md_file}")
    blocks = parse_markdown_to_blocks(md_file)
    print(f"[*] Toplam {len(blocks)} blok hazırlandı. Notion'a aktarılıyor...")
    
    uploaded = upload_blocks_in_chunks(page_id, blocks)
    print(f"\n✅ BAŞARILI! Toplam {uploaded} içerik bloğu Notion sayfanıza ('{page_title}') aktarıldı!")

if __name__ == "__main__":
    main()

