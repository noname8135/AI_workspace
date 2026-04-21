"""
SA Portfolio Scraper - handles login + intercepts API calls
"""
from playwright.sync_api import sync_playwright
import json
import time

PROFILE_DIR = r'C:\Users\User\AppData\Local\sa_isolated_profile'
PORTFOLIO_URL = 'https://seekingalpha.com/account/portfolio/my_view_1?portfolioId=64625272'

captured_apis = {}

def handle_response(response):
    url = response.url
    if 'seekingalpha.com/api/v3' in url or 'finance-api.seekingalpha.com' in url:
        try:
            body = response.json()
            captured_apis[url] = body
            # Only print portfolio-relevant ones
            if any(k in url for k in ['portfolio', 'ticker', 'holding', 'position', 'account']):
                print(f'  [API {response.status}] {url[-90:]}')
        except:
            pass

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=False,
        channel='chrome',
        args=['--no-first-run', '--start-maximized']
    )
    page = ctx.new_page()
    page.on('response', handle_response)

    print('Opening SA...')
    page.goto('https://seekingalpha.com', wait_until='domcontentloaded')
    time.sleep(2)

    # Check if logged in
    current_url = page.url
    page_text = page.inner_text('body')
    is_logged_in = 'noname8135' in page_text or 'Sign Out' in page_text or 'Log Out' in page_text

    if not is_logged_in:
        print('\nNot logged in! Please log in with Google in the browser window.')
        print('Waiting up to 3 minutes...')
        for i in range(180):
            time.sleep(1)
            txt = page.inner_text('body')
            if 'noname8135' in txt or 'Sign Out' in txt:
                print('Logged in!')
                break
        else:
            print('Timed out waiting for login')

    # Now navigate to portfolio
    print(f'\nNavigating to portfolio...')
    captured_apis.clear()  # reset so we only capture portfolio calls
    page.goto(PORTFOLIO_URL, wait_until='networkidle', timeout=60000)
    print('Page loaded. Waiting for data...')
    time.sleep(12)

    # Scroll to trigger lazy loads
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(3)
    page.evaluate('window.scrollTo(0, 0)')
    time.sleep(2)

    # Save screenshot
    page.screenshot(path='sa_portfolio_screenshot.png', full_page=True)
    print('Screenshot saved: sa_portfolio_screenshot.png')

    # Save all captured APIs
    with open('sa_captured_apis.json', 'w', encoding='utf-8') as f:
        json.dump(captured_apis, f, indent=2, ensure_ascii=False)
    print(f'\nCaptured {len(captured_apis)} API calls')

    print('\n=== ALL CAPTURED API CALLS ===')
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
                all_tickers.append({'ticker': sym, 'shares': shares, 'avg_price': avg, 'price': price})

    if all_tickers:
        seen = set()
        unique = [t for t in all_tickers if t['ticker'] not in seen and not seen.add(t['ticker'])]
        print(f'\n=== HOLDINGS ({len(unique)} tickers) ===')
        for h in unique:
            print(f"  {h['ticker']:<8} shares={h['shares']}  avg=${h['avg_price']}  now=${h['price']}")
        with open('sa_portfolio.json', 'w', encoding='utf-8') as f:
            json.dump(unique, f, indent=2)
        print('Saved: sa_portfolio.json')
    else:
        print('\nNo holdings extracted — save cookies for manual inspection')
        # Save current cookies for reuse
        cookies = ctx.cookies()
        with open('sa_session.json', 'w') as f:
            json.dump(cookies, f, indent=2)
        print(f'Saved {len(cookies)} cookies to sa_session.json')

    input('\nPress Enter to close browser...')
    ctx.close()
