import asyncio
from django.test import TestCase
from django.contrib.auth import get_user_model
from unittest.mock import patch
from .consumers import ChatConsumer

User = get_user_model()


class FakeRedis:
    def __init__(self):
        self.rpush_calls = []
        self.storage = {}

    async def rpush(self, key, value):
        self.rpush_calls.append((key, value))

    async def eval(self, *args, **kwargs):
        # Not used in these tests
        return []

    # minimal helpers used elsewhere
    async def hset(self, *a, **k):
        return 1

    async def expire(self, *a, **k):
        return True


class PriorityQueueTests(TestCase):
    def setUp(self):
        self.user_premium = User.objects.create(username='p1', email='p1@example.com', coins=0, is_premium=True)
        self.user_normal = User.objects.create(username='n1', email='n1@example.com', coins=0, is_premium=False)

    def _make_consumer(self, user, channel_name='chan-test'):
        c = ChatConsumer(scope={})
        c.channel_name = channel_name
        c.user = user
        # capture send messages
        c.sent = []

        async def _send(msg):
            c.sent.append(msg)

        c.send = _send
        return c

    def test_premium_goes_to_premium_queue(self):
        fake = FakeRedis()
        consumer = self._make_consumer(self.user_premium, channel_name='chan-prem')
        data = {'mode': 'video', 'profile': {'gender': 'f', 'age': 30, 'location': 'loc'}}

        async def run():
            with patch('chat.consumers.get_redis', return_value=fake):
                await consumer.handle_enqueue(data)

        asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(any(call[0].endswith(':premium') for call in fake.rpush_calls))

    def test_non_premium_goes_to_normal_queue(self):
        fake = FakeRedis()
        consumer = self._make_consumer(self.user_normal, channel_name='chan-norm')
        data = {'mode': 'video', 'profile': {'gender': 'm', 'age': 25, 'location': 'loc'}}

        async def run():
            with patch('chat.consumers.get_redis', return_value=fake):
                await consumer.handle_enqueue(data)

        asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(any(not call[0].endswith(':premium') for call in fake.rpush_calls))
