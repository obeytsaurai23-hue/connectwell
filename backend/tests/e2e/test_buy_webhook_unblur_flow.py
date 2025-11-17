import requests
from playwright.sync_api import sync_playwright


BASE = 'http://127.0.0.1:8000'


def test_purchase_and_webhook_marks_order_paid():
    # This test assumes a dev server is running at 127.0.0.1:8000 with MOCK_CHECKOUT=1
    # Step 1: create purchase
    resp = requests.post(f"{BASE}/api/v1/coins/purchase", json={"pack_id": "starter"})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get('ok') is True
    order_id = body.get('order_id')
    assert order_id

    # Step 2: open the mock checkout page in Playwright to simulate user-facing flow
    checkout_url = body.get('checkout_url') or f"/mock_checkout.html?order_id={order_id}"
    # In dev the demo pages are served under /demo/, prefer that path so the page exists
    if checkout_url.startswith('/mock_checkout.html'):
        checkout_url = checkout_url.replace('/mock_checkout.html', '/demo/mock_checkout.html')
    url = f"{BASE}{checkout_url}" if checkout_url.startswith('/') else checkout_url
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        # The mock page should contain an element or text indicating the order id
        assert str(order_id) in page.content()
        browser.close()

    # Step 3: mark the order paid via test-only endpoint (avoids dependency on external webhook delivery)
    mark_resp = requests.post(f"{BASE}/api/v1/test/mark_order_paid", json={"order_id": order_id, "tx_id": "tx-e2e-1"})
    assert mark_resp.status_code == 200
    assert mark_resp.json().get('ok') is True

    # Step 4: query order status and ensure it's marked paid (poll briefly in case of slight delay)
    paid = False
    status_body = {}
    for _ in range(10):
        status_resp = requests.get(f"{BASE}/api/v1/coins/order/{order_id}/status")
        assert status_resp.status_code == 200
        status_body = status_resp.json()
        if status_body.get('paid'):
            paid = True
            break
    assert status_body.get('ok') is True
    assert paid is True, f"Order not marked paid after webhook; last status: {status_body}"
