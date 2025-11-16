from django.core.management.base import BaseCommand
import time
import redis
from django.conf import settings
from chat.models import MatchSession

PAIR_LUA = '''
local key = KEYS[1]
local a = redis.call('LPOP', key)
local b = redis.call('LPOP', key)
local res = {}
if a then table.insert(res, a) end
if b then table.insert(res, b) end
return res
'''


class Command(BaseCommand):
    help = 'Simple matchmaker worker: atomically pair channels from Redis queues.'

    def handle(self, *args, **options):
        redis_url = getattr(settings, 'REDIS_URL', None) or 'redis://localhost:6379/0'
        r = redis.from_url(redis_url)
        modes = ['video', 'text']
        self.stdout.write('Starting matchmaker (video & text queues)')
        try:
            while True:
                paired = False
                for mode in modes:
                    key = f'connectwell:queue:{mode}'
                    res = r.eval(PAIR_LUA, 1, key)
                    if res and len(res) == 2:
                        a = res[0].decode() if isinstance(res[0], (bytes, bytearray)) else res[0]
                        b = res[1].decode() if isinstance(res[1], (bytes, bytearray)) else res[1]
                        # create session
                        MatchSession.objects.create(user_a_channel=a, user_b_channel=b)
                        self.stdout.write(f'Paired {a} <-> {b} (mode={mode})')
                        paired = True
                if not paired:
                    time.sleep(0.5)
        except KeyboardInterrupt:
            self.stdout.write('Matchmaker stopped')
