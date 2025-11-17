from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from .models import MatchSession

User = get_user_model()


class NextAdLogicTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_a = User.objects.create(username='n1', email='n1@example.com', coins=0)
        self.user_b = User.objects.create(username='n2', email='n2@example.com', coins=0)
        # create session
        self.session = MatchSession.objects.create(
            user_a=self.user_a,
            user_b=self.user_b,
            user_a_channel='chan-a',
            user_b_channel='chan-b',
        )

    def test_non_premium_sees_ad_after_three_nexts(self):
        self.client.force_authenticate(user=self.user_a)
        url = f'/api/v1/sessions/{self.session.id}/next/'
        # first two nexts -> next_ack
        r1 = self.client.post(url, {})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.data.get('action'), 'next_ack')
        r2 = self.client.post(url, {})
        self.assertEqual(r2.data.get('action'), 'next_ack')
        # third next -> ad_required
        r3 = self.client.post(url, {})
        self.assertEqual(r3.data.get('action'), 'ad_required')
        self.assertGreaterEqual(int(r3.data.get('count', 0)), 3)
        # simulate watching ad -> reset counter
        ad_url = f'/api/v1/sessions/{self.session.id}/next/ad_watched/'
        r4 = self.client.post(ad_url, {})
        self.assertEqual(r4.status_code, 200)
        # after ad watched, next should be allowed again
        r5 = self.client.post(url, {})
        self.assertEqual(r5.data.get('action'), 'next_ack')

    def test_premium_no_ad(self):
        self.user_a.is_premium = True
        self.user_a.save()
        self.client.force_authenticate(user=self.user_a)
        url = f'/api/v1/sessions/{self.session.id}/next/'
        for i in range(5):
            r = self.client.post(url, {})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data.get('action'), 'next_ack')
