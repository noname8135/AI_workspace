"""
Shuai's Unified Portfolio — IBKR + Fidelity (via SnapTrade)
Prices: IB Gateway (live) > SnapTrade cache > memo cache (last known)
"""
from ib_insync import IB, Stock, util
from snaptrade_client import SnapTrade
from datetime import date, datetime
import time, json, os

# ── Config ──────────────────────────────────────────────────────────
IB_HOST   = '127.0.0.1'
IB_PORT   = 4001
IB_CLIENT = 15

ST_CLIENT = "PERS-QVW2R5PLDF11KSBNQT83"
ST_KEY    = "sCBpBZ0nzOhq7veDlzu7rqrDiO8EHBub3Ajqm0R8IO3obQ2zt1"
ST_USER   = "noname8135"
ST_SECRET = "3bb0fc5d-403c-4311-b603-72e5ca793729"

# Short display names for Fidelity accounts
ACCT_LABELS = {
    '1724c0c5-9459-4a84-9c9f-b40b2271de0c': 'Fid/BL',
    '6372f82f-fb5f-445a-862d-3e9768113e70': 'Fid/BLRoth',
    '4c6658c3-0fcb-4bd5-8346-98674ae0d30d': 'Fid/RothIRA',
    '78d44a9d-71f9-4f4a-a936-a3199ad80ef5': 'Fid/HSA',
}

MEMO_FILE = "price_memo.json"

today = date.today()
rows  = []
cash_rows = []  # (source, label, amount)

# ── Price memo: load / save last known prices ────────────────────────
def load_memo():
    if os.path.exists(MEMO_FILE):
        with open(MEMO_FILE) as f:
            return json.load(f)
    return {}

def save_memo(memo):
    with open(MEMO_FILE, 'w') as f:
        json.dump(memo, f, indent=2)

price_memo = load_memo()  # { "ALAB": {"price": 189.9, "ts": "2026-04-21 06:43"}, ... }

def memo_price(key, price):
    """Save a price to memo if it's valid (not nan, not 0)."""
    if price and price == price and price > 0:
        price_memo[key] = {"price": price, "ts": datetime.now().strftime("%Y-%m-%d %H:%M")}
        return price, False   # (price, is_stale)
    # Fall back to memo
    if key in price_memo:
        return price_memo[key]["price"], True  # stale=True
    return None, True

# ── Helpers ─────────────────────────────────────────────────────────
def dte(exp_str):
    try:
        d = datetime.strptime(exp_str, "%Y%m%d").date() if len(exp_str)==8 else date.fromisoformat(exp_str)
        return (d - today).days
    except:
        return None

def fmt_exp(exp_str, days):
    """Format expiry as 'Apr24(3d)' """
    if not exp_str:
        return ""
    try:
        d = datetime.strptime(exp_str, "%Y%m%d").date() if len(exp_str)==8 else date.fromisoformat(exp_str)
        label = d.strftime("%b") + str(d.day)  # e.g. Apr24
        return f"{label}({days}d)" if days is not None else label
    except:
        return exp_str

def apr(premium, strike, days):
    if not (premium and strike and days and days > 0):
        return None
    return (abs(float(premium)) / float(strike) / days) * 365 * 100

def fmt_pct(v):
    return f"{v:+.1f}%" if v is not None else ""

def fmt_apr(v):
    return f"{v:.0f}%" if v is not None else ""

def fmt_price(price, stale):
    if price is None:
        return "N/A"
    label = "*" if stale else ""  # * = last known
    return f"{price:.2f}{label}"

