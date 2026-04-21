from ib_insync import IB, Stock, Option
from datetime import date, datetime

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=15, readonly=True)
ib.reqMarketDataType(1)  # live

# Stock price — use mid if possible
tsla = Stock('TSLA', 'SMART', 'USD')
ib.qualifyContracts(tsla)
ts = ib.reqMktData(tsla, '', False, False)
ib.sleep(2)
bid = ts.bid if ts.bid and ts.bid > 0 else None
ask = ts.ask if ts.ask and ts.ask > 0 else None
price = (bid + ask) / 2 if (bid and ask) else ts.last or ts.close
print(f"TSLA: {price:.2f}  (bid={bid}  ask={ask})")

targets = [
    ('20260424', 400), ('20260424', 405), ('20260424', 410),
    ('20260424', 415), ('20260424', 420), ('20260424', 425),
    ('20260501', 400), ('20260501', 405), ('20260501', 410),
    ('20260501', 415), ('20260501', 420),
    ('20260508', 405), ('20260508', 410), ('20260508', 415), ('20260508', 420),
]

OUT = open(r'C:\Users\User\Desktop\AI_workspace\Stock\last_scan.txt', 'w')
def p(s=''):
    print(s)
    OUT.write(s + '\n')

p(f"\n{'Exp':<10} {'Stk':>5}   {'Bid':>6} {'Ask':>6} {'Mid':>6}   {'Delta':>6} {'Theta':>6}   {'DTE':>3} {'APR':>6} {'OTM%':>6}")
p("-" * 78)

for exp, strike in targets:
    try:
        c = Option('TSLA', exp, strike, 'C', 'SMART')
        cs = ib.qualifyContracts(c)
        if not cs:
            continue
        tc = ib.reqMktData(cs[0], '106', False, False)
        ib.sleep(1.5)

        bid = tc.bid if tc.bid and tc.bid > 0 else None
        ask = tc.ask if tc.ask and tc.ask > 0 else None
        mid = (bid + ask) / 2 if (bid and ask) else None

        if not mid:
            continue  # skip if no real quote

        g     = tc.modelGreeks
        delta = g.delta if g else None
        theta = g.theta if g else None

        d       = (datetime.strptime(exp, '%Y%m%d').date() - date.today()).days
        apr_val = mid / strike / d * 365 * 100 if d > 0 else None
        otm_pct = (strike / price - 1) * 100 if price else None

        bid_s  = f"{bid:.2f}" if bid else "  -  "
        ask_s  = f"{ask:.2f}" if ask else "  -  "
        mid_s  = f"{mid:.2f}"
        d_s    = f"{delta:.2f}" if delta else "  -  "
        th_s   = f"{theta:.2f}" if theta else "  -  "
        ap_s   = f"{apr_val:.0f}%" if apr_val else "?"
        ot_s   = f"{otm_pct:+.1f}%" if otm_pct is not None else "?"

        p(f"{exp}  {strike:>5}C   {bid_s:>6} {ask_s:>6} {mid_s:>6}   {d_s:>6} {th_s:>6}   {d:>3} {ap_s:>6} {ot_s:>6}")
    except Exception as e:
        print(f"{exp}  {strike}C  error: {e}")

OUT.close()
print('Saved to last_scan.txt')
ib.disconnect()
