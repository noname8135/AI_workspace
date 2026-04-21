"""
Live IBKR options positions with Entry APR and Current APR
"""
from ib_insync import IB, util
from datetime import datetime, date
import math

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=15, readonly=True)

portfolio = ib.portfolio()

def calc_apr(premium, strike, dte):
    if not all([premium, strike, dte]) or dte <= 0:
        return None
    return (premium / strike / dte) * 365 * 100

def parse_expiry(exp_str):
    try:
        return datetime.strptime(exp_str, "%Y%m%d").date()
    except:
        return None

today = date.today()

longs = []
shorts = []

for item in portfolio:
    c = item.contract
    if c.secType != 'OPT':
        continue

    pos = item.position
    mark = item.marketPrice
    avg_cost = item.averageCost  # per share (already divided by 100 by IB)
    unreal = item.unrealizedPNL
    mktval = item.marketValue

    exp = parse_expiry(c.lastTradeDateOrContractMonth)
    dte = (exp - today).days if exp else None
    strike = c.strike
    right = c.right  # 'C' or 'P'
    sym = c.symbol

    # Entry APR (based on avg_cost)
    # For shorts: avg_cost is negative (credit received), we use abs
    entry_prem = abs(avg_cost) / 100  # convert to per-share
    entry_apr = calc_apr(entry_prem, strike, dte) if dte else None

    # Current APR (based on current mark)
    curr_apr = calc_apr(abs(mark), strike, dte) if (mark and dte) else None

    row = {
        'sym': sym,
        'right': right,
        'strike': strike,
        'exp': c.lastTradeDateOrContractMonth,
        'dte': dte,
        'pos': int(pos),
        'mark': mark,
        'avg_cost': avg_cost,
        'entry_prem': entry_prem,
        'entry_apr': entry_apr,
        'curr_apr': curr_apr,
        'unreal': unreal,
        'mktval': mktval,
    }

    if pos < 0:
        shorts.append(row)
    else:
        longs.append(row)

print("\n" + "="*85)
print("SHORT OPTIONS (sold premium)")
print("="*85)
print(f"{'Symbol':<6} {'Type':<4} {'Strike':>7} {'Exp':<10} {'DTE':>4} {'Pos':>4} "
      f"{'Mark':>7} {'Entry$':>7} {'EntryAPR':>9} {'CurrAPR':>9} {'Unreal':>9}")
print("-"*85)

for r in sorted(shorts, key=lambda x: x['dte'] or 999):
    ea = f"{r['entry_apr']:.1f}%" if r['entry_apr'] else "N/A"
    ca = f"{r['curr_apr']:.1f}%" if r['curr_apr'] else "N/A"
    print(f"{r['sym']:<6} {r['right']:<4} {r['strike']:>7.0f} {r['exp']:<10} {str(r['dte'] or '?'):>4} "
          f"{r['pos']:>4} ${r['mark']:>6.2f} ${r['entry_prem']:>6.2f} "
          f"{ea:>9} {ca:>9} ${r['unreal']:>8.0f}")

print(f"\n{'TOTAL UNREALIZED P&L (shorts)':>50}: ${sum(r['unreal'] for r in shorts):,.0f}")

print("\n" + "="*85)
print("LONG OPTIONS (bought premium / LEAPs)")
print("="*85)
print(f"{'Symbol':<6} {'Type':<4} {'Strike':>7} {'Exp':<10} {'DTE':>4} {'Pos':>4} "
      f"{'Mark':>7} {'AvgCost':>8} {'Unreal':>9} {'MktVal':>9}")
print("-"*85)

for r in sorted(longs, key=lambda x: x['dte'] or 999):
    avg_per_share = abs(r['avg_cost']) / 100
    print(f"{r['sym']:<6} {r['right']:<4} {r['strike']:>7.0f} {r['exp']:<10} {str(r['dte'] or '?'):>4} "
          f"{r['pos']:>4} ${r['mark']:>6.2f} ${avg_per_share:>7.2f} "
          f"${r['unreal']:>8.0f} ${r['mktval']:>8.0f}")

print(f"\n{'TOTAL UNREALIZED P&L (longs)':>50}: ${sum(r['unreal'] for r in longs):,.0f}")
print(f"{'TOTAL UNREALIZED P&L (all options)':>50}: ${sum(r['unreal'] for r in shorts + longs):,.0f}")

# APR summary for shorts
print("\n" + "="*60)
print("SHORT OPTIONS APR SUMMARY")
print("="*60)
print(f"{'Symbol':<6} {'Type':<4} {'Strike':>7} {'DTE':>4} {'Entry APR':>10} {'Curr APR':>10} {'Status'}")
print("-"*60)
for r in sorted(shorts, key=lambda x: x['dte'] or 999):
    ea = r['entry_apr'] or 0
    ca = r['curr_apr'] or 0
    status = "decay" if ca < ea else "WIDENED"
    ea_str = f"{ea:.1f}%" if ea else "N/A"
    ca_str = f"{ca:.1f}%" if ca else "N/A"
    print(f"{r['sym']:<6} {r['right']:<4} {r['strike']:>7.0f} {str(r['dte'] or '?'):>4} "
          f"{ea_str:>10} {ca_str:>10}  {status}")

ib.disconnect()
