from django.test import TestCase
from rest_framework.test import APIClient
from .models import PinCode
from django.utils import timezone
from datetime import timedelta


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_send_pin_creates_pin(self):
        resp = self.client.post('/api/v1/auth/send_pin', {'email': 'test@example.com'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(PinCode.objects.filter(email='test@example.com').exists())

    def test_verify_pin_fails_with_wrong_pin(self):
        # create a pin entry
        PinCode.objects.create(email='foo@example.com', code_hash='notahash', expires_at=timezone.now() + timedelta(minutes=5))
        resp = self.client.post('/api/v1/auth/verify_pin', {'email': 'foo@example.com', 'pin': '0000'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_send_pin_rate_limit(self):
        # send pin 5 times (allowed), 6th should be throttled
        url = '/api/v1/auth/send_pin'
        for i in range(5):
            resp = self.client.post(url, {'email': 'rate@example.com'}, format='json')
            self.assertEqual(resp.status_code, 200)
        # 6th request
        resp = self.client.post(url, {'email': 'rate@example.com'}, format='json')
        self.assertIn(resp.status_code, (429, 400))
