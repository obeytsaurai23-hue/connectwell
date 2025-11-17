from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
import redis

User = get_user_model()


class FilterPurchaseTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create(username='filt', email='filt@example.com', coins=10)
        # set a fake channel mapping in redis so PurchaseFiltersView can persist channel key
        url = 'redis://localhost:6379/0'
        r = redis.from_url(url)
        r.set(f'connectwell:user_channel:{self.user.id}', f'chan-test-{self.user.id}')

    def test_purchase_filters_insufficient(self):
        self.client.force_authenticate(user=self.user)
        data = {'filters': {'gender': 'female'}, 'hours': 1}
        resp = self.client.post('/api/v1/filters/purchase', data=data, format='json')
        self.assertEqual(resp.status_code, 402)
        self.assertIn('required_coins', resp.data)

    def test_purchase_filters_success_and_redis(self):
        # give user enough coins
        self.user.coins = 100
        self.user.save()
        self.client.force_authenticate(user=self.user)
        data = {'filters': {'gender': 'female', 'location': '12.34,56.78'}, 'hours': 2}
        resp = self.client.post('/api/v1/filters/purchase', data=data, format='json')
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        self.assertEqual(data.get('coins_charged'), (15 * 2) + (15 * 2))
        # ensure Redis keys were set
        url = 'redis://localhost:6379/0'
        r = redis.from_url(url)
        chan_key = f"connectwell:active_filters:chan-test-{self.user.id}"
        user_key = f"connectwell:active_filters:user:{self.user.id}"
        val = r.get(chan_key) or r.get(user_key)
        self.assertIsNotNone(val)
