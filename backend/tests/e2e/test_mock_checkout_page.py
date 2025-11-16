import requests
from playwright.sync_api import sync_playwright


def test_mock_checkout_page_available():
    # Expect the dev server to be running at localhost:8000 in CI/dev before running this.
    url = 'http://127.0.0.1:8000/demo/mock_checkout.html'
    # simple HTTP check
    r = requests.get(url)
    assert r.status_code == 200
    # Use Playwright to open the page and assert content exists
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        assert 'Mock Checkout' in page.content() or '<form' in page.content()
        browser.close()
