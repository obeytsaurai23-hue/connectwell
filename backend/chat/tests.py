from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from .models import MatchSession
from accounts.models import WalletTransaction

User = get_user_model()


class ChatUnblurTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        # create two users
        self.user_a = User.objects.create(username='a', email='a@example.com', coins=10)
        self.user_b = User.objects.create(username='b', email='b@example.com', coins=10)
        # for these tests we simulate users who require viewers to pay to unblur
        self.user_a.charge_viewers = True
        self.user_a.save()
        self.user_b.charge_viewers = True
        self.user_b.save()
        # create a session where a and b are participants
        self.session = MatchSession.objects.create(user_a=self.user_a, user_b=self.user_b, user_a_channel='chan_a', user_b_channel='chan_b', unblur_price=5)

    def test_manual_unblur_charges_coins(self):
        # user_b will pay to unblur their own side
        self.client.force_authenticate(user=self.user_b)
        resp = self.client.post(f'/api/v1/sessions/{self.session.id}/unblur/')
        self.assertEqual(resp.status_code, 200)
        self.user_b.refresh_from_db()
        self.assertEqual(self.user_b.coins, 5)  # 10 - 5
        txs = WalletTransaction.objects.filter(user=self.user_b, reason__startswith=f'purchase:unblur:{self.session.id}')
        self.assertTrue(txs.exists())
        self.session.refresh_from_db()
        self.assertTrue(self.session.user_b_unblurred)

    def test_unblur_insufficient_coins(self):
        # user with insufficient coins cannot unblur
        self.user_a.coins = 1
        self.user_a.save()
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.post(f'/api/v1/sessions/{self.session.id}/unblur/')
        self.assertEqual(resp.status_code, 402)
        self.user_a.refresh_from_db()
        self.assertEqual(self.user_a.coins, 1)
        txs = WalletTransaction.objects.filter(user=self.user_a, reason__startswith=f'purchase:unblur:{self.session.id}')
        self.assertFalse(txs.exists())

    def test_auto_purchase_and_unblur_when_enabled(self):
        # user_b has no coins but auto_buy_coins enabled; env AUTO_COMPLETE_PURCHASES will simulate payment
        import os
        os.environ['AUTO_COMPLETE_PURCHASES'] = '1'
        try:
            self.user_b.coins = 0
            self.user_b.auto_buy_coins = True
            self.user_b.auto_buy_pack_id = 'starter'
            self.user_b.save()
            self.client.force_authenticate(user=self.user_b)
            resp = self.client.post(f'/api/v1/sessions/{self.session.id}/unblur/')
            self.assertEqual(resp.status_code, 200)
            self.user_b.refresh_from_db()
            # starter pack gives 25 coins, unblur price is 5, so final should be 20
            self.assertEqual(self.user_b.coins, 20)
            # transactions should include purchase and unblur
            txs_purchase = WalletTransaction.objects.filter(user=self.user_b, reason__startswith='purchase:starter')
            txs_unblur = WalletTransaction.objects.filter(user=self.user_b, reason__startswith=f'purchase:unblur:{self.session.id}')
            self.assertTrue(txs_purchase.exists())
            self.assertTrue(txs_unblur.exists())
        finally:
            del os.environ['AUTO_COMPLETE_PURCHASES']

    def test_unblur_sends_channel_notifications(self):
        # Ensure that when unblur occurs the channel layer send is invoked for both participants
        from types import SimpleNamespace
        from unittest.mock import patch
        recorded = []

        async def fake_send(channel_name, message):
            recorded.append((channel_name, message))

        fake_layer = SimpleNamespace(send=fake_send)
        with patch('chat.views.get_channel_layer', return_value=fake_layer):
            self.client.force_authenticate(user=self.user_b)
            resp = self.client.post(f'/api/v1/sessions/{self.session.id}/unblur/')
            self.assertEqual(resp.status_code, 200)
            # channel send should have been called at least once (for stored channels fallback)
            self.assertTrue(len(recorded) >= 1)
            # verify message payload contains unblur action
            found = False
            for _, msg in recorded:
                text = msg.get('text')
                if text and 'unblur' in text:
                    found = True
            self.assertTrue(found)
