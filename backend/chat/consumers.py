import json
from channels.generic.websocket import AsyncWebsocketConsumer
import redis.asyncio as aioredis
import os
from asgiref.sync import sync_to_async
from .models import MatchSession
from rest_framework_simplejwt.tokens import AccessToken
from accounts.models import User as AccountsUser
from accounts.models import WalletTransaction
from django.db import transaction
# small tidy: removed unused imports (random, async_to_sync)

# Redis queue key prefix
QUEUE_KEY_PREFIX = 'connectwell:queue:'


async def get_redis():
    url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    return aioredis.from_url(url)


PAIR_LUA = '''
-- atomically pop up to two items from list
local key = KEYS[1]
local a = redis.call('LPOP', key)
local b = redis.call('LPOP', key)
local res = {}
if a then table.insert(res, a) end
if b then table.insert(res, b) end
return res
'''


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Validate token from query string (access_token) if provided
        _token = None
        qs = self.scope.get('query_string', b'')
        if qs:
            try:
                qs_decoded = qs.decode()
                # support both token= and access_token= query keys
                if 'token=' in qs_decoded:
                    _token = qs_decoded.split('token=')[-1].split('&')[0]
                elif 'access_token=' in qs_decoded:
                    _token = qs_decoded.split('access_token=')[-1].split('&')[0]
            except Exception:
                _token = None

        self.user = None
        if _token:
            try:
                claims = AccessToken(_token)
                user_id = claims.get('user_id')
                if user_id:
                    try:
                        self.user = await sync_to_async(AccountsUser.objects.get)(pk=user_id)
                    except AccountsUser.DoesNotExist:
                        self.user = None
            except Exception:
                # invalid token -> reject
                await self.close(code=4001)
                return

        await self.accept()

        # store mapping channel -> user_id in Redis for later resolution
        try:
            r = await get_redis()
            if self.user:
                # set a per-channel key with TTL so mappings expire if client disappears
                await r.set(f'connectwell:channel_user:{self.channel_name}', str(self.user.id), ex=300)
                await r.hset('connectwell:channel_user', self.channel_name, str(self.user.id))
                # also set a reverse mapping user->channel for quick lookup
                await r.set(f'connectwell:user_channel:{self.user.id}', self.channel_name, ex=300)
        except Exception:
            pass

    async def disconnect(self, close_code):
        # Remove entry from Redis queue if present
        r = await get_redis()
        # remove any occurrence of this channel from all mode queues
        for mode in ('video', 'text'):
            try:
                await r.lrem(QUEUE_KEY_PREFIX + mode, 0, self.channel_name)
            except Exception:
                pass
        # remove channel->user mapping
        try:
            await r.hdel('connectwell:channel_user', self.channel_name)
            await r.delete(f'connectwell:channel_user:{self.channel_name}')
            # remove reverse mapping if it points to this channel
            try:
                val = await r.get(f'connectwell:user_channel:{self.user.id}') if self.user else None
                if val and val.decode() == self.channel_name:
                    await r.delete(f'connectwell:user_channel:{self.user.id}')
            except Exception:
                pass
        except Exception:
            pass

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or '{}')
        except Exception:
            return
        action = data.get('action')
        if action == 'enqueue':
            await self.handle_enqueue(data)
        elif action == 'signal':
            peer = data.get('peer')
            payload = data.get('payload')
            if peer and payload:
                signal_payload = {
                    'action': 'signal',
                    'from': self.channel_name,
                    'payload': payload,
                }
                await self.channel_layer.send(peer, {
                    'type': 'chat.message',
                    'text': json.dumps(signal_payload),
                })
        elif action == 'next':
            await self.send(json.dumps({'action': 'next_ack'}))
        elif action == 'heartbeat':
            # refresh TTL on channel->user mapping
            try:
                r = await get_redis()
                await r.expire(f'connectwell:channel_user:{self.channel_name}', 300)
            except Exception:
                pass

    async def handle_enqueue(self, data):
        mode = data.get('mode', 'video')
        r = await get_redis()
        key = QUEUE_KEY_PREFIX + mode
        # Push this channel into the tail of the list
        await r.rpush(key, self.channel_name)
        try:
            # Atomically pop up to two items using Lua script
            res = await r.eval(PAIR_LUA, 1, key)
            popped = [p.decode() if isinstance(p, (bytes, bytearray)) else p for p in res]
            if len(popped) < 2:
                # push back any popped items that aren't self
                for p in popped:
                    if p != self.channel_name:
                        await r.lpush(key, p)
                await self.send(json.dumps({'action': 'queued'}))
                return
            # determine peer which is not self
            if popped[0] == self.channel_name:
                peer_channel = popped[1]
            elif popped[1] == self.channel_name:
                peer_channel = popped[0]
            else:
                # we popped two other channels; requeue them and notify queued
                for p in popped:
                    await r.lpush(key, p)
                await self.send(json.dumps({'action': 'queued'}))
                return

            # create MatchSession with optional user references
            user_a = self.user if self.user else None
            # we don't have peer user mapping by channel here; leave user_b None
            create_args = {
                'user_a': user_a,
                'user_b': None,
                'user_a_channel': self.channel_name,
                'user_b_channel': peer_channel,
            }
            session = await sync_to_async(MatchSession.objects.create)(**create_args)

            # Determine initial unblur state based on whether the session owners require viewers to pay.
            # By default a user's video is visible unless that user has `charge_viewers=True`.
            try:
                r = await get_redis()
                # try to resolve both user ids from channel mapping
                user_a_id = await r.hget('connectwell:channel_user', self.channel_name)
                user_b_id = await r.hget('connectwell:channel_user', peer_channel)
                user_a_obj = None
                user_b_obj = None
                if user_a_id:
                    user_a_id = user_a_id.decode() if isinstance(user_a_id, (bytes, bytearray)) else user_a_id
                    try:
                        user_a_obj = await sync_to_async(AccountsUser.objects.get)(pk=user_a_id)
                    except AccountsUser.DoesNotExist:
                        user_a_obj = None
                if user_b_id:
                    user_b_id = user_b_id.decode() if isinstance(user_b_id, (bytes, bytearray)) else user_b_id
                    try:
                        user_b_obj = await sync_to_async(AccountsUser.objects.get)(pk=user_b_id)
                    except AccountsUser.DoesNotExist:
                        user_b_obj = None

                # By default unblurred unless the owner requires viewers to pay
                a_unblurred = not (user_a_obj and getattr(user_a_obj, 'charge_viewers', False))
                b_unblurred = not (user_b_obj and getattr(user_b_obj, 'charge_viewers', False))

                # persist initial state
                def _persist_state():
                    MatchSession.objects.filter(pk=session.pk).update(
                        user_a_unblurred=a_unblurred,
                        user_b_unblurred=b_unblurred,
                    )

                await sync_to_async(_persist_state)()

                # If owner requires viewers to pay (so owner side is blurred),
                # attempt auto-unblur by charging the viewer
                # If viewer has auto_unblur enabled and enough coins, charge and unblur immediately.
                if not a_unblurred and user_b_obj:
                    if user_b_obj.auto_unblur and user_b_obj.coins >= session.unblur_price:
                        def charge_and_unblur_a():
                            with transaction.atomic():
                                user_b_obj.coins -= session.unblur_price
                                user_b_obj.save()
                                WalletTransaction.objects.create(
                                    user=user_b_obj,
                                    amount=-session.unblur_price,
                                    reason=f'purchase:unblur:{session.id}',
                                )
                                s = MatchSession.objects.get(pk=session.pk)
                                s.user_a_unblurred = True
                                s.save()
                        await sync_to_async(charge_and_unblur_a)()
                        # notify both peers that the a side was unblurred
                        try:
                            payload = {
                                'action': 'unblur',
                                'side': 'a',
                                'session_id': str(session.id),
                            }
                            send_msg = {
                                'type': 'chat.message',
                                'text': json.dumps(payload),
                            }
                            await self.channel_layer.send(self.channel_name, send_msg)
                            await self.channel_layer.send(peer_channel, send_msg)
                        except Exception:
                            pass

                if not b_unblurred and user_a_obj:
                    if user_a_obj.auto_unblur and user_a_obj.coins >= session.unblur_price:
                        def charge_and_unblur_b():
                            with transaction.atomic():
                                user_a_obj.coins -= session.unblur_price
                                user_a_obj.save()
                                WalletTransaction.objects.create(
                                    user=user_a_obj,
                                    amount=-session.unblur_price,
                                    reason=f'purchase:unblur:{session.id}',
                                )
                                s = MatchSession.objects.get(pk=session.pk)
                                s.user_b_unblurred = True
                                s.save()
                        await sync_to_async(charge_and_unblur_b)()
                        # notify both peers that the b side was unblurred
                        try:
                            payload = {
                                'action': 'unblur',
                                'side': 'b',
                                'session_id': str(session.id),
                            }
                            send_msg = {
                                'type': 'chat.message',
                                'text': json.dumps(payload),
                            }
                            await self.channel_layer.send(self.channel_name, send_msg)
                            await self.channel_layer.send(peer_channel, send_msg)
                        except Exception:
                            pass
            except Exception:
                pass

            # notify both peers
            match_payload_peer = {
                'action': 'match_found',
                'you': peer_channel,
                'peer': self.channel_name,
                'session_id': str(session.id),
            }
            match_payload_self = {
                'action': 'match_found',
                'you': self.channel_name,
                'peer': peer_channel,
                'session_id': str(session.id),
            }
            send_peer_msg = {'type': 'chat.message', 'text': json.dumps(match_payload_peer)}
            send_self_msg = {'type': 'chat.message', 'text': json.dumps(match_payload_self)}
            await self.channel_layer.send(peer_channel, send_peer_msg)
            await self.channel_layer.send(self.channel_name, send_self_msg)
        except Exception:
            await self.send(json.dumps({'action': 'queued'}))

    async def chat_message(self, event):
        await self.send(event['text'])
