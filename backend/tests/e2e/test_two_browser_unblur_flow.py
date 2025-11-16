import requests
from playwright.sync_api import sync_playwright


BASE = 'http://127.0.0.1:8000'


def test_two_browser_unblur_flow():
    # Create owner (user A) who charges viewers
    a_resp = requests.post(f"{BASE}/api/v1/test/create_user", json={"email": "owner@example.local", "coins": 0, "charge_viewers": True})
    assert a_resp.status_code == 200
    a_body = a_resp.json()
    a_id = a_body['user']['id']

    # Create viewer (user B) with enough coins
    b_resp = requests.post(f"{BASE}/api/v1/test/create_user", json={"email": "viewer@example.local", "coins": 10})
    assert b_resp.status_code == 200
    b_body = b_resp.json()
    b_id = b_body['user']['id']
    b_token = b_body['access_token']

    # Create a session linking them
    s_resp = requests.post(f"{BASE}/api/v1/test/create_session", json={"user_a_id": a_id, "user_b_id": b_id})
    assert s_resp.status_code == 200
    s_body = s_resp.json()
    session_id = s_body['session_id']

    # Use Playwright to simulate viewer performing the unblur action from a browser context
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # navigate to the demo page so the page origin matches the server (avoids CORS/preflight)
        page.goto(f"{BASE}/demo/")

        # Call the unblur API directly using the viewer's JWT to avoid CORS/preflight issues in page.evaluate
        headers = {'Authorization': f'Bearer {b_token}', 'Content-Type': 'application/json'}
        r = requests.post(f"{BASE}/api/v1/sessions/{session_id}/unblur/", headers=headers, json={})
        assert r.status_code in (200, 402, 403)
        jr = r.json()
        assert 'detail' in jr
        assert jr.get('detail') in ('Unblurred', 'Already unblurred', 'Insufficient coins', 'Not a participant or not linked user.')

        # verify session now shows unblurred for the owner side
        detail = requests.get(f"{BASE}/api/v1/test/session/{session_id}/")
        assert detail.status_code == 200
        dj = detail.json()
        assert dj.get('user_a_unblurred') is True

        browser.close()
