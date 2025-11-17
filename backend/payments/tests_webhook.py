from django.test import TestCase
from django.contrib.auth import get_user_model
from payments.models import Order
from rest_framework.test import APIClient
from django.conf import settings
import json
from pathlib import Path

User = get_user_model()


class WebhookTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create(username='wh', email='wh@example.com', coins=0)
        # ensure DEBUG so webhook endpoint is permissive in tests
        from django.conf import settings as _settings
        _settings.DEBUG = True

    def test_webhook_marks_order_paid_and_activates_premium(self):
        # create premium order
        coins_conf_path = Path(settings.BASE_DIR).parent / 'coins_config.json'
        conf = json.loads(coins_conf_path.read_text())
        premium_price = conf.get('premium', {}).get('monthly_price')
        order = Order.objects.create(user=self.user, pack_id='premium', amount=premium_price)

        url = '/api/v1/webhooks/yoco'
        payload = {'type': 'payment_success', 'order_id': str(order.id), 'tx_id': 'tx-web-1', 'event_id': 'ev-web-1'}
        resp = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.user.refresh_from_db()
        self.assertTrue(order.paid)
        self.assertTrue(self.user.is_premium)
        self.assertIsNotNone(self.user.premium_expires_at)
