"""
SA Portfolio Scraper - uses your REAL Chrome profile (must be closed first)
"""
from playwright.sync_api import sync_playwright
import json
import time

REAL_CHROME_PROFILE = r'C:\Users\User\AppData\Local\Google\Chrome\User Data'
PORTFOLIO_URL = 'https://seekingalpha.com/account/portfolio/my_view_1?portfolioId=64625272'

captured_apis = {}

def handle_response(response):
    url = response.url
    if 'seekingalpha.com/api/v3' in url or 'finance-api.seekingalpha.com' in url:
        try:
            body = response.json()
            captured_apis[url] = body
            print(f'  [API {response.status}] {url[-90:]}')
        except:
            pass

with sync_playwright() as p:
    print('Launching your real Chrome...')
    print('(Chrome must be fully closed before this works)\n')

    ctx = p.chromium.launch_persistent_context(
        user_data_dir=REAL_CHROME_PROFILE,
        channel='chrome',
        headless=False,
        args=[
            '--profile-directory=Default',
            '--no-first-run',
            '--no-default-browser-check',
            '--start-maximized',
        ]
    )

    page = ctx.new_page()
    page.on('response', handle_response)

    print(f'Loading portfolio page...')
    page.goto(PORTFOLIO_URL, wait_until='networkidle', timeout=60000)
    print('Page loaded. Waiting for data to populate...')
    time.sleep(15)

    # Scroll to trigger lazy loads
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(3)
    page.evaluate('window.scrollTo(0, 0)')
    time.sleep(2)

    # Screenshot
    page.screenshot(path='sa_screenshot.png', full_page=True)
    print('Screenshot: sa_screenshot.png')

    # Save all APIs
    with open('sa_captured_apis.json', 'w', encoding='utf-8') as f:
        json.dump(captured_apis, f, indent=2, ensure_ascii=False)
    print(f'\nCaptured {len(captured_apis)} API calls')

    # Show all URLs
    print('\n=== CAPTURED API CALLS ===')
    for url in sorted(captured_apis.keys()):
        print(f'  {url}')

    # Extract holdings
    all_tickers = []
    for url, data in captured_apis.items():
        if not isinstance(data, dict):
            continue
        items = data.get('data', [])
        if not isinstance(items, list) or not items:
            continue
        included = {i['id']: i for i in data.get('included', [])}
        for item in items:
            if not isinstance(item, dict):
                continue
            attrs = item.get('attributes', {})
            rels = item.get('relationships', {})
            tid = rels.get('ticker', {}).get('data', {}).get('id', '')
            tinfo = included.get(tid, {}).get('attributes', {}) if tid else {}
            sym = (tinfo.get('slug') or attrs.get('ticker') or attrs.get('slug') or '').upper()
            if sym and 1 <= len(sym) <= 6:
                shares = attrs.get('quantity', '')
                avg = attrs.get('averagePrice', '')
                price = tinfo.get('close', tinfo.get('last', ''))
                chg = tinfo.get('changePercent', tinfo.get('change', ''))
                all_tickers.append({'ticker': sym, 'shares': shares, 'avg_price': avg, 'price': price, 'chg': chg})

    if all_tickers:
        seen = set()
        unique = [t for t in all_tickers if t['ticker'] not in seen and not seen.add(t['ticker'])]
        print(f'\n=== HOLDINGS ({len(unique)} tickers) ===')
        print(f"{'Ticker':<8} {'Shares':<10} {'Avg Price':<12} {'Current':<10} {'Chg%'}")
        print('-' * 55)
        for h in unique:
            p_str = f"${float(h['price']):.2f}" if h['price'] else '--'
            c_str = f"{float(h['chg']):+.2f}%" if h['chg'] else '--'
            avg_str = f"${float(h['avg_price']):.2f}" if h['avg_price'] else '--'
            print(f"{h['ticker']:<8} {str(h['shares']):<10} {avg_str:<12} {p_str:<10} {c_str}")
        with open('sa_portfolio.json', 'w', encoding='utf-8') as f:
            json.dump(unique, f, indent=2)
        print('\nSaved: sa_portfolio.json')
    else:
        print('\nNo holdings extracted from API calls')

    input('\nPress Enter to close browser...')
    ctx.close()
