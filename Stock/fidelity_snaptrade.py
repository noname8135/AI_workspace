"""
Fidelity full holdings via SnapTrade - all accounts
"""
from pprint import pprint
from snaptrade_client import SnapTrade
import json

CLIENT_ID    = "PERS-QVW2R5PLDF11KSBNQT83"
CONSUMER_KEY = "sCBpBZ0nzOhq7veDlzu7rqrDiO8EHBub3Ajqm0R8IO3obQ2zt1"
USER_ID      = "noname8135"
USER_SECRET  = "3bb0fc5d-403c-4311-b603-72e5ca793729"

snaptrade = SnapTrade(client_id=CLIENT_ID, consumer_key=CONSUMER_KEY)

def get_ticker(sym_obj):
    if not isinstance(sym_obj, dict):
        return str(sym_obj)
    inner = sym_obj.get("symbol", {})
    if isinstance(inner, dict):
        return inner.get("symbol", "") or inner.get("ticker", "")
    return str(inner)

# ── 1. All holdings across all accounts ──────────────────────────────
print("=== ALL HOLDINGS (get_user_holdings) ===")
try:
    r = snaptrade.account_information.get_user_holdings(
        user_id=USER_ID,
        user_secret=USER_SECRET,
    )
    all_data = r.body
    # Save raw for inspection
    with open("snaptrade_all_holdings.json", "w") as f:
        json.dump(all_data, f, indent=2, default=str)
    print("Saved raw: snaptrade_all_holdings.json")

    if isinstance(all_data, list):
        for acct_block in all_data:
            acct = acct_block.get("account", {})
            name = acct.get("name", acct.get("number", "?"))
            positions = acct_block.get("positions", [])
            balances  = acct_block.get("balances", [])
            options   = acct_block.get("option_positions", [])

            print(f"\n{'='*60}")
            print(f"  {name}  ({acct.get('institution_name','?')})")
            print(f"{'='*60}")

            # Cash balances
            for b in balances:
                curr = b.get("currency", {}).get("code", "")
                cash = b.get("cash", "")
                buying = b.get("buying_power", "")
                print(f"  Cash: ${cash}  Buying Power: ${buying}  ({curr})")

            # Stock positions
            if positions:
                print(f"\n  {'Ticker':<8} {'Qty':>10} {'Price':>10} {'Avg Cost':>10} {'Mkt Val':>12} {'P&L%':>8}")
                print("  " + "-"*62)
                total_val = 0
                for pos in positions:
                    ticker = get_ticker(pos.get("symbol", {}))
                    qty    = pos.get("units", 0) or 0
                    price  = pos.get("price", 0) or 0
                    avg    = pos.get("average_purchase_price", 0) or 0
                    mktval = float(qty) * float(price)
                    pnl    = (float(price)/float(avg) - 1)*100 if avg and float(avg) > 0 else 0
                    total_val += mktval
                    print(f"  {ticker:<8} {float(qty):>10,.2f} ${float(price):>9.2f} ${float(avg):>9.2f} ${mktval:>11,.0f} {pnl:>+7.1f}%")
                print(f"  {'TOTAL':>42} ${total_val:>11,.0f}")

            # Options
            if options:
                print(f"\n  OPTIONS:")
                for opt in options:
                    sym = opt.get("symbol", {})
                    ticker = get_ticker(sym)
                    exp  = sym.get("expiration_date", "?") if isinstance(sym, dict) else "?"
                    strike = sym.get("strike_price", "?") if isinstance(sym, dict) else "?"
                    right = sym.get("option_type", "?") if isinstance(sym, dict) else "?"
                    qty   = opt.get("units", "")
                    price = opt.get("price", "")
                    print(f"  {ticker:<8} {right} {strike} exp={exp}  qty={qty}  mark=${price}")
    else:
        pprint(all_data)

except Exception as e:
    print(f"Error: {e}")
    import traceback; traceback.print_exc()

# ── 2. All positions (alternative endpoint) ───────────────────────────
print("\n\n=== POSITIONS (get_user_account_positions - all accounts) ===")
try:
    # Get accounts first
    accts = snaptrade.account_information.list_user_accounts(
        user_id=USER_ID, user_secret=USER_SECRET).body
    for acct in accts:
        aid  = acct["id"]
        name = acct.get("name", acct.get("number", aid))
        print(f"\n--- {name} ---")
        r2 = snaptrade.account_information.get_user_account_positions(
            user_id=USER_ID,
            user_secret=USER_SECRET,
            account_id=aid,
        )
        positions = r2.body
        if not positions:
            print("  (empty)")
            continue
        print(f"  {'Ticker':<8} {'Qty':>10} {'Price':>10} {'Avg':>10} {'Val':>12}")
        print("  " + "-"*54)
        for pos in positions:
            ticker = get_ticker(pos.get("symbol", {}))
            qty   = pos.get("units", 0) or 0
            price = pos.get("price", 0) or 0
            avg   = pos.get("average_purchase_price", 0) or 0
            val   = float(qty) * float(price)
            print(f"  {ticker:<8} {float(qty):>10,.3f} ${float(price):>9.2f} ${float(avg):>9.2f} ${val:>11,.0f}")
except Exception as e:
    print(f"Error: {e}")