# ── 1. IBKR positions ────────────────────────────────────────────────
ib_prices = {}        # sym -> (price, stale)
ib_opt_contracts = [] # list of option tuples for greek fetch
print("Connecting to IB Gateway...")
try:
    ib = IB()
    ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT, readonly=True)
    ib.reqMarketDataType(3)

    # IB cash balances
    for v in ib.accountValues():
        if v.tag == 'CashBalance' and v.currency == 'USD' and v.account != 'All':
            try:
                amt = float(v.value)
                if amt != 0:
                    cash_rows.append(('IBKR', 'USD Cash', amt))
            except:
                pass

    for item in ib.portfolio():
        c      = item.contract
        pos    = item.position
        mark   = item.marketPrice
        avg    = item.averageCost

        if c.secType == 'STK':
            price, stale = memo_price(c.symbol, mark)
            pnl_pct = (price / avg - 1) * 100 if (price and avg) else None
            ib_prices[c.symbol] = (price, stale)
            rows.append({
                'source': 'IBKR', 'type': 'Stock', 'ticker': c.symbol,
                'strike': None, 'exp': None, 'dte': None,
                'qty': int(pos), 'price': price, 'stale': stale, 'avg': avg,
                'mktval': (price * pos) if price else item.marketValue,
                'pnl_pct': pnl_pct, 'entry_apr': None, 'curr_apr': None,
            })

        elif c.secType == 'OPT':
            exp_str = c.lastTradeDateOrContractMonth
            opt_key = f"{c.symbol}_{c.right}_{c.strike}_{exp_str}"
            d = dte(exp_str)
            avg_per_share = abs(avg) / 100
            price, stale = memo_price(opt_key, mark)
            e_apr = apr(avg_per_share, c.strike, d) if pos < 0 else None
            c_apr = apr(price, c.strike, d) if (pos < 0 and price) else None
            ib_opt_contracts.append((c, pos, price, stale, avg_per_share, d, exp_str, e_apr, c_apr))
            rows.append({
                'source': 'IBKR',
                'type': f"{'Short' if pos < 0 else 'Long'} {c.right}",
                'ticker': c.symbol,
                'strike': c.strike, 'exp': exp_str, 'dte': d,
                'qty': int(pos), 'price': price, 'stale': stale, 'avg': avg_per_share,
                'mktval': (price * pos * 100) if price else item.marketValue,
                'pnl_pct': (price / avg_per_share - 1) * 100 if (price and avg_per_share and pos > 0) else None,
                'entry_apr': e_apr, 'curr_apr': c_apr,
                'delta': None, 'theta': None, 'iv': None,  # filled below
            })

    # Fetch greeks for IBKR options
    greek_tickers = []
    for (c, pos, price, stale, avg_p, d, exp_str, e_apr, c_apr) in ib_opt_contracts:
        c.exchange = 'SMART'  # force SMART to avoid exchange validation error
        t = ib.reqMktData(c, '106', False, False)  # 106 = IV
        greek_tickers.append((c, t))
    if greek_tickers:
        ib.sleep(3)
    # Map greeks back into rows
    for (c, t) in greek_tickers:
        g = t.modelGreeks
        delta = g.delta if g else None
        theta = g.theta if g else None
        iv    = t.impliedVolatility
        key = f"{c.symbol}_{c.right}_{c.strike}_{c.lastTradeDateOrContractMonth}"
        for r in rows:
            if (r['source'] == 'IBKR' and r['ticker'] == c.symbol and
                r['strike'] == c.strike and r['exp'] == c.lastTradeDateOrContractMonth):
                r['delta'] = delta
                r['theta'] = theta
                r['iv']    = round(iv * 100, 1) if iv and iv == iv else None
                break

    ib.disconnect()
    print(f"IB: {len([r for r in rows if r['source']=='IBKR'])} positions loaded")
except Exception as e:
    print(f"IB error (Gateway may be off): {e}")

