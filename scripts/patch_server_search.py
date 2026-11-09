with open('server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Check explorer search in server.py
old_search = """    if is_valid_bct_address(q):
        bal = blockchain.get_balance(q)
        history = blockchain.get_wallet_transactions(q)
        return api_response(True, data={
            "type": "address",
            "result": {
                "address": q,
                "balance": bal,
                "transaction_count": len(history),
                "transactions": history[:50],
            },
        })"""

new_search = """    # BNS handle resolution in explorer search (e.g. @satoshi, satoshi.bct)
    clean_handle = q.lstrip("@").lower()
    bns_cand = clean_handle if clean_handle.endswith(".bct") else f"{clean_handle}.bct"
    if bns_cand in blockchain.bns_records:
        resolved_addr = blockchain.bns_records[bns_cand].get("owner", "")
        if resolved_addr and is_valid_bct_address(resolved_addr):
            bal = blockchain.get_balance(resolved_addr)
            history = blockchain.get_wallet_transactions(resolved_addr)
            return api_response(True, data={
                "type": "address",
                "result": {
                    "address": resolved_addr,
                    "handle": bns_cand,
                    "balance": bal,
                    "transaction_count": len(history),
                    "transactions": history,
                },
            })

    if is_valid_bct_address(q):
        bal = blockchain.get_balance(q)
        history = blockchain.get_wallet_transactions(q)
        return api_response(True, data={
            "type": "address",
            "result": {
                "address": q,
                "balance": bal,
                "transaction_count": len(history),
                "transactions": history,
            },
        })"""

if old_search in content:
    content = content.replace(old_search, new_search, 1)
    with open('server.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully patched server.py api_explorer_search!")
else:
    print("old_search not found in server.py!")

