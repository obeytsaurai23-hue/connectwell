from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from .models import Order
from accounts.models import WalletTransaction

User = get_user_model()


class PaymentsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create(email='paytest@example.com')

    def test_create_purchase_and_webhook_credits_coins(self):
        # create an order via endpoint
        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/v1/coins/purchase', {'pack_id': 'starter'}, format='json')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        order_id = body.get('order_id')
        self.assertIsNotNone(order_id)
        order = Order.objects.get(id=order_id)
        self.assertFalse(order.paid)
        # simulate webhook
        web_resp = self.client.post('/api/v1/webhooks/yoco', {'type': 'payment_success', 'order_id': order_id, 'tx_id': 'TX123'}, format='json')
        self.assertEqual(web_resp.status_code, 200)
        order.refresh_from_db()
        self.assertTrue(order.paid)
        # user should have coins credited (starter pack has 25 per coins_config.json)
        self.user.refresh_from_db()
        self.assertGreaterEqual(self.user.coins, 25)
        # WalletTransaction created
        txs = WalletTransaction.objects.filter(user=self.user, reason__startswith='purchase:')
        self.assertTrue(txs.exists())

    def test_create_order_and_poll_status_then_webhook(self):
        # create an order via endpoint as authenticated user
        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/v1/coins/purchase', {'pack_id': 'starter'}, format='json')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        order_id = body.get('order_id')
        self.assertIsNotNone(order_id)
        # initial status should be unpaid
        status_resp = self.client.get(f'/api/v1/coins/order/{order_id}/status')
        self.assertEqual(status_resp.status_code, 200)
        self.assertFalse(status_resp.json().get('paid'))
        # simulate webhook to mark paid
        web_resp = self.client.post('/api/v1/webhooks/yoco', {'type': 'payment_success', 'order_id': order_id, 'tx_id': 'WEBTX'}, format='json')
        self.assertEqual(web_resp.status_code, 200)
        status_resp2 = self.client.get(f'/api/v1/coins/order/{order_id}/status')
        self.assertTrue(status_resp2.json().get('paid'))

    def test_webhook_idempotent_double_post(self):
        # create an order and simulate the webhook twice; ensure coins are credited only once
        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/v1/coins/purchase', {'pack_id': 'starter'}, format='json')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        order_id = body.get('order_id')
        # first webhook
        web_resp1 = self.client.post('/api/v1/webhooks/yoco', {'type': 'payment_success', 'order_id': order_id, 'tx_id': 'TX1'}, format='json')
        self.assertEqual(web_resp1.status_code, 200)
        self.user.refresh_from_db()
        coins_after_first = self.user.coins
        # second webhook identical
        web_resp2 = self.client.post('/api/v1/webhooks/yoco', {'type': 'payment_success', 'order_id': order_id, 'tx_id': 'TX1'}, format='json')
        self.assertEqual(web_resp2.status_code, 200)
        self.user.refresh_from_db()
        coins_after_second = self.user.coins
        self.assertEqual(coins_after_first, coins_after_second)

    def test_webhook_signature_verification(self):
        import os, hmac, hashlib, json
        secret = 'shhhhh-test'
        os.environ['YOCO_WEBHOOK_SECRET'] = secret
        try:
            # create order
            self.client.force_authenticate(user=self.user)
            resp = self.client.post('/api/v1/coins/purchase', {'pack_id': 'starter'}, format='json')
            order_id = resp.json().get('order_id')
            payload = {'type': 'payment_success', 'order_id': order_id, 'tx_id': 'SIGTX', 'event_id': 'EV1'}
            body = json.dumps(payload)
            sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            # invalid signature should be rejected
            bad = self.client.post('/api/v1/webhooks/yoco', data=body, content_type='application/json', HTTP_X_YOCO_SIGNATURE='bad')
            self.assertEqual(bad.status_code, 400)
            # valid signature should be accepted
            good = self.client.post('/api/v1/webhooks/yoco', data=body, content_type='application/json', HTTP_X_YOCO_SIGNATURE=sig)
            self.assertEqual(good.status_code, 200)
        finally:
            del os.environ['YOCO_WEBHOOK_SECRET']

    def test_wallet_endpoint_returns_balance_and_transactions(self):
        # Ensure wallet endpoint returns coins and transactions for authenticated user
        # create a transaction
        WalletTransaction.objects.create(user=self.user, amount=50, reason='test:credit')
        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/v1/wallet')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn('coins', body)
        self.assertIn('transactions', body)
        self.assertTrue(isinstance(body['transactions'], list))