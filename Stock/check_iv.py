"""
Check IV, delta, theta for all short options
"""
from ib_insync import IB, Option
import time

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=15, readonly=True)
ib.reqMarketDataType(3)

shorts = [
    ('ALAB', '20260508', 130.0, 'C'),
    ('APP',  '20260508', 475.0, 'C'),
    ('META', '20260501', 675.0, 'C'),
    ('TSLA', '20260424', 320.0, 'P'),
    ('LITE', '20260515', 690.0, 'P'),
]

print(f"{'Symbol':<6} {'T':<2} {'Strike':>7} {'Exp':<6} {'Mark':>7} {'IV%':>7} {'Delta':>7} {'Theta':>8} {'Gamma':>7}")
print('-'*65)

for sym, exp, strike, right in shorts:
    c = Option(sym, exp, strike, right, 'SMART')
    try:
        ib.qualifyContracts(c)
        ticker = ib.reqMktData(c, '106', False, False)
        time.sleep(3)

        mark = ticker.marketPrice()
        iv   = ticker.impliedVolatility

        g = ticker.modelGreeks
        delta = g.delta if g else None
        theta = g.theta if g else None
        gamma = g.gamma if g else None

        def fmt(v, fmt_str):
            return (fmt_str.format(v)) if (v is not None and v == v) else 'N/A'

        exp_label = exp[4:6] + '/' + exp[6:8]
        iv_str    = fmt(iv * 100 if iv and iv == iv else None, '{:.1f}%')
        d_str     = fmt(delta, '{:.3f}')
        t_str     = fmt(theta, '{:.2f}')
        gm_str    = fmt(gamma, '{:.4f}')
        mk_str    = f'${mark:.2f}' if mark and mark == mark else 'N/A'

        print(f"{sym:<6} {right:<2} {strike:>7.0f} {exp_label:<6} {mk_str:>7} {iv_str:>7} {d_str:>7} {t_str:>8} {gm_str:>7}")

    except Exception as e:
        print(f"{sym:<6} {right:<2} {strike:>7.0f}  error: {e}")

ib.disconnect()