# ── 2. Fidelity via SnapTrade ────────────────────────────────────────
print("Fetching Fidelity via SnapTrade...")
try:
    st = SnapTrade(client_id=ST_CLIENT, consumer_key=ST_KEY)
    accounts = st.account_information.list_user_accounts(
        user_id=ST_USER, user_secret=ST_SECRET).body

    for acct in accounts:
        aid   = acct["id"]
        aname = ACCT_LABELS.get(aid, f'Fid/{acct.get("name",aid)[:10]}')  # already has Fid/ prefix

        # Stocks
        try:
            pos_data = st.account_information.get_user_account_positions(
                user_id=ST_USER, user_secret=ST_SECRET, account_id=aid).body
            for pos in pos_data:
                sym_obj = pos.get("symbol", {})
                inner   = sym_obj.get("symbol", {}) if isinstance(sym_obj, dict) else {}
                ticker  = inner.get("symbol", "") if isinstance(inner, dict) else str(inner)
                # Skip cash/money market tickers — captured via balances instead
                if ticker in ('FDRXX', 'FDIC91315', 'QMLTQ'):
                    continue
                if not ticker:
                    continue
                qty   = float(pos.get("units", 0) or 0)
                avg_p = float(pos.get("average_purchase_price", 0) or 0)
                # Prefer IB live price if same ticker exists there
                if ticker in ib_prices:
                    price, stale = ib_prices[ticker]
                else:
                    st_price = float(pos.get("price", 0) or 0)
                    price, stale = memo_price(ticker, st_price)
                pnl_pct = (price / avg_p - 1) * 100 if (price and avg_p) else None
                rows.append({
                    'source': aname, 'type': 'Stock', 'ticker': ticker,
                    'strike': None, 'exp': None, 'dte': None,
                    'qty': int(qty), 'price': price, 'stale': stale, 'avg': avg_p,
                    'mktval': qty * price if price else 0,
                    'pnl_pct': pnl_pct, 'entry_apr': None, 'curr_apr': None,
                })
        except Exception as e:
            pass

        # Fidelity cash balances
        try:
            hold_data = st.account_information.get_user_holdings(
                user_id=ST_USER, user_secret=ST_SECRET, account_id=aid).body
            for b in hold_data.get('balances', []):
                cash = b.get('cash', 0) or 0
                curr = b.get('currency', {}).get('code', 'USD')
                if cash and float(cash) > 0:
                    cash_rows.append((aname, f'{curr} Cash', float(cash)))
        except:
            pass

        # Options
        try:
            hold_data = st.account_information.get_user_holdings(
                user_id=ST_USER, user_secret=ST_SECRET, account_id=aid).body
            opts = hold_data.get("option_positions", [])
            for opt in opts:
                osym       = opt.get("symbol", {}).get("option_symbol", {})
                und        = osym.get("underlying_symbol", {}).get("symbol", "?")
                strike     = float(osym.get("strike_price", 0) or 0)
                exp_s      = osym.get("expiration_date", "")
                ticker_raw = osym.get("ticker", "")
                right      = "C" if "C" in ticker_raw.split()[-1] else "P"
                qty        = float(opt.get("units", 0) or 0)
                st_price   = float(opt.get("price", 0) or 0)
                opt_key    = f"{und}_{right}_{strike}_{exp_s}"
                price, stale = memo_price(opt_key, st_price)
                d          = dte(exp_s)
                avg_raw    = float(opt.get("average_purchase_price", 0) or 0)
                avg_p      = avg_raw / 100 if avg_raw > 50 else avg_raw
                e_apr      = apr(avg_p, strike, d) if qty < 0 else None
                c_apr      = apr(price, strike, d) if (qty < 0 and price) else None
                pnl_pct    = (price / avg_p - 1) * 100 if (price and avg_p and qty > 0) else None
                rows.append({
                    'source': aname,
                    'type': f"{'Short' if qty < 0 else 'Long'} {right}",
                    'ticker': und,
                    'strike': strike, 'exp': exp_s, 'dte': d,
                    'qty': int(qty), 'price': price, 'stale': stale, 'avg': avg_p,
                    'mktval': qty * price * 100 if price else 0,
                    'pnl_pct': pnl_pct, 'entry_apr': e_apr, 'curr_apr': c_apr,
                    'delta': None, 'theta': None, 'iv': None,
                })
        except Exception as e:
            pass

    print(f"Fidelity: {len([r for r in rows if 'Fid' in r['source']])} positions loaded")
except Exception as e:
    print(f"SnapTrade error: {e}")

# ── Save updated memo ────────────────────────────────────────────────
save_memo(price_memo)

# ── 3. Print tables ──────────────────────────────────────────────────
def leap_metrics(r):
    """Compute 5 LEAP metrics given a row with price, avg, strike, delta, theta, dte
    and the underlying stock price from ib_prices."""
    price   = r['price']       # option mark (per share)
    avg     = r['avg']         # entry premium (per share)
    strike  = r['strike']
    delta   = r['delta']
    theta   = r['theta']       # per day, negative
    d       = r['dte']
    ticker  = r['ticker']
    stk     = ib_prices.get(ticker, (None, None))[0]  # underlying price

    # Intrinsic value = max(stk - strike, 0) for calls
    intrinsic  = max(stk - strike, 0) if (stk and strike) else None
    extrinsic  = (price - intrinsic) if (price is not None and intrinsic is not None) else None

    # 1. Effective leverage = (stk * delta) / price
    leverage   = (stk * delta / price) if (stk and delta and price) else None

    # 2. Break-even % = (strike + avg) / stk - 1
    be_pct     = ((strike + avg) / stk - 1) * 100 if (stk and strike and avg) else None

    # 3. Extrinsic ratio = extrinsic / price
    ext_ratio  = (extrinsic / price * 100) if (extrinsic is not None and price) else None

    # 4. Annualized cost = (extrinsic / stk) / d * 365 * 100  (% of stock price per year)
    ann_cost   = (extrinsic / stk / d * 365 * 100) if (extrinsic and stk and d) else None

    # 5. Delta/Theta ratio = delta / abs(theta)
    dt_ratio   = (delta / abs(theta)) if (delta and theta and theta != 0) else None

    return leverage, be_pct, ext_ratio, ann_cost, dt_ratio


