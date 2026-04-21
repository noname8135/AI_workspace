"""
Pull tickers from SA portfolios using the correct account key
"""
import requests
import json

COOKIE_STR = (
    'machine_cookie=fejb9p4yg01749717025; '
    'sa-user-id=s%253A0-6ec99fb7-1ded-5f43-63cf-c2e7f6d391c2.8vl80SQqmjbyxRnAIAry9SXzGxULOfBbO9eDBx0JAeM; '
    'user_id=61474410; user_nick=noname8135; user_cookie_key=1lck18q; '
    'has_paid_subscription=true; ever_pro=1; '
    'user_remember_token=25a8238d5503b8487f8d9faaf02bafa731df5a7a; '
    'gk_user_access=1*premium.archived.community*1776623384; '
    'gk_user_access_sign=20010bb78d9d7de6c812b7d55cafb2220445bbec; '
    'session_id=e40dbc34-189b-4e62-9971-e32f882a2196; _ig=61474410; '
    'user_locale=en'
)

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Cookie': COOKIE_STR,
})

ACCOUNT_KEY = '1g2hldt'

# Portfolio IDs from earlier
portfolios = [
    ('64663649', 'Fidelity - BrokerageLink'),
    ('64663650', 'Fidelity - BrokerageLink Roth'),
    ('64625284', 'Fidelity - HSA'),
    ('64625283', 'Fidelity - ROTH IRA'),
    ('65001582', 'Holding'),
    ('64625272', 'Interactive Brokers'),
    ('64462971', 'Looking'),
    ('64483236', 'tools'),
]

all_results = {}

for pid, name in portfolios:
    print(f'\n--- {name} ({pid}) ---')

    # Try every plausible endpoint pattern
    attempts = [
        f'https://seekingalpha.com/api/v3/account/{ACCOUNT_KEY}/portfolios/{pid}/tickers?include=metrics,price_data',
        f'https://seekingalpha.com/api/v3/account/{ACCOUNT_KEY}/portfolios/{pid}/tickers',
        f'https://seekingalpha.com/api/v3/portfolio_items?ids={pid}&include=ticker',
        f'https://seekingalpha.com/api/v3/portfolios/{pid}/tickers',
        f'https://seekingalpha.com/api/v3/portfolios/{pid}?include=tickers',
        f'https://seekingalpha.com/api/v3/account/{ACCOUNT_KEY}/portfolios?ids={pid}&include=portfolio_items,portfolio_items.ticker',
    ]

    for url in attempts:
        r = s.get(url)
        if r.status_code == 200:
            data = r.json()
            items = data.get('data', [])
            print(f'  OK ({len(items)} items): {url[-70:]}')
            with open(f'sa_raw_{pid}.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            # Extract tickers
            tickers = []
            included = {i['id']: i for i in data.get('included', [])}
            for item in items:
                if isinstance(item, dict):
                    attrs = item.get('attributes', {})
                    rels = item.get('relationships', {})
                    tid = rels.get('ticker', {}).get('data', {}).get('id', '')
                    tinfo = included.get(tid, {}).get('attributes', {}) if tid else attrs
                    sym = (tinfo.get('slug') or tinfo.get('ticker') or attrs.get('slug') or '').upper()
                    qty = attrs.get('quantity', '')
                    avg = attrs.get('averagePrice', '')
                    price = tinfo.get('close', '')
                    if sym:
                        tickers.append({'ticker': sym, 'shares': qty, 'avg': avg, 'price': price})
                        print(f'    {sym:<8} shares={qty} avg=${avg} price=${price}')
            all_results[name] = tickers
            break
        else:
            print(f'  {r.status_code} {url[-60:]}')

# Save all
with open('sa_all_portfolios.json', 'w', encoding='utf-8') as f:
    json.dump(all_results, f, indent=2)
print('\nSaved: sa_all_portfolios.json')
