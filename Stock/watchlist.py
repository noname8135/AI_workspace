"""
Read IBKR watchlist / scanner
"""
from ib_insync import IB, Stock, util
import time

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=15, readonly=True)
ib.reqMarketDataType(3)

# Method 1: Get all positions (stocks only)
print("=== Current Stock Positions ===")
portfolio = ib.portfolio()
stock_positions = [i for i in portfolio if i.contract.secType == 'STK']
for item in stock_positions:
    print(f"  {item.contract.symbol:<8} qty={item.position:.0f}  avg=${item.averageCost:.2f}  mark=${item.marketPrice:.2f}  unreal=${item.unrealizedPNL:,.0f}")

# Method 2: Try to read scanner/watchlist tags
print("\n=== Attempting to read watchlists ===")
try:
    tags = ib.reqScannerParameters()
    # Save full scanner XML for inspection
    with open('scanner_params.xml', 'w') as f:
        f.write(tags)
    print(f"Scanner params saved ({len(tags)} chars) -> scanner_params.xml")
except Exception as e:
    print(f"Scanner params error: {e}")

# Method 3: Try to get account tags / model portfolios
print("\n=== Account Values ===")
vals = ib.accountValues()
relevant = [v for v in vals if any(k in v.tag for k in ['NetLiquid', 'TotalCash', 'GrossPosition', 'EquityWithLoan'])]
for v in relevant[:10]:
    print(f"  {v.tag}: {v.value} {v.currency}")

ib.disconnect()