def print_table(title, subset, show_apr=False, show_leap=False):
    if not subset:
        return 0
    if show_leap:
        H = f"{'Source':<13} {'Ticker':<5} {'Stk':>6} {'Expiry':<13} {'Qty':>3}  {'Price':>7}  {'P&L%':>6}  {'Lev':>5}  {'BE%':>6}  {'ExtR%':>6}  {'AnnCst':>7}  {'D/T':>6}"
    elif show_apr:
        H = f"{'Source':<13} {'Ticker':<6} {'Strike':>7} {'Expiry':<14} {'Qty':>5}  {'Price':>9}  {'Avg':>9}  {'MktVal':>10}  {'EntAPR':>7}  {'CurAPR':>7}"
    else:
        H = f"{'Source':<13} {'Ticker':<6} {'Strike':>7} {'Expiry':<14} {'Qty':>5}  {'Price':>9}  {'Avg':>9}  {'MktVal':>10}  {'P&L%':>7}"
    sep = "=" * len(H)
    print(f"\n{sep}")
    print(f"  {title}")
    print(sep)
    print(H)
    print("-" * len(H))
    total = 0
    for r in sorted(subset, key=lambda x: (x['source'], x['dte'] or 9999, x['ticker'])):
        price_s  = fmt_price(r['price'], r.get('stale', False))
        avg_s    = f"{r['avg']:>9.2f}" if r['avg'] else "         "
        val_s    = f"{r['mktval']:>10,.0f}" if r['mktval'] else "          "
        strike_s = f"{r['strike']:>7.0f}" if r['strike'] else "       "
        exp_s    = fmt_exp(r['exp'], r['dte']) if r['exp'] else ""
        if r['mktval']:
            total += r['mktval']
        if show_leap:
            lev, be, ext, ann, dt = leap_metrics(r)
            stk_s  = f"{r['strike']:>6.0f}" if r['strike'] else "      "
            pnl_s  = fmt_pct(r['pnl_pct'])
            lev_s  = f"{lev:>5.1f}x" if lev else "      "
            be_s   = f"{be:>+6.1f}%" if be is not None else "      "
            ext_s  = f"{ext:>6.1f}%" if ext is not None else "      "
            ann_s  = f"{ann:>6.1f}%" if ann is not None else "      "
            dt_s   = f"{dt:>6.1f}" if dt is not None else "      "
            print(f"{r['source']:<13} {r['ticker']:<5} {stk_s} {exp_s:<13} {r['qty']:>3}  {price_s:>7}  {pnl_s:>6}  {lev_s}  {be_s}  {ext_s}  {ann_s}  {dt_s}")
        elif show_apr:
            eapr_s = fmt_apr(r['entry_apr'])
            capr_s = fmt_apr(r['curr_apr'])
            print(f"{r['source']:<13} {r['ticker']:<6} {strike_s} {exp_s:<14} {r['qty']:>5}  {price_s:>9}  {avg_s}  {val_s}  {eapr_s:>7}  {capr_s:>7}")
        else:
            pnl_s = fmt_pct(r['pnl_pct'])
            print(f"{r['source']:<13} {r['ticker']:<6} {strike_s} {exp_s:<14} {r['qty']:>5}  {price_s:>9}  {avg_s}  {val_s}  {pnl_s:>7}")
    print("-" * len(H))
    print(f"{'Subtotal':>{len(H)-11}} {total:>10,.0f}")
    print(sep)
    return total

stocks  = [r for r in rows if r['type'] == 'Stock']
long_c  = [r for r in rows if r['type'] == 'Long C']
long_p  = [r for r in rows if r['type'] == 'Long P']
short_c = [r for r in rows if r['type'] == 'Short C']
short_p = [r for r in rows if r['type'] == 'Short P']

t1  = print_table("STOCKS", stocks)
t2a = print_table("LONG CALLS", long_c, show_leap=True)
t2b = print_table("LONG PUTS", long_p, show_leap=True)
t3a = print_table("SHORT CALLS", short_c, show_apr=True)
t3b = print_table("SHORT PUTS", short_p, show_apr=True)

# ── Cash table ──────────────────────────────────────────────────────
total_cash = 0
if cash_rows:
    # Deduplicate IB cash (sum all segments)
    ib_cash = sum(amt for src, lbl, amt in cash_rows if src == 'IBKR')
    fid_cash = [(src, lbl, amt) for src, lbl, amt in cash_rows if src != 'IBKR']
    deduped = []
    if ib_cash:
        deduped.append(('IBKR', 'USD Cash', ib_cash))
    deduped.extend(fid_cash)

    CH = f"{'Source':<13} {'Label':<10} {'Amount':>12}"
    sep = '=' * len(CH)
    print(f'\n{sep}')
    print(f'  CASH & MONEY MARKET')
    print(sep)
    print(CH)
    print('-' * len(CH))
    for src, lbl, amt in sorted(deduped, key=lambda x: x[0]):
        print(f'{src:<13} {lbl:<10} {amt:>12,.0f}')
        total_cash += amt
    print('-' * len(CH))
    print(f"{'Subtotal':>23} {total_cash:>12,.0f}")
    print(sep)

grand = sum(t for t in [t1, t2a, t2b, t3a, t3b] if t) + total_cash
print(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  (* = last known price)")
print(f"GRAND TOTAL: {grand:,.0f}")
