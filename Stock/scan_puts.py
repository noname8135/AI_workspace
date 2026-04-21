from ib_insync import IB, Stock, Option
from datetime import date, datetime

SYMBOL = 'TMDX'
EXPS   = ['20260515', '20260618', '20260717']
OTM_LO = 0.02
OTM_HI = 0.20

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=15, readonly=True)
ib.reqMarketDataType(1)

stk = Stock(SYMBOL, 'SMART', 'USD')
ib.qualifyContracts(stk)
ts = ib.reqMktData(stk, '', False, False)
ib.sleep(2)
b, a = ts.bid, ts.ask
price = (b + a) / 2 if (b and b > 0 and a and a > 0) else ts.last or ts.close
print(f"{SYMBOL}: {price:.2f}")

lo = round(price * (1 - OTM_HI) / 5) * 5
hi = round(price * (1 - OTM_LO) / 5) * 5
strikes = list(range(lo, hi + 5, 5))
strike_step = 5  # TMDX only has $5 wide strikes
today = date.today()
print(f"Scanning strikes {lo}-{hi} across {EXPS}")

OUT = open(r'C:\Users\User\Desktop\AI_workspace\Stock\last_scan.txt', 'w')
def p(s=''):
    print(s)
    OUT.write(s + '\n')

p(f"\n{'Exp':<10} {'Stk':>5}   {'Bid':>6} {'Ask':>6} {'Mid':>6}   {'Delta':>6} {'Theta':>6}   {'DTE':>3} {'APR':>6} {'OTM%':>6}")
p("-" * 76)

for exp in EXPS:
    d = (datetime.strptime(exp, '%Y%m%d').date() - today).days
    if d < 1 or d > 100:
        continue
    for strike in strikes:
        try:
            c = Option(SYMBOL, exp, strike, 'P', 'SMART')
            cs = ib.qualifyContracts(c)
            if not cs:
                continue
            tc = ib.reqMktData(cs[0], '106', False, False)
            ib.sleep(1.2)

            bid = tc.bid if tc.bid and tc.bid > 0 else None
            ask = tc.ask if tc.ask and tc.ask > 0 else None
            mid = (bid + ask) / 2 if (bid and ask) else None
            if not mid:
                continue

            g     = tc.modelGreeks
            delta = g.delta if g else None
            theta = g.theta if g else None
            apr   = mid / strike / d * 365 * 100
            otm   = (strike / price - 1) * 100

            bid_s = f"{bid:.2f}" if bid else "  -  "
            ask_s = f"{ask:.2f}" if ask else "  -  "
            d_s   = f"{delta:.2f}" if delta else "  -  "
            th_s  = f"{theta:.2f}" if theta else "  -  "
            mark  = " <--" if delta and -0.42 <= delta <= -0.28 else ""
            if apr < 50:
                continue
            p(f"{exp}  {strike:>5}P   {bid_s:>6} {ask_s:>6} {mid:>6.2f}   {d_s:>6} {th_s:>6}   {d:>3} {apr:>5.0f}% {otm:>+5.1f}%{mark}")
        except Exception as e:
            pass

OUT.close()
print('Saved to last_scan.txt')
ib.disconnect()
