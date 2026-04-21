"""
One-time SA login - run this once to save your session.
Chrome does NOT need to be closed.
"""
from playwright.sync_api import sync_playwright
import json
import time

PROFILE_DIR = r'C:\Users\User\AppData\Local\sa_isolated_profile'

with sync_playwright() as p:
    print('Opening browser for SA login...')
    print('Please log in with Google when the browser opens.\n')

    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=False,
        channel='chrome',
        args=['--no-first-run', '--no-default-browser-check', '--start-maximized']
    )

    page = ctx.new_page()
    page.goto('https://seekingalpha.com/authentication/sign_in', wait_until='domcontentloaded')

    print('Waiting for you to log in... (up to 3 minutes)')
    print('Steps: click Sign In -> Continue with Google -> select account\n')

    for i in range(180):
        time.sleep(1)
        try:
            txt = page.inner_text('body')
            url = page.url
            if 'noname8135' in txt or ('seekingalpha.com' in url and 'sign_in' not in url and 'authentication' not in url and 'login' not in url):
                print(f'Logged in! URL: {url}')
                break
        except:
            pass
    else:
        print('Timeout — did not detect login')

    # Save cookies
    cookies = ctx.cookies()
    with open('sa_session.json', 'w') as f:
        json.dump(cookies, f, indent=2)
    print(f'Saved {len(cookies)} cookies to sa_session.json')

    # Navigate to portfolio
    print('\nNavigating to portfolio to confirm...')
    page.goto('https://seekingalpha.com/account/portfolio/my_view_1?portfolioId=64625272', wait_until='domcontentloaded')
    time.sleep(5)
    page.screenshot(path='sa_confirm.png')
    print('Screenshot saved: sa_confirm.png')

    input('\nPress Enter to close browser...')
    ctx.close()
    print('\nDone! Now run: python sa_scrape.py')
