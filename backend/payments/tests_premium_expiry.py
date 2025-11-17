from django.test import TestCase
from django.contrib.auth import get_user_model
from payments.models import Order
from rest_framework.test import APIClient
from django.conf import settings
import json
from pathlib import Path

User = get_user_model()


class PremiumExpiryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create(username='prem', email='prem@example.com', coins=0)
        # Ensure DEBUG is True so test-only endpoints are available
        from django.conf import settings as _settings
        _settings.DEBUG = True

    def test_premium_activation_sets_expiry(self):
        # create order
        coins_conf_path = Path(settings.BASE_DIR).parent / 'coins_config.json'
        conf = json.loads(coins_conf_path.read_text())
        premium_price = conf.get('premium', {}).get('monthly_price')
        order = Order.objects.create(user=self.user, pack_id='premium', amount=premium_price)
        # call test mark paid endpoint (enabled in DEBUG)
        url = '/api/v1/test/mark_order_paid'
        resp = self.client.post(url, data={'order_id': str(order.id), 'tx_id': 'tx1'}, format='json')
        print('RESP', resp.status_code, getattr(resp, 'data', None))
        self.assertEqual(resp.status_code, 200)
        # reload user and order to inspect changes
        order.refresh_from_db()
        self.user.refresh_from_db()
        print('ORDER paid:', order.paid, 'user premium:', self.user.is_premium, 'expiry:', self.user.premium_expires_at)
        self.assertTrue(self.user.is_premium)
        self.assertIsNotNone(self.user.premium_expires_at)
